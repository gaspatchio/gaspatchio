# ABOUTME: Projection accessor for actuarial projection operations.
# ABOUTME: Methods: cumulative survival, discount, period overrides.

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

        Discount factors from interest rates:

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"interest_rate": [[0.05, 0.05, 0.05]]}
        af = ActuarialFrame(data)

        # Complex cumulative discount - use projection method
        af.v = af.interest_rate.projection.cumulative_discount()

        # Simple multiplication - use operators
        af.pv_cashflow = af.net_cashflow * af.v
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

    def cumulative_discount(
        self,
        mode: Literal["compound", "simple"] = "compound",
        start_at: float | None = 1.0,
    ) -> ExpressionProxy:
        """Convert interest rates to cumulative discount factors.

        Transforms period-by-period interest rates into cumulative discount factors
        (also known as present value factors or v^t) using compound or simple interest.
        Essential for calculating present values of future cashflows in actuarial
        projections, reserve valuations, and pricing models.

        For list columns, applies element-wise cumulative product within each list.
        For scalar columns, applies cumulative product across rows (use `.over()` for
        grouping by policy).

        !!! note "When to use"
            * **Present Value Calculations:** Discount future cashflows (premiums,
                benefits, expenses) to their present value for pricing and reserving.
            * **Policy Valuations:** Calculate actuarial present values (APVs) of
                expected future payments for statutory and GAAP reserves.
            * **Pricing Models:** Determine profit margins and premium rates by
                discounting projected profits to policy issue date.
            * **Capital Modeling:** Project discounted cashflows for economic capital,
                embedded value, and risk-based capital calculations.

        Parameters
        ----------
        mode : str, optional
            Discount mode: "compound" for compound interest (default) or "simple"
            for simple interest
        start_at : float, optional
            Initial discount factor to prepend at t=0. Shifts results to give
            beginning-of-period values (standard actuarial practice). Common values:
            - 1.0 (default): Beginning-of-period, v^0=1.0 [1.0, v^1, v^2, ...]
            - None: End-of-period discount [v^1, v^2, ...]
            - Other: Custom initial discount factor

        Returns
        -------
            Cumulative discount factors

        Raises
        ------
            RuntimeError: If proxy not associated with an ActuarialFrame
            ValueError: If mode is not "compound" or "simple"

        Examples
        --------
        **Vector Example: Beginning-of-Period Discount**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"rate": [[0.05, 0.05, 0.05]]}
        af = ActuarialFrame(data)

        af.v = af.rate.projection.cumulative_discount()

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌────────────────────┬───────────────────────────┐
        │ rate               ┆ v                         │
        │ ---                ┆ ---                       │
        │ list[f64]          ┆ list[f64]                 │
        ╞════════════════════╪═══════════════════════════╡
        │ [0.05, 0.05, 0.05] ┆ [1.0, 0.952381, 0.907029] │
        └────────────────────┴───────────────────────────┘
        ```

        **Vector Example: Present Value Calculation**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "cashflow": [[1000, 1000, 1000]],
            "rate": [[0.05, 0.05, 0.05]],
        }
        af = ActuarialFrame(data)

        af.v = af.rate.projection.cumulative_discount()
        af.pv = af.cashflow * af.v

        print(af.collect())
        ```

        ```text
        shape: (1, 4)
        ┌────────────────────┬────────────────────┬──────────────────────┬────────┐
        │ cashflow           ┆ rate               ┆ v                    ┆ pv     │
        │ ---                ┆ ---                ┆ ---                  ┆ ---    │
        │ list[i64]          ┆ list[f64]          ┆ list[f64]            ┆ list[… │
        ╞════════════════════╪════════════════════╪══════════════════════╪════════╡
        │ [1000, 1000, 1000] ┆ [0.05, 0.05, 0.05] ┆ [0.952381, 0.907029, ┆ [952.3 │
        │                    ┆                    ┆ 0.863838]            ┆ 80952… │
        └────────────────────┴────────────────────┴──────────────────────┴────────┘
        ```

        **Vector Example: Simple Interest Mode**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"interest_rate": [[0.05, 0.05, 0.05]]}
        af = ActuarialFrame(data)

        af.v_simple = af.interest_rate.projection.cumulative_discount(mode="simple")

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌────────────────────┬───────────────────────────┐
        │ interest_rate      ┆ v_simple                  │
        │ ---                ┆ ---                       │
        │ list[f64]          ┆ list[f64]                 │
        ╞════════════════════╪═══════════════════════════╡
        │ [0.05, 0.05, 0.05] ┆ [1.0, 0.952381, 0.909091] │
        └────────────────────┴───────────────────────────┘
        ```

        """
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.dispatch import (
            ColumnTypeDetector,  # type: ignore[attr-defined]
        )
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Validate mode
        if mode not in ("compound", "simple"):
            msg = f"mode must be 'compound' or 'simple', got '{mode}'"
            raise ValueError(msg)

        # Get base expression and parent frame
        base_expr = self._get_polars_expr()
        parent_af = self._get_parent_frame()

        # Determine if this is a list column
        detector = ColumnTypeDetector(parent_af)
        is_list = False

        if isinstance(self._proxy, ColumnProxy):
            is_list = detector.is_list_column(self._proxy.name)

        # Apply appropriate calculation based on mode
        if mode == "compound":
            if is_list:
                # For list columns, apply element-wise cumulative discount.
                # This computes discount[t] = v[0] * v[1] * ... * v[t]
                # where v[i] = 1/(1+r[i]).
                discount_expr = base_expr.list.eval((1 / (1 + pl.element())).cum_prod())

                # Apply start_at shift if requested (for list columns)
                if start_at is not None:
                    # Prepend start_at value and drop last element to maintain length
                    # This gives beginning-of-period values: [start_at, v^1, v^2, ...]
                    list_len = discount_expr.list.len()
                    discount_expr = pl.concat_list(
                        [pl.lit([start_at]), discount_expr]
                    ).list.slice(0, list_len)
            else:
                # For scalar columns, apply cumulative product of discount factors.
                discount_expr = (1 / (1 + base_expr)).cum_prod()

                # Apply start_at shift if requested (for scalar columns)
                if start_at is not None:
                    discount_expr = discount_expr.shift(1, fill_value=start_at)
        elif is_list:
            # For list columns with simple interest.
            # This computes discount[t] = 1 / (1 + r * t) using period indices.
            # Inside list.eval, use element-wise index which starts at 0
            discount_expr = base_expr.list.eval(
                1 / (1 + pl.element() * (pl.element().cum_count() - 1))
            )

            # Apply start_at shift if requested (for list columns)
            if start_at is not None:
                list_len = discount_expr.list.len()
                discount_expr = pl.concat_list(
                    [pl.lit([start_at]), discount_expr]
                ).list.slice(0, list_len)
        else:
            # For scalar columns with simple interest, use cum_count for period indices.
            # Assumes first rate is at period 0.
            discount_expr = 1 / (1 + base_expr * (pl.cum_count().over(pl.all()) - 1))

            # Apply start_at shift if requested (for scalar columns)
            if start_at is not None:
                discount_expr = discount_expr.shift(1, fill_value=start_at)

        return ExpressionProxy(discount_expr, parent_af)

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

    def previous_period(self, fill_value=0) -> ExpressionProxy:
        """Get value from previous period (t-1).

        Equivalent to shifting back one period. Most common case for
        actuarial projections when referencing prior period values.

        For list columns, shifts values within each list. For scalar columns,
        shifts across rows (use `.over()` for grouping).

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
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()

        # For list columns: prepend fill_value and slice to original length
        # This creates the effect of shifting back one period (t-1)
        shifted_expr = pl.concat_list([pl.lit([fill_value]), base_expr]).list.slice(
            0, base_expr.list.len()
        )

        parent_af = self._get_parent_frame()
        return ExpressionProxy(shifted_expr, parent_af)
