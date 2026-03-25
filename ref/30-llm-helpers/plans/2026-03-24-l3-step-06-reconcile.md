# L3 Step 06: Reconciliation Exercise — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build L3 Step 06 as a hands-on reconciliation exercise where the student takes their L3 model, points it at L4's production data, discovers 4 actuarial gaps via reconciliation, and fixes them.

**Architecture:** Two model files — `model_with_gaps.py` (starting point with 4 deliberate gaps) and `model.py` (reference answer with all gaps fixed). A `reconcile.py` script compares either model against the lifelib reference. The README walks the student through discovering and fixing each gap. No data files in this step — references L4's data directly.

**Tech Stack:** Python, gaspatchio_core (ActuarialFrame, Table, when/then/otherwise, projection accessor including `accumulate()`), Polars

**Reference files:**
- `tutorial/level-3-mini-va/steps/05-rate-curves/model.py` — starting point for both models
- `tutorial/level-4-lifelib/base/model.py` — the target reconciled model (L4)
- `tutorial/level-4-lifelib/reconcile.py` — existing PV reconciliation script (pattern to follow)
- `tutorial/level-4-lifelib/reference/lifelib_reference.parquet` — lifelib PV reference for 8 model points
- `tutorial/level-4-lifelib/reference/lifelib_reference_full.parquet` — lifelib per-timestep intermediates
- `tutorial/level-4-lifelib/base/model_points.parquet` — 8 IF model points (2023Q4IF)
- `tutorial/level-4-lifelib/base/assumptions/` — 14 assumption parquet files

**Data facts (verified):**
- GMDB products (points 1-4) use DL001 dynamic lapse formula
- GMAB products (points 5-8) use DL002 dynamic lapse formula
- DL001 params: M=0, D=0, L=0.5, U=2.0 → factor always 1.0
- DL002 params: Y=1.0, Power=1.0 → factor = clip(ITM, Floor, Cap)
- Risk-free rates (USD, BASE) vary by year: 0.03357 at year 0 → 0.03366 at year 149
- Max policy duration over projection: ~12 years (below SCALAR_DURATION_CAP=14)
- L4 model points have 14 columns; product params, dyn lapse params, and space params are joined from assumption files

**The 4 deliberate gaps:**

| # | Gap | What the gapped model does | What the fixed model does | Numeric impact on 2023Q4IF | Actuarial lesson |
|---|-----|---------------------------|--------------------------|---------------------------|-----------------|
| 1 | AV via cum_prod (no accumulate) | `av_pp = av_pp_init * prev_cumulative_growth` | `av_pp_bef_fee = shifted_growth.projection.accumulate(initial=..., multiply=..., add=prem_to_av)` | Structural only (identical for IF) | `accumulate()` handles linear recurrences; needed for NB premium injection |
| 2 | Simple decrement ordering | `pols_death = pols_if * mort_rate_mth` | Deaths from `pols_if_bef_decr` after maturity/NB ordering | Small diff at maturity month (inv_income, av_change) | Multi-decrement timing: maturities → new biz → deaths → lapses from survivors |
| 3 | DL001 only (no DL002) | Single formula for all products | `when(formula_id == "DL001").then(dl001).otherwise(dl002)` | **Significant** — 4 of 8 points use DL002 | Different products model policyholder behavior differently |
| 4 | cum_prod discount factors | `per_period_disc.cum_prod()` | `exp(-month * ln(1 + disc_rate_mth))` (closed-form) | **Measurable** — rates change each year | Reconciliation means matching the reference formula, not being "more correct" |

---

## Task 1: Create model_with_gaps.py

**Files:**
- Create: `tutorial/level-3-mini-va/steps/06-reconcile/model_with_gaps.py`

This is L3 Step 05 adapted for L4's data, with the 4 deliberate gaps intact. The student starts here.

**What changes from L3 Step 05 to create this file:**

