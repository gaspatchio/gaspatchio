# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``projection.set()`` materialises the ``month`` period index.

Regression test for #36. Shipped examples used ``af.month`` as though it
existed; it did not, and hand-rolling it invited an off-by-one, because
``t_years()`` returns ``n_periods + 1`` values while ``year_fractions()``
returns ``n_periods``.

``month`` is **elapsed whole months from the projection start** and is stamped
only where that name is honest: month-aligned frequencies (1M/3M/6M/1Y) on a
projection-anchored axis. At 1W/1D a calendar-month difference over-counts by
up to a month, and on ``from_inception`` the axis is policy DURATION — in both
cases no index is fabricated.

There is deliberately **no** ``proj_year``: a projection-year label depends on
the model's timing convention. End-of-period rows: "year 1" is
``ceil(month/12)``; beginning-of-period rows: ``month // 12 + 1``. The two
disagree at every anniversary boundary, so the framework materialising either
would silently pick a timing convention on the user's behalf. The model states
its own one-line formula.
"""

import datetime

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, when


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "issue_age": [40],
                "policy_inception": [datetime.date(2020, 1, 1)],
            }
        )
    )


def _collected(frequency: str, n_periods: int) -> pl.DataFrame:
    af = _frame().projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=n_periods,
        frequency=frequency,
    )
    return af.collect()


def test_monthly_month_is_consecutive_from_zero() -> None:
    """Monthly periods are one month apart."""
    assert _collected("monthly", 24)["month"].to_list()[0] == list(range(25))


def test_quarterly_month_steps_by_three() -> None:
    """Quarterly periods are three months apart."""
    assert _collected("quarterly", 4)["month"].to_list()[0] == [0, 3, 6, 9, 12]


def test_annual_month_steps_by_twelve() -> None:
    """Annual periods are twelve months apart."""
    assert _collected("annual", 3)["month"].to_list()[0] == [0, 12, 24, 36]


def test_semi_annual_month_steps_by_six() -> None:
    """Semi-annual periods are six months apart."""
    assert _collected("semi-annual", 3)["month"].to_list()[0] == [0, 6, 12, 18]


def test_month_dtype_is_int32() -> None:
    """One dtype on every path — a period index does not need Int64."""
    assert _collected("monthly", 12).schema["month"] == pl.List(pl.Int32)


@pytest.mark.parametrize("frequency", ["weekly", "daily"])
def test_no_month_at_sub_month_frequencies(frequency: str) -> None:
    """No fabricated index where calendar months cannot label the periods.

    A calendar-month difference over-counts at these cadences — a daily grid
    from Jan 31 would read "month 1" after ONE day — so ``month`` is honest
    only on month-aligned grids and is not stamped elsewhere.
    """
    out = _collected(frequency, 9)
    assert "month" not in out.columns
    # The rest of the eager stamp is unaffected.
    assert "num_proj_months" in out.columns


def test_no_month_on_a_from_inception_axis() -> None:
    """from_inception counts from each policy's OWN inception.

    Elapsed months there are policy duration, not projection time — the exact
    `proj_year` vs `year` class of conflation Gotcha #7 warns about, and the
    axis scenarios/_aggregated.py already refuses for calendar aggregation.
    """
    from gaspatchio_core import Schedule

    mp = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "policy_inception": [
                datetime.date(2020, 3, 15),
                datetime.date(2022, 7, 1),
            ],
        }
    )
    schedule = Schedule.from_inception(
        n_periods=12,
        frequency="1M",
        inception_column="policy_inception",
    )
    out = ActuarialFrame(mp).projection.set(schedule=schedule).collect()
    assert "month" not in out.columns


def test_no_proj_year_column() -> None:
    """The framework must not pick the user's timing convention for them."""
    out = _collected("monthly", 12)
    assert "proj_year" not in out.columns
    assert "year" not in out.columns


