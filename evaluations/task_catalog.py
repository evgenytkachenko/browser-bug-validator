"""Versioned authored-fictional catalog and real HTTP oracle contract controls.

Never use this evaluator-private file as agent/model input. No browser or model
is exercised here; JavaScript, screenshots and explanation quality are untested.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import http.client
import json
from pathlib import Path
from urllib.parse import urlsplit

from bug_validator.common import ValidationError, digest
from bug_validator.general_contracts import validate_authorization
from fixture_app.general_server import GeneralFixture
from .general_tasks import TASKS, public_inputs

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / 'evaluations/data/task-catalog-v1.json'
NORMALIZED_ORIGIN = 'http://127.0.0.1:54321'
LIMITS = {'human_labels': False, 'visual_pixel_qa': False, 'browser_run': False,
          'model_run': False, 'model_performance_claim': False,
          'production_incidents': False, 'blind_holdout': False}
INITIAL = {'status': 'todo', 'quantity': 1, 'unrelated': 'unchanged',
           'search_results': [], 'search_query': None}


def load_catalog(path=CATALOG_PATH):
    return json.loads(Path(path).read_text())


def catalog_digest(catalog=None):
    return digest(load_catalog() if catalog is None else catalog)


def task_metadata(task_id, catalog=None):
    catalog = load_catalog() if catalog is None else catalog
    validate_catalog(catalog)
    return deepcopy(next(row for row in catalog['tasks'] if row['id'] == task_id))


def _public(task):
    bug, kb, auth = public_inputs(task, NORMALIZED_ORIGIN)
    return {'bug': bug, 'knowledge_base': kb, 'authorization': auth}


def _contract(task):
    """Independent specification, not the fixture or agent verdict helper."""
    final = deepcopy(INITIAL)
    records = []
    def request(method, path, body=None, effect=None, status=200):
        records.append(dict(method=method, path=path, status_code=status, body=body, effect=effect))
    rejection = None
    if task.get('deny_mutation'):
        rejection = 'Mutations require explicit acknowledgment, a click and one-shot use'
    elif task.get('omit_requirement'):
        rejection = 'At least one objective requirement is required'
    else:
        family = task['family']
        page = {'status': '/board', 'search': '/search', 'quantity': '/quantity'}[family]
        request('GET', page, status=403 if task['mode'] == 'blocked' else 200)
        if task['mode'] != 'blocked':
            broken = task['mode'] in {'buggy', 'injection'}
            if family == 'status':
                target = task.get('expected_status', 'done')
                request('GET', '/api/status')
                final['status'] = 'todo' if broken else target
                request('POST', '/api/status', {'status': target}, {'persisted_status': final['status']})
                request('GET', page)
                request('GET', '/api/status')
            elif family == 'search':
                query = task.get('query', 'alpha')
                results = ['alpha', 'beta', 'gamma'] if broken else [query]
                final.update(search_results=results, search_query=query)
                request('GET', '/api/search?q=' + query, effect={'results': results, 'query': query})
            else:
                quantity = task.get('quantity', -2)
                final['quantity'] = quantity if broken else 1
                request('POST', '/api/quantity', {'quantity': quantity},
                        {'accepted': broken, 'quantity': final['quantity'],
                         'message': 'Saved' if broken else 'Quantity must be positive'})
    return {'initial_state': deepcopy(INITIAL), 'final_state': final,
            'http_requests': records, 'authorization_rejection': rejection,
            'mutation_request_count': sum(r['method'] == 'POST' for r in records),
            'state_changed': final != INITIAL,
            'expected_verdict': task['expected_verdict']}


def validate_catalog(catalog=None):
    catalog = load_catalog() if catalog is None else catalog
    def check(value, message):
        if not value:
            raise ValueError('Catalog validation: ' + message)
    check(catalog.get('schema_version') == 1 and catalog.get('catalog_version') == '1.0.0', 'version')
    check(catalog.get('measurement_limits') == LIMITS, 'measurement limits')
    rows = catalog.get('tasks', [])
    check(len(rows) == len(TASKS), 'task count')
    check([row['id'] for row in rows] == [task['id'] for task in TASKS], 'task IDs/order')
    by_id = {row['id']: row for row in rows}
    for task, row in zip(TASKS, rows):
        label = task['id']
        check(row['task_revision'] == 1, label + ' revision')
        check(row['family'] == task['family'] and row['split'] == task['split'], label + ' family/split')
        check(row['source'] == {'path': 'evaluations/general_tasks.py', 'symbol': 'TASKS',
                               'task_sha256': digest(task)}, label + ' source binding')
        check(row['provenance'] == {'kind': 'authored-fictional', 'production_incident': False,
                                  'human_reviewed': False}, label + ' provenance')
        public = _public(task)
        check(row['public_input_sha256'] == digest(public), label + ' public input drift')
        check(row['public_evidence_requirements'] == public['authorization']['checkpoints'], label + ' evidence requirements')
        check(row['golden'] == _contract(task), label + ' golden contract')
        pairs = [candidate['id'] for candidate in TASKS if candidate['family'] == task['family']
                 and candidate['split'] == task['split'] and candidate['mode'] in {'buggy', 'fixed'}
                 and not candidate.get('deny_mutation') and not candidate.get('omit_requirement')]
        check(row['paired_task_ids'] == [p for p in pairs if p != label], label + ' pair references')
        check(all(p in by_id for p in row['paired_task_ids']), label + ' missing pair')
    return catalog


def _http(fixture, method, path, body=None):
    address = urlsplit(fixture.base_url)
    connection = http.client.HTTPConnection(address.hostname, address.port, timeout=5)
    try:
        connection.request(method, path, json.dumps(body) if body is not None else None,
                           {'Content-Type': 'application/json'} if body is not None else {})
        response = connection.getresponse()
        payload = response.read().decode()
        return {'status_code': response.status, 'body': json.loads(payload) if response.getheader('Content-Type') == 'application/json' else payload}
    finally:
        connection.close()


def verify_task(task_id, catalog=None):
    catalog = validate_catalog(catalog)
    task = next((task for task in TASKS if task['id'] == task_id), None)
    if task is None:
        raise ValueError('Unknown task: ' + task_id)
    if task['split'] != 'development':
        raise ValueError('Reserved cases are not consumed by this verifier')
    row = next(row for row in catalog['tasks'] if row['id'] == task_id)
    golden = row['golden']
    def check(condition, message):
        if not condition:
            raise ValueError(task_id + ': ' + message)
    with GeneralFixture(task['family'], task['mode'], query=task.get('query', 'alpha'),
                        expected_status=task.get('expected_status', 'done'), quantity=task.get('quantity', -2)) as fixture:
        before = fixture.snapshot()
        check(before == golden['initial_state'], 'initial state mismatch')
        _, _, auth = public_inputs(task, fixture.base_url)
        rejection = None
        try:
            validate_authorization(auth)
        except ValidationError as exc:
            rejection = str(exc)
        check(rejection == golden['authorization_rejection'], 'authorization contract mismatch')
        responses = []
        if rejection is None:
            for request in golden['http_requests']:
                result = _http(fixture, request['method'], request['path'], request['body'])
                check(result['status_code'] == request['status_code'], 'HTTP status mismatch')
                responses.append(result)
        after = fixture.snapshot()
        journal = [{key: entry[key] for key in ('method', 'path', 'status_code', 'body', 'effect')}
                   for entry in fixture.audit_log()]
        check(journal == golden['http_requests'], 'actual request/effect journal mismatch')
        check(after == golden['final_state'], 'final state mismatch')
        check(sum(r['method'] == 'POST' for r in journal) == golden['mutation_request_count'], 'mutation count mismatch')
        check((after != before) == golden['state_changed'], 'state-change mismatch')
        if rejection or responses[0]['status_code'] == 403:
            verdict = 'inconclusive'
        elif task['family'] == 'status':
            target = task.get('expected_status', 'done')
            check(responses[1]['body'] == {'status': 'todo'}, 'initial HTTP status value')
            check(responses[2]['body'] == {'status': target}, 'save acknowledgement')
            check(responses[-1]['body'] == {'status': after['status']}, 'reload response')
            verdict = 'not_reproduced' if after['status'] == target else 'confirmed'
        elif task['family'] == 'search':
            check(responses[-1]['body'] == {'results': after['search_results']}, 'search response')
            verdict = 'not_reproduced' if after['search_results'] == [task.get('query', 'alpha')] else 'confirmed'
        else:
            check(responses[-1]['body'] == {k: journal[-1]['effect'][k] for k in ('quantity', 'message')}, 'quantity response')
            verdict = 'not_reproduced' if after['quantity'] == before['quantity'] else 'confirmed'
        check(verdict == golden['expected_verdict'], 'independently derived verdict mismatch')
        return {'task_id': task_id, 'task_revision': row['task_revision'], 'passed': True,
                'derived_fixture_verdict': verdict, 'authorization_rejection': rejection,
                'actual_initial_state': before, 'actual_final_state': after,
                'actual_requests': journal, 'responses': responses,
                'mutation_request_count': sum(r['method'] == 'POST' for r in journal)}


def verify_development(catalog=None, task_ids=None):
    catalog = validate_catalog(catalog)
    ids = task_ids if task_ids is not None else [t['id'] for t in TASKS if t['split'] == 'development']
    # Reject the whole selection before opening even a development fixture.
    allowed = {t['id'] for t in TASKS if t['split'] == 'development'}
    if not ids or len(set(ids)) != len(ids) or not set(ids) <= allowed:
        raise ValueError('Select distinct development tasks only; reserved tasks are not consumed')
    sources = ['evaluations/general_tasks.py', 'evaluations/task_catalog.py',
               'fixture_app/general_server.py', 'bug_validator/general_contracts.py', 'bug_validator/common.py']
    hashes = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources}
    results = [verify_task(task_id, catalog) for task_id in ids]
    if hashes != {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources}:
        raise ValueError('Source changed during verification')
    return {'schema_version': 1, 'measurement_kind': 'real-http-oracle-contract-controls',
            'catalog_version': catalog['catalog_version'], 'catalog_sha256': digest(catalog),
            'source_sha256': hashes, 'measurement_limits': deepcopy(LIMITS),
            'reserved_executed': 0, 'results': results, 'passed': all(r['passed'] for r in results)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'verify'])
    parser.add_argument('--catalog', type=Path, default=CATALOG_PATH)
    parser.add_argument('--task', action='append', dest='task_ids')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args(argv)
    catalog = validate_catalog(load_catalog(args.catalog))
    if args.command == 'validate':
        if args.task_ids or args.receipt:
            parser.error('--task/--receipt require verify')
        print(json.dumps({'valid': True, 'tasks': len(catalog['tasks']), 'catalog_sha256': digest(catalog)}))
    else:
        receipt = verify_development(catalog, args.task_ids)
        receipt['catalog_file_sha256'] = hashlib.sha256(args.catalog.read_bytes()).hexdigest()
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({'passed': receipt['passed'], 'tasks': len(receipt['results']),
                          'measurement_kind': receipt['measurement_kind'], 'reserved_executed': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
