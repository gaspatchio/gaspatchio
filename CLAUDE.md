# CLAUDE.md

Claude Code reads `CLAUDE.md`; the canonical, cross-agent rules live in `AGENTS.md` files.
This shim imports the principles, the framework knowledge, and both subproject rule sets so
a session started at the repo root has everything loaded. Codex/Amp/Cursor read `PRINCIPLES.md`
and these `AGENTS.md` files natively.

Codex merges only the root `AGENTS.md` plus the one nearest the working directory, and stops
at `project_doc_max_bytes` (32 KiB) silently, so those two files carry a condensed form and
point at the rest by path. **Claude Code has no byte cap**, so the imports below also pull in
every file the condensation moved out — a Claude session loses nothing.

@PRINCIPLES.md
@AGENTS.md
@core/AGENTS.md
@bindings/python/AGENTS.md
@CONTRIBUTING.md
@core/docs/rust-standards.md
@bindings/python/docs/api-philosophy.md
@bindings/python/docs/architecture.md
