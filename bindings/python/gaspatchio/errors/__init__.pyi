# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from gaspatchio._warning import GaspatchioWarning as GaspatchioWarning

from .boundary import AmbiguousAttribution as AmbiguousAttribution
from .compilation_finder import CompilationErrorFinder as CompilationErrorFinder
from .formatter import ValidationErrorFormatter as ValidationErrorFormatter
from .formatting_errors import (
    PerformanceWarning as PerformanceWarning,
)
from .formatting_errors import (
    _extract_missing_column_robust as _extract_missing_column_robust,
)
from .formatting_errors import (
    _handle_execution_error as _handle_execution_error,
)
from .formatting_errors import (
    _handle_frame_error as _handle_frame_error,
)
from .formatting_errors import (
    _handle_plan_lowering_panic as _handle_plan_lowering_panic,
)
from .models import ColumnInfo as ColumnInfo
from .models import DataFrameContext as DataFrameContext
from .models import EnhancedError as EnhancedError
from .models import ErrorMetadata as ErrorMetadata
from .models import ErrorType as ErrorType
from .models import OperationContext as OperationContext
from .models import SourceLocation as SourceLocation
from .models import Suggestion as Suggestion
from .models import SuggestionType as SuggestionType
from .validation import (
    ValidationError as ValidationError,
)
from .validation import (
    capture_validation_context as capture_validation_context,
)
from .validation import (
    raise_validation_error as raise_validation_error,
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
