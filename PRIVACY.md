# Privacy

The **gaspatchio** plugin for AI coding agents (Claude Code, Cursor, GitHub
Copilot, and other Agent Skills / AGENTS.md consumers) ships **static content
only** — Agent Skills (Markdown instructions and reference files) and plugin
manifests. It:

- collects **no** personal data;
- includes **no** telemetry, analytics, or "phone-home" behaviour;
- makes **no** network calls of its own; and
- runs **no** bundled service or MCP server.

The skills instruct an AI coding agent to work on your own project files
locally, using the gaspatchio / `gspio` tooling you install separately. Any data
handling is governed by the AI client you use (for example, Claude Code) and
your own environment — this plugin transmits nothing and stores nothing.

Questions or concerns: open an issue at
<https://github.com/gaspatchio/gaspatchio/issues>.
