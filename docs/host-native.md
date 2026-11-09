# Host-native browser validation

This candidate lets Claude Code or Codex do the reasoning with its current model.
It requires no Ollama server, separate model API key, or new model subscription.
The host's own usage limits and any configured tool costs still apply.

## Two distinct paths

**Native browser:** The assistant uses an existing, authorized host browser tool
to investigate a specifically scoped web UI bug. The portable skill provides
target selection, observation-driven interaction, permission discipline, and
evidence/reporting guidance. It does not add a browser or enforce an HTTP allowlist.
Its constraints are instructions, plus whatever the actual host enforces.

**Controlled fixture:** The assistant chooses one structured action after each
fresh observation; the repository's existing isolated Playwright controller
executes only admitted fixture actions. This replaces the decision source, not
the browser/controller. It requires Python 3.10+, Node, existing Playwright and
compatible Chromium/Chrome, plus authorization to start local processes and the
disposable loopback app. See [host control](host-control.md).

Do not compare these as if they were the same evaluated system. Neither is an
OS sandbox, and the controlled mode remains fictional-fixture-only.

## Use the skill

The canonical source is `skills/browser-bug-validator-host/`. This candidate also
contains self-contained, generated project adapters:

- Claude Code: `.claude/skills/browser-bug-validator-host/`
- Codex: `.agents/skills/browser-bug-validator-host/`

From a local project session, use `/browser-bug-validator-host` in Claude Code or
`$browser-bug-validator-host` in Codex. Supply the report, exact target URL/record,
expected behavior, and allowed effects. Example scope:

> Check the reported search-results bug at the staging URL I supplied. Use only
> the test account already open in the authorized browser, enter the query in
> the report, and read the result list. Do not save settings or send data elsewhere.

If the current host lacks a browser tool, the skill should say so, not install
one or pretend an HTTP fetch reproduced the UI. Loading a skill does not authorize
test mutations, login changes, new integrations, external uploads, or publication.
No global skills, user settings, or browser profiles are modified by this package.

## Claude agent and Playwright MCP

The optional project agent `.claude/agents/browser-bug-validator-host.md` requests
skill preloading and inherits the current model. It instructs the agent to invoke
Skill before validation if the full instructions are absent; the frontmatter alone
does not prove the body was loaded in a CLI main session. Ask Claude to use that agent, or
start `claude --agent browser-bug-validator-host` from the repository. Its tools
include local reading/command support and `mcp__playwright__*`, scoped to an
already configured MCP server named `playwright`.

This distinction matters: an older agent listing only Read, Glob, Grep, and Bash
cannot use MCP tools. A Playwright Python/Node controller invoked through Bash
is not a native Playwright MCP tool. Neither the skill nor the new agent installs
or configures a server. Use the host's actual MCP/tool listing to check what is
available. If the server has another name, review the project agent's allowlist
against that real name; do not broaden access or install a server automatically.
Existing legacy agent definitions and global configuration remain untouched.

The canonical skill folder may be copied, when requested, into another project's
documented host location. Both generated folders include their references; they
do not depend on symlinks into this repository. The native-browser instructions
remain usable without this repository's Python controller. The controlled mode
does require the repository separately.

## Maintain the packaged adapters

Edit the canonical source. From the repository root:

```bash
python scripts/build_host_skills.py --check
python scripts/build_host_skills.py --write
python -m unittest discover -s tests -p 'test_host_skills.py' -v
```

The generator writes only these two project-local skill folders. It refuses
symlinked sources/destinations, unrecognized existing directories, extra files,
or local edits to generated files rather than overwriting them. It never changes
host settings, installs tools, or calls a model. `--check` is read-only.
The optional `.claude/agents` definition is maintained separately; the generator
does not overwrite a user's existing agent files.

## Evidence and verification limits

Read the skill's [evidence contract](../skills/browser-bug-validator-host/references/evidence.md).
Schema validation, discoverable folders, and scripted controls are not live host
behavior tests. Report packaging, unit checks, real-browser controls, live host
decisions, pixel inspection, and independent review separately. A `host=claude`
or `host=codex` label supplied by a caller is not identity attestation.
The bridge also does not attest skill loading or adherence; those need separate
host transcript evidence. Its scripted tests cannot verify host discovery.

The previous repository's recorded local-model baseline is unchanged. No new
model reliability, native browser safety equivalence, or production readiness is
implied by this candidate. See the separately recorded verification results for
exact checks actually run.

The [skill validation record](host-skill-validation.md) separates passed packaging
checks and an offline behavior scenario from the blocked CLI smoke test.
The [implementation verification record](host-native-validation.md) adds actual
Mac host discovery, scripted browser controls, a passing Claude loaded-skill
fixture trial, and the preserved Codex cleanup failure.

## Source

Based on public commit `6be965fa69c0b884613ddd72249c02524efead93` of
https://github.com/evgenytkachenko/browser-bug-validator. The host skill and bridge
are additional candidate work, not part of that published commit. MIT licensing
continues to apply. Runtime tools and models are not redistributed.

Host packaging was checked against the official
[Claude Code skills documentation](https://code.claude.com/docs/en/skills) and
[Codex skills documentation](https://developers.openai.com/codex/skills/) on
2026-11-09. The links describe discovery, not a guarantee of a browser integration.
