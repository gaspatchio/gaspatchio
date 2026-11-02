# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The content hash is the specification's own grammar, not an engine's bytes.

An assumption table's content stamp is what answers "is this the basis last
quarter's valuation ran against?", and it only answers it if the bytes behind
it are the values. A digest taken over a writer's file layout moves when the
writer is upgraded, with nothing behind the movement, and a drift alarm that
fires on a dependency upgrade is an alarm a reader learns to ignore.

The worked example in ``spec/graph-artifact/v0-preview.md`` section 12.3 is
reproduced here from the encoder itself. A specification whose worked example
nobody runs is a specification with an untested reading, and the digest below
is the one printed there.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Final

import numpy as np
import polars as pl
import pytest

from gaspatchio._dtypes import neutral_dtype
from gaspatchio._identity import (
    _MISSING,
    _PRESENT_MARK,
    _element_name,
    _flag_block,
    _flag_block_reference,
    _sequence_block,
    _sequence_block_reference,
    _text,
    _text_block,
    _text_block_reference,
    _varint,
    _whole_number_block,
    _without_fixed_width,
    content_bytes_of,
    content_sha_of,
)
from gaspatchio.frame.graph.fingerprint import _scalar

if TYPE_CHECKING:
    import numpy.typing as npt

# Section 12.3's worked example: three attained ages and the mortality rates
# against them, ordered by the dimension the table is keyed on, exactly as a
# Table orders its own frame before stamping it.
WORKED_EXAMPLE_BYTES: Final[str] = (
    "02036167651203025a025c025e0472617465"
    "1303023f50624dd2f1a9fc023f53a92a30553261023f589374bc6a7efa"
)
WORKED_EXAMPLE_DIGEST: Final[str] = (
    "sha256:5267aed7a08b589310c079677eddd6128fb44af9f9fbfbb1dc3d58e2b6dcd277"
)

# The column header a one-column frame named "v" writes before its first
# value: one column, the name behind its length, then the type tag, one row,
# and the present marker.
_ONE_COLUMN: Final[bytes] = b"\x01\x01v"
_ONE_ROW_PRESENT: Final[bytes] = b"\x01\x02"


def _worked_example() -> pl.DataFrame:
    """Return section 12.3's mortality basis, ordered by its dimension."""
    basis = pl.DataFrame({"age": [45, 46, 47], "rate": [0.001, 0.0012, 0.0015]})
    return basis.sort("age")


def _tagged_value(value: object, dtype: pl.DataType) -> bytes:
    """Return the type tag and the value bytes one cell writes in a content hash."""
    encoded = content_bytes_of(pl.Series("v", [value], dtype=dtype).to_frame())
    assert encoded.startswith(_ONE_COLUMN)
    tail = encoded[len(_ONE_COLUMN) :]
    tag, count_and_marker, body = tail[:1], tail[1:3], tail[3:]
    assert count_and_marker == _ONE_ROW_PRESENT
    return tag + body


def test_the_worked_example_reproduces():
    """The bytes and the digest section 12.3 prints are the ones the encoder writes."""
    mortality_basis = _worked_example()

    assert content_bytes_of(mortality_basis).hex() == WORKED_EXAMPLE_BYTES
    assert content_sha_of(mortality_basis) == WORKED_EXAMPLE_DIGEST


def test_the_bytes_are_the_grammar_s_not_a_writer_s():
    """One row spelled out by hand, so only the published grammar can produce it."""
    one_policy = pl.DataFrame(
        {"attained_age": [45], "mortality_rate": [0.001], "in_force": [True]}
    )

    expected = bytes.fromhex(
        "03"  # three columns
        "0c 61 74 74 61 69 6e 65 64 5f 61 67 65"  # "attained_age"
        "12"  # a whole number
        "01"  # one row
        "02 5a"  # present, zigzag(45)
        "0e 6d 6f 72 74 61 6c 69 74 79 5f 72 61 74 65"  # "mortality_rate"
        "13"  # a decimal
        "01"  # one row
        "02 3f 50 62 4d d2 f1 a9 fc"  # present, 0.001
        "08 69 6e 5f 66 6f 72 63 65"  # "in_force"
        "11"  # a true/false flag
        "01"  # one row
        "02 01"  # present, true
    )

    assert content_bytes_of(one_policy) == expected


