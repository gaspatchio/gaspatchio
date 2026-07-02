# Shipping gaspatchio as Plugins for Claude Code, Cursor, and GitHub Copilot

gaspatchio-core already authors 7 Agent Skills plus always-loaded `AGENTS.md` framework knowledge, driven by a single SSOT (`skills/skills.toml`) that fans out to three per-tool `plugin.json` manifests. This document consolidates four platform source-of-truth (SOT) scans and one inventory of what we ship today, to seed a brainstorm on turning that into properly *installable* plugins across the major coding agents. The short version: the **skill content is portable and largely ready**, but the **distribution/registration layer is missing** — no `marketplace.json` exists anywhere, so the headline install paths advertised in `AGENTS.md` are not actually backed by a registration file.

## Readiness verdict

| Platform | Verdict | One-line reason |
|----------|---------|-----------------|
| **Claude Code** | **Mostly** | Skills are shaped exactly right and `.claude-plugin/plugin.json` is valid, but no `.claude-plugin/marketplace.json` exists, so `/plugin marketplace add opioinc/gaspatchio-core` cannot resolve; AGENTS.md is also not loaded by the plugin path. |
| **Cursor** | **Mostly** | SKILL.md and nested AGENTS.md are consumed natively as-is, but `.cursor-plugin/plugin.json` uses non-schema `../skills/...` parent-traversal paths and there is no `.cursor-plugin/marketplace.json` for team import. |
| **GitHub Copilot** | **Gaps** | Skills live at repo-root `skills/`, which Copilot does **not** auto-discover; no `.github/skills/` tree, no `.github/copilot-instructions.md`, and the manifest sits at the undocumented `.github/plugin.json` location. |
| **Universal Skills / AGENTS.md** | **Mostly** | SKILL.md + AGENTS.md genuinely port, but frontmatter `name` (`gaspatchio-quickstart`) ≠ parent dir (`quickstart`) violates the open-spec hard rule, and the `npx skills add gaspatchio/gaspatchio-core` slug uses the wrong org. |

## The portability thesis

The entire packaging strategy rests on **one source, many targets**: a single tree of `skills/<name>/SKILL.md` folders (plus `references/`) and a layered `AGENTS.md` (root + nested `core/` and `bindings/python/`), generated/guarded from `skills/skills.toml` as the SSOT. The research confirms this model is real and increasingly standardized — but it is important to be precise about **what ports unchanged** versus **what must be re-expressed or generated per tool**.

**Ports unchanged across tools (the high-leverage surface):**
- **`skills/<name>/SKILL.md`** in the open Agent Skills format (governed at agentskills.io, spec at github.com/agentskills/agentskills). The *identical* file is consumed by Claude Code, Cursor ("implements the Agent Skills specification and uses the identical SKILL.md format"), Copilot/VS Code, Codex, and 70+ agents. Progressive disclosure (name+description always in context; body on activation; `references/*.md` on demand) works everywhere.
- **`AGENTS.md`** as the always-loaded "README for agents" — read natively by 30+ tools (Cursor root+nested with child-overrides-parent precedence, Copilot nearest-in-tree, Codex, Gemini CLI, etc.). Claude Code reads `CLAUDE.md` natively and the repo's `@AGENTS.md` shim is the correct pattern.
- The **"Skill Routing" table in AGENTS.md** is the bridge between the two layers: always-loaded context that tells the agent which on-demand skill to pull.

**Must be re-expressed or generated per tool (the bespoke wrapper layer):**
- **Plugin manifests** — `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `.github/plugin.json` (or `.github/plugin/plugin.json`). Each has its own schema, key set, and default discovery semantics (Claude `skills` ADDS to default scan; Cursor/Copilot a manifest path REPLACES folder discovery).
- **Marketplace/registration files** — `.claude-plugin/marketplace.json`, `.cursor-plugin/marketplace.json`, `.github/plugin/marketplace.json`. These are what actually make a plugin *installable* and are entirely absent today.
- **Discovery locations** — Copilot scans `.github/skills/` / `.claude/skills/` / `.agents/skills/` but **not** bare `skills/`; the emerging tool-neutral convention is `.agents/skills/`.
- **Install/auth mechanics** — `/plugin install`, Cursor "Import from Repo", `chat.plugins.marketplaces`, `npx skills add`, MCP `cursor://` deeplinks — all per-tool.

