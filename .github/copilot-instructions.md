<!-- GENERATED from AGENTS.md by scripts/gen_skill_manifests.py. Do not edit. -->

# Gaspatchio Framework Knowledge

High-performance actuarial modeling framework: Python API backed by Rust/Polars. The formula IS the code.

---

## Principles — read these first

The north star. Full text: [`PRINCIPLES.md`](PRINCIPLES.md) · published at
<https://gaspatchio.dev/principles/>. These are positions, not selling points — the choices
made and the alternatives rejected. **Justify design decisions and bug-triage verdicts against
them by name.**

| Principle | In one line |
|-----------|-------------|
| **Meet you where you are** | Accept tables, formulas, and conventions in the shape the user already has. The framework reshapes itself to you, not the other way round. |
| **Closed-form by default** | Cumulative products, powers, linear recurrences — not recursive cell-graphs. Escalate to state-machine rollforward only when within-period charges depend on the running balance. |
| **Optimize for the laptop** | 100K policies in seconds on the machine on your desk. An edit-run-refine loop past a few seconds is a bug; drop a capability before loosening the loop. |
| **Audit by default** | Expression lineage on every output column; `source_sha()`/`fingerprint()` on every Schedule, Table, Curve, MortalityTable, and compiled rollforward. Auditable by construction, not by separate workflow. |
| **LLM-shaped from the inside out** | User + LLM is the design target, not a retrofit. Docs, error messages, and the `gspio docs`/`gspio knowledge` CLI retrieval surface all exist in that shape deliberately. |
| **Sharp knives, no magic** | Expose primitives, the user composes them, the composition is visible in plain Python. When the composition is wrong, **refuse to run** rather than silently fill in a fallback. |
| **No vendor lock-in** | Calculation in code, data in Polars/Parquet, model file in Python. The model moves with the user between employers, auditors, and regulators. |

**The tension you will hit most:** *Meet you where you are* pulls toward accepting whatever the
user wrote; *Sharp knives, no magic* pulls toward refusing anything ambiguous. The resolution:
**be liberal about the shapes you accept, be strict about the meanings you infer.** A clear error
naming the ambiguity and the fix beats both silently guessing and failing opaquely.

---

## Core Concept: ActuarialFrame

An `ActuarialFrame` wraps a Polars DataFrame. Columns are either **scalar** (one value per policy) or **list** (one value per projection period). Arithmetic between scalar and list columns broadcasts automatically.

```python
from gaspatchio import ActuarialFrame, when
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
from gaspatchio.assumptions import Table, TableBuilder
import polars as pl

df = pl.read_parquet("assumptions/mortality.parquet")
mort = Table(name="mortality", source=df, dimensions={"age": "age", "duration": "duration"}, value="rate")
af.mort_rate = mort.lookup(age=af.attained_age, duration=af.duration)
```

**Key facts:**
- `lookup()` is exact-match only -- keys must exist in the table
- **A bare string is a dimension VALUE** (VLOOKUP semantics): `mort.lookup(product="annuity", age=af.age)` looks up the product *"annuity"*. Reference a **column** with `af.product` / `af["product"]` (or `pl.col("product")`). Passing a column name as a bare string produces a loud lookup miss naming the key.
- `dimensions` dict maps **your name** -> **source column name**
- `TableBuilder` for complex/programmatic table construction
- Dimension types: `DataDimension` (default), `MeltDimension` (wide-to-long), `CategoricalDimension`, `ComputedDimension`
- Overflow strategies: `ExtendOverflow`, `FillForward`, `FillConstant`, `LinearInterpolate`
- Always analyze files first: `uv run gspio describe assumptions/mortality.parquet`
- Always verify API: `uv run gspio docs "Table.lookup"`

---

## Timing Conventions

Several methods take a **timing convention**, and it is a choice you make, not a default to
ignore. Getting it wrong is a silent valuation error, not a crash — and **with constant rates
both conventions give identical answers**, so the mistake survives testing and only appears
once rates vary (at age boundaries, or on a real curve).

**The two defaults are opposite. Check, don't assume:**

| Method | Parameter | Default |
|--------|-----------|---------|
| `.projection.prospective_value()` | `timing` | `"end_of_period"` |
| `.projection.cumulative_survival()` | `rate_timing` | `"beginning_of_period"` |

- **`prospective_value(timing=...)`** — whether a period's cashflow lands at the beginning or
  the end of that period. Benefits are usually end-of-period, premiums beginning-of-period.
- **`cumulative_survival(rate_timing=...)`** — whether the decrement at period *t* has already
  been applied. `"beginning_of_period"` gives `[1.0, tpx[0], tpx[0]*tpx[1], ...]`;
  `"end_of_period"` gives `[tpx[0], tpx[0]*tpx[1], ...]` and matches Excel-style timing.
