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
    """Financial operations at the frame level for ActuarialFrame.

    Provides frame-level methods for financial calculations that require
    coordinated operations across multiple columns, particularly for list
    columns in actuarial projections.

    Accessed via `.finance` on an ActuarialFrame instance.

    Methods
    -------
    discount_factor(rate_col, periods_col, output_col, method="spot")
        Calculate discount factors from list columns using native Polars.
        Supports spot and forward discounting without map_elements.
    present_value(cashflow_col, rate_col, period_col)
        Calculate present value of cash flows.

    """

    def __init__(self, frame: ActuarialFrame) -> None:
        """Initialize the accessor with the parent ActuarialFrame.

        Sets up the finance accessor with reference to the parent frame for
        frame-level financial calculations including discount factors and
        present value computations across list columns.

        Parameters
        ----------
        frame : ActuarialFrame
            The parent ActuarialFrame instance to attach this accessor to.

        """
        super().__init__(frame)

    # --- Frame-level finance methods will go here ---
    def discount_factor(
        self,
        rate_col: str,
        periods_col: str,
        output_col: str,
        method: Literal["spot", "forward"] = "spot",
    ) -> ActuarialFrame:
        """Calculate discount factors for projection timelines using list_pow plugin.

        Computes present value discount factors v^t from interest rates across entire
        projection timelines. Uses Rust list_pow plugin for optimal performance -
        eliminates EXPLODE/GROUP_BY pattern for 10x+ speedup on list columns.

        !!! note "When to use"
            * **Reserve Calculations:** Discount future benefit payments and expenses
                to present value for statutory reserves, GAAP liabilities, or
                embedded value calculations.
            * **Cash Flow Projections:** Calculate present values of projected
                premiums, claims, and expenses in profit testing models for
                product pricing and profitability analysis.
            * **Guaranteed Benefits:** Discount guaranteed minimum death benefits
                (GMDB), withdrawal benefits (GMWB), or income benefits (GMIB) in
                variable annuity and equity-indexed product valuations.
            * **Economic Scenario Testing:** Apply forward rate curves from economic
                scenario generators for stochastic reserve calculations and risk
                capital models.

        Parameters
        ----------
        rate_col : str
            Name of column containing interest rates (as lists).
            Typically monthly rates for projection periods.
        periods_col : str
            Name of column containing time periods (as lists).
            Must align element-wise with rate_col.
        output_col : str
            Name for the new column containing discount factors.
        method : {"spot", "forward"}, default "spot"
            Discount method:

            - "spot": v[t] = (1 + r)^(-t) - Same rate for all periods
            - "forward": v[t] = ∏(1 + r[i])^(-1) for i < t - Period-varying rates

        Returns
        -------
        ActuarialFrame
            New frame with discount factor column added.

        Examples
        --------
        **Spot Discounting: Constant Rate**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": [1, 2],
            "monthly_rate": [[0.004, 0.004, 0.004], [0.003, 0.003]],
            "month": [[0, 1, 2], [0, 1]],
        }
        af = ActuarialFrame(data)

        af = af.finance.discount_factor(
            rate_col="monthly_rate",
            periods_col="month",
            output_col="disc_factors",
            method="spot",
        )

        print(af.collect())
        ```

        ```text
        shape: (2, 4)
        ┌───────────┬───────────────────────┬───────────┬───────────────────────────┐
        │ policy_id ┆ monthly_rate          ┆ month     ┆ disc_factors              │
        │ ---       ┆ ---                   ┆ ---       ┆ ---                       │
        │ i64       ┆ list[f64]             ┆ list[i64] ┆ list[f64]                 │
        ╞═══════════╪═══════════════════════╪═══════════╪═══════════════════════════╡
        │ 1         ┆ [0.004, 0.004, 0.004] ┆ [0, 1, 2] ┆ [1.0, 0.996016, 0.992048] │
        │ 2         ┆ [0.003, 0.003]        ┆ [0, 1]    ┆ [1.0, 0.997009]           │
        └───────────┴───────────────────────┴───────────┴───────────────────────────┘
        ```

        **Forward Discounting: Varying Rates**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": [1],
            "forward_rates": [[0.003, 0.004, 0.005]],
            "month": [[0, 1, 2]],
        }
        af = ActuarialFrame(data)

        af = af.finance.discount_factor(
            rate_col="forward_rates",
            periods_col="month",
            output_col="disc_factors",
            method="forward",
        )

        print(af.collect())
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬───────────────────────┬───────────┬───────────────────────────┐
        │ policy_id ┆ forward_rates         ┆ month     ┆ disc_factors              │
        │ ---       ┆ ---                   ┆ ---       ┆ ---                       │
        │ i64       ┆ list[f64]             ┆ list[i64] ┆ list[f64]                 │
        ╞═══════════╪═══════════════════════╪═══════════╪═══════════════════════════╡
        │ 1         ┆ [0.003, 0.004, 0.005] ┆ [0, 1, 2] ┆ [1.0, 0.997009, 0.993037] │
        └───────────┴───────────────────────┴───────────┴───────────────────────────┘
        ```

        See Also
        --------
        to_monthly : Convert annual rates to monthly rates

        """
        from gaspatchio_core.functions.vector import list_pow

        if method == "spot":
            # Prepare inputs using native Polars (fast SIMD operations)
            rate_plus_one = pl.col(rate_col) + 1.0
            period_neg = pl.col(periods_col) * -1.0

            # Use Rust plugin for (1 + rate) ** (-period)
            # This eliminates EXPLODE/GROUP_BY pattern
            discount_expr = list_pow(rate_plus_one, period_neg).alias(output_col)

            result = self._frame._df.with_columns([discount_expr])  # noqa: SLF001
            from gaspatchio_core.frame.base import ActuarialFrame

            return ActuarialFrame(result)

        if method == "forward":
            # Forward method: 1 / (1 + rate), then cumulative product
            rate_plus_one = pl.col(rate_col) + 1.0
            reciprocal = list_pow(rate_plus_one, pl.lit(-1.0))

            # Cumulative product for forward discounting
            result = self._frame._df.with_columns(  # noqa: SLF001
                [
                    pl.concat_list([pl.lit([1.0]), reciprocal])
                    .list.eval(pl.element().cum_prod())
                    .list.head(pl.col(rate_col).list.len())
                    .alias(output_col)
                ]
            )
            from gaspatchio_core.frame.base import ActuarialFrame

            return ActuarialFrame(result)

        msg = f"method must be 'spot' or 'forward', got '{method}'"
        raise ValueError(msg)

    def present_value(
        self,
        cashflow_col: IntoExprColumn,
        rate_col: IntoExprColumn,
        period_col: IntoExprColumn,
    ) -> ExpressionProxy:
        """Calculate the present value of cash flows.

        Computes present value using the formula ``PV = CF / (1 + rate)^period``,
        assuming cash flows occur at the end of each period. Essential for
        discounting future cash flows in pricing, reserving, and valuation.

        !!! note "When to use"
            * **Reserve Calculations:** Discount future benefit payments and
                expenses to calculate policy reserves under various standards.
            * **Product Pricing:** Calculate present value of expected premiums
                and claims to determine pricing margins and profitability.
            * **Embedded Value:** Discount projected profits for embedded value
                and value of in-force business calculations.
            * **Cash Flow Testing:** Present value cash flows for asset adequacy
                testing and scenario analysis.

        Parameters
        ----------
        cashflow_col : IntoExprColumn
            Column containing the cash flow amounts to discount.
        rate_col : IntoExprColumn
            Column with discount rate per period (e.g., 0.05 for 5% annual).
        period_col : IntoExprColumn
            Column with period number (1, 2, 3...). Must be >= 1.

        Returns
        -------
        ExpressionProxy
            Present value of each cash flow discounted to time zero.

        Examples
        --------
        **Scalar Example: Discount policy cash flows**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "cashflow": [1000.0, 2000.0],
            "rate": [0.05, 0.04],
            "period": [1, 2],
        }
        af = ActuarialFrame(data)

        af.pv = af.finance.present_value(af.cashflow, af.rate, af.period)

        print(af.collect())
        ```

        ```text
        shape: (2, 5)
        ┌───────────┬──────────┬──────┬────────┬─────────────┐
        │ policy_id ┆ cashflow ┆ rate ┆ period ┆ pv          │
        │ ---       ┆ ---      ┆ ---  ┆ ---    ┆ ---         │
        │ str       ┆ f64      ┆ f64  ┆ i64    ┆ f64         │
        ╞═══════════╪══════════╪══════╪════════╪═════════════╡
        │ P001      ┆ 1000.0   ┆ 0.05 ┆ 1      ┆ 952.380952  │
        │ P002      ┆ 2000.0   ┆ 0.04 ┆ 2      ┆ 1849.112426 │
        └───────────┴──────────┴──────┴────────┴─────────────┘
        ```

        See Also
        --------
        discount_factor : Calculate discount factors for projection timelines

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
    """Financial mathematics and valuation operations.

    Provides methods for rate conversion and present value computations
    on columns or expressions.

    Accessed via `.finance` on an ActuarialFrame column or expression proxy,
    e.g., `af["annual_rate"].finance.to_monthly()`.

    Methods
    -------
    to_monthly(method="compound")
        Convert annual interest rates to monthly rates
    discount(rate_expr, n_periods_expr)
        Discount values using specified rate and periods

    Notes
    -----
    For discount factor calculations on list columns, use the frame-level
    accessor: ``af.finance.discount_factor(rate_col, periods_col, output_col)``

    """

    def __init__(self, proxy: ColumnProxy | ExpressionProxy) -> None:
        """Initialize the accessor with the parent column or expression proxy.

        Sets up the finance column accessor with reference to the parent proxy
        for column-level financial calculations including rate conversions and
        discounting operations.

        Parameters
        ----------
        proxy : ColumnProxy | ExpressionProxy
            The parent column or expression proxy to attach this accessor to.

        """
        super().__init__(proxy)
        # Refine type hint for clarity
        self._proxy: ColumnProxy | ExpressionProxy = proxy

    def _get_polars_expr(self) -> pl.Expr:
        """Get the underlying Polars expression from the proxy.

        Extracts the raw Polars expression from either a ColumnProxy or
        ExpressionProxy, enabling the accessor methods to build expressions
        on top of the underlying column data.

        Returns
        -------
        pl.Expr
            The underlying Polars expression for the column or expression.

        Raises
        ------
        TypeError
            If the proxy is neither ColumnProxy nor ExpressionProxy.

        """
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
        using either compound or simple interest conventions. Essential for
        actuarial projections with monthly timesteps when assumptions are
        provided annually.

        For list columns, applies conversion element-wise within each list.
        For scalar columns, applies conversion to each row value.

        !!! note "When to use"
            * **Monthly Projections:** Convert annual discount rates, investment
                returns, or interest crediting rates to monthly equivalents for
                cash flow models with monthly timesteps.
            * **Pricing Models:** Transform annual pricing assumptions to monthly
                rates for variable annuity, universal life, or investment-linked
                product models.
            * **Reserve Calculations:** Convert annual reserve discount rates to
                monthly for mid-month or monthly reserve valuations.
            * **Policy Loans:** Calculate monthly interest accrual on policy loans
                when loan terms specify annual interest rates.

        Parameters
        ----------
        method : {"compound", "simple"}, default "compound"
            Conversion method:
            - "compound": (1 + r_annual)^(1/12) - 1 (standard actuarial practice)
            - "simple": r_annual / 12 (linear approximation)

        Returns
        -------
        ExpressionProxy
            Monthly interest rate with same structure as input (scalar or list)

        Examples
        --------
        **Scalar Example: Convert annual discount rates**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"annual_rate": [0.05, 0.06, 0.04]}
        af = ActuarialFrame(data)

        af.monthly_rate = af.annual_rate.finance.to_monthly()

        print(af.collect())
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬──────────────┐
        │ annual_rate ┆ monthly_rate │
        │ ---         ┆ ---          │
        │ f64         ┆ f64          │
        ╞═════════════╪══════════════╡
        │ 0.05        ┆ 0.004074     │
        │ 0.06        ┆ 0.004868     │
        │ 0.04        ┆ 0.003274     │
        └─────────────┴──────────────┘
        ```

        **Scalar Example: Simple conversion for approximation**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"annual_rate": [0.05, 0.06, 0.04]}
        af = ActuarialFrame(data)

        af.monthly_rate = af.annual_rate.finance.to_monthly(method="simple")

        print(af.collect())
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬──────────────┐
        │ annual_rate ┆ monthly_rate │
        │ ---         ┆ ---          │
        │ f64         ┆ f64          │
        ╞═════════════╪══════════════╡
        │ 0.05        ┆ 0.004167     │
        │ 0.06        ┆ 0.005        │
        │ 0.04        ┆ 0.003333     │
        └─────────────┴──────────────┘
        ```

        **Vector Example: Projection timeline with varying rates**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"annual_rates": [[0.05, 0.05, 0.06, 0.06]]}
        af = ActuarialFrame(data)

        af.monthly_rates = af.annual_rates.finance.to_monthly()

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌──────────────────────┬─────────────────────────────────┐
        │ annual_rates         ┆ monthly_rates                   │
        │ ---                  ┆ ---                             │
        │ list[f64]            ┆ list[f64]                       │
        ╞══════════════════════╪═════════════════════════════════╡
        │ [0.05, 0.05, … 0.06] ┆ [0.004074, 0.004074, … 0.00486… │
        └──────────────────────┴─────────────────────────────────┘
        ```

        Notes
        -----
        - Compound method is standard actuarial practice (maintains equivalence)
        - Simple method provides linear approximation (less accurate but faster)
        - For list columns, conversion is applied to each element
        - Formula: Compound = (1 + r_annual)^(1/12) - 1, Simple = r_annual / 12

        See Also
        --------
        discount_factor : Calculate discount factors from interest rates

        """
        # Import ColumnTypeDetector using getattr to avoid type-checking issues
        import gaspatchio_core.column.dispatch as dispatch_module
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        parent_frame = self._proxy._parent  # noqa: SLF001

        if parent_frame is None:
            msg = (
                "to_monthly() requires the expression to be part of an "
                "ActuarialFrame context."
            )
            raise RuntimeError(msg)

        # Detect if this is a list column
        # Use getattr since ColumnTypeDetector is not in dispatch.__all__
        ColumnTypeDetector = dispatch_module.ColumnTypeDetector  # type: ignore[attr-defined]  # noqa: N806
        detector = ColumnTypeDetector(parent_frame)
        is_list = False

        if isinstance(self._proxy, ColumnProxy):
            is_list = detector.is_list_column(self._proxy.name)

        # Build the conversion expression
        if method == "compound":
            if is_list:
                # For list columns: apply element-wise using list.eval
                monthly_expr = base_expr.list.eval(((1 + pl.element()).pow(1 / 12)) - 1)
            else:
                # For scalar columns: direct expression
                monthly_expr = ((1 + base_expr).pow(1 / 12)) - 1
        elif method == "simple":
            if is_list:
                # For list columns: apply element-wise using list.eval
                monthly_expr = base_expr.list.eval(pl.element() / 12)
            else:
                # For scalar columns: direct expression
                monthly_expr = base_expr / 12
        else:
            msg = f"method must be 'compound' or 'simple', got '{method}'"
            raise ValueError(msg)

        return ExpressionProxy(monthly_expr, parent_frame)

    def compound(
        self,
        rate: float,
        periods_per_year: int,
    ) -> ExpressionProxy:
        """Calculate compound growth factor for periods.

        Computes growth factors using the formula
        ``(1 + rate)^(period / periods_per_year)``.
        Commonly used for inflation adjustments, investment growth, or other
        compound growth calculations in actuarial projections.

        !!! note "When to use"
            * **Inflation Adjustments:** Calculate inflation factors for expenses,
                benefits, or premiums that grow with inflation over projection periods.
            * **Investment Growth:** Model accumulation of funds under compound
                interest assumptions.
            * **Benefit Increases:** Calculate growth factors for benefits that
                increase at a fixed compound rate.

        Parameters
        ----------
        rate : float
            Annual growth rate (e.g., 0.01 for 1% annual growth)
        periods_per_year : int
            Number of periods per year (e.g., 12 for monthly, 4 for quarterly)

        Returns
        -------
        ExpressionProxy
            Growth factors with same structure as input column (scalar or list)

        Examples
        --------
        **List column example: Monthly inflation factors**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"month": [[0, 1, 6, 12]]}
        af = ActuarialFrame(data)

        af.inflation_factor = af.month.finance.compound(rate=0.01, periods_per_year=12)

        print(af.collect())
        ```

        **Scalar column example: Quarterly growth**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"quarter": [0, 1, 4]}
        af = ActuarialFrame(data)

        af.growth_factor = af.quarter.finance.compound(rate=0.02, periods_per_year=4)

        print(af.collect())
        ```

        See Also
        --------
        to_monthly : Convert annual rates to monthly rates
        discount_factor : Calculate discount factors from interest rates

        """
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        parent_frame = self._proxy._parent  # noqa: SLF001

        if parent_frame is None:
            msg = (
                "compound() requires the expression to be part of an "
                "ActuarialFrame context."
            )
            raise RuntimeError(msg)

        # Detect if this is a list column
        import gaspatchio_core.column.dispatch as dispatch_module

        ColumnTypeDetector = dispatch_module.ColumnTypeDetector  # type: ignore[attr-defined]  # noqa: N806
        detector = ColumnTypeDetector(parent_frame)
        is_list = False

        if isinstance(self._proxy, ColumnProxy):
            is_list = detector.is_list_column(self._proxy.name)

        # Build the compound growth expression: (1 + rate)^(period / periods_per_year)
        if is_list:
            # For list columns: apply element-wise using list.eval
            compound_expr = base_expr.list.eval(
                (1 + rate) ** (pl.element() / periods_per_year)
            )
        else:
            # For scalar columns: direct expression
            compound_expr = pl.lit(1 + rate) ** (base_expr / periods_per_year)

        return ExpressionProxy(compound_expr, parent_frame)

    def discount(
        self, rate_expr: IntoExprColumn, n_periods_expr: IntoExprColumn
    ) -> ExpressionProxy:
        """Discount the value in the current column/expression.

        Computes discounted values using the formula
        ``Discounted Value = Value / (1 + rate)^n_periods``. Useful for
        converting future values to present values with flexible rate and
        period inputs from other columns or expressions.

        !!! note "When to use"
            * **Future Value Discounting:** Convert guaranteed maturity
                values, surrender values, or death benefits to present value.
            * **Reserve Calculations:** Discount projected liabilities back
                to valuation date for statutory or GAAP reserves.
            * **Profit Testing:** Calculate present value of future profits
                in pricing models and profitability analysis.
            * **Investment Returns:** Discount expected investment income or
                fund values in unit-linked or variable product models.

        Parameters
        ----------
        rate_expr : IntoExprColumn
            The discount rate per period (e.g., 0.05 for 5% annual).
            Can be a scalar, column reference, or expression.
        n_periods_expr : IntoExprColumn
            The number of periods to discount over. Can be a scalar,
            column reference, or expression.

        Returns
        -------
        ExpressionProxy
            Discounted values with same structure as input column.

        Examples
        --------
        **Scalar Example: Discount future values**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "future_value": [1050.0, 2080.0],
            "rate": [0.05, 0.04],
            "periods": [1, 2],
        }
        af = ActuarialFrame(data)

        af.present_value = af.future_value.finance.discount(af.rate, af.periods)

        print(af.collect())
        ```

        ```text
        shape: (2, 5)
        ┌───────────┬──────────────┬──────┬─────────┬───────────────┐
        │ policy_id ┆ future_value ┆ rate ┆ periods ┆ present_value │
        │ ---       ┆ ---          ┆ ---  ┆ ---     ┆ ---           │
        │ str       ┆ f64          ┆ f64  ┆ i64     ┆ f64           │
        ╞═══════════╪══════════════╪══════╪═════════╪═══════════════╡
        │ P001      ┆ 1050.0       ┆ 0.05 ┆ 1       ┆ 1000.0        │
        │ P002      ┆ 2080.0       ┆ 0.04 ┆ 2       ┆ 1923.076923   │
        └───────────┴──────────────┴──────┴─────────┴───────────────┘
        ```

        See Also
        --------
        present_value : Calculate present value of cash flows at frame level
        discount_factor : Calculate discount factors for projection timelines

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
