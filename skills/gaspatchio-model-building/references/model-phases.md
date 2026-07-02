# Model Phases

Every gaspatchio model has three phases. The boundary between Phase 1 and Phase 2 is `af.projection.set(...)`. The boundary between Phase 2 and Phase 3 is implicit — once the timeline exists, you're in the calculation phase.

## Phase 1: Setup (Scalar Operations)

Before the projection timeline, columns are **scalar** (one value per policy). This is where you:

- Load and prepare assumption tables
- Alias raw column names to clean snake_case
- Join external data (product params, surrender values)
- Compute derived scalar attributes (age bands, flags, durations)

### `.collect()` Is OK Here

Use `.collect()` freely in Phase 1 to drop into Polars DataFrame operations:

```python
mp = af.collect()
mp = mp.with_columns([
    pl.col("Policyholder sex").alias("sex"),
    pl.col("Policyholder issue age").alias("issue_age"),
    pl.col("Face amount").cast(pl.Float64).alias("face_amount"),
])
# Join product parameters
mp = mp.join(product_params, on="Product code", how="left")
af = ActuarialFrame(mp)
```

**Do NOT call `.collect()` after Phase 2.** Breaking lazy execution during projection destroys performance and can produce incorrect results.

### Helper Function Pattern

Every real model breaks Phase 1 into helper functions:

```python
def setup_ages(af, valuation_date, roll_forward_months=12):
    mp = af.collect()
    mp = mp.with_columns([
        pl.col("Policyholder issue age").alias("issue_age"),
        # ... more scalar setup ...
    ])
    return ActuarialFrame(mp)

def main(af):
    tables = load_assumptions()
    af = setup_ages(af, valuation_date)
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

For **scenario-level** parameters (shocked assumption tables, stress factors, sweep grids), don't reach for `@dataclass` — declare a `ScenarioRun(shocks=…, base_tables=…, aggregations=…)` and use `assumptions_override` on `main` so each scenario gets fresh tables. See the `gaspatchio-model-scenarios` skill for the canonical pattern.

---

## Phase 2: Projection Timeline

`af.projection.set(...)` transforms the ActuarialFrame. Scalar columns remain scalar; the call stamps three eager scalar columns per policy (`projection_start_date`, `projection_end_date`, `num_proj_months`) and records the schedule so that lazy accessors (list columns) can be built in Phase 3.

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

When `until_value` is a column name and `until` is `"term_months"` or `"term_years"`, each policy projects only its own horizon — list columns have variable length. This is the default (auto-selected). Pass `per_policy=False` to force a uniform rectangular grid instead:

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
| `projection_start_date` | `Date` | Valuation date |
| `projection_end_date` | `Date` | Per-policy end date |
| `num_proj_months` | `Int32` | Period count (including start boundary) |

For `until="maximum_age", until_value=100, issue_age=30`: `num_proj_months == 70 * 12 + 1` (the +1 is the start boundary at t=0).

**List columns** are built lazily in Phase 3 via the projection accessor:

```python
af.projection_date = af.projection.period_dates()    # List<Date> — one date per period
af.t_years = af.projection.t_years()                 # List<Float64> — cumulative year fracs
af.dt = af.projection.year_fractions()               # List<Float64> — per-period dt
```

`af.projection.t_years()` is the direct input to `Curve.discount_factor()` for
term-structure discounting — see [curves-and-scheduling.md](curves-and-scheduling.md).

### Deriving a period-index column (`month`)

`af.projection.set()` does NOT stamp an `af.month` or `af.t` index column — derive it from the date list:

```python
# Derive month index (0-based) from projection dates
af.projection_date = af.projection.period_dates()
af.month = (
    (af.projection_date.dt.year() - 2025) * 12
    + (af.projection_date.dt.month() - 1)
)
```

Adjust the reference year to match your `valuation_date`.

### `.projection` (frame) vs `.dt` (column) — They Are Different

| Accessor | Level | Methods |
|----------|-------|---------|
| `af.projection` | Frame-level | `set(...)`, `period_dates()`, `t_years()`, `year_fractions()`, `anniversary_mask()`, `is_in_force()` |
| `af.column.dt` | Column-level (Polars) | `.year()`, `.month()`, `.day()` |

These are NOT interchangeable. `af.projection.set()` is the frame-level timeline setup. Date component extraction on a column uses `af.column.dt`.

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
| 9. Expenses | Acquisition + maintenance, inflation | exp/log identity for `constant^list` |
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
| `.list` | `.sum()`, `.mean()`, `.cumsum()`, `.head()` |
| (expression) | `.cum_prod()`, `.sum()`, `.round()`, `.clip()` |

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
