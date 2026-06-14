# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Schedule.anniversary_mask() — true at policy / contract anniversaries.

Tests cover both constructors:
- ``from_inception``: uses ``anniversary_mask_expr()`` to produce a per-row
  boolean list expression.
- ``from_calendar_grid``: uses ``anniversary_mask()`` to produce a plain
  Python list.

Anniversary positions are structural (depend only on ``n_periods`` and
``frequency``), not on the per-row inception date.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

from gaspatchio_core.schedule._schedule import Schedule


class TestAnniversaryMaskFromInception:
    """``anniversary_mask_expr()`` on ``from_inception`` schedules."""

    def test_monthly_24_periods_anniversary_at_index_11(
        self, sample_policies: pl.DataFrame
    ) -> None:
        """Monthly periods, 24 of them.

        Anniversary every 12 months → mask[11] and mask[23] are True.
        All other positions are False.
        """
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=24,
            frequency="1M",
        )
        policies_with_mask = sample_policies.with_columns(
            mask=sched.anniversary_mask_expr()
        )
        for row_mask in policies_with_mask.get_column("mask").to_list():
            expected = [False] * 24
            expected[11] = True  # end of period 12 = first anniversary
            expected[23] = True  # end of period 24 = second anniversary
            assert row_mask == expected

    def test_quarterly_8_periods_anniversary_at_index_3(
        self, sample_policies: pl.DataFrame
    ) -> None:
        """Quarterly periods, 8 of them.

        Anniversary every 4 quarters → mask[3] and mask[7] are True.
        All other positions are False.
        """
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=8,
            frequency="3M",
        )
        policies_with_mask = sample_policies.with_columns(
            mask=sched.anniversary_mask_expr()
        )
        for row_mask in policies_with_mask.get_column("mask").to_list():
            expected = [False] * 8
            expected[3] = True
            expected[7] = True
            assert row_mask == expected


class TestAnniversaryMaskFromCalendarGrid:
    """``anniversary_mask()`` on ``from_calendar_grid`` schedules."""

    def test_monthly_returns_python_list(self) -> None:
        """Monthly 24-period grid returns a plain list of booleans.

        The result has length 24 with True at indices 11 and 23.
        """
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=24,
            frequency="1M",
        )
        mask = sched.anniversary_mask()
        assert len(mask) == 24
        expected = [False] * 24
        expected[11] = True
        expected[23] = True
        assert mask == expected
