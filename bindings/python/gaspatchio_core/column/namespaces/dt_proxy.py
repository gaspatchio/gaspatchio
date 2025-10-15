"""Proxy for datetime operations on ActuarialFrame columns/expressions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.frame.base import ActuarialFrame

    # Define a type alias for parent proxy types
    ParentProxyType = ColumnProxy | ExpressionProxy


class DtNamespaceProxy:
    """A proxy for Polars datetime (dt) namespace operations.

    Enables type-hinting and IDE intellisense for `ActuarialFrame` datetime
    manipulations.

    This proxy intercepts calls to datetime methods, retrieves the underlying
    Polars expression from its parent proxy (either a `ColumnProxy` or
    `ExpressionProxy`), applies the datetime operation, and then wraps the
    resulting Polars expression back into an `ExpressionProxy`.
    """

    def __init__(
        self,
        parent_proxy: ParentProxyType,
        parent_af: ActuarialFrame | None,
    ) -> None:
        """
        Initialize the DtNamespaceProxy.

        This constructor is typically not called directly by users. It's used
        internally when accessing the `.dt` attribute of an `ActuarialFrame`
        column or expression proxy (e.g., `af["my_date_col"].dt`).

        Args:
            parent_proxy: The parent proxy (ColumnProxy or ExpressionProxy)
                          from which this dt namespace is accessed.
            parent_af: The parent ActuarialFrame, if available, for context.

        """
        self._parent_proxy = parent_proxy
        self._parent_af = parent_af

    def _get_base_expr(self) -> pl.Expr:
        """
        Retrieve the underlying Polars expression from the parent proxy.

        Handles whether the parent is a ColumnProxy (needs pl.col()) or
        an ExpressionProxy (already has ._expr).

        Returns:
            The base Polars expression.

        Raises:
            TypeError: If the parent proxy is not of a supported type.

        """
        # Defer imports to avoid circular dependencies when this module is
        # imported directly at the top level by the proxy classes.
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        if isinstance(self._parent_proxy, ColumnProxy):
            return pl.col(self._parent_proxy.name)
        if isinstance(self._parent_proxy, ExpressionProxy):
            return self._parent_proxy._expr  # noqa: SLF001
        proxy_type = type(self._parent_proxy).__name__
        msg = f"Unsupported proxy type: {proxy_type}"
        raise TypeError(msg)

    def _is_list_of_temporals(self) -> bool:
        """Check if column is a list of temporal types.

        For ColumnProxy, it checks the DataFrame schema.
        For ExpressionProxy, this check is less definitive without evaluation
        context; it currently assumes False, as list shimming for arbitrary
        expressions based on type alone is complex.

        Returns:
            True if the column is a list of temporal types, False otherwise.

        """
        from gaspatchio_core.column.column_proxy import ColumnProxy

        if (
            isinstance(self._parent_proxy, ColumnProxy)
            and self._parent_af
            and self._parent_af._df is not None  # noqa: SLF001
        ):
            try:
                schema = self._parent_af._df.collect_schema()  # noqa: SLF001
                dtype = schema.get(self._parent_proxy.name)
                if isinstance(dtype, pl.List):
                    inner_dtype = dtype.inner
                    return isinstance(
                        inner_dtype,
                        (pl.Date, pl.Datetime, pl.Time),
                    )
            except (AttributeError, KeyError, TypeError):
                return False
        return False

    def _call_dt_method(
        self, method_name: str, *args: object, **kwargs: object
    ) -> ExpressionProxy:
        """Call a Polars dt namespace method.

        Applies list shimming if appropriate for ColumnProxy of List[Temporal].
        """
        from gaspatchio_core.column.dispatch import _unwrap, _wrap

        def _raise_not_callable_error(name: str) -> None:
            msg = f"Attribute '{name}' on Polars 'dt' namespace is not callable."
            raise TypeError(msg)

        base_expr = self._get_base_expr()
        unwrapped_args = [_unwrap(arg) for arg in args]
        unwrapped_kwargs = {key: _unwrap(val) for key, val in kwargs.items()}

        if self._is_list_of_temporals():
            try:
                element_dt_namespace = pl.element().dt
                element_dt_method = getattr(element_dt_namespace, method_name)
                shimming_result_expr = element_dt_method(
                    *unwrapped_args, **unwrapped_kwargs
                )
                result_expr = base_expr.list.eval(shimming_result_expr)
            except (AttributeError, TypeError, ValueError) as e_shim:
                try:
                    polars_dt_namespace = base_expr.dt
                    actual_method = getattr(polars_dt_namespace, method_name)
                    if not callable(actual_method):
                        _raise_not_callable_error(method_name)
                    result_expr = actual_method(*unwrapped_args, **unwrapped_kwargs)
                except (AttributeError, TypeError, ValueError) as e_fallback:
                    msg = (
                        f"Error calling dt method '{method_name}' after "
                        f"shimming failed: {e_shim}, {e_fallback}"
                    )
                    raise type(e_fallback)(msg) from e_fallback
        else:
            try:
                polars_dt_namespace = base_expr.dt
                actual_method = getattr(polars_dt_namespace, method_name)
                if not callable(actual_method):
                    _raise_not_callable_error(method_name)
                result_expr = actual_method(*unwrapped_args, **unwrapped_kwargs)
            except (AttributeError, TypeError, ValueError) as e_direct:
                msg = f"Error calling dt method '{method_name}': {e_direct}"
                raise type(e_direct)(msg) from e_direct

        return _wrap(self._parent_af, result_expr)

    def year(self) -> ExpressionProxy:
        """Extract the year from the underlying datetime expression.

        This function isolates the year component from a date or datetime,
        returning it as an integer (e.g., 2023). It is applicable to both
        single date values and lists of dates within your `ActuarialFrame`.

        !!! note "When to use"
            Extracting the year is fundamental in actuarial analysis for:

            *   **Valuation and Reporting:** Determining the calendar year
                for financial reporting or regulatory submissions.
            *   **Experience Studies:** Grouping data by calendar year of
                event (e.g., year of claim, year of lapse) to analyze trends.
            *   **Cohort Analysis:** Defining cohorts based on the year of
                policy issue or birth year.
            *   **Projection Models:** Calculating durations or projecting
                cash flows based on calendar years.

        Examples
        --------
        Scalar example (single-date column)::

        ```python
        import polars as pl
        from gaspatchio_core import ActuarialFrame

        data = {
            "dates": pl.Series(["2020-01-15", "2021-07-20"]).str.to_date(
                format="%Y-%m-%d"
            )
        }
        af = ActuarialFrame(data)
        year_expr = af.dates.dt.year()
        print(af.select(year_expr.alias("year")).collect())
        ```
        ```text
        shape: (2, 1)
        ┌──────┐
        │ year │
        │ ---  │
        │ i32  │
        ╞══════╡
        │ 2020 │
        │ 2021 │
        └──────┘
        ```

        Vector example (list-of-dates per policy)::

        ```python
        import datetime
        import polars as pl
        from gaspatchio_core import ActuarialFrame
        data_vec = {
            "policy_id": ["A001", "B002"],
            "policy_event_dates": [
                [datetime.date(2019, 12, 1), datetime.date(2020, 1, 20)],
                [
                    datetime.date(2021, 5, 10),
                    datetime.date(2021, 8, 15),
                    datetime.date(2022, 2, 25),
                ],
            ],
        }
        af_vec = ActuarialFrame(data_vec)
        af_vec = af_vec.with_columns(
            pl.col("policy_event_dates").cast(pl.List(pl.Date))
        )
        years_expr = af_vec.policy_event_dates.dt.year()
        result = af_vec.select(
            pl.col("policy_id"), years_expr.alias("event_years")
        )
        print(result.collect())
        ```
        ```text
        shape: (2, 2)
        ┌───────────┬────────────────────┐
        │ policy_id ┆ event_years        │
        │ ---       ┆ ---                │
        │ str       ┆ list[i32]          │
        ╞═══════════╪════════════════════╡
        │ A001      ┆ [2019, 2020]       │
        │ B002      ┆ [2021, 2021, 2022] │
        └───────────┴────────────────────┘
        ```

        """
        return self._call_dt_method("year")

    def month(self) -> ExpressionProxy:
        """Extract the month number (1-12) from a date or datetime expression.

        This function allows you to isolate the month component from a series of
        dates or datetimes. The result is an integer representing the month,
        where January is 1 and December is 12.

        !!! note "When to use"
            In actuarial modeling, extracting the month from dates is
            crucial for various analyses. For instance, you might use this to:

            *   Analyze seasonality in claims (e.g., identifying if certain
                types of claims are more frequent in specific months).
            *   Group policies by their issue month for cohort analysis or
                to study underwriting patterns.
            *   Determine premium due dates or benefit payment schedules
                that occur on a monthly basis.
            *   Calculate fractional year components for financial
                calculations.

        Examples
        --------
        Scalar example::

        ```python
        import polars as pl
        from gaspatchio_core import ActuarialFrame

        af = ActuarialFrame(
            {
                "d": pl.Series(["2022-01-01", "2022-02-01", "2022-03-01"]).str.to_date(
                    "%Y-%m-%d"
                )
            }
        )
        print(af.select(af.d.dt.month().alias("m")).collect())
        ```
        ```text
        shape: (3, 1)
        ┌─────┐
        │ m   │
        │ --- │
        │ i8  │
        ╞═════╡
        │ 1   │
        │ 2   │
        │ 3   │
        └─────┘
        ```

        Vector (list) example - claim-lodgement months::

        ```python
        import datetime
        import polars as pl
        from gaspatchio_core import ActuarialFrame
        data = {
            "policy_id": ["C003", "D004"],
            "claim_lodgement_dates": [
                [datetime.date(2022, 3, 10), datetime.date(2022, 4, 5)],
                [datetime.date(2023, 1, 20), datetime.date(2023, 11, 30)],
            ],
        }
        af = ActuarialFrame(data).with_columns(
            pl.col("claim_lodgement_dates").cast(pl.List(pl.Date))
        )
        months_expr = af.claim_lodgement_dates.dt.month()
        result = af.select(
            pl.col("policy_id"), months_expr.alias("lodgement_months")
        )
        print(result.collect())
        ```

        ```text
        shape: (2, 2)
        ┌───────────┬──────────────────┐
        │ policy_id ┆ lodgement_months │
        │ ---       ┆ ---              │
        │ str       ┆ list[i8]         │
        ╞═══════════╪══════════════════╡
        │ C003      ┆ [3, 4]           │
        │ D004      ┆ [1, 11]          │
        └───────────┴──────────────────┘
        ```

        """
        return self._call_dt_method("month")

    def day(self) -> ExpressionProxy:
        """Extract the day number of the month (1-31) from a date/datetime expression.

        This function isolates the day component from a date or datetime,
        returning it as an integer (e.g., 15 for the 15th of the month).
        It works for both individual dates and lists of dates.

        !!! note "When to use"
            Extracting the day of the month can be useful in actuarial
            contexts for:

            *   **Specific Date Checks:** Identifying events occurring on
                particular days (e.g., end-of-month processing).
            *   **Intra-month Analysis:** Analyzing patterns within a month,
                though less common than month or year analysis.
            *   **Data Validation:** Ensuring dates fall within expected day
                ranges for specific calculations.

        Examples
        --------
        Scalar example::

        ```python
        import polars as pl
        from gaspatchio_core import ActuarialFrame

        af = ActuarialFrame(
            {"d": pl.Series(["2023-06-05", "2023-06-15"]).str.to_date()}
        )
        print(af.select(af.d.dt.day().alias("day")).collect())
        ```
        ```text
        shape: (2, 1)
        ┌─────┐
        │ day │
        │ --- │
        │ i8  │
        ╞═════╡
        │ 5   │
        │ 15  │
        └─────┘
        ```

        Vector (list) example - loss-event days::

        ```python
        import datetime
        import polars as pl
        from gaspatchio_core import ActuarialFrame
        data = {
            "policy_id": ["E005", "F006"],
            "loss_event_dates": [
                [datetime.date(2023, 6, 5), datetime.date(2023, 6, 15)],
                [datetime.date(2024, 2, 1), datetime.date(2024, 2, 29)],
            ],
        }
        af = ActuarialFrame(data).with_columns(
            pl.col("loss_event_dates").cast(pl.List(pl.Date))
        )
        days_expr = af.loss_event_dates.dt.day()
        print(af.select("policy_id", days_expr.alias("event_days")).collect())
        ```
        ```text
        shape: (2, 2)
        ┌───────────┬────────────┐
        │ literal   ┆ event_days │
        │ ---       ┆ ---        │
        │ str       ┆ list[i8]   │
        ╞═══════════╪════════════╡
        │ policy_id ┆ [5, 15]    │
        │ policy_id ┆ [1, 29]    │
        └───────────┴────────────┘
        ```

        """
        return self._call_dt_method("day")

    def __getattr__(self, name: str) -> Callable[..., ExpressionProxy]:
        """Dynamically handle other Polars dt namespace methods.

        This provides a fallback for dt methods not explicitly defined on
        this proxy. It attempts to call the method via `_call_dt_method`.

        Args:
            name: The name of the dt method to access.

        Returns:
            A callable that, when invoked, will execute the corresponding
            Polars dt method and return an ExpressionProxy.

        Raises:
            AttributeError: If the method does not exist on the Polars dt
                namespace (raised by _call_dt_method if the underlying
                Polars call fails).

        """
        if name.startswith("_"):
            cls_name = type(self).__name__
            msg = f"'{cls_name}' object has no attribute '{name}'"
            raise AttributeError(msg)

        def dynamic_dt_method_caller(
            *args: object, **kwargs: object
        ) -> ExpressionProxy:
            return self._call_dt_method(name, *args, **kwargs)

        dynamic_dt_method_caller.__name__ = f"proxied_dt_{name}"
        dynamic_dt_method_caller.__doc__ = (
            f"Dynamically proxied Polars dt method: {name}"
        )

        return dynamic_dt_method_caller


# Unit tests for this will be added once more methods are in place,
# or in a separate test file.
