# Phase 4: Plugin Packaging & Distribution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Distribute gaspatchio's 6 actuarial modeling skills as first-class plugins across Claude Code, VS Code / Copilot, and Cursor, with always-loaded framework knowledge via AGENTS.md.

**Architecture:** Three editor-specific manifests (`.claude-plugin/`, `.cursor-plugin/`, `.github/plugin.json`) point to the existing shared `skills/` directory. An `AGENTS.md` provides always-loaded framework knowledge. An `.mcp.json` optionally connects to the remote knowledge server. All content is static markdown — no runtime code.

**Tech Stack:** JSON (manifests), Markdown (AGENTS.md, SKILL.md updates), YAML (frontmatter)

**Spec:** `ref/30-llm-helpers/specs/2026-03-26-phase-4-plugin-packaging-design.md`

---

## File Map

| Action | File | Purpose |
|---|---|---|
| Create | `.claude-plugin/plugin.json` | Claude Code plugin manifest |
| Create | `.cursor-plugin/plugin.json` | Cursor plugin manifest |
| Create | `.github/plugin.json` | VS Code / Copilot plugin manifest |
| Create | `AGENTS.md` | Always-loaded framework knowledge (<300 lines) |
| Create | `.mcp.json` | Optional remote MCP server config |
| Modify | `skills/quickstart/SKILL.md` | Add `allowed-tools` frontmatter |
| Modify | `skills/model-discovery/SKILL.md` | Add `allowed-tools` frontmatter |
| Modify | `skills/model-building/SKILL.md` | Add `allowed-tools` frontmatter |
| Modify | `skills/model-reconciliation/SKILL.md` | Add `allowed-tools` frontmatter + trim to <500 lines |
| Modify | `skills/model-review/SKILL.md` | Add `allowed-tools` frontmatter |
| Modify | `skills/model-scenarios/SKILL.md` | Add `allowed-tools` frontmatter |

---

### Task 1: Create Claude Code plugin manifest

**Files:**
- Create: `.claude-plugin/plugin.json`

- [ ] **Step 1: Create the manifest file**

```bash
mkdir -p ~/projects/gaspatchio/gaspatchio-core/.claude-plugin
```

Write `.claude-plugin/plugin.json`:

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

- [ ] **Step 2: Validate the JSON is well-formed**

Run: `python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "feat(plugin): add Claude Code plugin manifest"
```

---

### Task 2: Create VS Code / Copilot plugin manifest

**Files:**
- Create: `.github/plugin.json`

Note: `.github/workflows/` already exists. The `plugin.json` coexists alongside it.

- [ ] **Step 1: Create the manifest file**

Write `.github/plugin.json`:

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

The `../../skills/` paths are relative to `.github/plugin.json`'s location — two levels up to reach the repo root.

- [ ] **Step 2: Validate the JSON is well-formed**

Run: `python3 -c "import json; json.load(open('.github/plugin.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify paths resolve correctly**

Run: `python3 -c "from pathlib import Path; base = Path('.github'); [print('OK' if (base / p).resolve().exists() else f'MISSING: {p}') for p in ['../../skills/quickstart', '../../skills/model-discovery', '../../skills/model-building', '../../skills/model-reconciliation', '../../skills/model-review', '../../skills/model-scenarios']]"`
Expected: 6 lines of `OK`

- [ ] **Step 4: Commit**

```bash
git add .github/plugin.json
git commit -m "feat(plugin): add VS Code / Copilot plugin manifest"
```

---

### Task 3: Create Cursor plugin manifest

**Files:**
- Create: `.cursor-plugin/plugin.json`

- [ ] **Step 1: Create the manifest file**

```bash
mkdir -p ~/projects/gaspatchio/gaspatchio-core/.cursor-plugin
```

Write `.cursor-plugin/plugin.json`:

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

The `../skills/` paths are relative to `.cursor-plugin/plugin.json` — one level up to reach the repo root.

- [ ] **Step 2: Validate the JSON is well-formed**

Run: `python3 -c "import json; json.load(open('.cursor-plugin/plugin.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify paths resolve correctly**

