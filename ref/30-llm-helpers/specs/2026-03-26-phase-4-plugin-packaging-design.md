# Phase 4: Plugin Packaging & Distribution

**Date**: 2026-03-26
**Branch**: TBD (off `gsp-86-rollforward-impl` or new branch)
**Depends on**: Phases 1–3 complete (CLI improvements, tutorials, skills)
**Epic**: Distribute gaspatchio skills as first-class plugins across Claude Code, VS Code / Copilot, and Cursor

## Goal

An actuary installs the gaspatchio plugin in their editor and immediately has access to 6 actuarial modeling skills, always-loaded framework knowledge, and optional MCP integration — regardless of whether they use Claude Code, VS Code with Copilot, or Cursor.

## Context

### What Exists (Phase 3 Output)

Six skills already migrated to `skills/` at repo root with SKILL.md format:

| Skill | Lines | References |
|---|---|---|
| `quickstart` | 147 | — |
| `model-discovery` | 250 | — |
| `model-building` | 260 | 6 reference files (assumptions, common-mistakes, conditionals, model-phases, scenarios, timing) |
| `model-review` | 205 | 2 reference files (ASOP-56 checklist, gaspatchio antipatterns) |
| `model-scenarios` | 327 | — |
| `model-reconciliation` | 475 | 8 reference files (diagnostic techniques) |

All skills use YAML frontmatter with `name` and `description` fields. Reference files are in `references/` subdirectories within each skill.

### What Doesn't Exist Yet

- No `.claude-plugin/plugin.json` manifest
- No `.cursor-plugin/plugin.json` manifest
- No `.github/plugin.json` manifest (VS Code / Copilot)
- No `AGENTS.md` (always-loaded framework knowledge)
- No `.mcp.json` (MCP server config)
- No `agents/` directory (subagents)
- No marketplace submission

### Research Findings (March 2026)

Extensive research of the current ecosystem validates the approach and provides concrete format guidance:

**The SKILL.md open standard won.** Adopted by 26+ tools (Claude Code, VS Code/Copilot, Cursor, OpenAI Codex, Gemini CLI). Format: directory with `SKILL.md` containing YAML frontmatter + markdown. Progressive disclosure: ~100 tokens at startup (name + description only), full instructions when activated, reference files on demand.

**Multi-surface distribution is standard.** Stripe, Cloudflare, dbt, Timescale, Sentry, Expo all distribute from one repo with `.claude-plugin/`, `.cursor-plugin/`, and `.github/plugin.json` manifests pointing to shared `skills/`.

**AGENTS.md outperforms skills for broad knowledge.** Vercel's evals on Next.js 16 APIs: baseline 53%, skills 53–79%, AGENTS.md 100%. Always-loaded framework context eliminates the decision of "should I consult docs?" Skills are best for discrete, triggerable workflows.

**Two install paths coexist.** `npx skills add <owner/repo>` (universal, 26+ tools) and editor-native install (Claude Code `/plugin install`, VS Code `@agentPlugins`, Cursor auto-detect). Both should be supported.

**CLI beats MCP for local tools.** Community consensus: use CLI for local developer workflows, MCP only for remote services requiring auth. Gaspatchio's `gspio` CLI is the right primary interface; MCP at `mcp.gaspatchio.dev` is optional enrichment.

**Security matters.** HuggingFace analysis of 40K+ skills found 46% duplicates, 36% prompt injection, 13% critical security issues. First-party domain skills like gaspatchio's are inherently lower risk, but we should be explicit about our security posture.

Sources: See research notes in conversation context (Claude Code plugins docs, agentskills.io spec, Vercel AGENTS.md eval, HuggingFace skills analysis, SentinelOne marketplace research).

## Architecture

### Repository Layout (Target State)

