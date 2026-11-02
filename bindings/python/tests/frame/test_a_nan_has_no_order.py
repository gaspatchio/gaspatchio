# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A NaN has no place in an order, one answer per operation on both shapes.

0/0 is NaN (11.1.25): an in-the-money ratio over a nought guarantee is one.
Polars answered each operation over it by a rule of its own and a different
one by shape -- ``list.min`` skipped it, a per-policy ``NaN > 1.0`` was true
(Polars orders NaN above every number) while the per-period one was false --
so one line stored two answers for one value. Sections 11.1.16-17, 11.1.26,
11.1.27 and 11.1.28 now give one: a fold over a NaN period is NaN, a
comparison with a NaN operand is a NaN indicator, a ``when`` over it is NaN
(null where the answer holds no NaN), ``&``/``|``/``~`` over it have no truth
value, and ``cut`` places it in no band. ±infinity is ordered as IEEE orders it.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

NAN = float("nan")


def _same(got: object, want: object) -> bool:
    if isinstance(want, list):
        return (
            isinstance(got, list)
            and len(got) == len(want)
            and all(_same(g, w) for g, w in zip(got, want, strict=True))
        )
    if isinstance(want, float) and math.isnan(want):
        return isinstance(got, float) and math.isnan(got)
    return got == want


def _book() -> pl.DataFrame:
    # The NaN first, in the middle, last and alone; a finite control; and the
    # two infinities, each made the way a model makes one -- by dividing.
    return pl.DataFrame(
        {
            "a": [
                [0.0, 3.0, 4.0],
                [3.0, 0.0, 4.0],
                [3.0, 4.0, 0.0],
                [0.0],
                [1.0, 3.0, 4.0],
                [1.0, 3.0, 4.0],
            ],
            "b": [
                [0.0, 2.0, 2.0],
                [2.0, 0.0, 2.0],
                [2.0, 2.0, 0.0],
                [0.0],
                [2.0, 2.0, 2.0],
                [0.0, 2.0, 2.0],
            ],
            "a0": [0.0, 0.0, 0.0, None, 3.0, 1.0],
            "b0": [0.0, 0.0, 0.0, 1.0, 2.0, -0.0],
            "label": ["p1", "p2", "p3", "p4", "p5", "p6"],
            "units": [1, 2, 3, 4, 5, 6],
        }
    )


def _run(engine: str, **lines: object) -> dict[str, list[object]]:
    af = ActuarialFrame(_book())
    af.r = af.a / af.b
    af.r0 = af.a0 / af.b0
    for name, line in lines.items():
        af[name] = line(af)  # type: ignore[operator]
    out = af.collect(engine=engine)
    return {name: out.get_column(name).to_list() for name in lines}


ENGINES = ["in-memory", "streaming"]


@pytest.mark.parametrize("engine", ENGINES)
def test_a_fold_over_a_nan_period_is_nan_wherever_it_stands(engine: str) -> None:
    got = _run(engine, lo=lambda af: af.r.list.min(), hi=lambda af: af.r.list.max())
    assert _same(got["lo"], [NAN, NAN, NAN, NAN, 0.5, 1.5])
    assert _same(got["hi"], [NAN, NAN, NAN, NAN, 2.0, math.inf])


@pytest.mark.parametrize("engine", ENGINES)
def test_a_comparison_with_a_nan_is_a_nan_indicator_on_both_shapes(engine: str) -> None:
    got = _run(
        engine,
        gt0=lambda af: af.r0 > 1.0,
        eq0=lambda af: af.r0 == af.r0,
        gt=lambda af: af.r > 1.0,
        eq=lambda af: af.r == af.r,
    )
    assert _same(got["gt0"], [NAN, NAN, NAN, None, 1.0, 0.0])
    assert _same(got["eq0"], [NAN, NAN, NAN, None, 1.0, 1.0])
    assert _same(
        got["gt"],
        [
            [NAN, 1.0, 1.0],
            [1.0, NAN, 1.0],
            [1.0, 1.0, NAN],
            [NAN],
            [0.0, 1.0, 1.0],
            [1.0, 1.0, 1.0],
        ],
    )
    assert _same(got["eq"][0], [NAN, 1.0, 1.0])


