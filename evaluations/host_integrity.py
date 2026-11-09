"""Replay host decision/evidence binding. Consistency checks, not signatures.

The fixture's state/journal and public contract are the outcome oracle. A hash
inventory catches corruption, not a malicious writer who replaces all artifacts.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from bug_validator.common import digest, file_digest
from bug_validator.general_contracts import decision_schema
from bug_validator.host_protocol import PROTOCOL, read_json
from bug_validator.schemas import validate_response
from .general_integrity import safe_path, verify_hashes, validate_sources


def request_binding_errors(report, authorization, output, knowledge_base=None):
    """Bind each request to already captured observations, not caller assertions."""
    from bug_validator.general import SYSTEM, validate_inputs
    errors = []
    output = Path(output)
    observations, steps, calls = report.get('observations', []), report.get('steps', []), report.get('model_calls', [])
    counts, captured, consumed, terminal = {}, [], 0, False
    max_steps = authorization.get('budgets', {}).get('max_steps', 12)
    for index, call in enumerate(calls):
        try:
            if terminal:
                raise ValueError('Decision after a terminal or failed action')
            artifact = read_json(safe_path(output, call['artifact']))
            request = artifact['request']
            payload = request['payload']
            if request['stage'] != 'decide' or request['system'] != SYSTEM or digest(payload['bug']) != authorization['bug_sha256']:
                raise ValueError('Decision system/report binding mismatch')
            if knowledge_base is not None:
                selected, _ = validate_inputs(payload['bug'], knowledge_base)
                if payload['knowledge_base'] != selected:
                    raise ValueError('Decision knowledge differs from retrieval')
            available = {key: action for key, action in authorization['actions'].items()
                         if counts.get(key, 0) < action.get('max_uses', 1 if 'request' in action else 2) and consumed < max_steps}
            if consumed == 0:
                available = {key: action for key, action in available.items() if action['kind'] == 'navigate'}
            ready = len(captured) == len(authorization['checkpoints'])
            required_ids = [row['observation_id'] for row in captured] if ready else []
            if ready:
                available = {}
            current = copy.deepcopy(observations[consumed - 1]) if consumed else None
            if current:
                current['visible_text'] = current['visible_text'][:3000]
            expected = {'phase': 'assessment' if ready else 'action', 'required_evidence_ids': required_ids,
                        'next_checkpoint': None if ready else authorization['checkpoints'][len(captured)],
                        'capabilities': [{'id': key, 'kind': action['kind'], 'description': action['description'],
                                         **({'value': action['value']} if 'value' in action else {})} for key, action in available.items()],
                        'checkpoints': authorization['checkpoints'], 'current_observation': current,
                        'history': steps[:consumed], 'checkpoint_results': captured,
                        'remaining_steps': max_steps - consumed}
            if set(payload) != set(expected) | {'bug', 'knowledge_base'} or any(payload.get(key) != value for key, value in expected.items()):
                raise ValueError('Host request does not match prior observations/actions/phase')
            schema = decision_schema(available, required_ids, completion_ready=ready)
            if request['schema'] != schema:
                raise ValueError('Host request schema differs from permitted actions/evidence')
            if artifact.get('call') != call or call.get('request_sha256') != digest(request):
                raise ValueError('Host request/call hash mismatch')
            if call.get('status') != 'completed':
                terminal = True
                continue
            response = artifact['response']
            if (set(response) != {'protocol', 'session_id', 'request_id', 'request_sha256', 'answer'}
                    or response['protocol'] != PROTOCOL or response['session_id'] != report['provenance']['host_session_id']
                    or response['request_id'] != call['request_id'] or response['request_sha256'] != digest(request)
                    or digest(response) != call.get('response_sha256') or response['answer'] != call.get('answer')):
                raise ValueError('Host response envelope mismatch')
            answer = call['answer']
            validate_response(answer, schema)
            action = answer['action_id']
            if action in {'finish', 'stop'}:
                terminal = True
                continue
            counts[action] = counts.get(action, 0) + 1
            if consumed == len(observations):
                # An accepted action can fail in the browser, but cannot yield success.
                if report.get('verdict') != 'inconclusive':
                    raise ValueError('Action lacks an actual observation')
                terminal = True
                continue
            observation = observations[consumed]
            if observation.get('after_action') != action or steps[consumed] != {
                    'index': consumed + 1, 'action_id': action, 'status': 'completed', 'observation_id': observation['id']}:
                raise ValueError('Host action does not match its completed observation')
            consumed += 1
            if len(captured) < len(authorization['checkpoints']):
                checkpoint = authorization['checkpoints'][len(captured)]
                if checkpoint['after_action'] == action:
                    checks = []
                    for predicate in checkpoint['checks']:
                        actual, value = observation['values'][predicate['probe']], predicate['value']
                        met = actual == value if predicate['op'] == 'equals' else actual != value if predicate['op'] == 'not_equals' else isinstance(actual, str) and value in actual
                        checks.append({**predicate, 'actual': actual, 'met': met})
                    captured.append({'id': checkpoint['id'], 'after_action': action, 'observation_id': observation['id'], 'checks': checks})
        except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
            errors.append(f'Call {index + 1}: {exc}')
            break
    if consumed != len(observations) or consumed != len(steps):
        errors.append('Observations/steps have no one-to-one host decision source')
    return errors


def verify_case(directory):
    """Regrade an exact completed archive; reject missing, changed, or added files."""
    from .general_grading import grade
    from .general_tasks import TASKS, public_inputs
    from .general_run import fingerprint
    root = Path(directory).absolute()
    hashes = read_json(safe_path(root, 'artifact-hashes.json'))
    verify_hashes(root, hashes, {'artifact-hashes.json'})
    manifest = read_json(safe_path(root, 'manifest.json'))
    if (manifest.get('suite') != 'host-controlled-development-v1' or manifest.get('completed') is not True
            or manifest.get('source_frozen_through_run') is not True
            or manifest.get('backend') not in {'host-session', 'scripted-host-control'}
            or manifest.get('model_quality_claim_eligible') is not False):
        raise ValueError('Incomplete, unqualified, or mislabeled host run')
    validate_sources(manifest['sources'])
    if manifest['sources'] != fingerprint():
        raise ValueError('Source version differs; verify using the exact producing source')
    task = next((task for task in TASKS if task['id'] == manifest['task_id'] and task['split'] == 'development'), None)
    if task is None or read_json(root / 'oracle-private.json') != task:
        raise ValueError('Expected outcome does not match the author-visible canonical case')
    public = read_json(root / 'public-input.json')
    bug, kb, auth = public_inputs(task, public['authorization']['origin'])
    if public != {'bug': bug, 'knowledge_base': kb, 'authorization': auth}:
        raise ValueError('Public inputs differ from the independently authored case')
    report = read_json(root / 'agent/report.json')
    current = read_json(root / 'control/current.json')
    if (current.get('state') != 'completed' or current.get('verdict') != report.get('verdict')
            or current.get('session_id') != report.get('provenance', {}).get('host_session_id')
            or current.get('host_identity') != manifest.get('host_identity')
            or manifest.get('host_identity') != report.get('provenance', {}).get('host_identity')):
        raise ValueError('Final host status and manifest are not bound to the report')
    trace_path = root / 'agent/trace.jsonl'
    trace = [json.loads(line) for line in trace_path.read_text().splitlines()] if trace_path.exists() else []
    result = grade(task, report, read_json(root / 'state-before.json'), read_json(root / 'state-after.json'),
                   read_json(root / 'server-journal.json'), root / 'agent', auth, trace, manifest['backend'],
                   source_root=Path(__file__).resolve().parents[1], knowledge_base=kb)
    saved = read_json(root / 'grade.json')
    records = saved.get('checks')
    if (not isinstance(records, list) or any(not isinstance(row, dict) or not isinstance(row.get('name'), str)
            or type(row.get('passed')) is not bool for row in records)
            or len({row['name'] for row in records}) != len(records)):
        raise ValueError('Malformed or duplicated saved grade checks')
    actual_checks = {row['name']: row['passed'] for row in result['checks']}
    extras = {row['name']: row for row in records if row['name'] in {'source_frozen_through_run', 'scripted_responder_clean'}}
    if (set(extras) != {'source_frozen_through_run', 'scripted_responder_clean'}
            or extras['source_frozen_through_run']['passed'] is not True
            or extras['source_frozen_through_run'].get('detail') is not True
            or not isinstance(extras['scripted_responder_clean'].get('detail'), list)
            or extras['scripted_responder_clean']['passed'] is not (not extras['scripted_responder_clean']['detail'])):
        raise ValueError('Recorded source/responder checks are inconsistent')
    saved_checks = {row['name']: row['passed'] for row in records if row['name'] not in extras}
    combined_pass = result['passed'] and all(row['passed'] for row in extras.values())
    if (actual_checks != saved_checks or saved.get('passed') != combined_pass
            or manifest.get('deterministic_pass') != combined_pass or manifest.get('verdict') != report.get('verdict')
            or saved.get('backend') != manifest['backend'] or saved.get('host_identity') != manifest['host_identity']
            or saved.get('model_quality_claim_eligible') is not False):
        raise ValueError('Saved grading/manifest disagrees with independent replay')
    return {'verified': True, 'deterministic_pass': combined_pass, 'backend': manifest['backend'],
            'verdict': report['verdict'], 'model_quality_claim_eligible': False}