The takeaway: gaspatchio's content layer is already portable; the gap is almost entirely in the per-tool wrapper + registration layer, which is exactly what an SSOT generator should own.

## Claude Code

**SOT packaging.** A plugin is a self-contained directory whose only required metadata file is `.claude-plugin/plugin.json` (sole required key: `name`, kebab-case). **Everything else lives at the plugin ROOT**, never inside `.claude-plugin/`: `skills/<name>/SKILL.md`, `agents/*.md`, `hooks/hooks.json`, `.mcp.json`, `.lsp.json`, `monitors/monitors.json`, `bin/`. Optional manifest keys include `displayName` (v2.1.143+), `version`, `description`, `author{name,email,url}`, `homepage`, `repository`, `license`, `keywords`, `defaultEnabled` (v2.1.154+), `$schema`, and component-path keys. Critically, `skills` **ADDS** to the default `skills/` scan, whereas `commands`/`agents` **REPLACE** their default dir. Distribution requires a separate **`.claude-plugin/marketplace.json`** (required keys: `name`, `owner{name}`, `plugins[]`), at the ROOT of the marketplace repo — which may be the same repo via `"source": "./"`.

**Distribution.** Users run `/plugin marketplace add owner/repo` then `/plugin install name@marketplace`. Plugins are copied to a versioned cache at `~/.claude/plugins/cache` (so no `../shared` references survive install). Versioning resolution: plugin.json `version` → marketplace-entry `version` → git commit SHA → "unknown"; pinning `version` means `/plugin update` is a **no-op until bumped**, so omitting `version` (SHA-driven) is recommended for active dev. `claude plugin validate --strict` is the CI gate.

**How our skills map.** The repo is **already shaped correctly**: 7 skills at `skills/<name>/SKILL.md` with progressive-disclosure `references/` (e.g. `model-building/references/{assumptions,conditionals-and-lists,model-phases,...}`), and `.claude-plugin/plugin.json` correctly uses `"skills": "./skills/"` so all 7 are discovered. The same SKILL.md dirs also work standalone in `~/.claude/skills/` (invoke `/quickstart`) or in-plugin (`/gaspatchio:quickstart`).

**Our gaps:**
- **No `marketplace.json` anywhere.** The 4 `plugin.json` files make gaspatchio a valid plugin but nothing makes it installable; `/plugin marketplace add opioinc/gaspatchio-core` will fail until `.claude-plugin/marketplace.json` exists at that repo root (or an entry lands in `anthropics/claude-plugins-official`).
- **AGENTS.md is not loaded by the plugin path.** Plugins contribute context through skills/agents/hooks, **not** `CLAUDE.md`/`AGENTS.md`. Users who install the plugin get the 7 skills but **not** the "always-loaded framework knowledge" AGENTS.md advertises. That knowledge must be repackaged as a skill (e.g. a `user-invocable: false` reference skill) to actually ship.
- **`version: "1.0.0"` is pinned** in all three manifests with no documented bump/release process — even once a marketplace exists, new skill content won't reach users until the version is bumped.
- **No `$schema`** (json.schemastore.org/claude-code-plugin-manifest.json) for editor validation, and `--strict` is not run in CI to catch foreign/misspelled fields or non-kebab names.
- **Cosmetic name skew:** frontmatter `name: gaspatchio-quickstart` is a display label only; invocation is `gaspatchio:quickstart` (dir + namespace), so the frontmatter `name` is redundant/misleading.
- **Unused surfaces that fit our workflow:** no `hooks/` (a `PreToolUse` guard could deterministically enforce the AGENTS.md "non-negotiable" rules against `map_elements`/`.collect()` in projection phase), no `agents/` (a model-review or reconciliation subagent), no `.mcp.json` (the gaspatchio-mix RAG/MCP server could ship bundled). The plugin is skills-only.
- **No `category`/`tags`/`relevance`** for marketplace discovery; marketplace `name` must avoid reserved names and be kebab-case.

