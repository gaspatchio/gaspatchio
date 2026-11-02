# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A double's significant figures are the fifteen a spreadsheet holds, kept.

Section 11.1.12 reads a double as its fifteen-significant-digit decimal -- a
sixteenth digit of 5 or more going away from zero, as ``excel.round`` reads
its operand (11.1.35) -- rounds that decimal to its figures with a half away
from zero, and answers the double nearest the result. 0.15 is the double
0.1499999999999999944..., which reads as 0.150000000000000, so to one figure
it is 0.2, as Excel's ROUND gives; rounding its exact value answered 0.1, and
2.675 to three figures answered 2.67 for 2.68. From fifteen figures up the
answer is the fifteen-digit value. Outside the magnitudes the producer keeps
exactly -- below 10**(digits - 23), or from 10**37 -- Polars' own rounding
answers, where the run was refused; the reference reader stays exact there.
"""

from __future__ import annotations

import datetime
import math
import random
import sys
from decimal import ROUND_HALF_UP, Context, Decimal
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

_PRECISE = Context(prec=900, Emin=-99999, Emax=99999)
_HELD = 15


def _ruled(x: float, digits: int) -> float:
    """Return the double nearest ``x``'s fifteen-digit decimal kept to ``digits``."""
    if x == 0 or not math.isfinite(x):
        return x
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


def _frame(values: list[float], digits: int) -> list[float]:
    af = ActuarialFrame(pl.DataFrame({"x": pl.Series(values, dtype=pl.Float64)}))
    af.r = af.x.round_sig_figs(digits)
    return af.collect()["r"].to_list()


def _reader(value: float, digits: int) -> float:
    return rounding(value, name="round_sig_figs", attrs={"digits": digits})


# Each is the hand value, and what the exact-value route answered before.
_CASES = [
    pytest.param(0.15, 1, 0.2, id="0.15 reads as 0.150000000000000 (was 0.1)"),
    pytest.param(-0.15, 1, -0.2, id="its negative (was -0.1)"),
    pytest.param(0.285, 2, 0.29, id="0.285 to two figures (was 0.28)"),
    pytest.param(2.675, 3, 2.68, id="2.675 to three figures (was 2.67)"),
    pytest.param(1.005, 3, 1.01, id="1.005 to three figures (was 1.0)"),
    pytest.param(781098.0, 1, 800000.0, id="781098 to one figure"),
    pytest.param(-781098.0, 1, -800000.0, id="its negative"),
    pytest.param(
        68049.31499999999, 7, 68049.32, id="a workbook's 1.5 * 45366.21 (was 68049.31)"
    ),
    pytest.param(
        0.30000000000000004, 17, 0.3, id="seventeen figures are fifteen (was itself)"
    ),
    pytest.param(
        12345678901234.25, 15, 12345678901234.3, id="a sixteen-digit tie goes away"
    ),
    pytest.param(2.5, 1, 3.0, id="a tie goes away from zero"),
    pytest.param(-102.5, 3, -103.0, id="a negative tie"),
    pytest.param(0.001234567, 3, 0.00123, id="a small value"),
    pytest.param(9.996, 3, 10.0, id="a carry to a fourth figure"),
    pytest.param(1.5e-22, 1, 2e-22, id="the least magnitude kept at one figure"),
    pytest.param(9.5e36, 1, 1e37, id="the greatest magnitude, carried to 10**37"),
]


@pytest.mark.parametrize(("value", "digits", "hand"), _CASES)
def test_a_double_keeps_its_fifteen_digit_figures_on_the_frame(
    value: float, digits: int, hand: float
) -> None:
    assert _ruled(value, digits) == hand
    assert _frame([value], digits) == [hand]


@pytest.mark.parametrize(("value", "digits", "hand"), _CASES)
def test_a_double_keeps_its_fifteen_digit_figures_in_the_reference_reader(
    value: float, digits: int, hand: float
) -> None:
    assert _reader(value, digits) == hand


