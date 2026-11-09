"""Viewer curation controls, not new model/browser measurements."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'trace-viewer'
spec = importlib.util.spec_from_file_location('trace_demo_builder', ROOT / 'build_demo.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class TraceViewerTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'demo.json').read_text())
        self.provenance = json.loads((ROOT / 'provenance.json').read_text())

    def test_pinned_sources(self):
        for case in self.data['cases']:
            for index, run in enumerate(case['runs']):
                pins = self.provenance['runs'][['v02','v03'][index]]['trials'][run['trial_id']]
                self.assertEqual(pins, run['source_hashes'])
                self.assertTrue(all(len(v)==64 and int(v,16)>=0 for v in pins.values()))
                self.assertIn('agent/report.json',pins)

    def test_comparability(self):
        for value in self.data['comparability'].values():
            self.assertTrue(value['same'])
            self.assertEqual(value['baseline'],value['candidate'])

    def test_no_private_fields(self):
        text = (ROOT / 'demo.json').read_text()
        for forbidden in ['/Users/', '/home/', '/workspace/', 'http://127.0.0.1:', 'human-labels', 'source_message_id', 'reviewer', 'endpoint', 'Authorization:', 'api_key', 'access_token']:
            self.assertNotIn(forbidden,text)

    def test_screenshots_explicitly_absent(self):
        for case in self.data['cases']:
            for run in case['runs']:
                self.assertEqual(run['screenshot_status'],'not_included_not_visually_verified')
                for observation in run['observations']:
                    self.assertNotIn('screenshot',observation)
        self.assertEqual(list(ROOT.glob('*.png')),[])

    def test_trace_references_order(self):
        for case in self.data['cases']:
            for run in case['runs']:
                self.assertEqual([e['id'] for e in run['events'] if e['type']=='observation'], [o['id'] for o in run['observations']])
                self.assertEqual([e['index'] for e in run['events']],list(range(1,len(run['events'])+1)))

    def test_changed_or_missing_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial=Path(tmp)/'trial';trial.mkdir()
            (trial/'source.json').write_text('unreviewed private source')
            for name in ['source.json','missing.json']:
                with self.assertRaisesRegex(ValueError,'Source differs'):
                    builder.collect(Path(tmp),'trial',{name:'0'*64})

    def test_origin_sanitization(self):
        self.assertEqual(builder.clean({'s':'GET http://127.0.0.1:1234/api/tasks, status done'}),{'s':'GET [local fixture]/api/tasks, status done'})
        self.assertEqual(builder.clean(['done',True,4]),['done',True,4])

    def test_script_escaping(self):
        self.assertNotIn('</script',(ROOT/'demo-data.js').read_text().lower())
        self.assertNotIn('<',(ROOT/'demo-data.js').read_text())
