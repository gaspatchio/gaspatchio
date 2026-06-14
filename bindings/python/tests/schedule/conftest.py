# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for schedule tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest


@pytest.fixture
def sample_policies() -> pl.DataFrame:
    """Three policies with varying inception dates spanning a leap year."""
    return pl.DataFrame(
        {
            "policy_id": [1, 2, 3],
            "contract_inception": [
                date(2024, 2, 29),  # leap-day inception
                date(2024, 3, 15),  # mid-month inception
                date(2025, 6, 1),  # month-start inception in non-leap year
            ],
        }
    )
