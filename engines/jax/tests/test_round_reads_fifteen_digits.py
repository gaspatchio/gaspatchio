# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``round`` moves the fifteen figures a spreadsheet holds, on both engines.

Section 11.1.8 reads a double as its fifteen-significant-digit decimal -- a
sixteenth digit of 5 or more going away from zero, as ``excel.round`` reads
its operand -- and moves that decimal to its places by the tie rule the node
carries. 2.675 is the double 2.67499999999999982..., which reads as
2.67500000000000, a half: at two places it is 2.68 under either rule. Both
engines scaled the double in binary64, so 0.285 away from zero was 0.28 and a
workbook's 68049.31499999999 was 68049.31 for 68049.32. Every value below
10**37 at up to 22 places is exact on both; from 10**37 a double is whole and
its own answer, and past 22 places both answer by the native route, the same
double on both.
"""

from __future__ import annotations

import datetime
import json
import math
import random
import sys
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.frame.graph import GraphExporter

_PRECISE = Context(prec=900, Emin=-99999, Emax=99999)
_RULES = {"half_to_even": ROUND_HALF_EVEN, "half_away_from_zero": ROUND_HALF_UP}
_EVEN, _AWAY = "half_to_even", "half_away_from_zero"
_HALF = 0.5


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


def _both(
    values: list[float], decimals: int, mode: str
) -> tuple[list[float], list[float]]:
    book = pl.DataFrame({"x": pl.Series(values, dtype=pl.Float64)})
    af = ActuarialFrame(book)
    af.r = af.x.round(decimals, mode=mode)
    document = json.loads(GraphExporter(af).export(profile="executable"))
    jax = engine_named("jax").run(document, book, FrameSink()).columns["r"]
    return af.collect()["r"].to_list(), jax.to_list()


@pytest.mark.parametrize(
    ("value", "decimals", "mode", "hand"),
    [
        (2.675, 2, _EVEN, 2.68),
        (2.675, 2, _AWAY, 2.68),
        (0.285, 2, _EVEN, 0.28),
        (0.285, 2, _AWAY, 0.29),
        (1.005, 2, _AWAY, 1.01),
        (-1.005, 2, _AWAY, -1.01),
        (68049.31499999999, 2, _EVEN, 68049.32),
        (0.15, 1, _EVEN, 0.2),
        (0.125, 2, _EVEN, 0.12),
        (0.125, 2, _AWAY, 0.13),
        (2.5, 0, _EVEN, 2.0),
        (-2.5, 0, _AWAY, -3.0),
        (0.30000000000000004, 16, _AWAY, 0.3),
    ],
    ids=[
        "2.675 reads as a half: even",
        "2.675 away",
        "0.285 even (unchanged)",
        "0.285 away (was 0.28)",
        "1.005 away (was 1.0)",
        "its negative (was -1.0)",
        "a workbook's 1.5 * 45366.21 (was 68049.31)",
        "0.15 even: 0.2 is even",
        "an exact tie, even",
        "an exact tie, away",
        "a whole tie, even",
        "a negative whole tie, away",
        "sixteen places are the fifteen digits (was 0.3000000000000001)",
    ],
)
def test_both_engines_move_the_fifteen_digit_reading(
    value: float, decimals: int, mode: str, hand: float
) -> None:
    assert _ruled(value, decimals, mode) == hand
    assert _both([value], decimals, mode) == ([hand], [hand])


def test_a_run_moves_the_fifteen_digit_reading_on_both_engines() -> None:
    """Per period: 2.675 is 2.68 and 0.285 is 0.29 away from zero, every period."""
    book = pl.DataFrame({"x": [2.675, 0.285]})
    af = ActuarialFrame(book)
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.y = af.x + af.month * 0.0
    af.r = af.y.round(2, mode=_AWAY)
    document = json.loads(GraphExporter(af).export(profile="executable"))
    jax = engine_named("jax").run(document, book, FrameSink()).columns["r"]
    want = [[2.68] * 3, [0.29] * 3]

    assert af.collect()["r"].to_list() == want
    assert jax.to_list() == want


@pytest.mark.parametrize(
    "value",
    [2e37, -1.7359553413399977e96, 1.7976931348623157e308],
    ids=["past 1e37", "far past", "the largest double"],
)
@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_from_1e37_a_double_is_its_own_answer_on_both_engines(
    value: float, mode: str
) -> None:
    """Whole, so its own answer; the JAX engine's scaling overflowed to infinity."""
    assert _both([1.0, value], 2, mode) == ([1.0, value], [1.0, value])


@pytest.mark.parametrize(
    ("value", "decimals"),
    [(2.5e-23, 23), (1e-30, 30), (1e-310, 330)],
    ids=["23 places", "30 places", "330 places, past every power a double holds"],
)
@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_past_22_places_both_engines_answer_the_native_route(
    value: float, decimals: int, mode: str
) -> None:
    frame, jax = _both([1.0, value], decimals, mode)

    assert frame[1] == pl.Series([value]).round(decimals, mode=mode)[0]
    assert jax[1] == frame[1]


