# Curves and Scheduling

Five runnable scripts that exercise the **term-structure** (`Curve`) and
**scheduling** (`Schedule`, `DayCount`) primitives, and double as a reference
vocabulary for LLMs writing yield-curve discounting and projection-grid jobs
against this API.

Most short-duration models discount at a single flat rate. The moment a
regulatory basis hands you a *term structure* — a different zero rate at every
tenor (EIOPA, Solvency II, IFRS 17) — you reach for `Curve`. And the moment a
sub-annual projection has to be precise about *how much of a year* each period
is — across a leap February, say — you reach for an explicit `DayCount`. These
scripts build both from market inputs, query them, stress them, and discount a
cashflow with them, asserting each result against a hand-computed closed form.

Each script is self-contained — small inline inputs, the pattern, then an
`assert` that the output equals an independent closed-form / Python-dot-product
baseline. A clean run is the success signal.

| File | Pattern | Asserts |
|------|---------|---------|
| `01_curve_construction.py` | `Curve.from_zero_rates` + `spot_rate` / `discount_factor` / `forward_rate`; `Curve.from_par_rates` bootstrap | `DF(t)` == `(1 + spot(t))^(-t)` at every knot; `DF(0) == 1.0`; mid-knot `spot_rate` == hand linear interp; `forward_rate` == DF-implied forward; bootstrapped curve re-prices a 5y par bond to `1.0` |
| `02_curve_stress.py` | `shift_parallel(bps=100)`, `key_rate_shift(tenor=10.0, bps=25)` | Shifted `spot_rate` at each knot == base `+ 0.01` (+100bp); base curve **unchanged** after the shift (immutability); key-rate bump touches only the 10y knot; `key_rate_shift` on a non-knot tenor raises `ValueError` (caught) |
| `03_schedule_daycount.py` | `Schedule.from_calendar_grid` with `OneTwelfth()` vs `ActualActualISDA()`, spanning 2024 leap-Feb | `OneTwelfth` `year_fractions()` all exactly `1/12`; `ActualActualISDA` period 0 == `29/366` and period 1 == `31/366` (source-grounded hand calc); leap Jan→Feb is **below** 1/12, Feb→Mar **above**; the two totals disagree; `period_dates()` length == `n_periods + 1` |
| `04_curve_discounting.py` | The recorded door: `af.projection.t_years()` → `curve.discount_factor(<that column>)` → `(net_cf * df).list.sum()`; the pre-compute-and-broadcast escape hatch kept below it, labelled with its audit cost | Recorded DFs == a hand-derived spot-rate-and-compounding oracle (plain Python, no Gaspatchio) to 1e-12; recorded PV == that oracle's dot product; shared-grid policies share PV; the escape hatch returns the **identical** PV |
| `05_interpolation_methods.py` | Beyond default-linear: `interpolation="log_linear"` / `"pchip"`; `Curve.from_svensson` (Nelson-Siegel-Svensson); `Curve.fit_smith_wilson` (EIOPA / Solvency II) | Every method recovers its input rates at the knots; `log_linear` mid-knot == hand-built log-DF blend; `pchip` is monotone (no overshoot); NSS == independent Svensson eq.22 re-derivation + short/long limits; Smith-Wilson == published lifelib spot values at 3y / 20y |

## Running

```bash
uv run python \
    bindings/python/gaspatchio/tutorials/patterns/curves-and-scheduling/01_curve_construction.py
```

Swap in `02_curve_stress.py`, `03_schedule_daycount.py`,
`04_curve_discounting.py`, or `05_interpolation_methods.py`. Each script
asserts internally; a clean run with the printed reconciliation is the success
signal.

## API surface used

All imported from the **top level** — `Curve`, `Schedule`, and the day-counts
were promoted to `gaspatchio`:

```python
from gaspatchio import ActuarialFrame, Curve, Schedule, ActualActualISDA, OneTwelfth
```

