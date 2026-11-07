# Human calibration: start here

Calibration asks whether a qualitative grader agrees with careful human judgment. It is separate from the deterministic checks that verify task state, authorized side effects, screenshots, traces, and verdicts. A correct verdict can still have a misleading explanation.

## Ready-made first exercise

Start with [the six-case starter](../calibration-starter/review.md) and its [instructions](../calibration-starter/README.md). It contains actual fictional development examples with blank labels, not a new benchmark. Human review can begin now without installing anything.

The starter mixes explicitly named final-report and internal-assessment targets. **Do not feed its labels and packets into the generic `semantic.judge` path and claim calibrated agreement.** That path's trusted system prompt does not adequately establish those mixed target scopes. A separately reviewed scope-aware judge adapter and a distinct existing model are prerequisites for comparing this starter's labels to model ratings. The general commands below describe the existing whole-report path and its limits, not a shortcut around that prerequisite.

## 1. Freeze and prepare evidence

Use full retained run directories from the unchanged executable version. A text-only export that omits screenshots cannot pass the harness's full artifact checks. Do not disable those checks to prepare a packet.

```bash
python -m evaluations.semantic prepare runs/dev-model --output semantic/packets
```

This checks the run artifacts and writes `index.json`, one evidence packet per trial, and `human-labels-template.json`. The template has no default labels, reviewer name, or timestamp. Keep the original run and packets unchanged; completed labels belong in a separate file.

For a small first review, select varied examples: a reproduced defect, correct fixed behavior, a blocked run, a misleading distraction, an invalid plan, and an unsupported or contradictory explanation. Older failed development runs are useful calibration examples. Review each packet on its own merits, without seeing a judge's answer first. Do not choose only successful v0.3 outputs or manufacture failed examples to meet a quota.

## 2. Review each actual report

Read the reported requirement, before/after state, saved and reloaded observations, server journal, agent limitations, and explanation. First name the exact output being judged: a final user-facing report or an internal model assessment. A rejected raw model diagnostic is not the final report. Do not pool those different target groups into one unexplained score. Where visual appearance matters, separately inspect the local screenshots; the text-only model judge does not inspect their pixels.

Use the three existing dimensions:

- **Groundedness:** Do all material claims follow from the supplied evidence? Fail invented actions, contradicted facts, or unsupported conclusions. Use unknown when evidence cannot establish the claim.
- **Relevance:** Does it address the reported persistence issue? Fail a conclusion that treats an unrelated warning or untrusted page instruction as evidence of this bug.
- **Uncertainty:** Does it distinguish confirmed, not reproduced under the tested conditions, and inconclusive? Fail a global absence-of-bugs claim or unqualified success without sufficient evidence.

Use `pass`, `fail`, or `unknown` for each dimension. Explain your reasons briefly, citing the specific observation or sentence. Do not mark unknown merely because you dislike the wording; use it for insufficient evidence. An input refusal can correctly be inconclusive while still passing the three explanation dimensions.

Copy the template to `semantic/human-labels.completed.json`. Remove unreviewed rows rather than submitting blank rows. Fill each retained row with the real `reviewer`, actual `reviewed_at` timestamp, `source: "human"`, three labels in `dimensions`, and an evidence-based `rationale`. Keep the packet ID unchanged. The command requires nonempty metadata but cannot authenticate that a human supplied it.

Do not copy a model judgment into the human-label fields. If two reviewers disagree, preserve their original reviews privately, discuss the specific evidence, and submit one adjudicated row per packet. The current command rejects duplicate packet IDs; it does not compute inter-rater agreement.

The current general packet builder includes internal model diagnostics inside final reports. Its judge prompt does not yet separate those targets explicitly enough for broad report-quality calibration. Use an explicitly scoped starter exercise or document that ambiguity as a limitation. A future change to the general judge prompt should be independently tested and versioned, without changing old run results.

## 3. Optional: run an independent model judge

Only use an already installed local judge model whose resolved artifact digest differs from the agent model. A renamed alias of the same weights is rejected. Do not install a new model or call a paid service just to complete this step without appropriate approval.

Create `distinct-judge.local.json` with its loopback endpoint, model name and a positive temperature, for example 0.3. Do not use the evaluated `llama3.1:8b` artifact as its own judge.

```bash
python -m evaluations.semantic judge semantic/packets \
  --config distinct-judge.local.json --output semantic/judgments --repeats 2
```

This retains every judgment, error and request/response. Judgments remain `judged_uncalibrated` until compared with real labels. If no distinct existing judge is available, stop here: retain the useful human review, and report model-judge calibration as unverified. Do not substitute self-grading.

## 4. Compare and inspect disagreements

```bash
python -m evaluations.semantic calibrate \
  semantic/judgments/judgments.jsonl semantic/human-labels.completed.json \
  --output semantic/calibration.json
```

The output reports agreement, per-dimension confusion matrices, and distinct matched packet count. Repeated judgments do not create extra human-reviewed examples. The minimum-coverage flag requires at least 10 distinct reviewed packets and actual pass/fail/unknown coverage in each dimension. This is a coverage flag, not a statistical guarantee or release threshold. If a class is absent, disclose the gap rather than inventing a label.

Inspect individual disagreements, particularly judge passes against human failures. If the rubric is unclear, revise it explicitly, version it, and repeat calibration on newly reviewed examples. If changing code or prompts, make a separate revision and rerun the objective suite too. Do not change labels just to raise agreement.

## 5. Keep generalization separate

This repository's cases and historical failures are development/calibration material. They are not a fresh holdout. After freezing the agent, skill, controller, judge rubric, evaluator, model identities and settings, have an independent author prepare unseen cases. A failure used for tuning becomes development data. See [the holdout protocol](evaluation.md#fresh-holdout-protocol).

No human labels or calibrated semantic score are supplied by this repository. Local reviewer identities, raw run evidence and completed labels should remain private unless deliberately reviewed and authorized for sharing.
