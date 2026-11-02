# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The steps that turn a source into a table's processed frame, and its fingerprint.

A table's identity is a content hash over its processed frame in canonical
form, and two things need the frame built the same way: ``Table`` itself, as
it registers, and a reviewer re-reading a file on disk as the table a run
record names (``gspio verify --assumptions``). Both take these steps, so a
file the table was read from reaches the fingerprint the table carried.
Nothing here registers a table or reaches the lookup kernel: the module sits
below the authoring surface, where a reader of a record can call it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final

import polars as pl
from loguru import logger

from gaspatchio._dtypes import with_signed_zeros_as_zero
from gaspatchio._identity import content_sha_of
from gaspatchio._table_lifecycle import registering_framework_owned
from gaspatchio.assumptions._data import (
    _declared_output_columns,
    _declared_text_columns,
)
from gaspatchio.assumptions._dimensions import (
    CategoricalDimension,
    ComputedDimension,
    DataDimension,
    MeltDimension,
)
from gaspatchio.assumptions._utils import _materialise, _normalise_key_dtypes

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from gaspatchio.assumptions._dimensions import Dimension

__all__ = ["content_fingerprint_of", "shaping_steps"]


def _canonical_key_columns(columns: Sequence[str], value: str) -> list[str]:
    """Return a processed table's key columns in canonical order.

    Every column but the answer, ascending by name (code point order). The
    canonical order is what makes a table's content identity independent of
    the order its source listed columns in.
    """
    return sorted(column for column in columns if column != value)


def _canonical_frame(
    frame: pl.DataFrame, key_columns: Sequence[str], value: str
) -> pl.DataFrame:
    """Return ``frame`` in a table's canonical form.

    The key columns in the order given (canonical: see
    :func:`_canonical_key_columns`), the value column last, and the rows
    ascending by the keys in that order. A table's keys are unique, so the
    sort is a total order and the form is the same whatever order the rows
    or columns arrived in.
    """
    keys = list(key_columns)
    return frame.select([*keys, value]).sort(keys)


# The kinds a table refuses as a key: the content grammar names no duration
# and no time of day (section 12.3), so neither has a fingerprint of its own.
_KINDS_A_KEY_CANNOT_BE: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.Duration, pl.Time}
)


def _refuse_a_duration_or_time_key(
    name: str, frame: pl.DataFrame, key_columns: Sequence[str]
) -> None:
    """Refuse a key column holding durations or times of day, by its name.

    A table's identity is a content hash over its keys in their kind
    (section 12.3), and the content grammar names a date and an instant but
    neither a duration nor a time of day. Held as the bare count of its unit,
    such a key would share a fingerprint with the integer of that count and
    with the same count in another unit, so it is refused here, as every
    other door that hashes a column refuses the type, with the move: key the
    table on a whole number of the unit meant, or on a date.
    """
    for column in key_columns:
        dtype = frame.schema[column]
        if dtype.base_type() not in _KINDS_A_KEY_CANNOT_BE:
            continue
        if dtype.base_type() == pl.Duration:
            said, example, dated = (
                "durations",
                f"pl.col({column!r}).dt.total_days() or .dt.total_milliseconds()",
                "on a date",
            )
        else:
            said, example, dated = (
                "times of day",
                f"pl.col({column!r}).dt.hour(), or the seconds since midnight",
                "on a date and time, where the time belongs to a day",
            )
        msg = (
            f"Table {name!r} key column {column!r} holds {said} ({dtype}), which "
            "a table cannot be keyed on: its fingerprint would be the bare count "
            "of the unit, the same as a whole number's and as the same count in "
            "another unit. Key the table on a whole number of the unit you mean "
            f"-- for example {example} -- or {dated}, and write the lookup's key "
            "the same way."
        )
        raise ValueError(msg)


