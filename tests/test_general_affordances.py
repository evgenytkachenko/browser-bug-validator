"""Existing browser/evidence invariants exposed in the model contract.

Injected model/browser tests and58 exact rc3 replies, not new model-quality data.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from bug_validator.general import run_agent
from bug_validator.general_contracts import decision_schema
from bug_validator.common import ValidationError
from bug_validator.schemas import validate_response
from test_general_loop import FakeBrowser, inputs, decision
from test_general_phases import PhaseCaptureModel


class GeneralAffordanceTests(unittest.TestCase):
    def run_case(self, answers, mutate=None):
        bug, kb, auth = inputs()
        if mutate:
            mutate(auth)
        model = PhaseCaptureModel(answers)
        instances = []
        def factory(*args):
            instance = FakeBrowser(*args)
            instances.append(instance)
            return instance
        with tempfile.TemporaryDirectory() as tmp:
            report = run_agent(bug, kb, auth, tmp, model=model, browser_factory=factory)
        return report, model, instances

    def test_all58_actual_rc3_replies_preserve_their_outcome_constraints(self):
        rows = json.loads((Path(__file__).parent / 'fixtures/v04_rc3_decisions.json').read_text())
        self.assertEqual(len(rows), 58)
        self.assertEqual(sum(row['valid_affordance_contract'] for row in rows), 42)
        self.assertEqual(sum(not row['valid_affordance_contract'] and row['completion_ready'] for row in rows), 10)
        for row in rows:
            answer = json.loads(row['raw_content'])
            original = copy.deepcopy(answer)
            ids = [a['id'] for a in row['capabilities'] if row['current_observation_present'] or a['kind'] == 'navigate']
            schema = decision_schema(ids, row['required_evidence_ids'], completion_ready=row['completion_ready'])
            with self.subTest(source=row['source_artifact']):
                if row['valid_affordance_contract']:
                    validate_response(answer, schema)
                else:
                    with self.assertRaises(ValidationError):
                        validate_response(answer, schema)
                self.assertEqual(answer, original, 'Never populate missing references or fix actions')

    def test_initial_schema_exposes_only_navigation_then_unlocks_interaction(self):
        report, model, _ = self.run_case([decision('open'), decision('search'), decision('finish', 'not_reproduced', ['obs-0001', 'obs-0002'])])
        self.assertEqual(report['verdict'], 'not_reproduced')
        self.assertEqual(model.schemas[0]['properties']['action_id']['enum'], ['open', 'stop'])
        self.assertEqual([a['id'] for a in model.payloads[0]['capabilities']], ['open'])
        self.assertIn('search', model.schemas[1]['properties']['action_id']['enum'])

    def test_initial_non_navigation_choice_is_rejected_before_tool_execution(self):
        report, _, browsers = self.run_case([decision('search')])
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertEqual(browsers[0].steps, [])

    def test_multiple_arbitrary_navigation_ids_remain_model_choices(self):
        def mutate(auth):
            original = auth['actions'].pop('open')
            auth['actions']['inspect_first'] = copy.deepcopy(original)
            auth['actions']['inspect_other'] = copy.deepcopy(original)
            auth['checkpoints'][0]['after_action'] = 'inspect_first'
        report, model, browsers = self.run_case([decision('stop')], mutate)
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertEqual(model.schemas[0]['properties']['action_id']['enum'], ['inspect_first', 'inspect_other', 'stop'])
        self.assertEqual(browsers[0].steps, [])

    def test_no_navigation_grant_offers_only_safe_stop(self):
        def mutate(auth):
            auth['actions']['open'] = {'kind': 'observe', 'description': 'Observe only'}
        report, model, browsers = self.run_case([decision('stop')], mutate)
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertEqual(model.schemas[0]['properties']['action_id']['enum'], ['stop'])
        self.assertEqual(browsers[0].steps, [])

    def test_assessment_requires_checkpoints_not_intermediate_observations(self):
        def mutate(auth):
            auth['budgets']['max_steps'] = 3
        report, model, _ = self.run_case([decision('open'), decision('open'), decision('search'),
            decision('finish', 'not_reproduced', ['obs-0003', 'obs-0001'])], mutate)
        self.assertEqual(report['verdict'], 'not_reproduced')
        self.assertEqual(model.payloads[-1]['required_evidence_ids'], ['obs-0001', 'obs-0003'])
        evidence = model.schemas[-1]['properties']['evidence_ids']
        self.assertEqual((evidence['minItems'], evidence['maxItems']), (2, 2))
        self.assertEqual(evidence['items']['enum'], ['obs-0001', 'obs-0003'])
        self.assertTrue(evidence['uniqueItems'])

    def test_missing_extra_duplicate_and_fabricated_citations_remain_rejected(self):
        for refs in [['obs-0002'], ['obs-0001', 'obs-0001'], ['obs-0001', 'invented'], ['obs-0001', 'obs-0002', 'obs-0003']]:
            with self.subTest(refs=refs):
                report, _, browsers = self.run_case([decision('open'), decision('search'), decision('finish', 'not_reproduced', refs)])
                self.assertEqual(report['verdict'], 'inconclusive')
                self.assertEqual(len(browsers[0].steps), 2)

    def test_assessment_stop_with_exact_citations_is_inconclusive(self):
        report, _, _ = self.run_case([decision('open'), decision('search'), decision('stop', 'inconclusive', ['obs-0001', 'obs-0002'])])
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertTrue(any(s.startswith('Model stopped:') for s in report['limitations']))

    def test_assessment_stop_with_missing_citations_is_not_repaired(self):
        report, _, _ = self.run_case([decision('open'), decision('search'), decision('stop', 'inconclusive', [])])
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertTrue(any('array length' in s for s in report['limitations']))
        self.assertFalse(any(s.startswith('Model stopped:') for s in report['limitations']))


if __name__ == '__main__':
    unittest.main()
