# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Select-ultimate dispatch with select_period clamping."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio_core.mortality._mortality_table import MortalityTable

if TYPE_CHECKING:
    from gaspatchio_core.assumptions import Table


class TestSelectUltimateAt:
    """select_ultimate: clamps duration at select_period and looks up the table."""

    def test_duration_within_select_period_uses_select_rate(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """For duration <= select_period the lookup uses the actual duration."""
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        frame = pl.DataFrame({"age": [30, 40], "duration": [1, 3]})
        result = frame.with_columns(
            qx=m.at(age=pl.col("age"), duration=pl.col("duration")),
        )
        # Fixture rates: 0.001 * age * (1 + 0.1 * duration)
        # Age 30, duration 1 -> 0.001 * 30 * 1.1 = 0.033
        # Age 40, duration 3 -> 0.001 * 40 * 1.3 = 0.052
        assert result.get_column("qx").to_list() == pytest.approx([0.033, 0.052])

    def test_duration_above_select_period_clamps_to_select_period(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """Durations beyond select_period clamp to select_period."""
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        frame = pl.DataFrame({"age": [30, 40], "duration": [10, 25]})
        result = frame.with_columns(
            qx=m.at(age=pl.col("age"), duration=pl.col("duration")),
        )
        # Both clamped to duration=4 (the select_period):
        # 0.001 * age * (1 + 0.1 * 4) = 0.0014 * age
        # Age 30 -> 0.001 * 30 * 1.4 = 0.042
        # Age 40 -> 0.001 * 40 * 1.4 = 0.056
        assert result.get_column("qx").to_list() == pytest.approx([0.042, 0.056])

    def test_select_ultimate_requires_age_and_duration(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """select_ultimate requires both age and duration."""
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        pattern = "select_ultimate.*requires.*age.*duration"
        with pytest.raises(ValueError, match=pattern):
            m.at(age=pl.col("age"))
        with pytest.raises(ValueError, match=pattern):
            m.at(duration=pl.col("duration"))
