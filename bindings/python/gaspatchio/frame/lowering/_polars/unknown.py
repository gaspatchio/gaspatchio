# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A comparison with a NaN on either side, answered as an unknown.

0/0 is NaN (section 11.1.25), and an in-the-money ratio over a zero guarantee
is one. A NaN is no number, so it is neither greater than 1.0 nor less than
it nor equal to anything: ``NaN > 1.0`` has no truth value. Polars answered
one anyway, and a different one by shape -- per policy it orders a NaN above
every number, so ``NaN > 1.0`` was true; per period the comparison kernel
uses the processor's comparison, in which every test of a NaN is false -- so
one line stored 1.0 for one policy shape and 0.0 for the other.

Section 11.1.26 now answers it one way on both shapes and every engine: a
comparison with a NaN operand is a NaN indicator, a ``when`` over it answers
NaN where its answer is a number and a null where it is not (text, a whole
number, a date), and ``&``, ``|`` and ``~`` over it answer NaN too, as the
per-period arithmetic that combines indicators already did. A null on either
side stays a null: a policy with no value has no comparison to be unknown.
±infinity is a number and is ordered as IEEE orders it.

The helpers here are the two expressions every route uses:

- :func:`nan_poison` is ``-0.0`` where a value is a number and NaN where it
  is NaN. Added to an answer that is a double, it leaves every number as it
  was -- ``x + (-0.0)`` is ``x`` for every ``x``, a negative nought included --
  and makes the answer NaN wherever an operand was, while a null answer stays
  null.
- :func:`nan_as_null` reads a NaN as a null, for an answer that holds no
  NaN: the comparison kernel answers a null operand with a null.
- :func:`unknown_guard` answers ``none`` where a per-policy test has no
  truth value, and the selection everywhere else.

**Each is marked, so the record can write it back as the line written.** The
three are how the answer is computed, not what the model wrote, as the
null-run guard a per-period comparison carries is; a walk-through or the
``gaspatchio_lowered`` facet shows ``when(r > 1.0)...`` and not the NaN
tests around it. Each carries an alias no formula writes (:data:`MARKS`),
which renders as the last call of the piece, and the rendering takes each
piece off by it (``rendering.nan_guards_as_written``). An alias inside an
expression names nothing and computes nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import polars as pl

if TYPE_CHECKING:
    from typing import Literal

_NAN: Final = float("nan")

# The alias each guard piece carries; ':' cannot start a column a frame
# writes, and no formula aliases inside an expression.
POISON_MARK: Final = "gaspatchio:nan_poison"
AS_NULL_MARK: Final = "gaspatchio:nan_as_null"
UNKNOWN_MARK: Final = "gaspatchio:nan_unknown"
MARKS: Final = (POISON_MARK, AS_NULL_MARK, UNKNOWN_MARK)

# The addend that leaves every double as it was, a negative nought included.
_NOUGHT: Final = -0.0


def holds_a_nan(dtype: pl.DataType | None) -> bool:
    """Say whether a value of ``dtype`` -- or each period of it -- can be a NaN."""
    inner = dtype.inner if isinstance(dtype, pl.List) else dtype
    return inner in (pl.Float64, pl.Float32)


def nan_poison(expr: pl.Expr, shape: Literal["scalar", "list", "unknown"]) -> pl.Expr:
    """Return ``-0.0`` where ``expr`` is a number and NaN where it is NaN.

    A null reads ``-0.0`` here: the answer it is added to is already null
    wherever an operand is.
    """
    if shape == "list":
        poison = expr.list.eval(
            pl.when(pl.element().is_nan()).then(pl.lit(_NAN)).otherwise(pl.lit(_NOUGHT))
        )
    else:
        poison = pl.when(expr.is_nan()).then(pl.lit(_NAN)).otherwise(pl.lit(_NOUGHT))
    return poison.alias(POISON_MARK)


def nan_as_null(expr: pl.Expr, shape: Literal["scalar", "list", "unknown"]) -> pl.Expr:
    """Return ``expr`` with every NaN read as a null."""
    if shape == "list":
        return expr.list.eval(pl.element().fill_nan(None)).alias(AS_NULL_MARK)
    return expr.fill_nan(None).alias(AS_NULL_MARK)


def unknown_guard(unknown: pl.Expr, none: pl.Expr, selected: pl.Expr) -> pl.Expr:
    """Return ``none`` where ``unknown`` holds and ``selected`` everywhere else."""
    return pl.when(unknown.alias(UNKNOWN_MARK)).then(none).otherwise(selected)


def nan_literal(dtype: pl.DataType | None) -> pl.Expr:
    """Return a NaN in ``dtype``'s own width of double, ``Float64`` by default."""
    inner = dtype.inner if isinstance(dtype, pl.List) else dtype
    width = pl.Float32 if inner == pl.Float32 else pl.Float64
    return pl.lit(_NAN, dtype=width)


__all__ = [
    "AS_NULL_MARK",
    "MARKS",
    "POISON_MARK",
    "UNKNOWN_MARK",
    "holds_a_nan",
    "nan_as_null",
    "nan_literal",
    "nan_poison",
    "unknown_guard",
]