## Cursor

**SOT packaging.** Cursor (2.5+/3.x) has converged hard on the Claude Code / Agent Skills model — it is the closest non-Anthropic agent to our existing packaging. Four context mechanisms coexist: `.cursor/rules/*.mdc` (frontmatter `description`/`globs`/`alwaysApply`, four trigger types), native **AGENTS.md** (root + nested, auto-applied as an always-on rule, superseding deprecated `.cursorrules`), native **Agent Skills** (identical SKILL.md; also reads `.claude/skills/` and `.codex/skills/` for compat), and a first-class **Plugins** system behind `.cursor-plugin/plugin.json` (required key `name`; auto-discovery from `skills/`, `rules/`, `agents/`, `commands/`, `hooks/hooks.json`, `mcp.json` when the matching manifest key is omitted — and a manifest path REPLACES folder discovery). Multi-plugin repos add a root `.cursor-plugin/marketplace.json` (required `name`, `owner`, `plugins[]`, max 500).

**Distribution.** Five paths: public **Cursor Marketplace** (manually reviewed, one-click install from Customize), **Team/Enterprise marketplaces** via Dashboard → Plugins → Team Marketplaces → "Import from Repo" (GitHub App, optional auto-refresh on push — the realistic internal path), **local dev** via real copied dirs in `~/.cursor/plugins/local/` (symlinks are **not** loaded — known bug, cursor/plugins #35), **in-repo auto-detect** (open the repo → AGENTS.md + discovered SKILL.md load with zero install), and **MCP deeplinks** (`cursor://anysphere.cursor-deeplink/mcp/install?name=...&config=<base64>`).

**How our skills map.** 1:1 with **no rewrite**: the 7 SKILL.md files map directly onto Cursor skills provided they sit in a discovered location (a plugin `skills/` dir, `.cursor/skills/`, or — because Cursor reads it for compat — `.claude/skills/`). All three AGENTS.md (root + `core/` + `bindings/python/`) are read natively with child-overrides-parent precedence. Cursor's `/migrate-to-skills` confirms SKILL.md is the canonical primitive going forward (we don't need it).

**Our gaps:**
- **`.cursor-plugin/plugin.json` does not match Cursor's schema:** it uses a `skills` array of `../skills/quickstart` **parent-traversal** paths. Cursor expects auto-discovery from an in-plugin `skills/` dir or in-tree `skills` paths; parent-traversal arrays are undocumented and likely won't resolve. Fix: drop the `skills` key (rely on auto-discovery) or use in-tree paths, and place the manifest at a valid layout root.
- **Inconsistent metadata:** `.cursor-plugin/plugin.json` has no `author`/`license`/`repository` at all (thin manifest); license diverges across manifests (`MIT` in `.github` vs `Apache-2.0` in `.claude-plugin`).
- **No `.cursor-plugin/marketplace.json`** — required for "Import from Repo" team distribution and any future multi-plugin layout.
- **Zero `.cursor/rules/*.mdc`** — we rely entirely on AGENTS.md (which works) but forgo file-scoped `globs` rules (e.g. auto-attach Rust standards on `*.rs`, Python on `**/*.py`) that would precisely target the existing `core/` and `bindings/python/` AGENTS.md content.
- **Skills not in any Cursor-native discovery dir at repo root** (`.cursor/skills/`, `.agents/skills/`, or a valid plugin `skills/`). A `.claude/skills/` dir would make them load with zero Cursor-specific work since Cursor reads it for compat.
- **No `logo`/`assets/`** for a public-marketplace listing (minor).
- **Install docs incomplete:** AGENTS.md documents Claude `/plugin marketplace add` and `npx skills add` but not Cursor-native paths (open-repo auto-detect, `~/.cursor/plugins/local/` copy, Import-from-GitHub).