Run: `python3 -c "from pathlib import Path; base = Path('.cursor-plugin'); [print('OK' if (base / p).resolve().exists() else f'MISSING: {p}') for p in ['../skills/quickstart', '../skills/model-discovery', '../skills/model-building', '../skills/model-reconciliation', '../skills/model-review', '../skills/model-scenarios']]"`
Expected: 6 lines of `OK`

- [ ] **Step 4: Commit**

```bash
git add .cursor-plugin/plugin.json
git commit -m "feat(plugin): add Cursor plugin manifest"
```

---

### Task 4: Create MCP server configuration

**Files:**
- Create: `.mcp.json`

- [ ] **Step 1: Create the MCP config file**

Write `.mcp.json` at repo root:

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

Critical: The top-level key MUST be `mcpServers` (not `servers`). VS Code silently fails on the wrong key.

- [ ] **Step 2: Validate the JSON is well-formed**

Run: `python3 -c "import json; d = json.load(open('.mcp.json')); assert 'mcpServers' in d, 'Wrong key — must be mcpServers'; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .mcp.json
git commit -m "feat(plugin): add MCP server configuration for gaspatchio knowledge base"
```

---

### Task 5: Create AGENTS.md

**Files:**
- Create: `AGENTS.md`

This is the highest-value deliverable. Always-loaded framework knowledge that every agent gets automatically. Must be under 300 lines, dense and actionable.

Content sources to distill from:
- `bindings/python/project.md` — API philosophy, patterns, architecture
- `skills/model-building/SKILL.md` — gotcha table (condense top 8)
- `core/project.md` — Polars plugin guidelines, performance rules

- [ ] **Step 1: Write AGENTS.md**

Write `AGENTS.md` at repo root. The content below is the complete file — adapt wording as needed but preserve the structure and all technical details:

```markdown
# Gaspatchio — Agent Knowledge Base

Gaspatchio is a high-performance actuarial modeling framework. Python API + Rust core (Polars). Designed for actuaries — code should read like formulas, not data plumbing.

## Core Concept: ActuarialFrame

`ActuarialFrame` wraps Polars DataFrames with actuarial operations. Two column types:

- **Scalar columns**: one value per policy (age, sum_assured, premium)
- **List columns**: one vector per policy (monthly projections — mortality rates, cashflows, reserves)

```python
from gaspatchio_core import ActuarialFrame, when

af = ActuarialFrame(data)          # Wrap a dict, DataFrame, or parquet path
af.claims = af.sum_assured * af.pols_death  # Formula IS the code
result = af.collect()              # Execute lazily-built computation
```

## API Patterns

**Simple math → operators directly:**
```python
af.net_cf = af.premiums - af.claims - af.expenses - af.commissions
```

**Complex operations → named domain methods:**
```python
af.survival = af.combined_decrement.projection.cumulative_survival()
af.pols_prev = af.pols_if.projection.previous_period()
af.disc_mth = af.disc_ann.finance.to_monthly(method="compound")
```

**Business logic → when/then/otherwise (like Excel IF):**
```python
af.pols_maturity = when(af.month == af.policy_term * 12).then(af.surviving).otherwise(0.0)
```

**Column access:**
- Preferred: `af.mortality_rate` (attribute notation, snake_case)
- When needed: `af["Policy Number"]` (bracket for spaces/reserved words)
- Never: `af._private` (underscore prefix raises error)

## Assumption Tables

```python
from gaspatchio_core.assumptions import Table, TableBuilder

mort = Table(name="mortality", source=mort_df, dimensions={"age": "age"}, value="rate")
af.qx = mort.lookup(age=af.attained_age)
```

- `Table.lookup()` is **exact-match only** (not interpolating) — generate full-range tables
- Dimensions map model point columns to table columns
- `MeltDimension` for pivoted tables, `TableBuilder` for complex setups

## CLI Reference

Always use `uv run` — system Python does not have gaspatchio installed.

```bash
# Run full model
uv run gspio run-model model.py data.parquet

# Debug single policy (policy ID is POSITIONAL, not a flag)
uv run gspio run-single-policy model.py data.parquet "POL001"