def test_a_run_of_doubles_keeps_its_fifteen_digit_figures() -> None:
    """Per period: 0.15 is 0.2 and 781098 is 800000 at one figure, every period."""
    af = ActuarialFrame(pl.DataFrame({"x": [781098.0, 0.15]}))
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.y = af.x + af.month * 0.0
    af.r = af.y.round_sig_figs(1)

    assert af.collect()["r"].to_list() == [[800000.0] * 3, [0.2] * 3]


def test_null_nan_infinity_and_zero_are_their_own_answers() -> None:
    values = [None, math.nan, math.inf, -math.inf, 0.0, -0.0]
    got = _frame(values, 2)  # type: ignore[arg-type]

    assert got[0] is None
    assert math.isnan(got[1])
    assert got[2:] == [math.inf, -math.inf, 0.0, -0.0]
    assert math.copysign(1.0, got[5]) == -1.0


@pytest.mark.parametrize(
    ("value", "digits", "native"),
    [
        pytest.param(3e-24, 1, 3e-24, id="a residue where nought was meant"),
        pytest.param(-3e-24, 1, -3e-24, id="its negative"),
        pytest.param(1e-30, 3, 9.999999999999999e-31, id="far below"),
        pytest.param(
            9.9e-9, 15, 9.900000000000001e-09, id="below 1e-8 at fifteen figures"
        ),
        pytest.param(2e37, 2, 2.0000000000000001e37, id="past 1e37"),
        pytest.param(-1e300, 1, -1.0000000000000006e300, id="far past, negative"),
        pytest.param(5e-324, 1, 5e-324, id="the least subnormal"),
    ],
)
def test_a_double_outside_the_exact_range_takes_polars_own_route(
    value: float, digits: int, native: float
) -> None:
    """The run was refused there; it now answers what Polars' own rounding does."""
    assert pl.Series([value]).round_sig_figs(digits).to_list() == [native]
    assert _frame([1.0, value], digits)[1] == native


def test_a_run_holding_one_value_outside_the_range_answers_it() -> None:
    """A value far below the range rounds: the run no longer stops on it."""
    af = ActuarialFrame(pl.DataFrame({"x": [1.0, 2.0]}))
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.y = af.x * 10.0 ** (af.month * -20.0) * 3.0
    af.r = af.y.round_sig_figs(1)
    out = af.collect()
    far = [run[2] for run in out["y"].to_list()]

    # Inside the range the reading is exact; 3e-40 is Polars' own answer,
    # a unit in the last place from the reading's.
    assert [run[:2] for run in out["r"].to_list()] == [[3.0, 3e-20], [6.0, 6e-20]]
    assert [run[2] for run in out["r"].to_list()] == pl.Series(far).round_sig_figs(
        1
    ).to_list()


def test_the_reference_reader_stays_exact_where_the_engines_take_the_native_route() -> (
    None
):
    """11.1.12: the reader keeps the figures at every magnitude."""
    assert _reader(1e-30, 3) == 1e-30
    assert _reader(1.2345e-30, 3) == 1.23e-30
    assert _reader(2.25e300, 2) == 2.3e300


def _least_double_at_least(exact: Decimal) -> float:
    least = float(exact)
    return least if Decimal(least) >= exact else math.nextafter(least, math.inf)


@pytest.mark.parametrize("digits", [1, 3, 7, 14, 15, 17])
def test_the_range_bounds_are_exact(digits: int) -> None:
    """The least double at 10**(digits - 23) is read exactly; the one below natively.

    The same at the top: the greatest double below 10**37 is read exactly,
    and the least at or above it takes Polars' own route.
    """
    low = _least_double_at_least(Decimal(10) ** (min(digits, _HELD) - 23))
    high = _least_double_at_least(Decimal(10) ** 37)
    below_high = math.nextafter(high, 0.0)

    assert _frame([low, below_high], digits) == [
        _ruled(low, digits),
        _ruled(below_high, digits),
    ]
    for outside in (math.nextafter(low, 0.0), high):
        native = pl.Series([outside]).round_sig_figs(digits).to_list()
        assert _frame([outside], digits) == native


