# ASOP 56-Informed Review Checklist

## What is ASOP 56?

Actuarial Standard of Practice No. 56 — **Modeling** — was adopted by the Actuarial Standards Board in December 2019, effective October 1, 2020. It applies to all US actuaries who design, develop, select, modify, use, or review models.

ASOP 56 does not prescribe specific modeling techniques. Instead, it establishes professional standards for the modeling process: documentation, validation, governance, and communication of results. The checklist below translates ASOP 56 principles into concrete review checks for gaspatchio models.

**Key principle**: Documentation must be sufficient for "another actuary qualified in the same practice area" to assess the reasonableness of the work.

---

## Correctness Checks (Critical)

These are the highest-priority items. Errors here produce wrong numbers.

| # | Check | What to verify | Common failure modes |
|---|---|---|---|
| 1 | **Formula correctness** | Trace each formula back to its specification or source. Check operator precedence, parenthesization, and sign conventions. | Swapped subtraction order, missing parentheses around compound expressions, `1 - q` vs `1 / (1 + q)` |
| 2 | **Lookup table alignment** | Each `Table.lookup()` maps the correct model dimension to the correct table dimension. Spot-check values at known ages/durations. | Attained age vs issue age, annual vs monthly rates, 0-indexed vs 1-indexed duration |
| 3 | **Calculation order** | Variables are computed in dependency order. No variable reads a value that hasn't been set yet. Decrements apply before dependent cashflows. | Claims calculated before account value update, survival applied after cashflows instead of before |
| 4 | **Multiplicative vs additive** | Survival is multiplicative (cumulative product). Reserve changes are additive. Expense loading is additive to net premium. Discounting is multiplicative. | Using `cum_sum` for survival, using `cum_prod` for reserve changes |
| 5 | **Decrement timing consistency** | All decrements in the model use the same timing convention: beginning of period (BOP), mid-period, or end of period (EOP). Mixed timing causes 1-5% reconciliation gaps. | Mortality at BOP, lapses at EOP, claims referencing wrong AV timing |
| 6 | **Inter-decrement ordering** | When multiple decrements apply in the same period, later decrements must be applied to the population surviving prior decrements. Lapses should come from `pols_if_bef_decr - pols_death`, not from the full starting population. Applying all decrements to the starting population overstates total exits by approximately `mort_rate * lapse_rate` per period. | `pols_lapse = pols_if * lapse_rate` instead of `pols_lapse = (pols_if_bef_decr - pols_death) * lapse_rate` |

---

## Assumption Integrity Checks (Important)

These ensure the model's inputs are correct and internally consistent.

| # | Check | What to verify | Common failure modes |
|---|---|---|---|
| 1 | **Internal consistency** | Changed assumptions are consistent with unchanged ones. Economic assumptions are internally coherent (discount rate vs inflation vs investment return). | Updating mortality without updating morbidity, changing discount rate without updating reinvestment assumption |
| 2 | **Source documentation** | Every assumption table traces to a named source: experience study, regulatory table, pricing basis, or expert judgment with rationale. | "The mortality table" with no version, date, or source reference |
| 3 | **Reasonableness** | Spot-check assumption values against expected ranges. Mortality rates should be in a plausible range for the age band. Lapse rates should decline with duration for most products. | Mortality rates that are clearly annual used as monthly, lapse rates that increase with duration for a product with surrender charges |
| 4 | **Dimension mapping** | Table dimensions match model point fields exactly. Column names, types, and value ranges align. | Table keyed by `sex` with values "M"/"F" but model points use "Male"/"Female", or integer age vs float age |

---

## Change Impact Checks (Important)

These apply when reviewing changes to an existing model, not initial builds.

| # | Check | What to verify | Common failure modes |
|---|---|---|---|
| 1 | **Propagation completeness** | The change has been propagated to all dependent variables. If a rate changed, every downstream calculation that uses it has been re-validated. | Changing mortality rate formula but not re-checking death claims, reserves, and PVs |
| 2 | **Side effect analysis** | Run the model before and after the change. Compare key outputs. Check that unchanged variables are actually unchanged. | A "small" lapse rate change that moves BEL by 15% because of interaction with dynamic policyholder behavior |
| 3 | **Direction and magnitude** | The direction and magnitude of output changes should make actuarial sense. Increasing mortality should increase death claims and decrease survival-contingent benefits. | Increasing mortality causes reserves to decrease (possible sign of a timing or ordering bug) |
| 4 | **Boundary preservation** | Edge cases still behave correctly after the change. Check duration 0, maturity month, zero account value, maximum age, and policy start/end around valuation date. | Change works for mid-duration policies but crashes or gives wrong results for new business or at maturity |

---

## Documentation Checks (Minor)

These ensure the model is auditable and maintainable.

| # | Check | What to verify | Common failure modes |
|---|---|---|---|
| 1 | **Change rationale** | Commit messages, code comments, or build log explain WHY the change was made, not just WHAT changed. The business or actuarial reason should be clear. | "Updated mortality rates" with no explanation of why (new experience study? regulatory change? error correction?) |
| 2 | **Material limitations** | Simplifying assumptions are documented: no dynamic policyholder behavior, flat yield curve, deterministic scenarios only, single decrement vs multiple decrement, etc. | Model assumes level premium but documentation doesn't mention this; reviewer assumes flexible premium and draws wrong conclusions |
| 3 | **Methodology currency** | If the model has an accompanying methodology document, it reflects the current code. Version numbers or dates are consistent between code and documentation. | Methodology document describes an older version of the model; new features are undocumented |

---

## Applying the Checklist

### Order of operations

Work through the checklist in order: Correctness first, then Assumption Integrity, then Change Impact, then Documentation. Critical issues found early may invalidate later checks (a wrong formula makes assumption integrity checks meaningless until fixed).

### Evidence standard

Every check that passes should be verifiable. "I looked at it and it seems fine" is not evidence. Acceptable evidence includes:

- A single-policy model run showing expected intermediate values
- A before/after diff of key outputs when reviewing a change
- A spot-check comparing assumption table values to a named source document
- A screenshot or code snippet showing the formula matches the specification

### Materiality

Not every check applies to every model. A simple term life model may not have account values or dynamic policyholder behavior. Skip checks that are clearly inapplicable, but document why they were skipped. The goal is conscious exclusion, not accidental omission.

### Relationship to other skills

- **Model building** (`gaspatchio-model-building`): The post-build checklist in that skill covers construction quality. This checklist covers review quality. They overlap on anti-patterns but diverge on methodology and change impact.
- **Model reconciliation** (`gaspatchio-model-reconciliation`): Reconciliation proves numeric accuracy against a source. This checklist covers broader quality concerns that reconciliation alone does not address (documentation, assumption governance, change impact analysis).

---

## Review Summary

When applying this checklist, classify each finding by severity:

- **Critical** (Correctness): Will produce wrong numbers. Must fix before proceeding.
- **Important** (Assumption Integrity, Change Impact): Methodology risk or governance gap. Must fix before production.
- **Minor** (Documentation): Audit or maintainability concern. Fix when convenient.

The review is complete when all Critical and Important findings have been resolved. Minor findings should be logged for future attention.