# Save output as parquet (agent workflow — do NOT parse stdout)
uv run gspio run-single-policy model.py data.parquet "POL001" --output-file /tmp/result.parquet

# Inspect data structure
uv run gspio describe data.parquet --json

# Look up API methods (MANDATORY before using any method)
uv run gspio docs "cumulative_survival"

# Search actuarial knowledge base
uv run gspio knowledge "CSM calculation" -T IFRS17
```

**Agent workflow**: Always use `--output-file` to save results as parquet. Read with `gspio describe --json` or inline Polars. Never parse stdout.

## Performance Rules (Non-Negotiable)

| Never | Why |
|-------|-----|
| `map_elements` | ~14x slower; defeats vectorization |
| `for row in ...` / Python loops over policies | Breaks performance entirely |
| `.collect()` during projection phase | Breaks lazy execution — only in Phase 1 setup |
| `print()` in production code | Use `loguru` logger |

## Top Gotchas

1. **`when().then(scalar).otherwise(list_col)`** — crashes. Both branches must be same type (list or scalar).
2. **`projection_end_value=99`** — off-by-one truncates final year; use 100 for max age 100.
3. **`python3` instead of `uv run python3`** — `ModuleNotFoundError`. Always `uv run`.
4. **Policy ID is positional** — `gspio run-single-policy model.py data.parquet POL001`, NOT `--policy-id POL001`.
5. **Guessing method signatures** — agents get it wrong ~70% of the time. Run `gspio docs` first.
6. **`(1 + rate) ** af.month`** — TypeError for scalar^list. Use `(af.month * math.log(1 + rate)).exp()`.
7. **Boolean masking `value * (condition)`** — works but unreadable. Prefer `when/then/otherwise` for audit.
8. **Linter strips unused imports** — add import AND usage in a single edit, or ruff removes the import.

## Model Structure

Three phases, always in this order:

1. **Setup** (scalar ops, `.collect()` OK): Load model points, alias columns, load assumption tables
2. **Timeline** (`create_projection_timeline`): Build month/duration/age vectors. Set `projection_end_value` carefully.
3. **Calculations** (lazy — NO `.collect()`): Lookups, decrements, cashflows, PVs. All vectorized.

## Skill Routing

Use the right skill for your task:

| Task | Skill |
|------|-------|
| New to gaspatchio, first setup | `gaspatchio-quickstart` |
| Specifying a new model before coding | `gaspatchio-model-discovery` |
| Writing or editing model code | `gaspatchio-model-building` |
| Matching numbers to Excel/lifelib/vendor | `gaspatchio-model-reconciliation` |
| Reviewing model quality or compliance | `gaspatchio-model-review` |
| Stress testing, sensitivity, scenarios | `gaspatchio-model-scenarios` |

## Tutorial

Progressive tutorial in `tutorial/` — start from the level closest to your target:

- **Level 1** — Hello World: ActuarialFrame, column arithmetic, projections
- **Level 2** — Assumptions: Table, lookup, MeltDimension, select mortality
- **Level 3** — Full projection: mini-VA model, cumulative_survival, when/then, PV
- **Level 4** — Lifelib port: 860-line model reconciled to 0.0000% against lifelib
- **Level 5** — Scenarios: with_scenarios, parameter shocks, sensitivity analysis
```

- [ ] **Step 2: Verify line count is under 300**

