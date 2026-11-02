# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A book run in parts, and the parts adding up to the whole.

Batching exists because XLA allocates a rectangle's intermediates at once and
a rectangle of a million policies does not fit on a laptop. What it must not
cost is the answer: a book run in three parts is the same numbers in the same
order as the same book run in one, and the size of a part is read off what
the compiled program says it needs rather than guessed at.
"""

from __future__ import annotations

import numpy as np
import pytest
from polars.testing import assert_frame_equal

from gaspatchio_jax import batching
from gaspatchio_jax.batching import (
    BATCH_GRID,
    BUDGET_BYTES,
    batch_size,
    bytes_per_policy,
    chunks,
    grouped,
    in_the_books_order,
    one_timeline,
)
from gaspatchio_jax.horizon import BUCKETS, bucket_of
from gaspatchio_jax.plan import ExecutionPlan
from tests.helpers import Watched, a_running_sum, cells, with_batches

POLICIES = 3_000
PERIODS = 8


@pytest.fixture(scope="module")
def whole() -> object:
    """Return the three-thousand-policy book run as one batch."""
    return with_batches(a_running_sum(POLICIES, PERIODS))


def _plan_and_book(policies: int = POLICIES) -> tuple[ExecutionPlan, object]:
    one = a_running_sum(policies, PERIODS)
    plan = ExecutionPlan.stage_inspect(one.document)
    return plan, plan.stage_prepare(plan.stage_validate_inputs(one.inputs))


def test_a_budget_that_admits_a_thousand_policies_runs_three_batches(whole) -> None:
    """Three thousand policies, a budget for 1,024 of them, three parts.

    The budget is set from the program's own figure rather than from a
    number written here: what a policy costs in temporaries is a decision
    the compiler made, and a test that assumed one would pass or fail on the
    compiler's mood.

    ``check_exact=True``: three batches are the same bytes as one, not the
    same to a tolerance.
    """
    plan, prepared = _plan_and_book()
    next(plan.stage_batches(prepared, budget_bytes=BUDGET_BYTES))
    per_policy = plan.per_policy
    assert per_policy > 0
    plan, prepared = _plan_and_book()
    sink = Watched()
    streamed = plan.stage_stream(prepared, sink, budget_bytes=1024 * per_policy)
    assert [one.size for one in sink.handed] == [1024, 1024, 952]
    answered = plan.stage_complete(streamed, sink, prepared).columns
    assert_frame_equal(answered, whole, check_exact=True)


def test_the_rows_come_back_in_the_order_the_book_handed_them_in() -> None:
    """Whatever order the widths grouped them in, a row stands where it stood."""
    lengths = [4 + (policy % 3) * 20 for policy in range(90)]
    one = a_running_sum(len(lengths), lengths)
    answered = with_batches(one, batch=7)
    flows = answered["flow"].to_list()
    assert [list(row) for row in flows] == [
        cells(policy, length) for policy, length in enumerate(lengths)
    ]
    assert answered["answer"].to_list()[1][0] == pytest.approx(cells(1, 1)[0])


def test_a_jagged_book_is_grouped_by_width_before_it_is_batched() -> None:
    """Two policies of different widths are not two rows of one rectangle."""
    lengths = [4, 200, 4, 200, 4]
    one = a_running_sum(len(lengths), lengths)
    plan = ExecutionPlan.stage_inspect(one.document)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(one.inputs))
    groups = grouped(prepared.widths, prepared.inputs.rows)
    assert sorted(sorted(group.tolist()) for group in groups) == [[0, 2, 4], [1, 3]]


def test_the_batch_size_is_the_widest_on_the_grid_inside_the_budget() -> None:
    assert batch_size(1, 10**12) == BATCH_GRID[-1]
    assert batch_size(1024, 1024 * 1024) == 1024
    assert batch_size(10**9, 1) == BATCH_GRID[0]
    assert batch_size(0) == BATCH_GRID[-1]


def test_what_a_policy_costs_is_read_off_the_compiled_program() -> None:
    """The figure comes from XLA's own memory analysis, divided by the batch."""
    plan, prepared = _plan_and_book(64)
    settled = plan.stage_settle(prepared, np.arange(64))
    program, _outcome = plan.compile_for(settled)
    per_policy = bytes_per_policy(program.compiled, 64)
    temporaries = program.compiled.memory_analysis().temp_size_in_bytes
    assert per_policy == -(-int(temporaries) // 64)
    assert bytes_per_policy(program.compiled, 0) == 0


def test_a_group_of_no_policies_is_one_empty_batch_and_not_none() -> None:
    """An engine publishes at least one batch, carrying its schema."""
    assert [one.tolist() for one in chunks(np.arange(0), 16)] == [[]]
    assert [one.tolist() for one in chunks(np.arange(5), 2)] == [[0, 1], [2, 3], [4]]


def _grouped_row_by_row(widths: dict[str, np.ndarray], rows: int) -> list[np.ndarray]:
    """Return the grouping as the engine first wrote it, one policy at a time.

    Kept verbatim as the reference the column-at-a-time version is held to:
    the groups, their order, and the rows in each must be exactly these.
    """
    if not widths or not rows:
        return [np.arange(rows, dtype=np.int64)]
    counts = [np.asarray(one, dtype=np.int64) for one in widths.values()]
    rounded = [
        np.asarray([bucket_of(int(cell)) for cell in one], dtype=np.int64)
        for one in counts
    ]
    agreeing = [
        (counts[left] == counts[right]).astype(np.int64)
        for left in range(len(counts))
        for right in range(left + 1, len(counts))
    ]
    key = np.stack([*rounded, *agreeing], axis=1)
    _found, first, inverse = np.unique(
        key, axis=0, return_index=True, return_inverse=True
    )
    order = np.argsort(first)
    at = {int(group): place for place, group in enumerate(order)}
    held: list[list[int]] = [[] for _ in range(len(order))]
    for row, group in enumerate(np.asarray(inverse).reshape(-1)):
        held[at[int(group)]].append(row)
    return [np.asarray(one, dtype=np.int64) for one in held]


# Every edge of the grid, either side of it, past it, and none at all.
_EDGES = np.asarray(
    [
        *sorted({0, 1, *BUCKETS, *(b + 1 for b in BUCKETS), *(b - 1 for b in BUCKETS)}),
        1201,
        1500,
        5000,
    ],
    dtype=np.int64,
)


@pytest.mark.parametrize("seed", range(40))
def test_grouping_a_column_at_a_time_is_the_row_by_row_grouping(seed: int) -> None:
    """Same groups, in the same order, holding the same rows in the same order.

    Books of one to four axes, drawn from the grid's edges and from a small
    range so that axes often agree with each other and often do not.
    """
    rng = np.random.default_rng(seed)
    rows = int(rng.integers(1, 3_000))
    axes = int(rng.integers(1, 5))
    widths = {
        f"axis_{one}": (
            rng.choice(_EDGES, size=rows)
            if rng.random() < 0.5
            else rng.integers(0, 40, size=rows)
        ).astype(np.int64)
        for one in range(axes)
    }

    fast = grouped(widths, rows)
    slow = _grouped_row_by_row(widths, rows)

    assert len(fast) == len(slow)
    for mine, theirs in zip(fast, slow, strict=True):
        assert mine.dtype == np.int64
        np.testing.assert_array_equal(mine, theirs)


def test_grouping_an_empty_book_is_one_empty_group() -> None:
    for widths in ({}, {"axis": np.zeros(0, dtype=np.int64)}):
        fast = grouped(widths, 0)
        assert len(fast) == 1
        assert fast[0].size == 0


@pytest.mark.parametrize("seed", range(10))
def test_grouping_that_renumbers_its_key_still_agrees(
    seed: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the key renumbered after nearly every column, nothing moves.

    A model with many axes folds to more possible keys than the grouping will
    index, and renumbers the key densely as it goes. Real books rarely reach
    that, so the limit is lowered here to take the path on every book.
    """
    monkeypatch.setattr(batching, "_MOST_KINDS", 8)
    rng = np.random.default_rng(seed)
    rows = int(rng.integers(1, 3_000))
    widths = {
        f"axis_{one}": rng.choice(_EDGES, size=rows).astype(np.int64)
        for one in range(int(rng.integers(2, 6)))
    }

    fast = grouped(widths, rows)
    slow = _grouped_row_by_row(widths, rows)

    assert len(fast) == len(slow)
    for mine, theirs in zip(fast, slow, strict=True):
        np.testing.assert_array_equal(mine, theirs)


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        ([np.arange(10)], True),
        ([np.arange(0, 4), np.arange(4, 10)], True),
        ([np.arange(0)], True),
        ([np.arange(0, 10, 2), np.arange(1, 10, 2)], False),
        ([np.arange(4, 10), np.arange(0, 4)], False),
        ([np.array([0, 1, 3]), np.array([2, 4])], False),
        ([np.arange(1, 10)], False),
    ],
    ids=[
        "one group",
        "runs one after another",
        "the empty book",
        "interleaved",
        "runs the wrong way round",
        "a gap",
        "not from the first row",
    ],
)
def test_a_plan_is_in_the_book_s_order_only_when_its_groups_run_it_front_to_back(
    groups: list[np.ndarray], *, expected: bool
) -> None:
    """Group after group, each front to back: the book's rows 0 to N - 1, or not."""
    assert in_the_books_order(groups) is expected


def test_the_widths_of_a_sorted_book_group_it_into_runs_of_itself() -> None:
    """A book sorted by term is several groups and still arrives in its own order.

    Interleave the same widths and it does not: that book is staged.
    """
    widths = np.array([bucket_of(12)] * 5 + [bucket_of(24)] * 7, dtype=np.int64)
    interleaved = np.array([bucket_of(12), bucket_of(24)] * 6, dtype=np.int64)

    assert len(grouped({"axis": widths}, widths.size)) == 2
    assert in_the_books_order(grouped({"axis": widths}, widths.size))
    assert not in_the_books_order(grouped({"axis": interleaved}, interleaved.size))


@pytest.mark.parametrize(
    ("widths", "expected"),
    [
        ({}, True),
        ({"axis": np.full(5, 83)}, True),
        ({"axis": np.zeros(0, dtype=np.int64)}, True),
        ({"axis": np.full(5, 83), "other": np.full(5, 12)}, True),
        ({"axis": np.array([83, 83, 84])}, False),
        ({"axis": np.full(3, 83), "other": np.array([12, 12, 13])}, False),
    ],
    ids=[
        "no axis",
        "one width",
        "the empty book",
        "two axes of one width each",
        "one axis that varies",
        "a second axis that varies",
    ],
)
def test_one_timeline_holds_only_where_every_axis_lays_one_width(
    widths: dict[str, np.ndarray], *, expected: bool
) -> None:
    """Every policy the same cells on every axis, or the rows could widen."""
    assert one_timeline(widths) is expected
