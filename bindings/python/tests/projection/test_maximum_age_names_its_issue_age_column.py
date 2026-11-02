# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A ``maximum_age`` horizon names a missing or non-numeric issue-age column (11.1.1).

Each policy runs ``until_value`` less its issue age, read from the column
``issue_age_column`` names. A name the frame does not carry failed inside the
query plan in Polars' words (``ColumnNotFoundError``), text failed there as
arithmetic on a string, and a flag was read as an issue age of 1. Each is now
refused at ``projection.set()``, naming the column and the move.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame


def _set(frame: pl.DataFrame, **kwargs: object) -> ActuarialFrame:
    return ActuarialFrame(frame).projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        frequency="annual",
        until="maximum_age",
        until_value=100,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("kwargs", "named"),
    [
        ({}, "issue_age"),
        ({"issue_age_column": "nope"}, "nope"),
        ({"per_policy": True}, "issue_age"),
    ],
)
def test_a_missing_issue_age_column_is_refused_by_name(
    kwargs: dict[str, object], named: str
) -> None:
    with pytest.raises(ValueError, match=f"issue_age_column='{named}'") as refused:
        _set(pl.DataFrame({"id": [1], "age": [40]}), **kwargs)
    assert "Columns on the frame: id, age." in str(refused.value)


@pytest.mark.parametrize(("value", "kind"), [("98", "String"), (True, "Boolean")])
def test_an_issue_age_that_is_not_a_number_is_refused_by_kind(
    value: object, kind: str
) -> None:
    with pytest.raises(TypeError, match=f"which holds {kind} values"):
        _set(pl.DataFrame({"id": [1], "issue_age": [value]}))


@pytest.mark.parametrize("age", [98, 98.0, 97.5])
def test_a_numeric_issue_age_still_runs_its_whole_years(age: float) -> None:
    # 100 - 97.5 is 2.5 years, truncated toward zero (11.1.1).
    af = _set(pl.DataFrame({"id": [1], "issue_age": [age]}))
    af.t = af.projection.t_years()
    assert af.collect()["t"].to_list() == [[0.0, 1.0, 2.0]]
