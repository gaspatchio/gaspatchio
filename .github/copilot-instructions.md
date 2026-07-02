<!-- GENERATED from AGENTS.md by scripts/gen_skill_manifests.py. Do not edit. -->

# Gaspatchio Framework Knowledge

High-performance actuarial modeling framework: Python API backed by Rust/Polars. The formula IS the code.

---

## Core Concept: ActuarialFrame

An `ActuarialFrame` wraps a Polars DataFrame. Columns are either **scalar** (one value per policy) or **list** (one value per projection period). Arithmetic between scalar and list columns broadcasts automatically.

```python
from gaspatchio_core import ActuarialFrame, when
af = ActuarialFrame(polars_dataframe)
af.claims = af.sum_assured * af.pols_death        # scalar * list -> list (auto-broadcast)
af.net_cf = af.premiums - af.claims - af.expenses  # list - list - list -> list
```

---

## API Patterns

**Simple math -- use operators directly.** The formula is the code. No wrapper methods needed.
```python
af.pols_death = af.pols_if * af.mort_rate_mth
af.pols_lapse = (af.pols_if - af.pols_death) * af.lapse_rate_mth
```

**Complex operations -- use named methods with domain namespaces.**
```python
af.survival = af.combined_decrement.projection.cumulative_survival()
af.reserve_prev = af.reserve.projection.previous_period()
af.rate_next = af.interest_rate.projection.next_period()
af.reserve_t2 = af.reserve.projection.at_period(-2)   # t-2 (negative=prior, positive=future)
af.disc_rate_mth = af.disc_rate_ann.finance.to_monthly(method="compound")
```

**Conditionals -- `when/then/otherwise` (mirrors Excel IF).**
```python
af.pols_maturity = when(af.month == af.policy_term * 12).then(af.surviving_at_t).otherwise(0.0)
af.commissions = when(af.duration == 0).then(af.premiums).otherwise(0.0)
```

**Column access rules:**
- Prefer attribute notation: `af.mortality_rate` (not `af["mortality_rate"]`)
- Use brackets when name has spaces or is a Python keyword: `af["Policy Number"]`, `af["class"]`
- No underscore-prefixed names: `af._flag` raises an error
- Use snake_case for calculated columns; alias raw input columns first

---

## Assumption Tables

```python
from gaspatchio_core.assumptions import Table, TableBuilder
import polars as pl

df = pl.read_parquet("assumptions/mortality.parquet")
mort = Table(name="mortality", source=df, dimensions={"age": "age", "duration": "duration"}, value="rate")
af.mort_rate = mort.lookup(age=af.attained_age, duration=af.duration)
```

**Key facts:**
- `lookup()` is exact-match only -- keys must exist in the table
- `dimensions` dict maps **your name** -> **source column name**
- `TableBuilder` for complex/programmatic table construction
- Dimension types: `DataDimension` (default), `MeltDimension` (wide-to-long), `CategoricalDimension`, `ComputedDimension`
- Overflow strategies: `ExtendOverflow`, `FillForward`, `FillConstant`, `LinearInterpolate`
- Always analyze files first: `uv run gspio describe assumptions/mortality.parquet`
- Always verify API: `uv run gspio docs "Table.lookup"`

---

## CLI Reference

**All commands require `uv run`.** The system Python does not have gaspatchio or polars.

```bash
# Run full model
uv run gspio run-model model.py data.parquet

# Run single policy -- policy ID is POSITIONAL, not a flag
uv run gspio run-single-policy model.py data.parquet 123

# Save output for analysis (agent workflow: always do this)
uv run gspio run-single-policy model.py data.parquet 123 --output-file /tmp/result.parquet

# Specify policy ID column name (separate flag)
uv run gspio run-single-policy model.py data.parquet 123 --policy-id-column "Policy number"

# Look up API docs before using any method
uv run gspio docs "cumulative_survival"
uv run gspio docs "Table.lookup" -n 20

# Look up actuarial concepts
uv run gspio knowledge "CSM calculation" -T IFRS17

# Describe data files
uv run gspio describe assumptions/mortality.parquet
```