def _held_as_counts(
    frame: pl.DataFrame, key_columns: Sequence[str]
) -> tuple[pl.DataFrame, dict[str, pl.DataType]]:
    """Return ``frame`` with each date or timestamp key held as its count, and kinds.

    A date and a timestamp are keys of their own kind: a lookup reads one
    only with a key of that kind, converted to the table's unit. The lookup
    kernel holds it as the whole number of its unit -- exact for a
    nanosecond timestamp, where a double would merge two instants into one
    key -- and the kind each such column had is returned beside the frame,
    to be kept beside the table. A duration or a time of day key is refused
    before this (:func:`_refuse_a_duration_or_time_key`).
    """
    kinds = {
        column: frame.schema[column]
        for column in key_columns
        if frame.schema[column].is_temporal()
    }
    if not kinds:
        return frame, kinds
    counts = frame.with_columns(
        frame[column].to_physical().cast(pl.Int64) for column in kinds
    )
    return counts, kinds


def _in_its_kinds(
    frame: pl.DataFrame, kinds: Mapping[str, pl.DataType]
) -> pl.DataFrame:
    """Return a processed table frame with each date or timestamp key back in its kind.

    The inverse of :func:`_held_as_counts`: each count is read back as the
    date or timestamp it counts, in the unit and zone the table was built
    from -- the frame a table's identity is taken over, the frame its
    payload carries, and the source a shocked or stacked copy is rebuilt
    from.
    """
    restored = {
        column: kind for column, kind in kinds.items() if column in frame.columns
    }
    if not restored:
        return frame
    return frame.with_columns(
        frame[column].cast(pl.Int64).cast(kind) for column, kind in restored.items()
    )


def _hash_processed_df(
    processed_df: pl.DataFrame, kinds: Mapping[str, pl.DataType] | None = None
) -> str:
    """Return ``sha256:<hex>`` over the values of a processed table frame.

    Hashes the fully processed DataFrame that is registered with the Rust
    registry. The frame is in canonical form before this call (keys ascending
    by name, value last, rows sorted by the keys), so identical source data
    produces an identical hash regardless of the order its rows or columns
    arrived in. Shared by the graph and the native execution-time identity
    check, and returned by :meth:`Table.fingerprint`.

    A date or timestamp key the kernel holds as a count (``kinds``, as
    :func:`_held_as_counts` returned them) is hashed as the date or the
    instant it counts, under the content grammar's own tag (section 12.3), as
    the book digest hashes one: an instant kept in milliseconds,
    microseconds or nanoseconds has one fingerprint, a zone is part of it,
    and a count of days, of milliseconds or of nothing at all never shares
    one. A millisecond count whose microseconds leave an ``i64`` is refused
    by name, as every other door refuses it.
    """
    return content_sha_of(_in_its_kinds(processed_df, kinds or {}))


def _normalised_dimensions(
    dimensions: Mapping[str, str | Dimension],
) -> dict[str, Dimension]:
    """Return a ``dimensions=`` declaration with every entry a dimension object.

    The dict maps YOUR name -> SOURCE column name, so the source column is
    renamed to the dimension name during processing; lookup() kwargs then
    match the processed table's key columns (issue #30 -- the shorthand
    previously discarded the dict key and the rename never happened).
    """
    normalised: dict[str, Dimension] = {}
    for dim_name, dim_config in dimensions.items():
        if isinstance(dim_config, str):
            normalised[dim_name] = DataDimension(dim_config, rename_to=dim_name)
        elif (
            isinstance(dim_config, DataDimension)
            and dim_config.rename_to is None
            and dim_config.column != dim_name
        ):
            # An explicit DataDimension under a differing dict key gets the
            # same rename; a user-set rename_to always wins.
            normalised[dim_name] = replace(dim_config, rename_to=dim_name)
        else:
            normalised[dim_name] = dim_config
    return normalised


