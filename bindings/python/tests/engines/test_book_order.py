# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A sink puts every row back where its policy stood, whatever order it came in.

An engine may compute a book in an order of its own -- the JAX engine groups
policies by the width of their timelines -- and hand each batch over the
moment it finishes, with the book positions of its rows. Order is then the
sink's to keep, and publication is where it is checked: every row of the book
exactly once, or nothing is published and nothing written remains. Both sinks
are held to the same answer, and to the book itself.

An engine that knows before its first batch that the batches keep the book's
order says so as it opens the sink. The file sink then writes every batch
straight into the one result on a writer thread of Polars' own, and the
promise is held against every batch. The tests at the end hold that route to
everything the staged one promises -- nothing partial left behind, the
original error rather than Polars' wrapper round it, two runs apart -- and to
what it is for: a batch written once, and let go of as soon as it is.
"""

from __future__ import annotations

import gc
import itertools
import json
import os
import signal
import subprocess
import sys
import threading
import time
import weakref
from typing import TYPE_CHECKING

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from gaspatchio.engines import protocol
from gaspatchio.engines.protocol import (
    FrameSink,
    ParquetSink,
    ResultManifest,
    read_manifest,
)
from gaspatchio.engines.report import RunReport
from tests.engines.conftest import writers as _writers

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    import pyarrow as pa

    from gaspatchio.engines.protocol import ArrowStreamExportable

MANIFEST = ResultManifest(
    scope="final-schema",
    columns={
        "policy_id": "policy_id",
        "reserve": "reserve",
        "cashflows": "cashflows",
        "product": "product",
    },
    dtypes={
        "policy_id": "i64",
        "reserve": "f64",
        "cashflows": "list[f64]",
        "product": "str",
    },
    row_identity=("policy_id",),
    graph_fingerprint="sha256:" + "ab" * 32,
    inputs_digest="sha256:" + "cd" * 32,
    producer="stub",
    versions={"polars": pl.__version__},
)
DONE = RunReport(refusals=())


def _book(policies: int) -> pl.DataFrame:
    """Return a book whose every row says where it stands, one timeline apiece."""
    return pl.DataFrame(
        {
            "policy_id": pl.Series(range(policies), dtype=pl.Int64),
            "reserve": [policy * 1.5 for policy in range(policies)],
            "cashflows": [
                [float(policy * 100 + period) for period in range(policy % 5)]
                for policy in range(policies)
            ],
            "product": [f"P{policy % 3}" for policy in range(policies)],
        },
        schema_overrides={"cashflows": pl.List(pl.Float64)},
    )


def _as_an_engine_hands_them(
    policies: int, groups: int, batch: int, seed: int
) -> list[np.ndarray]:
    """Return batches of positions formed as the JAX engine forms them.

    The book is split into groups that interleave -- policies of different
    timeline widths sit side by side in a real book -- and each group is cut
    into batches of its own rows, ascending. The batches then arrive in an
    order of their own, as they may from an engine that runs them anywhere.
    """
    rng = np.random.default_rng(seed)
    labels = rng.integers(0, groups, size=policies)
    batches = [
        rows[at : at + batch]
        for group in range(groups)
        for rows in (np.flatnonzero(labels == group),)
        for at in range(0, rows.size, batch)
    ]
    return [batches[one] for one in rng.permutation(len(batches))]


def _beside(destination: Path) -> list[str]:
    """Return everything standing in the destination's own directory."""
    return sorted(one.name for one in destination.parent.iterdir())


def _sink(kind: str, destination: Path) -> FrameSink | ParquetSink:
    """Return an opened sink of the kind named: frame or file, in order or not.

    ``"file in order"`` is a file sink opened on the engine's promise that
    every batch is the book's next rows, which sends each batch straight
    into the one result; ``"file"`` is one opened without it, which stages.
    """
    sink: FrameSink | ParquetSink = (
        FrameSink() if kind.startswith("frame") else ParquetSink(destination)
    )
    sink.open(MANIFEST, in_order=kind.endswith("in order"))
    return sink


@pytest.mark.parametrize("seed", range(6))
def test_both_sinks_put_batches_from_any_order_back_in_the_book_s_order(
    tmp_path: Path, seed: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three interleaved groups, fourteen batches, arriving shuffled.

    The block is made small, so publication reads the staged parts across
    many blocks -- each part taken a slice at a time, a block gathering
    slices from several parts at once -- and writes a file of many row
    groups.
    """
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", 4_000)
    book = _book(500)
    batches = _as_an_engine_hands_them(book.height, groups=3, batch=37, seed=seed)
    destination = tmp_path / "result.parquet"
    in_memory, on_disk = FrameSink(), ParquetSink(destination)
    in_memory.open(MANIFEST)
    on_disk.open(MANIFEST)

    for rows in batches:
        in_memory.write_batch(book[rows], rows=rows)
        on_disk.write_batch(book[rows], rows=rows)
    (staging,) = tmp_path.glob("*.unpublished.d")
    assert len(list(staging.iterdir())) == len(batches)
    held = in_memory.publish(DONE)
    published = on_disk.publish(DONE)

    assert_frame_equal(held.columns, book)
    assert_frame_equal(pl.read_parquet(destination), book)
    assert read_manifest(destination) == MANIFEST
    assert published.columns.height == 0
    assert published.columns.schema == book.schema
    assert _beside(destination) == ["result.parquet"]


def test_batches_already_in_the_book_s_order_publish_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A book of one timeline, batched in its own order: nothing to gather."""
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", 4_000)
    book = _book(300)
    destination = tmp_path / "result.parquet"
    in_memory, on_disk = _sink("frame", destination), _sink("file", destination)

    for at in range(0, book.height, 64):
        rows = np.arange(at, min(at + 64, book.height))
        in_memory.write_batch(book[rows], rows=rows)
        on_disk.write_batch(book[rows], rows=rows)

    assert_frame_equal(in_memory.publish(DONE).columns, book)
    on_disk.publish(DONE)
    assert_frame_equal(pl.read_parquet(destination), book)


def test_one_batch_is_its_own_result_renamed_into_place(tmp_path: Path) -> None:
    """A run of one batch is written once: its part, manifest and all, renamed.

    The bytes that stand at the destination are the bytes staged when the
    batch was handed over -- no second write at publication.
    """
    book = _book(40)
    destination = tmp_path / "result.parquet"
    sink = _sink("file", destination)

    sink.write_batch(book, rows=np.arange(book.height))
    (staging,) = tmp_path.glob("*.unpublished.d")
    (part,) = staging.iterdir()
    staged = part.read_bytes()
    sink.publish(DONE)

    assert destination.read_bytes() == staged
    assert read_manifest(destination) == MANIFEST
    assert_frame_equal(pl.read_parquet(destination), book)
    assert _beside(destination) == ["result.parquet"]


def test_every_batch_is_staged_in_a_part_of_its_own_the_moment_it_arrives(
    tmp_path: Path,
) -> None:
    """Nothing is kept back in memory, not even the first batch.

    A batch held while the next one is computed is two batches in memory at
    the run's peak, which is the ceiling streaming exists to lift.
    """
    book = _book(60)
    destination = tmp_path / "result.parquet"
    sink = _sink("file", destination)

    sink.write_batch(book[20:40], rows=np.arange(20, 40))
    (staging,) = tmp_path.glob("*.unpublished.d")
    assert len(list(staging.iterdir())) == 1
    sink.write_batch(book[:20], rows=np.arange(20))
    assert len(list(staging.iterdir())) == 2
    sink.write_batch(book[40:], rows=np.arange(40, 60))
    assert len(list(staging.iterdir())) == 3
    sink.publish(DONE)

    assert_frame_equal(pl.read_parquet(destination), book)
    assert _beside(destination) == ["result.parquet"]


@pytest.mark.parametrize("kind", ["frame", "file", "frame in order", "file in order"])
@pytest.mark.parametrize("by_position_first", [True, False])
def test_mixing_positions_and_the_book_s_next_rows_is_refused(
    tmp_path: Path, kind: str, *, by_position_first: bool
) -> None:
    """One run, one form: after a batch placed by position there is no "next"."""
    book = _book(30)
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)
    for at in (0, 10):
        rows = np.arange(at, at + 10)
        sink.write_batch(book[rows], rows=rows if by_position_first else None)

    later = np.arange(20, 30)
    with pytest.raises(ValueError, match="A batch was handed") as refused:
        sink.write_batch(book[later], rows=None if by_position_first else later)

    assert "defect in the engine" in str(refused.value)
    assert _beside(destination) == []
    assert _writers() == []
    with pytest.raises(RuntimeError, match="without being opened"):
        sink.publish(DONE)


