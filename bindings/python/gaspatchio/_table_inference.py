# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: What the framework infers about a data file it has been handed.
# ABOUTME: Which column holds the rate, what keys it, and whether it is wide or long.
"""What `gspio describe` infers about a data file, and the rules it infers it by.

A user hands the command a parquet, a CSV or a workbook sheet and asks what it
is. Four questions get answered here, none of which the file states about
itself:

1. **Is this an assumption table at all, or a model's own output?** A column of
   per-period values -- a `List`, an `Array`, a `Struct` -- is projection
   output. Assumption storage cannot key on one, so a file carrying any is
   described as results rather than as a table -- *unless the user names one
   of its SCALAR columns as the value*, which is the user declaring that the
   scalar part IS a table and the per-period columns are along for the ride.
   The escape stops there: `--value-column` naming the per-period column
   itself is refused, because no melt or reshape makes a per-period list an
   assumption-table value, and the refusal lists the scalar columns that
   could be one. The command's own output advertises the escape ("Pass
   --value-column to describe them as a table anyway"), and
   `TableDescription.is_projection_output` states the verdict with the
   qualifier on it.
2. **Which column holds the rate?** By the header's wording first, by dtype and
   position second, by position alone last.
3. **What keys it?** Every column that is not the rate -- or, on a wide table
   whose rate is the post-melt ``value``, every column that is not melted.
4. **Is it wide or long?** By counting headers that read as numbers. A file
   that reads as a model-point extract -- an ID-like column and no clear rate
   -- is reported as neither: there is nothing to look up in it.

Every one of these is a guess about the user's data, and `PRINCIPLES.md` asks
the framework to be liberal about the shapes it accepts and strict about the
meanings it infers. **No rule here refuses, and none should:** `describe` is a
report a person reads before writing a `Table(...)` by hand, so declining to
describe a file would serve nobody. What the rules do now is say when the
answer was a choice. Handed a table with two equally plausible rate columns
the value rule names one and returns BOTH as candidates, and the command
names them and names `--value-column` as the way to settle it; handed a table
with no rate column at all it names the last column, and says that is the rule
that answered. A column the user has DECLARED is never overruled by any of
this. Read each function's own docstring for what it decides and what it falls
back to.

Every one of those answers is taken ONCE, in `describe_table`, and stored on
the `TableDescription`. The console and the `--json` payload both read it from
there; neither takes it again. That is the whole of what keeps the two
surfaces from telling one user two different things about one file.

The command that calls this lives in `cli.py`; it parses the arguments, calls
in here, and prints. The two Python snippets the output offers stay over there
too and arrive as `CodeExamples`: they are text in the command's voice, and
this module chooses between them rather than wording them. The richer
column-by-column analysis behind the `--json` payload is
`assumptions._analysis.analyze_table`, which this module calls but does not
duplicate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

import polars as pl
from pydantic import BaseModel

from .assumptions._analysis import analyze_table

if TYPE_CHECKING:
    from pathlib import Path

    from .assumptions._analysis import TableSchema

# Header wordings that name a rate rather than a key, tested as substrings of
# the lowercased header with underscores and spaces stripped out. No entry may
# carry an underscore: the header loses its own before the test, so a pattern
# holding one can never match. `zero_spot` was such an entry, and `spot` one
# line later caught the column it was written for anyway.
_VALUE_COLUMN_PATTERNS: Final = (
    "rate",
    "value",
    "amount",
    "factor",
    "probability",
    "qx",
    "px",
    "mortality",
    "lapse",
    "expense",
    "interest",
    "discount",
    "premium",
    "spot",
    "yield",
    "price",
    "cost",
)

# Above this many number-like headers a table reads as wide. Two durations
# side by side stay "long"; a third tips it.
_WIDE_HEADER_THRESHOLD: Final = 2

# Headers that mark a file as a model-point extract rather than an assumption
# table. Any one of them is enough.
_MODEL_POINT_INDICATORS: Final = frozenset(
    {
        "point_id",
        "policy_id",
        "pol_id",
        "age_at_entry",
        "sum_assured",
        "premium_pp",
        "av_pp_init",
        "policy_count",
        "policy_term",
    },
)

# A model-point file has at most this many columns that look like values; more
# than that and it is a table with keys, whatever its headers are called.
_MAX_MODEL_POINT_VALUES: Final = 1

# How much of the file the payload carries: rows of data, distinct values per
# dimension, and grid points per interpolation hint.
_SAMPLE_ROWS: Final = 5
_SAMPLE_VALUES: Final = 5
_HINT_VALUES: Final = 10


class ValueColumnError(ValueError):
    """The `--value-column` the user named cannot be this table's value.

    Carries the sentence the user should read. The CLI turns it into the
    refusal its own framework raises, so the exit status and the wording stay
    the command's to decide.
    """


class DimensionDetail(BaseModel):
    """Detailed information about a detected dimension.

    ``sample_values`` is the dimension's lowest distinct values in ascending
    order, not the first ones in the file: a dimension's distinct values are a
    set, so there is no file order to preserve, and sorting is what makes two
    runs comparable. ``unique_count`` counts them all, however few are shown.
    """

    name: str
    dtype: str
    unique_count: int
    sample_values: list[Any]
    suggested_type: str  # "key", "melt", "categorical", "value"
    numeric_pattern: str | None = None


class ListColumnDetail(BaseModel):
    """A per-period list column — projection output, never a lookup key.

    Reported separately from ``detected_dimensions`` so an agent reading this
    payload cannot mistake a per-period column for something it can key a
    ``Table.lookup()`` on.
    """

    name: str
    inner_dtype: str
    min_length: int
    max_length: int


class InterpolationDetail(BaseModel):
    """Interpolation opportunity for a dimension."""

    dimension: str
    detected_values: list[int | float]
    missing_values: list[int | float]
    suggested_method: str


class DescribeResponse(BaseModel):
    """Structured response for gspio describe --json.

    Provides everything an LLM agent needs to write a Table() constructor:
    schema, detected dimensions with types and unique values, suggested code,
    sample rows, and interpolation hints.

    Two fields qualify ``detected_value_column``, because the name on its own
    does not say what kind of name it is:

    * ``value_column_source`` is ``"declared"`` (the caller passed
      ``--value-column``, and nothing here overrules it), ``"inferred"`` (a
      column of the file, chosen by the rules), ``"after_melt"`` (the name
      the value column takes AFTER melting the wide columns -- not a column
      of the file, and the melt columns are the dimensions marked ``melt``),
      or ``"none"`` (there is no assumption table here to describe and
      ``detected_value_column`` is empty).
    * ``value_column_candidates`` names every column the rule could not rule
      out, whenever there was more than one. Non-empty means the file is
      ambiguous and the framework chose on nothing better than column order:
      pass ``--value-column`` to say which. Empty means the answer was not a
      choice between columns.

    Two more say how much of the file the dimension facts were measured on,
    and they are on EVERY payload rather than only a sampled one -- a field
    that appears only when the answer is bad leaves its absence to be read as
    good, which is the silence this pair exists to end:

    * ``scan`` is ``"full"`` when every row was read and ``"sampled"`` when
      the file was over the scan's cell budget and a sample stood in.
    * ``scanned_rows`` is how many rows were actually read. It equals ``rows``
      on a full scan and is smaller on a sampled one, where each
      ``detected_dimensions[].unique_count`` and ``sample_values`` is that
      sample's rather than the file's. ``rows``, ``columns``,
      ``column_types``, ``sample_rows`` and ``list_columns`` are the file's
      own either way.
    """

    file_path: str
    format: str
    rows: int
    columns: list[str]
    column_types: dict[str, str]
    table_shape: str
    detected_value_column: str
    value_column_source: str
    value_column_candidates: list[str] = []
    scan: str
    scanned_rows: int
    detected_dimensions: list[DimensionDetail]
    sample_rows: list[dict[str, Any]]
    suggested_code: str
    overflow_candidate: str | None = None
    interpolation_hints: list[InterpolationDetail] = []
    list_columns: list[ListColumnDetail] = []


def partition_nested_columns(df: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
    """Split a frame into its scalar part and its nested per-period columns.

    Nested dtypes (List, Array, Struct) are projection output, never
    assumption-table material — assumption storage cannot key on them. One
    classification consumed by every caller keeps the console and JSON output
    modes from disagreeing about what a results file is.

    Returns:
        The frame with nested columns removed, and their names in schema order.

    """
    nested = [name for name, dtype in df.schema.items() if dtype.is_nested()]
    return (df.drop(nested) if nested else df), nested


def describe_nested_column(df: pl.DataFrame, name: str) -> tuple[str, int, int]:
    """Return ``(inner_dtype, min_length, max_length)`` for one nested column.

    Struct and Array columns have no ``.list`` accessor, so length statistics
    only apply to List; the others report their dtype with zero lengths.
    """
    dtype = df.schema[name]
    if isinstance(dtype, pl.List):
        lengths = df[name].list.len()
        # min()/max() are typed as the full any-value union; the length of a
        # list column is always an integer, so narrow rather than int(...) it.
        lo = cast("int | None", lengths.min())
        hi = cast("int | None", lengths.max())
        return str(dtype.inner), lo or 0, hi or 0
    return str(dtype), 0, 0


@dataclass(frozen=True, slots=True)
class ValueColumnGuess:
    """Which column the rules named the rate, and what else could have been.

    Attributes:
        name: The column the rules chose.
        dimensions: Every other column, mapped to its own name.
        candidates: Every column the rule that answered could not rule out,
            in the file's own order, `name` among them. One entry means the
            rule had one answer; two or more means the file is ambiguous and
            the framework picked on nothing better than column order.
        rule: Which rule answered -- ``"wording"``, ``"dtype_and_position"``
            or ``"last_column"``. Reported to a person so the guess can be
            checked against the thing that made it.

    """

    name: str
    dimensions: dict[str, str]
    candidates: tuple[str, ...]
    rule: str

    @property
    def is_ambiguous(self) -> bool:
        """Whether more than one column was equally good as the rate."""
        return len(self.candidates) > 1


def detect_table_structure(df: pl.DataFrame) -> ValueColumnGuess:
    """Infer which column holds the rate, and treat every other column as a key.

    This is the VLOOKUP question asked of a file nobody has labelled: of these
    columns, which one is the thing being looked up, and which ones are what
    you look it up by. Three rules are tried in order, and the first that
    answers wins.

    1. **The header's wording, over numeric columns only.** Reading left to
       right, the first header that is NUMERIC and CONTAINS one of
       `_VALUE_COLUMN_PATTERNS` -- lowercased, with underscores and spaces
       removed first, so ``"Mortality Rate"`` and ``"mortality_rate"`` are the
       same header. "Numeric" is polars' own `is_numeric()`, the same test
       rule 2 applies, and it is what stops a String id column taking the rule
       on its name alone: on `lapse_rates.parquet` the String `lapse_id` used
       to answer ahead of the Float64 `lapse_rate` beside it. Measured over
       this repository's 136 tracked `.parquet` and `.csv` files, the filter
       moves the answer on 11, and on eight of those it moves to the very name
       the `--json` payload was already reporting.

       It is still a SUBSTRING test on a normalised header, with a consequence
       an actuary should know: ``premium_term``, plainly a term in years, is
       numeric, matches ``premium`` and is taken as the rate ahead of a
       genuine ``annual_charge``. An ends-with rule answers that shape and
       moves 43 files of the same corpus (46 with the numeric filter beside
       it), most of them no more right than before, so the substring test
       stands and the runners-up are reported instead. Every numeric header
       that matches a pattern is a candidate.
    2. **Dtype and position.** With no wording to go on, the LAST column that
       is numeric **and named** -- on the convention that keys come first and
       the rate comes last. "Numeric" is polars' own `is_numeric()`, so a rate
       stored as Decimal, UInt32 or Int16 is seen (a currency-denominated
       table arrives as Decimal); Boolean and the temporal dtypes are not.
       Both halves are a filter over the candidates, not a test applied after
       one is picked: on ``{"q": Float64, "": Float64, "zz": String}`` -- a
       CSV header row of ``q,,zz``, which is what an unnamed index column
       exports as -- ``q`` answers, where picking the last numeric and then
       discarding it for its blank name fell through to rule 3 and returned
       the String column ``zz``. Every named numeric column is a candidate.
    3. **Position alone.** Failing both, the last column, whatever it holds --
       including a string column that cannot be a rate. Its own candidate,
       and nothing else was in the running.

    **It still never refuses, but it no longer hides that it guessed.** A
    table with a `mortality_rate` and a `lapse_rate` returns the leftward one
    with BOTH in `candidates`; the four smoker/sex rate columns of
    `core/benches/fixtures/mortality.csv` return the last with all five
    numeric columns in `candidates`. `PRINCIPLES.md` asks for a clear
    statement naming the ambiguity and the fix rather than a silent pick, and
    the callers print exactly that: `describe` is a report a person reads
    before writing a `Table(...)`, so the honest move is to answer and say the
    answer was a choice, not to decline to describe the file.

    Args:
        df: The scalar part of the file. Must have at least one column: rule 3
            indexes the last one, so a width-zero frame raises `IndexError`.
            The caller decides what a file with nothing scalar in it means.

    Returns:
        The chosen column, the dimensions, the candidates and the rule that
        answered.

    """
    columns = df.columns

    # Rule 1: every NUMERIC header whose wording names a rate. The first
    # wins; the rest are what the caller reports as equally plausible. The
    # dtype filter is the same `is_numeric()` rule 2 uses -- see the docstring
    # for the id column it keeps out of the running.
    wording = [
        col
        for col in columns
        if df[col].dtype.is_numeric()
        and any(
            pattern in col.lower().replace("_", "").replace(" ", "")
            for pattern in _VALUE_COLUMN_PATTERNS
        )
    ]
    if wording:
        return _guess(columns, wording[0], tuple(wording), "wording")

    # Rule 2: every named numeric column, on the convention that keys come
    # first and the rate comes last. Blank-named columns are filtered OUT of
    # the running rather than picked and discarded -- see the docstring.
    numeric = [col for col in columns if col and df[col].dtype.is_numeric()]
    if numeric:
        return _guess(columns, numeric[-1], tuple(numeric), "dtype_and_position")

    # Rule 3: the last column, whatever it holds.
    return _guess(columns, columns[-1], (columns[-1],), "last_column")


def _guess(
    columns: list[str],
    name: str,
    candidates: tuple[str, ...],
    rule: str,
) -> ValueColumnGuess:
    """Assemble one answer, filing every other column as a lookup key."""
    return ValueColumnGuess(
        name=name,
        dimensions={col: col for col in columns if col != name},
        candidates=candidates,
        rule=rule,
    )


def analyze_table_shape(df: pl.DataFrame) -> str:
    """Infer whether the table is published wide or long.

    A **wide** table spreads one dimension across the headers -- the select
    period durations of a select-and-ultimate basis as ``0 1 2 3 4 Ult.``, one
    column per duration. A **long** table carries that dimension in a column of
    its own, one row per combination. Which one it is decides whether the user
    needs a `MeltDimension`, so the answer is worth stating even though nothing
    downstream is bound by it.

    The rule is a head-count: of the headers AFTER the first, how many read as
    a number to `float()`. More than `_WIDE_HEADER_THRESHOLD` of them and the
    table is called wide; otherwise long. The first header is skipped on the
    convention that column zero is the key the wide grid is indexed by.

    What that means at the edges:

    * A non-numeric header among the numbers does not disqualify the table.
      ``Ult.`` does not parse, so a `0 1 2 3 4 Ult.` basis counts five and is
      wide on the durations alone -- which is the shape this rule exists for.
    * A grid only two durations wide is called **long**. The threshold is a
      guess about how many number-like headers happen by accident, not a fact
      about the table.
    * `float()` accepts more than digits, so a column headed ``1e3`` or
      ``-0`` still counts as a duration. What it no longer accepts is
      ``nan``, ``inf`` and ``-inf``: those parse to a float, but no duration
      is one of them, and a CSV whose missing-value marker landed in the
      header row is the shape that reached this. `math.isfinite` is the whole
      of the guard.

    **It never refuses.** Every frame gets one of the two words back, including
    an empty one, which is called long because it has no headers to count.
    """
    columns = df.columns

    # Check if we have numeric column headers (indicating wide format)
    numeric_headers = 0
    for col in columns[1:]:  # Skip first column (usually ID/key)
        try:
            is_duration = math.isfinite(float(col))
        except (ValueError, TypeError):
            is_duration = False
        if is_duration:
            numeric_headers += 1

    if numeric_headers > _WIDE_HEADER_THRESHOLD:
        return "wide"
    return "long"


@dataclass(frozen=True, slots=True)
class TableDescription:
    """Everything inferred about one data file, before anything is printed.

    Attributes:
        file_path: The file the frame was read from.
        frame: The file as read, nested columns included.
        scalar_frame: The same frame with every nested column dropped.
        list_columns: One entry per nested column, in schema order.
        is_projection_output: True when the file carries per-period columns and
            the user named no value column -- a model's own output, which
            cannot be described as an assumption table.
        table_shape: ``"wide"`` or ``"long"``.
        value_column: The column `detect_table_structure` named, before the
            shared verdict was taken over it. `resolved_value_column` is what
            either surface reports; this is the candidate engine's own pick,
            kept because it is what `value_column_candidates` and
            `value_column_rule` describe.
        dimensions: The keys that go with `resolved_value_column`: every other
            scalar column on a long table, the key dimensions on a wide one,
            and nothing where there is no table to describe.
        analysis: The one `analyze_table` run behind both surfaces. Computed
            here so no caller runs it a second time and risks a second answer.
        is_model_points: True when the file reads as a model-point extract --
            a row per policy, with no rate to look up.
        resolved_value_column: The value column BOTH surfaces report. Empty on
            a model-point extract and where there is no table to describe.
            ``"value"`` on a wide table: the name the column takes after the
            melt, which is not a column of the file.
        value_column_source: What kind of name `resolved_value_column` is --
            ``"declared"``, ``"after_melt"``, ``"inferred"`` or ``"none"``.
        value_column_declared: True when the user named the value column, so
            nothing downstream may report a different one.
        value_column_candidates: Every column the rule could not rule out as
            the rate, in file order. Empty when the user declared one or
            there is no table to describe.
        value_column_rule: Which rule answered, or ``""`` where none ran.

    """

    file_path: Path
    frame: pl.DataFrame
    scalar_frame: pl.DataFrame
    list_columns: list[ListColumnDetail]
    is_projection_output: bool
    table_shape: str
    value_column: str
    dimensions: dict[str, str]
    analysis: TableSchema
    is_model_points: bool
    resolved_value_column: str
    value_column_source: str
    value_column_declared: bool = False
    value_column_candidates: tuple[str, ...] = ()
    value_column_rule: str = ""

    @property
    def value_column_is_ambiguous(self) -> bool:
        """Whether two or more columns were equally good as the rate."""
        return len(self.value_column_candidates) > 1

    @property
    def reported_shape(self) -> str:
        """The shape both surfaces report, model points displacing wide/long."""
        return "model_points" if self.is_model_points else self.table_shape

    @property
    def melt_columns(self) -> tuple[str, ...]:
        """The columns a wide table melts into one, in the analysis's order."""
        return tuple(
            dim.name
            for dim in self.analysis.data_dimensions
            if dim.suggested_type == "melt"
        )

    @property
    def describable_as_table(self) -> bool:
        """Whether there is an assumption table here to report at all."""
        return self.scalar_frame.width > 0 and not self.is_projection_output


