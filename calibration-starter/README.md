# Six-case human calibration starter

Start with [review.md](review.md). It contains six short, real excerpts from fictional task-board development trials. The original output text and factual evidence are retained; the packet bytes and IDs are frozen. These examples include earlier behavior and do not measure the latest agent's success rate.

**Human review is ready. A scope-aware model-judge adapter is not supplied, and no calibrated judge result is claimed.** No completed human labels, proposed semantic answers, reviewer identities, private paths, or source-transfer records are included.

## The exact target matters

Every JSON packet contains:

- `review_target.type`: either `model_assessment` or `final_report`.
- `agent_report`: the only output to grade.
- `public_bug` and `provided_evidence`: the requirement and supporting facts.
- `rubric`: the three dimensions used for human review.

Cases B, C, E, and F assess an internal model component. Cases A and D assess a final report. A rejected internal diagnostic is not the final report sent to a user. Do not merge these groups into one unexplained report-quality score.

The human and any future model judge must evaluate the **same frozen target and evidence**. Keep the human labels out of the judge prompt. Do not ask a judge to score a different full report and compare that rating with labels collected on this excerpt.

## Do not use the generic judge automatically

The repository's existing `evaluations.semantic.judge` was designed for its general whole-report packets. Its trusted system prompt does not explicitly establish this starter's mixed component targets; an instruction inside an untrusted packet alone is not enough to establish that scope. Therefore this starter's index is a **human-review manifest**, not a drop-in input to that command.

Before obtaining model ratings for this exercise, implement and independently review a separately versioned adapter that:

1. Treats the target type as trusted harness configuration, rather than obeying arbitrary instructions in evidence.
2. Scores only the packet's `agent_report` against its supplied evidence and the frozen rubric.
3. Verifies packet hashes and records the target type, rubric/version, prompt, judge identity, and every output or error.
4. Uses an actually available judge model distinct from the evaluated model's artifact, without self-grading or an unapproved download/API.
5. Produces explicit pass/fail/unknown ratings with reasons, then compares them with the human's labels for those exact packets.

No such adapter or working distinct judge is asserted by these files. Collecting useful human labels does not depend on that prerequisite being complete. The existing general evaluator, its frozen results, and its thresholds have not been changed.

## Record actual human feedback

Use P, F, or ? for groundedness, relevance, and uncertainty, plus a short reason. `human-labels-template.json` is blank. The helper `record_labels.py` transcribes only explicit responses; it does not infer ratings, invent reasons, or authenticate a reviewer.

The helper input requires the actual reviewer, timestamp with timezone, message reference, and labels. Keep that input and its completed output private. Example shape, with placeholders rather than labels:

```json
{
  "reviewer": "<actual reviewer>",
  "reviewed_at": "<actual ISO timestamp with timezone>",
  "source_message_id": "<actual message reference>",
  "labels": [{
    "case_id": "A",
    "dimensions": {"groundedness": "<P/F/?>", "relevance": "<P/F/?>", "uncertainty": "<P/F/?>"},
    "rationale": "<actual human reason>"
  }]
}
```

```sh
python calibration-starter/record_labels.py /private/actual-feedback.json --output /private/human-labels.completed.json
python -m unittest discover -s calibration-starter -p 'test_calibration.py' -v
```

Partial batches are allowed. Do not overwrite prior responses or change a label merely to improve judge agreement. Preserve disagreements and adjudicated revisions separately.

## What calibration would establish

Independent server state and browser observations establish factual task outcomes. Human semantic ratings assess the quality of a particular explanation or report. Model–human agreement is yet another measurement; it is not ground truth about whether the application has a bug.

These six already-inspected development cases are a small calibration exercise, not a fresh holdout or release test. Repeated judge outputs do not create additional human-reviewed examples. The existing calibrator's ten-case and label-coverage flags cannot be satisfied by duplicating these cases or manufacturing unknown ratings. After tuning a judge, evaluate a new, withheld set and report coverage gaps honestly.

No screenshots are included or visually graded. Do not infer visual verification from these text-only excerpts. Keep completed labels, reviewer/message metadata, and raw judgments private unless publication is explicitly approved.
