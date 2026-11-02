# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""On a column accessor, a bare string operand is refused.

Frame-level methods name a column by string -- ``af.date.create_timeline``,
``af.date.add_duration("issue_date", "1y")``, ``af.finance.present_value`` --
the way ``rename`` and ``drop`` do. On a column accessor the operand is the
other half of a formula, so a string there is genuinely ambiguous:
``af.issue_date.excel.edate("months")`` could mean the ``months`` column or the
literal text. Rather than silently producing nulls, the call is refused, and the
message names both spellings: the column, and a value.

One voice, but never a remedy the next line refuses. The value half names
what the parameter itself accepts: a date for a date formula, a number for a
numeric one, ``discount_rate=`` for a factor that is one value per period and
has no single-number form at all. A period override goes further still --
it is exactly one number, so a column is not among its answers and it is not
offered one.
"""

import datetime
from collections.abc import Callable

import pytest

from gaspatchio import ActuarialFrame


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        {
            "start": [datetime.date(2023, 1, 1)],
            "end": [datetime.date(2024, 1, 1)],
            "months": [6],
            "rate": [0.05],
            "nper": [10.0],
            "pmt": [1000.0],
            "av_init": [1000.0],
            "growth": [[1.01, 1.01, 1.01]],
            "net_flow": [[10.0, 10.0, 10.0]],
            "benefit": [[100.0, 100.0, 100.0]],
            "v_t": [[0.95, 0.91, 0.86]],
        }
    )


# The value half of the message is per-parameter: it offers only what the
# parameter itself accepts. A date is a real operand for the excel and date
# formulas; on a numeric one it is not, so those rows say so.
_DATE_OR_NUMBER = "a number or a datetime.date"
_NUMBER = "a number"


@pytest.mark.parametrize(
    ("call", "parameter", "offending", "value_phrase"),
    [
        (
            lambda af: af.start.excel.edate("months"),
            "months",
            "months",
            _DATE_OR_NUMBER,
        ),
        (
            lambda af: af.start.excel.eomonth("months"),
            "months",
            "months",
            _DATE_OR_NUMBER,
        ),
        (lambda af: af.end.excel.days("start"), "start_date", "start", _DATE_OR_NUMBER),
        (
            lambda af: af.start.excel.yearfrac("end"),
            "end_date_expr",
            "end",
            _DATE_OR_NUMBER,
        ),
        (lambda af: af.rate.excel.pv("nper", af.pmt), "nper", "nper", _DATE_OR_NUMBER),
        (lambda af: af.rate.excel.pv(af.nper, "pmt"), "pmt", "pmt", _DATE_OR_NUMBER),
        (lambda af: af.rate.excel.irr(guess="rate"), "guess", "rate", _DATE_OR_NUMBER),
        (
            lambda af: af.start.date.months_between("end"),
            "other",
            "end",
            _DATE_OR_NUMBER,
        ),
        (
            lambda af: af.pmt.finance.discount("rate", af.nper),
            "rate_expr",
            "rate",
            _DATE_OR_NUMBER,
        ),
        (
            lambda af: af.pmt.finance.discount(af.rate, "nper"),
            "n_periods_expr",
            "nper",
            _DATE_OR_NUMBER,
        ),
        (
            lambda af: af.growth.projection.accumulate(
                initial="av_init", multiplier=af.growth, addend=af.net_flow
            ),
            "initial",
            "av_init",
            _NUMBER,
        ),
        (
            lambda af: af.growth.projection.accumulate(
                initial=af.av_init, multiplier="growth", addend=af.net_flow
            ),
            "multiplier",
            "growth",
            _NUMBER,
        ),
        (
            lambda af: af.growth.projection.accumulate(
                initial=af.av_init, multiplier=af.growth, addend="net_flow"
            ),
            "addend",
            "net_flow",
            _NUMBER,
        ),
        (
            lambda af: af.benefit.projection.prospective_value(discount_rate="rate"),
            "discount_rate",
            "rate",
            _NUMBER,
        ),
    ],
    ids=[
        "excel.edate",
        "excel.eomonth",
        "excel.days",
        "excel.yearfrac",
        "excel.pv-nper",
        "excel.pv-pmt",
        "excel.irr-guess",
        "date.months_between",
        "finance.discount-rate",
        "finance.discount-periods",
        "projection.accumulate-initial",
        "projection.accumulate-multiplier",
        "projection.accumulate-addend",
        "projection.prospective_value-rate",
    ],
)
def test_a_bare_string_operand_is_refused_at_the_call(
    call: Callable[[ActuarialFrame], object],
    parameter: str,
    offending: str,
    value_phrase: str,
) -> None:
    """The refusal is at the call, names the parameter, and shows both spellings."""
    af = _frame()

    with pytest.raises(TypeError, match=r'af\["\w+"\]') as excinfo:
        call(af)

    message = str(excinfo.value)
    assert parameter in message
    assert "bare string" in message
    # The string the caller actually wrote, and every way out of the
    # ambiguity: both column spellings, and the value forms this parameter
    # will actually take.
    assert repr(offending) in message
    assert f'af["{offending}"]' in message
    assert f"(or af.{offending})" in message
    assert f"for a value, pass {value_phrase}." in message
    # The rule the message states is the one the framework keeps: the
    # refusal is on the column accessor, and naming a column by string is
    # what the frame-level methods are for.
    assert "on a column accessor it is the operand" in message
    assert "frame-level idiom" in message


def test_a_discount_factor_is_offered_the_column_or_the_rate_argument() -> None:
    """A factor is per-period, so the remedy does not offer a single number.

    ``prospective_value`` refuses a numeric ``discount_factor`` outright --
    one number there is a rate somebody put in the wrong argument -- so
    the shared "pass a number" half would be a remedy that fails on the
    next line. The message says what is true instead.
    """
    af = _frame()

    with pytest.raises(TypeError) as excinfo:
        af.benefit.projection.prospective_value(discount_factor="v_t")

    message = str(excinfo.value)
    assert "discount_factor='v_t' is a bare string" in message
    assert 'af["v_t"]' in message
    assert "(or af.v_t)" in message
    # The value half names the argument a constant belongs in, not a number
    # this one would accept.
    assert "discount_rate=" in message
    assert "one value per period" in message
    assert "a number or a datetime.date" not in message


@pytest.mark.parametrize(
    ("call", "parameter"),
    [
        (
            lambda af: af.growth.projection.with_period(1, value="net_flow"),
            "value",
        ),
        (
            lambda af: af.growth.projection.with_periods({1: "net_flow"}),
            "updates[1]",
        ),
    ],
    ids=["projection.with_period", "projection.with_periods"],
)
def test_a_period_override_is_a_number_and_never_a_column(
    call: Callable[[ActuarialFrame], object], parameter: str
) -> None:
    """An override replaces one period with one number, so a column is not it."""
    af = _frame()

    with pytest.raises(TypeError) as excinfo:
        call(af)

    message = str(excinfo.value)
    assert message.startswith(f"{parameter}='net_flow' is a bare string")
    assert "an int or a float" in message
    assert "A column cannot be an override here" in message
    # A conditional is where a per-policy replacement belongs, so that is
    # the next move the message names.
    assert "when(" in message
    # The column spelling the operand refusal offers would be false here,
    # so it is not offered.
    assert 'af["net_flow"]' not in message