**Agent workflow:** Always use `--output-file` to save results as parquet. Read parquet with `gspio describe --json` or inline Polars. Do NOT parse stdout.

---

## Performance Rules (Non-Negotiable)

| Never | Why |
|-------|-----|
| `map_elements` or `apply` | ~14x slower; defeats vectorization |
| `for row in ...` / Python loops over policies | Breaks performance entirely |
| `.collect()` during projection phase | Breaks lazy execution (only OK in Phase 1 setup) |
| `print()` in production code | Use loguru logger instead |

Let Polars handle parallelization. Never add Rayon or threading inside plugins.

---

## Top Gotchas

| # | Gotcha | What Goes Wrong |
|---|--------|-----------------|
| 1 | Arithmetic-masking blends in conditional code | Old workaround for a fixed limitation -- `when/then/otherwise` now handles mixed scalar/list branches |
| 2 | `projection_end_value=99` | Truncates final year; use 100 (off-by-one is catastrophic, ~3% BEL gap) |
| 3 | `python3` instead of `uv run python3` | `ModuleNotFoundError: No module named 'polars'` |
| 4 | `--policy-id` flag | Policy ID is positional. `--policy-id-column` is a different thing |
| 5 | Hand-rolled exp/log identity for `scalar ** list` | `**` works directly on list columns now -- write it as the operator |
| 6 | Guessing method signatures | Agents get it wrong ~70% of the time -- `gspio docs` first |
| 7 | `proj_year` vs `year` confusion | Stress scenarios silently wrong -- mass lapse never fires |
| 8 | Column name case mismatch | Polars is case-sensitive; check `df.columns` first |

---

## Model Structure: Three Phases

```python
from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.assumptions import Table
import polars as pl, datetime

def load_assumptions():
    df = pl.read_parquet("assumptions/mortality.parquet")
    return {"mortality": Table(name="mortality", source=df, dimensions={"age": "age"}, value="rate")}

def main(af: ActuarialFrame, params=None) -> ActuarialFrame:
    tables = load_assumptions()

    # --- PHASE 1: Setup (scalar ops, .collect() OK here) ---
    mp = af.collect()
    mp = mp.with_columns(pl.col("Issue Age").alias("issue_age"))
    af = ActuarialFrame(mp)

    # --- PHASE 2: Projection timeline ---
    af = af.date.create_projection_timeline(
        valuation_date=datetime.date(2025, 1, 1),
        projection_end_type="maximum_age",
        projection_end_value=100,   # NOT 99
        projection_frequency="monthly",
    )

    # --- PHASE 3: Calculations (lazy -- NO .collect() from here) ---
    af.mort_rate = tables["mortality"].lookup(age=af.age)
    af.survival = af.mort_rate.projection.cumulative_survival()
    return af
```

Phase 1: Load data, rename columns, join enrichment data. `.collect()` is OK.
Phase 2: Create projection timeline. Sets up time dimension (list columns).
Phase 3: All calculations. Lazy only -- no `.collect()`, no Python loops.

---

## Skill Routing

| Task | Skill |
|------|-------|
| New to gaspatchio, first setup | `quickstart` |
| Scope a new model before writing code | `model-discovery` |
| Write or modify model code | `model-building` |
| Review model quality / actuarial standards | `model-review` |
| Match model to Excel/lifelib/vendor reference | `model-reconciliation` |
| Scenarios, shocks, sensitivity analysis | `model-scenarios` |

Skills are in the `skills/` directory. Each has a `SKILL.md` with full instructions.

---

## Tutorial Levels

| Level | Name | Teaches |
|-------|------|---------|
| 1 | Hello World | ActuarialFrame, column arithmetic, when/then, .collect() |
| 2 | Assumptions | Table.lookup(), dimensions, when/then on list columns |
| 3 | Mini Variable Annuity | Full VA projection: mortality, lapse, AV, claims, discounting (6 incremental steps) |
| 4 | Reconciled Lifelib | Production model reconciled to 0.0000% against lifelib across 1,016 model points |
| 5 | Scenarios | Deterministic scenarios, parameter shocks, sensitivity sweeps, regulatory reports |

