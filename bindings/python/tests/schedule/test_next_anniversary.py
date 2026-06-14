# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for Schedule.next_anniversary_date()."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio_core.schedule import Schedule


class TestNextAnniversaryDate:
    """``next_anniversary_date`` returns the Nth anniversary on/after valuation."""

    def test_n_equals_one_returns_next_anniversary(self) -> None:
        """Inception 2020-06-15; valuation 2025-01-01; n=1 -> 2025-06-15."""
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=120,
            frequency="1M",
        )
        result = sched.next_anniversary_date(
            inception=date(2020, 6, 15),
            valuation_date=date(2025, 1, 1),
            n=1,
        )
        assert result == date(2025, 6, 15)

    def test_valuation_on_anniversary_returns_same_date(self) -> None:
        """Valuation date that is itself an anniversary returns the same date."""
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=120,
            frequency="1M",
        )
        result = sched.next_anniversary_date(
            inception=date(2020, 6, 15),
            valuation_date=date(2025, 6, 15),
            n=1,
        )
        assert result == date(2025, 6, 15)

    def test_n_equals_two_returns_anniversary_after_next(self) -> None:
        """n=2 returns the anniversary one year after the next anniversary."""
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=120,
            frequency="1M",
        )
        result = sched.next_anniversary_date(
            inception=date(2020, 6, 15),
            valuation_date=date(2025, 1, 1),
            n=2,
        )
        assert result == date(2026, 6, 15)

    def test_leap_year_inception(self) -> None:
        """Feb 29 inception in a non-leap target year falls back to Feb 28."""
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=120,
            frequency="1M",
        )
        result = sched.next_anniversary_date(
            inception=date(2020, 2, 29),
            valuation_date=date(2024, 12, 1),
            n=1,
        )
        assert result == date(2025, 2, 28)

    def test_n_zero_raises(self) -> None:
        """n=0 raises ValueError; n must be >= 1."""
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=120,
            frequency="1M",
        )
        with pytest.raises(ValueError, match="n must be >= 1"):
            sched.next_anniversary_date(
                inception=date(2020, 6, 15),
                valuation_date=date(2025, 1, 1),
                n=0,
            )

    def test_only_valid_for_from_inception(self) -> None:
        """from_calendar_grid schedules raise — they have no per-policy anchor."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        with pytest.raises(ValueError, match="from_inception"):
            sched.next_anniversary_date(
                inception=date(2020, 6, 15),
                valuation_date=date(2025, 1, 1),
                n=1,
            )
