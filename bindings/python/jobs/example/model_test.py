# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import sys
from pathlib import Path

import gaspatchio_core as gs
import polars as pl
from gaspatchio_core import ActuarialFrame
from loguru import logger

# Add the current directory to the path so we can import setup.py
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))


def setup_mortality_table(mortality_file_path=None):
    """
    Setup the mortality table for lookup using the new load_assumptions API.
    """
    mortality_df = pl.read_parquet("jobs/example/assumptions/mortality.parquet")

    logger.info("Read mortality table, registering...")

    # Use new load_assumptions API instead of TableRegistry + WideToLongTransformSpec
    gs.load_assumptions(
        "mortality_rates",
        mortality_df,
        id="age-last",
        value="mortality_rate",
        value_vars=["MNS", "FNS", "MS", "FS"],
    )


def setup_lapse_table(lapse_file_path=None):
    """
    Setup the lapse table for lookup using the new load_assumptions API.
    """
    lapse_df = pl.read_parquet("jobs/example/assumptions/lapse.parquet")

    logger.info("Read lapse table, registering...")

    # Use new load_assumptions API - this is already a curve table
    gs.load_assumptions(
        "lapse_rates", lapse_df, id="policy duration", value="lapse rate"
    )


def setup_premium_table(premium_file_path=None):
    """
    Setup the premium table for lookup using the new load_assumptions API.
    """
    premium_df = pl.read_parquet("jobs/example/assumptions/premium-rate.parquet")

    logger.info("Read premium table, registering...")

    # Use new load_assumptions API instead of TableRegistry + WideToLongTransformSpec
    gs.load_assumptions(
        "premium_rates",
        premium_df,
        id="age-last",
        value="premium_rate",
        value_vars=["MNS", "FNS", "MS", "FS"],
    )


def setup_ages(af: ActuarialFrame) -> ActuarialFrame:
    """
    Setup the ages for the model.
    """
    logger.info("Setting up ages")
    # Add age squared calculation
    max_age = 101
    af["num_proj_months"] = (max_age - af["age"]) * 12

    # Using custom plugin functions

    af["proj_months"] = af.fill_series(af["num_proj_months"], 0, 1)
    af["month"] = af["proj_months"]

    af["proj_years"] = af["proj_months"] / 12

    # Update age with monthly increment
    af["age"] = af["age"] + (af["proj_months"] / 12)

    # --- Core Change Here ---
    # 1. Calculate fractional policy duration list first (overwrites original scalar column)
    af["policy duration"] = af["policy duration"] + (af["proj_months"] / 12)

    # 2. Calculate integer duration for lookups by flooring the fractional duration list
    #    This mimics Excel's ROUNDDOWN(duration, 0)
    af["policy_duration_as_int"] = (
        af["policy duration"].floor().cast(pl.List(pl.Int64))
    )  # <------ This needs to be an int.
    # --- End Core Change ---

    # Use floor to get age last and cast the list elements to Int64
    af["age-last"] = af["age"].floor().cast(pl.List(pl.Int64))

    return af


def mortality_rate(af: ActuarialFrame) -> ActuarialFrame:
    logger.info("Calculating mortality cost")

    # Combine gender and smoking status for lookup
    # Note: Ensure 'gender' and 'smoking_status' columns exist before this point
    af["variable"] = af["gender"] + af["smoking status"]

    # Create the expression inside the function
    af["mortality rate"] = gs.assumption_lookup(
        "age-last",
        "variable",
        table_name="mortality_rates",
    )
    return af


def lapse_rate(af: ActuarialFrame) -> ActuarialFrame:
    # Only create the expression when the function is called in the pipeline
    af["lapse rate"] = gs.assumption_lookup(
        "policy_duration_as_int",
        table_name="lapse_rates",
    )

    return af


def premium_rate(af: ActuarialFrame) -> ActuarialFrame:
    af["premium rate"] = gs.assumption_lookup(
        "age-last",
        "variable",
        table_name="premium_rates",
    )
    return af


def probability_in_force(
    af: ActuarialFrame, monthly_persist_prob_col: str
) -> ActuarialFrame:
    """
    Calculates the probability of being in force at the start of each period.

    This assumes the input column contains lists of *monthly* probabilities
    of persisting (e.g., (1 - qx/12) * (1 - lapse/12)).

    Args:
        af: The ActuarialFrame.
        monthly_persist_prob_col: Name of the column providing lists of
                                   monthly persistence probabilities.

    Returns:
        The ActuarialFrame with the 'P[IF]' column added.
    """
    af["P[IF]"] = pl.col(monthly_persist_prob_col).list.eval(
        # Calculate cumulative product, shift down for start-of-period, fill first with 1.0
        pl.element().cum_prod().shift(1).fill_null(1.0)
    )
    return af


