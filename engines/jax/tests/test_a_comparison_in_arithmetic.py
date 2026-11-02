# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A comparison in arithmetic answers its indicator here as on the producer.

Section 11.1.25 reads a flag beside a number as its 0.0 or 1.0, and a
comparison stored as a value is that indicator. ``(af.k > 2) * 1.0`` raised
Python's own TypeError where the line was written, so no record of it could
reach this engine; with the comparison on the right it ran here already. Each
order now records one node, and this engine answers it as the producer does.
"""

from __future__ import annotations

import datetime as dt
import operator
from typing import TYPE_CHECKING

import polars as pl
import pytest
from polars.testing import assert_series_equal

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

_OPERATORS: dict[str, Callable[[object, object], object]] = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "div": operator.truediv,
    "pow": operator.pow,
}
_BOOK = pl.DataFrame({"k": [5, 1], "x": [2.5, -4.0]})


@pytest.mark.parametrize("op", sorted(_OPERATORS))
@pytest.mark.parametrize(
    "first", [True, False], ids=["comparison-first", "other-first"]
)
def test_a_per_policy_comparison_answers_as_the_producer_does(
    op: str, *, first: bool
) -> None:
    af = ActuarialFrame(_BOOK)
    apply = _OPERATORS[op]
    af.r = apply(af.k > 2, 2.0) if first else apply(2.0, af.k > 2)

    reference, engine = af.collect()["r"], af.collect(engine="jax")["r"]

    assert engine.dtype == pl.Float64
    assert_series_equal(engine, reference, check_exact=True)


def test_hand_values_per_policy_and_per_period() -> None:
    af = ActuarialFrame(_BOOK).projection.set(
        start_date=dt.date(2025, 1, 1),
        n_periods=1,
        frequency="monthly",
    )
    af.a = (af.k > 2) * 3.0
    af.b = (af.month >= 1) + (af.month >= 1)
    af.c = 1 - (af.k > 2)

    out = af.collect(engine="jax")

    assert out["a"].to_list() == [3.0, 0.0]
    assert out["b"].to_list() == [[0.0, 2.0], [0.0, 2.0]]
    assert out["c"].to_list() == [0.0, 1.0]
