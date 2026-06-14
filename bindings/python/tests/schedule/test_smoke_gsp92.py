# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end smoke test mirroring the GSP-92 VA Illustration schedule shape.

Validates that a 1200-period (100yr) per-policy schedule with the
OneTwelfth + NullCalendar default produces consistent dt[t] = 1/12 and
correctly-aligned anniversary masks across leap-year crossings.

This is the canonical 'hard case' the redesign exists to enable.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import Schedule


class TestGsp92ScheduleShape:
    """Smoke tests for a 1200-period per-policy schedule (GSP-92 shape)."""

    def test_1200_period_schedule_constructs(self) -> None:
        """Schedule.from_inception with n_periods=1200 stores the count correctly."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        assert sched.n_periods == 1200

    def test_1200_period_year_fractions_per_row(self) -> None:
        """Every row of year_fractions_expr() yields 1200 entries all equal to 1/12."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        policies = pl.DataFrame(
            {
                "policy_id": [1, 2],
                "contract_inception": [date(2024, 2, 29), date(2025, 6, 1)],
            }
        )
        result = policies.with_columns(yfs=sched.year_fractions_expr())
        for row in result.get_column("yfs").to_list():
            assert len(row) == 1200
            for yf in row:
                assert yf == pytest.approx(1 / 12)

    def test_anniversary_mask_fires_at_every_12th_period(self) -> None:
        """anniversary_mask_expr() marks exactly 100 True entries per 12th period."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        policies = pl.DataFrame(
            {
                "policy_id": [1, 2],
                "contract_inception": [date(2024, 2, 29), date(2025, 6, 1)],
            }
        )
        result = policies.with_columns(mask=sched.anniversary_mask_expr())
        for row in result.get_column("mask").to_list():
            assert sum(row) == 100  # 100 anniversaries over 1200 monthly periods
            for t in range(1200):
                assert row[t] == ((t + 1) % 12 == 0)

    def test_period_dates_per_policy_count(self) -> None:
        """period_dates_expr() yields n_periods + 1 boundary dates per row."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        policies = pl.DataFrame(
            {
                "policy_id": [1, 2],
                "contract_inception": [date(2024, 2, 29), date(2025, 6, 1)],
            }
        )
        result = policies.with_columns(dates=sched.period_dates_expr())
        for row in result.get_column("dates").to_list():
            assert len(row) == 1201  # 1200 periods -> 1201 boundaries

    def test_source_sha_stable_across_runs(self) -> None:
        """Two identically-parameterised schedules produce the same source_sha()."""
        a = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        b = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        assert a.source_sha() == b.source_sha()