Tutorial models are in `tutorial/`. Start at Level 1 if new, Level 3 base for a complete VA model to study.

---

## Before You Write Code

1. Look up the method: `uv run gspio docs "<method>"`
2. Analyze data files: `uv run gspio describe <file>.parquet`
3. Build incrementally -- one section at a time, validate with `run-single-policy` after each
4. Do NOT guess method signatures. Do NOT assume you know how a method works.

---

## Extending Gaspatchio

To add custom calculations or accessor methods, use the `extending-gaspatchio` skill.
Do not write raw Python loops or `map_elements` — compose Polars expressions.
The accessor pattern (`@register_accessor` + base classes) is the primary extension mechanism.

**Performance ladder:** Before writing anything, determine if the calculation is a setup utility (Python function), a reusable column operation (column accessor), a frame-level operation (frame accessor), or a Rust kernel contribution. The skill walks through the decision tree.

**Anti-patterns:** `map_elements`, Python for-loops over policies, dict lookups per row — all cause 50-1000x slowdowns. The skill documents 7 concrete anti-patterns with correct alternatives.

---

# Contributing to gaspatchio-core

> The sections above describe how to **use** gaspatchio to build models.
> The sections below are for **developing** gaspatchio-core itself.

## Development rules (where they live)

Rules live next to the code they govern; every agent auto-loads the nearest file when it
edits in that subtree. A Claude Code session started at the repo root loads all of them
at once via `CLAUDE.md`.

- **Rust** core crate — [`core/AGENTS.md`](core/AGENTS.md)
- **Python** bindings + API — [`bindings/python/AGENTS.md`](bindings/python/AGENTS.md)

## Commit conventions

- **Sign your commits.** This repository requires signed commits — configure SSH or GPG
  signing and enable `git config commit.gpgsign true`.
- Use **conventional commit** format (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`) and
  explain the "why", not just the "what". Keep commits focused and atomic.
- Reference issue numbers (e.g. `GSP-NNN`) when applicable.
- **Never** add an AI-assistant signature or `Co-Authored-By: <assistant>` trailer to commit
  messages.

## Build & test

```bash
# Install workspace dependencies
uv sync

# Build the Rust extension after Rust changes
cd bindings/python && maturin build -uv

# Rust tests / benchmarks
cd core && cargo test
cd core && cargo bench

# Python tests (incl. docstring validation)
cd bindings/python && uv run pytest -v
cd bindings/python && uv run pytest --doctest-modules --doctest-glob="*.pyi"
```

## Documentation Audience

Gaspatchio documentation targets two audiences:

1. **Actuaries** — They know the products and actuarial concepts. They need to see their workflow in the code.
2. **LLMs** — They need complete examples with realistic actuarial data so they can generate correct code.

Every documentation section should follow: **business problem** → **Gaspatchio solution** → **code example**. Lead with the actuarial problem being solved, not the computer science architecture. Skip internal implementation details (Rust kernels, Struct columns, kwargs serialization) unless directly relevant to how the user calls the API.

## Design Documents and Plans

Design specs and implementation plans live in `ref/<topic>/` alongside the relevant reference material. The `ref/` directory uses numbered prefixes (e.g., `ref/30-llm-helpers/`).

- **Specs**: `ref/<topic>/specs/YYYY-MM-DD-<name>-design.md`
- **Plans**: `ref/<topic>/plans/YYYY-MM-DD-<name>.md`

When using Superpowers skills (brainstorming, writing-plans), save output to the relevant `ref/` subdirectory. If unsure which `ref/` folder applies, ask the user. Do NOT use `docs/superpowers/` — that directory does not exist in this project.

Current active topic: `ref/30-llm-helpers/` (LLM skills, tutorial, CLI improvements).