```
gaspatchio-core/                          (repo root IS the plugin)
├── .claude-plugin/
│   └── plugin.json                       Claude Code manifest
├── .cursor-plugin/
│   └── plugin.json                       Cursor manifest
├── .github/
│   ├── plugin.json                       VS Code / Copilot manifest
│   └── workflows/                        (existing CI — unchanged)
├── AGENTS.md                             Always-loaded framework knowledge
├── .mcp.json                             Optional MCP server config
├── skills/                               Shared skills (already exists)
│   ├── quickstart/SKILL.md
│   ├── model-discovery/SKILL.md
│   ├── model-building/
│   │   ├── SKILL.md
│   │   └── references/                   (6 files)
│   ├── model-reconciliation/
│   │   ├── SKILL.md
│   │   └── references/                   (8 files)
│   ├── model-review/
│   │   ├── SKILL.md
│   │   └── references/                   (2 files)
│   └── model-scenarios/SKILL.md
├── agents/                               Subagents (deferred — not in v1)
├── core/                                 (existing Rust core)
├── bindings/python/                      (existing Python bindings)
├── tutorial/                             (existing tutorials)
└── ref/                                  (existing reference material)
```

### What Each Editor Gets

| Component | Claude Code | VS Code / Copilot | Cursor | `npx skills add` |
|---|---|---|---|---|
| 6 skills (SKILL.md) | ✅ | ✅ | ✅ | ✅ |
| AGENTS.md (always-loaded) | ✅ (via CLAUDE.md) | ✅ (via `.github/copilot-instructions.md` or workspace) | ✅ (via `.cursorrules` or auto-detect) | ❌ (skills only) |
| MCP server (`mcp.gaspatchio.dev`) | ✅ (via `.mcp.json`) | ✅ (via `.mcp.json`) | ✅ (via `.mcp.json`) | ❌ |
| Subagents | ✅ (via `agents/`) | ✅ (via `agents/`) | ❌ | ❌ |
| Hooks | ✅ (future) | ✅ (future) | ❌ | ❌ |

## Detailed Design

### 1. Plugin Manifests

#### Claude Code: `.claude-plugin/plugin.json`

```json
{
  "name": "gaspatchio",
  "version": "1.0.0",
  "description": "Actuarial modeling toolkit — skills for building, reconciling, and reviewing gaspatchio models",
  "author": {
    "name": "Gaspatchio",
    "url": "https://github.com/opioinc/gaspatchio-core"
  },
  "repository": "https://github.com/opioinc/gaspatchio-core",
  "license": "MIT",
  "keywords": ["actuarial", "modeling", "polars", "insurance", "projections"],
  "skills": "./skills/",
  "mcpServers": "./.mcp.json"
}
```

#### VS Code / Copilot: `.github/plugin.json`

```json
{
  "name": "gaspatchio",
  "version": "1.0.0",
  "description": "Actuarial modeling toolkit — skills for building, reconciling, and reviewing gaspatchio models",
  "author": {
    "name": "Gaspatchio",
    "email": "team@gaspatchio.dev"
  },
  "license": "MIT",
  "keywords": ["actuarial", "modeling", "polars", "insurance", "projections"],
  "skills": [
    "../../skills/quickstart",
    "../../skills/model-discovery",
    "../../skills/model-building",
    "../../skills/model-reconciliation",
    "../../skills/model-review",
    "../../skills/model-scenarios"
  ]
}
```

Note: VS Code `plugin.json` must reference skills relative to its location inside `.github/`. Paths like `../../skills/quickstart` resolve correctly.

#### Cursor: `.cursor-plugin/plugin.json`

```json
{
  "name": "gaspatchio",
  "version": "1.0.0",
  "description": "Actuarial modeling toolkit — skills for building, reconciling, and reviewing gaspatchio models",
  "skills": [
    "../skills/quickstart",
    "../skills/model-discovery",
    "../skills/model-building",
    "../skills/model-reconciliation",
    "../skills/model-review",
    "../skills/model-scenarios"
  ]
}
```

### 2. AGENTS.md

Always-loaded framework knowledge for any agent working in a gaspatchio project. Contains the broad API knowledge that Vercel's evals show is most effective as passive context (100% pass rate vs 53–79% for on-demand skills).

