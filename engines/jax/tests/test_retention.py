# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A batch's values do not outlive it: the engine keeps none once it is written.

Streaming's memory property, and the one the rest of it stands on: a book
larger than memory runs because a batch's columns are let go of as soon as
they are written. Nothing about the answer shows it -- a run that kept every
batch publishes the same numbers -- so it is held here directly.

Every array a batch holds on the device is watched by weak reference, from
the moment the batch is handed to its program (``stage_dispatch``): the columns
its program returned; every check's count and first caught cell, which the
program hands back in one array; and a coarse check's mask and the
operands its exact judgement reads -- the program's and the settlement's.
Before the card counted, every mask came back whole, and under a fold that returns
only the columns folded the masks were most of a batch (on level 4, 4.8 KB a
policy of checks against 0.7 KB of columns); a coarse check's still do, so a
watch that saw only columns would miss what a kept batch keeps. **What may be
alive there is the batches still in flight, and nothing older**: the
card computes the next batch while the host reads this one back, so when batch
*k + 1* is dispatched, batch *k* is on the card and may be alive -- but
nothing of batch *k - 1* may be. Run one at a time (depth nought), not even
batch *k* may be. When completion begins, nothing of any batch may be alive.
Garbage collection is off while the watch runs, so a value kept in a reference
cycle counts as kept: the property is that the engine lets go of a batch, not
that the collector eventually cleans up after it.

