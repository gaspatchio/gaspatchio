# Level 4 Reconciliation Report: Gaspatchio vs Lifelib IntegratedLife

Running document tracking the reconciliation of the gaspatchio appliedlife model against lifelib's IntegratedLife implementation.

**Last updated**: 2026-03-24
**Gold standard**: Lifelib IntegratedLife (modelx v0.28.1, lifelib v0.11.0)
**Model**: `base/model.py`

---

## Overall Scoreboard

| Dataset | Points | Ages | Terms | Sex | Timesteps | PV Variables | Intermediates | Status |
|---------|--------|------|-------|-----|-----------|-------------|---------------|--------|
| 2023Q4IF | 8 | 70 | 10yr | M/F | 82 | 10/10 PASS | 25/25 PASS | PASS |
| 2022Q4IF | 8 | 70 | 10yr | All M | 82 | 10/10 PASS | 25/25 PASS | PASS |
| 202401NB | 1,000 | 20-79 | 5-20yr | M/F | 252 | 10/10 PASS | 25/25 PASS | PASS |
| **Total** | **1,016** | | | | | | | **PASS** |

All differences are at floating-point representation level (10^-12 to 10^-14 percent). For practical purposes: **0% difference across all variables, all points, all time steps.** Approximately 9 million individual data point comparisons.

---

## Reconciled Variables (35 total)

### PV Aggregates (10)

| Variable | Description | Status |
|----------|-------------|--------|
| pv_claims | Total PV of all claims | PASS |
| pv_claims_death | PV of death benefit claims (GMDB) | PASS |
| pv_claims_lapse | PV of lapse/surrender claims | PASS |
| pv_claims_maturity | PV of maturity claims (GMAB) | PASS |
| pv_expenses | PV of maintenance expenses | PASS |
| pv_commissions | PV of commission payments | PASS |
| pv_premiums | PV of future premiums | PASS |
| pv_inv_income | PV of investment income | PASS |
| pv_av_change | PV of account value changes | PASS |
| pv_net_cf | PV of net cashflows | PASS |

### Intermediate Variables — Per Point, Per Timestep (25)

| Category | Variable | Description | Status |
|----------|----------|-------------|--------|
| Mortality | mort_rate | Annual mortality rate | PASS |
| Mortality | mort_rate_mth | Monthly mortality rate | PASS |
| Lapse | base_lapse_rate | Base annual lapse rate | PASS |
| Lapse | dyn_lapse_factor | Dynamic lapse adjustment factor | PASS |
| Lapse | lapse_rate | Final annual lapse rate | PASS |
| Policies | pols_if | Policies in force (before maturity) | PASS |
| Policies | pols_death | Deaths per period | PASS |
| Policies | pols_lapse | Lapses per period | PASS |
| Policies | pols_maturity | Maturities per period | PASS |
| AV | av_pp_bef_prem | Account value per policy (before premium) | PASS |
| AV | av_pp_bef_fee | Account value per policy (before fee) | PASS |
| AV | av_pp_mid_mth | Account value per policy (mid-month) | PASS |
| AV | maint_fee_pp | Maintenance fee per policy | PASS |
| AV | inv_return_mth | Monthly investment return | PASS |
| Cashflows | claims_death | Death claims | PASS |
| Cashflows | claims_lapse | Lapse/surrender claims | PASS |
| Cashflows | claims_maturity | Maturity claims | PASS |
| Cashflows | premiums | Premium cashflow | PASS |
| Cashflows | expenses | Expense cashflow | PASS |
| Cashflows | commissions | Commission cashflow | PASS |
| Cashflows | inv_income | Investment income | PASS |
| Cashflows | av_change | Change in account value | PASS |
| Cashflows | net_cf | Net cashflow | PASS |
| Discount | disc_factors | Cumulative discount factors | PASS |
| Discount | disc_rate_mth | Monthly discount rate | PASS |

---

## Dataset Details

### 2023Q4IF — In-Force Q4 2023 (Primary)

8 policies: GMDB/GMAB x PLAN_A/PLAN_B x FUND4-6 x M/F, all age 70, 10-year term.
In-force business with existing account values (AV > premium paid).