- `Curve.from_zero_rates(tenors=, rates=, interpolation=)` — knot-based zero curve; `interpolation` is `"linear"` (default, linear-on-rates), `"log_linear"` (linear in log-DF), or `"pchip"` (monotone cubic Hermite); flat extrapolation outside the grid
- `Curve.from_par_rates(tenors=, par_rates=)` — coupon-stripping bootstrap (annual integer tenors from 1)
- `Curve.from_svensson(b0=, b1=, b2=, b3=, tau1=, tau2=)` — Nelson-Siegel-Svensson parametric curve (Fed / ECB published form); `Curve.fit_svensson(tenors=, rates=)` calibrates the six parameters to market knots
- `Curve.fit_smith_wilson(tenors=, rates=, ufr=, alpha=)` — EIOPA / Solvency II extrapolation: fits the liquid knots, pulls smoothly to the Ultimate Forward Rate
- `Curve.spot_rate(t)` — interpolated zero rate; scalar/list/ndarray/Series/Expr in, matching shape out
- `Curve.discount_factor(t)` — annually-compounded `DF(t) = (1 + r(t))^(-t)`; on a **tracked column** (`af.projection.t_years()`) it is a recorded core-tier operation publishing the curve's digest as the assumption entry's `fingerprint`, lowering through the `curve_eval` + `list_pow` Rust kernels
- `Curve.forward_rate(t1=, t2=)` — annually-compounded forward between two tenors (keyword-only, scalar)
- `Curve.shift_parallel(bps=)` / `Curve.key_rate_shift(tenor=, bps=)` — return a **new** stressed curve; `key_rate_shift` requires an exact knot
- `Schedule.from_calendar_grid(start_date=, n_periods=, frequency=, day_count=)` — shared grid; `anchor="month_end"` default
- `Schedule.period_dates()` — list of `n_periods + 1` boundary dates (calendar grid only)
- `Schedule.year_fractions()` — per-period year fractions under the schedule's day-count (length `n_periods`)
- `Schedule.cumulative_year_fractions()` — `[0, yf[0], yf[0]+yf[1], …]`, length `n_periods + 1`; feeds `Curve.discount_factor`
- `OneTwelfth()` / `ActualActualISDA()` — day-count conventions passed to `from_calendar_grid(day_count=)`
- `af.projection.t_years()` — the projection's own cumulative year fractions as a tracked list column, length `n_periods + 1`; the input `Curve.discount_factor` is meant to read
- `pl.lit(disc, dtype=pl.List(pl.Float64))` — broadcast a pre-computed DF vector as a list literal (the **escape hatch**: faster on a shared grid, but the values arrive with no recorded source)

## Conventions grounded from source

The reference docs can lag the implementation, so every numeric expectation in
these scripts was confirmed against the source — not a textbook variant:

- **`discount_factor` is annually compounded:** `DF(t) = (1 + r(t))^(-t)`
  (`curves/_curve.py:657` docstring, `:701` implementation). `DF(0.0) == 1.0`
  exactly. Continuously-compounded (`exp(-r·t)`) discounting is **not** supported
  — the compounding choice is canonical, not user-configurable.
- **`spot_rate` interpolates linearly on rates** between knots, with flat
  extrapolation outside the grid (`curves/_curve.py:604`, `:647`; the
  `linear_interpolate` path in `curves/_interpolation.py`). A mid-knot rate is
  the straight-line blend of the two surrounding knot rates.
- **`from_par_rates` bootstraps zero rates** with
  `DF(t) = (1 − p_t · Σ_{i<t} DF(i)) / (1 + p_t)` and `r_t = DF(t)^(−1/t) − 1`
  (`curves/_bootstrap.py`), so the derived curve re-prices the input par bonds
  back to par (1.0).
- **`OneTwelfth.year_fraction` is whole-months / 12** (`schedule/_day_count.py:60`)
  — every monthly period is **exactly** `1/12`, date-independent.
- **`ActualActualISDA.year_fraction` (same-year period)** is
  `(end − start).days / (366 if the year is leap else 365)`
  (`schedule/_day_count.py:166`). Across 2024 (a leap year): Jan 31 → Feb 29 is
  `29/366` ≈ 0.07923 (**below** 1/12); Feb 29 → Mar 31 is `31/366` ≈ 0.08470
  (**above** 1/12). Cross-year periods split the actual days at Jan 1 of the end
  year, each part over its own year's denominator.

## Gotchas these scripts encode

- **Discount through the recorded door: `curve.discount_factor(<a tracked
  column>)`.** It is a recorded core-tier operation — the curve's digest reaches
  the artifact as the assumption entry's `fingerprint`, and under the
  `executable` profile as the node's `expr.attrs.curve`, the same string, while
  the artifact carries the curve's canonical form — and it lowers to the
  `curve_eval` + `list_pow` Rust kernels, one pass over the list column with
  no `map_elements`. Measured at 10,000 policies × 120 monthly
  periods, end-to-end through `.collect()` on the streaming engine — the one
  `collect()` uses — on a sixteen-thread laptop with eight physical cores:
  ~28 ms, against ~0.63 s–1.44 s for the same discounting hand-rolled through
  `map_elements` — about **21x–48x**, and where in that range you land is set by
  the Python callable you wrote rather than by the framework (a plain-Python
  hand-roll with the segment table hoisted out of the callable costs ~0.63 s;
  handing the row straight to the curve, ~0.97 s; re-deriving the spot rate in
  Python, as `04`'s own `oracle_spot()` does, ~1.41 s). (No *validator* warning
  fires on that hand-roll, because the line does read a column; the runtime's
  telemetry logger warns on it twice per call regardless.)
