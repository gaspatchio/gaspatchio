# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A column a whole-number literal types is the same i64 on both engines.

The record names every whole number ``i64`` and this engine computes in it.
The producer stored ``af.c = 5`` and ``when(...).then(70000).otherwise(0)``
as ``Int32``, so ``* 70000`` answered 605,032,704 there and 4,900,000,000
here, from one document. These pin that the two engines now agree, at the
hand values.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable


def _lines(af: Any) -> None:  # noqa: ANN401 -- a frame being written
    af.c = 5
    af.r = af.c * 70000 * 70000


_FORMS: list[tuple[str, Callable[[Any], None], list[Any]]] = [
    ("c = 5; c * 70000 * 70000", _lines, [24_500_000_000, 24_500_000_000]),
    (
        "when(x > 2).then(70000).otherwise(0) * 70000",
        lambda af: setattr(af, "r", when(af.x > 2).then(70000).otherwise(0) * 70000),
        [0, 4_900_000_000],
    ),
]


@pytest.mark.parametrize(
    ("written", "lines", "expected"), _FORMS, ids=[f[0] for f in _FORMS]
)
def test_a_literal_typed_column_answers_one_i64_on_both_engines(
    written: str,  # noqa: ARG001 -- the id
    lines: Callable[[Any], None],
    expected: list[int],
) -> None:
    book = pl.DataFrame({"pid": [1, 2], "x": [1.5, 3.5]})
    af = ActuarialFrame(book)
    lines(af)
    produced = af.collect()

    document = json.loads(GraphExporter(af).export(profile="executable"))
    result = engine_named("jax").run(document, book, FrameSink())

    assert produced["r"].to_list() == expected
    assert result.columns["r"].to_list() == expected
    assert produced.schema["r"] == result.columns["r"].dtype == pl.Int64


def test_a_per_period_literal_typed_column_answers_one_i64_on_both_engines() -> None:
    """Hand values: 70,000 * 70,000 = 4,900,000,000 after month 0."""
    book = pl.DataFrame({"pid": [1, 2], "x": [1.5, 3.5]})
    af = ActuarialFrame(book).projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.r = when(af.month > 0).then(70000).otherwise(0) * 70000
    produced = af.collect()

    document = json.loads(GraphExporter(af).export(profile="executable"))
    result = engine_named("jax").run(document, book, FrameSink())

    expected = [[0, 4_900_000_000, 4_900_000_000]] * 2
    assert produced["r"].to_list() == expected
    assert result.columns["r"].to_list() == expected
    assert produced.schema["r"] == result.columns["r"].dtype == pl.List(pl.Int64)
