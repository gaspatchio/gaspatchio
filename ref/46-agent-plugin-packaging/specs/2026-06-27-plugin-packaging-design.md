# gaspatchio Plugin Packaging — Design Spec

**Date:** 2026-06-27
**Status:** Design — approved in brainstorm; ready for writing-plans
**Topic:** `ref/46-agent-plugin-packaging`
**Research inputs:** [`../2026-06-27-plugin-packaging-research.md`](../2026-06-27-plugin-packaging-research.md), [`../2026-06-27-oss-bundling-field-scan.md`](../2026-06-27-oss-bundling-field-scan.md)

---

## Goal

Make the AI-plugin install paths gaspatchio **already advertises** actually work — self-hosted, across **Claude Code, Cursor, GitHub Copilot, and the universal `npx skills` path** — driven from a single source of truth (`skills/skills.toml`) so the per-tool wrapper/registration layer cannot drift.

The content layer (SKILL.md + AGENTS.md) is already portable; the gap is entirely the per-tool **wrapper + registration** layer. This spec makes the `skills.toml` SSOT own that layer end to end.

## Non-goals (v1)

- **External marketplace submission / review** — `anthropics/claude-plugins-official`, the public Cursor Marketplace (manual review), a `github/awesome-copilot` PR. (Fast-follow; we self-host `marketplace.json` at our repo root.)
- **MCP server, `hooks/`, `agents/` subagents, Cursor `.mdc` rules.** (Fast-follow.)
- **A dedicated router/overview skill.** Not warranted at 7 skills (field norm); routing stays in the `AGENTS.md` table + per-skill `description:` triggers.
- **Materialized `.agents/skills/` copies.** Only added if a verification gate proves a tool can't discover via the manifest pointer (see Gate 2). The default is **no copies**.

## Decisions (locked in brainstorm)

