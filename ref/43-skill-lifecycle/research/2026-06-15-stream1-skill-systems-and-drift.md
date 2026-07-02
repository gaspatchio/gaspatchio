# Research Stream 1 — How agent-skill systems version, distribute, and stay current

**Date:** 2026-06-15 · primary-source brief · `[VERIFIED]` = official docs/specs/repos; `[INFERENCE]` = labelled reasoning.

---

## 1. Anthropic Agent Skills + Claude Code plugins
**Format [VERIFIED]** (agentskills.io/specification): directory with required `SKILL.md` (YAML frontmatter + Markdown), optional `scripts/`, `references/`, `assets/`. Frontmatter: `name` (required, ≤64 chars, lowercase alphanumeric + hyphens, **must match parent directory name**); `description` (required, ≤1024 chars); optional `license`, `compatibility`, `metadata` (where `version` lives), `allowed-tools` (experimental).

**Progressive disclosure [VERIFIED]:** metadata (~100 tokens, all skills, at startup) → SKILL.md body (<5000 tokens, on activation) → resources (on demand). "Keep SKILL.md under 500 lines." "Keep file references one level deep."

**Validation [VERIFIED]:** `skills-ref validate` checks frontmatter/naming only — **no code-example validation**. `claude plugin validate [--strict]` recommended for CI ("the review pipeline runs the same check"); `--strict` treats warnings as errors, catching leftover fields from another tool's manifest.

**Versioning [VERIFIED]** (plugins-reference §Version management): explicit `version` (opt-in updates, "stable release cycles") vs omit version → commit-SHA (updates every commit, "internal/active development"). "Pushing new commits alone is not enough" if `version` is set.

**Provably effective [VERIFIED]** (anthropics/skills DeepWiki §4.2): ships `evals/evals.json` per skill — `skill_name`, `evals[]` with `id`/`prompt`/`expected_output`/optional `files`/`expectations` ("verifiable statements used for grading"). Harness `run_eval.py`: (1) trigger testing (does the description make Claude invoke the skill, watching for Skill/Read tool calls); (2) execution; (3) LLM Grader Agent citing evidence for each PASS/FAIL → `grading.json`. CI usage not documented.

**Drift vs evolving API: GAP [INFERENCE].** Nothing detects stale embedded examples. Validation is frontmatter/naming + optional behavioral evals.

## 2. Cursor Rules
**[VERIFIED]** `.cursor/rules/*.mdc`, frontmatter `description`/`globs`/`alwaysApply`; four activation modes; legacy `.cursorrules` deprecated late-2024. **Anti-drift doctrine [VERIFIED]:** "Reference files instead of copying their contents — this keeps rules short and **prevents them from becoming stale as code changes**." No versioning/validation/sync mechanism. [INFERENCE] Argues *against* embedding code that duplicates the API — directly relevant.

## 3. GitHub Copilot
**[VERIFIED]** `.github/copilot-instructions.md` (repo-wide), `.github/instructions/**/*.instructions.md` (`applyTo` glob), plus `AGENTS.md`/`CLAUDE.md`. No versioning/validation/single-source documented. **Cross-target find [VERIFIED]** (code.visualstudio.com agent-plugins): "The plugin format is shared between VS Code, GitHub Copilot CLI, and Claude Code. A single plugin repository can work across all three tools." Auto-detects `.plugin/plugin.json`, `plugin.json`, `.github/plugin/plugin.json`, `.claude-plugin/plugin.json`. **Trap [VERIFIED]:** "all tools require plain kebab-case names in SKILL.md. Namespace prefixes (like myorg/skillname) cause silent load failures."

## 4. OpenAI
**[VERIFIED]** JSON-schema function tools + freeform `instructions`. `strict: true` guarantees output matches schema; "Generate Anything" generates a schema from pasted code. [INFERENCE] Keeps *output* conformant and eases authoring, but nothing keeps schema/instructions in sync with code as it changes; no instruction-versioning/registry.

## 5. MCP
**[VERIFIED]** Tools (`name`/`description`/`inputSchema`/optional `outputSchema`/`annotations`) introspected at runtime via `tools/list`; `listChanged` notifications; date-based protocol version. [INFERENCE] Eliminates static-file drift for tool *existence/shape* (renamed/removed tool propagates automatically) but has **no mechanism ensuring the human-written description matches what the code does** — solves structural, not prose/semantic, drift.

## 6. Community registries — superpowers / `npx skills`
**[VERIFIED]** `npx skills add obra/superpowers --agent claude-code` targets Claude Code/Codex/Cursor/Copilot/Gemini/etc. **superpowers v2.0 [VERIFIED]:** skills moved to a dedicated repo; plugin became a shim managing a local clone; session-start hook fetches + fast-forward auto-merges, notifies on divergence; skills version independently. [INFERENCE] Closest field analogue to a single canonical registry fanning out to many targets — pushes *latest* continuously (git-fetch) rather than pinning.

## 7. Auto-maintenance / auto-repair + FIELD DATA
**gh-aw [VERIFIED]:** Markdown+YAML workflows compiled to GitHub Actions that open PRs; a "Daily Documentation Updater" identifies out-of-sync doc files; deliberately narrow, one-concern-per-workflow; validation-only variants exist.

**Merge-rate field data [VERIFIED]** (gh-aw continuous-docs blog):

| Workflow | Scope | Merge rate |
|---|---|---|
| Glossary Maintainer | narrow | 100% (10/10) |
| Daily Documentation Updater | narrow | 96% (57/59) |
| Documentation Unbloat | medium | 85% (88/103) |
| Documentation Noob Tester | broad | 43% (9/21) |

**MSR 2026 [VERIFIED]** (arXiv 2601.15195, 33k PRs): "documentation, CI, and build update achieve the highest merge success." "Not-merged PRs tend to involve larger code changes, touch more files, and often do not pass CI/CD."

## Implications
1. **Single canonical registry — CONFIRMED, and ahead of most of the field.** Only superpowers v2.0 and the shared plugin standard do true single-source; Cursor/Copilot/OpenAI have none. The shared format makes one canonical source genuinely multi-target — no need to hand-maintain N manifests.
2. **Deterministic-gates-first — CONFIRMED by field data** (96–100% vs 43%; merged PRs pass CI). Gate on `claude plugin validate --strict` + frontmatter/name/dir-name consistency + cross-tool traps; scope any auto-repair narrowly.
3. **Where we'd LEAD [INFERENCE]:** executable validation of embedded examples vs the live API — no surveyed system does it; our docstring-test infra positions us to own it.
4. **Currency is a real fork:** Anthropic pins; superpowers auto-pulls. Recommend currency via regenerate-from-gated-source, human-facing source on deliberate cadence.
5. **Reconcile "reference don't duplicate" vs "complete examples for LLMs":** only by test-covering embedded examples.
6. **Borrow `anthropics/skills` evals.json** schema for effectiveness; wire into CI (which Anthropic has not documented doing).

### Key URLs
agentskills.io/specification · github.com/agentskills/agentskills/tree/main/skills-ref · code.claude.com/docs/en/plugins-reference · deepwiki.com/anthropics/skills/4.2 · cursor.com/docs/context/rules · docs.github.com/en/copilot/reference/custom-instructions-support · code.visualstudio.com/docs/agent-customization/agent-plugins · modelcontextprotocol.io/specification/draft/server/tools · github.com/obra/superpowers/blob/main/RELEASE-NOTES.md · github.github.com/gh-aw/blog/2026-01-13 · arxiv.org/abs/2601.15195
