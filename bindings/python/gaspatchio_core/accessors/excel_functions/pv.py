from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

from gaspatchio_core import _internal
from gaspatchio_core.functions.utils import to_polars_expression

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn

LIB = Path(_internal.__file__)


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
        * **Reserve Calculations:** Calculate the present value of future benefit payments for reserve valuations and liability calculations.
        * **Annuity Pricing:** Determine the present value of annuity payment streams for pricing immediate or deferred annuities.
        * **Loan Analysis:** Evaluate the present value of loan repayments for asset-liability management and investment decisions.
        * **Capital Budgeting:** Assess the present value of project cash flows for capital allocation and ROI analysis.
        * **Policy Valuation:** Calculate policy reserves by discounting expected future benefit payments to present value.
        * **Pension Obligations:** Determine the present value of pension benefit obligations for funding and accounting purposes.

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
    **Scalar Example: Annuity Present Value**

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {
        "policy_id": ["POL001", "POL002", "POL003"],
        "interest_rate": [0.05, 0.04, 0.06],
        "num_periods": [10.0, 15.0, 20.0],
        "payment": [1000.0, 1500.0, 2000.0],
    }
    af = ActuarialFrame(data)

    af.present_value = af.interest_rate.excel.pv(nper=af.num_periods, pmt=af.payment)

    print(af.collect())
    ```

    ```text
    shape: (3, 5)
    ┌───────────┬───────────────┬─────────────┬─────────┬───────────────┐
    │ policy_id ┆ interest_rate ┆ num_periods ┆ payment ┆ present_value │
    │ ---       ┆ ---           ┆ ---         ┆ ---     ┆ ---           │
    │ str       ┆ f64           ┆ f64         ┆ f64     ┆ f64           │
    ╞═══════════╪═══════════════╪═════════════╪═════════╪═══════════════╡
    │ POL001    ┆ 0.05          ┆ 10.0        ┆ 1000.0  ┆ -7721.734929  │
    │ POL002    ┆ 0.04          ┆ 15.0        ┆ 1500.0  ┆ -16677.581148 │
    │ POL003    ┆ 0.06          ┆ 20.0        ┆ 2000.0  ┆ -22939.842437 │
    └───────────┴───────────────┴─────────────┴─────────┴───────────────┘
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





