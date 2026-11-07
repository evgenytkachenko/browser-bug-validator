import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bug_validator.agent import classify_execution, run_agent
from bug_validator.common import ValidationError, loopback_origin, validate_bug, validate_entry, WORKFLOW
from bug_validator.knowledge import retrieve
from bug_validator.model import LocalModel

ORIGIN = 'http://127.0.0.1:18181'
BUG = {'id': 'unit-1', 'title': 'Done status reverts after reload', 'description': 'Save done status and reload to test persistence.',
       'target_task_id': 'T-101', 'expected_status': 'done', 'authorization': {'origin': ORIGIN, 'allowed_task_ids': ['T-101'],
       'allowed_actions': ['select_status', 'save', 'reload']}}
ENTRY = {'id':'task-status-persistence', 'title':'Task status persistence', 'description':'Save status and reload',
         'keywords':['status','save','reload','persist'], 'route':'/', 'workflow':WORKFLOW,
         'selectors': {'ready':'board-ready','blocked':'access-blocked','row':'task-row-{task_id}',
                       'status':'task-status-{task_id}','save':'save-task-{task_id}','persisted':'persisted-status-{task_id}'}}
KB = {'schema_version':1, 'entries':[ENTRY]}


def execution(final='todo', completed=True):
    observations = []
    for i, (phase, status) in enumerate([('initial','todo'),('saved','done'),('reloaded',final)], 1):
        observations.append({'id':f'obs-{i:04}', 'phase':phase, 'url':ORIGIN+'/', 'screenshot':f'{i}.png',
                             'screenshot_sha256':hashlib.sha256(b'fake-unit-test-png').hexdigest(), 'visible_text':'unit fixture',
                             'values':{'target_task_id':'T-101','selected_status':status,'persisted_status':status}})
    return {'completed':completed, 'observations':observations, 'steps':[], 'limitations':[], 'trace':'trace.jsonl',
            'trace_sha256':hashlib.sha256(b'unit-test-trace\n').hexdigest()}


def fake_execute(*args):
    output = args[4]
    result = execution()
    for o in result['observations']:
        (output/o['screenshot']).write_bytes(b'fake-unit-test-png')
    (output/'trace.jsonl').write_bytes(b'unit-test-trace\n')
    return result


class InputTests(unittest.TestCase):
    def test_explicit_local_origin(self):
        self.assertEqual(loopback_origin(ORIGIN+'/'),ORIGIN)
        self.assertEqual(loopback_origin('http://[::1]:1234'),'http://[::1]:1234')
    def test_external_or_ambiguous_origins_denied(self):
        for url in ['https://example.com','http://127.0.0.1','http://127.0.0.1:3/path','http://user:pass@127.0.0.1:3',
                    'http://127.0.0.1:3?x=y','http://127.0.0.2:123','file:///tmp/app','http://127.0.0.1:bad']:
            with self.subTest(url=url), self.assertRaises(ValidationError): loopback_origin(url)
    def test_precise_authorization_required(self):
        self.assertEqual(validate_bug(BUG,ORIGIN),ORIGIN)
        for change in [{'origin':'http://127.0.0.1:9999'}, {'allowed_task_ids':['T-202']}, {'allowed_actions':['reload']}]:
            bug = copy.deepcopy(BUG); bug['authorization'].update(change)
            with self.subTest(change=change), self.assertRaises(ValidationError): validate_bug(bug,ORIGIN)
    def test_authorization_strings_are_not_lists(self):
        for field,value in [('allowed_task_ids','T-1010'),('allowed_actions','select_status save reload'),('allowed_task_ids',{'T-101':True})]:
            bug=copy.deepcopy(BUG); bug['authorization'][field]=value
            with self.subTest(field=field), self.assertRaises(ValidationError): validate_bug(bug,ORIGIN)
    def test_missing_target_not_guessed(self):
        bug = copy.deepcopy(BUG); del bug['target_task_id']
        with self.assertRaises(ValidationError): validate_bug(bug,ORIGIN)
    def test_invalid_task_or_status(self):
        for field, value in [('target_task_id','T-1]/../admin'),('expected_status','deleted')]:
            bug=copy.deepcopy(BUG); bug[field]=value
            with self.assertRaises(ValidationError): validate_bug(bug,ORIGIN)
    def test_kb_retrieval(self):
        best, all_rows=retrieve(BUG,KB); self.assertEqual(best['entry']['id'], ENTRY['id']); self.assertGreater(best['score'],1)
    def test_retrieval_missing_or_ambiguous(self):
        with self.assertRaises(ValidationError): retrieve({'title':'Pricing currency','description':'Tax calculation wrong'},KB)
        other=copy.deepcopy(ENTRY); other['id']='second-journey'
        with self.assertRaises(ValidationError): retrieve(BUG,{'entries':[ENTRY,other]})
    def test_selector_injection_rejected(self):
        bad=copy.deepcopy(ENTRY); bad['selectors']['save']='save-task-{task_id}\"] button'
        with self.assertRaises(ValidationError): validate_entry(bad,'T-101')
    def test_wrong_target_kb_selector_is_rejected(self):
        bad=copy.deepcopy(ENTRY); bad['selectors']['persisted']='persisted-status-T-202'
        with self.assertRaises(ValidationError): validate_entry(bad,'T-101')
    def test_workflow_and_route_cannot_expand(self):
        for key,value in [('route','/admin'),('workflow',WORKFLOW+['delete_all'])]:
            bad=copy.deepcopy(ENTRY); bad[key]=value
            with self.assertRaises(ValidationError): validate_entry(bad,'T-101')
    def test_model_cannot_send_external(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValidationError): LocalModel({'endpoint':'https://api.example.com'},Path(d))
            model=LocalModel({'endpoint':ORIGIN,'seed':8},Path(d)); self.assertEqual(model.seed,8)


