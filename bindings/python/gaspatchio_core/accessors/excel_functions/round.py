# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio_core.functions.utils import to_polars_expression

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn


def round(number: IntoExprColumn, num_digits: int = 0) -> pl.Expr:  # noqa: A001
    """Round half away from zero, exactly like Excel's ROUND.

    Excel's ROUND sends a tie away from zero: ``ROUND(0.125, 2)`` is ``0.13``
    and ``ROUND(-0.125, 2)`` is ``-0.13``. Polars' native ``.round()`` uses
    banker's rounding (half to even), which sends the same tie to ``0.12`` —
    a difference that compounds when rounding happens inside a recursion,
    which is why a workbook conversion must use the workbook's rule.

    !!! note "When to use"
        * **Workbook Conversion:** Reproduce a spreadsheet's rounding exactly —
            premiums, charges, and cashflows a workbook rounds to cents.
        * **Regulatory Reporting:** Match report figures rounded under the
            away-from-zero convention most published tables use.
        * **Reconciliation:** Eliminate half-cent mismatches that are rounding
            convention, not model error, before investigating real differences.

    Parameters
    ----------
    number : IntoExprColumn
        The value to round: a column name, expression, or proxy. Scalar
        (per-policy) columns round directly; for per-period list columns use
        the ``.excel.round()`` accessor, which applies the rule element-wise.
    num_digits : int
        Digits after the decimal point, as in Excel: ``2`` rounds to cents,
        ``0`` to whole units, and a negative value rounds to the left of the
        decimal point (``-2`` rounds to hundreds). Defaults to 0.

    Returns
    -------
    pl.Expr
        Float64 expression with each value rounded half away from zero.

    Examples
    --------
    **Scalar Example: The tie that separates the conventions**

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {"charge": [0.125, -0.125, 7558.485]}
    af = ActuarialFrame(data)

    af.rounded = af.charge.excel.round(2)

    print(af.collect())
    ```

    ```text
    shape: (3, 2)
    ┌──────────┬─────────┐
    │ charge   ┆ rounded │
    │ ---      ┆ ---     │
    │ f64      ┆ f64     │
    ╞══════════╪═════════╡
    │ 0.125    ┆ 0.13    │
    │ -0.125   ┆ -0.13   │
    │ 7558.485 ┆ 7558.49 │
    └──────────┴─────────┘
    ```

    **Negative digits: rounding to hundreds**

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {"face": [1250.0, 1249.0]}
    af = ActuarialFrame(data)

    af.banded = af.face.excel.round(-2)

    print(af.collect())
    ```

    ```text
    shape: (2, 2)
    ┌────────┬────────┐
    │ face   ┆ banded │
    │ ---    ┆ ---    │
    │ f64    ┆ f64    │
    ╞════════╪════════╡
    │ 1250.0 ┆ 1300.0 │
    │ 1249.0 ┆ 1200.0 │
    └────────┴────────┘
    ```
    """
    expr = to_polars_expression(number)
    if num_digits >= 0:
        return expr.round(num_digits, mode="half_away_from_zero")
    # Polars rejects negative decimals; scale into range, round to a whole
    # number under the same rule, and scale back — ROUND(1250, -2) = 1300.
    factor = 10.0 ** (-num_digits)
    return (expr / factor).round(0, mode="half_away_from_zero") * factor
