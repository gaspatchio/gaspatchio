# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A comparison compared answers here as on the producer.

``(af.k > 2) == 1`` answered Python's own ``False`` where the line was
written, so no record of it reached this engine, and per period the
producer failed in Polars' words where this engine already read the inner
comparison as its 0.0/1.0 indicator. Each order now records one comparison
over the other, and this engine answers it as the producer does.
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

_COMPARISONS: dict[str, Callable[[object, object], object]] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "ge": operator.ge,
}
_BOOK = pl.DataFrame({"k": [5, 1], "x": [2.5, -1.0], "b": [True, False]})


@pytest.mark.parametrize("op", sorted(_COMPARISONS))
@pytest.mark.parametrize("periods", [False, True], ids=["per-policy", "per-period"])
def test_a_comparison_compared_answers_as_the_producer_does(
    op: str, *, periods: bool
) -> None:
    af = ActuarialFrame(_BOOK)
    if periods:
        af = af.projection.set(
            start_date=dt.date(2025, 1, 1), n_periods=2, frequency="monthly"
        )
    test = (af.month >= 1) if periods else (af.k > 2)
    compare = _COMPARISONS[op]
    af.literal = compare(test, 1)
    af.flag = compare(af.b, test)
    af.column = compare(test, af.x)
    af.two = compare(test, af.k > 4)

    reference, engine = af.collect(), af.collect(engine="jax")

    # The test's own indicator, compared with 1 by hand.
    indicator = [0.0, 1.0, 1.0] if periods else [1.0, 0.0]
    hand = [float(compare(value, 1)) for value in indicator]
    assert engine["literal"].to_list() == ([hand, hand] if periods else hand)
    for name in ("literal", "flag", "column", "two"):
        assert_series_equal(engine[name], reference[name], check_exact=True)


def test_hand_values_per_policy_and_per_period() -> None:
    af = ActuarialFrame(_BOOK).projection.set(
        start_date=dt.date(2025, 1, 1), n_periods=1, frequency="monthly"
    )
    af.a = (af.k > 2) == 1
    af.b2 = (af.month >= 1) != (af.b == True)  # noqa: E712 - the flag compared
    af.c = 0.5 < (af.k > 2)  # noqa: SIM300 - the literal first is the order tested

    out = af.collect(engine="jax")

    assert out["a"].to_list() == [1.0, 0.0]
    assert out["b2"].to_list() == [[1.0, 0.0], [0.0, 1.0]]
    assert out["c"].to_list() == [1.0, 0.0]
