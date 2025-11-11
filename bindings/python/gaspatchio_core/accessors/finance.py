"""Accessors for finance-related operations on ActuarialFrame objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import polars as pl

from gaspatchio_core.accessors.base import BaseColumnAccessor, BaseFrameAccessor
from gaspatchio_core.frame.registry import register_accessor

if TYPE_CHECKING:
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.frame.base import ActuarialFrame
    from gaspatchio_core.typing import IntoExprColumn


# Register this accessor for frame objects
@register_accessor("finance", kind="frame")
class FinanceFrameAccessor(BaseFrameAccessor):
    """Provide finance-related methods applicable to the entire ActuarialFrame.

    Accessed via `.finance` on an ActuarialFrame instance,
    e.g., `af.finance`.
    """

    def __init__(self, frame: ActuarialFrame) -> None:
        """Initialize the accessor with the parent ActuarialFrame."""
        super().__init__(frame)

    # --- Frame-level finance methods will go here ---
    def present_value(
        self,
        cashflow_col: IntoExprColumn,
        rate_col: IntoExprColumn,
        period_col: IntoExprColumn,
    ) -> ExpressionProxy:
        """Calculate the present value of cash flows.

        Assumes cash flows occur at the end of each period.

        Formula: PV = CF / (1 + rate)^period

        Args:
            cashflow_col: Column containing the cash flow amounts.
            rate_col: Column with discount rate per period (e.g., 0.05 for 5%).
            period_col: Column with period number (e.g., 1, 2, 3). Must be >= 1.

        Returns:
            An ExpressionProxy representing the present value for each cash flow.

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        cf_expr = self._frame._convert_to_expr(cashflow_col)  # noqa: SLF001
        rate_expr = self._frame._convert_to_expr(rate_col)  # noqa: SLF001
        period_expr = self._frame._convert_to_expr(period_col)  # noqa: SLF001

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
    """Provide finance-related methods applicable to columns or expressions.

    Accessed via `.finance` on an ActuarialFrame column or expression proxy,
    e.g., `af["my_value_col"].finance`.
    """

    def __init__(self, proxy: ColumnProxy | ExpressionProxy) -> None:
        """Initialize the accessor with the parent proxy."""
        super().__init__(proxy)
        # Refine type hint for clarity
        self._proxy: ColumnProxy | ExpressionProxy = proxy

    def _get_polars_expr(self) -> pl.Expr:
        """Get the underlying Polars expression from the proxy."""
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        if isinstance(self._proxy, ExpressionProxy):
            return self._proxy._expr  # noqa: SLF001
        if isinstance(self._proxy, ColumnProxy):
            return pl.col(self._proxy.name)
        # Should not happen with correct type hints, but raise defensively
        msg = (
            f"FinanceColumnAccessor expected ColumnProxy or "
            f"ExpressionProxy, got {type(self._proxy).__name__}"
        )
        raise TypeError(msg)

    # --- Column/Expression-level finance methods will go here ---
    def to_monthly(
        self,
        method: Literal["compound", "simple"] = "compound",
    ) -> ExpressionProxy:
        """Convert annual interest rate to monthly rate.

        Transforms annual effective interest rates to equivalent monthly rates
        using either compound or simple interest conventions.

        Parameters
        ----------
        method : {"compound", "simple"}, default "compound"
            Conversion method:
            - "compound": (1 + r_annual)^(1/12) - 1 (standard actuarial)
            - "simple": r_annual / 12 (linear approximation)

        Returns
        -------
        ExpressionProxy
            Monthly interest rate with same structure as input (scalar/list)

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        parent_frame = self._proxy._parent  # noqa: SLF001

        if parent_frame is None:
            msg = (
                "to_monthly() requires the expression to be part of an "
                "ActuarialFrame context."
            )
            raise RuntimeError(msg)

        # Compound conversion: (1 + annual)^(1/12) - 1
        if method == "compound":
            monthly_expr = ((1 + base_expr).pow(1 / 12)) - 1
        elif method == "simple":
            # Simple conversion: annual / 12
            monthly_expr = base_expr / 12
        else:
            msg = f"method must be 'compound' or 'simple', got '{method}'"
            raise ValueError(msg)

        return ExpressionProxy(monthly_expr, parent_frame)

    def discount(
        self, rate_expr: IntoExprColumn, n_periods_expr: IntoExprColumn
    ) -> ExpressionProxy:
        """Discount the value in the current column/expression.

        Formula: Discounted Value = Value / (1 + rate)^n_periods

        Args:
            rate_expr: The discount rate per period (e.g., 0.05 for 5%).
                       Can be a scalar, column name, or another expression.
            n_periods_expr: The number of periods to discount over.
                            Can be a scalar, column name, or another expression.

        Returns:
            An ExpressionProxy representing the discounted value.

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        parent_frame = self._proxy._parent  # noqa: SLF001

        if parent_frame is None:
            # Handle case where expression might be standalone
            # In this basic version, we require a parent frame context.
            msg = (
                "Discount operation requires the expression to be part of "
                "an ActuarialFrame context."
            )
            raise RuntimeError(msg)

        # Convert rate and periods using the parent frame's context
        pl_rate_expr = parent_frame._convert_to_expr(rate_expr)  # noqa: SLF001
        pl_n_periods_expr = parent_frame._convert_to_expr(  # noqa: SLF001
            n_periods_expr
        )

        # Calculate discount factor: 1 / (1 + rate)^n
        discount_factor = (1 + pl_rate_expr).pow(pl_n_periods_expr)

        # Apply discount: Value / Discount Factor
        # Handle potential division by zero if discount_factor is 0
        # (e.g., rate = -1). Polars might handle this, but check safer.
        discounted_expr = (
            pl.when(discount_factor != 0)
            .then(base_expr / discount_factor)
            .otherwise(pl.lit(None))
        )  # Or handle error appropriately

        return ExpressionProxy(discounted_expr, parent_frame)
