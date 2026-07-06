# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for af.projection.set(...) — kwargs and Schedule paths."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.schedule import Schedule


class TestSetKwargsPath:
    """set() with valuation_date + until + until_value + frequency."""

    def test_maximum_age_uniform(self) -> None:
        af = ActuarialFrame({"policy_id": ["P1"], "issue_age": [30]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="maximum_age",
            until_value=100,
            frequency="monthly",
        )
        # Eager stamps present
        result = af.collect()
        assert "projection_start_date" in result.columns
        assert "projection_end_date" in result.columns
        assert "num_proj_months" in result.columns
        # Frame carries projection metadata
        assert af._projection is not None
        # 70 years × 12 months
        assert result["num_proj_months"][0] == 70 * 12 + 1  # +1 for start boundary

    def test_maximum_age_sizes_grid_from_youngest_life(self) -> None:
        """A shared max-age grid must be long enough for the YOUNGEST life.

        Regression for F1: the integer branch sized the uniform grid from
        ``max(issue_age)`` (the OLDEST life), giving the fewest months and
        truncating every younger cohort. For issue ages {30, 70} with
        ``until_value=100`` the grid must let the age-30 life reach attained
        age 100 -> 70 years -> 840 monthly periods (not 30 years / 360).
        """
        af = ActuarialFrame({"policy_id": ["P1", "P2"], "issue_age": [30, 70]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="maximum_age",
            until_value=100,
            frequency="monthly",
        )
        # Youngest life (age 30) reaches age 100 -> 70y -> 840 monthly periods.
        assert af._projection.n_periods == 70 * 12
        result = af.collect()
        assert result["num_proj_months"][0] == 70 * 12 + 1

    def test_term_years_uniform(self) -> None:
        af = ActuarialFrame({"policy_id": ["P1"]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_years",
            until_value=10,
            frequency="monthly",
        )
        result = af.collect()
        assert result["num_proj_months"][0] == 10 * 12 + 1

    def test_term_months_uniform(self) -> None:
        af = ActuarialFrame({"policy_id": ["P1"]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_months",
            until_value=24,
            frequency="monthly",
        )
        result = af.collect()
        assert result["num_proj_months"][0] == 24 + 1

    def test_term_months_per_policy_via_column(self) -> None:
        """Per-policy column until_value: jagged is the default.

        A column ``until_value`` with a ``term_*`` horizon auto-selects the
        jagged (per_policy) path, so each policy projects only its own horizon
        (num_proj_months = remaining + 1). Passing ``per_policy=False`` forces
        the uniform max+1 grid for every policy.
        """
        af = ActuarialFrame(
            {
                "policy_id": ["P1", "P2"],
                "remaining": [12, 36],
            }
        )
        # Default (auto) -> jagged: each policy projects its own horizon.
        jagged = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_months",
            until_value="remaining",
            frequency="monthly",
        ).collect()
        assert jagged["num_proj_months"].to_list() == [13, 37]

        # Opt out -> uniform max+1 for every policy.
        uniform = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_months",
            until_value="remaining",
            frequency="monthly",
            per_policy=False,
        ).collect()
        assert uniform["num_proj_months"].to_list() == [37, 37]

    def test_fixed_date(self) -> None:
        af = ActuarialFrame({"policy_id": ["P1"]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="fixed_date",
            until_value=date(2026, 1, 1),
            frequency="monthly",
        )
        result = af.collect()
        assert result["num_proj_months"][0] == 13


class TestSetSchedulePath:
    """set(schedule=Schedule.from_*(...)) accepts a pre-built Schedule."""

    def test_from_calendar_grid(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        af = ActuarialFrame({"policy_id": ["P1"]})
        af = af.projection.set(schedule=sched)
        assert af._projection is sched
        result = af.collect()
        assert "projection_start_date" in result.columns

    def test_from_inception(self) -> None:
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=12,
            frequency="1M",
        )
        af = ActuarialFrame(
            {
                "policy_id": ["P1"],
                "policy_inception": [date(2020, 6, 15)],
            }
        )
        af = af.projection.set(schedule=sched)
        assert af._projection is sched


class TestSetMutualExclusion:
    """schedule= cannot be combined with kwargs."""

    def test_schedule_with_kwargs_raises(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        af = ActuarialFrame({"policy_id": ["P1"]})
        with pytest.raises(ValueError, match="schedule= cannot be combined"):
            af.projection.set(
                schedule=sched,
                valuation_date=date(2025, 1, 1),
                until="term_years",
                until_value=10,
                frequency="monthly",
            )


class TestSetReturnsBehaviour:
    """set() returns a new frame; original is unchanged."""

    def test_returns_new_frame_original_untouched(self) -> None:
        af1 = ActuarialFrame({"policy_id": ["P1"], "issue_age": [30]})
        af2 = af1.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_years",
            until_value=10,
            frequency="monthly",
        )
        assert af1 is not af2
        assert af1._projection is None
        assert af2._projection is not None

    def test_recall_replaces_projection(self) -> None:
        af = ActuarialFrame({"policy_id": ["P1"], "issue_age": [30]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_years",
            until_value=10,
            frequency="monthly",
        )
        sched1 = af._projection
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_years",
            until_value=20,
            frequency="monthly",
        )
        assert af._projection is not sched1
        assert af.collect()["num_proj_months"][0] == 20 * 12 + 1


class TestSetSyntheticPath:
    """set() with start_date + n_periods + frequency for no-policy use."""

    def test_synthetic(self) -> None:
        af = ActuarialFrame({"id": ["demo"]})
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=10,
            frequency="monthly",
        )
        result = af.collect()
        assert result["num_proj_months"][0] == 11


class TestSetFrequencyVocab:
    """Both English and Schedule-shorthand vocabs accepted."""

    def test_english_monthly(self) -> None:
        af = ActuarialFrame({"id": ["P1"]})
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="monthly",
        )
        assert af._projection.frequency == "1M"

    def test_shorthand_1M(self) -> None:
        af = ActuarialFrame({"id": ["P1"]})
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        assert af._projection.frequency == "1M"

    def test_english_annual(self) -> None:
        af = ActuarialFrame({"id": ["P1"]})
        af = af.projection.set(
            start_date=date(2025, 1, 1),
            n_periods=10,
            frequency="annual",
        )
        assert af._projection.frequency == "1Y"
