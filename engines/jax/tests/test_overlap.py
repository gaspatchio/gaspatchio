# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The host settles the next batch while the card computes this one.

A book runs batch by batch: settle a batch on the host, find its program, run
it on the card, read the answers back. Done one after another, the card idles
while the host settles and the host idles while the card computes. Overlapping
them rests on one property first: **settling a batch reads nothing back off
the device**. A read-back queues behind whatever the card is already running,
so a settlement that read would wait for the previous batch's program, and
the overlap would be a queue.

That property is invisible in every answer, so it is held here directly, on
the two shipped models and on the jagged book, and beside it the proof that
the counts handed in are exactly the counts the read-back gave.

**How a read-back is caught.** On a GPU, JAX's transfer guard refuses every
device-to-host transfer inside the settlement outright. On the CPU there is
no transfer to guard -- a CPU array is host memory, and ``np.asarray`` views
it through the buffer protocol without passing through anything a test can
watch -- so the count is taken where the reads were: every axis laid without
its host counts (``Horizon.over`` with no ``host=``) is one read-back.
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import TYPE_CHECKING, Any

import jax
import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from gaspatchio.engines.report import EngineRefusal, Refusal, RunReport
from gaspatchio.scenarios import PeriodMax, PeriodSum
from gaspatchio_jax import aggregate as aggregate_module
from gaspatchio_jax.batching import chunks, grouped
from gaspatchio_jax.horizon import Horizon
from gaspatchio_jax.plan import ExecutionPlan, LoweringContext, depth_on
from tests.conftest import PROJECT, invocation
from tests.helpers import Watched, a_running_sum

if TYPE_CHECKING:
    from collections.abc import Iterator

    from gaspatchio.engines.format import Call
    from gaspatchio_jax.plan import Batched, Dispatched, Prepared, Program, Settled
    from gaspatchio_jax.vectors import Invocation

MODELS = PROJECT / "tests/models"
BOOKS = ("level-4", "level-5", "jagged")

# Batches small enough that every book is several of them, in every group.
BATCH = 128


def _book(
    which: str, request: pytest.FixtureRequest
) -> tuple[dict[str, object], pl.DataFrame]:
    """Return one book and its artifact: a shipped model's, or the jagged one."""
    if which == "jagged":
        jagged: tuple[dict[str, object], pl.DataFrame] = request.getfixturevalue(
            "jagged_book"
        )
        return jagged
    artifact: dict[str, object] = json.loads(
        (MODELS / f"{which}.artifact.json").read_text(encoding="utf-8")
    )
    return artifact, pl.read_parquet(MODELS / f"{which}.book.parquet")


def _prepared(
    which: str, request: pytest.FixtureRequest
) -> tuple[ExecutionPlan, Prepared]:
    artifact, book = _book(which, request)
    plan = ExecutionPlan.stage_inspect(artifact)  # type: ignore[arg-type]
    return plan, plan.stage_prepare(plan.stage_validate_inputs(book))


def _batches(prepared: Prepared) -> Iterator[np.ndarray]:
    """Return every batch's rows, group by group, as the engine cuts them."""
    for group in grouped(prepared.widths, prepared.inputs.rows):
        yield from chunks(group, BATCH)


@contextlib.contextmanager
def _no_transfer_back() -> Iterator[None]:
    """Refuse every device-to-host transfer, where the backend has any to refuse."""
    if jax.default_backend() == "cpu":
        yield
        return
    with jax.transfer_guard_device_to_host("disallow"):
        yield


