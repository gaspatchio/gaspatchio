# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Gaspatchio Core - Actuarial computation framework."""

# Import key components for easier access
from __future__ import annotations

from gaspatchio_core.telemetry import (
    configure_telemetry,
)

# Import submodules that need loading (e.g., for registration) or public exposure
# Important: Ensure accessor modules are imported to run registration decorators
# This needs to happen after Frame/ColumnProxy are defined if accessors depend on them.
from . import (
    accessors,  # noqa: F401 - Import for side effects (registration)
    functions,
)

# Import assumptions functionality - new API
from .assumptions import (
    Table,
    TableBuilder,
    get_table_metadata,
    list_tables,
    list_tables_with_metadata,
)
from .column import ColumnProxy, ExpressionProxy
from .curves import Curve
from .errors import PerformanceWarning
from .frame import ActuarialFrame, run_model
from .functions.conditional import when
from .mortality import MortalityTable
from .rollforward._builder import RollforwardBuilder
from .rollforward._collector import RollforwardCollector
from .rollforward._compile import compile_rollforward
from .rollforward._compiled import CompiledRollforward
from .scenarios import (
    AggregatedResult,
    PeriodCount,
    PeriodCTE,
    PeriodMax,
    PeriodMean,
    PeriodMedian,
    PeriodMin,
    PeriodQuantile,
    PeriodStd,
    PeriodSum,
    PeriodVariance,
    ScenarioRun,
    SpillResult,
    run_aggregated,
    run_to_parquet,
    with_scenarios,
)
from .schedule import (
    TARGET,
    Actual360,
    Actual365Fixed,
    ActualActualISDA,
    BusinessDayConvention,
    Calendar,
    DayCount,
    NullCalendar,
    OneTwelfth,
    Schedule,
    Thirty360,
    UnitedKingdom,
    UnitedStates,
)
from .util import (
    execution_mode,  # Context manager
    get_default_mode,  # Getter
    set_default_mode,  # Setter
)

configure_telemetry(enable=True)


# Define the public API surface
__all__ = [
    "TARGET",
    "Actual360",
    "Actual365Fixed",
    "ActualActualISDA",
    "ActuarialFrame",
    "AggregatedResult",
    "BusinessDayConvention",
    "Calendar",
    "ColumnProxy",
    "CompiledRollforward",
    "Curve",
    "DayCount",
    "ExpressionProxy",
    "MortalityTable",
    "NullCalendar",
    "OneTwelfth",
    "PerformanceWarning",
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
    "RollforwardBuilder",
    "RollforwardCollector",
    "ScenarioRun",
    "Schedule",
    "SpillResult",
    "Table",
    "TableBuilder",
    "Thirty360",
    "UnitedKingdom",
    "UnitedStates",
    "compile_rollforward",
    "execution_mode",
    "functions",
    "get_default_mode",
    "get_table_metadata",
    "list_tables",
    "list_tables_with_metadata",
    "run_aggregated",
    "run_model",
    "run_to_parquet",
    "set_default_mode",
    "when",
    "with_scenarios",
]