class EvidenceTests(unittest.TestCase):
    def test_confirmed_requires_save_then_revert(self):
        verdict, assertions=classify_execution(execution('todo'),BUG)
        self.assertEqual(verdict,'confirmed'); self.assertFalse(assertions[0]['met'])
    def test_fixed_is_not_reproduced_not_global_absence(self):
        verdict, assertions=classify_execution(execution('done'),BUG)
        self.assertEqual(verdict,'not_reproduced'); self.assertTrue(assertions[0]['met'])
    def test_incomplete_does_not_become_not_reproduced(self):
        self.assertEqual(classify_execution(execution('done',False),BUG)[0],'inconclusive')
    def test_missing_target_or_wrong_target_evidence(self):
        for variant in ['missing','wrong-target','unknown-status','already-done','save-not-done']:
            result=execution()
            if variant=='missing': result['observations'].pop()
            if variant=='wrong-target': result['observations'][-1]['values']['target_task_id']='T-202'
            if variant=='unknown-status': result['observations'][-1]['values']['persisted_status']='Error banner'
            if variant=='already-done': result['observations'][0]['values']['persisted_status']='done'
            if variant=='save-not-done': result['observations'][1]['values']['persisted_status']='todo'
            with self.subTest(variant=variant): self.assertEqual(classify_execution(result,BUG)[0],'inconclusive')
    def test_duplicate_or_reordered_evidence_is_inconclusive(self):
        for variant in ['duplicate-id','duplicate-phase','reorder','extra']:
            result=execution()
            if variant=='duplicate-id': result['observations'][-1]['id']=result['observations'][0]['id']
            if variant=='duplicate-phase': result['observations'][-1]['phase']='saved'
            if variant=='reorder': result['observations'].reverse()
            if variant=='extra': result['observations'].append(copy.deepcopy(result['observations'][-1]))
            with self.subTest(variant=variant): self.assertEqual(classify_execution(result,BUG)[0],'inconclusive')
    @patch('bug_validator.agent.execute_browser',side_effect=fake_execute)
    def test_report_and_artifact_chain(self,_):
        with tempfile.TemporaryDirectory() as d:
            report=run_agent(BUG,KB,ORIGIN,Path(d)/'run')
            self.assertEqual(report['verdict'],'confirmed'); self.assertEqual(report['model_calls'],[])
            self.assertTrue(report['provenance']['skill_sha256'])
            self.assertTrue(any('did not call a language model' in x for x in report['limitations']))
            self.assertEqual(json.loads((Path(d)/'run/report.json').read_text())['verdict'],'confirmed')
    @patch('bug_validator.agent.execute_browser')
    def test_missing_input_stops_before_browser(self,mock):
        with tempfile.TemporaryDirectory() as d:
            bug=copy.deepcopy(BUG); del bug['target_task_id']
            self.assertEqual(run_agent(bug,KB,ORIGIN,d)['verdict'],'inconclusive')
            mock.assert_not_called()
    @patch('bug_validator.agent.execute_browser',side_effect=lambda *args: execution())
    def test_missing_screenshots_fail_closed(self,_):
        with tempfile.TemporaryDirectory() as d:
            report=run_agent(BUG,KB,ORIGIN,d)
            self.assertEqual(report['verdict'],'inconclusive')
            self.assertTrue(any('missing or hash-mismatched' in x for x in report['limitations']))
    def test_preserve_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'important.txt').write_text('keep')
            with self.assertRaises(ValidationError): run_agent(BUG,KB,ORIGIN,d)
            self.assertEqual((Path(d)/'important.txt').read_text(),'keep')
    @patch('bug_validator.agent.LocalModel')
    @patch('bug_validator.agent.execute_browser')
    def test_model_scope_change_rejected_before_browser(self,browser,model_class):
        model=model_class.return_value; model.calls=[]
        model.ask.return_value={'journey_id':ENTRY['id'],'target_task_id':'T-202','expected_status':'done'}
        with tempfile.TemporaryDirectory() as d:
            report=run_agent(BUG,KB,ORIGIN,d,backend='local-model')
            self.assertEqual(report['verdict'],'inconclusive'); browser.assert_not_called()
    @patch('bug_validator.agent.LocalModel')
    @patch('bug_validator.agent.execute_browser',side_effect=fake_execute)
    def test_model_false_persistence_judgment_is_not_accepted(self,_,model_class):
        model=model_class.return_value; model.calls=[]
        model.ask.side_effect=[{'journey_id':ENTRY['id'],'target_task_id':'T-101','expected_status':'done'},
            {'saved_status':'done','reloaded_status':'todo','status_persisted':True,'evidence_ids':['obs-0002','obs-0003'],'explanation':'Fabricated conclusion'}]
        with tempfile.TemporaryDirectory() as d:
            report=run_agent(BUG,KB,ORIGIN,d,backend='local-model')
            self.assertEqual(report['verdict'],'inconclusive')
    @patch('bug_validator.agent.LocalModel')
    @patch('bug_validator.agent.execute_browser',side_effect=fake_execute)
    def test_hallucinated_model_citation_rejected(self,_,model_class):
        model=model_class.return_value; model.calls=[]
        model.ask.side_effect=[{'journey_id':ENTRY['id'],'target_task_id':'T-101','expected_status':'done'},
            {'saved_status':'done','reloaded_status':'todo','status_persisted':False,'evidence_ids':['obs-0002','obs-0003','invented'],'explanation':'Unsupported extra citation'}]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run_agent(BUG,KB,ORIGIN,d,backend='local-model')['verdict'],'inconclusive')

if __name__=='__main__': unittest.main()
