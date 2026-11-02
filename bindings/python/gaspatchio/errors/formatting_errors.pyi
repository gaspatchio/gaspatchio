# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from typing import NoReturn

from gaspatchio._warning import GaspatchioWarning
from gaspatchio.frame.base import ActuarialFrame

# Docstrings live in formatting_errors.py, which the API reference reads.
class PerformanceWarning(GaspatchioWarning): ...

def _extract_missing_column_robust(error_str: str) -> str | None: ...
def _find_similar_columns(
    missing_col: str, available_cols: list[str], max_suggestions: int = ...
) -> list[str]: ...

# The alias of _handle_frame_error the frame's collect and profile call.
def _handle_execution_error(frame: ActuarialFrame, e: Exception) -> None: ...

# Handles errors during frame operations; _handle_execution_error is its alias.
def _handle_frame_error(frame: ActuarialFrame, e: Exception) -> None: ...

# Converts an attributed schema-derivation panic into a SchemaError.
def _handle_plan_lowering_panic(
    frame: ActuarialFrame, panic: BaseException
) -> NoReturn: ...

# Routes one frame error to the tier and the panel it has earned.
def _diagnose_frame_error(frame: ActuarialFrame, e: Exception) -> None: ...

# Puts a refusal the lazy plan smuggled out at the top of the message. Reads
# the list of values Polars reports a strict cast could not convert, and
# nothing wider; not called under AF_ERROR_MODE=off.
def _lift_plan_refusal(error: BaseException) -> None: ...
def wide_read_refusal(column: str | None, read: str) -> str: ...
def integer_total_refusal(column: str, total: int, where: str = ...) -> str: ...

# What the API reference documents from this module.
__all__ = ["PerformanceWarning"]
