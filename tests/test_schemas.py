"""Regression tests use frozen model outputs or fake transport, not fresh model trials."""
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from bug_validator.common import ValidationError
from bug_validator.model import LocalModel
from bug_validator.schemas import assessment_schema, plan_schema, reject_duplicate_fields, validate_response

PLAN = {'journey_id':'task-status-persistence','target_task_id':'T-101','expected_status':'done'}
SCHEMA = plan_schema('task-status-persistence')

class FakeOpener:
    def __init__(self, content=None, error=None):
        self.requests=[]; self.content=content; self.error=error
    def open(self, request, timeout):
        self.requests.append(json.loads(request.data))
        if self.error: raise self.error
        return io.BytesIO(json.dumps({'message':{'content':self.content}, 'prompt_eval_count':40,'eval_count':20}).encode())

class PhaseSchemaTests(unittest.TestCase):
    def test_valid_plan_and_null_abstention(self):
        validate_response(PLAN,SCHEMA)
        validate_response({**PLAN,'journey_id':None},SCHEMA)
    def test_all_ten_observed_v01_failures_still_rejected(self):
        rows=json.loads((Path(__file__).parent/'fixtures/v01_invalid_plans.json').read_text())
        self.assertEqual(len(rows),10)
        for row in rows:
            with self.subTest(trial=row['source_trial']), self.assertRaises(ValidationError):
                validate_response(json.loads(row['raw_content']),SCHEMA)
    def test_missing_wrong_typed_and_extra_fields_rejected(self):
        for value in [{}, {**PLAN,'verdict':'confirmed'}, {**PLAN,'target_task_id':101},
                      {**PLAN,'expected_status':'delete'}, {**PLAN,'journey_id':'admin-delete'}]:
            with self.subTest(value=value), self.assertRaises(ValidationError): validate_response(value,SCHEMA)
    def test_assessment_cannot_invent_citations_or_duplicate(self):
        schema=assessment_schema(['obs-0001','obs-0002','obs-0003'])
        good={'saved_status':'done','reloaded_status':'todo','status_persisted':False,'evidence_ids':['obs-0002','obs-0003'],'explanation':'Status reverted on reload.'}
        validate_response(good,schema)
        for value in [{**good,'evidence_ids':['obs-0002','made-up']}, {**good,'evidence_ids':['obs-0002','obs-0002']},
                      {**good,'explanation':''}, {**good,'other':'value'}]:
            with self.assertRaises(ValidationError): validate_response(value,schema)
    def test_duplicate_json_fields_rejected(self):
        with self.assertRaises(ValidationError): json.loads('{"target_task_id":"T-202","target_task_id":"T-101"}',object_pairs_hook=reject_duplicate_fields)
    def test_structured_schema_is_actually_sent(self):
        with tempfile.TemporaryDirectory() as d:
            model=LocalModel({},Path(d)); opener=FakeOpener(json.dumps(PLAN));model.opener=opener
            prompt=(Path(__file__).resolve().parents[1]/'skills/browser-bug-validator/references/plan.md').read_text()
            answer=model.ask('plan',prompt,{'bug':PLAN},SCHEMA)
            self.assertEqual(answer,PLAN);self.assertEqual(len(opener.requests),1)
            self.assertEqual(opener.requests[0]['format'],SCHEMA)
            self.assertIs(opener.requests[0]['format']['additionalProperties'],False)
            self.assertEqual(opener.requests[0]['messages'][0]['content'],prompt)
            self.assertEqual(model.calls[0]['status'],'completed')
    def test_noncompliant_response_not_salvaged_and_is_retained(self):
        raw=json.dumps({**PLAN,'verdict':'confirmed','evidence':{'fabricated':True}})
        with tempfile.TemporaryDirectory() as d:
            model=LocalModel({},Path(d));model.opener=FakeOpener(raw)
            with self.assertRaises(ValidationError): model.ask('plan','Planning only',{'bug':PLAN},SCHEMA)
            self.assertEqual(len(model.opener.requests),1);self.assertEqual(model.calls[0]['status'],'error')
            artifact=json.loads((Path(d)/'model-001-plan.json').read_text())
            self.assertEqual(artifact['response']['message']['content'],raw)
    def test_unsupported_schema_api_never_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            model=LocalModel({},Path(d));model.opener=FakeOpener(error=ValueError('Server rejects format schema'))
            with self.assertRaises(ValidationError): model.ask('plan','Planning only',{'bug':PLAN},SCHEMA)
            self.assertEqual(len(model.opener.requests),1);self.assertEqual(model.calls[0]['status'],'error')
    def test_http_schema_rejection_body_is_retained_without_retry(self):
        body=b'{"error":"invalid format: unsupported JSON schema"}'
        error=urllib.error.HTTPError('http://127.0.0.1:11434/api/chat',400,'Bad Request',{},io.BytesIO(body))
        with tempfile.TemporaryDirectory() as d:
            model=LocalModel({},Path(d)); model.opener=FakeOpener(error=error)
            with self.assertRaises(ValidationError): model.ask('plan','Planning only',{'bug':PLAN},SCHEMA)
            self.assertEqual(len(model.opener.requests),1)
            artifact=json.loads((Path(d)/'model-001-plan.json').read_text())
            self.assertEqual(artifact['http_status'],400);self.assertEqual(artifact['raw_response'],body.decode())
            self.assertFalse(artifact['raw_response_truncated'])
    def test_http_error_body_is_bounded(self):
        body=b'x'*(1024*1024+100)
        error=urllib.error.HTTPError('http://127.0.0.1:11434/api/chat',400,'Bad Request',{},io.BytesIO(body))
        with tempfile.TemporaryDirectory() as d:
            model=LocalModel({},Path(d));model.opener=FakeOpener(error=error)
            with self.assertRaises(ValidationError):model.ask('plan','Planning only',{'bug':PLAN},SCHEMA)
            artifact=json.loads((Path(d)/'model-001-plan.json').read_text())
            self.assertEqual(len(artifact['raw_response']),1024*1024);self.assertTrue(artifact['raw_response_truncated'])
    def test_unknown_schema_keyword_fails_closed(self):
        with self.assertRaises(ValidationError): validate_response(PLAN,{**SCHEMA,'custom_relaxation':True})

if __name__=='__main__':unittest.main()