- **Discount factors are timing-anchored.** If you pass `discount_factor=` rather than
  `discount_rate=`, the factors must be built on the same convention you asked for. Under
  varying (per-period) rates the two are **not** related by a single multiplication — each
  cashflow carries its own compounded factor.

Run `uv run gspio docs "prospective_value"` for the full contract. When reconciling against a
reference model, confirm its timing convention before assuming a difference is an assumption
error.

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
| 2 | `until_value=99` | Truncates final year; use 100 (off-by-one is catastrophic, ~3% BEL gap) |
| 3 | `python3` instead of `uv run python3` | `ModuleNotFoundError: No module named 'polars'` |
| 4 | `--policy-id` flag | Policy ID is positional. `--policy-id-column` is a different thing |
| 5 | Hand-rolled exp/log identity for `scalar ** list` | `**` works directly on list columns now -- write it as the operator |
| 6 | Guessing method signatures | Agents get it wrong ~70% of the time -- `gspio docs` first |
| 7 | `proj_year` vs `year` confusion | Stress scenarios silently wrong -- mass lapse never fires. The framework materialises **only** `month`; derive your year label with the formula you mean (`month // 12` duration-style, or the ordinal `when/then` from the period-index section — a bare `(month + 11) // 12` labels the month-0 boundary year 0) and never reuse a calendar `year` column as a projection year |
| 8 | Column name case mismatch | Polars is case-sensitive; check `df.columns` first |

---

## Model Structure: Three Phases

```python
from gaspatchio import ActuarialFrame, when
from gaspatchio.assumptions import Table
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
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="maximum_age",
        until_value=100,   # NOT 99
        frequency="monthly",
    )

    # --- PHASE 3: Calculations (lazy -- NO .collect() from here) ---
    # Attained age varies by period, so the lookup returns one rate per period.
    # month // 12 is completed years since projection start (duration-style).
    af.attained_age = af.issue_age + af.month // 12
    af.mort_rate = tables["mortality"].lookup(age=af.attained_age)
    af.survival = af.mort_rate.projection.cumulative_survival()
    return af
```

`projection.set()` materialises **`af.month`** — elapsed **whole months** from the
projection start: `0,1,2,…` monthly, `0,3,6,…` quarterly, `0,12,24,…` annual. Length
`n_periods + 1`, aligned with `projection.t_years()`, so a maturity test like
`when(af.month == af.policy_term * 12)` reaches the final boundary. Jagged on per-policy
timelines. Not stamped at weekly/daily frequency (calendar months cannot honestly label
those periods) nor on `from_inception` schedules (that axis is policy *duration*, not
projection time).

**There is deliberately no `proj_year` or `year` column.** A projection-year label depends
on your timing convention, and the two candidates disagree at every anniversary boundary
(month 12, 24, …) — so the framework stamping one would silently pick your convention for
you. Write the one-line formula you mean:

```python
af.duration_years = af.month // 12            # completed years: 0,0,…,1,1,… (lifelib-style)
# Ordinal "year 1" = ceil(month/12), Excel ROUNDUP-style. The month-0 boundary
# (the projection start) belongs to year 1 — a bare ceil would label it year 0
# and a `policy_year == 1` shock would skip the first row:
af.policy_year = when(af.month == 0).then(1).otherwise((af.month + 11) // 12)
```

With **end-of-period** rows, "year 1" of a BSCR-style shock is `ceil`; with
**beginning-of-period** rows it is `month // 12 + 1`. See Timing Conventions above. Any
`year` column on the frame is **yours** (calendar year) — the framework never creates one.

If the frame already carries a `month` column and no in-session projection, `set()` raises:
rename it if it is yours, `drop("month")` if it came from a previous run's output.

**Your mortality table must cover every attained age the projection reaches.**
`until="maximum_age"` sizes one grid from the *youngest* life, so older policies run
past `until_value` — a 55-year-old on a grid built for a 40-year-old reaches attained
age 115. Lookups raise on a miss (`on_missing="raise"`), so this surfaces immediately
rather than silently producing NaN reserves.

Phase 1: Load data, rename columns, join enrichment data. `.collect()` is OK.
Phase 2: Create projection timeline. Sets up time dimension (list columns).
Phase 3: All calculations. Lazy only -- no `.collect()`, no Python loops.

---

## Scenarios: the native shape is rows

A scenario axis in gaspatchio is a **cross-join on the model-point frame** — N policies
× M scenarios become N×M rows and the model runs once, vectorized. `with_scenarios` /
`ScenarioRun` are the helpers that build exactly that axis with shocked assumption
tables; do not hand-roll the cross-join before checking them (`uv run gspio docs
"with_scenarios"`). If the variants differ in *wiring* rather than inputs — different
formulas per scenario tab, re-pointed references — the row axis is still the shape, but
divergence belongs in per-variant data columns, never `when(scenario == ...)` control
flow. The model-building skill's classification gate routes this decision.

