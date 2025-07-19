from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from polars.plugins import register_plugin_function

from gaspatchio_core import _internal
from gaspatchio_core.functions.utils import to_polars_expression

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio_core.typing import IntoExprColumn

LIB = Path(_internal.__file__)


def yearfrac(
    start_date: IntoExprColumn,
    end_date: IntoExprColumn,
    basis: int = 1,
) -> pl.Expr:
    start_date = to_polars_expression(start_date)
    end_date = to_polars_expression(end_date)

    return register_plugin_function(
        args=[start_date, end_date],
        plugin_path=LIB,
        function_name="yearfrac",
        is_elementwise=True,
        kwargs={"basis": basis},
    )
