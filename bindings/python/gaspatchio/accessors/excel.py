# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Accessors for Excel-related operations on ActuarialFrame columns/expressions."""

from typing import TYPE_CHECKING

from gaspatchio._authoring import emit

# Import registry decorator
from gaspatchio.frame.registry import register_accessor

# Use the new base location
from .base import BaseColumnAccessor, BaseFrameAccessor, refuse_bare_string_operand

# Use TYPE_CHECKING for core components to avoid circular imports
if TYPE_CHECKING:
    import datetime

    import polars as pl

    from gaspatchio._semantic.ir import AttrValue

    # Update imports to new locations
    from gaspatchio.column.column_proxy import ColumnProxy
    from gaspatchio.column.expression_proxy import ExpressionProxy
    from gaspatchio.frame.base import ActuarialFrame

# A day-count basis: 0-4, or a name for one -- "us_nasd_30_360", "act/act",
# "actual/360", "actual/365", "european_30_360" and the aliases the yearfrac
# lowering also reads (frame/lowering/_excel/yearfrac.py). Names are matched in
# any case, so a Literal of these spellings would refuse ones that work; the
# list lives in yearfrac's docstring, and a bad value is refused at run time.
BasisType = int | str


@register_accessor("excel", kind="frame")
class ExcelFrameAccessor(BaseFrameAccessor):
    """Provides Excel-related methods applicable to the entire ActuarialFrame.

    Accessed via `.excel` on an ActuarialFrame instance,
    e.g., `af.excel`.

    ``excel`` is a reserved attribute on the frame, as ``date``, ``finance``,
    ``graph`` and ``projection`` are. A model whose data really does carry a
    column called ``excel`` still has it -- reach it as ``af["excel"]`` --
    but ``af.excel`` is always this accessor.
    """

    def __init__(self, frame: "ActuarialFrame") -> None:
        """Initialize the accessor with the parent ActuarialFrame.

        Internal initialization method for the Excel frame accessor.
        """
        super().__init__(frame)
        # Placeholder for any frame-level excel methods


