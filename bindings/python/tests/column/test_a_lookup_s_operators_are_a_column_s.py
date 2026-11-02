# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-policy table lookup answers every operator as the column it would be.

A lookup read from a frame is a bound ``ProxyAwareExpr``, and per period its
operators were already the frame's. Per policy it kept Polars' own: ``lookup
& 1`` failed in Polars' words (``bitand operation not supported for dtype
f64``) where a column refuses it by name, ``lookup ** True`` and ``True **
lookup`` failed in Polars' words where a column answers them, ``lookup ^ 1``
was an engine fragment refused at assignment, and the expression's own
quotient by a literal, read in plain Polars, was Polars' product by the
reciprocal (135.021 / 1000 came back 0.135021, a last bit off the true
quotient a column, the record and the JAX engine answer). Each operator now
goes through the frame's proxy over the same node. A comparison comes back
as a bound expression marked a comparison, still a Polars expression, so
``&`` and ``|`` read it as a test.
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame({"k": [1, 5], "q": [135.021, 0.25]})
_TABLE = Table(
    name="a_lookup_s_operators",
    source=pl.DataFrame({"k": [1, 5], "rate": [135.021, 0.25]}),
    dimensions={"k": "k"},
    value="rate",
)


def _lookup(af: ActuarialFrame) -> ProxyAwareExpr:
    return _TABLE.lookup(k=af.k)


@pytest.mark.parametrize(
    ("line", "make"),
    [
        ("lookup & 1", lambda v: v & 1),
        ("1 & lookup", lambda v: 1 & v),
        ("lookup | 4", lambda v: v | 4),
        ("True | lookup", lambda v: True | v),
    ],
)
def test_a_logical_operator_on_a_number_is_refused_by_name(
    line: str, make: Callable[[object], object]
) -> None:
    del line
    af = ActuarialFrame(_BOOK)

    with pytest.raises(TypeError, match="combines Boolean values"):
        make(_lookup(af))


@pytest.mark.parametrize("make", [lambda v: v ^ 1, lambda v: True ^ v])
def test_an_exclusive_or_is_refused_by_name(make: Callable[[object], object]) -> None:
    af = ActuarialFrame(_BOOK)

    with pytest.raises(TypeError, match=r"\^ is not an operation"):
        make(_lookup(af))


@pytest.mark.parametrize(
    ("make", "hand"),
    [
        (lambda v: v**True, [135.021, 0.25]),
        (lambda v: True**v, [1.0, 1.0]),
        (lambda v: v**False, [1.0, 1.0]),
    ],
)
def test_a_power_of_a_flag_answers_as_a_column_s(
    make: Callable[[object], object], hand: list[float]
) -> None:
    af = ActuarialFrame(_BOOK)
    af.r = make(_lookup(af))
    af.s = make(af.q)

    out = af.collect()

    assert out.schema["r"] == pl.Float64
    assert out["r"].to_list() == hand == out["s"].to_list()


def test_the_expression_s_own_quotient_is_the_true_quotient() -> None:
    af = ActuarialFrame(_BOOK)
    quotient = _lookup(af) / 1000

    raw = _BOOK.select(quotient.alias("r"))["r"].to_list()

    assert isinstance(quotient, ProxyAwareExpr)
    assert raw == [135.021 / 1000, 0.25 / 1000]
    assert raw[0] == 0.13502099999999997  # not Polars' 135.021 * 0.001


@pytest.mark.parametrize("compare", [operator.gt, operator.le, operator.eq])
def test_a_comparison_stays_a_polars_expression_marked_a_test(
    compare: Callable[[object, object], object],
) -> None:
    af = ActuarialFrame(_BOOK)
    test = compare(_lookup(af), 1.0)

    assert isinstance(test, ProxyAwareExpr)
    assert test.kind == "comparison"
    af.both = test & (af.q > 0)
    af.indicator = test * 1.0

    out = af.collect()

    truth = [compare(135.021, 1.0), compare(0.25, 1.0)]
    assert out["both"].to_list() == truth
    assert out["indicator"].to_list() == [float(t) for t in truth]