def _resolve_value_column(
    df: pl.DataFrame,
    scalar_df: pl.DataFrame,
    nested: list[str],
    value_column: str | None,
    *,
    is_projection_output: bool,
) -> ValueColumnGuess:
    """Take the user's value column if they named one, or infer it if not.

    A declared column comes back with no candidates and no rule: nothing was
    chosen between, so there is nothing to report as a runner-up.

    Raises:
        ValueColumnError: The named column is not on the frame, or is a
            per-period column that cannot be an assumption-table value.

    """
    if value_column is None:
        if scalar_df.width == 0 or is_projection_output:
            # Nothing to describe as a table — reporting a detected value
            # column here handed the reader a wrong answer to scan.
            return ValueColumnGuess(name="", dimensions={}, candidates=(), rule="")
        return detect_table_structure(scalar_df)

    if value_column not in df.columns:
        available_cols = ", ".join(df.columns)
        msg = (
            f"Value column '{value_column}' not found. "
            f"Available columns: {available_cols}"
        )
        raise ValueColumnError(msg)
    if value_column in nested:
        # A per-period list is projection output, never an assumption-table
        # value. Validating against `df` alone would accept it and then report
        # it as one.
        msg = (
            f"Value column '{value_column}' is a list column "
            f"(per-period projection output), which cannot be an "
            f"assumption-table value. Scalar columns available: "
            f"{', '.join(scalar_df.columns) or 'none'}"
        )
        raise ValueColumnError(msg)
    return ValueColumnGuess(
        name=value_column,
        dimensions={col: col for col in scalar_df.columns if col != value_column},
        candidates=(),
        rule="",
    )


