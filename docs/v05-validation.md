# v0.5 validation record

Validation performed on 2026-11-08. This increment changes evaluation tooling,
not the v0.4 agent/runtime, browser controllers, fixtures or task definitions.
The agent's recorded baseline remains 5/16 full browser-validation model trials.

## Completed checks

- 170 main unit/contract tests passed. These include synthetic browser/model
  doubles, real local HTTP fixture controls and a fake Ollama HTTP transport
  server. A fake server response is not a real model judgment.
- All five preserved calibration-starter tests passed.
- Python compilation and both Node browser-controller syntax checks passed.
- All 17 catalog task definitions validated against canonical task/input/golden
  bindings. The actual development HTTP golden verifier passed 11/11 cases and
  executed zero reserved cases.
- Four actual subprocess refusal trials passed: two repetitions each for missing
  mutation acknowledgment and missing objective requirement. They made **zero
  model calls and opened zero browsers**. All four trial artifacts passed the
  integrity loader, and four exact final-report review packets were prepared.
  These are refusal-path controls, not end-to-end agent-quality measurements.
- Independent code review, negative probes and repeated test execution checked
  task/oracle binding, omitted hard gates, retrieval contamination guards,
  final-report target separation, source/response identity, raw-response binding,
  calibration baseline replay, repetition accounting and local ledger behavior.

## Blocked or not performed

A scripted status-bug browser smoke attempt failed during Chromium startup in
the restricted execution environment, before any browser observation or model
call. The trial remains failed in its preserved run record. No sandbox setting
was weakened. Consequently this environment did **not** provide a new passing
real-browser integration run for v0.5.

A read-only probe of the local Ollama endpoint returned connection refused.
No real judge invocation, new agent model trial, real human review or calibrated
semantic result was produced. No model was installed or downloaded. No reserved
transfer trial was executed, and no fresh blind holdout result is claimed.

## Artifact and publication boundaries

Actual local logs, golden receipt, attempted-browser run, refusal runs and blank
review packets are retained separately, not included in the public source
archive. The archive contains source, synthetic illustrations, tests and guides;
it contains no completed human label set, local model/browser configuration,
screenshots or raw runs. `SHA256SUMS.json` identifies the distributed files.

Run hashes are same-writer consistency checks, not independent signatures. The
judge-only corpus is synthetic and requires real expert calibration. Family and
exact-text exclusions do not detect all semantic near-duplicates or prove
reference provenance. See [the evaluation guide](evaluation-foundation.md) for
commands, trust limits and the remaining work.
