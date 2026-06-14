# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""MortalityTable construction + validation tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING

import pytest

from gaspatchio_core.mortality._mortality_table import MortalityTable

if TYPE_CHECKING:
    from gaspatchio_core.assumptions import Table


class TestMortalityTableConstruction:
    """Frozen MortalityTable with structure/age_basis/select_period validation."""

    def test_aggregate_basic_construction(self, aggregate_table: Table) -> None:
        """Aggregate construction stores table reference + metadata.

        select_period defaults to None.
        """
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        assert m.table is aggregate_table
        assert m.age_basis == "age_last_birthday"
        assert m.structure == "aggregate"
        assert m.select_period is None

    def test_select_ultimate_requires_select_period(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """select_ultimate without select_period raises ValueError."""
        with pytest.raises(ValueError, match="select_period"):
            MortalityTable(
                table=select_ultimate_table,
                age_basis="age_last_birthday",
                structure="select_ultimate",
            )

    def test_select_ultimate_with_select_period_constructs(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """select_ultimate with positive select_period constructs."""
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=10,
        )
        assert m.structure == "select_ultimate"
        assert m.select_period == 10

    def test_aggregate_rejects_select_period(self, aggregate_table: Table) -> None:
        """select_period only valid for structure='select_ultimate'."""
        with pytest.raises(ValueError, match="select_period"):
            MortalityTable(
                table=aggregate_table,
                age_basis="age_last_birthday",
                structure="aggregate",
                select_period=10,
            )

    def test_joint_basic_construction(self, joint_life_table: Table) -> None:
        """Joint structure constructs without select_period."""
        m = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        assert m.structure == "joint"
        assert m.select_period is None

    def test_invalid_age_basis_raises(self, aggregate_table: Table) -> None:
        """Unknown age_basis raises ValueError."""
        with pytest.raises(ValueError, match="age_basis"):
            MortalityTable(
                table=aggregate_table,
                age_basis="age_curtate",  # type: ignore[arg-type]
                structure="aggregate",
            )

    def test_invalid_structure_raises(self, aggregate_table: Table) -> None:
        """Unknown structure raises ValueError."""
        with pytest.raises(ValueError, match="structure"):
            MortalityTable(
                table=aggregate_table,
                age_basis="age_last_birthday",
                structure="multi_decrement",  # type: ignore[arg-type]
            )

    def test_age_nearest_birthday_accepted(self, aggregate_table: Table) -> None:
        """age_nearest_birthday is a valid age_basis."""
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_nearest_birthday",
            structure="aggregate",
        )
        assert m.age_basis == "age_nearest_birthday"

    def test_is_frozen(self, aggregate_table: Table) -> None:
        """Dataclass is frozen -- assignment raises FrozenInstanceError."""
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        with pytest.raises(FrozenInstanceError):
            m.something = 42  # type: ignore[misc]


class TestPublicAPI:
    """MortalityTable reachable via top-level and subpackage imports."""

    def test_mortality_table_importable_from_subpackage(self) -> None:
        """Subpackage re-export is the same object as the private implementation."""
        from gaspatchio_core.mortality import MortalityTable
        from gaspatchio_core.mortality._mortality_table import MortalityTable as Private

        assert MortalityTable is Private

    def test_top_level_import(self) -> None:
        """gaspatchio_core has a MortalityTable attribute."""
        import gaspatchio_core

        assert hasattr(gaspatchio_core, "MortalityTable")

    def test_top_level___all___includes_mortality_table(self) -> None:
        """gaspatchio_core.__all__ includes 'MortalityTable'."""
        import gaspatchio_core

        assert "MortalityTable" in gaspatchio_core.__all__
