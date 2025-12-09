# Gaspatchio Model Specification: AppliedLife GMXB

## Overview

This specification defines a Gaspatchio implementation of the lifelib IntegratedLife model for variable annuity products with Guaranteed Minimum Benefits (GMXB).

**Objective**: 100% reconciliation with lifelib IntegratedLife model output.

**Source of Truth**: `appliedlife/ref/appliedlife/IntegratedLife/ProductBase/__init__.py`

---

## Actuarial Background

This section provides actuarial context for the key concepts used in this model. Understanding these fundamentals is essential for correct implementation and debugging.

### Variable Annuities with Guaranteed Minimum Benefits (GMXB)

Variable annuities (VAs) are long-term insurance contracts where:
- Premiums are invested in separate account funds (typically equity/bond funds)
- Account value fluctuates with investment performance
- Policyholder bears investment risk on the underlying assets
- Insurer provides **guarantees** that protect against downside risk

**Sources**: SOA "Pricing and Risk Management of Variable Annuities with Multiple Guaranteed Minimum Benefits"

### GMDB (Guaranteed Minimum Death Benefit)

- **Definition**: Guarantees that the death benefit will be at least a minimum amount, regardless of account performance
- **Typical Structures**:
  - **Return of Premium**: Death benefit = max(AV, total premiums paid)
  - **Ratchet (MAV)**: Death benefit = max(AV, highest anniversary value)
  - **Roll-up**: Death benefit = max(AV, premium accumulated at X% per year)
  - **Combination**: max(AV, ratchet value, roll-up value)
- **In This Model**: Death benefit = max(sum_assured, account_value) when `has_gmdb = true`
- **Fees**: Typically 15-35 bps of account value per annum

### GMAB (Guaranteed Minimum Accumulation Benefit)

- **Definition**: Guarantees that the surrender value will be at least a minimum amount at a specified future date
- **Typical Structure**: At maturity, policyholder receives max(account_value, guaranteed_value)
- **In This Model**: Maturity benefit = max(sum_assured, account_value) when `has_gmab = true`
- **Key Difference from GMDB**: Paid on survival to maturity, not death
- **Fees**: Typically 25-75 bps of account value per annum

### Option-Like Characteristics

Both GMDB and GMAB are economically similar to **put options**:
- The policyholder has the right to receive at least the guaranteed amount
- The "strike price" is the guaranteed value (sum_assured)
- The "underlying" is the account value
- The guarantee has value when AV < guaranteed value ("in the money")

**Guarantee Cost** = Claim paid - Claim from account value
= max(guarantee, AV) - AV
= max(guarantee - AV, 0)  ← This is the put option payoff

### Select and Ultimate Mortality

Life insurance mortality tables often distinguish between:

**Select Period** (first N years after policy issue):
- Mortality rates depend on **both** attained age AND duration since issue
- Reflects underwriting selection effect - recently underwritten lives have lower mortality
- Lookup: `rate = table[attained_age, duration]`

**Ultimate Period** (after select period):
- Mortality rates depend only on attained age
- Selection effect has "worn off"
- Lookup: `rate = table[attained_age]`

**In This Model**:
- Select period: 25 years (duration 0-24)
- For duration ≥ 25, use ultimate rates
- Tables: VBT 2015 (T3275 male, T3276 female)

### Monthly Rate Conversion

Annual rates must be converted to monthly for monthly projection models.

**Formula** (constant force of mortality assumption):
```
q_monthly = 1 - (1 - q_annual)^(1/12)
```

**Why not q_annual / 12?**
- Simple division assumes deaths occur uniformly throughout the year
- The power formula assumes a **constant force of mortality** (exponential survival)
- The constant force assumption is standard actuarial practice
- Example: If q_annual = 12%, then q_monthly = 1 - (0.88)^(1/12) = 1.06% (not 1.00%)

**Source**: SOA "Experience Study Calculations" monograph

### Dynamic Lapse Behavior

Lapse rates for VAs with guarantees are not static - they depend on the **moneyness** of the guarantee.

**In-The-Money (ITM) Ratio**:
```
ITM = Account Value / Guaranteed Value
```

**Behavioral Economics**:
- When ITM > 1 (guarantee out-of-money): Higher lapse propensity - guarantee has little value
- When ITM < 1 (guarantee in-the-money): Lower lapse propensity - guarantee is valuable
- This is **rational economic behavior** - policyholders optimize their position

