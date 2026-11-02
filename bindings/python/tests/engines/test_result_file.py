# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A result file is Parquet with the manifest in its footer, whoever wrote it.

The manifest is what makes a file a result rather than a table of numbers,
so where it lives decides who can write one. It lives in the Parquet
footer's key-value metadata -- the one place every Parquet writer shares --
and these tests hold that: a file written here, by pyarrow with its Arrow
schema, and by a writer that stores no Arrow schema at all are all read the
same. Beside that, the sinks take any Arrow stream, not only a Polars frame,
and the book's digest the manifest carries is the specification's content
grammar (section 12.3) rather than any writer's file bytes.
"""

from __future__ import annotations

import hashlib
import struct
from typing import TYPE_CHECKING

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from gaspatchio.engines.protocol import (
    ArrowStreamExportable,
    FrameSink,
    ParquetSink,
    ResultManifest,
    digest_of_inputs,
    read_manifest,
    write_with_manifest,
)
from gaspatchio.engines.report import RunReport

if TYPE_CHECKING:
    from pathlib import Path

MANIFEST = ResultManifest(
    scope="final-schema",
    columns={"policy_id": "policy_id", "reserve": "reserve"},
    dtypes={"policy_id": "i64", "reserve": "f64"},
    row_identity=("policy_id",),
    graph_fingerprint="sha256:" + "ab" * 32,
    inputs_digest="sha256:" + "cd" * 32,
    producer="polars",
    versions={"polars": pl.__version__},
)
FRAME = pl.DataFrame({"policy_id": [1, 2, 3], "reserve": [10.0, 20.5, 31.25]})


def _stamped() -> dict[bytes, bytes]:
    return {
        key.encode(): value.encode() for key, value in MANIFEST.to_metadata().items()
    }


def test_a_written_result_reads_back_its_manifest_and_values(tmp_path: Path) -> None:
    path = tmp_path / "result.parquet"

    write_with_manifest(FRAME, MANIFEST, path)

    assert read_manifest(path) == MANIFEST
    assert pl.read_parquet(path).equals(FRAME)


def test_a_result_pyarrow_wrote_with_its_arrow_schema_is_still_read(
    tmp_path: Path,
) -> None:
    # How 1.0.0's previews wrote results: the manifest as Arrow schema metadata,
    # which pyarrow also copies into the footer.
    path = tmp_path / "result.parquet"
    table = FRAME.to_arrow().replace_schema_metadata(_stamped())
    pq.write_table(table, path)  # type: ignore[no-untyped-call]

    assert read_manifest(path) == MANIFEST


def test_a_result_whose_manifest_is_only_in_the_footer_is_read(
    tmp_path: Path,
) -> None:
    # Polars, like parquet-rs or DuckDB, puts key-value metadata in the footer
    # and not in an Arrow schema. Read through pyarrow's schema, as results
    # once were, such a file carried no manifest and was refused.
    path = tmp_path / "result.parquet"
    FRAME.write_parquet(path, metadata=MANIFEST.to_metadata())
    schema = pq.read_schema(path).metadata or {}  # type: ignore[no-untyped-call]
    assert b"gaspatchio.scope" not in schema

    assert read_manifest(path) == MANIFEST


def test_a_file_with_no_manifest_is_refused_by_name(tmp_path: Path) -> None:
    path = tmp_path / "numbers.parquet"
    FRAME.write_parquet(path)

    with pytest.raises(ValueError, match=r"carries no 'gaspatchio\.scope'"):
        read_manifest(path)


@pytest.mark.parametrize(
    ("member", "written", "said"),
    [
        ("columns", '["a", "b"]', "gaspatchio.columns is a list"),
        ("dtypes", "7", "gaspatchio.dtypes is a number"),
        ("versions", "[[[]]]", "gaspatchio.versions is a list"),
        ("versions", '{"polars": 1}', "gaspatchio.versions is a mapping whose"),
        ("graph_fingerprint", '{"a": 1}', "gaspatchio.graph_fingerprint is a mapping"),
        ("producer", "null", "gaspatchio.producer is null"),
        ("scope", '"some-nodes"', "gaspatchio.scope is 'some-nodes'"),
        ("versions", "{not json", "gaspatchio.versions does not parse"),
    ],
)
def test_a_manifest_member_of_the_wrong_shape_is_refused_by_name(
    tmp_path: Path, member: str, written: str, said: str
) -> None:
    """Each member is held to the shape its writer writes, before anything reads it."""
    path = tmp_path / "damaged.parquet"
    metadata = MANIFEST.to_metadata()
    metadata[f"gaspatchio.{member}"] = written
    FRAME.write_parquet(path, metadata=metadata)

    with pytest.raises(ValueError, match="result manifest is damaged") as refused:
        read_manifest(path)
    assert said in str(refused.value)


class _OnlyAStream:
    """Something that is an Arrow stream and nothing else."""

    def __init__(self, table: pa.Table) -> None:
        self._table = table

    def __arrow_c_stream__(self, requested_schema: object | None = None) -> object:
        return self._table.__arrow_c_stream__(requested_schema)


def _handed_as(kind: str, frame: pl.DataFrame) -> ArrowStreamExportable:
    if kind == "pyarrow":
        table: ArrowStreamExportable = frame.to_arrow()
        return table
    if kind == "bare-stream":
        return _OnlyAStream(frame.to_arrow())
    return frame


@pytest.mark.parametrize("kind", ["polars", "pyarrow", "bare-stream"])
def test_both_sinks_take_any_arrow_stream(tmp_path: Path, kind: str) -> None:
    first, second = FRAME.head(2), FRAME.tail(1)

    in_memory = FrameSink()
    in_memory.open(MANIFEST)
    in_memory.write_batch(_handed_as(kind, first))
    in_memory.write_batch(_handed_as(kind, second))
    held = in_memory.publish(RunReport(refusals=()))

    path = tmp_path / "result.parquet"
    on_disk = ParquetSink(path)
    on_disk.open(MANIFEST)
    on_disk.write_batch(_handed_as(kind, first))
    on_disk.write_batch(_handed_as(kind, second))
    on_disk.publish(RunReport(refusals=()))

    assert held.columns.equals(FRAME)
    assert pl.read_parquet(path).equals(FRAME)
    assert read_manifest(path) == MANIFEST


# --- the book's digest -------------------------------------------------------


def test_the_book_digest_is_the_specification_s_content_grammar() -> None:
    # Built by hand from spec section 12.3, not by calling the encoder, so a
    # digest that drifted to any library's serialisation fails here: a column
    # count, then per column in name order its name, its tag, its row count,
    # and each value behind a presence marker.
    book = pl.DataFrame({"b": [1.5, -0.0], "a": [3, None]})
    expected = (
        b"\x02"  # two columns
        b"\x01a\x12\x02"  # "a", whole number, two rows
        b"\x02\x06"  # 3, zigzagged to 6
        b"\x01\x00"  # missing
        b"\x01b\x13\x02"  # "b", decimal, two rows
        b"\x02"
        + struct.pack(">d", 1.5)
        + b"\x02"
        + struct.pack(">d", 0.0)  # negative zero is zero
    )

    digest = digest_of_inputs(book, ["b", "a"])

    assert digest == "sha256:" + hashlib.sha256(expected).hexdigest()


def test_the_book_digest_ignores_column_order_and_storage_width() -> None:
    wide = pl.DataFrame({"age": [40, 51], "sum_assured": [1e5, 2e5]})
    narrow = pl.DataFrame(
        {"sum_assured": [1e5, 2e5], "age": pl.Series([40, 51], dtype=pl.Int32)}
    )

    assert digest_of_inputs(wide, ["age", "sum_assured"]) == digest_of_inputs(
        narrow, ["sum_assured", "age"]
    )


def test_the_book_digest_tells_a_count_from_a_decimal_and_a_row_from_another() -> None:
    counts = pl.DataFrame({"x": [1, 1]})

    assert digest_of_inputs(counts, ["x"]) != digest_of_inputs(
        counts.cast(pl.Float64), ["x"]
    )
    assert digest_of_inputs(counts, ["x"]) != digest_of_inputs(
        pl.DataFrame({"x": [1, 2]}), ["x"]
    )


def test_the_book_digest_names_only_the_columns_the_book_holds() -> None:
    book = pl.DataFrame({"age": [40]})

    assert digest_of_inputs(book, ["age", "not_in_the_book"]) == digest_of_inputs(
        book, ["age"]
    )
