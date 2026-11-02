# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Projection accessor for actuarial projection operations.
# ABOUTME: Methods: cumulative survival, period overrides, time-shifting.
# ruff: noqa: PLC0415

"""Projection accessor for actuarial operations on time-series."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import polars as pl

from gaspatchio.accessors.base import (
    BaseColumnAccessor,
    refuse_bare_string_operand,
    refuse_bare_string_override,
)
from gaspatchio.frame.registry import register_accessor

if TYPE_CHECKING:
    from polars.datatypes import DataTypeClass

    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.column.column_proxy import ColumnProxy
    from gaspatchio.column.expression_proxy import ExpressionProxy
    from gaspatchio.frame.base import ActuarialFrame


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
        - Terminal/aggregate values: Use Polars (`.polars_native().list.last()`)

    Accessed via `.projection` on a column or expression, e.g.,
    `af["mortality_rate"].projection.cumulative_survival()`.

    A bare string operand is refused here, as on every column accessor;
    see `refuse_bare_string_operand` for the rule and why it holds.

    Examples:
        Cumulative survival from mortality rates:

        ```python
        from gaspatchio import ActuarialFrame

        data = {"qx": [[0.001, 0.0011, 0.0012], [0.002, 0.0022, 0.0024]]}
        af = ActuarialFrame(data)

        # Complex cumulative product - use projection method
        af.survival_to_t = af.qx.projection.cumulative_survival()

        # Simple multiplication - use operators
        af.death_benefit = af.face_amount * af.survival_to_t * af.qx
        af.premium = af.annual_premium * af.survival_to_t

        # Terminal value - use Polars
        af.maturity_benefit = af.face_amount.polars_native().list.last()
        ```

        Premium holiday modeling:

        ```python
        from gaspatchio import ActuarialFrame

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

    def _get_node(self) -> OpNode:
        """Get the op-tree node this accessor's column stands for.

        Every method below emits a ``Call`` over this node rather than
        building a Polars expression: the accessor decides *what* the
        actuary asked for, and the registered lowering in
        ``frame/lowering/rules/projection.py`` decides how it is computed.
        """
        from gaspatchio.column.column_proxy import ColumnProxy
        from gaspatchio.column.expression_proxy import ExpressionProxy

        if isinstance(self._proxy, (ColumnProxy, ExpressionProxy)):
            return self._proxy._node  # noqa: SLF001
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
        *,
        from_survival: bool = False,
    ) -> ExpressionProxy:
        """Convert mortality rates to cumulative survival probabilities.

        Transforms period mortality rates (qx) into cumulative survival probabilities
        using the formula `tpx[t] = (1-qx[0]) * (1-qx[1]) * ... * (1-qx[t])`. Essential
        for life insurance projections, reserve calculations, and any actuarial work
        requiring survival probabilities from mortality assumptions.

        When the source hands you a **survival-shaped** factor instead — a combined
        persistency `px = (1-qx)(1-lapse)`, extremely common in reserving — pass
        ``from_survival=True`` and the factors cumulate directly, with no
        inversion anywhere. Spelling it as ``1 - px`` so the method can undo it
        is a lossy round trip: ``1 - (1 - px)`` is exact only while
        ``px >= 0.5``, and a shock-lapse year sits well below that. The error
        is tiny (~1e-17) but avoidable for free, and a strict tie-out sees it.

        For list columns, applies element-wise cumulative product within each list.
        A per-policy (scalar) column is refused on a frame with a projection
        timeline, where the rows are policies: derive a per-period column first. On
        a frame without one, where each row is a period, it applies the cumulative
        product down the rows (use `.over()` for grouping by policy).

        !!! note "When to use"
            * **Life Insurance Projections:** Calculate the probability policies remain
                inforce for death benefit, premium, and cash value projections.
            * **Reserve Calculations:** Compute expected policy counts for reserve
                valuations and capital requirements.
            * **Persistency Analysis:** Model combined mortality and lapse decrements
                to project policy persistency over time.
            * **Pricing Models:** Calculate expected present values of benefits and
                premiums weighted by survival probabilities.

        A null decrement ends the running survival's knowledge of itself.

        Timing Conventions
        ------------------
        The `rate_timing` parameter controls when decrement rates are applied:

        * **beginning_of_period** (default): Rate at period t is NOT yet applied to
          P[IF][t]. The survival at t represents the probability of surviving TO the
          start of period t. Result: ``[1.0, tpx[0], tpx[0]*tpx[1], ...]``

        * **end_of_period**: Rate at period t HAS been applied to P[IF][t]. The
          survival at t represents the probability of surviving THROUGH period t.
          This matches Excel-style timing. Result: ``[tpx[0], tpx[0]*tpx[1], ...]``

        The two conventions do not give the same values, even at a flat rate: the
        end-of-period survival at t is the beginning-of-period survival at t+1, one
        period's decrement further on -- at q = 0.01 the default gives
        ``[1.0, 0.99, 0.9801]`` and ``end_of_period`` gives
        ``[0.99, 0.9801, 0.970299]``.
        Use the one the source model uses, and test with rates that vary by period
        (across an age boundary, say): a flat-rate test can pass a wrong conversion
        between the two timing conventions, which fails once rates vary.

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
            - Other ``a``: ``[a, tpx[0], tpx[1], ...]`` -- ``a`` is the value
              at the opening boundary only, not a factor on later periods
              (spec 11.1.19). To scale the whole curve, for a cohort of which
              95% survived underwriting, multiply it:
              ``0.95 * af.qx.projection.cumulative_survival()``.
        from_survival : bool, optional
            The column already holds survival-shaped factors (px, persistency),
            not decrement rates. Factors cumulate directly — no ``1 - x``
            anywhere — so shock-lapse years below px = 0.5 stay bit-exact.
            Timing parameters mean exactly the same thing in both shapes.

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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

        **Survival-Shaped Input (Combined Persistency)**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "px": [[0.999, 0.998, 0.997]],
        }
        af = ActuarialFrame(data)

        # The column already holds survival factors - cumulate them directly
        af.cum_px = af.px.projection.cumulative_survival(
            rate_timing="end_of_period", from_survival=True
        )

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌───────────────────────┬─────────────────────────────┐
        │ px                    ┆ cum_px                      │
        │ ---                   ┆ ---                         │
        │ list[f64]             ┆ list[f64]                   │
        ╞═══════════════════════╪═════════════════════════════╡
        │ [0.999, 0.998, 0.997] ┆ [0.999, 0.997002, 0.994011] │
        └───────────────────────┴─────────────────────────────┘
        ```

        **A Partial Cohort Scales the Whole Curve**

        ``start_at`` is only the opening boundary's value -- ``start_at=0.95``
        gives ``[0.95, 0.999, 0.997002]``, an in-force that rises at t=1. For a
        cohort of which 95% survived underwriting, multiply the curve:

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "qx": [[0.001, 0.002, 0.003]],
        }
        af = ActuarialFrame(data)

        # 95% of the cohort survived underwriting: scale the whole curve by 0.95
        af.pols_if = 0.95 * af.qx.projection.cumulative_survival()

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌───────────────────────┬───────────────────────────┐
        │ qx                    ┆ pols_if                   │
        │ ---                   ┆ ---                       │
        │ list[f64]             ┆ list[f64]                 │
        ╞═══════════════════════╪═══════════════════════════╡
        │ [0.001, 0.002, 0.003] ┆ [0.95, 0.94905, 0.947152] │
        └───────────────────────┴───────────────────────────┘
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
        from gaspatchio._authoring import emit

        parent_af = self._get_parent_frame()
        return emit.call(
            "projection.cumulative_survival",
            (_read_as_a_double(self._get_node(), parent_af, opening=False),),
            parent_af,
            (("start_at", start_at), ("from_survival", from_survival)),
        )

    def with_period(self, period: int, value: float) -> ExpressionProxy:
        """Override value at a specific period (zero-indexed).

        Creates a modified version of a list column with a specific element set to
        a new value. Essential for modeling planned policy changes, premium holidays,
        benefit adjustments, and other known discontinuities in actuarial projections.

        This method only works with list columns. For scalar columns, use conditional
        logic with `.when()` and `.then()`.

        The override is one number, so a bare string is refused (see
        `refuse_bare_string_override`) and so is a column: a replacement
        that varies by policy is a `when/otherwise` conditional.

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
        value : int or float
            The number to set at that period.

        Returns
        -------
            Modified list with value changed at specified period

        Raises
        ------
            RuntimeError: If proxy not associated with an ActuarialFrame
            TypeError: If ``value`` is a bare string
            ValueError: If period is out of bounds for the list

        Examples
        --------
        **Vector Example: Premium Holiday**

        ```python
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio._authoring import emit

        refuse_bare_string_override(value, parameter="value")

        parent_af = self._get_parent_frame()
        return emit.call(
            "projection.with_period",
            (self._get_node(),),
            parent_af,
            (("period", period), ("value", value)),
        )

    def with_periods(self, updates: dict[int, int | float]) -> ExpressionProxy:
        """Override values at multiple specific periods.

        Creates a modified version of a list column with multiple elements changed
        at once. More efficient and readable than chaining multiple `with_period()`
        calls. Essential for modeling complex benefit schedules, premium patterns,
        and assumption variations across policy durations.

        Each override is one number, on the same terms as `with_period`.

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
        updates : dict[int, int | float]
            Dictionary mapping period indices (zero-based) to the numbers to
            set there. Negative indices are supported (-1 = last period).

        Returns
        -------
            Modified list with values changed at specified periods

        Raises
        ------
            RuntimeError: If proxy not associated with an ActuarialFrame
            TypeError: If any override is a bare string
            ValueError: If any period is out of bounds for the list

        Examples
        --------
        **Vector Example: Multiple Premium Holidays**

        ```python
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio.column.expression_proxy import ExpressionProxy

        # Every override is checked before any of them is applied, and each
        # refusal names its own dict entry -- `updates[3]`, not `value` --
        # so the message points at the line the actuary wrote rather than
        # at whichever entry the chaining below happened to reach first.
        for period, override in updates.items():
            refuse_bare_string_override(override, parameter=f"updates[{period}]")

        parent_af = self._get_parent_frame()

        # Sort updates by period index to apply them in order.
        # This ensures negative indices work correctly.
        sorted_updates = sorted(updates.items(), key=lambda x: x[0])

        # Apply each update sequentially by chaining with_period calls. No
        # expression is built here -- each step nests one Call inside the
        # next, so the whole sequence of overrides is one op-tree.
        temp_proxy = ExpressionProxy._from_node(  # noqa: SLF001
            self._get_node(), parent_af
        )
        for period, value in sorted_updates:
            temp_proxy = ProjectionColumnAccessor(temp_proxy).with_period(period, value)

        return temp_proxy

    def previous_period(self, fill_value=0.0) -> ExpressionProxy:
        """Get value from previous period (t-1).

        Equivalent to shifting back one period. Most common case for
        actuarial projections when referencing prior period values.

        For list columns, shifts values within each list. A per-policy (scalar)
        column is refused on a frame with a projection timeline, where the rows
        are policies. On a frame without one, where each row is a period, it
        shifts down the rows (use `.over()` for grouping).

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio._authoring import emit

        parent_af = self._get_parent_frame()
        return emit.call(
            "projection.previous_period",
            (_a_run_shifted_under(self._get_node(), fill_value, parent_af), fill_value),
            parent_af,
        )

    def next_period(self, fill_value=0.0) -> ExpressionProxy:
        """Get value from next period (t+1).

        Equivalent to shifting forward one period. Less common than
        `previous_period()` but useful for certain actuarial calculations
        requiring forward-looking values.

        For list columns, shifts values within each list. A per-policy (scalar)
        column is refused on a frame with a projection timeline, where the rows
        are policies. On a frame without one, where each row is a period, it
        shifts down the rows (use `.over()` for grouping).

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio._authoring import emit

        parent_af = self._get_parent_frame()
        return emit.call(
            "projection.next_period",
            (_a_run_shifted_under(self._get_node(), fill_value, parent_af), fill_value),
            parent_af,
        )

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

        For list columns, shifts values within each list. A per-policy (scalar)
        column is refused on a frame with a projection timeline, where the rows
        are policies. On a frame without one, where each row is a period, it
        shifts down the rows (use `.over()` for grouping).

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio._authoring import emit

        parent_af = self._get_parent_frame()
        return emit.call(
            "projection.at_period",
            (_a_run_shifted_under(self._get_node(), fill_value, parent_af), fill_value),
            parent_af,
            (("relative_period", relative_period),),
        )

    def broadcast_to_periods(
        self, like: ColumnProxy | ExpressionProxy | pl.Expr | None = None
    ) -> ExpressionProxy:
        """Broadcast a per-policy scalar column across the projection periods.

        Repeats this column's value once per projection period, producing a
        list column aligned with the frame's axis. Works for **every dtype**
        — strings, booleans, and categoricals included — unlike the numeric
        idiom ``af.scalar + af.list * 0.0``, which has no string equivalent
        and previously forced hand-rolled ``repeat_by`` helpers into model
        code.

        !!! note "When to use"
            * **String dimensions in lookups:** A per-policy ``occupation_class``
                or ``smoker_status`` feeding a per-period `Table.lookup` needs
                one value per period, not one per policy.
            * **Per-period conditionals on policy attributes:** Broadcasting a
                label before a ``when()`` that selects between per-period lists.
            * **Any scalar-to-period alignment** where arithmetic broadcasting
                does not apply (non-numeric dtypes).

        Parameters
        ----------
        like : ColumnProxy or ExpressionProxy or pl.Expr, optional
            A list column whose per-row lengths define the broadcast length —
            use this on frames without a projection axis, or to match a
            specific column's (possibly jagged) lengths. Defaults to the
            frame's ``month`` period index, stamped by ``projection.set()``.

        Returns
        -------
        ExpressionProxy
            List column repeating this column's value once per period.

        Raises
        ------
        ValueError
            If ``like`` is not given and the frame has no ``month`` column
            to take period lengths from.

        Examples
        --------
        **String attribute broadcast to the projection axis**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "occupation_class": ["M", "H"],
            "month": [[0, 1, 2], [0, 1, 2]],
        }
        af = ActuarialFrame(data)

        af.occupation_per_period = af.occupation_class.projection.broadcast_to_periods()

        print(af.collect())
        ```

        ```text
        shape: (2, 3)
        ┌──────────────────┬───────────┬───────────────────────┐
        │ occupation_class ┆ month     ┆ occupation_per_period │
        │ ---              ┆ ---       ┆ ---                   │
        │ str              ┆ list[i64] ┆ list[str]             │
        ╞══════════════════╪═══════════╪═══════════════════════╡
        │ M                ┆ [0, 1, 2] ┆ ["M", "M", "M"]       │
        │ H                ┆ [0, 1, 2] ┆ ["H", "H", "H"]       │
        └──────────────────┴───────────┴───────────────────────┘
        ```

        **Matching a specific (jagged) list column with `like=`**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "frequency": ["monthly", "annual"],
            "premiums": [[100.0, 100.0], [1200.0, 1200.0, 1200.0]],
        }
        af = ActuarialFrame(data)

        af.frequency_per_period = af.frequency.projection.broadcast_to_periods(
            like=af.premiums
        )

        print(af.collect())
        ```

        ```text
        shape: (2, 3)
        ┌───────────┬──────────────────┬───────────────────────────┐
        │ frequency ┆ premiums         ┆ frequency_per_period      │
        │ ---       ┆ ---              ┆ ---                       │
        │ str       ┆ list[f64]        ┆ list[str]                 │
        ╞═══════════╪══════════════════╪═══════════════════════════╡
        │ monthly   ┆ [100.0, 100.0]   ┆ ["monthly", "monthly"]    │
        │ annual    ┆ [1200.0, … 1200… ┆ ["annual", "annual", "an… │
        └───────────┴──────────────────┴───────────────────────────┘
        ```

        See Also
        --------
        previous_period : Access prior-period values on the same axis

        """
        from gaspatchio._authoring import emit
        from gaspatchio._semantic.ir import Col
        from gaspatchio.column.column_proxy import ColumnProxy
        from gaspatchio.column.expression_proxy import ExpressionProxy

        parent_af = self._get_parent_frame()
        args: tuple[object, ...] = (self._get_node(),)

        if like is not None:
            if not isinstance(like, (ColumnProxy, ExpressionProxy, pl.Expr)):
                msg = (
                    "broadcast_to_periods(like=...) expects a list column "
                    f"(ColumnProxy/ExpressionProxy/pl.Expr); got {type(like)}"
                )
                raise TypeError(msg)
            args = (*args, like)
        else:
            columns = getattr(parent_af, "columns", None)
            # A calendar axis stamps `month` where it is honest, and a
            # fixed-step axis always stamps `step`; either is one value per
            # boundary, so either gives the period length.
            schema = getattr(parent_af, "_schema", None) or {}
            index = (
                "step"
                if "month" not in schema and isinstance(schema.get("step"), pl.List)
                else "month"
            )
            if columns is not None and index not in columns:
                msg = (
                    "broadcast_to_periods() needs a period length and this "
                    "frame has no `month` or `step` period index "
                    "(projection.set() stamps one). Either set a projection "
                    "axis first, or pass like=<a list column> to broadcast to "
                    "that column's lengths."
                )
                raise ValueError(msg)

            # The axis affects the result just as an explicit `like` does.
            # Record the read so graph traversal and portable replay see it.
            args = (*args, Col(index))

        return emit.call("projection.broadcast_to_periods", args, parent_af)

    def remaining_sum(self) -> ExpressionProxy:
        """Compute backward cumulative sum (remaining sum from each period to end).

        For each element at position ``t``, returns the sum of all elements
        from ``t`` to the end of the list. Equivalent to reversing the list,
        computing a cumulative sum, then reversing back.

        This is the standard pattern for IFRS 17 coverage unit remaining
        totals, remaining premium factors, and annuity-due calculations
        where you need "sum of all future values from this point."

        !!! note "When to use"
            * **IFRS 17 Coverage Units:** Compute ``cu_remaining[t]`` — the
                total remaining coverage from period ``t`` onward — for CSM
                amortisation factor calculation: ``amort[t] = cu[t] / cu_remaining[t]``.
            * **Remaining Premium Factors:** Calculate the remaining expected
                premium stream from each period for net premium reserve
                formulas.
            * **Annuity-Due Factors:** Derive the running sum of future
                discount factors for annuity-due present value calculations.

        A null period makes that position and every earlier position null. A
        modeller who means nought writes ``af.col.fill_null(0.0)`` before the
        total, and the graph then records that they said so.

        Returns
        -------
        ExpressionProxy
            List column where each element is the sum from that position
            to the end of the original list.

        Examples
        --------
        **IFRS 17 coverage unit remaining totals**

        ```python
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame(
            {
                "policy_id": ["P001", "P002"],
                "coverage_units": [
                    [100, 90, 80, 70, 60],
                    [200, 180, 160, 140, 120],
                ],
            }
        )

        af.cu_remaining = af.coverage_units.projection.remaining_sum()

        print(af.collect().select(["policy_id", "coverage_units", "cu_remaining"]))
        ```

        ```text
        shape: (2, 3)
        ┌───────────┬───────────────────┬───────────────────┐
        │ policy_id ┆ coverage_units    ┆ cu_remaining      │
        │ ---       ┆ ---               ┆ ---               │
        │ str       ┆ list[i64]         ┆ list[i64]         │
        ╞═══════════╪═══════════════════╪═══════════════════╡
        │ P001      ┆ [100, 90, … 60]   ┆ [400, 300, … 60]  │
        │ P002      ┆ [200, 180, … 120] ┆ [800, 600, … 120] │
        └───────────┴───────────────────┴───────────────────┘
        ```

        Notes
        -----
        - At the last period, ``remaining_sum`` equals the element itself.
        - At ``t=0``, it equals the total sum of the entire list.
        - The relationship ``amort_factor[t] = cu[t] / cu_remaining[t]``
          gives the proportion of CSM to release in each period.

        See Also
        --------
        cumulative_survival : Forward cumulative product for survival probabilities
        prospective_value : Present value of future cashflows from each period

        """
        from gaspatchio._authoring import emit

        parent_af = self._get_parent_frame()
        return emit.call("projection.remaining_sum", (self._get_node(),), parent_af)

    def prospective_value(
        self,
        discount_rate: float | ExpressionProxy | ColumnProxy | None = None,
        discount_factor: ExpressionProxy | ColumnProxy | None = None,
        *,
        timing: Literal["beginning_of_period", "end_of_period"] = "end_of_period",
    ) -> ExpressionProxy:
        """Calculate prospective (present) value of future cashflows from each time t.

        Computes, at each period t, the present value at t of the cashflows from t to
        the end: a discounted reverse cumulative sum. Under the default
        ``end_of_period`` timing every cashflow is discounted a full period,
        PV(t) = v(t) * (CF(t) + PV(t+1)); under ``beginning_of_period`` the period's
        own cashflow is not, PV(t) = CF(t) + v(t) * PV(t+1). It is summed in one
        pass, not stepped, so it can differ from a hand-stepped recursion in the
        last few bits.

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

        A null cashflow period makes that position and every earlier position null.
        A modeller who means nought writes ``af.col.fill_null(0.0)`` before the
        total, and the graph then records that they said so.

        Parameters
        ----------
        discount_rate : float or ExpressionProxy or ColumnProxy, optional
            Per-period discount rate for discounting future cashflows:

            - Scalar float: Constant rate for all periods (e.g., 0.05 for 5%)
            - List column: Per-period rates that may vary over time

            Cannot be specified together with `discount_factor`.
        discount_factor : ExpressionProxy or ColumnProxy, optional
            Pre-computed cumulative discount factors. Use when you have yield
            curve or scenario-specific discount factors already calculated.

            **Convention (timing-dependent):** ``discount_factor[t]`` must
            discount the position-``t`` cashflow *at the instant implied by
            the timing* back to the valuation point:

            - ``timing="end_of_period"``: the position-0 cashflow is paid one
              period out, so ``discount_factor[0]`` already includes one
              period's discounting — ``[v, v*v, v*v*v, ...]``, **not 1.0
              first**.
            - ``timing="beginning_of_period"``: the position-0 cashflow is
              immediate — ``[1.0, v, v*v, ...]``.

            Supplying beginning-anchored factors (leading 1.0) with
            ``end_of_period`` timing shifts every period's discounting by one
            period and leaves the first cashflow undiscounted.

            Cannot be specified together with `discount_rate`.
        timing : {"beginning_of_period", "end_of_period"}, default "end_of_period"
            When cashflows occur within each period, following the Excel PV/annuity
            convention:

            - ``"end_of_period"`` (Excel ``type=0``, ordinary annuity): the cashflow at
              ``t`` is paid at the end of the period, so every cashflow is discounted a
              full period. This is the SMALLER value. Typical for benefits.
            - ``"beginning_of_period"`` (Excel ``type=1``, annuity-due): the cashflow at
              ``t`` is paid at the start of the period, so the first cashflow is
              undiscounted. This is the LARGER value. Typical for premiums.

        Returns
        -------
        ExpressionProxy
            Present value of future cashflows at each projection period

        Raises
        ------
        ValueError
            If both `discount_rate` and `discount_factor` are specified,
            or if neither is specified
        TypeError
            If either operand is a bare string, or is otherwise not one of
            the forms above

        Examples
        --------
        **Death Benefit PV with Constant Discount Rate**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "death_benefit": [[100.0, 100.0, 100.0]],
        }
        af = ActuarialFrame(data)

        # Calculate prospective value at 5% discount rate.
        # Default timing is "end_of_period" (Excel type=0, ordinary annuity):
        # every cashflow is discounted a full period, e.g. at t=0
        # 100/1.05 + 100/1.05^2 + 100/1.05^3 = 272.32.
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
        │ [100.0, 100.0, ... ┆ [272.32, 185.94, 95.24]     │
        └────────────────────┴─────────────────────────────┘
        ```

        **Premium PV with Time-Varying Rates**

        ```python
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

        data = {
            "benefit": [[100.0, 100.0, 100.0]],
            # 5% end-of-period factors: position 0 pays one period out, so the
            # first factor is v = 1/1.05, not 1.0 (see discount_factor docs).
            "v_t": [[0.952381, 0.907029, 0.863838]],
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
        2. Apply reverse -> cumsum -> reverse pattern to get "sum from t to end"
        3. Adjust for timing convention

        NaN cashflows propagate into every affected period's PV — a NaN means
        an upstream defect (e.g. a lookup miss under ``on_missing="nan"``).
        Zero beyond-term periods explicitly with ``when/otherwise``.

        **Replaces Ugly Pattern:**

        This method replaces verbose Polars list manipulation. The old pattern
        required 6+ lines of Polars list operations (reverse, cumsum, reverse),
        while the new API is a single clean method call.

        See Also
        --------
        cumulative_survival : Calculate cumulative survival probabilities
        previous_period : Access prior period values for reserve rollforward

        """
        from gaspatchio._authoring import emit

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

        if timing not in ("beginning_of_period", "end_of_period"):
            msg = (
                f"Invalid timing value: {timing!r}. "
                "Must be 'beginning_of_period' or 'end_of_period'"
            )
            raise ValueError(msg)

        from gaspatchio.column.column_proxy import ColumnProxy
        from gaspatchio.column.expression_proxy import ExpressionProxy

        # A bare string is the one wrong operand that looks right, so it is
        # answered first and in the framework's one voice for it. The value
        # half of that answer differs between the two: a discount RATE may
        # be a constant number, while a FACTOR is one value per period, so
        # the actuary who wrote a number there is pointed at discount_rate=
        # rather than at a number this argument would refuse anyway. Neither
        # takes the date the default phrase would offer -- the type check
        # below refuses one -- so both name what they actually accept.
        refuse_bare_string_operand(
            discount_factor,
            parameter="discount_factor",
            value_hint=(
                "discount_rate=<the rate> instead -- a factor is one value "
                "per period, never a single number"
            ),
        )
        refuse_bare_string_operand(
            discount_rate, parameter="discount_rate", value_hint="a number"
        )

        # Beyond that the two operands are not interchangeable and neither
        # is anything else. A single number where a factor belongs is a rate
        # somebody put in the wrong argument, and accepting it would raise
        # deep inside a list evaluation instead of here. A raw Polars
        # expression is not on the rate's contract either: the framework
        # cannot tell whether it is start- or end-anchored, and guessing is
        # the silent valuation error this method exists to avoid. Both
        # refusals name the type they got, at the line the actuary wrote.
        if discount_factor is not None and not isinstance(
            discount_factor, (ExpressionProxy, ColumnProxy)
        ):
            msg = (
                "discount_factor must be ExpressionProxy or ColumnProxy, "
                f"got {type(discount_factor)}"
            )
            raise TypeError(msg)
        if discount_rate is not None and not isinstance(
            discount_rate, (int, float, ExpressionProxy, ColumnProxy)
        ):
            msg = (
                "discount_rate must be float, ExpressionProxy, or ColumnProxy, "
                f"got {type(discount_rate)}"
            )
            raise TypeError(msg)

        # Which of the two the actuary supplied is part of what the formula
        # MEANS -- a rate is start-anchored and a factor is end-anchored, and
        # the end-of-period adjustment differs accordingly -- so it is stamped
        # on the node rather than re-derived from the operand's type later.
        discount_kind = "rate" if discount_rate is not None else "factor"
        discount = discount_rate if discount_rate is not None else discount_factor

        parent_af = self._get_parent_frame()
        return emit.call(
            "projection.prospective_value",
            (
                _read_as_a_double(self._get_node(), parent_af, opening=False),
                _read_as_a_double(discount, parent_af, opening=False),
            ),
            parent_af,
            (("timing", timing), ("discount_kind", discount_kind)),
        )

    def accumulate(
        self,
        *,
        initial: float | pl.Expr | ExpressionProxy | ColumnProxy,
        multiplier: float | pl.Expr | ExpressionProxy | ColumnProxy,
        addend: float | pl.Expr | ExpressionProxy | ColumnProxy,
        reverse: bool = False,
    ) -> ExpressionProxy:
        """Accumulate values using a linear recurrence, forward or backward.

        Computes ``state[t] = state[t-1] * multiplier[t] + addend[t]`` for each
        time step, returning all intermediate states as a list column. This is
        the core primitive for account value rollforwards and other
        state-dependent actuarial projections where cashflows at time *t*
        depend on accumulated state at *t-1*.

        With ``reverse=True`` the same recurrence runs from each policy's own
        last period back to its first:
        ``state[t] = state[t+1] * multiplier[t] + addend[t]``, where
        ``initial`` is the value after the last period. That is a workbook's
        rollback -- a reserve whose row reads the row below it, ``R[1]C`` --
        written as one line rather than as "reverse, accumulate, reverse
        back". Discounting alone has its own name,
        ``projection.prospective_value``, and so does a suffix sum,
        ``projection.remaining_sum``; this is for any other linear rollback.
        The recurrence is stepped, never divided out, so a zero multiplier is
        an ordinary value in either direction. The direction is on the record:
        the node carries ``reverse`` whichever way it ran.

        The actuary pre-computes the multiplicative and additive components in
        Python, keeping business logic readable, while the Rust kernel handles
        the tight sequential loop per policy. Polars parallelises across
        policies automatically.

        All three operands are column-level, so a bare string is refused
        here as it is everywhere else on a column accessor; see
        `refuse_bare_string_operand` for the rule.

        All three are numbers, read when the formula is assigned. A number or
        a null is read as it is, and a Decimal is read as its value. A
        Boolean, text, a category, a date, a time, a duration and any other
        type is refused there, because the kernel would read what the engine
        stores rather than what the column means -- a date as its count of
        days since 1970-01-01, a category as its code, a flag as 1 or 0. An
        in-force flag used as a mask is written as the amount it stands
        for: ``when(af.in_force).then(1.0).otherwise(0.0)``. A length of time
        is measured into a column first --
        ``af.valuation_date.excel.days(af.issue_date)`` for days, or
        ``af.issue_date.excel.yearfrac(af.valuation_date)`` for years -- and
        text that holds numbers is cast to a number first.

        !!! note "When to use"
            * **Account Value Rollforward:** Accumulate account values where
                premiums, fees, and investment returns interact with the running
                balance each period.
            * **Reserve Accumulation:** Build up statutory or GAAP reserves
                period-by-period using interest and cashflow assumptions.
            * **Universal Life Projections:** Model COI deductions, crediting
                rates, and expense charges that depend on the current account
                value via Picard iteration with ``accumulate()``.
            * **Unit-Linked Fund Projection:** Project fund values forward
                where management charges are deducted as a proportion of the
                current fund value.

            * **Reserve Rollback:** Roll a net premium reserve or a
                discounted value back from the end of each policy's term --
                a backward recursion, ``V[t] = v[t] * V[t+1] + cf[t]`` --
                with ``reverse=True``.
            * **Not a floored rollback:** A backward recursion floored each
                period -- ``MAX(0, v * V[t+1] + cf)``, a reserve zeroized
                when it turns negative -- is not this recurrence: the floor is
                not linear, so ``accumulate`` cannot carry it, and 1.0 has no
                named form for it.

        A null multiplier or a null addend at position ``t`` makes ``s[t]`` and
        every later position null -- under ``reverse=True``, every earlier
        position, because the recurrence then runs toward period zero and
        that is the direction the missing term would have travelled. A
        modeller who means nought writes ``af.col.fill_null(0.0)`` before the
        recurrence, and the graph then records that they said so.

        Parameters
        ----------
        initial : float or pl.Expr or ExpressionProxy or ColumnProxy
            Initial state per policy (e.g., starting account value). A scalar
            column with one value per row, or one number for every policy.
            Broadcasts when length is 1. Under ``reverse=True`` this is the
            value after each policy's last period (e.g., ``0.0`` for a
            reserve that runs off at the end of the term).
        multiplier : float or pl.Expr or ExpressionProxy or ColumnProxy
            Multiplicative growth factor per time step (e.g.,
            ``1 + interest_rate``). A list column with one list per policy,
            or a scalar (number or scalar column) — a scalar broadcasts to
            the ``addend`` list's per-policy lengths.
        addend : float or pl.Expr or ExpressionProxy or ColumnProxy
            Additive flow per time step (e.g., premiums minus charges, grown
            by the interest factor). A list column with one list per policy,
            or a scalar — broadcasts to ``multiplier``'s per-policy lengths.
            When both are lists, inner lengths must match. At least one of
            ``multiplier``/``addend`` must be a list: two scalars leave no
            timeline to broadcast onto, and the growth-free case has a
            closed form (``initial + flow.cum_sum()``).
        reverse : bool, default False
            ``False`` runs the recurrence forward from period zero;
            ``True`` runs it backward from each policy's own last period.
            The value at position ``t`` is still the state at period ``t``
            either way, so the result needs no reversing back.

        Returns
        -------
        ExpressionProxy
            List column of accumulated values at each time step.

        Raises
        ------
        TypeError
            At the call, if an operand is a bare string, or if ``reverse`` is
            not ``True`` or ``False``. When the formula is assigned, if an
            operand resolves to anything but a number, a Boolean, a null or a
            Decimal.
        ValueError
            When the formula is assigned, if ``multiplier`` and ``addend``
            are both scalar.

        Examples
        --------
        **Simple Account Value Rollforward**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "av_init": [1000.0, 2000.0],
            "growth": [[1.01, 1.01, 1.01], [1.02, 1.02, 1.02]],
            "net_flow": [[50.0, 50.0, 50.0], [100.0, 100.0, 100.0]],
        }
        af = ActuarialFrame(data)

        af.av = af.growth.projection.accumulate(
            initial=af.av_init,
            multiplier=af.growth,
            addend=af.net_flow,
        )
        print(af.collect()["av"].to_list())
        # [[1060.0, 1120.6, 1181.8059999999998], [2140.0, 2282.8, 2428.456]]
        ```

        **Scalar Growth Factor**

        A scalar ``multiplier`` broadcasts to the flow's per-policy timeline —
        each policy's list length sets its own repetition count:

        ```python
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame(
            {
                "av_init": [1000.0],
                "net_flow": [[100.0, 100.0, 100.0]],
            }
        )
        af.av = af.net_flow.projection.accumulate(
            initial=af.av_init,
            multiplier=1.5,
            addend=af.net_flow,
        )
        print(af.collect()["av"].to_list())
        # [[1600.0, 2500.0, 3850.0]]
        ```

        **Reserve Rollback From the End of the Term**

        A workbook column whose row reads the row below it,
        ``V[t] = v * V[t+1] + cf[t]``, rolled back from zero after each
        policy's own last period -- the second policy is one period long:

        ```python
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame(
            {
                "cf": [[1.0, 2.0, 3.0], [10.0]],
                "v": [[0.9, 0.9, 0.9], [0.5]],
            }
        )
        af.reserve = af.cf.projection.accumulate(
            initial=0.0,
            multiplier=af.v,
            addend=af.cf,
            reverse=True,
        )
        print(af.collect()["reserve"].to_list())
        # [[5.23, 4.7, 3.0], [10.0]]
        ```

        """
        from gaspatchio._authoring import emit

        # All three are numeric: a date is refused when the formula is
        # assigned (the kernel would read it as its epoch day, a plausible
        # number and a meaningless one), so the remedy names only what the
        # recurrence can actually use.
        refuse_bare_string_operand(initial, parameter="initial", value_hint="a number")
        refuse_bare_string_operand(
            multiplier, parameter="multiplier", value_hint="a number"
        )
        refuse_bare_string_operand(addend, parameter="addend", value_hint="a number")
        # The direction is the calculation, so it is never inferred: a 1, a
        # "yes" or a NumPy flag is refused rather than read as one.
        if not isinstance(reverse, bool):
            msg = (
                "accumulate(reverse=...) takes True or False, and got "
                f"{reverse!r} ({type(reverse).__name__}). reverse=False runs "
                "the recurrence forward from period zero; reverse=True runs it "
                "back from each policy's own last period. Write the one you mean."
            )
            raise TypeError(msg)

        parent_af = self._get_parent_frame()
        return emit.call(
            "projection.accumulate",
            (
                _read_as_a_double(initial, parent_af, opening=True),
                _read_as_a_double(multiplier, parent_af, opening=False),
                _read_as_a_double(addend, parent_af, opening=False),
            ),
            parent_af,
            (("reverse", reverse),),
        )


def _read_as_a_double(
    operand: object, parent_af: ActuarialFrame, *, opening: bool
) -> object:
    """Return one operand of a Float64 period operation with the widening it applies.

    The rule section 11.1.20 states for ``accumulate``, and the one
    ``cumulative_survival``, ``prospective_value`` and a period shift under a
    decimal fill follow too: each runs in doubles, and an integer operand
    handed to one is widened on the record, never silently in the engine.

    The recurrence runs in doubles, and the kernel widens an integer
    operand to one on the way in -- an opening balance read from an
    integer column, a step read from ``af.month``. The record used to
    carry the integer column bare, so the tree said ``projection.accumulate``
    over an ``i64`` where section 11.1.20 states the operation over Float64
    only, and a reader holding the published vocabulary refused the line
    and every calculation downstream of it. The widening is real, so the
    record now states it: an integer operand reaches the tree as
    ``to_float(...)``, the checked widening section 11.1.38 defines, which
    refuses an integer outside ``[-2**53, 2**53]`` rather than rounding it.

    An integer *literal* opening balance (``initial=0``) is recorded as the
    double it opens the recurrence at, the same number in the type the
    section states. A literal step stays as written: the section takes a
    numeric literal there. Anything that is not an integer -- a double, a
    Boolean, a type the lowering refuses -- is handed on unchanged,
    and the lowering says what is wrong with it where it already does.
    """
    from gaspatchio._authoring.emit import call_node
    from gaspatchio._semantic.ir import Lit
    from gaspatchio.frame.lowering.ingress import to_node

    if isinstance(operand, (bool, float, str)) or operand is None:
        return operand
    node = to_node(operand)
    if isinstance(node, Lit):
        value = node.value
        if opening and isinstance(value, int) and not isinstance(value, bool):
            return Lit(float(value))
        return node
    element = _element_type(node, parent_af)
    if element is None or not element.is_integer():
        return node
    return call_node("to_float", (node,))


def _a_run_shifted_under(
    run: OpNode, fill_value: object, parent_af: ActuarialFrame
) -> object:
    """Return the run a period shift moves, widened where its fill makes it a double.

    A shift keeps the run's own type, so a whole-number run shifted under a
    whole-number fill (or none) stays the ``i64`` it is. Under a decimal fill
    -- the ``0.0`` default -- the frame computed the run in doubles without
    a word: a policy count of 2**53 + 1 came back as 2**53, while the record
    still named the column ``list[i64]``. That is the widening ``accumulate``
    states (section 11.1.20), and it is stated the same way here: the run
    reaches the tree as ``to_float(...)``, which refuses a whole number no
    double names exactly rather than rounding it.
    """
    if not isinstance(fill_value, float):
        return run
    return _read_as_a_double(run, parent_af, opening=False)


def _element_type(
    node: OpNode, parent_af: ActuarialFrame
) -> pl.DataType | DataTypeClass | None:
    """Return the type one operand holds per value, or None where it cannot be read.

    None is not a verdict: an operand whose type cannot be resolved here is
    lowered again with the rest of the line, and refused there by name if
    it has to be.
    """
    from gaspatchio.frame.lowering.context import LoweringContext
    from gaspatchio.frame.lowering.polars import lower_polars

    context = LoweringContext(frame=parent_af)
    try:
        dtype = context.dtype_of_expr(lower_polars(node, context))
    except Exception:  # noqa: BLE001 — the line's own lowering names the fault
        return None
    return dtype.inner if isinstance(dtype, pl.List) else dtype


# What the API reference documents from this module.
__all__ = ["ProjectionColumnAccessor"]
