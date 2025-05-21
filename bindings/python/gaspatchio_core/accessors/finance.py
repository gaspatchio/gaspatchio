"""Accessors for finance-related operations on ActuarialFrame objects."""

from typing import TYPE_CHECKING

import polars as pl

# Import the registry decorator
from ..frame.registry import register_accessor

# Updated import for base accessors
from .base import BaseColumnAccessor, BaseFrameAccessor

# Use TYPE_CHECKING for core components to avoid circular imports
if TYPE_CHECKING:
    # Updated imports to point to new locations
    from ..column.proxy import (  # Adjusted path
        ColumnProxy,
        ExpressionProxy,
        IntoExprColumn,
    )
    from ..frame.base import ActuarialFrame  # Adjusted path


# Register this accessor for frame objects
@register_accessor("finance", kind="frame")
class FinanceFrameAccessor(BaseFrameAccessor):
    """Provides finance-related methods applicable to the entire ActuarialFrame.

    Accessed via `.finance` on an ActuarialFrame instance,
    e.g., `af.finance`.
    """

    def __init__(self, frame: "ActuarialFrame"):
        """Initializes the accessor with the parent ActuarialFrame."""
        super().__init__(frame)

    # --- Frame-level finance methods will go here ---
    def present_value(
        self,
        cashflow_col: "IntoExprColumn",
        rate_col: "IntoExprColumn",
        period_col: "IntoExprColumn",
    ) -> "ExpressionProxy":
        """Calculates the present value of cash flows.

        Assumes cash flows occur at the end of each period.

        Formula: PV = CF / (1 + rate)^period

        Args:
            cashflow_col: Column containing the cash flow amounts.
            rate_col: Column containing the discount rate per period (e.g., 0.05 for 5%).
            period_col: Column containing the period number (e.g., 1, 2, 3...). Must be >= 1.

        Returns:
            An ExpressionProxy representing the present value for each cash flow.
        """
        # Defer import - updated path
        from ..column.proxy import ExpressionProxy

        cf_expr = self._frame._convert_to_expr(cashflow_col)
        rate_expr = self._frame._convert_to_expr(rate_col)
        period_expr = self._frame._convert_to_expr(period_col)

        # Basic PV calculation: PV = CF / (1 + rate)^period
        # Ensure period is >= 1 for the formula to make sense
        pv_expr = (
            pl.when(period_expr >= 1)
            .then(cf_expr / (1 + rate_expr).pow(period_expr))
            .otherwise(pl.lit(None))
        )  # Or 0, or handle differently?

        return ExpressionProxy(pv_expr, self._frame)


# Register this accessor for column/expression objects
@register_accessor("finance", kind="column")
class FinanceColumnAccessor(BaseColumnAccessor):
    """Provides finance-related methods applicable to columns or expressions.

    Accessed via `.finance` on an ActuarialFrame column or expression proxy,
    e.g., `af["my_value_col"].finance`.
    """

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy"):
        """Initializes the accessor with the parent proxy."""
        super().__init__(proxy)
        # Refine type hint for clarity
        self._proxy: "ColumnProxy | ExpressionProxy" = proxy

    def _get_polars_expr(self) -> pl.Expr:
        """Helper to get the underlying Polars expression from the proxy."""
        # Defer import to avoid circularity at runtime - updated path
        from ..column.proxy import ColumnProxy, ExpressionProxy

        if isinstance(self._proxy, ExpressionProxy):
            return self._proxy._expr
        elif isinstance(self._proxy, ColumnProxy):
            return pl.col(self._proxy.name)
        else:
            # Should not happen with correct type hints, but raise defensively
            raise TypeError(
                f"FinanceColumnAccessor expected ColumnProxy or ExpressionProxy, got {type(self._proxy).__name__}"
            )

    # --- Column/Expression-level finance methods will go here ---
    def discount(
        self, rate_expr: "IntoExprColumn", n_periods_expr: "IntoExprColumn"
    ) -> "ExpressionProxy":
        """Discounts the value in the current column/expression.

        Formula: Discounted Value = Value / (1 + rate)^n_periods

        Args:
            rate_expr: The discount rate per period (e.g., 0.05 for 5%).
                       Can be a scalar, column name, or another expression.
            n_periods_expr: The number of periods to discount over.
                            Can be a scalar, column name, or another expression.

        Returns:
            An ExpressionProxy representing the discounted value.
        """
        # Defer import - updated path
        from ..column.proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        parent_frame = self._proxy._parent  # Need the parent to convert other exprs

        if parent_frame is None:
            # Handle case where expression might be standalone (though less common for accessors)
            # In this basic version, we might require a parent frame context.
            raise RuntimeError(
                "Discount operation requires the expression to be part of an ActuarialFrame context."
            )

        # Convert rate and periods using the parent frame's context
        pl_rate_expr = parent_frame._convert_to_expr(rate_expr)
        pl_n_periods_expr = parent_frame._convert_to_expr(n_periods_expr)

        # Calculate discount factor: 1 / (1 + rate)^n
        discount_factor = (1 + pl_rate_expr).pow(pl_n_periods_expr)

        # Apply discount: Value / Discount Factor
        # Handle potential division by zero if discount_factor is 0
        # (e.g., rate = -1). Polars might handle this, but adding a check is safer.
        discounted_expr = (
            pl.when(discount_factor != 0)
            .then(base_expr / discount_factor)
            .otherwise(pl.lit(None))
        )  # Or handle error appropriately

        return ExpressionProxy(discounted_expr, parent_frame)
