# Host-native implementation: verification and limits

Recorded 2026-11-09. This is a development verification record, not a model
benchmark, security certification, or production-readiness claim.

## What the implementation provides

- A portable skill using the current host model, with project adapters for Claude
  Code and Codex. No separate Ollama server or model API is required.
- Native-browser instructions for an existing authorized host browser tool.
  Those instructions do not add a browser integration or a security boundary.
- A distinct controlled-fixture bridge where the host selects decisions and the
  existing bounded Playwright controller executes admitted actions.

## Software checks

The initial cloud candidate passed 213 unit/contract tests, 5 calibration-tool
tests, 13 trace-viewer tests, and all 11 development HTTP golden checks. Python
and JavaScript syntax checks passed. The adapter generator's consistency check,
10 packaging tests, and all three skill frontmatter validations passed.

Independent review added 55 protocol, grading, and exact-archive probes. They
tested malformed/replayed inputs, altered evidence, failed outcomes, and honest
host provenance. These checks use synthetic observations where noted; they do
not establish live-browser or model reliability.

After the interruption fix, the final cloud suite passed **215/215** tests under
a deliberately symlinked temporary-directory root. Independent review passed
**62/62** probes: the original 55 plus seven actual interruption, timeout, and
malformed-response lifecycle checks. Interrupted/unanswered attempts are retained
as completed failed/inconclusive archives and replay without a grader traceback.
No controller, permission, provenance, or evidence gate was relaxed.

The post-fix `evaluations/general_grading.py` SHA-256 is
`b67002918113784e61f5a356165b897986d11c58685e7b945c4b58dfc466507e`.
Mac observations below used the earlier matching evaluator and are not claimed
as fresh trials of this post-fix revision.

The optional Claude project-agent frontmatter was parsed and checked for the
inherited model, requested skill preload, scoped Playwright tool allowlist, and absence
of inline server setup, hooks, or permission overrides. That static check does
not establish an installed Playwright MCP server or a live browser invocation.

An installed `claude --agent browser-bug-validator-host` main-session preflight
registered the wrapper and Skill tool, but reported the full skill body absent.
The wrapper now instructs the agent to invoke Skill before validation when the
full body is missing. Automatic main-session preload and delegated-subagent preload are
not claimed verified. That inspected installation had no configured Playwright
MCP server; the server wildcard did not create browser tools.

The corrected wrapper was then exercised in an actual installed
`claude --agent browser-bug-validator-host` main session. Its log showed an
explicit `Skill(browser-bug-validator-host)` call, followed by an accurate
description of both modes and the missing Playwright MCP capability. That
preflight performed no browser action. It verifies the explicit-load fallback,
not automatic preload or delegated-subagent preload.

## Post-fix Mac installation checks

The revised candidate passed 215/215 tests on the Mac. A real-browser interruption
before the first host response produced a completed `inconclusive` report and
archive; replay verified the expected failed outcome without the former grader
crash. This is interruption handling, not a successful bug reproduction.

Project-scoped installation preserved the existing legacy wrappers and added no
global settings or MCP configuration. The existing checkout included six legacy
tests in addition to the candidate's 215. Its final installed suite passed
**221/221**, zero skipped, after restoring a legacy README documentation link
required by that checkout. Generator consistency, the installed file inventory,
and diff checks passed. Candidate and installed-checkout test counts are not
interchangeable. No commit, push, or remote CI outcome is implied by these local
checks.

## Actual Mac host and browser observations

These tests used candidate archive SHA-256
`b4eaf420d41ff1a8d6c03a60f8e2cf54eca2e9c2eefe67f5197674fcf40ed0dd`, before the
interrupted-response grading fix. Runtime: macOS 26.4, Python 3.12.15, Node
24.22.1, Playwright 1.57.0, Chromium 156.0.8078.80, Claude Code 2.1.319, and Codex
CLI 0.167.0-alpha.3.2. Existing installations and authentication were used.

- **Mac software tests:** 213 passed, zero skipped after an existing Node binary
  was added to that process's PATH and an owned canonical temporary path was used.
- **Scripted browser controls:** 11/11 cases passed and replayed independently.
  Counts were 9 browser starts, 8 completed exercises, 3 expected refusals, and
  35 mailbox decisions. These were scripted decisions, not model-quality evidence.
- **Claude host decisions, fixed search:** `claude-opus-5-5` supplied four real
  decisions; three browser observations supported `not_reproduced`. Archive replay
  passed. Skill loading was separately observed, but these four calls did not
  invoke the Skill tool, so this is not a loaded-skill adherence result.
- **Claude loaded skill, buggy search:** Each of four real decision calls invoked
  `Skill(browser-bug-validator-host)` before returning the structured decision.
  Three browser observations supported `confirmed`; independent replay passed.
  This is one successful loaded-skill controlled-fixture development trial.
- **Codex loaded skill, fixed search:** `gpt-6.1-sol` read the skill and relevant
  references and supplied four valid decisions with three browser observations.
  Browser cleanup then timed out at 60 seconds. The final result was correctly
  `inconclusive`, with a failed objective grade. Archive replay verified that
  failed outcome. It is not a Codex end-to-end pass.

The CLI model identifiers were exposed by those host invocations. The bridge's
own host labels remain self-reported. Logs provide observational provenance, not
cryptographic identity attestation. Raw logs and screenshots remain local;
screenshots were not visually inspected by the host models in these trials.

## Failed attempts were preserved

The initial Mac test run encountered 3 failures and 10 errors because temporary
directories traversed macOS's `/var` symlink alias. A canonical temporary root
resolved the test-environment issue. Test fixtures now normalize only their own
new temporary roots; the runtime's symlink checks were not weakened. A later
213-test run had two skips due to Node not being on the process PATH, before the
fully passing run above.

Initial Claude discovery excluded project settings and therefore correctly found
no project skill. A corrected project-only invocation demonstrated discovery and
Skill loading. A first relay attempt hit a startup race before any model/browser
evidence; later trials used a new directory and waited for controller readiness.

The first Codex fixture invocation's optional strict-output-schema flag was
rejected for `uniqueItems` before model decisions. The next invocation omitted
that CLI flag, while the controller continued enforcing its full schema. The
interrupted first attempt exposed a null-response grading crash; that crash is
fixed and covered by the new regression. None of these attempts is counted as a
passing host trial.

Cloud Chromium could not start because of its execution environment's socket
permissions. Cloud Codex CLI failed before model invocation with a read-only
app-server storage error. Those are preserved blockers, not model failures or
successful reproductions.

## Still unverified

- Direct use of each host's native browser integration was not exercised by the
  controlled Playwright trials.
- One successful Claude loaded-skill case does not establish general reliability;
  the observed Codex trial failed end-to-end during cleanup.
- There is no blind holdout, visual-pixel evaluation, human-calibrated semantic
  score, or arbitrary-site production validation in this record.
- The historical local-Ollama baseline is unchanged and does not transfer to
  these host-native workflows.

The GitHub Actions workflow now covers scripted host-mailbox browser controls and
archive replay. A configured workflow is not evidence that a remote CI run passed;
check the exact published commit's checks separately.
