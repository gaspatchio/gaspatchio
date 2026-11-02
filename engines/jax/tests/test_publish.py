# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Nothing partial is ever visible, and every row comes back where it stood.

A run that refuses at completion has done all the work. Every batch has been
computed and, since the engine streams, written away as it finished -- and the
one thing that must not happen is that those numbers are found later under
the name a finished result goes by, because a result on disk is a result
somebody will value a book from, and a partial one carries no sign that it is
partial.

So publication is one moment, reached down one of two routes. Where the
engine's batching plan hands the book over in its own order -- every book of
one timeline width -- it says so as it opens the sink, and each batch goes
straight into the one unpublished result. Where it does not, each batch is
staged as a part and the parts are put back in order at the end. Either way
the rename is the publication. What these tests hold is
the moment rather than the mechanism -- a refusal after batches were written,
a fault building a batch behind a refusal, an interrupt, a destination that
already holds a good result, two runs writing to one name at once -- down
both routes with the same books, and the order: policies computed group by
group come back where they stood in the book, whichever sink they went to.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from typing import TYPE_CHECKING

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from gaspatchio.engines import protocol
from gaspatchio.engines.protocol import FrameSink, ParquetSink, read_manifest
from gaspatchio.engines.report import EngineRefusal
from gaspatchio_jax import plan as plan_module
from gaspatchio_jax.plan import ExecutionPlan
from tests.conftest import PROJECT
from tests.helpers import a_read_that_misses, a_running_sum, streamed

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path

    import numpy as np
    from numpy.typing import ArrayLike

    from gaspatchio.engines.protocol import (
        ArrowStreamExportable,
        EngineResult,
        ResultManifest,
    )
    from gaspatchio.engines.report import RunReport
    from gaspatchio_jax.plan import Batched, Dispatched, Program, Settled

# Ten policies to a batch, three batches, and the miss in the second one: the
# point is that the run got past the first batch before it found anything
# wrong.
BATCH = 10
MISSES_AT = 15
POLICIES = 30

# A book of three widths -- four, twenty-four and forty-four periods, which
# round up to 12, 24 and 48 -- interleaved policy by policy, as a term book's
# are. Grouped by width and cut into batches of seven, it is several batches
# in each of three groups, none of them in the book's order.
JAGGED = [4 + (policy % 3) * 20 for policy in range(90)]

# The same widths with the book sorted by them: three groups, each an
# unbroken run of the book, so the batches arrive in its own order -- and its
# rows widen batch by batch, so it is staged all the same.
SORTED = sorted(JAGGED)

MODELS = PROJECT / "tests/models"

# How long, in seconds, a test's writer threads may take to end once it is
# over, and how long the file sink waits on a writer that takes no row and
# writes no byte -- a minute in a run, where nothing a test here writes takes
# a second.
WRITERS_END_WITHIN = 15.0
PATIENCE_UNDER_TEST = 10.0