def describe_table(
    df: pl.DataFrame,
    file_path: Path,
    value_column: str | None = None,
) -> TableDescription:
    """Answer the four questions this module exists to answer, about one file.

    **One verdict, taken here, printed by both surfaces.** The model-point
    verdict and the wide/melt verdict are taken on this one `analyze_table`
    run and stored on the description; `build_describe_response` reads them
    off it and so does the console. They used to be taken inside
    `build_describe_response`, which only `--json` reached, so the console
    answered from `detect_table_structure` alone — and on 85 of this
    repository's 136 tracked data files the two surfaces named different value
    columns, or one named a column the other said did not exist.

    The cost is that the console now runs the analysis it did not run before:
    27 ms on the largest file the package ships, 600,000 cells.

    Args:
        df: The file as read.
        file_path: Where it was read from, used for the read-back snippet.
        value_column: The column the user declared as the rate, if any.

    Raises:
        ValueColumnError: The named value column cannot be one.

    """
    # A file carrying list columns is projection output, not an assumption
    # table: assumption-table storage cannot key on List dtypes, so routing
    # those columns through table-structure detection surfaced a Rust
    # storage error ("Unsupported key type for array storage") for what is
    # the documented way to read back a model's own results (#40).
    # Summarise them separately and analyse only the scalar columns.
    #
    # `is_nested()` rather than `isinstance(dtype, pl.List)`: Array and
    # Struct hit the same storage error, and gaspatchio's own rollforward
    # machinery puts Struct columns in frames, so a results parquet can
    # carry one.
    scalar_df, nested = partition_nested_columns(df)

    # Auto-detection cannot describe projection output as an assumption
    # table. An explicit --value-column is a different matter: the user has
    # declared that the scalar part IS a table, and the nested columns just
    # come along for the ride.
    is_projection_output = bool(nested) and value_column is None

    guess = _resolve_value_column(
        df,
        scalar_df,
        nested,
        value_column,
        is_projection_output=is_projection_output,
    )

    # The column-by-column analysis runs ONCE, here, and both surfaces read
    # its answer off the description. It used to run inside
    # `build_describe_response`, which only the `--json` flag reached, so the
    # console answered from `detect_table_structure` alone and the two
    # printed different value columns on 85 of this repository's 136 tracked
    # data files. The declared column goes in, so the dimension types, the
    # suggested code and the reported value column all answer with it.
    declared = value_column if value_column is not None else None
    analysis = analyze_table(
        scalar_df,
        detect_overflow=True,
        detect_interpolation=True,
        value_column=declared,
    )

    describable = scalar_df.width > 0 and not is_projection_output

    # Model points: an ID-like column, and no clear value column. A DECLARED
    # column reaches past this verdict exactly as it reaches past the
    # projection-output one -- `--value-column` is the documented way to
    # describe a results file's scalar part as a table, and without this the
    # declaration made the verdict CERTAIN rather than escaping it (a declared
    # column is one value column, which passes the count test).
    has_mp_columns = bool(set(df.columns) & _MODEL_POINT_INDICATORS)
    is_model_points = (
        has_mp_columns
        and value_column is None
        and len(analysis.value_columns) <= _MAX_MODEL_POINT_VALUES
    )

    # `analysis.value_columns[0]` is preferred because it is the name the
    # suggested `Table(...)` uses, and a surface whose value column and whose
    # snippet disagree cannot be acted on. The one name it can carry that is
    # not a column of the file is `"value"`, the post-melt name, and
    # `value_column_source` says so rather than leaving the reader to look for
    # a column that is not there.
    resolved = (
        (analysis.value_columns[0] if analysis.value_columns else guess.name)
        if describable and not is_model_points
        else ""
    )
    source = _value_column_source(
        value_col=resolved,
        analysis=analysis,
        declared=value_column is not None,
    )

    return TableDescription(
        file_path=file_path,
        frame=df,
        scalar_frame=scalar_df,
        list_columns=[
            ListColumnDetail(
                name=name,
                inner_dtype=inner,
                min_length=lo,
                max_length=hi,
            )
            for name, (inner, lo, hi) in (
                (name, describe_nested_column(df, name)) for name in nested
            )
        ],
        is_projection_output=is_projection_output,
        table_shape=analyze_table_shape(scalar_df),
        value_column=guess.name,
        dimensions=_keys_for(scalar_df, analysis, resolved, source),
        analysis=analysis,
        is_model_points=is_model_points,
        resolved_value_column=resolved,
        value_column_source=source,
        value_column_declared=value_column is not None,
        value_column_candidates=guess.candidates,
        value_column_rule=guess.rule,
    )


