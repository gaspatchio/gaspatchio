# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from abc import ABC
from typing import NoReturn

import polars as pl

from gaspatchio._semantic.ir import OpNode
from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.frame.base import ActuarialFrame

def column_expr(
    frame: ActuarialFrame,
    designator: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
    *,
    parameter: str,
) -> pl.Expr: ...
def column_node(
    frame: ActuarialFrame,
    designator: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
    *,
    parameter: str,
) -> OpNode: ...
def refuse_missing_column(
    frame: ActuarialFrame, *, parameter: str, name: str
) -> NoReturn: ...
def refuse_bare_string_operand(
    value: object, *, parameter: str, value_hint: str | None = None
) -> None: ...
def refuse_bare_string_override(value: object, *, parameter: str) -> None: ...

class BaseFrameAccessor(ABC):
    _frame: ActuarialFrame
    def __init__(self, frame: ActuarialFrame) -> None: ...

class BaseColumnAccessor(ABC):
    _proxy: ColumnProxy | ExpressionProxy
    def __init__(self, proxy: ColumnProxy | ExpressionProxy) -> None: ...

# The bases a custom accessor subclasses, as the extending skill documents them.
__all__ = ["BaseColumnAccessor", "BaseFrameAccessor"]
