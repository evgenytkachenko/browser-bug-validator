"""Synthetic unit contract tests. Fake HTTP judge responses are never real LLM runs."""
import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from bug_validator.common import digest
from evaluations import general_semantic as sem
from evaluations.general_tasks import TASKS, public_inputs
from evaluations.judge_retrieval import load_corpus, retrieve


class FakeJudge:
    """Explicit transport test double, not an installed model."""
    def __init__(self, *, malformed=False, drift=False):
        self.malformed, self.drift, self.requests, self.tag_calls = malformed, drift, [], 0
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def emit(self, payload):
                raw = json.dumps(payload).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_GET(self):
                owner.tag_calls += 1
                sha = 'e' if owner.drift and owner.tag_calls > 1 else 'a'
                self.emit({'models': [{'name': 'unit-test-judge:latest', 'digest': sha * 64}]})
            def do_POST(self):
                owner.requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                dims = {d: {'label': 'pass', 'rationale': 'Synthetic transport test response, not a real model judgment.'} for d in sem.DIMENSIONS}
                self.emit({'model': 'unit-test-judge', 'done': True, 'message': {'role': 'assistant', 'content': 'not json' if owner.malformed else json.dumps({'dimensions': dims})}, 'prompt_eval_count': 10, 'eval_count': 5})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
    def __enter__(self):
        self.thread.start(); return self
    def __exit__(self, *_):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
    @property
    def config(self):
        return {'endpoint': f'http://127.0.0.1:{self.server.server_port}', 'model': 'unit-test-judge', 'temperature': 0.3, 'seed': 10}


def make_packets(root, tasks=None, review_role='calibration', source_split='development'):
    """Construct a small synthetic packet fixture via prepare's production projection."""
    tasks = tasks or [TASKS[9]]
    run = root / 'synthetic-run'; run.mkdir()
    records = {}
    for i, task in enumerate(tasks):
        trial_id = task['id'] + '--001'
        directory = run / trial_id; (directory / 'agent').mkdir(parents=True)
        bug, kb, auth = public_inputs(task, 'http://127.0.0.1:54321')
        report = {'verdict': task['expected_verdict'], 'summary': 'Synthetic report fixture with no real browser execution.',
                  'observations': [], 'steps': [], 'decisions': [], 'checkpoint_results': [], 'assertions': [],
                  'limitations': ['Synthetic unit test data only.'], 'started_at': str(i),
                  'model_calls': [], 'provenance': {'unit_test': True}, 'backend': 'test-double'}
        for name, value in [('agent/report.json', report), ('public-input.json', {'bug': bug, 'knowledge_base': kb, 'authorization': auth}),
                            ('state-before.json', {'status': 'todo', 'quantity': 1}), ('state-after.json', {'status': 'todo', 'quantity': 1}),
                            ('server-journal.json', [])]:
            sem.write(directory / name, value)
        records[trial_id] = {'task_id': task['id'], 'family': task['family']}
    manifest = {'split': source_split, 'backend': 'scripted-control', 'model_identity_before': {'status': 'not_applicable'}, 'model_identity_stable': True}
    packets = root / 'packets'
    with patch.object(sem, 'load_general_run', return_value=(manifest, records)):
        sem.prepare(run, packets, review_role, source_split != 'development')
    return packets


def synthetic_labels(packets, *, label='pass'):
    """Parser inputs only; never used or published as actual human calibration."""
    labels = sem.read_json(packets / 'human-labels-template.json')
    for row in labels['labels']:
        row.update(reviewer='SYNTHETIC UNIT TEST, NOT A HUMAN REVIEW', reviewed_at='2026-01-01T00:00:00+00:00')
        row['dimensions'] = {d: {'label': label, 'rationale': 'SYNTHETIC parser exercise; no human review occurred.'} for d in sem.DIMENSIONS}
    path = packets.parent / 'synthetic-labels.json'; sem.write(path, labels); return path


