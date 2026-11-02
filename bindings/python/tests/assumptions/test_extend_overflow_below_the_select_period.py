# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``ExtendOverflow`` with ``to_value`` inside the select period is refused.

A 5-year select table with an ``Ult.`` column and ``to_value=3`` (or 5)
extended the ultimate rows over no duration: they dropped out of the table
with no word, and a lookup past the select period missed -- or, under
``on_missing``, answered its fill. The extension now refuses, naming where it
would start and the ``to_value`` it would need.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import ExtendOverflow, MeltDimension, Table

SRC = pl.DataFrame(
    {
        "age": [50],
        "1": [0.01],
        "2": [0.02],
        "3": [0.03],
        "4": [0.04],
        "5": [0.05],
        "Ult.": [0.09],
    }
)
COLUMNS = ["1", "2", "3", "4", "5", "Ult."]


def _table(name: str, overflow: ExtendOverflow) -> Table:
    return Table(
        name=name,
        source=SRC,
        value="q",
        dimensions={
            "age": "age",
            "dur": MeltDimension(COLUMNS, name="dur", overflow=overflow),
        },
    )


@pytest.mark.parametrize("to_value", [3, 5])
def test_a_to_value_inside_the_select_period_is_refused(to_value: int) -> None:
    with pytest.raises(ValueError, match=r"at least 6") as caught:
        _table(f"eo_below_{to_value}", ExtendOverflow("Ult.", to_value=to_value))
    assert f"to_value={to_value}" in str(caught.value)


def test_a_from_value_past_to_value_is_refused() -> None:
    with pytest.raises(ValueError, match=r"from_value=9"):
        _table("eo_from", ExtendOverflow("Ult.", to_value=8, from_value=9))


def test_a_to_value_past_the_select_period_extends_the_ultimate_rate() -> None:
    table = _table("eo_ok", ExtendOverflow("Ult.", to_value=8))
    af = ActuarialFrame(pl.DataFrame({"a": [50, 50, 50], "d": [5, 6, 8]}))
    af.q = table.lookup(age=af.a, dur=af.d)
    assert af.collect()["q"].to_list() == [0.05, 0.09, 0.09]
