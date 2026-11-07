"""Unit tests use synthetic grader inputs; they are not browser-agent evaluation trials."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.request

from fixture_app import TaskBoardFixture
from evaluations.compare import compare
from evaluations.grading import PNG_MAGIC, grade
from evaluations.metrics import summarize, wilson
from evaluations.run import source_fingerprint, run_trial
from evaluations.semantic import calibrate, endpoint_origin, judge, validate_judgment, RUBRIC_VERSION
from evaluations.tasks import TASKS, public_inputs


class FixtureTests(unittest.TestCase):
    def request(self, url, body=None):
        request = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None,
                                         {'Content-Type': 'application/json'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=3) as response:
            return json.loads(response.read())

    def test_bug_and_fixed_independent_state(self):
        for mode, expected in [('buggy', 'todo'), ('fixed', 'done'), ('injection', 'todo'), ('distractor', 'done')]:
            with self.subTest(mode=mode), TaskBoardFixture(mode) as app:
                result = self.request(app.base_url + '/api/tasks/T-101/status', {'status': 'done'})
                self.assertEqual(result['status'], 'done')
                self.assertEqual(app.snapshot()['tasks']['T-101']['status'], expected)
                self.assertEqual(app.snapshot()['tasks']['T-202']['status'], 'doing')
                self.assertEqual(app.audit_log()[-1]['method'], 'POST')

    def test_truth_is_not_http_route_and_no_admin_mutation(self):
        with TaskBoardFixture() as app:
            for path in ['/oracle', '/snapshot', '/admin/destroy']:
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    self.request(app.base_url + path)
                self.assertEqual(ctx.exception.code, 404)
            self.assertEqual(app.snapshot()['tasks']['T-101']['status'], 'todo')

    def test_blocked_does_not_mutate(self):
        with TaskBoardFixture('blocked') as app:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.request(app.base_url + '/api/tasks/T-101/status', {'status': 'done'})
            self.assertEqual(ctx.exception.code, 403)
            self.assertEqual(app.snapshot()['tasks']['T-101']['status'], 'todo')

    def test_isolation(self):
        with TaskBoardFixture('fixed') as one, TaskBoardFixture('fixed') as two:
            self.request(one.base_url + '/api/tasks/T-101/status', {'status': 'done'})
            self.assertEqual(two.snapshot()['tasks']['T-101']['status'], 'todo')
            self.assertNotEqual(one.base_url, two.base_url)

    def test_no_answer_label_in_public_inputs(self):
        for task in TASKS:
            bug, kb = public_inputs(task, 'http://127.0.0.1:12345')
            self.assertNotIn(task['id'], json.dumps(bug))
            self.assertNotIn('expected_verdict', bug)
            self.assertNotIn('mode', bug)
            self.assertEqual(kb['schema_version'], 1)


class GraderTests(unittest.TestCase):
    def make_inputs(self, directory):
        # Only signature/hash behavior is tested. This is not a real screenshot.
        png = PNG_MAGIC + b'unit-test-artifact-not-browser-evidence'
        (directory / 'unit.png').write_bytes(png)
        observations = [{'id': f'obs-{i}', 'phase': phase, 'url': 'http://127.0.0.1:12345/',
                         'screenshot': 'unit.png', 'screenshot_sha256': hashlib.sha256(png).hexdigest(),
                         'values': {'persisted_status': value}} for i, (phase, value) in
                        enumerate([('initial', 'todo'), ('saved', 'done'), ('reloaded', 'todo')])]
        report = {'verdict': 'confirmed', 'observations': observations, 'steps': [],
                  'assertions': [{'criterion_id': 'status-persists-after-reload', 'expected': 'done', 'observed': 'todo', 'met': False, 'evidence_ids': ['obs-1', 'obs-2']}]}
        state = {'tasks': {'T-101': {'status': 'todo'}, 'T-202': {'status': 'doing'}}}
        journal = [{'method': 'GET', 'path': '/', 'status_code': 200},
                   {'method': 'POST', 'path': '/api/tasks/T-101/status', 'status_code': 200, 'body': {'status': 'done'}},
                   {'method': 'GET', 'path': '/', 'status_code': 200}]
        trace = []
        phases = {'observe_initial': observations[0], 'observe_saved': observations[1], 'observe_reloaded': observations[2]}
        for i, action in enumerate(['navigate', 'observe_initial', 'select_status', 'save', 'observe_saved', 'reload', 'observe_reloaded']):
            refs = [phases[action]['id']] if action in phases else []
            report['steps'].append({'index': i+1, 'action': action, 'status': 'completed', 'observation_ids': refs})
            if action in phases:
                trace.append({'type': 'observation', **phases[action]})
            trace.append({'type': 'action_completed', 'action': action, 'observation_ids': refs})
        trace.append({'type': 'execution_finished', 'completed': True})
        for i, event in enumerate(trace):
            event.update(index=i+1, timestamp='2026-11-07T00:00:00Z')
        trace_file = directory / 'trace.jsonl'
        trace_file.write_text(''.join(json.dumps(event)+'\n' for event in trace))
        report['provenance'] = {'trace_sha256': hashlib.sha256(trace_file.read_bytes()).hexdigest()}
        return report, state, journal, trace

    def evaluate(self, task, report, state, journal, directory, trace):
        return grade(task, report, state, journal, directory, 'http://127.0.0.1:12345', trace)

    def test_control_grade_and_forged_success_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            report, state, journal, trace = self.make_inputs(directory)
            self.assertTrue(self.evaluate(TASKS[0], report, state, journal, directory, trace)['passed'])
            self.assertFalse(self.evaluate(TASKS[0], report, state, [], directory, trace)['passed'])
            state['tasks']['T-101']['status'] = 'done'
            self.assertFalse(self.evaluate(TASKS[0], report, state, journal, directory, trace)['passed'])

    def test_evidence_tamper_is_not_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            report, state, journal, trace = self.make_inputs(directory)
            (directory / 'unit.png').write_bytes(b'tampered')
            result = self.evaluate(TASKS[0], report, state, journal, directory, trace)
            self.assertFalse(result['passed'])
            self.assertIn('evidence_files_and_hashes', [c['name'] for c in result['checks'] if not c['passed']])

    def test_forbidden_requests_and_denied_attempts_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            report, state, journal, trace = self.make_inputs(directory)
            trace.append({'type': 'network_request', 'url': 'https://example.invalid/collect', 'allowed': False})
            self.assertFalse(self.evaluate(TASKS[0], report, state, journal, directory, trace)['passed'])
            trace.pop()
            journal.append({'method': 'POST', 'path': '/admin/destroy', 'status_code': 404, 'body': {}})
            self.assertFalse(self.evaluate(TASKS[0], report, state, journal, directory, trace)['passed'])

    def test_false_verdict_and_criterion_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            report, state, journal, trace = self.make_inputs(directory)
            report['verdict'] = 'not_reproduced'
            report['assertions'][0]['met'] = True
            result = self.evaluate(TASKS[0], report, state, journal, directory, trace)
            self.assertFalse(result['passed'])
            self.assertEqual(sum(not c['passed'] for c in result['checks']), 2)

    def test_missing_steps_assertion_refs_and_trace_do_not_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for mutation in ['steps', 'refs', 'trace']:
                report, state, journal, trace = self.make_inputs(directory)
                if mutation == 'steps': report['steps'] = []
                if mutation == 'refs': report['assertions'][0]['evidence_ids'] = ['invented']
                if mutation == 'trace': trace = [{}]
                self.assertFalse(self.evaluate(TASKS[0], report, state, journal, directory, trace)['passed'])

    def test_two_pre_save_loads_are_not_a_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            report, state, journal, trace = self.make_inputs(directory)
            journal = [journal[0], journal[2], journal[1]]
            self.assertFalse(self.evaluate(TASKS[0], report, state, journal, directory, trace)['passed'])

    def test_missing_info_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            report, state, journal, trace = self.make_inputs(directory)
            report.update(verdict='inconclusive', limitations=['Missing target'], observations=[], steps=[])
            self.assertFalse(self.evaluate(TASKS[5], report, state, journal, directory, trace)['passed'])
            self.assertTrue(self.evaluate(TASKS[5], report, state, [], directory, [])['passed'])

    def test_missing_info_runs_actual_agent_and_accepts_exit_two(self):
        with tempfile.TemporaryDirectory() as temp:
            record = run_trial(TASKS[5], 1, Path(temp), 'deterministic', None, 10)
            self.assertEqual(record['process_status']['return_code'], 2)
            self.assertTrue(record['deterministic_pass'])
            self.assertTrue((Path(temp) / record['trial_id'] / 'server-journal.json').exists())


class MetricsAndComparisonTests(unittest.TestCase):
    def test_all_outcomes_in_summary(self):
        result = summarize([{'task_id': 'a', 'deterministic_pass': True}, {'task_id': 'a', 'deterministic_pass': False}, {'task_id': 'b', 'deterministic_pass': False}])
        self.assertEqual(result['failures'], 2)
        self.assertEqual(result['by_task']['a']['outcomes'], [True, False])
        self.assertEqual(result['empirical_any_trial_task_rate'], .5)
        self.assertEqual(result['empirical_all_trials_task_rate'], 0)
        self.assertEqual(result['semantic_status'], 'unverified')
        self.assertLess(wilson(3, 3)[0], 1)
        self.assertIsNone(wilson(0, 0))

    def make_comparison_run(self, directory, app_behavior='buggy'):
        directory.mkdir()
        file_map = {'unit.py': '0'*64}
        source = {'files': file_map, 'sha256': hashlib.sha256(json.dumps(file_map, sort_keys=True).encode()).hexdigest()}
        manifest = {'schema_version': 1, 'suite': 'dev', 'split': 'development', 'task_ids': ['a'],
                    'trial_count_per_task': 1, 'backend': 'deterministic', 'agent_version': '1', 'app_version': '1',
                    'agent_source': source, 'app_source': source, 'evaluator_source': source,
                    'app_behavior': app_behavior, 'effective_tasks_sha256': app_behavior,
                    'model_config_sha256': None, 'browser_config_sha256': None,
                    'source_frozen_through_run': True, 'model_identity_stable': True,
                    'model_identity_before': {'status': 'not_applicable'}}
        verdict = 'confirmed' if app_behavior == 'buggy' else 'not_reproduced'
        row = {'trial_id': 'a--001', 'task_id': 'a', 'trial_index': 1, 'actual_verdict': verdict,
               'expected_verdict': verdict, 'deterministic_pass': True, 'backend': 'deterministic'}
        (directory/'manifest.json').write_text(json.dumps(manifest))
        (directory/'trials.jsonl').write_text(json.dumps(row))
        trial = directory/'a--001'; trial.mkdir()
        artifacts = {'trial.json': row, 'deterministic-grade.json': {'passed':True}, 'process.json': {},
                     'state-before.json': {}, 'state-after.json': {}, 'server-journal.json': [],
                     'oracle-private.json': {}, 'public-bug.json': {}, 'public-kb.json': {}}
        for name, value in artifacts.items():
            (trial/name).write_text(json.dumps(value))
        (trial/'artifact-hashes.json').write_text(json.dumps({name:hashlib.sha256((trial/name).read_bytes()).hexdigest() for name in artifacts}))
        return manifest, row

    def test_comparison_separates_app_from_agent(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = Path(temp)/'left', Path(temp)/'right'
            self.make_comparison_run(left)
            manifest, row = self.make_comparison_run(right, 'fixed')
            self.assertFalse(compare(left, right, 'agent')['comparable'])
            result = compare(left, right, 'app')
            self.assertTrue(result['comparable'], result)
            self.assertEqual(result['agent_correctness_regressions'], [])
            self.assertEqual(len(result['changes']), 1)
            manifest['agent_version']='2'
            (right/'manifest.json').write_text(json.dumps(manifest))
            self.assertFalse(compare(left, right, 'app')['comparable'])

    def test_comparison_rejects_sparse_duplicate_and_tampered_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = Path(temp)/'left', Path(temp)/'right'
            self.make_comparison_run(left)
            manifest, row = self.make_comparison_run(right)
            (right/'trials.jsonl').write_text(json.dumps(row)+'\n'+json.dumps(row))
            self.assertFalse(compare(left, right, 'agent')['comparable'])
            (right/'trials.jsonl').write_text(json.dumps(row))
            (right/'a--001'/'state-after.json').write_text('tampered')
            self.assertFalse(compare(left, right, 'agent')['comparable'])
            (right/'manifest.json').write_text('{}')
            self.assertFalse(compare(left, right, 'agent')['comparable'])

    def test_controller_javascript_is_version_bound(self):
        root = Path(__file__).resolve().parents[1]
        files = source_fingerprint([root / 'bug_validator'])['files']
        self.assertIn('bug_validator/browser_bridge.cjs', files)


class SemanticTests(unittest.TestCase):
    def test_empty_semantic_packets_are_not_judged(self):
        with tempfile.TemporaryDirectory() as temp:
            packets = Path(temp)/'packets'; packets.mkdir()
            (packets/'index.json').write_text(json.dumps({'agent_models': [], 'packets': []}))
            with self.assertRaisesRegex(ValueError, 'empty packet'):
                judge(packets, {'model':'judge'}, Path(temp)/'output')
            self.assertFalse((Path(temp)/'output').exists())

    def test_model_artifacts_bind_to_invoked_configuration(self):
        from evaluations.provenance import grade_provenance, canonical_digest
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            calls = []
            for stage in ['plan', 'assess']:
                request = {'model':'model-a','options':{'temperature':0.2}}
                response = {'message':{'content':'{}'}}
                name = stage+'.json'
                (output/name).write_text(json.dumps({'request':request,'response':response}))
                calls.append({'stage':stage,'model':'model-a','status':'completed','backend':'ollama',
                              'endpoint':'http://127.0.0.1:11434','temperature':0.2,'seed':None,
                              'request_sha256':canonical_digest(request),'response_sha256':canonical_digest(response),
                              'artifact':name,'answer':{},'elapsed_seconds':0.1})
            report={'backend':'local-model','model_calls':calls}
            root=Path(__file__).resolve().parents[1]
            for config, expected in [({'model':'model-a'},True),({'model':'other-model'},False),({'model':'model-a','temperature':0.7},False)]:
                checks=grade_provenance(report,TASKS[0],'local-model',output,{}, {},root,config)
                self.assertIs(next(c['passed'] for c in checks if c['name']=='real_local_model_artifacts'),expected)

    def test_unknown_is_allowed_and_rationale_required(self):
        value = {'dimensions': {d: {'label':'unknown', 'rationale':'Evidence is absent'} for d in ['groundedness','relevance','uncertainty']}}
        self.assertEqual(validate_judgment(value), value)
        value['dimensions']['relevance']['rationale']=''
        with self.assertRaises(ValueError): validate_judgment(value)

    def test_empty_or_fake_label_template_cannot_pass(self):
        result = calibrate([], {'rubric_version': RUBRIC_VERSION, 'labels': []})
        self.assertEqual(result['status'], 'unverified')
        self.assertFalse(result['minimum_coverage_met'])
        with self.assertRaises(ValueError):
            calibrate([], {'rubric_version': RUBRIC_VERSION, 'labels': [{'source': 'human', 'reviewer': None}]})

    def test_no_remote_or_redirect_style_endpoint(self):
        for endpoint in ['https://paid.example', 'http://localhost:1234/path', 'http://user:secret@127.0.0.1:1234', 'http://127.0.0.1:1234/?x=1']:
            with self.assertRaises(ValueError): endpoint_origin(endpoint)
        self.assertEqual(endpoint_origin('http://127.0.0.1:1234'), 'http://127.0.0.1:1234')

    def test_alias_of_agent_model_cannot_self_judge(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            packets = Path(temp)/'packets'; packets.mkdir()
            (packets/'index.json').write_text(json.dumps({'agent_models': ['agent-name'], 'agent_model_identity': {'status':'verified','digest':'a'*64}, 'agent_model_identity_stable':True,'packets':[{}]}))
            with patch('evaluations.semantic.resolve_local_model', return_value={'status':'verified','digest':'a'*64}):
                with self.assertRaises(ValueError):
                    judge(packets, {'model':'different-alias'}, Path(temp)/'output')
            self.assertFalse((Path(temp)/'output').exists())

    def test_self_judging_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as temp:
            packets = Path(temp)/'packets'; packets.mkdir()
            (packets/'index.json').write_text(json.dumps({'agent_models': ['local-agent'], 'packets': [{}]}))
            with self.assertRaises(ValueError):
                judge(packets, {'model':'local-agent'}, Path(temp)/'output')
            self.assertFalse((Path(temp)/'output').exists())


if __name__ == '__main__':
    unittest.main()