def content_fingerprint_of(
    source: str | Path | pl.DataFrame,
    dimensions: Mapping[str, str | Dimension],
    value: str,
) -> str:
    """Return the fingerprint a table built over ``source`` would carry.

    What ``Table(name, source, dimensions, value).fingerprint()`` returns,
    taken without building the table: nothing is registered, so no lookup
    anywhere in the process can be moved by asking, and no name is spent.
    The source goes through the same steps a table's construction takes --
    the dimensions, the undeclared columns set aside, the keys judged on
    their cells unless declared text, the canonical form -- and the hash is
    the content hash over the result. It is how ``gspio verify
    --assumptions`` re-reads a file on disk as the table a run record names.

    !!! note "When to use"
        * **Audit:** Re-read an assumption file as the table a run record
          names, and compare with the `fingerprint` its entry carries.
        * **Pre-run checks:** Confirm this quarter's file holds the basis a
          known-good fingerprint names, before any table is built.

    Args:
        source: The file, or the frame, a table would be read from.
        dimensions: The ``dimensions=`` a table would be declared with.
        value: The column it would answer with.

    Returns:
        ``sha256:`` followed by 64 lowercase hexadecimal digits.

    Raises:
        ValueError: If the source does not hold what the declaration names,
            exactly as building the table would refuse it.

    Examples:
    --------
    ```python
    import polars as pl
    from gaspatchio.assumptions import Table
    from gaspatchio.assumptions._processing import content_fingerprint_of

    rates = pl.DataFrame({"age": [30, 31], "qx": [0.001, 0.0012]})
    table = Table("mortality_reread", rates, {"age": "age"}, "qx")
    reread = content_fingerprint_of(rates.reverse(), {"age": "age"}, "qx")

    print(reread == table.fingerprint())
    ```

    ```text
    True
    ```
    """
    declared = _normalised_dimensions(dimensions)
    shaped = _shaped_frame(
        _materialise(source), declared, value, validate=True, name="fingerprint"
    )
    key_columns = _canonical_key_columns(shaped.columns, value)
    _refuse_a_duration_or_time_key("fingerprint", shaped, key_columns)
    counted, kinds = _held_as_counts(shaped, key_columns)
    return _hash_processed_df(_judged_frame(counted, declared, value), kinds)


def _judged_frame(
    shaped: pl.DataFrame,
    dimensions: dict[str, Dimension],
    value: str,
    *,
    name: str | None = None,
) -> pl.DataFrame:
    """Return a shaped table frame with its keys judged, in canonical form.

    The other half of building a table, after :func:`_shaped_frame`: the key
    columns are every column but the answer, ascending by name. Ordinary keys
    are normalized for native lookup, wide identities retained -- and a key
    the author declared text stays text: the declaration is the meaning, and
    judging its cells on the numbers they spell would override it. Then the
    frame is put in its canonical form, key columns ascending by name, the
    value column last, rows ascending by those keys. The sort also keeps
    array storage indices in categorical order (position == index), and the
    column order is the one every reader binds lookup operands in, so a
    reordered source changes nothing downstream.
    """
    # A negative zero is written as zero where a table's data enters, before
    # it is hashed or read (spec section 12.3). A table the framework builds
    # for itself -- a scenario plan's per-scenario factors, whose identity step
    # adds -0.0 so that x * 1.0 + -0.0 is x for a signed zero too, or a shocked
    # copy of a table already read -- is the plan's recipe, not data entering,
    # and keeps its bits.
    if not registering_framework_owned():
        shaped = with_signed_zeros_as_zero(shaped)
    key_columns = _canonical_key_columns(shaped.columns, value)
    if not key_columns:
        msg = (
            f"No key columns found after dimension processing. All columns "
            f"cannot be the value column '{value}'"
        )
        raise ValueError(msg)
    declared_text = _declared_text_columns(dimensions)
    judged = _normalise_key_dtypes(
        shaped, [col for col in key_columns if col not in declared_text]
    )
    answered = _answer_read_as_f64(judged, value, name=name)
    return _canonical_frame(answered, key_columns, value)


# The largest integer magnitude every value up to which an f64 holds exactly.
_F64_EXACT_INTEGERS = 2**53