Run: `wc -l AGENTS.md`
Expected: Under 300 lines

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "feat(plugin): add AGENTS.md with always-loaded framework knowledge"
```

---

### Task 6: Update SKILL.md frontmatter for all 6 skills

**Files:**
- Modify: `skills/quickstart/SKILL.md`
- Modify: `skills/model-discovery/SKILL.md`
- Modify: `skills/model-building/SKILL.md`
- Modify: `skills/model-reconciliation/SKILL.md`
- Modify: `skills/model-review/SKILL.md`
- Modify: `skills/model-scenarios/SKILL.md`

Add `allowed-tools` to the YAML frontmatter of each skill. This pre-approves safe tool patterns so the agent doesn't prompt the user for every `uv run gspio` call.

- [ ] **Step 1: Update quickstart frontmatter**

In `skills/quickstart/SKILL.md`, change the frontmatter from:

```yaml
---
name: gaspatchio-quickstart
description: Use when user is new to gaspatchio, setting up for the first time, or wants to get started quickly with actuarial modeling
---
```

To:

```yaml
---
name: gaspatchio-quickstart
description: Use when user is new to gaspatchio, setting up for the first time, or wants to get started quickly with actuarial modeling
allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob
---
```

- [ ] **Step 2: Update model-discovery frontmatter**

In `skills/model-discovery/SKILL.md`, add `allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob` as the third line of frontmatter (after `description`).

- [ ] **Step 3: Update model-building frontmatter**

In `skills/model-building/SKILL.md`, add `allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob` as the third line of frontmatter (after `description`).

- [ ] **Step 4: Update model-reconciliation frontmatter**

In `skills/model-reconciliation/SKILL.md`, add `allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob` as the third line of frontmatter (after `description`).

- [ ] **Step 5: Update model-review frontmatter**

In `skills/model-review/SKILL.md`, add `allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob` as the third line of frontmatter (after `description`).

- [ ] **Step 6: Update model-scenarios frontmatter**

In `skills/model-scenarios/SKILL.md`, add `allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob` as the third line of frontmatter (after `description`).

- [ ] **Step 7: Verify all 6 skills have the new field**

Run: `grep -l "allowed-tools" skills/*/SKILL.md | wc -l`
Expected: `6`

- [ ] **Step 8: Commit**

```bash
git add skills/*/SKILL.md
git commit -m "feat(plugin): add allowed-tools frontmatter to all 6 skills"
```

---

### Task 7: Trim model-reconciliation SKILL.md to under 500 lines

**Files:**
- Modify: `skills/model-reconciliation/SKILL.md`
- Create: `skills/model-reconciliation/references/tolerance-tiers.md` (if content moved)

The reconciliation skill is 475 lines — close to the 500-line SKILL.md limit. Move reference-quality content to `references/` to bring it comfortably under.

- [ ] **Step 1: Read the current file and identify movable sections**

Read `skills/model-reconciliation/SKILL.md` and identify sections that are reference material (lookup tables, templates) rather than core workflow instructions. Candidates:
- The build log template (the large markdown code block starting with "### Report structure")
- The tolerance tiers table
- The diagnostic technique selection table

- [ ] **Step 2: Move the build log template to a reference file**

If the build log template section (from `### Report structure (copy/paste template)` through the closing triple-backtick) is more than 40 lines, extract it to `skills/model-reconciliation/references/build-log-template.md` and replace the section in SKILL.md with:

```markdown
### Report structure

Use the template in [references/build-log-template.md](references/build-log-template.md). Copy it into your model directory as `model_build.md` and update it continuously as you reconcile.
```

- [ ] **Step 3: Verify line count is comfortably under 500**

Run: `wc -l skills/model-reconciliation/SKILL.md`
Expected: Under 450 lines (leave headroom)

- [ ] **Step 4: Verify references are intact**

Run: `ls skills/model-reconciliation/references/`
Expected: Should list the 8 existing technique files plus any newly extracted files.

- [ ] **Step 5: Commit**

```bash
git add skills/model-reconciliation/
git commit -m "refactor(skills): extract build log template to reference file, trim reconciliation under 500 lines"
```

---

### Task 8: Update README with installation instructions

**Files:**
- Modify: `bindings/python/project.md` (the Python project.md that contains development instructions)

Add an "AI Plugin Installation" section. This is the user-facing documentation for all install paths.

- [ ] **Step 1: Read the current project.md**

Read `bindings/python/project.md` to find the right insertion point. Add the new section after the "Related Repositories" section (line ~309) and before "High-Level Architecture".

- [ ] **Step 2: Add installation section**

Insert after the "Related Repositories" section:

```markdown
## AI Plugin Installation

Gaspatchio ships as a plugin for AI coding agents. Install once to get 6 actuarial modeling skills and always-loaded framework knowledge.

### Claude Code (recommended)
```
/plugin marketplace add opioinc/gaspatchio-core
```

### VS Code / GitHub Copilot
Search `@agentPlugins gaspatchio` in VS Code, or add to user settings:
```json
{
  "chat.plugins.marketplaces": ["opioinc/gaspatchio-core"]
}
```
Requires `"chat.plugins.enabled": true` (Agent Plugins is in preview).

### Cursor
Open any gaspatchio project — the `.cursor-plugin/` directory is auto-detected.

### Any Agent (universal)
```bash
npx skills add gaspatchio/gaspatchio-core
```

### Firewalled / Offline
Clone the repo. Editors auto-detect plugin directories when the project is opened.

### What You Get
- **6 skills**: quickstart, model-discovery, model-building, model-reconciliation, model-review, model-scenarios
- **AGENTS.md**: Always-loaded framework knowledge (API patterns, CLI reference, gotchas)
- **MCP integration**: Optional connection to gaspatchio knowledge base at `mcp.gaspatchio.dev`
```

- [ ] **Step 3: Commit**

```bash
git add bindings/python/project.md
git commit -m "docs: add AI plugin installation instructions to project.md"
```

---

### Task 9: Validate end-to-end plugin structure

This task verifies the complete plugin structure is correct and all files are in place.

**Files:** (read-only validation, no modifications)

- [ ] **Step 1: Verify all plugin files exist**

Run:
```bash
python3 -c "
from pathlib import Path
files = [
    '.claude-plugin/plugin.json',
    '.cursor-plugin/plugin.json',
    '.github/plugin.json',
    'AGENTS.md',
    '.mcp.json',
]
for f in files:
    p = Path(f)
    status = 'OK' if p.exists() else 'MISSING'
    print(f'{status}: {f}')
"
```
Expected: All 5 files show `OK`

- [ ] **Step 2: Validate all JSON files parse correctly**

Run:
```bash
python3 -c "
import json
from pathlib import Path
for f in ['.claude-plugin/plugin.json', '.cursor-plugin/plugin.json', '.github/plugin.json', '.mcp.json']:
    try:
        json.load(open(f))
        print(f'OK: {f}')
    except Exception as e:
        print(f'FAIL: {f} — {e}')
"
```
Expected: All 4 files show `OK`

- [ ] **Step 3: Verify all skill paths from manifests resolve**

Run:
```bash
python3 -c "
import json
from pathlib import Path

# Claude Code — uses directory path
cc = json.load(open('.claude-plugin/plugin.json'))
skills_dir = Path('.claude-plugin') / cc['skills']
count = len(list(skills_dir.resolve().glob('*/SKILL.md')))
print(f'Claude Code: {count} skills found')

# VS Code — uses explicit paths
vs = json.load(open('.github/plugin.json'))
for p in vs['skills']:
    resolved = (Path('.github') / p / 'SKILL.md').resolve()
    status = 'OK' if resolved.exists() else 'MISSING'
    print(f'VS Code {Path(p).name}: {status}')

# Cursor — uses explicit paths
cur = json.load(open('.cursor-plugin/plugin.json'))
for p in cur['skills']:
    resolved = (Path('.cursor-plugin') / p / 'SKILL.md').resolve()
    status = 'OK' if resolved.exists() else 'MISSING'
    print(f'Cursor {Path(p).name}: {status}')
"
```
Expected: `Claude Code: 6 skills found` and all skill paths show `OK`

- [ ] **Step 4: Verify AGENTS.md is under 300 lines**

Run: `wc -l AGENTS.md`
Expected: Under 300

- [ ] **Step 5: Verify all skills have allowed-tools frontmatter**

Run: `grep -c "allowed-tools" skills/*/SKILL.md`
Expected: Each file shows `1`

- [ ] **Step 6: Verify .mcp.json uses correct key**

Run: `python3 -c "import json; d = json.load(open('.mcp.json')); assert 'mcpServers' in d; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Verify model-reconciliation is under 500 lines**

Run: `wc -l skills/model-reconciliation/SKILL.md`
Expected: Under 500

- [ ] **Step 8: Final commit (if any fixups needed)**

If any validation steps revealed issues that were fixed:

```bash
git add -A
git commit -m "fix(plugin): address validation issues in plugin structure"
```

If all validations passed with no changes, skip this step.
