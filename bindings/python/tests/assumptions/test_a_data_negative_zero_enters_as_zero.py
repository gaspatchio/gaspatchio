# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A negative zero in data is written as zero where the data enters (section 12.3).

Section 12.3 hashes a column of data with a -0.0 written as 0.0, so a
one-cell table holding 0.0 and one holding -0.0 shared one fingerprint and
one graph, yet ``to_text`` answered '0.0' and '-0.0' and ``sign`` 0.0 and
-0.0: two answers under one identity. The zero is now written as 0.0 where
an assumption table or an injected column enters, before it is hashed or
read, so a sign-reading operation sees +0.0 and no published hash moves. A
compiled machine's setting is under the recipe grammar and keeps its sign.
"""

from __future__ import annotations

import datetime
import math

import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.assumptions import Table


def _signs(values: list[float]) -> list[bool]:
    return [math.copysign(1.0, value) < 0 for value in values]


def _one_cell(name: str, rate: float, **options: object) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": [40], "rate": [rate]}),
        dimensions={"age": "age"},
        value="rate",
        **options,  # type: ignore[arg-type]
    )


def _read(table: Table) -> tuple[pl.DataFrame, str]:
    af = ActuarialFrame(pl.DataFrame({"age": [40]}))
    af.r = table.lookup(age=af.age)
    af.txt = af.r.to_text()
    af.s = af.r.sign()
    return af.collect(), af.graph.fingerprint()


def test_a_table_s_negative_zero_reads_as_zero_under_its_one_identity() -> None:
    plus = _one_cell("signed_zero_plus", 0.0)
    minus = _one_cell("signed_zero_minus", -0.0)

    plus_out, plus_graph = _read(plus)
    minus_out, minus_graph = _read(minus)

    assert minus.fingerprint() == plus.fingerprint()
    assert minus_out["txt"].to_list() == ["0.0"] == plus_out["txt"].to_list()
    assert _signs(minus_out["r"].to_list()) == [False]
    assert _signs(minus_out["s"].to_list()) == [False]
    # The graph names its table by name, so only the answers are compared
    # across the two names; the published fingerprint did not move.
    assert plus_graph.startswith("sha256:")
    assert minus_graph.startswith("sha256:")


def test_a_table_extended_with_a_negative_zero_reads_it_as_zero() -> None:
    table = _one_cell("signed_zero_extended", 0.5, storage_mode="hash")
    table.extend(pl.DataFrame({"age": [41], "rate": [-0.0]}))

    af = ActuarialFrame(pl.DataFrame({"age": [41]}))
    af.txt = table.lookup(age=af.age).to_text()

    assert af.collect()["txt"].to_list() == ["0.0"]


@pytest.mark.parametrize(
    "values",
    [
        pl.Series("v", [0.0, -0.0]),
        np.array([0.0, -0.0]),
        pl.Series("v", [0.0, -0.0], dtype=pl.Float32),
    ],
    ids=["series", "array", "float32-series"],
)
def test_an_injected_negative_zero_reads_as_zero_and_stamps_as_before(
    values: object,
) -> None:
    af = ActuarialFrame(pl.DataFrame({"p": [1, 2]}))
    af.v = values
    af.txt = af.v.to_text()
    plus = ActuarialFrame(pl.DataFrame({"p": [1, 2]}))
    plus.v = (
        np.array([0.0, 0.0])
        if isinstance(values, np.ndarray)
        else pl.Series("v", [0.0, 0.0], dtype=values.dtype)  # type: ignore[attr-defined]
    )
    plus.txt = plus.v.to_text()

    out = af.collect()

    assert _signs(out["v"].to_list()) == [False, False]
    assert out["txt"].to_list() == ["0.0", "0.0"]
    assert af.graph.fingerprint() == plus.graph.fingerprint()


def test_a_negative_zero_inside_an_injected_list_reads_as_zero() -> None:
    af = ActuarialFrame(pl.DataFrame({"p": [1, 2]}))
    af = af.with_columns(pl.Series("v", [[-0.0, 1.0], [None, -0.0]]))

    flat = af.collect()["v"].explode().drop_nulls().to_list()

    assert _signs(flat) == [False, False, False]


def test_a_literal_and_a_book_column_keep_their_sign() -> None:
    """Only a table and an injected column are data entering; neither of these is."""
    af = ActuarialFrame(pl.DataFrame({"x": [-0.0]}))
    af.lit = af.x * 0.0 + -0.0
    af.book = af.x.to_text()

    out = af.collect()

    assert out["book"].to_list() == ["-0.0"]


def _floored(floor: float) -> tuple[str, list[float]]:
    book = pl.DataFrame(
        {"policy_id": ["B"], "av_init": [-5.0], "fund_return": [[0.01, 0.01]]}
    )
    af = ActuarialFrame(book)
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=2, frequency="monthly"
    )
    states = af.projection.rollforward(states={"av": af["av_init"]})
    states["av"].grow(af["fund_return"], label="fund_return").floor(value=floor)
    af.av = compile_rollforward(states).expr_for("av")
    return af.graph.fingerprint(), af.collect()["av"].to_list()[0]


def test_a_compiled_machine_s_negative_zero_setting_keeps_its_own_identity() -> None:
    plus_graph, plus_av = _floored(0.0)
    minus_graph, minus_av = _floored(-0.0)

    assert minus_graph != plus_graph
    assert _signs(plus_av) == [False] * len(plus_av)
    assert _signs(minus_av) == [True] * len(minus_av)
