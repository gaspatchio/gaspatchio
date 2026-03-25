# ABOUTME: Scenario support module for multi-scenario actuarial model execution.
# ABOUTME: Provides scenario expansion, batching, and audit trail functions.

"""Scenario support module for multi-scenario actuarial model execution."""

from ._batching import batch_scenarios
from ._config import parse_scenario_config, parse_shock_config
from ._describe import describe_scenarios
from ._sensitivity import sensitivity_analysis
from ._with_scenarios import with_scenarios
from .shocks import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    ParameterShock,
    PipelineShock,
    RelativeFloorShock,
    Shock,
    TimeConditionalShock,
)

__all__ = [
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
