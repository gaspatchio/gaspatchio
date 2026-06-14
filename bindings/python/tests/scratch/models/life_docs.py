# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import datetime

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table

# Configure Polars for better terminal display
pl.Config.set_tbl_cols(-1)  # Show all columns
pl.Config.set_tbl_width_chars(300)  # Wider width to show full column names
pl.Config.set_fmt_str_lengths(15)  # Limit string length for readability
pl.Config.set_tbl_rows(-1)  # Show all rows

# Create sample policy data
model_data = {
    "policy_id": ["P001", "P002", "P003"],
    "age": [35, 42, 55],
    "gender": ["M", "F", "M"],
    "smoking_status": ["NS", "NS", "S"],
    "sum_assured": [100000, 250000, 500000],
    "issue_date": [
        datetime.date(2022, 1, 15),
        datetime.date(2021, 6, 1),
        datetime.date(2023, 3, 10),
    ],
    "valuation_date": [
        datetime.date(2024, 12, 31),
        datetime.date(2024, 12, 31),
        datetime.date(2024, 12, 31),
    ],
    "annual_premium": [1200, 2800, 8500],
    "interest_rate": [0.03, 0.035, 0.04],
    "policy_term_years": [20, 25, 15],
}
af = ActuarialFrame(model_data)

# Create mortality table
mortality_data = pl.DataFrame(
    {
        "age_last": [
            35,
            35,
            35,
            35,
            37,
            37,
            37,
            37,
            42,
            42,
            42,
            42,
            45,
            45,
            45,
            45,
            55,
            55,
            55,
            55,
            56,
            56,
            56,
            56,
        ],
        "sex_smoking": [
            "MNS",
            "FNS",
            "MS",
            "FS",  # Age 35
            "MNS",
            "FNS",
            "MS",
            "FS",  # Age 37
            "MNS",
            "FNS",
            "MS",
            "FS",  # Age 42
            "MNS",
            "FNS",
            "MS",
            "FS",  # Age 45
            "MNS",
            "FNS",
            "MS",
            "FS",  # Age 55
            "MNS",
            "FNS",
            "MS",
            "FS",  # Age 56
        ],
        "mortality_rate": [
            0.001,
            0.0008,
            0.002,
            0.0015,  # Age 35
            0.0012,
            0.001,
            0.0025,
            0.0018,  # Age 37
            0.002,
            0.0015,
            0.004,
            0.003,  # Age 42
            0.0025,
            0.002,
            0.005,
            0.0035,  # Age 45
            0.008,
            0.006,
            0.015,
            0.012,  # Age 55
            0.009,
            0.007,
            0.018,
            0.014,  # Age 56
        ],
    }
)

mortality_table = Table(
    name="mortality_demo",
    source=mortality_data,
    dimensions={"age_last": "age_last", "sex_smoking": "sex_smoking"},
    value="mortality_rate",
)

# Create lapse table
lapse_data = pl.DataFrame(
    {
        "policy_duration": [1, 2, 3, 4, 5],
        "lapse_rate": [0.05, 0.08, 0.12, 0.15, 0.18],
    }
)

lapse_table = Table(
    name="lapse_demo",
    source=lapse_data,
    dimensions={"policy_duration": "policy_duration"},
    value="lapse_rate",
)


# 1. DATE CALCULATIONS (Excel Functions)
af.days_in_force = af.valuation_date.excel.days(af.issue_date)
af.years_in_force = af.issue_date.excel.yearfrac(
    af.valuation_date, basis="act/act"
).round(2)
af.age_at_valuation = (af.age + af.years_in_force).round(2)

# 2. ASSUMPTION TABLE LOOKUPS
af.sex_smoking = af.gender + af.smoking_status
af.age_last = af.age_at_valuation.floor()
af.policy_duration_int = af.years_in_force.floor()

af.mortality_rate = mortality_table.lookup(
    age_last=af.age_last, sex_smoking=af.sex_smoking
).round(2)
af.lapse_rate = lapse_table.lookup(policy_duration=af.policy_duration_int).round(2)

# 3. PRESENT VALUE CALCULATIONS (Excel PV Function)
af.remaining_term = (af.policy_term_years - af.years_in_force).round(2)
af.pv_future_premiums = af.interest_rate.excel.pv(
    nper=af.remaining_term, pmt=af.annual_premium
).round(2)
af.pv_sum_assured = (
    af.sum_assured / (1 + af.interest_rate) ** af.remaining_term
).round(2)
af.npv = (af.pv_sum_assured + af.pv_future_premiums).round(2)

# 4. CASH FLOW PROJECTIONS (Vector Operations)
af.expected_claims = (af.mortality_rate * af.sum_assured).round(2)
af.expected_premiums = (af.annual_premium * (1 - af.lapse_rate)).round(2)
af.net_cash_flows = (af.expected_premiums - af.expected_claims).round(2)

# =============================================================================
# EXECUTE ONCE AND DISPLAY RESULTS
# =============================================================================

print("\n=== FINAL RESULTS ===")
# Execute all calculations in one go (single query plan)
df = af.collect()
print(df)

# =============================================================================
# SUMMARY METRICS
# =============================================================================

print("\n=== SUMMARY METRICS ===")
summary_data = {
    "total_sum_assured": df["sum_assured"].sum(),
    "total_annual_premium": df["annual_premium"].sum(),
    "average_age": round(df["age_at_valuation"].mean(), 2),
    "average_mortality_rate": df["mortality_rate"].mean(),
    "average_lapse_rate": df["lapse_rate"].mean(),
    "total_npv": df["npv"].sum(),
}

summary_af = ActuarialFrame(summary_data)
print(summary_af.collect())