**Two Main Hypotheses** (from academic literature):
1. **Interest Rate Hypothesis**: Lapses inversely related to internal returns vs external alternatives
2. **Emergency Funds Hypothesis**: Lapses driven by policyholder financial distress

**In This Model** (two dynamic lapse formulas):

**DL001** (multiplicative adjustment):
```
factor = min(U, max(L, 1 - M * (1/ITM - D)))
lapse_rate = factor * base_lapse_rate
```

**DL002** (power function):
```
factor = min(FactorCap, max(FactorFloor, Y * ITM^Power))
lapse_rate = factor * base_lapse_rate
```

Both formulas apply a floor to prevent negative lapse rates.

**Source**: SOA "Modeling of Policyholder Behavior for Life Insurance and Annuity Products", a commercial provider "Variable Annuity Dynamic Lapse Study"

### Account Value Mechanics

The account value is the policyholder's investment account, which evolves as:

```
AV(t+1) = [AV(t) + Premium - Fees] × (1 + Investment Return)
```

**Fee Types**:
- **Premium Load**: Percentage of premium not added to AV (covers acquisition costs)
- **M&E (Mortality & Expense)**: Percentage of AV (covers mortality risk + admin)
- **Maintenance Fee**: Flat or percentage fee for administration
- **COI (Cost of Insurance)**: Charge for mortality risk = COI_rate × Net Amount at Risk
- **Surrender Charge**: Applied if policyholder surrenders early (decreases over time)

**Net Amount at Risk** (NAAR):
```
NAAR = max(Death Benefit - Account Value, 0)
```
This is the amount the insurer is "at risk" for if the policyholder dies.

**In This Model**:
- COI is set to 0 (disabled)
- Maintenance fee = maint_fee_rate × AV (monthly)
- Premium load = load_prem_rate × premium
- Surrender charges decline over first ~10 years

### Present Value Calculation

Future cashflows are discounted to valuation date using risk-free rates.

**Discount Factor**:
```
disc_factors(t) = (1 + disc_rate_mth)^(-t)
```

**Present Value**:
```
PV = Σ cashflow(t) × disc_factors(t)
```

For monthly models, the monthly discount rate is derived from annual:
```
disc_rate_mth = (1 + disc_rate_annual)^(1/12) - 1
```

---

## 1. Model Configuration

### Run Parameters (run_id=2 for reconciliation)

| Parameter | Value |
|-----------|-------|
| base_date | 2023-12-31 |
| valuation_date | 2024-01-01 (base_date + 1 day) |
| mp_file_id | 2023Q4IF |
| sens_int_rate | BASE |
| space | GMXB |

### Space Parameters (GMXB)

| Parameter | Value |
|-----------|-------|
| expense_acq | 5000 |
| expense_maint | 500 |
| currency | USD |
| is_lapse_dynamic | true |

---

## 2. Model Points

**File**: `appliedlife/model_points.parquet`
**Count**: 8 policies (4 GMDB + 4 GMAB)

### Schema

| Column | Type | Description |
|--------|------|-------------|
| point_id | i64 | Unique policy identifier |
| product_id | str | GMDB or GMAB |
| plan_id | str | PLAN_A or PLAN_B |
| entry_date | str | Issue date (YYYY/MM/DD format) |
| age_at_entry | i64 | Issue age |
| sex | str | M or F |
| policy_term | i64 | Contract term in years |
| fund_index | str | Investment fund (FUND1-FUND6) |
| policy_count | i64 | Number of policies in group |
| sum_assured | i64 | Guarantee amount |
| duration_mth | i64 | Initial months in force (from model point file) |
| premium_pp | i64 | Premium per policy |
| av_pp_init | i64 | Initial account value per policy |
| accum_prem_init_pp | i64 | Accumulated premium per policy |

### Model Point Preparation

Model points must be joined with product parameters to add:
- has_gmdb, has_gmab
- premium_type (SINGLE/LEVEL)
- has_surr_charge, surr_charge_id
- load_prem_rate, maint_fee_rate, commission_rate
- mort_table_male, mort_table_female
- mort_scalar_id, lapse_id
- dyn_lapse_param_id, dyn_lapse_floor
- is_wl (whole life flag)

---

## 3. Projection Parameters

### Duration Calculation

```
duration_mth_init = (val_date.year * 12 + val_date.month)
                  - (entry_date.year * 12 + entry_date.month)
```

