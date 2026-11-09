# Native Claude Code and Codex agents

This checkout includes two project-scoped **operator agents** named
`browser-bug-validator`:

- Claude Code: `.claude/agents/browser-bug-validator.md`.
- Codex: `.codex/agents/browser-bug-validator.toml`.

They guide the selected coding assistant through the existing validator, inspect
its evidence, and report the result. They **do not replace the local Ollama model**
inside `python -m bug_validator run-general`. Claude/Codex conversation usage is
still governed by your account; the existing validator does not gain an Anthropic
or OpenAI runtime backend, a cloud fallback, or arbitrary-site support.

## Select in Claude Code

Open a terminal in this checkout and start the agent as the main session:

```bash
claude --agent browser-bug-validator
```

In an existing Claude Code session rooted here, type `@` and select
`browser-bug-validator`, then give it the request. You can also explicitly ask
Claude to delegate to that agent. Start a new session after adding the file if it
has not been discovered. In current Claude Code, `/agents` points to file-based configuration, while
`claude agents` opens the background-session view. Neither is a custom-agent
creation wizard.

For a safe initial interaction, ask: “What inputs do you need to validate a bug?
Do not run the browser or model yet.” For execution, supply the actual local file
paths and explicit approval for the disposable fixture and its exact effects.
Do not use bypass-permission flags.

## Select in Codex

Open this checkout as the project in the local app, or start the CLI in this
directory. Start a fresh conversation and ask:

> Spawn the browser-bug-validator agent to tell me which inputs are needed.
> Do not run the browser or model yet.

For a real run, explicitly request that same agent and provide the reviewed
inputs and authorization below. This is a **named subagent**, not a new model in
the model selector or a `codex --agent` command. The current CLI's `/subagents`
view shows active spawned agents; the `codex agents` command manages sessions.
If the custom agent is not found, verify the project root and client version and
restart the session. Do not silently substitute another agent.

Some Mac app installations bundle the CLI without putting it on shell `PATH`.
Use the app normally. If needed, inspect your installation to locate its binary;
no shell profile edit or separate CLI install is required for these files.

## Required inputs and behavior

Provide the paths to the bug JSON, public KB JSON, independently reviewed
operator capability JSON, existing local Ollama config, existing browser config,
and a fresh output directory. Read [the runtime contract](general-agent.md) for
exact formats, mutation grants, report-hash binding and evidence rules. Only
explicitly authorized disposable fictional data at a numerical HTTP loopback
origin is supported. A capability file is not, by itself, user consent.

The agent must stop for missing inputs, mismatched authorization, unavailable
local dependencies, or denied access. It must not install packages/models,
generate and trust its own authorization, bypass the runner with direct browser
tools, or overwrite evidence. A fixture being on localhost does not make it safe
or authorized. Do not use production data or credentials.

Shell access is necessary to invoke the existing Python runner. Claude's
explicit tools list is `Read, Glob, Grep, Bash`; it is **not a shell-command
allowlist** and does not mechanically prevent shell writes. Its `permissionMode`
is `default`, subject to the host's parent-mode rules. Codex disables app/plugin
and memory features for this agent but otherwise inherits the parent permissions,
sandbox, provider, and available tools. Instructions are behavioral limits, not
an OS security boundary. Neither definition grants permission or configures MCP,
installs software, disables sandboxing, or enables automatic approvals.

The files intentionally inherit the platform's model instead of pinning an
account-specific model. The local validator's model is chosen separately in its
existing local model config. A successful native-agent load is not a model or
browser validation result; scripted controls are not model-reliability evidence.

## Project scope versus global installation

The files are discovered for sessions in **this checkout**. They do not install
into `~/.claude/agents/` or `~/.codex/agents/`, modify user-wide settings, add a
sidebar project, or become available in every repository. No global config file
is needed. Copying just an agent file to another project is insufficient: the
runner, documentation and trusted inputs must also be present. A user-wide
installation is a separate, optional change requiring an explicit decision.

## Compatibility and verification

The definitions follow the current official formats, reviewed on 2026-11-09:

- [Claude Code custom subagents](https://code.claude.com/docs/en/sub-agents):
  project Markdown with YAML frontmatter, main-session `--agent`, and @ selection.
- [Codex custom subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents):
  standalone project TOML containing `name`, `description` and
  `developer_instructions`. This is the current format, not the older
  `agents.<name>.config_file` registration scheme.

Local version checks found Claude Code **2.1.319** and the app-bundled Codex
CLI **0.167.0-alpha.3.2**. Claude's initialization-only native handshake listed
`browser-bug-validator` with the expected description. No user prompt or model
request was sent. Codex's no-inference prompt renderer ran successfully, but its
output did not establish custom-agent discovery, so Codex selection has not been
verified in a live session. TOML parsing and format checks passed. Older clients may have
different discovery/configuration behavior; these are not claimed minimum versions.
Keep project trust and approval choices under your normal platform policy.

Both files carry the same operator protocol. The repository's unit tests check
that they stay synchronized and retain the narrow tool/configuration shape.
Python 3.11+ also parses the TOML with the standard-library parser; on Python 3.10
that parser-specific test is skipped rather than installing a dependency. These
static checks do not establish live agent behavior or runtime reliability.

Verification on this change also passed all 191 unit/contract tests (including
six new native-definition checks), five synthetic calibration-tool tests,
13 trace-viewer JavaScript tests, syntax checks, the 17-task catalog validator,
11 development HTTP goldens, and all 11 scripted development controls (nine
real-browser trials and two preflight refusals). No model calls or reserved
transfer cases were executed. These are packaging and integration controls,
not native-agent behavior or model-reliability measurements.

On the checked Mac, the system `python3` is too old; an existing Python 3.12 was
used. The first unit run also encountered macOS temporary-directory symlink
rejection and two missing-Node skips. The final full run used an existing Node
binary on the command-local `PATH` and a real, checkout-local `TMPDIR` under
ignored `runs/`; all 191 then passed without skips. No application guardrail was
relaxed and no global shell configuration was changed.