def _answer_read_as_f64(
    frame: pl.DataFrame, value: str, *, name: str | None = None
) -> pl.DataFrame:
    """Return ``frame`` with its answer column read as the ``f64`` a lookup answers.

    A lookup answers ``f64`` (section 11.1.24: "an ``f64`` answer column"),
    and the native kernel holds the answer column in nothing else. A
    published table whose answers are whole numbers -- a count, an integer
    percentage, a rate in basis points -- arrives as an integer column, and
    a single-precision file as ``Float32``, a database extract as a
    fixed-point ``Decimal``; each is read as the double it is (a decimal's
    nearest double), so the table is the same table, under one fingerprint, as the
    one whose source spelled them ``3.0``. An integer is read only where the
    double holds it exactly, within ``2**53``: past that the answer the
    lookup gave would not be the number the file holds, so the table is
    refused by the value that does not fit.

    A column that is not a number at all -- a flag, text, a date -- is not
    read as one: which number a ``True`` or a ``"5%"`` stands for is the
    author's to say, so the table is refused with the cast that says it.

    Raises:
        ValueError: If the answer column is not numeric, or holds an integer
            an ``f64`` does not hold exactly.

    """
    if value not in frame.columns:
        return frame
    table = f"Table {name!r}: the" if name is not None else "The"
    column = frame[value]
    dtype = column.dtype
    if dtype == pl.Float64:
        return frame
    if dtype == pl.Float32 or isinstance(dtype, pl.Decimal):
        # A fixed-point decimal is read as the double nearest it, as a book
        # column of one is where it enters the frame.
        return frame.with_columns(column.cast(pl.Float64))
    if dtype.is_integer():
        # Read off the extremes in Python: a narrow column compared with
        # 2**53 would overflow Polars' own scalar.
        extremes = [column.min(), column.max()]
        too_wide = [
            each
            for each in extremes
            if isinstance(each, int) and abs(each) > _F64_EXACT_INTEGERS
        ]
        if too_wide:
            msg = (
                f"{table} answer column {value!r} holds {too_wide[0]}, an integer "
                f"past 2**53. A lookup answers an f64, which holds every whole "
                f"number only up to 2**53 ({_F64_EXACT_INTEGERS:,}), so this "
                f"table's answer would not be the number its source holds. "
                f"Scale the column into range before building the table, or "
                f"cast it with pl.col({value!r}).cast(pl.Float64) to accept "
                f"the nearest double."
            )
            raise ValueError(msg)
        return frame.with_columns(column.cast(pl.Float64))
    msg = (
        f"{table} answer column {value!r} holds {dtype}, and a lookup answers a "
        f"number (an f64). Convert it before building the table -- for a "
        f"flag, pl.col({value!r}).cast(pl.Float64) reads true as 1.0 and "
        f"false as 0.0 -- so the record carries the reading the model made."
    )
    raise ValueError(msg)