- **Pre-compute-and-broadcast is the escape hatch, and it costs the record.**
  On a shared grid the DF vector can be computed once in Python from
  `cumulative_year_fractions()` and handed over with `pl.lit(…, dtype=pl.List(…))`
  — numerically identical, and **under 2x** quicker like-for-like on the engine
  `collect()` uses: hold `projection.set` and `t_years()` equal, as a real model
  does, and that **like-for-like broadcast** reads ~17 ms against the door's
  ~28 ms — 1.6x–1.9x at every scale measured here (1.60x–1.88x at 10,000 × 120,
  1.90x–1.94x at 100,000 × 120, 1.71x–1.74x at 10,000 × 360). That band is a
  **streaming, sixteen-thread** one and nothing else: on the in-memory engine the
  same comparison reads 10.0x–15.5x, and pinned to a single thread ~10.6x, because
  the door parallelises about 4x and the broadcast it is divided by does not.
  Skip the projection entirely, as the script's hatch does — the **bare
  broadcast** — and it reads ~9 ms: a bigger gap, but one that books the
  projection scaffolding to the curve read. On the whole-script comparison, the
  door against that bare broadcast, each figure is stable on one axis only: the
  ratio (3.3x, 3.6x, 3.4x on those three scales) across **scale**, on one machine
  at one engine and one load; the delta (~20 ms, ~196 ms, ~55 ms) across
  **machines**, at one fixed scale. Neither is a band to lift from someone else's
  portfolio — and threads land very unevenly across the four rows: the door reads
  ~110–113 ms pinned to a single thread against ~28 ms on sixteen (4.0x out of
  eight physical cores), the bare broadcast and the `map_elements` row
  gain nothing measurable, and the like-for-like broadcast is *faster* pinned
  (~10.7 ms against ~17.5 ms). So re-time on the job you actually run. But `pl.lit()`
  reads no column and names no assumption base, so nothing in the artifact ties
  those numbers to the curve, and the artifact validator warns on the shape. Take
  it only when a measured bottleneck justifies giving up the lineage.
  `04_curve_discounting.py` teaches the recorded door and keeps the hatch below
  it, labelled.
- **Curve stress returns a new curve; the base is immutable.** `shift_parallel`
  / `key_rate_shift` never mutate the original — safe to fan out scenarios from
  one base curve.
- **`key_rate_shift` requires an exact knot.** A non-knot tenor raises
  `ValueError` rather than guessing an interpolated bump.
- **`anchor="month_end"` (the default) lands the February boundary on the leap
  day** (Feb 29 in 2024), which is what makes the Act/Act contrast visible.

## Provenance

- **Zero curves, forward rates, bootstrapping** (`Curve`): Hull, J. C.,
  *Options, Futures & Other Derivatives*, Pearson — the standard reference for
  term-structure construction and forward-rate consistency.
- **Risk-free term structure** (the regulatory `Curve` input shape): EIOPA
  risk-free interest-rate term-structure technical documentation — the published
  zero-rate curves and parallel interest-rate shocks that drive Solvency II
  valuations.
- **Parametric curves and extrapolation** (`from_svensson` / `fit_smith_wilson`):
  Svensson (1994), *Estimating and Interpreting Forward Interest Rates* (the
  Fed / ECB-published NSS form); Smith & Wilson (2001) and the EIOPA RFR
  methodology (the Solvency II extrapolation to an Ultimate Forward Rate). The
  Smith-Wilson spot values asserted in `05` are reproduced as factual fixtures
  from the lifelib `economic_curves` worked example (MIT).
- **Monotone interpolation** (`interpolation="pchip"`): Fritsch & Carlson (1980),
  *Monotone Piecewise Cubic Interpolation* — the shape-preserving Hermite spline.
- **Day-count fractions** (`DayCount`): ISDA day-count fraction definitions
  (Actual/Actual ISDA, 30/360, Act/365F, Act/360) — the market conventions for
  converting date intervals to year fractions.
