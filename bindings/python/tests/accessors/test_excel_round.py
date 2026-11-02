# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Excel-style column rounding: the 15-digit value, half away from zero, list-aware.

There was no working way to round a per-period column (gh#68): polars'
``.round()`` raises on a list column, and the ``plugins.round`` wrapper
panicked on a Rust symbol that does not exist. ``.excel.round()`` provides
the working path, and names its convention: Excel's half away from zero,
the same rule as the rollforward's ``Round`` op — while polars' ``.round()``
keeps banker's rounding. The inconsistency of gh#70 becomes two documented
conventions, each requested explicitly.
"""

from __future__ import annotations

import math
import random
import struct
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward


def test_scalar_ties_round_away_from_zero() -> None:
    """0.125 -> 0.13 (Excel), not 0.12 (banker's); sign is preserved."""
    af = ActuarialFrame({"x": [0.125, -0.125, 7558.485]})
    af.rounded = af.x.excel.round(2)
    out = af.collect()
    assert out.get_column("rounded").to_list() == [0.13, -0.13, 7558.49]


def test_list_column_rounds_element_wise() -> None:
    """The gh#68 case: a per-period list column, rounded to cents."""
    af = ActuarialFrame({"coi": [[10.125, 7558.485], [0.005, -0.005]]})
    af.rounded = af.coi.excel.round(2)
    out = af.collect()
    assert out.get_column("rounded").to_list() == [
        [10.13, 7558.49],
        [0.01, -0.01],
    ]


def test_default_rounds_to_whole_units() -> None:
    af = ActuarialFrame({"x": [2.5, -2.5, 2.4]})
    af.rounded = af.x.excel.round()
    out = af.collect()
    assert out.get_column("rounded").to_list() == [3.0, -3.0, 2.0]


def test_negative_digits_round_left_of_the_decimal() -> None:
    """ROUND(1250, -2) = 1300 — Excel's negative num_digits."""
    af = ActuarialFrame({"face": [1250.0, 1249.0, -1250.0]})
    af.banded = af.face.excel.round(-2)
    out = af.collect()
    assert out.get_column("banded").to_list() == [1300.0, 1200.0, -1300.0]


def test_polars_native_round_still_bankers() -> None:
    """The two conventions coexist, each by name — polars stays half-to-even."""
    assert pl.select(pl.lit(0.125).round(2)).item() == 0.12


def test_matches_the_rollforward_round_op() -> None:
    """Column-side excel.round and the kernel's Round op are the same rule.

    Grow a balance, round it in the kernel each period; reproduce the same
    figures column-side from the unrounded closing balances' inputs. The two
    surfaces must agree to the cent on the tie-heavy rate chosen here.
    """
    af = ActuarialFrame({"p": [1], "init": [1000.0], "rate": [[0.0125] * 3]})
    af = af.projection.set(
        start_date=date(2025, 12, 31), n_periods=3, frequency="annual"
    )
    rf = af.projection.rollforward(states={"av": af["init"]})
    rf["av"].grow(af["rate"])
    rf["av"].round(2)
    af.kernel = compile_rollforward(rf).expr_for("av")
    out = af.collect()

    balance = 1000.0
    expected = []
    for _ in range(3):
        grown = ActuarialFrame({"x": [balance * 1.0125]})
        grown.r = grown.x.excel.round(2)
        balance = grown.collect().get_column("r").to_list()[0]
        expected.append(balance)
    assert out.get_column("kernel").to_list()[0] == expected


def test_dead_plugin_wrappers_are_gone() -> None:
    """floor/round/round_to_int panicked on a missing Rust symbol; they are
    removed rather than left as landmines.
    """
    from gaspatchio.frame.lowering._polars import plugins

    assert not hasattr(plugins, "round")
    assert not hasattr(plugins, "round_to_int")
    assert not hasattr(plugins, "floor")
    with pytest.raises(ImportError):
        # The import IS the assertion: the dead wrapper must stay gone, so
        # importing it must fail. Not unused, not dead — do not "fix" it away.
        from gaspatchio.frame.lowering._polars.plugins import round  # noqa: A004, F401


def test_composed_list_expression_rounds_element_wise() -> None:
    """A composed per-period expression must take the element-wise path.

    The shape gate keys off ``shape``, not the proxy's concrete type, so a
    list-valued ExpressionProxy (here ``coi * factor``) rounds inside the
    list rather than hitting scalar ``Expr.round`` and failing at collect.
    """
    af = ActuarialFrame({"coi": [[10.124, 7558.484]], "factor": [1.0001]})
    af.rounded = (af.coi * af.factor).excel.round(2)
    out = af.collect()
    assert out.get_column("rounded").to_list() == [[10.13, 7559.24]]


def test_extreme_negative_digits_round_to_zero() -> None:
    """ROUND(x, -309) is 0 for every finite float — not an OverflowError.

    10**309 is not representable, but no finite value is within half of it
    (max double is under 1.8e308), so the result is exactly zero, sign
    normalised; nulls stay null.
    """
    af = ActuarialFrame({"x": [1.7e308, -1.7e308, 123.45, None]})
    af.rounded = af.x.excel.round(-309)
    af.rounded_more = af.x.excel.round(-400)
    out = af.collect()
    assert out.get_column("rounded").to_list() == [0.0, 0.0, 0.0, None]
    assert out.get_column("rounded_more").to_list() == [0.0, 0.0, 0.0, None]


# --- Excel rounds the value's 15-significant-digit decimal -------------


def _excel_round(value: float, num_digits: int) -> float:
    """Excel's ROUND, written from the rule with exact decimals.

    Take the double's exact decimal expansion to 15 significant digits (a
    sixteenth digit of 5 or more going away from zero), round that to
    ``num_digits`` places half away from zero, and read back the nearest
    double with the input's sign. Shares nothing with the kernel.
    """
    if not math.isfinite(value) or value == 0.0:
        return value
    with localcontext() as context:
        context.prec = 2000
        exact = Decimal(value)
        unit = exact.adjusted() - 14
        held = exact.quantize(Decimal(1).scaleb(unit), rounding=ROUND_HALF_UP)
        if unit < -num_digits:
            held = held.quantize(Decimal(1).scaleb(-num_digits), rounding=ROUND_HALF_UP)
        answer = float(held)
    if math.isinf(answer):
        answer = abs(value)
    return math.copysign(abs(answer), value)


def _rounded(values: list[float], num_digits: int) -> list[float]:
    af = ActuarialFrame(pl.DataFrame({"x": pl.Series(values, dtype=pl.Float64)}))
    af.r = af.x.excel.round(num_digits)
    return af.collect()["r"].to_list()


@pytest.mark.parametrize(
    ("value", "num_digits", "excel"),
    [
        # UniversalLife.xlsx 'Account Values -- Type B'!O19 = ROUND(1.5*K19, 2),
        # K19 = 45366.20999999999: the double is 68049.31499999999...
        (1.5 * 45366.20999999999, 2, 68049.32),
        # 80725.665 in decimal, 80725.66499999999... as a double.
        (0.5 * 161451.33, 2, 80725.67),
        # 'Account Values -- Type A'!Q74: interest on 5657268.499999999 at 3%.
        (5657268.499999999 * 0.03, 2, 169718.06),
        # Doubles just under their decimal ties.
        (2.675, 2, 2.68),
        (1.005, 2, 1.01),
        (-1.005, 2, -1.01),
        (0.49999999999999994, 0, 1.0),
        # The fifteen digits are what Excel holds: 0.30000000000000004 is 0.3.
        (0.1 + 0.2, 17, 0.3),
    ],
)
def test_excel_rounds_the_fifteen_digit_value(
    value: float, num_digits: int, excel: float
) -> None:
    """The workbook's own cached values, which a rounding of the double missed."""
    assert _rounded([value], num_digits) == [excel]


def test_the_room_value_round_sig_figs_could_not_reach() -> None:
    """0.5 * 161451.33 is below its decimal tie in binary at every width.

    A conversion tried ``round_sig_figs(15)`` first; rounding in binary to
    fifteen figures does not reach the decimal tie, so only the decimal rule
    gives Excel's 80725.67 -- and ``.excel.round`` applies it on its own.
    """
    af = ActuarialFrame({"x": [0.5 * 161451.33]})
    af.r = af.x.excel.round(2)
    assert af.collect()["r"].to_list() == [80725.67]


def test_magnitudes_past_fifteen_digits_answer_the_fifteen_digit_value() -> None:
    """Where the 15 digits are coarser than the step, ROUND has nothing left."""
    assert _rounded([12345678901234.25], 2) == [12345678901234.3]
    assert _rounded([999_999_999_999_999.5], 0) == [1e15]
    assert _rounded([-123_456_789_012_345_678.0], -2) == [-1.23456789012346e17]
    assert _rounded([1.7976931348623157e308], 0) == [1.7976931348623157e308]


def test_signs_and_non_finite_values() -> None:
    out = _rounded([-0.001, -0.0, math.nan, math.inf, -math.inf], 2)
    assert [math.copysign(1.0, v) for v in out[:2]] == [-1.0, -1.0]
    assert math.isnan(out[2])
    assert out[3:] == [math.inf, -math.inf]


def test_whole_numbers_answer_doubles_as_the_clause_states() -> None:
    """Section 11.1.35: the output cells are Float64, whatever the places.

    A whole-number column rounded at places after the point used to come back
    Int64, where the clause and the JAX engine answer Float64.
    """
    af = ActuarialFrame({"n": [1250, -1249]})
    af.kept = af.n.excel.round(2)
    af.banded = af.n.excel.round(-2)
    af.per_period = af.n.excel.round(0)
    out = af.collect()
    assert out.schema["kept"] == pl.Float64
    assert out["kept"].to_list() == [1250.0, -1249.0]
    assert out["banded"].to_list() == [1300.0, -1200.0]
    lists = ActuarialFrame({"n": [[1, 2], [3]]})
    lists.r = lists.n.excel.round(1)
    collected = lists.collect()
    assert collected.schema["r"] == pl.List(pl.Float64)
    assert collected["r"].to_list() == [[1.0, 2.0], [3.0]]


def _corpus(seed: int, size: int) -> list[tuple[float, int]]:
    """Return values a binary rounding gets wrong, beside ordinary ones.

    Decimal ties nudged a few ulps either way, workbook-style products,
    random doubles over wide magnitudes, quarter values at 1e12 to 1e15
    whose sixteenth digit is an exact tie, and magnitudes past 1e15.
    """
    rng = random.Random(seed)  # noqa: S311 -- a reproducible corpus, not a secret
    cases: list[tuple[float, int]] = []
    for _ in range(size):
        kind = rng.random()
        digits = rng.randint(-10, 10)
        if kind < 0.3:
            whole = rng.randint(0, 10 ** rng.randint(1, 14))
            tie = (
                (whole + 0.5) / 10**digits
                if digits >= 0
                else (whole + 0.5) * 10**-digits
            )
            bits = struct.unpack("<q", struct.pack("<d", tie))[0] + rng.randint(-40, 40)
            value = struct.unpack("<d", struct.pack("<q", bits))[0]
        elif kind < 0.5:
            amount = round(rng.uniform(0, 1e7), rng.randint(0, 4))
            value = amount * rng.choice([0.5, 1.5, 0.03, 0.032, 1.1, 0.07 / 12, 3.0])
        elif kind < 0.7:
            value = math.ldexp(rng.random() + 0.5, rng.randint(-60, 90))
        elif kind < 0.85:
            value = rng.randint(10**12, 10**15) + rng.choice([0.25, 0.5, 0.75])
            digits = rng.randint(-3, 3)
        else:
            value = rng.uniform(1e13, 1e17)
            digits = rng.randint(-3, 3)
        cases.append((-value if rng.random() < 0.5 else value, digits))
    return cases


def test_a_randomised_corpus_agrees_with_the_written_rule() -> None:
    """40,000 values against the rule, computed in exact decimals.

    Grouped by digits so each group is one column through the kernel; the
    comparison is bit for bit, a zero's sign included.
    """
    by_digits: dict[int, list[float]] = {}
    for value, digits in _corpus(seed=80, size=40_000):
        by_digits.setdefault(digits, []).append(value)
    wrong = []
    for digits, values in by_digits.items():
        for value, got in zip(values, _rounded(values, digits), strict=True):
            want = _excel_round(value, digits)
            if struct.pack("<d", got) != struct.pack("<d", want):
                wrong.append((value, digits, got, want))
    assert not wrong, wrong[:10]


def test_excel_round_and_the_kernel_round_are_one_rule() -> None:
    """A column rounding and a rollforward rounding agree on the corpus.

    One period per value: the kernel's ``Round`` on a balance opened at the
    value, against ``.excel.round`` on the same value, at 2 places.
    """
    values = [value for value, _ in _corpus(seed=81, size=2_000)]
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "p": list(range(len(values))),
                "init": values,
                "rate": [[0.0]] * len(values),
            }
        )
    )
    af = af.projection.set(
        start_date=date(2025, 12, 31), n_periods=1, frequency="annual"
    )
    rf = af.projection.rollforward(states={"av": af["init"]})
    rf["av"].grow(af["rate"])
    rf["av"].round(2)
    af.kernel = compile_rollforward(rf).expr_for("av")
    af.column = af.init.excel.round(2)
    out = af.collect()
    kernel = [row[0] for row in out["kernel"].to_list()]
    assert kernel == out["column"].to_list()
