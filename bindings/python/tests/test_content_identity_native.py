# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The content grammar's encoder is the Rust core's, writing the reference's bytes.

Every result's manifest digests every cell of the book it ran over, so the
encoder reads every value of every run, which is why it moved into the core.
Where it runs moved; the bytes did not. The Python encoder it replaced stays in
``gaspatchio._identity`` as the reference, and the tests here hold the two
byte-identical across every type the grammar tags, nulls at every level of a
list, frames with no rows and no columns, sliced and chunked columns, and a
few hundred frames drawn at random under a fixed seed.

A stamp that moved when its encoder moved would tell every table, join,
injection and result written before the move that its data had changed. That
is the drift alarm nobody can trust again, so nothing here is allowed to move
a byte.
"""

from __future__ import annotations

import datetime
import decimal
import hashlib
import io
import threading
import time
from typing import TYPE_CHECKING, Final

import numpy as np
import polars as pl
import pyarrow as pa
import pytest
from pyarrow import feather

from gaspatchio import ActuarialFrame, _internal
from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio._identity import (
    SHA256_PREFIX,
    _content_bytes_of_reference,
    _content_sha_of_reference,
    _injected_content_sha_of_reference,
    content_bytes_of,
    content_sha_of,
    injected_content_sha_of,
)
from gaspatchio._semantic.ir import Call
from gaspatchio.engines.protocol import digest_of_inputs
from gaspatchio.frame.calculations import CalculationRecord
from gaspatchio.frame.graph.validate import _payload_digest
from gaspatchio.scenarios._audit import model_points_fingerprint

if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy.typing as npt

# The seed every randomised frame here is drawn under, so a failure names a
# frame anybody can draw again.
SEED: Final[int] = 20260924


def _assert_native_is_reference(frame: pl.DataFrame) -> None:
    """Hold the core's bytes and digest to the Python reference's, for one frame."""
    reference = _content_bytes_of_reference(frame)

    assert content_bytes_of(frame) == reference
    assert content_sha_of(frame) == _content_sha_of_reference(frame)
    assert content_sha_of(frame) == (
        f"{SHA256_PREFIX}{hashlib.sha256(reference).hexdigest()}"
    )


def _floats_from_bits(
    patterns: list[int], width: type[np.unsignedinteger], float_type: type[np.floating]
) -> npt.NDArray[np.floating]:
    """Return floats with exactly these bit patterns, payloads and signs kept."""
    return np.array(patterns, dtype=width).view(float_type)


# --- every type the vocabulary names ------------------------------------------

_I64_MIN: Final[int] = -(2**63)
_I64_MAX: Final[int] = 2**63 - 1

_DOUBLE_BITS: Final[list[int]] = [
    0x7FF8000000000000,  # the quiet NaN
    0xFFF8000000000000,  # the same, sign bit set
    0x7FF8DEADBEEF0000,  # a quiet NaN carrying a payload
    0x7FF0000000000001,  # a signalling NaN
    0x8000000000000000,  # negative zero
    0x0000000000000000,  # zero
    0x7FF0000000000000,  # infinity
    0xFFF0000000000000,  # negative infinity
    0x0000000000000001,  # the smallest subnormal
    0x800FFFFFFFFFFFFF,  # the largest negative subnormal
    0x7FEFFFFFFFFFFFFF,  # the largest finite
    0x3FB999999999999A,  # 0.1
]

_SINGLE_BITS: Final[list[int]] = [
    0x7FC00000,  # the quiet NaN
    0xFFC00000,  # the same, sign bit set
    0x7FC0DEAD,  # a quiet NaN carrying a payload
    0x7F800001,  # a signalling NaN
    0x80000000,  # negative zero
    0x7F800000,  # infinity
    0xFF800000,  # negative infinity
    0x00000001,  # the smallest subnormal
    0x7F7FFFFF,  # the largest finite
    0x3DCCCCCD,  # 0.1, as a single
]

_STRINGS: Final[list[str | None]] = [
    "",
    "\x00",
    "a",
    "ß",
    "中",
    "𝄞",
    "😀",
    None,
    "a" * 127,
    "a" * 128,
    "é" * 8_191 + "a",  # 16,383 bytes: the last length a two-byte varint holds
    "é" * 8_192,  # 16,384 bytes: the first that needs three
    "中" * 5,
    "TERM",
]


def _instants(name: str, dtype: pl.Datetime) -> pl.Series:
    """Return a timestamp column whose stored counts sit on every rounding edge.

    A nanosecond count either side of a whole microsecond, a millisecond
    count at the edge of what scaling to microseconds keeps inside i64, and
    both ends of the sixty-four-bit range. A millisecond column holds only
    the counts whose microseconds an i64 holds: one past them is refused by
    name rather than wrapped (section 12.3), which
    ``test_a_millisecond_count_past_i64_is_refused_alike`` holds.
    """
    counts = [
        -1,
        -999,
        -1_000,
        -1_001,
        1,
        999,
        1_000,
        1_001,
        2**62,
        -(2**62),
        9_223_372_036_854_775,
        9_223_372_036_854_776,
        -9_223_372_036_854_776,
        -9_223_372_036_854_777,
        _I64_MAX,
        _I64_MIN,
        None,
        0,
    ]
    if dtype.time_unit == "ms":
        counts = [c for c in counts if c is None or abs(c) <= _MILLIS_IN_I64]
    return pl.Series(name, counts, dtype=pl.Int64).cast(dtype)


# The largest millisecond count whose microseconds an i64 holds, either side.
_MILLIS_IN_I64: Final = (2**63 - 1) // 1_000


_EVERY_TYPE: Final[list[pl.Series]] = [
    pl.Series("int8", [-128, -1, 0, 1, 63, 64, 127, None], dtype=pl.Int8),
    pl.Series("int16", [-32_768, -129, -65, 128, 32_767, None], dtype=pl.Int16),
    pl.Series("int32", [-(2**31), 2**31 - 1, None, 0, -64], dtype=pl.Int32),
    pl.Series(
        "int64",
        [_I64_MIN, _I64_MAX, -1, 0, 1, None, 12_345_678_901, 2**56, 2**56 - 1],
        dtype=pl.Int64,
    ),
    pl.Series("uint8", [0, 1, 127, 128, 255, None], dtype=pl.UInt8),
    pl.Series("uint16", [0, 65_535, 16_383, 16_384, None], dtype=pl.UInt16),
    pl.Series("uint32", [0, 2**32 - 1, 2**31, None], dtype=pl.UInt32),
    pl.Series(
        "float16",
        [1.5, None, -0.0, float("nan"), 65_504.0, 6e-8, float("inf"), -2.0],
        dtype=pl.Float16,
    ),
    pl.Series("float32", _floats_from_bits(_SINGLE_BITS, np.uint32, np.float32)),
    pl.Series("float64", _floats_from_bits(_DOUBLE_BITS, np.uint64, np.float64)),
    pl.Series("float64_nulls", [None, 1.0, None, -0.0], dtype=pl.Float64),
    pl.Series("flags", [True, False, None, True]),
    pl.Series("text", _STRINGS, dtype=pl.String),
    pl.Series(
        "dates",
        [
            datetime.date(1970, 1, 1),
            datetime.date(1970, 1, 2),
            datetime.date(1969, 12, 31),
            datetime.date(1, 1, 1),
            datetime.date(9999, 12, 31),
            None,
        ],
    ),
    pl.Series("date_extremes", [-(2**31), 2**31 - 1, None], dtype=pl.Int32).cast(
        pl.Date
    ),
    _instants("nanoseconds", pl.Datetime("ns")),
    _instants("microseconds", pl.Datetime("us")),
    _instants("milliseconds", pl.Datetime("ms")),
    _instants("nanoseconds_utc", pl.Datetime("ns", "UTC")),
    _instants("microseconds_kolkata", pl.Datetime("us", "Asia/Kolkata")),
    _instants("milliseconds_new_york", pl.Datetime("ms", "America/New_York")),
]


@pytest.mark.parametrize("column", _EVERY_TYPE, ids=lambda column: str(column.name))
def test_every_type_the_grammar_tags_writes_the_reference_s_bytes(
    column: pl.Series,
) -> None:
    """One column of each type, extremes and edges included, both ways round.

    Integers at every width and each width's extremes; floats at every width
    with every NaN payload, both zeros, both infinities and subnormals; text
    from the empty string to lengths either side of each varint boundary,
    with NUL and one- to four-byte characters; dates either side of the epoch
    and at the ends of their range; timestamps in all three units, with and
    without a time zone, at every rounding edge a unit change meets.
    """
    _assert_native_is_reference(column.to_frame())


def test_the_top_of_the_unsigned_64_bit_range_is_refused_as_the_reference_refuses() -> (
    None
):
    """``UInt64`` is refused by width, whatever it holds, with the same message.

    The content grammar is never handed a column's values to judge a wide
    integer by, so the vocabulary refuses the width itself: a column that can
    hold numbers no ``i64`` carries is not named ``i64`` unmeasured. The
    largest ``UInt32`` is an ordinary whole number, and is in the table above.
    """
    for values in ([7], [2**63 - 1], [2**63], [2**64 - 1]):
        frame = pl.Series("policy_id", values, dtype=pl.UInt64).to_frame()
        with pytest.raises(UnmappedDtypeError) as native:
            content_bytes_of(frame)
        with pytest.raises(UnmappedDtypeError) as reference:
            _content_bytes_of_reference(frame)

        assert str(native.value) == str(reference.value)


# --- sequences, and a missing value at every level -----------------------------

_SEQUENCES: Final[list[pl.Series]] = [
    pl.Series("floats", [[1.0, None], [], None, [-0.0, float("nan")]]),
    pl.Series("whole", [[1, -2], None, [], [63, 64, -65]], dtype=pl.List(pl.Int64)),
    pl.Series("narrow", [[1, -2], None, [127]], dtype=pl.List(pl.Int8)),
    pl.Series(
        "text", [["a", None], [], None, ["", "ß" * 100]], dtype=pl.List(pl.String)
    ),
    pl.Series("flags", [[True, None], [], None, [False]], dtype=pl.List(pl.Boolean)),
    pl.Series(
        "dates",
        [[datetime.date(1969, 12, 31), None], None, []],
        dtype=pl.List(pl.Date),
    ),
    pl.Series("instants", [[-1_001, None, 1], None], dtype=pl.List(pl.Int64)).cast(
        pl.List(pl.Datetime("ns"))
    ),
    pl.Series("halves", [[1.5, None], None, [-0.0]], dtype=pl.List(pl.Float16)),
    pl.Series(
        "two_deep",
        [[[1.0, None], []], None, [], [[]], [None, [2.0]]],
        dtype=pl.List(pl.List(pl.Float64)),
    ),
    pl.Series(
        "three_deep",
        [[[[1, None], None, []], None, [[None]]], None, [], [[]], [[[]]]],
        dtype=pl.List(pl.List(pl.List(pl.Int64))),
    ),
    pl.Series("all_missing", [None, None], dtype=pl.List(pl.Float64)),
    pl.Series("no_rows", [], dtype=pl.List(pl.List(pl.String))),
    pl.Series(
        "fixed_width", [[1.0, 2.0], [3.0, None], None], dtype=pl.Array(pl.Float64, 2)
    ),
    pl.Series("zero_width", [[], None, []], dtype=pl.List(pl.Int64)).cast(
        pl.Array(pl.Int64, 0)
    ),
    pl.Series(
        "arrays_in_a_list", [[[1, 2], None], None, []], dtype=pl.List(pl.List(pl.Int32))
    ).cast(pl.List(pl.Array(pl.Int32, 2))),
    pl.Series(
        "lists_in_an_array",
        [[[1.0], []], None, [None, [2.0, None]]],
        dtype=pl.List(pl.List(pl.Float64)),
    ).cast(pl.Array(pl.List(pl.Float64), 2)),
    pl.Series(
        "arrays_of_arrays",
        [[[1, 2], [3, None]], None, [None, [5, 6]]],
        dtype=pl.List(pl.List(pl.Int16)),
    ).cast(pl.Array(pl.Array(pl.Int16, 2), 2)),
    pl.Series("text_arrays", [["a", None, ""], None], dtype=pl.List(pl.String)).cast(
        pl.Array(pl.String, 3)
    ),
]


@pytest.mark.parametrize("column", _SEQUENCES, ids=lambda column: str(column.name))
def test_every_sequence_writes_the_reference_s_bytes(column: pl.Series) -> None:
    """Lists, lists of lists, and fixed-width arrays, with nulls at every level.

    Each row is its marker and its count, then its members under the
    element's own form, each with a marker of its own. A missing row, an
    empty one and one holding a missing member are three different things,
    and an array is the list it holds whatever width it was stored at.
    """
    _assert_native_is_reference(column.to_frame())


# --- frames, chunks and slices ---------------------------------------------------


def test_a_frame_with_no_columns_or_no_rows_writes_the_reference_s_bytes() -> None:
    """The counts are the whole of the encoding, and they must agree too."""
    _assert_native_is_reference(pl.DataFrame())
    _assert_native_is_reference(
        pl.DataFrame(
            schema={
                "a": pl.Int64,
                "b": pl.List(pl.String),
                "c": pl.Datetime("ns"),
                "d": pl.Array(pl.Float32, 3),
            }
        )
    )


@pytest.mark.parametrize(
    "dtype",
    [
        pl.Boolean,
        pl.Int8,
        pl.UInt32,
        pl.Int64,
        pl.Float16,
        pl.Float32,
        pl.Float64,
        pl.String,
        pl.Date,
        pl.Datetime("ms"),
        pl.List(pl.Int64),
        pl.Array(pl.String, 2),
    ],
    ids=str,
)
def test_an_all_missing_column_writes_the_reference_s_bytes(
    dtype: pl.DataType,
) -> None:
    """A column nobody supplied a value for is its markers, row by row."""
    _assert_native_is_reference(pl.Series("v", [None] * 3, dtype=dtype).to_frame())


def _chunked(*pieces: pl.Series) -> pl.Series:
    """Return the pieces end to end, left as separate chunks."""
    joined = pl.concat(pieces, rechunk=False)
    assert joined.n_chunks() == len(pieces)
    return joined


def test_sliced_and_chunked_columns_write_the_reference_s_bytes() -> None:
    """A column is its rows, however many chunks it came in and wherever it starts.

    A book loaded in batches arrives in chunks, and a column cut from a
    larger one keeps the larger one's buffers. Neither is content.
    """
    rng = np.random.default_rng(SEED)
    text = pl.Series(
        "text",
        [
            None if rng.random() < 0.2 else "x" * int(rng.integers(0, 200))
            for _ in range(400)
        ],
    )
    numbers = pl.Series("numbers", rng.integers(-(2**40), 2**40, size=400))
    rates = pl.Series("rates", rng.normal(size=400)).set(
        pl.Series(rng.random(400) < 0.1), None
    )
    paths = pl.Series(
        "paths", rng.normal(size=(400, 6)).tolist(), dtype=pl.List(pl.Float64)
    )
    # A fixed-width array whose window holds a null keeps its validity's
    # offset, and polars-arrow 0.53's importer slices the values the exporter
    # already sliced -- a panic, had the door not handed each array over as
    # the list it holds. Every window below holds one of these nulls.
    rows_of_six: list[list[float] | None] = rng.normal(size=(400, 6)).tolist()
    for missing in (40, 95, 150, 305):
        rows_of_six[missing] = None
    fixed = pl.Series("fixed", rows_of_six, dtype=pl.List(pl.Float64)).cast(
        pl.Array(pl.Float64, 6)
    )
    columns = [text, numbers, rates, paths, fixed]

    for column in columns:
        _assert_native_is_reference(column[37:311].to_frame())
        _assert_native_is_reference(
            _chunked(column[:90], column[90:91], column[91:400]).to_frame()
        )
        _assert_native_is_reference(_chunked(column[10:50], column[300:333]).to_frame())

    frame = pl.DataFrame(columns)
    _assert_native_is_reference(frame.slice(123, 77))
    _assert_native_is_reference(
        pl.concat([frame.slice(0, 5), frame.slice(200, 150)], rechunk=False)
    )


def test_a_frame_wider_than_the_digest_s_stage_digests_as_its_bytes() -> None:
    """The digest streams through a stage; where the stage breaks moves nothing.

    Two hundred thousand rows are a few megabytes of encoded content, so the
    stage fills and flushes many times over, and one text is a megabyte on
    its own -- wider than the stage, so it is handed to the hasher whole.
    """
    rows = 200_000
    frame = pl.DataFrame(
        {
            "point_id": pl.int_range(1, rows + 1, eager=True),
            "sex": pl.Series(["M", "F", None, "F"] * (rows // 4)),
            "sum_assured": pl.Series(np.arange(rows, dtype=np.float64) * 12.5),
        }
    )
    _assert_native_is_reference(frame)
    _assert_native_is_reference(pl.Series("wide", ["a" * 2**20, "b", None]).to_frame())


# --- frames drawn at random --------------------------------------------------------

# The leaf types a random column draws from. Dates and timestamps are drawn as
# the counts they are stored as and cast afterwards, so their ranges are the
# storage's rather than Python's calendar's.
_LEAVES: Final[list[pl.DataType]] = [
    pl.Int8(),
    pl.Int16(),
    pl.Int32(),
    pl.Int64(),
    pl.UInt8(),
    pl.UInt16(),
    pl.UInt32(),
    pl.Float16(),
    pl.Float32(),
    pl.Float64(),
    pl.Boolean(),
    pl.String(),
    pl.Date(),
    pl.Datetime("ns"),
    pl.Datetime("us"),
    pl.Datetime("ms"),
    pl.Datetime("us", "UTC"),
]

_RANGES: Final[dict[type[pl.DataType], tuple[int, int]]] = {
    pl.Int8: (-(2**7), 2**7 - 1),
    pl.Int16: (-(2**15), 2**15 - 1),
    pl.Int32: (-(2**31), 2**31 - 1),
    pl.Int64: (_I64_MIN, _I64_MAX),
    pl.UInt8: (0, 2**8 - 1),
    pl.UInt16: (0, 2**16 - 1),
    pl.UInt32: (0, 2**32 - 1),
    pl.Date: (-(2**31), 2**31 - 1),
    pl.Datetime: (_I64_MIN, _I64_MAX),
}

_SPECIAL_FLOATS: Final[list[float]] = [
    0.0,
    -0.0,
    float("nan"),
    float("inf"),
    -float("inf"),
    5e-324,
]
_ALPHABET: Final[list[str]] = ["a", "Z", " ", "\x00", "ß", "é", "中", "𝄞", "😀"]


def _physical(leaf: pl.DataType) -> pl.DataType:
    """Return the type a leaf's random values are drawn as."""
    if leaf.base_type() is pl.Date:
        return pl.Int32()
    if leaf.base_type() is pl.Datetime:
        return pl.Int64()
    return leaf


