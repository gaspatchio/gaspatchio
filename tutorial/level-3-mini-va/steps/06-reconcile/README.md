# Step 06: Reconciliation — From Tutorial to Production

> **Prerequisites:** Complete Steps 01-05. Familiarity with Level 4's model structure (`tutorial/level-4-lifelib/README.md`).

## What this step teaches

You've built a working VA model through Steps 01-05. Now you'll learn how to **validate it against a reference implementation** — the discipline that separates "it runs" from "it's correct."

This step uses Level 4's real assumption data (8 model points, 14 assumption files) and compares against lifelib's IntegratedLife model output. Your starting model has 4 deliberate gaps. You'll discover each one through reconciliation and fix it.

## Quick start

```bash
# Run the starting model with gaps — see reconciliation failures
uv run python tutorial/level-3-mini-va/steps/06-reconcile/reconcile.py --model gaps

# Run the fixed model — see all points pass
uv run python tutorial/level-3-mini-va/steps/06-reconcile/reconcile.py --model fixed
```

**Expected output (gapped model):**

```
Point    Product  Plan     Max Diff %         Worst Variable       Status
--------------------------------------------------------------------------------
1        GMDB     PLAN_A   51.7069%           pv_net_cf            FAIL
2        GMDB     PLAN_A   11.5968%           pv_net_cf            FAIL
...
8        GMAB     PLAN_B   2.4919%            pv_inv_income        FAIL

RESULT: RECONCILIATION FAILED
```

**Expected output (fixed model):**

```
Point    Product  Plan     Max Diff %         Worst Variable       Status
--------------------------------------------------------------------------------
1        GMDB     PLAN_A   0.0000%            pv_net_cf            PASS
...
8        GMAB     PLAN_B   0.0000%            pv_net_cf            PASS

RESULT: ALL POINTS PASS
```

## Files in this step

| File | Purpose |
|---|---|
| `model_with_gaps.py` | Starting model — L3 Step 05 adapted for L4 data, with 4 deliberate gaps |
| `model.py` | Reference answer — all 4 gaps fixed, reconciles at 0.0000% |
| `reconcile.py` | Comparison script — runs either model against lifelib reference |
| `README.md` | This walkthrough |

No data files — this step references Level 4's data directly at `tutorial/level-4-lifelib/base/`.

## What changed from Step 05 (data pipeline)

The model logic is the same patterns you learned in Steps 01-05. What changes is the **data source** — L4's production assumptions instead of L3's tutorial data:

| Aspect | L3 Step 05 | Step 06 |
|---|---|---|
| Model points | 4 simple policies, all params inline | 8 diverse policies, params joined from tables |
| Product config | Columns on model points | Joined from `product_params_gmxb.parquet` |
| Dynamic lapse params | M, D, L, U on model points | Joined from `dynamic_lapse_params.parquet` |
| Expenses | On model points | Joined from `space_params.parquet` |
| Investment returns | Pre-shaped `inv_returns.parquet` | Wide-format `scenario_returns.parquet`, unpivoted to long |
| Projection length | 240 months | 82 months (matching lifelib configuration) |

These data pipeline changes are already done in both `model_with_gaps.py` and `model.py`. They're infrastructure, not gaps.

## The 4 gaps

Each gap is marked in `model_with_gaps.py` with a `=== GAP N` comment.

### Gap 1: Account value — `cum_prod()` vs `accumulate()`

**Section 5 in model_with_gaps.py**

**What the gapped model does:** Merges growth and fee into one factor and uses cumulative product:
```python
af.av_pp = af.av_pp_init * af.prev_cumulative_growth
```

**What you'll discover:** The AV intermediate variables (`av_pp_bef_fee`, `av_pp_bef_prem`, `av_pp_bef_inv`) don't exist. The model produces `av_pp` but not the decomposed timing stages that L4 needs for correct maturity claims and AV change.

**The fix:** Replace cum_prod with `accumulate()` — gaspatchio's linear recurrence method:
```python
af.av_pp_bef_fee = af.shifted_growth.projection.accumulate(
    initial=af.av_pp_init,
    multiply=af.shifted_growth,
    add=af.prem_to_av,
)
af.av_pp_bef_prem = af.av_pp_bef_fee - af.prem_to_av
af.maint_fee_pp = af.av_pp_bef_fee * af.maint_fee_rate / 12.0
af.av_pp_bef_inv = af.av_pp_bef_fee - af.maint_fee_pp
```

