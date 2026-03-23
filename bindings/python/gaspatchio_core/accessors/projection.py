# ABOUTME: Projection accessor for actuarial projection operations.
# ABOUTME: Methods: cumulative survival, period overrides, time-shifting.
# ruff: noqa: PLC0415

"""Projection accessor for actuarial operations on time-series."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import polars as pl

from gaspatchio_core.accessors.base import BaseColumnAccessor
from gaspatchio_core.frame.registry import register_accessor

if TYPE_CHECKING:
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.frame.base import ActuarialFrame


@register_accessor("projection", kind="column")
class ProjectionColumnAccessor(BaseColumnAccessor):
    """Actuarial projection operations for time-series calculations.

    This accessor provides methods for transforming rates and probabilities
    into cumulative values over projection periods. Complex operations like
    cumulative products use these methods, while simple operations like
    multiplication should use standard operators.

    Design Philosophy:
        - Complex cumulative operations: Use projection methods
        - Simple arithmetic: Use operators (`*`, `+`, `-`, `/`)
        - Terminal/aggregate values: Use Polars (`.list.last()`)

    Accessed via `.projection` on a column or expression, e.g.,
    `af["mortality_rate"].projection.cumulative_survival()`.

    Examples:
        Cumulative survival from mortality rates:

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"qx": [[0.001, 0.0011, 0.0012], [0.002, 0.0022, 0.0024]]}
        af = ActuarialFrame(data)

        # Complex cumulative product - use projection method
        af.survival_to_t = af.qx.projection.cumulative_survival()

        # Simple multiplication - use operators
        af.death_benefit = af.face_amount * af.survival_to_t * af.qx
        af.premium = af.annual_premium * af.survival_to_t

        # Terminal value - use Polars
        af.maturity_benefit = af.face_amount.list.last()
        ```

        Premium holiday modeling:

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"premium": [[1000, 1000, 1000, 1000, 1000]]}
        af = ActuarialFrame(data)

        # Period override - use projection method
        af.premium_with_holiday = af.premium.projection.with_period(3, value=0)
        # Result: [1000, 1000, 1000, 0, 1000]
        ```

    """

    def __init__(self, proxy: ColumnProxy | ExpressionProxy) -> None:
        """Initialize the projection accessor.

        This is typically called internally when accessing `.projection`.

        Args:
            proxy: The ColumnProxy or ExpressionProxy instance.

        """
        super().__init__(proxy)
        self._proxy: ColumnProxy | ExpressionProxy = proxy

    def _get_polars_expr(self) -> pl.Expr:
        """Get the underlying Polars expression from the proxy.

        Helper method to extract the raw Polars expression from either a ColumnProxy
        or ExpressionProxy for use in projection calculations.

        Returns
        -------
        pl.Expr
            The underlying Polars expression

        """
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        if isinstance(self._proxy, ExpressionProxy):
            return self._proxy._expr  # noqa: SLF001
        if isinstance(self._proxy, ColumnProxy):
            return pl.col(self._proxy.name)
        msg = (
            f"ProjectionColumnAccessor expected ColumnProxy or "
            f"ExpressionProxy, got {type(self._proxy).__name__}"
        )
        raise TypeError(msg)

    def _get_parent_frame(self) -> ActuarialFrame:
        """Get the parent ActuarialFrame from the proxy.

        Helper method to retrieve the parent ActuarialFrame context needed for
        projection operations that require access to other columns or metadata.

        Returns
        -------
        ActuarialFrame
            The parent ActuarialFrame instance

        Raises
        ------
        RuntimeError
            If the proxy is not associated with an ActuarialFrame context

        """
        parent_af = getattr(self._proxy, "_parent", None)
        if parent_af is None:
            msg = (
                "Projection operations require the column to be part of an "
                "ActuarialFrame context"
            )
            raise RuntimeError(msg)
        return parent_af

    def cumulative_survival(
        self,
        rate_timing: Literal["beginning_of_period", "end_of_period"] | None = None,
        start_at: float | None = 1.0,
    ) -> ExpressionProxy:
        """Convert mortality rates to cumulative survival probabilities.

        Transforms period mortality rates (qx) into cumulative survival probabilities
        using the formula `tpx[t] = (1-qx[0]) * (1-qx[1]) * ... * (1-qx[t])`. Essential
        for life insurance projections, reserve calculations, and any actuarial work
        requiring survival probabilities from mortality assumptions.

        For list columns, applies element-wise cumulative product within each list.
        For scalar columns, applies cumulative product across rows (use `.over()` for
        grouping by policy).

        !!! note "When to use"
            * **Life Insurance Projections:** Calculate the probability policies remain
                inforce for death benefit, premium, and cash value projections.
            * **Reserve Calculations:** Compute expected policy counts for reserve
                valuations and capital requirements.
            * **Persistency Analysis:** Model combined mortality and lapse decrements
                to project policy persistency over time.
            * **Pricing Models:** Calculate expected present values of benefits and
                premiums weighted by survival probabilities.

        Timing Conventions
        ------------------
        The `rate_timing` parameter controls when decrement rates are applied:

        * **beginning_of_period** (default): Rate at period t is NOT yet applied to
          P[IF][t]. The survival at t represents the probability of surviving TO the
          start of period t. Result: ``[1.0, tpx[0], tpx[0]*tpx[1], ...]``

        * **end_of_period**: Rate at period t HAS been applied to P[IF][t]. The
          survival at t represents the probability of surviving THROUGH period t.
          This matches Excel-style timing. Result: ``[tpx[0], tpx[0]*tpx[1], ...]``

        With constant rates, both conventions give identical values. The difference
        only appears when rates change over time (e.g., at age boundaries).

        Parameters
        ----------
        rate_timing : {"beginning_of_period", "end_of_period"}, optional
            When decrement rates are applied. Recommended for most users:

            - ``"beginning_of_period"``: Rate at t NOT yet applied (default behavior)
            - ``"end_of_period"``: Rate at t HAS been applied (Excel-style)

            If not specified, falls back to `start_at` parameter behavior.
        start_at : float, optional
            Lower-level control over timing. Only use if `rate_timing` is not set.
            Initial survival probability to prepend at t=0:

            - 1.0 (default): Beginning-of-period [1.0, tpx[0], tpx[1], ...]
            - None: End-of-period [tpx[0], tpx[1], ...]
            - Other: Custom initial value (e.g., 0.95 for partial cohort)

        Returns
        -------
        ExpressionProxy
            Cumulative survival probabilities for each period

        Raises
        ------
        ValueError
            If both `rate_timing` and a non-default `start_at` are specified,
            or if `rate_timing` has an invalid value
        RuntimeError
            If the column is not part of an ActuarialFrame context

        Examples
        --------
        **Beginning-of-Period Timing (Default)**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "qx": [[0.001, 0.002, 0.003], [0.002, 0.003, 0.004]],
        }
        af = ActuarialFrame(data)

        # Default: rate at t not yet applied
        af.pols_if = af.qx.projection.cumulative_survival()
        # Or explicitly:
        af.pols_if = af.qx.projection.cumulative_survival(
            rate_timing="beginning_of_period"
        )

        print(af.collect())
        ```

        ```text
        shape: (2, 3)
        ┌───────────┬───────────────────────┬────────────────────────┐
        │ policy_id ┆ qx                    ┆ pols_if                │
        │ ---       ┆ ---                   ┆ ---                    │
        │ str       ┆ list[f64]             ┆ list[f64]              │
        ╞═══════════╪═══════════════════════╪════════════════════════╡
        │ P001      ┆ [0.001, 0.002, 0.003] ┆ [1.0, 0.999, 0.997002] │
        │ P002      ┆ [0.002, 0.003, 0.004] ┆ [1.0, 0.998, 0.995006] │
        └───────────┴───────────────────────┴────────────────────────┘
        ```

        **End-of-Period Timing (Excel-Style)**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "qx": [[0.001, 0.002, 0.003]],
        }
        af = ActuarialFrame(data)

        # Excel-style: rate at t has been applied
        af.tpx = af.qx.projection.cumulative_survival(rate_timing="end_of_period")

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌───────────────────────┬─────────────────────────────┐
        │ qx                    ┆ tpx                         │
        │ ---                   ┆ ---                         │
        │ list[f64]             ┆ list[f64]                   │
        ╞═══════════════════════╪═════════════════════════════╡
        │ [0.001, 0.002, 0.003] ┆ [0.999, 0.997002, 0.994011] │
        └───────────────────────┴─────────────────────────────┘
        ```

        **Custom Initial Value (Partial Cohort)**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "qx": [[0.001, 0.002, 0.003]],
        }
        af = ActuarialFrame(data)

        # 95% survived underwriting - use start_at for custom values
        af.pols_if = af.qx.projection.cumulative_survival(start_at=0.95)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌───────────────────────┬─────────────────────────┐
        │ qx                    ┆ pols_if                 │
        │ ---                   ┆ ---                     │
        │ list[f64]             ┆ list[f64]               │
        ╞═══════════════════════╪═════════════════════════╡
        │ [0.001, 0.002, 0.003] ┆ [0.95, 0.999, 0.997002] │
        └───────────────────────┴─────────────────────────┘
        ```

        """
        # Handle rate_timing parameter - maps to start_at for backwards compatibility
        if rate_timing is not None:
            # Validate rate_timing value
            valid_timings = ("beginning_of_period", "end_of_period")
            if rate_timing not in valid_timings:
                msg = (
                    f"Invalid rate_timing value: {rate_timing!r}. "
                    f"Must be one of {valid_timings}"
                )
                raise ValueError(msg)

            # Check for conflicting parameters
            if start_at != 1.0:
                msg = (
                    "Cannot specify both 'rate_timing' and 'start_at'. "
                    "Use 'rate_timing' for standard timing conventions, "
                    "or 'start_at' for custom initial values."
                )
                raise ValueError(msg)

            # Map rate_timing to start_at
            start_at = 1.0 if rate_timing == "beginning_of_period" else None
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.dispatch import (
            ColumnTypeDetector,  # type: ignore[attr-defined]
        )
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Get base expression and parent frame
        base_expr = self._get_polars_expr()
        parent_af = self._get_parent_frame()

        # Determine if this is a list column
        detector = ColumnTypeDetector(parent_af)
        is_list = False

        if isinstance(self._proxy, ColumnProxy):
            is_list = detector.is_list_column(self._proxy.name)

        # Apply appropriate calculation based on column type
        if is_list:
            # For list columns, apply element-wise cumulative product within each list.
            # This computes survival[t] = px[0] * px[1] * ... * px[t]
            # where px[i] = 1 - qx[i].
            survival_expr = base_expr.list.eval((1 - pl.element()).cum_prod())

            # Apply start_at shift if requested (for list columns)
            if start_at is not None:
                # Prepend start_at value and drop last element to maintain length
                # This gives beginning-of-period values: [start_at, tpx[0], tpx[1], ...]
                list_len = survival_expr.list.len()
                survival_expr = pl.concat_list(
                    [pl.lit([start_at]), survival_expr]
                ).list.slice(0, list_len)
        else:
            # For scalar columns, apply cumulative product across rows.
            # User should add .over() for grouping if needed.
            survival_expr = (1 - base_expr).cum_prod()

            # Apply start_at shift if requested (for scalar columns)
            if start_at is not None:
                survival_expr = survival_expr.shift(1, fill_value=start_at)

        return ExpressionProxy(survival_expr, parent_af)

    def with_period(self, period: int, value: float | str) -> ExpressionProxy:
        """Override value at a specific period (zero-indexed).

        Creates a modified version of a list column with a specific element set to
        a new value. Essential for modeling planned policy changes, premium holidays,
        benefit adjustments, and other known discontinuities in actuarial projections.

        This method only works with list columns. For scalar columns, use conditional
        logic with `.when()` and `.then()`.

        !!! note "When to use"
            * **Premium Holidays:** Model scheduled breaks in premium payments, such
                as waiver of premium periods or contractual payment holidays.
            * **Benefit Changes:** Implement known benefit adjustments at specific
                durations, like step-up death benefits or maturity bonuses.
            * **Policy Events:** Model surrender charge schedules, conversion options,
                or guaranteed insurability riders that activate at specific times.
            * **Assumption Overrides:** Apply one-time adjustments to mortality rates,
                lapse rates, or expenses for specific policy anniversaries.

        Parameters
        ----------
        period : int
            Zero-based index to modify. Negative indices supported (-1 = last period).
        value : float or str
            Value to set at that period

        Returns
        -------
            Modified list with value changed at specified period

        Raises
        ------
            RuntimeError: If proxy not associated with an ActuarialFrame
            ValueError: If period is out of bounds for the list

        Examples
        --------
        **Vector Example: Premium Holiday**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"premium": [[1000, 1000, 1000]]}
        af = ActuarialFrame(data)

        af.premium_adj = af.premium.projection.with_period(1, value=0)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌────────────────────┬─────────────────┐
        │ premium            ┆ premium_adj     │
        │ ---                ┆ ---             │
        │ list[i64]          ┆ list[i64]       │
        ╞════════════════════╪═════════════════╡
        │ [1000, 1000, 1000] ┆ [1000, 0, 1000] │
        └────────────────────┴─────────────────┘
        ```

        **Vector Example: Negative Index (Last Period)**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"benefit": [[1000, 1000, 1000]]}
        af = ActuarialFrame(data)

        af.benefit_adj = af.benefit.projection.with_period(-1, value=5000)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌────────────────────┬────────────────────┐
        │ benefit            ┆ benefit_adj        │
        │ ---                ┆ ---                │
        │ list[i64]          ┆ list[i64]          │
        ╞════════════════════╪════════════════════╡
        │ [1000, 1000, 1000] ┆ [1000, 1000, 5000] │
        └────────────────────┴────────────────────┘
        ```

        **Vector Example: Benefit Increase**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"face_amount": [[100000, 100000, 100000]]}
        af = ActuarialFrame(data)

        af.face_adj = af.face_amount.projection.with_period(1, value=150000)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌──────────────────────────┬──────────────────────────┐
        │ face_amount              ┆ face_adj                 │
        │ ---                      ┆ ---                      │
        │ list[i64]                ┆ list[i64]                │
        ╞══════════════════════════╪══════════════════════════╡
        │ [100000, 100000, 100000] ┆ [100000, 150000, 100000] │
        └──────────────────────────┴──────────────────────────┘
        ```

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        parent_af = self._get_parent_frame()

        # Slice the list to extract parts before and after the target period
        # Polars list.slice doesn't handle negative lengths like Python,
        # so we need to compute the actual length for negative indices
        if period < 0:
            # For negative indices, compute length from list size
            # period = -1 means last element, so before has length = len - 1
            # period = -2 means second-to-last, so before has length = len - 2
            list_len = base_expr.list.len()
            before_length = (
                list_len + period
            )  # period is negative, so this is len - abs(period)
            before_slice = base_expr.list.slice(0, before_length)

            # After slice: from position (len + period + 1) to end
            if period == -1:
                # Last element: no elements after
                after_slice = base_expr.list.slice(0, 0)  # Empty slice
            else:
                # Other negative: take from (period + 1) onwards
                after_start = list_len + period + 1
                after_slice = base_expr.list.slice(after_start, None)
        else:
            # Positive indices work as expected
            before_slice = base_expr.list.slice(0, period)
            after_slice = base_expr.list.slice(period + 1, None)

        # Create a list with single replacement value
        # We need to ensure it's wrapped as a list column
        replacement = pl.lit([[value]])

        # Concatenate slices with new value in the middle
        # concat_list concatenates list elements, so we need to extract the inner list
        modified_expr = pl.concat_list(
            [before_slice, replacement.list.first(), after_slice]
        )

        return ExpressionProxy(modified_expr, parent_af)

    def with_periods(self, updates: dict[int, int | float | str]) -> ExpressionProxy:
        """Override values at multiple specific periods.

        Creates a modified version of a list column with multiple elements changed
        at once. More efficient and readable than chaining multiple `with_period()`
        calls. Essential for modeling complex benefit schedules, premium patterns,
        and assumption variations across policy durations.

        !!! note "When to use"
            * **Benefit Schedules:** Model policies with multiple benefit changes,
                such as increasing term insurance or scheduled death benefit steps.
            * **Premium Patterns:** Implement complex premium schedules with multiple
                holidays, increases, or decreases at known policy anniversaries.
            * **Surrender Charges:** Define surrender charge schedules that decrease
                over time or change at specific durations.
            * **Assumption Testing:** Apply multiple one-time adjustments to test
                sensitivity to assumption changes at different policy durations.

        Parameters
        ----------
        updates : dict[int, int | float | str]
            Dictionary mapping period indices (zero-based) to new values.
            Negative indices are supported (-1 = last period).

        Returns
        -------
            Modified list with values changed at specified periods

        Raises
        ------
            RuntimeError: If proxy not associated with an ActuarialFrame
            ValueError: If any period is out of bounds for the list

        Examples
        --------
        **Vector Example: Multiple Premium Holidays**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"premium": [[500, 500, 500]]}
        af = ActuarialFrame(data)

        af.premium_adj = af.premium.projection.with_periods({0: 0, 2: 0})

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌─────────────────┬─────────────┐
        │ premium         ┆ premium_adj │
        │ ---             ┆ ---         │
        │ list[i64]       ┆ list[i64]   │
        ╞═════════════════╪═════════════╡
        │ [500, 500, 500] ┆ [0, 500, 0] │
        └─────────────────┴─────────────┘
        ```

        **Vector Example: Benefit Schedule**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"benefit": [[1000, 1000, 1000]]}
        af = ActuarialFrame(data)

        af.benefit_adj = af.benefit.projection.with_periods({0: 1500, -1: 5000})

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌────────────────────┬────────────────────┐
        │ benefit            ┆ benefit_adj        │
        │ ---                ┆ ---                │
        │ list[i64]          ┆ list[i64]          │
        ╞════════════════════╪════════════════════╡
        │ [1000, 1000, 1000] ┆ [1500, 1000, 5000] │
        └────────────────────┴────────────────────┘
        ```

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Start with the base expression and parent frame
        result_expr = self._get_polars_expr()
        parent_af = self._get_parent_frame()

        # Sort updates by period index to apply them in order
        # This ensures negative indices work correctly
        sorted_updates = sorted(updates.items(), key=lambda x: x[0])

        # Apply each update sequentially by chaining with_period calls
        temp_proxy = ExpressionProxy(result_expr, parent_af)
        temp_accessor = ProjectionColumnAccessor(temp_proxy)

        for period, value in sorted_updates:
            temp_proxy = temp_accessor.with_period(period, value)
            # Update accessor for next iteration
            temp_accessor = ProjectionColumnAccessor(temp_proxy)

        return temp_proxy

    def previous_period(self, fill_value=0.0) -> ExpressionProxy:
        """Get value from previous period (t-1).

        Equivalent to shifting back one period. Most common case for
        actuarial projections when referencing prior period values.

        For list columns, shifts values within each list. For scalar columns,
        shifts across rows (use `.over()` for grouping).

        !!! note "When to use"
            * **Inforce Rollforward:** Calculate beginning-of-period inforce values
                using ending inforce from the previous period in life insurance models.
            * **Reserve Calculations:** Access prior period reserves for reserve
                rollforward formulas and cash flow testing.
            * **Period Comparisons:** Compare current period values against previous
                period for variance analysis and experience studies.
            * **Dependent Calculations:** Reference lagged values in formulas where
                current period depends on prior period results.

        Parameters
        ----------
        fill_value : scalar, optional
            Value to use for first period where no previous value exists.
            Default is 0.

        Returns
        -------
        ExpressionProxy
            Expression with values shifted from previous period

        Examples
        --------
        **Basic Usage: Previous Period Values**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"pols_death": [[10, 15, 20]]}
        af = ActuarialFrame(data)

        af.pols_death_prev = af.pols_death.projection.previous_period()

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌──────────────┬──────────────────┐
        │ pols_death   ┆ pols_death_prev  │
        │ ---          ┆ ---              │
        │ list[i64]    ┆ list[i64]        │
        ╞══════════════╪══════════════════╡
        │ [10, 15, 20] ┆ [0, 10, 15]      │
        └──────────────┴──────────────────┘
        ```

        **Custom Fill Value: Reserve Calculations**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"reserve": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        # Use None to get null for missing values
        af.reserve_prev = af.reserve.projection.previous_period(fill_value=None)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌──────────────────┬──────────────────┐
        │ reserve          ┆ reserve_prev     │
        │ ---              ┆ ---              │
        │ list[i64]        ┆ list[i64]        │
        ╞══════════════════╪══════════════════╡
        │ [1000, 1100, ...] ┆ [null, 1000, ...] │
        └──────────────────┴──────────────────┘
        ```

        **Actuarial Formula: Inforce Rollforward**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "pols_if_after_death": [[1000, 990, 975]],
            "pols_lapse": [[5, 8, 10]],
        }
        af = ActuarialFrame(data)

        # Calculate beginning-of-period inforce using previous period values
        # pols_if_bop(t) = pols_if_after_death(t-1) - pols_lapse(t-1)
        af.pols_if_prev = af.pols_if_after_death.projection.previous_period(
            fill_value=1000
        )
        af.pols_lapse_prev = af.pols_lapse.projection.previous_period()
        af.pols_if_bop = af.pols_if_prev - af.pols_lapse_prev

        print(af.collect())
        ```

        ```text
        shape: (1, 4)
        ┌─────────────────────┬─────────────┬────────────────┬─────────────┐
        │ pols_if_after_death ┆ pols_lapse  ┆ pols_if_prev   ┆ pols_if_bop │
        │ ---                 ┆ ---         ┆ ---            ┆ ---         │
        │ list[i64]           ┆ list[i64]   ┆ list[i64]      ┆ list[i64]   │
        ╞═════════════════════╪═════════════╪════════════════╪═════════════╡
        │ [1000, 990, 975]    ┆ [5, 8, 10]  ┆ [1000, 1000... ┆ [1000, 995..│
        └─────────────────────┴─────────────┴────────────────┴─────────────┘
        ```

        See Also
        --------
        next_period : Get value from next period (t+1)
        at_period : Get value at arbitrary period offset

        """
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.dispatch import (
            ColumnTypeDetector,  # type: ignore[attr-defined]
        )
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        parent_af = self._get_parent_frame()

        # Determine if this is a list column/expression
        detector = ColumnTypeDetector(parent_af)
        is_list = False

        if isinstance(self._proxy, ColumnProxy):
            # For ColumnProxy, check by column name
            is_list = detector.is_list_column(self._proxy.name)
        elif isinstance(self._proxy, ExpressionProxy):
            # For ExpressionProxy, infer output type from the expression
            is_list = detector.is_expression_list_output(base_expr)

        if is_list:
            # For list columns: use list.eval with shift to operate element-wise
            # This applies shift(1, fill_value) to each element within the list
            # More efficient and compatible than concat_list approach
            shifted_expr = base_expr.list.eval(
                pl.element().shift(1, fill_value=fill_value)
            )
        else:
            # For scalar columns: use shift(1) to get previous period value
            shifted_expr = base_expr.shift(1, fill_value=fill_value)

        result = ExpressionProxy(shifted_expr, parent_af)

        # Tag as element-wise to prevent incorrect list broadcasting
        result._list_broadcast_metadata = {"element_wise": True}  # noqa: SLF001

        return result

    def next_period(self, fill_value=0.0) -> ExpressionProxy:
        """Get value from next period (t+1).

        Equivalent to shifting forward one period. Less common than
        `previous_period()` but useful for certain actuarial calculations
        requiring forward-looking values.

        For list columns, shifts values within each list. For scalar columns,
        shifts across rows (use `.over()` for grouping).

        !!! note "When to use"
            * **Forward-Looking Calculations:** Access next period values for
                calculations that require looking ahead in the projection timeline.
            * **Period-Over-Period Growth:** Calculate growth rates or changes by
                comparing current values to next period values.
            * **Validation Checks:** Verify that projected values follow expected
                patterns by comparing current and next period results.
            * **Timing Adjustments:** Reference future period values when modeling
                payment or benefit timing that leads the valuation period.

        Parameters
        ----------
        fill_value : scalar, optional
            Value to use for last period where no next value exists.
            Default is 0.

        Returns
        -------
        ExpressionProxy
            Expression with values shifted from next period

        Examples
        --------
        **Basic Usage: Next Period Values**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"interest_rate": [[0.05, 0.06, 0.07]]}
        af = ActuarialFrame(data)

        af.rate_next = af.interest_rate.projection.next_period()

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌────────────────────┬───────────────────┐
        │ interest_rate      ┆ rate_next         │
        │ ---                ┆ ---               │
        │ list[f64]          ┆ list[f64]         │
        ╞════════════════════╪═══════════════════╡
        │ [0.05, 0.06, 0.07] ┆ [0.06, 0.07, 0.0] │
        └────────────────────┴───────────────────┘
        ```

        **Forward-Looking Calculation Example**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"cashflow": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        # Compare current period to next period
        af.cf_next = af.cashflow.projection.next_period()
        af.cf_growth = af.cf_next - af.cashflow

        print(af.collect())
        ```

        ```text
        shape: (1, 3)
        ┌──────────────────┬─────────────────┬──────────────────┐
        │ cashflow         ┆ cf_next         ┆ cf_growth        │
        │ ---              ┆ ---             ┆ ---              │
        │ list[i64]        ┆ list[i64]       ┆ list[i64]        │
        ╞══════════════════╪═════════════════╪══════════════════╡
        │ [1000, 1100, ...] ┆ [1100, 1200, 0] ┆ [100, 100, -...] │
        └──────────────────┴─────────────────┴──────────────────┘
        ```

        See Also
        --------
        previous_period : Get value from previous period (t-1)
        at_period : Get value at arbitrary period offset

        """
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.dispatch import (
            ColumnTypeDetector,  # type: ignore[attr-defined]
        )
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        parent_af = self._get_parent_frame()

        # Determine if this is a list column/expression
        detector = ColumnTypeDetector(parent_af)
        is_list = False

        if isinstance(self._proxy, ColumnProxy):
            # For ColumnProxy, check by column name
            is_list = detector.is_list_column(self._proxy.name)
        elif isinstance(self._proxy, ExpressionProxy):
            # For ExpressionProxy, infer output type from the expression
            is_list = detector.is_expression_list_output(base_expr)

        if is_list:
            # For list columns: use list.eval with shift to operate element-wise
            # This applies shift(-1, fill_value) to each element within the list
            # More efficient and compatible than concat_list approach
            shifted_expr = base_expr.list.eval(
                pl.element().shift(-1, fill_value=fill_value)
            )
        else:
            # For scalar columns: use shift(-1) to get next period value
            shifted_expr = base_expr.shift(-1, fill_value=fill_value)

        result = ExpressionProxy(shifted_expr, parent_af)

        # Tag as element-wise to prevent incorrect list broadcasting
        result._list_broadcast_metadata = {"element_wise": True}  # noqa: SLF001

        return result

    def at_period(
        self, relative_period: int, fill_value: float | None = 0.0
    ) -> ExpressionProxy:
        """Get value at relative period offset.

        Access values from other time periods using mathematical t notation.
        Negative values reference prior periods (t-1, t-2), positive values
        reference future periods (t+1, t+2).

        This method provides flexible time-shifting for arbitrary period offsets,
        complementing the convenience methods `previous_period()` (t-1) and
        `next_period()` (t+1).

        For list columns, shifts values within each list. For scalar columns,
        shifts across rows (use `.over()` for grouping).

        !!! note "When to use"
            * **Multi-Period Lag Analysis:** Access values from multiple periods back
                (t-2, t-3) for trend analysis and smoothing calculations.
            * **Reserve Rollforward:** Reference reserves from specific prior periods
                in complex reserve formulas requiring multiple lag periods.
            * **Experience Studies:** Compare values across multiple time periods to
                analyze experience trends and validate assumptions.
            * **Flexible Time-Shifting:** Use when previous_period() and next_period()
                don't provide the specific offset needed for your calculation.

        Parameters
        ----------
        relative_period : int
            Period offset from current time using mathematical notation:
            - Negative values: prior periods (e.g., -1 for t-1, -2 for t-2)
            - Positive values: future periods (e.g., 1 for t+1, 2 for t+2)
            - Zero: current period (no shift)
        fill_value : scalar, optional
            Value to use for missing entries at boundaries. Default is 0.

        Returns
        -------
        ExpressionProxy
            Expression with values from specified relative period

        Examples
        --------
        **Previous Period: t-1**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"reserve": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        # at_period(-1) is equivalent to previous_period()
        af.reserve_t1 = af.reserve.projection.at_period(-1)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌──────────────────┬──────────────────┐
        │ reserve          ┆ reserve_t1       │
        │ ---              ┆ ---              │
        │ list[i64]        ┆ list[i64]        │
        ╞══════════════════╪══════════════════╡
        │ [1000, 1100, ...] ┆ [0, 1000, 1100]  │
        └──────────────────┴──────────────────┘
        ```

        **Two Periods Back: t-2**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"value": [[100, 110, 120, 130, 140]]}
        af = ActuarialFrame(data)

        af.value_t2 = af.value.projection.at_period(-2)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌───────────────────────┬──────────────────────┐
        │ value                 ┆ value_t2             │
        │ ---                   ┆ ---                  │
        │ list[i64]             ┆ list[i64]            │
        ╞═══════════════════════╪══════════════════════╡
        │ [100, 110, 120, 13... ┆ [0, 0, 100, 110, 120]│
        └───────────────────────┴──────────────────────┘
        ```

        **Next Period: t+1**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"cashflow": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        # at_period(1) is equivalent to next_period()
        af.cf_tp1 = af.cashflow.projection.at_period(1)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌──────────────────┬─────────────────┐
        │ cashflow         ┆ cf_tp1          │
        │ ---              ┆ ---             │
        │ list[i64]        ┆ list[i64]       │
        ╞══════════════════╪═════════════════╡
        │ [1000, 1100, ...] ┆ [1100, 1200, 0] │
        └──────────────────┴─────────────────┘
        ```

        **Reserve Rollforward Formula**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "reserve": [[0, 950, 1900, 2850]],
            "premium": [[1000, 1000, 1000, 1000]],
            "interest": [[50, 52, 55, 58]],
            "benefit": [[100, 102, 105, 108]],
        }
        af = ActuarialFrame(data)

        # Reserve rollforward formula:
        # Reserve(t) = Reserve(t-1) + Premium(t) + Interest(t) - Benefit(t)
        af.reserve_t1 = af.reserve.projection.at_period(-1)
        af.reserve_calc = af.reserve_t1 + af.premium + af.interest - af.benefit

        print(af.collect())
        ```

        ```text
        shape: (1, 6)
        ┌─────────────────┬─────────────┬─────────┬─────────┬──────────┬──────────────┐
        │ reserve         ┆ premium     ┆ intere.. ┆ benefit ┆ reserve..┆ reserve_calc │
        │ ---             ┆ ---         ┆ ---     ┆ ---     ┆ ---      ┆ ---          │
        │ list[i64]       ┆ list[i64]   ┆ list..  ┆ list..  ┆ list[i64]┆ list[i64]    │
        ╞═════════════════╪═════════════╪═════════╪═════════╪══════════╪══════════════╡
        │ [0, 950, 19...┆ [1000, 10...┆ [50, 52...┆ [100, ...┆ [0, 0, 9...┆ [950, 19...│
        └─────────────────┴─────────────┴─────────┴─────────┴──────────┴──────────────┘
        ```

        See Also
        --------
        previous_period : Convenience method for t-1
        next_period : Convenience method for t+1

        """
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.dispatch import (
            ColumnTypeDetector,  # type: ignore[attr-defined]
        )
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        parent_af = self._get_parent_frame()

        # Determine if this is a list column/expression
        detector = ColumnTypeDetector(parent_af)
        is_list = False

        if isinstance(self._proxy, ColumnProxy):
            # For ColumnProxy, check by column name
            is_list = detector.is_list_column(self._proxy.name)
        elif isinstance(self._proxy, ExpressionProxy):
            # For ExpressionProxy, infer output type from the expression
            is_list = detector.is_expression_list_output(base_expr)

        if is_list:
            # For list columns: use list.eval with shift to operate element-wise
            # This applies shift(-relative_period, fill_value) within the list
            # Note: Polars shift convention is opposite, so negate relative_period
            # at_period(-1) means t-1 (prior), which needs shift(1)
            # at_period(1) means t+1 (future), which needs shift(-1)
            if relative_period == 0:
                # Zero offset: no shift
                shifted_expr = base_expr
            else:
                shifted_expr = base_expr.list.eval(
                    pl.element().shift(-relative_period, fill_value=fill_value)
                )
        else:
            # For scalar columns: negate relative_period
            # (Polars uses opposite convention)
            # at_period(-1) means t-1 (prior), which needs shift(1)
            # at_period(1) means t+1 (future), which needs shift(-1)
            shifted_expr = base_expr.shift(-relative_period, fill_value=fill_value)

        result = ExpressionProxy(shifted_expr, parent_af)

        # Tag as element-wise to prevent incorrect list broadcasting
        result._list_broadcast_metadata = {"element_wise": True}  # noqa: SLF001

        return result

    def _build_discount_factors(
        self,
        cashflow_expr: pl.Expr,
        discount_rate: float | ExpressionProxy | ColumnProxy | None,
        discount_factor: ExpressionProxy | ColumnProxy | None,
    ) -> pl.Expr:
        """Build discount factor expression from rate or factor input.

        Helper method to construct the v^t discount factor expression from either
        a discount rate (scalar or list) or pre-computed discount factors.

        """
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        if discount_factor is not None:
            # Use provided discount factors directly
            if isinstance(discount_factor, ExpressionProxy):
                return discount_factor._expr  # noqa: SLF001
            if isinstance(discount_factor, ColumnProxy):
                return pl.col(discount_factor.name)
            msg = (
                "discount_factor must be ExpressionProxy or ColumnProxy, "
                f"got {type(discount_factor)}"
            )
            raise TypeError(msg)

        # Compute discount factors from rate: v(t) = 1 / (1 + r(t))
        if isinstance(discount_rate, (int, float)):
            # Scalar rate: v^t = v^t for each period t
            v = 1.0 / (1.0 + discount_rate)
            return cashflow_expr.list.eval(
                pl.lit(v).pow(pl.int_range(0, pl.element().len()))
            )

        if isinstance(discount_rate, ExpressionProxy):
            rate_expr = discount_rate._expr  # noqa: SLF001
        elif isinstance(discount_rate, ColumnProxy):
            rate_expr = pl.col(discount_rate.name)
        else:
            msg = (
                "discount_rate must be float, ExpressionProxy, or ColumnProxy, "
                f"got {type(discount_rate)}"
            )
            raise TypeError(msg)

        # List column of rates: cumulative product of 1/(1+r)
        v_expr = rate_expr.list.eval((1.0 / (1.0 + pl.element())).cum_prod())
        # Shift to get beginning-of-period: [1, v[0], v[0]*v[1], ...]
        list_len = v_expr.list.len()
        return pl.concat_list([pl.lit([1.0]), v_expr]).list.slice(0, list_len)

    def prospective_value(
        self,
        discount_rate: float | ExpressionProxy | ColumnProxy | None = None,
        discount_factor: ExpressionProxy | ColumnProxy | None = None,
        *,
        timing: Literal["beginning_of_period", "end_of_period"] = "end_of_period",
    ) -> ExpressionProxy:
        """Calculate prospective (present) value of future cashflows from each time t.

        Computes the present value of all future cashflows from each projection period
        onwards, using backward recursion: PV(t) = CF(t) + PV(t+1) * v(t).

        This is the standard actuarial "prospective policy value" calculation, essential
        for reserve valuations, embedded value projections, profit testing, and asset
        adequacy testing. Replaces complex Polars list operations with a clean,
        actuarial-focused API.

        !!! note "When to use"
            * **Reserve Calculations:** Compute present value of future benefits less
                premiums for statutory and GAAP reserve valuations.
            * **Embedded Value:** Calculate present value of future profits for
                embedded value and value of in-force business metrics.
            * **Profit Testing:** Project present value of cashflows at each duration
                for pricing validation and profitability analysis.
            * **Asset Adequacy:** Test sufficiency of assets to cover future liabilities
                under various interest rate scenarios.

        Parameters
        ----------
        discount_rate : float or ExpressionProxy or ColumnProxy, optional
            Per-period discount rate for discounting future cashflows:

            - Scalar float: Constant rate for all periods (e.g., 0.05 for 5%)
            - List column: Per-period rates that may vary over time

            Cannot be specified together with `discount_factor`.
        discount_factor : ExpressionProxy or ColumnProxy, optional
            Pre-computed discount factors (v^t values). Use when you have yield curve
            or scenario-specific discount factors already calculated.

            Cannot be specified together with `discount_rate`.
        timing : {"beginning_of_period", "end_of_period"}, default "end_of_period"
            When cashflows occur within each period:

            - ``"end_of_period"``: Cashflow at t paid at end of period (benefits)
            - ``"beginning_of_period"``: Cashflow at t paid at start (premiums)

        Returns
        -------
        ExpressionProxy
            Present value of future cashflows at each projection period

        Raises
        ------
        ValueError
            If both `discount_rate` and `discount_factor` are specified,
            or if neither is specified

        Examples
        --------
        **Death Benefit PV with Constant Discount Rate**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "death_benefit": [[100.0, 100.0, 100.0]],
        }
        af = ActuarialFrame(data)

        # Calculate prospective value at 5% discount rate
        af.pv_benefits = af.death_benefit.projection.prospective_value(
            discount_rate=0.05
        )

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌────────────────────┬─────────────────────────────┐
        │ death_benefit      ┆ pv_benefits                 │
        │ ---                ┆ ---                         │
        │ list[f64]          ┆ list[f64]                   │
        ╞════════════════════╪═════════════════════════════╡
        │ [100.0, 100.0, ... ┆ [285.94, 195.24, 100.0]     │
        └────────────────────┴─────────────────────────────┘
        ```

        **Premium PV with Time-Varying Rates**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "premium": [[1000.0, 1000.0, 1000.0]],
            "disc_rate": [[0.04, 0.05, 0.06]],
        }
        af = ActuarialFrame(data)

        af.pv_premiums = af.premium.projection.prospective_value(
            discount_rate=af.disc_rate,
            timing="beginning_of_period"
        )

        print(af.collect())
        ```

        **With Pre-Computed Discount Factors**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "benefit": [[100.0, 100.0, 100.0]],
            "v_t": [[1.0, 0.952381, 0.907029]],  # 5% discount factors
        }
        af = ActuarialFrame(data)

        af.pv = af.benefit.projection.prospective_value(discount_factor=af.v_t)

        print(af.collect())
        ```

        Notes
        -----
        **Implementation Details:**

        The method internally performs:

        1. Compute discounted cashflows: CF(t) * v(t)
        2. Fill NaN values with 0 (handles cashflows beyond policy term)
        3. Apply reverse -> cumsum -> reverse pattern to get "sum from t to end"
        4. Adjust for timing convention

        **Replaces Ugly Pattern:**

        This method replaces verbose Polars list manipulation. The old pattern
        required 6+ lines of Polars list operations (reverse, cumsum, reverse),
        while the new API is a single clean method call.

        See Also
        --------
        cumulative_survival : Calculate cumulative survival probabilities
        previous_period : Access prior period values for reserve rollforward

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Validate parameters
        if discount_rate is not None and discount_factor is not None:
            msg = (
                "Cannot specify both 'discount_rate' and 'discount_factor'. "
                "Use 'discount_rate' for interest rates, or 'discount_factor' "
                "for pre-computed v^t values."
            )
            raise ValueError(msg)

        if discount_rate is None and discount_factor is None:
            msg = (
                "Must specify either 'discount_rate' or 'discount_factor'. "
                "Use 'discount_rate' for interest rates (e.g., 0.05 for 5%), or "
                "'discount_factor' for pre-computed v^t values."
            )
            raise ValueError(msg)

        # Get base cashflow expression and parent frame
        cashflow_expr = self._get_polars_expr()
        parent_af = self._get_parent_frame()

        # Build discount factor expression
        v_expr = self._build_discount_factors(
            cashflow_expr, discount_rate, discount_factor
        )

        # Compute discounted cashflows: CF(t) * v(t)
        discounted_cf = cashflow_expr * v_expr

        # Apply reverse -> cumsum -> reverse pattern to get remaining PV
        remaining_pv = (
            discounted_cf.list.eval(pl.element().fill_nan(0.0))
            .list.reverse()
            .list.eval(pl.element().cum_sum())
            .list.reverse()
        )

        # Apply timing adjustment: end_of_period gives PV with no extra discounting,
        # beginning_of_period multiplies by per-period v[t] (one extra discount period)
        end_of_period_result = remaining_pv / v_expr

        if timing == "end_of_period":
            result_expr = end_of_period_result
        elif timing == "beginning_of_period":
            # Compute per-period discount factor v[t] = 1/(1+r[t])
            # GSP-70 fix: multiply by v[t] at ALL periods including t=0
            if isinstance(discount_rate, (int, float)):
                # Scalar rate: constant v
                per_period_v = 1.0 / (1.0 + discount_rate)
                result_expr = end_of_period_result * per_period_v
            elif discount_rate is not None:
                # List column of rates: v[t] = 1/(1+r[t])
                from gaspatchio_core.column.column_proxy import ColumnProxy
                from gaspatchio_core.column.expression_proxy import ExpressionProxy

                if isinstance(discount_rate, ExpressionProxy):
                    rate_expr = discount_rate._expr  # noqa: SLF001
                elif isinstance(discount_rate, ColumnProxy):
                    rate_expr = pl.col(discount_rate.name)
                else:
                    rate_expr = discount_rate
                per_period_v = rate_expr.list.eval(1.0 / (1.0 + pl.element()))
                result_expr = end_of_period_result * per_period_v
            else:
                # discount_factor provided: derive v from v[t]/v[t-1]
                # For BOP, we need the per-period v, which is v[t]/v[t-1]
                # At t=0: v[0]/v[-1] = v[0]/1 = v[0]
                # At t=1: v[1]/v[0]
                v_prev = v_expr.list.eval(pl.element().shift(1, fill_value=1.0))
                per_period_v = v_expr / v_prev
                result_expr = end_of_period_result * per_period_v
        else:
            msg = (
                f"Invalid timing value: {timing!r}. "
                "Must be 'beginning_of_period' or 'end_of_period'"
            )
            raise ValueError(msg)

        return ExpressionProxy(result_expr, parent_af)

    def accumulate(
        self,
        *,
        initial: str | pl.Expr | ExpressionProxy | ColumnProxy,
        multiply: str | pl.Expr | ExpressionProxy | ColumnProxy,
        add: str | pl.Expr | ExpressionProxy | ColumnProxy,
    ) -> ExpressionProxy:
        """Accumulate values using a linear recurrence.

        Computes ``state[t] = state[t-1] * multiply[t] + add[t]`` for each
        time step, returning all intermediate states as a list column.

        This is the core primitive for account value rollforwards and other
        state-dependent actuarial projections.

        Parameters
        ----------
        initial
            Initial state per policy (e.g., starting account value).
        multiply
            Multiplicative growth factor per time step.
        add
            Additive flow per time step (premiums minus charges, etc.).

        Returns
        -------
        ExpressionProxy
            List column of accumulated values at each time step.

        Examples
        --------
        >>> growth = 1 + af.interest_rate
        >>> net_flow_grown = (af.premiums - af.fees) * growth
        >>> af.av = af.projection.accumulate(
        ...     initial=af.av_pp_init,
        ...     multiply=growth,
        ...     add=net_flow_grown,
        ... )

        """
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.functions.vector import accumulate as _accumulate

        parent_af = self._get_parent_frame()

        def _resolve_to_expr(
            param: str | pl.Expr | ExpressionProxy | ColumnProxy,
        ) -> pl.Expr:
            """Resolve a parameter to a Polars expression."""
            if isinstance(param, ExpressionProxy):
                return param._expr  # noqa: SLF001
            if isinstance(param, ColumnProxy):
                return pl.col(param.name)
            if isinstance(param, str):
                return pl.col(param)
            return param

        initial_expr = _resolve_to_expr(initial)
        multiply_expr = _resolve_to_expr(multiply)
        add_expr = _resolve_to_expr(add)

        result_expr = _accumulate(initial_expr, multiply_expr, add_expr)
        return ExpressionProxy(result_expr, parent_af)