@pytest.mark.parametrize("kind", ["frame", "file"])
@pytest.mark.parametrize(
    ("second", "said"),
    [
        (np.arange(12, 22), "2 positions are missing, 0 rows repeat a position"),
        (np.arange(5, 15), "5 positions are missing, 5 rows repeat a position"),
        (np.arange(10, 20) * 3, "10 rows stand past the end"),
    ],
    ids=["a gap", "a duplicate", "far past the end"],
)
def test_positions_that_are_not_the_book_s_rows_once_each_publish_nothing(
    tmp_path: Path, kind: str, second: np.ndarray, said: str
) -> None:
    """Counted and named, and nothing left behind to be found later."""
    book = _book(20)
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)
    sink.write_batch(book[:10], rows=np.arange(10))
    sink.write_batch(book[10:], rows=second)

    with pytest.raises(ValueError, match="once each") as refused:
        sink.publish(DONE)

    assert said in str(refused.value)
    assert "defect in the engine" in str(refused.value)
    assert _beside(destination) == []


@pytest.mark.parametrize("kind", ["frame", "file"])
@pytest.mark.parametrize(
    ("rows", "said"),
    [
        (np.array([2, 1, 0]), "ascend"),
        (np.array([0, 0, 1]), "ascend"),
        (np.array([0, 1]), "one position per row"),
        (np.array([[0, 1, 2]]), "one position per row"),
        (np.array([-1, 0, 1]), "below"),
        (np.array([0.0, 1.0, 2.0]), "whole numbers"),
    ],
    ids=["descending", "repeated", "short", "two-dimensional", "negative", "floats"],
)
def test_positions_a_batch_cannot_have_are_refused_as_it_is_written(
    tmp_path: Path, kind: str, rows: np.ndarray, said: str
) -> None:
    """Checked at the door, against the batch they came with."""
    book = _book(9)
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)
    sink.write_batch(book[3:6], rows=np.arange(3, 6))
    sink.write_batch(book[6:9], rows=np.arange(6, 9))

    with pytest.raises(ValueError, match=said):
        sink.write_batch(book[:3], rows=rows)

    assert _beside(destination) == []


class _OnlyAStream:
    """Something that is an Arrow stream and nothing else."""

    def __init__(self, table: pa.Table) -> None:
        self._table = table

    def __arrow_c_stream__(self, requested_schema: object | None = None) -> object:
        return self._table.__arrow_c_stream__(requested_schema)


@pytest.mark.parametrize("handed", ["pyarrow", "bare-stream"])
def test_a_batch_handed_as_another_arrow_stream_is_placed_by_position(
    tmp_path: Path, handed: str
) -> None:
    """A sink places a batch from any Arrow producer by position, in any order."""
    book = _book(90)
    destination = tmp_path / "result.parquet"
    in_memory, on_disk = _sink("frame", destination), _sink("file", destination)

    for rows in _as_an_engine_hands_them(book.height, groups=2, batch=20, seed=7):
        table = book[rows].to_arrow()
        batch: ArrowStreamExportable = (
            table if handed == "pyarrow" else _OnlyAStream(table)
        )
        in_memory.write_batch(batch, rows=rows)
        on_disk.write_batch(batch, rows=list(rows))

    assert_frame_equal(in_memory.publish(DONE).columns, book)
    on_disk.publish(DONE)
    assert_frame_equal(pl.read_parquet(destination), book)


@pytest.mark.parametrize(
    ("kind", "working"),
    [("file", "*.unpublished.d"), ("file in order", "*.unpublished")],
    ids=["staged", "in order"],
)
def test_two_runs_to_one_destination_stage_apart(
    tmp_path: Path, kind: str, working: str
) -> None:
    """Each run reserves its own working, and the last to publish is what stands.

    Two terminals, one output path: neither run's parts, nor the result it is
    writing straight into, can be taken for the other's, because the uuid in
    each run's names is its own.
    """
    destination = tmp_path / "result.parquet"
    short, long = _book(30), _book(47)
    first, second = _sink(kind, destination), _sink(kind, destination)
    for book, sink in ((short, first), (long, second)):
        for at in range(0, book.height, 10):
            rows = np.arange(at, min(at + 10, book.height))
            sink.write_batch(book[rows], rows=rows)

    assert len(list(tmp_path.glob(working))) == 2
    first.publish(DONE)
    assert_frame_equal(pl.read_parquet(destination), short)
    second.publish(DONE)

    assert_frame_equal(pl.read_parquet(destination), long)
    assert _beside(destination) == ["result.parquet"]


@pytest.mark.parametrize("kind", ["file", "file in order"])
def test_abandoning_removes_every_part_and_closes_the_sink(
    tmp_path: Path, kind: str
) -> None:
    """Nothing written survives, and nothing more can be written or published.

    In the book's order the writer is stopped and waited for before its
    result is removed, so nothing writes to the file after it has gone.
    """
    book = _book(30)
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)
    for at in range(0, 30, 10):
        sink.write_batch(book[at : at + 10], rows=np.arange(at, at + 10))
    assert list(tmp_path.glob("*.unpublished*"))

    sink.abandon()
    sink.abandon()

    assert _beside(destination) == []
    assert _writers() == []
    with pytest.raises(RuntimeError, match="without being opened"):
        sink.write_batch(book[:10], rows=np.arange(10))
    with pytest.raises(RuntimeError, match="without being opened"):
        sink.publish(DONE)


