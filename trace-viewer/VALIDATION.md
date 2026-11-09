# Trace viewer validation

Prepared 9 November 2026 against public repository commit
`b585691355c3f2be769cbf2f9e243202e50b7431`. This record describes pre-publication
source validation. No website deployment, model invocation or new agent trial
was performed. Public pull-request CI is an additional, separately recorded check.

## Passed

- **185 Python unit/contract tests**, including 8 new viewer artifact/exporter
  tests. Existing agent code is unchanged.
- **13 Node viewer tests**: preserved verdict attribution, genuine bug/refusal
  participation, fragment round trips, ordered filters, bad/missing/empty grades,
  unresolved citations, absent screenshots, JSON/script parity, inert text sinks.
- **5 calibration-tool tests**. These do not constitute human calibration.
- **17-task catalog validation** and **11 real-HTTP development golden controls**;
  no reserved tasks executed. These are not model measurements.
- Python compilation and Node syntax checks for both existing browser bridges
  plus viewer scripts.
- Exact regeneration of `demo.json` and `demo-data.js` from the pinned source.
- Independent source review: **104 retained text artifacts rehashed**, all **112
  controller events** ordered and trace-SHA-bound, observation/action references
  matched to reports, original parsed model assessments matched recorded outputs.
- Same fixture/evaluator/task/model artifact verified across historical runs;
  changed agent/assessment contract explicitly attributed.
- Independent projection review: wording, values, actions, model outputs, final
  verdicts, mapping and historical grades preserved; private-path/endpoint scan
  clean.
- Chromium local-HTTP UI inspection: case and version controls, phase selection,
  timeline filtering, citations, disclosures, repeated navigation, Back/Forward,
  skip link route preservation and keyboard focus. Evidence and check scroll
  regions have accessible names and keyboard focus.
- Responsive reflow at **388 CSS pixels**, using native browser zoom. No horizontal
  overflow was observed. This is zoom/reflow QA, not a physical-device test.

## Corrections verified during review

The skip link now focuses the workspace without overwriting fragment state.
Citations use distinct keys and deliberately focus their observation panel.
Bounded text/check regions are keyboard-scrollable. Empty historical check
collections cannot produce a passing-trial display. Refusal copy does not claim a
model-selected workflow occurred. Decorative unsupported glyphs were removed.

## Limits

- Direct `file://` opening could not be tested: the review browser's URL policy
  permits only HTTP(S). No bypass was attempted. Classic local scripts are used
  to support offline opening; the documented loopback HTTP command is verified.
- Device emulation was unavailable; narrow-layout inspection used browser zoom.
  No Safari, Firefox, physical-phone or screen-reader certification is claimed.
- Original historical screenshot PNGs are unavailable. Their contents were not
  visually verified. Any screenshot-integrity PASS in the UI is a **recorded
  original-machine result**, not a new check of files in this bundle.
- No new browser-agent integration control or real-model evaluation was run for
  this static UI change. Existing CI configuration will run its normal controls
  only if this source is later published through the authorized workflow.
- Security validation consists of source review, schema/error tests, CSP and
  inert-rendering checks, not a penetration test or hostile-code sandbox claim.