| # | Decision | Choice | Rationale / field evidence |
|---|----------|--------|----------------------------|
| 1 | Distribution goal | Make advertised installs work, **self-hosted** | Lowest-effort, highest-credibility; the advertised installs currently fail (no `marketplace.json`, wrong `npx` slug). |
| 2 | SSOT ownership | **Generate everything** from `skills.toml`; CI `--check` | Field: hand-edited manifests drift (`anthropics/skills`' `marketplace.json` has a stray comma; `awesome-copilot` CI rejects materialized skills on `main`). Our `gen_skill_manifests.py` already exists. |
| 3 | Skill naming | **Rename dirs `→ gaspatchio-*`** so `name == dir` | Open Agent Skills spec hard-requires `name == parent dir`; branded names are collision-safe in a flat standalone skills namespace. |
| 4 | Skill location | **One canonical `skills/` tree; per-tool manifests POINT at it** (`skills: "./skills/"`). No copies, no symlinks. | Field: `obra/superpowers` keeps one tree, each per-tool manifest points at it — zero duplicated SKILL.md. Windows-safe (no symlinks/copies). |
| 5 | Manifest footprint | **Minimal Claude core + thin per-tool manifests for advertised ecosystems** (Cursor, Copilot) | Field: Anthropic ships minimal (`{name,description,author}` + one `marketplace.json`); multi-tool repos add ~10-key sibling manifests only per targeted ecosystem. |
| 6 | Versioning | **Layered semver** — semver on the plugin/marketplace manifests, bumped by the generator; **no `version` in SKILL.md** | Field: a plugin's own manifest uses pinned semver wherever a release pipeline exists; SHA-pinning is only for *referencing external* repos; the SKILL.md spec has no `version` field. Semver **must** have an automated bumper (field caution). |
| 7 | Routing / knowledge | **No router skill**; routing via `AGENTS.md` table + sharp `description:`; generate `.github/copilot-instructions.md` | Field: majority of comparable repos ship no router at this scale; rely on always-loaded instructions + keyword-rich descriptions. |

## Architecture — the SSOT generator

```
skills/skills.toml                       ← SSOT: [plugin] metadata + semver + [skills].order
        │  scripts/gen_skill_manifests.py  (the ONLY writer of the wrapper layer)
        │  CI: gen_skill_manifests.py --check  (fails on any drift)
        ▼
skills/gaspatchio-*/SKILL.md             ← canonical, hand-authored (name == dir)
.claude-plugin/plugin.json               ← generated; points "skills": "./skills/"
.claude-plugin/marketplace.json          ← generated; self-host, source: "./"
.cursor-plugin/plugin.json               ← generated; thin; points at ./skills/
.github/plugin/marketplace.json          ← generated; Copilot
.github/copilot-instructions.md          ← generated from AGENTS.md
AGENTS.md (install section)              ← npx slug + per-tool install paths (guarded)
```

**Principle (field-grounded):** SKILL.md bodies are hand-authored; **everything else is generated and CI-guarded.** Never hand-edit a manifest.

### `skills.toml` schema (extended)

Today: `order = [...]`. Add a `[plugin]` table and rename the order entries to the branded dir names:

```toml
[plugin]
name         = "gaspatchio"
display_name = "Gaspatchio"
description  = "Actuarial modeling skills for gaspatchio (Python + Rust/Polars)."
version      = "1.0.0"                 # semver; the generator bumps this (see Versioning)
author_name  = "Opio Inc."
author_url   = "https://github.com/opioinc"
homepage     = "https://github.com/opioinc/gaspatchio-core"
repository   = "https://github.com/opioinc/gaspatchio-core"
license      = "Apache-2.0"            # the ONE canonical license — kills the MIT/Apache/none skew
keywords     = ["actuarial", "polars", "insurance", "ifrs17", "solvency-ii", "rust"]

[skills]
order = [
  "gaspatchio-quickstart",
  "gaspatchio-model-discovery",
  "gaspatchio-model-building",
  "gaspatchio-model-reconciliation",
  "gaspatchio-model-review",
  "gaspatchio-model-scenarios",
  "gaspatchio-extending",
]
```

### Generated artifacts (the fan-out)

| Artifact | Purpose | Makes-work-for |
|----------|---------|----------------|
| `.claude-plugin/plugin.json` | Claude plugin manifest (`$schema`, `version`, points `"skills": "./skills/"`) | `/plugin install` |
| `.claude-plugin/marketplace.json` | self-host, `source: "./"` | **`/plugin marketplace add opioinc/gaspatchio-core`** |
| `.cursor-plugin/plugin.json` | thin Cursor manifest pointing at `./skills/` (drop the current `../skills/...` parent-traversal) | Cursor plugin load (in-repo + import) |
| `.github/plugin/marketplace.json` | Copilot agent-plugin marketplace (note **nested** `plugin/`) | `chat.plugins.marketplaces: ["opioinc/gaspatchio-core"]` |
| `.github/copilot-instructions.md` | always-loaded Copilot context, derived from AGENTS.md | github.com code-review + cloud agent |
| `AGENTS.md` install block | correct `npx` slug + per-tool install steps | `npx skills add opioinc/gaspatchio-core` |

## Artifact specs

> Each manifest's **exact** key set is a post-cutoff fact — see **Verification Gates**. Shapes below are the best-known form from the field scan; confirm against current docs before generating.

### Skill dirs — rename to `gaspatchio-*`
- Rename the 7 dirs (`skills/quickstart/` → `skills/gaspatchio-quickstart/`, etc.). Frontmatter `name:` is already `gaspatchio-*`, so post-rename `name == dir`.
- Sweep references: `skills.toml order`, `AGENTS.md` "Skill Routing" table + "What You Get" list, skill→skill cross-references, the generator, and the structural tests.
- Intra-plugin path references use **`${CLAUDE_PLUGIN_ROOT}`**, never hardcoded/relative (field: mandated by the canonical `plugin-structure` skill). Component dirs must **not** live inside `.claude-plugin/`.
- **Accepted cosmetic consequence:** Claude's plugin invocation becomes `gaspatchio:gaspatchio-quickstart` (double-branded); skills are model-invoked by description, so this is cosmetic.

### `.claude-plugin/marketplace.json` (the keystone)
Best-known shape:
```json
{
  "name": "gaspatchio",
  "owner": { "name": "Opio Inc.", "url": "https://github.com/opioinc" },
  "plugins": [
    { "name": "gaspatchio", "source": "./", "description": "...", "version": "1.0.0" }
  ]
}
```
`source: "./"` = same-repo plugin. This is the single file that makes `/plugin marketplace add opioinc/gaspatchio-core` resolve.

### `.claude-plugin/plugin.json`
`{ $schema, name, version, description, author{name,url}, homepage, repository, license, keywords, "skills": "./skills/" }`. The `"./skills/"` glob auto-discovers all 7 (self-maintaining; new skills appear without editing the manifest).

### `.cursor-plugin/plugin.json`
Thin (~10 keys), points at `./skills/`. **Remove** the current non-schema `../skills/quickstart` parent-traversal array.

### `.github/plugin/marketplace.json` (+ `plugin.json` if required)
Move off the current undocumented `.github/plugin.json` to the documented **`.github/plugin/`** location. Exact schema per Gate 3.

### `.github/copilot-instructions.md`
Generated from the AGENTS.md framework knowledge + routing table. (Generated copy is acceptable duplication — it's generator-owned and `--check`-guarded; one file.)

## Versioning policy (layered semver)

- **Plugin/marketplace manifests** carry a single semver, sourced from `skills.toml [plugin].version`.
- **SKILL.md frontmatter carries no `version`** (spec-compliant; matches `anthropics/skills`). If a per-skill version is ever needed it goes under the freeform `metadata:` map, never a top-level key.
- **The bump is automated:** the generator (or a `--bump {patch,minor,major}` flag / release step) writes the new version into every manifest atomically. Field caution: *semver without an automated bumper is the worst of both worlds.*

## CI guards (extend `gen_skill_manifests.py --check`)

Widen the existing `--check` (today: only the `skills` array + the AGENTS.md count/list) to fail on drift in **all** generated artifacts, plus add:
- `frontmatter.name == dirname` for every skill.
- License / author / version consistency across every manifest.
- `marketplace.json` exists where the advertised install needs it.
- `npx` slug in AGENTS.md == `opioinc/gaspatchio-core`.
- **(pending Gate 4)** `claude plugin validate --strict` and the open-spec `skills-ref validate ./skills/<name>`.

## Verification gates — DO THESE FIRST in implementation

The research is post-knowledge-cutoff (mid-2026). Before generating any manifest, confirm each fact against live docs/tools; if a gate fails, adjust the artifact spec (cheap) rather than ship a guessed schema.

1. **Claude marketplace resolution.** Confirm the exact `.claude-plugin/marketplace.json` key set and that `/plugin marketplace add opioinc/gaspatchio-core` resolves a same-repo `source: "./"` plugin.
2. **In-place discovery (decides copies).** Confirm whether Cursor/Copilot **open-repo** discovery follows the per-tool manifest pointer (`skills: "./skills/"`) or requires skills physically at `.agents/skills/`. If the latter, the generator emits `.agents/skills/` **copies** (Windows-safe) — otherwise no copies (default).
3. **Cursor + Copilot manifest schemas.** Confirm `.cursor-plugin/plugin.json` and `.github/plugin/marketplace.json` (and whether a `.github/plugin/plugin.json` is also required) exact schemas.
4. **Validators exist.** Confirm `claude plugin validate --strict` and `skills-ref validate` are available for CI; if not, fall back to the structural test we already have.
5. **Copilot reads `.agents/skills` / distribution path.** Confirm Copilot's actual product-skill delivery (marketplace manifest vs location scan) so we back the right path.

## Out of scope / fast-follow

External marketplace submission; MCP server; `hooks/` perf-rule enforcement; `agents/` subagents; Cursor `.mdc` rules; `.agents/skills/` copies (only if Gate 2 requires); subset/sliced sub-bundles (the `anthropics/skills` 1-tree-3-plugins pattern) if we later want modeling-vs-review splits.

## Rollout order

1. **Verification gates** — confirm the post-cutoff schemas/behaviors above.
2. `skills.toml` `[plugin]` schema + semver.
3. Rename skill dirs `→ gaspatchio-*` + reference sweep + `name == dir` guard.
4. Extend `gen_skill_manifests.py` to emit every artifact (manifests, marketplaces, `copilot-instructions.md`); fold in canonical license/author/keywords + semver bump.
5. Run the generator; commit the generated files.
6. Widen CI `--check` + add validators (Gate 4).
7. Update the AGENTS.md install section (correct `npx` slug + per-tool steps).
8. **Verify each advertised install path** end-to-end (Claude marketplace add/install; `npx skills add … --copy` on a Windows check; Cursor import/open; Copilot marketplace).

## Spec self-review

- **Placeholder scan:** none. The "best-known shape" manifests are explicitly gated on verification, not TODOs.
- **Internal consistency:** decisions 4–7 are reflected consistently in Architecture, Artifact specs, Versioning, and Rollout. No `.agents/skills/` copies unless Gate 2 flips — stated the same way throughout.
- **Scope:** single subsystem (the packaging/wrapper layer). Out-of-scope list keeps v1 bounded.
- **Ambiguity:** the post-cutoff manifest internals are the only soft spots, and they are explicitly quarantined into Verification Gates that run first — by design, not omission.
