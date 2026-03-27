"""
Level 1: Hello World — Term Life Portfolio

The simplest possible gaspatchio model. Three term life policies, no
time dimension, five lines of business logic.

Run this first. Once it works, move to Step 01 to add projections.

Key concepts introduced here:

  - ActuarialFrame: a specialised DataFrame where each row is one policy.
    You access columns as attributes (af.sum_assured) and assign new columns
    the same way (af.expected_claims = ...). Under the hood gaspatchio queues
    each operation lazily — nothing runs until you call .collect().

  - Column arithmetic: Python operators (+, -, *, /, **) work element-wise
    across all policies at once. No loops, no apply(), no iteration. Write the
    formula once and gaspatchio evaluates it for every row.

  - when().then().otherwise(): gaspatchio's conditional expression, equivalent
    to Excel's IF(condition, value_if_true, value_if_false). Works element-wise
    so you can express business rules that read like plain English:
      when(profit > 0).then("Yes").otherwise("No")

  - .collect(): ActuarialFrame is lazy — every assignment queues a computation
    but does not execute it. Call .collect() at the end to materialise the
    result as a standard Polars DataFrame. This laziness lets gaspatchio
    optimise the entire computation graph before running it.

  - Methods under .projection, .finance, .date, .excel are gaspatchio-specific.
    Everything else (.round(), .cast(), .list.sum()) is standard Polars.

Sections:
  1. Inline Data
  2. Claims & Premiums
  3. Profitability

How to run:
  uv run python model.py
"""

from gaspatchio_core import ActuarialFrame, when

# =========================================================================
# SECTION 1: INLINE DATA
# =========================================================================

# Three term life insurance policies — representative spread of ages/sums
MODEL_POINTS = {
    "policy_id": ["POL001", "POL002", "POL003"],
    "age": [30, 45, 60],
    "sex": ["M", "F", "M"],
    "sum_assured": [500_000, 250_000, 100_000],
    "annual_premium": [450, 1_200, 2_800],
    "mortality_rate": [0.001, 0.004, 0.015],  # annual qx
    "expense_rate": [0.10, 0.10, 0.10],  # % of premium
}


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Run the term life portfolio model.

    Args:
        af: ActuarialFrame with model points.

    Returns:
        ActuarialFrame with computed results.

    """
    # =====================================================================
    # SECTION 2: CLAIMS & PREMIUMS
    # =====================================================================

    # Expected claims: sum assured weighted by annual mortality rate
    af.expected_claims = af.sum_assured * af.mortality_rate

    # Expense loading: a percentage of annual premium
    af.expenses = af.annual_premium * af.expense_rate

    # Net premium: premium income after expenses
    af.net_premium = af.annual_premium - af.expenses

    # =====================================================================
    # SECTION 3: PROFITABILITY
    # =====================================================================

    # Profit: net premium minus expected claims
    af.profit = af.net_premium - af.expected_claims

    # Loss ratio: what fraction of premium is paid out in claims
    af.loss_ratio = (af.expected_claims / af.annual_premium).round(4)

    # Profitability flag: when/then/otherwise is gaspatchio's IF()
    # Works element-wise across all policies simultaneously
    af.is_profitable = when(af.profit > 0).then("Yes").otherwise("No")

    return af


# =========================================================================
# STANDALONE EXECUTION
# =========================================================================

if __name__ == "__main__":
    af = ActuarialFrame(MODEL_POINTS)
    result_af = main(af)
    result = result_af.collect()

    print(result.select(["policy_id", "expected_claims", "profit", "loss_ratio", "is_profitable"]))

    # Expected output:
    # ┌───────────┬─────────────────┬──────────┬────────────┬───────────────┐
    # │ policy_id ┆ expected_claims ┆ profit   ┆ loss_ratio ┆ is_profitable │
    # │ ---       ┆ ---             ┆ ---      ┆ ---        ┆ ---           │
    # │ str       ┆ f64             ┆ f64      ┆ f64        ┆ str           │
    # ╞═══════════╪═════════════════╪══════════╪════════════╪═══════════════╡
    # │ POL001    ┆ 500.0           ┆ -95.0    ┆ 1.1111     ┆ No            │
    # │ POL002    ┆ 1000.0          ┆ 80.0     ┆ 0.8333     ┆ Yes           │
    # │ POL003    ┆ 1500.0          ┆ 1020.0   ┆ 0.5357     ┆ Yes           │
    # └───────────┴─────────────────┴──────────┴────────────┴───────────────┘