class RetrievalTests(unittest.TestCase):
    def test_corpus_is_separate_synthetic_and_deterministic(self):
        corpus = load_corpus()
        self.assertEqual(len(corpus['examples']), 8)
        self.assertTrue(all(e['provenance']['human_reviewed'] is False for e in corpus['examples']))
        packet = {'public_bug': {'title': 'Profile access blocked'}, 'target': {'summary': 'Inconclusive after denied access'}}
        context = {'task_id': 'other', 'family': 'profile', 'lineage': 'other'}
        a = retrieve(corpus, packet, context); b = retrieve(corpus, packet, context)
        self.assertEqual(a, b)
        self.assertNotIn('profile-blocked', [e['id'] for e in a[0]])
        self.assertIn({'id': 'profile-blocked', 'reason': 'same_family'}, a[1]['excluded'])

    def test_copy_and_task_lineage_exclusion(self):
        corpus = load_corpus(); row = corpus['examples'][0]
        packet = {'public_bug': {'title': 'Pagination'}, 'target': {'summary': row['report']}}
        examples, receipt = retrieve(corpus, packet, {'task_id': 'not-same', 'family': 'not-same', 'lineage': 'not-same'})
        self.assertNotIn(row['id'], [e['id'] for e in examples])
        self.assertIn({'id': row['id'], 'reason': 'exact_current_text_copy'}, receipt['excluded'])
        _, receipt = retrieve(corpus, packet, {'task_id': row['source_task_id'], 'family': 'other', 'lineage': 'other'})
        self.assertIn({'id': row['id'], 'reason': 'same_task'}, receipt['excluded'])
        _, receipt = retrieve(corpus, packet, {'task_id': 'other', 'family': 'other', 'lineage': row['lineage']})
        self.assertIn({'id': row['id'], 'reason': 'same_lineage'}, receipt['excluded'])

    def test_corpus_poisoning_validation(self):
        for mutation in ['split', 'human', 'reserved', 'extra', 'duplicate']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                corpus = load_corpus()
                if mutation == 'split': corpus['examples'][0]['split'] = 'reserved-transfer'
                if mutation == 'human': corpus['examples'][0]['provenance']['human_reviewed'] = True
                if mutation == 'reserved': corpus['examples'][0]['source_task_id'] = TASKS[-1]['id']
                if mutation == 'extra': corpus['examples'][0]['execute'] = 'untrusted instructions'
                if mutation == 'duplicate': corpus['examples'].append(copy.deepcopy(corpus['examples'][0]))
                path = Path(temp) / 'corpus.json'; sem.write(path, corpus)
                with self.assertRaises(ValueError): load_corpus(path)


