# ABOUTME: Test file that validates the Complete Life Insurance Model example from assumptions.md
# ABOUTME: Ensures the documented code patterns compile and produce valid results

"""
This file contains the EXACT code from docs/concepts/assumptions.md
to ensure our documentation examples actually work.

Run with: python -m tests.scratch.models.complete_life_model_docs
"""

import datetime

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import MeltDimension, Table

# Configure Polars for better display
pl.Config.set_tbl_cols(-1)
pl.Config.set_tbl_width_chars(200)
pl.Config.set_tbl_rows(20)


def setup_assumptions():
    """Load all assumption tables for the model"""

    # Create sample mortality data (wide format with MNS, FNS, MS, FS columns)
    mortality_df = pl.DataFrame({
        "age_last": list(range(30, 70)),
        "MNS": [0.001 * (1.05 ** (age - 30)) for age in range(30, 70)],  # Male Non-Smoker
        "FNS": [0.0008 * (1.05 ** (age - 30)) for age in range(30, 70)],  # Female Non-Smoker
        "MS": [0.002 * (1.05 ** (age - 30)) for age in range(30, 70)],   # Male Smoker
        "FS": [0.0015 * (1.05 ** (age - 30)) for age in range(30, 70)],  # Female Smoker
    })

    mortality_table = Table(
        name="mortality_rates",
        source=mortality_df,
        dimensions={
            "age_last": "age_last",
            "variable": MeltDimension(
                columns=["MNS", "FNS", "MS", "FS"],
                name="variable"
            )
        },
        value="mortality_rate"
    )

    # Create sample lapse data (simple 1D table)
    lapse_df = pl.DataFrame({
        "policy_duration": list(range(0, 50)),
        "lapse_rate": [0.15 if d == 0 else 0.10 if d < 3 else 0.05 if d < 10 else 0.02 for d in range(50)]
    })

    lapse_table = Table(
        name="lapse_rates",
        source=lapse_df,
        dimensions={
            "policy_duration": "policy_duration"
        },
        value="lapse_rate"
    )

    # Create sample premium data (wide format)
    premium_df = pl.DataFrame({
        "age_last": list(range(30, 70)),
        "MNS": [12.0 * (1.03 ** (age - 30)) for age in range(30, 70)],
        "FNS": [10.0 * (1.03 ** (age - 30)) for age in range(30, 70)],
        "MS": [18.0 * (1.03 ** (age - 30)) for age in range(30, 70)],
        "FS": [14.0 * (1.03 ** (age - 30)) for age in range(30, 70)],
    })

    premium_table = Table(
        name="premium_rates",
        source=premium_df,
        dimensions={
            "age_last": "age_last",
            "variable": MeltDimension(
                columns=["MNS", "FNS", "MS", "FS"],
                name="variable"
            )
        },
        value="premium_rate"
    )

    return mortality_table, lapse_table, premium_table


def life_model(policies_df):
    """Complete life insurance projection model"""

    # Setup assumption tables
    mortality_table, lapse_table, premium_table = setup_assumptions()

    # Create ActuarialFrame
    af = ActuarialFrame(policies_df)

    # Create projection timeline using fill_series
    # Calculate number of projection months based on policy term
    max_age = 70  # Project until age 70
    af.num_proj_months = (max_age - af.issue_age) * 12
    af.month = af.fill_series(af.num_proj_months, start=0, increment=1)

    # Calculate indexing columns as projection vectors
    af.attained_age = af.issue_age + af.month // 12
    af.duration = af.month // 12

    # Create gender/smoking variable for lookups
    af.variable = af.gender + af.smoking_status

    # Vector lookups - get rates for all timesteps at once
    af.mort_rate = mortality_table.lookup(age_last=af.attained_age, variable=af.variable)
    af.lapse_rate = lapse_table.lookup(policy_duration=af.duration)
    af.premium_rate = premium_table.lookup(age_last=af.attained_age, variable=af.variable)

    # Calculate monthly persistence probability
    af.monthly_persist = (1 - af.mort_rate / 12) * (1 - af.lapse_rate / 12)

    # Probability in force using projection accessor
    af.pols_if = af.monthly_persist.projection.cumulative_survival()

    # Cash flows
    af.premium_cf = af.premium_rate / 12 * af.pols_if * af.sum_assured / 1000
    af.claims_cf = af.pols_if * af.mort_rate / 12 * af.sum_assured
    af.profit_cf = af.premium_cf - af.claims_cf

    return af


def create_sample_policies():
    """Create sample policy data for testing"""
    return pl.DataFrame({
        "policy_id": ["P001", "P002", "P003", "P004"],
        "issue_age": [35, 42, 50, 38],
        "gender": ["M", "F", "M", "F"],
        "smoking_status": ["NS", "NS", "S", "NS"],
        "sum_assured": [100_000, 250_000, 500_000, 150_000],
        "issue_date": [
            datetime.date(2020, 1, 1),
            datetime.date(2019, 6, 15),
            datetime.date(2021, 3, 1),
            datetime.date(2022, 9, 1),
        ],
        "maturity_date": [
            datetime.date(2045, 1, 1),   # 25 years
            datetime.date(2044, 6, 15),  # 25 years
            datetime.date(2041, 3, 1),   # 20 years
            datetime.date(2052, 9, 1),   # 30 years
        ],
    })


if __name__ == "__main__":
    print("=" * 80)
    print("COMPLETE LIFE INSURANCE MODEL - Documentation Example Validation")
    print("=" * 80)

    # Create sample policies
    policies = create_sample_policies()
    print("\n--- Input Policies ---")
    print(policies)

    # Run the model
    print("\n--- Running Model ---")
    results = life_model(policies)

    # Collect and display results
    df = results.collect()

    print("\n--- Model Output (selected columns) ---")
    output_cols = [
        "policy_id",
        "issue_age",
        "gender",
        "smoking_status",
        "sum_assured",
        "month",
        "attained_age",
        "duration",
        "mort_rate",
        "lapse_rate",
        "pols_if",
        "premium_cf",
        "claims_cf",
        "profit_cf",
    ]
    # Only show columns that exist
    available_cols = [c for c in output_cols if c in df.columns]
    print(df.select(available_cols))

    # Validate results
    print("\n--- Validation ---")
    assert "pols_if" in df.columns, "pols_if column should exist"
    assert "mort_rate" in df.columns, "mort_rate column should exist"
    assert "profit_cf" in df.columns, "profit_cf column should exist"

    # Check that projection vectors have the expected structure
    first_row = df.row(0, named=True)
    assert isinstance(first_row["month"], list), "month should be a list (projection vector)"
    assert isinstance(first_row["pols_if"], list), "pols_if should be a list (projection vector)"

    # Check that pols_if starts at 1.0 and decreases
    pols_if = first_row["pols_if"]
    assert abs(pols_if[0] - 1.0) < 0.01, f"pols_if should start at ~1.0, got {pols_if[0]}"
    assert pols_if[-1] < pols_if[0], "pols_if should decrease over time"

    print("✓ All validations passed!")
    print("\n--- Summary ---")
    print(f"Policies processed: {len(df)}")
    print(f"Projection months per policy: {len(first_row['month'])}")
    print(f"Final pols_if for P001: {pols_if[-1]:.4f}")
