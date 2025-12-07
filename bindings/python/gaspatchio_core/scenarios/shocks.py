# ABOUTME: Shock specification data model for ad-hoc scenario modifications.
# ABOUTME: Provides MultiplicativeShock, AdditiveShock, and OverrideShock classes.

"""Shock specification data model for ad-hoc scenario modifications."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl


class Shock(ABC):
    """Base class for shock specifications."""

    table: str | None
    column: str | None

    @abstractmethod
    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """
        Convert this shock to a Polars expression.

        Args:
            col: The column expression to apply the shock to

        Returns:
            Modified expression with shock applied

        """

    @abstractmethod
    def describe(self) -> str:
        """
        Return a human-readable description of this shock.

        Returns:
            Description string for audit trails

        """


@dataclass(frozen=True)
class MultiplicativeShock(Shock):
    """
    A shock that multiplies values by a factor.

    Used for scenarios like "increase mortality by 20%" (factor=1.2)
    or "decrease lapse by 10%" (factor=0.9).

    Args:
        factor: The multiplicative factor to apply
        table: Optional table name this shock targets
        column: Optional column name this shock targets

    !!! note "When to use"
        - Stress testing with percentage changes
        - Sensitivity analysis on rates
        - Regulatory capital scenarios (e.g., SCR shocks)

    Examples:
    --------
    **20% increase in mortality:**

    ```python no_output_check
    from gaspatchio_core.scenarios.shocks import MultiplicativeShock

    shock = MultiplicativeShock(factor=1.2, table="mortality")
    ```

    **10% decrease in lapse rates:**

    ```python no_output_check
    shock = MultiplicativeShock(factor=0.9, table="lapse")
    ```

    """

    factor: float
    table: str | None = None
    column: str | None = None

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply multiplicative shock to column expression."""
        return col * self.factor

    def describe(self) -> str:
        """Return description of this shock."""
        target = ""
        if self.table:
            target = f" to {self.table}"
        if self.column:
            target += f".{self.column}" if self.table else f" to {self.column}"
        return f"multiply{target} by {self.factor}"


@dataclass(frozen=True)
class AdditiveShock(Shock):
    """
    A shock that adds a constant delta to values.

    Used for scenarios like "increase discount rate by 50bps" (delta=0.005)
    or "decrease expense loading by 1%" (delta=-0.01).

    Args:
        delta: The additive constant to apply
        table: Optional table name this shock targets
        column: Optional column name this shock targets

    !!! note "When to use"
        - Interest rate shocks (parallel shifts)
        - Expense loading adjustments
        - Basis point changes to rates

    Examples:
    --------
    **Add 50bps to discount rates:**

    ```python no_output_check
    from gaspatchio_core.scenarios.shocks import AdditiveShock

    shock = AdditiveShock(delta=0.005, table="discount_rates")
    ```

    **Subtract 1% from expense loading:**

    ```python no_output_check
    shock = AdditiveShock(delta=-0.01, table="expenses")
    ```

    """

    delta: float
    table: str | None = None
    column: str | None = None

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply additive shock to column expression."""
        return col + self.delta

    def describe(self) -> str:
        """Return description of this shock."""
        target = ""
        if self.table:
            target = f" to {self.table}"
        if self.column:
            target += f".{self.column}" if self.table else f" to {self.column}"
        sign = "+" if self.delta >= 0 else ""
        return f"add{target} {sign}{self.delta}"


@dataclass(frozen=True)
class OverrideShock(Shock):
    """
    A shock that replaces all values with a constant.

    Used for scenarios like "set lapse to zero" (value=0.0)
    or "assume 100% mortality" (value=1.0).

    Args:
        value: The constant value to set
        table: Optional table name this shock targets
        column: Optional column name this shock targets

    !!! note "When to use"
        - Extreme stress scenarios
        - Disabling a decrement entirely
        - Testing boundary conditions

    Examples:
    --------
    **Set lapse rates to zero:**

    ```python no_output_check
    from gaspatchio_core.scenarios.shocks import OverrideShock

    shock = OverrideShock(value=0.0, table="lapse")
    ```

    **Override discount rate to flat 5%:**

    ```python no_output_check
    shock = OverrideShock(value=0.05, table="discount_rates")
    ```

    """

    value: Any
    table: str | None = None
    column: str | None = None

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply override shock to column expression."""
        import polars as pl

        # Cast column to Float64 first to avoid type coercion issues.
        # The original `col * 0 + lit(value)` fails when col is integer
        # and value is float. Casting to Float64 ensures compatibility.
        return col.cast(pl.Float64) * 0 + self.value

    def describe(self) -> str:
        """Return description of this shock."""
        target = ""
        if self.table:
            target = f" {self.table}"
        if self.column:
            target += f".{self.column}" if self.table else f" {self.column}"
        return f"set{target} = {self.value}"


__all__ = [
    "AdditiveShock",
    "MultiplicativeShock",
    "OverrideShock",
    "Shock",
]
