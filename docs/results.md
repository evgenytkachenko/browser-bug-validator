# Recorded development results

These results were produced by real local model calls and an isolated Chrome browser on a Mac, not by the mocked unit tests. The small suite contains eight known development tasks. Model runs used two trials per task; reference runs used one. Source revisions and failed outcomes were retained separately throughout tuning.

| Version | Model-backed suite | Model planning calls | Full exercise/assessment cases | Reference browser suite |
| --- | --- | --- | --- | --- |
| v0.1 | 6/16 passed | 10, all rejected before browser | 0 reached | 8/8 passed |
| v0.2 | 12/16 passed | 10, all accepted | 8 reached, 4 passed | 8/8 passed |
| v0.3 | 16/16 passed | 10, all accepted | 8 reached, 8 passed | 8/8 passed |

Each 16-trial suite also includes six input/authorization refusals that deliberately invoke no model. In v0.2 and v0.3, two additional model-planned trials encounter denied access and correctly stop without an assessment call. In v0.1, those plans are rejected before browser execution, so the access block is never observed. Do not call 16/16 sixteen complete LLM reproductions.

## What changed

- **v0.1:** The model mixed end-to-end reporting into the plan, adding premature verdict or evidence fields. Strict validation rejected every affected plan. These were genuine full-system failures, not discarded infrastructure noise.
- **v0.2:** Phase-specific prompts and closed structured-output schemas fixed the planning issue. Four fixed/distractor trials then produced incorrect or inconsistent defect classifications, despite observations showing that done persisted. The guard downgraded them to inconclusive, so they failed the independent verdict oracle.
- **v0.3:** The model task changed explicitly: extract saved/reloaded statuses, assess whether the requested status persisted, and cite evidence. Exact facts, target, phase IDs and predicate must match browser observations. Only then does code map verified persistence to not reproduced or confirmed. Wrong facts, uncertainty, contradictions, extra fields and invented evidence still fail closed.

v0.3 is an architecture change, not proof that the same model learned free-form verdict-label reasoning. Explanation semantics remain separately unverified. The evaluator, fixture, browser controller and development cases did not change in these corrective iterations. Model/browser configuration and the resolved model artifact were held fixed for the paired comparisons.

The full-artifact comparisons recorded four improvements against v0.2 and ten against v0.1, with zero observed regressions on these cases. The v0.3 outcome counts were four confirmed, four not reproduced, and eight inconclusive, all matching each case's expected outcome.

## Runtime and checks

- Python 3.12; Node.js 24.22.1; Playwright 1.57.0; Google Chrome 156.0.8078.80.
- Local Ollama `llama3.1:8b`, temperature 0.2, no fixed seed; resolved model identity checked before and after each run. No paid API was used.
- 66 unit tests passed. Python compilation and browser-controller JavaScript syntax checks passed. These checks include simulated model/browser responses and do not themselves establish live behavior.
- Independent review tested malformed outputs, fact/predicate mismatches, evidence attribution, scope guards, redirects and response budgets. Review is not a proof of a hardened security boundary.

The runtime components in this repository are byte-identical to the verified v0.3 candidate. Documentation and packaging were updated for this repository without changing those components. SHA256 fingerprints use `evaluations.run.source_fingerprint` over each listed directory:

| Component | SHA256 |
| --- | --- |
| `bug_validator/` | `3be9ed39c80684331a35999e48642cc52f93038026421d2ad8bbe2e00b9fd896` |
| `skills/` | `b3b96425a8206a6d046ca010d28749e358a49c44c84892faed32dd6677b96a8d` |
| `evaluations/` | `8d1e769025162ebda57b2dcaf5f8e95def018cab1420efca1042ff6ed3cfac29` |
| `fixture_app/` | `3c1351d3519a037d2655f354aa71bea5c743c10d0ab3cbab1f06c3baa8a83c8b` |

## Limits of this record

The full original runs, including browser captures and machine-specific metadata, are retained separately and are not published here. This document summarizes those observed runs; it is not a portable replay receipt or a fresh remote CI run. Small fictional regression fixtures derived from failed model outputs are included in tests, but the complete historical v0.1/v0.2 runtime snapshots are not.

There is no fresh holdout score, human-calibrated semantic score, general production reliability estimate, arbitrary-site adapter, or proprietary-product integration. All cases were visible during development. Two repeated trials per case are too few to establish model reliability. A public-site exploratory measurement, if performed separately, is not included in these accuracy counts.
