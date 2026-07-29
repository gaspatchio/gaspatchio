# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``projection.set()`` materialises the period index.

Regression test for #36. Shipped examples used ``af.month`` as though it
existed; it did not, and hand-rolling it invited an off-by-one, because
``t_years()`` returns ``n_periods + 1`` values while ``year_fractions()``
returns ``n_periods``.

``month`` is **elapsed whole months from the projection start**, derived from
the period boundary dates rather than from a periods-to-months multiple, so the
name stays honest at every frequency including the ones that are not
month-aligned (``1W``, ``1D``).

The annual index is ``proj_year``, never ``year``: model points routinely carry
a calendar ``year``, and AGENTS.md Gotcha #7 already names ``proj_year`` vs
``year`` as a cause of silently-wrong stress scenarios.
"""

import datetime

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


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


def _months_for(frequency: str, n_periods: int) -> list[int]:
    af = _frame().projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=n_periods,
        frequency=frequency,
    )
    return af.collect()["month"].to_list()[0]


def test_monthly_month_is_consecutive_from_zero() -> None:
    """Monthly periods are one month apart."""
    assert _months_for("monthly", 24) == list(range(25))


def test_quarterly_month_steps_by_three() -> None:
    """Quarterly periods are three months apart."""
    assert _months_for("quarterly", 4) == [0, 3, 6, 9, 12]


def test_annual_month_steps_by_twelve() -> None:
    """Annual periods are twelve months apart."""
    assert _months_for("annual", 3) == [0, 12, 24, 36]


def test_semi_annual_month_steps_by_six() -> None:
    """Semi-annual periods are six months apart."""
    assert _months_for("semi-annual", 3) == [0, 6, 12, 18]


def test_weekly_month_is_elapsed_months_not_a_period_count() -> None:
    """A non-month-aligned frequency must still report honest months.

    Nine weekly periods from 1 Jan cross into February; a periods-to-months
    multiple would report 0..9 as if they were months.
    """
    months = _months_for("weekly", 9)
    assert months[0] == 0
    assert max(months) <= 3  # nine weeks is at most three calendar months on
    assert months == sorted(months)  # never goes backwards


def test_proj_year_is_month_floor_div_twelve() -> None:
    """proj_year is exactly month // 12."""
    af = _frame().projection.set(
        start_date=datetime.date(2025, 1, 1),
        n_periods=30,
        frequency="monthly",
    )
    out = af.collect()
    months = out["month"].to_list()[0]
    assert out["proj_year"].to_list()[0] == [m // 12 for m in months]


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


@pytest.mark.parametrize("reserved", ["month", "proj_year"])
def test_existing_column_collision_raises(reserved: str) -> None:
    """Silently overwriting a user's column is the failure this batch removes."""
    mp = pl.DataFrame(
        {
            "policy_id": [1],
            "issue_age": [40],
            "policy_inception": [datetime.date(2020, 1, 1)],
            reserved: [7],
        }
    )
    with pytest.raises(ValueError, match=reserved):
        ActuarialFrame(mp).projection.set(
            start_date=datetime.date(2025, 1, 1),
            n_periods=12,
            frequency="monthly",
        )


def test_reprojecting_replaces_the_period_index() -> None:
    """Calling set() twice is supported; the index is ours to replace.

    The collision guard protects the user's columns, not the ones a previous
    set() stamped — a user-supplied ``month`` could never have survived the
    first call.
    """
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
    lengths = [len(m) for m in out["month"].to_list()]
    assert lengths[0] != lengths[1]
    for months in out["month"].to_list():
        assert months == list(range(len(months)))
