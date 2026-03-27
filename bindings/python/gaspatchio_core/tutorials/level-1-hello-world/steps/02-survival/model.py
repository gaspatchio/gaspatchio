"""
Level 1 → Step 02: Cumulative Survival

Delta from Step 01:
  - INLINE DATA: Add lapse_rate column
  - SECTION 3: Monthly decrement rates (actuarially correct conversion)
  - SECTION 4: Combined decrement and cumulative survival (NEW)
  - SECTION 5: Claims and premiums weighted by policies in force

New concepts introduced here:

  - Actuarially correct monthly rates: The annual-to-monthly conversion is
    NOT simply rate / 12. The correct formula is:
      q_monthly = 1 - (1 - q_annual)^(1/12)
    This ensures that applying the monthly rate 12 times gives exactly the
    same annual decrement as the annual rate. For small rates the difference
    is minor, but it compounds significantly over a long projection.

  - Combined decrement: When a policy can exit via death OR lapse, the
    combined monthly decrement is:
      combined = 1 - (1 - mort_mth) * (1 - lapse_mth)
    NOT simply mort_mth + lapse_mth (which double-counts simultaneous exits).

  - Broadcasting scalars to list columns: After create_projection_timeline(),
    scalar columns stay scalar until combined with a list column. To convert
    a per-policy scalar to a per-period list, add it to a zero-valued list:
      af.combined_decrement_list = af.combined_decrement + af.month * 0.0
    This pattern — "broadcast via month" — gives a constant-valued list where
    every element equals the original scalar. Use it whenever you need to pass
    a scalar into a method that expects a list column (like cumulative_survival).

  - .projection.cumulative_survival(): takes a per-period decrement rate list
    and returns the fraction of policies still in force at EACH period. It
    starts at 1.0 (everyone in force at t=0) and multiplies by (1 - rate)
    cumulatively:
      t=0: 1.000                 (start of period — no decrements yet)
      t=1: (1 - d)               (first decrement applied)
      t=2: (1 - d)^2             (second decrement applied)
      ...
    This is the vectorised equivalent of lifelib's pols_if(t) or an Excel
    column of =IF(t=0, 1, prev_cell * (1 - decrement)).

  - Once you have pols_if, multiply any per-policy quantity by pols_if to
    weight it by the fraction of policies still active in that period.

Sections:
  1. Inline Data & Constants
  2. Time Setup
  3. Monthly Rates (actuarially correct)
  4. Cumulative Survival
  5. Weighted Claims & Premiums

How to run:
  uv run python model.py
"""

import datetime

from gaspatchio_core import ActuarialFrame

# =========================================================================
# SECTION 1: INLINE DATA & CONSTANTS
# =========================================================================

VALUATION_DATE = datetime.date(2025, 1, 1)
PROJECTION_MONTHS = 12

MODEL_POINTS = {
    "policy_id": ["POL001", "POL002", "POL003"],
    "age": [30, 45, 60],
    "sex": ["M", "F", "M"],
    "sum_assured": [500_000, 250_000, 100_000],
    "annual_premium": [450, 1_200, 2_800],
    "mortality_rate": [0.001, 0.004, 0.015],  # annual qx
    "lapse_rate": [0.05, 0.08, 0.03],  # annual lapse rate
    "expense_rate": [0.10, 0.10, 0.10],
    "entry_date": ["2024/01/15", "2023/06/01", "2022/03/10"],
}


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Run the 12-month term life projection with survival.

    Args:
        af: ActuarialFrame with model points.

    Returns:
        ActuarialFrame with projection results.

    """
    # =====================================================================
    # SECTION 2: TIME SETUP
    # =====================================================================

    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    af = af.date.create_projection_timeline(
        valuation_date=VALUATION_DATE,
        projection_end_type="term_months",
        projection_end_value=PROJECTION_MONTHS,
        projection_frequency="monthly",
        output_column="projection_date",
    )

    af.month = (
        af.projection_date.dt.year() - VALUATION_DATE.year
    ) * 12 + (af.projection_date.dt.month() - VALUATION_DATE.month)

    # =====================================================================
    # SECTION 3: MONTHLY RATES (ACTUARIALLY CORRECT)
    # =====================================================================

    # Convert annual to monthly using the exact actuarial formula.
    # These are still scalar columns (one value per policy, not per period)
    # because they derive only from the scalar model point data.
    af.mort_rate_mth = 1 - (1 - af.mortality_rate) ** (1 / 12)
    af.lapse_rate_mth = 1 - (1 - af.lapse_rate) ** (1 / 12)

    # =====================================================================
    # SECTION 4: CUMULATIVE SURVIVAL
    # =====================================================================

    # Combined monthly decrement: probability of leaving the portfolio
    # (by death OR lapse) in any given month. Still scalar at this point.
    af.combined_decrement = 1 - (1 - af.mort_rate_mth) * (1 - af.lapse_rate_mth)

    # .projection.cumulative_survival() requires a list column (one rate per
    # period). Our combined_decrement is a scalar (one rate per policy).
    # Broadcast it to a list by adding af.month * 0.0 — this creates a
    # constant-valued list where every element equals the scalar rate.
    # Real models avoid this by using Table.lookup(), which naturally
    # produces list columns (see Level 2). Here we need the explicit broadcast.
    af.decrement_list = af.combined_decrement + af.month * 0.0

    # Policies in force: cumulative survival from the per-period decrement.
    # Starts at 1.0 at t=0, decreases each period as policies exit.
    af.pols_if = af.decrement_list.projection.cumulative_survival()

    # =====================================================================
    # SECTION 5: WEIGHTED CLAIMS & PREMIUMS
    # =====================================================================

    # Monthly premium income: weighted by fraction of policies still active
    af.monthly_premium = af.annual_premium / 12.0
    af.premium_income = af.monthly_premium * af.pols_if

    # Expected monthly claims: only surviving policies generate claims
    af.expected_claims = af.sum_assured * af.mort_rate_mth * af.pols_if

    # Monthly expenses
    af.expenses = af.monthly_premium * af.expense_rate * af.pols_if

    # Total over projection (undiscounted) — list.sum() aggregates the list
    af.total_premium = af.premium_income.list.sum()
    af.total_claims = af.expected_claims.list.sum()

    return af


# =========================================================================
# STANDALONE EXECUTION
# =========================================================================

if __name__ == "__main__":
    af = ActuarialFrame(MODEL_POINTS)
    result_af = main(af)
    result = result_af.collect()

    # Show summary columns (scalars) alongside the pols_if list
    print(result.select(["policy_id", "pols_if", "total_premium", "total_claims"]))

    # pols_if is a list: each element is the fraction of policies in force
    # at that month (1.0 at t=0, decreasing over time).
    # total_premium and total_claims are scalars: the sum over all 12 months.