def test_a_publication_that_fails_part_way_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full disk while the parts are read back is not a half-written result."""
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", 2_000)
    book = _book(200)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"last quarter's result")
    sink = _sink("file", destination)
    for at in range(0, 200, 50):
        sink.write_batch(book[at : at + 50], rows=np.arange(at, at + 50))
    taking = protocol._Part.take  # noqa: SLF001 -- the part reader under test
    taken: list[int] = []

    def fails_on_the_third(part: protocol._Part, count: int) -> pl.DataFrame:
        taken.append(count)
        if len(taken) == 3:
            message = "No space left on device"
            raise OSError(message)
        return taking(part, count)

    monkeypatch.setattr(protocol._Part, "take", fails_on_the_third)  # noqa: SLF001 -- as above
    # The error the merge met, not Polars' ComputeError wrapped round it.
    with pytest.raises(OSError, match="No space left on device"):
        sink.publish(DONE)

    assert destination.read_bytes() == b"last quarter's result"
    assert _beside(destination) == ["result.parquet"]


def test_a_batch_that_cannot_be_staged_removes_everything_staged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full disk on the third batch: nothing staged survives, and the sink is shut."""
    book = _book(30)
    destination = tmp_path / "result.parquet"
    sink = _sink("file", destination)
    writing = protocol.write_with_manifest
    written: list[Path] = []

    def full_on_the_third(
        frame: pl.DataFrame,
        manifest: ResultManifest,
        path: Path,
        *,
        row_group_size: int | None = None,
    ) -> None:
        written.append(path)
        if len(written) == 3:
            message = "No space left on device"
            raise OSError(message)
        writing(frame, manifest, path, row_group_size=row_group_size)

    monkeypatch.setattr(protocol, "write_with_manifest", full_on_the_third)
    sink.write_batch(book[:10], rows=np.arange(10))
    sink.write_batch(book[10:20], rows=np.arange(10, 20))
    with pytest.raises(OSError, match="No space left on device"):
        sink.write_batch(book[20:], rows=np.arange(20, 30))

    assert _beside(destination) == []
    with pytest.raises(RuntimeError, match="without being opened"):
        sink.publish(DONE)


@pytest.mark.parametrize("kind", ["file", "file in order"])
def test_a_published_sink_is_closed_and_cannot_publish_over_itself(
    tmp_path: Path, kind: str
) -> None:
    """One run, one publication: a second would rename a second file over it."""
    book = _book(20)
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)
    sink.write_batch(book[:10], rows=np.arange(10))
    sink.write_batch(book[10:], rows=np.arange(10, 20))
    sink.publish(DONE)
    standing = destination.read_bytes()

    with pytest.raises(RuntimeError, match="without being opened"):
        sink.publish(DONE)

    assert destination.read_bytes() == standing


@pytest.mark.parametrize("kind", ["frame", "file", "file in order"])
def test_an_empty_book_publishes_its_columns_and_no_rows(
    tmp_path: Path, kind: str
) -> None:
    """One batch of nothing, placed at no positions: a result with no rows."""
    book = _book(0)
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)

    sink.write_batch(book, rows=np.zeros(0, dtype=np.int64))
    answered = sink.publish(DONE)

    written = answered.columns if kind == "frame" else pl.read_parquet(destination)
    assert written.height == 0
    assert written.schema == book.schema
    if kind != "frame":
        assert read_manifest(destination) == MANIFEST
        assert _beside(destination) == ["result.parquet"]


@pytest.mark.parametrize("where", ["staging a part", "merging the parts"])
def test_an_interrupt_inside_the_file_sink_leaves_nothing_and_stays_an_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    """A key pressed while a part is written, or while the parts are merged.

    Last quarter's result stands, nothing of this run remains beside it, and
    what comes out is the ``KeyboardInterrupt`` itself -- not an error Polars
    wrapped round it while its writer was pulling the merge.
    """
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", 2_000)
    book = _book(200)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"last quarter's result")
    sink = _sink("file", destination)
    calls: list[int] = []

    def interrupting(original: object, on_call: int) -> object:
        def interrupted(*arguments: object, **named: object) -> object:
            calls.append(1)
            if len(calls) == on_call:
                raise KeyboardInterrupt
            return original(*arguments, **named)  # type: ignore[operator]

        return interrupted

    if where == "staging a part":
        monkeypatch.setattr(
            protocol,
            "write_with_manifest",
            interrupting(protocol.write_with_manifest, on_call=3),
        )
        for at in (0, 50):
            sink.write_batch(book[at : at + 50], rows=np.arange(at, at + 50))
        with pytest.raises(KeyboardInterrupt):
            sink.write_batch(book[100:150], rows=np.arange(100, 150))
    else:
        for at in range(0, 200, 50):
            sink.write_batch(book[at : at + 50], rows=np.arange(at, at + 50))
        monkeypatch.setattr(
            protocol._Part,  # noqa: SLF001 -- the part reader under test
            "take",
            interrupting(protocol._Part.take, on_call=2),  # noqa: SLF001 -- as above
        )
        with pytest.raises(KeyboardInterrupt):
            sink.publish(DONE)

    assert destination.read_bytes() == b"last quarter's result"
    assert _beside(destination) == ["result.parquet"]


@pytest.mark.parametrize("kind", ["frame", "file", "file in order"])
@pytest.mark.parametrize(
    ("second", "refused"),
    [
        ({"a": ["x", "y"]}, pl.exceptions.SchemaError),
        ({"b": [None, None]}, pl.exceptions.ShapeError),
    ],
    ids=["a column of another type", "another column"],
)
def test_a_batch_whose_columns_are_not_the_first_s_is_refused_alike(
    tmp_path: Path, kind: str, second: dict[str, list[object]], refused: type
) -> None:
    """Both sinks refuse it the same way, as it is written, and keep nothing.

    The first batch's column is all null, so Polars types it ``Null``: the
    case the frame sink used to refuse at publication and the file sink as a
    ``ComputeError`` naming neither.
    """
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)
    sink.write_batch(pl.DataFrame({"a": [None, None]}), rows=np.arange(2))

    with pytest.raises(refused):
        sink.write_batch(pl.DataFrame(second), rows=np.arange(2, 4))

    assert _beside(destination) == []
    assert _writers() == []
    with pytest.raises(RuntimeError, match="without being opened"):
        sink.publish(DONE)


def test_a_stray_file_in_the_staging_directory_does_not_stop_publication(
    tmp_path: Path,
) -> None:
    """A Finder's .DS_Store among the parts: the run still publishes, cleanly."""
    book = _book(30)
    destination = tmp_path / "result.parquet"
    sink = _sink("file", destination)
    sink.write_batch(book, rows=np.arange(book.height))
    (staging,) = tmp_path.glob("*.unpublished.d")
    (staging / ".DS_Store").write_bytes(b"Finder was here")

    sink.publish(DONE)

    assert_frame_equal(pl.read_parquet(destination), book)
    assert _beside(destination) == ["result.parquet"]


