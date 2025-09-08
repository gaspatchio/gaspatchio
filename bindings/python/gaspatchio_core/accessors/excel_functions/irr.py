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


def irr(
    values: IntoExprColumn,
    guess: IntoExprColumn | None = None,
    *,
    default_guess: float | None = None,
) -> pl.Expr:
    """Internal rate of return, Excel-compatible IRR via Rust implementation.

    Args:
        values: List[Float64] column or Float64 column. For lists, each row contains cash flows.
        guess: Optional per-row Float64 guess column/expression. If provided, overrides default_guess for that row.
        default_guess: Optional scalar fallback when `guess` not provided. Defaults to 0.1 in Rust.

    Returns:
        Polars expression evaluating to Float64 IRR per row.

    """
    values_expr = to_polars_expression(values)
    args = [values_expr]
    if guess is not None:
        args.append(to_polars_expression(guess))

    kwargs: dict[str, float] = {}
    if default_guess is None:
        # Provide Rust's default explicitly so plugin kwargs parsing always has content
        kwargs["guess"] = 0.1
    else:
        kwargs["guess"] = float(default_guess)

    return register_plugin_function(
        args=args,
        plugin_path=LIB,
        function_name="irr",
        is_elementwise=True,
        kwargs=kwargs,
    )
