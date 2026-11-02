# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Independent shared rules for the published synthetic vectors."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    dtype: str
    values: list

    @property
    def listed(self) -> bool:
        return self.dtype.startswith("list[")

    @property
    def arrayed(self) -> bool:
        # A fixed-width array is an input-only name: it is the door a
        # conversion clause converts from, never a result a case expects.
        # It is deliberately not "listed" -- 11.1.40 refuses a list and
        # converts an array, so reading the two as one shape would lose the
        # distinction the clause is about.
        return self.dtype.startswith("array[")

    @property
    def inner(self) -> str:
        if self.listed:
            return self.dtype[5:-1]
        if self.arrayed:
            return self.dtype[len("array[") : -1].rsplit(",", 1)[0]
        return self.dtype


class DomainRefusal(ValueError):
    """The invocation is outside the explicitly stated vector domain."""


# The whole numbers an i64 holds (section 10).
I64_LEAST, I64_GREATEST = -(2**63), 2**63 - 1


def held_whole(value: int) -> int:
    """Answer a whole number an ``i64`` holds, or refuse it by name.

    An answer outside the signed 64-bit range is outside the portable domain
    (11.1.25), so a consumer claiming only that domain refuses it rather than
    wrap it or carry it into a double.
    """
    if not I64_LEAST <= value <= I64_GREATEST:
        raise DomainRefusal("integer-overflow")
    return value


def as_double(value):
    """Carry one present value into the double an ``f64`` cell holds."""
    return None if value is None else float(value)


# The Python type each value of a label is held as. A date travels as its ISO
# string. A label outside this table names no single Python type.
_HELD_AS = {"i64": int, "f64": float, "bool": bool, "str": str, "date": str}


def contradicts(column: Column) -> bool:
    """Say whether a value is held as another type than the label names.

    A whole number under ``f64``, a double under ``i64`` or a flag under
    either is a reader answering one type and naming another, which a
    comparison of values alone does not see: 2.0 equals 2.
    """
    held = _HELD_AS.get(column.inner)
    if held is None:
        return False
    rows = column.values if column.listed or column.arrayed else [column.values]
    return any(
        value is not None and type(value) is not held
        for row in rows
        if row is not None
        for value in row
    )


def map_values(function, operands: list[Column], inner: str) -> Column:
    """Apply a cell function independently at each policy and period."""
    count = len(operands[0].values)
    if any(len(column.values) != count for column in operands):
        raise DomainRefusal("policy-count-mismatch")
    listed = any(column.listed for column in operands)
    result = []
    for policy in range(count):
        cells = [column.values[policy] for column in operands]
        if not listed:
            result.append(function(*cells))
            continue
        result.append(map_periods(function, cells, operands))
    return Column(f"list[{inner}]" if listed else inner, result)


def map_periods(function, cells: list, operands: list[Column]) -> list | None:
    lists = [cell for cell, column in zip(cells, operands) if column.listed]
    if any(cell is None for cell in lists):
        return None
    width = len(lists[0])
    if any(len(cell) != width for cell in lists):
        raise DomainRefusal("period-count-mismatch")
    return [
        function(
            *(
                cell[period] if column.listed else cell
                for cell, column in zip(cells, operands)
            )
        )
        for period in range(width)
    ]


def decode(value):
    if isinstance(value, list):
        return [decode(cell) for cell in value]
    if isinstance(value, dict) and set(value) == {"nonfinite"}:
        return {"nan": math.nan, "+inf": math.inf, "-inf": -math.inf}[
            value["nonfinite"]
        ]
    return value


def differences(
    actual, expected, atol: float, rtol: float = 0.0, path: str = "values"
) -> list[str]:
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [path + ": shape differs"]
        return [
            finding
            for index, (a, e) in enumerate(zip(actual, expected))
            for finding in differences(a, e, atol, rtol, f"{path}[{index}]")
        ]
    if expected is None or isinstance(expected, (str, bool)):
        return (
            []
            if type(actual) is type(expected) and actual == expected
            else [path + ": value/type differs"]
        )
    return numeric_differences(actual, expected, atol, rtol, path)


def numeric_differences(
    actual: object, expected: int | float, atol: float, rtol: float, path: str
) -> list[str]:
    if isinstance(expected, float) and math.isnan(expected):
        return (
            []
            if isinstance(actual, float) and math.isnan(actual)
            else [path + ": expected NaN"]
        )
    if not isinstance(actual, (int, float)) or isinstance(actual, bool):
        return [path + ": expected number"]
    if actual == expected:
        return []
    if (
        isinstance(expected, float)
        and math.isfinite(actual)
        and math.isfinite(expected)
        and abs(actual - expected) <= atol + rtol * abs(expected)
    ):
        return []
    return [f"{path}: {actual!r} != {expected!r}"]
