# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Type stubs for the public scenarios module surface.
# ABOUTME: GSP-101 (v0.2): Beam-style Aggregator Protocol + .over() partitioning.
# ruff: noqa: F401, ANN401, E501

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

import polars as pl

from gaspatchio_core.assumptions import Table
from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._metric import _Partitioned as _Partitioned
from gaspatchio_core.scenarios.shocks import AdditiveShock as AdditiveShock
from gaspatchio_core.scenarios.shocks import ClipShock as ClipShock
from gaspatchio_core.scenarios.shocks import FilteredShock as FilteredShock
from gaspatchio_core.scenarios.shocks import MaxShock as MaxShock
from gaspatchio_core.scenarios.shocks import MinShock as MinShock
from gaspatchio_core.scenarios.shocks import (
    MultiplicativeShock as MultiplicativeShock,
)
from gaspatchio_core.scenarios.shocks import OverrideShock as OverrideShock
from gaspatchio_core.scenarios.shocks import ParameterShock as ParameterShock
from gaspatchio_core.scenarios.shocks import PipelineShock as PipelineShock
from gaspatchio_core.scenarios.shocks import (
    RelativeFloorShock as RelativeFloorShock,
)
from gaspatchio_core.scenarios.shocks import Shock as Shock
from gaspatchio_core.scenarios.shocks import (
    TimeConditionalShock as TimeConditionalShock,
)

type ScenarioID = str | int

@runtime_checkable
class Aggregator(Protocol):
    def create_accumulator(self) -> Any: ...
    def add_input(self, state: Any, value: Any) -> Any: ...
    def merge_accumulators(self, a: Any, b: Any) -> Any: ...
    def extract_output(self, state: Any) -> Any: ...
    def canonical_form(self) -> dict[str, Any]: ...

class _BaseAggregator:
    column: str
    within: str
    alias_: str | None
    within_expr_override: pl.Expr | None
    def alias(self, name: str) -> _BaseAggregator: ...
    def over(self, by: str | tuple[str, ...]) -> _Partitioned: ...
    @classmethod
    def of(cls, within_expr: pl.Expr) -> _BaseAggregator: ...
    def create_accumulator(self) -> Any: ...
    def add_input(self, state: Any, value: Any) -> Any: ...
    def merge_accumulators(self, a: Any, b: Any) -> Any: ...
    def extract_output(self, state: Any) -> Any: ...
    def canonical_form(self) -> dict[str, Any]: ...

BaseAggregator = _BaseAggregator

