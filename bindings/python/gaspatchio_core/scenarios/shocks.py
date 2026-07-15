# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Shock specification data model for ad-hoc scenario modifications.
# ABOUTME: Provides shock classes for stress testing: Clip, Pipeline, Filter, etc.

"""Shock specification data model for ad-hoc scenario modifications.

This module provides the core shock types for actuarial stress testing:

- **MultiplicativeShock**: Scale values by a factor (e.g., mortality * 1.2)
- **AdditiveShock**: Add a constant (e.g., rates + 50bps)
- **OverrideShock**: Replace with a constant (e.g., set lapse = 0)
- **ClipShock**: Cap/floor values (e.g., lapse ≤ 100%)
- **PipelineShock**: Chain multiple operations (e.g., multiply then clip)
- **FilteredShock**: Apply shock only to rows matching a filter (where clause)
- **TimeConditionalShock**: Apply shock only at specific projection times (when clause)

These support the full range of Solvency II SCR, IFRS 17, and US RBC scenarios.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl

# Type alias for filter conditions
FilterCondition = dict[str, Any]  # e.g., {"duration": {"lte": 5}}


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

    def canonical_form(self) -> dict[str, Any]:
        """Deterministic JSON-encodable identity recipe for the audit chain.

        Default implementation introspects ``__dataclass_fields__``;
        subclasses with nested shocks recurse via ``_encode_field``.

        Returns:
            Dict with ``"kind"`` (class name) plus every dataclass field,
            sorted by key. Nested ``Shock`` instances recurse.

        Raises:
            TypeError: If a field value is not JSON-encodable
                (e.g. ``OverrideShock`` with a non-scalar value).

        """
        from dataclasses import fields

        out: dict[str, Any] = {"kind": type(self).__name__}
        for fld in fields(self):  # type: ignore[arg-type]
            out[fld.name] = Shock._encode_field(getattr(self, fld.name))
        return dict(sorted(out.items()))

    @staticmethod
    def _encode_field(val: Any) -> Any:  # noqa: ANN401 — recursive any-encoder by design
        """Recursive JSON-safe encoding for canonical_form field values."""
        if isinstance(val, Shock):
            return val.canonical_form()
        if isinstance(val, tuple):
            return [Shock._encode_field(v) for v in val]
        if isinstance(val, list):
            return [Shock._encode_field(v) for v in val]
        if isinstance(val, dict):
            return {k: Shock._encode_field(v) for k, v in sorted(val.items())}
        if isinstance(val, (int, float, str, bool, type(None))):
            return val
        msg = f"Shock field {type(val).__name__} not canonical-encodable"
        raise TypeError(msg)


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


@dataclass(frozen=True)
class ClipShock(Shock):
    """
    A shock that clips (caps/floors) values to a range.

    Used for scenarios like "lapse rate cannot exceed 100%" (max=1.0)
    or "mortality floor of 0.1%" (min=0.001). Can also combine both.

    This is essential for regulatory scenarios like Solvency II SCR lapse up,
    where shocked values must be capped at actuarial limits.

    Args:
        min_value: Optional floor value (values below are set to this)
        max_value: Optional ceiling value (values above are set to this)
        table: Optional table name this shock targets
        column: Optional column name this shock targets

    !!! note "When to use"
        - Post-shock value constraints (e.g., lapse ≤ 100%)
        - Regulatory scenarios with actuarial limits
        - Preventing unrealistic shocked values
        - Combining with other shocks in a pipeline

    Examples:
    --------
    **Cap lapse rates at 100%:**

    ```python no_output_check
    from gaspatchio_core.scenarios.shocks import ClipShock

    shock = ClipShock(max_value=1.0, table="lapse")
    ```

    **Floor mortality at 0.1%:**

    ```python no_output_check
    shock = ClipShock(min_value=0.001, table="mortality")
    ```

    **Clip to a range:**

    ```python no_output_check
    shock = ClipShock(min_value=0.0, max_value=1.0, table="rates")
    ```

    """

    min_value: float | None = None
    max_value: float | None = None
    table: str | None = None
    column: str | None = None

    def __post_init__(self) -> None:
        """Validate that at least one bound is provided."""
        if self.min_value is None and self.max_value is None:
            msg = "ClipShock requires at least one of min_value or max_value"
            raise ValueError(msg)
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            msg = (
                f"ClipShock min_value ({self.min_value}) cannot exceed "
                f"max_value ({self.max_value})"
            )
            raise ValueError(msg)

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply clip shock to column expression."""
        import polars as pl

        result = col
        if self.min_value is not None:
            result = (
                pl.when(result < self.min_value)
                .then(pl.lit(self.min_value))
                .otherwise(result)
            )
        if self.max_value is not None:
            result = (
                pl.when(result > self.max_value)
                .then(pl.lit(self.max_value))
                .otherwise(result)
            )
        return result

    def describe(self) -> str:
        """Return description of this shock."""
        target = ""
        if self.table:
            target = f" {self.table}"
        if self.column:
            target += f".{self.column}" if self.table else f" {self.column}"

        if self.min_value is not None and self.max_value is not None:
            return f"clip{target} to [{self.min_value}, {self.max_value}]"
        if self.min_value is not None:
            return f"clip{target} min={self.min_value}"
        return f"clip{target} max={self.max_value}"