def test_width_collapses_deliberately():
    """Storage width is not content: the same durations hash alike at either width."""
    eight_bytes = pl.Series("policy_term", [10, 20, 30], dtype=pl.Int64).to_frame()
    four_bytes = pl.Series("policy_term", [10, 20, 30], dtype=pl.Int32).to_frame()

    assert content_sha_of(eight_bytes) == content_sha_of(four_bytes)


def test_a_value_change_moves_the_hash_and_sorted_row_order_does_not():
    """Sorting is what makes two loads agree; a changed rate is what parts them."""
    mortality_basis = _worked_example()
    shuffled = mortality_basis.sample(fraction=1.0, shuffle=True, seed=11).sort("age")
    one_rate_moved = mortality_basis.with_columns(
        pl.when(pl.col("age") == 46)
        .then(pl.lit(0.0013))
        .otherwise(pl.col("rate"))
        .alias("rate")
    )

    assert content_sha_of(shuffled) == content_sha_of(mortality_basis)
    assert content_sha_of(one_rate_moved) != content_sha_of(mortality_basis)


def test_scalar_byte_forms_agree_with_the_node_grammar():
    """One value has one encoding, whichever of the two grammars writes it down."""
    in_force = True
    assert _tagged_value(in_force, pl.Boolean) == _scalar(in_force)
    assert _tagged_value(0.0012, pl.Float64) == _scalar(0.0012)
    assert _tagged_value(45, pl.Int64) == _scalar(45)
    assert _tagged_value("female", pl.String) == _scalar("female")


def test_a_json_round_trip_reproduces_the_hash():
    """What a consumer does with an inline payload, and it reaches the same digest."""
    mortality_basis = _worked_example()

    rebuilt = pl.DataFrame(json.loads(json.dumps(mortality_basis.to_dicts())))

    assert content_sha_of(rebuilt) == content_sha_of(mortality_basis)


# --- the rules section 12.3 states, pinned at the byte -----------------------


def test_a_date_is_a_count_of_days_and_a_timestamp_a_count_of_microseconds() -> None:
    """The two tags the content grammar adds, and the units they count in.

    Section 12.1 has no literal for either, and a column of data does need
    both. They take their own tags rather than borrowing ``i64``'s because
    a count of days and a plain whole number are different claims about a
    column, and a reader comparing two quarters has to be able to see one
    become the other. Both are zigzagged, so a pre-epoch date costs one
    byte rather than ten.
    """
    day_after_epoch = pl.Series("v", [datetime.date(1970, 1, 2)]).to_frame()
    day_before_epoch = pl.Series("v", [datetime.date(1969, 12, 31)]).to_frame()
    one_microsecond = pl.Series(
        "v",
        [datetime.datetime(1970, 1, 1, 0, 0, 0, 1)],  # noqa: DTZ001
    ).to_frame()

    assert content_bytes_of(day_after_epoch) == bytes.fromhex(
        "01"  # one column
        "01 76"  # "v"
        "16"  # a count of days
        "01"  # one row
        "02 02"  # present, zigzag(1)
    )
    assert content_bytes_of(day_before_epoch) == bytes.fromhex(
        "01 01 76 16 01 02 01"  # present, zigzag(-1)
    )
    assert content_bytes_of(one_microsecond) == bytes.fromhex(
        "01"  # one column
        "01 76"  # "v"
        "17 00"  # an instant, naive: an empty zone
        "01"  # one row
        "02 02 00"  # present, zigzag(1) microseconds, no nanoseconds past
    )


def test_one_instant_has_one_encoding_whatever_unit_it_was_kept_in() -> None:
    """Milliseconds and nanoseconds are storage; the instant is the content.

    A frame loaded from parquet carries whatever time unit the writer
    chose, and two loads of one basis that differ only in that unit are
    one basis. The column is put on microseconds first, so the stamp moves
    when the instant moves and not when the engine's storage does.
    """
    instant = datetime.datetime(1970, 1, 1, 0, 0, 0, 1000)  # noqa: DTZ001
    in_microseconds = pl.Series("v", [instant], dtype=pl.Datetime("us")).to_frame()
    in_milliseconds = pl.Series("v", [instant], dtype=pl.Datetime("ms")).to_frame()
    in_nanoseconds = pl.Series("v", [instant], dtype=pl.Datetime("ns")).to_frame()

    expected = bytes.fromhex(
        "01"  # one column
        "01 76"  # "v"
        "17 00"  # an instant, naive: an empty zone
        "01"  # one row
        "02 d0 0f 00"  # present, zigzag(1000) microseconds, no nanoseconds past
    )

    assert content_bytes_of(in_microseconds) == expected
    assert content_bytes_of(in_milliseconds) == expected
    assert content_bytes_of(in_nanoseconds) == expected


