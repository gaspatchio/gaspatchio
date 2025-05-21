# Extending the ActuarialFrame Accessor System

This guide explains how to add new functionality to the `ActuarialFrame` DSL by either adding methods to existing accessors (like `.date` or `.finance`) or by creating entirely new accessor namespaces (like a potential `.mortality` accessor).

This system is designed to be extensible following the principles outlined in the [`07-spec.md`](./07-spec.md).

## 1. Adding a Method to an Existing Accessor

Let's say you want to add a new method, for example, `compound_interest` to the `FinanceColumnAccessor`.

**Steps:**

1.  **Implement the Method (`finance.py`):**
    *   Open `gaspatchio_core/bindings/python/gaspatchio_core/dsl/accessors/finance.py`.
    *   Add the new method to the appropriate class (`FinanceColumnAccessor` for column/expression operations, `FinanceFrameAccessor` for frame operations).
    *   Use Polars expressions (`pl.Expr`) for the core logic.
    *   Ensure the method accepts necessary arguments (often including other columns or expressions via `IntoExprColumn`).
    *   Return a new `ExpressionProxy` (for column methods) or `ActuarialFrame` (for frame methods). Remember to import these locally within the method to avoid circular dependencies at runtime.
    *   Access the underlying Polars expression via `self._get_polars_expr()` (for column accessors) or the parent frame via `self._frame` (for frame accessors). Use helper methods like `_get_parent_frame()` or `_frame._convert_to_expr()` as needed.

    ```python
    # In gaspatchio_core/dsl/accessors/finance.py
    from gaspatchio_core.dsl.core import ExpressionProxy, IntoExprColumn # Local import needed

    class FinanceColumnAccessor(BaseColumnAccessor):
        # ... existing methods ...

        def compound_interest(
            self, rate_expr: "IntoExprColumn", n_periods_expr: "IntoExprColumn"
        ) -> "ExpressionProxy":
            """Applies compound interest to the value in the current column/expression.

            Formula: Compounded Value = Value * (1 + rate)^n_periods

            Args:
                rate_expr: The interest rate per period.
                n_periods_expr: The number of periods to compound over.

            Returns:
                An ExpressionProxy representing the compounded value.
            """
            # Use helper to get parent frame context if needed for conversions
            parent_frame = self._get_parent_frame()
            base_expr = self._get_polars_expr()

            # Convert inputs to Polars expressions
            pl_rate_expr = parent_frame._convert_to_expr(rate_expr)
            pl_n_periods_expr = parent_frame._convert_to_expr(n_periods_expr)

            # Calculate compound factor
            compound_factor = (1 + pl_rate_expr).pow(pl_n_periods_expr)

            # Apply compounding
            compounded_expr = base_expr * compound_factor

            # Wrap and return
            return ExpressionProxy(compounded_expr, parent_frame)

    ```

2.  **Update Stubs (`core.pyi`):**
    *   Open `gaspatchio_core/bindings/python/gaspatchio_core/dsl/core.pyi`.
    *   Add the method signature to the corresponding accessor class declaration.

    ```python
    # In gaspatchio_core/dsl/core.pyi
    class FinanceColumnAccessor:
        # ... existing methods ...
        def compound_interest(
            self, rate_expr: "IntoExprColumn", n_periods_expr: "IntoExprColumn"
        ) -> "ExpressionProxy": ...
    ```

3.  **Add Tests (`test_finance_*.py`):**
    *   Open the relevant test file (e.g., `tests/dsl/accessors/test_finance_column.py`).
    *   Add new test functions for the method, covering various scenarios (scalars, columns, expressions as input, edge cases like zero periods, negative rates, nulls).
    *   Use `polars.testing.assert_frame_equal` for robust comparisons.

## 2. Adding a New Accessor Namespace

Let's create a new `.mortality` accessor namespace.

**Steps:**

1.  **Create Accessor File (`mortality.py`):**
    *   Create `gaspatchio_core/bindings/python/gaspatchio_core/dsl/accessors/mortality.py`.
    *   Define `MortalityFrameAccessor(BaseFrameAccessor)` and `MortalityColumnAccessor(BaseColumnAccessor)`.
    *   Implement `__init__` for both, calling `super()`.
    *   Add placeholder methods (e.g., `apply_survival_curve` to `MortalityColumnAccessor`, `validate_life_table` to `MortalityFrameAccessor`). Implement their basic structure using Polars expressions and returning `ExpressionProxy` or `ActuarialFrame`.

    ```python
    # gaspatchio_core/dsl/accessors/mortality.py
    from typing import TYPE_CHECKING
    import polars as pl
    from .base import BaseColumnAccessor, BaseFrameAccessor

    if TYPE_CHECKING:
        from gaspatchio_core.dsl.core import (
            ActuarialFrame, ColumnProxy, ExpressionProxy, IntoExprColumn
        )

    class MortalityFrameAccessor(BaseFrameAccessor):
        def __init__(self, frame: "ActuarialFrame"):
            super().__init__(frame)
        # Add frame methods like validate_life_table(self, ...) -> bool: ...

    class MortalityColumnAccessor(BaseColumnAccessor):
        def __init__(self, proxy: "ColumnProxy | ExpressionProxy"):
            super().__init__(proxy)
            self._proxy: "ColumnProxy | ExpressionProxy" = proxy

        def _get_polars_expr(self) -> pl.Expr: # Helper
            from gaspatchio_core.dsl.core import ColumnProxy, ExpressionProxy
            if isinstance(self._proxy, ExpressionProxy): return self._proxy._expr
            if isinstance(self._proxy, ColumnProxy): return pl.col(self._proxy.name)
            raise TypeError("Invalid proxy type")

        def _get_parent_frame(self) -> "ActuarialFrame": # Helper
             if not hasattr(self._proxy, "_parent") or self._proxy._parent is None:
                 raise RuntimeError("Operation requires ActuarialFrame context.")
             return self._proxy._parent

        def apply_survival_curve(self, curve_expr: "IntoExprColumn") -> "ExpressionProxy":
            from gaspatchio_core.dsl.core import ExpressionProxy # Local import
            parent_frame = self._get_parent_frame()
            base_expr = self._get_polars_expr()
            pl_curve_expr = parent_frame._convert_to_expr(curve_expr)
            # Example: result = base_expr * pl_curve_expr # Placeholder logic
            result_expr = base_expr * pl_curve_expr # Replace with actual logic
            return ExpressionProxy(result_expr, parent_frame)
        # Add other column methods
    ```

