# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every operator on a value the frame hands back answers, or is refused by name.

An operator a value's class does not define falls through to Python, which
answers ``==`` and ``!=`` by identity -- a Python ``bool`` the frame then
stores as a column -- and refuses the rest in its own words. Four such holes
are closed here. ``^`` is refused in gaspatchio's words on a column, an
expression, a comparison and a mask, naming the comparison that writes
"one or the other, not both". ``+x`` answers ``x``. An unfinished
``when(...).then(...)`` used as a value -- compared, combined, stored, or as
another chain's condition -- is refused in its own words where ``==``
answered ``False``. And a number raised to a lookup's power answers, where
it recursed until the interpreter gave up.
"""

from __future__ import annotations

import datetime as dt
import operator
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.assumptions import Table

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame({"k": [5, 1], "x": [2.5, -1.0], "b": [True, False]})
_TABLE = Table(
    name="operator_sweep_rates",
    source=pl.DataFrame({"k": [1, 5], "rate": [0.25, 0.5]}),
    dimensions={"k": "k"},
    value="rate",
)


def _frame(*, periods: bool) -> ActuarialFrame:
    af = ActuarialFrame(_BOOK)
    if periods:
        af = af.projection.set(
            start_date=dt.date(2025, 1, 1), n_periods=1, frequency="monthly"
        )
    return af


_VALUES: dict[str, Callable[[ActuarialFrame], object]] = {
    "a column": lambda af: af.k,
    "a stored flag": lambda af: af.b,
    "an expression": lambda af: af.x * 2,
    "a comparison": lambda af: af.k > 2,
    "a mask": lambda af: (af.k > 2) & (af.x > 0),
    "a finished when": lambda af: when(af.k > 2).then(1.0).otherwise(0.0),
}
_OTHERS: dict[str, Callable[[ActuarialFrame], object]] = {
    "1": lambda _: 1,
    "True": lambda _: True,
    "a flag": lambda af: af.b,
    "a comparison": lambda af: af.x > 0,
}


@pytest.mark.parametrize("other", sorted(_OTHERS))
@pytest.mark.parametrize("value", sorted(_VALUES))
@pytest.mark.parametrize("periods", [False, True], ids=["per-policy", "per-period"])
def test_an_exclusive_or_is_refused_by_name(
    value: str, other: str, *, periods: bool
) -> None:
    af = _frame(periods=periods)
    left, right = _VALUES[value](af), _OTHERS[other](af)

    for written in (lambda: left ^ right, lambda: right ^ left):
        with pytest.raises(TypeError, match=r"\^ is not an operation") as refused:
            written()
        assert "!=" in str(refused.value)


@pytest.mark.parametrize("value", sorted(_VALUES))
@pytest.mark.parametrize("periods", [False, True], ids=["per-policy", "per-period"])
def test_a_sign_kept_is_the_value_itself(value: str, *, periods: bool) -> None:
    af = _frame(periods=periods)
    af.plain = _VALUES[value](af)
    af.signed = +_VALUES[value](af)

    out = af.collect()

    assert out["signed"].dtype == out["plain"].dtype
    assert out["signed"].to_list() == out["plain"].to_list()


_UNFINISHED_USES: dict[str, Callable[[object, ActuarialFrame], object]] = {
    "== 1.0": lambda chain, _: chain == 1.0,
    "1.0 == chain": lambda chain, _: 1.0 == chain,  # noqa: SIM300 - the order tested
    "!= a column": lambda chain, af: chain != af.x,
    "< 1": lambda chain, _: chain < 1,
    "+ 1": lambda chain, _: chain + 1,
    "a column - chain": lambda chain, af: af.x - chain,
    "& a comparison": lambda chain, af: chain & (af.x > 0),
    "a lookup * chain": lambda chain, af: _TABLE.lookup(k=af.k) * chain,
    "-chain": lambda chain, _: -chain,
    "abs(chain)": lambda chain, _: abs(chain),
    "~chain": lambda chain, _: ~chain,
    "bool(chain)": lambda chain, _: bool(chain),
    "as a condition": lambda chain, _: when(chain).then(1.0).otherwise(0.0),
}


@pytest.mark.parametrize("use", sorted(_UNFINISHED_USES))
@pytest.mark.parametrize("periods", [False, True], ids=["per-policy", "per-period"])
def test_an_unfinished_chain_used_as_a_value_is_refused(
    use: str, *, periods: bool
) -> None:
    af = _frame(periods=periods)
    chain = when(af.k > 2).then(1.0)

    with pytest.raises(TypeError, match=r"requires \.otherwise\(\)"):
        _UNFINISHED_USES[use](chain, af)


def test_an_unfinished_chain_is_not_stored() -> None:
    af = ActuarialFrame(_BOOK)

    with pytest.raises(TypeError, match=r"requires \.otherwise\(\)"):
        af.r = when(af.k > 2).then(1.0)


@pytest.mark.parametrize(
    ("base", "hand"),
    [
        (1.05, [1.05**0.5, 1.05**0.25]),
        (2, [2**0.5, 2**0.25]),
        (1, [1.0, 1.0]),
    ],
)
def test_a_number_raised_to_a_lookups_power(base: float, hand: list[float]) -> None:
    af = ActuarialFrame(_BOOK)
    af.r = base ** _TABLE.lookup(k=af.k)

    assert af.collect()["r"].to_list() == hand


@pytest.mark.parametrize(
    ("write", "hand"),
    [
        (operator.sub, [0.5, 0.75]),
        (operator.truediv, [2.0, 4.0]),
        (operator.floordiv, [2.0, 4.0]),
        (operator.mod, [0.0, 0.0]),
    ],
)
def test_a_number_beside_a_lookup_on_its_right(
    write: Callable[[object, object], object], hand: list[float]
) -> None:
    af = ActuarialFrame(_BOOK)
    af.r = write(1, _TABLE.lookup(k=af.k))

    assert af.collect()["r"].to_list() == hand
