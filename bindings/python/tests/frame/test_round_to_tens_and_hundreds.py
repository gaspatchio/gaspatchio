# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``round`` with a negative ``decimals`` rounds to tens, hundreds and coarser.

Section 11.1.8 defines ``round(decimals=-n)`` as rounding to a multiple of
``10**n``, as a spreadsheet's ``ROUND(x, -n)`` does, under both tie rules. A
double is read as its fifteen significant figures and moved to the nearest
multiple; a whole number is moved exactly in whole numbers, and an answer no
``i64`` holds is refused by name. The frame answered a double but raised
Python's own ``OverflowError`` for a whole number, at the line.
"""

from __future__ import annotations

import json
import math
import random
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

_PRECISE = Context(prec=900, Emin=-99999, Emax=99999)
_RULES = {"half_to_even": ROUND_HALF_EVEN, "half_away_from_zero": ROUND_HALF_UP}
_EVEN, _AWAY = "half_to_even", "half_away_from_zero"
_I64_MAX, _I64_MIN = 2**63 - 1, -(2**63)
_ENGINES = ("streaming", "in-memory")
_PAST_I64 = "past the signed 64-bit range"


def _ruled(x: float, decimals: int, mode: str) -> float:
    """Return the double nearest ``x``'s fifteen-digit decimal moved to ``decimals``."""
    if x == 0 or not math.isfinite(x):
        return x
    exact = Decimal(x)
    held = exact.quantize(
        Decimal((0, (1,), exact.adjusted() - 14)),
        rounding=ROUND_HALF_UP,
        context=_PRECISE,
    )
    step = Decimal((0, (1,), -decimals))
    if step.as_tuple().exponent > held.as_tuple().exponent:
        held = held.quantize(step, rounding=_RULES[mode], context=_PRECISE)
    return math.copysign(float(held), x)


def _same(a: float, b: float) -> bool:
    """Say whether two doubles are one value, the sign of a nought included."""
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return a == b and math.copysign(1.0, a) == math.copysign(1.0, b)


def _rounded(
    values: list[object], dtype: pl.DataType, decimals: int, mode: str, engine: str
) -> list[object]:
    frame = ActuarialFrame(pl.DataFrame({"x": pl.Series(values, dtype=dtype)}))
    frame.r = frame.x.round(decimals, mode=mode)
    return frame.collect(engine=engine)["r"].to_list()


_WHOLE = [
    (25, -1, _EVEN, 20),
    (25, -1, _AWAY, 30),
    (-25, -1, _EVEN, -20),
    (-25, -1, _AWAY, -30),
    (35, -1, _EVEN, 40),
    (35, -1, _AWAY, 40),
    (15, -1, _EVEN, 20),
    (1234, -2, _EVEN, 1200),
    (1250, -2, _EVEN, 1200),
    (1250, -2, _AWAY, 1300),
    # 2**53 + 13: through the double nearest it, 2**53 + 12, the tie is lost.
    (9007199254741005, -1, _AWAY, 9007199254741010),
    (9007199254741005, -1, _EVEN, 9007199254741000),
    (_I64_MAX, -18, _EVEN, 9 * 10**18),
    (_I64_MIN, -18, _AWAY, -9 * 10**18),
    (5 * 10**18, -19, _EVEN, 0),
    (4999999999999999999, -19, _AWAY, 0),
    (_I64_MAX, -20, _AWAY, 0),
    (_I64_MIN, -20, _EVEN, 0),
]


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize(("value", "decimals", "mode", "hand"), _WHOLE)
def test_a_whole_number_moves_to_its_step_exactly(
    value: int, decimals: int, mode: str, hand: int, engine: str
) -> None:
    """0.9.0 raised Python's own OverflowError where the line was written."""
    assert _rounded([value], pl.Int64, decimals, mode, engine) == [hand]


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_run_of_whole_numbers_moves_each_period(engine: str) -> None:
    frame = ActuarialFrame(pl.DataFrame({"k": [[25, 35, -25, None], [], None]}))
    frame.even = frame.k.round(-1)
    frame.away = frame.k.round(-1, mode=_AWAY)
    out = frame.collect(engine=engine)
    assert out.schema["even"] == pl.List(pl.Int64)
    assert out["even"].to_list() == [[20, 40, -20, None], [], None]
    assert out["away"].to_list() == [[30, 40, -30, None], [], None]


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize(
    ("value", "decimals", "mode"),
    [
        (_I64_MAX, -1, _EVEN),
        (_I64_MIN, -1, _AWAY),
        (_I64_MAX, -19, _EVEN),
        (5 * 10**18, -19, _AWAY),
        (-(5 * 10**18) - 1, -19, _EVEN),
    ],
)
def test_a_whole_number_whose_step_no_i64_holds_is_refused_by_name(
    value: int, decimals: int, mode: str, engine: str
) -> None:
    """2**63 - 1 to tens is 9223372036854775810, which no i64 holds."""
    with pytest.raises(pl.exceptions.PolarsError, match=_PAST_I64):
        _rounded([value, 25], pl.Int64, decimals, mode, engine)


