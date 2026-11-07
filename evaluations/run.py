"""Run every trial against the actual agent in a separate process.

Example: python -m evaluations.run --output runs/dev --trials 3
Outputs are append-free immutable run directories. Failed and timed-out runs are
retained, and each has evaluator-owned pre/post state and server journal.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

from fixture_app import TaskBoardFixture
from .grading import grade, load_jsonl
from .metrics import summarize
from .provenance import grade_provenance
from .identity import resolve_local_model
from .tasks import TASKS, public_inputs, requires_exercise

ROOT = Path(__file__).resolve().parents[1]


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def source_fingerprint(paths):
    files = {}
    for folder in paths:
        for path in sorted(folder.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix in {'.py', '.js', '.cjs', '.md', '.json'}:
                files[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'sha256': digest(files), 'files': files}


def run_trial(task, trial_index, output, backend, model_config, timeout, browser_config=None):
    trial_id = f"{task['id']}--{trial_index:03}"
    directory = output / trial_id
    directory.mkdir()
    agent_dir = directory / 'agent'
    agent_dir.mkdir()
    expected_model_config = json.loads(model_config.read_text()) if model_config else {}
    started = time.monotonic()
    process_status = {'state': 'not_started'}
    with TaskBoardFixture(task['mode']) as fixture:
        bug, kb = public_inputs(task, fixture.base_url)
        dump(directory / 'public-bug.json', bug)
        dump(directory / 'public-kb.json', kb)
        # Never place truth in public input or pass the fixture object to the agent.
        dump(directory / 'oracle-private.json', task)
        dump(directory / 'state-before.json', fixture.snapshot())
        command = [sys.executable, '-m', 'bug_validator', 'run', '--bug', str(directory / 'public-bug.json'),
                   '--kb', str(directory / 'public-kb.json'), '--base-url', fixture.base_url,
                   '--output', str(agent_dir), '--backend', backend]
        if model_config:
            command += ['--model-config', str(model_config)]
        if browser_config:
            command += ['--browser-config', str(browser_config)]
        try:
            with (directory / 'stdout.txt').open('w') as stdout, (directory / 'stderr.txt').open('w') as stderr:
                proc = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                        stdin=subprocess.DEVNULL, start_new_session=True)
                try:
                    return_code = proc.wait(timeout=timeout)
                    process_status = {'state': 'exited', 'return_code': return_code}
                except subprocess.TimeoutExpired:
                    # Kill the full process group, so browser children cannot leak into later trials.
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    process_status = {'state': 'timeout', 'return_code': proc.returncode}
        except Exception as exc:
            process_status = {'state': 'launch_error', 'error': f'{type(exc).__name__}: {exc}'}
        final_state, journal = fixture.snapshot(), fixture.audit_log()
        dump(directory / 'state-after.json', final_state)
        dump(directory / 'server-journal.json', journal)
        try:
            report = json.loads((agent_dir / 'report.json').read_text())
            if not isinstance(report, dict):
                raise ValueError('Agent report is not an object')
        except (OSError, ValueError) as exc:
            report = {}
            process_status['report_error'] = str(exc)
        try:
            trace = load_jsonl(agent_dir / 'trace.jsonl')
        except (OSError, ValueError) as exc:
            trace = []
            process_status['trace_error'] = str(exc)
        try:
            grading = grade(task, report, final_state, journal, agent_dir, fixture.base_url, trace)
            grading['checks'].extend(grade_provenance(report, task, backend, agent_dir, bug, kb, ROOT, expected_model_config))
            grading['passed'] = all(c['passed'] for c in grading['checks'])
        except Exception as exc:
            grading = {'passed': False, 'checks': [], 'grader_error': f'{type(exc).__name__}: {exc}', 'semantic_status': 'unverified'}
        process_ok = process_status.get('state') == 'exited' and process_status.get('return_code') == (2 if report.get('verdict') == 'inconclusive' else 0)
        grading['checks'].append({'name': 'agent_process_completed', 'passed': process_ok, 'detail': process_status})
        grading['passed'] = grading['passed'] and process_ok
        dump(directory / 'deterministic-grade.json', grading)
        dump(directory / 'process.json', process_status)
        record = {'task_id': task['id'], 'trial_index': trial_index, 'trial_id': trial_id,
                  'app_mode': task['mode'], 'expected_verdict': task['expected_verdict'],
                  'actual_verdict': report.get('verdict'), 'backend': backend,
                  'deterministic_pass': grading['passed'], 'semantic_status': 'unverified',
                  'elapsed_seconds': round(time.monotonic() - started, 4),
                  'process_status': process_status,
                  'failed_checks': [c['name'] for c in grading['checks'] if not c['passed']]}
        dump(directory / 'trial.json', record)
        # Snapshot integrity manifest is written by the harness after agent termination.
        artifacts = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(directory.rglob('*')) if p.is_file()}
        dump(directory / 'artifact-hashes.json', artifacts)
        return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--backend', choices=['deterministic', 'local-model'], default='deterministic')
    parser.add_argument('--model-config', type=Path)
    parser.add_argument('--browser-config', type=Path)
    parser.add_argument('--task', action='append', choices=[t['id'] for t in TASKS])
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--agent-version', default='working-tree')
    parser.add_argument('--app-version', default='fixture-v1')
    parser.add_argument('--app-behavior', choices=['as-defined', 'buggy', 'fixed'], default='as-defined')
    args = parser.parse_args(argv)
    if not 1 <= args.trials <= 100 or args.timeout <= 0:
        parser.error('Trials must be 1..100; timeout must be positive')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    tasks = [copy.deepcopy(t) for t in TASKS if not args.task or t['id'] in args.task]
    if args.app_behavior != 'as-defined':
        for task in tasks:
            if requires_exercise(task):
                task['mode'] = args.app_behavior
                task['expected_verdict'] = 'confirmed' if args.app_behavior == 'buggy' else 'not_reproduced'
    model_config = args.model_config.resolve() if args.model_config else None
    browser_config = args.browser_config.resolve() if args.browser_config else None
    model_identity = resolve_local_model(json.loads(model_config.read_text()) if model_config else {}) if args.backend == 'local-model' else {'status': 'not_applicable'}
    manifest = {'schema_version': 1, 'created_unix': time.time(), 'suite': 'development-v1',
                'split': 'development', 'holdout_status': 'not_run', 'trial_count_per_task': args.trials,
                'model_identity_before': model_identity,
                'backend': args.backend, 'agent_version': args.agent_version, 'app_version': args.app_version,
                'agent_source': source_fingerprint([ROOT / 'bug_validator', ROOT / 'skills']),
                'app_source': source_fingerprint([ROOT / 'fixture_app']),
                'evaluator_source': source_fingerprint([ROOT / 'evaluations']),
                'app_behavior': args.app_behavior,
                'task_ids': [t['id'] for t in tasks], 'effective_tasks_sha256': digest(tasks),
                'model_config_sha256': hashlib.sha256(model_config.read_bytes()).hexdigest() if model_config else None,
                'browser_config_sha256': hashlib.sha256(browser_config.read_bytes()).hexdigest() if browser_config else None,
                'runtime': {'python': sys.version, 'platform': platform.platform()},
                'separation_limit': 'Process separation and withheld input, not OS filesystem isolation. Agent has no filesystem tools, but the subprocess user can read sibling files.'}
    dump(output / 'manifest.json', manifest)
    records = []
    for task in tasks:
        for index in range(1, args.trials + 1):
            record = run_trial(task, index, output, args.backend, model_config, args.timeout, browser_config)
            records.append(record)
            with (output / 'trials.jsonl').open('a') as stream:
                stream.write(json.dumps(record, sort_keys=True) + '\n')
            print(json.dumps(record), flush=True)
    model_identity_after = resolve_local_model(json.loads(model_config.read_text()) if model_config else {}) if args.backend == 'local-model' else {'status': 'not_applicable'}
    manifest['model_identity_after'] = model_identity_after
    manifest['model_identity_stable'] = model_identity == model_identity_after and model_identity.get('status') in {'verified', 'not_applicable'}
    manifest['source_frozen_through_run'] = manifest['agent_source'] == source_fingerprint([ROOT / 'bug_validator', ROOT / 'skills']) and manifest['app_source'] == source_fingerprint([ROOT / 'fixture_app']) and manifest['evaluator_source'] == source_fingerprint([ROOT / 'evaluations']) and manifest['model_config_sha256'] == (hashlib.sha256(model_config.read_bytes()).hexdigest() if model_config else None) and manifest['browser_config_sha256'] == (hashlib.sha256(browser_config.read_bytes()).hexdigest() if browser_config else None)
    dump(output / 'manifest.json', manifest)
    summary = summarize(records)
    summary['source_frozen_through_run'] = manifest['source_frozen_through_run']
    summary['model_identity_stable'] = manifest['model_identity_stable']
    summary['backend'] = args.backend
    summary['agent_version'] = args.agent_version
    summary['app_version'] = args.app_version
    summary['eligible_for_regression_comparison'] = manifest['source_frozen_through_run'] and manifest['model_identity_stable']
    dump(output / 'summary.json', summary)
    print(json.dumps(summary, indent=2))
    if not summary['eligible_for_regression_comparison']:
        return 2
    return 0 if summary['failures'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
