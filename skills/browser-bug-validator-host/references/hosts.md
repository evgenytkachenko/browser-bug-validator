# Host adapters

The shared workflow is plain Agent Skills Markdown. Each host runs its current
model and tools. There is no embedded model client, automatic tool grant, MCP
installation, hook, background command, or global configuration change.

## Claude Code

Use the project-local `.claude/skills/browser-bug-validator-host/SKILL.md` in a
local Claude Code project. Invoke `/browser-bug-validator-host` followed by the
report and scope, or let ordinary skill discovery select it when relevant. The
package intentionally sets no `model`, `context: fork`, or `allowed-tools` field.
Normal host permissions still apply. This skill does not create a browser tool.

At runtime inspect the tools that the current Claude Code session actually
exposes. If an authorized browser integration is present, use its instructions
and native tool calls. Otherwise report the missing capability or use the
controlled fixture bridge only when that is the requested test. Do not claim
that packaging compatibility proves Claude ran the workflow.

Official reference: https://code.claude.com/docs/en/skills
Checked 2026-11-09. Project-local skills are documented for local Claude Code
sessions; cloud/Cowork availability and account skill sync have different rules.
Do not promise that copying a project folder installs it in all Claude surfaces.

### Agent tool access is separate from skill loading

A Claude agent with `tools: Read, Glob, Grep, Bash` cannot use MCP tools. Loading a
skill does not widen that agent allowlist. The repository includes an optional
`.claude/agents/browser-bug-validator-host.md` that requests skill preloading,
inherits the current model, and adds `mcp__playwright__*` to local support tools.
Before validation, that agent must invoke Skill if the full instructions are
absent. Main-session CLI loading and delegated-agent preloading can differ; a
registered skill description is not proof that its body was loaded. It assumes
an already configured server named `playwright`; it neither installs nor
configures one. A different server name needs a reviewed project allowlist change.
Check actual server/tool availability in the host before promising browser use.

Invoke that agent by asking Claude to use `browser-bug-validator-host`, or start
`claude --agent browser-bug-validator-host`. This agent file is separate from the
portable skill folder. Existing legacy agent definitions are not overwritten by
the skill generator. Official agent tool-filter reference:
https://code.claude.com/docs/en/sub-agents

## Codex

Use the project-local `.agents/skills/browser-bug-validator-host/SKILL.md`.
Invoke `$browser-bug-validator-host` with the report and scope, or use normal
skill selection. Optional `agents/openai.yaml` supplies display metadata, not a
browser connection or permission. Automatic selection remains enabled.

Read the actual browser tool/skill made available by this Codex session. Tools
can vary across CLI, IDE, desktop, and cloud environments. A shell alone does
not imply an existing browser capability. Use the controlled bridge only for
its approved fixture mode; do not use it as a fallback way into a live site.

Official reference: https://developers.openai.com/codex/skills/
Checked 2026-11-09; it currently redirects to
https://learn.chatgpt.com/docs/build-skills and documents repository discovery
under `.agents/skills` between the working directory and repository root.

## Portable copy

The complete `skills/browser-bug-validator-host` directory is self-contained for
native-browser guidance. A user can explicitly copy it into either documented
project skill location. Use only one same-named copy per host scope when practical,
and check for existing personal/enterprise skills that could shadow it. Do not
overwrite another skill or install it globally without approval.

The controlled bridge is repository code, not bundled into the portable folder.
If that mode is needed, obtain an authorized checkout and inspect its documented
commands and prerequisites. The native mode does not require that checkout,
Python, Node, Playwright, or Ollama beyond the host's own browser requirements.