@dataclass(frozen=True)
class PipelineShock(Shock):
    """
    A shock that chains multiple operations in sequence.

    Used for complex scenarios like "multiply by 1.5 then cap at 100%"
    which requires composing multiple shock operations.

    The operations are applied left-to-right: the output of each
    shock becomes the input to the next.

    Args:
        shocks: Sequence of shocks to apply in order
        table: Optional table name this shock targets
        column: Optional column name this shock targets

    !!! note "When to use"
        - Solvency II lapse up: multiply then cap
        - Complex stress scenarios with multiple transformations
        - Building reusable shock combinations

    Examples:
    --------
    **Solvency II lapse up (multiply by 1.5, cap at 100%):**

    ```python no_output_check
    from gaspatchio_core.scenarios.shocks import (
        PipelineShock,
        MultiplicativeShock,
        ClipShock,
    )

    shock = PipelineShock(
        shocks=[
            MultiplicativeShock(factor=1.5),
            ClipShock(max_value=1.0),
        ],
        table="lapse",
    )
    ```

    **Lapse down with floor (multiply by 0.5, floor at original - 0.2):**

    This would need a custom approach for relative floors.

    """

    shocks: tuple[Shock, ...] = field(default_factory=tuple)
    table: str | None = None
    column: str | None = None

    def __post_init__(self) -> None:
        """Validate that at least one shock is provided."""
        if not self.shocks:
            msg = "PipelineShock requires at least one shock in the pipeline"
            raise ValueError(msg)

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply all shocks in sequence."""
        result = col
        for shock in self.shocks:
            result = shock.to_expression(result)
        return result

    def describe(self) -> str:
        """Return description of this shock."""
        target = ""
        if self.table:
            target = f" to {self.table}"
        if self.column:
            target += f".{self.column}" if self.table else f" to {self.column}"

        steps = [s.describe() for s in self.shocks]
        return f"pipeline{target}: " + " → ".join(steps)


def _build_filter_expr(filter_config: FilterCondition) -> pl.Expr:
    """
    Build a Polars expression from a filter configuration.

    Supports:
    - Simple equality: {"sex": "F"}
    - Comparison operators: {"age": {"gte": 65}}
    - Range: {"duration": {"between": [1, 5]}}
    - Multiple conditions (AND): {"sex": "F", "age": {"gte": 65}}

    Args:
        filter_config: Dictionary of filter conditions

    Returns:
        Polars boolean expression for the filter

    """
    import polars as pl

    conditions = []

    for column, condition in filter_config.items():
        if isinstance(condition, dict):
            # Comparison operators
            for op, value in condition.items():
                if op == "eq":
                    conditions.append(pl.col(column) == value)
                elif op == "ne":
                    conditions.append(pl.col(column) != value)
                elif op == "gt":
                    conditions.append(pl.col(column) > value)
                elif op == "gte":
                    conditions.append(pl.col(column) >= value)
                elif op == "lt":
                    conditions.append(pl.col(column) < value)
                elif op == "lte":
                    conditions.append(pl.col(column) <= value)
                elif op == "between":
                    low, high = value
                    conditions.append(
                        (pl.col(column) >= low) & (pl.col(column) <= high)
                    )
                elif op == "in":
                    conditions.append(pl.col(column).is_in(value))
                elif op == "not_in":
                    conditions.append(~pl.col(column).is_in(value))
                else:
                    msg = f"Unknown filter operator: {op}"
                    raise ValueError(msg)
        else:
            # Simple equality
            conditions.append(pl.col(column) == condition)

    # Combine with AND
    if not conditions:
        return pl.lit(True)

    result = conditions[0]
    for cond in conditions[1:]:
        result = result & cond

    return result


@dataclass(frozen=True)
class FilteredShock(Shock):
    """
    A shock that applies only to rows matching a filter condition (WHERE clause).

    Used for dimension-filtered shocks like "increase early-duration lapse by 25%"
    where only rows matching the filter are modified.

    This implements GSP-65: Dimension-filtered shocks.

    Args:
        shock: The shock to apply to matching rows
        where: Filter condition dictionary
        table: Optional table name this shock targets
        column: Optional column name this shock targets

    !!! note "When to use"
        - Apply shocks to specific segments (e.g., early durations)
        - Age-specific mortality adjustments
        - Product-specific lapse stress
        - Regulatory scenarios with conditional shocks

    Examples:
    --------
    **Increase early-duration lapse by 25%:**

    ```python no_output_check
    from gaspatchio_core.scenarios.shocks import FilteredShock, MultiplicativeShock

    shock = FilteredShock(
        shock=MultiplicativeShock(factor=1.25),
        where={"duration": {"lte": 3}},
        table="lapse",
    )
    ```

    **Mortality shock for elderly lives:**

    ```python no_output_check
    shock = FilteredShock(
        shock=MultiplicativeShock(factor=1.15),
        where={"attained_age": {"gte": 65}},
        table="mortality",
    )
    ```

    **Complex filter with multiple conditions:**

    ```python no_output_check
    shock = FilteredShock(
        shock=AdditiveShock(delta=0.02),
        where={"sex": "F", "smoker_status": "S"},
        table="mortality",
    )
    ```

    """

    shock: Shock
    where: FilterCondition
    table: str | None = None
    column: str | None = None

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply shock only to rows matching the filter."""
        import polars as pl

        filter_expr = _build_filter_expr(self.where)
        shocked_expr = self.shock.to_expression(col)

        return pl.when(filter_expr).then(shocked_expr).otherwise(col)

    def describe(self) -> str:
        """Return description of this shock."""
        target = ""
        if self.table:
            target = f" to {self.table}"
        if self.column:
            target += f".{self.column}" if self.table else f" to {self.column}"

        # Format the filter conditions
        filter_parts = []
        for column, condition in self.where.items():
            if isinstance(condition, dict):
                for op, value in condition.items():
                    if op == "between":
                        filter_parts.append(f"{value[0]} ≤ {column} ≤ {value[1]}")
                    else:
                        op_symbols = {
                            "eq": "=",
                            "ne": "≠",
                            "gt": ">",
                            "gte": "≥",
                            "lt": "<",
                            "lte": "≤",
                            "in": "∈",
                            "not_in": "∉",
                        }
                        filter_parts.append(
                            f"{column} {op_symbols.get(op, op)} {value}"
                        )
            else:
                filter_parts.append(f"{column} = {condition}")

        filter_str = " AND ".join(filter_parts)
        return f"{self.shock.describe()}{target} WHERE {filter_str}"


