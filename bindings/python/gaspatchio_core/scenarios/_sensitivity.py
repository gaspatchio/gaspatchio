# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Implementation of sensitivity_analysis() for parameter sweep scenarios.
# ABOUTME: Generates shock configurations across a range of values for testing.

"""Implementation of sensitivity_analysis() for parameter sweep scenarios."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from gaspatchio_core.scenarios.shocks import Shock

from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    MultiplicativeShock,
    OverrideShock,
)


def sensitivity_analysis(  # noqa: PLR0913
    table: str,
    shock_type: Literal["multiplicative", "additive", "override"],
    values: list[float],
    *,
    column: str | None = None,
    scenario_format: str | None = None,
    include_base: bool = False,
) -> dict[str, list[Shock]]:
    """
    Generate shock configurations for sensitivity analysis across a range of values.

    Creates a dictionary of scenarios, each with a single shock applied at
    different values. Useful for parameter sweeps and sensitivity testing.

    !!! note "When to use"
        - Sensitivity testing across parameter ranges
        - Generating stress scenarios for regulatory reporting
        - Parameter calibration and validation
        - Creating scenario grids for analysis

    Args:
        table: The table name the shocks target
        shock_type: Type of shock - "multiplicative", "additive", or "override"
        values: List of values to sweep (factors, deltas, or constants)
        column: Optional column name within the table
        scenario_format: Format string for scenario IDs (default: "{table}_{value}")
        include_base: If True, include a "BASE" scenario with no shocks

    Returns:
        Dictionary mapping scenario IDs to lists of shocks

    Raises:
        ValueError: If values is empty or shock_type is invalid

    Examples:
    --------
    **Mortality sensitivity sweep:**

    ```python no_output_check
    from gaspatchio_core.scenarios._sensitivity import sensitivity_analysis

    scenarios = sensitivity_analysis(
        table="mortality",
        shock_type="multiplicative",
        values=[0.8, 0.9, 1.0, 1.1, 1.2],
    )
    # Returns: {"mortality_0.8": [...], "mortality_0.9": [...], ...}
    ```

    **Interest rate parallel shifts:**

    ```python no_output_check
    scenarios = sensitivity_analysis(
        table="discount_rates",
        shock_type="additive",
        values=[-0.01, -0.005, 0.0, 0.005, 0.01],
    )
    ```

    **With custom scenario naming:**

    ```python no_output_check
    scenarios = sensitivity_analysis(
        table="mortality",
        shock_type="multiplicative",
        values=[0.9, 1.1],
        scenario_format="mort_shock_{value}",
    )
    # Returns: {"mort_shock_0.9": [...], "mort_shock_1.1": [...]}
    ```

    **Include base case:**

    ```python no_output_check
    scenarios = sensitivity_analysis(
        table="mortality",
        shock_type="multiplicative",
        values=[0.9, 1.1],
        include_base=True,
    )
    # Returns: {"BASE": [], "mortality_0.9": [...], "mortality_1.1": [...]}
    ```

    """
    if not values:
        msg = "values must not be empty"
        raise ValueError(msg)

    valid_shock_types = {"multiplicative", "additive", "override"}
    if shock_type not in valid_shock_types:
        msg = f"shock_type must be one of {valid_shock_types}, got '{shock_type}'"
        raise ValueError(msg)

    # Default format string
    if scenario_format is None:
        scenario_format = "{table}_{value}"

    result: dict[str, list[Shock]] = {}

    # Optionally include base case
    if include_base:
        result["BASE"] = []

    # Generate shocks for each value
    for value in values:
        scenario_id = scenario_format.format(table=table, value=value)
        shock = _create_shock(shock_type, value, table, column)
        result[scenario_id] = [shock]

    return result


def _create_shock(
    shock_type: str,
    value: float,
    table: str,
    column: str | None,
) -> Shock:
    """Create appropriate shock instance based on type."""
    if shock_type == "multiplicative":
        return MultiplicativeShock(factor=value, table=table, column=column)
    if shock_type == "additive":
        return AdditiveShock(delta=value, table=table, column=column)
    # override
    return OverrideShock(value=value, table=table, column=column)


# Module is now internal; no public __all__.
# Use ScenarioRun + sweep configs instead. The function remains importable
# from gaspatchio_core.scenarios._sensitivity for internal/tutorial callers.
