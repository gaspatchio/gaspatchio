"""Base type stubs for common proxy elements."""

from __future__ import annotations

import builtins
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import polars as pl
from polars.type_aliases import PolarsDataType

# Import types used in signatures
if TYPE_CHECKING:
    # import polars # Not needed if using type_aliases correctly
    from polars.type_aliases import (
        ExprArray,
        ExprBinary,
        ExprCategorical,
        ExprStruct,
    )
    from polars.type_aliases import (
        ExprList as PolarsExprList,  # Alias for use in string hint
    )

    from ..frame.base import ActuarialFrame  # For DtNamespaceProxy.__init__
    from .column_proxy import ColumnProxy  # For DtNamespaceProxy.__init__ parent type

    # Import local types carefully
    from .expression_proxy import ExpressionProxy
    from .namespaces.dt_proxy import (
        DtNamespaceProxy as _DtNamespaceProxy,  # MODIFIED: For type hint
    )
    from .namespaces.string_proxy import (
        StringNamespaceProxy as _StringNamespaceProxy,  # ADDED
    )

    # Type alias for DtNamespaceProxy parent, consistent with dt_proxy.py
    type ParentProxyType = ColumnProxy | ExpressionProxy

    # Although __dir__ is added dynamically, including it helps tools
    def __dir__(self) -> builtins.list[str]: ...

# --- Stub for DtNamespaceProxy --- ADDED ---
class DtNamespaceProxy:
    """Date and time accessor for actuarial data analysis.

    Provides specialized date and time operations essential for actuarial modeling,
    including policy anniversary calculations, age computations, duration analysis,
    and regulatory date-based calculations. Enables efficient date arithmetic and
    extraction of date components for pricing models, reserve calculations, and
    experience studies.
    """

    _parent_proxy: ParentProxyType
    _parent_af: ActuarialFrame | None

    def __init__(
        self,
        parent_proxy: ParentProxyType,
        parent_af: ActuarialFrame | None,
    ) -> None: ...
    def year(self) -> ExpressionProxy:
        """Extract calendar year from date values.

        Extracts the calendar year component from date columns, essential for
        actuarial analysis requiring year-based grouping, trend analysis, and
        regulatory reporting. Converts date values to four-digit year integers
        for policy anniversary calculations, experience studies, and temporal
        analysis in actuarial modeling.

        !!! note "When to use"
            * **Policy Anniversary Analysis:** Group policies by issue year for
                experience studies and persistency analysis.
            * **Regulatory Reporting:** Extract years for annual statements,
                solvency reports, and regulatory filings.
            * **Trend Analysis:** Analyze mortality, lapse, and claims trends
                across calendar years.
            * **Vintage Analysis:** Group model points by policy vintage year
                for cohort-based analysis and pricing studies.

        Returns
        -------
        ExpressionProxy
            An expression containing the calendar year as integers.

        Examples
        --------
        **Scalar Example: Policy Issue Year**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003"],
            "issue_date": ["2020-03-15", "2021-07-22", "2019-12-01"],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["issue_date"].str.to_date().dt.year().alias("issue_year")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌───────────┬────────────┐
        │ policy_id ┆ issue_year │
        │ ---       ┆ ---        │
        │ str       ┆ i32        │
        ╞═══════════╪════════════╡
        │ P001      ┆ 2020       │
        │ P002      ┆ 2021       │
        │ P003      ┆ 2019       │
        └───────────┴────────────┘
        ```

        **Vector Example: Claim Year Analysis**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "age": [55, 38],
            "month": [
                [1, 2, 3, 4],
                [1, 2, 3, 4]
            ],
            "claim_dates": [
                ["2020-01-15", "2020-06-30", "2021-03-22", "2021-12-15"],
                ["2019-12-01", "2020-08-15", "2021-11-30", "2022-05-10"]
            ]
        }
        af = ActuarialFrame(data)

        af["claim_years"] = af["claim_dates"].str.to_date().dt.year()

        print(af.collect())
        ```

        ```text
        shape: (2, 5)
        ┌───────────┬─────┬──────────────┬─────────────────────────────┬─────────────────────────┐
        │ policy_id ┆ age ┆ month        ┆ claim_dates                 ┆ claim_years             │
        │ ---       ┆ --- ┆ ---          ┆ ---                         ┆ ---                     │
        │ str       ┆ i64 ┆ list[i64]    ┆ list[str]                   ┆ list[i32]               │
        ╞═══════════╪═════╪══════════════╪═════════════════════════════╪═════════════════════════╡
        │ P001      ┆ 55  ┆ [1, 2, 3, 4] ┆ ["2020-01-15", "2020-06-…  ┆ [2020, 2020, 2021, …   │
        │ P002      ┆ 38  ┆ [1, 2, 3, 4] ┆ ["2019-12-01", "2020-08-…  ┆ [2019, 2020, 2021, …   │
        └───────────┴─────┴──────────────┴─────────────────────────────┴─────────────────────────┘
        ```
        """

    # Add other common dt methods as they are implemented or needed for type hints
    # For now, __getattr__ will handle them dynamically at runtime, but stubs improve DX.
    def month(self) -> ExpressionProxy:
        """Extract calendar month from date values.

        Extracts the calendar month component (1-12) from date columns for
        seasonal analysis, anniversary tracking, and premium payment scheduling.
        Essential for actuarial calculations requiring month-based grouping,
        seasonal mortality patterns, and policy administration workflows.

        !!! note "When to use"
            * **Premium Payment Cycles:** Extract months for premium billing
                schedules and payment frequency analysis.
            * **Seasonal Analysis:** Analyze mortality, lapse, and claims patterns
                by calendar month for seasonal adjustments.
            * **Policy Anniversaries:** Track monthly anniversary dates for
                reserve calculations and policy reviews.
            * **Regulatory Reporting:** Extract months for quarterly and annual
                regulatory filing requirements.

        Returns
        -------
        ExpressionProxy
            An expression containing the calendar month as integers (1-12).

        Examples
        --------
        **Scalar Example: Premium Payment Month**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003"],
            "payment_date": ["2023-03-15", "2023-07-22", "2023-12-01"],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["payment_date"].str.to_date().dt.month().alias("payment_month")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌───────────┬───────────────┐
        │ policy_id ┆ payment_month │
        │ ---       ┆ ---           │
        │ str       ┆ i8            │
        ╞═══════════╪═══════════════╡
        │ P001      ┆ 3             │
        │ P002      ┆ 7             │
        │ P003      ┆ 12            │
        └───────────┴───────────────┘
        ```

        **Vector Example: Monthly Premium Schedule**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "age": [45, 52],
            "month": [
                [1, 2, 3, 4],
                [1, 2, 3, 4]
            ],
            "premium_dates": [
                ["2023-01-15", "2023-04-15", "2023-07-15", "2023-10-15"],
                ["2023-02-28", "2023-05-31", "2023-08-31", "2023-11-30"]
            ]
        }
        af = ActuarialFrame(data)

        af["premium_months"] = af["premium_dates"].str.to_date().dt.month()

        print(af.collect())
        ```

        ```text
        shape: (2, 5)
        ┌───────────┬─────┬──────────────┬─────────────────────────────┬───────────────────┐
        │ policy_id ┆ age ┆ month        ┆ premium_dates               ┆ premium_months    │
        │ ---       ┆ --- ┆ ---          ┆ ---                         ┆ ---               │
        │ str       ┆ i64 ┆ list[i64]    ┆ list[str]                   ┆ list[i8]          │
        ╞═══════════╪═════╪══════════════╪═════════════════════════════╪═══════════════════╡
        │ P001      ┆ 45  ┆ [1, 2, 3, 4] ┆ ["2023-01-15", "2023-04-…  ┆ [1, 4, 7, 10]     │
        │ P002      ┆ 52  ┆ [1, 2, 3, 4] ┆ ["2023-02-28", "2023-05-…  ┆ [2, 5, 8, 11]     │
        └───────────┴─────┴──────────────┴─────────────────────────────┴───────────────────┘
        ```
        """
    def day(self) -> ExpressionProxy:
        """Extract day of month from date values.

        Extracts the day component (1-31) from date columns for precise date
        calculations, payment processing, and policy administration. Essential
        for actuarial workflows requiring specific day-based analysis, billing
        cycles, and anniversary date tracking in insurance operations.

        !!! note "When to use"
            * **Payment Due Dates:** Extract specific days for premium billing
                schedules and payment reminder systems.
            * **Policy Anniversaries:** Calculate exact anniversary dates for
                policy reviews and benefit adjustments.
            * **Grace Period Calculations:** Determine exact day counts for
                grace periods and late payment penalties.
            * **Regulatory Deadlines:** Track specific calendar days for
                regulatory filing and compliance requirements.

        Returns
        -------
        ExpressionProxy
            An expression containing the day of month as integers (1-31).

        Examples
        --------
        **Scalar Example: Payment Due Day**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003"],
            "due_date": ["2023-03-15", "2023-07-01", "2023-12-31"],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["due_date"].str.to_date().dt.day().alias("due_day")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌───────────┬─────────┐
        │ policy_id ┆ due_day │
        │ ---       ┆ ---     │
        │ str       ┆ i8      │
        ╞═══════════╪═════════╡
        │ P001      ┆ 15      │
        │ P002      ┆ 1       │
        │ P003      ┆ 31      │
        └───────────┴─────────┘
        ```

        **Vector Example: Anniversary Day Tracking**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "age": [35, 42],
            "month": [
                [1, 2, 3, 4],
                [1, 2, 3, 4]
            ],
            "anniversary_dates": [
                ["2023-01-15", "2023-02-15", "2023-03-15", "2023-04-15"],
                ["2023-01-28", "2023-02-28", "2023-03-28", "2023-04-28"]
            ]
        }
        af = ActuarialFrame(data)

        af["anniversary_days"] = af["anniversary_dates"].str.to_date().dt.day()

        print(af.collect())
        ```

        ```text
        shape: (2, 5)
        ┌───────────┬─────┬──────────────┬─────────────────────────────┬──────────────────┐
        │ policy_id ┆ age ┆ month        ┆ anniversary_dates           ┆ anniversary_days │
        │ ---       ┆ --- ┆ ---          ┆ ---                         ┆ ---              │
        │ str       ┆ i64 ┆ list[i64]    ┆ list[str]                   ┆ list[i8]         │
        ╞═══════════╪═════╪══════════════╪═════════════════════════════╪══════════════════╡
        │ P001      ┆ 35  ┆ [1, 2, 3, 4] ┆ ["2023-01-15", "2023-02-…  ┆ [15, 15, 15, 15] │
        │ P002      ┆ 42  ┆ [1, 2, 3, 4] ┆ ["2023-01-28", "2023-02-…  ┆ [28, 28, 28, 28] │
        └───────────┴─────┴──────────────┴─────────────────────────────┴──────────────────┘
        ```
        """
    def __getattr__(
        self,
        name: str,
    ) -> Callable[..., ExpressionProxy]: ...  # MODIFIED: More precise return type

# --- Stub for StringNamespaceProxy --- ADDED ---
class StringNamespaceProxy:
    """String manipulation accessor for actuarial text data processing.

    Provides comprehensive string operations for actuarial data management,
    including policy number formatting, product code standardization, address
    cleansing, and regulatory text processing. Essential for data quality
    improvements, matching operations, and preparing text data for actuarial
    analysis and reporting.
    """

    _parent_proxy: (
        ParentProxyType  # Assuming ParentProxyType is ColumnProxy | ExpressionProxy
    )
    _parent_af: ActuarialFrame | None

    def __init__(
        self,
        parent_proxy: ParentProxyType,
        parent_af: ActuarialFrame | None,
    ) -> None: ...

    # --- Explicitly defined methods from string_proxy.py ---
    def contains(
        self,
        pattern: str | pl.Expr,
        literal: bool = False,
        strict: bool = False,
    ) -> ExpressionProxy: ...
    def to_uppercase(self) -> ExpressionProxy: ...
    def to_lowercase(self) -> ExpressionProxy: ...
    def n_chars(self) -> ExpressionProxy: ...
    def len_chars(self) -> ExpressionProxy: ...
    def len_bytes(self) -> ExpressionProxy: ...
    def strip_chars(
        self,
        characters: str | pl.Expr | None = None,
    ) -> ExpressionProxy: ...
    def strip_chars_start(
        self,
        characters: str | pl.Expr | None = None,
    ) -> ExpressionProxy: ...
    def lstrip(
        self,
        characters: str | pl.Expr | None = None,
    ) -> ExpressionProxy: ...
    def strip_chars_end(
        self,
        characters: str | pl.Expr | None = None,
    ) -> ExpressionProxy: ...
    def rstrip(
        self,
        characters: str | pl.Expr | None = None,
    ) -> ExpressionProxy: ...
    def strip_prefix(self, prefix: str | pl.Expr) -> ExpressionProxy: ...
    def remove_prefix(self, prefix: str | pl.Expr) -> ExpressionProxy: ...
    def strip_suffix(self, suffix: str | pl.Expr) -> ExpressionProxy: ...
    def remove_suffix(self, suffix: str | pl.Expr) -> ExpressionProxy: ...
    def zfill(self, alignment: int) -> ExpressionProxy: ...
    def ljust(self, width: int, fill_char: str = " ") -> ExpressionProxy: ...
    def pad_start(
        self,
        width: int,
        fill_char: str = " ",
    ) -> ExpressionProxy: ...  # Alias for rjust
    def rjust(self, width: int, fill_char: str = " ") -> ExpressionProxy: ...
    def pad_end(
        self,
        width: int,
        fill_char: str = " ",
    ) -> ExpressionProxy: ...  # Alias for ljust
    def starts_with(self, prefix: str | pl.Expr) -> ExpressionProxy: ...
    def ends_with(self, suffix: str | pl.Expr) -> ExpressionProxy: ...

    # Add __getattr__ for dynamic methods if we want to hint them generally
    def __getattr__(self, name: str) -> Callable[..., ExpressionProxy]: ...

