# Model Phases

Every gaspatchio model has three phases. The boundary between Phase 1 and Phase 2 is `af.projection.set(...)`. The boundary between Phase 2 and Phase 3 is implicit — once the timeline exists, you're in the calculation phase.

## Phase 1: Setup (Scalar Operations)

Before the projection timeline, columns are **scalar** (one value per policy). This is where you:

- Load and prepare assumption tables
- Alias raw column names to clean snake_case
- Join external data (product params, surrender values)
- Compute derived scalar attributes (age bands, flags, durations)

A parameter that is one number for the run — an expense loading, a valuation rate — stays a
model-point column (join it on, or cross-join a one-row frame) or a one-row `Table` read. Do
not pull it out with `.item()` into a formula: the record then holds a bare literal that names
no file or row, and a scenario's `column=` shock has no column to name.

### Stay on the Frame, Then `materialize()`

Do the setup on the ActuarialFrame — `rename`, `join`, `with_columns` all work there — and close Phase 1 with `af.materialize()`:

```python
af = af.rename({
    "Policyholder sex": "sex",
    "Policyholder issue age": "issue_age",
    "Face amount": "face_amount",
})
af.face_amount = af.face_amount * 1.0          # cast/derive on the frame
af = af.join(product_params, left_on="Product code", right_on="product_code")
af = af.materialize()                          # freeze the finished setup
```

`materialize()` freezes everything calculated so far into values, so Phase 3 plans on top of settled model points instead of re-deriving the setup on every collect. It replaces the old `mp = af.collect()` / edit in raw Polars / `af = ActuarialFrame(mp)` round-trip, which froze the values and threw away everything else the frame knew — how each column was calculated, which projection axis it was on, which columns were inputs. `materialize()` keeps all of it and hands back the same frame.

Reach for `.collect()` when you want the eager Polars DataFrame *itself* — handing column arrays to a numpy RNG, writing output. Reach for `.materialize()` when you want to carry on modelling.

### When the Values Really Do Leave: `continue_from=`

Sometimes the DataFrame has to go outside — a numpy generator, an enrichment routine that only speaks Polars. Coming back with a bare `ActuarialFrame(df)` records each column still holding values the model calculated as a `rebuilt` hole: the record no longer says what made it, and a second engine refuses the lines that read it. Name the frame it came out of instead:

```python
values = af.collect()                                   # the values have to leave
values = values.with_columns(pl.Series("died", rng.binomial(1, p)))
af = ActuarialFrame(values, continue_from=af)           # and this is the way back
af.claims = af.sum_assured * af.died                    # the model carries on
```

A column still holding the values the model's calculations produced keeps saying what made it. A column the trip changed, and a column the trip added, is recorded as data arriving at that point, with the line it came back on. What decides which is a comparison of the values, never a match on the name — and the keyword is never implied: a bare `ActuarialFrame(df)` carries no log across, and says only which columns it cannot account for. Write `continue_from=` where the frame really left; write `materialize()` everywhere else.

**Under a batch runner the trip is judged against the batch.** `run_aggregated` cutting the book into more than one batch, and a scenario plan whose batch holds more than one scenario, refuse a frame rebuilt from a DataFrame — bare or with `continue_from=` — that holds a column the batch did not hold, a changed column, or other rows: the collected frame is the batch, not the book, and under a plan it is every scenario's copy of the book. Keep the setup on the frame and close it with `materialize()`, compute a book-wide figure on the model points before the run, or run one scenario a batch (`batch_size=1`) where the values must leave. See [running-at-scale.md](running-at-scale.md) and [scenarios.md](scenarios.md#phase-1-under-a-plan-keep-the-setup-on-the-frame).

**Do NOT call `.collect()` after Phase 2.** Breaking lazy execution during projection destroys performance and can produce incorrect results.

### Helper Function Pattern

Every real model breaks Phase 1 into helper functions. They take a frame and return a frame:

