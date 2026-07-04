# Privacy

The **gaspatchio** plugin for AI coding agents (Claude Code, Cursor, GitHub
Copilot, and other Agent Skills / AGENTS.md consumers) ships **static content** —
Agent Skills (Markdown instructions and reference files) and plugin manifests.
The plugin's own files contain no telemetry and make no network calls.

## Network use via the gaspatchio tooling

Some skills instruct the agent to run helper commands from the separately
installed gaspatchio Python package (`gspio`) — notably **`gspio docs`** and
**`gspio knowledge`**. When those commands run, they send **your search query**
to a gaspatchio-operated documentation and knowledge API (default
`https://gaspatchio-mix.fly.dev`, overridable via the `GASPATCHIO_API_URL`
environment variable) and return the results.

- **What is transmitted:** the text of the query you or the agent searches for
  (an API symbol, an actuarial concept, etc.).
- **What is not:** the plugin sends nothing on its own; only these explicit
  lookup commands make a request, and only when they are run.

All other skills (model building, reconciliation, review, scenarios, extending)
operate on your own project files **locally** and make no network calls.

## What the plugin does not do

- It collects no personal data itself.
- It includes no telemetry, analytics, or background "phone-home" behaviour.
- It bundles no service or MCP server.

Handling of the search queries sent to the gaspatchio documentation and knowledge
API is governed by its operator, **Opio Inc.** To avoid the hosted lookups, do
not run `gspio docs` / `gspio knowledge` (the other skills do not require them),
or point `GASPATCHIO_API_URL` at your own endpoint. Questions or concerns: open an
issue at <https://github.com/gaspatchio/gaspatchio/issues>.