def _one_whole(low: int, high: int, rng: np.random.Generator) -> int:
    """Return a whole number in range: an edge, a small one, or anything at all."""
    if rng.random() < 0.2:
        return int(rng.choice([low, high, 0, -1 if low < 0 else 1]))
    span = high if rng.random() < 0.3 else min(high, 2**20)
    return int(rng.integers(max(low, -span), span, endpoint=True))


def _one_decimal(base: type[pl.DataType], rng: np.random.Generator) -> float:
    """Return a float: a special value now and then, else one of some magnitude."""
    if rng.random() < 0.2:
        return float(rng.choice(_SPECIAL_FLOATS))
    scale = 1.0 if base is pl.Float16 else 10.0 ** int(rng.integers(-5, 8))
    return float(rng.normal() * scale)


def _one_leaf(leaf: pl.DataType, rng: np.random.Generator) -> object:
    """Return one random value for a leaf, or ``None`` about one time in eight."""
    if rng.random() < 0.125:
        return None
    base = leaf.base_type()
    if isinstance(leaf, pl.Datetime) and leaf.time_unit == "ms":
        return _one_whole(-_MILLIS_IN_I64, _MILLIS_IN_I64, rng)
    if base in _RANGES:
        return _one_whole(*_RANGES[base], rng)
    if leaf.is_float():
        return _one_decimal(base, rng)
    if base is pl.Boolean:
        return bool(rng.random() < 0.5)
    length = int(rng.choice([0, 1, 5, 12, 13, 40, 127, 128]))
    return "".join(rng.choice(_ALPHABET, size=length))


