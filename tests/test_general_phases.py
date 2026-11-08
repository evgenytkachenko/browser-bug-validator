"""Phase-gate regressions, including all24 preserved actual rc2 model replies.

Runtime tests use injected model/browser doubles. These tests do not establish
that a fresh language model selects the correct next action.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from bug_validator.common import ValidationError
from bug_validator.general import run_agent
from bug_validator.general_contracts import decision_schema
from bug_validator.schemas import validate_response
from test_general_loop import FakeBrowser, ScriptedModel, decision, inputs


class PhaseCaptureModel(ScriptedModel):
    def __init__(self, answers):
        super().__init__(answers)
        self.schemas = []

    def ask(self, stage, system, payload, schema):
        self.schemas.append(copy.deepcopy(schema))
        return super().ask(stage, system, payload, schema)


class GeneralPhaseTests(unittest.TestCase):
    def run_case(self, answers, config=None):
        bug, kb, auth = inputs()
        model = PhaseCaptureModel(answers)
        instances = []
        def factory(*args):
            instance = FakeBrowser(*args)
            instances.append(instance)
            return instance
        with tempfile.TemporaryDirectory() as tmp:
            report = run_agent(bug, kb, auth, tmp, browser_config=config, model=model, browser_factory=factory)
        return report, model, instances

    def test_every_actual_rc2_response_keeps_its_original_admissibility(self):
        rows = json.loads((Path(__file__).parent / 'fixtures/v04_rc2_decisions.json').read_text())
        self.assertEqual(len(rows), 24)
        self.assertEqual(sum(row['valid_action_contract'] for row in rows), 6)
        for row in rows:
            answer = json.loads(row['raw_content'])
            original = copy.deepcopy(answer)
            schema = decision_schema(row['available_action_ids'], row['observed_ids'])
            with self.subTest(source=row['source_artifact']):
                if row['valid_action_contract']:
                    validate_response(answer, schema)
                else:
                    with self.assertRaises(ValidationError):
                        validate_response(answer, schema)
                self.assertEqual(answer, original, 'Never strip or repair an observed invalid answer')

    def test_observed_initial_premature_claims_do_not_execute_tools(self):
        rows = json.loads((Path(__file__).parent / 'fixtures/v04_rc2_decisions.json').read_text())
        initial_failures = [row for row in rows if not row['valid_action_contract'] and not row['observed_ids']]
        self.assertEqual(len(initial_failures), 12)
        for row in initial_failures:
            with self.subTest(source=row['source_artifact']):
                report, model, browsers = self.run_case([json.loads(row['raw_content'])])
                self.assertEqual(report['verdict'], 'inconclusive')
                self.assertEqual(browsers[0].steps, [])
                self.assertEqual(len(model.calls), 1)

    def test_action_schema_forbids_claims_even_with_observed_evidence(self):
        schema = decision_schema(['open'], ['obs-0001'])
        self.assertEqual(schema['properties']['verdict'], {'type': 'null'})
        self.assertEqual(schema['properties']['evidence_ids']['maxItems'], 0)
        self.assertNotIn('finish', schema['properties']['action_id']['enum'])
        validate_response(decision('open'), schema)
        for answer in [decision('open', 'inconclusive'), decision('open', evidence_ids=['obs-0001']),
                       decision('finish', 'not_reproduced', ['obs-0001'])]:
            with self.assertRaises(ValidationError):
                validate_response(answer, schema)

    def test_assessment_schema_cannot_execute_browser_actions(self):
        schema = decision_schema(['open'], ['obs-0001'], completion_ready=True)
        self.assertEqual(schema['properties']['action_id']['enum'], ['finish', 'stop'])
        validate_response(decision('finish', 'not_reproduced', ['obs-0001']), schema)
        for answer in [decision('open'), decision('finish'), decision('finish', 'confirmed', ['invented'])]:
            with self.assertRaises(ValidationError):
                validate_response(answer, schema)

    def test_host_enters_assessment_only_after_all_checkpoints(self):
        report, model, _ = self.run_case([decision('open'), decision('search'), decision('finish', 'not_reproduced', ['obs-0001', 'obs-0002'])])
        self.assertEqual(report['verdict'], 'not_reproduced')
        self.assertEqual([p['phase'] for p in model.payloads], ['action', 'action', 'assessment'])
        self.assertEqual([p['next_checkpoint']['id'] if p['next_checkpoint'] else None for p in model.payloads], ['initial', 'result', None])
        self.assertEqual(model.payloads[-1]['capabilities'], [])
        self.assertEqual(model.schemas[-1]['properties']['action_id']['enum'], ['finish', 'stop'])
        self.assertEqual(len(report['steps']), 2)

    def test_action_phase_stop_null_is_an_explicit_inconclusive_stop(self):
        report, _, browsers = self.run_case([decision('stop')])
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertTrue(any(row.startswith('Model stopped:') for row in report['limitations']))
        self.assertFalse(any('ValidationError' in row for row in report['limitations']))
        self.assertEqual(browsers[0].steps, [])

    def test_exhaustion_before_completion_offers_only_stop(self):
        report, model, _ = self.run_case([decision('open'), decision('open'), decision('stop')])
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertEqual(model.schemas[-1]['properties']['action_id']['enum'], ['stop'])
        self.assertEqual(model.payloads[-1]['phase'], 'action')
        self.assertEqual(len(report['checkpoint_results']), 1)

    def test_failed_precondition_never_enters_assessment(self):
        report, model, browsers = self.run_case([decision('open')], {'initial': 'unexpected'})
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertEqual([p['phase'] for p in model.payloads], ['action'])
        self.assertEqual(len(browsers[0].steps), 1)

    def test_browser_action_after_completion_is_not_executed(self):
        report, _, browsers = self.run_case([decision('open'), decision('search'), decision('open')])
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertEqual(len(browsers[0].steps), 2)

    def test_assessment_stop_requires_inconclusive(self):
        report, _, _ = self.run_case([decision('open'), decision('search'), decision('stop', 'confirmed', ['obs-0001', 'obs-0002'])])
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertTrue(any('Stop violated' in row for row in report['limitations']))


if __name__ == '__main__':
    unittest.main()
