# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars implementation of the Excel-compatible round function."""

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

# Past these, every double rounds the same way: at 400 places or more each
# one is already its own fifteen-digit value, and at -400 or fewer each is
# below half a step. Holding the count here keeps it inside the kernel's
# 32-bit argument whatever whole number a model writes.
_DIGITS_THAT_STILL_MOVE = 400


def round(number: IntoExprColumn, num_digits: int = 0) -> pl.Expr:  # noqa: A001
    """Round as Excel's ROUND does: the value Excel holds, half away from zero.

    Excel does not round the binary double a cell holds; it rounds the value
    it shows, the cell's **15-significant-digit decimal**, and sends a half
    **away from zero** for either sign. Both halves of that rule move money.
    ``ROUND(0.125, 2)`` is ``0.13`` where Polars' native ``.round()`` (half
    to even) gives ``0.12``. And a workbook's ``ROUND(1.5 * 45366.20999999999,
    2)`` is ``68049.32``: the product is the double ``68049.31499999999…``,
    whose fifteen digits read ``68049.3150000000`` -- a half. Rounding the
    double itself answers ``68049.31``, a cent short, and inside a recursion
    the cent compounds. ``2.675`` (``2.67499999999999982…`` as a double) is
    ``2.68`` for the same reason.

    The rule, in full: take the value's decimal expansion to 15 significant
    digits (a sixteenth digit of 5 or more going away from zero, a double that
    is exactly a sixteen-digit tie included: ``12345678901234.25`` is held as
    ``12345678901234.3``); round that
    decimal to ``num_digits`` places, a half going away from zero; answer the
    double nearest the result, with the input's sign. Where the fifteen digits
    are coarser than the step -- 10^15 or more at whole units, 10^13 or more
    at cents -- the answer is the fifteen-digit value itself, as in Excel.
    Non-finite values pass through, and nulls stay null. The rollforward's
    ``round_charge=`` and ``.round()`` round by this same rule, in the same
    code.

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
        (per-policy) and per-period list columns both round element-wise.
    num_digits : int
        Digits after the decimal point, as in Excel: ``2`` rounds to cents,
        ``0`` to whole units, and a negative value rounds to the left of the
        decimal point (``-2`` rounds to hundreds). Defaults to 0.

    Returns
    -------
    pl.Expr
        Float64 expression (List(Float64) for a list column) with each value
        rounded as Excel rounds it, a whole-number column included.

    Examples
    --------
    **Scalar Example: the two halves of Excel's rule**

    ```python
    from gaspatchio import ActuarialFrame

    data = {"charge": [0.125, -0.125, 1.5 * 45366.20999999999, 2.675]}
    af = ActuarialFrame(data)

    af.rounded = af.charge.excel.round(2)

    print(af.collect())
    ```

    ```text
    shape: (4, 2)
    ┌───────────┬──────────┐
    │ charge    ┆ rounded  │
    │ ---       ┆ ---      │
    │ f64       ┆ f64      │
    ╞═══════════╪══════════╡
    │ 0.125     ┆ 0.13     │
    │ -0.125    ┆ -0.13    │
    │ 68049.315 ┆ 68049.32 │
    │ 2.675     ┆ 2.68     │
    └───────────┴──────────┘
    ```

    **Negative digits: rounding to hundreds**

    ```python
    from gaspatchio import ActuarialFrame

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
    digits = max(-_DIGITS_THAT_STILL_MOVE, min(_DIGITS_THAT_STILL_MOVE, num_digits))
    return register_plugin_function(
        args=[to_polars_expression(number)],
        plugin_path=LIB,
        function_name="excel_round",
        is_elementwise=True,
        kwargs={"num_digits": digits},
    )
