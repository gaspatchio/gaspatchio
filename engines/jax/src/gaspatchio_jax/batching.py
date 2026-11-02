# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""How many policies one compiled program is handed at a time, and why that many.

A projection is a rectangle of policies by periods, and XLA allocates the
intermediates of the whole rectangle at once. A hundred columns over a
million policies and eighty-three periods is six hundred gigabytes of
temporaries, which is not a number this laptop has; the same model over
sixteen thousand policies is ten gigabytes, and over four thousand it is two
and a half. So the book is cut into batches, and the size of a batch is read
from what the compiled program says it needs rather than guessed.

**The size comes off a grid, and the grid is short on purpose.** One program
per batch size is one compilation, and a compilation of a real model is
seconds; a size chosen freely from the temporaries would give a different
program for every book, and the last short batch of every run would be a
compilation of its own. Five widths cover three orders of magnitude, and the
run's last batch is the only one that ever falls off the grid.

**Policies are grouped before they are batched.** Two policies whose
timelines round up to one width are two rows of one rectangle; two whose
timelines round up to different widths are not, and putting them in one batch
would pad the shorter to the longer for no reason the model gave. So the
grouping is by the widths a policy's axes take -- and by which of those axes
agree with each other, because 11.1.18 refuses two per-period operands of
different lengths and that answer has to be the same for every policy a
program was built for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from .horizon import BUCKETS

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    import jax

__all__ = [
    "BATCH_GRID",
    "BUDGET_BYTES",
    "batch_size",
    "bytes_per_policy",
    "chunks",
    "grouped",
    "in_the_books_order",
    "one_timeline",
]

# The batch sizes this engine compiles for. Five, covering three orders of
# magnitude, so that a book of any size is a handful of compilations.
BATCH_GRID: tuple[int, ...] = (256, 1024, 4096, 16384, 65536)

# What the temporaries of one batch are allowed to reach. Two gigabytes: a
# laptop running a model is also running an editor, a browser and the process
# that will read the result, and a budget that took the whole machine would
# make the edit-run-refine loop a thing you leave the room for.
BUDGET_BYTES: Final = 2 * 1024**3