def _one_value(
    shape: list[int | None], leaf: pl.DataType, rng: np.random.Generator
) -> object:
    """Return one value of a nesting: ``None`` is a list, a number an array's width."""
    if not shape:
        return _one_leaf(leaf, rng)
    if rng.random() < 0.1:
        return None
    width = shape[0]
    count = int(rng.integers(0, 5)) if width is None else width
    return [_one_value(shape[1:], leaf, rng) for _ in range(count)]


def _nested(
    shape: list[int | None], leaf: pl.DataType, *, as_lists: bool
) -> pl.DataType:
    """Return the type of a nesting, with every array a list if ``as_lists``."""
    dtype = leaf
    for width in reversed(shape):
        dtype = pl.List(dtype) if width is None or as_lists else pl.Array(dtype, width)
    return dtype


def _random_column(name: str, rows: int, rng: np.random.Generator) -> pl.Series:
    """Return a column of a random type, nested up to three deep, with random nulls."""
    leaf = _LEAVES[int(rng.integers(len(_LEAVES)))]
    depth = int(rng.choice([0, 0, 1, 1, 2, 3]))
    shape: list[int | None] = [
        None if rng.random() < 0.6 else int(rng.integers(0, 4)) for _ in range(depth)
    ]
    values = [_one_value(shape, leaf, rng) for _ in range(rows)]
    drawn = pl.Series(
        name, values, dtype=_nested(shape, _physical(leaf), as_lists=True)
    )
    return drawn.cast(_nested(shape, leaf, as_lists=False))


