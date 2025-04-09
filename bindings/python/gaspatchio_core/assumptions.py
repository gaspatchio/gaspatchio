"""
Assumption lookup functionality.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

# Import the typing helper if it exists, otherwise define locally for now
try:
    from gaspatchio_core.typing import IntoExpr
except ImportError:
    from typing import Union

    IntoExpr = Union[str, pl.Expr]

if TYPE_CHECKING:
    pass  # Keep this structure for potential future complex types

# Define LIB path consistently with functions.py
LIB = Path(__file__).parent


def assumption_lookup(*keys: IntoExpr, table_name: str) -> pl.Expr:
    """Creates a Polars expression for performing an assumption lookup.

    This function looks up values from a previously registered assumption table
    based on the provided key columns.

    Args:
        *keys: One or more key columns (can be column names as strings or
            Polars expressions).
        table_name: The name of the assumption table registered in the global registry.

    Returns:
        A Polars expression that performs the lookup when evaluated.

    Examples:
        >>> import polars as pl
        >>> from gaspatchio_core.assumptions import assumption_lookup
        >>> # Assuming 'mortality_rates' table is registered with keys 'age' and 'gender'
        >>> df = pl.DataFrame({"age": [30, 31], "gender": ["M", "F"]})
        >>> df.with_columns(
        ...     mort_rate=assumption_lookup("age", "gender", table_name="mortality_rates")
        ... )
        # This will compute the lookup when the DataFrame is evaluated.

    """
    # Ensure keys are actual expressions, converting strings to pl.col()
    key_exprs = [pl.col(key) if isinstance(key, str) else key for key in keys]

    return register_plugin_function(
        plugin_path=LIB,
        function_name="lookup_plugin_binding",  # Must match #[polars_expr] function name
        args=key_exprs,
        kwargs={"table_name": table_name},
        is_elementwise=False,  # Vector lookup is not elementwise
    )
