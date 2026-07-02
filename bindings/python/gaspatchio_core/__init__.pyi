# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: F401 - symbols are publicly exposed
from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING, Any, TypeAlias

import polars as pl

# Expose the functions submodule
from . import functions as functions

# Import types for the public API - NEW v2 assumption API
from .assumptions import Table as Table
from .assumptions import TableBuilder as TableBuilder
from .assumptions import get_table_metadata as get_table_metadata
from .assumptions import list_tables as list_tables
from .assumptions import list_tables_with_metadata as list_tables_with_metadata

# Core proxy classes
from .column import ColumnProxy as ColumnProxy
from .column import ExpressionProxy as ExpressionProxy

# Frame and error classes
from .errors import PerformanceWarning as PerformanceWarning
from .frame import ActuarialFrame as ActuarialFrame
from .frame import run_model as run_model

# Functions
from .functions.conditional import when as when

# Scenarios
from .scenarios import AggregatedResult as AggregatedResult
from .scenarios import PeriodCount as PeriodCount
from .scenarios import PeriodCTE as PeriodCTE
from .scenarios import PeriodMax as PeriodMax
from .scenarios import PeriodMean as PeriodMean
from .scenarios import PeriodMedian as PeriodMedian
from .scenarios import PeriodMin as PeriodMin
from .scenarios import PeriodQuantile as PeriodQuantile
from .scenarios import PeriodStd as PeriodStd
from .scenarios import PeriodSum as PeriodSum
from .scenarios import PeriodVariance as PeriodVariance
from .scenarios import ScenarioRun as ScenarioRun
from .scenarios import SpillResult as SpillResult
from .scenarios import run_aggregated as run_aggregated
from .scenarios import run_to_parquet as run_to_parquet
from .scenarios import with_scenarios as with_scenarios

# Schedule and date conventions
from .schedule import TARGET as TARGET
from .schedule import Actual360 as Actual360
from .schedule import Actual365Fixed as Actual365Fixed
from .schedule import ActualActualISDA as ActualActualISDA
from .schedule import NullCalendar as NullCalendar
from .schedule import OneTwelfth as OneTwelfth
from .schedule import Thirty360 as Thirty360
from .schedule import UnitedKingdom as UnitedKingdom
from .schedule import UnitedStates as UnitedStates

# Utility functions
from .util import execution_mode as execution_mode
from .util import get_default_mode as get_default_mode
from .util import set_default_mode as set_default_mode

if TYPE_CHECKING:
    # Make submodules available for type checking if needed, but not strictly part of __all__
    from . import accessors as accessors
    from . import assumptions as assumptions
    from . import errors as errors
    from . import frame as frame
    from . import util as util

# Define __all__ to match __init__.py exactly
__all__: list[str] = [
    "TARGET",
    "Actual360",
    "Actual365Fixed",
    "ActualActualISDA",
    "ActuarialFrame",
    "AggregatedResult",
    "ColumnProxy",
    "ExpressionProxy",
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
    "ScenarioRun",
    "SpillResult",
    "Table",
    "TableBuilder",
    "Thirty360",
    "UnitedKingdom",
    "UnitedStates",
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
