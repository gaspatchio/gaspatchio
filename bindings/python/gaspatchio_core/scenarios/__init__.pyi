# ABOUTME: Type stubs for scenario support module.
# ABOUTME: Provides type hints for scenario expansion and audit trail functions.

from collections.abc import Iterator
from typing import Any, Literal, overload

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios.shocks import (
    AdditiveShock as AdditiveShock,
    ClipShock as ClipShock,
    FilterCondition as FilterCondition,
    FilteredShock as FilteredShock,
    MaxShock as MaxShock,
    MinShock as MinShock,
    MultiplicativeShock as MultiplicativeShock,
    OverrideShock as OverrideShock,
    ParameterShock as ParameterShock,
    PipelineShock as PipelineShock,
    RelativeFloorShock as RelativeFloorShock,
    Shock as Shock,
    TimeConditionalShock as TimeConditionalShock,
)

def with_scenarios(
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = "scenario_id",
    *,
    categorical: bool = False,
) -> ActuarialFrame: ...
def batch_scenarios[T: (str, int)](
    scenario_ids: list[T],
    batch_size: int = 1000,
) -> Iterator[list[T]]: ...
@overload
def describe_scenarios(
    scenarios: dict[str, list[Shock]],
    output_format: Literal["text", "markdown"] = "markdown",
) -> str: ...
@overload
def describe_scenarios(
    scenarios: dict[str, list[Shock]],
    output_format: Literal["dict"],
) -> dict[str, list[str]]: ...
def sensitivity_analysis(
    table: str,
    shock_type: Literal["multiplicative", "additive", "override"],
    values: list[float],
    *,
    column: str | None = None,
    scenario_format: str | None = None,
    include_base: bool = False,
) -> dict[str, list[Shock]]: ...
def parse_scenario_config(
    config: list[str | dict[str, Any]],
) -> dict[str, list[Shock]]: ...
def parse_shock_config(config: dict[str, Any]) -> Shock | ParameterShock: ...

__all__: list[str] = [
    "AdditiveShock",
    "ClipShock",
    "FilteredShock",
    "MaxShock",
    "MinShock",
    "MultiplicativeShock",
    "OverrideShock",
    "ParameterShock",
    "PipelineShock",
    "RelativeFloorShock",
    "Shock",
    "TimeConditionalShock",
    "batch_scenarios",
    "describe_scenarios",
    "parse_scenario_config",
    "parse_shock_config",
    "sensitivity_analysis",
    "with_scenarios",
]
