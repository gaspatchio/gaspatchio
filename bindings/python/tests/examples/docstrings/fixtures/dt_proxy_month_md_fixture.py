from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaspatchio_core.column.namespaces import ColumnProxy, ExpressionProxy

    # Define a type alias for parent proxy types
    ParentProxyType = ColumnProxy | ExpressionProxy


class DtNamespaceProxy:
    def month(self) -> "ExpressionProxy":
        """Extract the month number (1-12) from a date or datetime expression.

        This function allows you to isolate the month component from a series of
        dates or datetimes. The result is an integer representing the month,
        where January is 1 and December is 12.

        !!! note "When to use"
            In actuarial modeling, extracting the month from dates is crucial for various analyses.
            For instance, you might use this to:

            *   Analyze seasonality in claims (e.g., identifying if certain types of claims are more frequent in specific months).
            *   Group policies by their issue month for cohort analysis or to study underwriting patterns.
            *   Determine valuation periods or calculate month-based durations for reserving or financial reporting.
            *   As a feature in predictive models, such as those for lapse rates or claim frequency, where monthly trends might be significant.

        Examples
        --------
        Scalar example - Policy Start Months::

            Scenario: You have a dataset of policies and want to analyze them based on the month their coverage started.

            ```python
            import datetime
            # import polars as pl # Removed as pl is not used
            from gaspatchio_core import ActuarialFrame

            af = ActuarialFrame({
                "policy_id": ["P001", "P002", "P003"],
                "policy_start_date": [
                    datetime.date(2023, 11, 15),
                    datetime.date(2023, 12, 5),
                    datetime.date(2024, 1, 20)
                ]
            })
            # Extract the month from the 'policy_start_date'
            print(af.select(af["policy_start_date"].dt.month().alias("start_month")).collect())
            ```
            ```
            shape: (3, 1)
            ┌─────────────┐
            │ start_month │
            │ ---         │
            │ i8          │
            ╞═════════════╡
            │ 11          │
            │ 12          │
            │ 1           │
            └─────────────┘
            ```

        Vector (list) example – Claim Lodgement Months::

            Scenario: For policies that have multiple claims, you want to extract the month for each claim lodgement date.

            ```python
            import datetime
            import polars as pl # pl is used for pl.List and pl.Date
            from gaspatchio_core import ActuarialFrame

            data = {
                "policy_id": ["C003", "D004"],
                "claim_lodgement_dates": [
                    [datetime.date(2022, 3, 10), datetime.date(2022, 4, 5)], # Policy C003 claims
                    [datetime.date(2023, 1, 20), datetime.date(2023, 11, 30)], # Policy D004 claims
                ],
            }
            af = ActuarialFrame(data)
            af = af.with_columns(
                af["claim_lodgement_dates"].cast(pl.List(pl.Date)) # Changed pl.col to af[] and separated with_columns
            )
            # Get the month for each date in the lists
            lodgement_months_expr = af["claim_lodgement_dates"].dt.month()
            print(af.select(af["policy_id"], lodgement_months_expr.alias("lodgement_months")).collect())
            ```
            ```
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
        pass
