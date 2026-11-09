# Browser bug validator, v0.5.0 evaluation foundation

## Explore the recorded trace

Open [the local trace viewer](trace-viewer/index.html) to compare three real,
text-only historical cases from v0.2 and v0.3. Follow browser actions, model
outputs, safeguarded final reports and independent checks side by side. It needs
no model, API key, dependency installation or backend. The fixed-app example
shows a false-positive model proposal caught by a guardrail, then the checked-fact
contract that changed the system's final result. [Start here](trace-viewer/README.md)
for offline use, provenance and limits. Original screenshot pixels are not included;
these selected development examples are not new reliability measurements.

## Token-free continuous integration

[GitHub Actions](.github/workflows/evals.yml) checks the unit/contract suite,
development HTTP goldens, and all 11 development tasks using real Chromium with
a scripted decision policy. No model API key is required. A green run verifies
those controls, **not model reliability**. See [the CI setup and future real-model
plan](docs/ci-evaluations.md), including what a Bedrock integration would require.


## New: traceable evaluations and judge calibration tooling

v0.5 adds a versioned **17-task catalog**, executable development golden checks,
eight **synthetic judge-only reference examples**, a runnable independent local
judge for general-loop reports, explicit human calibration/validation, repeated
trial metrics and a consume-once transfer ledger. Start with the
[evaluation foundation guide](docs/evaluation-foundation.md) and
[task/golden catalog](docs/task-catalog.md). See the [v0.5 validation record](docs/v05-validation.md) for what actually ran and what remains unverified.

This improves the evaluation tooling, **not the agent's measured reliability**.
No new real-model run, real judge calibration, human label set or blind holdout
result is claimed. The recorded v0.4 result below remains the agent baseline.

## Preserved v0.4: reusable model-driven loop

v0.4 adds `run-general`: a persistent **observe → decide → browser action → observe** loop. The model reads different reports and relevant KB entries, selects one explicitly permitted action at a time, and receives actual browser evidence before deciding again. Three controlled fixture families cover status persistence, search correctness, and invalid quantity validation.

**Final development result:** the configured local model passed **5 of 16 full browser-validation trials**. Overall it passed 11/22, including six correct refusal/access controls. The scripted browser control passed 11/11 and all 136 unit tests passed, but those do not establish model reliability. This remains an **unreliable research prototype**, not a finished general-purpose validator. See [the final results and limitations](docs/final-validation.md).

Operator-authored capabilities and evidence checks are still required. This is a reusable controlled-fixture foundation, not an unrestricted agent for arbitrary websites. The original v0.3 workflow below is preserved, and its recorded results do not transfer to the new loop.

Start with the [general-agent contract and commands](docs/general-agent.md) and [v0.4 verification record](docs/general-results.md). The new development/transfer harness is `python -m evaluations.general_run`; its scripted control, unit doubles, and real-model results are reported separately.

An original runnable agent, executable skill, disposable browser app, and regression evaluator built together. This is an original implementation, with no proprietary product code or private product data.

The narrow first workflow is a fictional task board: a reported status change is saved, then lost after reload. The agent reads a public bug report and knowledge base, identifies the task, uses a real browser, and returns **confirmed**, **not_reproduced**, or **inconclusive**, with screenshots and trace evidence.

## What is in the box

- `bug_validator/`: Python orchestrator, KB retrieval, real local Ollama model adapter, and bounded Node/Playwright browser controller.
- `skills/browser-bug-validator/SKILL.md`: legacy operator entrypoint, fingerprinted but not injected into model calls; its plan/assess references are the legacy runtime prompts.
- `skills/browser-bug-validator-general/SKILL.md`: new general-loop operator entrypoint; its runtime prompt is defined and fingerprinted in `bug_validator/general.py`.
- `fixture_app/`: real HTTP/JavaScript task board with buggy, fixed, blocked, distractor, and untrusted-note variants. The evaluator owns the hidden variant, final state and server audit log.
- `evaluations/`: tasks, repeated trials, deterministic graders, descriptive metrics, baseline/candidate comparison, independent semantic grading and human calibration workflow.
- `tests/`: agent contract/safety and evaluator negative controls. Unit tests with mocked browser/model are labeled as such; they do not establish real-browser or real-model quality.

## Requirements

Python 3.10+ for the complete evaluation suite, an existing Node.js, Playwright 1.48+, and Chromium/Chrome on macOS or Linux. The evaluation runner uses POSIX process groups and does not currently support Windows. Model mode additionally requires an existing local Ollama server and installed model. No Python packages are required. Normal agent/evaluation commands do not download dependencies or models, change the user's browser profile, install software, or call a paid service. The explicit [CI setup](docs/ci-evaluations.md) installs its pinned browser dependencies on the disposable runner.

Run from this directory. If Playwright or Chrome is not discoverable, provide `--browser-config` with the existing executable/module paths. Example for an installed ChatGPT Mac application:

```json
{
  "node_executable": "/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node",
  "playwright_module": "/Applications/ChatGPT.app/Contents/Resources/cua_node/lib/node_modules/playwright",
  "executable_path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "headless": true,
  "timeout_ms": 8000,
  "process_timeout_seconds": 60
}
```

Save this as `browser.local.json` only if those installed paths exist on your machine. On Linux with discoverable Playwright, `/usr/bin/chromium` is detected automatically. The browser sandbox stays enabled. Restricted containers may prevent browser startup: that is an execution blocker, not a passing reproduction.

