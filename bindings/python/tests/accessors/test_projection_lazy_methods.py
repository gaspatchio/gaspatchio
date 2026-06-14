# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for af.projection.{period_dates, year_fractions, t_years, ...} lazy methods."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.schedule import Schedule


def _af_with_synthetic_projection(n: int = 12) -> ActuarialFrame:
    af = ActuarialFrame({"id": ["P1"]})
    return af.projection.set(
        start_date=date(2025, 1, 31),
        n_periods=n,
        frequency="monthly",
    )


class TestPeriodDates:
    def test_returns_list_of_n_plus_one_dates(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(af.projection.period_dates().alias("period_dates"))
        result = af.collect()
        assert len(result["period_dates"][0]) == 13


class TestYearFractions:
    def test_length_n_for_monthly(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(af.projection.year_fractions().alias("year_fractions"))
        result = af.collect()
        assert len(result["year_fractions"][0]) == 12

    def test_each_value_is_one_twelfth(self) -> None:
        af = _af_with_synthetic_projection(n=3)
        af = af.with_columns(af.projection.year_fractions().alias("year_fractions"))
        result = af.collect()
        values = result["year_fractions"][0]
        for v in values:
            assert v == pytest.approx(1.0 / 12.0)


class TestTYears:
    def test_starts_at_zero_length_n_plus_one(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(af.projection.t_years().alias("t_years"))
        result = af.collect()
        ty = result["t_years"][0]
        assert len(ty) == 13
        assert ty[0] == pytest.approx(0.0)
        assert ty[-1] == pytest.approx(1.0)

    def test_monotonically_increasing(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(af.projection.t_years().alias("t_years"))
        result = af.collect()
        ty = result["t_years"][0]
        for i in range(len(ty) - 1):
            assert ty[i + 1] > ty[i]


class TestAnniversaryMask:
    def test_length_n_for_monthly(self) -> None:
        af = _af_with_synthetic_projection(n=24)
        af = af.with_columns(af.projection.anniversary_mask().alias("mask"))
        result = af.collect()
        assert len(result["mask"][0]) == 24

    def test_anniversary_at_period_11_and_23(self) -> None:
        af = _af_with_synthetic_projection(n=24)
        af = af.with_columns(af.projection.anniversary_mask().alias("mask"))
        result = af.collect()
        mask = result["mask"][0]
        # Every 12th period closes an anniversary
        assert mask[11] is True
        assert mask[23] is True
        assert mask[0] is False
        assert mask[10] is False


class TestIsInForce:
    def test_uniform_true_when_no_end(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(af.projection.is_in_force().alias("in_force"))
        result = af.collect()
        assert result["in_force"][0].to_list() == [True] * 12


class TestContractBoundary:
    def test_uniform_false_when_no_end(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(af.projection.contract_boundary().alias("boundary"))
        result = af.collect()
        assert result["boundary"][0].to_list() == [False] * 12


class TestGovernanceHooks:
    def test_canonical_form_returns_dict(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        cf = af.projection.canonical_form()
        assert isinstance(cf, dict)
        assert cf["n_periods"] == 12
        assert cf["frequency"] == "1M"

    def test_source_sha_starts_with_sha256(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        sha = af.projection.source_sha()
        assert sha.startswith("sha256:")
        assert len(sha) == len("sha256:") + 64

    def test_source_sha_matches_kwargs_and_schedule_paths(self) -> None:
        """Both paths produce identical canonical bytes for equivalent inputs."""
        af1 = ActuarialFrame({"id": ["P1"]})
        af1 = af1.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="monthly",
        )
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        af2 = ActuarialFrame({"id": ["P1"]})
        af2 = af2.projection.set(schedule=sched)
        assert af1.projection.source_sha() == af2.projection.source_sha()


class TestErrorWhenNoProjection:
    def test_period_dates_without_set_raises(self) -> None:
        af = ActuarialFrame({"id": ["P1"]})
        with pytest.raises(ValueError, match="no projection"):
            af.projection.period_dates()
