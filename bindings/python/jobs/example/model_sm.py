# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import sys
from pathlib import Path

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.functions import fill_series, floor
from loguru import logger

# Add the current directory to the path so we can import setup.py
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))


def setup_ages(af: ActuarialFrame) -> ActuarialFrame:
    """
    Setup the ages for the model.
    """
    logger.info("Setting up ages")
    # Add age squared calculation
    max_age = 100
    af["num_proj_months"] = (max_age - af["age"]) * 12 + 1

    # Using custom plugin functions
    af["proj_months"] = fill_series(af["num_proj_months"], 0, 1)
    af["proj_years"] = floor((af["proj_months"] - 1) / 12) + 1

    # Update age with monthly increment
    af["age"] = af["age"] + (af["proj_months"] / 12)

    # Update policy_duration with monthly increment
    af["policy_duration"] = af["policy_duration"] + (af["proj_months"] / 12)

    # Use floor to get age last
    af["age-last"] = floor(af["age"])

    # Add gender and smoking status
    af["gender_smoking"] = af["gender"] + af["smoking_status"]

    return af


def mortality_cost(af: ActuarialFrame) -> ActuarialFrame:
    logger.info("Calculating mortality cost")

    # Combine gender and smoking status for lookup
    af["gender_smoking"] = af["gender"] + af["smoking_status"]

    logger.info("Looking up mortality rates")
    af = af.lookup_table_vector("mortality_rates")
    # Calculate mortality cost as sum_assured * mortality_rate
    af["mortality_cost"] = af["sum_assured"] * af["mortality_rate"]
    af["mortality_vect"] = af["mortality_cost"] * af["mortality_rate"]

    return af


# Define a model function
def life_model(af):
    """Simple model function that works with the actual model points columns"""
    # Setup the mortality table
    # setup_mortality_table()

    af = setup_ages(af)

    return af
