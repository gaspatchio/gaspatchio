"""Accessors for Excel-related operations on ActuarialFrame columns/expressions."""

import datetime
from typing import TYPE_CHECKING

import polars as pl

# Import registry decorator
from ..frame.registry import register_accessor

# Use the new base location
from .base import BaseColumnAccessor, BaseFrameAccessor

# Use TYPE_CHECKING for core components to avoid circular imports
if TYPE_CHECKING:
    # Update imports to new locations
    from ..column.column_proxy import ColumnProxy
    from ..column.expression_proxy import ExpressionProxy
    from ..frame.base import ActuarialFrame
    from ..typing import IntoExprColumn  # Added for yearfrac


@register_accessor("excel", kind="frame")
class ExcelFrameAccessor(BaseFrameAccessor):
    """Provides Excel-related methods applicable to the entire ActuarialFrame.

    Accessed via `.excel` on an ActuarialFrame instance,
    e.g., `af.excel`.
    """

    def __init__(self, frame: "ActuarialFrame"):
        """Initializes the accessor with the parent ActuarialFrame."""
        super().__init__(frame)
        # Placeholder for any frame-level excel methods


@register_accessor("excel", kind="column")
class ExcelColumnAccessor(BaseColumnAccessor):
    """Provides Excel-related methods applicable to columns or expressions.

    Accessed via `.excel` on an ActuarialFrame column or expression proxy,
    e.g., `af["my_excel_col"].excel`.
    """

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy"):
        """Initializes the accessor with the parent proxy."""
        super().__init__(proxy)
        self._proxy: "ColumnProxy | ExpressionProxy" = proxy

    def _get_polars_expr(self) -> pl.Expr:
        """Helper to get the underlying Polars expression from the proxy."""
        if hasattr(self._proxy, "_expr") and isinstance(self._proxy._expr, pl.Expr):
            return self._proxy._expr
        elif hasattr(self._proxy, "name") and isinstance(self._proxy.name, str):
            return pl.col(self._proxy.name)
        else:
            raise TypeError(
                f"ExcelColumnAccessor expected ColumnProxy or ExpressionProxy, got {type(self._proxy).__name__}"
            )

    def _get_parent_frame(self) -> "ActuarialFrame":
        """Helper to get the parent ActuarialFrame, raising error if absent."""
        if not hasattr(self._proxy, "_parent") or self._proxy._parent is None:
            raise RuntimeError(
                "Operation requires the expression/column to be part of an ActuarialFrame context."
            )
        return self._proxy._parent

    def from_excel_serial(self, epoch: str = "1900") -> "ExpressionProxy":
        """Converts Excel serial numbers (integers or floats) to Polars Date.
        Follows logic similar to openpyxl for compatibility.

        1900 Epoch (WINDOWS_1900_EPOCH = 1899-12-30):
        - Serial 1 is 1900-01-01.
        - Excel's serial 60 (phantom 1900-02-29) is mapped to 1900-03-01.
        - Serials > 60 are adjusted by -1 day before adding to epoch.
        1904 Epoch (MAC_1904_EPOCH = 1904-01-01):
        - Serial 1 is 1904-01-01. Days to add from epoch are serial - 1.
        Args:
            epoch: The epoch system used by Excel ('1900' or '1904').
                   Defaults to '1900'.
        Returns:
            An ExpressionProxy representing the converted date column.
        Raises:
            ValueError: If an invalid epoch is provided.
        """
        base_expr = self._get_polars_expr()
        numeric_expr = base_expr.cast(pl.Float64, strict=False)
        int_expr = numeric_expr.floor()  # For exact comparison like == 60

        if epoch == "1900":
            EPOCH_DT = datetime.date(1899, 12, 30)

            # Adjust serial for numbers > 60 due to Excel's 1900 leap year bug
            # This serial is then added to EPOCH_DT
            effective_serial_days = (
                pl.when(numeric_expr > 60)
                .then(numeric_expr - 1)
                .otherwise(numeric_expr)
            )

            date_expr = (
                pl.when(numeric_expr < 1)
                .then(None)  # Invalid serial
                .when(int_expr == 60)
                .then(pl.lit(datetime.date(1900, 3, 1)))  # Correct Excel's 1900-02-29
                .otherwise(pl.lit(EPOCH_DT) + pl.duration(days=effective_serial_days))
                .cast(pl.Date)
            )

        elif epoch == "1904":
            EPOCH_DT = datetime.date(1904, 1, 1)
            # For 1904 epoch, serial 1 is the first day (Jan 1, 1904).
            # So, timedelta to add is (serial - 1) days.
            days_to_add = numeric_expr - 1

            date_expr = (
                pl.when(numeric_expr < 1)
                .then(None)  # serial 0 or less is invalid if 1 is first day
                .otherwise(pl.lit(EPOCH_DT) + pl.duration(days=days_to_add))
                .cast(pl.Date)
            )

        else:
            raise ValueError(f"Invalid epoch '{epoch}'. Must be '1900' or '1904'.")

        parent_frame = self._get_parent_frame()
        from ..column.expression_proxy import ExpressionProxy

        return ExpressionProxy(date_expr, parent_frame)

    def yearfrac(
        self, end_date_expr: "IntoExprColumn", basis: str = "act/act"
    ) -> "ExpressionProxy":
        """Calculates the fraction of a year between the date in this column/expression
        and another date expression, based on a day count convention.

        Note: This requires a custom implementation as Polars doesn't have built-in yearfrac.
              The current implementation is a simplified placeholder using 'act/act'.

        Args:
            end_date_expr: The end date for the period (column name, expression, or literal).
            basis: The day count basis (e.g., "act/act", "30/360").
                   Currently, only a simplified "act/act" is implemented.

        Returns:
            An ExpressionProxy representing the year fraction (float).

        Raises:
            NotImplementedError: If a basis other than the simplified "act/act" is requested.
            ValueError: If end_date_expr is invalid.
            RuntimeError: If the proxy is not part of an ActuarialFrame context.
            pl.ComputeError: On date difference calculation errors.
        """
        parent_frame = self._get_parent_frame()
        start_expr = self._get_polars_expr()
        try:
            # Ensure ExpressionProxy is imported if not already at module level for type hint
            # from ..column.expression_proxy import ExpressionProxy # Already imported locally in from_excel_serial
            end_expr = parent_frame._convert_to_expr(end_date_expr)
        except Exception as e:
            raise ValueError(f"Invalid end_date_expr provided: {e}") from e

        if basis.lower() == "act/act":
            start_date = start_expr.cast(pl.Date)
            end_date = end_expr.cast(pl.Date)
            days_diff = (end_date - start_date).dt.total_days()
            year_frac_expr = days_diff / 365.25
        else:
            raise NotImplementedError(f"Day count basis '{basis}' not yet implemented.")

        # Ensure ExpressionProxy is available for return
        from ..column.expression_proxy import ExpressionProxy

        return ExpressionProxy(year_frac_expr.cast(pl.Float64), parent_frame)
