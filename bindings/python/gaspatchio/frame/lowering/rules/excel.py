# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars lowerings for the ``excel`` and ``date`` accessors.

The Excel-compatibility surface an actuary reaches for by name --
``yearfrac``, ``irr``, ``pv``, ``round``, ``days``, ``edate``,
``eomonth``, and the serial-date conversion that has to reproduce Excel's
1900 leap-year bug -- plus the two date-namespace conversions. Each rule
is the accessor method's own former body; the Excel semantics themselves
live in ``frame/lowering/_excel/``, which these call exactly as the
accessors did. The original function imports remain compatibility aliases.
"""

from __future__ import annotations

import datetime
import re
from typing import TYPE_CHECKING, cast

import polars as pl

from gaspatchio._semantic.ir import Col
from gaspatchio.frame.lowering import kinds
from gaspatchio.frame.lowering._polars.validation import (
    checked_integer_refusal,
    require_valid_rows,
)
from gaspatchio.frame.lowering.polars import lower_arg, register_lowering

if TYPE_CHECKING:
    from polars._typing import ClosedInterval

    from gaspatchio._semantic.ir import AttrValue, Call
    from gaspatchio.frame.lowering.context import LoweringContext

# Excel counts days from the day before 1900-01-01 on the 1900 system, and
# from 1904-01-01 on the Mac system.
_EPOCH_1900 = datetime.date(1899, 12, 30)
_EPOCH_1904 = datetime.date(1904, 1, 1)

# Serial 60 is Excel's phantom 1900-02-29, a date that never existed.
_PHANTOM_LEAP_SERIAL = 60


def _attrs(node: Call) -> dict[str, AttrValue]:
    """Read a call's typed configuration back as a dict."""
    return dict(node.attrs)


def _text(node: Call, key: str) -> str:
    """Read a string attribute, refusing anything else.

    Emission validates these already; the check is here so a
    hand-constructed node cannot smuggle the wrong type past the rule and
    fail somewhere less legible inside Polars.
    """
    value = _attrs(node)[key]
    if not isinstance(value, str):
        msg = f"{node.name}: {key!r} must be a string, got {value!r}"
        raise TypeError(msg)
    return value


def _count(node: Call, key: str, *, optional: bool = False) -> int | None:
    """Read a whole-number attribute (a digit count, an annuity type)."""
    value = _attrs(node)[key]
    if value is None and optional:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{node.name}: {key!r} must be a whole number, got {value!r}"
        raise TypeError(msg)
    return value


