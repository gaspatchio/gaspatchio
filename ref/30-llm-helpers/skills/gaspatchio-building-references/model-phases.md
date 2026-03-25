# Model Phases

Every gaspatchio model has three phases. The boundary between Phase 1 and Phase 2 is `create_projection_timeline()`. The boundary between Phase 2 and Phase 3 is implicit — once the timeline exists, you're in the calculation phase.

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
    af = af.date.create_projection_timeline(...)
    # ... Phase 3 ...
    return af
```

### Dataclass for Parameters

For models that run multiple scenarios, use a dataclass:

```python
from dataclasses import dataclass

@dataclass
class ScenarioParams:
    mortality_factor: float = 1.0
    discount_rate: float = 0.025
    inflation_rates: tuple = (0.02, 0.02, 0.02, 0.02, 0.02)

def main(af, params=None):
    if params is None:
        params = ScenarioParams()
    # Use params.mortality_factor, params.discount_rate, etc.
```

---

## Phase 2: Projection Timeline

`create_projection_timeline()` transforms the ActuarialFrame. Scalar columns remain scalar; date-based projection columns become **list columns** (one list per policy, with one element per projection period).

```python
af = af.date.create_projection_timeline(
    valuation_date=datetime.date(2025, 1, 1),
    projection_end_type="maximum_age",
    projection_end_value=100,
    projection_frequency="monthly",
)
```

### Critical: `projection_end_value=100`, NOT 99

If your mortality table goes to age 100, use `projection_end_value=100`. Using 99 truncates the final year where high-mortality cashflows spike. This single off-by-one caused a 3% BEL gap in production.

### No Built-In `af.t`

There is **no automatic period counter column**. `create_projection_timeline()` produces only a `date` list column. You must derive `t` yourself:

```python
# Common pattern: derive from dates
af.t = (af["date"].dt.year() - valuation_date.year) * 12 + (af["date"].dt.month() - valuation_date.month)
```

Or look up the framework approach: `uv run gspio docs "period index" -n 10`

### `.date` vs `.dt` — They Are Different

| Accessor | Level | Methods |
|----------|-------|---------|
| `af.date` | Frame-level | `create_projection_timeline()`, `create_timeline()`, `add_duration()` |
| `af.column.dt` | Column-level (Polars) | `.year()`, `.month()`, `.day()` |

These are NOT interchangeable. `create_projection_timeline()` is on `af.date`. Date component extraction is on `af.column.dt`.

---

## Phase 3: Calculations (Lazy Execution)

After the projection timeline, all operations should be **lazy** — expressed as column assignments that build a computation graph. Gaspatchio executes the graph efficiently when results are needed.

### Typical Calculation Order

Production models have 10+ logical sections, not just 3 phases. Here is the realistic section breakdown used by the tutorial and appliedlife models:

| Section | What it computes | Key patterns |
|---------|-----------------|--------------|
| 1. Assumptions | Load tables, join product params | `Table()`, `.collect()` + `.join()` OK here |
| 2. Time setup | `month`, `duration`, `age`, projection timeline | `create_projection_timeline()`, date arithmetic |
| 3. Mortality | Table lookup, scalars, annual→monthly | `Table.lookup()`, `.clip()`, `1-(1-q)^(1/12)` |
| 4. Lapse | Base rate lookup, dynamic adjustment | ITM ratio, `.clip()` for caps/floors |
| 5. Investment | Fund returns, account value, fees | `cum_prod()`, `previous_period(fill_value=1.0)` |
| 6. Policy counts | Survival, in-force, deaths, lapses | `cum_prod()`, `previous_period()`, `when/then` for maturity |
| 7. Claims | Death/lapse/maturity, guarantees | Nested `when/then` for GMDB/GMAB |
| 8. Premiums | Single/regular, timing | `when(duration_mth_t == 0)` for single premium |
| 9. Expenses | Acquisition + maintenance, inflation | exp/log identity for `constant^list` |
| 10. Net cashflow | Investment income, AV change | `next_period(fill_value=0.0)` |
| 11. Discounting | Rate lookup or constant, PVs | `cum_prod(1/(1+r))` for varying rates, `.list.sum()` |

**Important**: Section ordering may change based on dependencies. For example, if dynamic lapse depends on account value (ITM ratio), move the AV section before lapse. The tutorial Level 3 Steps 04-05 demonstrate this reordering.

### Key Accessor Methods

Always look these up with `gspio docs` before using. Here's the landscape:

| Accessor | Key Methods |
|----------|------------|
| `.projection` | `cumulative_survival()`, `prospective_value()`, `previous_period()`, `next_period()`, `at_period()`, `with_period()` |
| `.finance` | `to_monthly()`, `compound()`, `discount_factor()`, `present_value()` |
| `.excel` | `pv()`, `yearfrac()`, `from_excel_serial()` |
| `.list` | `.sum()`, `.mean()`, `.cumsum()`, `.head()` |

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