```python
def setup_ages(af, valuation_date, roll_forward_months=12):
    af = af.rename({"Policyholder issue age": "issue_age"})
    af.attained_age = af.issue_age + roll_forward_months // 12
    # ... more scalar setup ...
    return af

def main(af):
    tables = load_assumptions()
    af = setup_ages(af, valuation_date)
    af = af.materialize()
    af = af.projection.set(...)
    # ... Phase 3 ...
    return af
```

### Dataclass for Model-Level Parameters

For per-run *model-level* parameters that don't vary across scenarios — valuation date, projection length, regulatory regime flags, paths to assumption files — a dataclass is a clean way to wire them through `main`:

```python
from dataclasses import dataclass
import datetime

@dataclass(frozen=True)
class ModelParams:
    valuation_date: datetime.date
    projection_months: int = 240
    regime: str = "IFRS17"

def main(af, params=None):
    if params is None:
        params = ModelParams(valuation_date=datetime.date(2025, 1, 1))
    # Use params.valuation_date etc.
```

For **scenario-level** parameters (shocked assumption tables, stress factors, sweep grids), don't reach for `@dataclass` — declare a `ScenarioRun(shocks=…, aggregations=…)` and run the model unchanged with `plan.run(af, model.main)`: shocks name the model's tables and model-point columns, and `main` takes no override. See the `gaspatchio-model-scenarios` skill for the canonical pattern.

---

## Phase 2: Projection Timeline

`af.projection.set(...)` transforms the ActuarialFrame. Scalar columns remain scalar; the call stamps three eager scalar columns per policy (`projection_start_date`, `projection_end_date`, `num_proj_months`) and records the schedule so that lazy accessors (list columns) can be built in Phase 3.

**Where the projection starts depends on the grid it lays.** A per-policy (jagged) grid
starts on the date given: `valuation_date=date(2025, 6, 15)` with a term column, or with
`until="maximum_age"` at the default `per_policy`, gives `projection_start_date` 2025-06-15 and
period dates 2025-07-15, 2025-08-15, … . Every shared grid starts on the last day of the
start month instead: the policy-anchored form with a whole-number `until_value`
(`until_value=12`), with `fixed_date`, or with `per_policy=False` opens 2025-06-15 at
2025-06-30, with period dates 2025-07-31, 2025-08-31, … (and `fixed_date=date(2026, 6, 15)`
closes the axis at 2026-06-30); the fixed-grid form (`start_date=` with `n_periods=`) on a
calendar cadence gives 2025-01-31 for `start_date=date(2025, 1, 1)` or `date(2025, 1, 15)`.
Dates read off the axis (`period_dates()`, an attained age from a date of birth) follow that
start, so check it against a workbook whose dates start mid-month.

```python
af = af.projection.set(
    valuation_date=datetime.date(2025, 1, 1),
    until="maximum_age",   # "maximum_age" | "term_years" | "term_months" | "fixed_date"
    until_value=100,       # int, date, or column-name str for per-policy timelines
    frequency="monthly",
)
```

### Critical: `until_value=100`, NOT 99

If your mortality table goes to age 100, use `until_value=100`. Using 99 truncates the final year where high-mortality cashflows spike. This single off-by-one caused a 3% BEL gap in production.

### Per-policy (jagged) timelines

When `until_value` is a column name and `until` is `"term_months"` or `"term_years"`, each policy projects only its own horizon — list columns have variable length. This is the default (auto-selected). `until="maximum_age"` runs each policy to its own horizon: `until_value` less its issue age, in whole years, so every life stops at attained age `until_value` whoever shares the run. That holds for a number, a column name or an expression `until_value`, at a monthly, quarterly, semi-annual or annual frequency; a weekly or daily one is refused, as it is for a term, since a number of years is not a whole number of weeks or days. Pass `per_policy=False` to force a uniform rectangular grid instead. Its length is read from the rows -- the longest term, the youngest life -- so it is refused wherever the frame is not the whole book: in a batch runner cutting the book into batches, and on a scenario axis. There, keep the jagged default or state the length as a number:

```python
# Jagged (default): each policy projects its own remaining term
af = af.projection.set(
    valuation_date=datetime.date(2025, 1, 1),
    until="term_months",
    until_value="remaining_term_months",
    frequency="monthly",
)

# Uniform: all policies get max-length lists (wastes compute for short policies)
af = af.projection.set(
    valuation_date=datetime.date(2025, 1, 1),
    until="term_months",
    until_value="remaining_term_months",
    frequency="monthly",
    per_policy=False,
)
```

### Eager stamps vs lazy list columns

`af.projection.set()` stamps three **scalar** columns immediately (usable in Phase 1 guards or joins):

| Column | Type | Meaning |
|--------|------|---------|
| `projection_start_date` | `Date` | Valuation date as given on a per-policy grid; its month's last day on a shared grid |
| `projection_end_date` | `Date` | Per-policy end date |
| `num_proj_months` | `Int64` | Boundary count, `n_periods + 1` — it counts points, not periods |

For `until="maximum_age", until_value=100, issue_age=30`: `num_proj_months == 70 * 12 + 1` for that policy, whatever other ages share the run (the +1 is the start boundary at t=0).

**List columns** are built lazily in Phase 3 via the projection accessor:

```python
af.projection_date = af.projection.period_dates()    # List<Date> — one date per period
af.t_years = af.projection.t_years()                 # List<Float64> — cumulative year fracs
af.dt = af.projection.year_fractions()               # List<Float64> — per-period dt
```

`af.projection.t_years()` is the direct input to `Curve.discount_factor()` for
term-structure discounting — see [curves-and-scheduling.md](curves-and-scheduling.md).

### The period-index column (`month`)

`af.projection.set()` **materialises `af.month`** — elapsed whole months from the
projection start: `0,1,2,…` monthly, `0,3,6,…` quarterly, `0,12,24,…` annual. Do not
rebuild it from `period_dates()`; it is already there, and calendar-date arithmetic
gets the elapsed-months semantics wrong at month boundaries.

Three things about its shape that do bite:

- It is **point-indexed**: `n_periods + 1` values, one per period boundary, aligned
  with `t_years()`, and every column derived from an axis inherits the extra value.
  Rollforward inputs are period-indexed (`n_periods` values). Build them with one value
  per period: pass a per-policy value as it stands (the rollforward reads it in every
  period), repeat one with
  `.projection.broadcast_to_periods(like=af.projection.year_fractions())`, or derive the
  column from `af.projection.year_fractions()`, which holds one value per period. A column
  already derived from an axis — a lookup keyed on `af.issue_age + af.month // 12` — has
  no declared cut: `.polars_native().list.head(n_periods)` drops its final boundary and
  records the line `engine_native`, so it runs only on Polars, and so does the rollforward
  that reads it. `n_periods = num_proj_months - 1`; on a **jagged** schedule there is no
  single count — never cut with a portfolio-wide constant.
- It is **not stamped** at weekly/daily frequency (calendar months cannot honestly
  label those periods) nor on `from_inception` schedules (that axis is policy
  *duration*, not projection time). On those, use `t_years()` as your axis.
- If the input frame already carries a `month` column, `set()` **raises** rather than
  silently overwriting: rename it if it is yours, `drop("month")` if it came from a
  previous run's output.

There is deliberately no `proj_year` column — a projection-year label depends on your
timing convention. Derive the one you mean (`af.month // 12` for completed years);
see [timing-and-dates.md](timing-and-dates.md).

### Off-calendar workbooks: a fixed-step axis

