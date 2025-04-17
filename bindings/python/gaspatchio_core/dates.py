"""
Actuarial date and timeline utilities for projection models.

This module provides functions for creating and manipulating date-based
projections commonly used in actuarial work, such as policy projections,
cashflow modeling, and demographic projections.
"""

import datetime
from typing import Literal, Union

import polars as pl
from dateutil.relativedelta import relativedelta

from gaspatchio_core.dsl.core import ActuarialFrame


# Define a function to generate the projection dates
def generate_projection_dates(
    row,
    projection_frequency: Literal[
        "monthly", "quarterly", "semi-annual", "annual"
    ] = "monthly",
):
    start = row["projection_start_date"]
    end = row["projection_end_date"]

    # Determine the increment using relativedelta
    if projection_frequency == "monthly":
        delta = relativedelta(months=1)
    elif projection_frequency == "quarterly":
        delta = relativedelta(months=3)
    elif projection_frequency == "semi-annual":
        delta = relativedelta(months=6)
    elif projection_frequency == "annual":
        delta = relativedelta(years=1)
    # NOTE: Validation moved to create_projection_timeline

    # Generate list of projection dates using relativedelta
    proj_dates = []
    current_date = start
    while current_date <= end:
        proj_dates.append(current_date)
        current_date += delta

    # Ensure the final date exactly matches 'end' if it wasn't naturally hit
    # This handles cases where the interval doesn't perfectly align with the end date
    # e.g., projecting 1.5 years quarterly.
    # However, for the exact definition used before (number of intervals based on month/year diff),
    # this simpler approach might be sufficient.
    # If exact end date matching is needed, more complex logic might be required.

    # Let's stick to the interval calculation logic for consistency with previous version
    # Calculate the number of intervals (original logic)
    if projection_frequency == "monthly":
        intervals = (end.year - start.year) * 12 + end.month - start.month
    elif projection_frequency == "quarterly":
        intervals = ((end.year - start.year) * 12 + end.month - start.month) // 3
    elif projection_frequency == "semi-annual":
        intervals = ((end.year - start.year) * 12 + end.month - start.month) // 6
    elif projection_frequency == "annual":
        intervals = end.year - start.year
    else:  # Should not happen due to eager validation
        intervals = 0

    # Generate list using the calculated number of intervals and relativedelta
    return [start + delta * i for i in range(intervals + 1)]


def create_projection_timeline(
    af: ActuarialFrame,
    valuation_date: datetime.date,
    projection_end_type: Literal[
        "maximum_age", "term_years", "term_months", "fixed_date"
    ] = "maximum_age",
    projection_end_value: Union[int, datetime.date] = 100,
    issue_age_column: str = "issue_age",
    projection_frequency: Literal[
        "monthly", "quarterly", "semi-annual", "annual"
    ] = "monthly",
    projection_start_offset_months: int = 0,
    store_start_date: bool = True,
    store_end_date: bool = True,
    output_column: str = "proj_dates",
) -> ActuarialFrame:
    """
    Creates a projection timeline for actuarial calculations.

    Args:
        af: The ActuarialFrame to add the projection timeline to
        valuation_date: The valuation date from which to project
        projection_end_type: How to determine the end of the projection:
            - "maximum_age": Project until the policyholder reaches the maximum age
            - "term_years": Project for a fixed number of years
            - "term_months": Project for a fixed number of months
            - "fixed_date": Project until a specific calendar date
        projection_end_value: The value corresponding to the projection_end_type:
            - For "maximum_age": The maximum age (e.g., 100)
            - For "term_years": The number of years to project
            - For "term_months": The number of months to project
            - For "fixed_date": A datetime.date object
        issue_age_column: The column containing the issue age (needed for "maximum_age")
        projection_frequency: The frequency of projection points
        projection_start_offset_months: Months to offset the start date from valuation
        store_start_date: Whether to store the projection start date
        store_end_date: Whether to store the projection end date
        output_column: The name of the column to store the projection dates

    Returns:
        The updated ActuarialFrame
    """
    # Eagerly validate projection_frequency
    valid_frequencies = ("monthly", "quarterly", "semi-annual", "annual")
    if projection_frequency not in valid_frequencies:
        raise ValueError(
            f"Invalid projection frequency: {projection_frequency}. "
            f"Must be one of {valid_frequencies}"
        )

    # Convert valuation_date to a Polars expression
    valuation_date_expr = pl.lit(valuation_date)

    # Calculate the projection start date based on offset
    start_date_expr = valuation_date_expr
    if projection_start_offset_months != 0:
        start_date_expr = valuation_date_expr.dt.offset_by(
            f"{projection_start_offset_months}mo"
        )

    # Calculate the projection end date based on the end type
    if projection_end_type == "maximum_age":
        max_age = projection_end_value
        years_to_project_expr = (pl.lit(max_age) - pl.col(issue_age_column)).cast(
            pl.Int64
        )
        end_date_expr = start_date_expr.dt.offset_by(
            pl.concat_str(years_to_project_expr.cast(pl.Utf8), pl.lit("y"))
        )
    elif projection_end_type == "term_years":
        end_date_expr = start_date_expr.dt.offset_by(f"{projection_end_value}y")
    elif projection_end_type == "term_months":
        end_date_expr = start_date_expr.dt.offset_by(f"{projection_end_value}mo")
    elif projection_end_type == "fixed_date":
        end_date_expr = pl.lit(projection_end_value)
    else:
        raise ValueError(f"Invalid projection end type: {projection_end_type}")

    # Store start and end dates if requested
    if store_start_date:
        af["projection_start_date"] = start_date_expr

    if store_end_date:
        af["projection_end_date"] = end_date_expr

    # Generate the projection dates using the calculated expressions
    af[output_column] = pl.struct(
        [
            start_date_expr.alias("projection_start_date"),
            end_date_expr.alias("projection_end_date"),
        ]
    ).map_elements(
        lambda row: generate_projection_dates(
            row, projection_frequency=projection_frequency
        ),
        return_dtype=pl.List(pl.Date),
    )

    return af
