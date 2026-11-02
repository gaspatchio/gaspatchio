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

Every shock in a scenario plan names exactly one target: ``table=`` an
assumption table the model reads, by the name the ``Table`` was built with,
or ``column=`` a model-point column -- a valuation rate, an expense, a
solved premium -- that the plan rewrites per scenario before the model runs.
A table shock is confined to some rows with ``FilteredShock(where=...)``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any

import polars as pl

# Type alias for filter conditions
FilterCondition = dict[str, Any]  # e.g., {"duration": {"lte": 5}}

# The two fields that name what a shock moves: an assumption table, or a
# model-point column. A plan's shock names exactly one.
_TARGETS = frozenset({"table", "column"})

# Each shock written with every argument named, as a refusal quotes it. A
# shock's arguments are read in order -- ``ClipShock``'s first is
# ``min_value``, ``PipelineShock``'s second is ``table`` -- so one written
# without its keyword lands in the next slot, and only the keyword says
# which slot was meant.
_SPELLED_OUT: dict[str, str] = {
    "MultiplicativeShock": 'MultiplicativeShock(factor=1.2, table="mortality")',
    "AdditiveShock": 'AdditiveShock(delta=0.01, column="valuation_rate")',
    "OverrideShock": 'OverrideShock(value=0.0, table="lapse")',
    "ClipShock": 'ClipShock(max_value=1.0, table="lapse")',
    "PipelineShock": (
        "PipelineShock(shocks=(MultiplicativeShock(1.4), "
        'ClipShock(max_value=1.0)), column="lapse_rate")'
    ),
    "FilteredShock": (
        "FilteredShock(shock=MultiplicativeShock(1.25), "
        'where={"duration": {"lte": 3}}, table="lapse")'
    ),
    "TimeConditionalShock": (
        "TimeConditionalShock(shock=AdditiveShock(0.40), "
        'when={"policy_year": {"eq": 1}}, table="lapse")'
    ),
    "MaxShock": (
        "MaxShock(shock_a=MultiplicativeShock(0.5), "
        'shock_b=AdditiveShock(-0.2), table="lapse")'
    ),
    "MinShock": (
        "MinShock(shock_a=MultiplicativeShock(1.5), "
        'shock_b=OverrideShock(0.1), table="mortality")'
    ),
}

# What each target names, in the words a refusal uses.
_TARGET_SAID: dict[str, str] = {
    "table": "the name of the assumption table the shock moves",
    "column": "the name of the model-point column the shock moves",
}


def _held(value: object) -> str:
    """Return how a refusal names a misplaced argument: its kind, or its value."""
    if isinstance(value, Shock):
        return f"a {type(value).__name__}"
    shown = repr(value)
    if len(shown) > 60:  # noqa: PLR2004 -- a value quoted in a sentence, not a dump
        shown = f"{shown[:57]}..."
    return f"{shown}, a {type(value).__name__}"


def _misplaced(shock: Shock, name: str, value: object, belongs: str) -> TypeError:
    """Return the refusal for an argument that cannot be what its slot holds."""
    kind = type(shock).__name__
    named = getattr(value, "name", None)
    hint = (
        f" If it is the Table itself, pass its name: {name}={named!r}."
        if name in _TARGETS and not isinstance(value, Shock) and isinstance(named, str)
        else ""
    )
    msg = (
        f"{kind}: {name}= holds {_held(value)}, where {belongs} belongs. A "
        "shock's arguments are read in order, so one written without its "
        "keyword lands in the next slot, and the run would fail on it later. "
        f"Name each argument: {_SPELLED_OUT[kind]}.{hint}"
    )
    return TypeError(msg)


