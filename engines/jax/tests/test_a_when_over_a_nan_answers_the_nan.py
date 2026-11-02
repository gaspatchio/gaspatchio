# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A ``when`` over a NaN comparison answers the NaN where its answer is a double.

Section 11.1.28: a condition a NaN left without a truth value answers NaN, and
a null where the answer holds no NaN. The double case was refused by name on
this engine while a NaN selected into a double answer could move the products
that answer feeds; with every product rounded before the sum that reads it,
the NaN is the answer, and what reads it -- a product, a sum -- is the
reference producer's to the bit.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

_BOOK = {
    "x": [0.5, math.nan, 2.0, 1.5],
    "y": [1.1, 2.2, 3.3, 4.4],
    "w": [0.3, 0.7, 0.011, 5.0],
}


def _same(left: list[float], right: list[float]) -> bool:
    return len(left) == len(right) and all(
        (math.isnan(a) and math.isnan(b))
        or (a == b and math.copysign(1, a) == math.copysign(1, b))
        for a, b in zip(left, right, strict=True)
    )


def _flat(frame: pl.DataFrame, column: str) -> list[float]:
    values = frame[column].to_list()
    return [x for run in values for x in run] if isinstance(values[0], list) else values


@pytest.mark.parametrize("shape", ["per-policy", "per-period"])
def test_the_nan_is_the_answer_and_what_reads_it_agrees(shape: str) -> None:
    periods = shape == "per-period"
    book = pl.DataFrame(
        {name: [[v, v * 0.5, v] for v in values] for name, values in _BOOK.items()}
        if periods
        else _BOOK
    )
    af = ActuarialFrame(book)
    af.chosen = when(af.x > 1.0).then(af.y * 1.1).otherwise(af.y + 0.25)
    af.read = af.w + af.chosen * 0.3
    producer, engine = af.collect(), af.collect(engine="jax")
    for column in ("chosen", "read"):
        assert _same(_flat(engine, column), _flat(producer, column)), column
    chosen = _flat(engine, "chosen")
    assert math.isnan(chosen[3 if periods else 1])
    assert sum(math.isnan(v) for v in chosen) == (3 if periods else 1)
