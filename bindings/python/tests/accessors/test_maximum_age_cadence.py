# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A maximum age is refused at a weekly or daily cadence, as a term is.

A maximum age runs each policy a whole number of years -- the age less its
issue age -- and a number of years is not a whole number of weeks or days
(52 a year against the calendar's 52.18). ``term_*`` already refuses those
cadences for the same reason; ``maximum_age`` laid one shared grid of 52 or
365 periods a year sized from the youngest life, two policies aged 98 and 99
both getting 105 weekly boundaries. It is now refused in the same sentence.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

BOOK = pl.DataFrame({"policy_id": ["A", "B"], "issue_age": [98, 99]})


@pytest.mark.parametrize("frequency", ["weekly", "daily", "1W", "1D"])
@pytest.mark.parametrize("per_policy", [None, False, True])
def test_a_maximum_age_at_a_weekly_or_daily_cadence_is_refused(
    frequency: str,
    per_policy: bool | None,  # noqa: FBT001 -- a parametrized case
) -> None:
    with pytest.raises(ValueError, match="month/year horizon") as refused:
        ActuarialFrame(BOOK).projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="maximum_age",
            until_value=100,
            frequency=frequency,
            per_policy=per_policy,
        )
    message = str(refused.value)
    assert "until='maximum_age'" in message
    assert "requires a month-aligned frequency" in message
    assert "not a whole number of weeks or days" in message


def test_the_sentence_is_the_term_horizons_own() -> None:
    with pytest.raises(ValueError, match="month/year horizon") as term:
        ActuarialFrame(BOOK).projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="term_years",
            until_value=5,
            frequency="weekly",
        )
    with pytest.raises(ValueError, match="month/year horizon") as age:
        ActuarialFrame(BOOK).projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="maximum_age",
            until_value=100,
            frequency="weekly",
        )
    assert str(age.value).startswith(
        str(term.value).replace("until='term_years'", "until='maximum_age'")
    )


def test_a_month_aligned_cadence_still_runs_each_life_to_the_age() -> None:
    # Hand values: ages 98 and 99 to 100 quarterly are 8 and 4 periods.
    out = (
        ActuarialFrame(BOOK)
        .projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="maximum_age",
            until_value=100,
            frequency="quarterly",
        )
        .collect()
    )
    assert out["num_proj_months"].to_list() == [9, 5]
