# Agent and browser contracts

The Python library entrypoint is `bug_validator.run_agent(bug_report, knowledge_base, base_url, output_dir, backend='deterministic', model_config=None, browser_config=None)`. The output directory must be new or empty. Every completed call writes `report.json` and `report.md`; execution adds `execution.json`, `trace.jsonl`, and screenshots. The CLI exits 2 for an inconclusive report and 0 for a conclusive verdict. Evaluation must read the report, not infer correctness from exit status.

## Bug input

```json
{
  "id": "status-001",
  "title": "Done status reverts after reload",
  "description": "Save the task as done, reload, and see whether the status persisted.",
  "target_task_id": "T-101",
  "expected_status": "done",
  "authorization": {
    "origin": "http://127.0.0.1:PORT",
    "allowed_task_ids": ["T-101"],
    "allowed_actions": ["select_status", "save", "reload"]
  }
}
```

The caller must provide truthful authorization, not infer it from third-party text. This first version only supports HTTP loopback origins with explicit ports. There are no credentials, uploads, general-purpose JavaScript tools, shell actions, or public-site mutations in the agent action space. Optional `journey_id` identifies an already-known KB entry; normal examples omit it to exercise retrieval.

## Knowledge base

The root is `{ "schema_version": 1, "entries": [...] }`. A supported entry is:

```json
{
  "id": "task-status-persistence",
  "title": "Task status persistence",
  "description": "Save a task status then reload; the saved status must persist.",
  "keywords": ["status", "save", "reload", "persist", "done"],
  "route": "/",
  "selectors": {
    "ready": "board-ready", "blocked": "access-blocked",
    "row": "task-row-{task_id}", "status": "task-status-{task_id}",
    "save": "save-task-{task_id}", "persisted": "persisted-status-{task_id}"
  },
  "workflow": ["observe_initial", "select_status", "save", "observe_saved", "reload", "observe_reloaded"]
}
```

Selectors are the exact reviewed data-testid templates above, not arbitrary CSS/JS or interchangeable task selectors. The controller scopes fields under the target row and reads the rendered task ID before attributing evidence. Additional journeys are not supported until an adapter, scope policy, and evals are added. Lexical retrieval is deliberately transparent and conservative, not an embedding search engine.

## Browser configuration

```json
{
  "node_executable": "/absolute/path/to/node",
  "playwright_module": "/absolute/path/to/playwright",
  "executable_path": "/absolute/path/to/chrome",
  "headless": true,
  "timeout_ms": 8000,
  "process_timeout_seconds": 60
}
```

Only a trusted operator may set executable/module paths. Playwright 1.48+ is required for WebSocket blocking. The browser has a fresh profile, no stored credentials, no permissions, blocked service workers, and a request capability guard. Only GET `/`, GET `/api/tasks`, GET `/favicon.ico`, and one armed POST `/api/tasks/TARGET/status` with the exact allowed status may proceed. Requests are proxied through a native loopback HTTP transport with no redirects, proxies, retries, or cookies; streamed response bodies are capped at 256 KiB. Popups and downloads are blocked. Limits are 60 requests, 400 trace events, 20,000 characters per event, and fixed 1100×800 screenshots. Chromium's sandbox is enabled. This application-level guard is not an OS/network sandbox and does not prove containment of browser vulnerabilities. Use a controlled fixture with fictional data.

## Local model configuration

```json
{"endpoint":"http://127.0.0.1:11434","model":"llama3.1:8b","temperature":0.2,"seed":42,"timeout_seconds":180}
```

The backend performs one planning call and, after a complete browser reproduction, one evidence-assessment call. It uses Ollama `/api/chat`, phase-specific closed JSON Schema output, 4096-token context, a 320-token output cap, and `keep_alive: 0`. Proxy environment variables and redirects are disabled. Each response, request hash, timing, model, sampling parameters, and evidence are retained. No model is downloaded, installed, or pulled automatically. Invalid model output or disagreement with browser evidence is inconclusive. Model-selected target or status changes are rejected before browser work.

## Report schema v1

- `verdict`: `confirmed`, `not_reproduced`, or `inconclusive`.
- `scenario_id`: copies only public `bug.id`; no scenario variant/truth is accepted.
- `backend`: explicit `deterministic` or `local-model`.
- `observations`: IDs, phases (`initial`, `saved`, `reloaded`, `blocked`), browser URL, bounded visible text, target/status values, screenshot file and SHA256.
- `steps`: action name, status, observation IDs. Failed actions are preserved.
- `assertions`: criterion, expected/observed status, whether the expectation was met, evidence IDs.
- `model_calls`: actual calls only; request/response files and hashes, model sampling settings, timings and failures.
- `provenance`: bug/KB hashes, skill hash, source hashes and controller trace hash.
- `limitations`: blockers, scope, backend limitations.

The report is an agent artifact, not independent truth. The evaluator must check the fixture's own audit log and final state, observed screenshots/trace, and expected task outcome separately. Retain a trusted run manifest and external artifact hashes to detect later edits. A report's self-declared hashes alone are not an authenticity guarantee.

### v0.2 phase separation

Planning loads `skills/browser-bug-validator/references/plan.md`; assessment loads `references/assess.md`. The full end-to-end skill is not inserted into either model call. Each request supplies `format` as a JSON Schema object with required fields and `additionalProperties: false`. Responses are independently validated against the same small internal schema, duplicate JSON keys are rejected, and original raw responses are retained even on failure. The plan equality check and browser-evidence verdict checks are unchanged. There is no fallback to generic JSON and no repair that drops unexpected fields.

### v0.3 observation proposition

Assessment output is now exactly `{saved_status, reloaded_status, status_persisted, evidence_ids, explanation}`. The first two fields must match the actual saved/reloaded observation strings. `status_persisted` must be a boolean equal to `saved_status == expected_status and reloaded_status == expected_status`, after validating that the save reached the expected status; null or disagreement is inconclusive. The runner then maps true to `not_reproduced` and false to `confirmed`, and still compares that result with its existing admissibility check. No model conclusion is silently ignored or repaired. Assessment input distinguishes the authoritative expected behavior from the unverified reported symptom.
