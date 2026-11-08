# Final v0.4 validation: implemented loop, unreliable model behavior

Date: 2026-11-08. This is the final result of the rc1–rc4 development pass. No further tuning or success-seeking retries were performed after rc4.

The reusable observe/decide/browser loop is implemented and the controlled browser integration works. **The configured local model is not reliable enough to call this a finished general-purpose bug validator. It passed only 5 of 16 full validation exercises.** This package is an evaluated research prototype for authorized fictional loopback fixtures.

## Final results and denominators

| Stage | Result | What it establishes |
| --- | --- | --- |
| Unit/contract/evaluator/security tests | 136/136 passed in cloud and on Mac | Regression behavior, including explicitly labeled doubles and transport controls; not live-model quality |
| Scripted-policy real-browser control | 11/11 passed: 8 full exercises, 1 access-denied case, 2 preflight refusals | Controlled browser integration with a scripted policy, not language-model reasoning |
| Genuine local-model development trials | 11/22 passed overall | Includes six nonexercise controls; the overall percentage must not be presented as full-task reliability |
| Full model/browser exercises | **5/16 passed (31.25%)** | The relevant observed success rate for the complete validation task on these tuned development cases |
| Access-denied model trials | 2/2 passed | Correctly remained inconclusive after denied access |
| Preflight refusals | 4/4 passed | Missing permission/specification stopped before model invocation |

The model run made 93 calls, all of which returned schema-valid responses, across 18 model-invoking trials. Sixteen trials produced 75 browser observations. There were 15 proposed finishes: five accepted, ten rejected for incorrect verdicts. One remaining exercise failed during browser execution. A completed model response or proposed finish is not a successful validation.

### Per-case model outcomes

Each development case was run twice, with every attempt retained.

| Case | Passes | Category |
| --- | --- | --- |
| Status persistence, buggy | 0/2 | Full exercise |
| Status persistence, fixed | 2/2 | Full exercise |
| Search, buggy | 0/2 | Full exercise |
| Search, fixed | 1/2 | Full exercise |
| Invalid quantity, buggy | 1/2 | Full exercise |
| Invalid quantity, fixed | 0/2 | Full exercise |
| Access denied | 2/2 | Expected inconclusive control |
| Search with injected page note | 1/2 | Full exercise |
| Quantity with unrelated warning | 0/2 | Full exercise |
| Unacknowledged write | 2/2 | Preflight refusal |
| Missing objective requirement | 2/2 | Preflight refusal |

## What failed, and what the guards did

Ten completed workflows proposed a verdict inconsistent with their actual captured requirement checks. Every one supplied the complete required citation set. The unchanged host verdict check rejected those claims and returned inconclusive. This demonstrates that schema-valid, fully cited output can still be substantively wrong. It does not show independent semantic reasoning or explanation quality.

In the other failed exercise, the model followed `open → type_quantity → type_quantity → open → apply`. Reopening the form reset its quantity input from the authorized test value of -2 to 1. Applying that state attempted a POST outside the exact approved payload. The controller recorded the request as disallowed and blocked it before the fixture received it; the server journal contains only the two GETs and no POST. The action then timed out after eight seconds waiting for a response that the blocked request could not produce. This was a model sequencing error followed by a successful boundary block, **not merely an environment timeout and not an absence of unsafe attempts**.

The guards contained the demonstrated incorrect verdicts and the mismatched request. They are application-level checks, not an OS sandbox, complete egress firewall, production-security certification, or proof that every future failure will be caught. The operator still supplies authorization, fixed action values, probes and requirements; the system does not independently certify those specifications or their correspondence to a real bug.

## Development history, not a blind benchmark

The same 11 visible development cases were used for two real-model trials per revision:

- rc1: 4/22 overall, 0/16 full exercises. All 18 model attempts failed with a provider schema error; four preflight refusals passed.
- rc2: 4/22 overall, 0/16 full exercises. The provider accepted requests, but all 18 model-invoking trials failed the action contract for premature result claims.
- rc3: 6/22 overall, 0/16 full exercises. Ten workflows ended with incomplete citations and six chose field interaction before navigation. Two denied-access cases and four preflight refusals passed.
- rc4: 11/22 overall, **5/16 full exercises**. Ten wrong terminal verdicts and one blocked-payload/action-timeout sequence remained.

The earlier failures remain in the record; later results do not overwrite them. The changes tightened the runtime's interface and exposed already-required navigation/citation constraints. There was no deterministic fallback, automatic completion of workflow actions, repaired model output, weakened final-evidence gate or changed expected verdict to manufacture success.

These are small, repeatedly inspected and tuned development cases. The six reserved alternate-input cases were not run; they are author-visible and would not constitute a blind holdout even if run. No arbitrary websites, production data or live-site mutations were tested. No human-calibrated or independent-model semantic score is claimed. Citation completeness in rc4 is schema-enforced; it is not evidence that the model learned citation selection.

## Exact executed provenance

The executed source archive was `Browser-bug-validator-v0.4.0-rc4.zip`:

- SHA256: `eb43832669f7dd5f74446d38bc9620139a0d96a450941726a561402365e40461`
- 168,399 bytes; 74 source/document files plus their checksum manifest.
- macOS 26.4 arm64; Python 3.12.15; Node v24.22.1; Chrome 156.0.8078.80.
- Model: `llama3.1:8b`, temperature 0.2, context setting 4096, no configured seed; model unloaded after each call.
- Model digest: `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`.
- Model configuration SHA256: `8723404d931a9412a5d9ecef75b803b3f3ab3331ca905aad8a69a19018897bd6`.
- Browser configuration SHA256: `d959e870283050f1e7f22f63982235a8d5d8e2e5f42084947f8f04f3a615af4e`.
- Agent component fingerprint: `7a5438e15b5c6d5f2936e656e18085a3478e708f59e15c069ce2919d092794d4`.
- Fixture component fingerprint: `60bae2fc233ed53313c87531882c2dda5033e401f14012eb1d3cc2c9d4e4c018`.
- Evaluator component fingerprint: `c6f3a4b806cf9e206e45c4ff132de1e5bea836c16077bb666adb05abf3db3e25`.

The recorded source, configuration and model identities stayed stable throughout the final run. Existing installed dependencies were used; no dependencies or weights were downloaded for these trials. The final deliverable keeps all runtime, test, evaluator and fixture bytes identical to rc4. Only documentation and the package checksum manifest were updated after the run. Its ZIP hash therefore differs from the executed rc4 archive; this is not an untested runtime revision.

## Independent verification and evidence limits

A separate verifier checked the frozen archive and all 74 manifest entries and reran all 136 tests, compilation, Node syntax and CLI checks. It matched all 93 raw Ollama replies to the recorded answers and request/schema/response hashes. It then directly checked the original Mac artifacts, including all 101 screenshots, and replayed the full grader. All 787 checks across the 33 control/model trials reproduced the original outcomes exactly: 760 passed checks and 27 failed checks, with zero mismatches. Check counts are not additional trial successes.

The text evidence transfer's SHA256 is `2af7390a15e132e3027e3a41a12f9bcb776a41e105969d360f4e31716c47ff52`. The verifier checked 651 transferred text-file hashes and 605 available original artifact hashes, then directly verified all 706 original artifact hashes and 74 source hashes on the Mac, without editing or rerunning any trial. The 101 PNG screenshots were explicitly omitted from the text transfer but were included in that direct hash verification. Screenshot byte integrity was verified; visual/semantic screenshot quality was not reviewed.

Full raw evidence is retained separately and is not included in this distributable source package because it contains local machine configuration paths. The package includes only the previously retained fictional response regression fixtures and this results record. No repository push, merge or deployment was performed as part of preparing this final bundle.