@pytest.mark.parametrize("batches", [1, 3], ids=["one batch", "three batches"])
def test_the_rename_into_place_is_the_last_thing_publication_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, batches: int
) -> None:
    """The staging directory refuses to go: the destination is still last quarter's.

    Everything staged is removed before the rename, so a failure removing it
    is a failure before publication, and abandoning afterwards leaves
    nothing -- not the result under its own name.
    """
    book = _book(30)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"last quarter's result")
    sink = _sink("file", destination)
    for rows in np.array_split(np.arange(book.height), batches):
        sink.write_batch(book[rows], rows=rows)
    removing = protocol.shutil.rmtree
    removed: list[object] = []

    def refuses_once(*arguments: object, **named: object) -> None:
        removed.append(arguments)
        if len(removed) == 1:
            message = "Directory not empty"
            raise OSError(message)
        removing(*arguments, **named)  # type: ignore[arg-type]

    monkeypatch.setattr(protocol.shutil, "rmtree", refuses_once)
    with pytest.raises(OSError, match="Directory not empty"):
        sink.publish(DONE)

    assert destination.read_bytes() == b"last quarter's result"
    assert _beside(destination) == ["result.parquet"]


@pytest.mark.parametrize(
    ("kind", "working"),
    [("file", "*.unpublished.d"), ("file in order", "*.unpublished")],
    ids=["staged", "in order"],
)
def test_opening_an_open_file_sink_again_removes_what_it_had_staged(
    tmp_path: Path, kind: str, working: str
) -> None:
    """Nothing is orphaned beside the destination by a sink opened twice."""
    book = _book(40)
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)
    for at in (0, 10):
        sink.write_batch(book[at : at + 10], rows=np.arange(at, at + 10))
    (earlier,) = tmp_path.glob(working)

    sink.open(MANIFEST, in_order=kind.endswith("in order"))

    assert not earlier.exists()
    assert _beside(destination) == []
    assert _writers() == []
    for at in range(0, 40, 20):
        sink.write_batch(book[at : at + 20], rows=np.arange(at, at + 20))
    sink.publish(DONE)
    assert_frame_equal(pl.read_parquet(destination), book)
    assert _beside(destination) == ["result.parquet"]