1. **Data pipeline** (new code, not a gap — infrastructure to use L4's data):
   - Change paths to reference L4's data: `L4_DIR = Path(__file__).resolve().parent.parent.parent.parent / "level-4-lifelib"` (navigate from `06-reconcile/` up to `tutorial/` then into `level-4-lifelib/`)
   - `ASSUMPTIONS_DIR = L4_DIR / "base" / "assumptions"`
   - Change `PROJECTION_MONTHS = 82` (from 240)
   - Load product_params, dyn_lapse_params, space_params as DataFrames (same as L4)
   - Add 3 joins before creating ActuarialFrame (same as L4 lines 204-277):
     - `product_params_gmxb.parquet` join on (product_id, plan_id) → adds mort_table_male/female, mort_scalar_id, lapse_id, maint_fee_rate, has_gmdb, has_gmab, etc.
     - `dynamic_lapse_params.parquet` join on dyn_lapse_param_id → adds formula_id, U, L, M, D, FactorCap, FactorFloor, Y, Power (with null fill defaults)
     - `space_params.parquet` filtered to GMXB → adds expense_acq, expense_maint via pl.lit()
   - Unpivot `scenario_returns.parquet` from wide (FUND1-FUND6 columns) to long format, create inv_returns Table
   - Load model points from `L4_DIR / "base" / "model_points.parquet"`

2. **Sections that stay the same as L3 Step 05** (copy directly):
   - SECTION 2: Time setup (entry_date, duration, age)
   - SECTION 3: Mortality rates (select table lookup, scalar adjustment)
   - SECTION 9: Expenses & commissions (inflation, acq + maint)

3. **Section changes for L4 data compatibility** (not gaps, just data adaptations):
   - Mortality: column names now `af.M` instead of `af.M_param` (from join), same for `af.D` instead of `af.D_param`
   - Investment returns: use unpivoted Table instead of pre-loaded inv_returns.parquet
   - Duration capping on mortality and lapse: add `when((af.duration >= 0) & (af.duration <= CAP)).then(...).otherwise(0.0)` guards (same as L4) — these are NOT a gap, they're needed for correctness even though they don't trigger on this data

4. **The 4 gaps** (deliberately simplified from L4):

**GAP 1 — AV via cum_prod (SECTION 5):**
```python
# Account value via cumulative product (simplified — no accumulate)
af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (1.0 + af.inv_return_mth)
af.cumulative_growth = af.combined_growth_factor.cum_prod()
af.prev_cumulative_growth = af.cumulative_growth.projection.previous_period(fill_value=1.0)
af.av_pp = af.av_pp_init * af.prev_cumulative_growth
af.maint_fee_pp = af.av_pp * af.maint_fee_rate / 12.0
af.av_pp_after_fee = af.av_pp - af.maint_fee_pp
af.inv_income_pp = af.inv_return_mth * af.av_pp_after_fee
af.av_pp_mid_mth = af.av_pp_after_fee + 0.5 * af.inv_income_pp
```

**GAP 2 — Simple decrement ordering (SECTION 6):**
```python
# Policy counts — simple ordering (no BEF_DECR)
af.combined_decrement = 1.0 - (1.0 - af.mort_rate_mth) * (1.0 - af.lapse_rate_mth)
af.survival_factor = 1.0 - af.combined_decrement
af.cumulative_survival = af.survival_factor.cum_prod()
af.survival_prob = af.cumulative_survival.projection.previous_period(fill_value=1.0)

af.maturity_month = af.policy_term * 12

af.pols_if = (
    when(af.duration_mth_t < af.maturity_month)
    .then(af.survival_prob * af.policy_count)
    .otherwise(0.0)
)
af.pols_maturity = (
    when(af.duration_mth_t == af.maturity_month)
    .then(af.survival_prob * af.policy_count)
    .otherwise(0.0)
)
af.pols_new_biz = when(af.duration_mth_t == 0).then(af.policy_count).otherwise(0.0)
af.pols_death = af.pols_if * af.mort_rate_mth
af.pols_lapse = (af.pols_if - af.pols_death) * af.lapse_rate_mth
```

**GAP 3 — DL001 only (SECTION 4):**
```python
# Dynamic lapse — single formula (DL001 only)
af.itm = af.av_pp_mid_mth / af.sum_assured.cast(pl.Float64)
af.dyn_lapse_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)

af.lapse_rate = when(
    (af.duration >= 0) & (af.duration <= LAPSE_DURATION_CAP)
).then(
    (af.dyn_lapse_factor * af.base_lapse_rate).clip(af.dyn_lapse_floor, None)
).otherwise(0.0)
af.lapse_rate_mth = 1.0 - (1.0 - af.lapse_rate) ** (1.0 / 12.0)
```

**GAP 4 — cum_prod discount factors (SECTION 11):**
```python
# Discount factors via cumulative product
af.year = af.month // 12
af.disc_rate = risk_free_rates.lookup(
    scenario=pl.lit("BASE"), currency=pl.lit("USD"), year=af.year
)
af.disc_rate_mth = (1.0 + af.disc_rate) ** (1.0 / 12.0) - 1.0
af.per_period_disc = 1.0 / (1.0 + af.disc_rate_mth)
af.disc_factors = af.per_period_disc.cum_prod()
```

5. **Remaining sections** (same as L3 Step 05, adapted for column names):
   - SECTION 7: Claims (death with GMDB, lapse with surrender charges, maturity with GMAB)
     - Maturity claims use `af.av_pp` (gapped model's name for BOB AV)
   - SECTION 8: Premiums (`premium_pp_list * pols_if`)
   - SECTION 10: Net cashflow (`av_total = av_pp * pols_if`, same L3 pattern)
   - SECTION 12: Present values (same list.sum() pattern)

6. **Standalone execution block:**
```python
if __name__ == "__main__":
    mp = pl.read_parquet(L4_DIR / "base" / "model_points.parquet")
    af = ActuarialFrame(mp)
    result_af = main(af)
    result = result_af.collect()
    print(result.select(["point_id", "product_id", "plan_id", "pv_net_cf", "pv_claims"]))
```

- [ ] **Step 1: Create model_with_gaps.py**

Start from `tutorial/level-3-mini-va/steps/05-rate-curves/model.py`. Apply the data pipeline changes and keep the 4 gaps as described above. The model should:
- Load L4's model points and assumptions
- Perform the 3 joins (product_params, dyn_lapse_params, space_params)
- Unpivot scenario_returns
- Run the full projection with the 4 gaps intact
- Compute all PV variables
- Be ~450-500 lines

Key column name changes from L3 Step 05 to L4 data:
- `af.M_param` → `af.M` (from dyn_lapse_params join)
- `af.D_param` → `af.D`
- `af.formula_id` is now available (from join) but not used in Gap 3
- `af.FactorCap`, `af.FactorFloor`, `af.Y`, `af.Power` are now available but not used

Include comments marking each gap: `# GAP 1: ...`, `# GAP 2: ...`, etc. so they're easy to find.

- [ ] **Step 2: Run model_with_gaps.py to verify it executes**

Run: `uv run python tutorial/level-3-mini-va/steps/06-reconcile/model_with_gaps.py`
Expected: Prints 8 rows with PV columns. Some PV values will differ from L4 reference (due to gaps).

- [ ] **Step 3: Commit**

```
feat(tutorial): add L3 Step 06 model_with_gaps.py — reconciliation starting point
```

---

## Task 2: Create model.py (fixed version)

**Files:**
- Create: `tutorial/level-3-mini-va/steps/06-reconcile/model.py`

This is the reference answer — model_with_gaps.py with all 4 gaps fixed. Should match L4's logic and produce 0.0000% difference against lifelib.

- [ ] **Step 1: Create model.py**

Copy model_with_gaps.py, then apply these 4 fixes:

**FIX 1 — Replace cum_prod AV with accumulate() (SECTION 5):**
```python
# Account value via accumulate() — production pattern
af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (1.0 + af.inv_return_mth)

# Premium deposited to AV: only at entry (duration_mth_t == 0)
af.prem_to_av = af.premium_pp * (1.0 - af.load_prem_rate) * (af.duration_mth_t == 0)

# Shifted growth for accumulate: growth[t] = combined_growth[t-1], fill_value=1.0 at t=0
af.shifted_growth = af.combined_growth_factor.projection.previous_period(fill_value=1.0)

# Linear recurrence: av[t] = av[t-1] * growth[t-1] + prem_to_av[t]
af.av_pp_bef_fee = af.shifted_growth.projection.accumulate(
    initial=af.av_pp_init,
    multiply=af.shifted_growth,
    add=af.prem_to_av,
)

# Decompose AV into timing stages
af.av_pp_bef_prem = af.av_pp_bef_fee - af.prem_to_av
af.maint_fee_pp = af.av_pp_bef_fee * af.maint_fee_rate / 12.0
af.av_pp_bef_inv = af.av_pp_bef_fee - af.maint_fee_pp
af.inv_income_pp = af.inv_return_mth * af.av_pp_bef_inv
af.av_pp_mid_mth = af.av_pp_bef_inv + 0.5 * af.inv_income_pp
```

**FIX 2 — BEF_DECR decrement ordering (SECTION 6):**
```python
# Policy counts with BEF_MAT/BEF_DECR ordering
af.combined_decrement = 1.0 - (1.0 - af.mort_rate_mth) * (1.0 - af.lapse_rate_mth)
af.survival_factor = 1.0 - af.combined_decrement
af.cumulative_survival = af.survival_factor.cum_prod()
af.survival_prob = af.cumulative_survival.projection.previous_period(fill_value=1.0)

af.maturity_month = af.policy_term * 12

# Policies in force before maturity (includes maturity month, excludes pre-entry)
af.pols_if_bef_mat = (
    af.survival_prob
    * af.policy_count
    * (af.duration_mth_t <= af.maturity_month)
    * (af.duration_mth_t > 0)
)
af.pols_if = af.pols_if_bef_mat

# Maturities first
af.pols_maturity = af.pols_if_bef_mat * (af.duration_mth_t == af.maturity_month)

# Remove maturities, add new business
af.pols_if_bef_nb = af.pols_if_bef_mat - af.pols_maturity
af.pols_new_biz = af.policy_count * (af.duration_mth_t == 0)
af.pols_if_bef_decr = af.pols_if_bef_nb + af.pols_new_biz

# Deaths from BEF_DECR population, lapses from survivors
af.pols_death = af.pols_if_bef_decr * af.mort_rate_mth
af.pols_lapse = (af.pols_if_bef_decr - af.pols_death) * af.lapse_rate_mth
```

**FIX 3 — Add DL002 formula selection (SECTION 4):**
```python
# Dynamic lapse with dual formula selection
af.itm = af.av_pp_mid_mth / af.sum_assured.cast(pl.Float64)

# DL001: clip(1 - M * (1/ITM - D), L, U)
af.dl001_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)

# DL002: clip(Y * ITM^Power, FactorFloor, FactorCap)
af.dl002_factor = (af.Y * af.itm ** af.Power).clip(af.FactorFloor, af.FactorCap)

# Select by formula_id
af.dyn_lapse_factor = (
    when(af.formula_id == "DL001").then(af.dl001_factor).otherwise(af.dl002_factor)
)

af.lapse_rate = when(
    (af.duration >= 0) & (af.duration <= LAPSE_DURATION_CAP)
).then(
    (af.dyn_lapse_factor * af.base_lapse_rate).clip(af.dyn_lapse_floor, None)
).otherwise(0.0)
af.lapse_rate_mth = 1.0 - (1.0 - af.lapse_rate) ** (1.0 / 12.0)
```

**FIX 4 — Closed-form discount factors (SECTION 11):**
```python
# Discount factors: closed-form (1 + r)^(-t)
# Using exp/log identity: a^b = exp(b * ln(a))
af.year = af.month // 12
af.disc_rate = risk_free_rates.lookup(
    scenario=pl.lit("BASE"), currency=pl.lit("USD"), year=af.year
)
af.disc_rate_mth = (1.0 + af.disc_rate) ** (1.0 / 12.0) - 1.0
af.disc_factors = (
    af.month.cast(pl.Float64) * -1.0 * (1.0 + af.disc_rate_mth).log()
).exp()
```

**Additional changes in the fixed model** (consequential to Fix 1 & 2):
- Maturity claims use `af.av_pp_bef_prem` instead of `af.av_pp`
- Premiums use `af.pols_if_bef_decr` instead of `af.pols_if`
- Expenses use `af.pols_if_bef_decr` instead of `af.pols_if`
- Investment income uses `af.pols_if_bef_mat.projection.next_period()` instead of `af.pols_if.projection.next_period()`
- AV change uses `af.av_pp_bef_prem * af.pols_if_bef_mat` instead of `af.av_pp * af.pols_if`

Remove the `# GAP N:` comments and replace with explanatory comments matching L4's style.

- [ ] **Step 2: Run model.py to verify**

Run: `uv run python tutorial/level-3-mini-va/steps/06-reconcile/model.py`
Expected: Prints 8 rows. PV values should closely match L4.

- [ ] **Step 3: Commit**

```
feat(tutorial): add L3 Step 06 model.py — reconciled reference answer
```

---

## Task 3: Create reconcile.py

**Files:**
- Create: `tutorial/level-3-mini-va/steps/06-reconcile/reconcile.py`

A comparison script that runs a Step 06 model against the lifelib reference and reports per-point PV differences. Follows the pattern of `tutorial/level-4-lifelib/reconcile.py`.

- [ ] **Step 1: Create reconcile.py**

The script should:
1. Accept `--model` flag: `"gaps"` (default) or `"fixed"` to select which model to run
2. Accept `--gaspatchio-output` flag to skip model run and use pre-computed parquet
3. Load model points from `tutorial/level-4-lifelib/base/model_points.parquet`
4. Import and run the selected model's `main(af)`
5. Load lifelib reference from `tutorial/level-4-lifelib/reference/lifelib_reference.parquet`, filter to t=0
6. Compare 10 PV variables per point (same list as L4's reconcile.py)
7. Print per-point table: point_id, product_id, plan_id, max_diff%, worst_variable, status (PASS/FAIL)
8. Print summary: max overall difference, tolerance (0.0001%), PASS/ALL counts
9. If `--model gaps`: also print a hint section showing which gaps likely caused which mismatches:
   - "GMAB points failing? → Check dynamic lapse formula (DL002)"
   - "All points off by small amount? → Check discount factor formula"
10. Exit code 0 if all pass, 1 if any fail

```python
# Key structure:
import sys
import argparse
from pathlib import Path

import polars as pl

STEP_DIR = Path(__file__).parent
L4_DIR = STEP_DIR.parent.parent.parent / "level-4-lifelib"
TOLERANCE_PCT = 0.0001

PV_VARIABLES = [
    ("pv_claims", "pv_claims", "PV Total Claims"),
    ("pv_claims_death", "pv_claims_death", "PV Death Claims"),
    # ... same 10 as L4's reconcile.py
]

def run_model(model_name: str) -> pl.DataFrame:
    mp = pl.read_parquet(L4_DIR / "base" / "model_points.parquet")
    from gaspatchio_core import ActuarialFrame
    af = ActuarialFrame(mp)
    if model_name == "gaps":
        import model_with_gaps as mod
    else:
        import model as mod
    return mod.main(af).collect()

def compare(gaspatchio_df, lifelib_df) -> tuple[bool, dict]:
    # Same comparison logic as L4's reconcile.py
    # Returns (all_pass, per_point_results)
    ...

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["gaps", "fixed"], default="gaps")
    parser.add_argument("--gaspatchio-output", type=str)
    args = parser.parse_args()
    # ... run, compare, report
```

- [ ] **Step 2: Test reconcile.py with model_with_gaps.py**

Run: `uv run python tutorial/level-3-mini-va/steps/06-reconcile/reconcile.py --model gaps`
Expected: GMAB points (5-8) show significant differences (DL002 gap). All points may show small differences (discount factor gap). Overall: FAIL.

- [ ] **Step 3: Test reconcile.py with model.py**

Run: `uv run python tutorial/level-3-mini-va/steps/06-reconcile/reconcile.py --model fixed`
Expected: All 8 points PASS at 0.0000% (or very close). Overall: PASS.

- [ ] **Step 4: Commit**

```
feat(tutorial): add L3 Step 06 reconcile.py — comparison script
```

---

## Task 4: Create README.md

**Files:**
- Modify: `tutorial/level-3-mini-va/steps/06-reconcile/README.md` (replace existing)

- [ ] **Step 1: Write README**

Structure:

```markdown
# Step 06: Reconciliation — From Tutorial to Production

> **Prerequisites:** Complete Steps 01-05. Familiarity with Level 4's model structure.

## What this step teaches

You've built a working VA model through Steps 01-05. Now you'll learn how to
**validate it against a reference implementation** — the discipline that separates
"it runs" from "it's correct."

This step uses Level 4's real assumption data and compares against lifelib's
IntegratedLife model output. Your Step 05 model has 4 deliberate gaps. You'll
discover each one through reconciliation and fix it.

## Quick start

[instructions to run model_with_gaps.py, then reconcile.py --model gaps, see failures]
[instructions to run model.py (reference answer), then reconcile.py --model fixed, see passes]

## The 4 gaps

### Gap 1: Account value — `cum_prod()` vs `accumulate()`

**What the gapped model does:** [description]
**What you'll see:** [intermediate variables missing, structural mismatch]
**The fix:** [replace cum_prod with accumulate, decompose AV]
**Why it matters:** [accumulate handles linear recurrences, NB support]
**gaspatchio concept:** `projection.accumulate(initial=..., multiply=..., add=...)`

### Gap 2: Decrement ordering — simple vs BEF_DECR

**What the gapped model does:** [description]
**What you'll see:** [small diff at maturity month in inv_income, av_change]
**The fix:** [maturities → new biz → deaths → lapses from survivors]
**Why it matters:** [multi-decrement timing, production standard]
**gaspatchio concept:** `projection.previous_period()`, `projection.next_period()` for timing

### Gap 3: Dynamic lapse — single formula vs product-specific

**What the gapped model does:** [DL001 only]
**What you'll see:** [GMAB points (5-8) show large lapse rate differences]
**The fix:** [when(formula_id == "DL001").then(dl001).otherwise(dl002)]
**Why it matters:** [product-specific policyholder behavior]
**gaspatchio concept:** `when().then().otherwise()` for formula selection

### Gap 4: Discount factors — `cum_prod()` vs closed-form

**What the gapped model does:** [cumulative product of per-period factors]
**What you'll see:** [all points off by small amount in PV variables]
**The fix:** [exp(-t * ln(1 + r)) closed-form]
**Why it matters:** [reconciliation means matching the reference formula]
**gaspatchio concept:** `exp()`, `log()` on list columns

## Recommended fix order

1. **Gap 3 (DL002)** first — largest numeric impact, easiest to diagnose
2. **Gap 4 (discount factors)** — affects all PV variables
3. **Gap 1 (accumulate)** — structural improvement, exposes intermediate variables
4. **Gap 2 (BEF_DECR)** — production standard ordering, subtle timing effects

## What changed from Step 05

[Table showing the data pipeline changes: L4 data, joins, unpivot, projection length]

## The reconciliation discipline

[Brief recap of the approach from the existing Step 06 README: one variable at a time,
 isolate inputs → formula → timing → rounding, fix cycle]

## Next: Level 4

With all 4 gaps fixed, your model matches Level 4. The Step 06 `model.py` IS the
Level 4 model, simplified for this tutorial's data pipeline. Level 4 adds:
- Storage mode optimization
- Scenario override parameters
- Support for multiple model point sets (2022Q4IF, 202401NB)
```

- [ ] **Step 2: Commit**

```
docs(tutorial): add L3 Step 06 README — reconciliation walkthrough
```

---

## Task 5: Update top-level tutorial README

**Files:**
- Modify: `tutorial/README.md`

- [ ] **Step 1: Update L3 Step 06 entry**

In the "Level 3 steps" table, update Step 06:

```markdown
| 06 | Reconcile | Bridge to Level 4 — 4 actuarial gaps discovered and fixed via reconciliation against lifelib |
```

- [ ] **Step 2: Commit**

```
docs(tutorial): update README with L3 Step 06 description
```

---

## Parallelization Notes

Tasks 1 and 2 share structure (model.py is model_with_gaps.py + 4 fixes), so Task 2 depends on Task 1.
Task 3 (reconcile.py) can be built in parallel with Task 2 but needs Task 1 for testing.
Task 4 (README) depends on Tasks 1-3 being verified.
Task 5 is a small update after everything else is done.

**Recommended sequence:** Task 1 → Task 2 → Task 3 → verify all → Task 4 → Task 5
