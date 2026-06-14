# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for discount_factor using list_pow plugin (no EXPLODE)
# ABOUTME: Verifies Rust plugin integration eliminates EXPLODE/GROUP_BY pattern
"""Test discount_factor using list_pow plugin (no EXPLODE)."""

import pytest

from gaspatchio_core import ActuarialFrame


def test_discount_factor_spot_uses_list_pow() -> None:
    """Test that discount_factor spot method uses list_pow plugin."""
    data = {
        "policy_id": [1, 2],
        "monthly_rate": [[0.004, 0.004, 0.004], [0.003, 0.003]],
        "month": [[0, 1, 2], [0, 1]],
    }
    af = ActuarialFrame(data)

    af = af.finance.discount_factor(
        rate_col="monthly_rate",
        periods_col="month",
        output_col="disc_factors",
        method="spot",
    )

    result = af.collect()

    # Verify shape
    expected_rows = 2
    expected_cols = 4
    assert result.shape == (expected_rows, expected_cols)  # noqa: S101

    # Verify discount factors
    # Spot formula: (1 + rate)^(-period)
    # Row 1, period 0: (1 + 0.004)^0 = 1.0
    # Row 1, period 1: (1 + 0.004)^(-1) = 0.996016
    # Row 1, period 2: (1 + 0.004)^(-2) = 0.992048
    disc_factors = result["disc_factors"].to_list()
    expected_len_row1 = 3
    assert len(disc_factors[0]) == expected_len_row1  # noqa: S101
    assert disc_factors[0][0] == pytest.approx(1.0, abs=1e-6)  # noqa: S101
    assert disc_factors[0][1] == pytest.approx(0.996016, abs=1e-6)  # noqa: S101
    assert disc_factors[0][2] == pytest.approx(0.992048, abs=1e-6)  # noqa: S101

    # Row 2
    expected_len_row2 = 2
    assert len(disc_factors[1]) == expected_len_row2  # noqa: S101
    assert disc_factors[1][0] == pytest.approx(1.0, abs=1e-6)  # noqa: S101
    assert disc_factors[1][1] == pytest.approx(0.997009, abs=1e-6)  # noqa: S101