@pytest.mark.parametrize("layout", ["interleaved", "in order"])
def test_each_part_is_written_in_its_share_of_a_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: str
) -> None:
    """Four groups a row apart: each part a quarter of a block to a row group.

    That is what keeps publication's reading to about a block however finely
    an engine's groups interleave. Parts that run in the book's order are a
    whole block to a group, and so is a run of one batch -- the layout of
    every file the sink publishes.
    """
    import pyarrow.parquet as pq

    book = _book(400)
    rows_a_block = 40
    monkeypatch.setattr(protocol, "_LEAST_PART_GROUP_BYTES", 1)
    destination = tmp_path / "result.parquet"
    sink = _sink("file", destination)
    per_row = -(-int(book.estimated_size()) // book.height)
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", rows_a_block * per_row)
    groups = [
        np.arange(group, book.height, 4)
        if layout == "interleaved"
        else np.arange(group * 100, (group + 1) * 100)
        for group in range(4)
    ]
    for rows in groups:
        sink.write_batch(book[rows], rows=rows)
    (staging,) = tmp_path.glob("*.unpublished.d")
    parts = sorted(staging.iterdir())
    written = [pq.ParquetFile(part).metadata.row_group(0).num_rows for part in parts]

    # A quarter of a block, rounded up: a group's rows are four apart, so
    # its hundred rows span 397 positions of the book.
    share = rows_a_block / 4 if layout == "interleaved" else rows_a_block
    assert all(abs(one - share) <= 1 for one in written), written
    sink.publish(DONE)
    assert_frame_equal(pl.read_parquet(destination), book)


# In the book's order: every batch straight into the one result.


def test_batches_promised_in_order_go_straight_into_one_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No staging and no parts: one unpublished result, from the first batch on.

    The block is made small, so each batch is cut into several pieces and the
    file into many row groups; a batch of no rows in the middle adds nothing.
    What publishes is the book under its manifest, alone, with the writer's
    thread gone.
    """
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", 4_000)
    book = _book(300)
    destination = tmp_path / "result.parquet"
    sink = _sink("file in order", destination)
    edges = [0, 64, 128, 128, 192, 256, 300]
    working: list[list[str]] = []

    for low, high in itertools.pairwise(edges):
        rows = np.arange(low, high)
        sink.write_batch(book[rows], rows=rows)
        working.append(_beside(destination))
    published = sink.publish(DONE)

    assert all(len(names) == 1 for names in working), working
    assert all(names[0].endswith(".unpublished") for names in working), working
    assert_frame_equal(pl.read_parquet(destination), book)
    assert read_manifest(destination) == MANIFEST
    assert published.columns.height == 0
    assert published.columns.schema == book.schema
    assert _beside(destination) == ["result.parquet"]
    assert _writers() == []


def test_a_result_written_in_order_is_a_block_to_a_row_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The layout of a result put back in order from its parts, whatever the batches.

    Batches of seventy rows and a block of forty: each batch is cut into a
    piece of forty and one of thirty -- never more than a block, which is what
    bounds what the writer holds -- and Polars' writer joins each thirty to
    the next batch's first forty, so every row group of the file is a block.
    It does so in its streaming engine whatever engine the caller's session
    prefers, because the bound is the streaming engine's.
    """
    import pyarrow.parquet as pq

    book = _book(400)
    rows_a_block = 40
    first = book[:70]
    per_row = -(-int(first.estimated_size()) // first.height)
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", rows_a_block * per_row)
    cutting = protocol._piece_of  # noqa: SLF001 -- the copy under test
    pieces: list[int] = []

    def counted(batch: pl.DataFrame, at: int, rows: int) -> pl.DataFrame:
        piece = cutting(batch, at, rows)
        pieces.append(piece.height)
        return piece

    monkeypatch.setattr(protocol, "_piece_of", counted)
    writing = pl.LazyFrame.sink_parquet
    engines: list[object] = []

    def recorded(frame: pl.LazyFrame, *arguments: object, **named: object) -> None:
        engines.append(named.get("engine"))
        writing(frame, *arguments, **named)  # type: ignore[arg-type]

    monkeypatch.setattr(pl.LazyFrame, "sink_parquet", recorded)
    destination = tmp_path / "result.parquet"
    sink = _sink("file in order", destination)

    for at in range(0, book.height, 70):
        rows = np.arange(at, min(at + 70, book.height))
        sink.write_batch(book[rows], rows=rows)
    sink.publish(DONE)

    layout = pq.ParquetFile(destination).metadata
    groups = [layout.row_group(at).num_rows for at in range(layout.num_row_groups)]
    assert groups == [rows_a_block] * (book.height // rows_a_block)
    assert sum(pieces) == book.height
    assert max(pieces) == rows_a_block
    assert engines == ["streaming"]
    assert_frame_equal(pl.read_parquet(destination), book)


def _spans(frame: pl.DataFrame, columns: list[str]) -> list[tuple[int, int]]:
    """Return where in memory each buffer of these columns lies."""
    return [
        (buffer.address, buffer.address + buffer.size)
        for name in columns
        for buffer in frame[name].to_arrow().buffers()
        if buffer is not None and buffer.size
    ]


def _shares(piece: pl.DataFrame, batch: pl.DataFrame, columns: list[str]) -> bool:
    """Return whether any buffer of the piece lies inside one of the batch's."""
    held = _spans(batch, columns)
    return any(
        low < high_held and low_held < high
        for low, high in _spans(piece, columns)
        for low_held, high_held in held
    )


def test_a_piece_owns_its_rows_rather_than_sharing_the_batch_s() -> None:
    """A piece is a copy, so one waiting in Polars' writer holds only itself.

    A slice would share its batch's buffers, so one piece still in Polars'
    writer would keep the whole batch in memory while the engine builds the
    next. The slice beside the piece is the control: it shows that sharing
    is what the check sees. Text is left out of it, because Polars hands text
    to Arrow as a copy whether it was sliced or not.
    """
    book = _book(300)
    numeric = ["policy_id", "reserve", "cashflows"]
    piece = protocol._piece_of(book, 50, 60)  # noqa: SLF001 -- the copy under test

    assert_frame_equal(piece, book[50:110])
    assert not _shares(piece, book, numeric)
    assert _shares(book.slice(50, 60), book, numeric)


def test_write_batch_returns_once_the_writer_has_taken_every_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Handed over and waited for: after ``write_batch`` nothing refers to the batch.

    The writer is made slow to cut a piece, so a hand-over that returned
    before the batch was taken would still be holding it here. What it holds
    instead is nothing, and the batch goes as soon as the engine lets go of
    it -- before the engine builds the next.
    """
    book = _book(300)
    cutting = protocol._piece_of  # noqa: SLF001 -- the copy under test

    def slow(batch: pl.DataFrame, at: int, rows: int) -> pl.DataFrame:
        time.sleep(0.2)
        return cutting(batch, at, rows)

    monkeypatch.setattr(protocol, "_piece_of", slow)
    destination = tmp_path / "result.parquet"
    sink = _sink("file in order", destination)
    batch = book[:150].rechunk()
    watched = weakref.ref(batch)
    sink.write_batch(batch, rows=np.arange(150))
    del batch
    gc.collect()

    assert watched() is None
    sink.write_batch(book[150:], rows=np.arange(150, 300))
    sink.publish(DONE)
    assert_frame_equal(pl.read_parquet(destination), book)


@pytest.mark.parametrize("kind", ["frame in order", "file in order"])
@pytest.mark.parametrize(
    ("batches", "said"),
    [
        (
            [np.arange(0, 10), np.arange(11, 21)],
            "positions 11 to 20, where the book's next rows are 10 to 19",
        ),
        (
            [np.arange(0, 10), np.arange(5, 15)],
            "positions 5 to 14, where the book's next rows are 10 to 19",
        ),
        (
            [np.arange(10, 20)],
            "positions 10 to 19, where the book's next rows are 0 to 9",
        ),
        (
            [np.arange(0, 10), np.array([10, 12, 13])],
            "positions 10 to 13, where the book's next rows are 10 to 12",
        ),
    ],
    ids=["a gap", "a repeat", "not from the start", "a hole inside the batch"],
)
def test_a_batch_that_breaks_the_promise_of_order_is_refused_as_it_is_written(
    tmp_path: Path, kind: str, batches: list[np.ndarray], said: str
) -> None:
    """The promise is held against every batch, and a broken one leaves nothing."""
    book = _book(30)
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)
    *kept, broken = batches
    for rows in kept:
        sink.write_batch(book[rows], rows=rows)

    with pytest.raises(ValueError, match="promised its batches in the book") as refused:
        sink.write_batch(book[broken], rows=broken)

    assert said in str(refused.value)
    assert "defect in the engine" in str(refused.value)
    assert _beside(destination) == []
    assert _writers() == []
    with pytest.raises(RuntimeError, match="without being opened"):
        sink.publish(DONE)


@pytest.mark.parametrize("kind", ["frame in order", "file in order"])
@pytest.mark.parametrize(
    ("rows", "said"),
    [
        (np.array([8, 7, 6]), "ascend"),
        (np.array([6, 6, 7]), "ascend"),
        (np.array([6, 7]), "one position per row"),
        (np.array([[6, 7, 8]]), "one position per row"),
        (np.array([-1, 0, 1]), "below"),
        (np.array([6.0, 7.0, 8.0]), "whole numbers"),
    ],
    ids=["descending", "repeated", "short", "two-dimensional", "negative", "floats"],
)
def test_positions_a_batch_cannot_have_are_refused_under_a_promise_too(
    tmp_path: Path, kind: str, rows: np.ndarray, said: str
) -> None:
    """Checked at the door as on the staged route, before the promise is."""
    book = _book(9)
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)
    sink.write_batch(book[:3], rows=np.arange(3))
    sink.write_batch(book[3:6], rows=np.arange(3, 6))

    with pytest.raises(ValueError, match=said):
        sink.write_batch(book[6:9], rows=rows)

    assert _beside(destination) == []
    assert _writers() == []


def test_the_book_s_next_rows_keep_a_promise_of_order(tmp_path: Path) -> None:
    """Batches with no positions are the book's next rows, which is the promise."""
    book = _book(90)
    destination = tmp_path / "result.parquet"
    sink = _sink("file in order", destination)
    for at in range(0, book.height, 20):
        sink.write_batch(book[at : at + 20])
    sink.publish(DONE)

    assert_frame_equal(pl.read_parquet(destination), book)
    assert _beside(destination) == ["result.parquet"]


@pytest.mark.parametrize("handed", ["pyarrow", "bare-stream"])
def test_a_batch_in_order_handed_as_another_arrow_stream_is_written_through(
    tmp_path: Path, handed: str
) -> None:
    """A sink takes any Arrow producer's batch on this route too, in order."""
    book = _book(90)
    destination = tmp_path / "result.parquet"
    sink = _sink("file in order", destination)
    for at in range(0, book.height, 20):
        rows = np.arange(at, min(at + 20, book.height))
        table = book[rows].to_arrow()
        batch: ArrowStreamExportable = (
            table if handed == "pyarrow" else _OnlyAStream(table)
        )
        sink.write_batch(batch, rows=list(rows))
    sink.publish(DONE)

    assert_frame_equal(pl.read_parquet(destination), book)


def _third_batch(book: pl.DataFrame) -> int:
    """Return the first policy of the batch the failing tests fail in."""
    return int(book["policy_id"][100])


def test_a_writer_that_fails_mid_batch_leaves_nothing_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An error the source meets cutting the third batch comes out of ``write_batch``.

    As itself, not inside Polars' ``ComputeError``: what the writer's source
    met on Polars' own thread is kept, and that is what the engine's thread
    raises. Last quarter's result stands, and nothing of this run is beside
    it -- nor its writer.
    """
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", 2_000)
    book = _book(200)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"last quarter's result")
    sink = _sink("file in order", destination)
    cutting = protocol._piece_of  # noqa: SLF001 -- the copy under test

    def full_in_the_third(batch: pl.DataFrame, at: int, rows: int) -> pl.DataFrame:
        if int(batch["policy_id"][0]) == _third_batch(book):
            message = "No space left on device"
            raise OSError(message)
        return cutting(batch, at, rows)

    monkeypatch.setattr(protocol, "_piece_of", full_in_the_third)
    for at in (0, 50):
        sink.write_batch(book[at : at + 50], rows=np.arange(at, at + 50))
    with pytest.raises(OSError, match="No space left on device"):
        sink.write_batch(book[100:150], rows=np.arange(100, 150))

    assert destination.read_bytes() == b"last quarter's result"
    assert _beside(destination) == ["result.parquet"]
    assert _writers() == []
    with pytest.raises(RuntimeError, match="without being opened"):
        sink.publish(DONE)


def test_a_writer_that_fails_finishing_the_file_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An error Polars' writer raises finishing the file comes out of ``publish``.

    The error Polars' own writer meets, rather than one the source met, is
    raised as Polars raised it; the rename never happens.
    """
    book = _book(60)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"last quarter's result")
    sink = _sink("file in order", destination)
    writing = pl.LazyFrame.sink_parquet

    def full_at_the_end(
        frame: pl.LazyFrame, *arguments: object, **named: object
    ) -> None:
        writing(frame, *arguments, **named)  # type: ignore[arg-type]
        message = "No space left on device"
        raise OSError(message)

    monkeypatch.setattr(pl.LazyFrame, "sink_parquet", full_at_the_end)
    for at in range(0, book.height, 20):
        sink.write_batch(book[at : at + 20], rows=np.arange(at, at + 20))
    with pytest.raises(OSError, match="No space left on device"):
        sink.publish(DONE)

    assert destination.read_bytes() == b"last quarter's result"
    assert _beside(destination) == ["result.parquet"]
    assert _writers() == []


def test_an_interrupt_on_the_writer_s_thread_stays_an_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``KeyboardInterrupt`` met cutting a piece comes out of ``write_batch``."""
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", 2_000)
    book = _book(200)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"last quarter's result")
    sink = _sink("file in order", destination)
    cutting = protocol._piece_of  # noqa: SLF001 -- the copy under test

    def interrupted(batch: pl.DataFrame, at: int, rows: int) -> pl.DataFrame:
        if int(batch["policy_id"][0]) == _third_batch(book):
            raise KeyboardInterrupt
        return cutting(batch, at, rows)

    monkeypatch.setattr(protocol, "_piece_of", interrupted)
    for at in (0, 50):
        sink.write_batch(book[at : at + 50], rows=np.arange(at, at + 50))
    with pytest.raises(KeyboardInterrupt):
        sink.write_batch(book[100:150], rows=np.arange(100, 150))

    assert destination.read_bytes() == b"last quarter's result"
    assert _beside(destination) == ["result.parquet"]
    assert _writers() == []


def test_a_key_pressed_while_a_batch_is_written_stops_the_run_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SIGINT reaches the engine's thread while it waits for the writer, and ends it.

    Python delivers a key press to the main thread, which is why the engine's
    loop stays there and the writer is the one on a thread of its own: the
    wait for a batch to be taken is interrupted, and the run is abandoned
    while the writer is still cutting the batch rather than once it has
    taken it. The writer is then stopped and waited for, and last quarter's
    result stands alone.
    """
    book = _book(100)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"last quarter's result")
    sink = _sink("file in order", destination)
    cutting = protocol._piece_of  # noqa: SLF001 -- the copy under test
    main = threading.main_thread().ident
    assert main is not None
    assert threading.current_thread() is threading.main_thread()
    cut: list[float] = []

    def pressed(batch: pl.DataFrame, at: int, rows: int) -> pl.DataFrame:
        if int(batch["policy_id"][0]) == int(book["policy_id"][50]):
            signal.pthread_kill(main, signal.SIGINT)
            time.sleep(1.0)
            cut.append(time.perf_counter())
        return cutting(batch, at, rows)

    abandoning = ParquetSink.abandon
    abandoned: list[float] = []

    def timed(self: ParquetSink) -> None:
        abandoned.append(time.perf_counter())
        abandoning(self)

    monkeypatch.setattr(protocol, "_piece_of", pressed)
    monkeypatch.setattr(ParquetSink, "abandon", timed)
    sink.write_batch(book[:50], rows=np.arange(50))
    with pytest.raises(KeyboardInterrupt):
        sink.write_batch(book[50:], rows=np.arange(50, 100))

    assert abandoned
    assert cut
    assert abandoned[0] < cut[0]
    assert destination.read_bytes() == b"last quarter's result"
    assert _beside(destination) == ["result.parquet"]
    assert _writers() == []


def test_a_writer_that_fails_between_batches_refuses_the_next_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Polars' writer fails after the first batch was taken; the second is refused.

    The failure is Polars' own, met after ``write_batch`` had returned -- a
    piece it refuses once it has it -- so it is the next batch handed over
    that raises it, and the run leaves nothing behind.
    """
    book = _book(60)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"last quarter's result")
    sink = _sink("file in order", destination)
    cutting = protocol._piece_of  # noqa: SLF001 -- the copy under test

    def refused_by_polars(batch: pl.DataFrame, at: int, rows: int) -> pl.DataFrame:
        piece = cutting(batch, at, rows)
        return piece.with_columns(pl.col("reserve").cast(pl.Float32))

    monkeypatch.setattr(protocol, "_piece_of", refused_by_polars)
    sink.write_batch(book[:30], rows=np.arange(30))
    with pytest.raises(pl.exceptions.PolarsError):
        sink.write_batch(book[30:], rows=np.arange(30, 60))

    assert destination.read_bytes() == b"last quarter's result"
    assert _beside(destination) == ["result.parquet"]
    assert _writers() == []


# A key pressed at either end of the writer's life.


def _the_writer_ends(within: float = 10.0) -> list[str]:
    """Return the writer threads still running once they have had time to end."""
    deadline = time.monotonic() + within
    while _writers() and time.monotonic() < deadline:
        time.sleep(0.05)
    return _writers()


def test_a_key_pressed_as_the_writer_starts_leaves_no_writer_and_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Thread.start`` interrupted after the writer's thread was made.

    ``Thread.start`` waits for the new thread to say it is running, and a key
    pressed in that wait raises out of it with the thread already made. The
    sink holds the stream before starting it, so abandoning the run finds a
    stream to stop: the writer is told, waited for, and takes its file with
    it.
    """
    starting = threading.Thread.start

    def interrupted(thread: threading.Thread) -> None:
        starting(thread)
        if thread.name.startswith("gaspatchio writer"):
            raise KeyboardInterrupt

    monkeypatch.setattr(threading.Thread, "start", interrupted)
    book = _book(100)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"last quarter's result")
    sink = _sink("file in order", destination)

    with pytest.raises(KeyboardInterrupt):
        sink.write_batch(book[:50], rows=np.arange(50))

    assert _writers() == []
    assert destination.read_bytes() == b"last quarter's result"
    assert _beside(destination) == ["result.parquet"]


