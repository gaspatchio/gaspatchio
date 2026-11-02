# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Independent base rules for the published synthetic vectors."""

from __future__ import annotations

import math
import operator
from functools import partial

from .shared import Column, DomainRefusal, map_values


def ordinary_numeric(left: Column, right: Column, name: str) -> str:
    """Resolve the type in the bounded i64/f64 arithmetic domain."""
    if left.inner not in {"i64", "f64"} or right.inner not in {"i64", "f64"}:
        raise DomainRefusal("numeric-operands-required")
    if name == "div" or "f64" in {left.inner, right.inner}:
        return "f64"
    if name == "pow" and (left.listed or right.listed):
        return "f64"
    return "i64"


def divide(left, right):
    if right == 0:
        if left == 0 or math.isnan(left):
            return math.nan
        return math.copysign(
            math.inf, math.copysign(1.0, left) * math.copysign(1.0, right)
        )
    return left / right


def floor_or_mod(a, b, *, name: str, inner: str):
    if inner == "i64":
        return None if b == 0 else (a // b if name == "floordiv" else a % b)
    quotient = divide(float(a), float(b))
    # IEEE's floor keeps the sign of a zero: the floor of -0.0 is -0.0, and that
    # sign decides a division by it (11.1.25). ``math.floor`` answers an int,
    # which has no negative zero.
    floor = (
        math.copysign(float(math.floor(quotient)), quotient)
        if math.isfinite(quotient)
        else quotient
    )
    return floor if name == "floordiv" else float(a) - float(b) * floor


def power(a, b, *, inner: str, scalar_list: bool):
    if a < 0 and scalar_list:
        raise DomainRefusal("negative-scalar-base-list-power")
    if inner == "i64" and not 0 <= b <= 2**32 - 1:
        raise DomainRefusal("integer-power-exponent")
    if inner == "i64" and abs(a) > 1 and b > 63:
        raise DomainRefusal("integer-overflow")
    try:
        return a**b if inner == "i64" else math.pow(a, b)
    except (OverflowError, ValueError) as error:
        raise DomainRefusal("power-domain") from error


def numeric_cell(a, b, *, function, inner: str):
    if a is None or b is None:
        return None
    result = function(a, b)
    if inner == "i64" and result is not None and not -(2**63) <= result < 2**63:
        raise DomainRefusal("integer-overflow")
    return float(result) if inner == "f64" and result is not None else result


def as_indicator(column: Column) -> Column:
    """Read a Boolean operand of arithmetic as the 0 or 1 it indicates (11.1.25).

    True is 1.0, false is 0.0 and a null stays null, per policy and per
    period, on either side and under every operator; the answer is then the
    double the other operand meets. A comparison already arrives as its
    indicator; a stored Boolean column did not, and was refused.
    """
    if column.inner != "bool":
        return column

    def read(value):
        return None if value is None else float(value)

    if column.listed:
        rows = [
            None if row is None else [read(v) for v in row] for row in column.values
        ]
        return Column("list[f64]", rows)
    return Column("f64", [read(value) for value in column.values])


def arithmetic(
    name: str, left: Column, right: Column, *, exponent_written: bool = False
) -> Column:
    # 11.1.25: a per-policy Boolean on both sides of one operation is not
    # admitted; one beside a number, or a run of them, reads as its 0/1.
    if left.dtype == right.dtype == "bool":
        raise DomainRefusal("boolean-on-both-sides")
    left, right = as_indicator(left), as_indicator(right)
    inner = ordinary_numeric(left, right, name)
    # 11.1.25: an exponent written as an integer literal outside [0, 2^32-1]
    # answers f64, the base read as its double and raised by the binary64
    # power, held to the relative 1e-12 (not to the bits of `1 / a`); one
    # held in a column keeps the integer rule.
    if exponent_written and inner == "i64":
        inner = "f64"
    functions = {
        "add": operator.add,
        "sub": operator.sub,
        "mul": operator.mul,
        "div": lambda a, b: divide(float(a), float(b)),
        "floordiv": partial(floor_or_mod, name=name, inner=inner),
        "mod": partial(floor_or_mod, name=name, inner=inner),
        "pow": partial(
            power, inner=inner, scalar_list=not left.listed and right.listed
        ),
    }
    if inner == "f64":
        check_exact_conversion(left, right)
    cell = partial(numeric_cell, function=functions[name], inner=inner)
    return map_values(cell, [left, right], inner)


def check_exact_conversion(*columns: Column) -> None:
    for column in columns:
        if column.inner != "i64":
            continue
        for row in column.values:
            if row is None:
                continue
            cells = row if column.listed else [row]
            if any(cell is not None and abs(cell) > 2**53 for cell in cells):
                raise DomainRefusal("arithmetic-outside-exact-numeric-range")


COMPARISONS = {
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
    "eq": operator.eq,
    "ne": operator.ne,
}


def unknown(value) -> bool:
    """Say whether a truth value is the unknown a NaN comparison answers (11.1.26)."""
    return isinstance(value, float) and math.isnan(value)


def comparison(name: str, left: Column, right: Column, *, indicator: bool) -> Column:
    def cell(a, b):
        if a is None or b is None:
            return None
        # 11.1.26: a NaN operand leaves no truth value; the indicator is NaN
        # and so is the truth value a condition reads. Infinity is a number
        # and is ordered as IEEE orders it.
        if unknown(a) or unknown(b):
            return math.nan
        # Two whole numbers compare exactly over the whole of i64, per policy
        # and per period alike; only a whole number met by a decimal is
        # bounded to the range a double names every whole number in.
        if left.inner != right.inner and any(
            isinstance(value, int)
            and not isinstance(value, bool)
            and abs(value) > 2**53
            for value in (a, b)
        ):
            raise DomainRefusal("comparison-outside-exact-numeric-range")
        value = COMPARISONS[name](a, b)
        return float(value) if indicator else value

    return map_values(cell, [left, right], "f64" if indicator else "bool")


_KLEENE = {
    "and": {
        (False, False): False,
        (False, True): False,
        (False, None): False,
        (True, False): False,
        (True, True): True,
        (True, None): None,
        (None, False): False,
        (None, True): None,
        (None, None): None,
    },
    "or": {
        (False, False): False,
        (False, True): True,
        (False, None): None,
        (True, False): True,
        (True, True): True,
        (True, None): True,
        (None, False): None,
        (None, True): True,
        (None, None): None,
    },
}


def logical_cell(a, b=None, *, name: str, listed: bool):
    supplied = [a] if name == "not_" else [a, b]
    # 11.1.27 over 11.1.26's unknown: a test with no truth value makes the
    # combination have none, a null beside it winning, as the per-period
    # arithmetic gives (a null indicator times a NaN one is a null). A
    # per-policy result is a Boolean wherever it is read, stored or inline:
    # a null there, which whatever reads it reads as a null.
    if any(unknown(value) for value in supplied):
        if not listed or any(value is None for value in supplied):
            return None
        return math.nan
    if any(
        value is not None and value not in (False, True, 0.0, 1.0) for value in supplied
    ):
        raise DomainRefusal("logical-indicator-domain")
    if name == "not_":
        result = None if a is None else not a
    elif listed and (a is None or b is None):
        result = None
    else:
        result = _KLEENE[name][a, b]
    return float(result) if listed and result is not None else result


def stored_indicator(column: Column) -> Column:
    """Read a direct ``f64`` column reference under 11.1.18's stored rule.

    11.1.27 takes such a column as a logical operand: every value finite,
    non-null and exactly 0.0 or 1.0, a negative zero being zero. A per-policy
    one stands for its Boolean; a per-period one stays its 0/1 indicator. A
    null outer list is a null value too, so it refuses rather than passing on.
    """

    def check(value):
        if value is None or not math.isfinite(value) or value not in (0.0, 1.0):
            raise DomainRefusal("stored-numeric-predicate")
        return float(value == 1.0) if column.listed else value == 1.0

    if not column.listed:
        return Column("bool", [check(value) for value in column.values])
    if any(row is None for row in column.values):
        raise DomainRefusal("stored-numeric-predicate")
    return Column(column.dtype, [[check(v) for v in row] for row in column.values])


def logical(name: str, left: Column, right: Column | None = None) -> Column:
    operands = [left] if right is None else [left, right]
    listed = any(column.listed for column in operands)
    if any(
        column.inner != "bool" and not (listed and column.inner == "f64")
        for column in operands
    ):
        raise DomainRefusal("boolean-operands-required")

    cell = partial(logical_cell, name=name, listed=listed)
    return map_values(cell, operands, "f64" if listed else "bool")
