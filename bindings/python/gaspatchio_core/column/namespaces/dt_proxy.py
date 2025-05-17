"""Proxy for datetime operations on ActuarialFrame columns/expressions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

import polars as pl

if TYPE_CHECKING:
    from ...frame.base import ActuarialFrame  # Adjusted from ..frame.base
    from ..column_proxy import ColumnProxy  # Adjusted from .column_proxy
    from ..expression_proxy import ExpressionProxy  # Adjusted from .expression_proxy

    # Define a type alias for parent proxy types
    ParentProxyType = ColumnProxy | ExpressionProxy


class DtNamespaceProxy:
    """
    A proxy for Polars datetime (dt) namespace operations, enabling type-hinting
    and IDE intellisense for `ActuarialFrame` datetime manipulations.

    This proxy intercepts calls to datetime methods, retrieves the underlying
    Polars expression from its parent proxy (either a `ColumnProxy` or
    `ExpressionProxy`), applies the datetime operation, and then wraps the
    resulting Polars expression back into an `ExpressionProxy`.
    """

    def __init__(
        self,
        parent_proxy: "ParentProxyType",
        parent_af: Optional["ActuarialFrame"],
    ):
        """
        Initialize the DtNamespaceProxy.

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
        # Defer imports for ColumnProxy and ExpressionProxy to avoid circular dependencies
        # if this module were to be imported directly by them at the top level.
        # This is generally safer for proxy/dispatch mechanisms.
        from ..column_proxy import ColumnProxy  # Adjusted from .column_proxy
        from ..expression_proxy import (
            ExpressionProxy,  # Adjusted from .expression_proxy
        )

        if isinstance(self._parent_proxy, ColumnProxy):
            return pl.col(self._parent_proxy.name)
        if isinstance(self._parent_proxy, ExpressionProxy):
            return self._parent_proxy._expr
        raise TypeError(
            "DtNamespaceProxy parent must be ColumnProxy or ExpressionProxy, "
            f"got {type(self._parent_proxy).__name__}"
        )

    def _is_list_of_temporals(self) -> bool:
        """
        Check if the parent proxy refers to a column that is a list of temporal types.

        For ColumnProxy, it checks the DataFrame schema.
        For ExpressionProxy, this check is less definitive without evaluation context;
        it currently assumes False, as list shimming for arbitrary expressions
        based on type alone is complex. The _call_dt_method will handle specific
        shimming strategies for expressions.

        Returns:
            True if the column is a list of temporal types, False otherwise.
        """
        from ..column_proxy import ColumnProxy  # Adjusted from .column_proxy
        # ExpressionProxy is not strictly needed here for logic, but good for context
        # from ..expression_proxy import ExpressionProxy # Adjusted from .expression_proxy

        if isinstance(self._parent_proxy, ColumnProxy):
            if self._parent_af and self._parent_af._df is not None:
                try:
                    dtype = self._parent_af._df.schema.get(self._parent_proxy.name)
                    if isinstance(dtype, pl.List):
                        inner_dtype = dtype.inner
                        # Check if the inner type is any of the Polars temporal types
                        is_temporal = isinstance(
                            inner_dtype,
                            (
                                pl.Date,
                                pl.Datetime,
                                pl.Time,
                                # pl.Duration # Duration might not have all dt methods
                            ),
                        )
                        return is_temporal
                except Exception:
                    # If column not in schema or other error, assume not list of temporals
                    return False
        # For ExpressionProxy, it's hard to know the type without evaluation.
        # The original shimming logic in dispatch.py for general expressions was:
        # elif isinstance(self_proxy, ExpressionProxy):
        #    should_use_list_shim = True # (for unary numeric)
        # For dt, we'll let _call_dt_method decide based on the operation itself
        # if it's an ExpressionProxy, as type introspection is hard here.
        return False

    def _call_dt_method(
        self, method_name: str, *args: Any, **kwargs: Any
    ) -> "ExpressionProxy":
        """
        Call a method on the Polars `dt` namespace of the base expression,
        applying list shimming if appropriate (for ColumnProxy of List[Temporal]).
        """
        from ..dispatch import _unwrap, _wrap  # Adjusted from .dispatch
        # ColumnProxy not strictly needed here anymore but was part of original thought

        base_expr = self._get_base_expr()
        unwrapped_args = [_unwrap(arg) for arg in args]
        unwrapped_kwargs = {key: _unwrap(val) for key, val in kwargs.items()}

        if (
            self._is_list_of_temporals()
        ):  # Only try shimming if we know it's a List[Temporal] column
            try:
                element_dt_namespace = getattr(pl.element(), "dt")
                element_dt_method = getattr(element_dt_namespace, method_name)
                # Call the method on pl.element().dt with the unwrapped arguments
                shimming_result_expr = element_dt_method(
                    *unwrapped_args, **unwrapped_kwargs
                )
                result_expr = base_expr.list.eval(shimming_result_expr)
            except (
                Exception
            ) as e_shim:  # Fallback for safety or if method not on pl.element().dt
                # This fallback might be hit if a specific dt method isn't on pl.element().dt
                # or if _is_list_of_temporals had a rare misidentification.
                try:
                    polars_dt_namespace = getattr(base_expr, "dt")
                    actual_polars_method = getattr(polars_dt_namespace, method_name)
                    if not callable(actual_polars_method):
                        raise TypeError(
                            f"Attribute '{method_name}' on Polars 'dt' namespace is not callable."
                        )
                    result_expr = actual_polars_method(
                        *unwrapped_args, **unwrapped_kwargs
                    )
                except Exception as e_direct_fallback:
                    raise type(e_direct_fallback)(
                        f"Error calling Polars dt method '{method_name}' directly after shimming failed (shimming error: {e_shim}): {e_direct_fallback}"
                    ) from e_direct_fallback
        else:
            # Standard path for non-list temporals or ExpressionProxy parents
            try:
                polars_dt_namespace = getattr(base_expr, "dt")
                actual_polars_method = getattr(polars_dt_namespace, method_name)
                if not callable(actual_polars_method):
                    raise TypeError(
                        f"Attribute '{method_name}' on Polars 'dt' namespace is not callable."
                    )
                result_expr = actual_polars_method(*unwrapped_args, **unwrapped_kwargs)
            except Exception as e_direct:
                raise type(e_direct)(
                    f"Error calling Polars dt method '{method_name}' directly: {e_direct}"
                ) from e_direct

        return _wrap(self._parent_af, result_expr)

    def year(self) -> "ExpressionProxy":
        """Extract the year from the underlying datetime expression.

        Corresponds to Polars ``Expr.dt.year()``.

        Examples
        --------
        Scalar example (single-date column)::

            >>> import polars as pl
            >>> from gaspatchio_core import ActuarialFrame
            >>> data = {
            ...     "dates": pl.Series(["2020-01-15", "2021-07-20"]).str.to_date(format="%Y-%m-%d")
            ... }
            >>> af = ActuarialFrame(data)
            >>> year_expr = af["dates"].dt.year()
            >>> print(af.select(year_expr.alias("year")).collect())
            shape: (2, 1)
            ┌──────┐
            │ year │
            │ ---  │
            │ i32  │
            ╞══════╡
            │ 2020 │
            │ 2021 │
            └──────┘

        Vector example (list-of-dates per policy)::

            >>> import datetime, polars as pl
            >>> from gaspatchio_core import ActuarialFrame
            >>> data_vec = {
            ...     "policy_id": ["A001", "B002"],
            ...     "policy_event_dates": [
            ...         [datetime.date(2019, 12, 1), datetime.date(2020, 1, 20)],
            ...         [datetime.date(2021, 5, 10), datetime.date(2021, 8, 15), datetime.date(2022, 2, 25)],
            ...     ],
            ... }
            >>> af_vec = ActuarialFrame(data_vec)
            >>> af_vec = af_vec.with_columns(pl.col("policy_event_dates").cast(pl.List(pl.Date)))
            >>> years_expr = af_vec["policy_event_dates"].dt.year()
            >>> print(af_vec.select(pl.col("policy_id"), years_expr.alias("event_years")).collect())
            shape: (2, 2)
            ┌───────────┬────────────────────┐
            │ policy_id ┆ event_years        │
            │ ---       ┆ ---                │
            │ str       ┆ list[i32]          │
            ╞═══════════╪════════════════════╡
            │ A001      ┆ [2019, 2020]       │
            │ B002      ┆ [2021, 2021, 2022] │
            └───────────┴────────────────────┘
        """
        return self._call_dt_method("year")

    def month(self) -> "ExpressionProxy":
        """Extract the month number from a date/datetime expression.

        Examples
        --------
        Scalar example::

            >>> import polars as pl
            >>> from gaspatchio_core import ActuarialFrame
            >>> af = ActuarialFrame({"d": pl.date_range("2022-01-01", "2022-03-01", interval="1mo")})
            >>> print(af.select(af["d"].dt.month().alias("m")).collect())
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

        Vector (list) example – claim-lodgement months::

            >>> import datetime, polars as pl
            >>> from gaspatchio_core import ActuarialFrame
            >>> data = {
            ...     "policy_id": ["C003", "D004"],
            ...     "claim_lodgement_dates": [
            ...         [datetime.date(2022, 3, 10), datetime.date(2022, 4, 5)],
            ...         [datetime.date(2023, 1, 20), datetime.date(2023, 11, 30)],
            ...     ],
            ... }
            >>> af = ActuarialFrame(data).with_columns(
            ...     pl.col("claim_lodgement_dates").cast(pl.List(pl.Date))
            ... )
            >>> months_expr = af["claim_lodgement_dates"].dt.month()
            >>> print(af.select("policy_id", months_expr.alias("lodgement_months")).collect())
            shape: (2, 2)
            ┌───────────┬──────────────────┐
            │ literal   ┆ lodgement_months │
            │ ---       ┆ ---              │
            │ str       ┆ list[i8]         │
            ╞═══════════╪══════════════════╡
            │ policy_id ┆ [3, 4]           │
            │ policy_id ┆ [1, 11]          │
            └───────────┴──────────────────┘
        """
        return self._call_dt_method("month")

    def day(self) -> "ExpressionProxy":
        """Extract the day number of the month from a date/datetime expression.

        Examples
        --------
        Scalar example::

            >>> import polars as pl
            >>> from gaspatchio_core import ActuarialFrame
            >>> af = ActuarialFrame({"d": pl.Series(["2023-06-05", "2023-06-15"]).str.to_date()})
            >>> print(af.select(af["d"].dt.day().alias("day")).collect())
            shape: (2, 1)
            ┌─────┐
            │ day │
            │ --- │
            │ i8  │
            ╞═════╡
            │ 5   │
            │ 15  │
            └─────┘

        Vector (list) example – loss-event days::

            >>> import datetime, polars as pl
            >>> from gaspatchio_core import ActuarialFrame
            >>> data = {
            ...     "policy_id": ["E005", "F006"],
            ...     "loss_event_dates": [
            ...         [datetime.date(2023, 6, 5), datetime.date(2023, 6, 15)],
            ...         [datetime.date(2024, 2, 1), datetime.date(2024, 2, 29)],
            ...     ],
            ... }
            >>> af = ActuarialFrame(data).with_columns(
            ...     pl.col("loss_event_dates").cast(pl.List(pl.Date))
            ... )
            >>> days_expr = af["loss_event_dates"].dt.day()
            >>> print(af.select("policy_id", days_expr.alias("event_days")).collect())
            shape: (2, 2)
            ┌───────────┬────────────┐
            │ literal   ┆ event_days │
            │ ---       ┆ ---        │
            │ str       ┆ list[i8]   │
            ╞═══════════╪════════════╡
            │ policy_id ┆ [5, 15]    │
            │ policy_id ┆ [1, 29]    │
            └───────────┴────────────┘
        """
        return self._call_dt_method("day")

    def __getattr__(self, name: str) -> Callable[..., "ExpressionProxy"]:
        """
        Dynamically handle any other methods available on Polars' dt namespace.

        This provides a fallback for dt methods not explicitly defined on this proxy.
        It attempts to call the method via `_call_dt_method`.

        Args:
            name: The name of the dt method to access.

        Returns:
            A callable that, when invoked, will execute the corresponding
            Polars dt method and return an ExpressionProxy.

        Raises:
            AttributeError: If the method does not exist on the Polars dt namespace
                          (raised by _call_dt_method if the underlying Polars call fails).
        """
        # Check if the attribute is private or dunder, common for __getattr__ guards
        if name.startswith("_"):
            # This typically shouldn't be reached for intended dt methods,
            # but good practice to avoid proxying private attributes.
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

        # We need to return a callable that will then take *args and **kwargs
        # and pass them to _call_dt_method.
        # functools.wraps can be tricky here because we don't have the original method
        # from Polars at this stage to wrap. We are creating a new function.
        # The main purpose of wraps is to preserve name, docstring, etc. of the wrapped function.
        # Here, the function being called is _call_dt_method with `name` as an argument.

        # Define the function that will be returned when an attribute is accessed.
        def dynamic_dt_method_caller(*args: Any, **kwargs: Any) -> "ExpressionProxy":
            return self._call_dt_method(name, *args, **kwargs)

        # Try to give it a somewhat useful name for debugging, though it won't be perfect.
        # A more sophisticated approach might try to get the docstring from the actual Polars
        # method at this point if possible, but that adds complexity.
        dynamic_dt_method_caller.__name__ = f"proxied_dt_{name}"
        # Potentially, try to fetch actual docstring from pl.Expr().dt.<name> if it exists
        # but this might be slow or error-prone here.
        # For now, a generic docstring:
        dynamic_dt_method_caller.__doc__ = (
            f"Dynamically proxied Polars dt method: {name}"
        )

        return dynamic_dt_method_caller


# Unit tests for this will be added once more methods are in place,
# or in a separate test file.