2.  **Update Accessor `__init__.py`:**
    *   Open `gaspatchio_core/bindings/python/gaspatchio_core/dsl/accessors/__init__.py`.
    *   Import and add `MortalityFrameAccessor` and `MortalityColumnAccessor` to `__all__`.

3.  **Integrate into Core DSL (`core.py`):**
    *   Open `gaspatchio_core/bindings/python/gaspatchio_core/dsl/core.py`.
    *   Import the new accessors within `if TYPE_CHECKING:`.
    *   Add `@property` methods named `mortality` to `ActuarialFrame`, `ColumnProxy`, and `ExpressionProxy` that return instances of the corresponding new accessor classes.

    ```python
    # In gaspatchio_core/dsl/core.py
    if TYPE_CHECKING:
        # ... other imports ...
        from .accessors.mortality import MortalityColumnAccessor, MortalityFrameAccessor

    class ActuarialFrame:
        # ... existing properties ...
        @property
        def mortality(self) -> "MortalityFrameAccessor":
            from .accessors.mortality import MortalityFrameAccessor # Local import
            return MortalityFrameAccessor(self)

    class ColumnProxy:
        # ... existing properties ...
        @property
        def mortality(self) -> "MortalityColumnAccessor":
            from .accessors.mortality import MortalityColumnAccessor # Local import
            return MortalityColumnAccessor(self)

    class ExpressionProxy:
        # ... existing properties ...
        @property
        def mortality(self) -> "MortalityColumnAccessor":
            from .accessors.mortality import MortalityColumnAccessor # Local import
            return MortalityColumnAccessor(self)
    ```

4.  **Update Delegation (`_delegation.py`):**
    *   Open `gaspatchio_core/bindings/python/gaspatchio_core/dsl/_delegation.py`.
    *   Add `"mortality"` to the `_RESERVED_ACCESSOR_NAMES` set to prevent `_autopatch` from interfering.

5.  **Update Stubs (`core.pyi`):**
    *   Open `gaspatchio_core/bindings/python/gaspatchio_core/dsl/core.pyi`.
    *   Import the new accessors `from ..accessors.mortality import ...`.
    *   Add the `.mortality` property type hints to `ActuarialFrame`, `ColumnProxy`, and `ExpressionProxy`.
    *   Add the class declarations for `MortalityFrameAccessor` and `MortalityColumnAccessor` with their method signatures.

    ```python
     # In gaspatchio_core/dsl/core.pyi
     from ..accessors.mortality import MortalityColumnAccessor, MortalityFrameAccessor

     class ActuarialFrame:
         # ...
         @property
         def mortality(self) -> "MortalityFrameAccessor": ...

     class ColumnProxy(ExpressionProxy):
         # ...
         @property
         def mortality(self) -> "MortalityColumnAccessor": ...

     class ExpressionProxy(BaseProxy):
         # ...
         @property
         def mortality(self) -> "MortalityColumnAccessor": ...

     # --- Mortality Accessors ---
     class MortalityFrameAccessor:
         _parent: "ActuarialFrame"
         def __init__(self, parent: "ActuarialFrame") -> None: ...
         # Add method signatures:
         # def validate_life_table(self, ...) -> bool: ...

     class MortalityColumnAccessor:
         _expr: pl.Expr
         _parent: "_ActuarialFrame | None"
         def __init__(self, expr: pl.Expr, parent: "_ActuarialFrame | None" = ...) -> None: ...
         # Add method signatures:
         def apply_survival_curve(self, curve_expr: "IntoExprColumn") -> "ExpressionProxy": ...

    ```

6.  **Add Tests (`test_mortality_*.py`, `test_integration.py`):**
    *   Create `tests/dsl/accessors/test_mortality_frame.py` and `tests/dsl/accessors/test_mortality_column.py`.
    *   Write tests for the new mortality methods.
    *   Update `tests/dsl/test_integration.py` to verify `af.mortality` and `af['col'].mortality` work correctly and appear in `dir()`.

By following these patterns, you can systematically extend the `ActuarialFrame` DSL with new domain-specific functionalities while maintaining consistency, discoverability, and testability. Remember to consult [`07-spec.md`](./07-spec.md) for the detailed design rationale.
