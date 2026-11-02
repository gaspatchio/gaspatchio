# Curves and Scheduling

Term-structure discounting with `Curve` and explicit schedule construction with
`Schedule`. Both modules are public in `gaspatchio`; this reference covers
construction, the key patterns, and the actuarial rationale for each.

---

## Term-Structure Discounting with `Curve`

### When to use `Curve`

Most short-duration models discount at a single flat rate. The two paths are:

| Discounting approach | Use when |
|----------------------|----------|
| `projection.prospective_value(discount_rate=0.03)` | Single flat rate, quick sensitivity analysis |
| `Curve.discount_factor(af.projection.t_years())` | Yield-curve input required (Solvency II, IFRS 17, EIOPA, rate-scenario stress) |

`Curve` is the upgrade path, not the default. The flat-rate approach in
`prospective_value` remains correct whenever a single discount rate is the
contractual or regulatory basis.

---

### Constructing a Curve

`Curve` is a frozen dataclass. Construct via classmethods — direct instantiation
is intentionally awkward.

#### From zero (spot) rates

```python
from gaspatchio import Curve

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
- A `Curve`'s default day count is `ActualActualISDA` (a `Schedule`'s is `OneTwelfth`, below).
  Override via `day_count=`.

#### From par (coupon swap) rates — bootstrap

```python
# Boot-strap par coupon rates to zero rates — contiguous annual tenors, starting at 1
par_curve = Curve.from_par_rates(
    tenors=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
    par_rates=[0.028, 0.030, 0.031, 0.032, 0.033, 0.034, 0.035, 0.036, 0.037, 0.038],
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
from gaspatchio import Curve

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
nss_fit = Curve.fit_svensson(  # needs >=6 observations — one per NSS parameter
    tenors=[1, 2, 5, 10, 20, 30],
    rates=[0.030, 0.032, 0.035, 0.037, 0.038, 0.039],
)

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

### Per-period discounting — read the curve through the recorded door

**Recommended: call `Curve.discount_factor()` on a tracked time column.** This is
both the fast path and the audited one, and the two no longer trade against each
other:

```python
af.t_years = af.projection.t_years()                    # tracked list column, length n_periods + 1
af.discount_factor = rfr_curve.discount_factor(af.t_years)
af.pv_net_cf = (af.net_cf * af.discount_factor).list.sum()
```

- **Audited.** `curve.discount_factor` on a tracked column is a recorded
  core-tier operation. The node carries the curve's own `source_sha`, and the
  audit artifact grows an assumption entry holding the curve's `canonical_form()`
  — so a reviewer re-hashes the knots the liabilities were discounted on, and a
  quarter-over-quarter comparison can say *which* curve moved.
- **Fast.** It lowers through the `curve_eval` and `list_pow` Rust kernels — one
  pass over the list column, no `map_elements` in the lazy graph.
- **Works on any grid.** Because it evaluates per row, a jagged per-policy
  timeline (`from_per_policy_grid`, or `until_value=` a column) discounts on each
  policy's own `t` vector. Pre-computing cannot do this at all.

**Measured**, 10,000 policies on a shared monthly grid of 120 periods, whole
model end-to-end through `.collect()`, on a sixteen-thread laptop with eight
physical cores (medians of nine interleaved repetitions, loadavg 1.2–4.1).
**Every time below is on the streaming engine** — the one
`ActuarialFrame.collect()` uses unless you ask for another — because the door
costs four times as much on the in-memory one, so a time without an engine
beside it is not a time:

| Path | Time (streaming) | Recorded? |
|------|------|-----------|
| `curve.discount_factor(af.t_years)` — recorded door | **~28 ms** | Yes — curve `source_sha` + assumption entry |
| the same projection built and `af.t_years` materialised, discount factors broadcast in — **the like-for-like broadcast** | ~17 ms | No — nothing ties the values to the curve |
| `pl.lit(pre_computed_df)` with no projection built at all — **the bare broadcast** | ~9 ms | No — nothing ties the values to the curve |
| the same discounting hand-rolled through `map_elements` | ~0.63 s–1.44 s — set by your callable | No — the curve is inside a Python callable, so the artifact never sees it, and because the line *does* read a column no *validator* warning fires either (the runtime's own telemetry logger does warn on `map_elements`, twice per call — a clean artifact is a different thing from a quiet run) |

**Rows two and three are different comparisons, and this page keeps them apart by
name.** The **like-for-like broadcast** builds the same projection the door does and
swaps only the discounting — that is the comparison a model faces. The **bare
broadcast** builds no projection at all, so it also books the projection scaffolding
to the curve read. Every multiple below says which of the two it is divided by.

**That last row is a range because the cost is the Python callable, not the
framework.** Three correct spellings of the same discounting, timed here against the
streaming door: a plain-Python spot-and-compound hand-roll with the segment table
hoisted out of the callable reads ~0.63 s, about **21x** the door; handing the row
straight to the curve (`curve.discount_factor(ts)`) reads ~0.97 s, about **33x**;
re-deriving the spot rate with the `oracle_spot()` that `04_curve_discounting.py`
already defines — the function a reader of that pattern is likeliest to reuse —
costs ~1.41 s, about **48x**. Same discounting, same PV, and the multiple more than
doubles across the three, so quote it against the callable you actually wrote rather
than off this page.

**Budget against the like-for-like broadcast: under 2x on the engine `collect()`
uses.** A real model has a projection either way — its `net_cf` came from one — so
`projection.set` and `t_years()` are not part of what the curve read buys you. Hold
them equal and vary only the discounting, and on the **streaming** engine the
recorded door costs **1.6x–1.9x** the like-for-like broadcast: 1.60x–1.88x at
10,000 × 120 over seven runs, 1.90x–1.94x at 100,000 × 120, 1.71x–1.74x at
10,000 × 360. It drifts upward with policy count rather than standing still, so
carry the range and not a point. On the **in-memory** engine the same comparison
reads **10.0x–15.5x** — 10.8x and 12.2x at 10,000 × 120, 15.5x at 100,000 × 120, 10.0x
at 10,000 × 360 — and it stands still on no axis there either. The door against the
bare broadcast is a different and larger number, because that comparison books the
projection scaffolding to the curve read as well; that difference is real, but it is
not the one a model actually faces.

**That multiple travels furthest on the engine axis and the thread axis, and least
on the scale axis.** The band above is a threaded one on the streaming engine, sixteen
threads on this machine, loadavg 1.2–4.1. Pin it (`POLARS_MAX_THREADS=1`) and the
same comparison reads **~10.6x** — ~113 ms against ~10.7 ms — because the door
parallelises about 4x and the like-for-like broadcast it is divided by does not: the
broadcast is in fact *faster* on one thread, ~10.7 ms against ~17.5 ms. Pinned
streaming lands almost exactly where free-running in-memory does — 113 / 10.7 / 8.3 ms
against 115 / 10.6 / 8.3 ms for door / like-for-like / bare — and that is the whole of
the mechanism: the door's speed on the default engine *is* its parallelism, so an
engine or a thread count that takes that away moves the multiple from under 2x to
over 10x. Quote the figure with the engine and the thread count it was measured on;
without both it is not a figure.

**The two whole-script figures are each stable on one axis and only one.** Say which
axis you are quoting, because a figure moved onto the other one is simply wrong.
Streaming, sixteen threads, for all six cells:

| Figure | 10,000 × 120 | 100,000 × 120 | 10,000 × 360 | Holds still across… |
|---|---|---|---|---|
| ratio (door ÷ the bare broadcast) | 3.3x | 3.6x | 3.4x | **scale** — one machine, one engine, one load |
| delta (door − the bare broadcast) | ~20 ms | ~196 ms | ~55 ms | **machines** — one fixed scale |

The ratio barely moves over a tenfold change in policies and a threefold change in
grid; the delta moves an order of magnitude over the same range, because the door
evaluates the curve once per policy per period and the count of those *is* the job.
Re-time the same scale somewhere else and it is the other way round — the delta is
what reproduces, and the ratio is not. So neither is a band to carry off this page:
re-time on the job you actually run. The denominator makes that advice sharper than
it sounds — single repetitions of the bare broadcast ran 4.5 ms to 13.4 ms across
sixty-three of them here, which against a fixed ~28 ms numerator spans the ratio
from 2.1x to 6.4x on its own.

**Threads land very unevenly across the four rows, and hardest on the door.** Pinned
to a single thread (`POLARS_MAX_THREADS=1`) the door takes ~110–113 ms at
10,000 × 120 against ~28 ms on sixteen — 4.0x out of eight physical cores, and the
same 4.0x at 100,000 × 120 and at 10,000 × 360 — and the
whole-script ratio goes to **13x–16x** at all three scales. The bare broadcast and the
`map_elements` row gain nothing measurable: each lands within a few per cent of its
threaded time on one thread. The like-for-like broadcast goes the other way and is
*faster* pinned, ~10.7 ms against ~17.5 ms, because on this job sixteen threads cost
it more to coordinate than they save it in work.
The multiple you measure is therefore set by how many cores the door gets: give it
fewer, by pinning or on a machine busy enough to contend for them, and the door moves a
long way while the other three barely move at all.

**Escape hatch — pre-compute in Python and broadcast.** On a *shared uniform*
grid every policy has the same `t`, so the DF vector can be computed once outside
the frame and handed over as a list literal. It gives the identical numbers about
1.7x quicker like-for-like on the streaming engine, in a model that has its
projection either way — ~11 ms saved at 10,000 × 120, ~130 ms at 100,000 × 120 —
because it does one curve evaluation per period rather than one per policy per
period:

```python
import polars as pl

t_years_list = sched.cumulative_year_fractions()        # Python list[float] (from a Schedule, below)
disc_factors = rfr_curve.discount_factor(t_years_list)  # computed ONCE → list[float]
af.discount_factor = pl.lit(disc_factors, dtype=pl.List(pl.Float64))  # broadcast, unrecorded
af.pv_net_cf = (af.net_cf * af.discount_factor).list.sum()
```

**The audit cost, in one sentence:** `pl.lit(...)` reads no column of the model
and names no assumption base, so nothing in the artifact ties those discount
factors to the curve — no assumption entry, no `source_sha`, nothing for next
quarter's comparison to attribute a movement to — and the artifact validator
warns on exactly that shape. On the engine `collect()` uses, the like-for-like
broadcast buys under a doubling — about 11 ms at 10,000 policies and about 130 ms at
100,000 — which is a poor price for the lineage; on the in-memory engine, or pinned
to one thread, it buys ~104 ms and ~1.0 s instead and the price is still the lineage.
Take the hatch only when a *measured* bottleneck justifies it, and say in the model
why.

The flat-rate built-in stays valid and correct for single-rate discounting:

```python
af.pv_net_cf = af.net_cf.projection.prospective_value(discount_rate=0.03)
```

---

### Curve stress — parallel and key-rate shifts

`Curve` stress methods return new `Curve` instances, leaving the original
unchanged. Each stressed curve is a plain Python object you hand to a scenario
yourself — see the dispatch note below the examples.

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

**There is no curve shock, so a stressed curve cannot ride the shock dispatch.**
A shock moves a `Table` or a model-point column; a `Curve` is neither, and
`ScenarioRun.run()` has no parameter that would carry one. Build the
stressed curves yourself, as above, and give each scenario **its own `Curve`
object** through the drivers shape of `for_each_scenario` at `batch_size=1`, which
calls the model once per scenario and forwards the drivers to it. Anything else —
one run, one curve, a `scenario_id` column that changes nothing — produces
scenario rows that all carry the base answer. See
[references/scenarios.md](scenarios.md) for the worked call and for what the
record then carries.

---

### Schedule-based pre-computation — the escape hatch in full

The recorded door above needs no `Schedule` of its own: `af.projection.t_years()`
already gives the projection's cumulative year fractions as a tracked column. Build
an explicit `Schedule` when you are taking the pre-compute-and-broadcast escape
hatch and need the same year fractions as a Python `list[float]`:

```python
from datetime import date
from gaspatchio import Curve, Schedule

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

# Broadcast into the model as a literal — zero per-row overhead, and no record
import polars as pl
af.discount_factor = pl.lit(disc_factors_list, dtype=pl.List(pl.Float64))
af.pv_net_cf = (af.net_cf * af.discount_factor).list.sum()
```

Two conditions have to hold before this is available at all. The grid must be
**shared and uniform** — the moment `t` differs by policy the single vector is
wrong, and only the recorded door still works. And the curve must be **static**
across the run; a scenario that re-points the curve needs the pre-compute moved
with it, which is one more thing to keep in step by hand.

What you give up is the record: the broadcast column reads no input and names no
assumption base, so the artifact cannot say the numbers came off this curve. Weigh
that against a like-for-like multiple of under 2x on the streaming engine, whose
absolute size is whatever your scale makes it — ~11 ms saved at 10,000 policies ×
120 periods, ~130 ms at 100,000 × 120 — before reaching for it.

---

### Flat rate vs yield curve — guidance

| Situation | Approach |
|-----------|----------|
| Single discount rate, fixed across scenarios | `prospective_value(discount_rate=r)` |
| EIOPA / SII risk-free rate (term structure) | `Curve.from_zero_rates(…)` + `curve.discount_factor(af.projection.t_years())` |
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

- `cumulative_year_fractions()` — a Python `list[float]` of the grid's year fractions, for the pre-compute-and-broadcast escape hatch (see above); the recorded path uses `af.projection.t_years()` and needs no explicit `Schedule`.
- Per-policy inception-anchored period grids (`from_inception`).
- Non-default `Calendar`, `DayCount`, or `BusinessDayConvention`.
- Per-policy variable-length (jagged) timelines with their own horizon column (`from_per_policy_grid`).
- An axis of fixed steps in years with no calendar under it (`fixed_step`) — the same axis as
  `af.projection.set(n_periods=..., step_years=...)`; see
  [model-phases.md](model-phases.md#off-calendar-workbooks-a-fixed-step-axis).

---

### Three constructors

#### `from_calendar_grid` — shared grid, same dates for all policies

Use for cohort aggregation, SII reporting, or any model where all policies share
a common valuation grid.

```python
from datetime import date
from gaspatchio import Schedule

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
from gaspatchio import Schedule

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
from gaspatchio import Schedule

sched = Schedule.from_per_policy_grid(
    start_date=date(2025, 1, 31),
    frequency="1M",
    until_kind="term_months",            # "term_months" or "term_years"
    until_value_column="remaining_term", # column of per-policy horizon lengths
)

# Per-policy variable-length list expressions
dates_expr = sched.per_policy_period_dates_expr()   # pl.Expr → List<Date>
count_expr = sched.per_policy_period_count_expr()   # pl.Expr → Int64 (per-policy length)
```

The grid takes no `n_periods`: each policy's length is its own column, so no
other policy's horizon is part of the schedule's identity, and a model's
`graph_fingerprint` stays put when another policy's term changes or the book
runs in batches. The longest horizon in a run is in the run record
(`run_metadata.n_periods`).

---

### Supporting types

```python
from gaspatchio import (
    Calendar,           # Abstract base
    DayCount,           # Abstract base
    BusinessDayConvention,
)
from gaspatchio.schedule import (
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
from gaspatchio import Schedule
from gaspatchio.schedule import ActualActualISDA

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
from gaspatchio import Schedule
from gaspatchio.schedule import TARGET
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
Is the axis a calendar at all? (dates, months, a valuation date)
└── No — k steps of h years, no dates → Schedule.fixed_step(n_periods=, step_years=h)
                                         or Schedule.fixed_step(n_periods=, steps_per_year=n)

Do all policies share the same period grid?
├── Yes → Schedule.from_calendar_grid(start_date=, n_periods=, frequency=)
│         └── Need cumulative year fractions for Curve? → .cumulative_year_fractions()
└── No — each policy has its own inception date?
    ├── Yes, same projection length → Schedule.from_inception(inception_column=, n_periods=, frequency=)
    └── Yes, variable-length horizon → Schedule.from_per_policy_grid(start_date=, frequency=,
                                         until_kind=, until_value_column=)

Need t for Curve.discount_factor?
└── Any grid, shared or per-policy → af.projection.t_years() # tracked column; recorded + kernel-lowered
    └── Escape hatch, shared uniform grid only, unrecorded:
        sched.cumulative_year_fractions() → pl.lit(...)      # returns list[float]
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
> - [scenarios.md](scenarios.md) — the cross-join boundary, and one `Curve` per scenario through the drivers shape
