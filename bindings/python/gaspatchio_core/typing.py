# ADDED: Import necessary types outside TYPE_CHECKING block
import sys
from typing import TYPE_CHECKING, Union

import polars as pl

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias

# ADDED: Define IntoExprColumn outside TYPE_CHECKING block
IntoExprColumn: TypeAlias = Union[pl.Expr, str, pl.Series]

if TYPE_CHECKING:
    # import sys # Removed, imported above
    # import polars as pl # Removed, imported above

    # if sys.version_info >= (3, 10): # Removed, handled above
    #     from typing import TypeAlias
    # else:
    #     from typing_extensions import TypeAlias

    from polars.datatypes import DataType, DataTypeClass

    # IntoExprColumn: TypeAlias = Union[pl.Expr, str, pl.Series] # Removed, defined above
    PolarsDataType: TypeAlias = Union[DataType, DataTypeClass]
