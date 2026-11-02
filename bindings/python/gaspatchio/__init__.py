# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Gaspatchio - Actuarial computation framework.

**Logs are off unless enabled.** gaspatchio logs through loguru and, used
as a library, keeps its log records to itself: importing it mutes them.
``gspio`` turns them on for its own commands. To see them from a script or
a notebook, enable them by the package's name once it is imported -- an
enable that runs before the import is undone by it::

    import gaspatchio
    from loguru import logger

    logger.enable("gaspatchio")

**Warnings arrive as** ``GaspatchioWarning``. What a user must hear
unasked -- an assumption table re-registered with different data, a slow
pattern in their own code, a request the framework answered another way --
is raised through Python's own ``warnings``, not logged, so it is shown
whether or not the logs are on. Each names the line of the user's code
that led to it, and the usual filters apply::

    import warnings

    warnings.filterwarnings("ignore", category=gaspatchio.GaspatchioWarning)

``PerformanceWarning``, raised for a slow pattern, is a
``GaspatchioWarning`` too.
"""

# Import key components for easier access
from __future__ import annotations

from loguru import logger as _logger

# A library speaks only when asked. Loguru's default handler prints every
# level from DEBUG up to stderr, so the package mutes its own records, as
# loguru's documentation advises a library to, and leaves turning them on to
# the application: gspio does, and a script can. It comes first, so nothing a
# submodule logs while it loads reaches a user who has not asked for it; the
# imports below follow it on purpose, hence their E402 exemptions.
_logger.disable("gaspatchio")

from gaspatchio.telemetry import (  # noqa: E402
    configure_telemetry,
)

# Import submodules that need loading (e.g., for registration) or public exposure
# Important: Ensure accessor modules are imported to run registration decorators
# This needs to happen after Frame/ColumnProxy are defined if accessors depend on them.
from . import (  # noqa: E402
    accessors,  # noqa: F401 - Import for side effects (registration)
    functions,
)
from ._version import package_version as _package_version  # noqa: E402

# Import assumptions functionality - new API
from .assumptions import (  # noqa: E402
    Table,
    TableBuilder,
    get_table_metadata,
    list_tables,
    list_tables_with_metadata,
)
from .column import ColumnProxy, ExpressionProxy  # noqa: E402
from .curves import Curve  # noqa: E402
from .errors import GaspatchioWarning, PerformanceWarning  # noqa: E402
from .frame import ActuarialFrame, run_model  # noqa: E402
from .functions.conditional import when  # noqa: E402
from .mortality import MortalityTable  # noqa: E402
from .rollforward._builder import RollforwardBuilder  # noqa: E402
from .rollforward._compile import compile_rollforward  # noqa: E402
from .rollforward._compiled import CompiledRollforward  # noqa: E402
from .scenarios import (  # noqa: E402
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
from .schedule import (  # noqa: E402
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
from .util import (  # noqa: E402
    execution_mode,  # Context manager
    get_default_mode,  # Getter
    set_default_mode,  # Setter
)

configure_telemetry(enable=True)

# The installed distribution's version, as ``gspio --version`` reports it:
# module metadata rather than API, so ``__all__`` leaves it out.
__version__: str = _package_version()


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
    "GaspatchioWarning",
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
