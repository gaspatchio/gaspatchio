# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Accessors for finance-related operations on ActuarialFrame objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from gaspatchio._authoring import emit
from gaspatchio._semantic.ir import Col
from gaspatchio.accessors.base import (
    BaseColumnAccessor,
    BaseFrameAccessor,
    column_expr,
    column_node,
    refuse_bare_string_operand,
)
from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
from gaspatchio.frame.lowering.context import context_for
from gaspatchio.frame.lowering.polars import lower_polars
from gaspatchio.frame.registry import register_accessor

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio._semantic.ir import AttrValue
    from gaspatchio.frame.base import ActuarialFrame


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

    Notes
    -----
    ``finance`` is a reserved attribute on the frame, as ``date``, ``excel``,
    ``graph`` and ``projection`` are. A model whose data really does carry a
    column called ``finance`` still has it -- reach it as ``af["finance"]``
    -- but ``af.finance`` is always this accessor.

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
            Typically monthly rates for projection periods. A **string is
            the name of a column on this frame** (refused if the frame does
            not carry it).
        periods_col : str
            Name of column containing time periods (as lists).
            Must align element-wise with rate_col, and is named the same way.
        output_col : str
            Name for the new column containing discount factors. This one
            names the column being written, so it is the caller's to choose;
            a name the frame already carries is overwritten.
        method : {"spot", "forward"}, default "spot"
            Discount method:

            - "spot": v[t] = (1 + r)^(-t) - Same rate for all periods
            - "forward": v[t] = ∏(1 + r[i])^(-1) for i < t - Period-varying rates

        Returns
        -------
        ActuarialFrame
            New frame with discount factor column added.

        Raises
        ------
        pl.exceptions.ColumnNotFoundError
            If ``rate_col`` or ``periods_col`` is not a column on this frame.

        Examples
        --------
        **Spot Discounting: Constant Rate**

        ```python
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        # Frame level, so a string is a column NAME, checked against the
        # frame -- the rule `column_expr` states, and the one `present_value`
        # below already reads by. The refusal is what is wanted from it here:
        # the two names go into the op-tree as `Col`s rather than as the
        # expressions it hands back. Left unchecked, a typo comes back from
        # the engine as a resolved query plan naming neither the parameter
        # that carried it nor, unless the engine's own matcher finds one, the
        # column that was meant.
        column_expr(self._frame, rate_col, parameter="rate_col")
        column_expr(self._frame, periods_col, parameter="periods_col")

        if method not in ("spot", "forward"):
            msg = f"method must be 'spot' or 'forward', got '{method}'"
            raise ValueError(msg)

        node = emit.call_node(
            "finance.discount_factor",
            (Col(rate_col), Col(periods_col)),
            (("method", method),),
        )
        discount_expr = lower_polars(node, context_for(self._frame)).alias(output_col)
        # Added to the frame the caller already holds, through the frame's own
        # recorded door. Building a bare `ActuarialFrame(result)` here dropped
        # everything the frame knew -- its calculation log, its projection
        # axis, its mode -- so a discount factor erased the history of the
        # rates it discounts. `with_columns` mutates in place and records,
        # and the expression is wrapped so the record keeps this operation's
        # own identity instead of reading as an opaque engine expression.
        return self._frame.with_columns(
            ProxyAwareExpr.wrap(discount_expr, node=node, parent=self._frame)
        )

    def present_value(
        self,
        cashflow_col: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
        rate_col: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
        period_col: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
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
        cashflow_col : str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series
            The cash flow amounts to discount. A **string is the name of a
            column on this frame** (refused if the frame does not carry it);
            a column or expression is used as given.
        rate_col : str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series
            Discount rate per period (e.g., 0.05 for 5% annual), named the
            same two ways.
        period_col : str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series
            Period number (1, 2, 3...), named the same two ways. Must be >= 1.
            Each of the three is one value per policy (spec section 11.1.29);
            one held per period is refused by name -- a per-period valuation
            is ``.projection.prospective_value()``.

        Returns
        -------
        ExpressionProxy
            Present value of each cash flow discounted to time zero.

        Raises
        ------
        pl.exceptions.ColumnNotFoundError
            If any of the three names is not a column on this frame.

        Examples
        --------
        **Naming the three columns by string**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "cashflow": [1000.0, 2000.0],
            "rate": [0.05, 0.04],
            "period": [1, 2],
        }
        af = ActuarialFrame(data)

        af.pv = af.finance.present_value("cashflow", "rate", "period")

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

        **Scalar Example: Discount policy cash flows**

        ```python
        from gaspatchio import ActuarialFrame

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
        # Frame level, so a string is a column NAME, checked against the
        # frame -- the same rule `discount_factor` next door already reads
        # by. Left to the generic ingress a name becomes the literal text,
        # and `CF / (1 + rate) ** period` fails at collect with a Polars
        # error about String arithmetic, pages from the line that wrote it.
        # Each operand resolves to the node this call's own tree records
        # for it: a name to the column REFERENCE it is. `finance.
        # present_value` is an operation the format's vocabulary names, and
        # lowering the three names to the engine's own rendering first put
        # three engine fragments inside its tree, so a discounted cashflow
        # -- a closed form over three values standing at one period --
        # exported as an escape into Polars.
        return emit.call(
            "finance.present_value",
            (
                column_node(self._frame, cashflow_col, parameter="cashflow_col"),
                column_node(self._frame, rate_col, parameter="rate_col"),
                column_node(self._frame, period_col, parameter="period_col"),
            ),
            self._frame,
        )


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

    **A bare string operand is refused here: write the operand as
    ``af.column`` or ``af["column"]``.** That rule holds on every column
    accessor, and is stated once in
    ``gaspatchio.accessors.base.refuse_bare_string_operand`` -- along with
    the frame-level methods, ``af.finance.present_value`` and
    ``af.finance.discount_factor`` among them, that *do* name a column by
    string.

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

    def _emit(
        self,
        name: str,
        extra_args: tuple[object, ...] = (),
        attrs: tuple[tuple[str, AttrValue], ...] = (),
    ) -> ExpressionProxy:
        """Emit a finance ``Call`` over this accessor's own column.

        The accessor's job ends at recording what was asked for; the
        registered lowering in ``frame/lowering/rules/finance.py`` owns
        how it is computed. Every method below is one call into here.
        """
        if not isinstance(self._proxy, (ColumnProxy, ExpressionProxy)):
            msg = (
                f"FinanceColumnAccessor expected ColumnProxy or "
                f"ExpressionProxy, got {type(self._proxy).__name__}"
            )
            raise TypeError(msg)
        parent_frame = self._proxy._parent  # noqa: SLF001
        if parent_frame is None:
            msg = (
                f"{name.rsplit('.', maxsplit=1)[-1]}() requires the expression "
                "to be part of an ActuarialFrame context."
            )
            raise RuntimeError(msg)
        node_args = (self._proxy._node, *extra_args)  # noqa: SLF001
        return emit.call(name, node_args, parent_frame, attrs)

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        from gaspatchio import ActuarialFrame

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
        if method not in ("compound", "simple"):
            msg = f"method must be 'compound' or 'simple', got '{method}'"
            raise ValueError(msg)
        return self._emit("finance.to_monthly", attrs=(("method", method),))

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
        from gaspatchio import ActuarialFrame

        data = {"month": [[0, 1, 6, 12]]}
        af = ActuarialFrame(data)

        af.inflation_factor = af.month.finance.compound(rate=0.01, periods_per_year=12)

        print(af.collect())
        ```

        **Scalar column example: Quarterly growth**

        ```python
        from gaspatchio import ActuarialFrame

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
        return self._emit(
            "finance.compound",
            attrs=(("rate", rate), ("periods_per_year", periods_per_year)),
        )

    def discount(
        self,
        rate_expr: ColumnProxy | ExpressionProxy | pl.Expr | float,
        n_periods_expr: ColumnProxy | ExpressionProxy | pl.Expr | float,
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
        rate_expr : ColumnProxy | ExpressionProxy | pl.Expr | float
            The discount rate per period (e.g., 0.05 for 5% annual).
            Can be a number, column reference, or expression. A bare
            string is refused — pass ``af["rate"]`` for the column.
        n_periods_expr : ColumnProxy | ExpressionProxy | pl.Expr | float
            The number of periods to discount over. Can be a number,
            column reference, or expression. A bare string is refused —
            pass ``af["periods"]`` for the column.

        Returns
        -------
        ExpressionProxy
            One discounted value per policy. Every operand is one value per
            policy (spec section 11.1.29); one held per period is refused by
            name -- a per-period valuation is
            ``.projection.prospective_value()``.

        Examples
        --------
        **Scalar Example: Discount future values**

        ```python
        from gaspatchio import ActuarialFrame

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
        refuse_bare_string_operand(rate_expr, parameter="rate_expr")
        refuse_bare_string_operand(n_periods_expr, parameter="n_periods_expr")
        return self._emit("finance.discount", (rate_expr, n_periods_expr))


# What the API reference documents from this module.
__all__ = ["FinanceColumnAccessor", "FinanceFrameAccessor"]
