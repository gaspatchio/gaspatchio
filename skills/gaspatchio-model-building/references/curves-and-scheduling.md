# Curves and Scheduling

Term-structure discounting with `Curve` and explicit schedule construction with
`Schedule`. Both modules are public in `gaspatchio_core`; this reference covers
construction, the key patterns, and the actuarial rationale for each.

---

## Term-Structure Discounting with `Curve`

### When to use `Curve`

Most short-duration models discount at a single flat rate. The two paths are:

| Discounting approach | Use when |
|----------------------|----------|
| `projection.prospective_value(discount_rate=0.03)` | Single flat rate, quick sensitivity analysis |
| `Curve` + pre-computed DF (see below) | Yield-curve input required (Solvency II, IFRS 17, EIOPA, rate-scenario stress) |

`Curve` is the upgrade path, not the default. The flat-rate approach in
`prospective_value` remains correct whenever a single discount rate is the
contractual or regulatory basis.

---

### Constructing a Curve

`Curve` is a frozen dataclass. Construct via classmethods — direct instantiation
is intentionally awkward.

#### From zero (spot) rates

```python
from gaspatchio_core import Curve

# EIOPA-style EUR zero-rate curve (illustrative; not official data)
rfr_curve = Curve.from_zero_rates(
    tenors=[0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0],
    rates=[0.025, 0.028, 0.030, 0.031, 0.032, 0.033, 0.035, 0.036, 0.037, 0.038],
)
```

