# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Schedule canonical-form + source_sha tests."""

from __future__ import annotations

from datetime import date

from gaspatchio_core.schedule._calendar import NullCalendar, UnitedStates
from gaspatchio_core.schedule._day_count import Actual360
from gaspatchio_core.schedule._schedule import Schedule


class TestCanonicalForm:
    """Tests for Schedule.canonical_form() — structural identity dict."""

    def test_from_calendar_grid_canonical_shape(self) -> None:
        """canonical_form() for from_calendar_grid returns expected keys."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=240,
            frequency="1M",
        )
        cf = sched.canonical_form()
        assert cf == {
            "kind": "from_calendar_grid",
            "n_periods": 240,
            "frequency": "1M",
            "anchor": "month_end",
            "start_date": "2025-01-31",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
        }

    def test_from_inception_canonical_shape(self) -> None:
        """canonical_form() for from_inception returns expected keys."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=240,
            frequency="1M",
        )
        cf = sched.canonical_form()
        assert cf == {
            "kind": "from_inception",
            "n_periods": 240,
            "frequency": "1M",
            "inception_column": "contract_inception",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
        }


class TestSourceSha:
    """Tests for Schedule.source_sha() — sha256 fingerprint over canonical form."""

    def test_identical_schedules_have_identical_sha(self) -> None:
        """Two identically constructed schedules produce the same sha."""
        a = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M"
        )
        b = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M"
        )
        assert a.source_sha() == b.source_sha()

    def test_different_day_count_changes_sha(self) -> None:
        """Changing day_count produces a different sha."""
        a = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M"
        )
        b = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
            day_count=Actual360(),
        )
        assert a.source_sha() != b.source_sha()

    def test_different_calendar_changes_sha(self) -> None:
        """Changing calendar produces a different sha."""
        a = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
            calendar=NullCalendar(),
        )
        b = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
            calendar=UnitedStates(),
        )
        assert a.source_sha() != b.source_sha()

    def test_different_n_periods_changes_sha(self) -> None:
        """Changing n_periods produces a different sha."""
        a = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M"
        )
        b = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=24, frequency="1M"
        )
        assert a.source_sha() != b.source_sha()

    def test_sha_format_is_sha256_hex(self) -> None:
        """source_sha() returns 'sha256:' prefix + 64 hex chars."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M"
        )
        sha = sched.source_sha()
        assert sha.startswith("sha256:")
        assert len(sha) == len("sha256:") + 64  # 32-byte hex

    def test_constructor_kind_changes_sha_even_with_same_params(self) -> None:
        """from_inception and from_calendar_grid produce different shas."""
        a = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M"
        )
        b = Schedule.from_inception(
            inception_column="contract_inception", n_periods=12, frequency="1M"
        )
        assert a.source_sha() != b.source_sha()
