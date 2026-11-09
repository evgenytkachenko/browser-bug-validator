# Trace explorer

A buildless, offline-ready viewer for **six actual historical development trials**
against a fictional local task board: three cases recorded with v0.2 and v0.3.
No model, account, backend, dependency installation or API key is needed.

## Open

Open `trace-viewer/index.html` in a modern browser. Alternatively, from the repo root:

```sh
python -m http.server 8000 --bind 127.0.0.1 --directory trace-viewer
```

Visit `http://127.0.0.1:8000`. Serve only this directory, not the repository root,
which may contain private local runs or configuration. The viewer loads only its
own static files. It has no analytics, remote fonts, local storage or model calls.
Outbound source links open only when clicked.

Select a case, compare both versions or focus on one, switch the aligned
observation phase, and follow citations to evidence. Filter controller events,
expand historical checks, inspect the independent server journal or read the
curated JSON. Narrow screens stack the versions. Case, version, phase and filter
are URL-fragment state; Back/Forward restores them. All controls support keyboard
use and visible focus. This is a curated legacy-schema viewer, not an importer
for arbitrary `run-general` artifacts.

## The failure and fix

In the selected fixed-app trial, v0.2 observed `done` after save **and** reload.
Its local `llama3.1:8b` model nevertheless proposed **confirmed**. The safeguard
rejected that disagreement and returned **inconclusive**. The historical
independent evaluator failed the trial: 30/31 recorded checks passed.

v0.3 asked the same model artifact to extract saved/reloaded facts and a
persistence predicate. It checked those facts, then mapped the objective verdict
**in code** to **not_reproduced**: 31/31 recorded checks passed. This is a changed
system contract, not a corrected free-form model verdict or learned reasoning
improvement. Fixture, evaluator, task definitions and model artifact matched.

The other cases demonstrate the genuine persistence defect and an input refusal.
The refusal made no model calls and opened no browser. These selected development
examples are not a new quality measurement, a benchmark or an unseen holdout.
They do not supersede the newer v0.4 general-loop baseline of 5/16 full browser
trials. The viewer does not change the agent runtime.

## Evidence boundaries

- `demo.json` is the complete allowlisted projection. `demo-data.js` encodes the
  same content as a classic script for offline use without fetch. `provenance.json`
  pins original retained source SHA-256 hashes. Base public repo commit:
  `b585691355c3f2be769cbf2f9e243202e50b7431`.
- Sources are actual local-model/real-browser text exports recorded 7 November
  2026, not synthetic judge reference packets. Preparation checked source hashes,
  ordered events, report-to-trace bindings and comparison fingerprints.
- Every displayed grade is a **recorded historical result**, not a check rerun by
  this viewer. Model proposals, final reports and fixture oracle remain separate.
- Original PNGs were omitted from the text exports. **No screenshot pixels are
  included, visually verified or recreated.** The viewer shows recorded text,
  values and screenshot hashes. A historical hash-check pass does not establish
  screenshot semantics or mean the PNG exists in this bundle.
- Loopback origins/ports become `[local fixture]`. Unused configuration, provider
  endpoints, full model prompts and filesystem paths are omitted. No human
  labels, reviewer details, private discussion or credentials are included.
- Model outputs, final reports, observed values, actions and historical check
  results are preserved. Original hashes refer to the source bytes, not the
  sanitized projection; hash equality alone does not prove execution.
- These legacy versions chose a workflow with the model and ran a bounded
  controller. The individual browser actions were not each selected by a
  general-loop model.

## Reproduce and test

If you have the original matching text exports, regenerate using their run
folders. Raw run directories are not redistributed with this demo.

```sh
python trace-viewer/build_demo.py --baseline /path/to/runs/model-v02 --candidate /path/to/runs/model-v03
node --check trace-viewer/app.js
node --test trace-viewer/test_app.cjs
python -m unittest discover -s tests -v
python -m unittest discover -s calibration-starter -p 'test_*.py' -v
python -m evaluations.task_catalog validate
python -m evaluations.task_catalog verify --receipt /tmp/http-goldens.json
```

The exporter refuses input bytes that differ from the source pins. It is not a
privacy scrubber for arbitrary runs. New cases require a reviewed projection,
verified source evidence and privacy review, not merely changing hashes.
See [VALIDATION.md](VALIDATION.md) for checks and verification limits.

## Security and publication

All evidence uses `textContent`, not HTML. There is no arbitrary file import,
URL-based data loading, trace code execution or embedded screenshot content.
CSP denies network connections, images, objects, forms and base URLs. Static
JavaScript files themselves are trusted source; CSP is defense in depth, not a
sandbox for replacing those files.

This feature distributes the viewer as static source; it does not deploy a
public website. Any later hosting should publish only the static viewer files
after authorization and review, never raw run directories or local configuration.
The parent repository's MIT license applies.