Where `val_date = base_date + 1 day = 2024-01-01`

### Projection Length

```
proj_len = max(12 * policy_term - duration_mth_init + 1, 0)
max_proj_len = max(proj_len) across all model points
```

### Time Variables

| Variable | Formula |
|----------|---------|
| duration_mth(t) | duration_mth_init + t |
| duration(t) | duration_mth(t) // 12 |
| age(t) | age_at_entry + duration(t) |

---

## 4. Assumption Tables

### 4.1 Mortality (Select/Ultimate)

**Files**:
- `mortality_select.parquet` - Select period rates (9,600 rows)
- `mortality_ultimate.parquet` - Ultimate rates (2,178 rows)
- `mortality_table_defs.parquet` - Table metadata
- `mortality_scalars.parquet` - Duration-based multipliers

**Lookup Key**: (table_id, attained_age, duration)
- table_id selected by sex: mort_table_male if sex="M" else mort_table_female
- Duration capped at select_period_length (typically 25 years)
- Beyond select period, use ultimate rate (indexed by attained_age only)

**Active Tables**:
- T3275: 2015 VBT Male
- T3276: 2015 VBT Female

**Formulas**:
```
mort_table_id = mort_table_male if sex == "M" else mort_table_female
base_mort_rate(t) = lookup(table_id, age(t), min(duration(t), select_duration_cap))
mort_scalar(t) = lookup(mort_scalar_id, min(duration(t), scalar_duration_cap))
mort_rate(t) = mort_scalar(t) * base_mort_rate(t)
mort_rate_mth(t) = 1 - (1 - mort_rate(t))^(1/12)
```

### 4.2 Lapse Rates

**Files**:
- `lapse_rates.parquet` - Base lapse rates by (duration, lapse_id)
- `dynamic_lapse_params.parquet` - Dynamic lapse formula parameters

**Base Lapse**:
```
base_lapse_rate(t) = lookup(lapse_id, min(duration(t), lapse_duration_cap))
```

**Dynamic Lapse** (when is_lapse_dynamic = true):

Two formula types based on dyn_lapse_id:

**DL001 Formula**:
```
itm = av_pp_at(t, "MID_MTH") / sum_assured
factor = min(U, max(L, 1 - M * (1/itm - D)))
```

**DL002 Formula**:
```
itm = av_pp_at(t, "MID_MTH") / sum_assured
factor = min(FactorCap, max(FactorFloor, Y * (itm^Power)))
```

**Final Lapse Rate**:
```
lapse_rate(t) = max(dyn_lapse_floor, dyn_lapse_factor(t) * base_lapse_rate(t))
lapse_rate_mth(t) = 1 - (1 - lapse_rate(t))^(1/12)
```

### 4.3 Surrender Charges

**File**: `surrender_charges.parquet` - Rates by (duration, surr_charge_id)

```
surr_charge_rate(t) = lookup(surr_charge_id, min(duration(t), surr_charge_duration_cap))
                      if has_surr_charge else 0
```

### 4.4 Investment Returns

**File**: `risk_free_rates.parquet` - Forward rates by (scenario, currency, year)
**File**: `index_parameters.parquet` - Fund characteristics

```
disc_rate(t) = lookup(scenario, currency, t // 12)  # Annual spot rate
disc_rate_mth(t) = (1 + disc_rate(t))^(1/12) - 1

inv_return_mth(t) = lookup from scenario data by fund_index
```

### 4.5 Inflation

```
inflation_rate = 0.01  # 1% annual (hardcoded in lifelib)
inflation_factor(t) = (1 + inflation_rate)^(t/12)
```

---

## 5. Policy Counts (Decrements)

### Timing Concepts

The model uses three in-force timing points within each period:

