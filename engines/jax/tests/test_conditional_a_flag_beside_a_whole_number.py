# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A flag beside a whole number in a conditional is a double, here as on Polars.

This engine promoted a flag beside a whole number to the whole number, so
``when(x > 2).then(True).otherwise(n)`` answered ``i64`` per policy, and per
period it answered ``i64`` too and was settled to the record's ``f64`` only
at the end -- so the pair inside arithmetic computed in integers: ``% 0``
refused as an integer division by zero where the producer answered NaN.
Section 11.1.28 now answers the pair as a double, the flag read as its 0.0 or
1.0 indicator as 11.1.25 reads it beside a number, on both engines and both
routes. A whole number past 2**53 carried to a double refuses here by name,
as it does under ``flag + n``.
"""

from __future__ import annotations

import json
import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter


def _book(n: list[int]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "pid": pl.Series([1, 2], dtype=pl.Int64),
            "x": [1.5, 3.5],
            "n": pl.Series(n, dtype=pl.Int64),
            "b": [True, False],
            "m": pl.Series([[0, 1], [0, 1]], dtype=pl.List(pl.Int64)),
            "k": pl.Series([[10, 11], [20, 21]], dtype=pl.List(pl.Int64)),
        }
    )


def _both(book: pl.DataFrame, line: object) -> tuple[pl.Series, str, pl.Series]:
    """Return the producer's column, the record's type, and this engine's column."""
    af = ActuarialFrame(book)
    af.r = line(af)  # type: ignore[operator]
    produced = af.collect()["r"]
    document = json.loads(GraphExporter(af).export(profile="executable"))
    recorded = next(n["dtype"] for n in document["nodes"] if n["column"] == "r")
    ran = engine_named("jax").run(document, book, FrameSink()).columns["r"]
    return produced, recorded, ran


@pytest.mark.parametrize(
    ("line", "dtype", "hand", "record"),
    [
        (
            lambda af: when(af.x > 2).then(True).otherwise(af.n),  # noqa: FBT003
            pl.Float64(),
            [7.0, 1.0],
            "f64",
        ),
        (
            lambda af: when(af.x > 2).then(af.b).otherwise(5),
            pl.Float64(),
            [5.0, 0.0],
            "f64",
        ),
        (
            lambda af: when(af.m > 0).then(af.b).otherwise(af.k),
            pl.List(pl.Float64),
            [[10.0, 1.0], [20.0, 0.0]],
            "list[f64]",
        ),
    ],
    ids=["a flag literal per policy", "a flag column per policy", "per period"],
)
def test_a_flag_beside_a_whole_number_answers_a_double_on_both_engines(
    line: object, dtype: pl.DataType, hand: list[object], record: str
) -> None:
    produced, recorded, ran = _both(_book([7, -3]), line)
    assert recorded == record
    assert produced.dtype == dtype
    assert ran.dtype == dtype
    assert produced.to_list() == hand
    assert ran.to_list() == hand


@pytest.mark.parametrize(
    "line",
    [
        lambda af: when(af.x > 2).then(True).otherwise(af.n) % 0,  # noqa: FBT003
        lambda af: when(af.m > 0).then(True).otherwise(af.k) % 0,  # noqa: FBT003
    ],
    ids=["per policy", "per period"],
)
def test_the_pair_computes_as_a_double_inside_arithmetic(line: object) -> None:
    # Float mod by zero is NaN (11.1.25); an integer one is a null this engine refuses.
    produced, _, ran = _both(_book([7, -3]), line)
    flat = (
        pl.Series(ran.to_list()).explode() if ran.dtype == pl.List(pl.Float64) else ran
    )
    assert produced.dtype == ran.dtype
    assert all(math.isnan(value) for value in flat.to_list())


def test_a_whole_number_past_2_53_beside_a_flag_is_refused_as_in_arithmetic() -> None:
    book = _book([2**53 + 1, 3])
    for line in (
        lambda af: af.b + af.n,
        lambda af: when(af.x > 2).then(af.b).otherwise(af.n),
    ):
        with pytest.raises(EngineRefusal) as refused:
            _both(book, line)
        assert "mixed.2p53" in refused.value.report.render()