def probability_of_death(
    af: ActuarialFrame,
    p_if_col: str,
    annual_mortality_rate_col: str,
) -> ActuarialFrame:
    """
    Calculates the probability of death during each period.

    Formula: P[death](t) = P[IF](t) * (annual_mortality_rate(t) / 12)

    Args:
        af: The ActuarialFrame.
        p_if_col: Name of the column providing P[IF] lists.
        annual_mortality_rate_col: Name of the column providing lists of
                                   annual mortality rates (qx).

    Returns:
        The ActuarialFrame with the 'P[death]' column added.
    """
    p_if_expr = pl.col(p_if_col)
    mort_rate_expr = pl.col(annual_mortality_rate_col)
    monthly_mort_rate = mort_rate_expr / 12.0
    # Calculate P(death during t) = P(IF at start of t) * qx_monthly(t)
    prob_death_during_t = p_if_expr * monthly_mort_rate
    # Shift result down by 1 and fill first row with 0 to match spreadsheet layout
    expr = prob_death_during_t.list.eval(pl.element().shift(1).fill_null(0.0))
    af["P[death]"] = expr
    return af


def probability_of_lapse(
    af: ActuarialFrame,
    p_if_col: str,
    annual_mortality_rate_col: str,
    annual_lapse_rate_col: str,
) -> ActuarialFrame:
    """
    Calculates the probability of lapse during each period, assuming
    lapses occur after deaths within the period (end-of-period timing).

    Formula: P[lapse](t) = P[IF](t) * (1 - qx(t)/12) * (lapse_rate(t) / 12)

    Args:
        af: The ActuarialFrame.
        p_if_col: Name of the column providing P[IF] lists (at start of period).
        annual_mortality_rate_col: Name of the column providing lists of
                                   annual mortality rates (qx).
        annual_lapse_rate_col: Name of the column providing lists of
                               annual lapse rates.

    Returns:
        The ActuarialFrame with the 'P[lapse]' column added.
    """
    p_if_expr = pl.col(p_if_col)
    mort_rate_expr = pl.col(annual_mortality_rate_col)
    lapse_rate_expr = pl.col(annual_lapse_rate_col)

    monthly_mort_rate = mort_rate_expr / 12.0
    monthly_lapse_rate = lapse_rate_expr / 12.0

    # Calculate P(lapse during t) = P(IF start t) * P(Survive Death in t) * P(Lapse in t | Survived Death)
    prob_lapse_during_t = p_if_expr * (1.0 - monthly_mort_rate) * monthly_lapse_rate
    # Shift result down by 1 and fill first row with 0 to match spreadsheet layout
    expr = prob_lapse_during_t.list.eval(pl.element().shift(1).fill_null(0.0))
    af["P[lapse]"] = expr
    return af


def discount_rate(af: ActuarialFrame, interest_rate: float) -> ActuarialFrame:
    """
    Calculates the discount factor for each projection month.

    Formula: (1 / (1 + monthly_interest_rate)) ** proj_months

    Args:
        af: The ActuarialFrame.
        interest_rate: The annual interest rate.

    Returns:
        The ActuarialFrame with the 'discount_rate' column added.
    """
    logger.info("Calculating discount rate")
    monthly_interest_rate = interest_rate / 12.0
    monthly_discount_factor = 1.0 / (1.0 + monthly_interest_rate)
    # Use pl.col() inside list.eval to reference the list column correctly
    af["discount rate"] = pl.col("proj_months").list.eval(
        pl.lit(monthly_discount_factor).pow(pl.element())
    )
    return af


# Define a model function
def life_model(af):
    """Simple model function that works with the actual model points columns"""
    maintenance_cost = 15
    interest_rate = 0.05

    # Setup the mortality table
    setup_lapse_table()
    setup_mortality_table()
    setup_premium_table()

    af = setup_ages(af)

    # Calculate the rates using the assumption lookup functions
    af = mortality_rate(af)
    af = lapse_rate(af)
    af = premium_rate(af)

    af["expenses"] = maintenance_cost / 12

    af["monthly_persist_prob"] = (1 - af["mortality rate"] / 12) * (
        1 - af["lapse rate"] / 12
    )

    # Calculate probabilities
    af = probability_in_force(af, "monthly_persist_prob")
    af = probability_of_death(af, "P[IF]", "mortality rate")
    af = probability_of_lapse(af, "P[IF]", "mortality rate", "lapse rate")

    # Calculate premium cashflow
    af["premium cashflow"] = (
        af["premium rate"] / 12 * af["P[IF]"] * af["sum_assured"] / 1000
    )

    af["claims cashflow"] = af["P[death]"] * af["sum_assured"]
    af["expense cashflow"] = af["P[IF]"] * af["expenses"]
    af["profit"] = (
        af["premium cashflow"] - af["claims cashflow"] - af["expense cashflow"]
    )

    af = discount_rate(af, interest_rate)

    af["discounted premium cashflow"] = af["premium cashflow"] * af["discount rate"]
    af["discounted claims cashflow"] = af["claims cashflow"] * af["discount rate"]
    af["discounted expense cashflow"] = af["expense cashflow"] * af["discount rate"]
    af["discounted profit cashflow"] = af["profit"] * af["discount rate"]

    return af