def _random_frame(rng: np.random.Generator) -> pl.DataFrame:
    """Return a frame of random columns, sometimes sliced or left in chunks."""
    rows = int(rng.choice([0, 1, 2, 7, 33, 64]))
    frame = pl.DataFrame(
        [
            _random_column(f"c{index}", rows, rng)
            for index in range(int(rng.integers(1, 6)))
        ]
    )
    if rows > 2 and rng.random() < 0.3:
        frame = frame.slice(1, rows - 2)
    if rows > 2 and rng.random() < 0.3:
        frame = pl.concat([frame.slice(0, 1), frame.slice(1)], rechunk=False)
    return frame


@pytest.mark.parametrize(
    "dtype",
    [pl.Datetime("ms"), pl.Datetime("ms", "America/New_York")],
    ids=str,
)
@pytest.mark.parametrize(
    "count",
    [_MILLIS_IN_I64 + 1, -_MILLIS_IN_I64 - 1, 2**62, _I64_MAX, _I64_MIN],
)
def test_a_millisecond_count_past_i64_is_refused_alike(
    dtype: pl.Datetime, count: int
) -> None:
    """Both encoders refuse, in the same words, a ms count past i64 in microseconds.

    Scaling it would wrap onto another instant's microseconds and share its
    digest. Needs the core built with that refusal (core/src/identity.rs).
    """
    frame = pl.DataFrame(
        {"when": pl.Series([0, None, count], dtype=pl.Int64).cast(dtype)}
    )

    said = "leaves the 64-bit whole number"
    with pytest.raises(ValueError, match=said):
        _content_bytes_of_reference(frame)
    for door in (content_bytes_of, content_sha_of):
        with pytest.raises(ValueError, match=said) as native:
            door(frame)
        assert f"Column 'when' holds the timestamp {count} ms" in str(native.value)