def test_a_run_holding_a_whole_number_past_its_step_is_refused_by_name() -> None:
    frame = ActuarialFrame(pl.DataFrame({"k": [[25, _I64_MAX]]}))
    frame.r = frame.k.round(-1)
    with pytest.raises(pl.exceptions.PolarsError, match=_PAST_I64):
        frame.collect()


@pytest.mark.parametrize("dtype", [pl.Int32, pl.UInt16, pl.UInt64])
def test_another_whole_number_type_is_read_as_the_i64_it_holds(
    dtype: pl.DataType,
) -> None:
    out = _rounded([25, 35], dtype, -1, _EVEN, "streaming")
    assert out == [20, 40]


def test_a_wide_whole_number_past_i64_is_refused_by_name() -> None:
    with pytest.raises(pl.exceptions.PolarsError, match="signed 64-bit range"):
        _rounded([25, 2**64 - 1], pl.UInt64, -1, _EVEN, "streaming")


_DOUBLES = [
    (25.0, -1, _EVEN, 20.0),
    (25.0, -1, _AWAY, 30.0),
    (-25.0, -1, _AWAY, -30.0),
    (15.0, -1, _EVEN, 20.0),
    (1234.5, -2, _EVEN, 1200.0),
    (1234.5, -2, _AWAY, 1200.0),
    (1250.0, -2, _EVEN, 1200.0),
    (1250.0, -2, _AWAY, 1300.0),
    # 24.999999999999996 reads as 25.0000000000000: a half at tens.
    (24.999999999999996, -1, _EVEN, 20.0),
    (24.999999999999996, -1, _AWAY, 30.0),
    (68049.31499999999, -1, _EVEN, 68050.0),
    (-4.0, -1, _EVEN, -0.0),
    (2.5e22, -22, _EVEN, 2e22),
    (2.5e22, -22, _AWAY, 3e22),
    # Past 10**308 no step is a double: every finite value is under half one.
    (1e300, -309, _AWAY, 0.0),
    (-1.7976931348623157e308, -400, _EVEN, -0.0),
]


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize(("value", "decimals", "mode", "hand"), _DOUBLES)
def test_a_double_moves_its_reading_to_its_step(
    value: float, decimals: int, mode: str, hand: float, engine: str
) -> None:
    (answer,) = _rounded([value], pl.Float64, decimals, mode, engine)
    assert _same(answer, hand)  # type: ignore[arg-type]


def test_nan_and_infinity_are_their_own_answers_past_every_step() -> None:
    values = [math.nan, math.inf, -math.inf, None]
    for decimals in (-1, -30, -309):
        out = _rounded(values, pl.Float64, decimals, _EVEN, "streaming")
        assert math.isnan(out[0])  # type: ignore[arg-type]
        assert out[1:] == [math.inf, -math.inf, None]


