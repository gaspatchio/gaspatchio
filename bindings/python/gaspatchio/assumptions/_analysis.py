# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Enhanced analysis of assumption table structure, and configuration generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

from loguru import logger

from gaspatchio._shown import python_literal

from ._utils import _detect_overflow_column, _materialise

if TYPE_CHECKING:
    from pathlib import Path

    import polars as pl

# How many of a dimension's distinct values the analysis carries as examples.
# They are the LOWEST five in the column's own dtype order, not the first five
# in the file: see `analyze_table` on why the order is a sort and not a scan.
_SAMPLE_VALUES: Final = 5

# How much of a source the dimension scan reads before it starts sampling,
# counted in CELLS -- rows x columns -- because that is what the cost is
# linear in. Measured on this repository's pinned polars (1.42.1) with
# high-cardinality Int64 columns: 14M cells 743 ms, 50M cells 2,719 ms,
# 2M cells 105 ms, 5M cells 269 ms -- 18.4 to 20.6M cells per second across
# every shape, so a budget in rows alone would let a 50-column file cost 3.6x
# what a 14-column file of the same height costs. At 5,000,000 the scan reads
# every data file this repository has (the largest is 1.4M cells) and cannot
# cost more than about a quarter of a second, which is inside the command's
# own interpreter startup rather than beside it.
_SCAN_CELL_BUDGET: Final = 5_000_000

# The name the wide reading gives the value column AFTER melting. A frame that
# already has a column of this name is already long -- see `analyze_table`.
_MELTED_VALUE_NAME: Final = "value"

# What the suggested `Table(...)` names as its value when the analysis found no
# value column at all -- an empty frame, or one whose every column reads as a
# key. A real-looking name here (`rate` was the old fallback) is a column the
# source may well not carry, and the snippet is code the reader copies out and
# runs: it would fail on a name the framework invented rather than on the one
# fact worth stating, which is that nothing was found to name. Angle brackets
# are not a legal column name, so a snippet carrying this cannot be run by
# accident.
_NO_VALUE_COLUMN: Final = "<no value column found -- name yours here>"

# The spread (standard deviation) of a key column's consecutive differences
# under which its values are read as an evenly stepped range -- ages 0-120 by
# one -- and reported as "low-high" rather than as "continuous".
_EVEN_STEP_SPREAD: Final = 0.1

# The fewest distinct values a grid needs before its gaps can be compared:
# three values give two differences, the least that can disagree.
_FEWEST_VALUES_FOR_A_GAP: Final = 3


@dataclass
class DimensionInfo:
    """Information about a detected dimension in the data."""

    name: str
    dtype: str
    unique_count: int
    sample_values: list[Any]  # The five lowest distinct values, ascending
    suggested_type: Literal["key", "melt", "categorical", "value"]
    numeric_pattern: str | None = None  # e.g., "1-25", "continuous"


@dataclass
class InterpolationHint:
    """Suggestion for interpolation opportunities."""

    dimension: str
    detected_values: list[int | float]
    missing_values: list[int | float]
    suggested_method: Literal["linear", "log-linear", "cubic"]


