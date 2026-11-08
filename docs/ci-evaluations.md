# CI evaluation setup

The [token-free workflow](../.github/workflows/evals.yml) runs on pull requests,
pushes to `main`, and manual dispatch. It does **not** call a model, download a
model, use a paid API, or establish agent reliability. GitHub's own temporary
read-only job token is used for ordinary checkout; no user-supplied API token or
repository secret is needed. Standard public-repository hosted runners are
normally free under GitHub's applicable plan. Private-repository allowances and
other runner types may differ.

## What runs now

1. **Unit and contract controls.** Python compilation, both Node controller syntax
   checks, the main `unittest` suite, and the five calibration-tooling tests.
   The suite includes mocked model/browser responses and local fake HTTP model
   transport. Those are software checks, not actual model inference or human
   calibration.
2. **HTTP golden controls.** Validate all 17 catalog definitions, then execute the
   11 development cases against the actual disposable HTTP fixture and compare
   its request journal and final state with the oracle. This does not run page
   JavaScript or a browser. The six reserved cases are not executed.
3. **Scripted real-browser integration.** Install locked Playwright plus its
   matching Chromium on a fresh Linux runner. Execute the general agent loop on
   all 11 development cases, one trial each, using `ScriptedControl` instead of an
   LLM. Chromium actually navigates, fills/selects fields, clicks, reloads, and
   records evidence against a local fictional fixture. Objective graders check
   behavior, state changes, request scope, screenshots, and trace consistency.
   The integrity loader replays grades, and the CI gate rejects incomplete
   schedules or missing browser activity. Nine cases must start a real browser;
   two input/authorization refusals must not. Eight cases exercise a complete
   bug/fixed workflow; the ninth browser case checks denied access.

Both jobs fail on a failed check. Browser startup failure is **not** silently
skipped or called a passing eval. The browser sandbox remains enabled. No
`continue-on-error`, deterministic fallback for a model call, or reserved-split
execution is used. A green run means the software and scripted development
controls passed, not that an LLM can reliably choose the right actions.

The workflow uses read-only repository permissions, SHA-pinned official actions,
an npm lockfile, no persistent checkout credentials, short timeouts, and ordinary
`pull_request` rather than privileged `pull_request_target`. It grants no AWS or
other cloud identity. It publishes only named logs/summary files for seven days,
not raw screenshots, agent responses, local configs, or completed human labels.
The fixtures and summary content are fictional. Future runs against real data
need a separate review of what can be uploaded and who can access the artifacts.

## Reproduce locally

From the repository root, with Python 3.10+ and a supported Node installed:

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s calibration-starter -p 'test_*.py' -v
python -m evaluations.task_catalog validate
python -m evaluations.task_catalog verify --receipt runs/local-http-goldens.json
```

For actual browser controls, use an existing supported browser configuration as
documented in the README, or follow the explicit dependency installation and
config-generation steps in the workflow. Unlike the normal agent commands, the
CI setup intentionally installs Playwright, Chromium, and Linux dependencies.
It does not modify the user's ordinary browser profile.

```sh
python -m evaluations.general_run --backend scripted-control \
  --split development --trials 1 --browser-config browser.local.json \
  --timeout 120 --output runs/local-scripted-browser
python -m ci.verify_control runs/local-scripted-browser
```

Use a fresh output directory each time. The integrity verifier requires the
complete raw run locally; the small uploaded CI summaries alone are not a
replayable evidence bundle. Hashes check same-writer consistency, not independent
authenticity. CI is not a hardened hostile-code or production-data sandbox.

## Real-model stage: what would change

The test setup is still a disposable app plus a real browser. The model replaces
only the decision-maker: **observe → model chooses one allowed action → execute
in Playwright → observe again → finish → independently grade**. Hidden expected
outcomes and fixture state remain evaluator-owned, not model input. The browser
runs on the CI runner; Bedrock would supply inference, not host the browser.

The current code supports only a local Ollama endpoint, with verified model
identity and Ollama-specific provenance. **Bedrock is not implemented.** Adding
AWS credentials alone cannot make the current CLI use Bedrock, and there is no
working `--backend bedrock` command to enable. A real implementation needs:

- A separate Bedrock adapter using an authorized model ID/inference profile and
  region, mapping the existing action schema to supported structured responses.
  Keep strict parsing, action budgets, timeouts, and no silent fallback.
- Provider-aware model identity, provenance, token/latency records, and grading
  checks. Existing Ollama digest checks must not be bypassed or mislabeled.
- Tests with mocked Bedrock transport for adapter errors and schema behavior,
  followed by actual repeated model/browser trials. Mocks cannot qualify the
  real-model lane.
- Separately authorized AWS access. Prefer GitHub OIDC with short-lived role
  credentials, a trust policy limited to the intended repository/ref or protected
  environment, and only the necessary Bedrock invocation resources/actions.
  Do not expose cloud credentials to untrusted fork PR code. Creating that trust
  relationship is a separate security-sensitive setup step, not part of this CI.
- A trusted manual/scheduled workflow or a reviewed branch with explicit cost
  limits, maximum tasks/trials/tokens, timeouts, and spend monitoring. Keep the
  token-free PR checks separate. Start with a small paid smoke, then a frozen,
  repeated development suite; report failures and invalid/inconclusive outputs
  rather than retrying until green.

Agent performance should be broken out into full-workflow successes, refusals,
actual model participation, objective safety violations, latency, and cost. The
current recorded model baseline remains **5/16 full browser-validation trials**;
this CI change does not improve or replace that measurement. Do not turn that
unstable prototype into a mandatory 100%-pass model gate without a measured
baseline and an agreed regression policy.

An optional semantic judge is another model invocation after the agent run, not
the source of truth about the browser's effects. Keep it independent of the
agent, apply code checks first, calibrate it against real expert labels, and
report uncertainty/disagreements separately. The synthetic judge reference set
and passing calibration unit tests do not establish real judge accuracy.

Ollama itself does not require API tokens. A small open model can run on a
standard CPU runner if its license, memory/disk use, downloads, and runtime fit.
It may be slow, and choosing a smaller model changes the system being evaluated.
A reliable large-model agent plus a separate judge is not guaranteed by free CPU
capacity. No Ollama download or inference job is enabled in this workflow.

Reserved cases remain reserved rather than becoming a per-commit regression
suite. They are already author-visible and are not a blind benchmark. A new,
independently held-out set is needed for a credible unseen-generalization claim.
