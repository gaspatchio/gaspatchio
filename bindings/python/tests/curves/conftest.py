# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for Curve tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def eiopa_eur_2026q2_tenors() -> list[float]:
    """Return representative EIOPA-style EUR tenor grid (years)."""
    return [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0]


@pytest.fixture
def eiopa_eur_2026q2_zero_rates() -> list[float]:
    """Return representative EUR zero-rate curve.

    Illustrative values only — not official EIOPA data.
    """
    return [0.025, 0.028, 0.030, 0.031, 0.032, 0.033, 0.035, 0.036, 0.037, 0.038]


@pytest.fixture
def flat_3pct_tenors() -> list[float]:
    """Return knot grid for a flat 3% curve."""
    return [1.0, 5.0, 10.0, 30.0]


@pytest.fixture
def flat_3pct_rates() -> list[float]:
    """Return rate values for a flat 3% curve."""
    return [0.03, 0.03, 0.03, 0.03]
