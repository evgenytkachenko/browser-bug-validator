"""Controlled host-session harness, separate from scripted integration controls.

Only synthetic local fixtures are started. Independent fixture state, journal,
checks, and author-visible expected outcomes are withheld from decision requests.
The shared filesystem is not a security boundary. Host identity is self-reported;
this harness does not launch or authenticate Claude/Codex or call model services.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import threading
import time

from bug_validator.common import digest, file_digest, write_json
from bug_validator.general import run_agent
from bug_validator.host_protocol import HostDecisionSource, read_json, read_status, submit
from fixture_app.general_server import GeneralFixture
from .general_control import ScriptedControl
from .general_grading import grade
from .general_run import fingerprint
from .general_tasks import TASKS, public_inputs, exercise_required

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT = [task for task in TASKS if task['split'] == 'development']


def run_case(task, output, *, host, browser_config=None, scripted=False, session_label=None):
    """Block while an external host selects actions, or label the scripted control."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started_sources = fingerprint()
    origin = 'scripted-control' if scripted else 'host-session'
    backend = 'scripted-host-control' if scripted else 'host-session'
    manifest = {'schema_version': 1, 'suite': 'host-controlled-development-v1',
                'backend': backend, 'completed': False, 'task_id': task['id'],
                'host_identity_verification': 'self-reported-not-authenticated',
                'model_quality_claim_eligible': False, 'sources': started_sources,
                'browser_config_sha256': digest(browser_config or {}),
                'limitations': ['Author-visible synthetic cases, not a blind benchmark.',
                    'Expected results are withheld from host request payloads, not OS-isolated from the host.',
                    'Host/model identity and session label are self-reported, not authenticated.',
                    'Scripted controls are transport/browser integration evidence, never Claude/Codex success.']}
    write_json(output / 'manifest.json', manifest)
    source = HostDecisionSource(output, host=host, decision_origin=origin, session_label=session_label)
    stop_event = threading.Event()
    control_errors = []
    responder = None
    with GeneralFixture(task['family'], task['mode'], query=task.get('query', 'alpha'),
                        expected_status=task.get('expected_status', 'done'), quantity=task.get('quantity', -2)) as fixture:
        bug, kb, auth = public_inputs(task, fixture.base_url)
        write_json(output / 'public-input.json', {'bug': bug, 'knowledge_base': kb, 'authorization': auth})
        before = fixture.snapshot()
        if scripted:
            control_dir = output / 'scripted-control'
            control_dir.mkdir()
            policy = ScriptedControl(control_dir)
            def respond():
                seen = set()
                while not stop_event.wait(.02):
                    try:
                        current = read_status(output)
                        if current['state'] != 'waiting' or current['request_id'] in seen:
                            continue
                        seen.add(current['request_id'])
                        request = current['request']
                        answer = policy.ask(request['stage'], request['system'], request['payload'], request['schema'])
                        submit(output, current['request_id'], answer)
                    except Exception as exc:
                        control_errors.append(f'{type(exc).__name__}: {exc}')
                        break
            responder = threading.Thread(target=respond, daemon=True)
            responder.start()
        try:
            report = run_agent(bug, kb, auth, output / 'agent', browser_config=browser_config, host_source=source)
        finally:
            stop_event.set()
            if responder:
                responder.join(timeout=2)
        after, journal = fixture.snapshot(), fixture.audit_log()
    # Oracle facts are saved after interaction, never in host request payloads.
    write_json(output / 'oracle-private.json', task)
    write_json(output / 'state-before.json', before)
    write_json(output / 'state-after.json', after)
    write_json(output / 'server-journal.json', journal)
    trace_file = output / 'agent/trace.jsonl'
    trace = [json.loads(line) for line in trace_file.read_text().splitlines()] if trace_file.exists() else []
    result = grade(task, report, before, after, journal, output / 'agent', auth, trace, backend,
                   source_root=ROOT, knowledge_base=kb)
    source_frozen = started_sources == fingerprint()
    result['checks'] += [{'name': 'source_frozen_through_run', 'passed': source_frozen, 'detail': source_frozen},
                         {'name': 'scripted_responder_clean', 'passed': not control_errors, 'detail': control_errors}]
    result['passed'] = all(check['passed'] for check in result['checks'])
    result['backend'] = backend
    result['host_identity'] = source.identity
    result['model_quality_claim_eligible'] = False
    write_json(output / 'grade.json', result)
    manifest.update(completed=True, source_frozen_through_run=source_frozen,
                    host_identity=source.identity, verdict=report['verdict'], deterministic_pass=result['passed'])
    write_json(output / 'manifest.json', manifest)
    write_json(output / 'artifact-hashes.json', {str(path.relative_to(output)): file_digest(path)
                for path in sorted(output.rglob('*')) if path.is_file()})
    return {'case': task['id'], 'backend': backend, 'declared_host': host, 'verdict': report['verdict'],
            'deterministic_pass': result['passed'], 'model_quality_claim_eligible': False,
            'decision_calls': len(report['model_calls']), 'browser_observations': len(report['observations']),
            'browser_started': bool(report.get('provenance', {}).get('browser_runtime', {}).get('browser')),
            'exercise_required': exercise_required(task),
            'finished_assessment': any(call.get('status') == 'completed' and call.get('answer', {}).get('action_id') == 'finish' for call in report['model_calls']),
            'failed_checks': [check['name'] for check in result['checks'] if not check['passed']],
            'output': str(output)}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'verify':
        from .host_integrity import verify_case
        check = argparse.ArgumentParser(description='Regrade one exact completed host trial')
        check.add_argument('--run-dir', type=Path, required=True)
        args = check.parse_args(argv[1:])
        try:
            result = verify_case(args.run_dir)
            print(json.dumps(result))
            return 0 if result['deterministic_pass'] else 1
        except (ValueError, OSError, KeyError, TypeError) as exc:
            print(json.dumps({'verified': False, 'error': str(exc)}), file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser(description=__doc__, epilog='Regrade a completed case: python -m evaluations.host_control verify --run-dir PATH')
    parser.add_argument('command', choices=['serve', 'scripted'])
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--case', action='append', choices=[task['id'] for task in DEVELOPMENT])
    parser.add_argument('--host', choices=['codex', 'claude', 'other'], required=True)
    parser.add_argument('--session-label')
    parser.add_argument('--browser-config', type=Path)
    args = parser.parse_args(argv)
    tasks = [task for task in DEVELOPMENT if not args.case or task['id'] in args.case]
    if args.command == 'serve' and len(tasks) != 1:
        parser.error('serve requires exactly one --case; launch a fresh process/directory per host session')
    config = read_json(args.browser_config, 16000) if args.browser_config else None
    try:
        if args.command == 'serve':
            row = run_case(tasks[0], args.run_dir, host=args.host, browser_config=config, session_label=args.session_label)
            print(json.dumps(row))
            return 0 if row['deterministic_pass'] else 1
        args.run_dir.mkdir(parents=True, exist_ok=False)
        rows = []
        for task in tasks:
            row = run_case(task, args.run_dir / task['id'], host=args.host, browser_config=config,
                           scripted=True, session_label=args.session_label)
            rows.append(row)
            print(json.dumps(row), flush=True)
        browser_started = sum(row['browser_started'] for row in rows)
        summary = {'backend': 'scripted-host-control', 'trials': len(rows),
                   'passes': sum(row['deterministic_pass'] for row in rows), 'rows': rows,
                   'model_quality_claim_eligible': False,
                   'browser_started_trials': browser_started,
                   'trials_with_decisions': sum(row['decision_calls'] > 0 for row in rows),
                   'completed_exercise_trials': sum(row['exercise_required'] and row['deterministic_pass'] for row in rows),
                   'expected_refusal_passes': sum(not row['exercise_required'] and row['deterministic_pass'] for row in rows),
                   'finished_assessment_trials': sum(row['finished_assessment'] for row in rows),
                   'qualification': ('Scripted host-mailbox integration attempts; browser participation is reported separately. Not Claude/Codex performance.' if browser_started else 'No browser started. Only preflight/launch behavior tested; no host decision or model-quality evidence.')}
        write_json(args.run_dir / 'summary.json', summary)
        print(json.dumps(summary))
        return 0 if all(row['deterministic_pass'] for row in rows) else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'error': f'{type(exc).__name__}: {exc}'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
