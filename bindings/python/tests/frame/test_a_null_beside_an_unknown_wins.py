# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A null beside a test a NaN left unknown wins, in ``&`` and ``|`` per policy.

A missing smoker flag beside an in-the-money ratio over a nought guarantee:
``flag | (ratio > 1)`` with the flag null and the ratio 0/0. Section 11.1.26:
"A null on either side is still a null, and wins over a NaN on the other";
11.1.27: "false AND unknown is unknown, a null beside it winning". The
combination is a null there -- never the true Polars' own ``|`` gives by
ordering NaN above every number, nor the false its ``&`` gives to ``NaN < 1``.
A null beside a side with a truth value is still three-valued logic: false
AND null is false, true OR null is true, also where the null is itself a
combination a null won.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

NAN = float("nan")
ENGINES = ["in-memory", "streaming"]


def _same(got: list[object], want: list[object]) -> bool:
    def one(g: object, w: object) -> bool:
        if isinstance(w, float) and math.isnan(w):
            return isinstance(g, float) and math.isnan(g)
        return g == w

    return len(got) == len(want) and all(
        one(g, w) for g, w in zip(got, want, strict=True)
    )


def _run(engine: str, **lines: object) -> dict[str, list[object]]:
    # x / g: 0/0 is NaN (rows 1, 2, 6), 2.0, 0.5, and a null x (row 5).
    book = pl.DataFrame(
        {
            "x": [0.0, 0.0, 2.0, 0.5, None, 0.0],
            "g": [0.0, 0.0, 1.0, 1.0, 1.0, 0.0],
            "flag": [False, True, False, True, False, None],
        },
        schema={"x": pl.Float64, "g": pl.Float64, "flag": pl.Boolean},
    )
    af = ActuarialFrame(book)
    af.ratio = af.x / af.g
    for name, line in lines.items():
        af[name] = line(af)  # type: ignore[operator]
    out = af.collect(engine=engine)
    return {name: out.get_column(name).to_list() for name in lines}


@pytest.mark.parametrize("engine", ENGINES)
def test_a_null_beside_an_unknown_is_a_null_in_either_order(engine: str) -> None:
    got = _run(
        engine,
        or_gt=lambda af: af.flag | (af.ratio > 1.0),
        gt_or=lambda af: (af.ratio > 1.0) | af.flag,
        and_lt=lambda af: af.flag & (af.ratio < 1.0),
        lt_and=lambda af: (af.ratio < 1.0) & af.flag,
        or_ne=lambda af: af.flag | (af.ratio != 2.0),
        ne_or=lambda af: (af.ratio != 2.0) | af.flag,
    )
    # Row 6: the flag is null and the ratio NaN -- a null, on every line.
    assert got["or_gt"] == [None, None, True, True, None, None]
    assert got["gt_or"] == [None, None, True, True, None, None]
    assert got["and_lt"] == [None, None, False, True, False, None]
    assert got["lt_and"] == [None, None, False, True, False, None]
    assert got["or_ne"] == [None, None, False, True, None, None]
    assert got["ne_or"] == [None, None, False, True, None, None]


@pytest.mark.parametrize("engine", ENGINES)
def test_a_condition_a_null_won_selects_otherwise(engine: str) -> None:
    got = _run(
        engine,
        num=lambda af: when(af.flag | (af.ratio > 1.0)).then(1.0).otherwise(0.0),
        flipped=lambda af: when((af.ratio > 1.0) | af.flag).then(1.0).otherwise(0.0),
        text=lambda af: when(af.flag | (af.ratio != 2.0)).then("a").otherwise("b"),
        stored=lambda af: af.flag | (af.ratio > 1.0),
    )
    # Rows 1-2 and 6: the condition is a null Boolean (11.1.27), and a null
    # condition selects otherwise.
    assert _same(got["num"], [0.0, 0.0, 1.0, 1.0, 0.0, 0.0])
    assert _same(got["flipped"], [0.0, 0.0, 1.0, 1.0, 0.0, 0.0])
    assert got["text"] == ["b", "b", "b", "a", "b", "b"]
    assert got["stored"][5] is None


@pytest.mark.parametrize("engine", ENGINES)
def test_a_combination_a_null_won_is_read_as_a_null_by_what_encloses_it(
    engine: str,
) -> None:
    got = _run(
        engine,
        negated=lambda af: ~(af.flag | (af.ratio > 1.0)),
        and_false=lambda af: (af.flag | (af.ratio > 1.0)) & af.x.is_null(),
        false_and=lambda af: af.x.is_null() & (af.flag | (af.ratio > 1.0)),
        or_true=lambda af: (af.flag | (af.ratio > 1.0)) | af.x.is_not_null(),
        and_unknown=lambda af: (af.flag | (af.ratio > 1.0)) & (af.ratio < 3.0),
    )
    # Row 6: the inner combination is a null, not an unknown, so false AND
    # it is false and true OR it is true; beside an unknown it stays a null.
    assert got["negated"][5] is None
    assert got["and_false"][5] is False
    assert got["false_and"][5] is False
    assert got["or_true"][5] is True
    assert got["and_unknown"][5] is None
    # Row 1: the inner combination had no truth value, so it is a null
    # Boolean too, read as one: false AND it is false.
    assert got["and_false"][0] is False


@pytest.mark.parametrize("engine", ENGINES)
def test_a_logical_result_is_the_same_null_inline_as_stored(engine: str) -> None:
    """A value does not change by being named (11.1.27).

    ``flag & (ratio > 1.0)`` with the ratio 0/0 is a null Boolean whether it
    is stored and read or read where it is written, by every reader.
    """
    lines = {
        "is_in": lambda t: t.is_in([True]),
        "is_null": lambda t: t.is_null(),
        "fill_null": lambda t: t.fill_null(value=False),
        "eq": lambda t: t == True,  # noqa: E712
        "times": lambda t: t * 1.0,
        "when": lambda t: when(t).then(1.0).otherwise(0.0),
    }
    inline = _run(
        engine,
        **{
            name: (lambda af, read=read: read(af.flag & (af.ratio > 1.0)))
            for name, read in lines.items()
        },
    )
    stored = _run(
        engine,
        test=lambda af: af.flag & (af.ratio > 1.0),
        **{
            f"{name}_s": (lambda af, read=read: read(af.test))
            for name, read in lines.items()
        },
    )
    for name in lines:
        assert _same(inline[name], stored[f"{name}_s"]), name
    assert inline["is_null"][:2] == [True, True]
    assert inline["fill_null"][:2] == [False, False]
    assert inline["eq"][:2] == [None, None]
    assert inline["times"][:2] == [None, None]
    assert _same(inline["when"], [0.0] * 6)