@dataclass
class TableSchema:
    """Complete analysis result for a table.

    ``row_count`` is the source's own height. ``sampled_rows`` is ``None``
    when every dimension fact here was measured on the whole source, and the
    size of the sample when it was not — whether the caller asked for a
    sample or the source was over `_SCAN_CELL_BUDGET` cells — so a sampled
    count can never be read as a statement about the file.
    """

    data_dimensions: list[DimensionInfo]
    value_columns: list[str]
    format: Literal["curve", "wide"]
    overflow_candidate: str | None = None
    interpolation_opportunities: list[InterpolationHint] = field(default_factory=list)
    row_count: int = 0
    sampled_rows: int | None = None

    def suggest_table_config(self) -> str:
        """Generate example code for loading this table.

        The code is Python a reader copies out and runs, so every name in it
        is written as a string literal that reads back as that name (``repr``)
        -- a column name holding a quote once closed its literal and ran
        whatever followed. ``source=`` is a placeholder path to replace.

        A wide table with an ultimate column (``Ult.``) keyed by an issue age
        is a select and ultimate table, and its ultimate rates are read along
        the attained age, not along the row: see
        :func:`_select_ultimate_config`.
        """
        if self.format == "curve":
            return self._curve_config()
        select_ultimate = _select_ultimate_config(self)
        if select_ultimate is not None:
            return select_ultimate
        return self._wide_config()

    def _value_literal(self) -> str:
        """Return the value column the snippet names, as a literal."""
        value_col = self.value_columns[0] if self.value_columns else _NO_VALUE_COLUMN
        return python_literal(value_col)

    def _curve_config(self) -> str:
        """Return the configuration for a curve: one value column, keys beside it."""
        dimensions_str = ",\n".join(
            f"        {dim.name!r}: gs.DataDimension({dim.name!r})"
            for dim in self.data_dimensions
            if dim.name not in self.value_columns
        )
        return f"""# Suggested configuration for curve table
import gaspatchio.assumptions as gs

table = gs.Table(
    name="your_table_name",
    source="path/to/your/data.csv",
    dimensions={{
{dimensions_str}
    }},
    value={self._value_literal()},
)"""

    def _wide_config(self) -> str:
        """Return the configuration for a wide table melted into one value column.

        An ultimate column this reading does not re-key (no age key, or an
        attained age) is extended along the row with ``ExtendOverflow``,
        which is right there: the row's ultimate rate is the rate at every
        later duration. The strategy belongs to the ``MeltDimension`` whose
        values it extends.
        """
        lines = [
            f"        {dim.name!r}: gs.DataDimension({dim.name!r})"
            for dim in self.data_dimensions
            if dim.suggested_type == "key"
        ]
        melt_columns = [
            dim.name for dim in self.data_dimensions if dim.suggested_type == "melt"
        ]
        if melt_columns:
            overflow = (
                f", overflow=gs.ExtendOverflow({self.overflow_candidate!r}, "
                "to_value=200)"
                if self.overflow_candidate
                else ""
            )
            lines.append(
                f"        'duration': gs.MeltDimension({melt_columns!r}{overflow})"
            )
        dimensions_str = ",\n".join(lines)
        return f"""# Suggested configuration for wide table
import gaspatchio.assumptions as gs

table = gs.Table(
    name="your_table_name",
    source="path/to/your/data.csv",
    dimensions={{
{dimensions_str}
    }},
    value={self._value_literal()},
)"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "data_dimensions": [
                {
                    "name": dim.name,
                    "dtype": dim.dtype,
                    "unique_count": dim.unique_count,
                    "sample_values": dim.sample_values,
                    "suggested_type": dim.suggested_type,
                    "numeric_pattern": dim.numeric_pattern,
                }
                for dim in self.data_dimensions
            ],
            "value_columns": self.value_columns,
            "format": self.format,
            "overflow_candidate": self.overflow_candidate,
            "interpolation_opportunities": [
                {
                    "dimension": hint.dimension,
                    "detected_values": hint.detected_values,
                    "missing_values": hint.missing_values,
                    "suggested_method": hint.suggested_method,
                }
                for hint in self.interpolation_opportunities
            ],
            "row_count": self.row_count,
            "sampled_rows": self.sampled_rows,
        }


# The integer dtypes an age key can be added to in the select and ultimate
# snippet; an age held as text or a float is not re-keyed.
_INTEGER_DTYPES: Final = frozenset(
    {"Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64"}
)


@dataclass(frozen=True)
class _SelectUltimate:
    """What a select and ultimate snippet is written from: the file's own names."""

    age: str
    others: list[str]
    select_columns: list[str]
    ultimate: str
    years: int
    age_is_named_issue: bool


def _select_ultimate(schema: TableSchema) -> _SelectUltimate | None:
    """Return the select and ultimate reading of a wide table, where it is one.

    It is one where the table has an ultimate column, its other wide columns
    are the policy years 1 to N, and a key is an age that is not said to be
    an attained age. A table keyed by attained age reads its ultimate rate
    along its own row, and a table with no age key has no age to read it
    along, so ``ExtendOverflow`` is right for both and this returns None.
    """
    melt = [dim.name for dim in schema.data_dimensions if dim.suggested_type == "melt"]
    ultimate = schema.overflow_candidate
    if ultimate is None or ultimate not in melt:
        return None
    keys = [dim for dim in schema.data_dimensions if dim.suggested_type == "key"]
    ages = [dim for dim in keys if "age" in dim.name.lower()]
    if not ages or any("attained" in dim.name.lower() for dim in ages):
        return None
    age = next((dim for dim in ages if "issue" in dim.name.lower()), ages[0])
    select_columns = [name for name in melt if name != ultimate]
    years = [int(name) if name.strip().isdigit() else None for name in select_columns]
    if age.dtype not in _INTEGER_DTYPES or years != list(
        range(1, len(select_columns) + 1)
    ):
        return None
    return _SelectUltimate(
        age=age.name,
        others=[dim.name for dim in keys if dim is not age],
        select_columns=select_columns,
        ultimate=ultimate,
        years=len(select_columns),
        age_is_named_issue="issue" in age.name.lower(),
    )


