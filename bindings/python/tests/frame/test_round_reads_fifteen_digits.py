# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``round`` moves the fifteen figures a spreadsheet holds, under either tie rule.

Section 11.1.8 reads a double as its fifteen-significant-digit decimal -- a
sixteenth digit of 5 or more going away from zero, as ``excel.round`` reads
its operand (11.1.35) -- and moves that decimal to its places by the rule the
node carries. 2.675 is the double 2.67499999999999982..., which reads as
2.67500000000000, a half: 2.68 at two places under either rule. The frame
scaled the double in binary64, so 0.285 away from zero was 0.28, 1.005 was
1.0 and a workbook's 68049.31499999999 was 68049.31; the reference reader
rounded the exact value under ``half_to_even``, so 2.675 was 2.67 there. Every
value below 10**37 at up to 22 places is now exact on the frame and in the
reader; from 10**37 a double is whole and its own answer, and past 22 places
the frame takes Polars' own rounding.
"""

from __future__ import annotations

import datetime
import math
import random
import sys
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal
from pathlib import Path

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Call, Col
from gaspatchio.frame.lowering import lower_polars
from gaspatchio.frame.lowering.polars import LoweringError

_CONFORMANCE = Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"
sys.path.insert(0, str(_CONFORMANCE))
from reader.elementary import rounding  # noqa: E402
from reader.shared import DomainRefusal  # noqa: E402

_PRECISE = Context(prec=900, Emin=-99999, Emax=99999)
_RULES = {"half_to_even": ROUND_HALF_EVEN, "half_away_from_zero": ROUND_HALF_UP}
_EVEN, _AWAY = "half_to_even", "half_away_from_zero"
_TOP = math.nextafter(1e37, math.inf)


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


def _frame(values: list[float], decimals: int, mode: str) -> list[float]:
    af = ActuarialFrame(pl.DataFrame({"x": pl.Series(values, dtype=pl.Float64)}))
    af.r = af.x.round(decimals, mode=mode)
    return af.collect()["r"].to_list()


def _reader(value: float, decimals: int, mode: str) -> float:
    return rounding(value, name="round", attrs={"decimals": decimals, "mode": mode})


def _same(got: float, want: float) -> bool:
    """Equal, the sign of a nought included."""
    return got == want and math.copysign(1.0, got) == math.copysign(1.0, want)


# Each is the hand value, and what the frame answered before.
_CASES = [
    pytest.param(2.675, 2, _EVEN, 2.68, id="2.675 reads as a half, to even"),
    pytest.param(2.675, 2, _AWAY, 2.68, id="2.675 away"),
    pytest.param(0.285, 2, _EVEN, 0.28, id="0.285 to even"),
    pytest.param(0.285, 2, _AWAY, 0.29, id="0.285 away (was 0.28)"),
    pytest.param(1.005, 2, _AWAY, 1.01, id="1.005 away (was 1.0)"),
    pytest.param(-1.005, 2, _AWAY, -1.01, id="its negative (was -1.0)"),
    pytest.param(
        68049.31499999999,
        2,
        _EVEN,
        68049.32,
        id="a workbook's 1.5 * 45366.21 (was 68049.31)",
    ),
    pytest.param(
        68049.31499999999, 2, _AWAY, 68049.32, id="the same, away (was 68049.31)"
    ),
    pytest.param(0.15, 1, _EVEN, 0.2, id="0.15 to even: 2 is even"),
    pytest.param(0.25, 1, _EVEN, 0.2, id="an exact tie to even"),
    pytest.param(0.125, 2, _AWAY, 0.13, id="an exact tie away"),
    pytest.param(-2.5, 0, _EVEN, -2.0, id="a negative whole tie to even"),
    pytest.param(
        -0.5, 0, _EVEN, -0.0, id="a negative half to even is a negative nought"
    ),
    pytest.param(
        0.30000000000000004,
        16,
        _AWAY,
        0.3,
        id="sixteen places are the fifteen digits (was 0.3000000000000001)",
    ),
    pytest.param(1234.5678, 22, _EVEN, 1234.5678, id="22 places"),
]


@pytest.mark.parametrize(("value", "decimals", "mode", "hand"), _CASES)
def test_round_moves_the_fifteen_digit_reading_on_the_frame(
    value: float, decimals: int, mode: str, hand: float
) -> None:
    assert _same(_ruled(value, decimals, mode), hand)
    assert _same(_frame([value], decimals, mode)[0], hand)


@pytest.mark.parametrize(("value", "decimals", "mode", "hand"), _CASES)
def test_round_moves_the_fifteen_digit_reading_in_the_reference_reader(
    value: float, decimals: int, mode: str, hand: float
) -> None:
    """The reader's half_to_even arm rounded the exact value: 2.675 was 2.67."""
    assert _same(_reader(value, decimals, mode), hand)


