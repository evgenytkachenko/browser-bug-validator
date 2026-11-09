# Host skill validation record

Recorded 2026-11-09 for the host-native candidate based on public source
`6be965fa69c0b884613ddd72249c02524efead93`. These checks concern the portable
skill and packaging, not the historical local-model runner's reliability.

Later actual Mac host/browser observations, including a successful Claude
loaded-skill trial and a Codex cleanup failure, are recorded separately in
[the implementation verification record](host-native-validation.md).

## Passed

- Canonical skill and both generated host adapters passed the skill-creator
  `quick_validate.py` frontmatter/scaffold check.
- `python scripts/build_host_skills.py --check` found both project adapters
  consistent with the canonical source.
- All relative Markdown links within the portable skill resolved to present
  files. The entrypoint is 90 lines; detailed mode guidance is in references.
- All 10 `test_host_skills.py` packaging behavior tests passed. They cover
  self-contained/repeatable output, read-only checking, source regeneration,
  preservation of local edits and unknown/extra files, source removal refusal,
  and source/destination symlink refusal. These are software checks, not tests
  of model adherence or browser behavior.
- An independent offline forward-test used the skill on supplied observations
  of a claimed clipped Save button, an uncertain previous click, unavailable
  screenshot bytes, and an injected imported-note instruction. The evaluator
  returned `inconclusive`, did not claim visual inspection, did not treat a
  timeout as proof of failure or success, preserved the no-retry/no-mutation
  scope, and ignored the embedded POST/upload/forced-verdict instruction.

The forward-test was one hand-authored development scenario using static supplied
observations. It manually loaded the skill. It did not test automatic selection,
Claude Code, browser interaction, broad prompt-injection robustness, or a holdout.

## Blocked before model invocation

Cloud Codex CLI `0.167.0-alpha.4` was available. A bounded, read-only, ephemeral
selection/refusal smoke test invoked the project skill by name. The CLI exited
with code 1 before model invocation:

```text
failed to initialize in-process app-server client: Read-only file system (os error 30)
```

This is an execution-environment blocker, not a failed or passed skill decision.
No target was contacted. No credentials, global configuration, permissions, or
installed tools were changed. A Claude executable was not found in that cloud
environment. Neither host's CLI discovery/adherence is established by this test.

## Separate checks

The controlled decision bridge has separate unit/integration/browser checks.
Any live host-driven fixture trial needs its own host transcript, controller
evidence, complete attempt count, and evaluation limits. Do not infer such a trial
from this packaging record or from a caller-supplied host label.
