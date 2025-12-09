# AppliedLife - Gaspatchio Implementation of lifelib IntegratedLife

A complete Gaspatchio implementation of the [lifelib IntegratedLife](https://github.com/lifelib-dev/lifelib) model for variable annuity products with Guaranteed Minimum Benefits (GMXB).

## Overview

This model demonstrates a production-ready actuarial projection system built with Gaspatchio, achieving **100% reconciliation** with the original lifelib ModelX implementation. It supports:

- **Products:** GMDB (Guaranteed Minimum Death Benefit) and GMAB (Guaranteed Minimum Accumulation Benefit)
- **Mortality:** Select and ultimate mortality tables (2015 VBT) with duration-based scalar adjustments
- **Lapse Behavior:** Dynamic lapse formulas that adjust based on in-the-money ratio
- **Account Value:** Single-premium variable annuity mechanics with investment returns and fees
- **Economic Scenarios:** Multiple interest rate scenarios (BASE, UP, DOWN) with stochastic fund returns
- **Cashflows:** Death claims, surrender claims, maturity benefits, premiums, expenses, and commissions

### Reconciliation Status

**STATUS: ✓ 100% RECONCILED**

All 8 model points tested across 10 present value variables show differences at the level of floating-point precision (~10⁻¹²%). See [RECONCILIATION_REPORT.md](output/phase4_pv/RECONCILIATION_REPORT.md) for full details.

## Why lifelib as the Reference?

### What is lifelib?

[lifelib](https://lifelib.io) is an open-source actuarial modeling library created by Fumito Hanaoka. It provides production-quality life insurance models using [modelx](https://modelx.io), a Python framework for building complex calculation models with spreadsheet-like formula dependencies.

**Why it's a credible reference:**

- **Open source & peer-reviewed**: Code is publicly available and has been scrutinized by actuaries worldwide
- **Industry recognition**: Used by actuaries for prototyping, validation, and education
- **Well-documented**: Extensive documentation with formula explanations matching actuarial literature
- **Battle-tested**: The IntegratedLife model implements standard GMXB valuation techniques used in practice

### What We're Comparing

The reconciliation compares **every intermediate and final calculation** between the two implementations:

| Category | Variables Compared | What This Validates |
|----------|-------------------|---------------------|
| **Mortality** | `mort_rate`, `mort_rate_mth` | Correct table lookups, select/ultimate handling, scalar adjustments |
| **Lapse** | `base_lapse_rate`, `dyn_lapse_factor`, `lapse_rate` | Dynamic lapse formulas (DL001/DL002), ITM calculations |
| **Policy Counts** | `pols_if`, `pols_death`, `pols_lapse`, `pols_maturity` | Decrement ordering, survival calculations |
| **Account Value** | `av_pp_bef_prem`, `av_pp_mid_mth`, `inv_return_mth` | Fee deductions, investment returns, accumulation |
| **Cashflows** | `claims_*`, `premiums`, `expenses`, `commissions`, `net_cf` | Guarantee mechanics (GMDB/GMAB), surrender charges |
| **Present Values** | `pv_claims`, `pv_expenses`, `pv_net_cf`, etc. | Discount rate curves, time value calculations |

### What "100% Reconciliation" Means

When we say 100% reconciled, we mean:

1. **Numerical equivalence**: Both implementations produce identical results to machine precision (~10⁻¹² %)
2. **All paths tested**: 8 model points covering all product/plan/fund combinations
3. **Full projection**: 82-month projections with monthly granularity
4. **All variables**: Every intermediate calculation matches, not just final outputs

This level of precision confirms that the Gaspatchio implementation correctly replicates the actuarial logic of the reference model - the differences are purely floating-point rounding, not algorithmic.

## Quick Start

### Running the Model

Use the `gspio` CLI to run the model:

```bash
# Run the model for all 8 model points
uv run gspio run-model appliedlife/model_applied_life.py appliedlife/model_points.parquet

# Limit output display (first 5 columns, last 10 columns, 20 rows)
uv run gspio run-model appliedlife/model_applied_life.py appliedlife/model_points.parquet -f 5 -l 10 -r 20

# Run a single policy
uv run gspio run-single-policy appliedlife/model_applied_life.py appliedlife/model_points.parquet --policy-id 1
```

### Verifying Reconciliation

To confirm the model matches the lifelib reference:

```bash
uv run python appliedlife/scripts/verify_reconciliation.py
```

Expected output:
```
======================================================================
MODEL RECONCILIATION VERIFICATION
======================================================================

1. Running gaspatchio model (model_applied_life.py)...
   Model points: 8
   Output columns: 95

2. Loading lifelib reference (phase4_pv)...
   Reference points: 8

3. Comparing present values...
----------------------------------------------------------------------
Point    Product  Plan     Max Diff %      Status
----------------------------------------------------------------------
1        GMDB     PLAN_A   0.00000000      PASS
2        GMDB     PLAN_A   0.00000000      PASS
...

======================================================================
RESULT: ALL POINTS PASS - 100% RECONCILIATION ACHIEVED
======================================================================
```

## Directory Structure

```
appliedlife/
├── README.md                      # This file
├── MODEL_SPEC.md                  # Detailed technical specification
├── model_applied_life.py          # Main Gaspatchio model (reconciled)
├── model_scenarios.py             # Explicit scenarios example (BASE/UP/DOWN)
├── dynamic_scenarios.py           # Dynamic shocks example
├── SCENARIOS.md                   # Scenario support documentation
├── model_points.parquet           # 8 in-force policies for testing
├── assumptions/                   # Assumption tables (Parquet format)
│   ├── mortality_select.parquet   # Select mortality rates (25-year select period)
│   ├── mortality_ultimate.parquet # Ultimate mortality rates
│   ├── mortality_scalars.parquet  # Duration-based mortality adjustments
│   ├── lapse_rates.parquet        # Base lapse rates by duration
│   ├── dynamic_lapse_params.parquet # Dynamic lapse formula parameters
│   ├── surrender_charges.parquet  # Surrender charge schedules
│   ├── product_params_gmxb.parquet # Product configuration
│   ├── space_params.parquet       # Expense and space-level parameters
│   ├── risk_free_rates.parquet    # Interest rate curves (150 years)
│   └── scenario_returns.parquet   # Investment fund returns
├── scripts/                       # Utility scripts
│   ├── verify_reconciliation.py   # Quick reconciliation check
│   ├── reconcile_models.py        # Detailed variable-by-variable comparison
│   ├── run_integratedlife.py      # Run the lifelib reference model
│   ├── compare_models.py          # Side-by-side comparison
│   └── convert_assumptions.py     # Excel to Parquet converter
├── ref/                           # Original lifelib IntegratedLife model
│   └── appliedlife/               # ModelX implementation (reference)
└── output/                        # Model outputs and reconciliation results
    └── phase4_pv/                 # Present value reconciliation
        └── RECONCILIATION_REPORT.md
```

## Key Files

### Model Files

| File | Description |
|------|-------------|
| `model_applied_life.py` | Production Gaspatchio model - fully reconciled with lifelib |
| `model_points.parquet` | 8 test policies (4 GMDB + 4 GMAB, 2 plans each) |

### Documentation

| File | Description |
|------|-------------|
| `README.md` | This file - overview and usage guide |
| `MODEL_SPEC.md` | Complete technical specification with formulas and build order |
| `output/phase4_pv/RECONCILIATION_REPORT.md` | Detailed reconciliation results |

### Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `verify_reconciliation.py` | Quick check that model matches reference | `uv run python appliedlife/scripts/verify_reconciliation.py` |
| `reconcile_models.py` | Variable-by-variable comparison (for debugging) | `uv run python appliedlife/scripts/reconcile_models.py` |
| `run_integratedlife.py` | Run the lifelib reference model | `uv run python appliedlife/scripts/run_integratedlife.py --run-id 2` |
| `compare_models.py` | Side-by-side comparison of aggregated totals | `uv run python appliedlife/scripts/compare_models.py` |
| `convert_assumptions.py` | Convert Excel assumptions to Parquet | `uv run python appliedlife/scripts/convert_assumptions.py` |

## Model Points

The test dataset contains 8 in-force policies representing different product/plan combinations:

| Point ID | Product | Plan   | Fund   | Age | Sex | Term | Sum Assured | Premium   | AV Initial |
|----------|---------|--------|--------|-----|-----|------|-------------|-----------|------------|
| 1        | GMDB    | PLAN_A | FUND6  | 70  | M   | 10   | 500,000     | 500,000   | 550,000    |
| 2        | GMDB    | PLAN_A | FUND4  | 70  | F   | 10   | 500,000     | 475,000   | 522,500    |
| 3        | GMDB    | PLAN_B | FUND5  | 70  | M   | 10   | 500,000     | 450,000   | 495,000    |
| 4        | GMDB    | PLAN_B | FUND6  | 70  | F   | 10   | 500,000     | 425,000   | 467,500    |
| 5        | GMAB    | PLAN_A | FUND4  | 70  | M   | 10   | 500,000     | 400,000   | 440,000    |
| 6        | GMAB    | PLAN_A | FUND4  | 70  | F   | 10   | 500,000     | 375,000   | 412,500    |
| 7        | GMAB    | PLAN_B | FUND5  | 70  | M   | 10   | 500,000     | 350,000   | 385,000    |
| 8        | GMAB    | PLAN_B | FUND6  | 70  | F   | 10   | 500,000     | 325,000   | 357,500    |

**Coverage:**
- **Products:** GMDB (death benefit guarantee) and GMAB (maturity benefit guarantee)
- **Plans:** PLAN_A (3% commission, SC001 surrender charges) and PLAN_B (5% commission, SC002 surrender charges)
- **Funds:** FUND4 (USD, 6% return), FUND5 (USD, 8% return), FUND6 (USD, 10% return)
- **Demographics:** Male and Female, all age 70 at entry

All policies are single-premium, in-force (entered before valuation date), and projected for 10-year terms.

## Assumptions

### Mortality

| Table | Description | Usage |
|-------|-------------|-------|
| T3275 | 2015 VBT Male | Male lives |
| T3276 | 2015 VBT Female | Female lives |

- **Select Period:** 25 years (mortality varies by attained age AND duration)
- **Ultimate Period:** After 25 years (mortality varies by attained age only)
- **Scalars:** Duration-based adjustment factors (M001-M004)

### Lapse

**Base Lapse Rates** (L001-L004): Duration-based annual rates from 3% to 10%

**Dynamic Lapse Formulas:** Adjust for in-the-money ratio (ITM = Account Value / Guarantee)

- **DL001A/DL001B:** `factor = clip(1 - M * (1/ITM - D), L, U)`
- **DL002A/DL002B:** `factor = clip(Y * ITM^Power, FactorFloor, FactorCap)`

Final lapse rate: `max(dyn_lapse_floor, factor * base_lapse_rate)`

### Products

| Product | Plan | GMDB | GMAB | Premium | Surrender | Mortality | Lapse | Dynamic Lapse |
|---------|------|------|------|---------|-----------|-----------|-------|---------------|
| GMDB | PLAN_A | Yes | No | SINGLE | SC001 | T3275/T3276 | L001 | DL001A |
| GMDB | PLAN_B | Yes | No | SINGLE | SC002 | T3275/T3276 | L003 | DL001B |
| GMAB | PLAN_A | Yes | Yes | SINGLE | SC001 | T3275/T3276 | L002 | DL002A |
| GMAB | PLAN_B | Yes | Yes | SINGLE | SC002 | T3275/T3276 | L004 | DL002B |

**Product Parameters:**
- `load_prem_rate`: Premium load (% of premium not added to AV)
- `maint_fee_rate`: Monthly maintenance fee (% of AV)
- `commission_rate`: Commission on premiums (3% for PLAN_A, 5% for PLAN_B)

### Economic

**Investment Funds:**

| Fund | Currency | Return | Volatility | Risk-Free Rate |
|------|----------|--------|------------|----------------|
| FUND1 | EUR | 5% | 8% | 3% |
| FUND2 | GBP | 6% | 12% | 3% |
| FUND3 | JPY | 2% | 4% | 1% |
| FUND4 | USD | 6% | 4% | 5% |
| FUND5 | USD | 8% | 12% | 5% |
| FUND6 | USD | 10% | 20% | 5% |

**Interest Rate Scenarios:**
- BASE: Base interest rate curve
- UP: Rates shifted up by 100bp
- DOWN: Rates shifted down by 100bp

**Expenses:**
- Acquisition: 5,000 per policy (one-time at issue)
- Maintenance: 500 per policy per year (inflated at 1% annually)

## Model Output

The model produces comprehensive projection results including:

### Policy Counts
- `pols_if`: Policies in force
- `pols_death`: Deaths
- `pols_lapse`: Lapses/surrenders
- `pols_maturity`: Maturities
- `pols_new_biz`: New business

### Account Values
- `av_pp_bef_prem`: Account value per policy before premium
- `av_pp_bef_fee`: After premium, before fees
- `av_pp_bef_inv`: After fees, before investment
- `av_pp_mid_mth`: Mid-month (for ITM calculation)

### Cashflows
- `premiums`: Premium income
- `claims`: Total claims (death + lapse + maturity)
- `claims_death`: Death benefit claims (with GMDB guarantee)
- `claims_lapse`: Surrender claims (net of surrender charges)
- `claims_maturity`: Maturity benefit (with GMAB guarantee)
- `expenses`: Acquisition + maintenance expenses
- `commissions`: Commission payments
- `inv_income`: Investment income
- `net_cf`: Net cashflow

### Present Values (per policy)
- `pv_claims`: Total PV of claims
- `pv_claims_death`: PV of death claims
- `pv_claims_lapse`: PV of surrender claims
- `pv_claims_maturity`: PV of maturity claims
- `pv_expenses`: PV of expenses
- `pv_commissions`: PV of commissions
- `pv_premiums`: PV of premiums
- `pv_inv_income`: PV of investment income
- `pv_av_change`: PV of account value changes
- `pv_net_cf`: PV of net cashflow

## Reconciliation Workflow

The model was built incrementally and reconciled against lifelib at each step:

### Phase 1: Base Decrements
1. Basic projection timeline
2. Mortality rates (select table + scalars)
3. Deaths
4. Base lapse rates
5. Lapses
6. Policies in force

**Status:** ✓ All policy variables match (0.0000% diff)

### Phase 2: Account Value & Dynamic Lapse
7. Account value mechanics
8. Dynamic lapse factor
9. Re-enabled dynamic lapse

**Status:** ✓ Account value and dynamic lapse match

### Phase 3: Cashflows
10. Claims (death, lapse, maturity with guarantees)
11. Premiums
12. Expenses (acquisition + maintenance with inflation)
13. Commissions
14. Net cashflow (including investment income and AV changes)

**Status:** ✓ All cashflows match

### Phase 4: Present Values
15. Discount rates and factors
16. Present values for all cashflow components

**Status:** ✓ All 10 PV variables match within floating-point precision

### How to Verify

To verify reconciliation yourself:

```bash
# Quick check (runs model and compares PV results)
uv run python appliedlife/scripts/verify_reconciliation.py

# Detailed variable-by-variable analysis
uv run python appliedlife/scripts/reconcile_models.py

# Side-by-side comparison of aggregated totals
uv run python appliedlife/scripts/compare_models.py
```

## Reference Model

The original lifelib IntegratedLife model is located in `ref/appliedlife/`. It uses ModelX, a Python library for actuarial modeling based on spreadsheet-like dependency graphs.

**Key differences:**
- **lifelib (ModelX):** Cells-and-formulas paradigm, lazy evaluation
- **Gaspatchio:** DataFrame-based pipelines, vectorized operations

Despite the different paradigms, the Gaspatchio implementation achieves exact numerical equivalence with the ModelX original.

**Links:**
- [lifelib GitHub](https://github.com/lifelib-dev/lifelib)
- [lifelib Documentation](https://lifelib.readthedocs.io/)
- [IntegratedLife Model](https://github.com/lifelib-dev/lifelib/tree/main/lifelib/libraries/appliedlife)

## Advanced Usage

### Running with Scenarios

The model supports multiple economic scenarios. See [SCENARIOS.md](SCENARIOS.md) for full documentation.

**Quick start:**

```bash
# Explicit scenarios (BASE/UP/DOWN interest rates)
uv run python appliedlife/model_scenarios.py

# Dynamic shocks (fund return sensitivity)
uv run python appliedlife/dynamic_scenarios.py
```

### Running the Reference Model

To generate fresh lifelib reference data:

```bash
# Run with matching settings for reconciliation (8 points, 1 scenario, GMXB)
uv run python appliedlife/scripts/run_integratedlife.py \
    --run-id 2 --num-scenarios 1 --products gmxb --verbose

# Run with all scenarios (deterministic + stochastic)
uv run python appliedlife/scripts/run_integratedlife.py --run-id 2
```

### Regenerating Assumption Files

The assumption tables are stored in Parquet format for performance. If you need to regenerate them from the original Excel files:

```bash
uv run python appliedlife/scripts/convert_assumptions.py
```

This reads from `ref/appliedlife/input_tables/` and writes to `assumptions/`.

### Programmatic Usage

You can also import and use the model directly:

```python
import polars as pl
from gaspatchio_core import ActuarialFrame
from appliedlife.model_applied_life import main

# Load model points
mp = pl.read_parquet('appliedlife/model_points.parquet')
af = ActuarialFrame(mp)

# Run projection
result = main(af)

# Collect results as DataFrame
df = result.collect()

# Access specific variables
pv_claims = df.select(['point_id', 'pv_claims'])
print(pv_claims)
```

## Technical Notes

### Monthly Rate Conversion

Annual rates are converted to monthly using the constant force assumption:

```python
q_monthly = 1 - (1 - q_annual) ** (1/12)
```

This is standard actuarial practice and differs from simple division (`q_annual / 12`).

### Dynamic Lapse Behavior

The model implements rational policyholder behavior:
- When guarantees are out-of-the-money (ITM > 1): Higher lapse rates
- When guarantees are in-the-money (ITM < 1): Lower lapse rates

This reflects that policyholders are less likely to surrender when the guarantee has value.

### Timing Conventions

The model uses three in-force timing points per period:
- **BEF_MAT**: Before maturity (after previous period's decrements)
- **BEF_NB**: Before new business (after maturity)
- **BEF_DECR**: Before decrements (after new business)

Deaths occur before lapses in the same period.

### Numerical Precision

All reconciliation differences are at the level of floating-point precision:
- Typical: 10⁻¹² to 10⁻¹⁴ percent
- Maximum observed: 4.27 × 10⁻¹² percent

This corresponds to absolute differences of less than $0.01 for most variables.

## License

This model implementation is provided for educational and demonstration purposes. The original lifelib library is released under the MIT License.

## Support

For questions about:
- **Gaspatchio framework:** See the main gaspatchio repository
- **lifelib reference model:** See [lifelib documentation](https://lifelib.readthedocs.io/)
- **This implementation:** Check MODEL_SPEC.md for technical details

---

**Generated:** 2025-12-08
**Gaspatchio Version:** Latest
**lifelib Version:** 0.9.x (IntegratedLife model)