def test_frames_drawn_at_random_write_the_reference_s_bytes() -> None:
    """Three hundred frames of random types, shapes, nulls, slices and chunks.

    The tables above are the edges somebody thought of. These are the
    combinations nobody listed: an array of dates inside a list, a sliced
    frame of half floats, a timestamp column left in two chunks.
    """
    rng = np.random.default_rng(SEED)
    for draw in range(300):
        frame = _random_frame(rng)
        try:
            _assert_native_is_reference(frame)
        except AssertionError as failure:
            message = f"draw {draw} under seed {SEED}: {frame.schema}"
            raise AssertionError(message) from failure


# --- the injected stamp ------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        pl.Series("injected", [0.01, -0.02, 0.03]),
        pl.Series("simulated", [[0.1, None], None], dtype=pl.List(pl.Float64)),
        pl.Series("scenario", ["base", "up", "down"]),
        pl.Series("", [1, 2, 3], dtype=pl.Int32),
    ],
    ids=lambda values: repr(values.name),
)
def test_the_injected_stamp_is_the_reference_s(values: pl.Series) -> None:
    """An injection's stamp, under whatever name its values arrived with."""
    assert injected_content_sha_of(values, "shock") == (
        _injected_content_sha_of_reference(values, "shock")
    )


def test_the_section_12_1_injected_worked_example_reproduces() -> None:
    """The stamp section 12.1 prints for ``simulated_shock@1``."""
    shock = pl.Series("injected", [0.01, -0.02, 0.03])

    assert injected_content_sha_of(shock, "simulated_shock") == (
        "sha256:6103a3a7d560f2d5efc89e7822a8520aeda0062eaf4a44ba9632d872d819ed23"
    )


