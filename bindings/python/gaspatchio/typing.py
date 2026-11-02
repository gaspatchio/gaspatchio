# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Type aliases shared by gaspatchio's annotations."""

# ADDED: Import necessary types outside TYPE_CHECKING block
from typing import TYPE_CHECKING, TypeAlias

import polars as pl

# ADDED: Define IntoExprColumn outside TYPE_CHECKING block
IntoExprColumn: TypeAlias = pl.Expr | str | pl.Series

if TYPE_CHECKING:
    from polars.datatypes import DataType, DataTypeClass

    type PolarsDataType = DataType | DataTypeClass
