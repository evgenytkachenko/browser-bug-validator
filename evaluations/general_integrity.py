"""Verify general-loop run consistency. Same-writer hashes are NOT signatures."""
import json
import re
from math import isfinite
from pathlib import Path, PurePosixPath
from bug_validator.common import file_digest
from .run import digest


def safe_path(root, name):
    if not isinstance(name, str) or not name or '\\' in name or PurePosixPath(name).is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('Unsafe artifact path')
    path = root / name
    if any(part.is_symlink() for part in [path, *path.parents] if part != root.parent):
        raise ValueError('Symlink artifacts are not supported')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Artifact escapes run')
    return path


def parse_json(text):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate JSON key')
            obj[key] = value
        return obj
    return json.loads(text, object_pairs_hook=unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def read_json(path):
    try:
        return parse_json(path.read_text())
    except (OSError, TypeError) as exc:
        raise ValueError(f'Unreadable artifact: {path.name}') from exc


def validate_sources(sources):
    if not isinstance(sources, dict) or set(sources) != {'agent', 'fixture', 'evaluator'}:
        raise ValueError('Missing source fingerprints')
    for key, prefix in [('agent', 'bug_validator/'), ('fixture', 'fixture_app/'), ('evaluator', 'evaluations/')]:
        entry = sources[key]
        files = entry.get('files', {})
        if not files or entry.get('sha256') != digest(files):
            raise ValueError('Invalid source inventory digest')
        for name, sha in files.items():
            if not name.startswith(prefix) or any(part in ('', '.', '..') for part in name.split('/')) or '\\' in name or not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
                raise ValueError('Invalid source inventory entry')


def verify_hashes(root, hashes, excluded):
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('Missing artifact hashes')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()} - set(excluded)
    if actual != set(hashes):
        raise ValueError('Artifact inventory mismatch')
    for name, sha in hashes.items():
        path = safe_path(root, name)
        if not path.is_file() or not isinstance(sha, str) or file_digest(path) != sha:
            raise ValueError(f'Artifact hash mismatch: {name}')


