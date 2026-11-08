"""Synthetic unit tests of CI gating, not browser or model measurements."""
from copy import deepcopy
import unittest

from ci.verify_control import validate_control
from evaluations.general_tasks import TASKS


class CiControlTests(unittest.TestCase):
    def setUp(self):
        tasks = [t for t in TASKS if t['split'] == 'development']
        self.manifest = {'completed': True, 'backend': 'scripted-control', 'split': 'development',
                         'task_ids': [t['id'] for t in tasks], 'trials_per_task': 1,
                         'source_frozen_through_run': True, 'model_quality_claim_eligible': False}
        self.rows = {t['id'] + '--001': {'deterministic_pass': True, 'real_model_calls_attempted': 0,
                    'real_model_calls_completed': 0, 'browser_observations': 1,
                    'browser_started': not (t.get('deny_mutation') or t.get('omit_requirement') or False)} for t in tasks}

    def test_complete_scripted_control(self):
        receipt = validate_control(self.manifest, self.rows)
        self.assertEqual((receipt['trials'], receipt['real_browser_trials']), (11, 9))
        self.assertFalse(receipt['model_quality_claim'])

    def test_invalid_manifests(self):
        for patch in [{'completed': False}, {'backend': 'local-model'}, {'split': 'reserved-transfer'},
                      {'task_ids': self.manifest['task_ids'][:-1]}, {'trials_per_task': 2},
                      {'source_frozen_through_run': False}, {'model_quality_claim_eligible': True}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_control({**self.manifest, **patch}, self.rows)

    def test_missing_trial(self):
        self.rows.pop('dev-01-status-bug--001')
        with self.assertRaises(ValueError):
            validate_control(self.manifest, self.rows)

    def test_failed_trial(self):
        self.rows['dev-01-status-bug--001']['deterministic_pass'] = False
        with self.assertRaises(ValueError):
            validate_control(self.manifest, self.rows)

    def test_real_model_attempts_or_completions_rejected(self):
        for key in ('real_model_calls_attempted', 'real_model_calls_completed'):
            rows = deepcopy(self.rows)
            rows['dev-01-status-bug--001'][key] = 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_control(self.manifest, rows)

    def test_missing_browser_evidence_rejected(self):
        for patch in [{'browser_started': False}, {'browser_observations': 0}]:
            rows = deepcopy(self.rows)
            rows['dev-01-status-bug--001'].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_control(self.manifest, rows)

    def test_refusal_must_not_start_browser(self):
        self.rows['dev-10-unacknowledged-write--001']['browser_started'] = True
        with self.assertRaises(ValueError):
            validate_control(self.manifest, self.rows)
