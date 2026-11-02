# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Prepare the same lookup meaning for public table reads and mortality lowering."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import polars as pl

from gaspatchio._semantic.ir import BinOp, Call, Col, Lit, non_finite_literal_message
from gaspatchio.frame.lowering.artefacts import register_table, table_schema
from gaspatchio.frame.lowering.ingress import to_node

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.assumptions._data import TableData
    from gaspatchio.frame.lowering.context import LoweringContext

# The two values a flag is read as, as a table holds them.
_FLAG_VALUES: frozenset[float] = frozenset({0.0, 1.0})


def lookup_node(
    table: TableData,
    dimensions: Mapping[str, object],
    on_missing: str | float | None = None,
    *,
    ctx: LoweringContext | None = None,
) -> Call:
    """Pin the table identity and validated operands in one semantic read.

    A key that is a flag, against a dimension the table holds as numbers, is
    read as its 0 or 1 -- as a flag is in arithmetic -- and the record says
    so: the operand is written ``key * 1.0``, so the document is a numeric
    query every engine and reader answers alike. A dimension whose keys are
    not 0 and 1 is refused, naming its keys, since a flag there would read
    as a code it was never meant as.
    """
    inputs, miss_mode, miss_fill = table._lookup_inputs(dimensions, on_missing)  # noqa: SLF001 - shared table data contract
    fingerprint = register_table(table)
    if miss_fill is not None and not math.isfinite(miss_fill):
        msg = non_finite_literal_message(miss_fill, " as lookup's 'fill_value'")
        raise ValueError(msg)
    key_columns, _ = table_schema(table.name, fingerprint)
    operands = [to_node(arg) for arg in inputs]
    if ctx is not None and len(key_columns) == len(operands):
        operands = [
            _a_flag_read_as_its_number(table, column, operand, ctx)
            for column, operand in zip(key_columns, operands, strict=True)
        ]
    return Call(
        name="lookup",
        args=tuple(operands),
        attrs=(
            ("table", table.name),
            ("table_fingerprint", fingerprint),
            ("on_missing", miss_mode),
            ("fill_value", miss_fill),
        ),
    )


def _a_flag_read_as_its_number(
    table: TableData, column: str, operand: OpNode, ctx: LoweringContext
) -> OpNode:
    """Return a flag key written as its 0 or 1, or the key as it stands."""
    from gaspatchio.frame.lowering.polars import lower_arg  # noqa: PLC0415 - cycle

    held = None if table._df is None else table._df.schema.get(column)  # noqa: SLF001 - shared table data contract
    if held is None or not held.is_numeric():
        return operand
    dtype = ctx.dtype_of_expr(lower_arg(operand, ctx)[0])
    inner = dtype.inner if isinstance(dtype, pl.List) else dtype
    if inner != pl.Boolean:
        return operand
    keys = table._df.get_column(column).drop_nulls().unique().sort()  # type: ignore[union-attr]  # noqa: SLF001
    if not set(keys.to_list()) <= _FLAG_VALUES:
        raise TypeError(_a_flag_against_codes(table, column, operand, keys))
    return BinOp(op="mul", left=operand, right=Lit(1.0))


def _a_flag_against_codes(
    table: TableData, column: str, operand: OpNode, keys: pl.Series
) -> str:
    """Word the refusal of a flag against a dimension keyed by other numbers."""
    from gaspatchio.assumptions._dimensions import DataDimension  # noqa: PLC0415

    dimension = next(
        (
            name
            for name, dim in table._dimensions.items()  # noqa: SLF001 - shared table data contract
            if isinstance(dim, DataDimension)
            and (dim.rename_to or dim.column) == column
        ),
        column,
    )
    shown = ", ".join(f"{key:g}" for key in keys.head(6).to_list())
    more = ", ..." if keys.len() > 6 else ""  # noqa: PLR2004 - a quotation
    named = f"af.{operand.name}" if isinstance(operand, Col) else "the key"
    return (
        f"Table {table.name!r} cannot be looked up on dimension {dimension!r} "
        f"with a flag: {named} is true or false, which reads as 1 or 0, and "
        f"this table's keys are {shown}{more}. A flag against keys that are "
        "not 0 and 1 would read as a code it was never meant as (a 1/2 smoker "
        "code would answer true as the non-smoker's row). Write the key the "
        "table means while setting up the model points: "
        f"pl.when(pl.col({(operand.name if isinstance(operand, Col) else 'key')!r}))"
        ".then(2).otherwise(1), with the codes the table uses."
    )