# Base class for shared proxy methods/properties
class _BaseProxy:
    """Base proxy foundation for actuarial data operations.

    Provides core functionality shared across column and expression proxies,
    including arithmetic operations, comparisons, and conditional logic essential
    for actuarial calculations. Enables seamless mathematical operations on
    premium calculations, reserve computations, cash flow projections, and
    statistical analysis in actuarial modeling workflows.
    """

    # --- Operator Overloads (returning ExpressionProxy) ---
    def __add__(self, other: Any) -> ExpressionProxy: ...
    def __sub__(self, other: Any) -> ExpressionProxy: ...
    def __mul__(self, other: Any) -> ExpressionProxy: ...
    def __truediv__(self, other: Any) -> ExpressionProxy: ...
    def __floordiv__(self, other: Any) -> ExpressionProxy: ...
    def __mod__(self, other: Any) -> ExpressionProxy: ...
    def __pow__(self, other: Any) -> ExpressionProxy: ...
    def __eq__(self, other: object) -> ExpressionProxy: ...
    def __ne__(self, other: object) -> ExpressionProxy: ...
    def __lt__(self, other: Any) -> ExpressionProxy: ...
    def __le__(self, other: Any) -> ExpressionProxy: ...
    def __gt__(self, other: Any) -> ExpressionProxy: ...
    def __ge__(self, other: Any) -> ExpressionProxy: ...
    def __radd__(self, other: Any) -> ExpressionProxy: ...
    def __rsub__(self, other: Any) -> ExpressionProxy: ...
    def __rmul__(self, other: Any) -> ExpressionProxy: ...
    def __rtruediv__(self, other: Any) -> ExpressionProxy: ...
    def __rfloordiv__(self, other: Any) -> ExpressionProxy: ...
    def __rmod__(self, other: Any) -> ExpressionProxy: ...
    def __rpow__(self, other: Any) -> ExpressionProxy: ...

    # --- Namespaces (Accessors returning Namespace Proxies) ---
    @property
    def dt(self) -> _DtNamespaceProxy: ...  # MODIFIED: Changed to DtNamespaceProxy
    @property
    def str(
        self,
    ) -> _StringNamespaceProxy: ...  # MODIFIED: Changed to StringNamespaceProxy
    @property
    def list(self) -> PolarsExprList: ...  # Use aliased name in string hint
    @property
    def arr(self) -> ExprArray: ...
    @property
    def struct(self) -> ExprStruct: ...
    @property
    def cat(self) -> ExprCategorical: ...
    @property
    def bin(self) -> ExprBinary: ...

    # --- Common Autopatched Methods/Namespaces (Returning ExpressionProxy) ---
    def alias(self, name: str) -> ExpressionProxy:
        """Assign a new name to this expression for use in selections and computations.

        Creates a new ExpressionProxy with the specified column name. This is
        fundamental for creating derived columns, renaming computed values, and
        organizing actuarial calculations with meaningful, business-relevant names
        that enhance readability and maintainability of analytical workflows.

        !!! note "When to use"
            * **Derived Calculations:** Name computed values like "adjusted_premium",
              "net_present_value", or "mortality_adjustment" for clarity in analysis.
            * **Business Terminology:** Use actuarial terms like "reserves_best_estimate",
              "risk_margin", or "solvency_capital_requirement" for regulatory reporting.
            * **Data Standardization:** Rename columns from different sources to
              consistent naming conventions for portfolio analysis.
            * **Intermediate Results:** Name intermediate calculations in complex
              formulas for debugging and validation purposes.
            * **Reporting Clarity:** Create user-friendly column names for management
              dashboards and regulatory reports.
            * **Model Documentation:** Use descriptive names that match actuarial
              model specifications and documentation.

        Parameters
        ----------
        name : str
            The new name to assign to this expression. Should follow standard
            naming conventions and be descriptive of the value's purpose.

        Returns
        -------
        ExpressionProxy
            A new ExpressionProxy with the specified alias name.

        Examples
        --------
        **Scalar Example: Naming a Premium Calculation**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "base_premium": [1000.0, 1200.0, 800.0],
            "loading_factor": [1.15, 1.20, 1.10],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            (af["base_premium"] * af["loading_factor"]).alias("gross_premium")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 1)
        ┌───────────────┐
        │ gross_premium │
        │ ---           │
        │ f64           │
        ╞═══════════════╡
        │ 1150.0        │
        │ 1440.0        │
        │ 880.0         │
        └───────────────┘
        ```

        **Vector Example: Multiple Derived Calculations**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "sum_assured": [100000.0, 250000.0, 500000.0],
            "premium": [1200.0, 2800.0, 4500.0],
            "age": [35, 45, 55],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            (af["premium"] / af["sum_assured"] * 1000).alias("premium_per_1000"),
            ((af["age"] // 10) * 10).alias("age_decade")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌──────────────┬──────────┐
        │ premium_rate ┆ age_band │
        │ ---          ┆ ---      │
        │ f64          ┆ i64      │
        ╞══════════════╪══════════╡
        │ 12.0         ┆ 30       │
        │ 11.2         ┆ 40       │
        │ 9.0          ┆ 50       │
        └──────────────┴──────────┘
        ```
        """
    def clip(self, lower_bound: float, upper_bound: float) -> ExpressionProxy:
        """Constrain values to specified minimum and maximum bounds.

        Limits values to a specified range by setting any value below the lower bound
        to the lower bound and any value above the upper bound to the upper bound.
        Essential for risk management, regulatory compliance, and data standardization
        in actuarial analysis.

        !!! note "When to use"
            * **Risk Limits:** Enforce maximum exposure limits, claim caps, or
              minimum reserve requirements for regulatory compliance.
            * **Data Standardization:** Constrain outliers to reasonable ranges
              for statistical analysis and model development.
            * **Premium Bounds:** Apply minimum and maximum premium limits based
              on underwriting guidelines or regulatory requirements.
            * **Age Restrictions:** Enforce age eligibility ranges for specific
              products, benefits, or pricing tables.
            * **Financial Controls:** Limit investment allocations, benefit amounts,
              or commission rates within approved ranges.
            * **Quality Assurance:** Prevent extreme values that could indicate
              data errors or processing issues.

        Parameters
        ----------
        lower_bound : float
            The minimum value allowed. Values below this will be set to this value.
        upper_bound : float
            The maximum value allowed. Values above this will be set to this value.

        Returns
        -------
        ExpressionProxy
            An expression with values constrained to the specified bounds.

        Examples
        --------
        **Scalar Example: Age Eligibility Clipping**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "applicant_id": ["A001", "A002", "A003", "A004", "A005"],
            "age": [16, 25, 35, 70, 85],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["applicant_id"],
            original_age=af["age"],
            eligible_age=af["age"].clip(18, 65),
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌──────────────┬──────────────┬──────────────┐
        │ applicant_id ┆ original_age ┆ eligible_age │
        │ ---          ┆ ---          ┆ ---          │
        │ str          ┆ i64          ┆ i64          │
        ╞══════════════╪══════════════╪══════════════╡
        │ A001         ┆ 16           ┆ 18           │
        │ A002         ┆ 25           ┆ 25           │
        │ A003         ┆ 35           ┆ 35           │
        │ A004         ┆ 70           ┆ 65           │
        │ A005         ┆ 85           ┆ 65           │
        └──────────────┴──────────────┴──────────────┘
        ```

        **Vector Example: Claim Amount Limits**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "age": [35, 42],
            "month": [
                [1, 2, 3, 4],
                [1, 2, 3, 4]
            ],
            "claim_amounts": [
                [5000.0, 150000.0, 25000.0, 500000.0],
                [8000.0, 75000.0, 120000.0, 45000.0]
            ]
        }
        af = ActuarialFrame(data)

        af["capped_claims"] = af["claim_amounts"].clip(10000.0, 100000.0)

        print(af.collect())
        ```

        ```text
        shape: (2, 5)
        ┌───────────┬─────┬─────────────┬────────────────────────────────┬─────────────────────────────────┐
        │ policy_id ┆ age ┆ month       ┆ claim_amounts                  ┆ capped_claims                   │
        │ ---       ┆ --- ┆ ---         ┆ ---                            ┆ ---                             │
        │ str       ┆ i64 ┆ list[i64]   ┆ list[f64]                      ┆ list[f64]                       │
        ╞═══════════╪═════╪═════════════╪════════════════════════════════╪═════════════════════════════════╡
        │ P001      ┆ 35  ┆ [1, 2, … 4] ┆ [5000.0, 150000.0, … 500000.0] ┆ [10000.0, 100000.0, … 100000.0] │
        │ P002      ┆ 42  ┆ [1, 2, … 4] ┆ [8000.0, 75000.0, … 45000.0]   ┆ [10000.0, 75000.0, … 45000.0]   │
        └───────────┴─────┴─────────────┴────────────────────────────────┴─────────────────────────────────┘
        ```
        """
    def cast(self, dtype: PolarsDataType, *, strict: bool = True) -> ExpressionProxy:
        """Cast values in this expression to a different data type.

        Converts the data type of values in the column or expression to the specified
        target type. This is essential for ensuring data consistency, preparing data
        for calculations, and meeting specific type requirements in actuarial analysis.

        !!! note "When to use"
            * **Data Type Alignment:** Convert integer policy numbers to strings for
              concatenation, or string amounts to numeric types for calculations.
            * **Precision Control:** Cast floating-point values to specific decimal
              precision for financial calculations and regulatory reporting.
            * **Date/Time Handling:** Convert string dates to proper date types for
              temporal analysis and policy duration calculations.
            * **Memory Optimization:** Cast large integers to smaller types when range
              permits, reducing memory usage for large datasets.
            * **API Compatibility:** Ensure data types match requirements of external
              systems, databases, or regulatory reporting formats.
            * **Calculation Preparation:** Convert string percentages to decimals,
              or ensure all monetary amounts are in consistent numeric formats.

        Parameters
        ----------
        dtype : PolarsDataType
            Target data type to cast to (e.g., pl.Float64, pl.String, pl.Date).
        strict : bool, default True
            If True, raises an error when conversion fails. If False, returns null
            for values that cannot be converted.

        Returns
        -------
        ExpressionProxy
            An expression with values cast to the specified data type.

        Examples
        --------
        **Scalar Example: Convert String Policy Numbers to Integers**

        ```python
        from gaspatchio_core import ActuarialFrame
        import polars as pl

        data = {
            "policy_number": ["1001", "1002", "1003", "1004"],
            "premium": [1200.0, 1500.0, 800.0, 2000.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_number"].cast(pl.Int64).alias("policy_id"), af["premium"]
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌───────────┬─────────┐
        │ policy_id ┆ premium │
        │ ---       ┆ ---     │
        │ i64       ┆ f64     │
        ╞═══════════╪═════════╡
        │ 1001      ┆ 1200.0  │
        │ 1002      ┆ 1500.0  │
        │ 1003      ┆ 800.0   │
        │ 1004      ┆ 2000.0  │
        └───────────┴─────────┘
        ```

        **Vector Example: Cast Premium Rates to Higher Precision**

        ```python
        from gaspatchio_core import ActuarialFrame
        import polars as pl

        data = {
            "age_group": ["25-35", "36-45", "46-55", "56-65"],
            "mortality_rate": [0.001, 0.002, 0.004, 0.008],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["age_group"],
            precise_rate=af["mortality_rate"].cast(pl.Decimal(precision=10, scale=6))
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌───────────┬───────────────┐
        │ age_group ┆ precise_rate  │
        │ ---       ┆ ---           │
        │ str       ┆ decimal[10,6] │
        ╞═══════════╪═══════════════╡
        │ 25-35     ┆ 0.001000      │
        │ 36-45     ┆ 0.002000      │
        │ 46-55     ┆ 0.004000      │
        │ 56-65     ┆ 0.008000      │
        └───────────┴───────────────┘
        ```
        """
    def sum(self) -> ExpressionProxy: ...
    def cum_prod(self, *, reverse: bool = False) -> ExpressionProxy:
        """Compute the cumulative product of numeric values.

        Returns the cumulative product of all values in order, with each position
        containing the product of all values up to and including that position.
        Essential for compound interest calculations, premium accumulation, and
        mortality probability chains in actuarial modeling.

        !!! note "When to use"
            * **Compound Interest Calculations:** Calculate accumulated values where
                each period's interest compounds with previous periods.
            * **Mortality Probability Chains:** Compute survival probabilities by
                multiplying individual period survival rates sequentially.
            * **Premium Growth Factors:** Track how premiums grow when multiple
                rate increases are applied consecutively over policy years.
            * **Investment Return Accumulation:** Calculate portfolio values when
                multiple investment returns compound over time.
            * **Discount Factor Chains:** Build discount factor sequences for
                present value calculations across multiple time periods.

        Parameters
        ----------
        reverse : bool, default False
            When True, computes the cumulative product in reverse order.

        Returns
        -------
        ExpressionProxy
            An expression containing the cumulative product values.

        Examples
        --------
        **Scalar Example: Interest Rate Accumulation**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "year": [1, 2, 3, 4],
            "interest_rate": [1.03, 1.025, 1.04, 1.035],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["year"],
            af["interest_rate"],
            cumulative_factor=af["interest_rate"].cum_prod(),
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 3)
        ┌──────┬───────────────┬───────────────────┐
        │ year ┆ interest_rate ┆ cumulative_factor │
        │ ---  ┆ ---           ┆ ---               │
        │ i64  ┆ f64           ┆ f64               │
        ╞══════╪═══════════════╪═══════════════════╡
        │ 1    ┆ 1.03          ┆ 1.03              │
        │ 2    ┆ 1.025         ┆ 1.05575           │
        │ 3    ┆ 1.04          ┆ 1.09798           │
        │ 4    ┆ 1.035         ┆ 1.1364093         │
        └──────┴───────────────┴───────────────────┘
        ```

        **Vector Example: Survival Probability Chains**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "age": [55, 38],
            "month": [
                [1, 2, 3, 4],
                [1, 2, 3, 4]
            ],
            "monthly_survival_rate": [
                [0.9995, 0.9994, 0.9993, 0.9992],
                [0.9998, 0.9998, 0.9997, 0.9997]
            ]
        }
        af = ActuarialFrame(data)

        af["cumulative_survival"] = af["monthly_survival_rate"].cum_prod()

        print(af.collect())
        ```

        ```text
        shape: (2, 5)
        ┌───────────┬─────┬─────────────┬────────────────────────────┬─────────────────────────────────┐
        │ policy_id ┆ age ┆ month       ┆ monthly_survival_rate      ┆ cumulative_survival             │
        │ ---       ┆ --- ┆ ---         ┆ ---                        ┆ ---                             │
        │ str       ┆ i64 ┆ list[i64]   ┆ list[f64]                  ┆ list[f64]                       │
        ╞═══════════╪═════╪═════════════╪════════════════════════════╪═════════════════════════════════╡
        │ P001      ┆ 55  ┆ [1, 2, … 4] ┆ [0.9995, 0.9994, … 0.9992] ┆ [0.9995, 0.9989003, … 0.997403] │
        │ P002      ┆ 38  ┆ [1, 2, … 4] ┆ [0.9998, 0.9998, … 0.9997] ┆ [0.9998, 0.9996, … 0.999]       │
        └───────────┴─────┴─────────────┴────────────────────────────┴─────────────────────────────────┘
        ```
        """
    def mean(self) -> ExpressionProxy:
        """Compute the arithmetic mean of numeric values in this expression or column.

        Returns the arithmetic mean (average) of all non-null numeric values. For grouped
        operations, computes the mean within each group. This is a fundamental statistical
        measure used extensively in actuarial analysis for calculating average claim amounts,
        average premiums, or mean mortality rates across different segments.

        !!! note "When to use"
            * **Premium Analysis:** Calculate average premium amounts by policy type,
              age group, or geographic region to understand pricing patterns and
              identify potential underpricing or overpricing scenarios.
            * **Claim Analysis:** Determine mean claim amounts to assess loss ratios,
              set reserves, and evaluate the financial impact of different risk factors.
            * **Mortality Analysis:** Compute average mortality rates across different
              demographic segments to validate actuarial assumptions and pricing models.
            * **Performance Metrics:** Calculate average policy duration, average time
              to claim, or average customer lifetime value for business intelligence.
            * **Risk Assessment:** Determine mean exposure amounts, mean policy values,
              or average risk scores to understand portfolio composition and concentration.
            * **Benchmarking:** Compare mean values against industry standards or
              historical performance to evaluate competitive positioning.

        Returns
        -------
        ExpressionProxy
            An expression representing the mean value. If used in a `select` or
            `with_columns` context without a `group_by` or `over`, this will
            result in a single value. If used within a `group_by` or `over`
            context, it computes the mean per group or window.

        Examples
        --------
        **Scalar Example: Average Premium Amount**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": [1, 2, 3, 4, 5],
            "premium": [1200.0, 1500.0, 800.0, 2000.0, 1100.0],
        }
        af = ActuarialFrame(data)
        avg_premium_expr = af["premium"].mean()
        result = af.with_columns(avg_premium_expr.alias("avg_premium")).collect()
        print(result)
        ```

        ```text
        shape: (1, 1)
        ┌─────────────┐
        │ avg_premium │
        │ ---         │
        │ f64         │
        ╞═════════════╡
        │ 1320.0      │
        └─────────────┘
        ```

        **Vector Example: Average Premium by Policy Type**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "premium": [1200.0, 1500.0, 800.0, 2000.0, 1100.0],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["premium"].mean().alias("avg_premium")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬─────────────┐
        │ policy_type ┆ avg_premium │
        │ ---         ┆ ---         │
        │ str         ┆ f64         │
        ╞═════════════╪═════════════╡
        │ TERM        ┆ 1350.0      │
        │ WHOLE       ┆ 1400.0      │
        │ UL          ┆ 1100.0      │
        └─────────────┴─────────────┘
        ```
        """
    def min(self) -> ExpressionProxy:
        """Find the minimum value in this expression or column.

        Returns the smallest non-null value in a numeric column. For grouped operations,
        computes the minimum within each group. This is essential for actuarial analysis
        to identify floor values, minimum thresholds, or the most favorable outcomes
        across different risk segments or time periods.

        !!! note "When to use"
            * **Risk Analysis:** Find minimum claim amounts, lowest mortality rates,
              or smallest policy values to understand best-case scenarios and floor risks.
            * **Pricing Validation:** Identify minimum premiums charged to ensure they
              meet profitability thresholds and regulatory requirements.
            * **Performance Tracking:** Determine minimum policy durations, shortest
              claim settlement times, or lowest customer satisfaction scores.
            * **Portfolio Analysis:** Find minimum exposure amounts or smallest policy
              sizes to understand concentration risks and diversification levels.
            * **Regulatory Compliance:** Identify minimum reserves, capital requirements,
              or solvency ratios to ensure compliance with regulatory standards.
            * **Benchmarking:** Compare minimum values against industry standards or
              historical performance to evaluate competitive positioning.

        Returns
        -------
        ExpressionProxy
            An expression representing the minimum value. If used in a `select` or
            `with_columns` context without a `group_by` or `over`, this will
            result in a single value. If used within a `group_by` or `over`
            context, it computes the minimum per group or window.

        Examples
        --------
        **Scalar Example: Minimum Claim Amount**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_id": [1, 2, 3, 4, 5],
            "claim_amount": [1200.0, 500.0, 2800.0, 150.0, 3500.0],
        }
        af = ActuarialFrame(data)
        min_claim_expr = af["claim_amount"].min()
        result = af.with_columns(min_claim_expr.alias("min_claim")).collect()
        print(result)
        ```

        ```text
        shape: (1, 1)
        ┌───────────┐
        │ min_claim │
        │ ---       │
        │ f64       │
        ╞═══════════╡
        │ 150.0     │
        └───────────┘
        ```

        **Vector Example: Minimum Premium by Policy Type**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "premium": [1200.0, 800.0, 1500.0, 2000.0, 1100.0],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["premium"].min().alias("min_premium")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬─────────────┐
        │ policy_type ┆ min_premium │
        │ ---         ┆ ---         │
        │ str         ┆ f64         │
        ╞═════════════╪═════════════╡
        │ TERM        ┆ 800.0       │
        │ WHOLE       ┆ 1500.0      │
        │ UL          ┆ 1100.0      │
        └─────────────┴─────────────┘
        ```
        """
    def max(self) -> ExpressionProxy:
        """Find the maximum value in this expression or column.

        Returns the largest non-null value in a numeric column. For grouped operations,
        computes the maximum within each group. This is crucial for actuarial analysis
        to identify peak values, maximum exposures, or worst-case scenarios across
        different risk segments or time periods.

        !!! note "When to use"
            * **Risk Analysis:** Find maximum claim amounts, highest mortality rates,
              or largest policy values to understand worst-case scenarios and tail risks.
            * **Exposure Management:** Identify maximum exposure amounts or largest
              policy concentrations to manage catastrophic risk and reinsurance needs.
            * **Performance Tracking:** Determine maximum policy durations, longest
              claim settlement times, or highest customer satisfaction scores.
            * **Pricing Analysis:** Find maximum premiums charged to validate pricing
              models and ensure competitive positioning in the market.
            * **Regulatory Compliance:** Identify maximum risk concentrations or largest
              exposures to ensure compliance with regulatory capital requirements.
            * **Portfolio Optimization:** Find maximum returns, highest profit margins,
              or best-performing segments for strategic decision making.

        Returns
        -------
        ExpressionProxy
            An expression representing the maximum value. If used in a `select` or
            `with_columns` context without a `group_by` or `over`, this will
            result in a single value. If used within a `group_by` or `over`
            context, it computes the maximum per group or window.

        Examples
        --------
        **Scalar Example: Maximum Claim Amount**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_id": [1, 2, 3, 4, 5],
            "claim_amount": [1200.0, 500.0, 2800.0, 150.0, 3500.0],
        }
        af = ActuarialFrame(data)
        max_claim_expr = af["claim_amount"].max()
        result = af.with_columns(max_claim_expr.alias("max_claim")).collect()
        print(result)
        ```

        ```text
        shape: (1, 1)
        ┌───────────┐
        │ max_claim │
        │ ---       │
        │ f64       │
        ╞═══════════╡
        │ 3500.0    │
        └───────────┘
        ```

        **Vector Example: Maximum Premium by Policy Type**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "premium": [1200.0, 800.0, 1500.0, 2000.0, 1100.0],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["premium"].max().alias("max_premium")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬─────────────┐
        │ policy_type ┆ max_premium │
        │ ---         ┆ ---         │
        │ str         ┆ f64         │
        ╞═════════════╪═════════════╡
        │ TERM        ┆ 1200.0      │
        │ WHOLE       ┆ 2000.0      │
        │ UL          ┆ 1100.0      │
        └─────────────┴─────────────┘
        ```
        """
    def count(self) -> ExpressionProxy:
        """Count the number of non-null values in this expression or column.

        Returns the count of non-null values in the column. For grouped operations,
        computes the count within each group. This is fundamental for actuarial analysis
        to understand data completeness, calculate exposure counts, and determine sample
        sizes for statistical analysis and regulatory reporting.

        !!! note "When to use"
            * **Data Quality Assessment:** Count non-null values to assess data
              completeness and identify missing information that might affect analysis.
            * **Exposure Calculation:** Count the number of policies, claims, or lives
              exposed to risk for rate calculations and reserve estimations.
            * **Sample Size Analysis:** Determine sample sizes for statistical significance
              testing and confidence interval calculations in actuarial studies.
            * **Regulatory Reporting:** Count policies, claims, or transactions for
              regulatory filings and compliance reporting requirements.
            * **Business Intelligence:** Count active policies, new business, lapses,
              or claims by various dimensions for management reporting.
            * **Risk Segmentation:** Count observations in different risk categories
              to ensure adequate sample sizes for credible rate calculations.

        Returns
        -------
        ExpressionProxy
            An expression representing the count of non-null values. If used in a
            `select` or `with_columns` context without a `group_by` or `over`, this
            will result in a single value. If used within a `group_by` or `over`
            context, it computes the count per group or window.

        Examples
        --------
        **Scalar Example: Total Number of Valid Claims**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_id": [1, 2, 3, 4, 5],
            "claim_amount": [1200.0, None, 2800.0, 150.0, None],
        }
        af = ActuarialFrame(data)
        count_claims_expr = af["claim_amount"].count()
        result = af.with_columns(count_claims_expr.alias("valid_claims")).collect()
        print(result)
        ```

        ```text
        shape: (1, 1)
        ┌──────────────┐
        │ valid_claims │
        │ ---          │
        │ u32          │
        ╞══════════════╡
        │ 3            │
        └──────────────┘
        ```

        **Vector Example: Policy Count by Product Type**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "policy_id": ["P001", "P002", None, "P004", "P005"],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["policy_id"].count().alias("policy_count")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬──────────────┐
        │ policy_type ┆ policy_count │
        │ ---         ┆ ---          │
        │ str         ┆ u32          │
        ╞═════════════╪══════════════╡
        │ TERM        ┆ 2            │
        │ WHOLE       ┆ 1            │
        │ UL          ┆ 1            │
        └─────────────┴──────────────┘
        ```
        """
    def is_null(self) -> ExpressionProxy:
        """Check which values are null (missing) in this expression or column.

        Returns a boolean expression indicating which values are null/missing.
        This is essential for data quality assessment, missing data analysis,
        and implementing conditional logic based on data availability in
        actuarial datasets.

        !!! note "When to use"
            * **Data Quality Checks:** Identify missing premium payments, incomplete
              policy information, or missing claim details for data validation.
            * **Conditional Logic:** Create business rules that handle missing data
              differently, such as excluding incomplete records from calculations.
            * **Missing Data Analysis:** Assess patterns of missingness across
              different variables to understand data collection issues.
            * **Regulatory Compliance:** Identify incomplete records that may need
              special handling for regulatory reporting requirements.
            * **Risk Assessment:** Flag policies or claims with missing critical
              information that might require manual review or adjustment.
            * **Data Imputation:** Identify which values need imputation or
              estimation before performing actuarial calculations.

        Returns
        -------
        ExpressionProxy
            An expression containing boolean values indicating whether each
            value in the original expression is null (True) or not null (False).

        Examples
        --------
        **Scalar Example: Identifying Missing Claim Amounts**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_id": ["C001", "C002", "C003", "C004"],
            "claim_amount": [1200.0, None, 2800.0, None],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["claim_id"], missing_amount=af["claim_amount"].is_null()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌──────────┬────────────────┐
        │ claim_id ┆ missing_amount │
        │ ---      ┆ ---            │
        │ str      ┆ bool           │
        ╞══════════╪════════════════╡
        │ C001     ┆ false          │
        │ C002     ┆ true           │
        │ C003     ┆ false          │
        │ C004     ┆ true           │
        └──────────┴────────────────┘
        ```

        **Vector Example: Count Missing Values by Policy Type**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "beneficiary": ["John Doe", None, "Jane Smith", None, "Bob Wilson"],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["beneficiary"].is_null().sum().alias("missing_beneficiary_count")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬──────────────────────────┐
        │ policy_type ┆ missing_beneficiary_count │
        │ ---         ┆ ---                      │
        │ str         ┆ u32                      │
        ╞═════════════╪══════════════════════════╡
        │ TERM        ┆ 1                        │
        │ WHOLE       ┆ 1                        │
        │ UL          ┆ 0                        │
        └─────────────┴──────────────────────────┘
        ```
        """
    def fill_null(
        self,
        value: Any = None,
        *,
        strategy: str = None,
        limit: int = None,
    ) -> ExpressionProxy:
        """Replace null (missing) values with a specified value or using a filling strategy.

        Replaces all null values in the expression with the provided value or using
        a specified strategy like forward fill, backward fill, or statistical measures.
        This is crucial for data preprocessing in actuarial analysis, ensuring
        calculations can proceed without interruption from missing data while
        maintaining analytical integrity through appropriate imputation strategies.

        !!! note "When to use"
            * **Data Imputation:** Replace missing claim amounts with zeros,
              missing policy values with defaults, or missing dates with
              standard values for consistent calculations.
            * **Time Series Filling:** Use forward or backward fill strategies
              for missing premium payments, policy status updates, or claim dates.
            * **Statistical Imputation:** Fill missing values with mean, median,
              or other statistical measures appropriate for actuarial modeling.
            * **Default Value Assignment:** Set default beneficiaries, standard
              premium frequencies, or default coverage amounts for incomplete records.
            * **Regulatory Compliance:** Ensure all required fields have values
              for regulatory reporting, using appropriate defaults where permissible.
            * **Risk Calculations:** Replace missing risk factors with conservative
              estimates or industry averages to avoid excluding policies from analysis.

        Parameters
        ----------
        value : Any, optional
            The value to use as replacement for null values. Can be a scalar value,
            a Polars expression, or another column reference. Cannot be used with strategy.
        strategy : str, optional
            Strategy for filling null values. Options include 'forward', 'backward',
            'min', 'max', 'mean', 'zero', 'one'. Cannot be used with value.
        limit : int, optional
            Maximum number of consecutive null values to fill. Only applies when
            using strategy-based filling.

        Returns
        -------
        ExpressionProxy
            An expression with null values replaced according to the specified method.

        Examples
        --------
        **Scalar Example: Fill Missing Claim Amounts with Zero**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "claim_amount": [1200.0, None, 2800.0, None],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_id"], claim_amount_filled=af["claim_amount"].fill_null(0.0)
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌───────────┬─────────────────────┐
        │ policy_id ┆ claim_amount_filled │
        │ ---       ┆ ---                 │
        │ str       ┆ f64                 │
        ╞═══════════╪═════════════════════╡
        │ P001      ┆ 1200.0              │
        │ P002      ┆ 0.0                 │
        │ P003      ┆ 2800.0              │
        │ P004      ┆ 0.0                 │
        └───────────┴─────────────────────┘
        ```

        **Vector Example: Fill Missing Premium Payments with Forward Fill Strategy**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "month": [1, 2, 3, 4, 5, 6],
            "premium_received": [1200.0, 1200.0, None, None, 1200.0, None],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["month"],
            original_premium=af["premium_received"],
            forward_filled=af["premium_received"].fill_null(strategy="forward"),
            zero_filled=af["premium_received"].fill_null(0.0)
        ).collect()
        print(result)
        ```

        ```text
        shape: (6, 4)
        ┌───────┬──────────────────┬────────────────┬─────────────┐
        │ month ┆ original_premium ┆ forward_filled ┆ zero_filled │
        │ ---   ┆ ---              ┆ ---            ┆ ---         │
        │ i64   ┆ f64              ┆ f64            ┆ f64         │
        ╞═══════╪══════════════════╪════════════════╪═════════════╡
        │ 1     ┆ 1200.0           ┆ 1200.0         ┆ 1200.0      │
        │ 2     ┆ 1200.0           ┆ 1200.0         ┆ 1200.0      │
        │ 3     ┆ null             ┆ 1200.0         ┆ 0.0         │
        │ 4     ┆ null             ┆ 1200.0         ┆ 0.0         │
        │ 5     ┆ 1200.0           ┆ 1200.0         ┆ 1200.0      │
        │ 6     ┆ null             ┆ 1200.0         ┆ 0.0         │
        └───────┴──────────────────┴────────────────┴─────────────┘
        ```
        """
    def unique(self) -> ExpressionProxy:
        """Return unique values from this expression or column.

        Extracts distinct values, removing duplicates while preserving order of first occurrence.
        This is fundamental for data exploration, creating lookup tables, and identifying unique
        categories in actuarial datasets for segmentation and analysis purposes.

        !!! note "When to use"
            * **Data Exploration:** Identify unique policy types, product codes, or geographic
              regions to understand portfolio composition and coverage diversity.
            * **Reference Data Creation:** Extract unique values to create lookup tables,
              validation lists, or categorical mappings for data standardization.
            * **Portfolio Segmentation:** Find distinct risk categories, age bands, or
              coverage levels for actuarial analysis and pricing model development.
            * **Quality Assurance:** Verify expected categorical values and identify
              unexpected or erroneous entries in key classification fields.
            * **Regulatory Reporting:** Create lists of unique jurisdictions, product lines,
              or regulatory categories for compliance reporting requirements.
            * **Business Intelligence:** Generate unique customer segments, distribution
              channels, or sales territories for strategic analysis and planning.

        Returns
        -------
        ExpressionProxy
            An expression containing unique values in order of first appearance.
            If used within group_by context, returns unique values per group.

        Examples
        --------
        **Scalar Example: Unique Policy Types**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": [1, 2, 3, 4, 5, 6],
            "policy_type": ["TERM", "WHOLE", "TERM", "UL", "WHOLE", "TERM"],
        }
        af = ActuarialFrame(data)
        result = af.select(unique_types=af["policy_type"].unique()).collect()
        print(result)
        ```

        ```text
        shape: (3, 1)
        ┌──────────────┐
        │ unique_types │
        │ ---          │
        │ str          │
        ╞══════════════╡
        │ UL           │
        │ WHOLE        │
        │ TERM         │
        └──────────────┘
        ```

        **Vector Example: Unique Ages by Policy Type**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL", "UL"],
            "age": [35, 42, 35, 58, 42, 67],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["age"].unique().alias("unique_ages")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬─────────────┐
        │ policy_type ┆ unique_ages │
        │ ---         ┆ ---         │
        │ str         ┆ list[i64]   │
        ╞═════════════╪═════════════╡
        │ TERM        ┆ [35, 42]    │
        │ WHOLE       ┆ [35, 58]    │
        │ UL          ┆ [42, 67]    │
        └─────────────┴─────────────┘
        ```
        """
    def sort(self, *, descending: bool = False) -> ExpressionProxy:
        """Sort values in this expression or column.

        Arranges values in ascending or descending order, maintaining positional relationships
        with other columns when used in select contexts. Essential for ranking analysis,
        identifying top/bottom performers, and creating ordered datasets for actuarial reporting.

        !!! note "When to use"
            * **Risk Ranking:** Sort policies by claim amounts, risk scores, or premium
              values to identify highest exposure cases requiring special attention.
            * **Performance Analysis:** Order sales agents by production volume, policies
              by profitability, or claims by settlement time for performance evaluation.
            * **Regulatory Reporting:** Create sorted lists of largest policies, highest
              reserves, or top risk concentrations for regulatory compliance.
            * **Portfolio Management:** Sort by policy expiration dates, renewal dates,
              or premium due dates for operational scheduling and cash flow planning.
            * **Statistical Analysis:** Order data for percentile calculations, trend
              analysis, or creating cumulative distribution functions.
            * **Customer Segmentation:** Sort customers by lifetime value, claim frequency,
              or policy tenure for targeted marketing and retention strategies.

        Parameters
        ----------
        descending : bool, default False
            If True, sort in descending order (largest to smallest).
            If False, sort in ascending order (smallest to largest).

        Returns
        -------
        ExpressionProxy
            An expression with values sorted according to the specified order.
            When used in group_by context, sorts values within each group.

        Examples
        --------
        **Scalar Example: Sort Claims by Amount**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_id": ["C001", "C002", "C003", "C004"],
            "claim_amount": [2500.0, 1200.0, 4800.0, 800.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            sorted_amounts=af["claim_amount"].sort(descending=True)
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 1)
        ┌────────────────┐
        │ sorted_amounts │
        │ ---            │
        │ f64            │
        ╞════════════════╡
        │ 4800.0         │
        │ 2500.0         │
        │ 1200.0         │
        │ 800.0          │
        └────────────────┘
        ```

        **Vector Example: Sort Ages within Policy Types**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "age": [45, 32, 58, 41, 62],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["age"].sort().alias("sorted_ages")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬─────────────┐
        │ policy_type ┆ sorted_ages │
        │ ---         ┆ ---         │
        │ str         ┆ list[i64]   │
        ╞═════════════╪═════════════╡
        │ TERM        ┆ [32, 45]    │
        │ WHOLE       ┆ [41, 58]    │
        │ UL          ┆ [62]        │
        └─────────────┴─────────────┘
        ```
        """
    def head(self, n: int = 5) -> ExpressionProxy:
        """Return the first n values from this expression or column.

        Retrieves the top n values in their original order, useful for sampling data,
        previewing datasets, and analyzing leading observations in actuarial analysis.
        Essential for data exploration and creating focused subsets for detailed analysis.

        !!! note "When to use"
            * **Data Sampling:** Preview first few policies, claims, or transactions
              to understand data structure and validate import processes.
            * **Top Performance Analysis:** Extract first n highest-performing policies,
              agents, or products after sorting by relevant metrics.
            * **Time Series Analysis:** Get first n periods of policy data, premium
              payments, or claim events for trend analysis and forecasting.
            * **Quality Control:** Sample first n records from data loads to verify
              format, completeness, and accuracy before full processing.
            * **Reporting Limits:** Create executive summaries showing top n risks,
              largest policies, or most significant claims for management review.
            * **Model Development:** Use first n observations for initial model
              training or validation in actuarial modeling workflows.

        Parameters
        ----------
        n : int, default 5
            Number of values to return from the beginning of the column.
            Must be non-negative.

        Returns
        -------
        ExpressionProxy
            An expression containing the first n values in original order.
            If used within group_by context, returns first n values per group.

        Examples
        --------
        **Scalar Example: First 3 Largest Claims**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_id": ["C001", "C002", "C003", "C004", "C005"],
            "claim_amount": [2500.0, 4800.0, 1200.0, 800.0, 3200.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            top_claims=af["claim_amount"].sort(descending=True).head(3)
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 1)
        ┌────────────┐
        │ top_claims │
        │ ---        │
        │ f64        │
        ╞════════════╡
        │ 4800.0     │
        │ 3200.0     │
        │ 2500.0     │
        └────────────┘
        ```

        **Vector Example: First 2 Ages by Policy Type**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "age": [35, 42, 28, 45, 58, 33],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["age"].head(2).alias("first_ages")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬─────────────┐
        │ policy_type ┆ first_ages  │
        │ ---         ┆ ---         │
        │ str         ┆ list[i64]   │
        ╞═════════════╪═════════════╡
        │ TERM        ┆ [35, 42]    │
        │ WHOLE       ┆ [45, 58]    │
        │ UL          ┆ [33]        │
        └─────────────┴─────────────┘
        ```
        """
    def tail(self, n: int = 5) -> ExpressionProxy:
        """Return the last n values from this expression or column.

        Retrieves the bottom n values in their original order, useful for analyzing
        recent observations, final periods, and ending patterns in actuarial datasets.
        Essential for understanding recent trends and validating data completeness.

        !!! note "When to use"
            * **Recent Analysis:** Extract last n policy renewals, recent claims,
              or latest premium payments to analyze current portfolio trends.
            * **Data Validation:** Check last n records from data loads to ensure
              complete file transmission and proper ending sequences.
            * **Time Series Endings:** Analyze final periods of policy lifecycles,
              claim development patterns, or investment performance cycles.
            * **Quality Control:** Sample last n transactions to verify batch
              processing completeness and identify potential truncation issues.
            * **Performance Tracking:** Review most recent n sales, lapses, or
              claim settlements for current performance assessment.
            * **Model Validation:** Use recent n observations for out-of-time
              testing and model performance evaluation on latest data.

        Parameters
        ----------
        n : int, default 5
            Number of values to return from the end of the column.
            Must be non-negative.

        Returns
        -------
        ExpressionProxy
            An expression containing the last n values in original order.
            If used within group_by context, returns last n values per group.

        Examples
        --------
        **Scalar Example: Last 3 Claims by Amount**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_id": ["C001", "C002", "C003", "C004", "C005"],
            "claim_amount": [2500.0, 4800.0, 1200.0, 800.0, 3200.0],
        }
        af = ActuarialFrame(data)
        result = af.select(recent_claims=af["claim_amount"].tail(3)).collect()
        print(result)
        ```

        ```text
        shape: (3, 1)
        ┌───────────────┐
        │ recent_claims │
        │ ---           │
        │ f64           │
        ╞═══════════════╡
        │ 1200.0        │
        │ 800.0         │
        │ 3200.0        │
        └───────────────┘
        ```

        **Vector Example: Last 2 Ages by Policy Type**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "age": [35, 42, 28, 45, 58, 33],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["age"].tail(2).alias("last_ages")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬───────────┐
        │ policy_type ┆ last_ages │
        │ ---         ┆ ---       │
        │ str         ┆ list[i64] │
        ╞═════════════╪═══════════╡
        │ TERM        ┆ [42, 28]  │
        │ WHOLE       ┆ [45, 58]  │
        │ UL          ┆ [33]      │
        └─────────────┴───────────┘
        ```
        """
    def filter(self, predicate: ExpressionProxy | pl.Expr) -> ExpressionProxy:
        """Filter values based on a boolean condition.

        Selects only values that meet the specified criteria, returning a subset
        of the original data. Essential for subsetting actuarial datasets based
        on business rules, risk criteria, or analytical requirements.

        !!! note "When to use"
            * **Risk Segmentation:** Filter policies by age bands, coverage amounts,
              or risk scores to create homogeneous groups for analysis.
            * **Claim Analysis:** Select claims above certain thresholds, within
              specific date ranges, or meeting particular criteria for investigation.
            * **Regulatory Compliance:** Filter data to meet reporting requirements,
              such as policies above regulatory minimums or within jurisdiction rules.
            * **Performance Analysis:** Select high-performing agents, profitable
              products, or customers meeting specific value criteria.
            * **Data Quality:** Filter out invalid, incomplete, or suspicious records
              before performing actuarial calculations or statistical analysis.
            * **Portfolio Management:** Select policies due for renewal, claims
              requiring review, or customers eligible for specific programs.

        Parameters
        ----------
        predicate : ExpressionProxy | pl.Expr
            Boolean condition used to filter values. Only values where the
            predicate evaluates to True will be included in the result.

        Returns
        -------
        ExpressionProxy
            An expression containing only values that satisfy the predicate.
            When used within group_by context, filters values within each group.

        Examples
        --------
        **Scalar Example: Filter High-Value Claims**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_id": ["C001", "C002", "C003", "C004", "C005"],
            "claim_amount": [2500.0, 4800.0, 1200.0, 800.0, 3200.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            high_claims=af["claim_amount"].filter(af["claim_amount"] > 2000.0)
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 1)
        ┌─────────────┐
        │ high_claims │
        │ ---         │
        │ f64         │
        ╞═════════════╡
        │ 2500.0      │
        │ 4800.0      │
        │ 3200.0      │
        └─────────────┘
        ```

        **Vector Example: Filter Ages by Criteria within Policy Types**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "age": [35, 42, 28, 45, 58, 33],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["age"].filter(af["age"] >= 40).alias("senior_ages")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬─────────────┐
        │ policy_type ┆ senior_ages │
        │ ---         ┆ ---         │
        │ str         ┆ list[i64]   │
        ╞═════════════╪═════════════╡
        │ TERM        ┆ [42]        │
        │ WHOLE       ┆ [45, 58]    │
        │ UL          ┆ []          │
        └─────────────┴─────────────┘
        ```
        """
    def shift(self, n: int = 1, *, fill_value: any = None) -> ExpressionProxy:
        """Shift values by a specified number of periods.

        Moves values forward or backward in the sequence, creating lag or lead variables
        essential for time series analysis, policy lifecycle tracking, and comparative
        calculations in actuarial modeling and trend analysis.

        !!! note "When to use"
            * **Time Series Analysis:** Create lag variables for premium payments,
              claim frequencies, or mortality rates to analyze trends and correlations.
            * **Policy Lifecycle Tracking:** Compare current year values with previous
              years for renewal analysis, lapse prediction, and persistency studies.
            * **Comparative Analysis:** Calculate period-over-period changes in
              reserves, capital requirements, or portfolio performance metrics.
            * **Risk Modeling:** Create lagged risk factors for predictive models,
              such as previous claims history or prior period exposures.
            * **Regulatory Reporting:** Generate comparative figures showing changes
              from previous reporting periods for regulatory filings.
            * **Performance Measurement:** Calculate growth rates, variance analysis,
              and trend indicators using historical comparison periods.

        Parameters
        ----------
        n : int, default 1
            Number of periods to shift. Positive values shift forward (creating lags),
            negative values shift backward (creating leads). Zero returns original values.
        fill_value : any, optional
            Value to use for filling the shifted positions. If None (default), uses null values.
            Can be a scalar value, expression, or column reference.

        Returns
        -------
        ExpressionProxy
            An expression with values shifted by the specified number of periods.
            Shifted positions are filled with the specified fill_value or null values if not provided.

        Examples
        --------
        **Scalar Example: Create Lag Variable for Premium Analysis**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_year": [1, 2, 3, 4, 5],
            "annual_premium": [1200.0, 1260.0, 1323.0, 1389.0, 1458.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_year"],
            current_premium=af["annual_premium"],
            prior_premium=af["annual_premium"].shift(1),
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌─────────────┬─────────────────┬───────────────┐
        │ policy_year ┆ current_premium ┆ prior_premium │
        │ ---         ┆ ---             ┆ ---           │
        │ i64         ┆ f64             ┆ f64           │
        ╞═════════════╪═════════════════╪═══════════════╡
        │ 1           ┆ 1200.0          ┆ null          │
        │ 2           ┆ 1260.0          ┆ 1200.0        │
        │ 3           ┆ 1323.0          ┆ 1260.0        │
        │ 4           ┆ 1389.0          ┆ 1323.0        │
        │ 5           ┆ 1458.0          ┆ 1389.0        │
        └─────────────┴─────────────────┴───────────────┘
        ```

        **Vector Example: Quarterly Claims Comparison with Fill Value**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "quarter": ["Q1", "Q2", "Q3", "Q4"],
            "claim_count": [45, 52, 38, 49],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["quarter"],
            current_claims=af["claim_count"],
            next_quarter_claims=af["claim_count"].shift(-1),
            prior_quarter_with_fill=af["claim_count"].shift(1, fill_value=0)
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 4)
        ┌─────────┬────────────────┬─────────────────────┬─────────────────────────┐
        │ quarter ┆ current_claims ┆ next_quarter_claims ┆ prior_quarter_with_fill │
        │ ---     ┆ ---            ┆ ---                 ┆ ---                     │
        │ str     ┆ i64            ┆ i64                 ┆ i64                     │
        ╞═════════╪════════════════╪═════════════════════╪═════════════════════════╡
        │ Q1      ┆ 45             ┆ 52                  ┆ 0                       │
        │ Q2      ┆ 52             ┆ 38                  ┆ 45                      │
        │ Q3      ┆ 38             ┆ 49                  ┆ 52                      │
        │ Q4      ┆ 49             ┆ null                ┆ 38                      │
        └─────────┴────────────────┴─────────────────────┴─────────────────────────┘
        ```
        """
    def over(
        self,
        partition_by: str | list[str] | pl.Expr | list[pl.Expr],
        *,
        mapping_strategy: str = "join",
    ) -> ExpressionProxy:
        """Apply window function over partitions defined by grouping columns.

        Performs calculations within groups while maintaining the original row structure,
        enabling sophisticated analytical computations like running totals, rankings,
        and comparative metrics essential for actuarial analysis and portfolio management.

        !!! note "When to use"
            * **Running Calculations:** Compute cumulative premiums, running claim totals,
              or progressive reserves within policy groups or time periods.
            * **Ranking Analysis:** Rank policies by premium size, claims by amount,
              or agents by performance within their respective categories.
            * **Comparative Metrics:** Calculate percentiles, relative positions, or
              comparative ratios within peer groups for benchmarking analysis.
            * **Window Statistics:** Compute rolling averages, moving sums, or
              time-based aggregations within policy or customer segments.
            * **Portfolio Analytics:** Calculate portfolio-level metrics while
              maintaining individual policy detail for drill-down analysis.
            * **Regulatory Reporting:** Generate group-level statistics required
              for regulatory filings while preserving transaction-level detail.

        Parameters
        ----------
        partition_by : str | list[str] | pl.Expr | list[pl.Expr]
            Column(s) or expression(s) defining the partitions (groups) for window
            calculations. Each unique combination creates a separate partition.
        mapping_strategy : str, default "join"
            Strategy for mapping results back to original rows. "join" maintains
            original DataFrame structure with computed values.

        Returns
        -------
        ExpressionProxy
            An expression with window function results mapped to each row based
            on its partition membership.

        Examples
        --------
        **Scalar Example: Running Premium Total by Policy Type**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "TERM"],
            "premium": [1200.0, 1500.0, 2000.0, 2200.0, 1100.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_type"],
            af["premium"],
            running_total=af["premium"].sum().over("policy_type"),
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌─────────────┬─────────┬───────────────┐
        │ policy_type ┆ premium ┆ running_total │
        │ ---         ┆ ---     ┆ ---           │
        │ str         ┆ f64     ┆ f64           │
        ╞═════════════╪═════════╪═══════════════╡
        │ TERM        ┆ 1200.0  ┆ 3800.0        │
        │ TERM        ┆ 1500.0  ┆ 3800.0        │
        │ WHOLE       ┆ 2000.0  ┆ 4200.0        │
        │ WHOLE       ┆ 2200.0  ┆ 4200.0        │
        │ TERM        ┆ 1100.0  ┆ 3800.0        │
        └─────────────┴─────────┴───────────────┘
        ```

        **Vector Example: Rank Claims within Age Groups**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "age_band": ["30-39", "30-39", "40-49", "40-49", "30-39"],
            "claim_amount": [1200.0, 2500.0, 1800.0, 3200.0, 900.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["age_band"],
            af["claim_amount"],
            rank_in_band=af["claim_amount"].rank(method="ordinal").over("age_band")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌──────────┬──────────────┬──────────────┐
        │ age_band ┆ claim_amount ┆ rank_in_band │
        │ ---      ┆ ---          ┆ ---          │
        │ str      ┆ f64          ┆ u32          │
        ╞══════════╪══════════════╪══════════════╡
        │ 30-39    ┆ 1200.0       ┆ 2            │
        │ 30-39    ┆ 2500.0       ┆ 3            │
        │ 40-49    ┆ 1800.0       ┆ 1            │
        │ 40-49    ┆ 3200.0       ┆ 2            │
        │ 30-39    ┆ 900.0        ┆ 1            │
        └──────────┴──────────────┴──────────────┘
        ```
        """
    def when(self, *predicates: ExpressionProxy | pl.Expr) -> ExpressionProxy:
        """Begin a conditional expression chain with specified conditions.

        Creates conditional logic for data transformations, allowing different values
        or calculations based on business rules, risk criteria, or regulatory requirements.
        Essential for implementing actuarial business logic and data categorization.

        !!! note "When to use"
            * **Risk Classification:** Assign risk categories based on age, coverage
              amounts, medical conditions, or other underwriting criteria.
            * **Premium Adjustments:** Apply different pricing rules based on policy
              characteristics, geographic regions, or customer segments.
            * **Regulatory Compliance:** Implement jurisdiction-specific rules,
              reporting categories, or regulatory capital requirements.
            * **Business Rules:** Apply company-specific logic for claim processing,
              policy renewals, or customer eligibility determinations.
            * **Data Categorization:** Group policies, claims, or customers into
              meaningful segments for analysis and reporting purposes.
            * **Exception Handling:** Identify and handle special cases, outliers,
              or data quality issues requiring different treatment.

        Parameters
        ----------
        *predicates : ExpressionProxy | pl.Expr
            One or more boolean conditions to evaluate. Multiple predicates are
            combined with logical AND operation.

        Returns
        -------
        ExpressionProxy
            An expression that can be chained with .then() to specify the value
            when conditions are met, and optionally .otherwise() for default values.

        Examples
        --------
        **Scalar Example: Age-Based Premium Loading**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "age": [25, 45, 65, 75],
            "base_premium": [1000.0, 1200.0, 1500.0, 1800.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_id"],
            af["age"],
            loading_factor=af["age"].when(af["age"] >= 65).then(1.25).otherwise(1.0),
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 3)
        ┌───────────┬─────┬────────────────┐
        │ policy_id ┆ age ┆ loading_factor │
        │ ---       ┆ --- ┆ ---            │
        │ str       ┆ i64 ┆ f64            │
        ╞═══════════╪═════╪════════════════╡
        │ P001      ┆ 25  ┆ 1.0            │
        │ P002      ┆ 45  ┆ 1.0            │
        │ P003      ┆ 65  ┆ 1.25           │
        │ P004      ┆ 75  ┆ 1.25           │
        └───────────┴─────┴────────────────┘
        ```

        **Vector Example: Multi-Condition Risk Classification**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "WHOLE", "UL", "TERM", "WHOLE"],
            "sum_assured": [100000, 500000, 250000, 750000, 1000000],
            "age": [35, 45, 55, 65, 40],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_type"],
            af["sum_assured"],
            af["age"],
            risk_class=af["age"].when(
                (af["age"] >= 60) & (af["sum_assured"] >= 500000)
            ).then("HIGH").when(
                af["age"] >= 50
            ).then("MEDIUM").otherwise("STANDARD")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 4)
        ┌─────────────┬─────────────┬─────┬────────────┐
        │ policy_type ┆ sum_assured ┆ age ┆ risk_class │
        │ ---         ┆ ---         ┆ --- ┆ ---        │
        │ str         ┆ i64         ┆ i64 ┆ str        │
        ╞═════════════╪═════════════╪═════╪════════════╡
        │ TERM        ┆ 100000      ┆ 35  ┆ STANDARD   │
        │ WHOLE       ┆ 500000      ┆ 45  ┆ STANDARD   │
        │ UL          ┆ 250000      ┆ 55  ┆ MEDIUM     │
        │ TERM        ┆ 750000      ┆ 65  ┆ HIGH       │
        │ WHOLE       ┆ 1000000     ┆ 40  ┆ STANDARD   │
        └─────────────┴─────────────┴─────┴────────────┘
        ```
        """
    def then(self, expr: Any) -> ExpressionProxy:
        """Specify the value to return when the preceding when() condition is true.

        Defines the result value for rows that meet the conditional criteria specified
        in the preceding when() clause. Essential for implementing conditional business
        logic and data transformations in actuarial analysis.

        !!! note "When to use"
            * **Conditional Values:** Set specific values, calculations, or categories
              when business rules or risk criteria are satisfied.
            * **Premium Calculations:** Apply loading factors, discounts, or adjustments
              based on policy characteristics or risk assessments.
            * **Data Transformation:** Convert raw data into meaningful business categories
              or standardized values for reporting and analysis.
            * **Business Logic Implementation:** Execute specific calculations or
              assignments when regulatory, underwriting, or operational conditions are met.
            * **Risk Management:** Apply risk-specific treatments, reserves, or
              capital requirements based on exposure characteristics.
            * **Categorization:** Assign categorical values like risk classes, product
              types, or regulatory segments based on defined criteria.

        Parameters
        ----------
        expr : Any
            The value, expression, or calculation to return when the when() condition
            evaluates to True. Can be a scalar, another column, or complex expression.

        Returns
        -------
        ExpressionProxy
            An expression that can be further chained with additional when().then()
            clauses or concluded with otherwise() for default handling.

        Examples
        --------
        **See when() method for complete examples of conditional logic chains.**

        This method is always used in conjunction with when() and optionally otherwise():

        ```python # no_lint no_output_check
        # Basic pattern
        result = column.when(condition).then(value_if_true).otherwise(value_if_false)

        # Chained conditions
        result = (
            column.when(condition1)
            .then(value1)
            .when(condition2)
            .then(value2)
            .otherwise(default)
        )
        ```

        """
    def otherwise(self, expr: Any) -> ExpressionProxy:
        """Specify the default value when no preceding when() conditions are met.

        Provides the fallback value for rows that don't satisfy any of the conditional
        criteria in the when().then() chain. Essential for ensuring complete coverage
        in conditional logic and preventing null values in business rule implementations.

        !!! note "When to use"
            * **Default Values:** Provide standard values for cases that don't meet
              specific conditional criteria, ensuring complete data coverage.
            * **Fallback Logic:** Implement conservative assumptions or industry
              standard values when specific conditions don't apply.
            * **Risk Management:** Apply default risk classifications, reserve levels,
              or capital requirements for standard cases not requiring special treatment.
            * **Regulatory Compliance:** Ensure all records have appropriate values
              for regulatory reporting, using standard categories where specific rules don't apply.
            * **Data Completeness:** Prevent null values in derived calculations
              by providing meaningful defaults for unmatched conditions.
            * **Business Continuity:** Implement standard business practices for
              cases not covered by specific policies or procedures.

        Parameters
        ----------
        expr : Any
            The default value, expression, or calculation to return when none of the
            preceding when() conditions evaluate to True. Can be a scalar, column, or expression.

        Returns
        -------
        ExpressionProxy
            An expression containing the result of the complete conditional logic chain,
            with appropriate values for all possible cases.

        Examples
        --------
        **See when() method for complete examples of conditional logic chains.**

        This method concludes a conditional chain started with when().then():

        ```python # no_lint no_output_check
        # Complete conditional logic
        result = af.select(
            category=af["value"]
            .when(af["value"] > 1000)
            .then("HIGH")
            .when(af["value"] > 500)
            .then("MEDIUM")
            .otherwise("LOW")
        )

        # With default calculation
        adjusted_amount = (
            af["amount"]
            .when(af["special_case"])
            .then(af["amount"] * 1.2)
            .otherwise(af["amount"])
        )
        ```

        """

    # --- Autopatched Unary Numeric Methods (Returning ExpressionProxy) ---
    def abs(self) -> ExpressionProxy:
        """Compute the absolute value of numeric values in this expression or column.

        Returns the absolute value (magnitude) of all numeric values, converting
        negative values to positive while leaving positive values unchanged.
        This is essential in actuarial analysis for calculating differences,
        deviations, and ensuring positive values for regulatory calculations.

        !!! note "When to use"
            * **Loss Calculations:** Convert negative claim adjustments or refunds
              to positive values for loss ratio calculations and reserve analysis.
            * **Variance Analysis:** Calculate absolute deviations from expected
              values, budgets, or actuarial assumptions for performance measurement.
            * **Risk Metrics:** Compute absolute differences between actual and
              expected mortality, lapse rates, or investment returns.
            * **Data Validation:** Ensure all monetary amounts are positive for
              regulatory reporting where negative values are not permitted.
            * **Model Calibration:** Calculate absolute errors between model
              predictions and actual outcomes for model validation.
            * **Reinsurance Calculations:** Convert negative ceding commission
              adjustments to positive values for treaty accounting.

        Returns
        -------
        ExpressionProxy
            An expression containing the absolute values of the input.
            All negative values become positive, positive values remain unchanged.

        Examples
        --------
        **Scalar Example: Absolute Claim Adjustments**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_id": ["C001", "C002", "C003", "C004"],
            "adjustment_amount": [150.0, -75.0, 200.0, -50.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["claim_id"], abs_adjustment=af["adjustment_amount"].abs()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌──────────┬────────────────┐
        │ claim_id ┆ abs_adjustment │
        │ ---      ┆ ---            │
        │ str      ┆ f64            │
        ╞══════════╪════════════════╡
        │ C001     ┆ 150.0          │
        │ C002     ┆ 75.0           │
        │ C003     ┆ 200.0          │
        │ C004     ┆ 50.0           │
        └──────────┴────────────────┘
        ```

        **Vector Example: Portfolio Variance Analysis**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "WHOLE", "UL", "TERM", "WHOLE"],
            "actual_vs_expected": [0.05, -0.03, 0.08, -0.02, 0.04],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["actual_vs_expected"].abs().mean().alias("avg_abs_variance")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌─────────────┬──────────────────┐
        │ policy_type ┆ avg_abs_variance │
        │ ---         ┆ ---              │
        │ str         ┆ f64              │
        ╞═════════════╪══════════════════╡
        │ TERM        ┆ 0.035            │
        │ WHOLE       ┆ 0.035            │
        │ UL          ┆ 0.08             │
        └─────────────┴──────────────────┘
        ```
        """
    def sign(self) -> ExpressionProxy:
        """Compute the sign of numeric values.

        Returns the mathematical sign of each value: 1 for positive, -1 for negative,
        and 0 for zero. Essential for directional analysis, variance decomposition,
        and understanding the nature of financial movements in actuarial datasets.

        !!! note "When to use"
            * **Directional Analysis:** Identify positive vs negative movements in
              claims experience, premium adjustments, or reserve changes.
            * **Performance Assessment:** Classify gains and losses, profit vs loss
              periods, or favorable vs unfavorable variance components.
            * **Risk Classification:** Categorize exposure changes, mortality deviations,
              or investment return directions for risk management analysis.
            * **Trend Analysis:** Identify periods of growth vs decline in policy
              counts, premium volumes, or claim frequencies.
            * **Model Validation:** Analyze residual patterns, prediction errors,
              or model bias detection through directional indicators.
            * **Financial Analysis:** Categorize cash flows, investment returns,
              or expense variances by their directional impact.

        Returns
        -------
        ExpressionProxy
            An expression containing 1.0 for positive values, -1.0 for negative values,
            and 0.0 for zero values. NaN values remain NaN.

        Examples
        --------
        **Scalar Example: Claims Experience Direction**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "period": ["Q1", "Q2", "Q3", "Q4"],
            "claims_variance": [150.0, -75.0, 0.0, -200.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["period"], af["claims_variance"], direction=af["claims_variance"].sign()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 3)
        ┌────────┬─────────────────┬───────────┐
        │ period ┆ claims_variance ┆ direction │
        │ ---    ┆ ---             ┆ ---       │
        │ str    ┆ f64             ┆ f64       │
        ╞════════╪═════════════════╪═══════════╡
        │ Q1     ┆ 150.0           ┆ 1.0       │
        │ Q2     ┆ -75.0           ┆ -1.0      │
        │ Q3     ┆ 0.0             ┆ 0.0       │
        │ Q4     ┆ -200.0          ┆ -1.0      │
        └────────┴─────────────────┴───────────┘
        ```

        **Vector Example: Investment Return Classification**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "asset_class": ["Bonds", "Equities", "Real Estate", "Cash"],
            "annual_return": [0.035, -0.12, 0.08, 0.002],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["annual_return"].sign().alias("return_direction"),
            af["asset_class"].count().alias("count")
        ).collect()
        print(result)
        ```

        ```text
        shape: (2, 2)
        ┌──────────────────┬───────┐
        │ return_direction ┆ count │
        │ ---              ┆ ---   │
        │ f64              ┆ u32   │
        ╞══════════════════╪═══════╡
        │ -1.0             ┆ 1     │
        │ 1.0              ┆ 3     │
        └──────────────────┴───────┘
        ```
        """
    def floor(self) -> ExpressionProxy:
        """Round numeric values down to the nearest integer.

        Applies floor function to each value, returning the largest integer less than
        or equal to the input. Essential for actuarial calculations requiring conservative
        rounding, age calculations, and regulatory computations with specific rounding rules.

        !!! note "When to use"
            * **Age Calculations:** Convert decimal ages to completed years for
              underwriting, pricing tables, and regulatory age classifications.
            * **Conservative Estimates:** Apply conservative rounding for reserve
              calculations, capital requirements, or risk assessments.
            * **Regulatory Compliance:** Implement specific rounding rules required
              by insurance regulations or accounting standards.
            * **Policy Duration:** Calculate completed policy years or months for
              persistency analysis and commission calculations.
            * **Rate Table Lookups:** Round continuous values to discrete table
              entries for mortality tables, lapse rates, or premium factors.
            * **Financial Calculations:** Apply floor rounding for guaranteed minimum
              benefits, surrender values, or dividend calculations.

        Returns
        -------
        ExpressionProxy
            An expression containing values rounded down to the nearest integer.

        Examples
        --------
        **Scalar Example: Age Calculation**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "age_decimal": [35.8, 42.2, 58.9, 67.1],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_id"], completed_age=af["age_decimal"].floor()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌───────────┬───────────────┐
        │ policy_id ┆ completed_age │
        │ ---       ┆ ---           │
        │ str       ┆ f64           │
        ╞═══════════╪═══════════════╡
        │ P001      ┆ 35.0          │
        │ P002      ┆ 42.0          │
        │ P003      ┆ 58.0          │
        │ P004      ┆ 67.0          │
        └───────────┴───────────────┘
        ```

        **Vector Example: Policy Year Calculation**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "WHOLE", "UL", "ANNUITY"],
            "duration_decimal": [2.3, 5.7, 1.9, 10.4],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_type"],
            completed_years=af["duration_decimal"].floor()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌─────────────┬─────────────────┐
        │ policy_type ┆ completed_years │
        │ ---         ┆ ---             │
        │ str         ┆ f64             │
        ╞═════════════╪═════════════════╡
        │ TERM        ┆ 2.0             │
        │ WHOLE       ┆ 5.0             │
        │ UL          ┆ 1.0             │
        │ ANNUITY     ┆ 10.0            │
        └─────────────┴─────────────────┘
        ```
        """
    def ceil(self) -> ExpressionProxy:
        """Round numeric values up to the nearest integer.

        Applies ceiling function to each value, returning the smallest integer greater than
        or equal to the input. Essential for actuarial calculations requiring conservative
        upward rounding, capacity planning, and regulatory calculations with prudent assumptions.

        !!! note "When to use"
            * **Conservative Estimates:** Apply prudent upward rounding for reserve
              calculations, capital requirements, or risk margin computations.
            * **Capacity Planning:** Round up exposure units, policy counts, or
              resource requirements to ensure adequate capacity and coverage.
            * **Regulatory Compliance:** Implement conservative rounding rules required
              by prudential regulations or solvency frameworks.
            * **Policy Limits:** Calculate coverage units, deductible periods, or
              benefit payment periods requiring full unit coverage.
            * **Resource Allocation:** Round up staffing requirements, system capacity,
              or operational resources to meet service level agreements.
            * **Risk Management:** Apply conservative assumptions for stress testing,
              scenario analysis, or worst-case planning exercises.

        Returns
        -------
        ExpressionProxy
            An expression containing values rounded up to the nearest integer.

        Examples
        --------
        **Scalar Example: Conservative Reserve Calculation**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_type": ["Property", "Liability", "Auto", "Health"],
            "reserve_estimate": [15432.3, 28901.7, 7234.1, 45678.9],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["claim_type"], conservative_reserve=af["reserve_estimate"].ceil()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌────────────┬──────────────────────┐
        │ claim_type ┆ conservative_reserve │
        │ ---        ┆ ---                  │
        │ str        ┆ f64                  │
        ╞════════════╪══════════════════════╡
        │ Property   ┆ 15433.0              │
        │ Liability  ┆ 28902.0              │
        │ Auto       ┆ 7235.0               │
        │ Health     ┆ 45679.0              │
        └────────────┴──────────────────────┘
        ```

        **Vector Example: Policy Count Planning**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "region": ["North", "South", "East", "West"],
            "projected_policies": [1234.2, 2567.8, 1890.3, 3421.6],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["region"],
            capacity_needed=af["projected_policies"].ceil()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌────────┬─────────────────┐
        │ region ┆ capacity_needed │
        │ ---    ┆ ---             │
        │ str    ┆ f64             │
        ╞════════╪═════════════════╡
        │ North  ┆ 1235.0          │
        │ South  ┆ 2568.0          │
        │ East   ┆ 1891.0          │
        │ West   ┆ 3422.0          │
        └────────┴─────────────────┘
        ```
        """
    def round(self, decimals: int = 0) -> ExpressionProxy:
        """Round numeric values to specified number of decimal places.

        Performs standard mathematical rounding of floating-point values to control
        precision in financial calculations, ensure regulatory compliance, and maintain
        consistent presentation standards in actuarial reporting and analysis.

        !!! note "When to use"
            * **Financial Precision:** Round premium calculations, reserve amounts,
              or claim payments to currency-appropriate decimal places (typically 2).
            * **Regulatory Compliance:** Ensure reported figures meet regulatory
              precision requirements for filings, statutory reports, and audits.
            * **Rate Calculations:** Round mortality rates, lapse rates, or interest
              rates to standard industry precision levels for model consistency.
            * **Presentation Standards:** Standardize decimal precision for management
              reports, dashboards, and customer communications.
            * **Calculation Stability:** Control rounding errors in iterative
              calculations and ensure reproducible results across model runs.
            * **Data Export:** Prepare data for external systems with specific
              precision requirements or legacy system constraints.

        Parameters
        ----------
        decimals : int, default 0
            Number of decimal places to round to. Positive values specify decimal
            places, zero rounds to integers, negative values round to powers of 10.

        Returns
        -------
        ExpressionProxy
            An expression with values rounded to the specified decimal precision.

        Examples
        --------
        **Scalar Example: Round Premium Calculations**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003"],
            "calculated_premium": [1234.5678, 2567.1234, 987.9876],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_id"], rounded_premium=af["calculated_premium"].round(2)
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 2)
        ┌───────────┬─────────────────┐
        │ policy_id ┆ rounded_premium │
        │ ---       ┆ ---             │
        │ str       ┆ f64             │
        ╞═══════════╪═════════════════╡
        │ P001      ┆ 1234.57         │
        │ P002      ┆ 2567.12         │
        │ P003      ┆ 987.99          │
        └───────────┴─────────────────┘
        ```

        **Vector Example: Round to Different Precision Levels**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "metric": ["mortality_rate", "lapse_rate", "interest_rate"],
            "value": [0.001234, 0.045678, 0.0325],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["metric"],
            original=af["value"],
            rounded_4dp=af["value"].round(4),
            rounded_percentage=af["value"].round(2)
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 4)
        ┌────────────────┬──────────┬─────────────┬────────────────────┐
        │ metric         ┆ original ┆ rounded_4dp ┆ rounded_percentage │
        │ ---            ┆ ---      ┆ ---         ┆ ---                │
        │ str            ┆ f64      ┆ f64         ┆ f64                │
        ╞════════════════╪══════════╪═════════════╪════════════════════╡
        │ mortality_rate ┆ 0.001234 ┆ 0.0012      ┆ 0.0                │
        │ lapse_rate     ┆ 0.045678 ┆ 0.0457      ┆ 0.05               │
        │ interest_rate  ┆ 0.0325   ┆ 0.0325      ┆ 0.03               │
        └────────────────┴──────────┴─────────────┴────────────────────┘
        ```
        """
    def round_sig_figs(self, sig_figs: int) -> ExpressionProxy: ...
    def exp(self) -> ExpressionProxy:
        """Compute the exponential function (e^x) of numeric values.

        Calculates e raised to the power of each value, essential for actuarial
        mathematics including compound interest calculations, exponential growth
        models, and survival function computations in life insurance analytics.

        !!! note "When to use"
            * **Interest Rate Calculations:** Convert log rates back to multiplicative
              factors for compound interest and present value calculations.
            * **Survival Analysis:** Transform hazard rates or cumulative hazards
              back to survival probabilities in mortality modeling.
            * **Growth Models:** Calculate exponential growth factors for premium
              escalation, inflation adjustments, and benefit projections.
            * **Statistical Modeling:** Convert log-transformed variables back to
              original scale in regression models and statistical analysis.
            * **Risk Modeling:** Transform log-normal distributions or calculate
              exponential utility functions in economic capital models.
            * **Financial Mathematics:** Compute continuous compounding factors
              and exponential discounting in investment and pension calculations.

        Returns
        -------
        ExpressionProxy
            An expression containing e raised to the power of each input value.

        Examples
        --------
        **Scalar Example: Convert Log Interest Rates to Growth Factors**

        ```python
        from gaspatchio_core import ActuarialFrame
        import math

        data = {
            "year": [1, 2, 3, 4, 5],
            "log_interest_rate": [
                math.log(1.03),
                math.log(1.035),
                math.log(1.04),
                math.log(1.025),
                math.log(1.045),
            ],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["year"], growth_factor=af["log_interest_rate"].exp()
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 2)
        ┌──────┬───────────────┐
        │ year ┆ growth_factor │
        │ ---  ┆ ---           │
        │ i64  ┆ f64           │
        ╞══════╪═══════════════╡
        │ 1    ┆ 1.03          │
        │ 2    ┆ 1.035         │
        │ 3    ┆ 1.04          │
        │ 4    ┆ 1.025         │
        │ 5    ┆ 1.045         │
        └──────┴───────────────┘
        ```

        **Vector Example: Survival Probability from Cumulative Hazard**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "age": [65, 70, 75, 80, 85],
            "cumulative_hazard": [-0.05, -0.15, -0.35, -0.65, -1.20],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["age"],
            survival_prob=af["cumulative_hazard"].exp()
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 2)
        ┌─────┬───────────────┐
        │ age ┆ survival_prob │
        │ --- ┆ ---           │
        │ i64 ┆ f64           │
        ╞═════╪═══════════════╡
        │ 65  ┆ 0.951229      │
        │ 70  ┆ 0.860708      │
        │ 75  ┆ 0.704688      │
        │ 80  ┆ 0.522046      │
        │ 85  ┆ 0.301194      │
        └─────┴───────────────┘
        ```
        """
    def pow(self, exponent: float | ExpressionProxy) -> ExpressionProxy:
        """Raise numeric values to specified power.

        Computes the power operation element-wise, raising each value to the specified
        exponent. Essential for actuarial calculations involving compound growth,
        present value computations, mortality rate adjustments, and exponential
        modeling in insurance and pension mathematics.

        !!! note "When to use"
            * **Present Value Calculations:** Apply discount factors using compound
              interest formulas like (1 + i)^(-t) for cash flow valuations.
            * **Compound Interest:** Calculate future values using (1 + i)^n for
              policy cash values, premium accumulations, and benefit projections.
            * **Mortality Rate Adjustments:** Apply exponential improvements or
              deteriorations to base mortality rates over projection periods.
            * **Risk Factor Scaling:** Transform linear risk scores to exponential
              scales for underwriting models and pricing adjustments.
            * **Reserve Calculations:** Compute actuarial present values using
              discount factors in life insurance and annuity valuations.
            * **Stochastic Modeling:** Generate power-law distributions for
              catastrophic loss modeling and reinsurance pricing.

        Parameters
        ----------
        exponent : float | int | ExpressionProxy
            The power to raise values to. Can be a scalar or column expression.

        Returns
        -------
        ExpressionProxy
            An expression containing values raised to the specified power.

        Examples
        --------
        **Scalar Example: Present Value Discount Factors**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "discount_base": [1.05, 1.04, 1.06, 1.03],
            "time_years": [10, 15, 20, 25],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_id"],
            discount_factor=af["discount_base"].pow(-1 * af["time_years"]),
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌───────────┬─────────────────┐
        │ policy_id ┆ discount_factor │
        │ ---       ┆ ---             │
        │ str       ┆ f64             │
        ╞═══════════╪═════════════════╡
        │ P001      ┆ 0.613913        │
        │ P002      ┆ 0.555265        │
        │ P003      ┆ 0.311805        │
        │ P004      ┆ 0.477606        │
        └───────────┴─────────────────┘
        ```

        **Vector Example: Interest Compounding Factors**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "age": [35, 45],
            "month": [
                [1, 2, 3, 4],
                [1, 2, 3, 4]
            ],
            "base_rate": [
                [1.04, 1.045, 1.05, 1.055],
                [1.03, 1.035, 1.04, 1.045]
            ]
        }
        af = ActuarialFrame(data)

        af["squared_growth"] = af["base_rate"].pow(2.0)

        print(af.collect())
        ```

        ```text
        shape: (2, 5)
        ┌───────────┬─────┬─────────────┬────────────────────────┬────────────────────────────────┐
        │ policy_id ┆ age ┆ month       ┆ base_rate              ┆ squared_growth                 │
        │ ---       ┆ --- ┆ ---         ┆ ---                    ┆ ---                            │
        │ str       ┆ i64 ┆ list[i64]   ┆ list[f64]              ┆ list[f64]                      │
        ╞═══════════╪═════╪═════════════╪════════════════════════╪════════════════════════════════╡
        │ P001      ┆ 35  ┆ [1, 2, … 4] ┆ [1.04, 1.045, … 1.055] ┆ [1.0816, 1.092025, … 1.113025] │
        │ P002      ┆ 45  ┆ [1, 2, … 4] ┆ [1.03, 1.035, … 1.045] ┆ [1.0609, 1.071225, … 1.092025] │
        └───────────┴─────┴─────────────┴────────────────────────┴────────────────────────────────┘
        ```
        """
    def log(self, base: float = ...) -> ExpressionProxy:
        """Compute logarithm of numeric values with specified base.

        Calculates the logarithm of each value using the specified base, essential for
        actuarial mathematics including interest rate transformations, exponential model
        linearization, and statistical analysis requiring log-scale transformations.

        !!! note "When to use"
            * **Interest Rate Analysis:** Transform compound interest rates to additive
              log-scale for linear modeling and time series analysis.
            * **Statistical Modeling:** Apply log transformations to skewed distributions
              like claim amounts or policy values for improved model performance.
            * **Growth Rate Calculations:** Convert multiplicative growth factors to
              additive log-growth rates for trend analysis and forecasting.
            * **Risk Modeling:** Transform log-normal distributions to normal scale
              for parameter estimation and model calibration procedures.
            * **Financial Mathematics:** Calculate continuously compounded returns,
              discount factors, and present value calculations.
            * **Model Linearization:** Convert exponential relationships to linear
              form for regression analysis and parameter estimation.

        Parameters
        ----------
        base : float, default math.e
            The logarithm base. Common values include e (natural log), 10 (common log),
            or 2 (binary log). If not specified, defaults to natural logarithm.

        Returns
        -------
        ExpressionProxy
            An expression containing logarithm values. Returns NaN for non-positive inputs.

        Examples
        --------
        **Scalar Example: Interest Rate Transformation**

        ```python
        from gaspatchio_core import ActuarialFrame
        import math

        data = {
            "year": [1, 2, 3, 4, 5],
            "growth_factor": [1.03, 1.035, 1.04, 1.025, 1.045],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["year"], log_growth_rate=af["growth_factor"].log(math.e)
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 2)
        ┌──────┬─────────────────┐
        │ year ┆ log_growth_rate │
        │ ---  ┆ ---             │
        │ i64  ┆ f64             │
        ╞══════╪═════════════════╡
        │ 1    ┆ 0.029559        │
        │ 2    ┆ 0.034401        │
        │ 3    ┆ 0.039221        │
        │ 4    ┆ 0.024693        │
        │ 5    ┆ 0.044017        │
        └──────┴─────────────────┘
        ```

        **Vector Example: Log10 Transformation for Analysis**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_type": ["Property", "Liability", "Auto", "Health"],
            "claim_amount": [1000.0, 10000.0, 100000.0, 1000000.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["claim_type"],
            log10_amount=af["claim_amount"].log(10.0)
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌────────────┬──────────────┐
        │ claim_type ┆ log10_amount │
        │ ---        ┆ ---          │
        │ str        ┆ f64          │
        ╞════════════╪══════════════╡
        │ Property   ┆ 3.0          │
        │ Liability  ┆ 4.0          │
        │ Auto       ┆ 5.0          │
        │ Health     ┆ 6.0          │
        └────────────┴──────────────┘
        ```
        """
    def log1p(self) -> ExpressionProxy: ...
    def ln(self) -> ExpressionProxy:
        """Compute the natural logarithm (base e) of numeric values.

        Calculates the natural logarithm of each value, fundamental for actuarial
        mathematics including continuous interest rate calculations, survival analysis,
        and exponential model transformations essential in insurance and financial modeling.

        !!! note "When to use"
            * **Continuous Interest Rates:** Convert discrete interest rates to
              continuous compounding equivalents for advanced financial calculations.
            * **Survival Analysis:** Transform survival times or hazard rates for
              exponential and Weibull distribution analysis in mortality modeling.
            * **Growth Rate Analysis:** Calculate instantaneous growth rates from
              discrete growth factors for economic and demographic projections.
            * **Statistical Transformations:** Apply natural log transformations to
              right-skewed data like claim amounts for improved statistical modeling.
            * **Present Value Calculations:** Compute continuous discounting factors
              for pension and annuity valuations with continuous payment streams.
            * **Risk Modeling:** Transform multiplicative risk factors to additive
              log-scale for linear regression and model interpretation.

        Returns
        -------
        ExpressionProxy
            An expression containing natural logarithm values. Returns NaN for
            non-positive input values.

        Examples
        --------
        **Scalar Example: Continuous Interest Rate Conversion**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "period": ["Q1", "Q2", "Q3", "Q4"],
            "discrete_rate": [1.025, 1.030, 1.035, 1.020],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["period"], continuous_rate=af["discrete_rate"].log()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌────────┬─────────────────┐
        │ period ┆ continuous_rate │
        │ ---    ┆ ---             │
        │ str    ┆ f64             │
        ╞════════╪═════════════════╡
        │ Q1     ┆ 0.024693        │
        │ Q2     ┆ 0.029558        │
        │ Q3     ┆ 0.034401        │
        │ Q4     ┆ 0.019803        │
        └────────┴─────────────────┘
        ```

        **Vector Example: Log-Transform Claim Amounts**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_severity": ["Small", "Medium", "Large", "Catastrophic"],
            "amount": [500.0, 5000.0, 50000.0, 500000.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["claim_severity"],
            ln_amount=af["amount"].log()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌──────────────┬───────────┐
        │ claim_severity ┆ ln_amount │
        │ ---          ┆ ---       │
        │ str          ┆ f64       │
        ╞══════════════╪═══════════╡
        │ Small        ┆ 6.214608  │
        │ Medium       ┆ 8.517193  │
        │ Large        ┆ 10.819778 │
        │ Catastrophic ┆ 13.122363 │
        └──────────────┴───────────┘
        ```
        """
    def log10(self) -> ExpressionProxy: ...
    def sqrt(self) -> ExpressionProxy:
        """Compute the square root of numeric values.

        Calculates the positive square root of each value, essential for actuarial
        mathematics including standard deviation calculations, volatility measures,
        and risk metric computations in insurance and financial modeling.

        !!! note "When to use"
            * **Standard Deviation:** Calculate standard deviations from variance
              values for risk measurement and statistical analysis.
            * **Volatility Modeling:** Compute volatility measures from variance
              calculations in investment and market risk assessments.
            * **Risk Metrics:** Calculate standard errors, confidence intervals,
              and risk measures requiring square root transformations.
            * **Financial Mathematics:** Compute values in options pricing models,
              duration calculations, and portfolio optimization.
            * **Statistical Analysis:** Transform quadratic measures back to linear
              scale for interpretation and reporting purposes.
            * **Model Calibration:** Calculate parameter estimates requiring square
              root transformations in actuarial model fitting procedures.

        Returns
        -------
        ExpressionProxy
            An expression containing the square root of each input value.
            Returns NaN for negative input values.

        Examples
        --------
        **Scalar Example: Calculate Standard Deviation from Variance**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "portfolio": ["Life", "Health", "Property", "Annuity"],
            "variance": [2500.0, 1600.0, 3600.0, 900.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["portfolio"], standard_deviation=af["variance"].sqrt()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌───────────┬────────────────────┐
        │ portfolio ┆ standard_deviation │
        │ ---       ┆ ---                │
        │ str       ┆ f64                │
        ╞═══════════╪════════════════════╡
        │ Life      ┆ 50.0               │
        │ Health    ┆ 40.0               │
        │ Property  ┆ 60.0               │
        │ Annuity   ┆ 30.0               │
        └───────────┴────────────────────┘
        ```

        **Vector Example: Risk-Adjusted Returns**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "year": [2020, 2021, 2022, 2023],
            "squared_excess_return": [0.0025, 0.0016, 0.0036, 0.0049],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["year"],
            volatility=af["squared_excess_return"].sqrt()
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌──────┬────────────┐
        │ year ┆ volatility │
        │ ---  ┆ ---        │
        │ i64  ┆ f64        │
        ╞══════╪════════════╡
        │ 2020 ┆ 0.05       │
        │ 2021 ┆ 0.04       │
        │ 2022 ┆ 0.06       │
        │ 2023 ┆ 0.07       │
        └──────┴────────────┘
        ```
        """
    def cbrt(self) -> ExpressionProxy: ...
    def gamma(self) -> ExpressionProxy: ...
    def is_nan(self) -> ExpressionProxy: ...
    def is_finite(self) -> ExpressionProxy: ...
    def is_infinite(self) -> ExpressionProxy: ...
    def is_not_nan(self) -> ExpressionProxy: ...
    def is_not_null(self) -> ExpressionProxy:
        """Check which values are not null (not missing) in this expression or column.

        Returns a boolean expression indicating which values are present and valid.
        Essential for data quality assessment, filtering complete records, and implementing
        conditional logic based on data availability in actuarial analysis.

        !!! note "When to use"
            * **Data Quality Filtering:** Select only records with complete information
              for premium calculations, claim processing, or risk assessment.
            * **Conditional Processing:** Apply different business rules based on data
              availability, such as using default values only when primary data exists.
            * **Complete Case Analysis:** Identify policies or claims with full data
              sets for statistical analysis and model development.
            * **Validation Rules:** Ensure critical fields are populated before
              processing transactions, calculating reserves, or generating reports.
            * **Data Completeness Metrics:** Calculate percentages of complete records
              for data quality monitoring and process improvement.
            * **Business Logic:** Implement rules that require specific information
              to be present before applying rates, discounts, or risk adjustments.

        Returns
        -------
        ExpressionProxy
            An expression containing boolean values indicating whether each
            value in the original expression is not null (True) or null (False).

        Examples
        --------
        **Scalar Example: Filter Complete Policy Records**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "beneficiary": ["John Doe", None, "Jane Smith", "Bob Wilson"],
            "premium": [1200.0, 1500.0, None, 1800.0],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            (af["beneficiary"].is_not_null() & af["premium"].is_not_null()).alias(
                "complete_record"
            )
        ).collect()
        print(result)
        ```

        ```text
        shape: (2, 3)
        ┌───────────┬─────────────┬─────────┐
        │ policy_id ┆ beneficiary ┆ premium │
        │ ---       ┆ ---         ┆ ---     │
        │ str       ┆ str         ┆ f64     │
        ╞═══════════╪═════════════╪═════════╡
        │ P001      ┆ John Doe    ┆ 1200.0  │
        │ P004      ┆ Bob Wilson  ┆ 1800.0  │
        └───────────┴─────────────┴─────────┘
        ```

        **Vector Example: Data Completeness by Policy Type**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "medical_exam": ["Complete", None, "Complete", None, "Complete"],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["policy_type"].count().alias("total_policies"),
            af["medical_exam"].is_not_null().sum().alias("complete_exams")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 3)
        ┌─────────────┬────────────────┬───────────────┐
        │ policy_type ┆ total_policies ┆ complete_exams │
        │ ---         ┆ ---            ┆ ---           │
        │ str         ┆ u32            ┆ u32           │
        ╞═════════════╪════════════════╪═══════════════╡
        │ TERM        ┆ 2              ┆ 1             │
        │ WHOLE       ┆ 2              ┆ 1             │
        │ UL          ┆ 1              ┆ 1             │
        └─────────────┴────────────────┴───────────────┘
        ```
        """
