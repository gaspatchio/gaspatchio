# Step 07 — Anniversary-Aware Cashflows

**New in this step**: `af.projection.anniversary_mask()`.

## What you'll learn

How to gate cashflows on contract anniversaries — the canonical pattern for
anniversary commissions, anniversary fees, age-band step-ups, and GMxB
ratchets.

---

## `af.projection.anniversary_mask()`

```python
af.is_anniversary = pl.concat_list([
    af.projection.anniversary_mask(),
    pl.lit([False], dtype=pl.List(pl.Boolean)),
])
```

`af.projection.anniversary_mask()` returns a per-row `List<Boolean>` of
length `n_periods`, `True` at every period that closes a full 12-month
anniversary from the schedule start. The mask is purely structural — it
depends only on `n_periods` and `frequency`.

For monthly frequency: `True` at indices 11, 23, 35, ... (0-indexed). Index
11 marks the end of the 12th period — the first anniversary.

The frame's other list columns (e.g. `af.month`, `af.av_pp`, `af.disc_factors`)
have length `n_periods + 1` (one entry per period boundary, including
month 0). Append `False` so the mask aligns: month 0 is never an
anniversary by definition, and the structural pattern is preserved at
months 12, 24, 36, ....

---

## Why a structural mask works for anniversaries

Each policy's actual anniversary date depends on its `entry_date`, but
within a monthly grid the anniversary _cadence_ — every 12th month — is
the same for every policy. The structural mask captures the cadence
without per-policy date arithmetic. A policy issued on 2020-06-15 sees
its anniversary on 2021-06-15, 2022-06-15, ... — every 12 months, which
the structural mask fires correctly within a monthly projection cycle.

The simpler `af.duration_mth_t % 12 == 0` approximation fires whenever
`duration_mth_t` is a multiple of 12. For an in-force portfolio with
staggered inception dates, different policies hit those multiples at
different real anniversary moments. The `anniversary_mask()` accessor is
explicit about intent — a reader sees "anniversary cashflow" instead of
inferring it from modular arithmetic.

---

## The anniversary commission cashflow

```python
ANNIVERSARY_COMMISSION_RATE = 0.005  # 50 bps of initial AV per anniversary

af.anniversary_commission = (
    when(af.is_anniversary)
    .then(af.av_pp_init * ANNIVERSARY_COMMISSION_RATE * af.pols_if)
    .otherwise(0.0)
)

af.pv_anniversary_commission = (af.anniversary_commission * af.disc_factors).list.sum()
```

`when(af.is_anniversary)` broadcasts element-wise over the list column.
The commission fires only at anniversary months and is zero otherwise.
`av_pp_init` is a per-policy constant (the initial account value per policy),
so the commission is a flat rate on each surviving policy at each anniversary.

---

## When to use this in real models

- **Anniversary commissions**: trail commission paid at each policy anniversary
- **Anniversary fees**: annual policy fee deducted from AV at anniversary
- **Age-band step-ups**: mortality rate steps up at each birthday (requires
  `anniversary_mask_expr()` or age-based logic keyed to inception date)
- **GMxB ratchets**: guaranteed minimum benefit resets on each anniversary
- **Renewal premium adjustments**: indexed premium changes at annual intervals
- **Lapse rate seasonality**: some products have elevated lapse rates in the
  anniversary month

---

## Contrast with integer-arithmetic approximation

```python
# Approximation: fires every 12th projection month from the valuation date
af.is_approx_anniversary = af.duration_mth_t % 12 == 0

# Explicit: structural anniversary mask from the projection grid
af.is_anniversary = pl.concat_list([
    af.projection.anniversary_mask(),
    pl.lit([False], dtype=pl.List(pl.Boolean)),
])
```

Both approaches produce the same `True` indices for a monthly projection
grid. The accessor is preferred because it is explicit about intent — a
reader sees "anniversary cashflow" instead of inferring it from modular
arithmetic — and because it generalises to non-monthly frequencies and
non-trivial day-counts where the modular trick would silently break.

---

## Anniversary counts for this portfolio

The four model points in this tutorial were issued before the valuation date
(2024-01-01), so each policy has already passed some anniversaries by the time
the projection starts. The number of anniversaries within each policy's
remaining term:

| Policy | Entry date | Term | In-force at valuation | Anniversaries in projection |
|---|---|---|---|---|
| 1 | 2020-01-01 | 10y | 4y | 6 |
| 2 | 2015-06-01 | 20y | ~8.6y | 11 |
| 3 | 2022-01-01 | 5y | 2y | 3 |
| 4 | 2018-01-01 | 15y | 6y | 9 |

These counts are fewer than the policy terms because the projection starts
mid-way through each policy's life. A new-business cohort issued at the
valuation date would show anniversary counts equal to the policy term.

---

## Expected output

```
PV Net Cashflow + Claims + Premiums + Anniversary Commission

shape: (4, 5)
┌──────────┬───────────────┬───────────┬─────────────┬───────────────────────────┐
│ point_id ┆ pv_net_cf     ┆ pv_claims ┆ pv_premiums ┆ pv_anniversary_commission │
│ ---      ┆ ---           ┆ ---       ┆ ---         ┆ ---                       │
│ i64      ┆ f64           ┆ f64       ┆ f64         ┆ f64                       │
╞══════════╪═══════════════╪═══════════╪═════════════╪═══════════════════════════╡
│ 1        ┆ 266085.998013 ┆ 6.0518e6  ┆ 0.0         ┆ 126986.303142             │
│ 2        ┆ 143600.62995  ┆ 1.9299e6  ┆ 0.0         ┆ 61508.570463              │
│ 3        ┆ 469474.519553 ┆ 2.0223e7  ┆ 0.0         ┆ 245027.66071              │
│ 4        ┆ 254968.351475 ┆ 3.9702e6  ┆ 0.0         ┆ 111538.643305             │
└──────────┴───────────────┴───────────┴─────────────┴───────────────────────────┘
```

All four `pv_anniversary_commission` values are positive — commissions paid
out reduce net CF, which is consistent.

---

## Running this step

```bash
cd bindings/python
uv run gaspatchio_core/tutorials/level-3-mini-va-typed/steps/07-anniversary-aware/model.py
```
