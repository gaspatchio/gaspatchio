# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for Schedule.is_in_force_expr() — the per-period boundary mask."""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core.schedule import Schedule


class TestIsInForceExpr:
    """is_in_force_expr() returns a List<Boolean> of length n_periods."""

    def test_from_calendar_grid_all_true_when_no_end(self) -> None:
        """With no end_date, every period is in-force."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=4,
            frequency="1M",
        )
        frame = pl.DataFrame({"id": ["P1"]}).lazy()
        frame = frame.with_columns(in_force=sched.is_in_force_expr())
        result = frame.collect()["in_force"].to_list()
        assert result == [[True, True, True, True]]

    def test_from_inception_truncates_at_end_date(self) -> None:
        """Per-policy: each row's mask reflects its end_date column."""
        sched = Schedule.from_inception(
            inception_column="incep",
            n_periods=6,
            frequency="1M",
        )
        frame = pl.DataFrame(
            {
                "incep": [date(2025, 1, 31), date(2025, 1, 31)],
                "end_date": [date(2025, 4, 30), date(2025, 6, 30)],
            },
        ).lazy()
        frame = frame.with_columns(
            in_force=sched.is_in_force_expr(end_date_column="end_date"),
        )
        result = frame.collect()["in_force"].to_list()
        # First policy ends 2025-04-30: Feb/Mar/Apr in-force; May/Jun/Jul out.
        # Second policy ends 2025-06-30: Feb-Jun in-force; Jul out.
        assert result[0] == [True, True, True, False, False, False]
        assert result[1] == [True, True, True, True, True, False]

    def test_length_matches_n_periods(self) -> None:
        """The returned list per row has exactly ``n_periods`` entries."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=10,
            frequency="1M",
        )
        frame = pl.DataFrame({"id": ["P1"]}).lazy()
        frame = frame.with_columns(in_force=sched.is_in_force_expr())
        result = frame.collect()["in_force"].to_list()
        assert len(result[0]) == 10

    def test_null_end_date_treated_as_in_force(self) -> None:
        """A row with null end_date is treated as still in force — all True."""
        sched = Schedule.from_inception(
            inception_column="incep",
            n_periods=4,
            frequency="1M",
        )
        frame = pl.DataFrame(
            {
                "incep": [date(2025, 1, 31), date(2025, 1, 31)],
                "end_date": [date(2025, 3, 31), None],
            }
        ).lazy()
        frame = frame.with_columns(
            in_force=sched.is_in_force_expr(end_date_column="end_date"),
        )
        result = frame.collect()["in_force"].to_list()
        assert result[0] == [True, True, False, False]
        assert result[1] == [True, True, True, True]

    def test_n_periods_zero(self) -> None:
        """Zero-period schedule returns an empty list, regardless of branch."""
        sched_grid = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=0,
            frequency="1M",
        )
        sched_incep = Schedule.from_inception(
            inception_column="incep",
            n_periods=0,
            frequency="1M",
        )
        frame = pl.DataFrame(
            {
                "incep": [date(2025, 1, 31)],
                "end_date": [date(2025, 6, 30)],
            }
        ).lazy()
        # Both branches produce empty lists
        result_grid = (
            frame.with_columns(in_force=sched_grid.is_in_force_expr())
            .collect()["in_force"]
            .to_list()
        )
        result_incep = (
            frame.with_columns(
                in_force=sched_incep.is_in_force_expr(end_date_column="end_date"),
            )
            .collect()["in_force"]
            .to_list()
        )
        assert result_grid == [[]]
        assert result_incep == [[]]


class TestContractBoundaryExpr:
    """Tests for Schedule.contract_boundary_expr() — the is_in_force_expr negation."""

    def test_from_calendar_grid_all_false(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=4,
            frequency="1M",
        )
        frame = pl.DataFrame({"id": ["P1"]}).lazy()
        frame = frame.with_columns(boundary=sched.contract_boundary_expr())
        result = frame.collect()["boundary"].to_list()
        assert result == [[False, False, False, False]]

    def test_from_inception_fires_after_end_date(self) -> None:
        sched = Schedule.from_inception(
            inception_column="incep",
            n_periods=6,
            frequency="1M",
        )
        frame = pl.DataFrame(
            {
                "incep": [date(2025, 1, 31), date(2025, 1, 31)],
                "end_date": [date(2025, 4, 30), date(2025, 6, 30)],
            },
        ).lazy()
        frame = frame.with_columns(
            boundary=sched.contract_boundary_expr(end_date_column="end_date"),
        )
        result = frame.collect()["boundary"].to_list()
        # Policy 1 ends 2025-04-30: periods 0,1,2 in force (False); 3,4,5 terminated.
        # Policy 2 ends 2025-06-30: periods 0,1,2,3,4 in force (False); 5 terminated.
        assert result[0] == [False, False, False, True, True, True]
        assert result[1] == [False, False, False, False, False, True]

    def test_null_end_date_means_no_boundary(self) -> None:
        """Null end_date is treated as still in force — all False (no boundary)."""
        sched = Schedule.from_inception(
            inception_column="incep",
            n_periods=4,
            frequency="1M",
        )
        frame = pl.DataFrame(
            {
                "incep": [date(2025, 1, 31), date(2025, 1, 31)],
                "end_date": [date(2025, 3, 31), None],
            },
        ).lazy()
        frame = frame.with_columns(
            boundary=sched.contract_boundary_expr(end_date_column="end_date"),
        )
        result = frame.collect()["boundary"].to_list()
        assert result[0] == [False, False, True, True]  # policy 1 ends after period 1
        assert result[1] == [False, False, False, False]  # policy 2 null → all False
