# General-loop evaluation

The new evaluator tests the reusable action loop, separately from the legacy
single-workflow v0.3 suite. Its agent input is natural bug text plus public KB
facts and an operator-authored, exact capability/checkpoint document. The private
mode, expected verdict, server state and audit are withheld from model inputs.

## Cases and split

There are 11 development cases:

- Status save/reload: buggy and fixed.
- Project-name search: buggy and fixed.
- Invalid inventory quantity validation: buggy and fixed.
- HTTP 403 access denial.
- A forged system message in page text demanding early success, invented
  citations and external transmission.
- An unrelated warning in a working feature.
- Unacknowledged mutation and missing objective requirement, rejected before
  model or browser execution.

Six additional **reserved-transfer** cases change target status, search term or
invalid input across the same three workflow families. They are visible to the
authors, so they are not a blind or unseen benchmark. They are excluded from
default execution and require an explicit opt-in and frozen development source
manifest. Do not tune on their results and continue calling them reserved. If
they inform changes, record that contamination and author a new reserved set.

One development repetition is 11 trials: eight complete exercises, one blocked
case and two preflight refusals. Two repetitions are 22 trials, including 16
complete exercises, two access-denied cases and four preflight refusals. Always
report these denominators separately, along with actual model calls, browser
starts, evidence-bearing trials and completed finish assessments.

Model API attempts and successful decisions are separate counts. An HTTP error,
including a rejected response schema, is an attempted call, not a successful
decision. Reports expose attempted/completed calls and trial counts explicitly.
The legacy `model_calls`, `real_model_calls`, `trials_with_decision_calls` and
`real_model_trials` fields count **attempts** only. A real-model qualification
requires stable model/source provenance and at least one trial with a completed
Ollama decision plus actual browser observations. Error-only runs are labeled
attempted and unqualified; their failures and full trial denominator remain.

## Run

Use existing installed Node, Playwright 1.48+, Chrome/Chromium and, for model
runs, an existing Ollama model. No dependency/model installation is performed.
The browser sandbox remains enabled. Examples assume local config files already
contain valid executable paths/model configuration.

```bash
python -m unittest discover -s tests -v
python -m evaluations.general_run --output runs/general-reference --backend scripted-control --trials 1 --browser-config browser.local.json
python -m evaluations.general_run --output runs/general-model-development --backend local-model --trials 2 --model-config model.local.json --browser-config browser.local.json --timeout 600
```

The first run uses real browser actions with an explicitly scripted control
policy. It is integration coverage, **not model performance**. The second uses
the genuine Ollama adapter for every decision. There is no automatic fallback,
schema repair, retry-to-success or replacement of bad model choices with the
script. All outcomes, including timeouts, remain in the run.

The agent gets a 480-second budget, including up to five ordinary decisions in
the shortest status flow; the outer runner allows 600 seconds for teardown.
Longer model plans remain bounded by both action and wall-time limits.

Only after freezing the same source, and only if a reserved-transfer measurement
is intentionally wanted:

```bash
python -m evaluations.general_run --output runs/general-reserved --backend local-model --trials 2 --split reserved-transfer --frozen-manifest runs/general-model-development/manifest.json --acknowledge-author-visible-holdout --model-config model.local.json --browser-config browser.local.json --timeout 600
```

The reserved runner refuses changed agent, fixture or evaluator code. Config and
model identities are recorded separately. Do not compare two runs as an agent
improvement if model, fixture, task split, browser configuration, or evaluator
also changed. The existing `evaluations.compare` command is for legacy v0.3
artifacts, not this schema; no cross-schema comparison is claimed.

## What is graded

Deterministic checks inspect independent server-side effects and request order,
unrelated-state isolation, exact target/payload scope, reported values versus
fixture truth, ordered actions/observations, screenshot signatures/hashes, trace
binding, complete checkpoint citations, per-step decision participation, raw
decision artifacts, honest backend labels and absence of private oracle fields
in decision inputs. A fabricated success label is insufficient. Synthetic
browser provenance is explicitly rejected as a real browser trial.

Every trial retains public inputs, private oracle, before/after state, server
journal, process result, raw decision artifacts, browser captures/trace, report,
grade and artifact hash manifest. The run records source/config fingerprints,
model digest before/after and whether source stayed frozen. The same OS user can
read sibling files; this is process separation and input withholding, not an
OS-level hostile-agent security boundary.

## Model dependence and limits

The model selects each action after observing the current page. Only after the
host captures all ordered checkpoints can it choose finish or stop, with exact
citations for a conclusive finish. The runtime exposes only navigation before any
actual observation and encodes the full required checkpoint citation set in the
assessment schema. These are existing browser/evidence invariants made explicit
to the model, not autonomous action execution or independent citation reasoning.
The active response schema prevents premature
verdicts and citations; the host never repairs an invalid reply. Choosing the wrong sequence,
stopping early, accepting injected instructions, inventing citations or issuing
the wrong final verdict fails or becomes inconclusive. Controller-side checks
do not silently complete a workflow on the model's behalf.

The host provides verified checkpoint results and maps their predicates to the
admissible verdict. Therefore this measures **the whole model-driven bounded
system**, especially action selection and faithful reporting, not independent
free-form model discovery of an oracle. It does not measure visual bug finding,
autonomous adapter creation, arbitrary websites or production reliability.

Screenshot hashes establish byte integrity, not visual semantics. A model
explanation is not independently graded just because the objective checks pass.
Semantic grounding, relevance and uncertainty remain **unverified** until a
separate reviewer actually evaluates raw evidence. No human calibration or
independent-judge score is manufactured by these tests.

Unit tests use a clearly labeled synthetic HTTP/DOM adapter and signature-only
test artifacts. They exercise real fixture HTTP state and negative grader
controls, but are neither browser trials nor real-model runs. Their own
synthetic-browser outputs cannot pass the real-browser provenance check.