def _keys_for(
    scalar_df: pl.DataFrame,
    analysis: TableSchema,
    value_col: str,
    source: str,
) -> dict[str, str]:
    """Return the keys that go with the value column both surfaces report.

    Three answers, one per verdict. Where there is no value column there are
    no keys to report either. On a WIDE table the reported value column is the
    post-melt ``value``, so the keys are the analysis's key dimensions and the
    melted headers are not among them -- listing every header as a key beside
    a name none of them carries is the contradiction this replaces. Otherwise
    the value column is a column of the file and every other one keys it.
    """
    if not value_col:
        return {}
    if source == "after_melt":
        return {
            dim.name: dim.name
            for dim in analysis.data_dimensions
            if dim.suggested_type == "key"
        }
    return {col: col for col in scalar_df.columns if col != value_col}


@dataclass(frozen=True, slots=True)
class CodeExamples:
    """The two snippets the CLI writes itself, ready for whichever one fits.

    Both are Python source the user copies out of the output, so the command
    that prints them owns their wording; this module only decides which of them
    the file calls for. Keeping the text there also keeps a module that never
    touches an expression out of the lowering census's ledger.

    Attributes:
        read_back: How to read a projection-output file back and inspect a
            per-period column.
        model_points: How to load a model-point extract into an
            `ActuarialFrame`.

    """

    read_back: str
    model_points: str