# --- refusals ----------------------------------------------------------------------

_REFUSED: Final[list[pl.Series]] = [
    pl.Series("u64", [1], dtype=pl.UInt64),
    pl.Series("i128", [1], dtype=pl.Int128),
    pl.Series("u128", [1], dtype=pl.UInt128),
    pl.Series("decimal", [decimal.Decimal("1.5")], dtype=pl.Decimal(10, 2)),
    pl.Series("category", ["a"], dtype=pl.Categorical),
    pl.Series("enumerated", ["a"], dtype=pl.Enum(["a", "b"])),
    pl.Series("nothing", [None, None]),
    pl.Series("clock", [datetime.time(1, 2)]),
    pl.Series("gap", [datetime.timedelta(days=1)]),
    pl.Series("raw", [b"x"]),
    pl.Series("record", [{"a": 1}]),
    pl.Series("four_deep", [[[[[1.0]]]]]),
    pl.Series("array_of_nothing", [[None, None]], dtype=pl.Array(pl.Null, 2)),
    pl.Series("list_of_u64", [[1]], dtype=pl.List(pl.UInt64)),
]


def _refusal(call: Callable[[], object]) -> str:
    """Return what ``call`` refused with, as the message a reader sees."""
    with pytest.raises(UnmappedDtypeError) as refused:
        call()
    return str(refused.value)


