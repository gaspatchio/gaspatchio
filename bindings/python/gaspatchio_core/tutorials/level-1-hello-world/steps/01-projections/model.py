# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 1 → Step 01: Projections

Delta from base:
  - INLINE DATA: Add entry_date column
  - SECTION 2: Parse entry date, create 12-month projection timeline
  - SECTION 3: Broadcast scalar columns into monthly list columns
  - All scalar arithmetic from base is retained

New concepts introduced here:

  - af.projection.set(): declares the projection time axis on the frame. Every
    subsequent column assignment that references list-valued projection
    accessors (e.g. af.projection.period_dates()) produces a list column — one
    element per projection period. Existing scalar columns remain scalar and
    broadcast automatically when combined with list columns in arithmetic.

  - List columns in practice: af.monthly_premium is a scalar (1 value per
    policy). After af.projection.set(), af.monthly_premium * 1.0 still gives a
    scalar; broadcasting to a list happens when it combines with a list-valued
    expression. This is automatic: you never write loops, and you never
    replicate data manually.

  - projection_date: assigning af.projection.period_dates() materialises the
    per-period date vector as a list column on the frame. Each element is a
    date — the first day of each projected month. Use af.projection_date.dt.year(),
    .dt.month(), etc. to extract components.

  - Month index: af.projection.set() does not produce a month counter
    automatically. Derive it from the projection date and valuation date:
      month = (year - val_year) * 12 + (month - val_month)

Sections:
  1. Inline Data & Constants
  2. Time Setup
  3. Monthly Projections

How to run:
  uv run python model.py
"""

import datetime

from gaspatchio_core import ActuarialFrame, when

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
    "expense_rate": [0.10, 0.10, 0.10],
    "entry_date": ["2024/01/15", "2023/06/01", "2022/03/10"],
}


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Run the 12-month term life projection.

    Args:
        af: ActuarialFrame with model points.

    Returns:
        ActuarialFrame with projection results.

    """
    # =====================================================================
    # SECTION 2: TIME SETUP
    # =====================================================================

    # Parse entry date from string to date type
    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    # af.projection.set() is the key transformation. It declares the
    # projection time axis on the frame; later assignments that reference
    # list-valued projection accessors become list columns automatically.
    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value=PROJECTION_MONTHS,
        frequency="monthly",
    )

    # Materialise the per-period date vector as a list column. Each element
    # is the first day of a projected month.
    af.projection_date = af.projection.period_dates()

    # Month index (0 = valuation date, 1 = one month later, ...)
    # af.projection.set() does not produce this automatically.
    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )

    # =====================================================================
    # SECTION 3: MONTHLY PROJECTIONS
    # =====================================================================

    # Monthly premium: scalar divided by 12 gives a scalar.
    # Once we use it in list arithmetic below, it broadcasts to a list.
    af.monthly_premium = af.annual_premium / 12.0

    # Monthly mortality: simple annual / 12 approximation
    # (Step 02 replaces this with the actuarially correct monthly rate)
    af.monthly_mortality = af.mortality_rate / 12.0

    # Expected monthly claims: scalar * scalar = scalar, broadcasting to
    # a list when combined with a list-valued projection accessor.
    # Each policy has the same expected claims in every month (no lapse yet).
    af.expected_claims_monthly = af.sum_assured * af.monthly_mortality

    # Monthly expense loading
    af.expenses_monthly = af.monthly_premium * af.expense_rate

    # Net monthly premium after expenses
    af.net_premium_monthly = af.monthly_premium - af.expenses_monthly

    # Profitability flag still works the same way — when/then/otherwise
    # operates element-wise whether columns are scalar or list
    af.is_profitable = (
        when(af.net_premium_monthly > af.expected_claims_monthly)
        .then("Yes")
        .otherwise("No")
    )

    return af


# =========================================================================
# STANDALONE EXECUTION
# =========================================================================

if __name__ == "__main__":
    af = ActuarialFrame(MODEL_POINTS)
    result_af = main(af)
    result = result_af.collect()

    # Show the month index and monthly cashflows for each policy
    print(
        result.select(
            ["policy_id", "month", "expected_claims_monthly", "net_premium_monthly"]
        )
    )

    # Each row is one policy; month, expected_claims_monthly, and
    # net_premium_monthly are list columns with 13 elements each
    # (months 0 through 12).