def test_a_key_pressed_before_the_writer_s_thread_is_made_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Thread.start`` interrupted before the thread was made: nothing to wait for.

    The thread will never say it is running, so abandoning waits for it only
    as long as a made thread takes to say so, and then removes the name.
    """

    def interrupted(thread: threading.Thread) -> None:
        del thread
        raise KeyboardInterrupt

    monkeypatch.setattr(threading.Thread, "start", interrupted)
    monkeypatch.setattr(protocol, "_STARTING", 0.3)
    book = _book(100)
    destination = tmp_path / "result.parquet"
    sink = _sink("file in order", destination)

    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        sink.write_batch(book[:50], rows=np.arange(50))

    # The wait for a thread to say it is running, not a hang.
    assert time.monotonic() - started < 5
    assert _writers() == []
    assert _beside(destination) == []


def test_a_writer_that_begins_after_its_name_was_removed_takes_its_file_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Polars opens the file after the sink removed the name, and it still goes.

    A key pressed as the writer starts, and a second as the run is
    abandoned, so the sink removes the name without waiting for the writer --
    which by then is on its way into Polars. Polars makes the file afresh.
    Told the run is abandoned, the writer removes it as it ends, where it
    would otherwise stand beside the destination for good.
    """
    beginning, removed = threading.Event(), threading.Event()
    starting = threading.Thread.start

    def interrupted(thread: threading.Thread) -> None:
        starting(thread)
        if thread.name.startswith("gaspatchio writer"):
            assert beginning.wait(10)
            raise KeyboardInterrupt

    registering = protocol.register_io_source

    def late(*arguments: object, **named: object) -> pl.LazyFrame:
        beginning.set()
        assert removed.wait(10)
        return registering(*arguments, **named)  # type: ignore[arg-type]

    pieces = protocol._Stream._pieces  # noqa: SLF001 -- the source under test

    def once_the_file_stands(
        stream: protocol._Stream,
        *arguments: object,
    ) -> Iterator[pl.DataFrame]:
        # A generator, so this runs when Polars first asks for a piece -- once
        # its query has begun and made the file -- rather than while the query
        # is built. The source then says the run is over.
        deadline = time.monotonic() + 10
        while not any(tmp_path.glob("*.unpublished")):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        yield from pieces(stream, *arguments)  # type: ignore[arg-type]

    def pressed_again(stream: protocol._Stream) -> None:
        del stream
        raise KeyboardInterrupt

    monkeypatch.setattr(threading.Thread, "start", interrupted)
    monkeypatch.setattr(protocol, "register_io_source", late)
    monkeypatch.setattr(protocol._Stream, "_pieces", once_the_file_stands)  # noqa: SLF001 -- as above
    monkeypatch.setattr(protocol._Stream, "stop", pressed_again)  # noqa: SLF001 -- as above
    book = _book(100)
    destination = tmp_path / "result.parquet"
    sink = _sink("file in order", destination)

    with pytest.raises(KeyboardInterrupt):
        sink.write_batch(book[:50], rows=np.arange(50))
    assert _beside(destination) == []
    removed.set()

    assert _the_writer_ends() == []
    assert _beside(destination) == []


