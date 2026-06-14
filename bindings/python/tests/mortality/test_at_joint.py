# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Joint-life .at() lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio_core.mortality._mortality_table import MortalityTable

if TYPE_CHECKING:
    from gaspatchio_core.assumptions import Table


class TestJointAt:
    """Joint-life: .at(age_1=..., age_2=...) returns the looked-up qx."""

    def test_lookup_by_age_1_age_2_returns_expr(self, joint_life_table: Table) -> None:
        """.at returns a Polars expression and produces correct rates."""
        m = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        frame = pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "age_1": [60, 65, 70],
                "age_2": [60, 70, 65],
            },
        )
        result = frame.with_columns(
            qx=m.at(age_1=pl.col("age_1"), age_2=pl.col("age_2")),
        )
        assert result.get_column("qx").to_list() == pytest.approx(
            [0.0001 * 60 * 60, 0.0001 * 65 * 70, 0.0001 * 70 * 65],
        )

    def test_joint_requires_both_ages(self, joint_life_table: Table) -> None:
        """Joint structure requires both age_1 and age_2."""
        m = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        pattern = "joint.*requires.*age_1.*age_2"
        with pytest.raises(ValueError, match=pattern):
            m.at(age_1=pl.col("age_1"))
        with pytest.raises(ValueError, match=pattern):
            m.at(age_2=pl.col("age_2"))

    def test_joint_rejects_single_age_kwarg(self, joint_life_table: Table) -> None:
        """Joint structure refuses age=; demands age_1=... + age_2=..."""
        m = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        with pytest.raises(ValueError, match="joint.*age_1.*age_2"):
            m.at(age=pl.col("age_1"), age_2=pl.col("age_2"))