def test_an_instant_keeps_its_nanoseconds_and_its_zone() -> None:
    """Two books that compute two answers never share one digest.

    The model compares timestamps to the nanosecond and reads the calendar
    in the column's zone, so a claim notified 500 ns after a cut-off, and
    one issue instant shown in Pacific/Auckland, are other books. A naive
    column is read as UTC, so the two digest alike.
    """
    at = 1_577_880_000_000_000_000
    nanos = pl.Series("v", [at, at + 500], dtype=pl.Int64).cast(pl.Datetime("ns"))
    assert content_bytes_of(nanos[:1].to_frame()) != content_bytes_of(
        nanos[1:].to_frame()
    )
    assert content_bytes_of(
        pl.Series("v", [-1], dtype=pl.Int64).cast(pl.Datetime("ns")).to_frame()
    ) == bytes.fromhex(
        "01 01 76 17 00 0102 01 e7 07"  # microsecond -1, then 999 nanoseconds past it
    )

    naive = pl.Series("v", [1_000], dtype=pl.Int64).cast(pl.Datetime("us"))
    in_utc = naive.dt.replace_time_zone("UTC")
    in_auckland = in_utc.dt.convert_time_zone("Pacific/Auckland")
    assert content_bytes_of(in_utc.to_frame()) == content_bytes_of(naive.to_frame())
    assert (
        content_bytes_of(in_auckland.to_frame())
        == bytes.fromhex(
            "01 01 76 17"
            "10" + b"Pacific/Auckland".hex() + "01"  # the zone, behind its length
            "02 d0 0f 00"
        )
    )


def test_a_sequence_is_the_element_s_tag_and_a_counted_run_per_row() -> None:
    """The layout every projected column is stamped under, spelled out.

    The element's tag is hoisted into the column's own header and written
    once; each row is its marker, a count of members, and those members,
    each behind a marker of its own. A period with no value and a period
    whose value is nought are two different projections, so the member's
    marker is what keeps them apart -- and a row that is missing entirely
    is a third thing again from a row holding no members.
    """
    paths = pl.Series(
        "v", [[1.0, None], [], None], dtype=pl.List(pl.Float64)
    ).to_frame()

    assert content_bytes_of(paths) == bytes.fromhex(
        "01"  # one column
        "01 76"  # "v"
        "15 13"  # a sequence, of decimals
        "03"  # three rows
        "02 02"  # present, two members
        "02 3f f0 00 00 00 00 00 00"  # present, 1.0
        "01 00"  # a member nobody supplied
        "02 00"  # present, no members at all
        "01 00"  # a row nobody supplied
    )


def test_the_content_path_normalises_negative_zero_and_every_nan() -> None:
    """A decimal's bytes are the number, not the bit pattern it arrived in.

    Two runs that both produced a NaN have not drifted, and a zero in a
    column of data carries whatever sign the arithmetic that produced it
    left behind. Both would otherwise move a stamp with no data behind the
    movement, which is the failure the whole grammar exists to avoid.

    **This is where 12.3 and 12.1 part company**, since
    ``gspv0-preview-3``: the identity grammar keeps a negative zero's sign,
    because there it is a literal an author wrote and ``to_text`` reads the
    sign back. Here the sign is not authored, and a basis republished with
    the same rates must not announce a change nobody made. 12.3 states that
    in its own words rather than pointing at 12.1, and names what it leaves
    open.
    """
    patterns = np.array(
        [
            0x7FF8000000000000,  # the quiet NaN
            0xFFF8000000000000,  # the same, sign bit set
            0x7FF8DEADBEEF0000,  # a quiet NaN carrying a payload
            0x7FF0000000000001,  # a signalling NaN
        ],
        dtype=np.uint64,
    ).view(np.float64)
    every_nan = pl.Series("v", patterns).to_frame()
    minus_zero = pl.Series("v", [-0.0]).to_frame()
    plus_zero = pl.Series("v", [0.0]).to_frame()

    header = bytes.fromhex("01 01 76 13 04")  # one column "v", decimals, four rows
    quiet = bytes.fromhex("02 7f f8 00 00 00 00 00 00")

    assert content_bytes_of(every_nan) == header + quiet * 4
    assert content_bytes_of(minus_zero) == content_bytes_of(plus_zero)
    assert content_sha_of(minus_zero) == content_sha_of(plus_zero)