# Two real key presses, in a process of their own: a SIGINT reaches Polars' own
# interrupt flag as well as Python's, and a writer left running would leave
# that flag set for every query the process runs after it. Each press is sent
# at a point the script reaches, never after a delay: the first once the
# writer's source is waiting for a batch, or from inside the writer's cut; the
# second as abandoning enters the writer's stop.
_TWO_PRESSES = """
import json, os, signal, sys, threading, time
from pathlib import Path

import numpy as np
import polars as pl

from gaspatchio.engines import protocol
from gaspatchio.engines.protocol import ParquetSink, ResultManifest

where, moment = Path(sys.argv[1]), sys.argv[2]
manifest = ResultManifest(
    scope="final-schema", columns={}, dtypes={}, row_identity=None,
    graph_fingerprint="sha256:" + "ab" * 32, inputs_digest="sha256:" + "cd" * 32,
    producer="stub", versions={},
)
main = threading.main_thread().ident
book = pl.DataFrame({"policy_id": np.arange(400), "reserve": np.arange(400) * 1.5})
destination = where / "result.parquet"
destination.write_bytes(b"last quarter's result")


def writers():
    return [
        t.name for t in threading.enumerate() if t.name.startswith("gaspatchio writer")
    ]


def in_the_source():
    # Every thread, Polars' own included, whose stack is inside the source.
    found = 0
    for frame in sys._current_frames().values():
        while frame is not None:
            if frame.f_code.co_name == "_next_piece":
                found += 1
                break
            frame = frame.f_back
    return found


def until(ready, within=10.0):
    deadline = time.monotonic() + within
    while not ready() and time.monotonic() < deadline:
        time.sleep(0.01)


sink = ParquetSink(destination)
sink.open(manifest, in_order=True)
sink.write_batch(book[:100], rows=np.arange(100))
stopping = protocol._Stream.stop


def pressed_again(stream):
    # The second press, landing as abandoning enters the writer's stop.
    signal.pthread_kill(main, signal.SIGINT)
    return stopping(stream)


protocol._Stream.stop = pressed_again
raised = []
try:
    try:
        if moment == "while the writer cuts a piece":
            cutting = protocol._piece_of

            def pressed(batch, at, rows):
                # The first press, while the engine waits for this cut.
                signal.pthread_kill(main, signal.SIGINT)
                time.sleep(0.5)
                return cutting(batch, at, rows)

            protocol._piece_of = pressed
            sink.write_batch(book[100:], rows=np.arange(100, 400))
        else:
            # The first press, while the engine computes the next batch and
            # the writer's source waits for it.
            until(in_the_source)
            signal.pthread_kill(main, signal.SIGINT)
            time.sleep(5)
    finally:
        sink.abandon()
except KeyboardInterrupt as error:
    raised.append(type(error).__name__)
until(lambda: not writers() and not in_the_source())
answered = "ok"
try:
    pl.LazyFrame({"a": [1, 2, 3]}).select(pl.col("a").sum()).collect()
except BaseException as error:
    answered = type(error).__name__
print(json.dumps({
    "raised": raised,
    "writers": writers(),
    "waiting_in_the_source": in_the_source(),
    "beside": sorted(one.name for one in where.iterdir()),
    "destination": destination.read_bytes().decode(errors="replace"),
    "polars_after": answered,
}))
sys.stdout.flush()
os._exit(0)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT is sent with pthread_kill")
@pytest.mark.parametrize(
    "moment", ["while the engine computes", "while the writer cuts a piece"]
)
def test_a_second_key_press_as_the_run_is_abandoned_still_stops_the_writer(
    tmp_path: Path, moment: str
) -> None:
    """Two real SIGINTs: the second lands as abandoning enters the writer's stop.

    The first press abandons the run; the second interrupts the abandoning
    before it can call the writer's stop, so the writer is never woken. It
    was told by a plain store before that call, and its source looks up
    every tenth of a second, so it stops, takes its file with it, and lets
    go of Polars' interrupt flag -- where it would otherwise wait for a batch
    for ever on a thread of Polars' own pool, holding the removed file open
    and leaving every later Polars query in the process to raise
    ``KeyboardInterrupt``.
    """
    finished = subprocess.run(  # noqa: S603 -- this interpreter, this tree's own script
        [sys.executable, "-c", _TWO_PRESSES, str(tmp_path), moment],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    read = json.loads(finished.stdout.strip().splitlines()[-1])

    assert read["raised"] == ["KeyboardInterrupt"]
    assert read["writers"] == []
    assert read["waiting_in_the_source"] == 0
    assert read["beside"] == ["result.parquet"]
    assert read["destination"] == "last quarter's result"
    assert read["polars_after"] == "ok"


@pytest.mark.parametrize("lost", ["the first", "a middle one", "the last"])
def test_a_piece_lost_on_the_way_into_the_file_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lost: str
) -> None:
    """The finished file is held to the rows handed over, as the staged parts are.

    The writer's source is made to lose one piece -- a stand-in for a defect
    between the sink and Polars' writer. Without the count the file would
    publish short and say nothing; with it, publication refuses, names both
    counts, and leaves last quarter's result as it was.
    """
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", 3_000)
    pieces = protocol._Stream._pieces  # noqa: SLF001 -- the source under test

    def losing(stream: protocol._Stream, *arguments: object) -> Iterator[pl.DataFrame]:
        # One piece is held back until the next arrives, so that the last can
        # be told from the rest.
        held: pl.DataFrame | None = None
        for at, piece in enumerate(pieces(stream, *arguments)):  # type: ignore[arg-type]
            if held is not None:
                yield held
            dropped = (lost == "the first" and at == 0) or (
                lost == "a middle one" and at == 2
            )
            held = None if dropped else piece
        if held is not None and lost != "the last":
            yield held

    monkeypatch.setattr(protocol._Stream, "_pieces", losing)  # noqa: SLF001 -- as above
    book = _book(400)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"last quarter's result")
    sink = _sink("file in order", destination)
    for at in range(0, book.height, 100):
        sink.write_batch(book[at : at + 100], rows=np.arange(at, at + 100))

    with pytest.raises(RuntimeError, match="rows were lost or doubled") as refused:
        sink.publish(DONE)

    assert "400 rows were handed over" in str(refused.value)
    assert destination.read_bytes() == b"last quarter's result"
    assert _beside(destination) == ["result.parquet"]
    assert _writers() == []


# A write the operating system refuses, in a process of its own: the file size
# limit applies to the whole process, and a write past it fails with EFBIG
# once the signal that would otherwise end the process is ignored.
_TOO_LARGE = """
import json, os, resource, signal, sys, threading
from pathlib import Path

