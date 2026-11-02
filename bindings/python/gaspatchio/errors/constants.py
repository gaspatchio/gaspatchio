# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Constants for error handling system."""

# Where polars stops diagnosing and starts dumping the query plan it failed
# resolving. Three readers, which is why the text lives here rather than in
# any one of them: both error panels split the message on it and keep only the
# diagnosis (``FriendlyErrorFormatter._clean_error_message`` and
# ``EnhancedError._format_original_error``), and
# ``_extract_missing_column_robust`` scopes its bare-token heuristics to the
# same leading text. What they share is one fact about polars' output -- where
# it stops being addressed to the reader -- and they should not each hold it in
# their own spelling.
PLAN_DUMP_BOUNDARY = "Resolved plan until failure"

# Stands in a panel for the dropped dump, so an omission reads as an omission
# rather than as everything polars had to say. One spelling for both panels: a
# reader who learns what it means in one has learnt it for the other.
PLAN_DUMP_OMITTED = "[polars query plan omitted]"

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
    ],
    # Common durations
    "duration_units": ["days", "months", "years", "hours", "minutes", "seconds"],
    # Actuarial terms
    "actuarial_terms": [
        "mortality",
        "morbidity",
        "lapse",
        "premium",
        "benefit",
        "interest",
        "discount",
        "reserve",
        "annuity",
        "surrender",
    ],
}

# Common Python attributes by module/type
# Used for fuzzy matching in AttributeError handling
COMMON_ATTRIBUTES = {
    "datetime": {
        "module": [
            "date",
            "datetime",
            "time",
            "timedelta",
            "timezone",
            "MAXYEAR",
            "MINYEAR",
        ],
        "date_class": [
            "today",
            "fromtimestamp",
            "fromisoformat",
            "fromordinal",
            "min",
            "max",
            "resolution",
        ],
        "datetime_class": [
            "now",
            "today",
            "utcnow",
            "fromtimestamp",
            "utcfromtimestamp",
            "strptime",
            "combine",
            "fromisoformat",
        ],
        "instance_methods": [
            "strftime",
            "replace",
            "timetuple",
            "toordinal",
            "weekday",
            "isoweekday",
            "isocalendar",
            "isoformat",
            "ctime",
        ],
    },
    "str": [
        "split",
        "strip",
        "replace",
        "format",
        "join",
        "upper",
        "lower",
        "startswith",
        "endswith",
        "find",
        "index",
        "count",
        "encode",
    ],
    "list": [
        "append",
        "extend",
        "insert",
        "remove",
        "pop",
        "clear",
        "index",
        "count",
        "sort",
        "reverse",
        "copy",
    ],
    "dict": [
        "get",
        "keys",
        "values",
        "items",
        "update",
        "pop",
        "clear",
        "setdefault",
        "copy",
        "fromkeys",
    ],
    "pandas_dataframe": [
        "head",
        "tail",
        "info",
        "describe",
        "columns",
        "index",
        "shape",
        "dtypes",
        "values",
        "empty",
        "size",
    ],
    "polars_dataframe": [
        "select",
        "filter",
        "with_columns",
        "group_by",
        "sort",
        "join",
        "drop",
        "rename",
        "collect",
        "lazy",
    ],
}

# Maximum number of lines to capture for multi-line statements
MAX_MULTILINE_CAPTURE = 20

# Fuzzy matching threshold (0-100)
FUZZY_MATCH_THRESHOLD = 70

# How many did-you-mean suggestions the validation and attribute panels offer.
MAX_SUGGESTIONS = 3

# The validation panel lists every valid option outright when there are no
# more than this many and no fuzzy match was found.
MAX_OPTIONS_LISTED = 6

# The validation panel's last fuzzy pass looks for a typo: an option whose
# length is within TYPO_LENGTH_SLACK characters of the value given, and whose
# token-set score beats TYPO_MATCH_THRESHOLD -- stricter than
# FUZZY_MATCH_THRESHOLD, since this pass runs only after the others found
# nothing.
TYPO_LENGTH_SLACK = 2
TYPO_MATCH_THRESHOLD = 85