# --- the sequence path is vectorised, and writes the same bytes --------------


def _both_sequence_paths(column: pl.Series) -> tuple[bytes, bytes]:
    """Return one sequence column's bytes from the array path and the loop."""
    values = _without_fixed_width(column)
    element = _element_name(neutral_dtype(values.dtype, column=column.name))
    return (
        _sequence_block(values, element, column.name).data,
        _sequence_block_reference(values, element, column.name),
    )


def _projection_shaped(rows: int, periods: int) -> pl.Series:
    """Return the column a projection produces: one value per period, per policy."""
    generator: npt.NDArray[np.float64] = np.random.default_rng(3).normal(
        size=(rows, periods)
    )
    return pl.Series("path", generator.tolist(), dtype=pl.List(pl.Float64))


@pytest.mark.parametrize(
    "column",
    [
        pl.Series(
            "jagged", [[1.0, None, 3.0], [], None, [0.0]], dtype=pl.List(pl.Float64)
        ),
        pl.Series("whole", [[1, -2], None, [], [63, 64, -65]], dtype=pl.List(pl.Int64)),
        pl.Series("text", [["a", None], [], None, ["", "ß"]], dtype=pl.List(pl.String)),
        pl.Series(
            "flags", [[True, None], [], None, [False]], dtype=pl.List(pl.Boolean)
        ),
        pl.Series(
            "dates",
            [[datetime.date(1969, 12, 31), None], None, []],
            dtype=pl.List(pl.Date),
        ),
        pl.Series(
            "nested",
            [[[1.0, None], []], None, [], [[]]],
            dtype=pl.List(pl.List(pl.Float64)),
        ),
        pl.Series("all_missing", [None, None], dtype=pl.List(pl.Float64)),
        pl.Series("no_rows", [], dtype=pl.List(pl.Float64)),
        pl.Series(
            "fixed_width", [[1.0, 2.0], [3.0, None]], dtype=pl.Array(pl.Float64, 2)
        ),
        _projection_shaped(200, 12),
    ],
    ids=lambda column: str(column.name),
)
def test_the_sequence_path_writes_the_bytes_the_row_by_row_reading_writes(
    column: pl.Series,
) -> None:
    """The vectorised encoder and the definition it was derived from agree.

    The row-by-row reading is the grammar written out the way section 12.3
    reads: take each row, write its count, write its members. The shipped
    encoder does the same thing in one pass over the exploded values and
    splices the counts back in from the offsets, which is the only way a
    projection-shaped column gets stamped inside an edit-run-refine loop.
    Nothing about that is allowed to move a byte.
    """
    vectorised, row_by_row = _both_sequence_paths(column)

    assert vectorised == row_by_row


def test_a_projection_shaped_column_agrees_at_the_size_it_is_stamped_at() -> None:
    """A real projection's worth of values, where the row-by-row reading cost seconds.

    A thousand policies over ten years of months is the ordinary shape of
    an injected simulation, and the shape the row-by-row reading took
    hundreds of milliseconds on. Agreement on four hand-built rows would
    not say much about it.
    """
    column = _projection_shaped(1_000, 120)
    vectorised, row_by_row = _both_sequence_paths(column)

    assert vectorised == row_by_row


# --- the text and flag paths are vectorised, and write the same bytes ---------


def _every_width(values: list[str | None]) -> list[int]:
    """Return what each row takes under the row-by-row reading."""
    return [
        len(_MISSING if value is None else _PRESENT_MARK + _text(value))
        for value in values
    ]