**Reference**: `reference/lifelib_reference_full.parquet` (656 rows)
**Model points**: `base/model_points.parquet`

```bash
uv run python tutorial/level-4-lifelib/reconcile_full.py
```

### 2022Q4IF — In-Force Q4 2022

8 policies: same product mix as 2023Q4IF but **all male** with **underwater AVs** (AV < premium, ITM > 1). Tests dynamic lapse in deep-in-the-money conditions.

Uses 202312 assumptions via synthetic run_id=11 in gaspatchio-models (lifelib's `assumptions_202212.xlsx` is an upstream stub).

**Reference**: `reference/lifelib_reference_2022Q4IF.parquet` (656 rows)
**Model points**: `base/model_points_2022Q4IF.parquet`

```bash
uv run gspio run-model tutorial/level-4-lifelib/base/model.py \
    tutorial/level-4-lifelib/base/model_points_2022Q4IF.parquet
```

### 202401NB — New Business January 2024

1,000 policies with:
- **Ages 20-79** (diverse demographics, not just age 70)
- **Terms 5-20 years** (varied projection lengths)
- **M/F split** across both sexes
- **Zero initial AV** (`av_pp_init = 0`) — premium injection at entry via `accumulate()`
- **Staggered entry dates** throughout 2024 (negative `duration_mth_init`, policies enter at different projection timesteps)
- **252-month projection** (21 years)

This is the stress test — validates gaspatchio across a production-scale model point set.

**Reference**: generated via `gaspatchio-models/appliedlife/scripts/extract_per_point_reference.py --run-id 1` (requires patched lifelib, see Upstream Bugs below)
**Model points**: `gaspatchio-models/appliedlife/ref/appliedlife/model_point_data/model_point_202401NB_GMXB.csv`
**Scenario returns**: `base/assumptions/scenario_returns_nb.parquet` (252 months, extended from lifelib stochastic generator)

```bash
uv run python -c "
import polars as pl, sys
sys.path.insert(0, 'tutorial/level-4-lifelib/base')
from gaspatchio_core import ActuarialFrame
import model

mp = pl.read_csv('path/to/model_point_202401NB_GMXB.csv')
sr = pl.read_parquet('tutorial/level-4-lifelib/base/assumptions/scenario_returns_nb.parquet')
af = ActuarialFrame(mp)
result = model.main(af, scenario_returns_override=sr, projection_months=251)
"
```

---

## Key Implementation Details

### Account Value: `accumulate()` Linear Recurrence

The model uses gaspatchio's `accumulate()` Rust plugin for account value projection:

```python
# state[t] = state[t-1] * growth[t-1] + prem_to_av[t]
af.av_pp_bef_fee = af.shifted_growth.projection.accumulate(
    initial=af.av_pp_init,
    multiply=af.shifted_growth,
    add=af.prem_to_av,
)
```

This handles both:
- **IF business**: `av_pp_init > 0`, `prem_to_av = 0` — equivalent to cumulative product
- **NB business**: `av_pp_init = 0`, `prem_to_av > 0` at entry — premium creates the initial AV

First production use of `accumulate()`. Validated across 1,016 policies with zero regression on IF results.

### New Business Entry Timing

NB policies enter at staggered dates via `pols_new_biz(t)` when `duration_mth_t == 0`. Before entry:
- `pols_if_bef_mat = 0` (excluded by `duration_mth_t > 0` condition)
- `mort_rate = 0`, `lapse_rate = 0` (zeroed for `duration < 0`)
- Premium and AV are zero

This matches lifelib's `pols_if_init()` logic: `policy_count.where(duration_mth(0) > 0, other=0)`.

### Table Boundary Handling

Mortality scalar and lapse tables have 15 entries (duration 0-14). At duration 15+, rates are zeroed to match lifelib's behavior (see Upstream Bugs). Gaspatchio's Table lookup caps correctly at duration 14, but the final rate is multiplied by `(duration >= 0) & (duration <= cap)` to match lifelib.

---

## Features Validated

The reconciliation confirms gaspatchio correctly implements:

1. **Select mortality** with 3-dimensional lookup (table_id x attained_age x duration) and duration-based scalar adjustments
2. **Dynamic lapse** formulas (DL001, DL002) based on in-the-money ratios
3. **Account value accumulation** via `accumulate()` — handles both IF and NB with fund-specific returns and maintenance fees
4. **GMDB guarantees** — death benefit = max(AV, sum assured)
5. **GMAB guarantees** — maturity benefit = max(AV, sum assured)
6. **Surrender charges** — conditional lookup by product
7. **Maintenance expenses** with 1% annual inflation
8. **Risk-free rate curve** discounting with cumulative product of per-period factors
9. **Product parameterisation** via table joins (product_params_gmxb, dynamic_lapse_params, space_params)
10. **Multi-fund investment returns** (FUND4-6) with per-policy fund assignment
11. **Staggered new business entry** with premium injection at diverse entry dates
12. **Diverse demographics** — ages 20-79, terms 5-20 years, both sexes

---

## Upstream Bugs Found

### 1. NaN Propagation for Pre-Entry Periods (lifelib issue #70)

**Problem**: `mort_rate(t)` returns NaN for policies with negative `duration_mth` (before entry). Since `0 * NaN = NaN` in numpy, the NaN propagates through `pols_death` into the recursive `pols_if_at` chain, permanently corrupting all downstream calculations.

**Status**: Fixed in `BasicTerm_SE` via PR #71 (June 2024) with an `is_active(t)` guard, but **never applied to IntegratedLife** which was added 3 weeks later in PR #73.

**Our fix**: Patched `mort_rate` and `lapse_rate` in `gaspatchio-models/appliedlife/ref/appliedlife/IntegratedLife/ProductBase/__init__.py`:
```python
result = mort_scalar(t) * base_mort_rate(t)
return np.where(np.isnan(result) | (duration_mth(t) < 0), 0.0, result)
```

Verified no regression on 2023Q4IF results.

### 2. Off-By-One in Table Duration Caps

**Problem**: `mort_scalar_len()` and `lapse_len()` return the number of table entries (15), but are used as the cap value: `np.minimum(duration(t), 15)`. This allows duration=15 to be looked up, but the table only has entries 0-14. The `.reindex()` returns NaN.

**Impact**: Mortality and lapse rates silently become 0 at duration 15+ (year 15+). Affects NB points with terms > 14 years.

**Workaround**: Gaspatchio model zeros rates at `duration > cap` to match lifelib's (buggy) behavior. A correct fix in lifelib would use `np.minimum(duration(t), duration_cap - 1)`.

### 3. Empty Assumption File (assumptions_202212.xlsx)

**Problem**: `assumptions_202212.xlsx` is a stub (single empty `Sheet1`) in both gaspatchio-models and upstream lifelib. The 2022Q4IF run_id=5 references `asmp_id=202212` which tries to read from this empty file.

**Workaround**: Created synthetic run_id=11 pairing 2022Q4IF model points with 202312 assumptions.

---

## How to Verify

```bash
# Full reconciliation: 2023Q4IF (PVs + 25 intermediate variables)
uv run python tutorial/level-4-lifelib/reconcile_full.py

# PV-only reconciliation (original script, faster)
uv run python tutorial/level-4-lifelib/reconcile.py

# 2022Q4IF reconciliation
uv run python tutorial/level-4-lifelib/reconcile_full.py \
    --gaspatchio-output /tmp/2022.parquet \
    --reference tutorial/level-4-lifelib/reference/lifelib_reference_2022Q4IF.parquet
```

For 202401NB, the reference parquet must be generated from gaspatchio-models using the patched lifelib (see `gaspatchio-models/appliedlife/scripts/extract_per_point_reference.py`).

---

## Known Limitations

- **Single scenario only**: Model runs BASE scenario with hardcoded `pl.lit("BASE")`. Level 5 adds multi-scenario support.
- **No ultimate mortality**: Uses select mortality only (duration capped at 14 to match lifelib). The full appliedlife model in `gaspatchio-models` includes select-to-ultimate transition.
- **202401NB reference not checked in**: At 25MB, the NB reference parquet is too large for the tutorial directory. It must be regenerated from gaspatchio-models with the patched lifelib.
