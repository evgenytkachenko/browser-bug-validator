"""Fixture-only tests. No values here are actual human calibration labels."""
import hashlib,json,unittest
from pathlib import Path
from record_labels import convert
ROOT=Path(__file__).parent

class CalibrationTests(unittest.TestCase):
 def test_frozen_packet_hashes(self):
  index=json.loads((ROOT/'packets/index.json').read_text())
  self.assertEqual([r['case_id'] for r in index['packets']],list('ABCDEF'))
  for row in index['packets']:
   packet=json.loads((ROOT/'packets'/row['packet_file']).read_text())
   actual=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
   self.assertEqual(actual,row['packet_id'])
   self.assertNotIn('human_labels',packet)
   self.assertNotIn('expected_verdict',packet)
 def test_template_is_blank(self):
  data=json.loads((ROOT/'human-labels-template.json').read_text())
  for row in data['labels']:
   self.assertIsNone(row['reviewer']);self.assertIsNone(row['reviewed_at']);self.assertIsNone(row['rationale'])
   self.assertTrue(all(v is None for v in row['dimensions'].values()))
 def test_no_ratings_can_be_inferred(self):
  with self.assertRaises(ValueError):convert({}, {'packets':[]})
 def test_explicit_synthetic_fixture_transcription(self):
  fixture={'reviewer':'UNIT TEST ONLY','reviewed_at':'2000-01-01T00:00:00Z','source_message_id':'UNIT-TEST-NOT-A-USER-MESSAGE','labels':[{'case_id':'Z','dimensions':{'groundedness':'?','relevance':'P','uncertainty':'F'},'rationale':'SYNTHETIC UNIT FIXTURE; NOT A HUMAN LABEL'}]}
  result=convert(fixture,{'rubric_version':'semantic-v1','packets':[{'case_id':'Z','packet_id':'unit-fixture'}]})
  self.assertEqual(result['labels'][0]['dimensions'],{'groundedness':'unknown','relevance':'pass','uncertainty':'fail'})
  self.assertEqual(result['labels'][0]['rationale'],fixture['labels'][0]['rationale'])
 def test_missing_reason_is_rejected(self):
  fixture={'reviewer':'UNIT TEST ONLY','reviewed_at':'2000-01-01T00:00:00Z','source_message_id':'UNIT-TEST-NOT-A-USER-MESSAGE','labels':[{'case_id':'Z','dimensions':{'groundedness':'?','relevance':'P','uncertainty':'F'},'rationale':''}]}
  with self.assertRaises(ValueError):convert(fixture,{'rubric_version':'semantic-v1','packets':[{'case_id':'Z','packet_id':'unit-fixture'}]})

if __name__=='__main__':unittest.main()
