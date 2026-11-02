# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: LLM-friendly scenario config parsing for declarative shock specifications.
# ABOUTME: Converts dict/JSON configs to Shock objects for runtime injection.
# ruff: noqa: PLR2004, E501, C901

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
{"column": "infl_rate", "add": 0.01}
```
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from gaspatchio.scenarios._aggregators import _AGGREGATOR_REGISTRY
from gaspatchio.scenarios._metric import _Partitioned
from gaspatchio.scenarios.shocks import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    PipelineShock,
    Shock,
    TimeConditionalShock,
)

if TYPE_CHECKING:
    from gaspatchio.scenarios._metric import Aggregator

# Valid operation keys in shock config (basic operations)
SHOCK_OPERATIONS = {"multiply", "add", "set"}

# Extended operations for the unified schema
EXTENDED_OPERATIONS = {"clip", "max", "min"}


def _parse_clip_value(
    clip_config: dict[str, Any] | list[Any] | None,
) -> ClipShock:
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


# Every key a shock entry may hold: its target, its operation, and what
# confines it. Anything else is refused, so a misspelt key is never read as
# a shock that does nothing.
_TARGET_KEYS = {"table", "column", "param"}
_CONFINING_KEYS = {"where", "when"}
_SHOCK_KEYS = (
    _TARGET_KEYS
    | SHOCK_OPERATIONS
    | EXTENDED_OPERATIONS
    | _CONFINING_KEYS
    | {"pipeline", "shock"}
)


def _two_shocks(config: object, operation: str) -> tuple[Any, Any]:
    """Return the two shock entries a ``max`` or ``min`` takes."""
    if not isinstance(config, list) or len(config) != 2:
        msg = f"{operation} operation requires array of 2 shock configs"
        raise ValueError(msg)
    return config[0], config[1]


def _core(config: dict[str, Any]) -> Shock:  # noqa: PLR0911 -- one per operation
    """Return the shock an entry's operation names, before where/when confine it."""
    if "shock" in config:
        return _parse_node(config["shock"])
    if "pipeline" in config:
        steps = config["pipeline"]
        if not isinstance(steps, list) or len(steps) == 0:
            msg = "pipeline must be a non-empty list of shock steps"
            raise ValueError(msg)
        return PipelineShock(shocks=tuple(_parse_node(step) for step in steps))
    if "max" in config:
        a, b = _two_shocks(config["max"], "max")
        return MaxShock(shock_a=_parse_node(a), shock_b=_parse_node(b))
    if "min" in config:
        a, b = _two_shocks(config["min"], "min")
        return MinShock(shock_a=_parse_node(a), shock_b=_parse_node(b))
    operations_found = sorted(op for op in SHOCK_OPERATIONS if op in config)
    has_clip = "clip" in config
    if not operations_found and not has_clip:
        all_ops = SHOCK_OPERATIONS | EXTENDED_OPERATIONS | {"pipeline", "max", "min"}
        msg = (
            f"Shock config must include an operation: {sorted(all_ops)}. "
            f"Got keys: {list(config.keys())}"
        )
        raise ValueError(msg)
    if len(operations_found) > 1:
        msg = (
            f"Shock config must include exactly one basic operation, "
            f"but found multiple: {operations_found}"
        )
        raise ValueError(msg)
    if not operations_found:
        return _parse_clip_value(config["clip"])
    operation = operations_found[0]
    value = config[operation]
    base: Shock
    if operation == "multiply":
        base = MultiplicativeShock(factor=value)
    elif operation == "add":
        base = AdditiveShock(delta=value)
    else:  # "set"
        base = OverrideShock(value=value)
    # Syntactic sugar: an operation beside a clip is the two in sequence.
    if has_clip:
        return PipelineShock(shocks=(base, _parse_clip_value(config["clip"])))
    return base


def _parse_node(config: object) -> Shock:
    """Parse one shock entry, at any depth, into a Shock.

    The operation is read first, then ``where`` confines it to rows, then
    ``when`` to periods -- so ``{multiply, where, when}`` is a time condition
    around a filter around a multiply, as written. A target (``table:`` or
    ``column:``, with ``param:`` read as ``column:``) lands on the shock this
    entry builds.
    """
    if not isinstance(config, dict):
        msg = f"A shock entry is a mapping of operation keys; got {config!r}"
        raise ValueError(msg)  # noqa: TRY004 -- a malformed recipe, as the rest are
    unknown = sorted(set(config) - _SHOCK_KEYS)
    if unknown:
        msg = (
            f"Shock config has keys a shock does not take: {unknown}. A shock "
            f"entry holds a target ({sorted(_TARGET_KEYS - {'param'})}), one "
            f"operation ({sorted(SHOCK_OPERATIONS | EXTENDED_OPERATIONS | {'pipeline'})}) "
            "and optionally where/when."
        )
        raise ValueError(msg)
    if "param" in config and "column" in config:
        msg = (
            "Shock config names both column: and param:. param: is read as "
            "column: -- the model-point column the shock moves -- so give one."
        )
        raise ValueError(msg)
    shock = _core(config)
    if config.get("where") is not None:
        shock = FilteredShock(shock=shock, where=config["where"])
    if config.get("when") is not None:
        shock = TimeConditionalShock(shock=shock, when=config["when"])
    table = config.get("table")
    column = config.get("column", config.get("param"))
    if table is None and column is None:
        return shock
    return replace(shock, table=table, column=column)  # type: ignore[type-var]


def parse_shock_config(config: dict[str, Any]) -> Shock:
    """
    Parse a single shock configuration dict into a Shock object.

    Converts LLM-friendly dict format into the appropriate Shock subclass.
    This enables LLMs to generate JSON/dict configs that the framework
    can execute without writing Python code, and it is the form
    ``ScenarioRun.to_yaml`` writes, so a plan written down reads back to
    the same ``source_sha()``.

    Supports the unified schema with:
    - Basic operations: multiply, add, set
    - Value constraints: clip
    - Composable operations: pipeline, max, min (whose steps are shock
      entries of any kind)
    - Dimension filters: where
    - Time conditions: when
    - A confined shock written out in full: ``{where: ..., shock: {...}}``

    !!! note "When to use"
        - Parsing LLM-generated shock specifications
        - Loading shock configs from JSON/YAML files
        - Building shocks from API payloads

    Args:
        config: Dict with keys:
            - table or column (required): the assumption table the shock
              moves, by the name its Table was built with, or the
              model-point column it moves. ``param`` is read as ``column``.
            - One operation or pipeline (required)
            - where (optional): Dimension filter conditions
            - when (optional): Time condition

    Returns:
        Appropriate Shock subclass instance, its target on the outermost
        shock only.

    Raises:
        ValueError: If config is missing required fields, holds a key a shock
            does not take, or has invalid structure

    Examples:
    --------
    **Simple multiplicative shock:**

    ```python
    from gaspatchio.scenarios import parse_shock_config

    config = {"table": "mortality", "multiply": 1.2}
    shock = parse_shock_config(config)
    # Returns: MultiplicativeShock(factor=1.2, table="mortality")
    ```

    **A model-point column (a valuation rate up 100bp):**

    ```python
    config = {"column": "valuation_rate", "add": 0.01}
    shock = parse_shock_config(config)
    # Returns: AdditiveShock(delta=0.01, column="valuation_rate")
    ```

    **Solvency II lapse up (multiply then cap):**

    ```python
    config = {"table": "lapse", "pipeline": [{"multiply": 1.5}, {"clip": {"max": 1.0}}]}
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
    config = {"table": "lapse", "max": [{"multiply": 0.5}, {"add": -0.2}]}
    shock = parse_shock_config(config)
    # Returns: MaxShock(...)
    ```

    **Dimension-filtered shock:**

    ```python
    config = {"table": "lapse", "multiply": 1.25, "where": {"duration": {"lte": 3}}}
    shock = parse_shock_config(config)
    # Returns: FilteredShock(...)
    ```

    **Time-conditional shock:**

    ```python
    config = {"table": "lapse", "add": 0.40, "when": {"t": {"eq": 0}}}
    shock = parse_shock_config(config)
    # Returns: TimeConditionalShock(...)
    ```

    """
    if not any(key in config for key in _TARGET_KEYS):
        msg = (
            "Shock config must name its target: 'table' (an assumption table, "
            "by the name its Table was built with) or 'column' (a model-point "
            "column; 'param' is read as 'column')."
        )
        raise ValueError(msg)
    return _parse_node(config)


def parse_scenario_config(
    config: list[str | dict[str, Any]],
) -> dict[str, list[Shock]]:
    """
    Parse a full scenario configuration into shock mappings.

    Converts LLM-friendly list of scenario specs into the dict[str, list[Shock]]
    format used by ScenarioRun and Table.from_shocks(). This is the main entry
    point for LLM-generated scenario configurations.

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
    from gaspatchio.scenarios import parse_scenario_config

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


def _aggregations_not_a_list(spec: object) -> str:
    """Return the refusal for aggregations written as something other than a list."""
    example = "[{'kind': 'Sum', 'alias': 'total_loss', 'column': 'loss'}]"
    if isinstance(spec, dict):
        named = ", ".join(repr(key) for key in spec)
        shape = (
            f"a mapping keyed by alias ({named}): move each key into its "
            "entry as 'alias'"
        )
    else:
        shape = f"a {type(spec).__name__}"
    return (
        "A plan's aggregations are a list, one entry per aggregator naming its "
        f"kind and alias, for example {example}. These were given as {shape}."
    )


def parse_aggregations(
    spec: list[dict[str, Any]],
) -> tuple[Aggregator | _Partitioned, ...]:
    """Parse a list-of-dict YAML spec into a tuple of aggregators.

    Each entry is a recipe dict carrying ``kind``, ``alias``, plus the
    aggregator's constructor kwargs -- the aggregator's own canonical form
    with its alias beside it. ``over`` (one column name or a list of them)
    partitions the entry exactly as ``.over(by)`` does, which is how a
    partitioned aggregation is written by hand; ``_Partitioned`` entries,
    carrying ``by`` (list of partition columns) and ``inner`` (a nested recipe
    dict), are the same thing in the shape an audit record writes it.
    Unknown ``kind`` raises ``ValueError`` listing the available registrations.
    Aggregations given as anything but a list -- a mapping keyed by alias, say
    ``{"total": {"kind": "Sum", ...}}`` -- raise ``ValueError`` saying how to
    write them as the list.
    """
    if not isinstance(spec, list):
        # A config-format problem rather than a generic type error, so it is
        # a ValueError, which is what callers reading a recipe catch.
        raise ValueError(_aggregations_not_a_list(spec))  # noqa: TRY004

    return tuple(_parse_one(entry) for entry in spec)


def _parse_one(entry: dict[str, Any]) -> Aggregator | _Partitioned:
    """Parse one aggregator recipe dict into an aggregator or _Partitioned.

    A malformed recipe is a ``ValueError`` naming what is wrong with it, like
    every other refusal here -- never the ``AttributeError`` or ``KeyError``
    that reaching into something that is not a recipe would raise, which a
    caller reading a file cannot tell from a defect.
    """
    if not isinstance(entry, dict):
        msg = (
            "Aggregator entry must be an object with 'kind' and 'alias' fields; "
            f"got {entry!r}"
        )
        raise ValueError(msg)  # noqa: TRY004 -- a malformed recipe, as the rest are
    kind = entry.get("kind")
    if kind is None:
        msg = f"Aggregator entry missing 'kind' field: {entry!r}"
        raise ValueError(msg)
    alias = entry.get("alias")
    if alias is None:
        msg = f"Aggregator entry missing 'alias' field: {entry!r}"
        raise ValueError(msg)

    if kind == "_Partitioned":
        inner_entry = entry.get("inner")
        by = entry.get("by")
        if not isinstance(inner_entry, dict) or not (
            isinstance(by, list) and by and all(isinstance(one, str) for one in by)
        ):
            msg = (
                f"Aggregator {alias!r}: a '_Partitioned' entry carries 'by', a "
                "list of partition column names, and 'inner', the partitioned "
                f"aggregator's own recipe; got {entry!r}"
            )
            raise ValueError(msg)
        # The inner recipe doesn't carry its own alias; the wrapper owns it.
        # _parse_one requires an alias, so synthesise a sentinel for recursion;
        # the inner's .alias_ is irrelevant once it's wrapped in _Partitioned.
        inner_with_alias = dict(inner_entry)
        inner_with_alias.setdefault("alias", "__inner__")
        inner = _parse_one(inner_with_alias)
        return _Partitioned(by=tuple(by), inner=inner, alias=alias)

    if kind not in _AGGREGATOR_REGISTRY:
        available = sorted(_AGGREGATOR_REGISTRY.keys())
        msg = (
            f"Aggregator {kind!r} is not registered. Available: {available}. "
            f"To register a custom aggregator, call register_aggregator() "
            f"before parsing."
        )
        raise ValueError(msg)

    cls = _AGGREGATOR_REGISTRY[kind]
    kwargs = {k: v for k, v in entry.items() if k not in {"kind", "alias", "over"}}
    # YAML round-trip emits tuples as lists; coerce known tuple fields back.
    if "levels" in kwargs and isinstance(kwargs["levels"], list):
        kwargs["levels"] = tuple(kwargs["levels"])
    # The registry holds classes, so what one builds is untyped until it is
    # named here: an aggregator, or the partitioned wrapper ``over`` makes.
    built = cls(**kwargs).alias(alias)
    over = entry.get("over")
    if over is None:
        plain: Aggregator = built
        return plain
    if not (
        isinstance(over, str)
        or (isinstance(over, list) and all(isinstance(by, str) for by in over))
    ):
        msg = (
            f"Aggregator {alias!r}: 'over' names the column or columns to "
            f"partition by, as a string or a list of strings; got {over!r}."
        )
        raise ValueError(msg)
    partitioned: _Partitioned = built.over(
        over if isinstance(over, str) else tuple(over)
    )
    return partitioned


__all__ = ["parse_aggregations", "parse_scenario_config", "parse_shock_config"]
