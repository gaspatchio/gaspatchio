# ABOUTME: Projection accessor for actuarial projection operations.
# ABOUTME: Methods: cumulative survival, period overrides, time-shifting.

"""Projection accessor for actuarial operations on time-series."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

    def cumulative_survival(self, start_at: float | None = 1.0) -> ExpressionProxy:
        """Convert mortality rates to cumulative survival probabilities.

        Transforms period mortality rates (qx) into cumulative survival probabilities
        using the formula tpx[t] = (1-qx[0]) * (1-qx[1]) * ... * (1-qx[t]). Essential
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

        Parameters
        ----------
        start_at : float, optional
            Initial survival probability to prepend at t=0. Shifts results to give
            beginning-of-period values (standard actuarial practice). Common values:
            - 1.0 (default): Beginning-of-period, full cohort [1.0, tpx[0], tpx[1], ...]
            - None: End-of-period survival [tpx[0], tpx[1], ...]
            - Other: Partial cohort after initial selection (e.g., 0.95 for 95%)

        Returns
        -------
        ExpressionProxy
            Cumulative survival probabilities for each period

        Raises
        ------
        RuntimeError
            If the column is not part of an ActuarialFrame context

        Examples
        --------
        **Vector Example: Policies Inforce (Beginning-of-Period)**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "qx": [[0.001, 0.002, 0.003], [0.002, 0.003, 0.004]],
        }
        af = ActuarialFrame(data)

        af.pols_if = af.qx.projection.cumulative_survival()

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

        **Vector Example: End-of-Period Survival**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "qx": [[0.001, 0.002, 0.003]],
        }
        af = ActuarialFrame(data)

        # For death benefits, use end-of-period survival
        af.tpx = af.qx.projection.cumulative_survival(start_at=None)

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

        **Vector Example: Partial Cohort (Post-Underwriting)**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "qx": [[0.001, 0.002, 0.003]],
        }
        af = ActuarialFrame(data)

        # 95% survived underwriting
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