| Timing | Description |
|--------|-------------|
| BEF_MAT | Before maturity (after previous period's lapse/death) |
| BEF_NB | Before new business (after maturity) |
| BEF_DECR | Before decrements (after new business) |

### Formulas

**Initial In-Force**:
```
pols_if_init = policy_count if duration_mth_init > 0 else 0
```
(Existing policies only; new business enters via pols_new_biz)

**New Business**:
```
pols_new_biz(t) = policy_count if duration_mth(t) == 0 else 0
```

**Maturity**:
```
pols_maturity(t) = pols_if_at(t, "BEF_MAT") if duration_mth(t) == policy_term * 12 else 0
```

**Deaths**:
```
pols_death(t) = pols_if_at(t, "BEF_DECR") * mort_rate_mth(t)
```

**Lapses**:
```
pols_lapse(t) = (pols_if_at(t, "BEF_DECR") - pols_death(t)) * lapse_rate_mth(t)
```

**Policy In-Force at Timing Points**:
```
pols_if_at(t, "BEF_MAT"):
    t=0: pols_if_init
    t>0: pols_if_at(t-1, "BEF_DECR") - pols_lapse(t-1) - pols_death(t-1)

pols_if_at(t, "BEF_NB") = pols_if_at(t, "BEF_MAT") - pols_maturity(t)

pols_if_at(t, "BEF_DECR") = pols_if_at(t, "BEF_NB") + pols_new_biz(t)
```

**Main Output**:
```
pols_if(t) = pols_if_at(t, "BEF_MAT")  # Alias for reporting
```

---

## 6. Account Value

### Per-Policy Account Value

Account value evolves through multiple timing points within each period:

| Timing | Description |
|--------|-------------|
| BEF_PREM | Before premium payment |
| BEF_FEE | After premium, before fee deduction |
| BEF_INV | After fee deduction, before investment credit |
| MID_MTH | Mid-month (half investment income credited) |

### Formulas

```
av_pp_at(t, "BEF_PREM"):
    t=0: av_pp_init (from model point)
    t>0: av_pp_at(t-1, "BEF_INV") + inv_income_pp(t-1)

av_pp_at(t, "BEF_FEE") = av_pp_at(t, "BEF_PREM") + prem_to_av_pp(t)

av_pp_at(t, "BEF_INV") = av_pp_at(t, "BEF_FEE") - maint_fee_pp(t) - coi_pp(t)

av_pp_at(t, "MID_MTH") = av_pp_at(t, "BEF_INV") + 0.5 * inv_income_pp(t)
```

### Supporting Calculations

```
prem_to_av_pp(t) = (1 - load_prem_rate) * premium_pp(t)

maint_fee_pp(t) = (maint_fee_rate / 12) * av_pp_at(t, "BEF_FEE")

coi_pp(t) = coi_rate(t) * net_amt_at_risk(t)
coi_rate(t) = 0  # COI is disabled in lifelib GMXB

net_amt_at_risk(t) = max(sum_assured - av_pp_at(t, "BEF_FEE"), 0)

inv_income_pp(t) = inv_return_mth(t) * av_pp_at(t, "BEF_INV")
```

### Premium Logic

```
premium_pp(t):
    if premium_type == "SINGLE":
        return premium_pp if duration_mth(t) == 0 else 0
    elif premium_type == "LEVEL":
        return premium_pp if duration_mth(t) < 12 * policy_term else 0
```

### Total Account Value

```
av_at(t, "BEF_MAT") = av_pp_at(t, "BEF_PREM") * pols_if_at(t, "BEF_MAT")
av_at(t, "BEF_NB") = av_pp_at(t, "BEF_PREM") * pols_if_at(t, "BEF_NB")
av_at(t, "BEF_FEE") = av_pp_at(t, "BEF_FEE") * pols_if_at(t, "BEF_DECR")

av_change(t) = av_at(t+1, "BEF_MAT") - av_at(t, "BEF_MAT")
```

---

## 7. Claims

### Per-Policy Claim Amounts

**Death Claim**:
```
claim_pp(t, "DEATH"):
    if has_gmdb:
        return max(sum_assured, av_pp_at(t, "MID_MTH"))
    else:
        return av_pp_at(t, "MID_MTH")
```

**Surrender Claim**:
```
claim_pp(t, "LAPSE") = av_pp_at(t, "MID_MTH")
csv_pp(t) = (1 - surr_charge_rate(t)) * av_pp_at(t, "MID_MTH")
```

**Maturity Claim**:
```
claim_pp(t, "MATURITY"):
    if has_gmab:
        return max(sum_assured, av_pp_at(t, "BEF_PREM"))
    else:
        return av_pp_at(t, "BEF_PREM")
```

### Total Claims

```
claims(t, "DEATH") = claim_pp(t, "DEATH") * pols_death(t)

claims(t, "LAPSE") = claims_from_av(t, "LAPSE") - surr_charge(t)
                   = av_pp_at(t, "MID_MTH") * pols_lapse(t) - surr_charge(t)

claims(t, "MATURITY") = claim_pp(t, "MATURITY") * pols_maturity(t)

claims(t) = claims(t, "DEATH") + claims(t, "LAPSE") + claims(t, "MATURITY")
```

### Claims from Account Value

```
claims_from_av(t, "DEATH") = av_pp_at(t, "MID_MTH") * pols_death(t)
claims_from_av(t, "LAPSE") = av_pp_at(t, "MID_MTH") * pols_lapse(t)
claims_from_av(t, "MATURITY") = av_pp_at(t, "BEF_PREM") * pols_maturity(t)
```

### Claims Over Account Value (Guarantee Cost)

```
claims_over_av(t, kind) = claims(t, kind) - claims_from_av(t, kind)
```

---

## 8. Other Cashflows

### Premiums

```
premiums(t) = premium_pp(t) * pols_if_at(t, "BEF_DECR")
prem_to_av(t) = prem_to_av_pp(t) * pols_if_at(t, "BEF_DECR")
```

### Expenses

```
expenses(t) = expense_acq * pols_new_biz(t)
            + pols_if_at(t, "BEF_DECR") * (expense_maint / 12) * inflation_factor(t)
```

### Commissions

```
commissions(t) = commission_rate * premiums(t)
```

### Fees (deducted from AV)

```
maint_fee(t) = maint_fee_pp(t) * pols_if_at(t, "BEF_DECR")
coi(t) = coi_pp(t) * pols_if_at(t, "BEF_DECR")

surr_charge(t) = surr_charge_rate(t) * av_pp_at(t, "MID_MTH") * pols_lapse(t)
```

### Investment Income

```
inv_income(t) = inv_income_pp(t) * pols_if_at(t+1, "BEF_MAT")
              + 0.5 * inv_income_pp(t) * (pols_death(t) + pols_lapse(t))
```

---

## 9. Net Cashflow

```
net_cf(t) = premiums(t)
          + inv_income(t)
          - claims(t)
          - expenses(t)
          - commissions(t)
          - av_change(t)
```

---

## 10. Present Values

### Discount Factors

```
disc_factors(t) = (1 + disc_rate_mth(t))^(-t)
```

### Present Value Formulas

```
pv_premiums = sum(premiums(t) * disc_factors(t) for t in range(max_proj_len))
pv_claims(kind) = sum(claims(t, kind) * disc_factors(t) for t in range(max_proj_len))
pv_claims = pv_claims("DEATH") + pv_claims("LAPSE") + pv_claims("MATURITY")
pv_expenses = sum(expenses(t) * disc_factors(t) for t in range(max_proj_len))
pv_commissions = sum(commissions(t) * disc_factors(t) for t in range(max_proj_len))
pv_inv_income = sum(inv_income(t) * disc_factors(t) for t in range(max_proj_len))
pv_av_change = sum(av_change(t) * disc_factors(t) for t in range(max_proj_len))

pv_net_cf = pv_premiums + pv_inv_income - pv_claims - pv_expenses - pv_commissions - pv_av_change
```

---

## 11. Output Variables for Reconciliation

### gmxb_pols.csv (Time Series, Aggregated)

| Variable | Gaspatchio Name | Aggregation |
|----------|-----------------|-------------|
| pols_if | pols_if | sum across points |
| pols_maturity | pols_maturity | sum across points |
| pols_new_biz | pols_new_biz | sum across points |
| pols_death | pols_death | sum across points |
| pols_lapse | pols_lapse | sum across points |

### gmxb_cf.csv (Time Series, Aggregated)

| Variable | Gaspatchio Name | Aggregation |
|----------|-----------------|-------------|
| Premiums | premiums | sum across points |
| Claims | claims_total | sum across points |
| Expenses | expenses_total | sum across points |
| Commissions | commissions | sum across points |
| Net Cashflow | cf_net | sum across points |

### gmxb_pv.csv (Per Model Point)

| Variable | Gaspatchio Name |
|----------|-----------------|
| Premiums | pv_premiums |
| Death | pv_claims_death |
| Surrender | pv_claims_lapse |
| Maturity | pv_claims_maturity |
| Expenses | pv_expenses |
| Commissions | pv_commissions |
| Investment Income | pv_inv_income |
| Change in AV | pv_av_change |
| Net Cashflow | pv_net_cf |

---

## 12. Incremental Build Order

Build and reconcile in this order:

### Phase 1: Policy Counts (Foundation)
1. duration_mth_init, duration_mth(t), duration(t), age(t)
2. proj_len, max_proj_len
3. pols_if_init, pols_new_biz
4. pols_maturity
5. mort_rate (with select/ultimate lookup)
6. pols_death
7. lapse_rate (base only first)
8. pols_lapse
9. pols_if_at (all timings), pols_if

### Phase 2: Account Value
10. av_pp_init
11. premium_pp, prem_to_av_pp
12. maint_fee_pp (simple)
13. inv_return_mth, inv_income_pp
14. av_pp_at (all timings)
15. av_at (all timings), av_change

### Phase 3: Dynamic Lapse
16. dyn_lapse_factor (requires av_pp_at)
17. Update lapse_rate to use dynamic
18. Re-verify pols_lapse

### Phase 4: Claims
19. claim_pp (DEATH, LAPSE, MATURITY with GMDB/GMAB logic)
20. claims (all types)
21. claims_from_av, claims_over_av
22. surr_charge

### Phase 5: Other Cashflows
23. premiums
24. expenses (with inflation_factor)
25. commissions
26. maint_fee, coi
27. inv_income

### Phase 6: Net Cashflow
28. net_cf

### Phase 7: Present Values
29. disc_rate, disc_rate_mth, disc_factors
30. All pv_* variables

---

## 13. Key Implementation Notes

### Gaspatchio-Specific Considerations

1. **Vectorized Time Series**: Use `create_projection_timeline` for monthly projection
2. **Cumulative Products**: Use `.projection.cumulative_survival()` for survival probabilities
3. **Conditional Logic**: Use `when().then().otherwise()` for GMDB/GMAB conditions
4. **Table Lookups**: Use `Table.lookup()` for assumption table access
5. **List Operations**: Results are list columns; use `.list.sum()` for aggregation

### Common Pitfalls

1. **Duration Calculation**: lifelib uses `base_date + 1 day` as valuation date
2. **Monthly Conversion**: `1 - (1 - annual_rate)^(1/12)`, not `annual_rate / 12`
3. **Select/Ultimate Boundary**: Duration capped at select period length for lookup
4. **Policy Timing**: Death occurs before lapse in same period
5. **Lapse Calculation**: Applied to (pols_if_at(BEF_DECR) - pols_death), not full BEF_DECR

### Reconciliation Tolerance

- Target: < 0.01% difference on all variables
- Check at both aggregate and per-policy level
- Time series must match at every month, not just totals

---

## Appendix A: Assumption File Schemas

### mortality_select.parquet
- Dimensions: table_id, attained_age, duration
- Value: mort_rate
- Duration range: 0-24 (25 years select period)

### mortality_ultimate.parquet
- Dimensions: attained_age, table_id
- Value: mort_rate
- Age range: 0-120

### lapse_rates.parquet
- Dimensions: duration, lapse_id
- Value: lapse_rate
- Duration range: 0-14 (15 years)

### dynamic_lapse_params.parquet
- Dimensions: formula_id
- Values: U, L, M, D (DL001) or Y, Power, FactorCap, FactorFloor (DL002)

### surrender_charges.parquet
- Dimensions: duration, surr_charge_id
- Value: surr_charge_rate
- Duration range: 0-9 (10 years)

### risk_free_rates.parquet
- Dimensions: scenario, currency, year
- Value: forward_rate
- Scenarios: BASE, UP, DOWN
- Years: 0-149 (150 years)

---

## Appendix B: Product Configuration Reference

| Product | Plan | GMDB | GMAB | Premium | Surr Charge | Mort Table | Lapse | Dyn Lapse |
|---------|------|------|------|---------|-------------|------------|-------|-----------|
| GMDB | PLAN_A | Yes | No | SINGLE | SC001 | T3275/T3276 | L001 | DL001A |
| GMDB | PLAN_B | Yes | No | SINGLE | SC002 | T3275/T3276 | L003 | DL001B |
| GMAB | PLAN_A | Yes | Yes | SINGLE | SC001 | T3275/T3276 | L002 | DL002A |
| GMAB | PLAN_B | Yes | Yes | SINGLE | SC002 | T3275/T3276 | L004 | DL002B |

---

*Specification generated from lifelib IntegratedLife source code analysis.*
*Ready for handoff to gaspatchio-building skill.*
