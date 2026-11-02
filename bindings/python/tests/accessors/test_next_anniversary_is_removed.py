# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``until="next_anniversary"`` and ``projection.set(inception_column=)`` are gone.

``next_anniversary`` laid ``until_value`` whole years from the
valuation date for every policy -- ``term_years``'s count -- while its name and
design note promised each policy's own contract anniversary: three policies
whose anniversaries fall 5.42, 1.02 and 11.96 months away all ran 13 monthly
boundaries. ``inception_column=`` was accepted and never read; a column that
did not exist ran. The spelling is refused by name, pointing at ``term_years``
for whole years and at ``Schedule.from_inception`` with ``anniversary_mask``
for renewals; the keyword is removed.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

BOOK = pl.DataFrame(
    {
        "pid": [1, 2, 3],
        "issue_date": [
            dt.date(2020, 6, 15),
            dt.date(2024, 2, 1),
            dt.date(2019, 12, 31),
        ],
        "k": [1, 1, 2],
    }
)


@pytest.mark.parametrize("until_value", [1, "k"])
def test_next_anniversary_is_refused_naming_both_readings(
    until_value: object,
) -> None:
    af = ActuarialFrame(BOOK)
    with pytest.raises(ValueError, match=r'until="next_anniversary"\) is removed') as e:
        af.projection.set(
            valuation_date=dt.date(2025, 1, 1),
            until="next_anniversary",  # type: ignore[arg-type]
            until_value=until_value,
            frequency="monthly",
        )
    said = str(e.value)
    assert 'until="term_years", until_value=k' in said
    assert "Schedule.from_inception" in said
    assert "anniversary_mask()" in said


def test_inception_column_is_no_longer_a_keyword_of_set() -> None:
    af = ActuarialFrame(BOOK)
    with pytest.raises(TypeError, match=r"inception_column"):
        af.projection.set(  # type: ignore[call-arg]
            valuation_date=dt.date(2025, 1, 1),
            until="term_years",
            until_value=1,
            frequency="monthly",
            inception_column="nope",
        )


def test_term_years_is_the_count_next_anniversary_answered() -> None:
    """The old spelling's count, now written as what it is: 12 periods a year."""
    af = ActuarialFrame(BOOK)
    af = af.projection.set(
        valuation_date=dt.date(2025, 1, 1),
        until="term_years",
        until_value=1,
        frequency="monthly",
    )
    assert af.collect()["num_proj_months"].to_list() == [13, 13, 13]