def test_both_year_formulas_from_agents_md() -> None:
    """The two documented one-liners give the two documented conventions."""
    af = _frame().projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=25,
        frequency="monthly",
    )
    af.duration_years = af.month // 12
    # The AGENTS.md ordinal line, verbatim: month 0 (the projection start)
    # belongs to year 1 — a bare ceil would label it year 0 and a
    # `policy_year == 1` shock would skip the first row.
    af.policy_year = when(af.month == 0).then(1).otherwise((af.month + 11) // 12)
    out = af.collect()
    months = out["month"].to_list()[0]
    duration = out["duration_years"].to_list()[0]
    ordinal = out["policy_year"].to_list()[0]
    assert duration == [m // 12 for m in months]
    assert ordinal == [max(1, -(-m // 12)) for m in months]  # ceil, month 0 -> 1
    assert ordinal[0] == 1
    # And they disagree exactly at the anniversary boundaries, which is why
    # the framework stamps neither.
    disagreements = [
        m for m, d, o in zip(months, duration, ordinal, strict=False) if d + 1 != o
    ]
    assert disagreements == [12, 24]


def test_length_matches_t_years() -> None:
    """Aligned with t_years() so a maturity test can fire on the final period."""
    af = _frame().projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=12,
        frequency="monthly",
    )
    af.ty = af.projection.t_years()
    out = af.collect()
    assert len(out["month"].to_list()[0]) == len(out["ty"].to_list()[0])


def test_maturity_comparison_from_agents_md_fires() -> None:
    """The documented maturity idiom must actually reach the boundary."""
    mp = pl.DataFrame(
        {
            "policy_id": [1],
            "issue_age": [40],
            "policy_inception": [datetime.date(2020, 1, 1)],
            "policy_term": [2],
        }
    )
    af = ActuarialFrame(mp).projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=36,
        frequency="monthly",
    )
    af.at_maturity = af.month == af.policy_term * 12
    flags = af.collect()["at_maturity"].to_list()[0]
    # Comparisons materialise as 1.0/0.0 rather than booleans; what matters is
    # that the boundary is reachable and hit exactly once.
    assert sum(flags) == 1, "maturity must fire exactly once"
    assert flags[24], "maturity must fire at month 24 for a 2-year term"
    assert not any(flags[:24])
    assert not any(flags[25:])


def test_existing_month_column_raises_naming_both_exits() -> None:
    """We cannot tell a user's month from a reloaded run's — so refuse."""
    mp = pl.DataFrame(
        {
            "policy_id": [1],
            "issue_age": [40],
            "policy_inception": [datetime.date(2020, 1, 1)],
            "month": [7],
        }
    )
    with pytest.raises(ValueError, match="already has a 'month' column") as excinfo:
        ActuarialFrame(mp).projection.set(
            start_date=datetime.date(2025, 1, 1),
            n_periods=12,
            frequency="monthly",
        )
    message = str(excinfo.value)
    assert "rename" in message
    assert "drop" in message


@pytest.mark.parametrize("frequency", ["weekly", "daily"])
def test_existing_month_survives_an_unstamped_schedule(frequency: str) -> None:
    """No stamp, no collision — the user's column is left exactly alone.

    Weekly/daily schedules never materialise ``month``, so a frame carrying
    its own (e.g. a calendar month from the model points) must project
    without being told to rename a column nothing was going to touch.
    """
    mp = pl.DataFrame(
        {
            "policy_id": [1],
            "issue_age": [40],
            "policy_inception": [datetime.date(2020, 1, 1)],
            "month": [7],
        }
    )
    out = (
        ActuarialFrame(mp)
        .projection.set(
            start_date=datetime.date(2025, 1, 1),
            n_periods=9,
            frequency=frequency,
        )
        .collect()
    )
    assert out["month"].to_list() == [7]


def test_existing_month_survives_a_from_inception_schedule() -> None:
    """Same contract on the duration axis, which also never stamps."""
    from gaspatchio_core import Schedule

    mp = pl.DataFrame(
        {
            "policy_id": [1],
            "policy_inception": [datetime.date(2020, 3, 15)],
            "month": [7],
        }
    )
    schedule = Schedule.from_inception(
        n_periods=12,
        frequency="1M",
        inception_column="policy_inception",
    )
    out = ActuarialFrame(mp).projection.set(schedule=schedule).collect()
    assert out["month"].to_list() == [7]


def test_reprojecting_replaces_the_period_index() -> None:
    """Calling set() twice in-session is supported; the index is ours."""
    af = _frame().projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=12,
        frequency="monthly",
    )
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=24,
        frequency="monthly",
    )
    assert af.collect()["month"].to_list()[0] == list(range(25))


def test_round_trip_reprojection_raises_with_the_drop_remedy() -> None:
    """A reconstructed frame carries month without a live projection.

    ``ActuarialFrame(af.collect())`` (or a parquet reload) loses the
    in-session projection, so the guard cannot know the month column is ours.
    It must refuse with the drop remedy, not silently overwrite and not tell
    the user to rename the framework's own column as though it were theirs.
    """
    af = _frame().projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=12,
        frequency="monthly",
    )
    reloaded = ActuarialFrame(af.collect())
    with pytest.raises(ValueError, match="drop"):
        reloaded.projection.set(
            start_date=datetime.date(2025, 1, 1),
            n_periods=24,
            frequency="monthly",
        )
    # And the documented remedy works.
    recovered = ActuarialFrame(af.collect().drop("month")).projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=24,
        frequency="monthly",
    )
    assert recovered.collect()["month"].to_list()[0] == list(range(25))


def test_jagged_timeline_month_lengths_differ_per_policy() -> None:
    """Per-policy horizons make month jagged too, not padded to the longest."""
    mp = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "issue_age": [40, 60],
            "policy_inception": [
                datetime.date(2020, 1, 1),
                datetime.date(2020, 1, 1),
            ],
            "policy_term": [5, 10],
        }
    )
    af = ActuarialFrame(mp).projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_years",
        until_value="policy_term",
        frequency="monthly",
        per_policy=True,
    )
    out = af.collect()
    assert out.schema["month"] == pl.List(pl.Int32)
    lengths = [len(m) for m in out["month"].to_list()]
    assert lengths[0] != lengths[1]
    for months in out["month"].to_list():
        assert months == list(range(len(months)))


def test_null_horizon_stamps_an_empty_index_not_a_null_one() -> None:
    """Matches num_proj_months' own null guard four lines above it."""
    mp = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "issue_age": [40, 60],
            "policy_inception": [
                datetime.date(2020, 1, 1),
                datetime.date(2020, 1, 1),
            ],
            "policy_term": [5, None],
        }
    )
    af = ActuarialFrame(mp).projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_years",
        until_value="policy_term",
        frequency="monthly",
        per_policy=True,
    )
    out = af.collect()
    months = out["month"].to_list()
    assert months[1] == [], f"null horizon must stamp [], got {months[1]!r}"
