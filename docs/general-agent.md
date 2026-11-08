# Reusable browser loop, v0.4

## What changed

`python -m bug_validator run-general` runs a persistent browser session and consults a real local model **after every browser action**. The model reads the bug report, relevant KB entries, permitted action descriptions, current probe values, visible page text, prior actions, and captured checkpoints. It selects one action ID, sees its actual result, and chooses again. There is no fixture-specific recipe or deterministic fallback in the production loop.

This is a reusable **controlled-fixture agent**, not an arbitrary-website agent. A human operator still authors and reviews the exact capabilities, fixed inputs, probes, and objective requirements for each test. Different features no longer need a new orchestrator, but new sites need a reviewed capability file and evaluation fixtures. The included workflows exercise status persistence, search correctness, and invalid quantity validation.

The original `run` command, task-board controller, and v0.3 evaluation suite remain intact. Original v0.3 results apply only to that version's two-call workflow. They are not v0.4 quality evidence.

## Trust and permission boundaries

Three inputs have different roles:

1. **Bug report:** untrusted `id`, `title`, `description`, and optional `journey_id`. It cannot contain authorization. Reports are allegations, not observed facts.
2. **Knowledge base:** untrusted `entries` with unique IDs, titles, and descriptions. Lexical relevance retrieval supplies up to three entries, keeping an explicitly requested journey first. Insufficient or ambiguous matches stop before browser use. KB instructions cannot create capabilities.
3. **Operator capability file:** independently supplied, explicitly authorized scope and verifiable test specification. Its `bug_sha256` binds the exact report text. It must never be generated from page/KB content and automatically trusted. The operator is responsible for ensuring the test requirements actually correspond to the reported bug. A matching hash proves binding, not semantic correctness.

Only disposable, fictional data is supported. Do not use real credentials, production writes, payment/order controls, messages, account settings, or personal/sensitive records. Creating the capability file is not a substitute for obtaining the user's permission. Every endpoint and effect must already be authorized. An exact GET grant can still have server-side effects on a badly designed application; review it as an operation, not merely as an HTTP verb.

Browser request routing is an application-level control, not a hostile-code sandbox or complete OS egress firewall. Browser-engine facilities and vulnerabilities outside the routed request layer are not proven confined. Never load hostile code or rely on these controls to protect secrets. Browser and fixture processes share the host user's filesystem permissions.

## Capability file

The schema is strictly validated by `bug_validator/general_contracts.py`. Unknown fields and unsupported operations are rejected rather than stripped. Top-level fields:

- `schema_version`: `1`.
- `bug_sha256`: `bug_validator.common.digest(bug)` using canonical JSON, not the hash of pretty-printed input bytes.
- `origin`: exact numerical HTTP loopback origin with a nonzero, non-default explicit port, such as `http://127.0.0.1:41083`.
- `get_paths`: exact authorized request targets including any fixed query, such as `/search` and `/api/search?q=alpha`. No wildcard, percent-encoded target, redirect, protocol-relative target, or path traversal. Narrow canonical ASCII characters only.
- `acknowledge_mutations`: explicit boolean. Required `true` for any write grant.
- `actions`: map of action IDs to the fields below. Model output contains only an action ID, never executable arguments.
- `probes`: map of probe IDs to `{test_id, kind}`, where `kind` is `text`, `value`, or `count`. Only fixed `data-testid` identifiers are supported.
- `checkpoints`: ordered evidence requirements described below.
- `budgets`: optional `max_steps` (1–30, default 12) and `max_seconds` (5–600, default 180).

Each action has `kind` and `description`. Supported kinds:

- `navigate`: requires a fixed `path` that is present in `get_paths`.
- `click`: requires a fixed `test_id`.
- `fill` / `select`: require fixed `test_id` and string `value`. The model cannot invent input text.
- `reload` / `observe`: no selector or input fields.

Optional action fields:

- `max_uses`: 1–5, default two for read/UI actions and one for a write. A write can never exceed one use.
- `wait_for`: `{probe, equals}`. Wait for an independent UI acknowledgment, such as “Search complete”, rather than the outcome being tested. Otherwise a real bug may look like a timeout instead of a failed requirement.
- `request`: exact `{method, path, json}` for one POST/PUT/PATCH, only on a click action. The transport permits this body and target only while that action is armed, consumes the grant once, and requires the corresponding response. A wrong body/target, second request, or unrelated request is blocked. No auth, cookie, or arbitrary header propagation.

Clicks/fills/selects without a write grant may only produce permitted reads. They cannot acquire write permission from the page or from a model explanation. Until a successful browser observation exists, only authorized `navigate` actions (or stop) are exposed to the model. This mirrors the worker's existing about:blank guard; it does not choose a route or execute navigation automatically. Multiple authorized navigation choices remain model decisions. Navigation counts toward the same budget.

A text/value probe must find exactly one matching element or returns null. Missing/ambiguous required probes make the result inconclusive. `count` supports checks for presence/absence; counts and extracted text are bounded. Probe reading and screenshots use fixed browser code, not model-generated evaluation scripts.

## Objective evidence and verdicts

Each checkpoint is `{id, after_action, checks}`. A check is `{probe, op, value, role}`:

- `op`: `equals`, `not_equals`, or string `contains`.
- `role`: `precondition` or `requirement`.

Only the next pending checkpoint can be captured; it is bound to the observation immediately after its named action. An out-of-order action cannot backfill a prior checkpoint. Intermediate actions remain model-selected. Once captured, checkpoints cannot be rewritten by repeating an action.

The runtime, not the model or page, chooses the response phase. Before all checkpoints are captured, the action schema permits only available action IDs or `stop`, requires `verdict: null`, and requires empty citations. This includes stopping: the host keeps its inconclusive result. `finish` cannot be emitted in this phase. Once all required checkpoints have been captured, the assessment schema permits only `finish` or `stop`, exposes exactly the captured checkpoint observation IDs, and allows no more browser actions. The citation array must contain that entire set exactly once, including on assessment-phase `stop`, which also requires an inconclusive verdict. The runtime supplies this required set from actual checkpoint records, never from hidden evaluation labels. The model still chooses each browser action and whether to finish or abstain; the host does not infer or execute setup actions.

The next checkpoint's `after_action` is a measurement trigger, not necessarily the next action. The model must inspect current values and choose any necessary permitted input/setup actions before triggering a check. No hard-coded fixture recipe is used in production.

A precondition failure stops the run as inconclusive. Once all checkpoints are captured, at least one failed requirement means confirmed; all requirements holding means not_reproduced **for this operator-defined trial only**. This mapping is code, not free-form model judgment. The model must still issue a matching finish and cite exactly all checkpoint observations. Cardinality, uniqueness and allowed IDs are encoded in the response schema as well as checked locally. This is schema-enforced citation completeness, not evidence that the model independently learned citation selection. Wrong verdicts, invented/missing/duplicate citations, premature finishes, malformed JSON, extra fields, exhausted actions, and incomplete execution remain inconclusive. There is no correction or fallback that masks a model error.

A status example captures initial `todo`, then saved `done` as preconditions, then tests `done` after reload as the requirement. Search and quantity use different action types and independent predicates. The evaluator also checks server-side audit/state, so forged observation claims alone cannot pass the evaluation.

An observation contains ID, exact action ID, URL, probe values, bounded page text, screenshot filename, and screenshot hash. Model planning uses text/probes, not screenshot pixels; screenshots are retained for evidence review. Terminal evidence checks bind every per-step observation and action to the final worker result, verify screenshots and the trace hash, and compare trace observations to actual reported values/order. A blocked request or failed action prevents a conclusive verdict. Evidence hashes detect mismatches; they are not a tamper-proof proof against a hostile host user.

## Commands

Use existing installed dependencies only. This package does not install or download a browser or model.

```bash
python -m unittest discover -s tests -v
python -m bug_validator run-general \
  --bug bug.json --kb kb.json --authorization authorization.json \
  --model-config model.local.json --browser-config browser.local.json \
  --output runs/general-single
```

Model config is the existing local Ollama format, for example `{ "endpoint": "http://127.0.0.1:11434", "model": "llama3.1:8b", "temperature": 0.2, "timeout_seconds": 180 }`. Model output is checked against a closed JSON schema on each decision. There is no cloud fallback. Browser configuration uses the existing `node_executable`, `playwright_module`, `executable_path`, `headless`, `timeout_ms` fields. General mode `process_timeout_seconds` is a **per worker response** budget from 1–60 seconds, default 30, not the complete model-run timeout.

Run the controlled development cases:

```bash
python -m evaluations.general_run --backend scripted-control --trials 1 \
  --split development --browser-config browser.local.json \
  --timeout 600 --output runs/general-control
python -m evaluations.general_run --backend local-model --trials 2 \
  --split development --browser-config browser.local.json \
  --model-config model.local.json --timeout 600 --output runs/general-model
```

`scripted-control` is deliberately a test-double policy with fixture-specific recipes. It tests the real browser integration **only if the browser actually ran**. It is never an LLM score. `local-model` is the actual per-step model loop. Unit tests that inject both a model and browser are separately labeled and cannot establish either live capability.

The harness creates each isolated server, public inputs, and the operator grant; fixture modes/expected verdicts and server audit state remain outside the model input and in a separate harness process. Every trial, including blockers and refusals, is retained. Model/version and source fingerprints make comparisons auditable. Do not mix backend scores.

## Evaluation boundaries

Development has 11 author-visible cases across three feature families, including permission refusal, missing requirement, blocked access, an injected page note, and an unrelated warning. Six alternate-input cases are reserved for a frozen-revision transfer run. These are author-visible, **not a blind/unseen holdout**. The command requires the unchanged development manifest and explicit acknowledgment before reserved transfer. Tuning after inspecting those results contaminates that split.

Fixtures are deterministic; repeated trials explore model variation, not a representative sample of real websites. Semantic explanation quality remains unverified without independent review. Even a perfect controlled score would not prove arbitrary-site readiness, robust natural-language planning, or safe operation on untrusted production pages.

See `docs/general-results.md` for the verification record. Keep local configs, raw run directories, completed labels, screenshots, and credentials out of commits. Raw artifacts may include all supplied page/KB/report text.
