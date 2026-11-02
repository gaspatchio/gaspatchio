# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The three things a run must not depend on, each held to the bit.

They are the reason batching and the bucket grid are allowed to exist at all.
**How a book was cut into batches** is this engine's arithmetic about memory
and no part of the model. **How wide a rectangle was padded** is the same.
**Which run it is** is not a quantity at all. An answer that moved with any of
the three would make a result something a reader could not reproduce without
also reproducing this engine's internal bookkeeping -- and a valuation nobody
can reproduce is not a valuation.

Bit for bit, and not within the agreement band: the band is the rule between
*two engines* lowering one clause two ways. Inside one engine, one program,
one book, the answer is the same bits or something is wrong.

**Every comparison here passes ``check_exact=True``, and that keyword is the
whole test.** Polars' own default is ``check_exact=False`` with a relative
tolerance of 1e-5, which is eight orders wider than the one-ulp movement these
properties exist to catch -- a masked sum that read a padded cell at one
bucket and not at another would pass a 1e-5 band and fail these.
"""

from __future__ import annotations

from polars.testing import assert_frame_equal

from tests.helpers import a_running_sum, with_batches

# Wide enough that a batch of one, a batch of seven and one batch of the whole
# book are three genuinely different cuts, and small enough to compile three
# times in a test.
POLICIES = 1_000


def test_the_answer_does_not_depend_on_how_the_book_was_batched() -> None:
    """Batches of one, of seven and of the whole book: the same bytes."""
    one = a_running_sum(POLICIES, 8)
    whole = with_batches(one, batch=POLICIES)
    for size in (1, 7):
        assert_frame_equal(with_batches(one, batch=size), whole, check_exact=True)


def test_the_answer_does_not_depend_on_the_width_the_rectangle_was_padded_to(
    monkeypatch,
) -> None:
    """The masked-sum witness: one book, at a bucket of 128 and at one of 360.

    A cumulative sum runs over a rectangle padded past each policy's own
    horizon, and what fills the padding is the carrier's zero -- so an
    operation that read a padded cell would answer differently at two widths
    and the difference would be a number nobody in the model chose. The grid
    itself is replaced here rather than the book, because a policy's bucket
    follows from its own length: the only way to put one policy in two
    rectangles is to offer the engine two grids.
    """
    from gaspatchio_jax import horizon

    one = a_running_sum(24, [96 + policy for policy in range(24)])
    answers = []
    for width in (128, 360):
        monkeypatch.setattr(horizon, "BUCKETS", (width,))
        answers.append(with_batches(one))
        assert horizon.bucket_of(96) == width
    assert_frame_equal(answers[0], answers[1], check_exact=True)


def test_two_runs_of_one_book_are_the_same_bytes() -> None:
    """Nothing in a run is a quantity, including the run itself."""
    one = a_running_sum(64, 8)
    assert_frame_equal(with_batches(one), with_batches(one), check_exact=True)