**The loop is driven through a table of consumers**, one row per way the
engine's batches are taken: into the frame sink, into the file sink down each
of its two routes -- staged, and straight into the one result where the book
arrives in its own order -- after a refusal (when later batches run for their
findings and are never built), and with a fault building a batch's columns
held behind the rest -- and the same
three ways for a fold into aggregators, which reads each batch's
partials and builds no columns at all. Two more run a book whose program
carries a coarse check -- its count, its mask and its operands -- written and
folded, so that the watch is seen to watch them. Each brings its own book and
names the stage its batches end in: completion for the stream, and the fold's
own completion for a fold. Every row runs at both depths.
"""

from __future__ import annotations

import gc
import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from gaspatchio.engines.protocol import FrameSink, ParquetSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.scenarios import PeriodMax, PeriodSum, Sum
from gaspatchio_jax import aggregate as aggregate_module
from gaspatchio_jax import plan as plan_module
from gaspatchio_jax.plan import ExecutionPlan
from tests.conftest import invocation
from tests.helpers import a_read_that_misses, a_running_sum, streamed

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from gaspatchio_jax.plan import Batched, Dispatched, Program, Settled
    from gaspatchio_jax.typed import Value
    from gaspatchio_jax.vectors import Invocation

# A book of three widths interleaved policy by policy, cut into batches of
# seven: several batches in each of three groups, and three compiled programs.
JAGGED = [4 + (policy % 3) * 20 for policy in range(90)]
BATCH = 7

# The two depths the engine runs at: one batch at a time, and one ahead.
DEPTHS = (0, 1)


@dataclass
class Watch:
    """Every batch's arrays by weak reference, and what was alive where.

    Attributes:
        depth: How many batches the run dispatches ahead of the one it hands
            over -- the batches that may still be in flight at a dispatch.
        batches: Per batch the engine dispatched, a weak reference to each
            array it holds on the device: its columns, its checks' counts,
            and its coarse checks' masks and operands.
        seen: At each point checked, how many arrays were still alive of the
            batches that should be gone by then -- which must be none.
        ends: The stage the consumer's batches end in, as it named it.
        columns: Per batch, how many of the arrays watched are its columns
            -- the values a consumer takes, and so the ones it could keep.
        counted: How many checks' counts were watched, over every batch.
        masks: How many checks' masks were watched, over every batch.
        operands: How many coarse checks' operands were watched.

    """

    depth: int
    batches: list[list[weakref.ref[object]]] = field(default_factory=list)
    seen: list[tuple[str, int]] = field(default_factory=list)
    ends: str | None = None
    columns: list[int] = field(default_factory=list)
    counted: int = 0
    masks: int = 0
    operands: int = 0

    def at(self, where: str, *, in_flight: int = 0) -> None:
        """Count, here, the arrays still alive of every batch that should be gone.

        ``in_flight`` is how many of the latest batches may still be on the
        card, and are not counted.
        """
        gone = self.batches[: max(len(self.batches) - in_flight, 0)]
        alive = sum(one() is not None for batch in gone for one in batch)
        self.seen.append((where, alive))

    def before(self, owner: object, name: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """Check, as ``owner.name`` begins, that no batch dispatched is alive.

        How a consumer names the stage its batches end in: completion for the
        stream, and the fold's own completion for a fold. The owner is the
        class or the module the stage is looked up on.
        """
        self.ends = name
        running = getattr(owner, name)

        def checked(*arguments: object, **named: object) -> object:
            self.at(name)
            return running(*arguments, **named)

        monkeypatch.setattr(owner, name, checked)


@pytest.fixture(params=DEPTHS, ids=["one at a time", "one ahead"])
def watch(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Watch]:
    """Return a watch on every batch dispatched, at a depth, the collector off."""
    watched = Watch(depth=request.param)
    running = ExecutionPlan.stage_dispatch

    def dispatching(
        self: ExecutionPlan, settled: Settled, program: Program
    ) -> Dispatched:
        watched.at(f"before batch {len(watched.batches)}", in_flight=watched.depth)
        dispatched = running(self, settled, program)
        masks = [
            *dispatched.coarse_masks,
            *(entry.mask for entry in dispatched.flags.entries),
        ]
        operands = [
            *(one for carried in dispatched.coarse_operands for one in carried),
            *(one for entry in dispatched.flags.entries for one in entry.operands),
        ]
        watched.columns.append(len(dispatched.columns))
        watched.counted += int(dispatched.tallies.shape[-1])
        watched.masks += len(masks)
        watched.operands += len(operands)
        watched.batches.append(
            [
                weakref.ref(array)
                for array in (
                    *dispatched.columns.values(),
                    dispatched.tallies,
                    *masks,
                    *operands,
                )
            ]
        )
        return dispatched

    monkeypatch.setattr(ExecutionPlan, "stage_dispatch", dispatching)
    collecting = gc.isenabled()
    gc.disable()
    try:
        yield watched
    finally:
        if collecting:
            gc.enable()


def _jagged() -> Invocation:
    """Return the book most consumers run: three widths, interleaved."""
    return a_running_sum(len(JAGGED), JAGGED)


def _checked() -> Invocation:
    """Return a book whose program carries a coarse check: a product of whole numbers.

    An integer product's range cannot be tested exactly inside a trace whose
    widest type is the one being tested, so beside its count the check hands
    back a mask and the two operands its exact judgement reads
    (:mod:`gaspatchio_jax.checks`). Nothing here leaves the range, so the run
    publishes.
    """
    policies = len(JAGGED)
    return invocation(
        {
            "op": "binop",
            "kind": "mul",
            "left": {"op": "col", "name": "a"},
            "right": {"op": "col", "name": "b"},
        },
        {
            "a": {"dtype": "i64", "values": list(range(policies))},
            "b": {
                "dtype": "i64",
                "values": [1 + policy % 7 for policy in range(policies)],
            },
        },
        "i64",
    )


def _into_the_frame_sink(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the batches the frame door's way, into a sink that holds them as rows."""
    del tmp_path
    watch.before(ExecutionPlan, "stage_complete", monkeypatch)
    streamed(_jagged(), FrameSink(), batch=BATCH, depth=watch.depth)