## Preserved v0.3 quick start

```bash
python -m unittest discover -s tests -v
python -m evaluations.run --output runs/reference-v1 --trials 1 --backend deterministic --browser-config browser.local.json
```

The reference mode runs actual browser actions but uses deterministic planning and verdict logic. It is a useful integration/safety baseline, not a language-model test. Cases with missing authorization or required information stop before opening a browser.

For real model trials, make a local config:

```json
{"endpoint":"http://127.0.0.1:11434","model":"llama3.1:8b","temperature":0.2,"timeout_seconds":180}
```

Then run:

```bash
python -m evaluations.run --output runs/model-v1 --trials 3 --backend local-model --model-config model.local.json --browser-config browser.local.json --timeout 480
```

This retains **every** trial. Each applicable trial invokes the model once to plan the workflow/target and once to assess actual browser evidence. Malformed output, changed scope, unsupported citations, or model/evidence disagreement becomes inconclusive. There is no silent deterministic fallback. The model is unloaded after each call (`keep_alive: 0`) to limit retained memory. Use a small trial count first on constrained machines.

For a standalone report against an already-running authorized fictional fixture:

```bash
python -m bug_validator run --bug bug.json --kb kb.json --base-url http://127.0.0.1:PORT --output runs/single --backend local-model --model-config model.local.json --browser-config browser.local.json
```

Input, model and browser contracts: [docs/contracts.md](docs/contracts.md). Evaluation operations and limitations: [docs/evaluation.md](docs/evaluation.md).

## Preserved v0.3 evaluation design

The development suite covers a real persistence bug, fixed behavior, denied access, an unrelated warning, a malicious imported note, missing target, unapproved target and missing expected status. Private expected verdicts are never passed to the agent. The harness separately observes server-side mutations and reloads, so the agent's own success claim is insufficient.

Code checks cover outcome, actual effects, evidence existence/hashes, target isolation, request scope, and report consistency. Model or human graders assess grounding, relevance and appropriate uncertainty. They do not replace the code checks. An unfilled review template is not a review, model self-grading is rejected, and independent semantic grading stays unverified until actually performed. Keep a fresh holdout separate before tuning against this small visible development set.

Compare agent/skill revisions against an unchanged fixture; compare app versions with the agent/skill held constant. The comparison tool fingerprints these components so a change in application behavior is not silently attributed to the agent. See the evaluation guide for the exact commands.

## Safety and scope

Only an explicitly authorized loopback origin, target task and status are supported in v0.3. Browser requests are intercepted and sent through a no-redirect, bounded loopback HTTP transport. The controller admits only fixture reads and one exact save request, blocks workers/popups/downloads, uses an isolated browser profile, caps request/event counts and response size, and captures a fixed-size viewport. Page/KB text cannot add tools, execute code, or select arbitrary paths.

These are application-level controls for a small controlled fixture, not a hardened OS sandbox. The fixture oracle lives in a separate process and is withheld from agent input, but both processes run under the same filesystem user. Do not use this package as a hostile-code security boundary or pass real credentials, sensitive records, or production mutation targets.

The first workflow is intentionally narrow. It is not a general-purpose defect agent for arbitrary websites, does not prove a production bug is absent, and does not claim a fresh holdout or calibrated semantic score. A separate safe public-site smoke check, if performed, must be labeled separately until there is a corresponding authorized adapter and regression suite.

## Original v0.3 verified development results

The v0.3 system passed **16/16 repeated development trials** across eight known cases (two trials per case), using an actual local `llama3.1:8b` model and isolated Chrome browser. The deterministic browser reference passed 8/8. All 66 unit tests passed.

The denominator matters: six trials were correct input/authorization refusals with no model call. Ten invoked model planning, of which two correctly stopped at blocked access. Eight completed browser execution and model evidence assessment. The 16 results were four confirmed, four not reproduced, and eight appropriately inconclusive.

Earlier failures remain part of the development history: v0.1 passed 6/16 overall, with all 10 model-invoking trials rejected at planning; v0.2 passed 12/16, with four incorrect fixed/distractor assessments rejected. v0.3 checks model-extracted facts and a persistence predicate, then maps verified facts to the objective verdict in code. The improvement measures the **revised full system**, not free-form model verdict reasoning.

These are small, repeated **development** results, not an unseen benchmark, production certification, or a calibrated semantic score. Explanation quality still needs real human review. See [the result record and limits](docs/results.md) for counts, provenance and the design changes.

## Calibrate with a human reviewer

Start with [six short review cases](calibration-starter/review.md), then [the calibration guide](docs/calibration.md). Review actual evidence independently and label groundedness, relevance, and uncertainty as pass, fail, or unknown, with a short reason. Keep objective browser checks separate from explanation quality. A different local judge model is optional; without one, human review remains useful but judge calibration is not completed.

Do not commit completed reviewer labels, browser captures, local configuration, or raw run directories. The repository ignores the default local artifact locations; review file contents before publishing anything from a run.

## Provenance and license

Original source and the fictional examples are provided under [MIT](LICENSE). Browser, Playwright, Ollama and model weights are not redistributed and retain their own licenses. The repository includes fictional regression inputs and preserved model-generated responses from those trials, not production data or any proprietary library. See [provenance](docs/provenance.md).
