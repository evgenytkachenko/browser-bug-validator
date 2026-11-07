"""Bind report provenance and real model-call artifacts to evaluator-known inputs."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from .grading import check
from .tasks import requires_exercise


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def grade_provenance(report, task, backend, output, bug, kb, root, model_config=None):
    checks = []
    provenance = report.get('provenance', {})
    expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((root/'bug_validator').iterdir()) if p.suffix in {'.py', '.cjs'}}
    checks.append(check('agent_source_provenance', provenance.get('source_sha256') == expected, 'Compare report source hashes with harness-read package files'))
    checks.append(check('public_input_provenance', provenance.get('bug_sha256') == canonical_digest(bug) and provenance.get('knowledge_base_sha256') == canonical_digest(kb), 'Public input hashes'))
    skill_path = root / 'skills' / 'browser-bug-validator' / 'SKILL.md'
    checks.append(check('skill_provenance', skill_path.is_file() and provenance.get('skill_sha256') == hashlib.sha256(skill_path.read_bytes()).hexdigest(), 'Skill byte hash'))
    checks.append(check('backend_matches_invocation', report.get('backend') == backend, report.get('backend')))
    calls = report.get('model_calls', [])
    if backend == 'deterministic':
        checks.append(check('reference_backend_has_no_model_claim', calls == [], len(calls) if isinstance(calls, list) else None))
        return checks
    required_stages = ['plan', 'assess'] if requires_exercise(task) else (['plan'] if task['mode'] == 'blocked' else [])
    expected_config = model_config or {}
    expected_model = expected_config.get("model", "llama3.1:8b")
    expected_endpoint = expected_config.get("endpoint", "http://127.0.0.1:11434").rstrip("/")
    expected_temperature = expected_config.get("temperature", 0.2)
    expected_seed = expected_config.get("seed")
    errors = []
    if not isinstance(calls, list) or [c.get('stage') for c in calls if isinstance(c, dict)] != required_stages:
        errors.append('Missing, duplicate, or unexpected model-call stages')
        calls = calls if isinstance(calls, list) else []
    for call in calls:
        try:
            if not isinstance(call, dict) or call.get('status') != 'completed' or call.get('backend') != 'ollama':
                raise ValueError('Model call not completed by local Ollama')
            parsed = urlsplit(call.get('endpoint', ''))
            if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or not parsed.port:
                raise ValueError('Model endpoint was not explicit loopback')
            artifact = call.get('artifact', '')
            path = (output / artifact).resolve()
            if not artifact or Path(artifact).name != artifact or not path.is_relative_to(output.resolve()):
                raise ValueError('Invalid model-call artifact path')
            value = json.loads(path.read_text())
            request, response = value['request'], value['response']
            if call.get('request_sha256') != canonical_digest(request) or call.get('response_sha256') != canonical_digest(response):
                raise ValueError('Model request/response hash mismatch')
            if call.get('model') != expected_model or call.get('endpoint') != expected_endpoint or call.get('temperature') != expected_temperature or call.get('seed') != expected_seed:
                raise ValueError('Model call differs from evaluator-invoked configuration')
            options = request.get('options', {})
            if options.get('temperature') != expected_temperature or options.get('seed') != expected_seed:
                raise ValueError('Model request sampling differs from invoked configuration')
            if request.get('model') != call.get('model') or call.get('answer') != json.loads(response['message']['content']):
                raise ValueError('Model identity/answer mismatch')
            if type(call.get('elapsed_seconds')) not in {int, float} or call['elapsed_seconds'] < 0:
                raise ValueError('Missing model call timing')
        except (ValueError, KeyError, OSError, TypeError) as exc:
            errors.append(str(exc))
    checks.append(check('real_local_model_artifacts', not errors, errors))
    return checks