def _select_ultimate_config(schema: TableSchema) -> str | None:
    """Return the configuration that reads a select and ultimate table as one.

    In the published layout (the SOA's VBT tables among them) each row is an
    issue age x: the columns ``1`` to ``N`` are the select rates for policy
    years 1 to N, and ``Ult.`` is the ULTIMATE rate at attained age x + N. A
    policy issued at x is at attained age x + d - 1 in year d, so for d > N
    it reads the ``Ult.`` value of the row d - 1 - N issue ages further on,
    not its own row's. ``ExtendOverflow('Ult.')`` copies the row's own value
    to every later year, which holds the rate at age x + N for life: at year
    30 of a 3-year select table it is a tenth of the right rate.

    The snippet builds one long table keyed by issue age and policy year,
    whose later years carry the ultimate rate re-keyed to the attained age.
    A year past the last ``Ult.`` row is then a lookup miss, refused, rather
    than a rate held flat. Returns None where :func:`_select_ultimate` finds
    no such reading.
    """
    reading = _select_ultimate(schema)
    if reading is None:
        return None
    n, ult = reading.years, repr(reading.ultimate)
    age = f"pl.col({reading.age!r})"
    keys = [reading.age, *reading.others]
    key_cols = ", ".join(f"pl.col({name!r})" for name in keys)
    carried = "".join(f"pl.col({name!r}), " for name in reading.others)
    join = f"on={reading.others!r}" if reading.others else 'how="cross"'
    dimensions = "".join(f"{name!r}: {name!r}, " for name in keys)
    first, last = reading.select_columns[0], reading.select_columns[-1]
    preamble = [
        "# Suggested configuration for a select and ultimate table",
        "#",
        f"# Each row is an issue age. Columns {first!r} to {last!r} are the select",
        f"# rates for policy years 1 to {n}, and {ult} is the ultimate rate at",
        f"# attained age issue age + {n}. From year {n + 1} a policy reads the",
        "# ultimate rate at its own attained age, issue age + year - 1: the",
        f"# {ult} value of a later row, never its own row's carried forward.",
    ]
    if not reading.age_is_named_issue:
        preamble += [
            f"# {reading.age!r} is read as the issue age. If its rows are",
            "# attained ages, a row's ultimate rate is the rate for every later",
            "# year instead: melt the columns with",
            f"# overflow=gs.ExtendOverflow({ult}, to_value=200).",
        ]
    body = f"""import polars as pl
import gaspatchio.assumptions as gs

SELECT_YEARS = {n}
wide = pl.read_csv("path/to/your/data.csv")

# Years 1 to {n}: one row per issue age and policy year.
select = wide.unpivot(
    index={keys!r},
    on={reading.select_columns!r},
    variable_name="duration",
    value_name="value",
).with_columns(pl.col("duration").cast(pl.Int64))

# Years {n + 1} on: the {ult} rate at attained age issue age + year - 1.
ultimate = (
    wide.select({key_cols})
    .join(
        wide.select(
            {carried}({age} + SELECT_YEARS).alias("attained_age"),
            pl.col({ult}).alias("value"),
        ),
        {join},
    )
    .filter(pl.col("attained_age") >= {age} + SELECT_YEARS)
    .select(
        {key_cols},
        (pl.col("attained_age") - {age} + 1).alias("duration"),
        pl.col("value"),
    )
)

table = gs.Table(
    name="your_table_name",
    source=pl.concat([select, ultimate]),
    dimensions={{{dimensions}"duration": "duration"}},
    value="value",
)"""
    return "\n".join([*preamble, body])


@dataclass(frozen=True)
class _TableClassification:
    """Value-column and shape decision made from measured column facts."""

    format: Literal["curve", "wide"]
    is_wide: bool
    potential_value_columns: list[str]
    value_columns: list[str]