def _suggested_code(
    description: TableDescription,
    analysis: TableSchema,
    examples: CodeExamples,
    *,
    is_model_points: bool,
) -> str:
    """Return the snippet the payload offers as the user's next move.

    Three answers, one per verdict: a results file gets the read-back snippet,
    a model-point extract gets the frame-loading one, and anything still
    describable as a table gets the `Table(...)` the analyser suggests.
    """
    if not description.describable_as_table:
        return examples.read_back
    if is_model_points:
        return examples.model_points
    return analysis.suggest_table_config()


def _value_column_source(
    *,
    value_col: str,
    analysis: TableSchema,
    declared: bool,
) -> str:
    """Say what kind of name the reported value column is.

    An agent writing a `Table(...)` -- and a person reading the console -- has
    to tell "the column called `rate` in your file" from "the column you will
    have after melting these three". Reported as a word rather than left to a
    membership test, because the membership test alone cannot tell a post-melt
    name from a typo.

    So this asks the analysis which reading it took instead of re-deriving it
    from the name: `TableSchema.format` is ``"wide"`` exactly when
    `value_columns` holds the post-melt name. Testing `value_col in
    scalar_columns` -- the membership test the sentence above rules out --
    answered ``"inferred"`` on an already-long table whose own rate column is
    called `value`.

    Takes the declaration as a flag rather than a `TableDescription` because
    it is called while that description is still being built.
    """
    if not value_col:
        return "none"
    if declared:
        return "declared"
    if analysis.format == "wide":
        return "after_melt"
    return "inferred"


