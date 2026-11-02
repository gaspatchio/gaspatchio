# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A double's significant figures here are the producer's: the fifteen it holds.

Section 11.1.12 reads a double as its fifteen-significant-digit decimal -- a
sixteenth digit of 5 or more going away from zero, as ``excel.round`` reads
its operand -- rounds that decimal to its figures with a half away from zero,
and answers the double nearest the result. This engine rounded the double's
exact value, so 0.15 to one figure was 0.1 where a spreadsheet shows 0.2, and
2.675 to three was 2.67 for 2.68. Both engines now read the fifteen digits
exactly. Below the magnitudes they keep exactly, and from 10**37, both answer
by the native binary64 scaling, the same double on both, where they refused.
"""

from __future__ import annotations

import datetime
import json
import math
import random
from decimal import ROUND_HALF_UP, Context, Decimal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.frame.graph import GraphExporter

_PRECISE = Context(prec=900, Emin=-99999, Emax=99999)
_HELD = 15


def _ruled(x: float, digits: int) -> float:
    """Return the double nearest ``x``'s fifteen-digit decimal kept to ``digits``."""
    exact = Decimal(x)
    held = exact.quantize(
        Decimal((0, (1,), exact.adjusted() - _HELD + 1)),
        rounding=ROUND_HALF_UP,
        context=_PRECISE,
    )
    if digits < _HELD:
        step = Decimal((0, (1,), held.adjusted() - digits + 1))
        held = held.quantize(step, rounding=ROUND_HALF_UP, context=_PRECISE)
    return float(held)


def _both(values: list[float], digits: int) -> tuple[list[float], list[float]]:
    book = pl.DataFrame({"x": pl.Series(values, dtype=pl.Float64)})
    af = ActuarialFrame(book)
    af.r = af.x.round_sig_figs(digits)
    document = json.loads(GraphExporter(af).export(profile="executable"))
    jax = engine_named("jax").run(document, book, FrameSink()).columns["r"]
    return af.collect()["r"].to_list(), jax.to_list()


@pytest.mark.parametrize(
    ("value", "digits", "hand"),
    [
        (0.15, 1, 0.2),
        (0.285, 2, 0.29),
        (2.675, 3, 2.68),
        (1.005, 3, 1.01),
        (781098.0, 1, 800000.0),
        (-0.15, 1, -0.2),
        (0.30000000000000004, 17, 0.3),
        (2.5, 1, 3.0),
        (1.5e-22, 1, 2e-22),
        (9.5e36, 1, 1e37),
    ],
    ids=[
        "0.15 reads as 0.150000000000000 (was 0.1)",
        "0.285 (was 0.28)",
        "2.675 (was 2.67)",
        "1.005 (was 1.0)",
        "781098 to one figure",
        "a negative (was -0.1)",
        "seventeen figures are fifteen (was itself)",
        "a tie away from zero",
        "the least magnitude kept at one figure",
        "the greatest, carried to 10**37",
    ],
)
def test_both_engines_keep_the_fifteen_digit_figures(
    value: float, digits: int, hand: float
) -> None:
    assert _both([value], digits) == ([hand], [hand])


def test_a_run_of_doubles_keeps_its_fifteen_digit_figures_on_both_engines() -> None:
    """Per period: 781098 is 800000 and 0.15 is 0.2 at one figure, on both engines."""
    book = pl.DataFrame({"x": [781098.0, 0.15]})
    af = ActuarialFrame(book)
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.y = af.x + af.month * 0.0
    af.r = af.y.round_sig_figs(1)
    document = json.loads(GraphExporter(af).export(profile="executable"))
    jax = engine_named("jax").run(document, book, FrameSink()).columns["r"]
    want = [[800000.0] * 3, [0.2] * 3]

    assert af.collect()["r"].to_list() == want
    assert jax.to_list() == want


@pytest.mark.parametrize(
    ("value", "digits", "native"),
    [
        (3e-24, 1, 3e-24),
        (-3e-24, 1, -3e-24),
        (1e-30, 3, 9.999999999999999e-31),
        (9.9e-9, 15, 9.900000000000001e-09),
        (2e37, 2, 2.0000000000000001e37),
        (-1e300, 1, -1.0000000000000006e300),
        (1.7976931348623157e308, 3, 1.7976931348623157e308),
        (5e-324, 1, 5e-324),
    ],
    ids=[
        "a residue where nought was meant",
        "its negative",
        "far below",
        "below 1e-8 at fifteen figures",
        "past 1e37",
        "far past",
        "the largest double",
        "the least subnormal",
    ],
)
def test_outside_the_exact_range_both_engines_answer_by_the_native_route(
    value: float, digits: int, native: float
) -> None:
    """Each was refused on both engines; each is now Polars' own answer, on both."""
    frame, jax = _both([1.0, value], digits)

    assert pl.Series([value]).round_sig_figs(digits).to_list() == [native]
    assert frame[1] == native
    assert jax[1] == native


def _sample(rng: random.Random, digits: int) -> float:
    """Draw a value from 1e-22 to 1e36, three in five within an ulp of a half."""
    x = 10 ** rng.uniform(-22.0 + min(digits, _HELD), 36.0)
    place = math.floor(math.log10(x))
    draw = rng.random()
    if draw < 0.4:
        sixteen = rng.randint(10**14, 10**15 - 1) * 10 + 5
        x = float(Decimal(sixteen).scaleb(place - 15))
    elif draw < 0.6:
        figures = min(digits, 14)
        kept = rng.randint(10 ** (figures - 1), 10**figures - 1) * 10 + 5
        x = float(Decimal(kept).scaleb(place - figures))
    return math.nextafter(x, rng.choice([math.inf, -math.inf, x]))


def test_a_sweep_matches_the_fifteen_digit_rule_on_both_engines() -> None:
    """1,500 values: both engines answer the rule, at the halves where routes part."""
    rng = random.Random(93)  # noqa: S311 -- a reproducible sample, not a secret
    for digits in (1, 2, 3, 6, 10, 14, 15, 17):
        values = [_sample(rng, digits) for _ in range(190)]
        frame, jax = _both(values, digits)
        want = [_ruled(x, digits) for x in values]

        assert frame == want
        assert jax == want


def test_a_whole_number_keeps_every_digit_on_both_engines() -> None:
    """An i64 has no fifteen-digit reading: its sixteen figures are its own."""
    book = pl.DataFrame({"n": [12345678901234567, 781098]})
    af = ActuarialFrame(book)
    af.r = af.n.round_sig_figs(16)
    document = json.loads(GraphExporter(af).export(profile="executable"))
    jax = engine_named("jax").run(document, book, FrameSink()).columns["r"]

    assert af.collect()["r"].to_list() == [12345678901234570, 781098]
    assert jax.to_list() == [12345678901234570, 781098]
