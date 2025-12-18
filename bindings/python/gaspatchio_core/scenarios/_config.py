# ABOUTME: LLM-friendly scenario config parsing for declarative shock specifications.
# ABOUTME: Converts dict/JSON configs to Shock objects for runtime injection.

"""LLM-friendly scenario config parsing for declarative shock specifications.

This module parses the unified schema for scenario shocks:

```json
{
  "id": "SCENARIO_NAME",
  "shocks": [
    {
      "table": "lapse",
      "pipeline": [
        {"multiply": 1.5},
        {"clip": {"max": 1.0}}
      ],
      "where": {"duration": {"lte": 10}},
      "when": {"t": {"gte": 0}}
    }
  ]
}
```

Syntactic sugar for simple cases:
```json
{"table": "mortality", "multiply": 1.15}
{"table": "lapse", "multiply": 1.5, "clip": [null, 1.0]}
{"param": "infl_rate", "add": 0.01}
```
"""

from __future__ import annotations

from typing import Any

from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    ParameterShock,
    PipelineShock,
    Shock,
    TimeConditionalShock,
)

# Valid operation keys in shock config (basic operations)
SHOCK_OPERATIONS = {"multiply", "add", "set"}

# Extended operations for the unified schema
EXTENDED_OPERATIONS = {"clip", "max", "min"}

# Modifier keys that wrap operations
MODIFIER_KEYS = {"where", "when", "pipeline"}

# Reserved keys that are not operations
RESERVED_KEYS = {"table", "column", "where", "when", "pipeline", "param"}


def _parse_clip_value(clip_config: dict | list | None) -> ClipShock:
    """Parse clip configuration into ClipShock.

    Args:
        clip_config: Can be:
            - {"min": 0.0, "max": 1.0}
            - {"max": 1.0}
            - [null, 1.0] (syntactic sugar for max only)
            - [0.0, null] (syntactic sugar for min only)
            - [0.0, 1.0] (syntactic sugar for both)

    Returns:
        ClipShock instance

    """
    if isinstance(clip_config, dict):
        return ClipShock(
            min_value=clip_config.get("min"),
            max_value=clip_config.get("max"),
        )
    if isinstance(clip_config, list):
        if len(clip_config) != 2:
            msg = f"clip array must have exactly 2 elements [min, max], got {len(clip_config)}"
            raise ValueError(msg)
        min_val = clip_config[0] if clip_config[0] is not None else None
        max_val = clip_config[1] if clip_config[1] is not None else None
        return ClipShock(min_value=min_val, max_value=max_val)
    msg = f"clip must be dict or [min, max] array, got {type(clip_config).__name__}"
    raise ValueError(msg)


def _parse_pipeline_step(step: dict[str, Any]) -> Shock:
    """Parse a single step in a pipeline into a Shock.

    Pipeline steps are simpler - they don't have table/column/where/when.
    """
    if "multiply" in step:
        return MultiplicativeShock(factor=step["multiply"])
    if "add" in step:
        return AdditiveShock(delta=step["add"])
    if "set" in step:
        return OverrideShock(value=step["set"])
    if "clip" in step:
        return _parse_clip_value(step["clip"])
    if "max" in step:
        # max takes two shock configs
        max_config = step["max"]
        if not isinstance(max_config, list) or len(max_config) != 2:
            msg = "max operation requires array of 2 shock configs"
            raise ValueError(msg)
        return MaxShock(
            shock_a=_parse_pipeline_step(max_config[0]),
            shock_b=_parse_pipeline_step(max_config[1]),
        )
    if "min" in step:
        # min takes two shock configs
        min_config = step["min"]
        if not isinstance(min_config, list) or len(min_config) != 2:
            msg = "min operation requires array of 2 shock configs"
            raise ValueError(msg)
        return MinShock(
            shock_a=_parse_pipeline_step(min_config[0]),
            shock_b=_parse_pipeline_step(min_config[1]),
        )
    msg = f"Unknown pipeline step operation: {list(step.keys())}"
    raise ValueError(msg)