def _refuse_misplaced_arguments(
    shock: Shock,
    *,
    nested: tuple[str, ...] = (),
    sequence: str | None = None,
    condition: str | None = None,
) -> None:
    """Refuse, at construction, an argument that landed in the wrong slot.

    ``PipelineShock(MultiplicativeShock(1.4), ClipShock(1.0))`` built a
    pipeline whose ``table`` was a ``ClipShock`` and failed only at the run,
    with "'ClipShock' object is not iterable". A target is a name; a nested
    shock is a shock; a pipeline's steps are a sequence of shocks; a filter
    is a mapping. Anything else is refused here, naming the keyword spelling.
    """
    for name in ("table", "column"):
        value = getattr(shock, name)
        if value is not None and not isinstance(value, str):
            raise _misplaced(shock, name, value, _TARGET_SAID[name])
    for name in nested:
        value = getattr(shock, name)
        if not isinstance(value, Shock):
            raise _misplaced(shock, name, value, "a shock")
    if sequence is not None:
        _refuse_steps_that_are_not_shocks(shock, sequence)
    if condition is not None:
        value = getattr(shock, condition)
        if not isinstance(value, Mapping):
            raise _misplaced(
                shock, condition, value, 'a condition such as {"age": {"gte": 60}}'
            )


def _refuse_steps_that_are_not_shocks(shock: Shock, sequence: str) -> None:
    """Refuse pipeline steps that are not a sequence of shocks."""
    steps = getattr(shock, sequence)
    if not isinstance(steps, (tuple, list)):
        raise _misplaced(shock, sequence, steps, "a sequence of shocks")
    for step in steps:
        if not isinstance(step, Shock):
            raise _misplaced(shock, sequence, step, "a shock at each step")


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
        return self._canonical(nested=False)

    def _canonical(self, *, nested: bool) -> dict[str, Any]:
        """Return the canonical form, with a nested shock's target left to its outer.

        A shock moves the target its outermost shock names; one nested
        inside it -- a pipeline step, the shock a filter wraps -- may repeat
        that target or name none, and the plan refuses any other. So the two
        spellings say one thing and share one identity, which is what lets a
        plan written down and read back keep its SHA.
        """
        out: dict[str, Any] = {"kind": type(self).__name__}
        for fld in fields(self):  # type: ignore[arg-type]
            if nested and fld.name in _TARGETS:
                out[fld.name] = None
                continue
            out[fld.name] = Shock._encode_field(getattr(self, fld.name))
        return dict(sorted(out.items()))

    @staticmethod
    def _encode_field(val: Any) -> Any:  # noqa: ANN401 — recursive any-encoder by design
        """Recursive JSON-safe encoding for canonical_form field values."""
        if isinstance(val, Shock):
            return val._canonical(nested=True)  # noqa: SLF001 -- the same class
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
        table: The assumption table this shock moves, by the name the
            ``Table`` was built with. A shock names exactly one target.
        column: The model-point column this shock moves, instead of a
            table: a single number the model reads off each policy.

    !!! note "When to use"
        - Stress testing with percentage changes
        - Sensitivity analysis on rates
        - Regulatory capital scenarios (e.g., SCR shocks)

    Examples:
    --------
    **20% increase in mortality:**

    ```python no_output_check
    from gaspatchio.scenarios.shocks import MultiplicativeShock

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

    def __post_init__(self) -> None:
        """Refuse a target that is not a name, naming the keyword spelling."""
        _refuse_misplaced_arguments(self)

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
        table: The assumption table this shock moves, by the name the
            ``Table`` was built with. A shock names exactly one target.
        column: The model-point column this shock moves, instead of a
            table: a single number the model reads off each policy.

    !!! note "When to use"
        - Interest rate shocks (parallel shifts)
        - Expense loading adjustments
        - Basis point changes to rates

    Examples:
    --------
    **Add 50bps to discount rates:**

    ```python no_output_check
    from gaspatchio.scenarios.shocks import AdditiveShock

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

    def __post_init__(self) -> None:
        """Refuse a target that is not a name, naming the keyword spelling."""
        _refuse_misplaced_arguments(self)

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
        table: The assumption table this shock moves, by the name the
            ``Table`` was built with. A shock names exactly one target.
        column: The model-point column this shock moves, instead of a
            table: a single number the model reads off each policy.

    !!! note "When to use"
        - Extreme stress scenarios
        - Disabling a decrement entirely
        - Testing boundary conditions

    Examples:
    --------
    **Set lapse rates to zero:**

    ```python no_output_check
    from gaspatchio.scenarios.shocks import OverrideShock

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

    def __post_init__(self) -> None:
        """Refuse a target that is not a name, naming the keyword spelling."""
        _refuse_misplaced_arguments(self)

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply override shock to column expression."""
        # Cast column to Float64 first to avoid type coercion issues.
        # The original `col * 0 + lit(value)` fails when col is integer
        # and value is float. Casting to Float64 ensures compatibility.
        # (`value` is typed Any, so the sum is too until it is named here.)
        overridden: pl.Expr = col.cast(pl.Float64) * 0 + self.value
        return overridden

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
        table: The assumption table this shock moves, by the name the
            ``Table`` was built with. A shock names exactly one target.
        column: The model-point column this shock moves, instead of a
            table: a single number the model reads off each policy.

    !!! note "When to use"
        - Post-shock value constraints (e.g., lapse ≤ 100%)
        - Regulatory scenarios with actuarial limits
        - Preventing unrealistic shocked values
        - Combining with other shocks in a pipeline

    Examples:
    --------
    **Cap lapse rates at 100%:**

    ```python no_output_check
    from gaspatchio.scenarios.shocks import ClipShock

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
        """Validate the target and that at least one bound is provided."""
        _refuse_misplaced_arguments(self)
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
        table: The assumption table this shock moves, by the name the
            ``Table`` was built with. A shock names exactly one target.
        column: The model-point column this shock moves, instead of a
            table: a single number the model reads off each policy.

    !!! note "When to use"
        - Solvency II lapse up: multiply then cap
        - Complex stress scenarios with multiple transformations
        - Building reusable shock combinations

    Examples:
    --------
    **Solvency II lapse up (multiply by 1.5, cap at 100%):**

    ```python no_output_check
    from gaspatchio.scenarios.shocks import (
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
        """Validate the target and the steps, and that there is at least one."""
        _refuse_misplaced_arguments(self, sequence="shocks")
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
    conditions: list[pl.Expr] = []

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

    Args:
        shock: The shock to apply to matching rows
        where: Filter condition dictionary
        table: The assumption table this shock moves, by the name the
            ``Table`` was built with. A shock names exactly one target.
        column: The model-point column this shock moves, instead of a
            table: a single number the model reads off each policy.

    !!! note "When to use"
        - Apply shocks to specific segments (e.g., early durations)
        - Age-specific mortality adjustments
        - Product-specific lapse stress
        - Regulatory scenarios with conditional shocks

    Examples:
    --------
    **Increase early-duration lapse by 25%:**

    ```python no_output_check
    from gaspatchio.scenarios.shocks import FilteredShock, MultiplicativeShock

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

    def __post_init__(self) -> None:
        """Refuse an argument that landed in the wrong slot, naming the spelling."""
        _refuse_misplaced_arguments(self, nested=("shock",), condition="where")

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply shock only to rows matching the filter."""
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
    A shock that applies only to the time-keyed rows a condition names (WHEN clause).

    Used for time-conditional shocks like "a 40% mass lapse in the first
    policy year only". The condition is read against the shocked table's own
    key columns -- the policy year or duration the table is keyed by -- not
    the model's projection time, so write it in that key's values: a lapse
    table keyed by policy year 1 to 20 has its first year at
    ``{"policy_year": {"eq": 1}}``. A condition on a column the table does not
    hold, or one that selects none of its rows (``{"policy_year": {"eq": 0}}``
    on that table), is refused when the scenario is built, as the scenario
    would otherwise equal BASE.

    Args:
        shock: The shock to apply to the matching rows
        when: Condition on the table's key columns, such as
            ``{"policy_year": {"lte": 5}}``
        table: The assumption table this shock moves, by the name the
            ``Table`` was built with. A shock names exactly one target.
        column: The model-point column this shock moves, instead of a
            table: a single number the model reads off each policy.

    !!! note "When to use"
        - Mass lapse in the first policy year
        - First-year expense shocks
        - Time-limited stress scenarios
        - Shock only during specific periods

    Examples:
    --------
    **Mass lapse in the first policy year** (a lapse table keyed by
    ``policy_year`` from 1):

    ```python no_output_check
    from gaspatchio.scenarios.shocks import TimeConditionalShock, AdditiveShock

    shock = TimeConditionalShock(
        shock=AdditiveShock(delta=0.40),  # Add 40% lapse
        when={"policy_year": {"eq": 1}},
        table="lapse",
    )
    ```

    **Expense shock for the first 5 years** (an expense table keyed by
    ``policy_year`` from 1):

    ```python no_output_check
    shock = TimeConditionalShock(
        shock=MultiplicativeShock(factor=1.10),
        when={"policy_year": {"lte": 5}},
        table="expenses",
    )
    ```

    """

    shock: Shock
    when: FilterCondition
    table: str | None = None
    column: str | None = None

    def __post_init__(self) -> None:
        """Refuse an argument that landed in the wrong slot, naming the spelling."""
        _refuse_misplaced_arguments(self, nested=("shock",), condition="when")

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply shock only at matching times."""
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
class MaxShock(Shock):
    """
    A shock that takes the maximum of two shock expressions.

    Used for scenarios like Solvency II lapse down: "max(lapse * 0.5, lapse - 0.2)"
    where the result is the larger of two transformations.

    Args:
        shock_a: First shock option
        shock_b: Second shock option
        table: The assumption table this shock moves, by the name the
            ``Table`` was built with. A shock names exactly one target.
        column: The model-point column this shock moves, instead of a
            table: a single number the model reads off each policy.

    !!! note "When to use"
        - Solvency II lapse down: max(×0.5, -0.2)
        - Taking the less severe of two shocks
        - Complex regulatory scenarios

    Examples:
    --------
    **Solvency II lapse down:**

    ```python no_output_check
    from gaspatchio.scenarios.shocks import (
        MaxShock,
        MultiplicativeShock,
        AdditiveShock,
    )

    shock = MaxShock(
        shock_a=MultiplicativeShock(factor=0.5),
        shock_b=AdditiveShock(delta=-0.2),
        table="lapse",
    )
    # Result: max(lapse * 0.5, lapse - 0.2)
    ```

    """

    shock_a: Shock
    shock_b: Shock
    table: str | None = None
    column: str | None = None

    def __post_init__(self) -> None:
        """Refuse an argument that landed in the wrong slot, naming the spelling."""
        _refuse_misplaced_arguments(self, nested=("shock_a", "shock_b"))

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply max of two shock expressions."""
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
        table: The assumption table this shock moves, by the name the
            ``Table`` was built with. A shock names exactly one target.
        column: The model-point column this shock moves, instead of a
            table: a single number the model reads off each policy.

    !!! note "When to use"
        - Taking the more severe of two shocks
        - Cap scenarios (similar to ClipShock but based on transformations)
        - Complex regulatory scenarios

    Examples:
    --------
    **Take the lower of two mortality assumptions:**

    ```python no_output_check
    from gaspatchio.scenarios.shocks import (
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

    def __post_init__(self) -> None:
        """Refuse an argument that landed in the wrong slot, naming the spelling."""
        _refuse_misplaced_arguments(self, nested=("shock_a", "shock_b"))

    def to_expression(self, col: pl.Expr) -> pl.Expr:
        """Apply min of two shock expressions."""
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


__all__ = [
    "AdditiveShock",
    "ClipShock",
    "FilterCondition",
    "FilteredShock",
    "MaxShock",
    "MinShock",
    "MultiplicativeShock",
    "OverrideShock",
    "PipelineShock",
    "Shock",
    "TimeConditionalShock",
]