def build_describe_response(
    description: TableDescription,
    examples: CodeExamples,
) -> DescribeResponse:
    """Turn a description into the JSON payload `gspio describe --json` prints.

    The payload is the documented way for an agent to read a file's shape
    before writing model code, so what is and is not asserted here matters.
    Four things it will not assert:

    * Where there is no assumption table to describe, the value column is
      reported empty rather than filled in with a plausible name.
    * Where the name it reports is not a column of the file — ``"value"``,
      after melting — ``value_column_source`` says so.
    * Where more than one column could have been the rate,
      ``value_column_candidates`` names them all.
    * Where the dimension facts were measured on a sample rather than on the
      file, ``scan`` and ``scanned_rows`` say so.

    **Every count here says what it was measured on.** ``rows`` is the file's
    height and ``scanned_rows`` is how many of those rows the ``unique_count``
    and ``sample_values`` beside them came from — equal on a full scan, and
    apart on a file over the scan's cell budget. A payload that reported a
    1,000-row sample's distinct counts beside the file's true ``rows``, with
    nothing saying which was which, told a reader a 10,000-policy extract held
    1,000 distinct policies.

    **Two runs over one unchanged file produce the identical payload**, and
    every list in it is ordered on purpose. An agent diffing this quarter's
    output against last quarter's should see only what actually moved, which
    is what *Audit by default* asks of a machine-readable output.

    Where the order is the answer, it is kept:

    * ``columns``, ``column_types`` and each row of ``sample_rows`` are in the
      file's own column order. That order is what the user sees on opening the
      file, and `detect_table_structure` reads headers left to right, so
      sorting them would hide the input to the rule.
    * ``detected_dimensions`` is in first-seen order -- the order the columns
      appear in the file -- for the same reason.
    * ``list_columns`` is in schema order.
    * ``interpolation_hints[].detected_values`` is the ascending grid the
      dimension is published on; the gaps reported are the gaps in it.

    Where the file's own order is not the answer, one is chosen:

    * ``sample_values`` is sorted ascending, so it is the dimension's lowest
      five distinct values. The order polars' ``unique()`` returns is a hash
      order that differs between two calls in one process, so it could not
      stay. A first-seen order was the alternative and does exist --
      ``unique(maintain_order=True)`` -- and was passed over because it moves
      when the same data is exported in a different row order, which makes a
      quarter-over-quarter diff light up on a rewrite that changed nothing.
    """
    df = description.frame
    scalar_df = description.scalar_frame

    # The analysis, the model-point verdict and the value column are READ off
    # the description rather than computed here. `describe_table` takes them
    # once, so the console and this payload cannot answer differently -- which
    # they did, on 85 of this repository's 136 tracked data files.
    analysis = description.analysis
    is_model_points = description.is_model_points

    # Build dimension details from analysis
    dim_details = [
        DimensionDetail(
            name=dim.name,
            dtype=dim.dtype,
            unique_count=dim.unique_count,
            sample_values=dim.sample_values[:_SAMPLE_VALUES],
            suggested_type=dim.suggested_type,
            numeric_pattern=dim.numeric_pattern,
        )
        for dim in analysis.data_dimensions
        if dim.suggested_type != "value"
    ]

    # The value column and what kind of name it is: both taken in
    # `describe_table`, where the console reads them too. For projection
    # output — or a frame with no scalar columns at all, or a model-point
    # extract — there is no assumption-table value to report, and naming one
    # handed the reader a wrong answer to scan.
    value_col = description.resolved_value_column
    source = description.value_column_source

    # Build interpolation hints
    interp_hints = [
        InterpolationDetail(
            dimension=hint.dimension,
            detected_values=hint.detected_values[:_HINT_VALUES],
            missing_values=hint.missing_values[:_HINT_VALUES],
            suggested_method=hint.suggested_method,
        )
        for hint in analysis.interpolation_opportunities
    ]

    # Sample rows, nested columns excluded. Dumping five rows of raw
    # per-period lists is what `list_columns` exists to replace: a
    # 10-column x 1200-period file produced ~900 KB of JSON, which
    # destroys the context of the agent that follows the documented
    # `--output-file` then `describe --json` workflow.
    sample_rows = scalar_df.head(_SAMPLE_ROWS).to_dicts()

    return DescribeResponse(
        file_path=str(description.file_path),
        format=description.file_path.suffix.lstrip(".").lower(),
        rows=len(df),
        columns=df.columns,
        column_types={
            col: str(dtype) for col, dtype in zip(df.columns, df.dtypes, strict=True)
        },
        table_shape=description.reported_shape,
        detected_value_column=value_col,
        value_column_source=source,
        value_column_candidates=(
            list(description.value_column_candidates)
            if value_col and description.value_column_is_ambiguous
            else []
        ),
        scan="full" if analysis.sampled_rows is None else "sampled",
        scanned_rows=(
            analysis.row_count
            if analysis.sampled_rows is None
            else analysis.sampled_rows
        ),
        detected_dimensions=dim_details,
        sample_rows=sample_rows,
        suggested_code=_suggested_code(
            description,
            analysis,
            examples,
            is_model_points=is_model_points,
        ),
        overflow_candidate=analysis.overflow_candidate,
        interpolation_hints=interp_hints,
        list_columns=description.list_columns,
    )
