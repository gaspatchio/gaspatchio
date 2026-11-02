# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A one-row table keyed by text builds and answers, in every storage mode.

A parameter table often has one row: a single switch, a single rate keyed by
the one product it applies to. Keyed by text, it was refused at build time
under the default storage with "null or unencodable key value in column
'item' at source row 0 while building table" -- while the same table with a
second row, or built with ``storage_mode="hash"``, was fine. Polars holds a
one-row column as a scalar, and the array store's key encoder had no arm for
the form a scalar hands its text key back in.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table


@pytest.mark.parametrize("storage_mode", ["auto", "array", "hash"])
def test_a_one_row_text_keyed_table_builds_and_answers(storage_mode: str) -> None:
    table = Table(
        name=f"one_row_text_key_{storage_mode}",
        source=pl.DataFrame({"item": ["zeroize_reserves"], "flag": [0.0]}),
        dimensions={"item": "item"},
        value="flag",
        storage_mode=storage_mode,
    )
    af = ActuarialFrame({"policy": [1, 2]})
    af.flag = table.lookup(item="zeroize_reserves")

    assert af.collect()["flag"].to_list() == [0.0, 0.0]


def test_a_one_row_table_keyed_by_text_and_age_builds_and_answers() -> None:
    table = Table(
        name="one_row_text_and_age",
        source=pl.DataFrame({"product": ["annuity"], "age": [40], "rate": [0.002]}),
        dimensions={"product": "product", "age": "age"},
        value="rate",
    )
    af = ActuarialFrame({"plan": ["annuity"], "age": [40]})
    af.rate = table.lookup(product=af.plan, age=af.age)

    assert af.collect()["rate"].to_list() == [0.002]
