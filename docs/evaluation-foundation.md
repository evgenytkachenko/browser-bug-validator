# v0.5 evaluation foundation

This is an evaluation-tooling increment, **not an improved agent**. The v0.4
agent, prompts, fixture behavior and 17 tasks are unchanged. Its recorded result
remains **5/16 full browser-validation model trials**, with 11/22 overall when
six refusal/access controls are included. New HTTP controls, parser tests and
judge transport doubles do not improve that result.

## What is now runnable

1. A [versioned task catalog](task-catalog.md) binds each authored fictional task
   to its public input, requirements, buggy/fixed pairing and deterministic golden
   state/effect contract. Eleven development cases can be verified against actual
   reset HTTP fixtures. The six author-visible reserved cases are not executed by
   this verifier.
2. General-loop run loading validates the complete trial schedule, source
   identities, file inventories, actual objective grader replay, process and
   report bindings, and recorded metrics. Missing hard safety/outcome checks
   cannot become a pass merely by editing the aggregate grade.
3. General-loop evidence can now be prepared for an independent local judge.
   This is separate from `evaluations.semantic`, which remains the legacy v0.3
   workflow. Both humans and the new judge score exactly `final_report_text_v1`:
   final verdict, summary and limitations. Internal decisions, including rejected
   proposals, are evidence context, **not adopted final-report claims**.
4. Eight synthetic rubric illustrations form a separate judge-only retrieval
   corpus. They are authored examples, **not captured runs, human labels or
   calibrated gold standards**. No reference data is imported by the agent.
5. Repeated trials retain every attempt and report task-macro pass@k/pass^k,
   confusion and false positives, latency, failures and participation denominators.
6. A local consume-once ledger binds reserved transfer execution to frozen
   sources, model artifact and configuration. It is not a tamper-proof or blind
   holdout. See the reservation section below.