class GeneralSemanticTests(unittest.TestCase):
    def test_prepare_same_target_for_human_and_judge_and_no_oracle(self):
        with tempfile.TemporaryDirectory() as temp:
            packets = make_packets(Path(temp))
            index, content = sem.load_packets(packets)
            packet = next(iter(content.values()))
            self.assertEqual(packet['target_type'], sem.TARGET_TYPE)
            self.assertEqual(set(packet['target']), {'verdict', 'summary', 'limitations'})
            self.assertIn('decisions', packet['evidence']['agent_trace'])
            self.assertNotIn('model_calls', packet['target']); self.assertNotIn('provenance', packet['target'])
            self.assertNotIn('expected_verdict', json.dumps(packet)); self.assertNotIn('deterministic_pass', json.dumps(packet))
            template = sem.read_json(packets / 'human-labels-template.json')
            self.assertEqual(template['labels'][0]['target_sha256'], digest(packet['target']))
            self.assertIsNone(template['labels'][0]['reviewer'])
            self.assertEqual(template['packet_index_sha256'], digest(index))

    def test_packet_hash_path_and_canonical_context_fail_closed(self):
        for mutation in ['packet', 'path', 'family', 'lineage', 'target', 'public_bug']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                packets = make_packets(Path(temp)); index = sem.read_json(packets / 'index.json'); row = index['packets'][0]
                path = packets / row['packet_file']; packet = sem.read_json(path)
                if mutation == 'packet': packet['target']['summary'] += 'tampered'; sem.write(path, packet)
                if mutation == 'path': row['packet_file'] = '../secret.json'
                if mutation == 'family': row['context']['family'] = 'other'
                if mutation == 'lineage': row['context']['lineage'] = 'other'
                if mutation == 'target': row['target_sha256'] = 'c' * 64
                if mutation == 'public_bug':
                    packet['public_bug']['title'] = 'Different bug'
                    row['packet_id'] = digest(packet); row['packet_file'] = row['packet_id'] + '.json'
                    sem.write(packets / row['packet_file'], packet)
                sem.write(packets / 'index.json', index)
                with self.assertRaises(ValueError): sem.load_packets(packets)

    def test_real_http_adapter_contract_and_audit_binding_not_real_model(self):
        with tempfile.TemporaryDirectory() as temp, FakeJudge() as fake:
            root = Path(temp); packets = make_packets(root); output = root / 'judged'
            summary = sem.judge(packets, fake.config, output, repeats=2)
            self.assertEqual(summary['status'], 'judged_uncalibrated')
            self.assertEqual(len(fake.requests), 2)
            self.assertEqual([r['options']['seed'] for r in fake.requests], [10, 11])
            self.assertTrue(all(r['keep_alive'] == 0 for r in fake.requests))
            manifest, index, rows = sem.load_judgments(output, packets)
            self.assertEqual(len(rows), 2); self.assertEqual(summary['human_calibration'], 'unverified')
            body = json.loads(fake.requests[0]['messages'][1]['content'])
            self.assertEqual(body['current_packet']['target_type'], sem.TARGET_TYPE)
            self.assertNotIn('expected_verdict', json.dumps(body))
            self.assertTrue(body['judge_reference_examples'])
            with self.assertRaises(ValueError): sem.calibrate(output, packets, packets / 'human-labels-template.json')
            result = sem.calibrate(output, packets, synthetic_labels(packets))
            self.assertEqual(result['human_reviewed_packets'], 1)
            self.assertEqual(result['distinct_tasks'], 1)
            self.assertEqual(result['valid_judgments'], 2)
            self.assertEqual(result['release_gate'], 'not_automatically_approved')
            self.assertFalse(result['per_dimension']['groundedness']['all_three_human_labels_covered'])
            artifact_path = output / rows[0]['artifact']; artifact = sem.read_json(artifact_path)
            artifact['request']['messages'][1]['content'] = '{}'; sem.write(artifact_path, artifact)
            with self.assertRaises(ValueError): sem.load_judgments(output, packets)

    def test_response_record_cannot_disagree_with_raw_http_body(self):
        with tempfile.TemporaryDirectory() as temp, FakeJudge() as fake:
            root = Path(temp); packets = make_packets(root); out = root / 'out'
            sem.judge(packets, fake.config, out, repeats=1)
            manifest, _, rows = sem.load_judgments(out, packets)
            row = rows[0]; path = out / row['artifact']; artifact = sem.read_json(path)
            changed = {'dimensions': {d: {'label': 'fail', 'rationale': 'Altered parsed object.'} for d in sem.DIMENSIONS}}
            artifact['response']['message']['content'] = json.dumps(changed)
            row.update(dimensions=changed['dimensions'], response_sha256=digest(artifact['response']), artifact_sha256=digest(artifact))
            sem.write(path, artifact)
            (out / 'judgments.jsonl').write_text(json.dumps(row) + '\n')
            manifest['judgments_sha256'] = digest(rows); sem.write(out / 'manifest.json', manifest)
            with self.assertRaises(ValueError): sem.load_judgments(out, packets)

    def test_missing_source_identity_fails_closed(self):
        for field in ['agent_backend', 'agent_models', 'agent_model_identity', 'agent_model_identity_stable']:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                packets = make_packets(Path(temp)); index = sem.read_json(packets / 'index.json')
                del index[field]; sem.write(packets / 'index.json', index)
                with self.assertRaises(ValueError): sem.load_packets(packets)

    def test_response_identity_and_completion_are_required(self):
        identity = {'requested_model': 'judge', 'resolved_name': 'judge:latest'}
        good = {'model': 'judge:latest', 'done': True, 'message': {'role': 'assistant'}}
        sem.validate_response_identity(good, identity)
        for field in ['model', 'done', 'message']:
            bad = copy.deepcopy(good); del bad[field]
            with self.subTest(field=field), self.assertRaises(ValueError): sem.validate_response_identity(bad, identity)
        with self.assertRaises(ValueError): sem.validate_response_identity(dict(good, model='other'), identity)
        with self.assertRaises(ValueError): sem.validate_response_identity(dict(good, done=False), identity)
        with self.assertRaises(ValueError): sem.validate_response_identity({'done': True, 'message': {'role': 'assistant'}}, {'requested_model': 'judge', 'resolved_name': None})

    def test_malformed_judge_never_passes_or_disappears(self):
        with tempfile.TemporaryDirectory() as temp, FakeJudge(malformed=True) as fake:
            root = Path(temp); packets = make_packets(root); out = root / 'out'
            summary = sem.judge(packets, fake.config, out, repeats=2)
            self.assertEqual(summary['status'], 'unverified'); self.assertEqual(summary['errors'], 2)
            _, _, rows = sem.load_judgments(out, packets)
            self.assertEqual(len(rows), 2)
            self.assertEqual(sem.calibrate(out, packets, synthetic_labels(packets))['status'], 'unverified')

    def test_judge_identity_drift_rejected_for_calibration(self):
        with tempfile.TemporaryDirectory() as temp, FakeJudge(drift=True) as fake:
            root = Path(temp); packets = make_packets(root); out = root / 'out'
            self.assertEqual(sem.judge(packets, fake.config, out, repeats=1)['status'], 'unverified')
            with self.assertRaises(ValueError): sem.load_judgments(out, packets)

    def test_self_judging_digest_alias_and_bad_config_are_rejected_before_call(self):
        with tempfile.TemporaryDirectory() as temp, FakeJudge() as fake:
            root = Path(temp); packets = make_packets(root)
            index = sem.read_json(packets / 'index.json')
            index.update(agent_backend='local-model', agent_models=['evaluated-name'], agent_model_identity_stable=True,
                         agent_model_identity={'status': 'verified', 'digest': 'a' * 64})
            sem.write(packets / 'index.json', index)
            with self.assertRaises(ValueError): sem.judge(packets, fake.config, root / 'out')
            self.assertFalse(fake.requests)
            for config in [dict(fake.config, endpoint='https://example.com'), dict(fake.config, temperature=float('nan')),
                           dict(fake.config, seed=True), dict(fake.config, extra='value')]:
                with self.assertRaises(ValueError): sem.normalized_config(config)

    def test_fake_human_label_target_timestamp_and_duplicate_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp, FakeJudge() as fake:
            root = Path(temp); packets = make_packets(root); out = root / 'out'
            sem.judge(packets, fake.config, out, repeats=1)
            label_path = synthetic_labels(packets); good = sem.read_json(label_path)
            for mutation in ['source', 'target', 'timestamp', 'duplicate', 'missing']:
                labels = copy.deepcopy(good)
                if mutation == 'source': labels['labels'][0]['source'] = 'model'
                if mutation == 'target': labels['labels'][0]['target_sha256'] = 'b' * 64
                if mutation == 'timestamp': labels['labels'][0]['reviewed_at'] = '2026-01-01'
                if mutation == 'duplicate': labels['labels'].append(copy.deepcopy(labels['labels'][0]))
                if mutation == 'missing': labels['labels'] = []
                sem.write(label_path, labels)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError): sem.calibrate(out, packets, label_path)

    def test_validation_requires_frozen_disjoint_lineage(self):
        with tempfile.TemporaryDirectory() as temp, FakeJudge() as fake:
            root = Path(temp); (root / 'cal').mkdir(); (root / 'val').mkdir(); (root / 'leak').mkdir()
            cal = make_packets(root / 'cal', [TASKS[9]])
            sem.judge(cal, fake.config, root / 'cal/judged', repeats=1)
            baseline = sem.calibrate(root / 'cal/judged', cal, synthetic_labels(cal))
            baseline_path = root / 'baseline.json'; sem.write(baseline_path, baseline)
            val = make_packets(root / 'val', [TASKS[10]], review_role='validation')
            sem.judge(val, fake.config, root / 'val/judged', repeats=1)
            with self.assertRaises(ValueError): sem.calibrate(root / 'val/judged', val, synthetic_labels(val))
            incomplete = {key: baseline[key] for key in ['review_role', 'status', 'policy_sha256']}
            sem.write(root / 'incomplete-baseline.json', incomplete)
            with self.assertRaises(ValueError): sem.calibrate(root / 'val/judged', val, synthetic_labels(val), root / 'incomplete-baseline.json')
            result = sem.calibrate(root / 'val/judged', val, synthetic_labels(val), baseline_path)
            self.assertEqual(result['validation'], 'disjoint_task_and_lineage_validation_not_blind')
            leak = make_packets(root / 'leak', [TASKS[1]], review_role='validation')
            sem.judge(leak, fake.config, root / 'leak/judged', repeats=1)
            with self.assertRaises(ValueError): sem.calibrate(root / 'leak/judged', leak, synthetic_labels(leak), baseline_path)


if __name__ == '__main__': unittest.main()
