# ABOUTME: Type stubs for scenario support module.
# ABOUTME: Provides type hints for scenario expansion and audit trail functions.

"""Type stubs for scenario support module."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal, TypeVar, overload

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios.shocks import Shock

T = TypeVar("T", str, int)

def with_scenarios(
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = "scenario_id",
    *,
    categorical: bool = False,
) -> ActuarialFrame: ...
def batch_scenarios(
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

__all__: list[str] = [
    "batch_scenarios",
    "describe_scenarios",
    "sensitivity_analysis",
    "with_scenarios",
]
