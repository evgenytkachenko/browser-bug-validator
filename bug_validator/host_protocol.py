"""File mailbox for an existing host agent; no model API or automatic policy.

The authoritative controller lives in one Python process. Mailbox nonces prevent
accidental stale/replayed submissions, not malicious same-user filesystem edits.
Host/model identity is self-reported and never qualifies model-quality claims.
"""
from __future__ import annotations

import json
import os
import re
import stat
import time
import uuid
from pathlib import Path

from .common import ValidationError, digest
from .general_contracts import require
from .schemas import validate_response

PROTOCOL = 'host-selected-action-v1'
MAX_JSON_BYTES = 262144
TOKEN = re.compile(r'[0-9a-f]{32}\Z')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def read_json(path, limit=MAX_JSON_BYTES):
    """Bounded regular-file-only JSON read; reject symlinks and duplicate keys."""
    path = Path(path)
    require(not path.is_symlink(), 'Symlink JSON input is not permitted')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'JSON input must be a regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit, 'JSON byte budget exceeded')
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=lambda _value: (_ for _ in ()).throw(ValidationError('Nonfinite JSON value')))
    finally:
        os.close(fd)


def atomic_json(path, data, *, exclusive=False):
    path = Path(path)
    raw = (json.dumps(data, allow_nan=False, indent=2, sort_keys=True) + '\n').encode('utf-8')
    require(len(raw) <= MAX_JSON_BYTES, 'JSON byte budget exceeded')
    require(not path.is_symlink(), 'Symlink output is not permitted')
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            # Hard-link installation is atomic and never overwrites a prior response.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_status(run_dir):
    root = Path(run_dir)
    require(root.is_dir() and not root.is_symlink(), 'Run directory must be a real directory')
    control = root / 'control'
    require(control.is_dir() and not control.is_symlink(), 'Control directory must be a real directory')
    result = read_json(control / 'current.json')
    require(type(result) is dict and result.get('protocol') == PROTOCOL, 'Unknown host protocol')
    return result


def submit(run_dir, request_id, decision):
    """Submit once to the currently waiting request; never advances the browser."""
    require(type(request_id) is str and TOKEN.fullmatch(request_id), 'Invalid request ID')
    status = read_status(run_dir)
    require(status.get('state') == 'waiting' and status.get('request_id') == request_id,
            'Request is stale, unknown, or no longer waiting')
    require(status.get('request_sha256') == digest(status['request']), 'Request hash mismatch')
    response = {'protocol': PROTOCOL, 'session_id': status['session_id'], 'request_id': request_id,
                'request_sha256': status['request_sha256'], 'answer': decision}
    atomic_json(Path(run_dir) / 'control' / ('response-' + request_id + '.json'), response, exclusive=True)
    return {'protocol': PROTOCOL, 'state': 'submitted', 'request_id': request_id,
            'note': 'Submission is not execution or a verified verdict; poll next for controller status.'}


class HostDecisionSource:
    """Only transports host-selected decisions. There is no fallback decision rule."""
    def __init__(self, run_dir, *, host, decision_origin='host-session', session_label=None):
        require(host in {'codex', 'claude', 'other'}, 'Unknown host label')
        require(decision_origin in {'host-session', 'scripted-control'}, 'Unknown decision origin')
        require(session_label is None or (type(session_label) is str and 1 <= len(session_label) <= 200),
                'Invalid session label')
        self.root = Path(run_dir)
        require(self.root.is_dir() and not self.root.is_symlink(), 'Create a fresh run directory first')
        self.control = self.root / 'control'
        self.control.mkdir(exist_ok=False)
        self.output_dir = self.root / 'agent'
        self.session_id = uuid.uuid4().hex
        self.identity = {'claimed_host': host, 'session_label': session_label,
                         'decision_origin': decision_origin, 'verification': 'self-reported-not-authenticated',
                         'model_quality_claim_eligible': False}
        self.calls = []
        self.timeout = 600
        self.closed = False
        self._status('starting')

    def _status(self, state, **fields):
        atomic_json(self.control / 'current.json', {'protocol': PROTOCOL, 'state': state,
            'session_id': self.session_id, 'host_identity': self.identity, **fields})

    def ask(self, stage, system, payload, schema):
        require(not self.closed, 'Host source is closed')
        request = {'stage': stage, 'system': system, 'payload': payload, 'schema': schema}
        request_id = uuid.uuid4().hex
        artifact = f'host-{len(self.calls) + 1:03d}.json'
        call = {'id': artifact[:-5], 'stage': stage, 'backend': 'host-selected-actions',
                'status': 'pending', 'artifact': artifact, 'request_id': request_id,
                'session_id': self.session_id, 'request_sha256': digest(request)}
        self.calls.append(call)
        self._status('waiting', request_id=request_id, request_sha256=digest(request), request=request)
        deadline = time.monotonic() + self.timeout
        response_file = self.control / ('response-' + request_id + '.json')
        response = None
        try:
            while not response_file.exists() and not response_file.is_symlink():
                require(time.monotonic() < deadline, 'Host decision time budget exceeded')
                time.sleep(min(.05, max(0, deadline - time.monotonic())))
            require(time.monotonic() < deadline, 'Host decision time budget exceeded')
            response = read_json(response_file, 16384)
            require(type(response) is dict and set(response) == {'protocol', 'session_id', 'request_id', 'request_sha256', 'answer'},
                    'Malformed host response envelope')
            require(response['protocol'] == PROTOCOL and response['session_id'] == self.session_id
                    and response['request_id'] == request_id and response['request_sha256'] == digest(request),
                    'Host response is not bound to the active request')
            validate_response(response['answer'], schema)
            call.update(status='completed', answer=response['answer'], response_sha256=digest(response))
            self._status('accepted', request_id=request_id)
            return response['answer']
        except (Exception, KeyboardInterrupt) as exc:
            call.update(status='failed', error=f'{type(exc).__name__}: {str(exc)[:1000]}')
            self._status('rejected', request_id=request_id, error=call['error'])
            raise
        finally:
            atomic_json(self.output_dir / artifact, {'kind': 'host-selected-actions', 'identity': self.identity,
                'request': request, 'response': response, 'call': call})

    def complete(self, report):
        self.closed = True
        self._status('completed', verdict=report['verdict'], report='agent/report.json',
                     limitations=report.get('limitations', []))
