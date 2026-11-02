# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Error types and formatters that turn failures into actionable messages."""

from gaspatchio._warning import GaspatchioWarning

from .boundary import AmbiguousAttribution
from .compilation_finder import CompilationErrorFinder
from .formatter import ValidationErrorFormatter
from .formatting_errors import (
    PerformanceWarning,
)
from .formatting_errors import (
    _extract_missing_column_robust as _extract_missing_column_robust,
)

# The frame and the scenario runner reach these handlers through this package,
# so it keeps them importable by name; they are not among its public names.
from .formatting_errors import (
    _handle_execution_error as _handle_execution_error,
)
from .formatting_errors import (
    _handle_frame_error as _handle_frame_error,
)
from .formatting_errors import (
    _handle_plan_lowering_panic as _handle_plan_lowering_panic,
)
from .models import (
    ColumnInfo,
    DataFrameContext,
    EnhancedError,
    ErrorMetadata,
    ErrorType,
    OperationContext,
    SourceLocation,
    Suggestion,
    SuggestionType,
)
from .validation import (
    ValidationError,
    capture_validation_context,
    raise_validation_error,
)

__all__ = [
    "AmbiguousAttribution",
    "ColumnInfo",
    "CompilationErrorFinder",
    "DataFrameContext",
    "EnhancedError",
    "ErrorMetadata",
    "ErrorType",
    "GaspatchioWarning",
    "OperationContext",
    "PerformanceWarning",
    "SourceLocation",
    "Suggestion",
    "SuggestionType",
    "ValidationError",
    "ValidationErrorFormatter",
    "capture_validation_context",
    "raise_validation_error",
]