**Why it matters:**
- `accumulate()` handles the linear recurrence `state[t] = state[t-1] * M[t] + A[t]` in one call
- For IF business (no premium injection), results are identical to cum_prod
- For NB business (premium at entry), `add=prem_to_av` creates the initial AV — cum_prod cannot do this
- Decomposing AV into timing stages exposes intermediate values needed for correct claim calculations

**gaspatchio concept:** `projection.accumulate(initial=..., multiply=..., add=...)`

---

### Gap 2: Decrement ordering — simple vs BEF_DECR

**Section 6 in model_with_gaps.py**

**What the gapped model does:** Computes deaths and lapses directly from `pols_if`:
```python
af.pols_death = af.pols_if * af.mort_rate_mth
af.pols_lapse = (af.pols_if - af.pols_death) * af.lapse_rate_mth
```

**What you'll discover:** Small differences in `inv_income` and `av_change` near the maturity month, because `pols_if` excludes policies at the maturity month while `pols_if_bef_mat` includes them. The timing of when maturities are removed affects the AV change calculation.

**The fix:** Implement the BEF_MAT/BEF_DECR ordering:
```python
# 1. Policies before maturity (includes maturity month)
af.pols_if_bef_mat = af.survival_prob * af.policy_count * (af.duration_mth_t <= af.maturity_month) * (af.duration_mth_t > 0)

# 2. Remove maturities
af.pols_maturity = af.pols_if_bef_mat * (af.duration_mth_t == af.maturity_month)
af.pols_if_bef_nb = af.pols_if_bef_mat - af.pols_maturity

# 3. Add new business
af.pols_if_bef_decr = af.pols_if_bef_nb + af.pols_new_biz

# 4. Deaths from BEF_DECR, lapses from survivors
af.pols_death = af.pols_if_bef_decr * af.mort_rate_mth
af.pols_lapse = (af.pols_if_bef_decr - af.pols_death) * af.lapse_rate_mth
```

**Why it matters:**
- The ordering — maturities, then new business, then deaths, then lapses from survivors — is the production standard for multi-decrement models
- `pols_if_bef_decr` is the correct population for premiums and expenses (before anyone exits)
- `pols_if_bef_mat` with `next_period()` is the correct base for investment income and AV change
- For NB business, the `duration_mth_t > 0` guard prevents double-counting (NB enters via `pols_new_biz`)

**gaspatchio concepts:** `projection.previous_period()`, `projection.next_period()`, boolean multiplication for timing masks

---

### Gap 3: Dynamic lapse — single formula vs product-specific

**Section 4 in model_with_gaps.py**

**What the gapped model does:** Only implements DL001:
```python
af.dyn_lapse_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)
```

**What you'll discover:** GMDB points (1-4) are reasonably close, but GMAB points (5-8) show large lapse rate differences. This is because:
- GMDB products use DL001 (the formula above) with M=0, D=0 → factor always 1.0
- GMAB products use DL002 (power function) → factor = clip(ITM, Floor, Cap)

Applying DL001 to GMAB points gives a factor of 1.0, but the correct DL002 factor varies with ITM ratio, significantly changing lapse behavior.

**The fix:**
```python
# DL001: clip(1 - M * (1/ITM - D), L, U)
af.dl001_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)

# DL002: clip(Y * ITM^Power, FactorFloor, FactorCap)
af.dl002_factor = (af.Y * af.itm ** af.Power).clip(af.FactorFloor, af.FactorCap)

# Select by formula_id
af.dyn_lapse_factor = (
    when(af.formula_id == "DL001").then(af.dl001_factor).otherwise(af.dl002_factor)
)
```

**Why it matters:**
- Different products model policyholder behavior differently
- GMAB policyholders lapse based on how far their account is in-the-money relative to the guarantee
- DL001 and DL002 are two different approaches: DL001 uses an offset formula, DL002 uses a power function
- The model must be **parameter-driven** — the formula to use comes from assumption tables, not hardcoded logic