@register_accessor("excel", kind="column")
class ExcelColumnAccessor(BaseColumnAccessor):
    """Provides Excel-related methods applicable to columns or expressions.

    Accessed via `.excel` on an ActuarialFrame column or expression proxy,
    e.g., `af["my_excel_col"].excel`.

    **A bare string operand is refused here: write the operand as
    ``af.column`` or ``af["column"]``.** That rule holds on every column
    accessor, and is stated once in
    ``gaspatchio.accessors.base.refuse_bare_string_operand`` -- along with
    the frame-level methods that *do* name a column by string.
    """

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy") -> None:
        """Initialize the accessor with the parent proxy.

        Internal initialization method for the Excel column accessor.
        """
        super().__init__(proxy)
        self._proxy: ColumnProxy | ExpressionProxy = proxy

    def _get_parent_frame(self) -> "ActuarialFrame":
        """Return the frame this accessor's column belongs to.

        Every Excel method emits a ``Call`` node carried by a proxy, and a
        proxy carries the frame whose schema its formula is written
        against. A detached column has no such frame, so there is nothing
        to attach the result to and nothing to resolve shapes against --
        which is a refusal, not a default.

        Raises:
            RuntimeError: If the column is detached from any frame.

        """
        # Friend access: ColumnProxy and ExpressionProxy both set ``_parent``
        # in ``__init__`` and expose the frame under no public name.
        parent = self._proxy._parent  # noqa: SLF001 -- the bound proxy's frame
        if parent is None:
            msg = (
                "Operation requires the expression/column to be part of an "
                "ActuarialFrame context."
            )
            raise RuntimeError(msg)
        return parent

    def _emit(
        self,
        name: str,
        extra_args: tuple[object, ...] = (),
        attrs: tuple[tuple[str, "AttrValue"], ...] = (),
    ) -> "ExpressionProxy":
        """Emit an Excel-compatibility ``Call`` over this accessor's column.

        The method's job ends at recording which Excel function was asked
        for and with what configuration; the registered lowering in
        ``frame/lowering/rules/excel.py`` owns how it computes.
        """
        node = getattr(self._proxy, "_node", None)
        if node is None:
            msg = (
                f"ExcelColumnAccessor expected ColumnProxy or ExpressionProxy, "
                f"got {type(self._proxy).__name__}"
            )
            raise TypeError(msg)
        return emit.call(name, (node, *extra_args), self._get_parent_frame(), attrs)

    def from_excel_serial(self, epoch: str = "1900") -> "ExpressionProxy":
        """Convert Excel serial numbers (integers or floats) to Polars Date.

        Follows logic similar to openpyxl for compatibility. This method handles
        Excel's date serialization system, including the notorious Excel 1900
        leap year bug where Excel incorrectly treats 1900 as a leap year.

        !!! note "When to use"
            *   **Excel File Import:** When importing Excel files that contain date
                columns stored as serial numbers rather than proper date values.
            *   **Legacy Data Processing:** When working with older Excel files or
                systems that export dates as numeric serial values.
            *   **Cross-Platform Compatibility:** When handling Excel files that may
                have been created on different platforms (Windows vs Mac) with different
                epoch systems.
            *   **Data Validation:** When you need to convert and validate date serial
                numbers from external Excel-based data sources.

        Args:
            epoch: The epoch system used by Excel ('1900' or '1904').
                   Defaults to '1900'.

                   - 1900 Epoch (WINDOWS_1900_EPOCH = 1899-12-30):
                     Serial 1 is 1900-01-01. Excel's serial 60 (phantom 1900-02-29)
                     is mapped to 1900-02-28 (same as serial 59). Serials 1-59 add
                     serial+1 days to epoch; serials > 60 add serial days to epoch.
                   - 1904 Epoch (MAC_1904_EPOCH = 1904-01-01):
                     Serial 0 is invalid (represents time only). Serial 1 is 1904-01-02.
                     Days to add from epoch are equal to the serial number.

        Returns:
            An ExpressionProxy representing the converted date column.

        Raises:
            ValueError: If an invalid epoch is provided.

        Examples:
            ```python
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002", "P003"],
                "excel_date_serial": [44197, 44562, 44927],
            }
            af = ActuarialFrame(data)

            af.actual_date = af.excel_date_serial.excel.from_excel_serial(epoch="1900")

            print(af.collect())
            ```

            ```text
            shape: (3, 3)
            ┌───────────┬───────────────────┬─────────────┐
            │ policy_id ┆ excel_date_serial ┆ actual_date │
            │ ---       ┆ ---               ┆ ---         │
            │ str       ┆ i64               ┆ date        │
            ╞═══════════╪═══════════════════╪═════════════╡
            │ P001      ┆ 44197             ┆ 2021-01-01  │
            │ P002      ┆ 44562             ┆ 2022-01-01  │
            │ P003      ┆ 44927             ┆ 2023-01-01  │
            └───────────┴───────────────────┴─────────────┘
            ```
        """
        if epoch not in ("1900", "1904"):
            msg = f"Invalid epoch '{epoch}'. Must be '1900' or '1904'."
            raise ValueError(msg)
        return self._emit("excel.from_excel_serial", attrs=(("epoch", epoch),))

    def yearfrac(
        self,
        end_date_expr: "ColumnProxy | ExpressionProxy | pl.Expr | datetime.date",
        basis: BasisType = "act/act",
    ) -> "ExpressionProxy":
        """Calculate the year fraction between two dates, as Excel's YEARFRAC does.

        This function computes the fraction of a year represented by the number of
        whole days between a start date (the column/expression this accessor is on)
        and an end date. It uses a specified day count basis.

        As in Excel, the answer does not depend on which date comes first: the
        earlier one is the start, and the fraction is never negative, so a
        workbook's ``YEARFRAC(valuation, issue)`` converts as written. To tell
        a future-dated policy's pre-inception periods apart, compare the dates
        (``when(af["date"] < af.issue_date)``) rather than the sign. The
        leap-day and one-year rules of basis 1 and the February rules of basis
        0 are Excel's as well, on both the Polars and the JAX engine.

        !!! note "When to use"
            *   **Premium Proration**: Calculate the portion of an annual premium that
                corresponds to a partial policy term, for example, if a policy starts or
                ends mid-year.
            *   **Exposure Calculation**: Determine fractional exposure periods for
                reserving or IBNR (Incurred But Not Reported) calculations, especially
                when dealing with policies that are not in force for a full year.
            *   **Investment Analysis**: Compute fractional year periods for accrued
                interest calculations or for annualizing returns on investments held for
                parts of a year.
            *   **Performance Metrics**: Analyze time-based metrics such as
                time-to-claim or duration of an event, expressed as a fraction of a
                year.

        Parameters
        ----------
        end_date_expr : ColumnProxy | ExpressionProxy | pl.Expr | datetime.date
            The end dates: a column of dates, an expression, or a fixed
            ``datetime.date``. A bare string is refused — pass ``af["col"]``
            for the column.
        basis : int or str, optional
            The day count basis to use. Can be an integer (0-4) or a string name.
            Defaults to "act/act" (which is basis 1).

            Supported bases:
            - `0` or `'us_nasd_30_360'` (30/360 US NASD) - US (NASD) 30/360 convention
            - `1` or `'act/act'` (Actual/Actual) - Actual/Actual convention
            - `2` or `'actual_360'` (Actual/360) - Actual/360 convention
            - `3` or `'actual_365'` (Actual/365 fixed) - Actual/365 convention
            - `4` or `'european_30_360'` (30/360 European) - European 30/360 convention

        Returns
        -------
        ExpressionProxy
            An expression representing the calculated year fraction as a `Float64`.

        Raises
        ------
        TypeError
            If the underlying proxy for the start date is not a `ColumnProxy` or
            `ExpressionProxy`.
        RuntimeError
            If the operation requires an `ActuarialFrame` context that is not available.
        ValueError
            If an invalid basis is provided.

        Examples
        --------
        Calculating Policy Term as Year Fraction (Scalar/Column Operations)::

            Scenario: You have policy start and end dates and want to calculate the
            policy term in years.

            ```python
            import datetime
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002", "P003"],
                "start_date": [
                    datetime.date(2020, 1, 1),
                    datetime.date(2021, 6, 15),
                    datetime.date(2022, 3, 1),
                ],
                "end_date": [
                    datetime.date(2021, 1, 1),
                    datetime.date(2022, 6, 15),
                    datetime.date(2022, 9, 1),
                ],
            }
            af = ActuarialFrame(data)

            af.term_years = af.start_date.excel.yearfrac(af.end_date, basis="act/act")

            print(af.collect())
            ```

            ```
            shape: (3, 4)
            ┌───────────┬────────────┬────────────┬────────────┐
            │ policy_id ┆ start_date ┆ end_date   ┆ term_years │
            │ ---       ┆ ---        ┆ ---        ┆ ---        │
            │ str       ┆ date       ┆ date       ┆ f64        │
            ╞═══════════╪════════════╪════════════╪════════════╡
            │ P001      ┆ 2020-01-01 ┆ 2021-01-01 ┆ 1.0        │
            │ P002      ┆ 2021-06-15 ┆ 2022-06-15 ┆ 1.0        │
            │ P003      ┆ 2022-03-01 ┆ 2022-09-01 ┆ 0.50411    │
            └───────────┴────────────┴────────────┴────────────┘
            ```


        List Column Workaround::

            For actuarial projections stored as list columns (e.g., monthly projection
            dates), use the explode/group_by pattern:

            ```python
            import datetime
            import polars as pl
            from gaspatchio import ActuarialFrame
            from gaspatchio.frame.lowering._excel.yearfrac import yearfrac

            # Example with monthly projection dates
            projection_data = {
                "policy_id": ["P001", "P002"],
                "projection_dates": [
                    # 12 monthly dates
                    [datetime.date(2024, i, 1) for i in range(1, 13)],
                    [datetime.date(2024, i, 15) for i in range(1, 13)]
                ],
                "maturity_date": [
                    datetime.date(2024, 12, 31),
                    datetime.date(2025, 1, 1)
                ]
            }
            af_proj = ActuarialFrame(projection_data)

            # Calculate yearfrac for each projection date using explode/group_by
            result = (
                af_proj.collect()
                .lazy()
                .with_row_index("_idx")
                .explode("projection_dates")
                .with_columns(
                    yearfrac(
                        pl.col("projection_dates"),
                        pl.col("maturity_date"),
                        basis="act/act",
                    )
                    .alias("years_to_maturity")
                )
                .group_by("_idx")
                .agg([
                    pl.col("policy_id").first(),
                    pl.col("years_to_maturity"),
                    pl.col("maturity_date").first()
                ])
                .drop("_idx")
                .collect()
            )
            print(result)
            ```

            ```
            shape: (2, 3)
            ┌───────────┬──────────────────────────────────┬───────────────┐
            │ policy_id ┆ years_to_maturity                ┆ maturity_date │
            │ ---       ┆ ---                              ┆ ---           │
            │ str       ┆ list[f64]                        ┆ date          │
            ╞═══════════╪══════════════════════════════════╪═══════════════╡
            │ P001      ┆ [0.997268, 0.912568, … 0.081967] ┆ 2024-12-31    │
            │ P002      ┆ [0.961749, 0.877049, … 0.046575] ┆ 2025-01-01    │
            └───────────┴──────────────────────────────────┴───────────────┘
            ```

            Note: List columns are not directly supported due to Polars plugin
            limitations. Excel 365 achieves this with dynamic arrays, but we require
            explicit data transformation.

        """
        refuse_bare_string_operand(end_date_expr, parameter="end_date_expr")
        # Import the yearfrac function from the accessor functions module
        return self._emit("excel.yearfrac", (end_date_expr,), (("basis", basis),))

    def irr(
        self,
        *,
        guess: "ColumnProxy | ExpressionProxy | pl.Expr | float | None" = None,
        default_guess: float | None = None,
    ) -> "ExpressionProxy":
        """Calculate the internal rate of return for a series of cash flows.

        This function computes the discount rate that makes the net present value (NPV)
        of all cash flows equal to zero, using Excel's IRR algorithm.

        !!! note "When to use"
            *   **Investment Analysis**: Evaluate the profitability of investment
                portfolios or individual securities
            *   **Project Evaluation**: Compare the returns of different actuarial
                projects or initiatives
            *   **Premium Adequacy**: Assess whether premium cash flows generate
                sufficient returns
            *   **Asset-Liability Matching**: Evaluate the performance of matched asset
                and liability cash flows

        Parameters
        ----------
        guess : ColumnProxy | ExpressionProxy | pl.Expr | float, optional
            Optional per-row initial guess for IRR. If not provided, uses
            default_guess. A bare string is refused — pass ``af["col"]``
            for the column.
        default_guess : float, optional
            Scalar fallback guess when `guess` is not provided. Defaults to 0.1 (10%).

        Returns
        -------
        ExpressionProxy
            Float64 IRR per row representing the internal rate of return.

        Examples
        --------
        Calculate IRR for investment cash flows::

            ```python
            from gaspatchio import ActuarialFrame

            data = {
                "investment_id": ["INV001", "INV002"],
                "cash_flows": [
                    [-1000.0, 300.0, 400.0, 500.0],  # Initial investment + returns
                    [-5000.0, 1000.0, 2000.0, 3500.0]  # Different investment
                ]
            }
            af = ActuarialFrame(data)

            af.irr = af.cash_flows.excel.irr()

            print(af.collect())
            ```

            ```
            shape: (2, 3)
            ┌───────────────┬─────────────────────────────┬──────────┐
            │ investment_id ┆ cash_flows                  ┆ irr      │
            │ ---           ┆ ---                         ┆ ---      │
            │ str           ┆ list[f64]                   ┆ f64      │
            ╞═══════════════╪═════════════════════════════╪══════════╡
            │ INV001        ┆ [-1000.0, 300.0, … 500.0]   ┆ 0.088963 │
            │ INV002        ┆ [-5000.0, 1000.0, … 3500.0] ┆ 0.117921 │
            └───────────────┴─────────────────────────────┴──────────┘
            ```

        """
        refuse_bare_string_operand(guess, parameter="guess")
        extra = () if guess is None else (guess,)
        return self._emit("excel.irr", extra, (("default_guess", default_guess),))

    def pv(
        self,
        nper: "ColumnProxy | ExpressionProxy | pl.Expr | float",
        pmt: "ColumnProxy | ExpressionProxy | pl.Expr | float",
        *,
        fv: float | None = None,
        typ: int | None = None,
    ) -> "ExpressionProxy":
        """Calculate the present value of an investment based on periodic payments.

        This function computes the present value of a loan or an investment, based on a
        constant interest rate and regular payments, using Excel's PV formula.

        !!! note "When to use"
            *   **Reserve Calculations**: Calculate the present value of future benefit
                payments for reserve valuations
            *   **Annuity Pricing**: Determine the present value of annuity payment
                streams
            *   **Loan Analysis**: Evaluate the present value of loan repayments for
                asset-liability management
            *   **Capital Budgeting**: Assess the present value of project cash flows
                for investment decisions

        Parameters
        ----------
        nper : ColumnProxy | ExpressionProxy | pl.Expr | float
            Number of periods as a number, column or list column. A bare
            string is refused — pass ``af["col"]`` for the column.
        pmt : ColumnProxy | ExpressionProxy | pl.Expr | float
            Payment per period as a number, column or list column. A bare
            string is refused — pass ``af["col"]`` for the column.
        fv : float, optional
            Future value at the end of nper periods. Defaults to 0.0.
        typ : int, optional
            Payment timing: 0 for payments at end of period (default), 1 for beginning.

        Returns
        -------
        ExpressionProxy
            Float64 or List[Float64] representing the present value.

        Examples
        --------
        Calculate present value of annuity payments::

            ```python
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["POL001", "POL002", "POL003"],
                "interest_rate": [0.05, 0.04, 0.06],  # Annual interest rates
                "num_periods": [10.0, 15.0, 20.0],  # Number of payment periods
                "payment": [1000.0, 1500.0, 2000.0],  # Payment per period
            }
            af = ActuarialFrame(data)

            af.present_value = af.interest_rate.excel.pv(
                nper=af.num_periods, pmt=af.payment
            )

            print(af.collect())
            ```

            ```
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
        refuse_bare_string_operand(nper, parameter="nper")
        refuse_bare_string_operand(pmt, parameter="pmt")
        return self._emit("excel.pv", (nper, pmt), (("fv", fv), ("typ", typ)))

    def round(self, num_digits: int = 0) -> "ExpressionProxy":
        """Round as Excel's ROUND does: the value Excel holds, half away from zero.

        Excel rounds the value a cell shows -- its **15-significant-digit
        decimal** -- not the binary double underneath, and sends a half **away
        from zero**. So ``ROUND(0.125, 2)`` is ``0.13`` (Polars' native
        ``.round()``, half to even, gives ``0.12``), and a workbook's
        ``ROUND(1.5 * 45366.20999999999, 2)`` is ``68049.32``: the double is
        ``68049.31499999999…``, but its fifteen digits read
        ``68049.3150000000``, a half. Rounding the double alone answers
        ``68049.31``. When a workbook rounds inside its recursion that cent
        compounds, so a conversion must use the workbook's rule. A sixteenth
        digit of 5 or more goes away from zero, a double that is exactly a
        sixteen-digit tie included. Where the fifteen digits are coarser than
        the step (10^13 or more at cents) the answer is the fifteen-digit
        value itself, as in Excel. The
        rollforward's ``rf["state"].round()`` and ``round_charge=`` apply this
        same rule, in the same code; this method is their column-side
        counterpart.

        Works on scalar and per-period list columns; list columns are rounded
        element-wise.

        !!! note "When to use"
            *   **Workbook Conversion**: Reproduce a spreadsheet's ROUND exactly.
            *   **Regulatory Reporting**: Match figures rounded away from zero.
            *   **Reconciliation**: Remove rounding-convention mismatches first.

        Parameters
        ----------
        num_digits : int
            Digits after the decimal point, as in Excel: ``2`` rounds to
            cents, ``0`` to whole units, negative values round to the left of
            the decimal point (``-2`` rounds to hundreds). Defaults to 0.

        Returns
        -------
        ExpressionProxy
            Float64 (or List[Float64] for list columns) rounded as Excel
            rounds it.

        Examples
        --------
        Round per-period charges to cents the way the workbook does::

            ```python
            from gaspatchio import ActuarialFrame

            af = ActuarialFrame({"coi": [[10.125, 7558.485, 1.5 * 45366.20999999999]]})
            af.coi_rounded = af.coi.excel.round(2)  # [10.13, 7558.49, 68049.32]
            ```

        """
        return self._emit("excel.round", attrs=(("num_digits", num_digits),))

    def norm_s_dist(self, *, cumulative: bool = True) -> "ExpressionProxy":
        """Evaluate Excel's NORM.S.DIST(z, TRUE): the standard normal distribution.

        This is the Excel spelling of ``.norm_cdf()``, and it records that same
        operation: ``af.z.excel.norm_s_dist()`` and ``af.z.norm_cdf()`` are one
        node with one identity, so a model converted from a workbook and one
        written from a textbook's N(d1) publish the same digest.
        ``NORMSDIST(z)`` is the same function under Excel's older name.

        Excel's ``NORM.DIST(x, mean, sd, TRUE)`` has no door of its own:
        standardise first and write ``((x - mean) / sd).norm_cdf()``.

        The accuracy is ``.norm_cdf()``'s: 1e-12 relative to the mathematical
        Φ wherever Φ is a normal double, exact at null, NaN and the
        infinities, and about 1e-14 in practice. Excel's own bits are not
        reproduced: its algorithm is unpublished, and its cached values sit
        within about 1e-14 of the true Φ, so reconcile a converted workbook at
        that order.

        !!! note "When to use"
            *   **Workbook Conversion**: A cell reading ``NORM.S.DIST(z, TRUE)``,
                ``NORMSDIST(z)`` or ``NORM.DIST(z, 0, 1, TRUE)``.
            *   **Guarantees priced as options**: The N(-d1) and N(-d2) of a
                GMDB or GMMB valued as a Black-Scholes put.

        Parameters
        ----------
        cumulative : bool
            ``True``, the distribution function, as Excel's second argument
            says. ``False`` asks for the density, which is refused with the
            density written in core operations:
            ``(-z**2 / 2).exp() / (2 * math.pi) ** 0.5``.

        Returns
        -------
        ExpressionProxy
            Φ of each value: Float64, or List[Float64] for a list column.

        Raises
        ------
        ValueError
            If ``cumulative`` is ``False``.
        TypeError
            If ``cumulative`` is not a bool.

        Examples
        --------
        The N(-d2) of a GMDB put, as the workbook writes it::

            ```python
            from gaspatchio import ActuarialFrame

            af = ActuarialFrame({"d2": [0.24, -0.15]})
            # =NORM.S.DIST(-d2, TRUE)
            af.n_minus_d2 = (-af.d2).excel.norm_s_dist()  # [0.405165, 0.559618]
            ```

        """
        if cumulative is False:
            msg = (
                "excel.norm_s_dist(cumulative=False) is the standard normal "
                "density, which is not an operation of its own: no workbook in "
                "evidence asks for it. Write it in core operations, which "
                "record and run on every engine: for a column z, "
                "(-z**2 / 2).exp() / (2 * math.pi) ** 0.5. The distribution "
                "function, cumulative=True, is .excel.norm_s_dist() or "
                ".norm_cdf()."
            )
            raise ValueError(msg)
        if cumulative is not True:
            msg = (
                "excel.norm_s_dist(cumulative=...) takes True or False, as "
                f"Excel's second argument does; it was given {cumulative!r}."
            )
            raise TypeError(msg)
        from gaspatchio.column._declared import (  # noqa: PLC0415 -- import cycle
            _call_declared_method,
        )

        return _call_declared_method("norm_cdf", self._proxy)

    def days(
        self, start_date: "ColumnProxy | ExpressionProxy | pl.Expr | datetime.date"
    ) -> "ExpressionProxy":
        """Calculate the number of days between two dates, similar to Excel's DAYS.

        This function computes the number of days between an end date (the
        column/expression this accessor is on) and a start date. The result is positive
        if the end date is after the start date, and negative if before.

        !!! note "When to use"
            *   **Duration Calculations**: Calculate the length of policy terms, claim
                periods, or other time-based intervals.
            *   **Age Calculations**: Determine the number of days between birth dates
                and valuation dates for precise age calculations.
            *   **Interest Calculations**: Calculate the exact number of days for
                interest accrual between two specific dates.
            *   **Exposure Period Analysis**: Measure exposure periods in days for risk
                assessment or premium calculations.

        Parameters
        ----------
        start_date : ColumnProxy | ExpressionProxy | pl.Expr | datetime.date
            The start dates: a column of dates, an expression, or a fixed
            ``datetime.date``. A bare string is refused — pass ``af["col"]``
            for the column.

        Returns
        -------
        ExpressionProxy
            An expression representing the calculated days difference as an `Int64`.

        Examples
        --------
        ```python
        import datetime
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "start_date": [datetime.date(2023, 1, 1), datetime.date(2023, 6, 15)],
            "end_date": [datetime.date(2023, 1, 31), datetime.date(2023, 7, 15)],
        }
        af = ActuarialFrame(data)

        # Calculate days between start and end dates
        af_with_days = af.with_columns(
            days_diff=af["end_date"].excel.days(af["start_date"])
        )
        print(af_with_days.collect())
        ```

        """
        refuse_bare_string_operand(start_date, parameter="start_date")
        return self._emit("excel.days", (start_date,))

    def edate(
        self, months: "ColumnProxy | ExpressionProxy | pl.Expr | int"
    ) -> "ExpressionProxy":
        """Add months to a date, similar to Excel's EDATE.

        This function adds the specified number of months to the date column/expression
        this accessor is on, returning the resulting date. Handles month boundaries
        correctly (e.g., January 31 + 1 month = February 28/29).

        !!! note "When to use"
            *   **Policy Anniversary Dates**: Calculate policy renewal dates or
                anniversary dates by adding months to the issue date.
            *   **Payment Schedules**: Determine future premium due dates or benefit
                payment dates based on monthly intervals.
            *   **Maturity Calculations**: Calculate policy or investment maturity dates
                by adding a term in months to the start date.
            *   **Projection Periods**: Generate future valuation dates for cash flow
                projections or reserving calculations.

        Parameters
        ----------
        months : ColumnProxy | ExpressionProxy | pl.Expr | int
            The number of months to add, positive or negative: a whole
            number, a column of them, or an expression, one per policy. A
            double counts where it is whole; a fraction, text, a flag or a
            count held per period is refused. A bare string is refused —
            pass ``af["col"]`` for the column.

        Returns
        -------
        ExpressionProxy
            An expression representing the date after adding months.

        Examples
        --------
        ```python
        import datetime
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "start_date": [datetime.date(2023, 1, 31), datetime.date(2023, 3, 15)],
            "months_to_add": [1, 3],
        }
        af = ActuarialFrame(data)

        # Add months to dates
        af_with_new_dates = af.with_columns(
            new_date=af["start_date"].excel.edate(af["months_to_add"])
        )
        print(af_with_new_dates.collect())
        ```

        """
        refuse_bare_string_operand(months, parameter="months")
        return self._emit("excel.edate", (months,))

    def eomonth(
        self, months: "ColumnProxy | ExpressionProxy | pl.Expr | int"
    ) -> "ExpressionProxy":
        """Get the end of month after adding months, similar to Excel's EOMONTH.

        This function adds the specified number of months to the date column/expression
        this accessor is on, then returns the last day of that resulting month.

        !!! note "When to use"
            *   **Reporting Periods**: Determine month-end dates for financial reporting
                or regulatory submissions.
            *   **Interest Calculations**: Calculate interest accrual periods that end
                on the last day of each month.
            *   **Benefit Payment Dates**: Set benefit payment dates to month-end when
                payments are made monthly.
            *   **Policy Term Boundaries**: Define policy terms or coverage periods that
                end on month boundaries.

        Parameters
        ----------
        months : ColumnProxy | ExpressionProxy | pl.Expr | int
            How far to move before the month's last day is taken, read
            exactly as ``edate`` reads it: one whole number of months per
            policy (a literal, a column or an expression), positive or
            negative. A bare string is refused — pass ``af["col"]``.

        Returns
        -------
        ExpressionProxy
            An expression representing the end-of-month date after adding months.

        Examples
        --------
        ```python
        import datetime
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "start_date": [datetime.date(2023, 3, 15), datetime.date(2023, 1, 5)],
            "months_to_add": [1, 2],
        }
        af = ActuarialFrame(data)

        # Get end of month after adding months
        af_with_eom_dates = af.with_columns(
            end_of_month=af["start_date"].excel.eomonth(af["months_to_add"])
        )
        print(af_with_eom_dates.collect())
        ```

        """
        refuse_bare_string_operand(months, parameter="months")
        return self._emit("excel.eomonth", (months,))


# What the API reference documents from this module.
__all__ = ["ExcelColumnAccessor"]
