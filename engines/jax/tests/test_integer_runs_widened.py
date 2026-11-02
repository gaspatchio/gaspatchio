# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A whole-number run a Float64 period operation reads arrives widened on the record.

The producer shifted an integer run under the default ``0.0`` fill in
doubles while its record named the column ``list[i64]``, so this engine,
computing the shift in doubles too, refused the document as a type it had
widened. The producer now writes the widening (``to_float``, as it does for
``accumulate``), and the two engines answer the same doubles.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_LINES: list[tuple[str, Callable[[Any], Any], list[list[float]]]] = [
    (
        "k.previous_period()",
        lambda af: af.k.projection.previous_period(),
        [[0.0, 3.0, 4.0], [0.0, 10.0, 11.0]],
    ),
    (
        "k.next_period()",
        lambda af: af.k.projection.next_period(),
        [[4.0, 5.0, 0.0], [11.0, 12.0, 0.0]],
    ),
    (
        "k.at_period(-1)",
        lambda af: af.k.projection.at_period(-1),
        [[0.0, 3.0, 4.0], [0.0, 10.0, 11.0]],
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "expected"), _LINES, ids=[x[0] for x in _LINES]
)
def test_a_shifted_integer_run_answers_one_double_on_both_engines(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    expected: list[list[float]],
) -> None:
    book = pl.DataFrame({"pid": [1, 2], "n": [3, 10]})
    af = ActuarialFrame(book).projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.k = af.n + af.month
    af.out = line(af)
    produced = af.collect()

    document = json.loads(GraphExporter(af).export(profile="executable"))
    result = engine_named("jax").run(document, book, FrameSink())

    assert produced["out"].to_list() == expected
    assert result.columns["out"].to_list() == expected
