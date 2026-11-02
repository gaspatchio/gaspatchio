# Gaspatchio Framework Knowledge

High-performance actuarial modeling framework: Python API backed by Rust/Polars. The formula IS the code.

---

## Where the rules live

Beside the code they govern — Rust in [`core/AGENTS.md`](core/AGENTS.md), Python in
[`bindings/python/AGENTS.md`](bindings/python/AGENTS.md), and contributor process, which
applies to an agent exactly as it applies to a person, in [`CONTRIBUTING.md`](CONTRIBUTING.md).
Claude Code loads all of them via `CLAUDE.md`. **Codex merges only this file plus the one
nearest your working directory, and stops at 32 KiB silently** — which is why this file
carries the framework knowledge and nothing else.

**Before you run anything: prefer the venv over `uv run`.** `uv run` silently rebuilds the
Rust extension at `--profile=dev`, swapping the parked *release* extension for a *debug* one:
test outcomes change and every timing figure here is invalidated. Use
`bindings/python/.venv/bin/python` and `.../.venv/bin/gspio`. The mechanism is in
[`bindings/python/AGENTS.md`](bindings/python/AGENTS.md); the release rebuild that recovers
from it is in `CONTRIBUTING.md`.

---

## Principles — read these first

The north star, condensed below because agents must load it, not fetch it: Codex does not
expand `@file` imports. **Full text: [`PRINCIPLES.md`](PRINCIPLES.md)**
(<https://gaspatchio.dev/latest/principles/>). The block below is generated from it — edit that file,
then run `bindings/python/.venv/bin/python scripts/gen_skill_manifests.py`. Each position
keeps the sentence that sets the problem and the sentence that states the answer. **Justify
design decisions and bug-triage verdicts against them by name.**

<!-- BEGIN GENERATED PRINCIPLES -->

These are the positions the framework takes.

### Meet you where you are

You arrive at any new modelling tool with a working setup: tables in the shape someone published them in, formulas you know from spreadsheets, a Python skill you didn't pick up to use this framework specifically. The framework reshapes itself to you, not the other way round.

### Closed-form by default, escalation when state demands it

Recursive cell-graphs — function calling function with time offsets, evaluation order resolved at run time — were the answer when actuarial modelling first landed in Python. The escalation is deliberate and explicit, not the default.

### Optimize for the laptop, not the cluster

Most actuarial modelling stacks scale by running somewhere else — overnight on a vendor batch, on a cluster IT provisioned six months ago, in a "production environment" you don't develop in. The edit-run-refine loop slipping past a few seconds is the failure mode we treat as broken, and we would rather drop a capability than loosen the loop to add it.

### Audit by default, not by request

Governance is what someone bolts on after the framework is chosen, the model is built, the regulator has asked a question. Quarter-over-quarter drift becomes visible the moment it appears, not on page seventeen of an experience study, not in the meeting where everyone has already left.

### LLM-shaped from the inside out

You and an LLM working together is the design target, not a retrofit. Every choice points at the same target.

### Sharp knives, no magic

Frameworks that wrap calculations in decorators, DSL macros, or magic class-attribute resolution save typing but cost transparency. Sharp knives in a competent hand are safer than blunt knives that pretend not to cut.

### No vendor lock-in, by construction

The model you build in this framework is not a hostage. There is no commercial decision in someone else's boardroom that ends the ability to run last year's valuation.

### Using these principles

**The tension you will hit most.** *Meet you where you are* pulls toward accepting whatever the
user wrote and reshaping around it. *Sharp knives, no magic* pulls toward refusing anything
ambiguous rather than guessing. They are both correct and they disagree at the boundary. The
resolution this framework uses: **be liberal about the shapes you accept, be strict about the
meanings you infer.** Accepting a wide mortality table is meeting the user where they are.
Guessing which column is the rate is magic. A clear error naming the ambiguity and the fix is
almost always better than either silently picking one or failing opaquely.

<!-- END GENERATED PRINCIPLES -->

---

## Core Concept: ActuarialFrame

An `ActuarialFrame` wraps a Polars DataFrame. Columns are either **scalar** (one value per policy) or **list** (one value per projection period). Arithmetic between scalar and list columns broadcasts automatically.

```python
from gaspatchio import ActuarialFrame, when
af = ActuarialFrame(polars_dataframe)
af.claims = af.sum_assured * af.pols_death        # scalar * list -> list (auto-broadcast)
af.net_cf = af.premiums - af.claims - af.expenses  # list - list - list -> list
```

The old `gaspatchio_core` import name was removed in 1.0.0; write `import gaspatchio`.

---

## API Patterns

**Simple math -- operators directly.** The formula is the code; no wrapper methods.
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
af.res = af.cf.projection.accumulate(initial=0.0, multiplier=af.v, addend=af.cf, reverse=True)
# ^ rollback from each policy's last period: V[t] = v[t]·V[t+1] + cf[t]
```

**Conditionals -- `when/then/otherwise` (mirrors Excel IF).**
```python
af.pols_maturity = when(af.month == af.policy_term * 12).then(af.surviving_at_t).otherwise(0.0)
af.commissions = when(af.duration == 0).then(af.premiums).otherwise(0.0)
```

**Column access:** prefer `af.mortality_rate` over `af["mortality_rate"]`; brackets only for
spaces or keywords (`af["Policy Number"]`, `af["class"]`). Underscore-prefixed names raise
(`af._flag`). snake_case for calculated columns; alias raw inputs first.

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
- **A bare string is a dimension VALUE** (VLOOKUP semantics): `mort.lookup(product="annuity", age=af.age)` looks up the product *"annuity"*. Reference a **column** with `af["product"]` (or `pl.col("product")`): `af.product` is a frame method. Passing a column name as a bare string produces a loud lookup miss naming the key.
- `dimensions` dict maps **your name** -> **source column name**
- `TableBuilder` for complex/programmatic table construction
- Dimension types: `DataDimension` (default), `MeltDimension` (wide-to-long), `CategoricalDimension`, `ComputedDimension`
- Overflow strategies: `ExtendOverflow`, `FillForward`, `FillConstant`, `LinearInterpolate`
- Always analyze files first: `uv run gspio describe assumptions/mortality.parquet`
- Always verify API: `uv run gspio docs "Table.lookup"`

---

## Timing Conventions

A **timing convention** is a choice you make, not a default to ignore. Getting it wrong is a
silent valuation error, not a crash. The two conventions differ even at flat rates, but a wrong
*conversion* between them — one multiplication by `v`, or factors raised from each period's own
rate — passes every flat-rate test and is wrong once rates vary: **test with varying rates**.

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

Run `gspio docs "prospective_value"` for the full contract. When reconciling against a
reference model, confirm its timing convention before assuming a difference is an assumption
error.

---

## CLI Reference

**These need the project environment; system Python has neither gaspatchio nor polars.** The
published docs write `uv run gspio`; **in a checkout of this repository substitute
`bindings/python/.venv/bin/gspio`** (see the rule at the top of this file).

```bash
gspio run-model model.py data.parquet
gspio run-single-policy model.py data.parquet 123          # policy ID POSITIONAL, not a flag
gspio run-single-policy model.py data.parquet 123 --output-file /tmp/result.parquet
gspio run-single-policy ... --policy-id-column "Policy number"   # different thing to the ID
gspio docs "cumulative_survival"        # look up API docs before using any method
gspio knowledge "CSM calculation" -T ifrs17
gspio describe assumptions/mortality.parquet
gspio run-artifact m.json data.parquet --engine jax  # JAX: gaspatchio[jax]; m.json from calc-graph --profile executable
```

**Agent workflow:** build one section at a time, validating with `run-single-policy` after
each. Always `--output-file` to parquet, then read it with `gspio describe --json` or inline
Polars. Do NOT parse stdout.

---

## Performance Rules (Non-Negotiable)

| Never | Why |
|-------|-----|
| `map_elements` or `apply` | ~14x slower; defeats vectorization |
| `for row in ...` / Python loops over policies | Breaks performance entirely |
| `.collect()` during projection phase | Breaks lazy execution (to freeze Phase 1, use `.materialize()`) |
| `print()` in production code | Use loguru logger instead |

Let Polars handle parallelization. Never add Rayon or threading inside plugins.

---

## Top Gotchas

| # | Gotcha | What Goes Wrong |
|---|--------|-----------------|
| 1 | Arithmetic-masking blends in conditional code | Old workaround for a fixed limitation -- `when/then/otherwise` now handles mixed scalar/list branches |
| 2 | `until_value=99` | Truncates final year; use 100 (off-by-one is catastrophic, ~3% BEL gap) |
| 3 | system `python3`, or `uv run` on this branch | `ModuleNotFoundError: polars`; `uv run` also swaps the parked release build — use `bindings/python/.venv/bin/python` |
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

    # --- PHASE 1: Setup (rename, join, derive per-policy attributes) ---
    af = af.rename({"Issue Age": "issue_age"})
    af = af.materialize()   # freeze the finished setup, keep the frame

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

`projection.set()` materialises **`af.month`** — elapsed **whole months** from projection
start: `0,1,2,…` monthly, `0,3,6,…` quarterly, `0,12,24,…` annual. Length `n_periods + 1`,
aligned with `projection.t_years()`, so `when(af.month == af.policy_term * 12)` reaches the
final boundary. Jagged on per-policy timelines. Not stamped at weekly/daily frequency
(calendar months cannot honestly label those periods) nor on `from_inception` schedules
(that axis is policy *duration*, not projection time).

**There is deliberately no `proj_year` or `year` column.** A projection-year label depends on
your timing convention, and the two candidates disagree at every anniversary boundary (month
12, 24, …), so stamping one would silently pick your convention for you. Write the formula
you mean:

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
`until="maximum_age"` runs each policy to its own horizon: `until_value` less its issue
age, in whole years, so every life stops at attained age `until_value` whoever shares the
run. Lookups raise on a miss (`on_missing="raise"`), so a short table surfaces
immediately rather than silently producing NaN reserves.

**Close Phase 1 with `af.materialize()`.** It freezes everything calculated so far into
values, so Phase 3 plans on top of settled model points instead of re-deriving the setup on
every collect. Unlike the old `ActuarialFrame(af.collect())` round-trip, it keeps what the
frame knew — how each column was calculated, its axis, its inputs — and hands back the same
frame, so assignments either side of it read as one model. Use `.collect()` when you want
the eager Polars DataFrame itself (handing arrays to a numpy RNG, writing output); use
`.materialize()` when you want to carry on modelling.

**When the values genuinely leave the frame, come back through
`ActuarialFrame(df, continue_from=af)`.** A numpy generator, or an enrichment routine that
only speaks Polars, needs the eager DataFrame — and a bare `ActuarialFrame(df)` on the way
back records each column still holding values the model calculated as a `rebuilt` hole, which
no longer says what made it. `continue_from=`
carries the log across instead: a column still holding the values the model's calculations
produced keeps saying what made it, and a column the trip changed or added is recorded as
data arriving at that point, with the line it came back on. Inheritance is decided by
comparing values, never by matching names, and the keyword is never implied — so write it
where the frame really left, and `materialize()` everywhere else.

```python
values = af.collect()                                   # the values have to leave
values = values.with_columns(pl.Series("died", rng.binomial(1, p)))
af = ActuarialFrame(values, continue_from=af)           # and this is the way back
```

Phase 1: Load data, rename columns, join enrichment data, then `af.materialize()`.
Phase 2: Create projection timeline. Sets up time dimension (list columns).
Phase 3: All calculations. Lazy only -- no `.collect()`, no Python loops.

---

## Scenarios: the native shape is rows

A scenario axis is a **cross-join on the model-point frame** — N policies × M scenarios become
N×M rows and the model runs once, vectorized. `with_scenarios` / `ScenarioRun` build exactly
that axis; don't hand-roll the cross-join (`gspio docs "with_scenarios"`). A plan runs the model
you reconciled, unchanged — `plan.run(af, model.main)` — each shock naming one target, a table
(`table=`) or a model-point column such as a valuation rate (`column=`), so BASE is provably
the reconciled model. If variants differ in *wiring* rather than inputs — different
formulas per tab, re-pointed references — the row axis is still the shape, but divergence
belongs in per-variant data columns, never `when(scenario == ...)` control flow. The
model-building skill's classification gate routes this.

**`with_scenarios` guarantees the row order it teaches: model points major, scenarios minor**
— policy 1 against every scenario, then policy 2 — and that holds under the streaming engine,
which is what `collect()` runs by default. Pinned, not incidental.

**That guarantee does not extend to the rest of the frame.** Row *position* is not row identity
under streaming: a lazy plan may emit chunks in whatever order they finish, so `with_row_index`
records where a row sat in the plan, not where it lands in the collected frame — adding one can
itself change the order. When order matters downstream, `sort` by the model's own axes
(`policy_id`, `scenario_id`, `month`) rather than trusting position.

---

## The calculation graph: `af.graph`

Every frame records what it built. `af.graph` is the audit surface over that record —
ask it rather than hand-rolling a walker over your own columns.

```python
af.graph.precedents("reserve")   # what reserve's own formula read — one hop back
af.graph.dependents("reserve")   # what reads reserve directly — one hop forward
af.graph.trace("reserve")        # everything behind it, down to the leaves
af.graph.affected("mort_rate")   # everything ahead of it — "if this moves, what moves?"
af.graph.versions("reserve")     # every definition of the name, oldest first
af.graph.latest("reserve")       # the node the current value came from
af.graph.holes()                 # columns the model cannot account for; `[]` is the claim
af.graph.fingerprint()           # one "sha256:<hex>" over the whole model
```

`precedents`/`dependents` are the worksheet's two audit arrows, one hop each way along an
edge. `trace` and `affected` are the transitive versions — read `trace` top to bottom and
you have the derivation, `affected` top to bottom and you have the propagation. All of
them answer for the **live** definition of a column name; pass `"column@ordinal"`
(`"reserve@1"`) to ask about a superseded one. The walk stops at leaves: a column the data
arrived with, and a column nothing accounts for. A **joined** column is not a leaf: it reads the
key it was joined on, and the right-hand table's content is in its fingerprint.

**The doors out**, on the audit file `gspio calc-graph model.py mp.parquet -o m.audit.json
--results r.parquet` writes (Python forms, and which identity answers which question:
model-review's `audit-record.md`):

```bash
gspio verify m.audit.json --results r.parquet --model model.py  # are these its files?
gspio diff old.audit.json m.audit.json --results old.parquet r.parquet  # what moved, how far
gspio graph trace m.audit.json reserve  # af.graph, from the file alone
gspio sheet m.audit.json -o m.xlsx      # each policy as a sheet, no Python
```

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
| Chart or total a finished run from its artifact and results file | `gaspatchio-results-analysis` |
| Add custom accessors or port functions from other libraries | `gaspatchio-extending` |

Skills are in the `skills/` directory. Each has a `SKILL.md` with full instructions. The
table names are the canonical skill names (directory and frontmatter). In Claude Code the
plugin prefixes its own name, so invoke as `gaspatchio:gaspatchio-model-building`.

---

## Tutorial Levels

Six graded tutorials in `tutorial/` — Level 1 (ActuarialFrame basics) to Level 5 (scenarios),
plus `rollforward-patterns` for the state-machine recursion. `gspio tutorial list` / `init
<name>`. Level 3 is the smallest complete VA model; Level 4 the lifelib reconciliation.

---

## Extending Gaspatchio

Use the `gaspatchio-extending` skill. Two rules hold whether or not you invoke it: compose
Polars expressions -- never `map_elements`, Python for-loops over policies, or per-row dict
lookups (50-1000x slowdowns) -- and reach for the accessor pattern (`@register_accessor` +
base classes) as the extension mechanism. The skill carries the performance ladder
(setup utility -> column accessor -> frame accessor -> Rust kernel) and 7 worked anti-patterns.

---

## Contributing to gaspatchio

Everything above is how to **use** gaspatchio. To work on gaspatchio itself, read
[`CONTRIBUTING.md`](CONTRIBUTING.md): it is canonical for an agent exactly as it is for a
person.