@pytest.fixture(autouse=True)
def _no_writer_outlives_its_test(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail a test that leaves the file sink's writer running, once it has had time.

    Only the writers this test started: one an earlier test left running is
    that test's failure. Every wait is bounded -- the sink's own by the
    patience it is given here -- so a writer that never ends fails the test
    in seconds rather than hanging the run.
    """
    monkeypatch.setattr(protocol, "_PATIENCE", PATIENCE_UNDER_TEST)
    before = set(threading.enumerate())

    def left() -> list[str]:
        return sorted(
            one.name
            for one in threading.enumerate()
            if one.name.startswith(protocol._WRITER)  # noqa: SLF001 -- the sink's own name for them
            and one not in before
        )

    yield
    deadline = time.monotonic() + WRITERS_END_WITHIN
    while left() and time.monotonic() < deadline:
        time.sleep(0.05)
    if left():
        pytest.fail(
            f"the file sink's writer threads outlived this test by "
            f"{WRITERS_END_WITHIN:.0f} s: {left()}"
        )


def _beside(destination: Path) -> list[str]:
    """Return everything standing in the destination's own directory."""
    return sorted(one.name for one in destination.parent.iterdir())


def _out_of_order(groups: Sequence[np.ndarray]) -> bool:
    """Say the plan does not hand the book over in its own order, whatever it is."""
    del groups
    return False


@pytest.fixture(params=["in order", "staged"])
def route(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a test down each of the file sink's two routes, with the same book.

    A book of one timeline width arrives in its own order, the engine says so
    as it opens the sink, and every batch goes straight into the one result.
    Telling the engine its plan is out of order sends the very same batches
    down the staged route, parts and all -- the route every book whose widths
    interleave takes.
    """
    if request.param == "staged":
        monkeypatch.setattr(plan_module, "in_the_books_order", _out_of_order)
    return str(request.param)


class _Staged(ParquetSink):
    """A file sink that remembers its names, its promise, and what it wrote.

    ``working`` is, after each batch, how many files the run had beside the
    destination: its parts on the staged route, its one result in the
    book's order.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.reserved: list[Path] = []
        self.staging: list[Path | None] = []
        self.promised: list[bool] = []
        self.written = 0
        self.working: list[int] = []

    def open(self, manifest: ResultManifest, *, in_order: bool = False) -> None:
        super().open(manifest, in_order=in_order)
        assert self._temporary is not None
        self.reserved.append(self._temporary)
        self.staging.append(self._staging)
        self.promised.append(in_order)

    def write_batch(
        self, frame: ArrowStreamExportable, *, rows: ArrayLike | None = None
    ) -> None:
        super().write_batch(frame, rows=rows)
        self.written += 1
        staging = self.staging[-1]
        if staging is None:
            self.working.append(int(self.reserved[-1].exists()))
        else:
            self.working.append(len(list(staging.iterdir())) if staging.exists() else 0)


def test_order_across_width_groups_and_batches_is_the_book_s_on_both_sinks(
    tmp_path: Path,
) -> None:
    """Three groups, several batches each, and the same answer four ways.

    The frame sink and the file sink, each handed the batches as the engine
    computed them; the same book with each group in one batch; and Polars'
    own running sum over the book. All four are one frame, in the book's
    order. The widths interleave, so the plan cannot promise the book's
    order and the file sink stages a part a batch.
    """
    one = a_running_sum(len(JAGGED), JAGGED)
    destination = tmp_path / "result.parquet"
    in_memory = streamed(one, FrameSink(), batch=7).columns
    on_disk = _Staged(destination)
    streamed(one, on_disk, batch=7)
    whole = streamed(one, FrameSink()).columns
    reference = one.inputs.with_columns(
        pl.col("flow").list.eval(pl.element().cum_sum()).alias("answer")
    )

    assert on_disk.promised == [False]
    assert on_disk.written > len({12, 24, 48})
    assert on_disk.working[-1] == on_disk.written
    assert_frame_equal(pl.read_parquet(destination), in_memory, check_exact=True)
    assert_frame_equal(in_memory, whole, check_exact=True)
    assert_frame_equal(in_memory, reference, check_exact=True)
    assert _beside(destination) == ["result.parquet"]


def _row_groups(path: Path) -> list[int]:
    """Return how many rows each row group of a Parquet file holds."""
    import pyarrow.parquet as pq

    layout = pq.ParquetFile(path).metadata
    return [layout.row_group(at).num_rows for at in range(layout.num_row_groups)]


def test_a_book_whose_rows_widen_is_staged_in_the_layout_it_always_had(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sorted by width, shortest first: in its own order, and staged all the same.

    Written straight through, the file's row groups would be sized from the
    first batch's narrow rows and swell as the rows widened -- at 400,000
    level-4 policies, groups of up to 860 MiB where a block is 64 MiB. So the
    plan promises the book's order only where every policy has one timeline
    on every axis, and this book is staged as before the file sink could
    write straight through: every row group a block of its widest rows, the
    layout of a run whose route is chosen for it, and the frame sink's answer
    and Polars' own.
    """
    monkeypatch.setattr(protocol, "_BLOCK_BYTES", 4_000)
    one = a_running_sum(len(SORTED), SORTED)
    widening, staged = tmp_path / "widening.parquet", tmp_path / "staged.parquet"
    on_disk = _Staged(widening)
    streamed(one, on_disk, batch=7)
    monkeypatch.setattr(plan_module, "in_the_books_order", _out_of_order)
    streamed(one, _Staged(staged), batch=7)
    in_memory = streamed(one, FrameSink(), batch=7).columns
    reference = one.inputs.with_columns(
        pl.col("flow").list.eval(pl.element().cum_sum()).alias("answer")
    )

    assert on_disk.promised == [False]
    assert on_disk.working[-1] == on_disk.written
    assert len(_row_groups(widening)) > 1
    assert _row_groups(widening) == _row_groups(staged)
    assert widening.read_bytes() == staged.read_bytes()
    assert_frame_equal(pl.read_parquet(widening), in_memory, check_exact=True)
    assert_frame_equal(in_memory, reference, check_exact=True)


@pytest.mark.parametrize(
    ("lengths", "promised"),
    [
        ([8] * 40, True),
        ([4 + (policy % 2) for policy in range(40)], False),
        (SORTED, False),
        (JAGGED, False),
        ([], True),
    ],
    ids=[
        "one timeline",
        "two timelines of one width",
        "sorted by width",
        "interleaved widths",
        "an empty book",
    ],
)
def test_the_sink_is_told_the_order_the_plan_hands_the_book_over_in(
    tmp_path: Path, lengths: list[int], *, promised: bool
) -> None:
    """The promise comes from the batching plan, before the first batch.

    Only where the book arrives in its own order and its rows cannot widen:
    every policy the same timeline on every axis. Four and five periods
    round up to one width and one program, but the second batch's rows could
    be longer than the first's.
    """
    destination = tmp_path / "result.parquet"
    sink = _Staged(destination)
    streamed(a_running_sum(len(lengths), lengths), sink, batch=7)

    assert sink.promised == [promised]
    assert pl.read_parquet(destination).height == len(lengths)
    assert _beside(destination) == ["result.parquet"]


def test_the_stream_groups_the_book_once_for_its_promise_and_its_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The order promised and the batches run come from one grouping of the book.

    Grouping reads every policy's widths -- at ten million policies it was the
    largest single cost of a run before it was vectorised -- so the stream
    settles it once, tells its sink from it, and hands the same groups to the
    batch loop rather than grouping the book a second time.
    """
    grouping = plan_module.grouped
    grouped_at: list[int] = []

    def counted(*arguments: object) -> list[np.ndarray]:
        found = grouping(*arguments)  # type: ignore[arg-type]
        grouped_at.append(len(found))
        return found

    monkeypatch.setattr(plan_module, "grouped", counted)
    answered = streamed(a_running_sum(len(SORTED), SORTED), FrameSink(), batch=7)

    assert grouped_at == [len({12, 24, 48})]
    assert answered.columns.height == len(SORTED)


def test_a_second_batch_refusal_leaves_nothing_at_the_destination(
    tmp_path: Path, route: str
) -> None:
    """The run computed every batch, refused, and wrote nothing anybody can read."""
    destination = tmp_path / "result.parquet"
    one = a_read_that_misses(POLICIES, MISSES_AT)
    sink = _Staged(destination)
    with pytest.raises(EngineRefusal) as refused:
        streamed(one, sink, batch=BATCH)
    assert "lookup.miss_raise" in refused.value.report.render()
    assert refused.value.report.closing_sentence() == "No results were published."
    assert sink.promised == [route == "in order"]
    assert not destination.exists()
    assert _beside(destination) == []


def test_a_refusal_in_the_last_batch_after_earlier_ones_were_written_leaves_nothing(
    tmp_path: Path, route: str
) -> None:
    """Two batches written, the third refuses, and none of it remains.

    Not the temporary, not the staging directory, not a part: the batches that
    were written were written into a result nobody could see -- two parts on
    the staged route, the one result in the book's order -- and a refusal
    takes that result away with it.
    """
    destination = tmp_path / "result.parquet"
    sink = _Staged(destination)
    with pytest.raises(EngineRefusal) as refused:
        streamed(a_read_that_misses(POLICIES, POLICIES - 3), sink, batch=BATCH)

    assert refused.value.report.closing_sentence() == "No results were published."
    assert sink.written == 2
    assert sink.working == ([1, 2] if route == "staged" else [1, 1])
    assert not destination.exists()
    assert _beside(destination) == []


def test_a_run_already_refused_writes_nothing_more_and_still_counts_every_batch(
    tmp_path: Path, route: str
) -> None:
    """A miss in the first batch: no batch is written, and the third's is counted.

    Once the findings so far refuse, nothing can be published, so nothing is
    built or written for it -- but every batch still runs, because the report
    owes the reader every cell, not the first one found.
    """
    del route
    destination = tmp_path / "result.parquet"
    sink = _Staged(destination)
    with pytest.raises(EngineRefusal) as refused:
        streamed(a_read_that_misses(POLICIES, 3, POLICIES - 3), sink, batch=BATCH)

    (refusal,) = refused.value.report.refusals
    assert refusal.count == 2
    assert sink.written == 0
    assert _beside(destination) == []


def _faulting_first_build(
    monkeypatch: pytest.MonkeyPatch,
) -> list[int]:
    """Make building the first batch's columns fail; return the build count."""
    building = plan_module._published  # noqa: SLF001 -- the build under test
    built: list[int] = []

    def faulting(*arguments: object) -> pl.DataFrame:
        built.append(len(built))
        if len(built) == 1:
            message = "a defect building the first batch's columns"
            raise RuntimeError(message)
        return building(*arguments)  # type: ignore[arg-type]

    monkeypatch.setattr(plan_module, "_published", faulting)
    return built


def _counted_regions(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count every batch the regions run for: every batch handed to a program."""
    running = ExecutionPlan.stage_dispatch
    ran: list[int] = []

    def counted(self: ExecutionPlan, settled: Settled, program: Program) -> Dispatched:
        ran.append(settled.count)
        return running(self, settled, program)

    monkeypatch.setattr(ExecutionPlan, "stage_dispatch", counted)
    return ran


def test_a_build_fault_waits_behind_a_refusal_in_a_later_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """The refusal is the run's answer; the defect is not allowed in front of it.

    The first batch's columns fail to build. The two batches after it still
    run, for their findings only, and the refusal they carry -- two misses,
    one in each -- is what the run says.
    """
    del route
    built = _faulting_first_build(monkeypatch)
    ran = _counted_regions(monkeypatch)
    destination = tmp_path / "result.parquet"
    one = a_read_that_misses(POLICIES, MISSES_AT, POLICIES - 3)
    with pytest.raises(EngineRefusal) as refused:
        streamed(one, _Staged(destination), batch=BATCH)

    (refusal,) = refused.value.report.refusals
    assert refusal.count == 2
    assert ran == [BATCH, BATCH, BATCH]
    assert built == [0]
    assert _beside(destination) == []


def test_a_build_fault_with_nothing_refused_is_raised_once_every_batch_has_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """No refusal to stand in front of it, so the defect is the run's answer.

    Raised at completion, after every batch has been checked, and with
    nothing written after it: a result missing a batch is not a result.
    """
    del route
    built = _faulting_first_build(monkeypatch)
    ran = _counted_regions(monkeypatch)
    destination = tmp_path / "result.parquet"
    sink = _Staged(destination)
    with pytest.raises(RuntimeError, match="building the first batch"):
        streamed(a_running_sum(POLICIES, 8), sink, batch=BATCH)

    assert ran == [BATCH, BATCH, BATCH]
    assert built == [0]
    assert sink.written == 0
    assert _beside(destination) == []


@pytest.mark.parametrize("after", [1, 2], ids=["one batch written", "two written"])
def test_an_interrupt_from_the_sink_mid_run_leaves_nothing(
    tmp_path: Path, after: int, route: str
) -> None:
    """Not a refusal and still not a half-written file.

    A refusal is the ordinary case and the report is what it is for. An
    interrupt is not: it is somebody pressing a key, and the sink has no
    report to hand them -- but the destination is in exactly the same state
    either way, whichever route the batches took and however many of them
    had been written.
    """
    destination = tmp_path / "result.parquet"
    sink = _Staged(destination)
    taking = sink.write_batch

    def stop(frame: ArrowStreamExportable, *, rows: ArrayLike | None = None) -> None:
        taking(frame, rows=rows)
        if sink.written == after:
            raise KeyboardInterrupt

    sink.write_batch = stop  # type: ignore[method-assign]
    with pytest.raises(KeyboardInterrupt):
        streamed(a_running_sum(POLICIES, 8), sink, batch=BATCH)
    assert sink.written == after
    assert sink.promised == [route == "in order"]
    assert not destination.exists()
    assert _beside(destination) == []


@pytest.mark.parametrize("depth", [0, 1], ids=["one after another", "one ahead"])
def test_an_interrupt_from_a_lowering_mid_run_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str, depth: int
) -> None:
    """Batches written, then a key pressed while the last batch's program is built.

    Twenty-five policies in batches of ten: the last, of five, is a program of
    its own. Run each batch after the one before it -- the CPU's own depth --
    it is built after two batches have gone into the result, or into their
    parts on the staged route; run one batch ahead -- a card's -- it is built
    while the second computes, after one. Both depths are named, so the
    interrupt lands mid-run on every backend rather than on the device's
    default alone.
    """
    destination = tmp_path / "result.parquet"
    sink = _Staged(destination)
    lowering = ExecutionPlan.lower

    def interrupted(self: ExecutionPlan, *arguments: object) -> object:
        if sink.written >= 2 - depth:
            raise KeyboardInterrupt
        return lowering(self, *arguments)  # type: ignore[arg-type]

    monkeypatch.setattr(ExecutionPlan, "lower", interrupted)
    with pytest.raises(KeyboardInterrupt):
        streamed(a_running_sum(25, 8), sink, batch=BATCH, depth=depth)
    assert sink.written >= 2 - depth
    assert sink.promised == [route == "in order"]
    assert max(sink.working) >= (2 - depth if route == "staged" else 1)
    assert not destination.exists()
    assert _beside(destination) == []


def test_a_batch_handed_at_the_wrong_positions_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """An engine defect in the positions is caught at the sink, and costs nothing.

    The last batch is handed one row further along the book than it stands.
    In the book's order the sink refuses it as it comes, a batch that breaks
    the promise; staged, it counts at publication one position missing and
    one past the end. Either way it says so and leaves nothing behind.
    """
    running = ExecutionPlan.stage_finish
    ran: list[int] = []

    def shifted(self: ExecutionPlan, *arguments: object) -> Batched:
        batched = running(self, *arguments)  # type: ignore[arg-type]
        ran.append(int(batched.rows.size))
        if len(ran) == POLICIES // BATCH:
            return replace(batched, rows=batched.rows + 1)
        return batched

    monkeypatch.setattr(ExecutionPlan, "stage_finish", shifted)
    destination = tmp_path / "result.parquet"
    said = (
        ("1 position is missing", "1 row stands past the end")
        if route == "staged"
        else ("promised its batches in the book's own order", "positions 21 to 30")
    )
    with pytest.raises(ValueError, match=said[0]) as defect:
        streamed(a_running_sum(POLICIES, 8), ParquetSink(destination), batch=BATCH)

    assert said[1] in str(defect.value)
    assert _beside(destination) == []


def test_an_existing_result_is_replaced_only_when_the_run_finishes(
    tmp_path: Path, route: str
) -> None:
    """A refusal leaves last quarter's answer standing, unchanged and readable."""
    del route
    destination = tmp_path / "result.parquet"
    streamed(a_running_sum(POLICIES, 8), ParquetSink(destination), batch=BATCH)
    standing = destination.read_bytes()
    assert read_manifest(destination).producer == "jax"
    with pytest.raises(EngineRefusal):
        streamed(
            a_read_that_misses(POLICIES, POLICIES - 3),
            ParquetSink(destination),
            batch=BATCH,
        )
    assert destination.read_bytes() == standing
    assert _beside(destination) == ["result.parquet"]


def test_a_finished_run_replaces_the_destination_and_carries_its_manifest(
    tmp_path: Path, route: str
) -> None:
    """The other half of the same rule: on success, the new answer is there."""
    del route
    destination = tmp_path / "result.parquet"
    streamed(a_running_sum(POLICIES, 8), ParquetSink(destination), batch=BATCH)
    first = pl.read_parquet(destination)
    streamed(a_running_sum(POLICIES + 5, 8), ParquetSink(destination), batch=BATCH)
    second = pl.read_parquet(destination)
    assert first.height == POLICIES
    assert second.height == POLICIES + 5
    assert read_manifest(destination).graph_fingerprint


def test_two_runs_to_one_destination_reserve_separate_staging(
    tmp_path: Path, route: str
) -> None:
    """Neither takes the other's rows, and the last to finish is what stands.

    Two runs of one model to one name is an ordinary thing to do by accident
    -- two terminals, one output path. Each reserves its *own* working file,
    and on the staged route its own staging directory, which is what the uuid
    in the names is for, so the only thing the two share is the moment each
    renames its own into place. Asserted on the names each reserved rather
    than on the end state: two runs that had written into one file would
    leave exactly the same directory behind, and one of them would carry the
    other's rows.
    """
    destination = tmp_path / "result.parquet"
    short, long = a_running_sum(POLICIES, 8), a_running_sum(POLICIES + 7, 8)
    first, second = _Staged(destination), _Staged(destination)
    ready: list[tuple[ExecutionPlan, object, _Staged, object]] = []
    for one, sink in ((short, first), (long, second)):
        plan = ExecutionPlan.stage_inspect(one.document)
        prepared = plan.stage_prepare(plan.stage_validate_inputs(one.inputs))
        ready.append(
            (plan, plan.stage_stream(prepared, sink, batch=BATCH), sink, prepared)
        )
    # Both runs are computed and written to the last batch before either
    # publishes, which is the case two terminals on one output path produce.
    staged = len(list(tmp_path.glob("*.unpublished.d")))
    results = len(list(tmp_path.glob("*.unpublished")))
    assert (staged, results) == ((2, 0) if route == "staged" else (0, 2))
    for plan, stream, sink, prepared in ready:
        published: EngineResult = plan.stage_complete(stream, sink, prepared)  # type: ignore[arg-type]
        assert published.manifest.producer == "jax"
    assert first.reserved[0] != second.reserved[0]
    assert first.reserved[0].name.endswith(".unpublished")
    if route == "staged":
        assert first.staging[0] != second.staging[0]
        assert str(first.staging[0]).endswith(".unpublished.d")
    assert pl.read_parquet(destination).height == POLICIES + 7
    assert _beside(destination) == ["result.parquet"]


def test_a_run_s_report_names_where_its_values_went(tmp_path: Path, route: str) -> None:
    """The file door hands back the schema and a note, not the book."""
    del route
    destination = tmp_path / "result.parquet"
    published = streamed(
        a_running_sum(POLICIES, 8), ParquetSink(destination), batch=BATCH
    )
    report: RunReport = published.report
    assert published.columns.height == 0
    assert published.columns.columns == ["flow", "answer"]
    assert any(str(destination) in note for note in report.notes)


def _every_node(
    model: str, book: pl.DataFrame, sink: _Staged, batch: int | None
) -> None:
    """Publish every node of one shipped model over a book, through one sink."""
    document = json.loads((MODELS / f"{model}.artifact.json").read_text("utf-8"))
    plan = ExecutionPlan.stage_inspect(document, every_node=True)
    settled = False
    try:
        prepared = plan.stage_prepare(plan.stage_validate_inputs(book))
        stream = plan.stage_stream(prepared, sink, batch=batch)
        plan.stage_complete(stream, sink, prepared)
        settled = True
    finally:
        if not settled:
            sink.abandon()


@pytest.mark.parametrize(
    ("model", "policies", "batch"),
    [
        ("level-4", 1000, 300),
        ("level-5", 1000, 300),
        ("level-4", 1000, None),
        ("level-4", 0, None),
    ],
    ids=["level 4 in four batches", "level 5 in four batches", "one batch", "empty"],
)
def test_both_routes_publish_the_same_result_for_every_node(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model: str,
    policies: int,
    batch: int | None,
) -> None:
    """Rows, values, types and footer: written straight through or staged, one result.

    Every node of a shipped model, which is every column type the engine
    publishes -- per-policy and per-period, numbers, dates, text -- over its
    own thousand-policy book, in several batches and in one, and over the
    empty book. The file itself may be laid out in other row groups; what a
    reader gets from it may not differ in a single cell or a single key of
    the footer.
    """
    book = pl.read_parquet(MODELS / f"{model}.book.parquet").head(policies)
    straight, staged = tmp_path / "straight.parquet", tmp_path / "staged.parquet"
    through = _Staged(straight)
    _every_node(model, book, through, batch)
    monkeypatch.setattr(plan_module, "in_the_books_order", _out_of_order)
    parts = _Staged(staged)
    _every_node(model, book, parts, batch)

    assert (through.promised, parts.promised) == ([True], [False])
    assert through.written == parts.written
    assert_frame_equal(
        pl.read_parquet(straight), pl.read_parquet(staged), check_exact=True
    )
    assert pl.read_parquet(straight).height == policies
    assert pl.read_parquet_metadata(straight) == pl.read_parquet_metadata(staged)
