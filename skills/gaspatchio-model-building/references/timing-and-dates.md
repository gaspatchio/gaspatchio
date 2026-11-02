# Timing and Dates

This is the most actuarially subtle area. Mistakes here are silent — the model runs fine but produces wrong PVs.

## `prospective_value()` Timing

**The parameter names are misleading.** Always verify with `gspio docs`:

```bash
uv run gspio docs "prospective_value" -t parameters
```

### What the Parameters Mean

| Parameter | Formula | When Cashflows Occur |
|-----------|---------|---------------------|
| `timing="end_of_period"` (default) | `PV[t] = CF[t]*v^1 + CF[t+1]*v^2 + ...` | End of each period — every cashflow discounted a full period (Excel `PV` type 0, ordinary annuity) |
| `timing="beginning_of_period"` | `PV[t] = CF[t]*v^0 + CF[t+1]*v^1 + ...` | Beginning of period — `CF[t]` is undiscounted (Excel `PV` type 1, annuity-due) |

The labels match Excel's `PV` convention: `end_of_period` = type 0 (ordinary annuity), `beginning_of_period` = type 1 (annuity-due). A beginning-of-period cashflow is discounted one fewer period, so `beginning_of_period` is always worth more than `end_of_period` for the same cashflows.

### Three Call Patterns

```python
# 1. Flat rate (most common)
af.pv = af.cashflow.projection.prospective_value(discount_rate=0.025)

# 2. Per-period rates (uses cumulative product internally — forward-rate semantics)
af.pv = af.cashflow.projection.prospective_value(discount_rate=af.rate_column)

# 3. Pre-computed discount factors. Where the factors are anchored decides the
#    timing, so option 3 is really two recipes and each carries its own timing.
#    Read "Name the anchoring" below before picking one.
af.v_end = ...    # end-anchored: [v(t1), v(t2), …], no leading 1.0
af.pv = af.cashflow.projection.prospective_value(discount_factor=af.v_end)

af.v_spot = ...   # valuation-date-anchored: [1.0, v(t1), v(t2), …]
af.pv = af.cashflow.projection.prospective_value(
    discount_factor=af.v_spot, timing="beginning_of_period"
)
```

**For term-structure discounting (yield curves):** a curve read on
`af.projection.t_years()` produces the **spot** vector, so it is the second recipe
of option 3 — **with `timing="beginning_of_period"`**:

```python
af.v_spot = curve.discount_factor(af.projection.t_years())  # [1.0, v(t1), v(t2), …]
af.pv = af.cashflow.projection.prospective_value(
    discount_factor=af.v_spot, timing="beginning_of_period"
)
```

**Name the anchoring.** `t_years()` starts at 0 and `v(0) = 1.0`, so that vector is
**spot factors anchored at the valuation date** — the beginning-of-period
convention, in which `CF[t]` falls at the instant `t_years[t]` names. Handing it to
the **default** `end_of_period` shifts every period by one and returns a *hybrid*:
on a flat 4% curve with `CF = [100, 100, 100, 100]` it gives
`[377.51, 277.51, 188.61, 96.15]`, where `PV[0]` is the annuity-due value and
`PV[1:]` are the ordinary-annuity ones. The total looks right and every later
reserve is on the other convention — exactly the silent error this page is about.
Want ordinary-annuity PVs? Keep the default and supply the **end-anchored**
`af.v_end` (`[v(t1), v(t2), …]`, no leading 1.0) instead, which on the same
cashflows returns `[362.99, 277.51, 188.61, 96.15]`. The two pairings never mix —
including in the option-3 block above, where each factor vector is written beside
the timing it belongs to.

That call is a recorded operation — the artifact carries the curve's `source_sha` — and
it lowers to the `curve_eval` + `list_pow` kernels; hand-rolling `(1+r_t)^(-t/12)`
gives up the record for no speed. Option 2 uses cumulative products (forward-rate
semantics), which is NOT the same as spot rates. See
[curves-and-scheduling.md](curves-and-scheduling.md).

### `cumulative_survival()` Parameters

```bash
uv run gspio docs "cumulative_survival" -t parameters
```

```python
af.survival = af.mort_rate.projection.cumulative_survival(
    rate_timing="beginning_of_period",  # or "end_of_period"
    start_at=1.0,                        # the value at t=0 only, not a factor
)
```

`start_at=a` sets the opening boundary and nothing else: `[a, tpx[0], tpx[1], ...]`. It does
not scale the curve -- `start_at=0.95` gives `[0.95, 0.999, 0.997]`, which rises at t=1. For a
cohort of which 95% survived underwriting, multiply: `0.95 * af.qx.projection.cumulative_survival()`.

The `rate_timing` parameter determines whether the rate applies at the start or end of each period. This matters for BOP vs EOP decrement conventions.

---

## Policy Year vs Projection Year

This is the #3 most common mistake. These are DIFFERENT things, and gaspatchio creates
**neither**: `projection.set()` materialises only `af.month`, the whole months since the
projection start. You derive the year you mean, with the formula you mean:

| Column you derive | Meaning | Use For |
|--------|---------|---------|
| `af.policy_year` | Policy year (years since issue) | Select-period lookups, policy anniversaries |
| `af.proj_year` | Projection year (years since projection start) | Stress scenario rate switching, inflation escalation |

