"""Model-checking contract tests; fake transport is not a real-model result."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bug_validator.agent import assessment_verdict, run_agent
from bug_validator.common import ValidationError
from bug_validator.schemas import assessment_schema, validate_response
from test_agent import BUG,KB,ORIGIN,ENTRY,execution,fake_execute


def answer(reloaded='todo'):
    return {'saved_status':'done','reloaded_status':reloaded,'status_persisted':reloaded=='done',
            'evidence_ids':['obs-0002','obs-0003'],'explanation':f'Saved done; reloaded {reloaded}.'}

class EvidenceContractTests(unittest.TestCase):
    def test_truth_table_all_status_pairs(self):
        for saved in ['todo','doing','done']:
            for reloaded in ['todo','doing','done']:
                observed=execution(reloaded)['observations'];observed[1]['values']['persisted_status']=saved
                model={**answer(reloaded),'saved_status':saved,'status_persisted':saved==reloaded}
                with self.subTest(saved=saved,reloaded=reloaded):
                    verdict=assessment_verdict(model,observed,saved)
                    self.assertEqual(verdict,'not_reproduced' if saved==reloaded else 'confirmed')
    def test_wrong_extraction_inverted_predicate_and_uncertainty_fail_closed(self):
        for change in [{'saved_status':'todo'},{'reloaded_status':'done'},{'status_persisted':True},
                       {'status_persisted':None},{'status_persisted':'false'},{'status_persisted':0},
                       {'evidence_ids':['obs-0001','obs-0003']},{'evidence_ids':['obs-0002','invented']},
                       {'evidence_ids':['obs-0002','obs-0002']},{'verdict':'confirmed'}]:
            with self.subTest(change=change),self.assertRaises(ValidationError):
                assessment_verdict({**answer(),**change},execution()['observations'],'done')
    def test_saved_expected_precondition_cannot_be_bypassed(self):
        observed=execution('todo')['observations'];observed[1]['values']['persisted_status']='todo'
        model={**answer('todo'),'saved_status':'todo','status_persisted':True}
        with self.assertRaises(ValidationError):assessment_verdict(model,observed,'done')
    def test_v02_wrong_verdict_outputs_are_not_salvaged(self):
        rows=json.loads((Path(__file__).parent/'fixtures/v02_assessments.json').read_text())
        self.assertEqual(len(rows),8)
        for row in rows:
            old=json.loads(row['response']['message']['content'])
            with self.subTest(trial=row['source_trial']),self.assertRaises(ValidationError):
                validate_response(old,assessment_schema(['obs-0001','obs-0002','obs-0003']))
    @patch('bug_validator.agent.LocalModel')
    @patch('bug_validator.agent.execute_browser',side_effect=fake_execute)
    def test_real_agent_path_checks_facts_and_records_mapping(self,_,model_class):
        model=model_class.return_value;model.calls=[]
        model.ask.side_effect=[{'journey_id':ENTRY['id'],'target_task_id':'T-101','expected_status':'done'},answer()]
        with tempfile.TemporaryDirectory() as d:
            report=run_agent(BUG,KB,ORIGIN,d,backend='local-model')
            self.assertEqual(report['verdict'],'confirmed')
            self.assertEqual(report['assessment_mapping']['mode'],'deterministic_after_model_checked_evidence')
            self.assertEqual(report['assessment_mapping']['mapped_verdict'],'confirmed')
            payload=model.ask.call_args_list[1].args[2]
            self.assertIn('requirement',payload);self.assertIn('unverified_report',payload)
            self.assertNotIn('status_persisted',payload)
    def test_valid_fixed_case_is_not_reproduced(self):
        self.assertEqual(assessment_verdict(answer('done'),execution('done')['observations'],'done'),'not_reproduced')
    def test_boolean_schema_rejects_numeric_coercion(self):
        schema=assessment_schema(['obs-0001','obs-0002','obs-0003'])
        validate_response(answer(),schema)
        for value in [0,1,'false','true']:
            with self.assertRaises(ValidationError):validate_response({**answer(),'status_persisted':value},schema)

if __name__=='__main__':unittest.main()