def parse_shock_config(config: dict[str, Any]) -> Shock:
    """
    Parse a single shock configuration dict into a Shock object.

    Converts LLM-friendly dict format into the appropriate Shock subclass.
    This enables LLMs to generate JSON/dict configs that the framework
    can execute without writing Python code.

    Supports the unified schema with:
    - Basic operations: multiply, add, set
    - Value constraints: clip
    - Composable operations: pipeline, max, min
    - Dimension filters: where
    - Time conditions: when

    !!! note "When to use"
        - Parsing LLM-generated shock specifications
        - Loading shock configs from JSON/YAML files
        - Building shocks from API payloads

    Args:
        config: Dict with keys:
            - table (required): Target table name
            - column (optional): Target column within table
            - One operation or pipeline (required)
            - where (optional): Dimension filter conditions
            - when (optional): Time condition

    Returns:
        Appropriate Shock subclass instance

    Raises:
        ValueError: If config is missing required fields or has invalid structure

    Examples:
    --------
    **Simple multiplicative shock:**

    ```python
    from gaspatchio_core.scenarios import parse_shock_config

    config = {"table": "mortality", "multiply": 1.2}
    shock = parse_shock_config(config)
    # Returns: MultiplicativeShock(factor=1.2, table="mortality")
    ```

    **Solvency II lapse up (multiply then cap):**

    ```python
    config = {
        "table": "lapse",
        "pipeline": [
            {"multiply": 1.5},
            {"clip": {"max": 1.0}}
        ]
    }
    shock = parse_shock_config(config)
    # Returns: PipelineShock(...)
    ```

    **Syntactic sugar with clip:**

    ```python
    config = {"table": "lapse", "multiply": 1.5, "clip": [None, 1.0]}
    shock = parse_shock_config(config)
    # Returns: PipelineShock([MultiplicativeShock, ClipShock])
    ```

    **Solvency II lapse down (max of two options):**

    ```python
    config = {
        "table": "lapse",
        "max": [
            {"multiply": 0.5},
            {"add": -0.2}
        ]
    }
    shock = parse_shock_config(config)
    # Returns: MaxShock(...)
    ```

    **Dimension-filtered shock:**

    ```python
    config = {
        "table": "lapse",
        "multiply": 1.25,
        "where": {"duration": {"lte": 3}}
    }
    shock = parse_shock_config(config)
    # Returns: FilteredShock(...)
    ```

    **Time-conditional shock:**

    ```python
    config = {
        "table": "lapse",
        "add": 0.40,
        "when": {"t": {"eq": 0}}
    }
    shock = parse_shock_config(config)
    # Returns: TimeConditionalShock(...)
    ```

    """
    # Check if this is a parameter shock
    if "param" in config:
        param_name = config["param"]

        # Find which operation is specified
        operations_found = [op for op in SHOCK_OPERATIONS if op in config]
        if len(operations_found) != 1:
            msg = (
                f"Parameter shock must include exactly one operation: {SHOCK_OPERATIONS}. "
                f"Got: {operations_found}"
            )
            raise ValueError(msg)

        operation = operations_found[0]
        value = config[operation]

        return ParameterShock(param=param_name, operation=operation, value=value)

    # Validate table for non-parameter shocks
    if "table" not in config:
        msg = "Shock config must include 'table' or 'param' key"
        raise ValueError(msg)

    table = config["table"]
    column = config.get("column")
    where_clause = config.get("where")
    when_clause = config.get("when")

    # Check if this is a pipeline-based config
    if "pipeline" in config:
        steps = config["pipeline"]
        if not isinstance(steps, list) or len(steps) == 0:
            msg = "pipeline must be a non-empty list of shock steps"
            raise ValueError(msg)

        shock_steps = tuple(_parse_pipeline_step(step) for step in steps)
        base_shock: Shock = PipelineShock(shocks=shock_steps, table=table, column=column)

    # Check if this is a max/min operation at the top level
    elif "max" in config:
        max_config = config["max"]
        if not isinstance(max_config, list) or len(max_config) != 2:
            msg = "max operation requires array of 2 shock configs"
            raise ValueError(msg)
        base_shock = MaxShock(
            shock_a=_parse_pipeline_step(max_config[0]),
            shock_b=_parse_pipeline_step(max_config[1]),
            table=table,
            column=column,
        )

    elif "min" in config:
        min_config = config["min"]
        if not isinstance(min_config, list) or len(min_config) != 2:
            msg = "min operation requires array of 2 shock configs"
            raise ValueError(msg)
        base_shock = MinShock(
            shock_a=_parse_pipeline_step(min_config[0]),
            shock_b=_parse_pipeline_step(min_config[1]),
            table=table,
            column=column,
        )

    else:
        # Find which basic operation is specified
        operations_found = [op for op in SHOCK_OPERATIONS if op in config]
        has_clip = "clip" in config

        if len(operations_found) == 0 and not has_clip:
            all_ops = SHOCK_OPERATIONS | EXTENDED_OPERATIONS | {"pipeline", "max", "min"}
            msg = (
                f"Shock config must include an operation: {all_ops}. "
                f"Got keys: {list(config.keys())}"
            )
            raise ValueError(msg)

        if len(operations_found) > 1:
            msg = (
                f"Shock config must include exactly one basic operation, "
                f"but found multiple: {operations_found}"
            )
            raise ValueError(msg)

        # Build the base shock
        if operations_found:
            operation = operations_found[0]
            value = config[operation]

            if operation == "multiply":
                base_shock = MultiplicativeShock(factor=value, table=table, column=column)
            elif operation == "add":
                base_shock = AdditiveShock(delta=value, table=table, column=column)
            else:  # "set"
                base_shock = OverrideShock(value=value, table=table, column=column)

            # Syntactic sugar: if clip is also present, wrap in pipeline
            if has_clip:
                clip_shock = _parse_clip_value(config["clip"])
                base_shock = PipelineShock(
                    shocks=(base_shock, clip_shock),
                    table=table,
                    column=column,
                )
        else:
            # Only clip, no basic operation
            base_shock = _parse_clip_value(config["clip"])
            # Add table/column to clip shock
            base_shock = ClipShock(
                min_value=base_shock.min_value,
                max_value=base_shock.max_value,
                table=table,
                column=column,
            )

    # Apply where clause if present
    if where_clause:
        base_shock = FilteredShock(
            shock=base_shock,
            where=where_clause,
            table=table,
            column=column,
        )

    # Apply when clause if present
    if when_clause:
        base_shock = TimeConditionalShock(
            shock=base_shock,
            when=when_clause,
            table=table,
            column=column,
        )

    return base_shock


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