**Content scope** (what goes here, not in skills):

| Section | Content |
|---|---|
| **Framework overview** | What gaspatchio is, ActuarialFrame concept, Polars foundation |
| **API patterns** | Column rules (attribute notation, snake_case), operator conventions, `when/then/otherwise` |
| **CLI reference** | `gspio` commands, flags, `--output-file` workflow, `uv run` requirement |
| **Performance rules** | No `map_elements`, no Python loops, no `.collect()` during projection |
| **Common gotchas** | Top 5–8 most frequent mistakes (condensed from building skill's gotcha table) |
| **Skill routing** | When to use each of the 6 skills — brief descriptions pointing agents to the right skill |

**Content exclusions** (stays in skills):

| Content | Lives In |
|---|---|
| One-question-at-a-time discovery workflow | `model-discovery` skill |
| Three-phase build pattern, full gotcha table, reference files | `model-building` skill |
| Variable-by-variable reconciliation loop, diagnostic toolkit | `model-reconciliation` skill |
| ASOP-56 checklist, antipattern detection | `model-review` skill |
| Scenario configuration, shock system | `model-scenarios` skill |
| Install verification, first model walkthrough | `quickstart` skill |

**Size target**: Under 300 lines. The research shows context window pressure is real — top 1% of skills exceed 100K tokens. AGENTS.md should be dense and actionable, not comprehensive. Skills handle depth.

**Multi-editor delivery**:

- Claude Code: Reference from `CLAUDE.md` (e.g., `@AGENTS.md`) or auto-detected at project root
- VS Code / Copilot: Also detected at project root, or referenced in `.github/copilot-instructions.md`
- Cursor: Auto-detected at project root, or referenced from `.cursorrules`

### 3. SKILL.md Frontmatter Updates

Current skills use minimal frontmatter (`name`, `description`). The Agent Skills spec supports additional fields. Update all 6 skills:

```yaml
---
name: model-building
description: >
  Use when writing or modifying gaspatchio actuarial model code —
  enforces ActuarialFrame idioms, mandatory doc lookup, three-phase
  build pattern, and performance rules.
allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob
---
```

Fields to add:

| Field | Value | Rationale |
|---|---|---|
| `allowed-tools` | `Bash(uv:*,gspio:*) Read Grep Glob` | Pre-approve safe tool patterns — `uv run gspio` is the primary CLI path |

Fields to NOT add (keep it simple for v1):

| Field | Why Not |
|---|---|
| `model` | Let the user's default model handle it |
| `effort` | Not needed — skills are instruction-heavy, not compute-heavy |
| `context: fork` | Not needed — skills don't modify shared state |
| `user-invocable` | Defaults to true, which is correct |

### 4. MCP Configuration (`.mcp.json`)

Optional enrichment pointing to the existing remote MCP server. Provides actuarial knowledge search and documentation lookup as active tools.

```json
{
  "mcpServers": {
    "gaspatchio-knowledge": {
      "url": "https://mcp.gaspatchio.dev/sse",
      "description": "Actuarial knowledge base and gaspatchio documentation search"
    }
  }
}
```

Note: Key must be `mcpServers` (not `servers`). VS Code silently fails on the wrong key.

This is optional — the plugin works without MCP. MCP adds `gspio docs` and `gspio knowledge` equivalent functionality as tools the agent can call directly, which is useful when the CLI is not installed or for remote/containerized environments.

### 5. Skill Sizing Review

The Agent Skills spec recommends SKILL.md under 500 lines. Current state:

| Skill | Lines | Status |
|---|---|---|
| `quickstart` | 147 | ✅ Well under limit |
| `model-discovery` | 250 | ✅ Under limit |
| `model-building` | 260 | ✅ Under limit (references handle depth) |
| `model-review` | 205 | ✅ Under limit |
| `model-scenarios` | 327 | ✅ Under limit |
| `model-reconciliation` | 475 | ⚠️ Close to limit — review for trimming |

**Action**: Review `model-reconciliation` for content that can move to reference files. The diagnostic toolkit technique selection table and tolerance tiers are good candidates — they're reference material, not core workflow instructions.

### 6. `npx skills add` Compatibility

The `npx skills add` command (maintained by Vercel) installs skills from a repo's `skills/` directory. Gaspatchio's existing layout is already compatible:

- Skills live at `skills/<name>/SKILL.md` ✅
- Each skill directory contains its own references ✅
- SKILL.md has YAML frontmatter with `name` and `description` ✅

**The no-npm constraint revisited**: The original design dropped `npx skills add` because "users are actuaries, often behind corporate firewalls" and "no npm/npx." However:

- `npx skills add` is a **one-time install command**, not a runtime dependency
- It copies SKILL.md files locally — no ongoing npm dependency
- It's the **universal install path** used by Stripe, Cloudflare, HashiCorp, Pulumi, dbt
- Users behind firewalls who can't run `npx` can still use native editor install or clone the repo directly

**Decision**: Support `npx skills add gaspatchio/gaspatchio-core` as the universal path. Document it alongside native editor install. Do not require npm in the project itself.

## Distribution & Installation

### User Installation Paths

| Scenario | Command / Action |
|---|---|
| **Claude Code** (preferred) | `/plugin marketplace add opioinc/gaspatchio-core` |
| **VS Code / Copilot** | Search `@agentPlugins gaspatchio` or add marketplace in settings |
| **Cursor** | Open the repo; `.cursor-plugin/` auto-detected |
| **Any agent** (universal) | `npx skills add gaspatchio/gaspatchio-core` |
| **Firewalled** (no npm, no marketplace) | Clone the repo; editors auto-detect plugin directories |
| **Team setup** (VS Code) | Add to `.vscode/settings.json` with `extraKnownMarketplaces` |

### Marketplace Submission

#### Claude Code: `anthropics/claude-plugins-official`

Submit the plugin to Anthropic's official curated marketplace (14.6K stars, 90+ plugins). Process: PR to the `anthropics/claude-plugins-official` repository adding gaspatchio to the plugin catalog.

After submission, users install with:
```
/plugin install gaspatchio@claude-plugins-official
```

#### VS Code / Copilot: `github/awesome-copilot`

Submit to the default Copilot marketplace (175+ agents, 208+ skills, 48+ plugins). Process: PR to `github/awesome-copilot`.

#### Self-hosted Marketplace (Fallback)

If official marketplace acceptance is delayed, gaspatchio-core itself can serve as a marketplace. Users point directly at the repo:

- Claude Code: `/plugin marketplace add opioinc/gaspatchio-core`
- VS Code: Add `"opioinc/gaspatchio-core"` to `chat.plugins.marketplaces` in user settings

This works immediately — no approval process needed.

### First-Run Experience

**Dropped: `gspio setup-ai` command.** The original design included a CLI command that prints install instructions per editor. This is unnecessary because:

- Claude Code has `/plugin install` and `/plugin marketplace add`
- VS Code has `@agentPlugins` search and settings-based marketplace
- Cursor auto-detects `.cursor-plugin/` when the repo is opened
- `npx skills add` is the universal fallback

The install instructions belong in the README and documentation, not in a CLI command.

**Dropped: First-run nudge.** The `~/.gaspatchio/.setup_ai_prompted` touch-file mechanism is unnecessary. Users who install the plugin already know about it. Users who don't install it won't see CLI hints.

## Security Posture

Gaspatchio skills are first-party, domain-specific, and low-risk:

| Risk Factor | Status |
|---|---|
| Code execution | Skills contain instructions only — no executable code. `gspio` CLI is the execution layer, already installed by the user. |
| Network access | No network calls from skills. Optional MCP server is remote and read-only (knowledge search). |
| File system writes | Skills instruct agents to write model files, which is the explicit purpose. No hidden writes. |
| Prompt injection | First-party skills — no third-party content injection risk. Reference files are static markdown. |
| Dependency hijack | No dependencies. Skills are markdown files. |
| Persistence | Skills are read-only once installed. No state mutation across sessions. |

**Recommendation**: Add a brief security note to the README: "Gaspatchio skills contain instructions and reference material only. They do not execute code, access the network, or modify system state. All model execution runs through the `gspio` CLI."

## What's Explicitly Out of Scope (Phase 4)

| Item | Reason |
|---|---|
| `gspio setup-ai` CLI command | Replaced by native editor install paths |
| First-run nudge / touch file | Unnecessary with plugin discovery |
| Chat Participant VS Code extension (`@gaspatchio`) | Only needed for custom UI / runtime logic — not yet justified |
| Local MCP server | Remote `mcp.gaspatchio.dev` already exists; local adds complexity without value |
| Tool registry / `tools list` / `tools describe` | 6 commands don't need introspection infrastructure |
| `gaspatchio.tool.json` canonical schema | Maintenance overhead without clear benefit |
| Python entry points for `gaspatchio.skills` | No third-party plugin ecosystem to support |
| Versioning contracts / `schema_version` | Git commits are the version history; co-versioned with framework |
| `agents/` directory with subagents | Deferred — skills are sufficient for v1; add subagents when specific use cases emerge |

## Success Criteria

Phase 4 is complete when:

1. All three plugin manifests exist and are valid (Claude Code, VS Code, Cursor)
2. `AGENTS.md` exists with core framework knowledge, under 300 lines
3. `.mcp.json` points to `mcp.gaspatchio.dev`
4. `npx skills add gaspatchio/gaspatchio-core` successfully installs all 6 skills
5. Plugin installs and works in Claude Code via `/plugin marketplace add`
6. Plugin installs and works in VS Code via `@agentPlugins` search (preview feature)
7. Plugin auto-detected by Cursor when repo is opened
8. `model-reconciliation` SKILL.md is under 500 lines (trimmed if needed)
9. All 6 skills have updated frontmatter with `allowed-tools`
10. PR submitted to `anthropics/claude-plugins-official`
11. PR submitted to `github/awesome-copilot`
12. README updated with installation instructions for all paths

## Open Questions

1. **AGENTS.md vs CLAUDE.md overlap**: The existing `CLAUDE.md` already contains framework knowledge. Should `AGENTS.md` replace relevant sections of `CLAUDE.md`, or should they coexist with `CLAUDE.md` referencing `AGENTS.md`? Recommendation: `CLAUDE.md` focuses on contributor development workflow (build commands, test commands, code standards), `AGENTS.md` focuses on framework usage knowledge (API patterns, CLI reference, gotchas).

2. **Marketplace org name**: Is the GitHub org `opioinc` or should it be `gaspatchio`? The marketplace URL depends on this.

3. **VS Code plugin.json relative paths**: The `.github/plugin.json` needs `../../skills/` relative paths to reach the root `skills/` directory. This is correct per the spec but should be validated with the actual VS Code plugin loader.

4. **MCP server availability**: Is `mcp.gaspatchio.dev/sse` currently operational and maintained? If not, skip `.mcp.json` for v1 or point to a health-check endpoint.

## Related Documents

- `ref/30-llm-helpers/2026-03-23-llm-helpers-design.md` — original 4-phase design (Phase 4 outline at lines 148–173)
- `ref/30-llm-helpers/analysis.md` — critical analysis of CLI skills article
- `ref/30-llm-helpers/skill-development-notes.md` — 19 observations from tutorial work
- `ref/30-llm-helpers/specs/2026-03-25-phase-3-skills-design.md` — Phase 3 skills spec
- Agent Skills specification: https://agentskills.io/specification
- Claude Code plugin docs: https://code.claude.com/docs/en/plugins
- VS Code Agent Plugins: https://code.visualstudio.com/docs/copilot/customization/agent-plugins
- Vercel AGENTS.md eval: https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals
