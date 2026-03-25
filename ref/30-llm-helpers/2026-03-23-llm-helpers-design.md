# LLM Helpers: Onboarding Skills & CLI Improvements

**Date**: 2026-03-23
**Branch**: `gsp-llm-helpers`
**Epic**: Help users go from zero to minimum value using an LLM-first approach

## Goal

An actuary opens Claude Code, Cursor, or VS Code Copilot in a gaspatchio project and — within 30 minutes — has a running actuarial model. The LLM guides them through data inspection, assumption setup, and model building using gaspatchio's skills and CLI.

## Constraints

- Users are actuaries, often behind corporate firewalls
- Available toolchain: Python, uv, Claude Code, Cursor, VS Code Copilot
- No npm/npx — delivery must be Python-native or git-based
- Skills must auto-update independently of gaspatchio-core runtime releases

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Skills repo location | Same repo (`gaspatchio-core`), extract later if needed | Simpler to maintain; plugin install points at git main, already decoupled from PyPI releases |
| Plugin directory | Repo root (repo IS the plugin) | Simplest path for `marketplace add` — just point at the repo |
| Delivery mechanism | Claude Code plugin + Copilot plugin (primary), Cursor file copy (fallback), `--local` flag for firewalled environments | Auto-updates via plugin system; local copy as escape hatch |
| Target editors | Claude Code (GA), VS Code Copilot (preview), Cursor | All three; same SKILL.md format works for Claude Code and Copilot |
| Approach | CLI-first, then skills, then marketplace (Approach B) | Polish the product before the shopfront |
| Quick-start persona | Actuary who knows Excel, new to Python/gaspatchio, with escape hatches for experienced Python users | Most gaspatchio users will be Excel-native actuaries |
| Example models | Progressive tutorial with on-ramps at every level, includes lifelib port and scenarios | Tutorial-style; users can start at any level |
| First-run nudge | One-time welcome message on first `gspio` invocation, set flag so it never repeats | Respectful of user time; like git's first-run hint |
| `gspio setup-ai` behaviour | Print plugin install commands (preferred), copy locally for Cursor, `--local` flag copies everything for firewalled environments | Plugin auto-update is the point; local copy is fallback |
| Editor detection | Don't detect — print all instructions, copy Cursor files unconditionally | Filesystem markers unreliable; just do everything |
| Distribution format | Native plugin systems (Claude Code, Copilot), not Vercel Skills (`npx skills add`) | Vercel Skills requires npm/npx which violates the no-npm constraint; native plugins also auto-update |

## Architecture

```
gaspatchio-core/                        (repo root IS the plugin)
├── .claude-plugin/
│   └── plugin.json                     Claude Code manifest
├── plugin.json                         Copilot manifest
├── skills/
│   ├── quickstart/
│   │   └── SKILL.md
│   ├── discovery/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── building/
│   │   ├── SKILL.md
│   │   └── references/
│   └── reconciliation/
│       ├── SKILL.md
│       └── references/
├── tutorial/
│   ├── level-1-hello-world/
│   │   ├── base/                       runnable starting point
│   │   └── steps/                      guided additions to reach level 2
│   ├── level-2-assumptions/
│   ├── level-3-projection/
│   ├── level-4-lifelib/
│   └── level-5-scenarios/
├── core/                               existing Rust core
├── bindings/python/                    existing Python bindings
└── ...
```

## Phasing

### Phase 1: CLI Improvements

Improve the CLI so skills have solid tooling to reference. Each item below is a focused working session.

**`gspio describe --json`:**
- Structured JSON output with schema, sample rows, detected dimensions, suggested Table code
- Currently outputs Rich-formatted text via `console.print()` — needs a parallel JSON code path with a `DescribeResponse` Pydantic model
- Human-readable output stays as default; `--json` is the LLM path

**`gspio run-single-policy` and `gspio run-model` — no `--json` flag needed:**
- The existing `--output-file results.parquet` flag is the agent path — DataFrames belong in parquet, not JSON (preserves schema, types, is Polars-native)
- Agent workflow: run with `--output-file`, then inspect the parquet with `gspio describe --json` or inline Polars
- Review whether stdout summary (status, timing, output path) could be improved, but no new response model needed

- `docs` and `knowledge` already output JSON via `model_dump_json()` — no changes needed
- `calc-graph` already outputs JSON to file — no changes needed

**~~`--dry-run`~~ — DROPPED:**
- All gaspatchio commands are idempotent — running the model doesn't mutate anything
- Running the model IS the validation; if it fails you get the error, if it works you get the result
- `--dry-run` was solving a problem that doesn't exist

**~~`gspio setup-ai`~~ — MOVED TO PHASE 4:**
- Depends on the plugin structure which doesn't exist until Phase 4
- Building it now with placeholders adds no value; build it when there's something real to install

**~~First-run nudge~~ — MOVED TO PHASE 4:**
- Coupled to `setup-ai`; ships together
- "Verify install" in the quick-start skill means running `gspio --version` and checking for a non-error exit code — no separate health-check command needed

### Phase 2: Example Model Curation

Build a progressive tutorial where each level builds on the previous, with on-ramps at every level. Each item below is a focused working session.

**Audit existing models:**
- Review `gaspatchio-models` models
- Review `tests/scratch/models/` in core
- Identify candidates for each tutorial level
- Audit is complete when each of the 5 tutorial levels has at least one candidate model identified, or is flagged as needing to be written from scratch

**Tutorial levels:**

| Level | Name | What it teaches | Base to next |
|---|---|---|---|
| 1 | Hello world | ActuarialFrame, column arithmetic, `.collect()` | Add an assumption table |
| 2 | Assumptions | Table, lookup, MeltDimension, fill_series | Add decrements + projection methods |
| 3 | Full projection | cumulative_survival, when/then/otherwise, PV | Port from lifelib |
| 4 | Lifelib port | Reconciliation against a known model, matching numbers | Add stress scenarios |
| 5 | Scenarios | with_scenarios, parameter shocks, sensitivity analysis | — |

**Each level ships as:**
- `tutorial/level-N-name/base/` — runnable model + data (the on-ramp)
- `tutorial/level-N-name/steps/` — guided steps showing what to add/change
- Users can start at any level's base without completing previous levels

Note: directory is named `tutorial/` not `examples/` to avoid collision with Rust's `examples/` convention for example binaries.

### Phase 3: Skills

Build skills that leverage the improved CLI and tutorial examples. Each item below is a focused working session.

**New quick-start skill:**
- Target: actuary who knows Excel, new to Python/gaspatchio (escape hatches for experienced Python users)
- Flow: verify install, inspect data with `gspio describe --json`, copy Level 1 base, run it, experiment, guide to Level 2
- References `gspio setup-ai` if invoked outside a skill context

**Refresh existing skills:**
- **Discovery**: reference tutorial levels, use `gspio describe --json` output, point at lifelib level when porting
- **Building**: reference tutorial progression, mandate `gspio docs` lookups, include explicit instructions to use `--output-file` for model results (agent reads parquet for validation, not stdout)
- **Reconciliation**: reference Level 4 (lifelib port) as canonical example, use `--output-file` parquet outputs for machine-readable diffs

**All skills must include `--output-file` as the standard agent workflow:**
- Skills should instruct agents to always use `gspio run-single-policy model.py data.parquet POL001 --output-file /tmp/result.parquet` rather than parsing stdout
- This ensures agents work with native parquet (typed, schema-preserved) rather than text parsing
- Starting point is the three existing skills in `ref/30-llm-helpers/skills/` — refreshed, not rewritten. Skills migrate from `ref/30-llm-helpers/skills/` to `skills/` at repo root, with reference subdirectories reorganised into each skill's `references/` directory

**Skill format:**
- SKILL.md with YAML frontmatter (works for both Claude Code and Copilot plugins)
- Supporting files in subdirectories (reference docs, technique guides)

### Phase 4: Plugin Packaging & Marketplace

Package everything for distribution. Each item below is a focused working session.

**Plugin structure:**
- `.claude-plugin/plugin.json` at repo root (Claude Code)
- `plugin.json` at repo root (Copilot)
- Both reference the same `skills/` directory

**`gspio setup-ai` command (moved from Phase 1):**
- New Typer subcommand
- Claude Code: print `/plugin marketplace add gaspatchio/gaspatchio-core`
- Copilot: print `chat.plugins.marketplaces` setting instruction
- Cursor: copy rules into `.cursor/rules/gaspatchio/` in current project
- `--local` flag: skip plugin instructions, copy all files locally for all editors
- Sets first-run flag via touch file at `~/.gaspatchio/.setup_ai_prompted`

**First-run nudge (moved from Phase 1):**
- On any `gspio` invocation, if `~/.gaspatchio/.setup_ai_prompted` does not exist, print to stderr:
  `hint: AI-assisted model building available. Run 'gspio setup-ai' to set up Claude Code, Copilot, or Cursor integration.`
- Create the flag file so it never shows again

**Marketplace submissions:**
- Claude Code: submit to official Anthropic marketplace
- Copilot: add to `github/awesome-copilot` community collection
- Both point at the same repo, same skills

## Cross-Phase Dependencies

- **Phase 3 requires Phase 1** (`describe --json`) and **Phase 2** (tutorial levels 1-3 minimum) to be complete before skills can be fully authored
- **Phase 4 requires Phase 3** — skills must be tested and polished before marketplace submission; `setup-ai` and first-run nudge ship here alongside plugin packaging
- **Phases 1 and 2 are independent** — can run in parallel or in either order

## Known Risks

- **Copilot plugin system is preview (not GA).** If the plugin format changes before Phase 4, the Copilot manifest may need to adapt. Claude Code plugins are GA and stable. Mitigation: design for both but publish Claude Code first; add Copilot when format stabilises.
- **Marketplace acceptance is not guaranteed.** Both Claude Code (Anthropic) and Copilot (`awesome-copilot`) have review processes. Mitigation: self-host via git repo as fallback — users can always `marketplace add` pointing directly at the repo.
- **`--dry-run` partial execution may not capture all computed columns.** If the model generates columns dynamically (e.g., in loops), partial execution may miss them. Mitigation: return what column tracking metadata captures and document the limitation.

## What's Explicitly Out of Scope

- Tool registry / `tools list` / `tools describe` introspection commands
- `gaspatchio.tool.json` canonical schema
- Local MCP server from shared registry
- `gemini-extension.json` or host-specific manifests
- Python entry points for `gaspatchio.skills` group
- Versioning contracts (`schema_version`, `skill_version`)
- Any npm/npx-based distribution

## Source Material

- `ref/30-llm-helpers/packaging-cli-skills-for-llm-agents.pdf` — ChatGPT research article
- `ref/30-llm-helpers/analysis.md` — critical analysis and red-teaming of the article
- `ref/30-llm-helpers/skills/` — existing skill drafts (discovery, building, reconciliation)
- Claude Code plugin docs: https://code.claude.com/docs/en/plugins.md
- VS Code Copilot plugin docs: https://code.visualstudio.com/docs/copilot/customization/agent-plugins
