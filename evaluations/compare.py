"""Compare complete, provenance-bound runs along exactly one change axis."""
import argparse
import hashlib
import json
from pathlib import Path
import re

REQUIRED_MANIFEST = {'schema_version','suite','split','task_ids','trial_count_per_task','backend',
    'agent_version','app_version','agent_source','app_source','evaluator_source','app_behavior',
    'effective_tasks_sha256','model_config_sha256','browser_config_sha256','source_frozen_through_run',
    'model_identity_before','model_identity_stable'}


def load_run(directory, require_comparable=True):
    manifest = json.loads((directory / 'manifest.json').read_text())
    if not isinstance(manifest, dict) or not REQUIRED_MANIFEST <= set(manifest) or manifest['schema_version'] != 1:
        raise ValueError('Missing or unsupported manifest fields')
    if require_comparable and (manifest['source_frozen_through_run'] is not True or manifest['model_identity_stable'] is not True):
        raise ValueError('Source/model identity was not verified stable through the run')
    ids, n = manifest['task_ids'], manifest['trial_count_per_task']
    if not isinstance(ids, list) or not ids or any(not isinstance(v, str) for v in ids) or len(set(ids)) != len(ids) or type(n) is not int or n < 1:
        raise ValueError('Invalid task IDs or trial count')
    for key in ['agent_source','app_source','evaluator_source']:
        source = manifest[key]
        if not isinstance(source, dict) or not source.get('files') or not isinstance(source.get('sha256'), str):
            raise ValueError(f'Missing {key} fingerprint')
        expected = hashlib.sha256(json.dumps(source['files'], sort_keys=True).encode()).hexdigest()
        if source['sha256'] != expected:
            raise ValueError(f'{key} fingerprint does not match its file map')
    records = {}
    rows = (directory / 'trials.jsonl').read_text().splitlines()
    for line in rows:
        row = json.loads(line)
        if not isinstance(row, dict) or not {'trial_id','task_id','trial_index','actual_verdict','expected_verdict','deterministic_pass','backend'} <= set(row):
            raise ValueError('Missing trial fields')
        trial_id = row['trial_id']
        if not isinstance(trial_id, str) or not re.fullmatch('[A-Za-z0-9_-]+', trial_id) or trial_id in records:
            raise ValueError('Invalid or duplicate trial ID')
        if row['task_id'] not in ids or type(row['trial_index']) is not int or not 1 <= row['trial_index'] <= n:
            raise ValueError('Unexpected task or trial index')
        if trial_id != f"{row['task_id']}--{row['trial_index']:03}":
            raise ValueError('Trial ID does not bind task and index')
        if type(row['deterministic_pass']) is not bool or row['backend'] != manifest['backend']:
            raise ValueError('Invalid outcome or inconsistent backend')
        trial_dir = directory / trial_id
        hashes = json.loads((trial_dir / 'artifact-hashes.json').read_text())
        if not isinstance(hashes, dict) or not {'trial.json','deterministic-grade.json','process.json','state-before.json','state-after.json','server-journal.json','oracle-private.json','public-bug.json','public-kb.json'} <= set(hashes):
            raise ValueError('Missing trial integrity manifest')
        for filename, expected_hash in hashes.items():
            path = (trial_dir / filename).resolve()
            if not path.is_relative_to(trial_dir.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                raise ValueError(f'Trial artifact integrity failure: {trial_id}/{filename}')
        if json.loads((trial_dir / 'trial.json').read_text()) != row:
            raise ValueError('Aggregate trial row differs from immutable trial record')
        if json.loads((trial_dir / 'deterministic-grade.json').read_text()).get('passed') is not row['deterministic_pass']:
            raise ValueError('Outcome differs from deterministic grade')
        records[trial_id] = row
    if len(records) != len(ids) * n:
        raise ValueError('Incomplete or empty run')
    expected_ids = {f'{task_id}--{index:03}' for task_id in ids for index in range(1,n+1)}
    if set(records) != expected_ids:
        raise ValueError('Repeated indices or missing trials')
    return manifest, records


def compare(before, after, axis):
    if axis not in {'agent','app'}:
        raise ValueError('axis must be agent or app')
    try:
        left, a = load_run(before)
        right, b = load_run(after)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {'comparable':False, 'axis':axis, 'reasons':[str(exc)], 'regressions':None}
    errors = []
    common = ['suite','split','task_ids','trial_count_per_task','evaluator_source']
    for field in common:
        if left[field] != right[field]:
            errors.append(f'{field} differs')
    if axis == 'agent':
        for field in ['app_source','app_behavior','app_version','effective_tasks_sha256','browser_config_sha256']:
            if left[field] != right[field]:
                errors.append(f'Application/oracle changed: {field}')
    else:
        for field in ['agent_source','agent_version','backend','model_config_sha256','browser_config_sha256']:
            if left[field] != right[field]:
                errors.append(f'Agent changed: {field}')
        if left['backend'] == 'local-model' or right['backend'] == 'local-model':
            if left['model_identity_before'].get('status') != 'verified' or right['model_identity_before'].get('status') != 'verified' or left['model_identity_before'].get('digest') != right['model_identity_before'].get('digest'):
                errors.append('Immutable agent model identity is changed or unverified')
    if set(a) != set(b):
        errors.append('Trial IDs differ')
    if errors:
        return {'comparable':False, 'axis':axis, 'reasons':errors, 'regressions':None}
    changes = [{'trial_id':key, 'before_verdict':a[key]['actual_verdict'], 'after_verdict':b[key]['actual_verdict'],
                'before_correct':a[key]['deterministic_pass'], 'after_correct':b[key]['deterministic_pass'],
                'before_expected':a[key]['expected_verdict'], 'after_expected':b[key]['expected_verdict']}
               for key in a if a[key]['actual_verdict'] != b[key]['actual_verdict'] or a[key]['deterministic_pass'] != b[key]['deterministic_pass']]
    regressions = [key for key in a if a[key]['deterministic_pass'] and not b[key]['deterministic_pass']]
    return {'comparable':True, 'axis':axis, 'changes':changes, 'agent_correctness_regressions':regressions,
            'interpretation':('Same application/oracle; changed agent correctness.' if axis == 'agent' else
                'Same agent; changed application behavior. A verdict change can be correct and is not by itself an agent regression.'),
            'semantic_comparison':'unverified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path); parser.add_argument('after', type=Path)
    parser.add_argument('--axis', choices=['agent','app'], required=True); parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = compare(args.before, args.after, args.axis)
    value = json.dumps(result, indent=2)+'\n'
    if args.output:
        if args.output.exists():
            raise ValueError('Refusing to overwrite comparison result')
        args.output.write_text(value)
    print(value)
    return 0 if result['comparable'] else 2

if __name__ == '__main__':
    raise SystemExit(main())
