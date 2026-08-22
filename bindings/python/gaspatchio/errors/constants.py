# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Constants for error handling system."""

from pathlib import Path

# The framework's own installed location. Anchored to the real package root —
# a bare "/gaspatchio/" would also match user model files that merely live
# under a directory called gaspatchio (the documented multi-repo workspace
# layout) and silently drop the user's source line from error messages. Both
# raw and resolved forms are kept: frame filenames come from code objects,
# which do not resolve symlinks.
_PACKAGE_ROOTS = {Path(__file__).parents[1], Path(__file__).resolve().parents[1]}

# Patterns to identify internal framework modules (not user code)
INTERNAL_MODULE_PATTERNS = [
    *(f"{root}/" for root in _PACKAGE_ROOTS),
    "/site-packages/",
    "/_internal",
    "/dist-packages/",
    "/.venv/",
    "/venv/",
    "/env/",
    "/.tox/",
    "/pytest",
    "/unittest",
]

# Specific framework files to skip when looking for user code
FRAMEWORK_FILE_PATTERNS = [
    "/validation.py",
    "/formatting_errors.py",
    "/formatter.py",
    "/runner.py",
    "/tracing.py",
    "/execution.py",
    "/dispatch.py",
    "/metadata.py",
    "/boundary.py",
]

# Common validation values that might be misspelled
# These are kept as reference sets for fuzzy matching, not hard mappings
COMMON_VALIDATION_VALUES = {
    # Date/time frequencies
    "frequencies": ["monthly", "quarterly", "semi-annual", "annual", "daily", "weekly"],

    # Projection end types
    # Values accepted by `projection.set(until=...)`. Kept in sync with the
    # Literal in accessors/projection_frame.py by
    # tests/errors/test_validation_constants_in_sync.py — this list had already
    # drifted once, so the invariant is asserted rather than requested.
    "projection_end_types": [
        "maximum_age",
        "term_years",
        "term_months",
        "fixed_date",
        "next_anniversary",
    ],

    # Common durations
    "duration_units": ["days", "months", "years", "hours", "minutes", "seconds"],

    # Actuarial terms
    "actuarial_terms": ["mortality", "morbidity", "lapse", "premium", "benefit",
                       "interest", "discount", "reserve", "annuity", "surrender"],
}

# Common Python attributes by module/type
# Used for fuzzy matching in AttributeError handling
COMMON_ATTRIBUTES = {
    "datetime": {
        "module": ["date", "datetime", "time", "timedelta", "timezone", "MAXYEAR", "MINYEAR"],
        "date_class": ["today", "fromtimestamp", "fromisoformat", "fromordinal",
                      "min", "max", "resolution"],
        "datetime_class": ["now", "today", "utcnow", "fromtimestamp", "utcfromtimestamp",
                          "strptime", "combine", "fromisoformat"],
        "instance_methods": ["strftime", "replace", "timetuple", "toordinal", "weekday",
                           "isoweekday", "isocalendar", "isoformat", "ctime"]
    },
    "str": ["split", "strip", "replace", "format", "join", "upper", "lower",
            "startswith", "endswith", "find", "index", "count", "encode"],
    "list": ["append", "extend", "insert", "remove", "pop", "clear", "index",
             "count", "sort", "reverse", "copy"],
    "dict": ["get", "keys", "values", "items", "update", "pop", "clear",
             "setdefault", "copy", "fromkeys"],
    "pandas_dataframe": ["head", "tail", "info", "describe", "columns", "index",
                        "shape", "dtypes", "values", "empty", "size"],
    "polars_dataframe": ["select", "filter", "with_columns", "group_by", "sort",
                        "join", "drop", "rename", "collect", "lazy"],
}

# Maximum number of lines to capture for multi-line statements
MAX_MULTILINE_CAPTURE = 20

# Maximum number of suggestions to show
MAX_SUGGESTIONS = 5

# Fuzzy matching threshold (0-100)
FUZZY_MATCH_THRESHOLD = 70
