# ruff: noqa: F401 - symbols are publicly exposed
from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING, TypeAlias

# Expose the functions submodule
from . import functions as functions

# Import types for the public API
from .column import ColumnProxy as ColumnProxy
from .column import ExpressionProxy as ExpressionProxy
from .errors import PerformanceWarning as PerformanceWarning
from .frame import ActuarialFrame as ActuarialFrame
from .frame import run_model as run_model
from .util import execution_mode as execution_mode
from .util import get_default_mode as get_default_mode
from .util import set_default_mode as set_default_mode

if TYPE_CHECKING:
    # Make submodules available for type checking if needed, but not strictly part of __all__
    from . import accessors as accessors
    from . import errors as errors
    from . import frame as frame
    from . import util as util

# Define __all__ to match __init__.py
__all__: list[str] = [
    "ActuarialFrame",
    "ColumnProxy",
    "ExpressionProxy",
    "run_model",
    "execution_mode",
    "get_default_mode",
    "set_default_mode",
    "PerformanceWarning",
    "functions",
]