@dataclass(frozen=True)
class TimeConditionalShock(Shock):
    """
    A shock that applies only at specific projection times (WHEN clause).

    Used for time-conditional shocks like "40% mass lapse at t=0 only"
    where the shock is applied based on projection period.

    This implements GSP-74: Time-conditional shocks.

    Args:
        shock: The shock to apply at matching times
        when: Time condition dictionary (uses 't' column by default)
        table: Optional table name this shock targets
        column: Optional column name this shock targets
        time_column: Column name for time (default: "t")

    !!! note "When to use"
        - Mass lapse at policy inception (t=0)
        - First-year expense shocks
        - Time-limited stress scenarios
        - Shock only during specific periods

    Examples:
    --------
    **Mass lapse at t=0:**

    ```python no_output_check
    from gaspatchio_core.scenarios.shocks import TimeConditionalShock, AdditiveShock

    shock = TimeConditionalShock(
        shock=AdditiveShock(delta=0.40),  # Add 40% lapse
        when={"t": {"eq": 0}},
        table="lapse",
    )
    ```

    **Expense shock for first 5 years:**

    ```python no_output_check
    shock = TimeConditionalShock(
        shock=MultiplicativeShock(factor=1.10),
        when={"t": {"lte": 5}},
        table="expenses",
    )
    ```

    """

    shock: Shock
    when: FilterCondition
    table: str | None = None
    column: str | None = None
    time_column: str = "t"

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply shock only at matching times."""
        import polars as pl

        filter_expr = _build_filter_expr(self.when)
        shocked_expr = self.shock.to_expression(col)

        return pl.when(filter_expr).then(shocked_expr).otherwise(col)

    def describe(self) -> str:
        """Return description of this shock."""
        target = ""
        if self.table:
            target = f" to {self.table}"
        if self.column:
            target += f".{self.column}" if self.table else f" to {self.column}"

        # Format the time conditions
        filter_parts = []
        for column, condition in self.when.items():
            if isinstance(condition, dict):
                for op, value in condition.items():
                    if op == "between":
                        filter_parts.append(f"{value[0]} ≤ {column} ≤ {value[1]}")
                    else:
                        op_symbols = {
                            "eq": "=",
                            "ne": "≠",
                            "gt": ">",
                            "gte": "≥",
                            "lt": "<",
                            "lte": "≤",
                        }
                        filter_parts.append(
                            f"{column} {op_symbols.get(op, op)} {value}"
                        )
            else:
                filter_parts.append(f"{column} = {condition}")

        filter_str = " AND ".join(filter_parts)
        return f"{self.shock.describe()}{target} WHEN {filter_str}"


@dataclass(frozen=True)
class RelativeFloorShock(Shock):
    """
    A shock that applies a floor relative to the original value.

    Used for scenarios like Solvency II lapse down: "max(lapse × 0.5, lapse - 0.2)"
    where the floor is relative to the original value, not absolute.

    Args:
        delta: The maximum decrease from original value
        table: Optional table name this shock targets
        column: Optional column name this shock targets

    !!! note "When to use"
        - Solvency II lapse down scenario
        - Relative floors that depend on original values
        - Preventing excessive decreases

    !!! warning "Not yet implemented"
        ``RelativeFloorShock`` raises ``NotImplementedError`` at execution:
        applying a relative floor needs the pre-shock table values at shock
        time, which the pipeline does not yet thread through. Construction
        and serialization succeed (plans can declare intent), but a run
        fails loudly instead of silently skipping the floor. Until it is
        implemented, apply relative floors in model code — e.g. compute the
        shocked rate as the maximum of ``rate * 0.5`` and ``rate - 0.2``
        with ``when/then/otherwise`` on the looked-up column.

    """

    delta: float
    table: str | None = None
    column: str | None = None

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Raise — ``RelativeFloorShock`` is not implemented.

        A floor *relative to the pre-shock original value* cannot be computed
        here: by the time this shock runs, ``col`` is already the shocked value
        and the original is unavailable. The previous placeholder floored at
        ``col - delta`` using the shocked value, so the condition was never true
        and the shock silently did nothing. Use :class:`MaxShock` instead, which
        composes the two transformations explicitly.
        """
        del col
        msg = (
            "RelativeFloorShock is not implemented: a floor relative to the "
            "original (pre-shock) value cannot be computed here because this "
            "shock only receives the already-shocked value. Use MaxShock "
            "instead to express 'max(shocked, original - delta)' (e.g. the "
            "Solvency II lapse-down max(lapse*0.5, lapse-0.2)); see the MaxShock "
            "docstring."
        )
        raise NotImplementedError(msg)

    def describe(self) -> str:
        """Return description of this shock."""
        target = ""
        if self.table:
            target = f" {self.table}"
        if self.column:
            target += f".{self.column}" if self.table else f" {self.column}"
        return f"relative_floor{target} (original - {self.delta})"


