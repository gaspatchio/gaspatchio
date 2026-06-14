# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for MortalityTable tests."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table


@pytest.fixture
def aggregate_table() -> Table:
    """Return a simple aggregate mortality table indexed by age."""
    frame = pl.DataFrame(
        {
            "age": [30, 35, 40, 45, 50, 55, 60, 65, 70],
            "qx": [0.001, 0.0015, 0.002, 0.003, 0.005, 0.008, 0.013, 0.020, 0.030],
        },
    )
    return Table(
        name="cso_2017_male_aggregate",
        source=frame,
        dimensions={"age": "age"},
        value="qx",
    )


@pytest.fixture
def select_ultimate_table() -> Table:
    """Return a select-ultimate mortality table indexed by age x duration.

    For a select_period of 5: durations 1..5 contain select rates;
    durations 6..N contain the ultimate rate (constant per age) so a
    'duration clamped at select_period' lookup yields the ultimate rate.
    """
    rows = [
        {
            "age": age,
            "duration": duration,
            "qx": 0.001 * age * (1 + 0.1 * duration),
        }
        for age in [30, 40, 50]
        for duration in range(1, 6)
    ]
    frame = pl.DataFrame(rows)
    return Table(
        name="select_ultimate_demo",
        source=frame,
        dimensions={"age": "age", "duration": "duration"},
        value="qx",
    )


@pytest.fixture
def joint_life_table() -> Table:
    """Return a simple joint-life mortality table indexed by both ages."""
    rows = [
        {"age_1": a1, "age_2": a2, "qx": 0.0001 * a1 * a2}
        for a1 in [60, 65, 70]
        for a2 in [60, 65, 70]
    ]
    frame = pl.DataFrame(rows)
    return Table(
        name="joint_life_demo",
        source=frame,
        dimensions={"age_1": "age_1", "age_2": "age_2"},
        value="qx",
    )