@register_lowering("excel.from_excel_serial")
def _lower_from_excel_serial(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Turn an Excel serial day number into a real date.

    On the 1900 system Excel believes 1900 was a leap year, so serials 1-59
    sit one day behind the true offset and serial 60 names a day that never
    existed. Serials 1-59 therefore add one compensating day, serial 60
    maps to the real 28 February 1900 (the same date as 59), and serials
    past 60 map directly. Below 1 there is no date at all, on either
    system -- serial 0 on the 1904 system is a time of day, not a date.
    """
    epoch = _text(node, "epoch")
    (base_expr,) = _per_policy_operands(node, ctx)
    numeric_expr = base_expr.cast(pl.Float64, strict=False)

    if epoch == "1904":
        return (
            pl.when(numeric_expr < 1)
            .then(None)
            .otherwise(pl.lit(_EPOCH_1904) + pl.duration(days=numeric_expr))
            .cast(pl.Date)
        )

    int_expr = numeric_expr.floor()
    effective_serial_days = (
        pl.when(numeric_expr > _PHANTOM_LEAP_SERIAL)
        .then(numeric_expr)
        .otherwise(numeric_expr + 1)
    )
    return (
        pl.when(numeric_expr < 1)
        .then(None)
        .when(int_expr == _PHANTOM_LEAP_SERIAL)
        .then(pl.lit(datetime.date(1900, 2, 28)))
        .otherwise(pl.lit(_EPOCH_1900) + pl.duration(days=effective_serial_days))
        .cast(pl.Date)
    )


@register_lowering("excel.yearfrac")
def _lower_yearfrac(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Year fraction between two dates on one of Excel's day-count bases."""
    from gaspatchio.frame.lowering._excel.yearfrac import yearfrac  # noqa: PLC0415

    basis = _attrs(node)["basis"]
    if not isinstance(basis, (str, int)) or isinstance(basis, bool):
        msg = f"yearfrac: 'basis' must be a day-count basis, got {basis!r}"
        raise TypeError(msg)
    start_expr, _ = lower_arg(node.args[0], ctx)
    end_expr, _ = lower_arg(node.args[1], ctx)
    return yearfrac(start_expr, end_expr, basis=basis)


@register_lowering("excel.irr")
def _lower_irr(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Solve for the internal rate of return over a per-period cashflow column.

    A starting guess is optional, and *absent* is not the same as a guess
    of null -- the solver seeds itself differently. So the guess is a node
    argument when one was given and simply not there when it was not,
    rather than a null literal standing in for both.
    """
    from gaspatchio.frame.lowering._excel.irr import irr  # noqa: PLC0415

    default_guess = _attrs(node)["default_guess"]
    if isinstance(default_guess, (str, bool)):
        msg = f"irr: 'default_guess' must be a number, got {default_guess!r}"
        raise TypeError(msg)
    values_expr, _ = lower_arg(node.args[0], ctx)
    guess_expr = None
    if len(node.args) > 1:
        guess_expr, guess_shape = lower_arg(node.args[1], ctx)
        if guess_shape == "list":
            raise kinds.shape_refusal(
                line="excel.irr()",
                does="seeds its solver with one guess for each policy's stream",
                clause="11.1.36",
                operand=node.args[1],
                holds=kinds.PER_PERIOD,
                move="Write the guess once per policy.",
            )
    return irr(values_expr, guess=guess_expr, default_guess=default_guess)


@register_lowering("excel.pv")
def _lower_pv(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Present value of a level annuity, Excel's ``PV``."""
    from gaspatchio.frame.lowering._excel.pv import pv  # noqa: PLC0415

    fv = _attrs(node)["fv"]
    if isinstance(fv, (str, bool)):
        msg = f"pv: 'fv' must be a number, got {fv!r}"
        raise TypeError(msg)
    rate_expr, _ = lower_arg(node.args[0], ctx)
    nper_expr, _ = lower_arg(node.args[1], ctx)
    pmt_expr, _ = lower_arg(node.args[2], ctx)
    return pv(
        rate_expr,
        nper_expr,
        pmt_expr,
        fv=fv,
        typ=_count(node, "typ", optional=True),
    )


@register_lowering("excel.round")
def _lower_round(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Round as Excel does: the 15-digit value, half away from zero.

    The kernel rounds a per-policy column and a per-period one alike, element
    by element, so the shape needs no branch here.
    """
    from gaspatchio.frame.lowering._excel.round import (  # noqa: PLC0415
        round as excel_round,
    )

    num_digits = _count(node, "num_digits")
    assert num_digits is not None  # noqa: S101
    base_expr, _shape = lower_arg(node.args[0], ctx)
    return excel_round(base_expr, num_digits)


@register_lowering("excel.days")
def _lower_days(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Whole days between two dates, Excel's ``DAYS``."""
    from gaspatchio.frame.lowering._excel.days import days  # noqa: PLC0415

    end_expr, start_expr = _per_policy_operands(node, ctx)
    return days(end_expr, start_expr)


@register_lowering("excel.edate")
def _lower_edate(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Move a date a whole number of months, keeping the day of the month."""
    from gaspatchio.frame.lowering._excel.edate import edate  # noqa: PLC0415

    start_expr, months_expr = _month_move_operands(node, "edate", ctx)
    return edate(start_expr, months_expr)


@register_lowering("excel.eomonth")
def _lower_eomonth(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Move a date a whole number of months, then take that month's last day."""
    from gaspatchio.frame.lowering._excel.eomonth import eomonth  # noqa: PLC0415

    start_expr, months_expr = _month_move_operands(node, "eomonth", ctx)
    return eomonth(start_expr, months_expr)


def _month_move_operands(
    node: Call, name: str, ctx: LoweringContext | None
) -> tuple[pl.Expr, pl.Expr]:
    """Return a month move's date and its whole months, or refuse the line."""
    start_expr, months_expr = _per_policy_operands(node, ctx)
    return start_expr, _whole_months(node, name, months_expr, ctx)


# Section 11.1.33 states every operation in it but excel.yearfrac over one
# value per policy. Each entry is what the operation reads for each policy and
# the move a per-period operand is refused with.
_RUN_OF_DATES = (
    "for a date in every period, build the run of dates from the start date "
    "with date.date_ranges(...)."
)
_PER_POLICY_READING: dict[str, tuple[str, str]] = {
    "excel.edate": (
        "moves one date by one count of months",
        f"Move a per-policy date by a per-policy count of months; {_RUN_OF_DATES}",
    ),
    "excel.eomonth": (
        "moves one date by one count of months",
        f"Move a per-policy date by a per-policy count of months; {_RUN_OF_DATES}",
    ),
    "date.offset_by": (
        "moves one date by its duration",
        f"Move a per-policy date; {_RUN_OF_DATES}",
    ),
    "date.months_between": (
        "counts the months from one start date to one end date",
        (
            "Count between per-policy dates; for the months elapsed at every "
            "period, add the timeline's own month count (af.month) to that "
            "per-policy count."
        ),
    ),
    "excel.days": (
        "counts the days from one start date to one end date",
        (
            "Count between per-policy dates; for the time elapsed to a date in "
            "every period, excel.yearfrac(...) reads one."
        ),
    ),
    "date.to_period": (
        "snaps one date to the start of its period",
        (
            "Snap a per-policy date; for the start of every period's month, "
            "build the run of dates with date.date_ranges(...) from a snapped "
            "start date."
        ),
    ),
    "date.date_ranges": (
        "builds one run of dates from one start date to one end date",
        "Build the run from a per-policy start date and a per-policy end date.",
    ),
    "excel.from_excel_serial": (
        "converts one spreadsheet serial to a date",
        f"Convert a per-policy serial; {_RUN_OF_DATES}",
    ),
}


def _per_policy_operands(node: Call, ctx: LoweringContext | None) -> list[pl.Expr]:
    """Return a calendar operation's operands, refusing one held per period.

    Section 11.1.33 states these operations for one value per policy. An
    operand held per period failed when the frame ran, in Polars' words
    (``cannot cast List type``, ```year` operation not supported``), naming
    neither the line nor a way through; it is refused where the line is
    written, with the operation's own move.
    """
    lowered = [lower_arg(argument, ctx) for argument in node.args]
    for operand, (_expr, shape) in zip(node.args, lowered, strict=True):
        if shape == "list":
            reads, move = _PER_POLICY_READING[node.name]
            msg = (
                f"{node.name}() {reads} for each policy (11.1.33), and "
                f"{kinds.shown(operand)} holds one value per period, so the "
                f"line is refused. {move}"
            )
            raise ValueError(msg)
    return [expr for expr, _shape in lowered]


# The largest magnitude a double holds every whole number below, as a double.
_I64_BOUND = float(2**63)


def _whole_months(
    node: Call, name: str, months: pl.Expr, ctx: LoweringContext | None
) -> pl.Expr:
    """Return a month move's months as whole numbers, refusing any that are not.

    Section 11.1.33 moves a date "a signed whole number m" of months, for
    ``excel.edate`` and ``excel.eomonth`` alike. A double or decimal that is
    a whole number is that number on every side; one that is not was
    truncated (1.5 months moved one), text was parsed ("2" moved two, "1.5"
    answered a silent null) and a flag moved one, where the JAX engine
    refused all of them. A count that is not a whole number is refused by
    value, as a whole-number conversion refuses it (11.1.23), and text or a
    flag by kind; a null stays null.
    """
    operand = node.args[1]
    dtype = kinds.operand_dtype(operand, months, ctx)
    if dtype is None or dtype == pl.Null:
        return months
    if dtype == pl.Boolean or not dtype.is_numeric():
        msg = (
            f"excel.{name}() moves a date a whole number of months, and "
            f"{kinds.shown(operand)} is {kinds.describe(dtype)} -- not a count "
            "of months (11.1.33). Text read as a number and a flag read as 0 or "
            "1 are conversions the formula never wrote, so the line is refused. "
            "Convert the months where they are loaded, to the whole number "
            "they stand for (.to_integer() over a number)."
        )
        raise TypeError(msg)
    if dtype.is_integer():
        return months
    column = operand.name if isinstance(operand, Col) else None
    refusal = checked_integer_refusal(column)
    whole = _whole_or_null(months)
    held = months.cast(pl.Float64).cast(pl.Int64, strict=False)
    return pl.when(require_valid_rows(whole, message=refusal) == 0).then(held)


def _whole_or_null(value: pl.Expr) -> pl.Expr:
    """Test for a null, or a finite whole number inside ``i64``, read as a double."""
    number = value.cast(pl.Float64)
    return value.is_null() | (
        number.is_finite()
        & (number == number.floor())
        & (number.abs() < pl.lit(_I64_BOUND))
    ).fill_null(value=False)


# Actuarial period labels, in the Polars interval spelling. Anything the
# map does not know is passed through as written, so a caller who already
# speaks Polars' interval language is not blocked.
_PERIOD_INTERVAL: dict[str, str] = {"Y": "1y", "M": "1mo", "W": "1w", "D": "1d"}

# An interval Polars reads: one or more counts, each with its unit. Anything
# else failed when the frame ran, in Polars' words ("expected leading integer
# in the duration string"), and is refused where the line is written.
_POLARS_INTERVAL = re.compile(r"(?:\d+(?:ns|us|ms|mo|s|m|h|d|w|q|y|i))+")


@register_lowering("date.to_period")
def _lower_to_period(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Snap a date back to the start of the period that contains it."""
    freq = _text(node, "freq")
    (base_expr,) = _per_policy_operands(node, ctx)
    interval = _PERIOD_INTERVAL.get(freq.upper(), freq)
    if _POLARS_INTERVAL.fullmatch(interval) is None:
        msg = (
            f"date.to_period() snaps a date to the start of its year, month, "
            f"week or day (11.1.33), and freq={freq!r} names none of them, so "
            "the line is refused. Write freq as Y, M, W or D; an interval "
            "written with its count -- '1q' for a quarter, '3mo' -- is answered "
            "here outside that entry."
        )
        raise ValueError(msg)
    return base_expr.dt.truncate(interval).cast(pl.Date)


@register_lowering("date.months_between")
def _lower_months_between(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Whole months from one date to another, counted on the calendar.

    Year and month only: 31 January to 1 February is one month, the same
    answer a policy-duration count gives. Day of month plays no part.
    """
    start_expr, end_expr = _per_policy_operands(node, ctx)
    return (end_expr.dt.year() - start_expr.dt.year()) * 12 + (
        end_expr.dt.month() - start_expr.dt.month()
    )


@register_lowering("date.offset_by")
def _lower_offset_by(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Shift a date by a calendar duration such as ``"1mo"`` or ``"-3d"``."""
    duration = _text(node, "duration")
    (base_expr,) = _per_policy_operands(node, ctx)
    return base_expr.dt.offset_by(duration)


@register_lowering("date.date_ranges")
def _lower_date_ranges(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Build one list of dates per row, from a start date to an end date."""
    start_expr, end_expr = _per_policy_operands(node, ctx)
    return pl.date_ranges(
        start=start_expr,
        end=end_expr,
        interval=_text(node, "interval"),
        closed=cast("ClosedInterval", _text(node, "closed")),
        eager=False,
    )
