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
| `timing="end_of_period"` (default) | `PV[t] = CF[t]*v^0 + CF[t+1]*v^1 + CF[t+2]*v^2 + ...` | End of each period (CF[t] is undiscounted) |
| `timing="beginning_of_period"` | `PV[t] = CF[t]*v^1 + CF[t+1]*v^2 + ...` | Beginning (everything gets one extra period of discounting) |

Despite the name, `"end_of_period"` produces standard actuarial BOP discounting (v^t). This matches Excel's `SUMPRODUCT(cashflows, discount_factors)` where `DF[t] = (1+r)^(-t/12)`.

### Three Call Patterns

```python
# 1. Flat rate (most common)
af.pv = af.cashflow.projection.prospective_value(discount_rate=0.025)

# 2. Per-period rates (uses cumulative product internally — forward-rate semantics)
af.pv = af.cashflow.projection.prospective_value(discount_rate=af.rate_column)

# 3. Pre-computed discount factors (for spot-rate curves)
af.pv = af.cashflow.projection.prospective_value(discount_factor=af.v_t)
```

**For term-structure discounting (yield curves):** Use option 3 with pre-computed `v(t) = (1+r_t)^(-t/12)` factors. Option 2 uses cumulative products (forward-rate semantics), which is NOT the same as spot rates.

### `cumulative_survival()` Parameters

```bash
uv run gspio docs "cumulative_survival" -t parameters
```

```python
af.survival = af.mort_rate.projection.cumulative_survival(
    rate_timing="beginning_of_period",  # or "end_of_period"
    start_at=1.0,                        # initial survival probability
)
```

The `rate_timing` parameter determines whether the rate applies at the start or end of each period. This matters for BOP vs EOP decrement conventions.

---

## Policy Year vs Projection Year

This is the #3 most common mistake. These are DIFFERENT things:

| Column | Meaning | Use For |
|--------|---------|---------|
| `af.year` | Policy year (years since effective date) | Mortality/CSO lookups, policy anniversaries |
| `af.proj_year` | Projection year (years since projection start) | Stress scenario rate switching, inflation escalation |

### Why It Matters

For stress scenarios like MASS_LAPSE that apply 50% lapse "in year 1":
- `when(af.year == 1)` — fires only for NEW policies (year 1 since inception). For established in-force policies (policy year 10-20+), this is NEVER true.
- `when(af.proj_year == 1)` — fires for the first 12 projection months for ALL policies. This is what BSCR scenarios mean by "year 1."

### How to Compute `proj_year`

**DO NOT use `ceil(t/12)`** — leap years cause 1-period offsets:

```python
# WRONG — at t=48, leap year 2028 causes YEARFRAC=4.003, rounding to 5 instead of 4
af.proj_year = (af.t / 12.0).ceil()

# RIGHT — use actual date-based YEARFRAC
af.proj_year = af.first_projection_date.excel.yearfrac(af["date"], 3).ceil().clip(lower_bound=1)
```

Under 12% stress inflation, the `ceil(t/12)` error caused a 0.78% accumulation bias that compounded to 21% BEL gap.

---

## Period 0 Is Special

Many Excel models explicitly exclude cashflows at period 0 (the projection start date):

```python
# Common pattern: mask period 0
af.period_zero_mask = when(af.t == 0).then(1.0).otherwise(0.0)
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

Key difference: Excel's `YEARFRAC` always returns positive (it swaps dates internally). Gaspatchio may return negative values when `end_date < start_date`. This matters for future-dated policies.

### Future-Dated Policies

When a policy's effective date is after the valuation date:
- YEARFRAC produces negative values for pre-inception periods
- The sign of `yearfrac(effective_date, projection_date)` tells you: negative = pre-inception, positive = post-inception

```python
af.year_frac_raw = af.effective_date.excel.yearfrac(af["date"], 1)
af.is_pre_inception = when(af.year_frac_raw < 0).then(1.0).otherwise(0.0)
```

### Leap Year Gotcha

YEARFRAC with basis 1 (Actual/Actual) handles Feb 29 differently than simple month arithmetic. Always include a leap-year policy (e.g., effective 2024-02-29) in your test cases.

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