---

## Skill Routing

| Task | Skill |
|------|-------|
| New to gaspatchio, first setup | `gaspatchio-quickstart` |
| Scope a new model before writing code | `gaspatchio-model-discovery` |
| Convert an Excel workbook to a model | `gaspatchio-workbook-conversion` |
| Write or modify model code | `gaspatchio-model-building` |
| Review model quality / actuarial standards | `gaspatchio-model-review` |
| Match model to Excel/lifelib/vendor reference | `gaspatchio-model-reconciliation` |
| Scenarios, shocks, sensitivity analysis | `gaspatchio-model-scenarios` |
| Add custom accessors or port functions from other libraries | `gaspatchio-extending` |

Skills are in the `skills/` directory. Each has a `SKILL.md` with full instructions. The
table names are the canonical skill names (directory and frontmatter). In Claude Code the
plugin prefixes its own name, so invoke as `gaspatchio:gaspatchio-model-building`.

---

## Tutorial Levels

| Level | Name | Teaches |
|-------|------|---------|
| 1 | Hello World | ActuarialFrame, column arithmetic, when/then, .collect() |
| 2 | Assumptions | Table.lookup(), dimensions, when/then on list columns |
| 3 | Mini Variable Annuity | Full VA projection: mortality, lapse, AV, claims, discounting (6 incremental steps) |
| 4 | Reconciled Lifelib | Production model reconciled to 0.0000% against lifelib across 1,016 model points |
| 5 | Scenarios | Deterministic scenarios, parameter shocks, sensitivity sweeps, regulatory reports |
| patterns | Rollforward Patterns | The state-machine recursion end to end: `af.projection.rollforward(...)` + `compile_rollforward` — fund growth, GMDB ratchet via cross-state read, lapse stop |

Tutorial models are in `tutorial/`. Start at Level 1 if new, Level 3 base for a complete VA model to study. For the rollforward (UL account values, anything where a within-period charge depends on the running balance), init the worked patterns: `gspio tutorial init rollforward-patterns`.

---

## Before You Write Code

1. Look up the method: `uv run gspio docs "<method>"`
2. Analyze data files: `uv run gspio describe <file>.parquet`
3. Build incrementally -- one section at a time, validate with `run-single-policy` after each
4. Do NOT guess method signatures. Do NOT assume you know how a method works.

---

## Extending Gaspatchio

To add custom calculations or accessor methods, use the `gaspatchio-extending` skill.
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

## GitHub workflow

**[`CONTRIBUTING.md`](CONTRIBUTING.md) is canonical** — branches vs forks, signing setup,
commit format, issue-title conventions, PR scope, and the merge policy all live there and
apply to you exactly as they apply to a human. Read it before opening an issue or a PR.
What follows is only what differs when there is no human in the loop.

- **`main` is protected by ruleset** (signed commits, no force-push, no deletion, no
  bypass actors). These are server-side rules — a push that violates one is refused, not
  warned about. Never commit to `main`; branch, then open a PR.
- **Verify claims; do not relay them.** "Reconciles to zero" and "all tests pass" are
  hypotheses until you have run them yourself. State what you ran, and on which SHA.
  Reporting a PR author's claim as though you had checked it is the failure mode that
  matters here.
- **Bind every test claim to a SHA.** Re-check `headRefOid` before asserting results — a
  branch can move between your fetch and your review, and a stale "all green" misleads the
  author more than saying nothing would.
- **Anchor findings to lines** via a formal review with inline comments, not a wall of
  prose. Separate blockers from risks from nits and say which is which; reserve
  `--request-changes` for genuine ship-blockers.
- **Never self-apply `confirmed`, `pending-release`, or the roadmap labels**
  (`exploring`/`building`/`shipped`) — those record a maintainer's judgement, not yours.
- **Name the principle.** When proposing a change, say which entry in `PRINCIPLES.md` it
  serves and which it strains. A change that strains one without saying so is the kind
  that gets reverted three months later.

## Build & test

**Every Python command runs from `bindings/python`** — that is where the Python project and
its lockfile live. There is no Python project at the repository root; running `uv` there
resolves nothing useful (and in a multi-repo checkout it can pick up a workspace spanning
sibling repositories). The repository-root `pyproject.toml` exists only to declare that
boundary.

`uv.lock` is tracked. Install with `--locked` so your environment matches CI exactly; if you
intend to move a dependency, run `uv lock` and commit the result with your change.

```bash
# Install Python dependencies (exact pinned versions)
cd bindings/python && uv sync --locked

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
