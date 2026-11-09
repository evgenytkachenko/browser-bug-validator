"""Synthetic artifact tests, not real browser or model quality trials."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from bug_validator.common import file_digest
from evaluations.run import digest
from evaluations.general_integrity import load_general_run
from evaluations.general_run import decision_counts, dump
from evaluations.general_tasks import TASKS, exercise_required, public_inputs
from evaluations.general_run import fingerprint
from evaluations.general_grading import grade
from bug_validator.general import run_agent
from evaluations.general_control import ScriptedControl
from evaluations.holdout import reserve, consume, mark_exposed, freeze_binding
from evaluations.trial_metrics import summarize_trials, failure_category


def sources():
    result = {}
    for key, name in [('agent', 'bug_validator/x.py'), ('fixture', 'fixture_app/x.py'), ('evaluator', 'evaluations/x.json')]:
        files = {name: 'a' * 64}
        result[key] = {'files': files, 'sha256': digest(files)}
    result['evaluator']['files']['evaluations/general_tasks.py'] = file_digest(Path(__file__).resolve().parents[1] / 'evaluations/general_tasks.py')
    result['evaluator']['sha256'] = digest(result['evaluator']['files'])
    return fingerprint()


def make_run(root):
    task = TASKS[9]
    process = {'state': 'exited', 'return_code': 2}
    agent_dir = root / (task['id'] + '--001') / 'agent'
    agent_dir.mkdir(parents=True)
    bug, kb, auth = public_inputs(task, 'http://127.0.0.1:12345')
    report = run_agent(bug, kb, auth, agent_dir, model=ScriptedControl(agent_dir))
    state = {'unrelated': 'unchanged'}
    result = grade(task, report, state, state, [], agent_dir, auth, [], 'scripted-control',
                   source_root=Path(__file__).resolve().parents[1], knowledge_base=kb)
    result['checks'].append({'name': 'agent_process_completed', 'passed': True, 'detail': process})
    row = {'trial_id': 'dev-test--001', 'task_id': 'dev-test', 'trial_index': 1, 'split': 'development', 'family': 'status', 'backend': 'scripted-control', 'expected_verdict': 'inconclusive', 'actual_verdict': 'inconclusive', 'deterministic_pass': True, 'failed_checks': [], 'process_status': process, 'browser_observations': 0, 'browser_started': False, 'model_calls': 0, 'real_model_calls': 0, 'elapsed_seconds': 1, **decision_counts(report)}
    row.update(task_id=task['id'], trial_id=task['id']+'--001', requires_exercise=exercise_required(task))
    manifest = {'suite': 'general-loop-v1', 'schema_version': 1, 'task_ids': [task['id']], 'trials_per_task': 1, 'split': 'development', 'backend': 'scripted-control', 'source_frozen_through_run': True, 'sources': sources(), 'model_identity_stable': True, 'model_identity_before': {'status': 'not_applicable'}}
    trial = root / row['trial_id']
    trial.mkdir(exist_ok=True)
    dump(trial / 'agent/report.json', report)
    dump(trial / 'trial.json', row)
    dump(trial / 'process.json', process)
    dump(trial / 'grade.json', result)
    dump(trial / 'oracle-private.json', task)
    dump(trial / 'public-input.json', {'bug': bug, 'knowledge_base': kb, 'authorization': auth})
    dump(trial / 'state-before.json', state)
    dump(trial / 'state-after.json', state)
    dump(trial / 'server-journal.json', [])
    for name in ('stdout.txt', 'stderr.txt'):
        (trial / name).write_text('')
    rehash(trial)
    dump(root / 'manifest.json', manifest)
    dump(root / 'summary.json', {'trials': 1, 'successes': 1})
    (root / 'trials.jsonl').write_text(json.dumps(row) + '\n')
    return manifest, row, trial


def rehash(trial):
    dump(trial / 'artifact-hashes.json', {p.relative_to(trial).as_posix(): file_digest(p) for p in trial.rglob('*') if p.is_file() and p.name != 'artifact-hashes.json'})


class IntegrityTests(unittest.TestCase):
    def test_valid_baseline_and_complete_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            manifest, row, trial = make_run(root)
            self.assertEqual(load_general_run(root), (manifest, {row['trial_id']: row}))
            (trial / 'extra.txt').write_text('unlisted')
            with self.assertRaises(ValueError): load_general_run(root)

    def test_tamper_missing_duplicate_and_unfrozen(self):
        for mutation in ('tamper', 'missing', 'duplicate', 'unfrozen', 'source', 'incomplete'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                manifest, row, trial = make_run(root)
                if mutation == 'tamper': (trial / 'stdout.txt').write_text('changed')
                elif mutation == 'missing': (trial / 'process.json').unlink()
                elif mutation == 'duplicate': (root / 'trials.jsonl').write_text((json.dumps(row)+'\n')*2)
                elif mutation == 'unfrozen': manifest['source_frozen_through_run'] = False
                elif mutation == 'incomplete': manifest['completed'] = False
                else: manifest['sources']['agent']['files']['bug_validator/x.py'] = 'b'*64
                dump(root / 'manifest.json', manifest)
                with self.assertRaises(ValueError): load_general_run(root)

    def test_row_grade_and_process_rebinding_rejected_even_with_hashes(self):
        for key in ('deterministic_pass', 'actual_verdict', 'model_calls_attempted', 'task_id'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                _, row, trial = make_run(root)
                row[key] = False if key == 'deterministic_pass' else 'forged'
                dump(trial / 'trial.json', row)
                (root / 'trials.jsonl').write_text(json.dumps(row)+'\n')
                rehash(trial)
                with self.assertRaises(ValueError): load_general_run(root)

    def test_missing_hard_gate_and_rehashed_forgery_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            _, _, trial = make_run(root)
            result = json.loads((trial / 'grade.json').read_text())
            result['checks'] = [c for c in result['checks'] if c['name'] == 'agent_process_completed']
            dump(trial / 'grade.json', result)
            rehash(trial)
            with self.assertRaises(ValueError): load_general_run(root)

    def test_summary_duplicate_json_and_unknown_oracle_rejected(self):
        for mutation in ('summary', 'duplicate_key', 'oracle', 'nonfinite'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                _, row, trial = make_run(root)
                if mutation == 'summary':
                    dump(root / 'summary.json', {'trials': 1, 'successes': 1, 'model_calls_attempted': 999})
                elif mutation == 'duplicate_key':
                    text = json.dumps(row)
                    (root / 'trials.jsonl').write_text(text[:-1] + ', "trial_id": "duplicate"}')
                elif mutation == 'nonfinite':
                    row['elapsed_seconds'] = float('nan')
                    (root / 'trials.jsonl').write_text(json.dumps(row))
                else:
                    oracle = json.loads((trial / 'oracle-private.json').read_text())
                    oracle['lineage'] = 'forged'
                    dump(trial / 'oracle-private.json', oracle)
                    rehash(trial)
                with self.assertRaises(ValueError): load_general_run(root)

    def test_path_escape_and_symlink(self):
        for escape in ('../escape', '/tmp/escape', 'agent/../../escape', 'agent\\escape'):
            with self.subTest(escape=escape), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                _, _, trial = make_run(root)
                hashes = json.loads((trial / 'artifact-hashes.json').read_text())
                hashes[escape] = 'a'*64
                dump(trial / 'artifact-hashes.json', hashes)
                with self.assertRaises(ValueError): load_general_run(root)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            _, _, trial = make_run(root)
            (trial / 'stdout.txt').unlink()
            (trial / 'stdout.txt').symlink_to(trial / 'stderr.txt')
            rehash(trial)
            with self.assertRaises(ValueError): load_general_run(root)


class MetricsTests(unittest.TestCase):
    def rows(self):
        return [{'trial_id': f'{task}-{i}', 'task_id': task, 'backend': 'local-model', 'split': 'development', 'deterministic_pass': passed, 'elapsed_seconds': i+1, 'expected_verdict': 'not_reproduced', 'actual_verdict': 'not_reproduced' if passed else 'confirmed', 'model_calls_attempted': 1, 'model_calls_completed': 1, 'real_model_calls_attempted': 1} for task in ('a', 'b') for i, passed in enumerate([True, False, True])]

    def test_finite_sample_estimators_and_denominators(self):
        result = summarize_trials(self.rows(), [1, 2, 3])
        self.assertAlmostEqual(result['repeated_trial_estimates']['2']['pass_at_k'], 1)
        self.assertAlmostEqual(result['repeated_trial_estimates']['2']['pass_power_k'], 1/3)
        self.assertEqual(result['repeated_trial_estimates']['3']['pass_power_k'], 0)
        self.assertEqual(result['false_positives']['confirmed_on_fixed'], 2)
        self.assertEqual(result['denominators']['no_call_refusal_controls']['trials'], 0)

    def test_reject_unequal_repeats_duplicates_and_invalid_k(self):
        for rows, ks in [(self.rows()[:-1], None), (self.rows()*2, None), (self.rows(), [4]), (self.rows(), [True])]:
            with self.assertRaises(ValueError): summarize_trials(rows, ks)
        self.assertEqual(summarize_trials([])['repeated_trial_estimates'], {})

    def test_browser_startup_or_predecision_is_conservative(self):
        row = {'deterministic_pass': False, 'requires_exercise': True,
               'browser_started': False, 'model_calls_attempted': 0}
        self.assertEqual(failure_category(row), 'browser_startup_or_predecision_failure')
        # Early config/preflight rejection is indistinguishable here and deliberately
        # receives a combined category, not a definite infrastructure label.
        self.assertEqual(failure_category({**row, 'failed_checks': ['preflight']}),
                         'browser_startup_or_predecision_failure')
        for key in ('browser_started', 'requires_exercise', 'model_calls_attempted'):
            missing = dict(row)
            del missing[key]
            self.assertEqual(failure_category(missing), 'agent_or_evidence_failure')
        self.assertEqual(failure_category({**row, 'requires_exercise': False}), 'agent_or_evidence_failure')
        self.assertEqual(failure_category({**row, 'model_calls_attempted': 1}), 'model_or_schema_error')
        self.assertEqual(failure_category({**row, 'deterministic_pass': True}), 'passed')

    def test_model_schema_errors_not_infrastructure(self):
        self.assertEqual(failure_category({'model_calls_attempted': 1, 'model_calls_completed': 0}), 'model_or_schema_error')
        self.assertEqual(failure_category({'process_status': {'state': 'timeout'}}), 'execution_timeout_unattributed')
        self.assertEqual(failure_category({'grader_error': 'oops'}), 'harness_grader_error')


class HoldoutTests(unittest.TestCase):
    tasks = [t for t in TASKS if t['split'] == 'reserved-transfer']

    def test_reserve_consume_once_and_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            manifest, _, _ = make_run(root)
            path = root / 'ledger.json'
            reserve(path, root / 'manifest.json', self.tasks)
            binding = freeze_binding(manifest)
            changed = copy.deepcopy(binding)
            changed['model_config_sha256'] = 'b'*64
            with self.assertRaises(ValueError): consume(path, self.tasks, changed, file_digest(root/'manifest.json'), root/'run')
            entry = consume(path, self.tasks, binding, file_digest(root/'manifest.json'), root/'run')
            self.assertEqual(entry['status'], 'consumed')
            with self.assertRaises(ValueError): consume(path, self.tasks, binding, file_digest(root/'manifest.json'), root/'run2')
            with self.assertRaises(ValueError): reserve(path, root/'manifest.json', self.tasks)

    def test_incomplete_freeze_and_subset_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            manifest, _, _ = make_run(root)
            with self.assertRaises(ValueError): reserve(root/'ledger.json', root/'manifest.json', self.tasks[:1])
            manifest.update(integrity_version=1, completed=False)
            dump(root/'manifest.json', manifest)
            with self.assertRaises(ValueError): reserve(root/'ledger.json', root/'manifest.json', self.tasks)

    def test_exposure_prevents_reservation_and_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            make_run(root)
            path = root/'ledger.json'
            mark_exposed(path, self.tasks, 'inspected results')
            with self.assertRaises(ValueError): reserve(path, root/'manifest.json', self.tasks)
            (root/'ledger.json.lock').write_text('')
            with self.assertRaises(ValueError): mark_exposed(path, self.tasks, 'again')


if __name__ == '__main__':
    unittest.main()
