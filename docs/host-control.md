# Host-selected action controller and test harness

The existing Claude or Codex session selects each action. No Ollama process,
model endpoint, API key, or additional paid service is used. This is a new input
transport for the existing bounded controller, not a replacement browser tool.

## Two separate workflows

- A host-native skill can use its host's approved browser tools. Those tools have
  their own permission rules. The skill's instructions are not a security sandbox.
- The controlled harness below uses the packaged capability-gated browser worker
  and disposable loopback fixtures. Only operator-authored action IDs are accepted.
  Do not describe native browser sessions as having the harness's code-enforced controls.

The harness reuses the existing origin/path/method/body allowlists, action-use and
wall-clock budgets, fresh browser context, screenshot/trace binding, ordered
checkpoints, precondition gates, and independently checked final verdict. It
never adds an alternative direct-request path, general JavaScript action, or
arbitrary selector/URL. A host cannot authorize its own capabilities through a
bug report, retrieved knowledge, or page instructions.

## Existing prerequisites

Use Python 3.10+, existing Node.js, an existing Playwright module, and an existing
Chromium-compatible browser. The browser config accepts the existing controller's
configuration keys, including `node_executable`, `playwright_module`,
`executable_path`, `headless`, `timeout_ms`, and `process_timeout_seconds`.
Executable/module paths are trusted operator configuration, never report content.
This package installs nothing and changes no global host/MCP/browser configuration.
If the environment prevents Chromium startup, report that failure. Do not weaken
sandbox/security settings, download software, or claim browser verification.

## One controlled host session

From the repository root, start this command using the host's background-task
facility. Choose a **new** directory for each trial. The `serve` command stays
running while it holds the fixture and browser open.

Use a physical directory path without symlinked ancestors for run artifacts.
The examples use a repository-local `runs/` directory. On macOS, paths such as
`/tmp` and `/var` are often symlink aliases; use their physical paths if testing
outside the repository. Artifact verification intentionally rejects symlinks.

```sh
python -m evaluations.host_control serve \
  --run-dir runs/host-search-trial \
  --case dev-04-search-fixed \
  --host codex \
  --browser-config /path/to/existing/browser.json
```

For Claude, use `--host claude`. That flag is an audit label, not authentication.
An optional `--session-label` is also self-reported. Only development cases are
available in this harness; author-visible task definitions are not a blind benchmark.

Poll the request:

```sh
python -m bug_validator.host next --run-dir runs/host-search-trial
```

`state` can be `starting`, `waiting`, `accepted`, `rejected`, or `completed`.
When `waiting`, read `request.system`, `request.payload`, and `request.schema`.
Use only those public inputs, current observations, and the permitted action IDs
to choose the next step. Do not inspect evaluator source, private oracle output,
server state, or scripted recipes to answer the trial. There is no OS-level
isolation preventing such reads; the experiment requires a cooperative host.

Write one decision as JSON, for example after checking that `open` is permitted:

```json
{"action_id":"open","reason":"Open the approved page to inspect the initial state.","verdict":null,"evidence_ids":[]}
```

Submit the decision using the **current** request ID:

```sh
python -m bug_validator.host submit \
  --run-dir runs/host-search-trial \
  --request-id THE_CURRENT_32_CHARACTER_REQUEST_ID \
  --decision runs/one-decision.json
```

`submitted` is an acknowledgment of file submission, not proof of execution.
Poll again for the next request or completion. Do not submit twice, batch future
actions, fabricate observations, or retry a rejected trial until it succeeds.
Schema-invalid submitted answers are recorded by the controller and terminate
inconclusive. Stale IDs, invalid JSON files, and duplicate submissions are rejected
by the client without advancing the browser. Malformed response envelopes, wrong
session/hash/nonce, size violations, and timeout fail closed in the controller.

Action-phase decisions must have `verdict:null` and `evidence_ids:[]`. In the
assessment phase, use the exact required checkpoint IDs and infer the outcome
from actual captured requirements. `finish` is independently checked; an incorrect
verdict, missing checkpoint, failed precondition, or broken artifact leaves the
trial inconclusive. `stop` remains available with the active phase's schema.

The existing fixture budget is 480 seconds, including host deliberation. No
extension is made automatically. Prefer an explicit `stop` decision for orderly
cancellation. KeyboardInterrupt is captured as inconclusive with browser cleanup.
An abrupt process kill or machine failure may leave stale `waiting` status; it is
not completion evidence. Do not reuse that run directory. Archives without a
completed manifest cannot pass verification.

## Operator-provided fixture inputs

For an already-running authorized fictional loopback fixture:

```sh
python -m bug_validator.host serve \
  --run-dir runs/host-custom-trial \
  --bug bug.json --kb kb.json --authorization authorization.json \
  --host claude --browser-config /path/to/existing/browser.json
```

The operator must review and authorize the capability document independently of
the host-generated report. The document binds the exact bug hash and fixes all
action arguments and objective requirements. This command produces evidence but
does **not** provide an independent fixture oracle or external production adapter.
Use the evaluation harness for independently graded controlled outcomes.

## Scripted controls, separately labeled

```sh
python -m evaluations.host_control scripted \
  --run-dir runs/host-scripted-controls \
  --host other --browser-config /path/to/existing/browser.json
```

This deliberately scripted policy exercises the same mailbox/controller/browser
path. It is **not** a live Claude or Codex session and measures no model quality.
The summary reports browser participation, decisions, completed exercises, and
expected refusal passes separately. A browser startup failure can never count as
a completed exercise; preflight refusal cases are not browser successes.

The token-free GitHub Actions workflow runs this scripted mailbox path alongside
the legacy browser control and replays every development case archive. It also
checks that both host skill adapters match the canonical source. These CI checks
do not launch Claude/Codex or measure model quality.

## Evidence and replay

Each case records:

- `agent/report.json`, screenshots, `trace.jsonl`, and `execution.json`.
- One `agent/host-NNN.json` request/response artifact per decision attempt.
- Session and request IDs, request/response hashes, and the declared host identity.
- Public inputs plus independent fixture state, request journal, and expected case.
- `grade.json`, `manifest.json`, and an exact file hash inventory.

Regrade one completed case with the exact source version that produced it:

```sh
python -m evaluations.host_control verify --run-dir runs/host-scripted-controls/dev-04-search-fixed
```

Replay checks the full file inventory, source fingerprints, canonical expected
case, public input binding, final status, and independently recomputed grade.
Requests are rebound to the actual prior observation, history, capabilities,
phase, and checkpoint results rather than trusting hashes alone. Changed or
missing files, duplicate checks, stale requests, and inconsistent case manifests fail. The suite-level summary is an informational
aggregation; verify each case directory rather than trusting its pass count.
`verified:true` means archive consistency, not necessarily a passing outcome;
check `deterministic_pass` and the command exit status.

Host identity stays `self-reported-not-authenticated`, and
`model_quality_claim_eligible` is always false. A genuine host-session observation
must additionally identify how the real host was launched/observed outside this
transport. Even then, a few author-visible synthetic cases do not establish
model-wide reliability, explanation quality, or arbitrary-site readiness.

The mailbox and browser instrumentation run under a trusted operator OS user.
Nonce/hash checks prevent stale, corrupt, and mismatched submissions. They are
not authentication or a sandbox against a malicious host that can edit code,
replace every artifact, access the filesystem, or invoke other tools directly.
