# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for af.projection.set(...) — kwargs and Schedule paths."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.schedule import Schedule


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

    def test_maximum_age_runs_each_life_to_the_age(self) -> None:
        """Each life runs to age 100 from its own issue age, and no further.

        For issue ages {30, 70} with ``until_value=100`` the age-30 life
        runs 70 years (840 monthly periods) and the age-70 life 30 years
        (360): neither is truncated, and the older life is not projected
        past the age asked for. The grid states no period count of its own:
        each life's is its own horizon, and no other life's moves the recipe.
        """
        af = ActuarialFrame({"policy_id": ["P1", "P2"], "issue_age": [30, 70]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="maximum_age",
            until_value=100,
            frequency="monthly",
        )
        assert af._projection.n_periods is None
        result = af.collect()
        assert result["num_proj_months"].to_list() == [70 * 12 + 1, 30 * 12 + 1]

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
        # NOTE: `set()` stamps the timeline IN PLACE and returns the same
        # frame, so these two calls are not two independent projections off
        # one set of model points -- the second re-projects the frame the
        # first one stamped. That is supported (a re-projection replaces the
        # axis), and it is what this test asserts: the same frame projected
        # jagged, then re-projected uniform. To compare two genuinely
        # independent timelines, build two frames.
        # Default (auto) -> jagged: each policy projects its own horizon.
        jagged = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_months",
            until_value="remaining",
            frequency="monthly",
        ).collect()
        assert jagged["num_proj_months"].to_list() == [13, 37]

        # Opt out -> uniform max+1 for every policy (a re-projection of `af`).
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
    """The three ways to declare an axis are alternatives, not a blend.

    ``schedule=`` excludes the construction kwargs, and the two kwargs
    forms exclude each other: the synthetic form lays a calendar grid from
    a start date, the policy-anchored form runs each policy from the
    valuation date to its own horizon. Mixing them used to build silently
    from the synthetic pair while the projection record echoed every kwarg
    passed -- an author who meant one convention got the other, with the
    valuation date recorded as if it had been honoured.
    """

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

    def test_set_refuses_the_synthetic_and_policy_anchored_forms_together(
        self,
    ) -> None:
        af = ActuarialFrame({"policy_id": [1], "issue_age": [40]})
        with pytest.raises(
            ValueError,
            match=r"start_date/n_periods.*valuation_date/until/until_value",
        ):
            af.projection.set(
                start_date=date(2025, 1, 1),
                n_periods=12,
                valuation_date=date(2025, 1, 1),
                until="term_years",
                until_value=5,
                frequency="monthly",
            )

    def test_set_refuses_one_stray_kwarg_from_the_other_form(self) -> None:
        af = ActuarialFrame({"policy_id": [1], "issue_age": [40]})
        # "synthetic form" is unique to this refusal. Matching on the kwarg
        # name alone would also be satisfied by the schedule= message, which
        # lists n_periods among the kwargs it excludes.
        with pytest.raises(ValueError, match=r"synthetic form.*n_periods"):
            af.projection.set(
                valuation_date=date(2025, 1, 1),
                until="term_years",
                until_value=5,
                n_periods=12,
                frequency="monthly",
            )


class TestSetReturnsBehaviour:
    """set() declares the axis on the frame it was called on."""

    def test_returns_the_same_frame_now_carrying_the_projection(self) -> None:
        """The timeline is a step in the same model, not a different frame.

        ``set()`` used to build a replacement frame from the stamped plan,
        which threw away everything the model had recorded up to that line.
        It now stamps the frame in hand -- the way ``rename``/``join``/
        ``filter`` already do -- so the projection axis costs no history.
        """
        af = ActuarialFrame({"policy_id": ["P1"], "issue_age": [30]})

        projected = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_years",
            until_value=10,
            frequency="monthly",
        )

        assert projected is af
        assert af._projection is not None

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


def test_set_on_an_uninitialized_frame_says_so() -> None:
    """A frame built with no data has no plan to project, and is told so.

    projection.set read the frame's plan without asking whether it had one,
    and ``ActuarialFrame()`` has none, so the call failed with an
    AttributeError about ``NoneType`` -- an internal name -- where every
    other door on the frame refuses an uninitialized frame by saying so.
    """
    with pytest.raises(ValueError, match="uninitialized ActuarialFrame"):
        ActuarialFrame().projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_years",
            until_value=10,
            frequency="monthly",
        )
