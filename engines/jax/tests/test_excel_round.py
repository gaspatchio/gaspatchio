# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``excel.round`` rounds the value a spreadsheet holds, as section 11.1.35 states.

The operand's exact decimal expansion to fifteen significant digits, a
sixteenth digit of 5 or more going away from zero; that decimal at the stated
places, a half going away from zero; the nearest double. Checked here against
the rule written out in exact decimals, which shares nothing with the
lowering, on the workbook values that found the gap and on a corpus built to
sit where a rounding of the double goes wrong.
"""

from __future__ import annotations

import math
import random
import struct
from decimal import ROUND_HALF_UP, Decimal, localcontext

import jax.numpy as jnp
import pytest

from gaspatchio_jax.checks import CHECKS
from gaspatchio_jax.lowerings.excel import _steps
from tests.conftest import invocation


def _spreadsheet(value: float, num_digits: int) -> float:
    """Return what section 11.1.35 answers, computed in exact decimals."""
    if not math.isfinite(value) or value == 0.0:
        return value
    with localcontext() as context:
        context.prec = 800
        exact = Decimal(value)
        unit = exact.adjusted() - 14
        held = exact.quantize(Decimal(1).scaleb(unit), rounding=ROUND_HALF_UP)
        if unit < -num_digits:
            held = held.quantize(Decimal(1).scaleb(-num_digits), rounding=ROUND_HALF_UP)
        return math.copysign(abs(float(held)), value)


def _rounded(values: list[float], num_digits: int) -> list[float]:
    """Return this engine's answers for one column of doubles at one place."""
    from gaspatchio.engines.protocol import FrameSink
    from gaspatchio_jax.engine import JaxEngine

    one = invocation(
        {
            "op": "call",
            "name": "excel.round",
            "args": [{"op": "col", "name": "x"}],
            "attrs": {"num_digits": num_digits},
        },
        {"x": {"dtype": "f64", "values": values}},
        "f64",
    )
    result = JaxEngine().run(one.document, one.inputs, FrameSink())
    return result.columns["answer"].to_list()


def _bits(value: float) -> bytes:
    return struct.pack("<d", value)


@pytest.mark.parametrize(
    ("value", "num_digits", "excel"),
    [
        # A workbook's ROUND(1.5 * K19, 2), K19 = 45366.20999999999: the double
        # is 68049.31499999999..., fifteen digits 68049.3150000000.
        (1.5 * 45366.20999999999, 2, 68049.32),
        (0.5 * 161451.33, 2, 80725.67),
        (5657268.499999999 * 0.03, 2, 169718.06),
        (2.675, 2, 2.68),
        (-1.005, 2, -1.01),
        (0.49999999999999994, 0, 1.0),
        (2.5, 0, 3.0),
        (-2.5, 0, -3.0),
        (1250.0, -2, 1300.0),
        # A sixteenth digit that is an exact 5, at a negative place: the one
        # spot the boundary is itself a double, compared exactly.
        (495048749999999.5, -8, 495048800000000.0),
        (1197222449999995.0, -8, 1197222500000000.0),
        # Fifteen digits coarser than the step: the fifteen-digit value.
        (12345678901234.25, 1, 12345678901234.3),
        (999999999999999.5, 0, 1e15),
    ],
)
def test_the_spreadsheet_s_values(value: float, num_digits: int, excel: float) -> None:
    assert _rounded([value], num_digits) == [excel]


def _corpus(seed: int, size: int) -> dict[int, list[float]]:
    """Return doubles a binary rounding gets wrong, beside ordinary ones, by place."""
    rng = random.Random(seed)  # noqa: S311 -- a reproducible corpus, not a secret
    by_place: dict[int, list[float]] = {}
    for _ in range(size):
        kind = rng.random()
        places = rng.randint(-10, 10)
        if kind < 0.4:
            # Decimal ties nudged a few units of the last place either way.
            whole = rng.randint(0, 10 ** rng.randint(1, 13))
            tie = (
                (whole + 0.5) / 10**places
                if places >= 0
                else (whole + 0.5) * 10**-places
            )
            bits = struct.unpack("<q", _bits(tie))[0] + rng.randint(-40, 40)
            value = struct.unpack("<d", struct.pack("<q", bits))[0]
        elif kind < 0.6:
            amount = round(rng.uniform(0, 1e7), rng.randint(0, 4))
            value = amount * rng.choice([0.5, 1.5, 0.03, 0.032, 1.1, 0.07 / 12])
        elif kind < 0.8:
            value = math.ldexp(rng.random() + 0.5, rng.randint(-30, 40))
        else:
            # Quarters at 10^12 to 10^15, whose sixteenth digit is an exact tie.
            value = rng.randint(10**12, 10**15) + rng.choice([0.25, 0.5, 0.75])
            places = rng.randint(-3, 2)
        if abs(value) * 10.0**places >= 2.0**52:
            # Outside the clause's bounded domain, which the engine refuses.
            continue
        by_place.setdefault(places, []).append(-value if rng.random() < 0.5 else value)
    return by_place


def test_a_corpus_agrees_with_the_rule_bit_for_bit() -> None:
    wrong = []
    for places, values in sorted(_corpus(seed=1135, size=12_000).items()):
        for value, got in zip(values, _rounded(values, places), strict=True):
            want = _spreadsheet(value, places)
            if _bits(got) != _bits(want):
                wrong.append((value, places, got, want))
    assert not wrong, wrong[:10]


def test_a_cell_binary_arithmetic_cannot_place_is_flagged(monkeypatch) -> None:
    """The margin is what marks a cell undecided, and nothing else does.

    No value a model computes sits within a few units of 2^-53 of the point
    its fifteen digits turn into a half, so the margin is widened here until
    every cell below 10^14 is inside it, and every one is then flagged.
    """
    monkeypatch.setattr("gaspatchio_jax.lowerings.excel._UNDECIDED", 1e30)
    magnitude = jnp.asarray([0.125, 68049.31499999999, 1e15])
    _steps_answer, undecided = _steps(magnitude, magnitude * 100.0, 2)
    assert undecided.tolist() == [True, True, False]
    assert "excel.round.sixteenth" in CHECKS


def test_an_ordinary_book_has_nothing_undecided() -> None:
    values = [value for row in _corpus(seed=7, size=4_000).values() for value in row]
    magnitude = jnp.abs(jnp.asarray(values))
    for places in (-2, 0, 2, 4):
        power = 10.0 ** abs(places)
        scaled = magnitude * power if places >= 0 else magnitude / power
        _answer, undecided = _steps(magnitude, scaled, places)
        assert not bool(undecided.any())
