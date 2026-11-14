# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A compiled rollforward opens each state at a column or a number.

An opening value written as an expression was recorded through its display
text, which drops arguments: ``.round(2)`` and ``.round(0)`` print alike, so
two different machines shared one fingerprint and, in one process, the
second one compiled ran the first one's numbers. Such an opening is refused
at ``compile_rollforward``, under the state's name, with a move that runs.
"""

from __future__ import annotations

import datetime
from fractions import Fraction

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward

PERIODS = 3
RETURN = 0.01
OPENING = 100_000.4567


def _frame() -> ActuarialFrame:
    af = ActuarialFrame({"av_init": [OPENING], "fund_return": [[RETURN] * PERIODS]})
    return af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=PERIODS, frequency="monthly"
    )


def _compile(af: ActuarialFrame, opening: object):  # noqa: ANN202 - the compiled machine
    builder = af.projection.rollforward(states={"av": opening})
    builder["av"].grow(af["fund_return"], label="g")
    return compile_rollforward(builder)


def _first_period(af: ActuarialFrame, opening: object) -> tuple[str, float]:
    compiled = _compile(af, opening)
    af.av = compiled.expr_for("av")
    return compiled.fingerprint(), af.collect()["av"].to_list()[0][0]


def _hand(opening: float) -> float:
    """One period's growth, worked out in exact arithmetic."""
    return float(Fraction(opening) * (1 + Fraction(RETURN)))


@pytest.mark.parametrize("digits", [2, 0])
def test_an_opening_at_an_expression_is_refused_with_the_move(digits: int) -> None:
    af = _frame()
    with pytest.raises(NotImplementedError) as refused:
        _compile(af, pl.col("av_init").round(digits))
    message = str(refused.value)
    assert "The opening value of state 'av' is the expression" in message
    assert ".round(2) and .round(0) print alike" in message
    assert "af.av_open = <the expression>" in message
    assert "states={'av': af.av_open}" in message


def test_the_move_gives_each_rounding_its_own_model_and_its_own_number() -> None:
    # Both machines read the column av_open, so they are one machine; the
    # rounding is in that column's own line, so the models differ.
    results = {}
    for digits in (2, 0):
        af = _frame()
        af.av_open = af.av_init.round(digits)
        _, value = _first_period(af, af.av_open)
        results[digits] = (af.graph.fingerprint(), value)
    (fp2, v2), (fp0, v0) = results[2], results[0]
    assert fp2 != fp0
    assert v2 == pytest.approx(_hand(round(OPENING, 2)), rel=1e-15)
    assert v0 == pytest.approx(_hand(round(OPENING, 0)), rel=1e-15)
    assert round(v2, 4) == 101000.4646
    assert v0 == 101000.0


def test_an_expression_reading_no_column_names_the_number() -> None:
    af = _frame()
    with pytest.raises(NotImplementedError) as refused:
        _compile(af, pl.lit(500.0) * 2)
    assert "comes to 1000.0 for every policy" in str(refused.value)
    assert "states={'av': 1000.0}" in str(refused.value)
    _, value = _first_period(_frame(), 1000.0)
    assert value == pytest.approx(_hand(1000.0), rel=1e-15)


def test_a_frame_dependent_expression_is_given_no_number() -> None:
    af = _frame()
    with pytest.raises(NotImplementedError) as refused:
        _compile(af, pl.len().cast(pl.Float64))
    assert "comes to" not in str(refused.value)
    assert "af.av_open = <the expression>" in str(refused.value)


def test_arithmetic_over_a_running_balance_is_refused_by_name() -> None:
    af = _frame()
    builder = af.projection.rollforward(
        states={"av": af["av_init"], "shadow": pl.col("av@bop") * 2}
    )
    builder["av"].grow(af["fund_return"], label="g")
    with pytest.raises(NotImplementedError) as refused:
        compile_rollforward(builder)
    assert "'av@bop' is a running balance" in str(refused.value)


def test_an_underscored_state_is_moved_to_a_bracketed_column() -> None:
    af = _frame()
    builder = af.projection.rollforward(states={"_av": pl.col("av_init") * 1.0})
    builder["_av"].grow(af["fund_return"], label="g")
    with pytest.raises(NotImplementedError) as refused:
        compile_rollforward(builder)
    assert "states={'_av': af[\"_av_open\"]}" in str(refused.value)


@pytest.mark.parametrize(
    "opening",
    [
        pytest.param(pl.lit(pl.Series([1.0])), id="one-value-series"),
        pytest.param(pl.lit(pl.Series([1.0, 2.0])), id="two-value-series"),
        pytest.param(pl.lit(pl.Series([2.0])).alias("q"), id="aliased-series"),
    ],
)
def test_a_series_literal_is_refused(opening: pl.Expr) -> None:
    # It prints as "Series" whatever it holds, so [1.0] and [2.0] would
    # share one machine and the second would run the first's numbers.
    af = _frame()
    with pytest.raises(NotImplementedError) as refused:
        _compile(af, opening)
    assert "records without its values" in str(refused.value)
    assert "states={'av': 1000.0}" in str(refused.value)


def test_a_cast_column_is_refused_with_the_column_move() -> None:
    af = _frame()
    with pytest.raises(NotImplementedError) as refused:
        _compile(af, pl.col("av_init").cast(pl.Float32))
    assert "states={'av': af.av_open}" in str(refused.value)


@pytest.mark.parametrize(
    "opening",
    [
        pytest.param("column", id="column"),
        pytest.param(pl.col("av_init"), id="pl.col"),
        pytest.param(pl.col("av_init").alias("start"), id="aliased-column"),
        pytest.param(pl.lit(OPENING).alias("start"), id="aliased-number"),
        pytest.param(OPENING, id="float"),
        pytest.param(pl.lit(OPENING), id="pl.lit"),
    ],
)
def test_a_column_or_a_number_still_opens(opening: object) -> None:
    af = _frame()
    _, value = _first_period(af, af["av_init"] if isinstance(opening, str) else opening)
    assert value == pytest.approx(_hand(OPENING), rel=1e-15)