@pytest.mark.parametrize("engine", ENGINES)
def test_infinity_is_ordered_as_ieee_orders_it(engine: str) -> None:
    got = _run(
        engine,
        big=lambda af: af.r0 > 1e300,
        neg=lambda af: af.r0 < -1e300,
        run=lambda af: af.r >= 1e300,
    )
    # Policy 6 divides 1 by -0.0: minus infinity.
    assert got["big"][5] == 0.0
    assert got["neg"][5] == 1.0
    assert got["run"][5] == [1.0, 0.0, 0.0]


@pytest.mark.parametrize("engine", ENGINES)
def test_a_when_over_a_nan_comparison_answers_nan_or_null(engine: str) -> None:
    got = _run(
        engine,
        num0=lambda af: when(af.r0 > 1.0).then(10.0).otherwise(20.0),
        num=lambda af: when(af.r > 1.0).then(10.0).otherwise(20.0),
        text0=lambda af: when(af.r0 > 1.0).then(af.label).otherwise(af.label),
        whole=lambda af: when(af.r > 1.0).then(af.units).otherwise(0),
        over_a_run=lambda af: when(af.r0 > 1.0).then(af.r).otherwise(0.0),
    )
    assert _same(got["num0"], [NAN, NAN, NAN, 20.0, 10.0, 20.0])
    assert _same(got["num"][1], [10.0, NAN, 10.0])
    assert got["text0"] == [None, None, None, "p4", "p5", "p6"]
    assert got["whole"][0] == [None, 1, 1]
    assert _same(got["over_a_run"][0], [NAN, NAN, NAN])


@pytest.mark.parametrize("engine", ENGINES)
def test_a_test_a_nan_left_unknown_leaves_its_combination_unknown(engine: str) -> None:
    got = _run(
        engine,
        both0=lambda af: when((af.r0 > 0.5) & (af.r0 < 10.0)).then(1.0).otherwise(0.0),
        both=lambda af: when((af.r > 0.5) & (af.r < 10.0)).then(1.0).otherwise(0.0),
        stored0=lambda af: (af.r0 > 0.5) & (af.r0 < 10.0),
        negated0=lambda af: ~(af.r0 > 0.5),
        compared0=lambda af: (af.r0 > 1.0) == 1,
        weighed0=lambda af: (af.r0 > 1.0) * 5.0,
    )
    # false AND unknown is unknown: per period NaN * 0.0 is NaN. Per policy
    # the result is a Boolean, null there (11.1.27), and a null condition
    # selects the otherwise, as it does when the line is stored first.
    assert _same(got["both0"], [0.0, 0.0, 0.0, 0.0, 1.0, 0.0])
    assert _same(got["both"][2], [1.0, 1.0, NAN])
    # A Boolean holds no NaN: the stored truth value is null there.
    assert got["stored0"][:3] == [None, None, None]
    assert got["negated0"][:3] == [None, None, None]
    assert _same(got["compared0"], [NAN, NAN, NAN, None, 1.0, 0.0])
    assert _same(got["weighed0"], [NAN, NAN, NAN, None, 5.0, 0.0])


@pytest.mark.parametrize("engine", ENGINES)
def test_a_nan_takes_no_band(engine: str) -> None:
    got = _run(
        engine,
        band0=lambda af: af.r0.cut([1.0], labels=["low", "high"]) == "low",
        band=lambda af: (
            af.r.cut([1.75], labels=["low", "high"], left_closed=True) == "low"
        ),
    )
    assert got["band0"][:3] == [None, None, None]
    assert got["band"][0] == [None, 1.0, 0.0]


def test_a_guarded_quotient_never_reaches_the_unknown() -> None:
    """The condition tests the guarantee, a number, so the 0/0 is never compared."""
    got = _run(
        "in-memory",
        guarded=lambda af: when(af.b0 > 0).then(af.a0 / af.b0).otherwise(0.0),
    )
    assert got["guarded"] == [0.0, 0.0, 0.0, None, 1.5, 0.0]
