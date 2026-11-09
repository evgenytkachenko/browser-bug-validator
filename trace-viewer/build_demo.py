"""Regenerate this curated, text-only historical demo. No models or browser run.

Only the exact pinned fictional source records are accepted. This is not a
privacy scrubber for arbitrary runs. See README before sharing new evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
CASES = [
    ('fixed', 'dev-02-fixed--001', 'Fixed behavior', 'The app was fixed. The model said otherwise.',
     'The saved status remained done after reload. v0.2 proposed a false positive; its safeguard stopped that verdict. v0.3 checked extracted facts and mapped them to not_reproduced in code.'),
    ('persistence', 'dev-01-persistence-bug--001', 'Persistence bug', 'A saved change did not survive reload.',
     'Both versions observed done after save and todo after reload. The fixture server independently recorded the lost change. Both final reports confirmed this controlled defect.'),
    ('missing-target', 'dev-06-missing-target--001', 'Missing target', 'Stopping is sometimes the correct result.',
     'Neither version had the required target. Both stopped before model or browser execution. This is an input-refusal control, not a successful browser reproduction.'),
]
FILES = ['agent/report.json', 'agent/trace.jsonl', 'public-bug.json', 'deterministic-grade.json', 'server-journal.json', 'state-before.json', 'state-after.json', 'trial.json']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def clean(value):
    if isinstance(value, str):
        return re.sub(r'http://127\.0\.0\.1:\d+', '[local fixture]', value)
    if isinstance(value, list):
        return [clean(x) for x in value]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    return value


def pick(value, keys):
    return {k: clean(value[k]) for k in keys if k in value}


def collect(root, trial_id, pins):
    directory = root / trial_id
    # Pin source bytes before extraction. Never accept an arbitrary run as sanitized.
    for name, expected in pins.items():
        path = directory / name
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f'Source differs from reviewed historical input: {trial_id}/{name}')
    report = read(directory / 'agent/report.json')
    trial = read(directory / 'trial.json')
    bug = read(directory / 'public-bug.json')
    trace_path = directory / 'agent/trace.jsonl'
    trace = [json.loads(line) for line in trace_path.read_text().splitlines()] if trace_path.exists() else []
    if trace:
        if digest(trace_path) != report['provenance']['trace_sha256']:
            raise ValueError('Recorded trace hash does not match report')
        if [event['index'] for event in trace] != list(range(1, len(trace) + 1)):
            raise ValueError('Controller events are not ordered')
        observations = [{k: v for k, v in event.items() if k not in ['index', 'timestamp', 'type']} for event in trace if event['type'] == 'observation']
        if observations != report['observations']:
            raise ValueError('Report observations are not bound to trace')
    elif report['observations'] or report['steps']:
        raise ValueError('Browser evidence has no controller trace')
    result = pick(report, ['agent_version', 'backend', 'verdict', 'summary', 'steps', 'assertions', 'limitations', 'model_assessment', 'assessment_mapping', 'elapsed_seconds', 'started_at'])
    result['trial_id'] = trial_id
    result['bug'] = pick(bug, ['id', 'title', 'description', 'expected', 'expected_status', 'target_task_id'])
    result['model_calls'] = [pick(c, ['id', 'stage', 'model', 'status', 'elapsed_seconds', 'prompt_tokens', 'output_tokens']) for c in report['model_calls']]
    result['observations'] = [pick(o, ['id', 'phase', 'visible_text', 'values', 'screenshot_sha256']) for o in report['observations']]
    result['events'] = [pick(e, ['index', 'timestamp', 'type', 'action', 'id', 'phase', 'url', 'method', 'status', 'allowed', 'completed', 'observation_ids']) for e in trace]
    result['grade'] = pick(read(directory / 'deterministic-grade.json'), ['passed', 'semantic_status', 'checks', 'limitations'])
    result['server'] = {
        'before': read(directory / 'state-before.json')['tasks'],
        'after': read(directory / 'state-after.json')['tasks'],
        'journal': [pick(e, ['index', 'method', 'path', 'status_code', 'effect', 'body']) for e in read(directory / 'server-journal.json')],
        'expected_verdict': trial['expected_verdict'],
    }
    result['source_hashes'] = pins
    result['browser_runtime'] = report['provenance'].get('browser_runtime')
    result['screenshot_status'] = 'not_included_not_visually_verified'
    return clean(result)


def build(baseline, candidate):
    provenance = read(ROOT / 'provenance.json')
    manifests = []
    for label, directory in [('v02', baseline), ('v03', candidate)]:
        if digest(directory / 'manifest.json') != provenance['runs'][label]['manifest_sha256']:
            raise ValueError('Run manifest differs from reviewed source')
        manifests.append(read(directory / 'manifest.json'))
    comparability = {}
    for key in ['app_source', 'evaluator_source', 'effective_tasks_sha256']:
        left = manifests[0][key]
        right = manifests[1][key]
        comparability[key] = {'same': left == right, 'baseline': left.get('sha256') if isinstance(left, dict) else left, 'candidate': right.get('sha256') if isinstance(right, dict) else right}
    digests = [m['model_identity_before']['digest'] for m in manifests]
    comparability['model_artifact'] = {'same': digests[0] == digests[1], 'baseline': digests[0], 'candidate': digests[1]}
    cases = []
    for id_, trial, title, headline, lesson in CASES:
        cases.append({'id': id_, 'title': title, 'headline': headline, 'lesson': lesson,
                      'runs': [collect(baseline, trial, provenance['runs']['v02']['trials'][trial]), collect(candidate, trial, provenance['runs']['v03']['trials'][trial])]})
    return {'schema_version': 1, 'title': 'Browser bug validator · Trace explorer', 'base_commit': provenance['base_commit'], 'comparability': comparability, 'cases': cases}


def write_bundle(data):
    serialized = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    (ROOT / 'demo.json').write_text(serialized)
    # Static, offline-safe classic script. No fetch, interpolation, or HTML parsing.
    safe = serialized.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    (ROOT / 'demo-data.js').write_text('"use strict";\nwindow.TRACE_DATA = ' + safe.rstrip() + ';\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    write_bundle(build(args.baseline, args.candidate))
    print('Built 3 historical comparisons. Screenshot pixels absent; no new trial or grading run.')


if __name__ == '__main__':
    main()