def test_a_run_moves_the_fifteen_digit_reading() -> None:
    """Per period: 2.675 and 1.005 away from zero, every period."""
    af = ActuarialFrame(pl.DataFrame({"x": [2.675, 1.005]}))
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.y = af.x + af.month * 0.0
    af.r = af.y.round(2, mode=_AWAY)

    assert af.collect()["r"].to_list() == [[2.68] * 3, [1.01] * 3]


def test_null_nan_infinity_and_nought_are_their_own_answers() -> None:
    for mode in (_EVEN, _AWAY):
        got = _frame([None, math.nan, math.inf, -math.inf, 0.0, -0.0], 2, mode)  # type: ignore[list-item]

        assert got[0] is None
        assert math.isnan(got[1])
        assert got[2:] == [math.inf, -math.inf, 0.0, -0.0]
        assert math.copysign(1.0, got[5]) == -1.0


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(2e37, id="past 1e37"),
        pytest.param(-1.7359553413399977e96, id="far past (Polars' own moves it)"),
        pytest.param(1.7976931348623157e308, id="the largest double"),
    ],
)
@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_from_1e37_a_double_is_whole_and_its_own_answer(
    value: float, mode: str
) -> None:
    assert _frame([1.0, value], 2, mode)[1] == value


@pytest.mark.parametrize(
    ("value", "decimals"),
    [
        pytest.param(2.5e-23, 23, id="23 places"),
        pytest.param(1e-30, 30, id="30 places"),
    ],
)
@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_past_22_places_the_frame_takes_polars_own_rounding(
    value: float, decimals: int, mode: str
) -> None:
    want = pl.Series([value]).round(decimals, mode=mode)[0]

    assert _frame([1.0, value], decimals, mode)[1] == want


def test_the_reader_refuses_a_reading_past_the_largest_double() -> None:
    """1.7976931348623157e308 reads as 1.79769313486232e308, which no double holds."""
    with pytest.raises(DomainRefusal, match="past-the-largest-double"):
        _reader(1.7976931348623157e308, 2, _EVEN)


def test_a_whole_number_keeps_its_type_and_every_digit() -> None:
    af = ActuarialFrame(pl.DataFrame({"n": [2**53 + 1, -7]}))
    af.r = af.n.round(2)
    out = af.collect()

    assert out.schema["r"] == pl.Int64
    assert out["r"].to_list() == [2**53 + 1, -7]
    assert _reader(2**53 + 1, 2, _AWAY) == 2**53 + 1  # type: ignore[arg-type]


def test_a_single_precision_value_is_rounded_by_its_double() -> None:
    """A Float32 book column arrives as the double it is exactly, and is rounded so.

    0.285f is 0.28499999642372131 as a double, so it rounds to 0.28.
    """
    af = ActuarialFrame(
        pl.DataFrame({"x": pl.Series([2.5, 0.125, 0.285], dtype=pl.Float32)})
    )
    af.r = af.x.round(2, mode=_AWAY)
    af.e = af.x.round(0)
    out = af.collect()

    assert out.schema["r"] == pl.Float64
    assert out["r"].to_list() == [2.5, 0.13, 0.28]
    assert out["e"].to_list() == [2.0, 0.0, 0.0]


def test_a_value_whose_type_cannot_be_read_is_refused_by_name() -> None:
    """With no frame to type it, neither rounding rule can be chosen."""
    node = Call("round", (Col("x"),), (("decimals", 2), ("mode", _EVEN)))

    with pytest.raises(
        LoweringError, match="type of the value it rounds cannot be read"
    ):
        lower_polars(node, None)


def _sample(rng: random.Random, decimals: int) -> float:
    """Draw a value near a half: of the places asked for, or of the reading itself."""
    if rng.random() < 0.5:
        count = rng.randrange(0, 10 ** rng.randint(1, 13))
        x = float(Decimal(10 * count + 5).scaleb(-decimals - 1))
    else:
        x = 10 ** rng.uniform(-6.0, 14.0)
        place = math.floor(math.log10(x))
        x = float(Decimal(rng.randint(10**14, 10**15 - 1) * 10 + 5).scaleb(place - 15))
    for _ in range(abs(nudge := rng.randint(-3, 3))):
        x = math.nextafter(x, math.inf if nudge > 0 else -math.inf)
    return -x if rng.random() < 0.5 else x


@pytest.mark.parametrize("mode", [_EVEN, _AWAY])
def test_a_sweep_matches_the_rule(mode: str) -> None:
    """3,000 values near a half: the frame and the reader miss none."""
    rng = random.Random(96)  # noqa: S311 -- a reproducible sample, not a secret
    misses = []
    for decimals in (0, 1, 2, 3, 4, 6, 9, 12, 15, 18, 22):
        values = [_sample(rng, decimals) for _ in range(275)]
        for x, got in zip(values, _frame(values, decimals, mode), strict=True):
            want = _ruled(x, decimals, mode)
            if not _same(got, want) or not _same(_reader(x, decimals, mode), want):
                misses.append((x, decimals, got, want))

    assert misses == []
