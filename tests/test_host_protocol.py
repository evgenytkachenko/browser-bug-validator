"""Host transport unit controls only; scripted choices and fake browser evidence."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bug_validator.common import ValidationError, digest
from bug_validator.general import run_agent
from bug_validator.model import LocalModel
from bug_validator.general_contracts import decision_schema
from bug_validator.host import serve
from bug_validator.host_protocol import HostDecisionSource, PROTOCOL, atomic_json, read_json, read_status, submit
from evaluations.host_integrity import request_binding_errors
from test_general_loop import FakeBrowser, decision, inputs


def wait_request(root):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = read_status(root)
        if status['state'] == 'waiting':
            return status
        time.sleep(.005)
    raise AssertionError('Host did not publish a request')


class HostProtocolTests(unittest.TestCase):
    def source(self, root):
        source = HostDecisionSource(root, host='codex', decision_origin='scripted-control')
        source.output_dir.mkdir()
        source.timeout = 1
        return source

    def ask(self, source):
        result = {}
        def run():
            try:
                result['answer'] = source.ask('decide', 'unit-test', {'unit_test': True}, decision_schema(['open'], []))
            except BaseException as exc:
                result['error'] = exc
        worker = threading.Thread(target=run)
        worker.start()
        return worker, result, wait_request(source.root)

    def test_single_valid_request_and_duplicate_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); source = self.source(root)
            worker, result, current = self.ask(source)
            submit(root, current['request_id'], decision('open'))
            with self.assertRaises((FileExistsError, ValidationError)):
                submit(root, current['request_id'], decision('open'))
            worker.join(2)
            self.assertEqual(result['answer'], decision('open'))
            self.assertEqual(source.calls[0]['status'], 'completed')
            artifact = read_json(root / 'agent/host-001.json')
            self.assertEqual(artifact['response']['request_sha256'], digest(artifact['request']))
            self.assertFalse(source.identity['model_quality_claim_eligible'])

    def test_wrong_binding_and_invalid_action_fail_without_retry(self):
        for field in ('protocol', 'session_id', 'request_id', 'request_sha256', 'answer'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve(); source = self.source(root)
                worker, result, current = self.ask(source)
                response = {'protocol': PROTOCOL, 'session_id': current['session_id'],
                            'request_id': current['request_id'], 'request_sha256': current['request_sha256'],
                            'answer': decision('open')}
                response[field] = decision('exfiltrate') if field == 'answer' else 'forged'
                atomic_json(root / 'control' / ('response-' + current['request_id'] + '.json'), response)
                worker.join(2)
                self.assertIsInstance(result['error'], ValidationError)
                self.assertEqual(len(source.calls), 1)
                self.assertEqual(read_status(root)['state'], 'rejected')

    def test_submit_invalid_schema_is_recorded_by_controller(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); source = self.source(root)
            worker, result, current = self.ask(source)
            bad = decision('open'); bad['url'] = 'https://example.invalid'
            self.assertEqual(submit(root, current['request_id'], bad)['state'], 'submitted')
            worker.join(2)
            self.assertIsInstance(result['error'], ValidationError)
            self.assertEqual(source.calls[0]['status'], 'failed')

    def test_editing_public_schema_does_not_change_authoritative_capabilities(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); source = self.source(root)
            worker, result, current = self.ask(source)
            current['request']['schema']['properties']['action_id']['enum'].append('escape')
            current['request_sha256'] = digest(current['request'])
            atomic_json(root / 'control/current.json', current)
            submit(root, current['request_id'], decision('escape'))
            worker.join(2)
            self.assertIsInstance(result['error'], ValidationError)

    def test_stale_nonce_cannot_submit_to_next_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); source = self.source(root)
            worker, _, current = self.ask(source)
            submit(root, current['request_id'], decision('open')); worker.join(2)
            old = current['request_id']
            worker, result, current = self.ask(source)
            with self.assertRaises(ValidationError):
                submit(root, old, decision('open'))
            submit(root, current['request_id'], decision('stop')); worker.join(2)
            self.assertEqual(result['answer']['action_id'], 'stop')

    def test_timeout_never_chooses_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.source(Path(temp).resolve()); source.timeout = .06
            worker, result, _ = self.ask(source); worker.join(2)
            self.assertIsInstance(result['error'], ValidationError)
            self.assertEqual(source.calls[0]['status'], 'failed')
            self.assertNotIn('answer', source.calls[0])

    def test_malformed_oversize_and_symlink_response_fail(self):
        for kind in ('malformed', 'duplicate', 'oversize', 'symlink'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve(); source = self.source(root)
                worker, result, current = self.ask(source)
                target = root / 'control' / ('response-' + current['request_id'] + '.json')
                if kind == 'symlink':
                    target.symlink_to(root / 'control/current.json')
                else:
                    target.write_text({'malformed': '{', 'duplicate': '{"a":1,"a":2}', 'oversize': ' ' * 16385}[kind])
                worker.join(2)
                self.assertIn('error', result)
                self.assertEqual(source.calls[0]['status'], 'failed')

    def test_json_reader_refuses_nonfinite_duplicate_fifo_and_size(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp).resolve() / 'input.json'
            for raw in ('{"x":1,"x":2}', '{"x":NaN}', ' ' * 1025):
                file.write_text(raw)
                with self.assertRaises(ValueError): read_json(file, 1024)
            file.unlink(); os.mkfifo(file)
            with self.assertRaises(ValueError): read_json(file)

    def test_preexisting_run_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            sentinel = Path(temp).resolve() / 'keep'; sentinel.write_text('preserved')
            with self.assertRaises(FileExistsError): serve(temp, {}, {}, {}, host='codex')
            self.assertEqual(sentinel.read_text(), 'preserved')


class HostLoopTests(unittest.TestCase):
    def execute(self, root, answers, config=None, modify=None):
        bug, kb, auth = inputs()
        if modify: modify(bug, kb, auth)
        source = HostDecisionSource(root, host='codex', decision_origin='scripted-control')
        results = {}
        def run():
            with patch.object(LocalModel, '__init__', side_effect=AssertionError('No model API permitted')):
                results['report'] = run_agent(bug, kb, auth, root / 'agent', browser_config=config,
                                              host_source=source, browser_factory=FakeBrowser)
        thread = threading.Thread(target=run); thread.start()
        for answer in answers:
            current = wait_request(root)
            submit(root, current['request_id'], answer)
            # Allow controller to consume; next request has a distinct nonce.
            deadline = time.monotonic() + 3
            while read_status(root).get('request_id') == current['request_id'] and time.monotonic() < deadline:
                time.sleep(.005)
        thread.join(6)
        self.assertFalse(thread.is_alive())
        return results['report'], auth, kb

    def test_host_loop_keeps_injected_browser_honestly_labeled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            report, auth, kb = self.execute(root, [decision('open'), decision('search'), decision('finish', 'not_reproduced', ['obs-0001', 'obs-0002'])])
            self.assertEqual(report['verdict'], 'not_reproduced')
            self.assertEqual(report['backend'], 'injected-test-double')
            self.assertTrue(report['provenance']['injected_browser'])
            self.assertFalse(report['provenance']['injected_model'])
            self.assertEqual(read_status(root)['state'], 'completed')
            self.assertEqual(request_binding_errors(report, auth, root / 'agent', kb), [])

    def test_host_invalid_action_stops_before_browser_and_remains_inconclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            report, _, _ = self.execute(Path(temp).resolve(), [decision('exfiltrate')])
            self.assertEqual(report['verdict'], 'inconclusive')
            self.assertEqual(report['observations'], [])
            self.assertEqual(report['model_calls'][0]['status'], 'failed')

    def test_host_wrong_verdict_and_screenshot_tampering_cannot_confirm(self):
        for config, verdict in (({}, 'confirmed'), ({'tampered_screenshot': True}, 'not_reproduced')):
            with self.subTest(config=config), tempfile.TemporaryDirectory() as temp:
                report, _, _ = self.execute(Path(temp).resolve(), [decision('open'), decision('search'), decision('finish', verdict, ['obs-0001', 'obs-0002'])], config)
                self.assertEqual(report['verdict'], 'inconclusive')

    def test_integrity_rejects_rehashed_stale_observation_and_schema(self):
        for mutation in ('observation', 'schema', 'history', 'replay'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                report, auth, kb = self.execute(root, [decision('open'), decision('search'), decision('finish', 'not_reproduced', ['obs-0001', 'obs-0002'])])
                file = root / 'agent/host-002.json'; data = read_json(file)
                if mutation == 'observation': data['request']['payload']['current_observation'] = None
                elif mutation == 'schema': data['request']['schema']['properties']['action_id']['enum'].append('escape')
                elif mutation == 'history': data['request']['payload']['history'] = []
                else: data['response']['request_id'] = report['model_calls'][0]['request_id']
                data['call']['request_sha256'] = digest(data['request'])
                data['response']['request_sha256'] = digest(data['request'])
                data['call']['response_sha256'] = digest(data['response'])
                report['model_calls'][1] = copy.deepcopy(data['call'])
                atomic_json(file, data)
                self.assertTrue(request_binding_errors(report, auth, root / 'agent', kb))

    def test_host_source_does_not_accept_second_model_or_output_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); source = HostDecisionSource(root, host='codex')
            bug, kb, auth = inputs()
            with self.assertRaises(ValidationError):
                run_agent(bug, kb, auth, root / 'agent', host_source=source, model=object())
            with self.assertRaises(ValidationError):
                run_agent(bug, kb, auth, root / 'other', host_source=source)


if __name__ == '__main__': unittest.main()
