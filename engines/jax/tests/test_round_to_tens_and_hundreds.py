# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``round`` with a negative ``decimals`` answers here, and agrees with the producer.

Section 11.1.8 defines ``round(decimals=-n)`` as rounding to a multiple of
``10**n``, as a spreadsheet's ``ROUND(x, -n)`` does. This engine refused the
record by name, before any book was read. It now moves a double's
fifteen-digit reading to the step, a whole number exactly in ``int64`` with an
answer no ``i64`` holds flagged, and answers the producer's double past 22
places and past every step a double holds.
"""

from __future__ import annotations

import json
import math
import random
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter

_PRECISE = Context(prec=900, Emin=-99999, Emax=99999)
_RULES = {"half_to_even": ROUND_HALF_EVEN, "half_away_from_zero": ROUND_HALF_UP}
_EVEN, _AWAY = "half_to_even", "half_away_from_zero"
_I64_MAX, _I64_MIN = 2**63 - 1, -(2**63)


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
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return a == b and math.copysign(1.0, a) == math.copysign(1.0, b)


def _both(book: pl.DataFrame, decimals: int, mode: str) -> tuple[list, list]:
    af = ActuarialFrame(book)
    af.r = af.x.round(decimals, mode=mode)
    document = json.loads(GraphExporter(af).export(profile="executable"))
    jax = engine_named("jax").run(document, book, FrameSink()).columns["r"]
    return af.collect()["r"].to_list(), jax.to_list()


@pytest.mark.parametrize(
    ("value", "decimals", "mode", "hand"),
    [
        (25.0, -1, _EVEN, 20.0),
        (25.0, -1, _AWAY, 30.0),
        (-25.0, -1, _AWAY, -30.0),
        (1234.5, -2, _EVEN, 1200.0),
        (1250.0, -2, _AWAY, 1300.0),
        (24.999999999999996, -1, _EVEN, 20.0),
        (68049.31499999999, -1, _AWAY, 68050.0),
        (-4.0, -1, _EVEN, -0.0),
        (2.5e22, -22, _EVEN, 2e22),
        (1e300, -309, _AWAY, 0.0),
        (-1e300, -400, _EVEN, -0.0),
    ],
)
def test_a_double_moves_to_its_step_on_both_engines(
    value: float, decimals: int, mode: str, hand: float
) -> None:
    produced, answered = _both(pl.DataFrame({"x": [value]}), decimals, mode)
    assert _same(produced[0], hand)
    assert _same(answered[0], hand)


@pytest.mark.parametrize(
    ("value", "decimals", "mode", "hand"),
    [
        (25, -1, _EVEN, 20),
        (25, -1, _AWAY, 30),
        (-25, -1, _AWAY, -30),
        (35, -1, _EVEN, 40),
        (9007199254741005, -1, _AWAY, 9007199254741010),
        (_I64_MAX, -18, _EVEN, 9 * 10**18),
        (5 * 10**18, -19, _EVEN, 0),
        (_I64_MIN, -20, _AWAY, 0),
    ],
)
def test_a_whole_number_moves_to_its_step_on_both_engines(
    value: int, decimals: int, mode: str, hand: int
) -> None:
    book = pl.DataFrame({"x": pl.Series([value], dtype=pl.Int64)})
    produced, answered = _both(book, decimals, mode)
    assert produced == [hand]
    assert answered == [hand]


def test_a_run_moves_each_period_on_both_engines() -> None:
    book = pl.DataFrame({"x": [[25, 35, -25], [150, 1]]})
    produced, answered = _both(book, -1, _EVEN)
    assert produced == answered == [[20, 40, -20], [150, 0]]
    doubles = pl.DataFrame({"x": [[25.0, 35.0, -25.0], [1234.5]]})
    produced, answered = _both(doubles, -1, _AWAY)
    assert produced == answered == [[30.0, 40.0, -30.0], [1230.0]]


@pytest.mark.parametrize(
    ("value", "decimals", "mode"),
    [(_I64_MAX, -1, _EVEN), (_I64_MIN, -1, _AWAY), (5 * 10**18, -19, _AWAY)],
)
def test_a_whole_number_whose_step_no_i64_holds_is_refused(
    value: int, decimals: int, mode: str
) -> None:
    """2**63 - 1 to tens is 9223372036854775810."""
    book = pl.DataFrame({"x": pl.Series([value], dtype=pl.Int64)})
    af = ActuarialFrame(book)
    af.r = af.x.round(decimals, mode=mode)
    document = json.loads(GraphExporter(af).export(profile="executable"))
    with pytest.raises(EngineRefusal, match="outside the range i64 carries"):
        engine_named("jax").run(document, book, FrameSink())


@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_near_halves_match_the_rule_and_the_producer(mode: str) -> None:
    """1,800 doubles within three units of a half at one to six places left."""
    rng = random.Random(6)  # noqa: S311 -- a reproducible sample, not a secret
    values = []
    places_of = []
    for places in range(1, 7):
        for _ in range(300):
            count = rng.randrange(0, 10 ** rng.randint(1, 14))
            reading = (Decimal(count) + Decimal("0.5")) * Decimal(10) ** places
            x = float(reading)
            for _ in range(rng.randint(0, 3)):
                x = math.nextafter(x, rng.choice([math.inf, -math.inf]))
            values.append(rng.choice([1.0, -1.0]) * x)
            places_of.append(places)
    for places in range(1, 7):
        chosen = [v for v, p in zip(values, places_of, strict=True) if p == places]
        produced, answered = _both(pl.DataFrame({"x": chosen}), -places, mode)
        for x, p, a in zip(chosen, produced, answered, strict=True):
            want = _ruled(x, -places, mode)
            assert _same(p, want), (x, places)
            assert _same(a, want), (x, places)


@pytest.mark.parametrize("decimals", [-23, -30, -100, -300, -308])
def test_past_22_places_left_both_engines_answer_the_same_double(decimals: int) -> None:
    """The native scaling, written as three products on both engines."""
    rng = random.Random(-decimals)  # noqa: S311 -- a reproducible sample
    values = [rng.choice([1, -1]) * 10 ** rng.uniform(15, 308.2) for _ in range(400)]
    values += [1.7976931348623157e308, -1.7976931348623157e308]
    for mode in (_EVEN, _AWAY):
        produced, answered = _both(pl.DataFrame({"x": values}), decimals, mode)
        assert all(_same(p, a) for p, a in zip(produced, answered, strict=True))


@pytest.mark.parametrize("decimals", [2, 0, -1])
def test_a_value_below_the_least_normal_double_keeps_its_sign(decimals: int) -> None:
    """The engine reads one as nought, and answered +0.0 for -5e-324."""
    book = pl.DataFrame({"x": [5e-324, -5e-324, -1e-310, -0.0]})
    produced, answered = _both(book, decimals, _EVEN)
    assert all(_same(p, a) for p, a in zip(produced, answered, strict=True))
    assert [math.copysign(1.0, a) for a in answered] == [1.0, -1.0, -1.0, -1.0]
