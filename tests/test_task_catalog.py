"""HTTP contract controls, never browser/model/visual evaluation."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from evaluations import task_catalog as catalog
from evaluations.general_tasks import TASKS, public_inputs


class TaskCatalogTests(unittest.TestCase):
    def test_complete_and_bound_to_authoritative_tasks(self):
        data = catalog.validate_catalog()
        self.assertEqual(len(data['tasks']), 17)
        self.assertEqual(sum(r['split'] == 'development' for r in data['tasks']), 11)
        self.assertEqual(sum(r['split'] == 'reserved-transfer' for r in data['tasks']), 6)
        self.assertFalse(any(data['measurement_limits'].values()))

    def test_all_development_goldens_using_actual_http(self):
        receipt = catalog.verify_development()
        self.assertTrue(receipt['passed'])
        self.assertEqual(len(receipt['results']), 11)
        self.assertEqual(receipt['reserved_executed'], 0)
        rows = {r['task_id']: r for r in receipt['results']}
        for task_id in ['dev-10-unacknowledged-write', 'dev-11-missing-requirement']:
            row = rows[task_id]
            self.assertTrue(row['authorization_rejection'])
            self.assertEqual(row['actual_requests'], [])
            self.assertEqual(row['actual_initial_state'], row['actual_final_state'])
        self.assertEqual(rows['dev-07-access-blocked']['responses'][0]['status_code'], 403)
        self.assertEqual(rows['dev-01-status-bug']['actual_final_state']['status'], 'todo')
        self.assertEqual(rows['dev-02-status-fixed']['actual_final_state']['status'], 'done')
        self.assertEqual(rows['dev-05-quantity-bug']['actual_final_state']['quantity'], -2)
        self.assertEqual(rows['dev-06-quantity-fixed']['actual_final_state']['quantity'], 1)

    def test_reserved_selection_refused_before_fixture_start(self):
        with patch.object(catalog.GeneralFixture, 'start', side_effect=AssertionError('must not start')):
            with self.assertRaises(ValueError):
                catalog.verify_development(task_ids=['dev-01-status-bug', 'reserved-01-status-alternate-bug'])
            with self.assertRaises(ValueError):
                catalog.verify_task('reserved-01-status-alternate-bug')

    def test_mutated_goldens_are_rejected(self):
        mutations = [
            lambda r: r['golden']['final_state'].update(status='done'),
            lambda r: r['golden']['initial_state'].update(quantity=2),
            lambda r: r['golden'].update(expected_verdict='not_reproduced'),
            lambda r: r['golden'].update(mutation_request_count=0),
            lambda r: r['golden']['http_requests'][2].update(effect={'persisted_status': 'done'}),
            lambda r: r.update(public_input_sha256='0' * 64),
            lambda r: r.update(task_revision=2),
            lambda r: r.update(paired_task_ids=[]),
            lambda r: r['public_evidence_requirements'].clear(),
            lambda r: r['provenance'].update(production_incident=True),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                data = deepcopy(catalog.load_catalog())
                mutation(data['tasks'][0])
                with self.assertRaises(ValueError):
                    catalog.validate_catalog(data)

    def test_actual_effect_corruption_is_rejected(self):
        original = catalog.GeneralFixture.snapshot
        def corrupt(fixture):
            state = original(fixture)
            if any(r['method'] == 'POST' for r in fixture.audit_log()):
                state['unrelated'] = 'corrupted'
            return state
        with patch.object(catalog.GeneralFixture, 'snapshot', corrupt):
            with self.assertRaisesRegex(ValueError, 'final state mismatch'):
                catalog.verify_task('dev-02-status-fixed')

    def test_public_inputs_never_include_goldens(self):
        for task in TASKS:
            public = public_inputs(task, catalog.NORMALIZED_ORIGIN)
            serialized = json.dumps(public)
            for private_key in ['expected_verdict', 'golden', 'paired_task_ids', 'task_sha256']:
                self.assertNotIn(private_key, serialized)

    def test_receipt_written_only_from_real_control(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            catalog.main(['verify', '--task', 'dev-04-search-fixed', '--receipt', str(path)])
            receipt = json.loads(path.read_text())
            self.assertTrue(receipt['passed'])
            self.assertEqual(receipt['results'][0]['actual_final_state']['search_results'], ['alpha'])
            self.assertEqual(len(receipt['catalog_file_sha256']), 64)
            self.assertIn('fixture_app/general_server.py', receipt['source_sha256'])
            self.assertEqual(receipt['measurement_kind'], 'real-http-oracle-contract-controls')


if __name__ == '__main__':
    unittest.main()