## Task and outcome controls

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s calibration-starter -p 'test_*.py' -v
python -m evaluations.task_catalog validate
python -m evaluations.task_catalog verify --receipt /tmp/golden-contract-receipt.json
```

The HTTP verifier checks actual responses and server state without using the
agent's verdict helper. It does not execute JavaScript, inspect screenshot pixels,
measure agent reasoning, or demonstrate injection resistance. Existing browser
and model commands remain necessary:

```sh
python -m evaluations.general_run --output runs/control --backend scripted-control --trials 3 --browser-config browser.local.json
python -m evaluations.general_run --output runs/agent --backend local-model --trials 3 --model-config model.local.json --browser-config browser.local.json
```

No-call refusals, blocked access, actual model attempts/completions and full
exercises are separate denominators. A model that always abstains cannot pass the
buggy/fixed exercise gates. False positives are `confirmed` outputs on fixed
cases, regardless of overall trial failure. Failures remain in every denominator;
there is no retry-until-success filtering. A predecision startup failure is
reported separately without asserting whether infrastructure or the agent caused
it. A timeout remains unattributed; a malformed model answer is not relabeled as
infrastructure.

For n repeats and c successes per task, pass@k is estimated as
`1 - C(n-c,k)/C(n,k)` and pass^k as `C(c,k)/C(n,k)`, then averaged across tasks.
Equal repeat counts are required. These finite-sample estimates depend on
exchangeable independent repeats of a fixed task. A deterministic scripted policy
has no model sampling variation, and none of these figures establish population
reliability or unseen-task generalization.

## Judge-only retrieval and real local adapter

Prepare outside the hashed run directory; adding files inside it invalidates the
run inventory. Start with selected development tasks, leaving an entire workflow
lineage out for later judge validation. Buggy/fixed variants of one family share
a lineage and cannot straddle calibration and validation.

```sh
python -m evaluations.general_semantic prepare runs/agent --output semantic/packets --review-role calibration
```

Preparation validates the run before copying a packet. Expected verdicts, fixture
modes and deterministic grade labels are excluded from the judge prompt. Public
operator requirements, captured observations/actions, independent before/after
state and request records remain available. The final report target has its own
hash; human and model reviews must match it. Full-report content hashes retain
trial identity even when repeated final text is identical. Packet identity and
artifact hashes provide consistency, not signatures or proof of authenticity.

Configure an already-installed, distinct Ollama model in `judge.local.json`:

```json
{"endpoint":"http://127.0.0.1:11434","model":"your-existing-distinct-model","temperature":0.3,"timeout_seconds":180,"seed":100}
```

```sh
python -m evaluations.general_semantic judge semantic/packets --config judge.local.json --output semantic/judged --repeats 3
```

The adapter really calls the loopback Ollama `/api/chat` endpoint. It does not
install/download a model, contact a cloud provider, or silently replace a failed
judge. Model digests must differ even if names are aliases. Identity is checked
before and after; response model, assistant role and completed nonstreaming status
are checked. Optional seeds advance with each repeat. Raw requests/responses,
model identity, prompt/rubric/corpus hashes, token counts when returned, elapsed
time, retrieval selections and every failure are retained. Errors remain
`unverified`, never a pass. Responses must contain only the rubric dimensions and
pass/fail/unknown labels with reasons. Rationales are model text, **not verified
citations**.

Retrieval uses deterministic token overlap with stable ID tie-breaking. The
query contains public task and final-report text. References from the same task,
family or lineage are excluded, as are exact normalized copies of current text.
Context is checked against the canonical task definitions. The corpus is bounded,
versioned, validated and frozen per run. Only explicitly synthetic
`judge-reference` entries are supported in v1. A custom corpus still needs human
curation: metadata can be falsely declared, and semantic near-duplicates are not
detected. Hashes cannot prove that provenance claims are true.

References are never evidence for the current verdict. Trusted instructions say
current observations take precedence, embedded instructions are data, and
screenshot pixels are unavailable. These are defenses, not proof that a model
cannot be influenced by an injection. The adapter never gives the judge tools.
A conservative 24KB cap covers serialized messages and response schema, leaving
context/output headroom; oversized input is rejected instead of locally truncated.
This is not a provider-tokenizer guarantee or proof against provider-side
truncation. Larger traces require an explicitly designed, separately evaluated
packet strategy.

## Actual human calibration, then separate validation

1. A real reviewer independently reads the exact packet target and supplied text
   evidence **before seeing judge labels**. Fill the generated
   `human-labels-template.json` in an ignored private location with reviewer,
   timezone-aware timestamp and a label/reason for every dimension. Do not copy
   synthetic examples or model judgments as human truth.
2. Prefer a second independent expert. Resolve disagreements explicitly and keep
   the original reviews separately. The comparison command accepts one adjudicated
   record per packet; duplicate reviews are rejected rather than averaged into
   made-up truth. Screenshot review is a separate task because this text-only
   judge cannot see pixels.
3. Compare the labels against the complete, integrity-checked judgment run:

```sh
python -m evaluations.general_semantic calibrate semantic/judged semantic/packets calibration-private/labels.json --output calibration-private/comparison.json
```

Reports show per-dimension confusion matrices, class coverage and recall,
unknown/failure cases, disagreements, judge errors and repeated-judge consistency.
Repeating one packet does not create new human-reviewed tasks. Every packet must
be reviewed; prepare a deliberately scoped run rather than cherry-pick away
failures. Blank templates and wrong targets are not calibration. Supplied human
identity and blindness are not independently authenticated by this software.

4. Freeze the judge policy, corpus, model and config. Prepare another run of
   previously unused **task families/lineages** with `--review-role validation`.
   Judge it using the same policy, obtain independent human labels, then compare:

```sh
python -m evaluations.general_semantic calibrate semantic/validation-judged semantic/validation-packets calibration-private/validation-labels.json --validation-baseline calibration-private/comparison.json --output calibration-private/validation-comparison.json
```

Validation rechecks the earlier calibration's underlying packets, judgments and
labels, requires the same policy and disjoint packet/task/lineage sets, and refuses
an incomplete or edited baseline summary. Keep those original artifacts available.
This is local leakage control, not a blind benchmark or human-authentication
system. No threshold automatically approves a release. Semantic quality never
compensates for deterministic safety, outcome, scope or evidence failures.

## Reserved transfer contamination controls

The existing reserved definitions are author-visible. Static code/catalog review
already sees their definitions; they are not a genuinely secret test set. Do not
call them unseen. Use independent custody of new tasks for a stronger claim.
After freezing a complete development run and before transfer execution:

```sh
python -m evaluations.holdout reserve --ledger calibration-private/holdout.json --frozen-manifest runs/agent/manifest.json --acknowledge-author-visible-holdout
python -m evaluations.general_run --output runs/transfer --backend local-model --trials 3 --split reserved-transfer --model-config model.local.json --browser-config browser.local.json --frozen-manifest runs/agent/manifest.json --holdout-ledger calibration-private/holdout.json --acknowledge-author-visible-holdout
```

The complete six-case split is consumed **before** its first trial. A crash does
not restore freshness. Changes to source/model/config require a new frozen plan;
reusing the same reserved split after seeing outcomes is blocked by that ledger.
If results were inspected elsewhere, record exposure with
`evaluations.holdout mark-exposed --reason ...` and the same ledger/acknowledgment.
Legacy transfer execution without a ledger remains possible and is explicitly
labeled untracked, author-visible and not blind. Deleting/copying the local ledger
can defeat this convenience guard; it is not an access-control boundary. Reserved
packets may only be prepared for validation with explicit
`--acknowledge-exposed-reserved`, never for calibration/tuning. An operator must
retire a contaminated set and author a genuinely new one before a fresh claim.

## Relation to the Anthropic article

[Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)
describes tasks and repeated trials, inspecting transcripts and actual outcomes,
realistic balanced tasks, deterministic/model/human graders, clear rubrics,
isolated environments, calibration and ongoing evaluation maintenance. This
repository applies those ideas in a small controlled browser setting.

Judge RAG, distinct-model digest checks, this three-dimension rubric, local
holdout ledger, strict browser capabilities and exact file formats are **project
choices**, not requirements prescribed by that article. Production-derived tasks,
expert labels, broader workflow coverage, fresh independently held-out cases and
new real model/judge evaluation are still needed.