### Why It Matters

For stress scenarios like MASS_LAPSE that apply 50% lapse "in year 1":
- `when(af.policy_year == 1)` — fires only for NEW policies (year 1 since issue). For established in-force policies (policy year 10-20+), this is NEVER true.
- `when(af.proj_year == 1)` — fires for the first 12 projection months for ALL policies. This is what BSCR scenarios mean by "year 1."

### How to Compute Them

```python
# Projection year, ordinal: the month-0 boundary belongs to year 1. A bare
# ceil(month / 12) labels it year 0, and a `proj_year == 1` shock skips the first row.
af.proj_year = when(af.month == 0).then(1).otherwise((af.month + 11) // 12)

# Policy year: completed months in force at the projection start, plus elapsed months
af.months_in_force = af.issue_date.date.months_between(af.valuation_date)
af.policy_year = (af.months_in_force + af.month) // 12 + 1
```

These are end-of-period labels. With **beginning-of-period** rows, projection year 1 is
`af.month // 12 + 1` instead — check your timing convention before choosing.

**Reconciling to a workbook that derives its year from dates.** A workbook that computes
the projection year as `ROUNDUP(YEARFRAC(start, period_date, 3))` drifts from a month count
across leap days: on a 2025 start it reads year 5 at month 48 and year 6 at month 60, where
the month count reads 4 and 5. To match such a workbook, use its formula on the period dates:

```python
af.period_date = af.projection.period_dates()
af.proj_year = af.projection_start_date.excel.yearfrac(af.period_date, 3).ceil().clip(lower_bound=1)
```

Under 12% stress inflation, a one-period offset in the year label against such a workbook
compounded to a 21% BEL gap. Match the reference's convention; do not assume it.

---

## Period 0 Is Special

Many Excel models explicitly exclude cashflows at period 0 (the projection start date):

```python
# Common pattern: mask period 0
af.period_zero_mask = when(af.month == 0).then(1.0).otherwise(0.0)
af.premium = af.premium_raw * (1 - af.period_zero_mask)
```

Things often excluded at t=0: premium income, anniversary cashflows, expense cashflows. Always check the gold standard for period-0 guards.

---

## YEARFRAC Behavior

### Gaspatchio vs Excel

```python
# Gaspatchio's Excel-compatible YEARFRAC
af.yf = af.start_date.excel.yearfrac(af["date"], basis)
```

Like Excel's `YEARFRAC`, it does not depend on argument order: the earlier date is the start and the answer is never negative, so a workbook's `YEARFRAC(valuation, issue)` converts as written. Its leap-day and one-year rules are Excel's too, on both engines.

### Future-Dated Policies

When a policy's effective date is after the valuation date, the year fraction cannot tell you which side of inception a period is on -- it is positive either way. Compare the dates:

```python
af.year_frac = af.effective_date.excel.yearfrac(af["date"], 1)
af.is_pre_inception = when(af["date"] < af.effective_date).then(1.0).otherwise(0.0)
```

### Leap Year Gotcha

YEARFRAC with basis 1 (Actual/Actual) handles Feb 29 differently than simple month arithmetic: 29 Feb 2024 to 28 Feb 2025 is 365/366, not 1. Always include a leap-year policy (e.g., effective 2024-02-29) in your test cases.

---

## Date Conversion

### Excel Serial Dates

```python
af.date_col = af["Excel Serial Date"].excel.from_excel_serial(epoch="1900")
```

Verify the conversion is correct for at least one date — off-by-one-day errors in serial date conversion cascade through YEARFRAC into year/month into mortality into survival into all cashflows.

### Roll-Forward

Some models project from a rolled-forward date, not the valuation date:

```
Valuation date: 2024-12-31
Roll-forward months: 12
Projection start: 2025-12-31 (= valuation + 12 months)
```

`t=0` in the projection corresponds to the rolled-forward start, not the valuation date. Don't confuse them.

---

## Discount factor conventions

Two approaches exist:

**Cumulative product** (actuarially intuitive):
```python
af.per_period_disc = 1.0 / (1.0 + af.disc_rate_mth)
af.disc_factors = af.per_period_disc.cum_prod()
```

**Closed-form** (matches lifelib):
```python
af.disc_factors = (1.0 + af.disc_rate_mth) ** (-af.month)
```

`**` takes a list exponent directly and records as a core operation. The older spelling,
`(af.month.polars_native().cast(...) * -1.0 * (1.0 + r).log()).exp()`, gives the same
factors but goes through the escape, so it records `engine_native` and runs only on Polars.

These give different results when rates change between years. The closed-form uses the current period's rate as if it applied from t=0. When reconciling against a reference model, match its formula. See Level 3 Step 06 (Gap 4).

## `t_years()` in the last bits

On a calendar grid `t_years()` is a running sum of year fractions, so a monthly grid differs
from `k/12` in the last bits — 219 of 241 boundaries of a 20-year monthly grid, by up to 25
ulp, the first at month 5 (`0.41666666666666663` against `0.4166666666666667`). Expect
last-bit differences against a workbook's `A/12`. Where there is no calendar under the model,
project on the fixed-step axis (`projection.set(n_periods=…, steps_per_year=12)`), whose
`t_years()` is `k/12` exactly — see model-phases.md.
