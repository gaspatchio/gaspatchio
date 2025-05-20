from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaspatchio_core.column.namespaces import ColumnProxy, ExpressionProxy

    # Define a type alias for parent proxy types
    ParentProxyType = ColumnProxy | ExpressionProxy


class DtNamespaceProxy:
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
        pass