def test_a_whole_number_keeps_every_digit_a_double_does_not() -> None:
    """An i64 has no fifteen-digit reading: its sixteen figures are its own."""
    whole = ActuarialFrame(pl.DataFrame({"n": [12345678901234567, 781098]}))
    whole.r = whole.n.round_sig_figs(16)
    whole.s = whole.n.round_sig_figs(1)
    out = whole.collect()

    assert out["r"].to_list() == [12345678901234570, 781098]
    assert out["s"].to_list() == [10000000000000000, 800000]
    assert out["r"].dtype == pl.Int64
    assert _frame([12345678901234567.0], 16) == [12345678901234600.0]


def _sample(count: int, seed: int) -> list[tuple[float, int]]:
    """Values from 1e-24 to 1e38, one to seventeen figures, three in five near a half.

    Two in five lie within three units of their last place of a value whose
    sixteenth digit is a 5 -- where the fifteen-digit reading itself turns --
    and one in five at a half of the kept figures.
    """
    rng = random.Random(seed)  # noqa: S311 -- a reproducible sample, not a secret
    rows = []
    for _ in range(count):
        digits = rng.randint(1, 17)
        x = 10 ** rng.uniform(-24.0, 38.0)
        place = math.floor(math.log10(x))
        draw = rng.random()
        if draw < 0.4:
            sixteen = rng.randint(10**14, 10**15 - 1) * 10 + 5
            x = float(Decimal(sixteen).scaleb(place - 15))
        elif draw < 0.6:
            figures = min(digits, 14)
            kept = rng.randint(10 ** (figures - 1), 10**figures - 1) * 10 + 5
            x = float(Decimal(kept).scaleb(place - figures))
        for _ in range(abs(nudge := rng.randint(-3, 3))):
            x = math.nextafter(x, math.inf if nudge > 0 else -math.inf)
        rows.append((-x if rng.random() < 0.5 else x, digits))
    return rows


def _inside(x: float, digits: int) -> bool:
    exact = Decimal(abs(x))
    return Decimal(10) ** (min(digits, _HELD) - 23) <= exact < Decimal(10) ** 37


def test_a_sweep_matches_the_fifteen_digit_rule() -> None:
    """3,000 sampled values: the frame and the reader miss none inside the range."""
    rows = [row for row in _sample(3000, seed=93) if _inside(*row)]
    misses = []
    for digits in range(1, 18):
        values = [x for x, d in rows if d == digits]
        for x, got in zip(values, _frame(values, digits), strict=True):
            want = _ruled(x, digits)
            if got != want or _reader(x, digits) != want:
                misses.append((x, digits, got, want))

    assert len(rows) > 2000
    assert misses == []


def test_a_single_precision_value_is_read_by_its_double() -> None:
    """A Float32 book column arrives as the double it is exactly, and is rounded so.

    0.15f is 0.15000000596046448 as a double, so to one figure it is 0.2.
    """
    af = ActuarialFrame(
        pl.DataFrame({"x": pl.Series([0.15, 781098.0, 2.5], dtype=pl.Float32)})
    )
    af.r = af.x.round_sig_figs(1)
    out = af.collect()

    assert out.schema["r"] == pl.Float64
    assert out["r"].to_list() == [0.2, 800000.0, 3.0]


def test_a_value_whose_type_cannot_be_read_is_refused_by_name() -> None:
    """With no frame to type it, neither rounding rule can be chosen."""
    node = Call("round_sig_figs", (Col("x"),), (("digits", 2),))

    with pytest.raises(
        LoweringError, match="type of the value it rounds cannot be read"
    ):
        lower_polars(node, None)