Rules:
- `tenors` must be strictly increasing, at least two knots.
- `rates` same length as `tenors`.
- Interpolation between knots is selectable via `interpolation=` (default
  `"linear"`); flat extrapolation outside the knot range (first/last rate holds
  to any tenor beyond the grid). See [Interpolation methods](#interpolation-methods).
- Default day-count: `ActualActualISDA`. Override via `day_count=`.

#### From par (coupon swap) rates — bootstrap

```python
# Boot-strap par coupon rates to zero rates — annual tenors only, starting at 1
par_curve = Curve.from_par_rates(
    tenors=[1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0, 30.0],
    par_rates=[0.028, 0.030, 0.031, 0.032, 0.033, 0.035, 0.037, 0.038],
)
```

`from_par_rates` requires contiguous integer tenors starting at 1 — it runs a
coupon-stripping bootstrap to derive zero rates. Use `from_zero_rates` if you
already have zero rates (the more common case for EIOPA / regulatory inputs).

---

### Interpolation methods

`from_zero_rates` / `from_par_rates` take an `interpolation=` keyword. All three
methods pass through the input knots exactly and flat-extrapolate beyond the grid;
they differ only *between* knots:

| `interpolation=` | Between knots | Use when |
|------------------|---------------|----------|
| `"linear"` (default) | Straight line on the zero rates | Default; matches most EIOPA / regulatory inputs |
| `"log_linear"` | Linear in log-discount-factor space (piecewise-constant instantaneous forwards) | Money-market / standard bootstrapping convention |
| `"pchip"` | Fritsch-Carlson monotone cubic Hermite — smooth but shape-preserving (no overshoot) | A smooth curve is wanted without the overshoot a plain cubic spline introduces |

```python
from gaspatchio_core import Curve

knots = {"tenors": [1.0, 2.0, 5.0, 10.0], "rates": [0.020, 0.025, 0.030, 0.033]}
linear = Curve.from_zero_rates(**knots)                          # default
loglin = Curve.from_zero_rates(**knots, interpolation="log_linear")
smooth = Curve.from_zero_rates(**knots, interpolation="pchip")
```

### Parametric curves — Svensson (NSS) and Smith-Wilson

For a curve defined by a *formula* rather than knot interpolation — the published
central-bank form, or the regulatory extrapolation to an ultimate rate — use the
parametric constructors. Both return an ordinary `Curve`; `spot_rate` /
`discount_factor` / stress methods all work identically.

```python
# Nelson-Siegel-Svensson — the form the Fed and ECB publish (six parameters)
nss = Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0)
nss_fit = Curve.fit_svensson(tenors=[1, 2, 5, 10, 30], rates=[0.030, 0.032, 0.035, 0.037, 0.039])

# Smith-Wilson — the EIOPA / Solvency II extrapolation to an Ultimate Forward Rate.
# Fits the liquid knots, then pulls smoothly to `ufr` beyond the last point.
sw = Curve.fit_smith_wilson(
    tenors=[1.0, 2.0, 4.0, 5.0, 6.0, 7.0],
    rates=[0.01, 0.02, 0.03, 0.032, 0.035, 0.04],
    ufr=0.04,        # ultimate forward rate
    alpha=0.15,      # convergence speed; omit to auto-calibrate to the EIOPA floor (0.05)
)
```

- `from_svensson` takes the six NSS parameters directly; `fit_svensson` calibrates
  them to market knots. `spot_rate(t)` is **annually compounded** (`exp(r_cc) - 1`,
  with `r_cc` the continuously-compounded Svensson rate).
- `fit_smith_wilson` reproduces the liquid input knots and extrapolates to `ufr`.
  Leave `alpha=None` to auto-calibrate; a supplied `alpha` below the `0.05` EIOPA
  floor is rejected.
- A runnable, fully-asserted walk-through of all five methods (the three
  interpolations + NSS + Smith-Wilson, each checked against a closed form or the
  published lifelib oracle) lives in
  `tutorial/patterns/curves-and-scheduling/05_interpolation_methods.py`.

---

### Query methods

All query methods accept `float | list[float] | np.ndarray | pl.Series | pl.Expr`
and return a matching shape.

```python
# Scalar queries
rfr_curve.spot_rate(5.0)           # → float: interpolated zero rate at 5y
rfr_curve.discount_factor(5.0)     # → float: (1 + r(5))^(-5)
rfr_curve.discount_factor(0.0)     # → 1.0 always

# List query
rfr_curve.discount_factor([1.0, 2.0, 5.0])   # → list[float]

# Forward rate (scalar only — t1 and t2 are keyword-only)
rfr_curve.forward_rate(t1=1.0, t2=5.0)       # → float: annual forward 1y→5y
```

`discount_factor` uses annually-compounded convention: `DF(t) = (1 + r(t))^(-t)`.
This is the canonical choice; continuously-compounded discounting is not yet
supported.

---

### Per-period discounting — production pre-computes, never `map_elements`

`Curve.discount_factor()` on a **scalar or a Python `list[float]`** is pure and
fast. But calling it on a **list column** (`af.projection.t_years()` is a
`ColumnProxy`/`pl.Expr`) falls back to `map_elements` internally — which the
framework's performance rules forbid (~14x slower; defeats vectorization). It is
acceptable only for a one-off single-policy debug check, never a portfolio run.

**Production (recommended) — pre-compute the discount-factor vector once and
broadcast it.** The curve is static and, on a uniform schedule, every policy
shares the same `t` grid, so you compute the DF list once in Python (no per-row
work) and broadcast it as a literal. Full setup in
[Schedule-based pre-computation](#schedule-based-pre-computation) below:

```python
import polars as pl

t_years_list = sched.cumulative_year_fractions()        # Python list[float] (from a Schedule, below)
disc_factors = rfr_curve.discount_factor(t_years_list)  # computed ONCE → list[float]
af.discount_factor = pl.lit(disc_factors, dtype=pl.List(pl.Float64))  # broadcast, zero per-row cost
af.pv_net_cf = (af.net_cf * af.discount_factor).list.sum()
```

**Debug only (single policy)** — the inline list-column form reads nicely but
`map_elements`; fine under `run-single-policy`, never ship it in a model:

```python
# DEBUG ONLY — map_elements path; do not use for a portfolio run
af.t = af.projection.t_years()
af.discount_factor = rfr_curve.discount_factor(af.t)   # ⚠ map_elements
af.pv_net_cf = (af.net_cf * af.discount_factor).list.sum()
```

The flat-rate built-in stays valid and correct for single-rate discounting:

```python
af.pv_net_cf = af.net_cf.projection.prospective_value(discount_rate=0.03)
```

---

### Curve stress — parallel and key-rate shifts

`Curve` stress methods return new `Curve` instances, leaving the original
unchanged. This composability integrates directly with the scenario system.

```python
# Parallel shift — all knot rates move together
rfr_up100 = rfr_curve.shift_parallel(bps=100)   # +100bp everywhere
rfr_dn75  = rfr_curve.shift_parallel(bps=-75)   # −75bp everywhere

# Key-rate shift — single knot moves; others held
rfr_kr10  = rfr_curve.key_rate_shift(tenor=10.0, bps=25)   # 10y knot +25bp

# Basis-point magnitude: 100 bps = 1 percentage point (bps=100 means +0.01 to rates)
```

`key_rate_shift` requires `tenor` to be an exact member of the curve's knots.
Use the curve's own knot list (`rfr_curve.tenors`) to check or loop:

```python
for tenor in [2.0, 5.0, 10.0, 20.0, 30.0]:
    if tenor in rfr_curve.tenors:
        bumped = rfr_curve.key_rate_shift(tenor=tenor, bps=25)
        ...
```

Stress curves integrate with the `ScenarioRun` / shock system — build stressed
`Curve` objects outside the model, pass them in via `assumptions_override`, and
let the scenario runner handle the dispatch. See
[references/scenarios.md](scenarios.md) for the full two-script pattern.

---

### Schedule-based pre-computation

For portfolio-scale runs (many policies), pre-compute discount-factor lists once
using `Schedule.cumulative_year_fractions()` and broadcast them rather than
computing per-row via a list-column expression:

```python
from datetime import date
from gaspatchio_core import Curve, Schedule

rfr_curve = Curve.from_zero_rates(
    tenors=[1.0, 5.0, 10.0, 20.0, 30.0],
    rates=[0.028, 0.032, 0.035, 0.037, 0.038],
)

# Build a shared monthly schedule for the projection horizon
sched = Schedule.from_calendar_grid(
    start_date=date(2025, 1, 31),   # valuation date, normalised to month-end
    n_periods=360,                   # 30 years monthly
    frequency="1M",
)
# cumulative_year_fractions() returns list of length n_periods+1: [0, 1/12, 2/12, ...]
t_years_list = sched.cumulative_year_fractions()

# Compute discount factors once as a Python list[float]
disc_factors_list = rfr_curve.discount_factor(t_years_list)

# Broadcast into the model as a literal — zero per-row overhead
import polars as pl
af.discount_factor = pl.lit(disc_factors_list, dtype=pl.List(pl.Float64))
af.pv_net_cf = (af.net_cf * af.discount_factor).list.sum()
```

Pre-computing once is the only optimize-safe way to apply a static curve across a
uniform projection — it keeps `map_elements` out of the lazy graph entirely. (For
a jagged / per-policy grid the `t` lists differ by policy, so pre-broadcast does
not apply; fall back to a flat rate or a per-period rate column fed to
`af.finance.discount_factor(rate_col, periods_col, output_col)`, the Rust
`list_pow` path.)

---

### Flat rate vs yield curve — guidance

| Situation | Approach |
|-----------|----------|
| Single discount rate, fixed across scenarios | `prospective_value(discount_rate=r)` |
| EIOPA / SII risk-free rate (term structure) | `Curve.from_zero_rates(…)` + pre-computed DF broadcast |
| Regulatory rate stress (parallel shift) | `rfr_curve.shift_parallel(bps=N)` + re-run |
| Key-rate sensitivity (one tenor at a time) | `rfr_curve.key_rate_shift(tenor=T, bps=N)` + re-run |
| Monthly discount factor from annual rate | `finance.to_monthly(method="compound")` still valid — flat-rate path |

---

## Explicit Schedules with `Schedule`

### When to use `Schedule` explicitly

Most models never construct a `Schedule` directly — `af.projection.set()` builds
one internally from its keyword arguments:

```python
af = af.projection.set(
    valuation_date=datetime.date(2025, 1, 1),
    until="term_months",
    until_value="remaining_term_months",
    frequency="monthly",
)
```

Use a `Schedule` explicitly when you need:

- `cumulative_year_fractions()` — to feed `Curve.discount_factor(t_years)` (see above).
- Per-policy inception-anchored period grids (`from_inception`).
- Non-default `Calendar`, `DayCount`, or `BusinessDayConvention`.
- Per-policy variable-length (jagged) timelines with their own horizon column (`from_per_policy_grid`).

---

### Three constructors

#### `from_calendar_grid` — shared grid, same dates for all policies

Use for cohort aggregation, SII reporting, or any model where all policies share
a common valuation grid.

```python
from datetime import date
from gaspatchio_core import Schedule

sched = Schedule.from_calendar_grid(
    start_date=date(2025, 1, 31),   # normalised to month-end by default
    n_periods=240,                   # 20 years monthly
    frequency="1M",                  # "1M" | "3M" | "6M" | "1Y" | "1W" | "1D"
)

# Access period boundaries as a Python list (calendar_grid only)
boundaries = sched.period_dates()               # list[date], length n_periods+1
t_years    = sched.cumulative_year_fractions()  # list[float], length n_periods+1
per_period = sched.year_fractions()             # list[float], length n_periods
```

`anchor` defaults to `"month_end"` — a mid-month `start_date` is normalised to
the last day of that month, matching US/UK/EU production practice. Options:
`"month_end"` (default), `"exact_date"`, `"month_start"`, `"year_end"`.

#### `from_inception` — per-policy, anchored on an inception-date column

Use when each policy has its own inception date and the period boundaries should
be anniversaries of that date.

```python
from gaspatchio_core import Schedule

sched = Schedule.from_inception(
    inception_column="contract_inception",  # column name in the DataFrame
    n_periods=360,                           # maximum projection periods
    frequency="1M",
)

# Expression-based methods — evaluated per-row
dates_expr   = sched.period_dates_expr()        # pl.Expr → List<Date>
yf_expr      = sched.year_fractions_expr()      # pl.Expr → List<Float64>
anniv_expr   = sched.anniversary_mask_expr()    # pl.Expr → List<Boolean>
```

There is no `anchor` parameter for `from_inception` — the inception column IS
the anchor. Period boundaries are the anniversary dates of each policy's own
inception date.

#### `from_per_policy_grid` — per-policy jagged timeline

Use when each policy has its own remaining horizon stored in a column. Every
policy gets a different number of projection periods.

```python
from datetime import date
from gaspatchio_core import Schedule

sched = Schedule.from_per_policy_grid(
    start_date=date(2025, 1, 31),
    n_periods=360,                       # portfolio maximum (for reference / error messages)
    frequency="1M",
    until_kind="term_months",            # "term_months" or "term_years"
    until_value_column="remaining_term", # column of per-policy horizon lengths
)

# Per-policy variable-length list expressions
dates_expr = sched.per_policy_period_dates_expr()   # pl.Expr → List<Date>
count_expr = sched.per_policy_period_count_expr()   # pl.Expr → Int64 (per-policy length)
```

---

### Supporting types

```python
from gaspatchio_core import (
    Calendar,           # Abstract base
    DayCount,           # Abstract base
    BusinessDayConvention,
)
from gaspatchio_core.schedule import (
    NullCalendar,       # Default — every day is a business day
    TARGET,             # TARGET2 / Eurozone
    UnitedKingdom,      # England-and-Wales bank holidays
    UnitedStates,       # US federal holidays
    OneTwelfth,         # Default — constant 1/12 per month
    ActualActualISDA,   # Act/Act ISDA — precise leap-year handling
    Actual365Fixed,     # Act/365F — UK sterling and EIOPA sub-annual
    Actual360,          # Act/360 — USD money-market
    Thirty360,          # 30/360 ISDA Bond Basis
)
```

**Calendar:** `NullCalendar` is the default for life-insurance liability
projections (matches VM-20/VM-21/IFRS 17 practice — no business-day adjustment).
Use `TARGET`, `UnitedKingdom`, or `UnitedStates` for asset-side cashflow
modelling or when your contract dates must follow the relevant holiday calendar.

**DayCount:** `OneTwelfth` is the default (constant `1/12` per monthly period,
matches ~80% of life-insurance production). For precise EIOPA / SII calculations,
use `ActualActualISDA`:

```python
from datetime import date
from gaspatchio_core import Schedule
from gaspatchio_core.schedule import ActualActualISDA

sched = Schedule.from_calendar_grid(
    start_date=date(2025, 12, 31),
    n_periods=60,
    frequency="1M",
    day_count=ActualActualISDA(),   # correct year fractions across leap years
)
```

**BusinessDayConvention:** When `calendar=NullCalendar()` (the default), the
convention is `UNADJUSTED` automatically. When you pass a real calendar, the
default flips to `MODIFIED_FOLLOWING`:

```python
from gaspatchio_core import Schedule
from gaspatchio_core.schedule import TARGET
from datetime import date

sched = Schedule.from_calendar_grid(
    start_date=date(2025, 12, 31),
    n_periods=120,
    frequency="1M",
    calendar=TARGET(),   # ModifiedFollowing convention applied automatically
)
```

Override explicitly with `convention=BusinessDayConvention.UNADJUSTED` if
needed.

---

### Quick-reference: constructor decision tree

```
Do all policies share the same period grid?
├── Yes → Schedule.from_calendar_grid(start_date=, n_periods=, frequency=)
│         └── Need cumulative year fractions for Curve? → .cumulative_year_fractions()
└── No — each policy has its own inception date?
    ├── Yes, same projection length → Schedule.from_inception(inception_column=, n_periods=, frequency=)
    └── Yes, variable-length horizon → Schedule.from_per_policy_grid(start_date=, n_periods=, frequency=,
                                         until_kind=, until_value_column=)

Need t_years for Curve.discount_factor?
├── Shared grid → sched.cumulative_year_fractions()          # returns list[float]
└── Per-policy → af.projection.t_years()                     # returns pl.Expr → List<Float64>
```

---

### Verify before writing

```bash
uv run gspio docs "Schedule.from_calendar_grid"
uv run gspio docs "Schedule.cumulative_year_fractions"
uv run gspio docs "Curve.discount_factor"
uv run gspio docs "Curve.from_zero_rates"
```

---

> **Related references**
>
> - [model-phases.md](model-phases.md) — Phase 2 timeline setup, `af.projection.t_years()`
> - [scenarios.md](scenarios.md) — Curve stress, `ScenarioRun`, the two-script pattern