def _load_general_run(directory):
    """Return (manifest, trial-ID mapping), rejecting incomplete or unfrozen runs."""
    root = Path(directory).absolute()
    manifest = read_json(safe_path(root, 'manifest.json'))
    if manifest.get('suite') != 'general-loop-v1' or manifest.get('schema_version') != 1:
        raise ValueError('Not a supported general-loop run')
    if 'integrity_version' in manifest and (manifest['integrity_version'] != 1 or manifest.get('completed') is not True):
        raise ValueError('Unsupported or incomplete integrity manifest')
    if manifest.get('source_frozen_through_run') is not True or manifest.get('completed', True) is not True:
        raise ValueError('Incomplete or source-unfrozen run')
    validate_sources(manifest.get('sources'))
    grader_source = Path(__file__).with_name('general_grading.py')
    if manifest['sources']['evaluator']['files'].get('evaluations/general_grading.py') != file_digest(grader_source):
        raise ValueError('Grader source version differs; use matching evaluator')
    task_source = Path(__file__).with_name('general_tasks.py')
    if manifest['sources']['evaluator']['files'].get('evaluations/general_tasks.py') != file_digest(task_source):
        raise ValueError('Task source version differs; use the matching evaluator to validate this archive')
    from .general_tasks import TASKS, exercise_required
    canonical_tasks = {t['id']: t for t in TASKS}
    if manifest.get('backend') not in {'local-model', 'scripted-control'}:
        raise ValueError('Invalid backend')
    n, tasks = manifest.get('trials_per_task'), manifest.get('task_ids')
    if type(n) is not int or not 1 <= n <= 100 or not isinstance(tasks, list) or not tasks or any(not isinstance(t, str) or not re.fullmatch('[A-Za-z0-9_-]+', t) for t in tasks) or len(set(tasks)) != len(tasks):
        raise ValueError('Invalid trial schedule')
    expected = {f'{task}--{i:03}': (task, i) for task in tasks for i in range(1, n+1)}
    try:
        lines = safe_path(root, 'trials.jsonl').read_text().splitlines()
        rows = [parse_json(line) for line in lines if line.strip()]
    except (OSError, ValueError) as exc:
        raise ValueError('Missing or malformed trial rows') from exc
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Trial row must be an object')
        trial_id = row.get('trial_id')
        if trial_id not in expected or trial_id in result:
            raise ValueError('Unexpected or duplicate trial')
        for key in ('trial_index', 'model_calls', 'real_model_calls', 'browser_observations',
                    'model_calls_attempted', 'model_calls_completed', 'real_model_calls_attempted', 'real_model_calls_completed'):
            if type(row.get(key)) is not int or row[key] < 0:
                raise ValueError('Invalid trial counter')
        latency = row.get('elapsed_seconds')
        if type(latency) not in (int, float) or not isfinite(latency) or latency < 0:
            raise ValueError('Invalid trial latency')
        for key in ('browser_started', 'requires_exercise', 'finished_with_assessment'):
            if type(row.get(key)) is not bool:
                raise ValueError('Invalid trial flag')
        trial = safe_path(root, trial_id)
        hashes = read_json(safe_path(trial, 'artifact-hashes.json'))
        verify_hashes(trial, hashes, {'artifact-hashes.json'})
        required = {'trial.json', 'grade.json', 'process.json', 'public-input.json', 'oracle-private.json', 'state-before.json', 'state-after.json', 'server-journal.json', 'stdout.txt', 'stderr.txt'}
        if not required <= set(hashes):
            raise ValueError('Missing required trial artifacts')
        grade = read_json(trial / 'grade.json')
        process = read_json(trial / 'process.json')
        oracle = read_json(trial / 'oracle-private.json')
        if row != read_json(trial / 'trial.json') or row.get('process_status') != process or type(row.get('deterministic_pass')) is not bool or row['deterministic_pass'] != grade.get('passed'):
            raise ValueError('Trial/grade/process binding mismatch')
        if (row.get('task_id'), row.get('trial_index')) != expected[trial_id] or row.get('backend') != manifest['backend'] or row.get('split') != manifest.get('split'):
            raise ValueError('Trial schedule binding mismatch')
        if oracle != canonical_tasks.get(row.get('task_id')):
            raise ValueError('Oracle differs from source-bound canonical task')
        if row.get('requires_exercise') != exercise_required(oracle):
            raise ValueError('Exercise denominator mismatch')
        if row.get('grader_error') != grade.get('grader_error'):
            raise ValueError('Grader error mismatch')
        for key in ('family', 'split', 'expected_verdict'):
            if row.get(key) != oracle.get(key):
                raise ValueError('Oracle binding mismatch')
        if oracle.get('id') != row['task_id']:
            raise ValueError('Oracle task mismatch')
        checks = grade.get('checks')
        if not isinstance(checks, list) or any(type(c.get('passed')) is not bool for c in checks) or row.get('failed_checks') != [c['name'] for c in checks if not c['passed']]:
            raise ValueError('Grade checks mismatch')
        if row['deterministic_pass'] and (not checks or not all(c['passed'] for c in checks) or grade.get('grader_error')):
            raise ValueError('Invalid passing grade')
        report = read_json(trial / 'agent/report.json') if 'agent/report.json' in hashes and not process.get('report_error') else {}
        from .general_run import decision_counts
        for key, value in decision_counts(report).items():
            if row.get(key) != value:
                raise ValueError('Decision accounting mismatch')
        expected_counts = {'model_calls': len(report.get('model_calls', [])),
                           'real_model_calls': sum(c.get('backend') == 'ollama' for c in report.get('model_calls', [])),
                           'browser_started': bool(report.get('provenance', {}).get('browser_runtime', {}).get('browser'))}
        if any(row.get(key) != value for key, value in expected_counts.items()):
            raise ValueError('Report participation mismatch')
        expected_sources = {Path(name).name: sha for name, sha in manifest['sources']['agent']['files'].items()
                            if len(Path(name).parts) == 2 and Path(name).suffix in {'.py', '.cjs'}}
        source_checks = [c for c in checks if c.get('name') == 'agent_source_binding']
        if source_checks and (len(source_checks) != 1 or source_checks[0]['passed'] != (report.get('provenance', {}).get('source_sha256') == expected_sources)):
            raise ValueError('Agent source check mismatch')
        if row.get('actual_verdict') != report.get('verdict') or row.get('browser_observations') != len(report.get('observations', [])):
            raise ValueError('Report binding mismatch')
        if not grade.get('grader_error'):
            from .general_grading import grade as regrade
            public = read_json(trial / 'public-input.json')
            trace_path = trial / 'agent/trace.jsonl'
            trace = [parse_json(line) for line in trace_path.read_text().splitlines() if line.strip()] if trace_path.exists() else []
            recomputed = regrade(oracle, report, read_json(trial / 'state-before.json'),
                                read_json(trial / 'state-after.json'), read_json(trial / 'server-journal.json'),
                                trial / 'agent', public['authorization'], trace, manifest['backend'],
                                knowledge_base=public['knowledge_base'])
            skip = {'agent_source_binding', 'invoked_model_config_binding', 'agent_process_completed'}
            recorded = [(c['name'], c['passed']) for c in checks if c['name'] not in skip]
            if recorded != [(c['name'], c['passed']) for c in recomputed['checks']]:
                raise ValueError('Recorded grade differs from replayed objective checks')
            if len(source_checks) != 1 or (manifest['backend'] == 'local-model' and len([c for c in checks if c['name'] == 'invoked_model_config_binding']) != 1):
                raise ValueError('Missing source or model binding checks')
        ok = process.get('state') == 'exited' and process.get('return_code') == (2 if report.get('verdict') == 'inconclusive' else 0)
        bound = [c for c in checks if c.get('name') == 'agent_process_completed']
        if len(bound) != 1 or bound[0]['passed'] != ok or bound[0].get('detail') != process:
            raise ValueError('Process grade mismatch')
        result[trial_id] = row
    if set(result) != set(expected):
        raise ValueError('Incomplete trial schedule')
    summary = read_json(safe_path(root, 'summary.json'))
    if summary.get('trials') != len(rows) or summary.get('successes') != sum(r['deterministic_pass'] for r in rows):
        raise ValueError('Summary binding mismatch')
    from .metrics import summarize
    from .trial_metrics import summarize_trials
    from .general_run import participation_summary
    derived = {**summarize(rows), **participation_summary(rows)}
    # Extended metric definitions evolve independently of immutable trial evidence.
    # Replay them only with their recorded implementation; otherwise the preserved
    # summary remains hash-bound, not certified against a different metric version.
    if manifest['sources']['evaluator']['files'].get('evaluations/trial_metrics.py') == file_digest(Path(__file__).with_name('trial_metrics.py')):
        derived.update(summarize_trials(rows))
    # Older v1 summaries omit extended metrics; validate all recorded derived fields.
    for key, value in derived.items():
        if key != 'limitations' and key in summary and summary[key] != value:
            raise ValueError(f'Summary derived metric mismatch: {key}')
    if manifest.get('integrity_version') == 1:
        verify_hashes(root, read_json(safe_path(root, 'run-artifact-hashes.json')), {'run-artifact-hashes.json'})
    return manifest, result


def load_general_run(directory):
    """Validate a complete general-loop-v1 run; return manifest and trial mapping.

    This checks local same-writer consistency, not authenticity or an independently
    trusted/signature-backed result. A matching task-source version is required.
    """
    try:
        return _load_general_run(directory)
    except (OSError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError(f'Malformed general run: {type(exc).__name__}') from exc