def test_the_record_carries_the_negative_count_as_written() -> None:
    frame = ActuarialFrame(pl.DataFrame({"x": [1234.5]}))
    frame.r = frame.x.round(-2, mode=_AWAY)
    artifact = json.loads(GraphExporter(frame).export(profile="executable"))
    (node,) = [n for n in artifact["nodes"] if n["column"] == "r"]
    assert node["tier"] == "core"
    assert node["expr"]["attrs"] == {"decimals": -2, "mode": _AWAY}


def test_a_fixed_point_decimal_is_rounded_as_the_double_it_entered_as() -> None:
    """The book's decimal is read as its double at the door, so it rounds as one."""
    book = pl.DataFrame(
        {"d": pl.Series([Decimal("1234.5678")], dtype=pl.Decimal(10, 4))}
    )
    frame = ActuarialFrame(book)
    frame.r = frame.d.round(-1)
    assert frame.collect()["r"].to_list() == [1230.0]


@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_a_flag_is_rounded_as_its_0_or_1(mode: str) -> None:
    frame = ActuarialFrame(pl.DataFrame({"b": [True, False, None]}))
    frame.r = frame.b.round(-1, mode=mode)
    frame.s = (frame.b == True).round(-1, mode=mode)  # noqa: E712 - a comparison
    out = frame.collect()
    assert out.schema["r"] == pl.Float64
    assert out["r"].to_list() == [0.0, 0.0, None]
    assert out["s"].to_list() == [0.0, 0.0, None]


@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_a_single_precision_value_is_rounded_by_its_double(mode: str) -> None:
    out = _rounded([25.0, -1234.5], pl.Float32, -1, mode, "streaming")
    assert out == ([20.0, -1230.0] if mode == _EVEN else [30.0, -1230.0])


def test_excel_round_and_round_away_from_zero_agree_on_either_side_of_the_point() -> (
    None
):
    """Inside 11.1.35's entry the two spellings are one rounding of a double."""
    rng = random.Random(8)  # noqa: S311 -- a reproducible sample, not a secret
    values = [rng.choice([1, -1]) * 10 ** rng.uniform(-3, 13) for _ in range(500)]
    values += [25.0, -25.0, 1250.0, 24.999999999999996, 68049.31499999999]
    frame = ActuarialFrame(pl.DataFrame({"x": values}))
    for places in range(1, 11):
        frame[f"e{places}"] = frame.x.excel.round(-places)
        frame[f"r{places}"] = frame.x.round(-places, mode=_AWAY)
    out = frame.collect()
    for places in range(1, 11):
        for e, r in zip(
            out[f"e{places}"].to_list(), out[f"r{places}"].to_list(), strict=True
        ):
            assert _same(e, r)


def test_excel_round_answers_a_double_where_round_keeps_a_whole_number() -> None:
    frame = ActuarialFrame(pl.DataFrame({"k": [25, -25]}))
    frame.e = frame.k.excel.round(-1)
    frame.r = frame.k.round(-1, mode=_AWAY)
    out = frame.collect()
    assert out["e"].to_list() == [30.0, -30.0]
    assert out["r"].to_list() == [30, -30]
    assert out.schema["r"] == pl.Int64


@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_a_sweep_near_halves_matches_the_rule(mode: str) -> None:
    """3,000 doubles within three units of a half at one to six places left."""
    rng = random.Random(98)  # noqa: S311 -- a reproducible sample, not a secret
    for places in range(1, 7):
        values = []
        for _ in range(500):
            count = rng.randrange(0, 10 ** rng.randint(1, 14))
            reading = (Decimal(count) + Decimal("0.5")) * Decimal(10) ** places
            x = float(reading)
            for _ in range(rng.randint(0, 3)):
                x = math.nextafter(x, rng.choice([math.inf, -math.inf]))
            values.append(rng.choice([1.0, -1.0]) * x)
        out = _rounded(values, pl.Float64, -places, mode, "streaming")
        for x, got in zip(values, out, strict=True):
            want = _ruled(x, -places, mode)
            assert _same(got, want), (x, places)  # type: ignore[arg-type]