def test_a_whole_number_is_its_own_answer_on_both_engines() -> None:
    book = pl.DataFrame({"n": [2**53 + 1, -7]})
    af = ActuarialFrame(book)
    af.r = af.n.round(2)
    document = json.loads(GraphExporter(af).export(profile="executable"))
    jax = engine_named("jax").run(document, book, FrameSink()).columns["r"]

    assert af.collect()["r"].to_list() == [2**53 + 1, -7]
    assert jax.to_list() == [2**53 + 1, -7]


def _sample(rng: random.Random, decimals: int) -> float:
    """Draw a value near a half: of the places asked for, or of the reading itself."""
    if rng.random() < 0.5:
        count = rng.randrange(0, 10 ** rng.randint(1, 13))
        x = float(Decimal(10 * count + 5).scaleb(-decimals - 1))
    else:
        x = 10 ** rng.uniform(-6.0, 14.0)
        place = math.floor(math.log10(x))
        x = float(Decimal(rng.randint(10**14, 10**15 - 1) * 10 + 5).scaleb(place - 15))
    for _ in range(rng.randint(0, 2)):
        x = math.nextafter(x, rng.choice([math.inf, -math.inf]))
    return -x if rng.random() < 0.5 else x


@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_a_sweep_matches_the_rule_on_both_engines(mode: str) -> None:
    """1,200 values near a half: both engines answer the decimal rule."""
    rng = random.Random(96)  # noqa: S311 -- a reproducible sample, not a secret
    for decimals in (0, 1, 2, 4, 9, 15, 22):
        values = [_sample(rng, decimals) for _ in range(170)]
        frame, jax = _both(values, decimals, mode)
        want = [_ruled(x, decimals, mode) for x in values]

        assert frame == want
        assert jax == want


def powered_ten(places: int) -> float:
    """Return ten to ``places``, squared and multiplied as Rust's ``powi`` is."""
    product, square, left = 1.0, 10.0, places
    while True:
        if left & 1:
            product *= square
        left >>= 1
        if not left:
            return product
        square *= square


def test_the_producer_scales_past_22_places_by_ten_squared_and_multiplied() -> None:
    """Polars' scale is Rust's ``powi``: products of doubles, each one rounded.

    At 23 places that is the double nearest 10**23, which lies halfway between
    two doubles -- glibc's ``pow`` takes the other one, 1.0000000000000001e23.
    At 33 places it is ten times 10**32, itself a rounded square: two roundings
    and 1.0000000000000001e33, where the double nearest 10**33 is 1e33.
    """
    assert powered_ten(23) == 1e23
    assert powered_ten(33) == 1.0000000000000001e33 != float(10**33)
    assert powered_ten(210) == 1.0000000000000004e210
    assert math.isinf(powered_ten(309))
    values = [2.5e-23, 1.5e-33, -3.5e-40, 7.25e-100, 1e-300]
    for places in range(23, 309):
        scale = powered_ten(places)
        for mode, rounded in ((_EVEN, round), (_AWAY, _away)):
            want = [
                rounded(value * scale) / scale
                if math.isfinite(rounded(value * scale) / scale)
                else value
                for value in values
            ]
            got = pl.Series(values).round(places, mode=mode).to_list()
            assert got == want, (places, mode)


def _away(value: float) -> float:
    """Return a double at its nearest whole number, a half going away from zero."""
    whole = math.floor(abs(value))
    return math.copysign(whole + (abs(value) - whole >= _HALF), value)


def _scale_sensitive(places: int) -> float:
    """Return a value whose rounding at ``places`` moves if the scale moves one ulp."""
    scale = powered_ten(places)
    neighbours = (math.nextafter(scale, 0.0), math.nextafter(scale, math.inf))
    for count in range(1, 10_000):
        value = (count + _HALF) / scale
        answers = {round(value * one) / one for one in (scale, *neighbours)}
        if min(value, *answers) < sys.float_info.min:
            # Below the least normal double this engine reads a value as
            # nought, a limit of its own and not the scale's.
            continue
        if len(answers) > 1:
            return value
    msg = f"no value at {places} places is moved by a one-ulp scale"
    raise AssertionError(msg)


@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_past_22_places_the_engine_scales_as_the_producer_at_every_count(
    mode: str,
) -> None:
    """Every count from 23 to 308, on a value a one-ulp scale would move.

    The engine scaled by the host's ``pow``: the double nearest 10**n on macOS,
    which is not the producer's from 33 places on, and on glibc not even at 23.
    """
    counts = range(23, 309)
    values = [_scale_sensitive(places) for places in counts]
    book = pl.DataFrame({"x": pl.Series([1.0, *values], dtype=pl.Float64)})
    af = ActuarialFrame(book)
    for places in counts:
        af[f"r{places}"] = af.x.round(places, mode=mode)
    document = json.loads(GraphExporter(af).export(profile="executable"))
    jax = engine_named("jax").run(document, book, FrameSink()).columns
    frame = af.collect()
    moved = {
        places: (frame[f"r{places}"].to_list(), jax[f"r{places}"].to_list())
        for places in counts
        if frame[f"r{places}"].to_list() != jax[f"r{places}"].to_list()
    }
    assert not moved, sorted(moved)[:10]
    for places, value in zip(counts, values, strict=True):
        assert (
            frame[f"r{places}"][counts.index(places) + 1]
            == pl.Series([value]).round(places, mode=mode)[0]
        )