@pytest.mark.parametrize("column", _REFUSED, ids=lambda column: str(column.name))
def test_a_type_with_no_tag_is_refused_in_the_reference_s_words(
    column: pl.Series,
) -> None:
    """The same refusal, word for word, from every door.

    The vocabulary names types in Python, before the core is asked for a
    byte, so the message still names the column and the cast that would
    carry it. A column the grammar can hash, ahead of the refused one, does
    not change which column is named.
    """
    frame = pl.DataFrame([pl.Series("fine", [1] * column.len()), column])

    assert _refusal(lambda: content_bytes_of(frame)) == _refusal(
        lambda: _content_bytes_of_reference(frame)
    )
    assert _refusal(lambda: content_sha_of(frame)) == _refusal(
        lambda: _content_sha_of_reference(frame)
    )
    assert _refusal(lambda: injected_content_sha_of(column, "shock")) == _refusal(
        lambda: _injected_content_sha_of_reference(column, "shock")
    )


@pytest.mark.parametrize(
    "column",
    [
        pl.Series("u64", [1], dtype=pl.UInt64),
        pl.Series("record", [{"a": 1}]),
        pl.Series("gap", [datetime.timedelta(days=1)]),
        pl.Series("four_deep", [[[[[1.0]]]]]),
        pl.Series("category", ["a"], dtype=pl.Categorical),
    ],
    ids=lambda column: str(column.name),
)
def test_the_core_refuses_a_type_with_no_tag_rather_than_writing_bytes(
    column: pl.Series,
) -> None:
    """Handed a column by some route that skipped the vocabulary, the core stops.

    Unreachable through ``gaspatchio._identity``, which refuses first. Held
    because a content hash that quietly wrote an unexpected type as something
    else would be wrong in the one stamp whose whole value is being right.
    """
    frame = column.to_frame()
    for encode in (_internal.content_bytes, _internal.content_sha256):
        with pytest.raises(ValueError, match=f"Column '{column.name}' has type"):
            encode(frame, frame.columns)


# --- the GIL -------------------------------------------------------------------------


def test_the_digest_lets_other_python_threads_run() -> None:
    """A digest of a large book holds up no other Python thread while it encodes.

    The encoding runs with the GIL released. A thread that held it would
    freeze every other Python thread for the whole of the encode, which
    shows as one long gap between the ticks another thread takes
    meanwhile; released, the ticks keep coming. Only the last tick and the
    longest gap are kept, because a debug build's encode is seconds long.
    The frame is sized so the encode is long enough for the difference to
    be unmistakable, and the bound is loose.
    """
    rows = 4_000_000
    frame = pl.DataFrame(
        {
            "point_id": pl.int_range(0, rows, eager=True),
            "sex": pl.Series(["M", "F", "F", "M"] * (rows // 4)),
            "rate": pl.Series(np.linspace(0.0, 1.0, rows)),
        }
    )
    window: list[float] = []

    def digest() -> None:
        started = time.perf_counter()
        _internal.content_sha256(frame, frame.columns)
        window.extend([started, time.perf_counter()])

    worker = threading.Thread(target=digest)
    worker.start()
    last = time.perf_counter()
    longest_gap = 0.0
    while worker.is_alive():
        tick = time.perf_counter()
        longest_gap = max(longest_gap, tick - last)
        last = tick
    worker.join()

    started, finished = window
    assert finished - started > 0.02, "the encode was too quick to tell anything"
    assert longest_gap < 0.5 * (finished - started)


def test_the_core_refuses_names_that_are_not_one_per_column() -> None:
    """The names cross beside the frame, so the core checks they match it."""
    frame = pl.DataFrame({"0": [1], "1": [2.0]})
    for encode in (_internal.content_bytes, _internal.content_sha256):
        with pytest.raises(ValueError, match="handed 1 column names for a frame of 2"):
            encode(frame, ["age"])


def test_the_core_names_a_refused_column_s_whole_type() -> None:
    """A list four deep is refused as the list the column is, not its element."""
    frame = pl.Series("0", [[[[[1.0]]]]]).to_frame()
    with pytest.raises(
        ValueError, match=r"Column 'deep' has type list\[list\[list\[list\[f64\]\]\]\],"
    ):
        _internal.content_sha256(frame, ["deep"])


# --- what the Arrow C interface carries as a C string ----------------------------

# A NUL at the start of a name, inside it, at its end, and as the whole of it.
_NUL_NAMES: Final[list[str]] = ["\x00rate", "rate\x00note", "rate\x00", "\x00"]


@pytest.mark.parametrize("name", _NUL_NAMES, ids=ascii)
def test_a_name_holding_a_nul_is_hashed_as_the_reference_hashes_it(name: str) -> None:
    """A Polars name may hold a NUL, and the grammar writes it like any other.

    The Arrow C interface the frame crosses into the core carries a column
    name as a NUL-terminated string, and exporting one holding a NUL stops
    with a panic that no ``except Exception`` catches. So the names cross
    beside the frame, as Python strings, and the frame under placeholders.
    """
    frame = pl.DataFrame({name: [0.001, 0.0012], "age": [45, 46]})
    values = pl.Series(name, [0.01, -0.02])

    _assert_native_is_reference(frame)
    assert injected_content_sha_of(values, "shock") == (
        _injected_content_sha_of_reference(values, "shock")
    )


def test_many_columns_named_with_nuls_hash_as_the_reference_hashes_them() -> None:
    """Fifty columns, every name holding a NUL, and names the placeholders use."""
    frame = pl.DataFrame(
        {f"{index}\x00{'x' * index}": [index, None] for index in range(50)}
        | {"1": ["a", None], "0": [True, None]}
    )

    _assert_native_is_reference(frame)


def test_a_join_s_right_side_is_stamped_whatever_its_column_names() -> None:
    """The join's fingerprint over a right side with a NUL in a column name.

    Describing the right side must never break the join, and the guard
    around it catches ``Exception``; a panic would have gone straight past.
    """
    right = pl.DataFrame(
        {"product_code": ["TERM", "WL"], "expense\x00note": [0.05, 0.08]}
    )
    book = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2, 3], "product_code": ["TERM", "TERM", "WL"]})
    )

    joined = book.join(right, on="product_code")

    records = [
        entry
        for entry in joined._calculations  # noqa: SLF001 -- the log under test
        if isinstance(entry, CalculationRecord) and entry.column == "expense\x00note"
    ]
    assert isinstance(records[-1].node, Call)
    assert dict(records[-1].node.attrs)["right_fingerprint"] == (
        _content_sha_of_reference(
            right.select(sorted(right.columns)).sort(sorted(right.columns))
        )
    )


