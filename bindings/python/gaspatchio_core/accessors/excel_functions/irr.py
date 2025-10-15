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


def irr(
    values: IntoExprColumn,
    guess: IntoExprColumn | None = None,
    *,
    default_guess: float | None = None,
) -> pl.Expr:
    """Calculate the internal rate of return, similar to Excel's IRR.

    Returns the internal rate of return for a series of periodic cash flows.
    The IRR is the discount rate that makes the net present value (NPV) of all
    cash flows equal to zero, calculated using Excel's iterative algorithm.

    !!! note "When to use"
        * **Investment Analysis:** Evaluate the profitability of investment portfolios or individual securities.
        * **Project Evaluation:** Compare the returns of different actuarial projects or capital investments.
        * **Premium Adequacy:** Assess whether premium cash flows generate sufficient returns relative to benefit payments.
        * **Asset-Liability Matching:** Evaluate the performance of matched asset and liability cash flows.
        * **Product Pricing:** Determine target profit margins for insurance products based on cash flow patterns.
        * **Regulatory Reporting:** Calculate internal rates of return for regulatory financial analysis.

    Parameters
    ----------
    values : IntoExprColumn
        A list column containing cash flows where each row represents a series
        of periodic cash flows. Must contain at least one positive and one negative
        value. Cash flows are assumed to occur at regular intervals.
    guess : IntoExprColumn, optional
        Optional per-row initial guess for the IRR calculation. If not provided,
        uses default_guess.
    default_guess : float, optional
        Scalar fallback guess when `guess` is not provided. Defaults to 0.1 (10%).

    Returns
    -------
    pl.Expr
        A Polars expression containing the internal rate of return as Float64
        for each row.

    Examples
    --------
    **Scalar Example: Investment Portfolio IRR**

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {
        "investment_id": ["INV001", "INV002", "INV003"],
        "cash_flows": [
            [-1000.0, 300.0, 400.0, 500.0],
            [-5000.0, 1000.0, 2000.0, 3500.0],
            [-2000.0, 500.0, 600.0, 800.0, 900.0]
        ]
    }
    af = ActuarialFrame(data)

    af.irr = af.cash_flows.excel.irr()

    print(af.collect())
    ```

    ```text
    shape: (3, 3)
    ┌───────────────┬─────────────────────────────┬──────────┐
    │ investment_id ┆ cash_flows                  ┆ irr      │
    │ ---           ┆ ---                         ┆ ---      │
    │ str           ┆ list[f64]                   ┆ f64      │
    ╞═══════════════╪═════════════════════════════╪══════════╡
    │ INV001        ┆ [-1000.0, 300.0, … 500.0]   ┆ 0.088963 │
    │ INV002        ┆ [-5000.0, 1000.0, … 3500.0] ┆ 0.117921 │
    │ INV003        ┆ [-2000.0, 500.0, … 900.0]   ┆ 0.134072 │
    └───────────────┴─────────────────────────────┴──────────┘
    ```
    """
    values_expr = to_polars_expression(values)
    args = [values_expr]
    if guess is not None:
        args.append(to_polars_expression(guess))

    kwargs: dict[str, float] = {}
    if default_guess is None:
        # Provide Rust's default explicitly so plugin kwargs parsing always has content
        kwargs["guess"] = 0.1
    else:
        kwargs["guess"] = float(default_guess)

    return register_plugin_function(
        args=args,
        plugin_path=LIB,
        function_name="irr",
        is_elementwise=True,
        kwargs=kwargs,
    )
