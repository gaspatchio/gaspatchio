from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

from gaspatchio_core import _internal
from gaspatchio_core.functions.utils import to_polars_expression

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn

LIB = Path(_internal.__file__)


def pv(
    rate: IntoExprColumn,
    nper: IntoExprColumn,
    pmt: IntoExprColumn,
    *,
    fv: float | None = None,
    typ: int | None = None,
) -> pl.Expr:
    """Present value, Excel-compatible PV via Rust implementation.

    Args:
        rate: Interest rate per period (Float64 scalar/column or List[Float64]).
        nper: Number of periods (Float64 scalar/column or List[Float64]).
        pmt: Payment per period (Float64 scalar/column or List[Float64]).
        fv: Future value (scalar). Defaults to 0.0 if not provided.
        typ: Payment timing (0=end, 1=begin). Any nonzero coerced to 1 by Rust.

    Returns:
        Polars expression producing Float64 or List[Float64] depending on inputs.

    """
    rate_expr = to_polars_expression(rate)
    nper_expr = to_polars_expression(nper)
    pmt_expr = to_polars_expression(pmt)

    kwargs = {}
    if fv is not None:
        kwargs["fv"] = float(fv)
    if typ is not None:
        kwargs["typ"] = int(typ)

    return register_plugin_function(
        args=[rate_expr, nper_expr, pmt_expr],
        plugin_path=LIB,
        function_name="pv",
        is_elementwise=True,
        kwargs=kwargs,
    )
