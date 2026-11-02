# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A null test over a per-period NaN indicator answers, as the producer does.

Per period, a test a NaN left unknown -- ``flag & (rate > 1.0)`` with a 0/0
rate in one period -- is its NaN indicator (11.1.26-27), and a NaN is not a
null (11.1.13): ``is_null`` over it is false in every period, and
``fill_null`` keeps the NaN. This engine refused both lines by name
(``comparison.unknown``) though nothing in them needs a null. Per policy the
same lines still refuse: the stored unknown there is a null, which this
engine does not carry.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines.report import EngineRefusal

NAN = math.nan


def _same(left: object, right: object) -> bool:
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, float) and isinstance(right, float):
        return (math.isnan(left) and math.isnan(right)) or left == right
    return left == right


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "flag": [False, True, True],
            "x": [NAN, NAN, 2.0],
            "rates": [[NAN, 2.0, 0.5], [NAN, 2.0, 0.5], [1.5, NAN, 0.5]],
        }
    )


def test_is_null_and_fill_null_over_a_per_period_nan_indicator_answer() -> None:
    af = ActuarialFrame(_book())
    af.missing = (af.flag & (af.rates > 1.0)).is_null()
    af.filled = (af.flag & (af.rates > 1.0)).fill_null(0.0)
    producer, engine = af.collect(), af.collect(engine="jax")
    for column in ("missing", "filled"):
        assert _same(
            engine.get_column(column).to_list(), producer.get_column(column).to_list()
        ), column
    assert engine.get_column("missing").to_list() == [[False] * 3] * 3
    assert _same(
        engine.get_column("filled").to_list(),
        [[NAN, 0.0, 0.0], [NAN, 1.0, 0.0], [1.0, NAN, 0.0]],
    )


@pytest.mark.parametrize("line", ["is_null", "fill_null"])
def test_the_per_policy_unknown_still_refuses_by_name(line: str) -> None:
    af = ActuarialFrame(_book())
    test = af.flag & (af.x > 1.0)
    af.read = test.is_null() if line == "is_null" else test.fill_null(value=False)
    with pytest.raises(EngineRefusal, match="no truth value"):
        af.collect(engine="jax")
