# Task catalog and verified golden contracts

`evaluations/data/task-catalog-v1.json` is evaluator-private, author-visible
catalog version 1.0.0. It describes all 17 unchanged tasks from
`evaluations/general_tasks.py`: 11 development and six reserved-transfer cases.
These are **authored fictional tasks**, not harvested production incidents or
human-reviewed labels. The reserved cases are author-visible transfer inputs,
not a blind or unseen benchmark.

Every row records a task revision, family, split, source symbol and canonical
source-task hash, paired base buggy/fixed references, public checkpoint
requirements and a normalized public-input hash. Origin normalization uses
`http://127.0.0.1:54321` solely for hashing, never as an execution target. The
existing public input builder remains authoritative and unchanged. Reports,
knowledge and capability grants are generated separately: do not pass this
catalog, fixture modes, expected verdicts or oracle state to an agent or judge.

## Static contract validation

```sh
python -m evaluations.task_catalog validate
```

Validation checks exact task coverage/order, revision, provenance, limits,
source/input bindings, evidence requirements, pair references and static golden
contracts. Golden contracts state initial/final server state, ordered HTTP
requests and effects, POST attempt counts, state-change flag, expected verdict
and exact authorization rejection where applicable. A POST attempt is not
necessarily a persisted mutation: buggy status saves and rejected invalid
quantities can leave state unchanged. Search GETs update fixture search state
without a POST. State includes unrelated fields to catch collateral effects.

Changing the source task, public inputs, expected effects or schema requires
an intentional catalog revision and validator review; validation will not
silently regenerate or bless a changed golden. Tests deliberately corrupt
verdicts, counts, state, effects and metadata and require rejection.

## Real HTTP verification

```sh
python -m evaluations.task_catalog verify
python -m evaluations.task_catalog verify --task dev-01-status-bug --receipt /tmp/golden-receipt.json
python -m unittest discover -s tests -p 'test_task_catalog.py' -v
```

The verifier starts a **fresh disposable local HTTP fixture per development
case**, observes its actual initial state, invokes the production authorization
validator, and exercises HTTP requests using the standard library. It compares
actual response values, ordered server journal effects, final state and mutation
attempt counts against the static golden, then independently derives a fixture
verdict from the observed values. It never calls the agent's verdict helper or
runs a scripted/model agent. Status cases explicitly check initial read, save
acknowledgement and subsequent persisted read. Search and quantity cases compare
actual response payloads and server effects. Blocked access must return HTTP
403. Denied mutation and missing requirement cases must actually fail the
capability contract before requests and leave an empty journal and unchanged
state. This tests the authorization validator, not the full agent refusal path.

Reserved task execution is refused, including mixed selections, before starting
a fixture. Static integrity validation of reserved definitions is not execution
or transfer evaluation. No override is offered by this command. Use separately
controlled evaluation workflows if a reserved transfer run is authorized.

Optional receipts contain actual results, canonical catalog digest, exact
catalog-file hash, and hashes for the verifier, task definitions, fixture and
authorization contract dependencies. Source drift during execution fails the
run. Receipts are created only after successful real checks; no canned passing
receipt is distributed. Keep generated receipts outside tracked source.

## Interpretation

These are **real HTTP oracle contract controls**, not browser runs, model
performance results, human calibration, or visual pixel QA. JavaScript execution,
selectors, rendering, action ordering in a model loop, screenshot quality and
explanation groundedness remain untested by this command. The injection and
unrelated-warning variants only verify their HTTP contract here; passing does
not establish prompt-injection resistance. Metadata explicitly records these
limits. Browser/model trials and semantic/human reviews must remain separate.
