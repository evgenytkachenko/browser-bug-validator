# Evidence and result contract

For each attempt preserve an ordered, concise record of the important actions and
observations. A readable report is the default; structured JSON is useful when
requested by a harness. Do not create fake empty evidence just to fill a template.

## Required information

- **Result and scope:** verdict, bug/target, environment, and what was actually
  tested. Use `inconclusive` if decisive evidence or prerequisites are absent.
- **Expectation:** the relevant behavior and its source. A bug report may define
  a hypothesis; it does not establish that the application violated it.
- **Execution:** native-browser or controlled-fixture mode, actual tools used,
  browser/viewport/account role when known, and host/model version only if the
  runtime actually exposes it. Otherwise say unknown or operator-declared.
- **Attempts:** steps taken, intended inputs, observed values, failed attempts,
  and the final decisive check. Keep failures and refusals in the denominator.
- **Evidence:** actual tool references, verified local artifact names, or direct
  excerpts bound to the observation where they were captured. Separate screenshot
  existence/integrity checks from actual visual inspection.
- **Limits and residual state:** blocked checks, relevant differences from the
  reported conditions, changed test data, uninspected artifacts, and any safe
  next step. Label a root-cause explanation as a hypothesis unless independently
  verified. Do not claim to have fixed anything in a validation-only task.

Example report shape (illustrative, not a completed run):

```text
Result: <confirmed | not_reproduced | inconclusive>
Scope: <environment, exact target, tested conditions>
Expected: <behavior and source>
Observed: <decisive before/action/after observations>
Attempts: <counts and relevant failures>
Evidence: <real references and what each supports>
Limits / residual state: <what remains unknown or changed>
```

## Strength of claims

Confirmation needs relevant observed mismatch, established preconditions, and
target identity. Lack of a visible error is not a completed negative trial.
Successful save feedback is not proof of persistence. Missing probe values or
access refusal cannot establish that a product defect exists.

The controlled harness derives an objective verdict from operator-defined checks
and validates the host's response against evidence. Passing that system measures
the combined host/controller/specification, not unconstrained model judgment.
An incorrect specification can still yield a formally valid but irrelevant result.

For evaluations, separate:

1. Unit/contract checks, which may use doubles.
2. HTTP fixture checks, which do not run a browser or model.
3. Scripted real-browser controls, which do not measure a host model.
4. Live host-selected decisions through the harness, with verified transcript
   provenance where available.
5. Native-browser host trials, whose safeguards and evidence differ from the harness.
6. Human or independent semantic review, only when it actually occurred.

Never relabel a replay or scripted policy as a live Claude/Codex trial. A declared
host label is not attestation. Do not infer improvement over the historical
5/16 full-trial local-model result without a comparable, disclosed experiment.
