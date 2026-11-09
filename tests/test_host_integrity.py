"""Exact-archive negative controls. Uses preflight refusal, never a real browser."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from bug_validator.common import file_digest
from bug_validator.host_protocol import HostDecisionSource, atomic_json, read_json
from evaluations.general_tasks import TASKS
from evaluations.host_control import run_case
from evaluations.host_integrity import verify_case
from test_general_evaluations import SyntheticHTTPBrowser


class HostArchiveTests(unittest.TestCase):
    def make(self, base):
        root = Path(base).resolve() / 'case'
        row = run_case(TASKS[9], root, host='other', scripted=True)
        self.assertTrue(row['deterministic_pass'])
        self.assertFalse(row['browser_started'])
        self.assertEqual(row['decision_calls'], 0)
        return root

    def rehash(self, root):
        atomic_json(root / 'artifact-hashes.json', {str(path.relative_to(root)): file_digest(path)
                    for path in sorted(root.rglob('*')) if path.is_file() and path.name != 'artifact-hashes.json'})

    def test_preflight_archive_replays_without_claiming_browser_or_model(self):
        with tempfile.TemporaryDirectory() as temp:
            result = verify_case(self.make(temp))
            self.assertEqual(result, {'verified': True, 'deterministic_pass': True,
                'backend': 'scripted-host-control', 'verdict': 'inconclusive', 'model_quality_claim_eligible': False})

    def test_modified_missing_or_added_artifact_fails(self):
        for mutation in ('changed', 'missing', 'extra'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = self.make(temp)
                if mutation == 'changed': (root / 'state-before.json').write_text('{}')
                elif mutation == 'missing': (root / 'grade.json').unlink()
                else: (root / 'extra.json').write_text('{}')
                with self.assertRaises(ValueError): verify_case(root)

    def test_rehashed_changed_sources_outcomes_binding_and_duplicate_checks_fail(self):
        for mutation in ('source', 'oracle', 'public', 'nonce', 'duplicate', 'grade', 'identity'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = self.make(temp)
                if mutation == 'source':
                    path = root / 'manifest.json'; data = read_json(path); data['source_frozen_through_run'] = False
                elif mutation == 'oracle':
                    path = root / 'oracle-private.json'; data = read_json(path); data['expected_verdict'] = 'confirmed'
                elif mutation == 'public':
                    path = root / 'public-input.json'; data = read_json(path); data['authorization']['acknowledge_mutations'] = True
                elif mutation == 'nonce':
                    path = root / 'control/current.json'; data = read_json(path); data['session_id'] = 'f' * 32
                elif mutation == 'identity':
                    path = root / 'agent/report.json'; data = read_json(path); data['provenance']['host_identity']['verification'] = 'authenticated'
                else:
                    path = root / 'grade.json'; data = read_json(path)
                    if mutation == 'duplicate': data['checks'].append(copy.deepcopy(data['checks'][0]))
                    else: data['passed'] = False
                atomic_json(path, data); self.rehash(root)
                with self.assertRaises(ValueError): verify_case(root)

    def test_recorded_responder_failure_stays_failed_on_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.make(temp)
            grade = read_json(root / 'grade.json')
            extra = next(row for row in grade['checks'] if row['name'] == 'scripted_responder_clean')
            extra.update(passed=False, detail=['Injected responder-failure test control'])
            grade['passed'] = False
            atomic_json(root / 'grade.json', grade)
            manifest = read_json(root / 'manifest.json'); manifest['deterministic_pass'] = False
            atomic_json(root / 'manifest.json', manifest); self.rehash(root)
            self.assertFalse(verify_case(root)['deterministic_pass'])

    def test_interrupted_unanswered_host_attempt_archives_and_replays_failed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / 'interrupted'
            # The browser is explicitly synthetic; no browser/model quality is
            # inferred. Interrupt the actual mailbox wait before any response.
            with patch('bug_validator.general.BrowserSession', SyntheticHTTPBrowser), \
                    patch('bug_validator.host_protocol.time.sleep', side_effect=KeyboardInterrupt):
                row = run_case(TASKS[3], root, host='other', scripted=False)
            self.assertEqual(row['verdict'], 'inconclusive')
            self.assertFalse(row['deterministic_pass'])
            self.assertEqual(row['browser_observations'], 0)
            self.assertEqual(row['decision_calls'], 1)
            manifest = read_json(root / 'manifest.json')
            self.assertTrue(manifest['completed'])
            self.assertFalse(manifest['model_quality_claim_eligible'])
            report = read_json(root / 'agent/report.json')
            self.assertEqual(report['model_calls'][0]['status'], 'failed')
            self.assertIn('KeyboardInterrupt', report['model_calls'][0]['error'])
            artifact_path = root / 'agent/host-001.json'
            artifact = read_json(artifact_path)
            self.assertIsNone(artifact['response'])
            self.assertTrue(verify_case(root)['verified'])
            self.assertFalse(verify_case(root)['deterministic_pass'])
            # Malformed persisted response shapes also fail instead of crashing.
            for malformed in (False, [], 'not an envelope'):
                with self.subTest(response=malformed):
                    artifact['response'] = malformed
                    atomic_json(artifact_path, artifact)
                    self.rehash(root)
                    self.assertFalse(verify_case(root)['deterministic_pass'])

    def test_unanswered_timeout_and_malformed_response_archive_failed(self):
        for failure in ('timeout', 'malformed-response'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve() / 'failed-attempt'
                original_ask = HostDecisionSource.ask
                original_status = HostDecisionSource._status
                def bounded_ask(source, *args, **kwargs):
                    source.timeout = .02
                    return original_ask(source, *args, **kwargs)
                def submit_malformed(source, state, **fields):
                    original_status(source, state, **fields)
                    if state == 'waiting' and failure == 'malformed-response':
                        atomic_json(source.control / ('response-' + fields['request_id'] + '.json'), [])
                with patch('bug_validator.general.BrowserSession', SyntheticHTTPBrowser), \
                        patch.object(HostDecisionSource, 'ask', bounded_ask), \
                        patch.object(HostDecisionSource, '_status', submit_malformed):
                    row = run_case(TASKS[3], root, host='other', scripted=False)
                self.assertFalse(row['deterministic_pass'])
                self.assertEqual(row['verdict'], 'inconclusive')
                self.assertTrue(read_json(root / 'manifest.json')['completed'])
                call = read_json(root / 'agent/report.json')['model_calls'][0]
                self.assertEqual(call['status'], 'failed')
                self.assertIn('time budget' if failure == 'timeout' else 'Malformed host response', call['error'])
                replay = verify_case(root)
                self.assertTrue(replay['verified'])
                self.assertFalse(replay['deterministic_pass'])


if __name__ == '__main__': unittest.main()