@dataclass(frozen=True)
class MaxShock(Shock):
    """
    A shock that takes the maximum of two shock expressions.

    Used for scenarios like Solvency II lapse down: "max(lapse × 0.5, lapse - 0.2)"
    where the result is the larger of two transformations.

    Args:
        shock_a: First shock option
        shock_b: Second shock option
        table: Optional table name this shock targets
        column: Optional column name this shock targets

    !!! note "When to use"
        - Solvency II lapse down: max(×0.5, -0.2)
        - Taking the less severe of two shocks
        - Complex regulatory scenarios

    Examples:
    --------
    **Solvency II lapse down:**

    ```python no_output_check
    from gaspatchio_core.scenarios.shocks import (
        MaxShock,
        MultiplicativeShock,
        AdditiveShock,
    )

    shock = MaxShock(
        shock_a=MultiplicativeShock(factor=0.5),
        shock_b=AdditiveShock(delta=-0.2),
        table="lapse",
    )
    # Result: max(lapse × 0.5, lapse - 0.2)
    ```

    """

    shock_a: Shock
    shock_b: Shock
    table: str | None = None
    column: str | None = None

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply max of two shock expressions."""
        import polars as pl

        expr_a = self.shock_a.to_expression(col)
        expr_b = self.shock_b.to_expression(col)

        return pl.max_horizontal(expr_a, expr_b)

    def describe(self) -> str:
        """Return description of this shock."""
        target = ""
        if self.table:
            target = f" to {self.table}"
        if self.column:
            target += f".{self.column}" if self.table else f" to {self.column}"
        return f"max({self.shock_a.describe()}, {self.shock_b.describe()}){target}"


@dataclass(frozen=True)
class MinShock(Shock):
    """
    A shock that takes the minimum of two shock expressions.

    Used for scenarios where the result should be the smaller of two
    transformations.

    Args:
        shock_a: First shock option
        shock_b: Second shock option
        table: Optional table name this shock targets
        column: Optional column name this shock targets

    !!! note "When to use"
        - Taking the more severe of two shocks
        - Cap scenarios (similar to ClipShock but based on transformations)
        - Complex regulatory scenarios

    Examples:
    --------
    **Take the lower of two mortality assumptions:**

    ```python no_output_check
    from gaspatchio_core.scenarios.shocks import (
        MinShock,
        MultiplicativeShock,
        OverrideShock,
    )

    shock = MinShock(
        shock_a=MultiplicativeShock(factor=1.5),
        shock_b=OverrideShock(value=0.1),  # Cap at 10% mortality
        table="mortality",
    )
    ```

    """

    shock_a: Shock
    shock_b: Shock
    table: str | None = None
    column: str | None = None

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply min of two shock expressions."""
        import polars as pl

        expr_a = self.shock_a.to_expression(col)
        expr_b = self.shock_b.to_expression(col)

        return pl.min_horizontal(expr_a, expr_b)

    def describe(self) -> str:
        """Return description of this shock."""
        target = ""
        if self.table:
            target = f" to {self.table}"
        if self.column:
            target += f".{self.column}" if self.table else f" to {self.column}"
        return f"min({self.shock_a.describe()}, {self.shock_b.describe()}){target}"