def test_the_validator_re_derives_a_payload_digest_under_a_nul_name() -> None:
    """An artifact's inline table is untrusted input, and its names may hold NULs.

    The validator re-derives each payload's digest to check the one beside
    it; a name it cannot hand over must not crash the validator.
    """
    payload = {
        "columns": [
            {"name": "rate\u0000", "dtype": "f64"},
            {"name": "age", "dtype": "i64"},
        ],
        "rows": [[0.001, 45], [0.0012, 46]],
    }

    digest, unreadable = _payload_digest("table", payload)

    assert unreadable is None
    assert digest == _content_sha_of_reference(
        pl.DataFrame({"rate\x00": [0.001, 0.0012], "age": [45, 46]})
    )


def test_the_model_point_stamp_takes_a_nul_name() -> None:
    """The stamp an audit record carries for the book a run read."""
    book = pl.DataFrame({"point_id": [1, 2], "age\x00at_entry": [40, 41]})

    assert model_points_fingerprint(book) == {
        "model_points": _content_sha_of_reference(book)
    }


def test_the_inputs_digest_takes_a_nul_name() -> None:
    """The digest a result's manifest carries, over the columns it read."""
    book = pl.DataFrame(
        {"point_id": [1, 2], "sum\x00assured": [1e5, 2e5], "unread": [0, 0]}
    )

    assert digest_of_inputs(book, ["sum\x00assured", "point_id"]) == (
        _content_sha_of_reference(book.select("point_id", "sum\x00assured"))
    )


def test_a_zone_holding_a_nul_is_refused_on_the_way_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The zone rides in the type's format string, another C string.

    Polars validates a zone wherever it builds a type, and a zone arriving
    through the Arrow C interface stops at its first NUL. With Polars' own
    validation switched off, an IPC file -- or a pickled series, which is
    one -- can still carry a zone holding a NUL. The grammar writes the zone
    in the column's header, so a zone the core would read cut short is
    refused by name by both encoders rather than written as another zone.
    """
    monkeypatch.setenv("POLARS_IGNORE_TIMEZONE_PARSE_ERROR", "1")
    written = io.BytesIO()
    feather.write_feather(
        pa.table(
            {"t": pa.array([1, -1_001, None], type=pa.timestamp("ns", "UTC\x00x"))}
        ),
        written,
        compression="uncompressed",
    )
    written.seek(0)
    column = pl.read_ipc(written)["t"]
    assert column.dtype == pl.Datetime("ns", "UTC\x00x")

    with pytest.raises(ValueError, match="holds a NUL"):
        content_bytes_of(column.to_frame())
    with pytest.raises(ValueError, match="holds a NUL"):
        _content_bytes_of_reference(column.to_frame())