## GitHub Copilot

**SOT packaging.** Two converged layers, plus a third to avoid. (A) **Agent Skills** (open SKILL.md standard) are auto-discovered at three workspace roots: **`.github/skills/`**, **`.claude/skills/`**, **`.agents/skills/`** — consumed by the Copilot cloud agent, code review, CLI, and agent mode in VS Code/JetBrains/VS. Required frontmatter: `name` (lowercase-hyphen, ≤64, == folder), `description` (≤1024, written as a retrieval query). (B) **Agent Plugins** (VS Code 1.110+, preview behind `chat.plugins.enabled`) bundle skills+agents+hooks+MCP under a `plugin.json` (required `name`; `skills` defaults to `skills/`). VS Code auto-detects the manifest at, in order: `.plugin/plugin.json`, root `plugin.json`, **`.github/plugin/plugin.json`**, **`.claude-plugin/plugin.json`** — so our existing `.claude-plugin/plugin.json` with `skills: "./skills/"` is *already a Copilot-valid manifest* (detection #4). (C) **Copilot Extensions** (GitHub-App agents/skillsets in GitHub Marketplace) are for external-API integrations and require hosting/OAuth/review — the **wrong vehicle** for static framework knowledge. Always-on context: `.github/copilot-instructions.md`, path-scoped `*.instructions.md` with `applyTo` globs, and natively-read `AGENTS.md`.

**Distribution.** Three channels in increasing cost: (1) **repo auto-detection** (zero-install) — commit `.github/skills/<name>/SKILL.md` + `.github/copilot-instructions.md`/`AGENTS.md` and any user opening the repo or running cloud agent / code review / CLI picks them up; (2) **Agent Plugin marketplace** (preview) — add via `chat.plugins.marketplaces: ["opioinc/gaspatchio-core"]`, install via `@agentPlugins` filter or `copilot plugin install`; (3) **Copilot Extensions** (GitHub App, avoid). Marketplace manifest: `.github/plugin/marketplace.json` (or `.claude-plugin/marketplace.json`).

**How our skills map.** The 7 SKILL.md files are spec-compatible **as-is**; they need a discoverable location and frontmatter validation. AGENTS.md is consumed natively (nearest-in-tree), so the Skill Routing table and API patterns load automatically. For repo-local use, the `.github/skills/` discovery path alone is the higher-leverage, lower-friction mechanism — no plugin manifest needed.

**Our gaps:**
- **Skills are invisible to Copilot.** They live at repo-root `skills/`, which Copilot does **not** scan. No `.github/skills/`, `.claude/skills/`, or `.agents/skills/` tree exists, so on cloud agent / code review / CLI / VS Code agent mode the skills don't load.
- **Manifest in the wrong/undocumented spot:** we ship `.github/plugin.json`, but the documented `.github` detection path is `.github/plugin/plugin.json`. Safer to rely on the already-detected `.claude-plugin/plugin.json`.
- **No `.github/copilot-instructions.md`** — github.com code-review and cloud-agent surfaces key off this file; AGENTS.md alone doesn't cover those surfaces.
- **No path-scoped `*.instructions.md`** with `applyTo` globs — the Rust (`core/AGENTS.md`) vs Python (`bindings/python/AGENTS.md`) split is expressed only via nested AGENTS.md, not via the mechanism github.com code-review honors per-path.
- **No `.github/plugin/marketplace.json`** (or `.claude-plugin/marketplace.json`) — the repo can't be added as a one-line Copilot marketplace.
- **The SSOT generator doesn't emit the `.github/skills/` tree** that Copilot's primary (manifest-less) mechanism actually requires.
- **`.github/plugin.json` carries `license: "MIT"`** (repo is Apache-2.0) and placeholder `author.email: team@gaspatchio.dev`.
- **No MCP wiring** (`.vscode/mcp.json` with root key `servers`, or repo-settings `mcpServers`) — a gap only if tool-calling is desired beyond the knowledge case.

## Universal Skills / AGENTS.md

**SOT packaging.** Two complementary open standards. **Agent Skills** (agentskills.io, spec at github.com/agentskills/agentskills): a skill folder is `SKILL.md` + optional `scripts/`/`references/`/`assets/`, three-tier progressive disclosure (~100 tokens at startup, body <5000 tokens / <500 lines on activation, files on demand). Frontmatter required keys: `name` (1-64, lowercase a-z/0-9/hyphens, no leading/trailing/consecutive hyphens, **MUST match parent directory exactly**) and `description` (1-1024, what + when). Optional: `license`, `compatibility` (≤500 chars, e.g. "Requires Python 3.14+ and uv"), `metadata` (string→string; `metadata.version` for per-skill versioning since the open spec has **no top-level `version`**), `allowed-tools` (experimental). **AGENTS.md** (agents.md, stewarded by the Agentic AI Foundation under the Linux Foundation) is the always-loaded layer read natively by 30+ tools.

**Distribution.** The open install path is **`npx skills add <owner/repo>`** (Vercel Labs CLI, github.com/vercel-labs/skills), which symlinks (or `--copy`) SKILL.md folders into each detected agent's dir (`.claude/skills/`, `.cursor/skills/`, `.agents/skills/`, `.codex/skills/`, etc.). Flags: `-s/--skill`, `-a/--agent`, `-g/--global`, `--list`, `--copy`. Auto-detects installed agents; public repo, no auth/review server. Validate with `skills-ref validate ./skills/<name>`. Most tools also auto-detect SKILL.md folders by walking the repo on open.

**How our skills map.** This is the **directly-portable surface** — gaspatchio already ships exactly `skills/<name>/SKILL.md` (7 skills, some with `references/`), and AGENTS.md is the complementary always-loaded layer with the Skill Routing table as the bridge.

**Our gaps:**
- **Frontmatter name ≠ directory (open-spec hard violation):** `name: gaspatchio-quickstart` vs dir `quickstart/`. Fails `skills-ref validate` and mis-loads under `npx skills`/Cursor/Codex. The `skills.toml` `order` list (unprefixed) also disagrees with the frontmatter (prefixed) — an internal SSOT inconsistency. Fix by renaming dirs to `gaspatchio-*/` or dropping the prefix from `name`.
- **Wrong `npx skills` slug:** AGENTS.md documents `npx skills add gaspatchio/gaspatchio-core`, but the repo is `opioinc/gaspatchio-core` — the universal install command is broken as written.
- **No open-format validation in CI:** we have a structural test + manifest generator but don't run `skills-ref validate` / the open-spec checker, so name/hyphen/description-length violations ship undetected.
- **Non-standard per-tool wrappers as dead weight:** `.cursor-plugin/plugin.json` and `.github/plugin.json` (array-of-paths form) are not the documented Cursor/Copilot consumption paths (those read bare SKILL.md folders); the wrappers can diverge from the SSOT.
- **Missing `compatibility` field:** skills hard-require `uv`+`gspio` but none declare it; the open spec has a 500-char `compatibility` key for exactly this.
- **No `metadata.version`** on individual skills (we version only the plugin).
- **No `.agents/skills/` convergence:** the emerging tool-neutral location (read by Cursor, Codex, OpenCode, and preferred by `npx skills`) is absent; we ship only `skills/` plus Claude-specific glue.
- **Manifest license/author disagreement** across wrappers (Apache-2.0 + url author vs MIT + email author) — a real correctness/legal gap.

## Where gaspatchio stands today

The inventory finding is that gaspatchio-core ships **one multi-agent "skills plugin"** with a genuinely solid SSOT+guard backbone, and the gaps are concentrated in distribution and metadata hygiene rather than skill quality.

**What we ship (and it's valid):**
- **`skills/skills.toml`** — the SSOT: a single `order = [...]` array of 7 skill dir names in routing order.
- **7 `skills/<name>/SKILL.md` + `references/`** — well-structured, valid Agent Skills (kebab-case, "Use when" descriptions, <600 lines, one-level-deep references, with enforced `## Integration` workflow-DAG, Red Flags / anti-rationalization, and Completion Gate sections). `model-building/references` (11 files), `model-reconciliation/references` (9), `model-review/references` (2), `extending-gaspatchio/references` (3); quickstart/model-discovery/model-scenarios have none.
- **`.claude-plugin/plugin.json`** — valid Claude manifest, correctly globs `"./skills/"` so new skills auto-discover; intentionally not listed in skills.toml (self-maintaining).
- **`scripts/gen_skill_manifests.py`** — generator/guard: reads skills.toml, rewrites the `skills` array in the two list manifests, `--check` mode for CI drift, wired into `CI.yml` alongside `pytest tests/skills/`. This machinery fixed a 2-month 6-of-7 Cursor/Copilot skill gap.
- **AGENTS.md** — always-loaded framework knowledge; its "What You Get: 7 skills" count+list is guarded against skills.toml (`test_agents_md_count_and_list_in_sync`), and the root "Skill Routing" table maps task→skill.

**What's bespoke / inconsistent / stale:**
- **`.cursor-plugin/plugin.json`** and **`.github/plugin.json`** are generated list-manifests; the Cursor one uses non-schema `../skills/...` paths and the auto-detection claims for both are asserted in AGENTS.md but not proven against current loader specs (possibly project-invented).
- **No `marketplace.json` of any kind** (confirmed absent) — the headline `/plugin marketplace add opioinc/gaspatchio-core` and the Cursor/Copilot install paths are not actually registered.
- **`.github/plugin.json` license="MIT"** (repo is Apache-2.0 — wrong/stale) and **`author.email="team@gaspatchio.dev"`** (placeholder); `.cursor-plugin/plugin.json` has no author/license at all.
- **`npx skills add gaspatchio/gaspatchio-core`** uses org `gaspatchio` while every other path uses `opioinc/` — inconsistent and likely non-functional.
- **Guard scope is narrow:** it only checks the `skills` array and the AGENTS.md count/list — **not** version bumps, license/author consistency, plugin.json schema validity, or marketplace existence, so drift in those fields ships silently.
- **Frontmatter `name` (gaspatchio-prefixed) is unlinked from the registry** (bare slug), so a rename of one wouldn't be caught.
- **No content-freshness gate:** per the ref/43 design, example-rot detection and effectiveness evals are deferred to the private docs repo — core today proves the files are well-*formed*, not that their embedded API examples still *run*.
- **Skills reach agents via the marketplace, not the wheel:** `skills/`, `scripts/`, `tests/`, `hooks/` live at repo root outside `bindings/python/`, so they're excluded from the maturin sdist/wheel.

## Gap analysis & prioritised recommendations

| # | Gap | Impact | Effort | Recommendation |
|---|-----|--------|--------|----------------|
| 1 | No `marketplace.json` anywhere | **Critical** — every advertised one-line install (`/plugin marketplace add`, Cursor import, Copilot marketplace) fails; the plugin is not installable | Low | Add `.claude-plugin/marketplace.json` at repo root with one entry (`"source": "./"`). Generate it from skills.toml. Decide Claude-only vs also `.cursor-plugin/`/`.github/plugin/` marketplace files. |
| 2 | Frontmatter `name` (`gaspatchio-quickstart`) ≠ dir (`quickstart`) | **High** — open-spec hard violation; fails `skills-ref validate`, mis-loads on Cursor/Codex/`npx skills`; SSOT (skills.toml) disagrees with frontmatter | Low | Pick one convention (drop prefix from `name`, or rename dirs to `gaspatchio-*/`). Add a guard that asserts `name == dirname`. |
| 3 | Skills not discoverable by Copilot (repo-root `skills/` not scanned) | **High** — Copilot users get zero skills on cloud agent / code review / CLI / VS Code | Low–Med | Generate a `.github/skills/` (or tool-neutral `.agents/skills/`) tree from skills.toml (symlink or copy); validate frontmatter against Copilot keys. |
| 4 | AGENTS.md not loaded by the Claude plugin path | **High** — "always-loaded framework knowledge" doesn't ship to plugin installers | Med | Repackage AGENTS.md framework knowledge as a `user-invocable: false` reference skill (or fold key parts into quickstart/model-building descriptions). |
| 5 | `version: "1.0.0"` pinned, no release process | **Medium** — even with a marketplace, content updates won't reach users until bumped | Low | Either omit `version` (SHA-driven updates) for active dev, or add a documented bump step to the generator/release flow. |
| 6 | License/author inconsistency (MIT vs Apache-2.0; placeholder email) | **Medium** — real correctness/legal gap; persists undetected | Low | Fold canonical `license`/`author`/`keywords` into the generator so all manifests carry one set; widen the guard to check them. |
| 7 | Cursor `plugin.json` uses non-schema `../skills/...` paths | **Medium** — likely won't resolve as a Cursor plugin | Low | Drop the `skills` key (auto-discovery) or use in-tree paths; align manifest to a valid layout; emit from generator. |
| 8 | Wrong `npx skills` org slug | **Medium** — universal install command is broken as written | Trivial | Fix to `opioinc/gaspatchio-core`; add a doc-string lint or test asserting the slug. |
| 9 | No `compatibility` / `metadata.version` on skills | **Low–Med** — skills hard-require `uv`+`gspio`; no per-skill versioning | Low | Add `compatibility: "Requires uv and gspio"` and `metadata.version` to each SKILL.md; emit from skills.toml. |
| 10 | Guard scope narrow; no `--strict`/`skills-ref validate` in CI | **Medium** — schema/name/license drift ships silently | Low–Med | Add `claude plugin validate --strict` + `skills-ref validate` + `npx skills add . --list` to CI; widen the guard. |
| 11 | No path-scoped Copilot `*.instructions.md` / `.github/copilot-instructions.md` | **Low–Med** — github.com surfaces (code review, cloud agent) miss repo-wide + per-path rules | Med | Add `.github/copilot-instructions.md`; consider `*.instructions.md` with `applyTo` globs for Rust vs Python. |
| 12 | Unused surfaces (hooks/agents/MCP) | **Low (high upside)** — performance "non-negotiables" not enforced deterministically; no bundled tooling | Med–High | Optional: a `PreToolUse` hook guarding `map_elements`/`.collect()`-in-projection; a model-review/reconciliation subagent; bundle the gaspatchio-mix RAG/MCP server. |

## Open questions for the brainstorm

1. **Single-repo plugin vs per-tool artifacts.** Keep one source tree + generated wrappers in gaspatchio-core, or split a dedicated marketplace repo? (Note Claude copies plugins to a versioned cache, so external `../shared` references break post-install.)
2. **Generate vs hand-author the wrapper layer.** Extend `gen_skill_manifests.py` to emit *all* manifests + `.github/skills/` tree + every `marketplace.json` from skills.toml, vs hand-maintaining a smaller, simpler set. How far does the SSOT's authority extend?
3. **Which platforms first?** Claude Code (closest to ready, just needs marketplace.json) → Cursor (native, needs manifest fix) → Copilot (most work: discovery tree + instructions). Do we ship Claude-only v1 and fast-follow, or land all three together?
4. **One tool-neutral skills location or per-tool trees?** Adopt `.agents/skills/` (read by Cursor/Codex/OpenCode/`npx skills`) as the canonical location, or keep `skills/` + generated per-tool copies? Does `.claude/skills/` (read by Cursor for compat) let us cover two birds?
5. **MCP server: ship one or not?** The gaspatchio-mix RAG/MCP and the `gspio` CLI exist but aren't exposed as MCP. Is tool-calling worth the cross-tool MCP config matrix (Claude `.mcp.json`, VS Code `servers`, coding-agent `mcpServers`, Cursor deeplinks), or do skills+instructions cover the knowledge case?
6. **Versioning policy.** Omit `version` (SHA-driven, zero-ceremony updates) vs pinned semver + per-skill `metadata.version` + a release/bump gate. What does our update cadence justify?
7. **Hosting/marketplace strategy.** Self-host (`marketplace.json` at our repo root) vs submit to `anthropics/claude-plugins-official` + the public Cursor Marketplace (manual review) + `github/awesome-copilot` (community PR). Public discovery vs internal team marketplaces (Cursor Import-from-Repo, `chat.plugins.marketplaces`)?
8. **Enforce performance rules via hooks?** Should the AGENTS.md "non-negotiable" rules (no `map_elements`, no `.collect()` in projection phase) become a deterministic `PreToolUse`/`agents` guard, and on which platform(s), given hook support varies?

## Sources

**Claude Code**
- https://code.claude.com/docs/en/plugins-reference
- https://code.claude.com/docs/en/plugin-marketplaces
- https://code.claude.com/docs/en/skills
- https://raw.githubusercontent.com/anthropics/claude-plugins-official/main/.claude-plugin/marketplace.json
- https://github.com/anthropics/claude-code/blob/main/plugins/README.md
- https://github.com/anthropics/claude-code/blob/main/.claude-plugin/marketplace.json
- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- https://agentskills.io

**Cursor**
- https://cursor.com/docs/context/rules
- https://cursor.com/docs/context/skills
- https://cursor.com/docs/context/mcp
- https://cursor.com/docs/context/mcp/install-links
- https://cursor.com/docs/plugins
- https://cursor.com/docs/reference/plugins
- https://github.com/cursor/plugins/blob/main/README.md
- https://github.com/cursor/plugins/issues/35
- https://cursor.com/marketplace

**GitHub Copilot**
- https://code.visualstudio.com/docs/agent-customization/agent-plugins
- https://code.visualstudio.com/docs/agent-customization/agent-skills
- https://code.visualstudio.com/docs/agent-customization/custom-instructions
- https://code.visualstudio.com/docs/agent-customization/mcp-servers
- https://docs.github.com/en/copilot/concepts/agents/about-agent-skills
- https://docs.github.com/en/copilot/concepts/agents
- https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot
- https://docs.github.com/copilot/customizing-copilot/using-model-context-protocol/extending-copilot-chat-with-mcp
- https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/configure-mcp-servers
- https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills
- https://www.kenmuse.com/blog/creating-agent-plugins-for-vs-code-and-copilot-cli/
- https://awesome-copilot.github.com/plugins/
- https://github.com/github/awesome-copilot

**Universal Skills / AGENTS.md**
- https://agentskills.io/home
- https://agentskills.io/specification
- https://github.com/anthropics/skills
- https://github.com/vercel-labs/skills
- https://agents.md/
- https://cursor.com/docs/context/skills
- https://www.npmjs.com/package/skills
- https://github.com/agentskills/agentskills
- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- https://code.claude.com/docs/en/skills

**Our current state (inventory)**
- ~/projects/gaspatchio/gaspatchio-core/.claude-plugin/plugin.json
- ~/projects/gaspatchio/gaspatchio-core/.cursor-plugin/plugin.json
- ~/projects/gaspatchio/gaspatchio-core/.github/plugin.json
- ~/projects/gaspatchio/gaspatchio-core/skills/skills.toml
- ~/projects/gaspatchio/gaspatchio-core/scripts/gen_skill_manifests.py
- ~/projects/gaspatchio/gaspatchio-core/tests/skills/test_skill_manifests.py
- ~/projects/gaspatchio/gaspatchio-core/tests/skills/test_skill_structure.py
- ~/projects/gaspatchio/gaspatchio-core/.github/workflows/CI.yml
- ~/projects/gaspatchio/gaspatchio-core/bindings/python/AGENTS.md
- ~/projects/gaspatchio/gaspatchio-core/ref/43-skill-lifecycle/specs/2026-06-15-skill-lifecycle-design.md