@dataclass(frozen=True)
class ParameterShock:
    """
    A shock specification for scalar model parameters (not table values).

    Used for scenarios like "increase expense inflation by 1%" where the
    target is a scalar model input rather than an assumption table.

    Unlike table shocks, parameter shocks store the transformation specification
    and are applied at model setup time by the model code.

    Args:
        param: Name of the parameter to shock
        operation: Type of operation ("multiply", "add", or "set")
        value: Value for the operation (factor, delta, or constant)

    !!! note "When to use"
        - Shocking scalar model inputs (expense inflation, discount rate spread)
        - Parameters that aren't stored in assumption tables
        - Model-level sensitivity analysis

    !!! warning "Not a Shock subclass"
        ParameterShock is NOT a Shock subclass because it doesn't operate on
        Polars expressions. It stores the shock specification for the model
        code to apply.

    Examples:
    --------
    **Add 1% to expense inflation:**

    ```python no_output_check
    from gaspatchio_core.scenarios.shocks import ParameterShock

    shock = ParameterShock(param="expense_inflation", operation="add", value=0.01)

    # Apply in model code:
    base_inflation = 0.02
    shocked_inflation = shock.apply(base_inflation)  # 0.03
    ```

    **Multiply discount spread:**

    ```python no_output_check
    shock = ParameterShock(param="discount_spread", operation="multiply", value=1.5)
    ```

    """

    param: str
    operation: str  # "multiply", "add", or "set"
    value: float

    def __post_init__(self) -> None:
        """Validate operation type."""
        valid_ops = {"multiply", "add", "set"}
        if self.operation not in valid_ops:
            msg = f"ParameterShock operation must be one of {valid_ops}, got '{self.operation}'"
            raise ValueError(msg)

    def apply(self, base_value: float) -> float:
        """
        Apply this shock to a base parameter value.

        Args:
            base_value: The original parameter value

        Returns:
            The shocked parameter value

        """
        if self.operation == "multiply":
            return base_value * self.value
        if self.operation == "add":
            return base_value + self.value
        # "set"
        return self.value

    def describe(self) -> str:
        """Return a human-readable description of this shock."""
        if self.operation == "multiply":
            return f"param {self.param} × {self.value}"
        if self.operation == "add":
            sign = "+" if self.value >= 0 else ""
            return f"param {self.param} {sign}{self.value}"
        # "set"
        return f"param {self.param} = {self.value}"


__all__ = [
    "AdditiveShock",
    "ClipShock",
    "FilterCondition",
    "FilteredShock",
    "MaxShock",
    "MinShock",
    "MultiplicativeShock",
    "OverrideShock",
    "ParameterShock",
    "PipelineShock",
    "RelativeFloorShock",
    "Shock",
    "TimeConditionalShock",
]