def _column_info(series: pl.Series, measured_rows: int) -> DimensionInfo:
    """Measure one column without losing its source order or dtype ordering."""
    is_numeric = series.dtype.is_numeric()
    # Sorted BEFORE the slice, and sorted in polars rather than in Python.
    # `unique()` returns a set in hash order, which differs between runs and
    # even between two calls in one process, so slicing it unsorted chose a
    # different five values each time and printed them in a different order
    # again. Sorting in polars keeps nulls, dates and mixed-width numerics
    # sortable, which `sorted()` does not.
    unique_values = series.unique().sort().to_list()[:_SAMPLE_VALUES]
    unique_count = series.n_unique()
    suggested_type: Literal["key", "melt", "categorical", "value"] = "key"
    numeric_pattern = None

    # Determine if this looks like a key column or value column. Compared
    # against what was MEASURED: on a 1,000-row sample of a 10,000-row file
    # almost any high-cardinality column passes a test written against the
    # file's own height.
    if is_numeric and (
        unique_count == measured_rows or _is_likely_id_column(series.name)
    ):
        numeric_pattern = _analyze_numeric_pattern(series)
    elif is_numeric:
        # Could be a melt column in a wide table or value in a curve table.
        suggested_type = "melt"

    return DimensionInfo(
        name=series.name,
        dtype=str(series.dtype),
        unique_count=unique_count,
        sample_values=unique_values,
        suggested_type=suggested_type,
        numeric_pattern=numeric_pattern,
    )


def _column_facts(
    df: pl.DataFrame,
    measured_rows: int,
) -> tuple[list[DimensionInfo], list[str]]:
    """Measure columns in their source order and retain the numeric names."""
    dimensions = [_column_info(df[name], measured_rows) for name in df.columns]
    numeric_columns = [name for name in df.columns if df[name].dtype.is_numeric()]
    return dimensions, numeric_columns


def _value_columns(
    *,
    all_columns: list[str],
    numeric_columns: list[str],
    potential_value_columns: list[str],
    named_value: str | None,
    is_wide: bool,
) -> list[str]:
    """Choose the output value-column names for one classified shape."""
    if named_value is not None:
        return [named_value]
    if is_wide:
        # Wide tables produce this value name after melting.
        return [_MELTED_VALUE_NAME]
    if potential_value_columns:
        return [potential_value_columns[0]]
    if numeric_columns:
        return [numeric_columns[-1]]
    return [all_columns[-1]] if all_columns else []


def _mark_dimension_types(
    dimensions: list[DimensionInfo],
    *,
    value_columns: list[str],
    potential_value_columns: list[str],
    is_wide: bool,
) -> None:
    """Apply the shape decision to the preliminary per-column types."""
    for dimension in dimensions:
        if not is_wide and dimension.name in value_columns:
            dimension.suggested_type = "value"
        elif is_wide and dimension.name in potential_value_columns:
            dimension.suggested_type = "melt"
        elif not is_wide and dimension.suggested_type == "melt":
            # `melt` is a wide-table word. A curve melts nothing, so every
            # non-value column is a key in the config built from this object.
            dimension.suggested_type = "key"


def _classify_table(
    dimensions: list[DimensionInfo],
    all_columns: list[str],
    numeric_columns: list[str],
    value_column: str | None,
) -> _TableClassification:
    """Resolve the declared/inferred value column and curve-versus-wide shape."""
    potential_value_columns = [
        name for name in numeric_columns if not _is_likely_id_column(name)
    ]

    # A declared value column ends the question before it is asked. The
    # caller has said which column holds the rate, so the table is a curve
    # keyed on everything else and no rule here may reach a different answer.
    declared = value_column if value_column in all_columns else None

    # The wide reading melts several columns into ONE called `value`, so it
    # cannot be the reading for a frame that already has a column of that
    # name. A frame carrying the post-melt name is already melted, and that
    # column is the rate.
    if declared is not None:
        named_value = declared
    elif _MELTED_VALUE_NAME in all_columns:
        named_value = _MELTED_VALUE_NAME
    else:
        named_value = None

    is_wide = named_value is None and len(potential_value_columns) > 1
    table_format: Literal["curve", "wide"] = "wide" if is_wide else "curve"
    value_columns = _value_columns(
        all_columns=all_columns,
        numeric_columns=numeric_columns,
        potential_value_columns=potential_value_columns,
        named_value=named_value,
        is_wide=is_wide,
    )
    _mark_dimension_types(
        dimensions,
        value_columns=value_columns,
        potential_value_columns=potential_value_columns,
        is_wide=is_wide,
    )
    return _TableClassification(
        format=table_format,
        is_wide=is_wide,
        potential_value_columns=potential_value_columns,
        value_columns=value_columns,
    )