def _into_the_file_sink(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the batches the file door's way, each staged on disk as it finishes."""
    watch.before(ExecutionPlan, "stage_complete", monkeypatch)
    streamed(
        _jagged(),
        ParquetSink(tmp_path / "result.parquet"),
        batch=BATCH,
        depth=watch.depth,
    )


def _into_the_file_sink_in_order(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run a book of one width the file door's way: each batch into the result.

    The book arrives in its own order, so every batch goes straight into the
    one unpublished result through Polars' writer, on a thread of its own.
    """
    watch.before(ExecutionPlan, "stage_complete", monkeypatch)
    streamed(
        a_running_sum(len(JAGGED), 8),
        ParquetSink(tmp_path / "result.parquet"),
        batch=BATCH,
        depth=watch.depth,
    )


def _after_a_refusal(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse in the first batch; run the rest for their findings, never built.

    A batch that is never built still has every value in it when the next
    batch is computed, so letting go of the batch itself is what frees them.
    """
    watch.before(ExecutionPlan, "stage_complete", monkeypatch)
    with pytest.raises(EngineRefusal):
        streamed(
            a_read_that_misses(len(JAGGED), 3),
            ParquetSink(tmp_path / "result.parquet"),
            batch=BATCH,
            depth=watch.depth,
        )
    # The read's checks are exact, so they travel as counts in one array, and
    # the watch watched it.
    assert watch.counted


def _with_a_build_fault_held(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail building the first batch's columns; run the rest for their findings.

    The fault is raised from a frame holding the value it was building, as a
    real defect's would be. Held until completion, its traceback must not
    keep that batch alive while every later batch runs.
    """

    def faulting(name: str, value: Value, dictionary: object) -> object:
        del dictionary
        message = f"a defect building {name} from {value.carrier} cells"
        raise RuntimeError(message)

    monkeypatch.setattr(plan_module, "_as_series", faulting)
    watch.before(ExecutionPlan, "stage_complete", monkeypatch)
    with pytest.raises(RuntimeError, match="a defect building"):
        streamed(
            _jagged(),
            ParquetSink(tmp_path / "result.parquet"),
            batch=BATCH,
            depth=watch.depth,
        )


def _into_a_fold(tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fold the batches into aggregators: partials read, no column ever built."""
    del tmp_path
    watch.before(aggregate_module, "completed", monkeypatch)
    one = _jagged()
    aggregate_module.aggregate(
        one.document,
        one.inputs,
        [PeriodSum("answer").alias("total"), PeriodMax("flow").alias("most")],
        batch=BATCH,
        depth=watch.depth,
    )


def _a_fold_after_a_refusal(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse in the first batch; fold nothing more, and let every batch go."""
    del tmp_path
    watch.before(aggregate_module, "completed", monkeypatch)
    one = a_read_that_misses(len(JAGGED), 3)
    with pytest.raises(EngineRefusal):
        aggregate_module.aggregate(
            one.document,
            one.inputs,
            [Sum("answer").alias("total")],
            batch=BATCH,
            depth=watch.depth,
        )
    assert watch.counted


def _a_fold_with_a_fault_held(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail queuing the first batch's partial; run the rest for their findings.

    Raised from a frame holding the cells it was folding, as a real defect's
    would be -- and, one batch ahead, raised while that batch is still on the
    card, held with it until its turn. Held until completion, its traceback
    must not keep that batch alive while every later batch runs.
    """
    del tmp_path

    def faulting(cells: object, *arguments: object, **named: object) -> object:
        del arguments, named
        message = f"a defect folding {getattr(cells, 'shape', None)} cells"
        raise RuntimeError(message)

    monkeypatch.setattr(aggregate_module, "_partials", faulting)
    watch.before(aggregate_module, "completed", monkeypatch)
    one = _jagged()
    with pytest.raises(RuntimeError, match="a defect folding"):
        aggregate_module.aggregate(
            one.document,
            one.inputs,
            [PeriodSum("answer").alias("total")],
            batch=BATCH,
            depth=watch.depth,
        )


def _a_checked_book_written(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Write a book whose coarse check carries a mask and operands, and publish it."""
    watch.before(ExecutionPlan, "stage_complete", monkeypatch)
    streamed(
        _checked(),
        ParquetSink(tmp_path / "result.parquet"),
        batch=BATCH,
        depth=watch.depth,
    )
    assert watch.counted
    assert watch.masks
    assert watch.operands


def _a_checked_book_folded(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fold the same book: the columns folded, the counts, and the coarse cells."""
    del tmp_path
    watch.before(aggregate_module, "completed", monkeypatch)
    one = _checked()
    aggregate_module.aggregate(
        one.document,
        one.inputs,
        [Sum("answer").alias("total")],
        batch=BATCH,
        depth=watch.depth,
    )
    assert watch.counted
    assert watch.masks
    assert watch.operands


CONSUMERS: dict[str, Callable[[Path, Watch, pytest.MonkeyPatch], None]] = {
    "into the frame sink": _into_the_frame_sink,
    "into the file sink": _into_the_file_sink,
    "into the file sink, in the book's order": _into_the_file_sink_in_order,
    "after a refusal": _after_a_refusal,
    "with a build fault held": _with_a_build_fault_held,
    "into a fold": _into_a_fold,
    "a fold after a refusal": _a_fold_after_a_refusal,
    "a fold with a fault held": _a_fold_with_a_fault_held,
    "a checked book, written": _a_checked_book_written,
    "a checked book, folded": _a_checked_book_folded,
}


@pytest.mark.parametrize("consumer", sorted(CONSUMERS))
def test_no_batch_s_values_outlive_it(
    consumer: str,
    tmp_path: Path,
    watch: Watch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing older than the batches in flight alive at a dispatch; none at the end."""
    CONSUMERS[consumer](tmp_path, watch, monkeypatch)

    assert len(watch.batches) > len({12, 24, 48})
    assert all(watch.batches), "a batch whose program returned no arrays"
    assert watch.ends is not None
    assert [where for where, _ in watch.seen][-1] == watch.ends
    alive = [count for _, count in watch.seen]
    assert alive == [0] * (len(watch.batches) + 1), watch.seen


def _kept(watch: Watch) -> list[int]:
    """Return what the watch sees of a run that keeps every batch it is handed.

    The columns of every batch the watch holds to account at a dispatch --
    all but those in flight -- and of every batch at the end. Columns only: a
    consumer keeps a batch's values, and a batch's counts are the program's,
    let go of with the batch whoever keeps its values.
    """
    batches = len(watch.batches)
    return [
        *(sum(watch.columns[: max(at - watch.depth, 0)]) for at in range(batches)),
        sum(watch.columns),
    ]


def test_the_watch_sees_a_batch_that_is_kept(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The watch itself, shown to see what it is for: a batch kept is counted.

    A consumer that keeps every batch's values -- the engine as it was before
    streaming -- has every batch older than the ones in flight alive at each
    dispatch. The values themselves, not the batch: the stream takes each
    value out of its batch as it builds the column, so a batch kept is not a
    batch's values kept.
    """
    kept: list[dict[str, Value]] = []
    running = ExecutionPlan.stage_finish

    def keeping(self: ExecutionPlan, *arguments: object) -> Batched:
        batched = running(self, *arguments)  # type: ignore[arg-type]
        kept.append(dict(batched.values))
        return batched

    monkeypatch.setattr(ExecutionPlan, "stage_finish", keeping)
    _into_the_frame_sink(tmp_path, watch, monkeypatch)

    assert len(watch.batches) > 1
    assert [alive for _, alive in watch.seen] == _kept(watch)


def test_the_watch_sees_a_fold_that_keeps_its_batches(
    tmp_path: Path, watch: Watch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The watch, shown to see a fold that keeps what it folds.

    A fold that held on to each batch's values -- by keeping the batch, or
    the values out of it -- has every batch older than the ones in flight
    alive at each dispatch, which is what the fold rows above must never
    show.
    """
    kept: list[dict[str, Value]] = []
    folding = aggregate_module.fold_batch_on_the_device

    def keeping(batched: Batched, *arguments: object, **named: object) -> None:
        kept.append(dict(batched.values))
        folding(batched, *arguments, **named)  # type: ignore[arg-type]

    monkeypatch.setattr(aggregate_module, "fold_batch_on_the_device", keeping)
    _into_a_fold(tmp_path, watch, monkeypatch)

    assert len(watch.batches) > 1
    assert [alive for _, alive in watch.seen] == _kept(watch)
