# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: ALL
"""
Deliberately broken model for testing the model-review skill.

This model contains ALL 10 anti-patterns that model-review should catch.
Each is marked with a comment: # ANTI-PATTERN: <name>

Used by: tests/skills/test_review_fixtures.py
"""

import math
from pathlib import Path

import polars as pl
from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.assumptions import Table


def load_assumptions():
    """Load assumption tables."""
    # ANTI-PATTERN: hardcoded — magic number instead of Table lookup
    MORTALITY_RATE = 0.015

    return {"mortality_rate": MORTALITY_RATE}


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Main model with deliberate anti-patterns."""
    assumptions = load_assumptions()

    # ANTI-PATTERN: map_elements — should use vectorized operations
    af.age_category = af.age_at_entry.map_elements(
        lambda x: "young" if x < 40 else "old", return_dtype=pl.String
    )

    # ANTI-PATTERN: for-loop — should use column operations
    results = []
    for row in af.collect().iter_rows(named=True):
        results.append({"policy_id": row["policy_id"], "premium_doubled": row["annual_premium"] * 2})
    doubled_df = pl.DataFrame(results)

    # ANTI-PATTERN: scalar-list confusion — scalar where list is needed
    # This would crash on list columns: trying to use scalar math on a projection
    af.mortality_rate = assumptions["mortality_rate"]

    # ANTI-PATTERN: inline-polars — should use Table.lookup()
    mort_df = pl.DataFrame({"age": [30, 45, 60], "qx": [0.001, 0.004, 0.015]})
    lookup_result = mort_df.filter(pl.col("age") == 45)

    af.expected_claims = af.sum_assured * assumptions["mortality_rate"]
    af.expenses = af.annual_premium * 0.10

    # ANTI-PATTERN: wrong-accessor — using list.sum where projection method needed
    # (conceptual — in a real model this would be a survival calculation done wrong)

    af.net_premium = af.annual_premium - af.expenses
    af.profit = af.net_premium - af.expected_claims

    # ANTI-PATTERN: missing-when-then — boolean masking for complex conditional
    af.is_profitable = af.profit * (af.profit > 0) / (af.profit + 0.001)

    # No section comments anywhere — ANTI-PATTERN: no-section-comments

    return af


if __name__ == "__main__":
    data = {
        "policy_id": ["POL001", "POL002", "POL003"],
        "age_at_entry": [30, 45, 60],
        "sex": ["M", "F", "M"],
        "sum_assured": [500000, 250000, 100000],
        "annual_premium": [450, 1200, 2800],
    }
    af = ActuarialFrame(data)
    result = main(af)
    print(result.collect())
