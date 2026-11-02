# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-policy `&`, `|` or `~` a NaN left unknown is a null flag, inline too.

Section 11.1.27: a per-policy logical result is a Boolean wherever it is
read, stored or inline -- null where a side had no truth value. A ``when``
over it selects the otherwise there, as the reference producer does (and as
over the same line stored first); an enclosing ``&`` reads it under
three-valued logic, so false AND it is false. This engine answered the
``when`` NaN and an inline ``== True`` or ``* 1.0`` NaN; it carries no null,
so those two now refuse by name. Per period nothing moves: the indicator
stays NaN.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
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


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "flag": [False, True, False, True],
                "off": [False, False, True, True],
                "x": [NAN, NAN, 2.0, 0.5],
                "rates": [[NAN, 2.0]] * 4,
            }
        )
    )


def test_a_when_and_an_enclosing_and_read_the_null() -> None:
    af = _frame()
    af.either = when(af.flag | (af.x > 1.0)).then(10.0).otherwise(20.0)
    af.negated = when(~(af.x > 1.0)).then(10.0).otherwise(20.0)
    af.both = af.off & (af.flag | (af.x > 1.0))
    af.flagged = when(af.off & (af.flag | (af.x > 1.0))).then(1).otherwise(0)
    af.per_period = when(af.flag & (af.rates > 1.0)).then(1.0).otherwise(0.0)
    producer, engine = af.collect(), af.collect(engine="jax")
    for column in ("either", "negated", "both", "flagged", "per_period"):
        assert _same(
            engine.get_column(column).to_list(), producer.get_column(column).to_list()
        ), column
    assert engine.get_column("either").to_list() == [20.0, 20.0, 10.0, 10.0]
    assert engine.get_column("negated").to_list() == [20.0, 20.0, 20.0, 10.0]
    assert engine.get_column("both").to_list() == [False, False, True, True]
    assert _same(engine.get_column("per_period").to_list()[1], [NAN, 1.0])


@pytest.mark.parametrize("line", ["eq", "times", "stored"])
def test_a_read_that_would_carry_the_null_refuses_by_name(line: str) -> None:
    af = _frame()
    test = af.flag & (af.x > 1.0)
    reads = {"eq": test == True, "times": test * 1.0, "stored": test}  # noqa: E712
    af.read = reads[line]
    with pytest.raises(EngineRefusal, match="no truth value"):
        af.collect(engine="jax")
