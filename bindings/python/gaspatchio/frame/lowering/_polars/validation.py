# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Vectorized runtime checks that remain inside the lazy expression plan."""

from __future__ import annotations

import polars as pl

# The one channel a lazy plan has for refusing a row is an operation it can be
# made to fail, so a refusal travels as a string that will not cast and Polars
# reports it as a type-conversion failure with the sentence buried in the list
# of values it could not convert. That is not a message anybody should have to
# read, so the frame's error door lifts the sentence back to the first line
# (``_lift_plan_refusal``). Two spellings of one text would break that lift
# silently, so each text lives here, once, and the door reads them from here.
STORED_PREDICATE_RULE = (
    "stored numeric predicate must be non-null, finite and exactly 0.0 or 1.0"
)

CHECKED_INTEGER_RULE = "invalid value for checked Int64 conversion"

CHECKED_FLOAT_RULE = "invalid value for checked Float64 conversion"

INTEGER_RANGE_RULE = "integer value outside the checked Int64 range"

WIDE_ARITHMETIC_RULE = "integer wider than Int64 read by arithmetic"

# The other reads of a column wider than ``i64`` that compute in its width,
# or carry it into doubles, where the record says ``i64``: one rule each, so
# the lifted sentence names the operation the author wrote. No rule is a
# substring of another, since the door matches by containment.
WIDE_SUM_RULE = "integer wider than Int64 read by a sum"
WIDE_RUNNING_SUM_RULE = "integer wider than Int64 read by a running sum"
WIDE_RUNNING_PRODUCT_RULE = "integer wider than Int64 read by a running product"
WIDE_REMAINING_SUM_RULE = "integer wider than Int64 read by a remaining sum"
WIDE_ABSOLUTE_VALUE_RULE = "integer wider than Int64 read by an absolute value"
WIDE_ROLLFORWARD_RULE = "integer wider than Int64 read by a rollforward"
WIDE_SIG_FIGS_RULE = "integer wider than Int64 read by round_sig_figs"
WIDE_CARRY_RULE = "integer wider than Int64 carried by an operation"
WIDE_BAND_RULE = "integer wider than Int64 placed in a band"
SIG_FIGS_PAST_I64_RULE = "whole number rounded past the Int64 range"
# A fold of whole numbers taken exactly, whose answer -- the total, or one
# period of a running one -- no ``i64`` holds.
SUM_PAST_I64_RULE = "whole numbers whose sum lies past the Int64 range"
RUNNING_SUM_PAST_I64_RULE = "whole numbers whose running sum lies past the Int64 range"
RUNNING_PRODUCT_PAST_I64_RULE = (
    "whole numbers whose running product lies past the Int64 range"
)
REMAINING_SUM_PAST_I64_RULE = (
    "whole numbers whose remaining sum lies past the Int64 range"
)
# The least i64, -2**63, whose absolute value no i64 holds.
ABSOLUTE_VALUE_PAST_I64_RULE = (
    "whole number whose absolute value lies past the Int64 range"
)
# A per-period clip by a bound a column gives runs in doubles, which hold a
# whole number exactly only up to 2**53.
CLIP_PAST_2_53_RULE = "whole number past 2**53 held between bounds a column gives"
ROUND_PAST_I64_RULE = "whole number moved to a step past the Int64 range"
# A conditional answers two time units in the finer of the two, and a date and
# time or a duration the finer unit cannot hold has no answer in it.
FINER_UNIT_RULE = "time value outside the range of the finer time unit"
# A conditional answers two fixed-point decimals, or a decimal and a whole
# number, in the one decimal type Polars gives the pair, and a value that type
# cannot hold has no answer in it.
DECIMAL_PAIR_RULE = (
    "decimal value outside the range of the decimal type a conditional answers in"
)

# What the column's name rides under, so the lifted sentence can say which
# column the model has to look at. The offending value does not ride with it,
# and the reason is mechanical rather than budgetary: ``when/then/otherwise``
# evaluates both branches, so a message built per row is a string formatted on
# every row that *passes* as well, for a refusal that almost never fires. The
# whole refusal is therefore one scalar literal whatever the frame's height.
# Observed 2026-09-12 against extension e9a7ee81..., Polars 1.42.1: 3.314 ms
# against 13.854 ms over a 200,000-row valid indicator, median of 12 collects.
# The observation dates; the reason above does not.
_COLUMN_TAG = " -- column "


def stored_predicate_refusal(column: str | None) -> str:
    """Return the refusal a stored-predicate row smuggles out of the plan."""
    return _tagged(STORED_PREDICATE_RULE, column)


def checked_integer_refusal(column: str | None) -> str:
    """Return the refusal a failed whole-number conversion smuggles out."""
    return _tagged(CHECKED_INTEGER_RULE, column)


def checked_float_refusal(column: str | None) -> str:
    """Return the refusal a number no double can name smuggles out."""
    return _tagged(CHECKED_FLOAT_RULE, column)


def integer_range_refusal(column: str | None) -> str:
    """Return the refusal a whole number too wide for an ``i64`` smuggles out."""
    return _tagged(INTEGER_RANGE_RULE, column)


def sig_figs_past_i64_refusal(column: str | None) -> str:
    """Return the refusal a whole number rounded up past ``i64`` smuggles out."""
    return _tagged(SIG_FIGS_PAST_I64_RULE, column)


def round_past_i64_refusal(column: str | None) -> str:
    """Return the refusal a whole number rounded to a step past ``i64`` smuggles out."""
    return _tagged(ROUND_PAST_I64_RULE, column)