import numpy as np
import polars as pl

from gaspatchio.engines.protocol import ParquetSink, ResultManifest
from gaspatchio.engines.report import RunReport

where, route = Path(sys.argv[1]), sys.argv[2]
manifest = ResultManifest(
    scope="final-schema", columns={}, dtypes={}, row_identity=None,
    graph_fingerprint="sha256:" + "ab" * 32, inputs_digest="sha256:" + "cd" * 32,
    producer="stub", versions={},
)
cells = np.random.default_rng(0).random(20_000 * 24)
book = pl.DataFrame({
    "policy_id": np.arange(20_000),
    "cashflows": pl.Series(cells).reshape((20_000, 24)).cast(pl.List(pl.Float64)),
})
destination = where / "result.parquet"
destination.write_bytes(b"last quarter's result")
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (1024**2, 1024**2))
sink = ParquetSink(destination)
sink.open(manifest, in_order=route == "in order")
raised = None
try:
    for at in range(0, 20_000, 5_000):
        sink.write_batch(book[at : at + 5_000], rows=np.arange(at, at + 5_000))
    sink.publish(RunReport(refusals=()))
except BaseException as error:
    raised = error
print(json.dumps({
    "raised": [kind.__name__ for kind in type(raised).__mro__] if raised else [],
    "message": str(raised),
    "beside": sorted(one.name for one in where.iterdir()),
    "destination": destination.read_bytes().decode(errors="replace"),
    "writers": [
        t.name for t in threading.enumerate() if t.name.startswith("gaspatchio writer")
    ],
}))
sys.stdout.flush()
os._exit(0)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="a file size limit needs resource")
@pytest.mark.parametrize("route", ["in order", "staged"])
def test_a_disk_that_refuses_a_write_leaves_nothing_and_says_what_it_said(
    tmp_path: Path, route: str
) -> None:
    """A real write failure, on either route: the file outgrows what the system allows.

    It is Polars' writer that meets it, so it comes out as Polars raised it --
    a ``ComputeError`` naming the operating system's error, EFBIG -- not as
    an ``OSError``: what the sink forwards as itself is what its own source
    raised. Last quarter's result stands, alone, and no writer is left.
    """
    finished = subprocess.run(  # noqa: S603 -- this interpreter, this tree's own script
        [sys.executable, "-c", _TOO_LARGE, str(tmp_path), route],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    read = json.loads(finished.stdout.strip().splitlines()[-1])

    assert read["raised"][:2] == ["ComputeError", "PolarsError"], read
    assert "File too large (os error 27)" in read["message"]
    assert read["destination"] == "last quarter's result"
    assert read["beside"] == ["result.parquet"]
    assert read["writers"] == []


@pytest.mark.parametrize("kind", ["file", "file in order"])
def test_the_file_is_written_by_polars_streaming_engine_whatever_the_session_prefers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """A session that prefers the in-memory engine does not move the file sink off it.

    Both routes bound what they hold by the streaming engine's own flight; in
    the in-memory engine a merge of the staged parts, or a run written
    straight through, would hold the whole book at once. So each asks for the
    streaming engine by name when it writes the result, and the session's
    ``POLARS_ENGINE_AFFINITY`` is not asked. (A staged part is written by
    ``DataFrame.write_parquet``, which names the streaming engine itself.)
    """
    monkeypatch.setenv("POLARS_ENGINE_AFFINITY", "in-memory")
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", 2_000)
    writing = pl.LazyFrame.sink_parquet
    engines: list[object] = []

    def recorded(frame: pl.LazyFrame, *arguments: object, **named: object) -> None:
        if str(arguments[0]).endswith(".unpublished"):
            engines.append(named.get("engine"))
        writing(frame, *arguments, **named)  # type: ignore[arg-type]

    monkeypatch.setattr(pl.LazyFrame, "sink_parquet", recorded)
    book = _book(300)
    destination = tmp_path / "result.parquet"
    sink = _sink(kind, destination)
    for at in range(0, book.height, 100):
        sink.write_batch(book[at : at + 100], rows=np.arange(at, at + 100))
    sink.publish(DONE)

    assert engines == ["streaming"]
    assert_frame_equal(pl.read_parquet(destination), book)
