# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Public scenarios module - typed plans, loop primitive, aggregators, shocks.
# ABOUTME: Aggregators follow a Beam-style Protocol, partitioned with .over().

"""Scenario support module for multi-scenario actuarial model execution.

The public surface:

* ``ScenarioRun`` - immutable plan dataclass
* ``for_each_scenario`` - the loop primitive
* ``as_scenario_model`` - explicit adaptation of a frame-only model
* ``ScenarioResult`` - run output (scalar metrics + DataFrames for partitioned)
* Aggregators: ``Sum``, ``Count``, ``Min``, ``Max``, ``ArgMin``, ``ArgMax``,
  ``Mean``, ``Variance``, ``Std``, ``Quantile``, ``Median``, ``CTE``, ``QuantileRank``
* Modifiers (methods on every aggregator):
  ``.alias(name)``, ``.over(by)``, ``.of(expr)``
* ``Aggregator`` - Beam-style Protocol for custom aggregators
* ``BaseAggregator`` - public base class for custom aggregator authors
* ``register_aggregator`` / ``scenario_aggregator`` - plugin entry points
* ``parse_aggregations``, ``parse_scenario_config``, ``parse_shock_config``
  - YAML helpers
* ``with_scenarios`` - shock-application helper
* Shocks: all classes from ``gaspatchio.scenarios.shocks``
"""

from gaspatchio.scenarios._aggregated import AggregatedResult, run_aggregated
from gaspatchio.scenarios._aggregators import (
    CTE,
    ArgMax,
    ArgMin,
    BaseAggregator,
    Count,
    Max,
    Mean,
    Median,
    Min,
    Quantile,
    QuantileRank,
    Std,
    Sum,
    Variance,
    register_aggregator,
    scenario_aggregator,
)
from gaspatchio.scenarios._config import (
    parse_aggregations,
    parse_scenario_config,
    parse_shock_config,
)
from gaspatchio.scenarios._for_each import BatchSnapshot, for_each_scenario
from gaspatchio.scenarios._metric import Aggregator
from gaspatchio.scenarios._model import as_scenario_model
from gaspatchio.scenarios._period_aggregators import (
    PeriodCount,
    PeriodMax,
    PeriodMean,
    PeriodMin,
    PeriodStd,
    PeriodSum,
    PeriodVariance,
    VectorAggregator,
)
from gaspatchio.scenarios._period_sketch import (
    PeriodCTE,
    PeriodMedian,
    PeriodQuantile,
)
from gaspatchio.scenarios._result import (
    ProbeResult,
    ScenarioResult,
    SelectionDecision,
)
from gaspatchio.scenarios._run import ScenarioRun
from gaspatchio.scenarios._spill import SpillResult, run_to_parquet
from gaspatchio.scenarios._with_scenarios import with_scenarios
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

__all__ = [
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
    "as_scenario_model",
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