class Sum(_BaseAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class Count(_BaseAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class Min(_BaseAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class Max(_BaseAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class ArgMax(_BaseAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class ArgMin(_BaseAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class Mean(_BaseAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class Variance(_BaseAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class Std(_BaseAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class Quantile(_BaseAggregator):
    levels: tuple[float, ...]
    relative_accuracy: float
    def __init__(
        self,
        column: str,
        levels: tuple[float, ...] = ...,
        relative_accuracy: float = ...,
        within: str = ...,
    ) -> None: ...

class Median(_BaseAggregator):
    relative_accuracy: float
    def __init__(
        self,
        column: str,
        relative_accuracy: float = ...,
        within: str = ...,
    ) -> None: ...

class CTE(_BaseAggregator):
    level: float
    direction: str
    relative_accuracy: float
    def __init__(
        self,
        column: str,
        level: float = ...,
        direction: Literal["upper", "lower"] = ...,
        relative_accuracy: float = ...,
        within: str = ...,
    ) -> None: ...

class QuantileRank(_BaseAggregator):
    at: float
    relative_accuracy: float
    def __init__(
        self,
        column: str,
        at: float = ...,
        relative_accuracy: float = ...,
        within: str = ...,
    ) -> None: ...

@dataclass(frozen=True, slots=True)
class ProbeResult:
    batch: int
    engine: Literal["streaming", "in-memory"]
    per_sc_s: float
    peak_mb: float | None
    fits: bool

@dataclass(frozen=True, slots=True)
class SelectionDecision:
    engine: Literal["streaming", "in-memory"]
    batch: int
    reason: Literal["fastest_fitting", "floor", "single_scenario", "forced_b1"]
    probed: list[ProbeResult]

class ScenarioResult:
    aggregations: dict[str, Any]
    plan_sha: str
    n_scenarios: int
    batch_size: int
    batch_size_resolution: Literal["manual", "auto_search"]
    wall_time_s: float
    peak_rss_mb: float | None
    n_batches: int
    sink_dir: Path | None
    selection: SelectionDecision | None
    audit_path: Path | None
    def __init__(
        self,
        aggregations: dict[str, Any],
        plan_sha: str,
        n_scenarios: int,
        batch_size: int,
        batch_size_resolution: Literal["manual", "auto_search"],
        wall_time_s: float,
        peak_rss_mb: float | None,
        n_batches: int,
        sink_dir: Path | None,
        selection: SelectionDecision | None = ...,
        audit_path: Path | None = ...,
    ) -> None: ...

class ScenarioRun:
    shocks: dict[str, list[Shock]]
    base_tables: dict[str, Table]
    aggregations: tuple[Aggregator | _Partitioned, ...]
    master_seed: int | None
    def __init__(
        self,
        shocks: dict[str, list[Shock]],
        base_tables: dict[str, Table],
        aggregations: tuple[Aggregator | _Partitioned, ...] = ...,
        master_seed: int | None = ...,
    ) -> None: ...
    def canonical_form(self) -> dict[str, Any]: ...
    def source_sha(self) -> str: ...
    def describe(self) -> str: ...
    def with_extra_shocks(self, more: dict[str, list[Shock]]) -> ScenarioRun: ...
    def with_extra_aggregations(
        self,
        more: tuple[Aggregator | _Partitioned, ...],
    ) -> ScenarioRun: ...
    def with_master_seed(self, seed: int) -> ScenarioRun: ...
    def run(
        self,
        af: ActuarialFrame,
        model_fn: Callable[..., ActuarialFrame],
        *,
        batch_size: int | Literal["auto"] = ...,
        target_memory_fraction: float = ...,
        return_full_grid: bool = ...,
        sink_dir: Path | None = ...,
        progress: bool = ...,
        on_batch: Callable[[BatchSnapshot], None] | None = ...,
        audit: bool | Path = ...,
    ) -> ScenarioResult: ...
    def to_dict(self) -> dict[str, Any]: ...
    def to_yaml(self, path: Path) -> None: ...
    @classmethod
    def from_dict(
        cls,
        config: dict[str, Any],
        *,
        base_tables: dict[str, Table],
    ) -> ScenarioRun: ...
    @classmethod
    def from_yaml(
        cls,
        path: Path,
        *,
        base_tables: dict[str, Table],
    ) -> ScenarioRun: ...

class BatchSnapshot:
    batch_idx: int
    scenarios_done: int
    total_scenarios: int
    outputs: dict[str, Any]
    peak_rss_mb: float | None
    elapsed_s: float
    @property
    def fraction_done(self) -> float: ...
    @property
    def eta_s(self) -> float | None: ...
    @property
    def throughput(self) -> float | None: ...
    def __init__(
        self,
        batch_idx: int,
        scenarios_done: int,
        total_scenarios: int,
        outputs: dict[str, Any],
        peak_rss_mb: float | None,
        elapsed_s: float,
    ) -> None: ...

class VectorAggregator(_BaseAggregator):
    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any: ...
    def within_expr(self) -> pl.Expr: ...

class PeriodSum(VectorAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class PeriodCount(VectorAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class PeriodMin(VectorAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class PeriodMax(VectorAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class PeriodMean(VectorAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class PeriodVariance(VectorAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class PeriodStd(VectorAggregator):
    def __init__(self, column: str, within: str = ...) -> None: ...

class PeriodQuantile(VectorAggregator):
    levels: tuple[float, ...]
    relative_accuracy: float
    def __init__(
        self,
        column: str,
        levels: tuple[float, ...] = ...,
        relative_accuracy: float = ...,
    ) -> None: ...

class PeriodMedian(VectorAggregator):
    relative_accuracy: float
    def __init__(
        self,
        column: str,
        relative_accuracy: float = ...,
    ) -> None: ...

class PeriodCTE(VectorAggregator):
    level: float
    direction: str
    relative_accuracy: float
    def __init__(
        self,
        column: str,
        level: float = ...,
        direction: Literal["upper", "lower"] = ...,
        relative_accuracy: float = ...,
    ) -> None: ...

class AggregatedResult:
    aggregations: dict[str, Any]
    n_policies: int
    n_periods: int
    batch_size: int
    wall_time_s: float
    peak_rss_mb: float | None
    def __init__(
        self,
        aggregations: dict[str, Any],
        n_policies: int,
        n_periods: int,
        batch_size: int,
        wall_time_s: float,
        peak_rss_mb: float | None,
    ) -> None: ...
    def __getattr__(self, name: str) -> Any: ...

def run_aggregated(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,
    aggregations: Sequence[Any],
    *,
    batch_size: int | Literal["auto"] = ...,
    align: Literal["calendar", "duration"] | None = ...,
) -> AggregatedResult: ...

class SpillResult:
    output_dir: Path
    n_policies: int
    n_batches: int
    wall_time_s: float
    peak_rss_mb: float | None
    def __init__(
        self,
        output_dir: Path,
        n_policies: int,
        n_batches: int,
        wall_time_s: float,
        peak_rss_mb: float | None,
    ) -> None: ...

def run_to_parquet(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,
    output_dir: Path,
    *,
    batch_size: int | Literal["auto"] = ...,
    mounts_text: str | None = ...,
) -> SpillResult: ...

def for_each_scenario(
    af: ActuarialFrame,
    scenarios: list[ScenarioID]
    | dict[ScenarioID, list[Shock]]
    | dict[ScenarioID, dict[str, Any]],
    model_fn: Callable[..., ActuarialFrame],
    *,
    aggregations: Sequence[Aggregator | _Partitioned],
    base_tables: dict[str, Table] | None = ...,
    batch_size: int | Literal["auto"] = ...,
    target_memory_fraction: float = ...,
    return_full_grid: bool = ...,
    sink_dir: Path | None = ...,
    master_seed: int | None = ...,
    progress: bool = ...,
    on_batch: Callable[[BatchSnapshot], None] | None = ...,
    plan_sha: str = ...,
) -> ScenarioResult: ...
def register_aggregator(name: str, cls: type) -> None: ...
def scenario_aggregator(name: str) -> Callable[[type], type]: ...
def with_scenarios(
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = ...,
    *,
    categorical: bool = ...,
) -> ActuarialFrame: ...
def parse_scenario_config(
    config: list[str | dict[str, Any]],
) -> dict[str, list[Shock | ParameterShock]]: ...
def parse_shock_config(config: dict[str, Any]) -> Shock | ParameterShock: ...
def parse_aggregations(
    spec: list[dict[str, Any]],
) -> tuple[Aggregator | _Partitioned, ...]: ...

__all__: list[str] = [
    "CTE",
    "AdditiveShock",
    "AggregatedResult",
    "Aggregator",
    "ArgMax",
    "ArgMin",
    "BaseAggregator",
    "BatchSnapshot",
    "ClipShock",
    "Count",
    "FilteredShock",
    "Max",
    "MaxShock",
    "Mean",
    "Median",
    "Min",
    "MinShock",
    "MultiplicativeShock",
    "OverrideShock",
    "ParameterShock",
    "PeriodCTE",
    "PeriodCount",
    "PeriodMax",
    "PeriodMean",
    "PeriodMedian",
    "PeriodMin",
    "PeriodQuantile",
    "PeriodStd",
    "PeriodSum",
    "PeriodVariance",
    "PipelineShock",
    "ProbeResult",
    "Quantile",
    "QuantileRank",
    "RelativeFloorShock",
    "ScenarioResult",
    "ScenarioRun",
    "SelectionDecision",
    "Shock",
    "SpillResult",
    "Std",
    "Sum",
    "TimeConditionalShock",
    "Variance",
    "VectorAggregator",
    "for_each_scenario",
    "parse_aggregations",
    "parse_scenario_config",
    "parse_shock_config",
    "register_aggregator",
    "run_aggregated",
    "run_to_parquet",
    "scenario_aggregator",
    "with_scenarios",
]
