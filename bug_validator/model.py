"""Optional real Ollama adapter. Only loopback endpoints; never an implicit cloud fallback."""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from .common import ValidationError, digest, loopback_origin, write_json
from .schemas import validate_response, reject_duplicate_fields

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValidationError("Model endpoint redirects are forbidden")

class LocalModel:
    def __init__(self, config, output_dir):
        if not isinstance(config, dict):
            raise ValidationError("local-model requires a configuration object")
        self.origin = loopback_origin(config.get("endpoint", "http://127.0.0.1:11434"))
        self.name = config.get("model", "llama3.1:8b")
        if not isinstance(self.name, str) or not self.name or len(self.name) > 120:
            raise ValidationError("Invalid model name")
        self.temperature = config.get("temperature", 0.2)
        if not isinstance(self.temperature, (int, float)) or not 0 <= self.temperature <= 2:
            raise ValidationError("temperature must be between 0 and 2")
        self.seed = config.get("seed")
        if self.seed is not None and (type(self.seed) is not int or not 0 <= self.seed < 2**31):
            raise ValidationError("seed must be a nonnegative 32-bit integer")
        self.timeout = config.get("timeout_seconds", 180)
        if not isinstance(self.timeout, (int, float)) or not 1 <= self.timeout <= 600:
            raise ValidationError("Model timeout must be between 1 and 600 seconds")
        self.output_dir = output_dir
        self.calls = []
        # Ignore proxy environment variables: public reports must never leave loopback.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def ask(self, stage, system, payload, schema):
        request = {"model": self.name, "stream": False, "format": schema, "keep_alive": 0,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                   "options": {"temperature": self.temperature, "num_predict": 320, "num_ctx": 4096}}
        if self.seed is not None:
            request["options"]["seed"] = self.seed
        started = time.monotonic()
        call = {"id": f"model-{len(self.calls)+1:03d}", "stage": stage, "backend": "ollama",
                "endpoint": self.origin, "model": self.name, "temperature": self.temperature,
                "seed": self.seed, "request_sha256": digest(request), "response_schema_sha256": digest(schema), "status": "started"}
        self.calls.append(call)
        artifact = {"request": request}
        try:
            req = urllib.request.Request(self.origin + "/api/chat", json.dumps(request).encode(),
                                         {"Content-Type": "application/json"}, method="POST")
            with self.opener.open(req, timeout=self.timeout) as response:
                raw = response.read(1024 * 1024 + 1)
            artifact["raw_response"] = raw[:1024 * 1024].decode("utf-8", errors="replace")
            artifact["raw_response_truncated"] = len(raw) > 1024 * 1024
            if len(raw) > 1024 * 1024:
                raise ValidationError("Model response exceeds size budget")
            parsed = json.loads(raw)
            artifact["response"] = parsed
            content = parsed.get("message", {}).get("content", "")
            answer = json.loads(content, object_pairs_hook=reject_duplicate_fields)
            validate_response(answer, schema)
            if not isinstance(answer, dict):
                raise ValidationError("Model must return one JSON object")
            artifact["response"] = parsed
            call.update(status="completed", response_sha256=digest(parsed), answer=answer,
                        prompt_tokens=parsed.get("prompt_eval_count"), output_tokens=parsed.get("eval_count"))
            return answer
        except Exception as exc:
            if isinstance(exc, urllib.error.HTTPError):
                artifact["http_status"] = exc.code
                try:
                    error_bytes = exc.read(1024 * 1024 + 1)
                    artifact["raw_response"] = error_bytes[:1024 * 1024].decode("utf-8", errors="replace")
                    artifact["raw_response_truncated"] = len(error_bytes) > 1024 * 1024
                except Exception as read_error:
                    artifact["error_body_read_failure"] = type(read_error).__name__
            call.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:500]}")
            artifact["error"] = call["error"]
            raise ValidationError("Real local model call failed: " + call["error"]) from exc
        finally:
            call["elapsed_seconds"] = round(time.monotonic() - started, 3)
            call["artifact"] = f"{call['id']}-{stage}.json"
            write_json(self.output_dir / call["artifact"], artifact)
