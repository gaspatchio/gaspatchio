# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: The audit chain's recipe encoding, content byte grammar, and SHA helpers.
# ABOUTME: Used by Schedule, Curve, MortalityTable, Table, joins, and injected columns.

"""The audit chain's two byte grammars, and the SHA-256 stamps taken over them.

A **recipe** -- a schedule, a curve, an assumption table's own description of
itself -- is encoded as canonical JSON, and its stamp is what ``source_sha``
carries.

A **frame of values** is encoded by the content grammar of
``spec/graph-artifact/v0-preview.md`` section 12.3, which is the
specification's own and deliberately not an engine's serialisation. A stamp
taken over a writer's file layout moves the moment that writer is upgraded,
with no data behind the movement, and a consumer holding the values alone
could never reproduce it. Both failures are the same failure: a content hash
that answers a question about the library rather than about the data.

**Three layers write the content grammar, and only one of them runs.**

- **The Rust core writes every stamp**: ``content_bytes_of``,
  ``content_sha_of`` and ``injected_content_sha_of`` hand the frame to it.
  Every result's manifest digests every cell of the book it ran over,
  and at a book's size that is the core's work. The vocabulary still names
  each column's type here first, so a refusal reads the same whichever
  encoder would have written.
- **The vectorised Python encoder** -- ``_content_bytes_of_reference`` and
  the ``_*_block`` functions beneath it -- is the oracle the core is held
  byte-identical to by test. Nothing in a run calls it. It is kept fast
  enough, by whole-array arithmetic, that a test can run it over frames of
  a real book's size, which is where a disagreement would hide.
- **The row-by-row ``_*_reference`` functions** are the grammar as section
  12.3 reads: take each row, write its marker, write its value. The
  vectorised encoder is held equal to them, so neither the oracle nor the
  core is its own only statement of intent.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final, NamedTuple

import numpy as np
import polars as pl

from gaspatchio._canonical import (
    SHA256_PREFIX,
    canonical_bytes,
    source_sha_of,
)
from gaspatchio._internal import content_bytes as _core_content_bytes
from gaspatchio._internal import content_sha256 as _core_content_sha256

if TYPE_CHECKING:
    import numpy.typing as npt

    from gaspatchio.typing import PolarsDataType

__all__ = [
    "SHA256_PREFIX",
    "canonical_bytes",
    "content_bytes_of",
    "content_sha_of",
    "injected_content_sha_of",
    "source_sha_of",
]

# --- the content grammar ----------------------------------------------------

# One tag byte per column type, taken from the block the calculation graph's
# own scalar tags occupy, so that a reader holding both grammars meets one
# number per type rather than two. ``date`` and ``datetime`` are the two the
# op-tree has no literal for and a column of data does need; they take the
# next two numbers rather than borrowing ``i64``'s, because a count of days
# and a plain whole number are different claims about a column and a reader
# comparing two quarters has to be able to see one become the other.
_TAG_FLAG: Final[bytes] = b"\x11"
_TAG_WHOLE_NUMBER: Final[bytes] = b"\x12"
_TAG_DECIMAL: Final[bytes] = b"\x13"
_TAG_TEXT: Final[bytes] = b"\x14"
_TAG_SEQUENCE: Final[bytes] = b"\x15"
_TAG_DATE: Final[bytes] = b"\x16"
_TAG_DATETIME: Final[bytes] = b"\x17"

_SCALAR_TAGS: Final[dict[str, bytes]] = {
    "bool": _TAG_FLAG,
    "i64": _TAG_WHOLE_NUMBER,
    "f64": _TAG_DECIMAL,
    "str": _TAG_TEXT,
    "date": _TAG_DATE,
    "datetime": _TAG_DATETIME,
}

# The two names that travel as a whole number: a count, and a count of days
# since 1970-01-01. A timestamp is not one of them: it travels as whole
# microseconds and the nanoseconds past them (``_instant_block``).
_WHOLE_NUMBER_NAMES: Final[frozenset[str]] = frozenset({"i64", "date"})
_DECIMAL_NAME: Final[str] = "f64"
_TEXT_NAME: Final[str] = "str"
_DATE_NAME: Final[str] = "date"
_DATETIME_NAME: Final[str] = "datetime"

# A timestamp travels as microseconds and the nanoseconds past them.
_NANOS_PER_MICRO: Final[int] = 1_000
_MICROS_PER_MILLI: Final[int] = 1_000

# How the type vocabulary spells a column whose values are runs of values.
_LIST_OPEN: Final[str] = "list["
_LIST_CLOSE: Final[str] = "]"

# A value carries a marker in front of it saying whether it is there at all.
# A rate nobody supplied and a rate of nought are two different assumptions
# -- one propagates a null, the other multiplies a reserve to zero -- so the
# difference is written down rather than left to be inferred from bytes that
# would otherwise look alike.
_PRESENT: Final[int] = 0x02
_ABSENT: Final[int] = 0x01
_NO_VALUE: Final[int] = 0x00
_PRESENT_MARK: Final[bytes] = bytes([_PRESENT])
_MISSING: Final[bytes] = bytes([_ABSENT, _NO_VALUE])
_MISSING_WIDTH: Final[int] = len(_MISSING)

# Eight IEEE-754 bytes for a decimal, and the ten seven-bit groups a
# sixty-four-bit zigzag varint can run to.
_DECIMAL_WIDTH: Final[int] = 8
_VARINT_GROUPS: Final[int] = 10
_GROUP_BITS: Final[int] = 7
_GROUP_MASK: Final[int] = 0x7F
_CONTINUES: Final[int] = 0x80
_SIGN_BITS: Final[int] = 0xFFFF_FFFF_FFFF_FFFF

# Precomputed once: the shift that lifts each seven-bit group into place and
# the group's own position, so that the varints of a whole column are built
# by array arithmetic rather than by a trip round a Python loop per row.
_SHIFTS: Final[npt.NDArray[np.uint64]] = np.arange(
    _VARINT_GROUPS, dtype=np.uint64
) * np.uint64(_GROUP_BITS)
_POSITIONS: Final[npt.NDArray[np.int64]] = np.arange(_VARINT_GROUPS, dtype=np.int64)


class _Block(NamedTuple):
    """A column's values, encoded, and the byte width each one took.

    The widths are not part of the grammar -- nothing reads them back out
    of the bytes -- they are what lets a run of values be spliced into a
    larger encoding without a trip round a Python loop per row. A sequence
    column encodes every member of every row in one pass and then reads
    each row's byte span off the running total of these.
    """

    data: bytes
    widths: npt.NDArray[np.int64]


_NO_WIDTHS: Final[npt.NDArray[np.int64]] = np.zeros(0, dtype=np.int64)
_EMPTY_BLOCK: Final[_Block] = _Block(b"", _NO_WIDTHS)

# The running total before the first value of any run, so that a cumulative
# sum can be read as a set of boundaries rather than as a set of ends.
_BEFORE_THE_FIRST: Final[npt.NDArray[np.int64]] = np.zeros(1, dtype=np.int64)


def _varint(value: int) -> bytes:
    """Encode a count or a byte length, seven bits at a time, low group first."""
    out = bytearray()
    while True:
        group = value & _GROUP_MASK
        value >>= _GROUP_BITS
        if not value:
            out.append(group)
            return bytes(out)
        out.append(group | _CONTINUES)


def _text(value: str) -> bytes:
    """Encode text as UTF-8 behind its byte length."""
    raw = value.encode("utf-8")
    return _varint(len(raw)) + raw


def content_bytes_of(frame: pl.DataFrame) -> bytes:
    """Return the bytes that stand for ``frame``'s columns and their values.

    The framework's content grammar, written out in
    ``spec/graph-artifact/v0-preview.md`` section 12.3 so that a consumer
    holding the values and nothing else reproduces the digest: a count of
    columns, then per column its name, the tag for the type it carries, a
    count of rows, and every value's bytes in row order, each behind a
    marker saying whether the value is there.

    **Storage width is not content.** A column's tag is the neutral type the
    artifact names it by, so an ``Int32`` and an ``Int64`` holding the same
    numbers -- or a ``Float32`` and a ``Float64`` -- write the same bytes.
    The values are the content; how many bytes an engine chose to keep them
    in is not something anybody promised. Where narrowing actually changed a
    number, the number moves and the hash moves with it.

    The bytes are written by the Rust core, and
    :func:`_content_bytes_of_reference` is the Python definition they are
    held byte-identical to.

    Args:
        frame: The columns to encode, in the order the frame holds them and
            with the rows in the order the caller put them in.

    Returns:
        The encoded bytes.

    Raises:
        UnmappedDtypeError: If a column has a type the artifact's own
            vocabulary cannot name. The refusal names the column, the type,
            and the cast that would carry the value.

    """
    return _core_content_bytes(*_handed_to_the_core(frame))


def content_sha_of(frame: pl.DataFrame) -> str:
    """Return ``sha256:<hex>`` over :func:`content_bytes_of` of ``frame``.

    The one content-identity primitive in the framework, taken over the
    specification's own grammar rather than any engine's serialisation: a
    consumer that holds the values -- from the file, from a payload read
    back out of an artifact -- re-derives the digest from the published
    grammar alone, with no library in common with the producer.

    **Row order is the caller's problem.** The bytes reflect the frame
    exactly as handed over, so a caller that wants two loads of the same
    data to agree must impose a deterministic order first — by unique key
    columns where it has them (``Table``), by every column where it does
    not (a join's right side). The third caller imposes none: an injected
    column lands on the frame's rows by position, so for an injection the
    order *is* the content and sorting it would hide the change the stamp
    is there to catch.

    **Hashes from different callers are not comparable**, even for the same
    underlying data: each one hashes the column set *it* considers the
    table's content, so a ``Table``'s dimension-plus-value projection and a
    join's whole right side produce different bytes from the same file. The
    hash answers "is this the same table as last quarter's run?", never "is
    this table the same as that other table?".

    **The bytes stream into SHA-256 as the core writes them**, with the GIL
    released, so a result's digest of a ten-million-policy book is one pass
    over its values and never a buffer the size of the book.
    """
    return f"{SHA256_PREFIX}{_core_content_sha256(*_handed_to_the_core(frame))}"


def injected_content_sha_of(values: pl.Series, column: str) -> str:
    """Return ``sha256:<hex>`` over one column of values injected at a line.

    The bytes are :func:`content_bytes_of`'s over the one-column frame the
    values make, so an injection's stamp and an assumption table's are
    taken under one grammar and one set of rules. The only thing added
    here is the name a refusal reads out.

    The values are hashed under the fixed placeholder name the injection
    gives them -- the series' own name is not part of what was injected,
    the column's name is the assignment key -- so the same values stamp
    alike whatever the series they arrived in was called. A column whose
    type the vocabulary cannot name has to be refused naming the column
    the author actually wrote, though: a message about a placeholder
    nobody named sends them looking for a line that is not in the model.

    Args:
        values: The injected column, under the placeholder name whose
            bytes the stamp is taken over.
        column: The name the assignment gave it, for the refusal.

    Returns:
        The stamp, as ``sha256:`` and sixty-four hex digits.

    Raises:
        UnmappedDtypeError: If the values have a type the artifact's own
            vocabulary cannot name.

    """
    # A frame of one column, which is what an injection is.
    one_column = _handed_to_the_core(values.to_frame(), refused_as=column)
    return f"{SHA256_PREFIX}{_core_content_sha256(*one_column)}"


def _handed_to_the_core(
    frame: pl.DataFrame, *, refused_as: str | None = None
) -> tuple[pl.DataFrame, list[str]]:
    """Return ``frame`` as the core's encoder takes it, and its column names.

    Every column's type is named here, by the vocabulary, before the core
    is asked for a byte: the same call on the same type the reference
    encoder makes, so a refusal names the column and the cast in the words
    it always has, whichever encoder would have written. ``refused_as`` is
    the name the refusal reads out, which is the column's own everywhere
    except the injected stamp.

    The frame then crosses into the extension through the Arrow C
    interface (pyo3-polars 0.26, polars-arrow 0.53), which carries some
    things only as NUL-terminated strings and reads some layouts back
    wrongly. So each column crosses as what it stands for rather than as it
    is kept, and nothing the grammar reads moves:

    - **Its name** crosses beside the frame, as a Python string, and the
      column itself under its position -- ``"0"``, ``"1"``, and so on. A
      Polars name may hold a NUL, which the grammar hashes like any other
      character and a C string cannot carry: the export would stop with a
      panic, which no ``except Exception`` catches.
    - **A time zone** crosses with the column: the grammar writes it in the
      column's header (section 12.3), because a model reads the calendar in
      the column's zone and two books one zone apart compute two answers.
      It rides in the type's format string, a C string too, so a zone
      holding a NUL -- reachable only with Polars' own zone validation
      switched off -- is refused by name rather than cut short on the way.
    - **A fixed-width array** crosses as the list it holds, which is how the
      grammar carries it anyway. The importer takes an array's values
      already sliced and slices them again, so an array sliced where its
      window holds a null panics, and one of width zero with rows panics
      or, holding a null, is refused.
    - **A half-precision float** crosses widened, exactly, to a double: the
      core is not built to read one.
    """
    # The calculation graph reads SHA256_PREFIX out of this module, so
    # naming the type vocabulary at import time would close the loop.
    from gaspatchio._dtypes import (  # noqa: PLC0415 — import cycle
        neutral_dtype,
    )

    handed: list[pl.Series] = []
    for position, column in enumerate(frame.get_columns()):
        named = column.name if refused_as is None else refused_as
        # Refuses, naming the column, where the vocabulary has no name.
        _type_tag(neutral_dtype(_as_carried(column.dtype), column=named), named)
        _zone_of(column.dtype, named)
        crossing = _as_handed_over(column.dtype)
        kept = column if crossing == column.dtype else column.cast(crossing)
        handed.append(kept.alias(str(position)))
    return pl.DataFrame(handed), frame.columns


def _content_bytes_of_reference(frame: pl.DataFrame) -> bytes:
    """Return :func:`content_bytes_of`'s bytes, encoded in Python.

    The oracle the core's encoder is held byte-identical to by test, and the
    encoder this module used until the work moved into Rust; nothing in
    a run calls it. It refuses exactly what :func:`content_bytes_of`
    refuses, in the same words, because the refusal is the same call.
    """
    out = bytearray(_varint(frame.width))
    for name in frame.columns:
        out += _one_column(frame.get_column(name), name, refused_as=name)
    return bytes(out)


def _content_sha_of_reference(frame: pl.DataFrame) -> str:
    """Return :func:`content_sha_of`'s stamp over the Python reference's bytes."""
    encoded = _content_bytes_of_reference(frame)
    return f"{SHA256_PREFIX}{hashlib.sha256(encoded).hexdigest()}"


def _injected_content_sha_of_reference(values: pl.Series, column: str) -> str:
    """Return :func:`injected_content_sha_of`'s stamp over the reference's bytes."""
    encoded = _varint(1) + _one_column(values, values.name, refused_as=column)
    return f"{SHA256_PREFIX}{hashlib.sha256(encoded).hexdigest()}"


def _one_column(column: pl.Series, name: str, *, refused_as: str) -> bytes:
    """Return one column's name, its tag, its row count and its values.

    ``refused_as`` is the name a refusal reads out, which is the column's
    own name everywhere except the injected-column stamp: that one hashes
    under a placeholder, because the name of the series a simulation handed
    over is not part of what was injected.
    """
    return _text(name) + _column_bytes(column, refused_as)


def _column_bytes(column: pl.Series, name: str) -> bytes:
    """Return one column's type tag, its row count, and every value's bytes."""
    # The calculation graph reads SHA256_PREFIX out of this module, so
    # naming the type vocabulary at import time would close the loop.
    from gaspatchio._dtypes import (  # noqa: PLC0415 — import cycle
        neutral_dtype,
    )

    series = _without_fixed_width(column)
    neutral = neutral_dtype(series.dtype, column=name)
    return (
        _type_tag(neutral, name, zone=_zone_of(series.dtype, name))
        + _varint(series.len())
        + _value_block(series, neutral, name).data
    )


def _type_tag(neutral: str, column: str, *, zone: str = "") -> bytes:
    """Return the tag for a neutral type, or the run of them for a list.

    A list is the sequence tag followed by the tag of what it holds, so
    ``list[list[f64]]`` is three bytes and the nesting is read off the
    encoding rather than counted somewhere else. A timestamp's tag is
    followed by its zone as text, wherever it sits in the nesting.
    """
    if neutral.startswith(_LIST_OPEN) and neutral.endswith(_LIST_CLOSE):
        return _TAG_SEQUENCE + _type_tag(_element_name(neutral), column, zone=zone)
    tag = _SCALAR_TAGS.get(neutral)
    if tag is not None:
        return tag + _text(zone) if neutral == _DATETIME_NAME else tag
    raise _no_tag_for(neutral, column)


# The zone a naive timestamp is read in, and so the one a UTC column is
# written as: the two name one instant per value, and digest alike.
_UTC: Final[str] = "UTC"


def _zone_of(dtype: pl.DataType, column: str) -> str:
    """Return the zone a timestamp column is written under, empty for naive or UTC.

    Read off the innermost type, so a list of timestamps carries its zone as
    a column of them does. A zone holding a NUL is refused, naming the
    column: no zone database spells one, and the core reads a zone as a C
    string, which would cut it at the NUL and write another zone than this.
    """
    inner: PolarsDataType = dtype
    while isinstance(inner, pl.List | pl.Array):
        inner = inner.inner
    if not isinstance(inner, pl.Datetime) or inner.time_zone in (None, _UTC):
        return ""
    zone = str(inner.time_zone)
    if "\x00" in zone:
        msg = (
            f"Column {column!r} is a timestamp in the zone {zone!r}, which holds a "
            "NUL. A zone is part of what a timestamp column is identified by "
            "(section 12.3), and no zone database names one with a NUL in it. "
            "Convert the column to a zone it does name, or to UTC, before it "
            "is hashed."
        )
        raise ValueError(msg)
    return zone


def _no_tag_for(neutral: str, column: str) -> Exception:
    """Build the refusal for a type name this grammar has no tag for.

    Unreachable while the type vocabulary holds: it answers with one of the
    six scalar names or a list of them and refuses everything else before
    this is asked. Named rather than left to a ``KeyError``, because a
    content hash that quietly encoded an unexpected type as something else
    would be wrong in the one stamp whose whole value is being right.
    """
    from gaspatchio._dtypes import (  # noqa: PLC0415 — import cycle
        NEUTRAL_SCALAR_ORDER,
        UnmappedDtypeError,
    )

    names = ", ".join(NEUTRAL_SCALAR_ORDER)
    return UnmappedDtypeError(
        f"Column {column!r} has the type name {neutral!r}, which the content "
        f"grammar has no tag for. It can hash {names}, and list[...] of any "
        "of those."
    )


def _element_name(neutral: str) -> str:
    """Return the type a ``list[...]`` name holds."""
    return neutral[len(_LIST_OPEN) : -len(_LIST_CLOSE)]


def _value_block(series: pl.Series, neutral: str, column: str) -> _Block:
    """Return every value's bytes, in row order, under ``neutral``'s form."""
    if neutral.startswith(_LIST_OPEN):
        return _sequence_block(series, _element_name(neutral), column)
    if neutral == _DECIMAL_NAME:
        return _decimal_block(series)
    if neutral == _DATETIME_NAME:
        return _instant_block(series, column)
    if neutral in _WHOLE_NUMBER_NAMES:
        return _whole_number_block(_as_whole_number(series, neutral))
    if neutral == _TEXT_NAME:
        return _text_block(series)
    return _flag_block(series)


def _as_whole_number(series: pl.Series, neutral: str) -> pl.Series:
    """Return the whole number a count or a date travels as.

    A date is a count of days since 1970-01-01, which is what the type
    vocabulary says a consumer with no date type of its own carries it as. A
    timestamp never reaches here: ``_value_block`` sends it to
    ``_instant_block``, which keeps the nanoseconds past each microsecond.
    """
    if neutral == _DATE_NAME:
        return series.to_physical()
    return series


def _instant_block(series: pl.Series, column: str) -> _Block:
    """Encode a column of timestamps: microseconds, then the nanoseconds past them.

    Each present value is the marker, the zigzag varint of whole microseconds
    since 1970-01-01T00:00:00Z, and a varint of the nanoseconds past that
    microsecond, 0 to 999 -- so one instant kept in milliseconds,
    microseconds or nanoseconds has one encoding, and two instants a
    nanosecond apart have two. Nanoseconds are divided towards the earlier
    microsecond and the remainder kept; milliseconds scale up, and a count
    whose microseconds leave ``i64`` -- which Polars' own unit cast would
    wrap onto another instant -- is refused by name (section 12.3), as the core
    refuses it.

    Part of the oracle; it runs a row at a time.

    Raises:
        ValueError: A present millisecond count whose microseconds leave
            ``i64``, naming the column and the count.
    """
    rows = series.len()
    if rows == 0:
        return _EMPTY_BLOCK
    dtype = series.dtype
    unit = dtype.time_unit if isinstance(dtype, pl.Datetime) else "us"
    missing = series.is_null().to_numpy()
    counts = series.to_physical().fill_null(0).to_numpy().astype(np.int64)
    if unit == "ns":
        micros = np.floor_divide(counts, _NANOS_PER_MICRO)
        past = np.remainder(counts, _NANOS_PER_MICRO)
    elif unit == "ms":
        _refuse_instants_past_i64(counts, missing, column)
        micros = counts * np.int64(_MICROS_PER_MILLI)
        past = np.zeros(rows, dtype=np.int64)
    else:
        micros = counts
        past = np.zeros(rows, dtype=np.int64)
    out = bytearray()
    widths = np.zeros(rows, dtype=np.int64)
    for row in range(rows):
        if missing[row]:
            value = _MISSING
        else:
            whole = int(micros[row])
            zigzag = ((whole << 1) ^ (whole >> 63)) & _SIGN_BITS
            value = _PRESENT_MARK + _varint(zigzag) + _varint(int(past[row]))
        out += value
        widths[row] = len(value)
    return _Block(bytes(out), widths)


# The largest millisecond count whose microseconds an i64 holds; its negation
# is the smallest (-2**63 / 1000 is -9223372036854775.808, so one more
# millisecond below it leaves i64 too).
_MILLIS_IN_I64: Final[int] = (2**63 - 1) // _MICROS_PER_MILLI


def _refuse_instants_past_i64(
    counts: npt.NDArray[np.int64], missing: npt.NDArray[np.bool_], column: str
) -> None:
    """Refuse a present ms count whose microseconds leave ``i64``, naming the column.

    Raises:
        ValueError: The core's own words for the first such count.
    """
    past = ~missing & ((counts > _MILLIS_IN_I64) | (counts < -_MILLIS_IN_I64))
    for row in np.flatnonzero(past)[:1]:
        count = int(counts[row])
        msg = (
            f"Column '{column}' holds the timestamp {count} ms past 1970-01-01, "
            "whose count in microseconds leaves the 64-bit whole number section "
            "12.3 writes an instant as (it holds about 292,000 years either side "
            "of 1970). Two such instants would otherwise wrap onto one digest. No "
            "calendar a model reads reaches this far: check the column was read in "
            "the unit it was written in, or drop the value before it is hashed."
        )
        raise ValueError(msg)


def _decimal_block(series: pl.Series) -> _Block:
    """Encode a column of decimals as eight bytes each, most significant first."""
    rows = series.len()
    if rows == 0:
        return _EMPTY_BLOCK
    missing = series.is_null().to_numpy()
    values = series.cast(pl.Float64).fill_null(0.0).to_numpy().astype(np.float64)
    # Negative zero is written as zero -- the two are one number in every
    # arithmetic an actuary cares about -- and every NaN as the one quiet
    # payload, because two runs that both produced a NaN have not drifted.
    values[values == 0.0] = 0.0
    values[np.isnan(values)] = np.nan
    record = np.zeros((rows, 1 + _DECIMAL_WIDTH), dtype=np.uint8)
    record[:, 0] = _PRESENT
    record[:, 1:] = np.frombuffer(
        values.astype(">f8").tobytes(), dtype=np.uint8
    ).reshape(rows, _DECIMAL_WIDTH)
    return _packed(record, 1 + _DECIMAL_WIDTH, missing)


def _whole_number_block(series: pl.Series) -> _Block:
    """Encode a column of whole numbers as zigzag varints.

    Zigzag so that a small negative number -- a period offset, a pre-epoch
    date -- costs one byte rather than ten.
    """
    rows = series.len()
    if rows == 0:
        return _EMPTY_BLOCK
    missing = series.is_null().to_numpy()
    values = series.cast(pl.Int64).fill_null(0).to_numpy().astype(np.int64)
    zigzag = (values.view(np.uint64) << np.uint64(1)) ^ np.where(
        values < 0, np.uint64(_SIGN_BITS), np.uint64(0)
    )
    return _varint_record(zigzag, missing)


def _varint_record(
    values: npt.NDArray[np.uint64], missing: npt.NDArray[np.bool_]
) -> _Block:
    """Encode already-unsigned values as varints, one marked record per row.

    Built by array arithmetic, so that the oracle can be run over a column
    of a book's size in a test: every seven-bit group of every value is
    shifted out at once, the groups that carry are marked at once, and the
    rectangle is cut down to the length each value actually took.

    The two things a varint stands for here reach this by different
    routes -- a whole number is zigzagged first, a count of members is
    already unsigned -- and share the encoding from here on, so a count
    and a number of the same magnitude write the same bytes.
    """
    rows = values.shape[0]
    # Only as many groups as the column's largest value takes. A column of
    # ages or policy counts needs one and a book's sums assured three, so a
    # rectangle ten groups wide would be mostly work whose bytes are cut off.
    levels = _groups_for(int(values.max())) if rows else 1
    groups = ((values[:, None] >> _SHIFTS[:levels]) & np.uint64(_GROUP_MASK)).astype(
        np.uint8
    )
    used = np.ones(rows, dtype=np.int64)
    for level in range(1, levels):
        threshold = np.uint64(1) << np.uint64(_GROUP_BITS * level)
        used += (values >= threshold).astype(np.int64)
    record = np.zeros((rows, 1 + levels), dtype=np.uint8)
    record[:, 0] = _PRESENT
    record[:, 1:] = groups | np.where(
        (used[:, None] - 1) > _POSITIONS[:levels], np.uint8(_CONTINUES), np.uint8(0)
    )
    return _packed(record, 1 + used, missing)


def _groups_for(value: int) -> int:
    """Return how many seven-bit groups a varint of ``value`` takes."""
    return max(1, -(-value.bit_length() // _GROUP_BITS))


def _packed(
    record: npt.NDArray[np.uint8],
    lengths: npt.NDArray[np.int64] | int,
    missing: npt.NDArray[np.bool_],
) -> _Block:
    """Flatten one fixed-width record per row, each cut to the length it takes.

    A missing value is the marker and one placeholder byte; a present one is
    the marker and however many bytes its own form runs to. Cutting a
    rectangle down to those lengths is what keeps a whole column's bytes one
    array operation rather than a concatenation per row.
    """
    record[missing, 0] = _ABSENT
    record[missing, 1] = _NO_VALUE
    taken = np.where(missing, _MISSING_WIDTH, lengths)
    keep = np.arange(record.shape[1]) < taken[:, None]
    return _Block(record[keep].tobytes(), taken)


def _text_block(series: pl.Series) -> _Block:
    """Encode a column of text, each value as UTF-8 behind its byte length.

    Built by array arithmetic, as numbers and sequences are. Every row's
    marker and byte length is one :func:`_varint_record` over the lengths,
    every value's UTF-8 is one join, and the two are spliced together at the
    offsets the widths give. UTF-8 of a concatenation is the concatenation of
    the UTF-8, so the joined bytes are each value's bytes in row order.

    Part of the oracle, and built this way so that a test can run it over a
    book's worth of text: walking the column a value at a time is a Python
    encode per row. ``_text_block_reference`` is that walk, the grammar as
    section 12.3 reads it, and this is held byte-identical to it.
    """
    rows = series.len()
    if rows == 0:
        return _EMPTY_BLOCK
    missing = series.is_null().to_numpy()
    lengths = series.str.len_bytes().fill_null(0).to_numpy().astype(np.int64)
    headers = _varint_record(lengths.astype(np.uint64), missing)
    joined = series.str.join("", ignore_nulls=True).item() or ""
    widths = headers.widths + lengths
    starts = _boundaries(widths)[:-1]
    out = np.zeros(int(widths.sum()), dtype=np.uint8)
    out[_spread(starts, headers.widths)] = np.frombuffer(headers.data, dtype=np.uint8)
    out[_spread(starts + headers.widths, lengths)] = np.frombuffer(
        joined.encode("utf-8"), dtype=np.uint8
    )
    return _Block(out.tobytes(), widths)


def _text_block_reference(series: pl.Series) -> bytes:
    """Return a text column's bytes the way section 12.3 reads.

    Take each row, write its marker, then its value's UTF-8 behind the
    value's byte length. It is the definition :func:`_text_block` is derived
    from and is held equal to by test.
    """
    out = bytearray()
    for value in series:
        out += _MISSING if value is None else _PRESENT_MARK + _text(value)
    return bytes(out)


def _flag_block(series: pl.Series) -> _Block:
    """Encode a column of true/false flags, each a marker and one byte.

    One record per row, cut to length by :func:`_packed` as every fixed-width
    form is. A present flag and a missing one both take two bytes: the
    marker, then the flag or the placeholder.
    """
    rows = series.len()
    if rows == 0:
        return _EMPTY_BLOCK
    missing = series.is_null().to_numpy()
    record = np.zeros((rows, 2), dtype=np.uint8)
    record[:, 0] = _PRESENT
    record[:, 1] = series.fill_null(value=False).to_numpy().astype(np.uint8)
    return _packed(record, 2, missing)


def _flag_block_reference(series: pl.Series) -> bytes:
    """Return a flag column's bytes the way section 12.3 reads: row by row."""
    out = bytearray()
    for value in series:
        out += _MISSING if value is None else _PRESENT_MARK + bytes([int(value)])
    return bytes(out)


def _sequence_block(series: pl.Series, element: str, column: str) -> _Block:
    """Encode a column whose values are themselves runs of values.

    Every list column a projection produces has this shape -- one value per
    period, per policy -- so a run behind its own count is what lets a
    projected column be stamped at all. The members are encoded under the
    element's own tag and carry their own marker, since a period with no
    value and a period whose value is nought are two different projections.

    Part of the oracle. A projection-shaped column has many more members
    than rows -- a thousand policies over ten years of months is 120,000
    values in a thousand rows -- so the members of every row are encoded in
    **one** pass over the flattened column, and the per-row counts and
    markers are spliced back in at the byte offsets the members' own widths
    give. That is what lets a test hold the core to this at a projection's
    size. ``_sequence_block_reference`` takes each row in turn, the grammar
    as section 12.3 reads it, and this is held byte-identical to it.
    """
    rows = series.len()
    if rows == 0:
        return _EMPTY_BLOCK
    missing = series.is_null().to_numpy()
    counts = series.list.len().fill_null(0).to_numpy().astype(np.int64)
    # A row that is missing and a row holding no members both contribute no
    # members, and the marker in the header is what tells them apart.
    members = _value_block(
        series.explode(empty_as_null=False, keep_nulls=False), element, column
    )
    headers = _varint_record(counts.astype(np.uint64), missing)

    # Each row's members are a run in the flat block, so the bytes it takes
    # are the difference of the running total at its own two boundaries.
    boundaries = _boundaries(counts)
    running = _boundaries(members.widths)
    spans = running[boundaries[1:]] - running[boundaries[:-1]]

    widths = headers.widths + spans
    starts = _boundaries(widths)[:-1]
    out = np.zeros(int(widths.sum()), dtype=np.uint8)
    out[_spread(starts, headers.widths)] = np.frombuffer(headers.data, dtype=np.uint8)
    out[_spread(starts + headers.widths, spans)] = np.frombuffer(
        members.data, dtype=np.uint8
    )
    return _Block(out.tobytes(), widths)


def _spread(
    starts: npt.NDArray[np.int64], lengths: npt.NDArray[np.int64]
) -> npt.NDArray[np.int64]:
    """Return the concatenated ranges ``starts[i] .. starts[i] + lengths[i]``.

    Where a run of already-contiguous bytes has to land, run by run, at
    positions something else decides -- which is what splicing a header in
    front of every row's members comes to.
    """
    total = int(lengths.sum())
    if total == 0:
        return _NO_WIDTHS
    begins = _boundaries(lengths)[:-1]
    return np.repeat(starts - begins, lengths) + np.arange(total, dtype=np.int64)


def _boundaries(lengths: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
    """Return the running total before each run, and after the last of them."""
    return np.concatenate((_BEFORE_THE_FIRST, np.cumsum(lengths)))


def _sequence_block_reference(series: pl.Series, element: str, column: str) -> bytes:
    """Return a sequence column's bytes the way section 12.3 reads.

    Take each row, write its marker, write its count of members, write
    those members. It is the definition ``_sequence_block`` is derived
    from and is held equal to by test, and it is kept because a
    vectorisation whose only statement of intent is itself is a
    vectorisation nobody can check.
    """
    out = bytearray()
    for value in series:
        if value is None:
            out += _MISSING
            continue
        out += _PRESENT_MARK + _varint(value.len())
        out += _value_block(value, element, column).data
    return bytes(out)


def _without_fixed_width(column: pl.Series) -> pl.Series:
    """Return the column with any fixed-width array carried as a list.

    An array is the ``list[...]`` the type vocabulary already has with its
    length fixed, and a fixed length is storage rather than content. A
    simulation that hands back one path per policy lands as an array column,
    so refusing it here would refuse a shape the frame already accepts, for
    the sake of a name nothing is written under.
    """
    if not _holds_fixed_width(column.dtype):
        return column
    return column.cast(_as_list(column.dtype))


def _as_carried(dtype: pl.DataType) -> pl.DataType:
    """Return the type the vocabulary names a column by: any array as a list."""
    return _as_list(dtype) if _holds_fixed_width(dtype) else dtype


def _holds_fixed_width(dtype: pl.DataType) -> bool:
    """Return whether a fixed-width array sits anywhere inside ``dtype``."""
    base = dtype.base_type()
    if base is pl.Array:
        return True
    inner = getattr(dtype, "inner", None)
    return base is pl.List and inner is not None and _holds_fixed_width(inner)


def _as_list(dtype: pl.DataType) -> pl.DataType:
    """Return ``dtype`` with every fixed-width array rewritten as a list."""
    inner = getattr(dtype, "inner", None)
    if inner is None or dtype.base_type() not in {pl.Array, pl.List}:
        return dtype
    return pl.List(_as_list(inner))


def _as_handed_over(dtype: pl.DataType) -> pl.DataType:
    """Return the type a column crosses into the core as.

    Every fixed-width array as the list it holds and every half float as a
    ``Float64``. Neither moves a value the grammar reads: the widening is
    exact, and the grammar carries an array as its list whichever encoder
    writes it. A timestamp keeps its zone, which the grammar writes.
    """
    if dtype.base_type() is pl.Float16:
        return pl.Float64()
    inner = getattr(dtype, "inner", None)
    if inner is None or dtype.base_type() not in {pl.Array, pl.List}:
        return dtype
    return pl.List(_as_handed_over(inner))


__all__ = [
    "SHA256_PREFIX",
    "canonical_bytes",
    "content_bytes_of",
    "content_sha_of",
    "injected_content_sha_of",
    "source_sha_of",
]
