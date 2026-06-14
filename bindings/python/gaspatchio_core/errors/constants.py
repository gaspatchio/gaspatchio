# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Constants for error handling system."""

# Patterns to identify internal framework modules (not user code)
INTERNAL_MODULE_PATTERNS = [
    "/gaspatchio_core/",
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
    "projection_end_types": ["maximum_age", "term_years", "term_months", "fixed_date"],
    
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