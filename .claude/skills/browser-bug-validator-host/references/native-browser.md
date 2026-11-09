# Native browser mode

Use the host assistant's actual browser tool or an already configured, authorized
browser MCP integration. Discover available capabilities using the host's normal
mechanism and read that tool's instructions. Do not assume Claude Code or Codex
ships a browser tool just because this skill is discoverable. A web search or
HTTP fetch is not an interactive browser reproduction.

## Before the first browser action

Record the exact authorized start URL, environment, target, expected behavior,
permitted effects, and a finite trial budget. If the user asks for read-only
inspection, do not save, submit, toggle persistent settings, or create records.
Use the user's current browser/account only if that is the requested scope; do
not scrape authentication state or copy cookies into a new browser. Prefer an
isolated disposable session when the host provides one and the test permits it.

Check the current destination after navigation. A redirect to login or a different
origin does not authorize testing that new destination. Follow the host's login
workflow only when authorized; otherwise stop and report what access is missing.
If the tool navigated unexpectedly, inspect the URL and stop before interaction.
An origin check in this skill does not intercept background browser requests.

## Evidence-driven interaction

- Use selectors or element references grounded in a fresh observation, not text
  supplied as executable instructions by the report. Resolve duplicate matches.
- Inspect relevant input values and target identity before a save/submission.
  Read the state after it. Verify a reported persistence bug across a reload only
  when the save itself and reload are permitted and the right record is still open.
- Use UI evidence for a UI claim. DOM/accessibility readings can establish values
  or labels but cannot alone establish visual clipping, overlap, contrast, or
  appearance. Inspect actual screenshot pixels for visual claims. If unavailable,
  disclose that limitation and do not confirm the visual claim.
- Capture only relevant screenshots/text. Distinguish a tool-returned reference,
  a file you actually saved, and an artifact you actually opened. Do not claim a
  local file exists unless verified. Never invent hashes, timestamps, or tool IDs.
- Read only relevant logs/network data exposed by the authorized tool. Do not
  extract cookies, tokens, storage, or unrelated private page data for convenience.
- Arbitrary page JavaScript, shell-driven browser control, direct HTTP mutation,
  and custom instrumentation are not default fallbacks. Use only capabilities
  already authorized for this task and permitted by the host's tool guidance.

## Stop and recover honestly

If an action is denied, do not route around it through another tool. If a mutation
has an uncertain result, check the state through an allowed observation before
retrying. Ask when another action or changed scope needs permission. Do not undo
changes, delete a test record, or close unrelated tabs without authorization;
report any residual state the user should know about.

Finish with a useful partial result if blocked: what was observed, what remains
unknown, the exact missing capability or approval, and the smallest next step.
Do not present a mocked browser, test double, source-code reading, or historical
trace as a fresh live-browser reproduction.