def _shaped_frame(
    df: pl.DataFrame,
    dimensions: dict[str, Dimension],
    value: str,
    *,
    validate: bool,
    name: str,
) -> pl.DataFrame:
    """Return a source frame put through a table's dimensions, the rest set aside.

    The half of building a table that turns the frame a source holds into the
    columns the table is keyed by and answers with: each dimension's own
    processing, in the order their dependencies need, and then every column
    the declaration does not name set aside. What is left is judged and put
    in canonical form by the caller.
    """
    if validate:
        # Check if we have MeltDimension - if so, value column will be created
        has_melt_dimension = any(
            dim.__class__.__name__ == "MeltDimension" for dim in dimensions.values()
        )

        # Only validate value column exists if we don't have melt dimension
        if not has_melt_dimension and value not in df.columns:
            available_cols = ", ".join(df.columns)
            msg = (
                f"Value column '{value}' not found in DataFrame.\n"
                f"Available columns: {available_cols}"
            )
            raise ValueError(msg)

    # Process dimensions in order
    # Note: Order matters for dependencies (e.g., ComputedDimension depends on others)
    current_df = df

    # Process dimensions in a specific order:
    # 1. DataDimension (base columns, renames)
    # 2. CategoricalDimension (add constant columns)
    # 3. MeltDimension (pivot operations)
    # 4. ComputedDimension (depends on other columns)

    dimension_order = [
        "DataDimension",
        "CategoricalDimension",
        "MeltDimension",
        "ComputedDimension",
    ]

    for dimension_type in dimension_order:
        for dim_name, dimension in dimensions.items():
            if dimension.__class__.__name__ == dimension_type:
                if validate:
                    dimension.validate(current_df)
                current_df = dimension.process(current_df)
                logger.debug(f"Processed dimension '{dim_name}' ({dimension_type})")

                # Handle MeltDimension value column naming
                if (
                    dimension_type == "MeltDimension"
                    and "value" in current_df.columns
                    and value != "value"
                ):
                    current_df = current_df.rename({"value": value})
                    logger.debug(
                        f"Renamed melt value column from 'value' to '{value}'",
                    )

    # Believe the declaration. Published assumption tables essentially
    # always carry extra columns — an earned rate next to a credited
    # rate, a count next to a rate, a source note — and requiring the
    # caller to pre-trim the frame is an ETL step. Promoting an
    # undeclared column to a dimension key is a guess about its meaning,
    # and the guess used to fail several steps later with a key-dtype
    # error that never named the column (gh#66). The user stated the key
    # set in `dimensions=`; keep exactly those columns (each dimension's
    # processed output name) plus the value, and set the rest aside.
    # This also drops a ComputedDimension's consumed inputs, which
    # previously leaked into the key set the same way.
    declared_outputs = set(_declared_output_columns(dimensions).values())
    undeclared = [
        c for c in current_df.columns if c not in declared_outputs and c != value
    ]
    if undeclared:
        current_df = current_df.drop(undeclared)
        logger.debug(
            f"Table '{name}': ignoring undeclared columns "
            f"{undeclared} (neither in dimensions= nor the value column)",
        )

    return current_df


def shaping_steps(dimensions: Mapping[str, Dimension]) -> list[dict[str, Any]]:
    """Return each step of a table's recipe that reshapes what it reads.

    A table's processed frame is a plain read of its source when every
    dimension takes a column as it stands: the same name, and the same type
    or text. Every other dimension changes the frame on the way -- a column
    renamed, cast, melted from several, set to a constant, or computed -- and
    a file read back without that recipe is not the table the recipe made.
    Each such step is one entry: ``step``, the ``column`` it produces, and
    ``from`` where it names the columns it was made from (``to`` for a cast).

    !!! note "When to use"
        * **Audit:** Say whether a table's file on disk can be read back as
          the table, before comparing fingerprints, so a reshaped table is
          never reported as an edited one.

    Args:
        dimensions: The table's declared dimensions, normalised.

    Returns:
        The steps, in the order the dimensions were declared; empty where the
        processed frame is a plain read of the source.

    Examples:
    --------
    ```python
    from gaspatchio.assumptions._dimensions import DataDimension
    from gaspatchio.assumptions._processing import shaping_steps

    print(shaping_steps({"age": DataDimension("age", rename_to="age")}))
    print(shaping_steps({"age": DataDimension("Age", rename_to="age")}))
    ```

    ```text
    []
    [{'step': 'renamed', 'column': 'age', 'from': 'Age'}]
    ```
    """
    steps: list[dict[str, Any]] = []
    for key, dimension in dimensions.items():
        if isinstance(dimension, DataDimension):
            produced = dimension.rename_to or dimension.column
            if produced != dimension.column:
                steps.append(
                    {"step": "renamed", "column": produced, "from": dimension.column}
                )
            if dimension.dtype is not None and dimension.dtype != pl.String:
                steps.append(
                    {"step": "cast", "column": produced, "to": str(dimension.dtype)}
                )
        elif isinstance(dimension, MeltDimension):
            steps.append(
                {
                    "step": "melted",
                    "column": dimension.name,
                    "from": list(dimension.columns),
                }
            )
        elif isinstance(dimension, CategoricalDimension):
            steps.append({"step": "set", "column": dimension.name or key})
        elif isinstance(dimension, ComputedDimension):
            steps.append({"step": "computed", "column": dimension.name})
        else:
            steps.append({"step": type(dimension).__name__, "column": key})
    return steps
