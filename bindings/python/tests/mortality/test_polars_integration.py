# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end smoke — MortalityTable in a Universal-Life-style pipeline.

Mirrors the spec §4.5 worked example shape:
    coi = mortality.at(age=af.attained_age) * (death_benefit - av)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio_core import MortalityTable

if TYPE_CHECKING:
    from gaspatchio_core.assumptions import Table


class TestUlWithCoiPattern:
    """UL+COI flow: lookup mortality rate, multiply by net amount at risk."""

    def test_aggregate_lookup_in_with_columns_pipeline(
        self,
        aggregate_table: Table,
    ) -> None:
        """Aggregate mortality feeds the COI multiplier in a Polars pipeline."""
        mortality = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        frame = pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "attained_age": [40, 50, 60],
                "av": [10_000.0, 25_000.0, 50_000.0],
                "death_benefit": [100_000.0, 100_000.0, 100_000.0],
            },
        )
        result = frame.with_columns(
            qx=mortality.at(age=pl.col("attained_age")),
        ).with_columns(
            coi=pl.col("qx") * (pl.col("death_benefit") - pl.col("av")),
        )
        # qx: age 40 -> 0.002, age 50 -> 0.005, age 60 -> 0.013
        # coi: 0.002*90_000=180, 0.005*75_000=375, 0.013*50_000=650
        assert result.get_column("qx").to_list() == pytest.approx(
            [0.002, 0.005, 0.013],
        )
        assert result.get_column("coi").to_list() == pytest.approx(
            [180.0, 375.0, 650.0],
        )

    def test_select_ultimate_in_with_columns_pipeline(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """select_ultimate mortality clamps duration in a Polars pipeline."""
        mortality = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        frame = pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "age": [30, 40, 50],
                "policy_year": [1, 6, 100],
            },
        )
        result = frame.with_columns(
            qx=mortality.at(age=pl.col("age"), duration=pl.col("policy_year")),
        )
        # Age 30, policy_year 1: select rate = 0.001 * 30 * 1.1 = 0.033
        # Age 40, policy_year 6 → clamped to 4: 0.001 * 40 * (1 + 0.4) = 0.056
        # Age 50, policy_year 100 → clamped to 4: 0.001 * 50 * (1 + 0.4) = 0.070
        assert result.get_column("qx").to_list() == pytest.approx([0.033, 0.056, 0.070])