def bytes_per_policy(compiled: jax.stages.Compiled, batch: int) -> int:
    """Return what one policy costs in temporaries, as this program reports it.

    XLA's own figure for the buffers the program needs beyond its arguments
    and its outputs, divided by the policies it was compiled for. It is read
    from a program rather than computed from the model, because what the
    temporaries are is a decision the compiler made -- which columns it fused,
    which it kept -- and the model cannot know it.
    """
    if batch <= 0:
        return 0
    stats = compiled.memory_analysis()
    if stats is None:  # pragma: no cover -- every backend this engine runs on reports
        return 0
    temporaries = int(stats.temp_size_in_bytes)
    return -(-temporaries // batch)


def batch_size(per_policy: int, budget_bytes: int = BUDGET_BYTES) -> int:
    """Return the widest batch on the grid whose temporaries stay inside the budget.

    The narrowest width where even one batch of it is over budget: a book has
    to run, and a refusal to run a model because its widest column is large
    would be this engine deciding an actuary's memory for them. The run
    reports the size it took, so a batch that is over budget is a fact in the
    report rather than a surprise in the machine.
    """
    if per_policy <= 0:
        return BATCH_GRID[-1]
    inside = [size for size in BATCH_GRID if per_policy * size <= budget_bytes]
    return max(inside) if inside else BATCH_GRID[0]


def grouped(widths: Mapping[str, np.ndarray], rows: int) -> list[np.ndarray]:
    """Return the book's rows grouped by the shape their program takes.

    Two policies are in one group when every axis of the model rounds up to
    the same width for both of them *and* the same axes agree with each other
    for both. The first is what makes them rows of one rectangle; the second
    is what makes 11.1.18's answer the same for both, which matters because
    that answer is settled while the program is built and the program is then
    run for every batch of the group.
    """
    if not widths or not rows:
        # A book of no policies is one group of no policies, not none: an
        # engine publishes at least one batch, carrying its schema, and a run
        # that produced no group at all would publish nothing to carry it in.
        return [np.arange(rows, dtype=np.int64)]
    counts = [np.asarray(one, dtype=np.int64) for one in widths.values()]
    # Each policy's key -- every axis's rounded width, and which axes agree --
    # as small whole-number codes, folded into one number per policy.
    codes = [_width_codes(one) for one in counts]
    codes += [
        ((counts[left] == counts[right]).astype(np.int64), 2)
        for left in range(len(counts))
        for right in range(left + 1, len(counts))
    ]
    key, kinds = _folded(codes)
    # Groups in the order their first policy appears, each holding its rows
    # in the order the book holds them. Whole-array operations throughout:
    # the first version sorted the book's keys row-wise and then walked it
    # one policy at a time, which at ten million policies was the largest
    # single cost of a run.
    first = np.full(kinds, rows, dtype=np.int64)
    np.minimum.at(first, key, np.arange(rows, dtype=np.int64))
    present = np.flatnonzero(first < rows)
    rank = np.zeros(kinds, dtype=np.int64)
    rank[present[np.argsort(first[present])]] = np.arange(present.size)
    labels = rank[key]
    held = np.argsort(labels.astype(_narrowest(present.size)), kind="stable")
    ends = np.cumsum(np.bincount(labels, minlength=present.size))[:-1]
    return list(np.split(held.astype(np.int64), ends))


def in_the_books_order(groups: Sequence[np.ndarray]) -> bool:
    """Return whether these groups, run one after another, hand the book over in order.

    Half of what the stream tells its sink before the first batch;
    :func:`one_timeline` is the other half. Where every batch will arrive as
    the book's next rows, a file sink can write each one straight into the
    result, where its rows will stand; where they will not, it stages them
    and puts the book back in order at the end, writing every row twice. So
    this is decided from the batching plan, before anything is computed, and
    never guessed from the first batches to arrive.

    The batches are handed over group by group, each group's front to back
    (:meth:`~gaspatchio_jax.plan.ExecutionPlan.stage_batches`), and a group
    holds its rows in the book's own order (:func:`grouped`). So the book
    arrives in order exactly when each group is an unbroken run of the book
    starting where the group before it ended, which one group always is. A
    group's rows ascend and never repeat, so its first and last rows settle
    whether it is such a run.
    """
    at = 0
    for rows in groups:
        if rows.size and (int(rows[0]) != at or int(rows[-1]) != at + rows.size - 1):
            return False
        at += int(rows.size)
    return True


def one_timeline(widths: Mapping[str, np.ndarray]) -> bool:
    """Return whether every policy of the book lays the same cells on every axis.

    The other half of what the stream tells its sink (see
    :func:`in_the_books_order`). A file sink writing straight into the result
    sizes the file's row groups from the first batch's rows, and cannot
    resize them once the file is begun: a book whose later policies run
    longer timelines -- one sorted by term, shortest first -- would widen its
    rows batch by batch, and every row group after the first batch's with
    them. At 400,000 level-4 policies every node sorted by width, that was
    row groups of up to 860 MiB where a block is 64 MiB, and a peak of 2.75
    GiB where staging peaked at 1.61. So the book's order is promised only
    where rows cannot widen: every policy the same timeline on every axis,
    which levels 4 and 5 are. Every other book is staged.
    """
    return all(
        not counts.size or int(counts.min()) == int(counts.max())
        for counts in widths.values()
    )


def _width_codes(counts: np.ndarray) -> tuple[np.ndarray, int]:
    """Return each horizon's rounded width as a small code, and how many codes.

    :func:`~gaspatchio_jax.horizon.bucket_of` over the whole column: the
    smallest width on the grid that holds a horizon is its position on the
    grid, and a horizon past the grid -- which takes its own width -- takes a
    code after the grid's, one per distinct horizon.
    """
    grid = np.asarray(BUCKETS, dtype=np.int64)
    code = np.searchsorted(grid, counts, side="left").astype(np.int64)
    past = code == grid.size
    if not past.any():
        return code, grid.size
    beyond, which = np.unique(counts[past], return_inverse=True)
    code[past] = grid.size + np.asarray(which).reshape(-1)
    return code, grid.size + beyond.size


# Past this many possible keys the folded key is renumbered densely rather
# than used as an index: an array this long is the most the grouping allocates.
_MOST_KINDS: Final = 1 << 24


def _folded(codes: list[tuple[np.ndarray, int]]) -> tuple[np.ndarray, int]:
    """Return one code per policy standing for all of its codes, and how many."""
    key = np.zeros_like(codes[0][0])
    kinds = 1
    for code, many in codes:
        key = key * many + code
        kinds *= many
        if kinds > _MOST_KINDS:
            distinct, dense = np.unique(key, return_inverse=True)
            key, kinds = np.asarray(dense, dtype=np.int64).reshape(-1), distinct.size
    return key, kinds


def _narrowest(groups: int) -> type[np.unsignedinteger]:
    """Return the narrowest unsigned type that numbers this many groups.

    A stable sort of sixteen-bit labels is a radix sort, a single pass; of
    sixty-four-bit ones it is a merge sort. Books have a handful of groups.
    """
    if groups <= np.iinfo(np.uint16).max:
        return np.uint16
    return np.uint32


def chunks(rows: np.ndarray, size: int) -> Iterator[np.ndarray]:
    """Return one batch of rows at a time, in the order the group holds them.

    A group of no policies is one empty batch rather than none. An engine
    publishes at least one batch -- empty where the book is empty, carrying
    its schema either way -- and a book of no policies is a book, not a run
    that produced nothing.
    """
    if not rows.size:
        yield rows
        return
    for at in range(0, int(rows.size), size):
        yield rows[at : at + size]