@pytest.mark.parametrize("which", BOOKS)
def test_settling_a_batch_reads_nothing_back_off_the_device(
    which: str, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every batch of the book settled with no axis laid from a read-back.

    Preparation is outside the watch: it runs once, before any batch, and
    what it reads back is what the widths every settlement is handed are
    made of.
    """
    plan, prepared = _prepared(which, request)
    laying = Horizon.over
    read_back: list[tuple[int, ...]] = []

    def over(
        lengths: jax.Array,
        *,
        bucket: int | None = None,
        host: np.ndarray | None = None,
    ) -> Horizon:
        if host is None:
            read_back.append(tuple(lengths.shape))
        return laying(lengths, bucket=bucket, host=host)

    monkeypatch.setattr(Horizon, "over", over)
    settled = 0
    with _no_transfer_back():
        for rows in _batches(prepared):
            plan.stage_settle(prepared, rows)
            settled += 1

    assert settled > 1
    assert read_back == []


def _as_read_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every lowering read its counts back, as settling did before."""

    def nothing(self: LoweringContext, call: Call) -> None:
        del self, call

    monkeypatch.setattr(LoweringContext, "cells_of", nothing)


def _same(mine: Settled, theirs: Settled) -> None:
    """Hold two settlements of one batch to each other, cell for cell."""
    assert list(mine.values) == list(theirs.values)
    for node_id, value in mine.values.items():
        other = theirs.values[node_id]
        assert (value.carrier, value.shape, value.dtype) == (
            other.carrier,
            other.shape,
            other.dtype,
        ), node_id
        np.testing.assert_array_equal(
            np.asarray(value.array), np.asarray(other.array), err_msg=node_id
        )
        assert (value.horizon is None) == (other.horizon is None), node_id
        if value.horizon is None or other.horizon is None:
            continue
        assert value.horizon.bucket == other.horizon.bucket, node_id
        np.testing.assert_array_equal(
            value.horizon.lengths, other.horizon.lengths, err_msg=node_id
        )
        np.testing.assert_array_equal(
            np.asarray(value.horizon.t), np.asarray(other.horizon.t), err_msg=node_id
        )
        np.testing.assert_array_equal(
            np.asarray(value.horizon.active),
            np.asarray(other.horizon.active),
            err_msg=node_id,
        )


@pytest.mark.parametrize("which", BOOKS)
def test_a_batch_settled_from_the_host_s_counts_is_the_one_the_read_back_gave(
    which: str, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The counts handed in are the counts the device holds, batch by batch.

    Each batch settled twice: from the widths preparation counted, and with
    every lowering reading its counts back as it used to. Every value, every
    width, every period count and every mask of the cells that are periods
    must be the same -- a count off by one would be a timeline one period
    long or short, which no total would show until it was published.
    """
    plan, prepared = _prepared(which, request)
    for rows in _batches(prepared):
        mine = plan.stage_settle(prepared, rows)
        with monkeypatch.context() as read_back:
            _as_read_back(read_back)
            theirs = plan.stage_settle(prepared, rows)
        _same(mine, theirs)


@pytest.mark.parametrize("which", BOOKS)
def test_finishing_a_batch_takes_its_period_counts_from_the_host(
    which: str, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every answer's timeline cut to the counts the batch was settled with.

    Reading a batch's answers back waits for its program: that is what
    finishing a batch is. Its period counts need not wait -- every axis these
    books' answers stand on is one the batch was handed in on, whose counts
    the host holds -- so none is read back, and each is the count the device
    computed with.
    """
    plan, prepared = _prepared(which, request)
    laying = Horizon.over
    read_back: list[tuple[int, ...]] = []

    def over(
        lengths: jax.Array,
        *,
        bucket: int | None = None,
        host: np.ndarray | None = None,
    ) -> Horizon:
        if host is None:
            read_back.append(tuple(lengths.shape))
        return laying(lengths, bucket=bucket, host=host)

    # One batch a group: a program per width is every axis these books take.
    for rows in grouped(prepared.widths, prepared.inputs.rows):
        settled = plan.stage_settle(prepared, rows)
        program, _outcome = plan._program_for(settled)  # noqa: SLF001 -- the stage under test
        dispatched = plan.stage_dispatch(settled, program)
        with monkeypatch.context() as watched:
            watched.setattr(Horizon, "over", over)
            batched = plan.stage_finish(dispatched)
        assert all(source is not None for source in program.sources)
        for node_id, value in batched.values.items():
            if value.horizon is None:
                continue
            np.testing.assert_array_equal(
                value.horizon.lengths, np.asarray(value.horizon.t), err_msg=node_id
            )
    assert read_back == []


# ---------------------------------------------------------------------------
# One batch ahead: the timing moves, and nothing else does
# ---------------------------------------------------------------------------

DEPTHS = (0, 1)


def _said(notes: tuple[str, ...]) -> list[str]:
    """Return a run's notes without what a second run of it says differently.

    A compilation's note carries how long it took and where the program came
    from, and the second of two runs finds the first's in the persistent
    cache. Which program, for which batch and widths, is the part that must
    not move.
    """
    return [
        re.sub(
            r"^compile cache: .* for (sha256:\w+ \(.*?widths \[.*?\]).*$", r"\1", one
        )
        for one in notes
    ]


def _streamed(
    plan: ExecutionPlan, prepared: Prepared, depth: int
) -> tuple[pl.DataFrame, list[list[int]], list[str]]:
    """Return one run's every-node frame, the batches as handed over, and its notes."""
    sink = Watched()
    streamed = plan.stage_stream(prepared, sink, batch=BATCH, depth=depth)
    result = plan.stage_complete(streamed, sink, prepared)
    return (
        result.columns,
        [one.tolist() for one in sink.handed],
        _said(result.report.notes),
    )


@pytest.mark.parametrize("which", BOOKS)
def test_a_book_run_one_batch_ahead_is_the_book_run_one_at_a_time(
    which: str, request: pytest.FixtureRequest
) -> None:
    """Every node, cell for cell, whether the card runs a batch ahead or not.

    The same batches in the same order, the same notes, and every value
    bit-identical: overlapping the host with the card changes when each
    batch's answers are read back and nothing about what they are.
    """
    artifact, book = _book(which, request)
    runs = []
    for depth in DEPTHS:
        plan = ExecutionPlan.stage_inspect(artifact, every_node=True)  # type: ignore[arg-type]
        runs.append(
            _streamed(plan, plan.stage_prepare(plan.stage_validate_inputs(book)), depth)
        )
    (one_at_a_time, handed, notes), (ahead, handed_ahead, notes_ahead) = runs
    assert handed == handed_ahead
    assert len(handed) > 1
    assert notes == notes_ahead
    assert_frame_equal(one_at_a_time, ahead, check_exact=True)


def _even_and_odd() -> Invocation:
    """Return a book whose odd policies' two timelines disagree and even ones' agree.

    ``a + b`` over two per-period columns: four periods and four for the even
    policies, four and five for the odd. The two kinds are two groups, and
    the second's program refuses when it is built (11.1.18) -- after the
    first group's batches have run.
    """
    policies = 8
    return invocation(
        {
            "op": "binop",
            "kind": "add",
            "left": {"op": "col", "name": "a"},
            "right": {"op": "col", "name": "b"},
        },
        {
            "a": {"dtype": "list[f64]", "values": [[1.0] * 4] * policies},
            "b": {
                "dtype": "list[f64]",
                "values": [[2.0] * (4 + policy % 2) for policy in range(policies)],
            },
        },
        "list[f64]",
    )


@pytest.mark.parametrize(
    ("batch", "handed"),
    [(2, [[0, 2], [4, 6]]), (None, [[0, 2, 4, 6]])],
    ids=["pinned", "sized by the budget"],
)
@pytest.mark.parametrize("depth", DEPTHS)
def test_a_refusal_building_a_later_program_comes_after_the_batches_before_it(
    depth: int, batch: int | None, handed: list[list[int]]
) -> None:
    """Every batch dispatched before the refusal is handed over, then it is raised.

    One batch ahead, the first group's last batch is still on the card when
    the second group's program refuses; it is read back and handed over
    first, exactly as it was when the batches ran one at a time. Twice over,
    because the second group's program is first built in two different
    places: with the batch pinned, when its first batch is settled; with the
    batch sized by the budget -- as both doors run it -- while its size is
    read off the program's own temporaries.
    """
    one = _even_and_odd()
    plan = ExecutionPlan.stage_inspect(one.document)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(one.inputs))
    sink = Watched()
    with pytest.raises(EngineRefusal) as refused:
        plan.stage_stream(prepared, sink, batch=batch, depth=depth)
    assert [rows.tolist() for rows in sink.handed] == handed
    assert [one.clause for one in refused.value.report.refusals] == ["11.1.18"]


@pytest.mark.parametrize("depth", DEPTHS)
def test_a_refusal_settling_a_batch_comes_after_every_batch_before_it(
    depth: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A settlement that refuses is raised once the batch before it is handed over."""
    one = a_running_sum(12, 8)
    plan = ExecutionPlan.stage_inspect(one.document)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(one.inputs))
    settling = ExecutionPlan.stage_settle
    refusal = Refusal(
        group="tree",
        where="answer@1",
        count=None,
        what="a settlement that refuses",
        move="none",
        clause="11.1",
    )

    def refusing(self: ExecutionPlan, prepared: Prepared, rows: np.ndarray) -> Settled:
        if int(rows[0]) == 9:
            raise EngineRefusal(RunReport(refusals=(refusal,), notes=()))
        return settling(self, prepared, rows)

    monkeypatch.setattr(ExecutionPlan, "stage_settle", refusing)
    sink = Watched()
    with pytest.raises(EngineRefusal):
        plan.stage_stream(prepared, sink, batch=3, depth=depth)
    assert [rows.tolist() for rows in sink.handed] == [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
    ]


@pytest.mark.parametrize("depth", DEPTHS)
def test_a_fold_s_partials_are_queued_straight_behind_their_own_program(
    depth: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each batch's partial is queued before the next batch's program is.

    On one device stream, work runs in the order it is queued: a partial
    queued after the next batch's program would wait for that program too,
    and the host reading it back would wait with it. So the order the host
    queues things in is what is held here -- program, its partial, next
    program -- and, one batch ahead, the next program before this batch is
    read back.
    """
    queued: list[str] = []
    dispatching = ExecutionPlan.stage_dispatch
    finishing = ExecutionPlan.stage_finish
    reducing = aggregate_module._partials  # noqa: SLF001 -- the device work under test

    def dispatched(
        self: ExecutionPlan, settled: Settled, program: Program
    ) -> Dispatched:
        queued.append(f"program {int(settled.rows[0])}")
        return dispatching(self, settled, program)

    def finished(self: ExecutionPlan, *arguments: Any) -> Batched:  # noqa: ANN401 -- passed through
        batched = finishing(self, *arguments)
        queued.append(f"read back {int(batched.rows[0])}")
        return batched

    def partial(*arguments: Any, **named: Any) -> Any:  # noqa: ANN401 -- passed through
        queued.append("partial")
        return reducing(*arguments, **named)

    monkeypatch.setattr(ExecutionPlan, "stage_dispatch", dispatched)
    monkeypatch.setattr(ExecutionPlan, "stage_finish", finished)
    monkeypatch.setattr(aggregate_module, "_partials", partial)
    one = a_running_sum(9, 8)
    aggregate_module.aggregate(
        one.document,
        one.inputs,
        [PeriodSum("answer").alias("total")],
        batch=3,
        depth=depth,
    )
    if depth == 0:
        assert queued == [
            *("program 0", "partial", "read back 0"),
            *("program 3", "partial", "read back 3"),
            *("program 6", "partial", "read back 6"),
        ]
    else:
        assert queued == [
            *("program 0", "partial"),
            *("program 3", "partial", "read back 0"),
            *("program 6", "partial", "read back 3"),
            "read back 6",
        ]


def _a_division_by(divisors: list[int]) -> Invocation:
    """Return whole-number flows floor-divided by each policy's own divisor.

    A divisor of nought is a finding the trace carries (``floordiv``'s zero
    divisor), so a book whose last policy divides by nought refuses at
    completion, after every batch has been folded.
    """
    return invocation(
        {
            "op": "binop",
            "kind": "floordiv",
            "left": {"op": "col", "name": "flow"},
            "right": {"op": "col", "name": "divisor"},
        },
        {
            "flow": {
                "dtype": "list[i64]",
                "values": [
                    [10 * policy + period for period in range(6)]
                    for policy in range(len(divisors))
                ],
            },
            "divisor": {"dtype": "i64", "values": divisors},
        },
        "list[i64]",
    )


@pytest.mark.parametrize(
    "a_later_batch_refuses", [True, False], ids=["refusal", "none"]
)
@pytest.mark.parametrize("depth", DEPTHS)
def test_a_fault_queuing_a_partial_is_held_to_its_batch_s_turn(
    depth: int, monkeypatch: pytest.MonkeyPatch, *, a_later_batch_refuses: bool
) -> None:
    """Met when the batch was dispatched, it is the run's only at the batch's turn.

    Behind a refusal in a later batch it is never raised: the refusal is the
    run's answer. With nothing refused it is raised at completion, once every
    batch has run.
    """
    calls: list[int] = []
    reducing = aggregate_module._partials  # noqa: SLF001 -- the device work under test

    def faulting(*arguments: Any, **named: Any) -> Any:  # noqa: ANN401 -- passed through
        calls.append(1)
        if len(calls) == 1:
            message = "a defect queuing the first batch's partial"
            raise RuntimeError(message)
        return reducing(*arguments, **named)

    monkeypatch.setattr(aggregate_module, "_partials", faulting)
    divisors = [1 + policy for policy in range(12)]
    if a_later_batch_refuses:
        divisors[-1] = 0
    one = _a_division_by(divisors)
    raised: type[Exception] = EngineRefusal if a_later_batch_refuses else RuntimeError
    with pytest.raises(raised):
        aggregate_module.aggregate(
            one.document,
            one.inputs,
            [PeriodSum("answer").alias("total")],
            batch=3,
            depth=depth,
        )
    # Queued for the first batch and, one ahead, for the second before the
    # first was folded; nothing after that, once the fault was held.
    assert len(calls) == 1 + depth


@pytest.mark.parametrize("depth", DEPTHS)
def test_the_first_fault_in_batch_order_is_the_run_s_whenever_it_was_met(
    depth: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fault folding batch one is the run's, not one met queuing batch two first.

    One batch ahead, batch two's partial is queued before batch one is
    folded, so its fault is met first in time. It is held for batch two's
    turn, which never comes: batch one's own fault is held by then.
    """
    folding = aggregate_module._fold_scalars  # noqa: SLF001 -- the host fold under test
    reducing = aggregate_module._partials  # noqa: SLF001 -- the device work under test
    scalars: list[int] = []
    partials: list[int] = []

    def scalar_fault(*arguments: Any, **named: Any) -> None:  # noqa: ANN401 -- passed through
        scalars.append(1)
        if len(scalars) == 1:
            message = "a defect folding batch one"
            raise RuntimeError(message)
        folding(*arguments, **named)

    def partial_fault(*arguments: Any, **named: Any) -> Any:  # noqa: ANN401 -- passed through
        partials.append(1)
        if len(partials) == 2:
            message = "a defect queuing batch two"
            raise RuntimeError(message)
        return reducing(*arguments, **named)

    monkeypatch.setattr(aggregate_module, "_fold_scalars", scalar_fault)
    monkeypatch.setattr(aggregate_module, "_partials", partial_fault)
    one = a_running_sum(9, 8)
    with pytest.raises(RuntimeError, match="folding batch one"):
        aggregate_module.aggregate(
            one.document,
            one.inputs,
            [PeriodSum("answer").alias("total"), PeriodMax("flow").alias("most")],
            batch=3,
            depth=depth,
        )


def _identical(one: object, other: object, where: str) -> None:
    """Hold two fold answers to each other exactly: every key, every bit, every NaN."""
    if isinstance(one, pl.DataFrame):
        assert isinstance(other, pl.DataFrame), where
        assert_frame_equal(one, other, check_exact=True)
        return
    if isinstance(one, dict):
        assert isinstance(other, dict), where
        assert one.keys() == other.keys(), where
        for key in one:
            _identical(one[key], other[key], f"{where}[{key}]")
        return
    np.testing.assert_array_equal(
        np.asarray(one, dtype=np.float64),
        np.asarray(other, dtype=np.float64),
        err_msg=where,
    )


@pytest.mark.parametrize("model", ["level-4", "level-5"])
def test_a_fold_one_batch_ahead_is_the_fold_one_at_a_time(
    model: str, request: pytest.FixtureRequest
) -> None:
    """Every supported aggregator, alone and partitioned, to the last bit.

    The partials are queued earlier and read back later; the batches are the
    same batches, folded in the same order, so every total is the same number
    -- not the same within the agreement band, the same.
    """
    from tests.test_aggregate import aggregations

    artifact, book = _book(model, request)
    built, _kinds = aggregations()
    answers = [
        aggregate_module.aggregate(artifact, book, built, batch=BATCH, depth=depth)  # type: ignore[arg-type]
        for depth in DEPTHS
    ]
    one_at_a_time, ahead = answers
    assert one_at_a_time.n_periods == ahead.n_periods
    assert one_at_a_time.batch_size == ahead.batch_size == BATCH
    assert list(one_at_a_time.aggregations) == list(ahead.aggregations)
    for alias, value in one_at_a_time.aggregations.items():
        _identical(value, ahead.aggregations[alias], alias)


@pytest.mark.parametrize(("backend", "ahead"), [("cpu", 0), ("gpu", 1), ("tpu", 1)])
def test_a_card_runs_a_batch_ahead_and_the_cpu_runs_them_one_at_a_time(
    backend: str, ahead: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The depth is the device's own wherever the caller names none.

    On a card the programs run on a device of their own and the host settles
    the next batch while one computes; on the CPU the device is the host's
    own cores, and the batches run one at a time as they always did. Held on
    the order the loop hands batches to their programs and reads them back,
    with the backend's name standing in for the device.
    """
    events: list[str] = []
    dispatching = ExecutionPlan.stage_dispatch
    finishing = ExecutionPlan.stage_finish

    def dispatched(
        self: ExecutionPlan, settled: Settled, program: Program
    ) -> Dispatched:
        events.append(f"program {int(settled.rows[0])}")
        return dispatching(self, settled, program)

    def finished(self: ExecutionPlan, *arguments: Any) -> Batched:  # noqa: ANN401 -- passed through
        batched = finishing(self, *arguments)
        events.append(f"read back {int(batched.rows[0])}")
        return batched

    monkeypatch.setattr(ExecutionPlan, "stage_dispatch", dispatched)
    monkeypatch.setattr(ExecutionPlan, "stage_finish", finished)
    monkeypatch.setattr(jax, "default_backend", lambda: backend)
    assert depth_on(backend) == ahead
    one = a_running_sum(9, 8)
    plan = ExecutionPlan.stage_inspect(one.document)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(one.inputs))
    sink = Watched()
    plan.stage_complete(plan.stage_stream(prepared, sink, batch=3), sink)
    if ahead:
        assert events == [
            "program 0",
            *("program 3", "read back 0"),
            *("program 6", "read back 3"),
            "read back 6",
        ]
    else:
        assert events == [
            *("program 0", "read back 0"),
            *("program 3", "read back 3"),
            *("program 6", "read back 6"),
        ]


@pytest.mark.parametrize("depth", [-1, 2])
def test_a_depth_other_than_nought_or_one_is_refused_before_the_book_is_read(
    depth: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One batch ahead is the whole of the overlap; two would keep three alive.

    Refused by the plan's own loop, by the stream over it, and by the fold
    -- the fold before it has read a single row of the book.
    """
    one = a_running_sum(9, 8)
    plan = ExecutionPlan.stage_inspect(one.document)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(one.inputs))
    with pytest.raises(ValueError, match="depth is 0"):
        next(plan.stage_batches(prepared, batch=3, depth=depth))
    with pytest.raises(ValueError, match="depth is 0"):
        plan.stage_stream(prepared, Watched(), batch=3, depth=depth)

    read: list[int] = []
    validating = ExecutionPlan.stage_validate_inputs

    def reading(self: ExecutionPlan, inputs: pl.DataFrame) -> Any:  # noqa: ANN401 -- passed through
        read.append(inputs.height)
        return validating(self, inputs)

    monkeypatch.setattr(ExecutionPlan, "stage_validate_inputs", reading)
    with pytest.raises(ValueError, match="depth is 0"):
        aggregate_module.aggregate(
            one.document,
            one.inputs,
            [PeriodSum("answer").alias("total")],
            batch=3,
            depth=depth,
        )
    assert read == []