def _random_text(rows: int, seed: int) -> list[str | None]:
    """Return text a book might carry and some it should never need to.

    One-byte, two-byte, three-byte and four-byte characters, the empty
    string, a NUL, and missing values, at lengths either side of every
    point where a byte length's varint grows by a byte.
    """
    rng = np.random.default_rng(seed)
    alphabet = ["a", "Z", " ", "\x00", "ß", "é", "中", "𝄞", "😀"]
    lengths = [0, 1, 42, 127, 128, 200, 16_383, 16_384]
    out: list[str | None] = []
    for row in range(rows):
        if rng.random() < 0.15:
            out.append(None)
            continue
        length = (
            lengths[row % len(lengths)]
            if row < len(lengths) * 3
            else int(rng.integers(0, 60))
        )
        out.append("".join(rng.choice(alphabet, size=length)))
    return out


@pytest.mark.parametrize(
    "column",
    [
        pl.Series("no_rows", [], dtype=pl.String),
        pl.Series("one", ["x"]),
        pl.Series("all_missing", [None, None, None], dtype=pl.String),
        pl.Series("empty_strings", ["", None, "", ""]),
        pl.Series("book_like", ["TERM", "WL", None, "M", "F", "2024-01-31"] * 50),
        pl.Series("unicode", _random_text(600, seed=5)),
        pl.Series("sliced", _random_text(400, seed=6))[37:311],
        pl.concat(
            [
                pl.Series("chunked", _random_text(90, seed=7)),
                pl.Series("chunked", _random_text(40, seed=8)),
            ],
            rechunk=False,
        ),
        pl.Series("categorical", ["M", None, "F", "M"], dtype=pl.Categorical).cast(
            pl.String
        ),
    ],
    ids=lambda column: str(column.name),
)
def test_the_text_path_writes_the_bytes_the_row_by_row_reading_writes(
    column: pl.Series,
) -> None:
    """Every row's marker, byte length and UTF-8, as section 12.3 reads them.

    The shipped encoder takes every length in one varint pass and every
    value's UTF-8 in one join, then splices the two together. A book's
    text columns are digested on every run that publishes a manifest, so
    the row-by-row reading was a Python encode per policy. Nothing about
    the faster path is allowed to move a byte, or a row's width.
    """
    block = _text_block(column)

    assert block.data == _text_block_reference(column)
    assert block.widths.tolist() == _every_width(column.to_list())


@pytest.mark.parametrize(
    "column",
    [
        pl.Series("no_rows", [], dtype=pl.Boolean),
        pl.Series("mixed", [True, False, None, True]),
        pl.Series("all_missing", [None, None], dtype=pl.Boolean),
        pl.Series(
            "random",
            [None if row % 7 == 0 else bool(row % 3) for row in range(500)],
            dtype=pl.Boolean,
        ),
    ],
    ids=lambda column: str(column.name),
)
def test_the_flag_path_writes_the_bytes_the_row_by_row_reading_writes(
    column: pl.Series,
) -> None:
    """A marker and one byte per row, whether the flag is there or not."""
    block = _flag_block(column)

    assert block.data == _flag_block_reference(column)
    assert block.widths.tolist() == [2] * column.len()


def _zigzag_reference(values: list[int | None]) -> bytes:
    """Return a whole-number column's bytes, one zigzag varint at a time."""
    out = bytearray()
    for value in values:
        if value is None:
            out += _MISSING
            continue
        zigzag = ((value << 1) ^ (-1 if value < 0 else 0)) & (2**64 - 1)
        out += _PRESENT_MARK + _varint(zigzag)
    return bytes(out)


@pytest.mark.parametrize(
    "values",
    [
        [0, 5, None, 63],
        list(range(-70, 70)),
        [2 ** (7 * groups) - 1 for groups in range(1, 10)]
        + [2 ** (7 * groups) for groups in range(1, 9)],
        [2**63 - 1, -(2**63), -1, 0, None, 12_345_678_901],
        [None, None],
        [],
    ],
    ids=[
        "one group",
        "either side of zero",
        "every group count",
        "extremes",
        "all missing",
        "no rows",
    ],
)
def test_a_whole_number_takes_only_the_groups_its_column_needs(
    values: list[int | None],
) -> None:
    """The record is as wide as the column's largest value, and the bytes do not move.

    A column of ages needs one seven-bit group and a book's sums assured
    three, so the encoder no longer builds ten groups for every value. The
    groups past a value's own length were always cut away, so no byte can
    change.
    """
    column = pl.Series("w", values, dtype=pl.Int64)

    assert _whole_number_block(column).data == _zigzag_reference(values)
