# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars implementation of the Excel-compatible pv function."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from polars.plugins import register_plugin_function

from gaspatchio._internal import __file__ as native_path
from gaspatchio.frame.lowering._polars.expressions import to_polars_expression

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio.typing import IntoExprColumn

LIB = Path(native_path)


def pv(
    rate: IntoExprColumn,
    nper: IntoExprColumn,
    pmt: IntoExprColumn,
    *,
    fv: float | None = None,
    typ: int | None = None,
) -> pl.Expr:
    """Calculate the present value of an investment, similar to Excel's PV.

    Calculates the present value of a loan or investment based on a constant
    interest rate and regular periodic payments. The present value is the total
    amount that a series of future payments is worth now.

    !!! note "When to use"
        * **Reserve Calculations:** Calculate the present value of future benefit
          payments for reserve valuations and liability calculations.
        * **Annuity Pricing:** Determine the present value of annuity payment streams
          for pricing immediate or deferred annuities.
        * **Loan Analysis:** Evaluate the present value of loan repayments for
          asset-liability management and investment decisions.
        * **Capital Budgeting:** Assess the present value of project cash flows for
          capital allocation and ROI analysis.
        * **Policy Valuation:** Calculate policy reserves by discounting expected future
          benefit payments to present value.
        * **Pension Obligations:** Determine the present value of pension benefit
          obligations for funding and accounting purposes.

    Parameters
    ----------
    rate : IntoExprColumn
        Interest rate per period. Can be a scalar, a column, or a list column.
        Must use consistent units with nper (e.g., if nper is in months, rate
        should be monthly rate).
    nper : IntoExprColumn
        Total number of payment periods. Can be a scalar, a column, or a list column.
    pmt : IntoExprColumn
        Payment made each period. Can be a scalar, a column, or a list column.
        Typically includes principal and interest. Negative values represent
        cash outflows (payments), positive values represent cash inflows.
    fv : float, optional
        Future value or cash balance after the last payment. Defaults to 0.0.
    typ : int, optional
        Payment timing: 0 for payments at end of period (default), 1 for
        payments at beginning of period.

    Returns
    -------
    pl.Expr
        A Polars expression containing the present value as Float64 (or List[Float64]
        for list columns). Result is typically negative, representing the cost of
        the investment or loan.

    Examples
    --------
    The kernel handles a zero rate without dividing by zero. The public
    ``ExcelColumnAccessor.pv`` example covers a complete policy frame.

    ```python
    import polars as pl
    from gaspatchio.frame.lowering._excel.pv import pv

    print(pl.select(pv(0.0, 12.0, 100.0)).item())
    ```

    ```text
    -1200.0
    ```
    """
    rate_expr = to_polars_expression(rate)
    nper_expr = to_polars_expression(nper)
    pmt_expr = to_polars_expression(pmt)

    # Always provide Excel defaults to avoid empty kwargs deserialization bug
    kwargs = {
        "fv": float(fv) if fv is not None else 0.0,
        "typ": int(typ) if typ is not None else 0,
    }

    return register_plugin_function(
        args=[rate_expr, nper_expr, pmt_expr],
        plugin_path=LIB,
        function_name="pv",
        is_elementwise=True,
        kwargs=kwargs,
    )
