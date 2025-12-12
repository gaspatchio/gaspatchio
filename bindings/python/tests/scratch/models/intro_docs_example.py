# ABOUTME: Test file that validates the intro.md vectorized Excel functions example
# ABOUTME: Ensures the documented code patterns compile and produce valid results

"""
This file contains the EXACT code from docs/concepts/intro.md
to ensure our documentation examples actually work.

Run with: python -m tests.scratch.models.intro_docs_example
"""

import polars as pl
from gaspatchio_core import ActuarialFrame

# Configure Polars for better display
pl.Config.set_tbl_cols(-1)
pl.Config.set_tbl_width_chars(200)
pl.Config.set_tbl_rows(20)


def intro_example():
    """Actuarial example: Calculate present value and IRR for policy cash flows."""

    # Portfolio of 3 policies with monthly cash flows over 5 years (60 months)
    # Premiums are received monthly, claims are sporadic
    policies = ActuarialFrame(
        {
            "policy_id": ["POL001", "POL002", "POL003"],
            "annual_rate": [0.05, 0.04, 0.06],
            "monthly_premiums": [
                [100.0] * 60,  # POL001: constant $100/month
                [150.0] * 60,  # POL002: constant $150/month
                [200.0] * 60,  # POL003: constant $200/month
            ],
            "monthly_claims": [
                [0.0] * 30 + [2000.0] + [0.0] * 29,  # POL001: one claim at month 30
                [0.0] * 20
                + [1500.0]
                + [0.0] * 19
                + [3000.0]
                + [0.0] * 19,  # POL002: two claims
                [0.0] * 60,  # POL003: no claims
            ],
        }
    )

    # Calculate net monthly cash flows (premiums - claims)
    policies.net_cashflows = policies.monthly_premiums - policies.monthly_claims

    # Calculate monthly interest rate
    policies.monthly_rate = policies.annual_rate / 12

    # Calculate present value of the cash flow streams using Excel PV function
    policies.pv_cashflows = policies.monthly_rate.excel.pv(
        nper=60,
        pmt=policies.net_cashflows,
    )

    # Calculate IRR on the net cash flows (internal rate of return)
    policies.irr_monthly = policies.net_cashflows.excel.irr()
    policies.irr_annual = (1 + policies.irr_monthly) ** 12 - 1

    # Round for reporting
    policies.pv_cashflows = policies.pv_cashflows.round(2)
    policies.irr_annual = policies.irr_annual.round(4)

    return policies


if __name__ == "__main__":
    print("=" * 80)
    print("INTRO.MD DOCUMENTATION EXAMPLE - Validation")
    print("=" * 80)

    # Run the example
    print("\n--- Running Example ---")
    result = intro_example()

    # Collect and display results
    df = result.collect()
    print("\n--- Results ---")
    print(df)

    # Validate results
    print("\n--- Validation ---")
    assert "pv_cashflows" in df.columns, "pv_cashflows column should exist"
    assert "irr_annual" in df.columns, "irr_annual column should exist"
    assert "net_cashflows" in df.columns, "net_cashflows column should exist"

    # Check net_cashflows is a list column
    first_row = df.row(0, named=True)
    assert isinstance(first_row["net_cashflows"], list), "net_cashflows should be a list"
    assert len(first_row["net_cashflows"]) == 60, "net_cashflows should have 60 elements"

    # Check pv_cashflows is a list column (Excel PV returns negative for positive cashflows)
    assert isinstance(first_row["pv_cashflows"], list), "pv_cashflows should be a list"

    print("✓ All validations passed!")
    print("\n--- Summary ---")
    print(f"Policies processed: {len(df)}")
