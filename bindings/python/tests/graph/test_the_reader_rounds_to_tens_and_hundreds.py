# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The reference reader rounds to tens, hundreds and coarser as section 11.1.8 states.

A double's fifteen-digit reading is moved to the nearest multiple of ``10**n``
by the tie rule, and a whole number is moved exactly in whole numbers, an
answer outside ``i64`` refused. The reader answered a whole number unmoved:
25 to tens was 25.
"""

from __future__ import annotations

import math
import random
import sys
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal
from pathlib import Path

import pytest

_CONFORMANCE = Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"
sys.path.insert(0, str(_CONFORMANCE))
from reader.elementary import rounding  # noqa: E402
from reader.shared import DomainRefusal  # noqa: E402

_PRECISE = Context(prec=900, Emin=-99999, Emax=99999)
_RULES = {"half_to_even": ROUND_HALF_EVEN, "half_away_from_zero": ROUND_HALF_UP}
_EVEN, _AWAY = "half_to_even", "half_away_from_zero"
_I64_MAX, _I64_MIN = 2**63 - 1, -(2**63)


def _read(value: float, decimals: int, mode: str) -> float:
    return rounding(value, name="round", attrs={"decimals": decimals, "mode": mode})


def _same(a: float, b: float) -> bool:
    return a == b and math.copysign(1.0, a) == math.copysign(1.0, b)


@pytest.mark.parametrize(
    ("value", "decimals", "mode", "hand"),
    [
        (25, -1, _EVEN, 20),
        (25, -1, _AWAY, 30),
        (-25, -1, _EVEN, -20),
        (-25, -1, _AWAY, -30),
        (35, -1, _EVEN, 40),
        (1250, -2, _EVEN, 1200),
        (1250, -2, _AWAY, 1300),
        (9007199254741005, -1, _AWAY, 9007199254741010),
        (_I64_MAX, -18, _EVEN, 9 * 10**18),
        (5 * 10**18, -19, _EVEN, 0),
        (_I64_MIN, -20, _AWAY, 0),
        (25, 2, _AWAY, 25),
    ],
)
def test_a_whole_number_moves_to_its_step(
    value: int, decimals: int, mode: str, hand: int
) -> None:
    answer = _read(value, decimals, mode)
    assert answer == hand
    assert type(answer) is int


@pytest.mark.parametrize(
    ("value", "decimals", "mode"),
    [
        (_I64_MAX, -1, _EVEN),
        (_I64_MIN, -1, _AWAY),
        (5 * 10**18, -19, _AWAY),
        (_I64_MAX, -19, _EVEN),
    ],
)
def test_a_whole_number_whose_step_no_i64_holds_is_refused(
    value: int, decimals: int, mode: str
) -> None:
    with pytest.raises(DomainRefusal, match="integer-overflow"):
        _read(value, decimals, mode)


@pytest.mark.parametrize(
    ("value", "decimals", "mode", "hand"),
    [
        (25.0, -1, _EVEN, 20.0),
        (25.0, -1, _AWAY, 30.0),
        (-25.0, -1, _AWAY, -30.0),
        (1234.5, -2, _EVEN, 1200.0),
        (24.999999999999996, -1, _EVEN, 20.0),
        (-4.0, -1, _AWAY, -0.0),
        (1e300, -309, _AWAY, 0.0),
        (-1.7976931348623157e308, -400, _EVEN, -0.0),
    ],
)
def test_a_double_moves_its_reading_to_its_step(
    value: float, decimals: int, mode: str, hand: float
) -> None:
    assert _same(_read(value, decimals, mode), hand)


def test_a_reading_past_the_largest_double_is_refused() -> None:
    """1.7976931348623157e308 to 10**308 reads as 2e308."""
    with pytest.raises(DomainRefusal, match="rounding-past-the-largest-double"):
        _read(1.7976931348623157e308, -308, _EVEN)


@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_whole_numbers_near_a_half_match_integer_arithmetic(mode: str) -> None:
    rng = random.Random(19)  # noqa: S311 -- a reproducible sample, not a secret
    for places in range(1, 19):
        step = 10**places
        for _ in range(100):
            count = rng.randrange(0, _I64_MAX // step)
            value = rng.choice([1, -1]) * (
                count * step + step // 2 + rng.randint(-1, 1)
            )
            magnitude = abs(value)
            kept, rest = divmod(magnitude, step)
            if 2 * rest > step or (2 * rest == step and (mode == _AWAY or kept % 2)):
                kept += 1
            want = kept * step if value >= 0 else -kept * step
            if _I64_MIN <= want <= _I64_MAX:
                assert _read(value, -places, mode) == want


def test_doubles_near_a_half_match_decimal_arithmetic() -> None:
    rng = random.Random(29)  # noqa: S311 -- a reproducible sample, not a secret
    for places in range(1, 23):
        for mode in (_EVEN, _AWAY):
            count = rng.randrange(0, 10 ** rng.randint(1, 14))
            reading = (Decimal(count) + Decimal("0.5")) * Decimal(10) ** places
            x = float(reading)
            held = Decimal(x).quantize(
                Decimal((0, (1,), Decimal(x).adjusted() - 14)),
                rounding=ROUND_HALF_UP,
                context=_PRECISE,
            )
            want = float(
                held.quantize(
                    Decimal((0, (1,), places)), rounding=_RULES[mode], context=_PRECISE
                )
            )
            assert _same(_read(x, -places, mode), want)
