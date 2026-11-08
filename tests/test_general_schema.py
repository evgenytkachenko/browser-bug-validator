"""rc1 real-provider schema rejection regression, using explicit fake transport.

These tests model the observed Ollama compiler restriction, not a fresh live
model evaluation. A separate Mac run checks actual provider compatibility.
"""
import io
import json
import tempfile
import unittest
from pathlib import Path
from bug_validator.common import ValidationError
from bug_validator.general_contracts import decision_schema
from bug_validator.model import LocalModel
from bug_validator.schemas import validate_response

ANSWER = {'action_id': 'open', 'reason': 'Inspect the approved page.', 'verdict': None, 'evidence_ids': []}


def reject_empty_enums(schema):
    if isinstance(schema, dict):
        if 'enum' in schema and not schema['enum']:
            raise ValueError('enum must be a non-empty array')
        for value in schema.values():
            reject_empty_enums(value)
    elif isinstance(schema, list):
        for value in schema:
            reject_empty_enums(value)


class SchemaCheckingFakeOpener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout):
        body = json.loads(request.data)
        self.requests.append(body)
        reject_empty_enums(body['format'])
        return io.BytesIO(json.dumps({'message': {'content': json.dumps(ANSWER)}}).encode())


class GeneralSchemaProviderRegressionTests(unittest.TestCase):
    def test_empty_evidence_schema_accepts_only_an_empty_citation_array(self):
        schema = decision_schema(['open'], [])
        reject_empty_enums(schema)
        self.assertEqual(schema['properties']['evidence_ids']['maxItems'], 0)
        self.assertNotIn('enum', schema['properties']['evidence_ids']['items'])
        validate_response(ANSWER, schema)
        for ids in [['obs-0001'], ['invented'], [None], None, '']:
            with self.subTest(citations=ids), self.assertRaises(ValidationError):
                validate_response(dict(ANSWER, evidence_ids=ids), schema)

    def test_known_evidence_keeps_exact_enum_and_duplicate_rejection(self):
        schema = decision_schema([], ['obs-0001', 'obs-0002'], completion_ready=True)
        self.assertEqual(schema['properties']['evidence_ids']['items']['enum'], ['obs-0001', 'obs-0002'])
        validate_response(dict(ANSWER, action_id='finish', verdict='not_reproduced', evidence_ids=['obs-0001', 'obs-0002']), schema)
        for ids in [['fabricated'], ['obs-0001', 'obs-0001']]:
            with self.subTest(citations=ids), self.assertRaises(ValidationError):
                validate_response(dict(ANSWER, action_id='finish', verdict='not_reproduced', evidence_ids=ids), schema)

    def test_exhausted_action_schema_never_generates_empty_enums(self):
        schema = decision_schema([], [])
        reject_empty_enums(schema)
        self.assertEqual(schema['properties']['action_id']['enum'], ['stop'])
        validate_response(dict(ANSWER, action_id='stop'), schema)
        with self.assertRaises(ValidationError):
            validate_response(ANSWER, schema)

    def test_ollama_request_transmits_supported_schema_without_fallback(self):
        schema = decision_schema(['open'], [])
        legacy = json.loads(json.dumps(schema))
        legacy['properties']['evidence_ids']['items']['enum'] = []
        with self.assertRaisesRegex(ValueError, 'non-empty array'):
            reject_empty_enums(legacy)
        with tempfile.TemporaryDirectory() as directory:
            model = LocalModel({}, Path(directory))
            opener = SchemaCheckingFakeOpener()
            model.opener = opener
            answer = model.ask('decide', 'Use approved actions only.', {'current_observation': None}, schema)
            self.assertEqual(answer, ANSWER)
            self.assertEqual(len(opener.requests), 1)
            self.assertEqual(opener.requests[0]['format'], schema)
            self.assertEqual(model.calls[0]['status'], 'completed')
            with self.assertRaises(ValidationError):
                model.ask('decide', 'Use approved actions only.', {'current_observation': None}, legacy)
            self.assertEqual(len(opener.requests), 2)
            self.assertEqual(model.calls[-1]['status'], 'error')


if __name__ == '__main__':
    unittest.main()