def wide_arithmetic_refusal(column: str | None) -> str:
    """Return the refusal arithmetic on a whole number past ``i64`` smuggles out."""
    return _tagged(WIDE_ARITHMETIC_RULE, column)


def tagged_refusal(rule: str, column: str | None) -> str:
    """Return ``rule`` with ``column`` attached, for a check built elsewhere."""
    return _tagged(rule, column)


def _tagged(rule: str, column: str | None) -> str:
    """Attach ``column`` to ``rule`` in the one spelling the door reads back."""
    if column is None:
        return rule
    return f"{rule}{_COLUMN_TAG}{column!r}"


def refused_column(reported: str) -> str | None:
    """Return the column named by a smuggled refusal in ``reported``.

    ``reported`` is the list of values Polars says it could not convert, and
    nothing wider. Searching the whole error text instead would find the tag
    in the resolved-plan dump, which carries every literal the plan holds --
    including refusals that did not fire.

    ``None`` when the refusal carried no name and when the name cannot be read
    back whole -- a name holding the quote the tag closes on costs nothing to
    allow for, and would otherwise hand a reader half a column name as though
    it were the column.
    """
    start = reported.find(_COLUMN_TAG)
    if start < 0:
        return None
    quoted = reported[start + len(_COLUMN_TAG) :]
    if not quoted.startswith("'"):
        return None
    end = quoted.find("'", 1)
    return quoted[1:end] if end > 1 else None


def require_valid_rows(valid: pl.Expr, *, message: str) -> pl.Expr:
    """Return zero for valid rows and make Polars refuse every invalid row."""
    return (
        pl.when(valid)
        .then(pl.lit("0"))
        .otherwise(pl.lit(message))
        .cast(pl.Int64, strict=True)
    )


def _every_value_converts(value: pl.Expr, element: pl.DataType, depth: int) -> pl.Expr:
    """Return, per row, whether every value ``value`` holds has a name in ``element``.

    Asked of the non-strict cast itself rather than of two bounds, so the
    test is the conversion's own: it answers null exactly where a value does
    not fit, and an absent value is not a value out of range. ``depth`` is
    how many lists deep the values sit; an empty list fits.
    """
    if depth == 0:
        return value.is_null() | value.cast(element, strict=False).is_not_null()
    within = _every_value_converts(pl.element(), element, depth - 1)
    return value.is_null() | value.list.eval(within).list.all()


def read_as_i64_where_it_fits(
    value: pl.Expr,
    read: pl.DataType,
    *,
    depth: int,
    column: str | None,
    rule: str = WIDE_ARITHMETIC_RULE,
) -> pl.Expr:
    """Return a wide integer operand read as ``read``, refusing a value past ``i64``.

    ``read`` is the operand's type with each ``UInt64``, ``Int128`` or
    ``UInt128`` in it as ``Int64``. Every row that fits converts exactly; a
    row that does not makes the plan refuse with ``rule`` --
    :data:`WIDE_ARITHMETIC_RULE` unless the read is one of the others --
    which the frame's error door lifts to the first line, rather than wrap.
    """
    fits = _every_value_converts(value, pl.Int64(), depth)
    refused = require_valid_rows(fits, message=_tagged(rule, column))
    return pl.when(refused == 0).then(value.cast(read, strict=False))


def read_in_the_finer_unit(
    value: pl.Expr,
    read: pl.DataType,
    *,
    element: pl.DataType,
    depth: int,
    column: str | None,
) -> pl.Expr:
    """Return a date-and-time or duration branch read in a finer unit, or refuse.

    ``read`` is the branch's type in the finer unit, ``element`` the type of
    one value in it. Every value the finer unit holds converts exactly; one
    it cannot -- a nanosecond count reaches only the years 1677 to 2262 --
    makes the plan refuse under :data:`FINER_UNIT_RULE`, which the frame's
    error door lifts to the first line, rather than turn into a null.
    """
    fits = _every_value_converts(value, element, depth)
    refused = require_valid_rows(fits, message=_tagged(FINER_UNIT_RULE, column))
    return pl.when(refused == 0).then(value.cast(read, strict=False))


def read_in_the_shared_decimal(
    value: pl.Expr,
    read: pl.DataType,
    *,
    element: pl.DataType,
    depth: int,
    column: str | None,
) -> pl.Expr:
    """Return a decimal or whole-number branch in the pair's decimal type, or refuse.

    ``read`` is the branch's type with its element written as ``element``,
    the decimal type the two branches share. A value it holds converts
    exactly; one it cannot -- ``2**62`` beside twenty decimal places needs
    thirty-nine digits -- makes the plan refuse under
    :data:`DECIMAL_PAIR_RULE`, which the frame's error door lifts to the
    first line, rather than turn into a null.
    """
    fits = _every_value_converts(value, element, depth)
    refused = require_valid_rows(fits, message=_tagged(DECIMAL_PAIR_RULE, column))
    return pl.when(refused == 0).then(value.cast(read, strict=False))


def checked_numeric_predicate(
    value: pl.Expr, *, per_period: bool, column: str | None = None
) -> pl.Expr:
    """Require each stored numeric predicate to be present and exactly 0 or 1."""
    element = pl.element() if per_period else value
    valid = (
        element.is_not_null()
        & element.is_finite()
        & ((element == 0.0) | (element == 1.0))
    ).fill_null(value=False)
    if per_period:
        valid = value.is_not_null() & value.list.eval(valid).list.all().fill_null(
            value=False
        )
    return value + require_valid_rows(valid, message=stored_predicate_refusal(column))