def _interpolation_hints(
    df: pl.DataFrame,
    dimensions: list[DimensionInfo],
    *,
    enabled: bool,
) -> list[InterpolationHint]:
    """Build ordered interpolation hints for eligible key dimensions."""
    opportunities: list[InterpolationHint] = []
    if not enabled:
        return opportunities

    for dimension in dimensions:
        if dimension.suggested_type != "key" or dimension.dtype not in {
            "Int64",
            "Float64",
        }:
            continue
        opportunities.extend(
            [
                InterpolationHint(
                    dimension=dimension.name,
                    detected_values=hint["detected"],
                    missing_values=hint["missing"],
                    suggested_method=hint["method"],
                )
                for hint in _detect_interpolation_opportunities(df[dimension.name])
            ],
        )
    return opportunities


def analyze_table(
    source: str | Path | pl.DataFrame,
    sample_rows: int | None = None,
    detect_overflow: bool = True,
    detect_interpolation: bool = True,
    value_column: str | None = None,
) -> TableSchema:
    """
    Analyze table structure and suggest loading configuration.

    Args:
        source: Data source to analyze
        sample_rows: Rows to measure the dimension facts on. ``None``, the
            default, is ADAPTIVE: a source inside `_SCAN_CELL_BUDGET` cells
            (rows x columns) is read whole, so every count is the source's
            own, and a larger one is sampled down to what the budget buys.
            Pass a number to fix the sample size yourself -- above or below
            the budget, an explicit number is the one used. Either way
            ``sampled_rows`` is ``None`` only when the whole source was read.
        detect_overflow: Whether to detect overflow columns
        detect_interpolation: Whether to detect interpolation opportunities
        value_column: The column the caller has DECLARED is the rate. Given,
            it is the answer -- no rule runs, the table is read as a curve
            keyed on every other column, and nothing here overrules it. A
            name that is not on the frame is ignored; validating the caller's
            own declaration belongs to the caller.

    Returns:
        TableSchema with analysis results

    Note:
        **Every count here says what it was measured on.** ``row_count``
        names the source; ``sampled_rows`` is ``None`` when the dimension
        facts are the whole source's and the size of the sample when they are
        not. Measuring a 1,000-row sample and reporting the answers beside
        the file's own ``row_count`` -- with nothing saying so -- told a
        reader a 10,000-policy extract held 1,000 distinct policies. Sampling
        is only dishonest when it is silent, which is why the size of what
        was read travels with the answer.


        **Every list in the result has a stated order, and it is the same
        order every run.** `gspio describe --json` is built on this and
        `AGENTS.md` names that payload as how an agent reads a file's shape,
        so a result that could not be diffed against last quarter's would not
        be auditable.

        * `data_dimensions` is in the file's own column order. A column's
          position is information -- it is what the user sees on opening the
          file, and the value-column rule reads headers left to right -- so it
          is kept rather than sorted.
        * `sample_values` is **sorted ascending**, and is therefore the lowest
          five distinct values rather than the first five encountered. A
          first-seen order does exist and is available —
          ``unique(maintain_order=True)`` — and it was passed over on
          purpose: first-seen values move when the same data is exported in a
          different row order, so a quarter-over-quarter diff would light up
          on a re-sorted rewrite of an unchanged table. The lowest five move
          only when the data does, and they say where the dimension's grid
          begins, which is what a reader scans this field for. That claim is
          about whatever ``sampled_rows`` says was read.
        * `interpolation_opportunities[].detected_values` is the ascending
          grid the dimension is published on. That order is the answer -- the
          gaps being reported are the gaps between consecutive values.

    """
    logger.debug(f"Starting table analysis for source: {source}")

    # Materialize the data
    df = _materialise(source)

    # The source's own height, kept whatever is measured below: `row_count`
    # names the file, and a sampled height wearing that name is what made
    # `unique_count: 1000` sit beside `rows: 10000` in the describe payload.
    row_count = len(df)

    # How much of the source to read. Exact counts are what make every
    # dimension fact the file's own, and they are not free: measured here,
    # 100,000 rows x 14 columns costs +35 ms over a thousand-row sample,
    # 1,000,000 x 14 costs +737 ms and 1,000,000 x 50 costs +2,699 ms. The
    # first is a price *Optimize for the laptop* can carry on a one-shot
    # inspection command and the last is not, so the scan reads whole up to
    # `_SCAN_CELL_BUDGET` cells and takes the biggest sample the budget buys
    # above it. A caller who names `sample_rows` has said what to read and
    # gets exactly that. `sampled_rows` carries which of the three happened,
    # because a sample nobody is told about is the defect this replaced.
    budget_rows = max(_SCAN_CELL_BUDGET // df.width, 1) if df.width else row_count
    cap = sample_rows if sample_rows is not None else budget_rows
    sampled_rows = None
    if row_count > cap:
        df = df.sample(n=cap, seed=42)
        sampled_rows = cap
        logger.debug(f"Sampled {cap} rows from {row_count} total rows")

    measured_rows = len(df)
    all_columns = df.columns

    logger.debug(
        f"Analyzing DataFrame with {row_count} rows and {len(all_columns)} columns",
    )

    dimension_info, numeric_columns = _column_facts(df, measured_rows)
    classification = _classify_table(
        dimension_info,
        all_columns,
        numeric_columns,
        value_column,
    )

    logger.debug(f"Detected table format: {classification.format}")

    # Detect overflow column if requested
    overflow_candidate = None
    if detect_overflow and classification.is_wide:
        overflow_candidate = _detect_overflow_column(
            classification.potential_value_columns,
            "auto",
        )
        logger.debug(f"Overflow detection result: {overflow_candidate}")

    interpolation_opportunities = _interpolation_hints(
        df,
        dimension_info,
        enabled=detect_interpolation,
    )

    schema = TableSchema(
        data_dimensions=dimension_info,
        value_columns=classification.value_columns,
        format=classification.format,
        overflow_candidate=overflow_candidate,
        interpolation_opportunities=interpolation_opportunities,
        row_count=row_count,
        sampled_rows=sampled_rows,
    )

    logger.info(
        f"Analysis complete: {classification.format} table with "
        f"{len(dimension_info)} dimensions",
    )
    return schema


def _is_likely_id_column(col_name: str) -> bool:
    """Check if a column name suggests it's an ID/key column."""
    col_lower = col_name.lower()
    id_patterns = [
        "age",
        "year",
        "duration",
        "term",
        "time",
        "period",
        "index",
        "id",
        "key",
        "code",
        "product",
        "sex",
        "smoking",
    ]
    return any(pattern in col_lower for pattern in id_patterns)


def _analyze_numeric_pattern(series: pl.Series) -> str | None:
    """Analyze numeric patterns in a series."""
    values = series.drop_nulls().sort()
    if len(values) == 0:
        return None

    min_val = values.min()
    max_val = values.max()

    # Check if it's a continuous range
    if len(values) > 1:
        spread = values.diff().drop_nulls().std()
        # A numeric column's spread is a float. Two values make one
        # difference, which has no spread (None): no pattern to report.
        if not isinstance(spread, float):
            return None
        if spread < _EVEN_STEP_SPREAD:
            return f"{min_val!s}-{max_val!s}"

    return "continuous"


def _detect_interpolation_opportunities(series: pl.Series) -> list[dict[str, Any]]:
    """Detect potential interpolation opportunities in a numeric series.

    The distinct values are put in ascending order and kept that way: the gap
    test below differences consecutive values, so it only means anything on a
    sorted grid, and the grid is also what the caller reports.
    """
    # `unique()` last would leave the order to polars, which does not
    # promise to preserve its input's and demonstrably does not for
    # String columns. Only Int64/Float64 reach here today, where this
    # build happens to return them ascending anyway; sorting after makes
    # that a property of this function rather than of polars' internals.
    values = series.drop_nulls().unique().sort()
    if len(values) < _FEWEST_VALUES_FOR_A_GAP:
        return []

    # Look for gaps in what appears to be a sequence
    diffs = values.diff().drop_nulls()
    if len(diffs) == 0:
        return []

    # Find the most common difference (step size)
    diff_list = diffs.to_list()
    if not diff_list:
        return []

    # If we have irregular gaps (differences vary significantly), suggest
    # interpolation
    min_diff = min(diff_list)
    max_diff = max(diff_list)

    # If maximum gap is more than 2x the minimum gap, suggest interpolation
    if max_diff > min_diff * 2:
        # Suggest interpolation method based on data characteristics
        method = "linear"  # Default
        # Only Int64 and Float64 dimensions reach here, so the minimum is
        # a number.
        lowest = values.min()
        if isinstance(lowest, int | float) and lowest > 0:
            # All positive values might benefit from log-linear
            method = "log-linear"

        return [
            {
                "detected": values.to_list(),
                # Would need more sophisticated gap detection to identify
                # specific missing values
                "missing": [],
                "method": method,
            },
        ]

    return []
