# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Aggregate-structure .at() lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio_core.mortality._mortality_table import MortalityTable

if TYPE_CHECKING:
    from gaspatchio_core.assumptions import Table


class TestAggregateAt:
    """Aggregate structure: .at(age=...) returns Table.lookup result."""

    def test_lookup_by_age_returns_expr(self, aggregate_table: Table) -> None:
        """.at returns a Polars expression."""
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        result = m.at(age=pl.col("attained_age"))
        assert isinstance(result, pl.Expr)

    def test_lookup_in_with_columns_returns_correct_rates(
        self,
        aggregate_table: Table,
    ) -> None:
        """.at composes inside with_columns and produces the correct qx values."""
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        frame = pl.DataFrame({"attained_age": [30, 40, 50, 60, 70]})
        result = frame.with_columns(qx=m.at(age=pl.col("attained_age")))
        assert result.get_column("qx").to_list() == pytest.approx(
            [0.001, 0.002, 0.005, 0.013, 0.030],
        )

    def test_aggregate_rejects_duration_kwarg(self, aggregate_table: Table) -> None:
        """Aggregate structure refuses duration=...; clearer error than Table."""
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        with pytest.raises(ValueError, match="aggregate.*duration"):
            m.at(age=pl.col("attained_age"), duration=pl.col("policy_year"))

    def test_age_basis_kwarg_documented_only(self, aggregate_table: Table) -> None:
        """Matching age_basis is accepted as a no-op."""
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        frame = pl.DataFrame({"attained_age": [40]})
        result = frame.with_columns(
            qx=m.at(age=pl.col("attained_age"), age_basis="age_last_birthday"),
        )
        assert result.get_column("qx").to_list() == pytest.approx([0.002])

    def test_age_basis_kwarg_mismatch_raises(self, aggregate_table: Table) -> None:
        """Mismatched age_basis raises — cross-basis conversion not supported."""
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        with pytest.raises(ValueError, match="cross-basis conversion"):
            m.at(age=pl.col("attained_age"), age_basis="age_nearest_birthday")