A teaching workbook, a numerical solution of Thiele's or Kolmogorov's equations (multi-state
occupancy — one `accumulate` per state, [recursive-patterns.md](recursive-patterns.md)
Pattern 6), or a continuous-time product discretised for valuation steps *k × h years* and
has **no dates**: a step column `A` running `0..T` and a time column `B` written `x + A*h`
or `x + A/12`. Do not fake a calendar for it (2,947 "annual" periods gives `t_years`
1, 2, 3 … instead of 0.1, 0.2, 0.3), and do not carry the step index as model-point data:
a frame with no projection has no timeline, so a period method on a per-policy column runs
**down the policies** (each policy gets the previous policy's value), and there is no
rollforward and no `t_years()`. Declare the step axis instead:

```python
af = af.projection.set(n_periods=2947, step_years=0.1)   # sheet writes x + A*h
af = af.projection.set(n_periods=240, steps_per_year=12)  # sheet writes x + A/12
af.x_t = af.issue_age + af.projection.t_years()           # column B, bit for bit
af.mu01 = intensities.lookup(step=af.step, ...)           # step is stamped 0..T
```

- **Pick the spelling the workbook uses.** `t_years()` is `k * step_years` or
  `k / steps_per_year`, one rounding per boundary; the two (and a running sum) differ in the
  last bits at a third of the boundaries or more, so only the sheet's own spelling
  reconciles to the bit.
- It stamps `step` (Int64, `0..T`), `num_proj_months` (`T + 1`), and `month` only where a
  step is whole months (`steps_per_year` of 1, 2, 3, 4, 6, 12). **`step` is reserved like
  `month`**: model points that carry their own `step` column are refused — rename it.
- No dates: `period_dates()` and `end_date_column` refuse, and so do `start_date`,
  `valuation_date`, `frequency` and `until=` beside the step (horizons are `n_periods`
  only). `anniversary_mask()` needs `steps_per_year` (every n-th step); on `step_years` it
  refuses rather than guess whether ten steps of 0.1 make a year.
- `year_fractions()` is `h` (or `1/n`) each period — `year_fractions().cum_sum()` is **not**
  `t_years()` in the last bits; read time from `t_years()`.
- The rollforward, the period methods and the JAX engine all run on it unchanged.

### `.projection` (frame) vs `.date` (column) — They Are Different

| Accessor | Level | Methods |
|----------|-------|---------|
| `af.projection` | Frame-level | `set(...)`, `period_dates()`, `t_years()`, `year_fractions()`, `anniversary_mask()`, `is_in_force()` |
| `af.<col>.date` | Column-level (declared) | `months_between(other)`, `to_period("1mo")` |
| `af.<col>.excel` | Column-level (declared) | `days`, `edate`, `eomonth`, `yearfrac` |
| `af.<col>.polars_native().dt` | Column-level (escape) | `.year()`, `.month()`, `.day()` |

These are NOT interchangeable. `af.projection.set()` is the frame-level timeline setup. The
date operations the vocabulary declares are `af.<col>.date.months_between(other)` (whole
months, positive when `other` is later) and `af.<col>.date.to_period("1mo")`, beside
`excel.days`, `excel.edate`, `excel.eomonth` and `excel.yearfrac`. A date part — year, month,
day — has no declared form in 1.0: read it with `af.<col>.polars_native().dt.year()`, which
records the line `engine_native` (it runs only on Polars, and so does every calculation that
reads it). Where the part only feeds a duration, `months_between` says it without the escape.

---

## Phase 3: Calculations (Lazy Execution)

After the projection timeline, all operations should be **lazy** — expressed as column assignments that build a computation graph. Gaspatchio executes the graph efficiently when results are needed.

### Typical Calculation Order

Production models have 10+ logical sections, not just 3 phases. Here is the realistic section breakdown used by the tutorial and appliedlife models:

| Section | What it computes | Key patterns |
|---------|-----------------|--------------|
| 1. Assumptions | Load tables, join product params | `Table()`, `.collect()` + `.join()` OK here |
| 2. Time setup | `month`, `duration`, `age`, projection timeline | `af.projection.set()`, `af.projection.period_dates()`, date arithmetic |
| 3. Mortality | Table lookup, scalars, annual→monthly | `Table.lookup()`, `.clip()`, `1-(1-q)^(1/12)` |
| 4. Lapse | Base rate lookup, dynamic adjustment | ITM ratio, `.clip()` for caps/floors |
| 5. Investment | Fund returns, account value, fees | `cum_prod()`, `previous_period(fill_value=1.0)` |
| 6. Policy counts | Survival, in-force, deaths, lapses | `cum_prod()`, `previous_period()`, `when/then` for maturity |
| 7. Claims | Death/lapse/maturity, guarantees | Nested `when/then` for GMDB/GMAB |
| 8. Premiums | Single/regular, timing | `when(duration_mth_t == 0)` for single premium |
| 9. Expenses | Acquisition + maintenance, inflation | `(1 + infl) ** af.projection.t_years()` — `**` works on list columns |
| 10. Net cashflow | Investment income, AV change | `next_period(fill_value=0.0)` |
| 11. Discounting | Rate lookup or constant, PVs | `cum_prod(1/(1+r))` for varying rates, `.list.sum()`; for a yield curve / EIOPA term structure: `Curve.discount_factor(af.projection.t_years())` — see [curves-and-scheduling.md](curves-and-scheduling.md) |

**Important**: Section ordering may change based on dependencies. For example, if dynamic lapse depends on account value (ITM ratio), move the AV section before lapse. The tutorial Level 3 Steps 04-05 demonstrate this reordering.

### Key Accessor Methods

Always look these up with `gspio docs` before using. Here's the landscape:

| Accessor | Key Methods |
|----------|------------|
| `.projection` | `cumulative_survival()`, `prospective_value()`, `previous_period()`, `next_period()`, `at_period()`, `with_period()`, `accumulate()`, `remaining_sum()` |
| `.finance` | `to_monthly()`, `compound()`, `discount_factor()`, `present_value()` |
| `.excel` | `pv()`, `yearfrac()`, `from_excel_serial()` |
| `.list` | `.sum()`, `.mean()`, `.min()`, `.max()` |
| (expression) | `.cum_prod()`, `.cum_sum()`, `.round()`, `.clip()` |
| `.polars_native()` | The escape: Polars methods the vocabulary does not declare, such as `.list.head()`. The line records `engine_native` and runs only on Polars, as does everything reading it — `af.graph.tiers()` names them |

**Do not memorize signatures.** Look them up:

```bash
uv run gspio docs "prospective_value" -t parameters
uv run gspio docs "cumulative_survival" -t code_example
```

### Running and Debugging

```bash
# Single policy — your primary debugging tool
uv run gspio run-single-policy model.py data.parquet 123 -r 30 -f 5 -l 10

# Full model run
uv run gspio run-model model.py data.parquet

# Describe data file structure
uv run gspio describe data.parquet
```

Use `run-single-policy` heavily. Verify each section produces correct output for one policy before proceeding.

---

## Decrement ordering: BEF_DECR pattern

For production models with multiple decrements and new business:

1. `pols_if_bef_mat` = survival × policy_count × (duration ≤ maturity) × (duration > 0)
2. `pols_maturity` = pols_if_bef_mat × (duration == maturity_month)
3. `pols_if_bef_nb` = pols_if_bef_mat − pols_maturity
4. `pols_new_biz` = policy_count × (duration == 0)
5. `pols_if_bef_decr` = pols_if_bef_nb + pols_new_biz
6. `pols_death` = pols_if_bef_decr × mort_rate_mth
7. `pols_lapse` = (pols_if_bef_decr − pols_death) × lapse_rate_mth

The `duration > 0` guard prevents double-counting NB policies that enter via `pols_new_biz`. For IF-only business, the simple ordering gives identical results. See Level 4 model.py SECTION 8.
