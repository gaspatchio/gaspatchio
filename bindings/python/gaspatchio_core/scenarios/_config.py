# ABOUTME: LLM-friendly scenario config parsing for declarative shock specifications.
# ABOUTME: Converts dict/JSON configs to Shock objects for runtime injection.

"""LLM-friendly scenario config parsing for declarative shock specifications."""

from __future__ import annotations

from typing import Any

from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    MultiplicativeShock,
    OverrideShock,
    Shock,
)

# Valid operation keys in shock config
SHOCK_OPERATIONS = {"multiply", "add", "set"}


def parse_shock_config(config: dict[str, Any]) -> Shock:
    """
    Parse a single shock configuration dict into a Shock object.

    Converts LLM-friendly dict format into the appropriate Shock subclass.
    This enables LLMs to generate JSON/dict configs that the framework
    can execute without writing Python code.

    !!! note "When to use"
        - Parsing LLM-generated shock specifications
        - Loading shock configs from JSON/YAML files
        - Building shocks from API payloads

    Args:
        config: Dict with keys:
            - table (required): Target table name
            - column (optional): Target column within table
            - One of: multiply, add, or set (required)

    Returns:
        Appropriate Shock subclass instance

    Raises:
        ValueError: If config is missing required fields or has invalid structure

    Examples:
    --------
    **Multiplicative shock:**

    ```python
    from gaspatchio_core.scenarios import parse_shock_config

    config = {"table": "mortality", "multiply": 1.2}
    shock = parse_shock_config(config)
    # Returns: MultiplicativeShock(factor=1.2, table="mortality")
    ```

    **Additive shock with column:**

    ```python
    config = {"table": "rates", "column": "forward", "add": 0.005}
    shock = parse_shock_config(config)
    # Returns: AdditiveShock(delta=0.005, table="rates", column="forward")
    ```

    **Override shock:**

    ```python
    config = {"table": "lapse", "set": 0.0}
    shock = parse_shock_config(config)
    # Returns: OverrideShock(value=0.0, table="lapse")
    ```

    """
    # Validate table
    if "table" not in config:
        msg = "Shock config must include 'table' key specifying target table name"
        raise ValueError(msg)

    table = config["table"]
    column = config.get("column")

    # Find which operation is specified
    operations_found = [op for op in SHOCK_OPERATIONS if op in config]

    if len(operations_found) == 0:
        msg = (
            f"Shock config must include exactly one operation: {SHOCK_OPERATIONS}. "
            f"Got keys: {list(config.keys())}"
        )
        raise ValueError(msg)

    if len(operations_found) > 1:
        msg = (
            f"Shock config must include exactly one operation, "
            f"but found multiple: {operations_found}"
        )
        raise ValueError(msg)

    operation = operations_found[0]
    value = config[operation]

    # Create appropriate shock type
    if operation == "multiply":
        return MultiplicativeShock(factor=value, table=table, column=column)
    if operation == "add":
        return AdditiveShock(delta=value, table=table, column=column)
    # Default case: "set" operation
    return OverrideShock(value=value, table=table, column=column)


def parse_scenario_config(
    config: list[str | dict[str, Any]],
) -> dict[str, list[Shock]]:
    """
    Parse a full scenario configuration into shock mappings.

    Converts LLM-friendly list of scenario specs into the dict[str, list[Shock]]
    format used by describe_scenarios() and Table.from_shocks(). This is the
    main entry point for LLM-generated scenario configurations.

    !!! note "When to use"
        - Parsing LLM-generated scenario configurations
        - Loading scenario configs from JSON/YAML files
        - Building scenarios from natural language queries

    Args:
        config: List of scenario specifications. Each element can be:
            - str: Scenario ID with no shocks (e.g., "BASE")
            - dict: Scenario with optional shocks:
                - id (required): Scenario identifier
                - shocks (optional): List of shock configs

    Returns:
        Dictionary mapping scenario IDs to lists of Shock objects

    Raises:
        ValueError: If config is empty, has duplicates, or invalid structure

    Examples:
    --------
    **Simple config with strings:**

    ```python
    from gaspatchio_core.scenarios import parse_scenario_config

    config = ["BASE", "STRESS"]
    scenarios = parse_scenario_config(config)
    # Returns: {"BASE": [], "STRESS": []}
    ```

    **LLM-generated config with shocks:**

    ```python
    config = [
        {"id": "BASE"},
        {
            "id": "RATES_UP_50BPS",
            "shocks": [{"table": "discount_rates", "add": 0.005}],
        },
    ]
    scenarios = parse_scenario_config(config)
    # Returns: {
    #     "BASE": [],
    #     "RATES_UP_50BPS": [AdditiveShock(delta=0.005, table="discount_rates")],
    # }
    ```

    **Complex multi-shock scenario:**

    ```python
    config = [
        {"id": "BASE"},
        {
            "id": "ADVERSE",
            "shocks": [
                {"table": "mortality", "multiply": 1.2},
                {"table": "lapse", "multiply": 0.8},
                {"table": "interest", "add": -0.01},
            ],
        },
    ]
    scenarios = parse_scenario_config(config)
    ```

    """
    if not config:
        msg = "Scenario config cannot be empty. Provide at least one scenario."
        raise ValueError(msg)

    result: dict[str, list[Shock]] = {}
    seen_ids: set[str] = set()

    for item in config:
        if isinstance(item, str):
            # Simple string scenario ID with no shocks
            scenario_id = item
            shocks: list[Shock] = []
        elif isinstance(item, dict):
            # Dict scenario with optional shocks
            if "id" not in item:
                msg = (
                    "Scenario dict must include 'id' key. "
                    f"Got keys: {list(item.keys())}"
                )
                raise ValueError(msg)

            scenario_id = item["id"]
            shock_configs = item.get("shocks", [])
            shocks = [parse_shock_config(sc) for sc in shock_configs]
        else:
            msg = (
                f"Scenario config items must be str or dict, got {type(item).__name__}"
            )
            raise TypeError(msg)

        # Check for duplicates
        if scenario_id in seen_ids:
            msg = (
                f"Duplicate scenario ID: '{scenario_id}'. "
                "Each scenario ID must be unique."
            )
            raise ValueError(msg)

        seen_ids.add(scenario_id)
        result[scenario_id] = shocks

    return result


__all__ = ["parse_scenario_config", "parse_shock_config"]