**gaspatchio concept:** `when().then().otherwise()` for formula selection based on product parameters

---

### Gap 4: Discount factors — `cum_prod()` vs closed-form

**Section 11 in model_with_gaps.py**

**What the gapped model does:** Cumulative product of per-period discount factors:
```python
af.per_period_disc = 1.0 / (1.0 + af.disc_rate_mth)
af.disc_factors = af.per_period_disc.cum_prod()
```

**What you'll discover:** All points are off by a small but consistent amount in every PV variable. The risk-free rate changes each year (e.g., 4.789% in year 0, 4.398% in year 1), and the two formulas compound differently across year boundaries.

**The fix:**
```python
af.disc_factors = (
    af.month.cast(pl.Float64) * -1.0 * (1.0 + af.disc_rate_mth).log()
).exp()
```

This computes `(1 + r_mth)^(-t)` using the exp/log identity, matching lifelib's convention.

**Why it matters:**
- When rates change between years, `cum_prod` and the closed-form give different results
- `cum_prod` compounds at each period's actual rate: `df[12] = (1/(1+r_0))^12 * (1/(1+r_1))^1`
- The closed-form uses the current period's rate as if it applied from t=0: `df[12] = (1+r_1)^(-12)`
- Neither is objectively "more correct" — but **reconciliation means matching the reference**
- This teaches a key reconciliation lesson: your formula might be defensible, but if the reference uses a different convention, you match the reference first, then discuss the difference

**gaspatchio concepts:** `.log()`, `.exp()`, `.cast()` on list columns

## Recommended fix order

1. **Gap 3 (DL002)** — Largest numeric impact (up to 51% on pv_net_cf). Easiest to diagnose: GMAB points fail dramatically while GMDB points are closer.

2. **Gap 4 (Discount factors)** — Affects all PV variables uniformly. After fixing Gap 3, the remaining small systematic error across all points points to discounting.

3. **Gap 1 (accumulate)** — Structural improvement. For IF business the numbers are identical, but you need the decomposed AV stages for the Gap 2 fix and for NB readiness.

4. **Gap 2 (BEF_DECR)** — Subtle timing effects at maturity month. Requires Gap 1's `av_pp_bef_prem` and produces `pols_if_bef_decr` needed for correct premiums/expenses.

## The reconciliation discipline

### Start with PVs, then dig into intermediates

The reconciliation script compares 10 PV aggregate variables. When a PV fails:
1. Which points fail? (Product-specific → Gap 3. All points → Gap 4.)
2. Which PV variable has the worst mismatch? (pv_claims → check AV/claims. pv_net_cf → check everything.)
3. Run a single policy and inspect intermediates:

```bash
uv run gspio run-single-policy tutorial/level-3-mini-va/steps/06-reconcile/model_with_gaps.py \
    tutorial/level-4-lifelib/base/model_points.parquet 1 \
    --output-file /tmp/debug.parquet
```

### The fix cycle

```
For each gap:
  1. Run reconcile.py — note which points fail and by how much
  2. Hypothesize the cause (use the debugging hints)
  3. Apply the fix in model_with_gaps.py
  4. Re-run reconcile.py — confirm improvement
  5. Move to the next gap when all affected points improve
```

### Matching intermediates, not just PVs

A model can give the right PVs for the wrong reasons. Gaps 1 and 2 may not change PV values for IF business, but they change intermediate variables (`av_pp_bef_fee`, `pols_if_bef_decr`). The full L4 reconciliation (`tutorial/level-4-lifelib/reconcile_full.py`) compares 25 intermediate variables per point per timestep — passing PVs is necessary but not sufficient.

## What's next: Level 4

With all 4 gaps fixed, your Step 06 `model.py` produces the same results as Level 4's model. Level 4 adds:
- `storage_mode` optimization for large assumption tables
- `scenario_returns_override` parameter for scenario analysis
- Support for multiple datasets (2022Q4IF, 202401NB with 1,000 points)
- `accumulate()` handling both IF and NB in a single formula

See `tutorial/level-4-lifelib/README.md` for the full production model and `tutorial/level-4-lifelib/reconciliation_report.md` for the complete reconciliation results across 1,016 model points and 35 variables.
