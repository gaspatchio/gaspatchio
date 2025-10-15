"""Actuarial example: Calculate IRR for investment projects using list operations."""

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.accessors.excel_functions.irr import irr

# Configure Polars for better terminal display
pl.Config.set_tbl_cols(-1)  # Show all columns
pl.Config.set_tbl_width_chars(300)  # Wider width to show full column names
pl.Config.set_fmt_str_lengths(15)  # Limit string length for readability
pl.Config.set_tbl_rows(-1)  # Show all rows

# Investment projects with cash flows: initial cost (negative) followed by returns
data = {
    "project_id": ["PROJ001", "PROJ002", "PROJ003"],
    "cash_flows": [
        [-10000.0] + [500.0] * 36,
        [-25000.0] + [1200.0] * 30,
        [-15000.0, 2000.0, 3000.0, 4000.0, 5000.0, 6000.0],
    ],
}

# Use Polars directly first to calculate list-based metrics
project_data = pl.DataFrame(data)
project_data = project_data.with_columns(
    [
        pl.col("cash_flows").list.len().alias("num_periods"),
        (pl.col("cash_flows").list.first() * -1).round(2).alias("initial_investment"),
        pl.col("cash_flows").list.tail(-1).list.sum().round(2).alias("total_inflows"),
    ]
)
project_data = project_data.with_columns(
    (pl.col("total_inflows") - pl.col("initial_investment"))
    .round(2)
    .alias("net_cashflow")
)

# Now bring into ActuarialFrame for IRR calculation
projects = ActuarialFrame(project_data)

# Calculate IRR using ActuarialFrame Excel functions
projects.irr_rate = irr(projects.cash_flows).round(6)
projects.irr_annual = ((1 + projects.irr_rate) ** 12 - 1).round(4)

print(projects.collect())
