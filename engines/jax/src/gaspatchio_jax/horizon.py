# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Where each policy's timeline stops, and what an operation owes that fact.

A term book has hundreds of distinct period counts and a rectangular array
has one. Compiling a program for every count is a quarter of an hour cold, so
each policy's count is rounded **up** to a small fixed grid of widths, the
arrays are padded to that width, and every policy's own count travels beside
them as one integer. What leaves the engine is cut back to that count, so the
padding is never published.

**The padding is not neutral, and that is the whole difficulty.** A
position-local formula runs over the padded cells like any others: a rate of
``base + 0.05`` is 0.05 past the horizon, a cashflow of ``premium * count``
is whatever those two are there. An operation whose value at one position can
depend on a *later* position -- a reverse fold, a reduction, a shift, a
selection -- then reads cells that are not periods of that policy, and the
answer moves with the width of a bucket nobody in the model chose. So each
such operation masks its operands to its own neutral element first: a
cashflow to 0, a rate to 0, a product operand to 1. The neutral is the
operation's, not one zero for everything, because a product masked to zero is
zero.

**Seven classes, and the class is on the registration.** Position-local,
forward fold, recurrence, reverse fold, reduction, shift or selection,
generator. Four of them cross the horizon and every identifier in those four
carries a padding witness in the suite -- an actual horizon against a padded
one, equal after the trim -- so the classification is tested rather than
asserted.

**This is not a null mask.** A padded cell is not a period carrying no value;
it is not a period at all. A null still refuses at the door, because this
engine cannot hold one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, NamedTuple

import jax
import jax.numpy as jnp
import numpy as np

from .typed import DomainRefused, Shape, Value

__all__ = [
    "BUCKETS",
    "Aligned",
    "Horizon",
    "aligned",
    "boundary",
    "bucket_of",
    "mask_to_neutral",
    "resolve_position",
    "spread",
    "trim",
]

# The widths a horizon is rounded up to. Months, and chosen for the shapes a
# life book actually takes: a year, two, three, five, seven, ten, fifteen,
# twenty, thirty, forty, fifty, sixty, eighty and a hundred years. A book of
# five-, ten- and twenty-year terms compiles three programs rather than
# hundreds, and the widest waste any policy carries is the distance to the
# next width up.
BUCKETS: tuple[int, ...] = (
    12,
    24,
    36,
    48,
    60,
    84,
    120,
    180,
    240,
    360,
    480,
    600,
    720,
    960,
    1200,
)

# What a per-period value is held in, for the cheap index row every mask and
# every shift is built from.
_POSITION_TYPE: Final = jnp.int32

# 11.1.18's own sentence, for the refusal two operands of unequal length take.
_SHAPES: Final = "11.1.18"


def bucket_of(t: int) -> int:
    """Return the width one horizon is padded to.

    The smallest width on the grid that holds it. Past the grid there is no
    rounding left worth doing -- a horizon of a hundred and one years is one
    program either way -- so such a horizon takes its own width and the grid
    stops being consulted.
    """
    for width in BUCKETS:
        if t <= width:
            return width
    return t


@dataclass(frozen=True, slots=True)
class Horizon:
    """One per-period value's axis: how long each policy's own timeline is.

    **The period counts are two things at once, and both are kept.** They are
    data -- a denominator, a boundary, the position ``-1`` names -- and they
    are the shape: what width the arrays are padded to, and whether two
    operands are the same timeline. The first has to reach a compiled program
    as an argument, or a program compiled for one batch would be a program
    about that batch's terms. The second has to be answerable while the
    program is being built, which is before any argument has a value. So
    ``t`` carries the cells the arithmetic reads and ``lengths`` carries the
    same counts on the host, and every question about the *shape* is asked of
    ``lengths``.

    Attributes:
        t: ``[B]``, each policy's own number of cells, as the trace reads
            them. Not the bucket: every rule that resolves a boundary, a
            negative position or a denominator resolves it against this.
        bucket: The width the arrays are padded to, one for the whole book.
        active: ``[B, bucket]``, true at the cells that are periods of that
            policy and false at the padding.
        lengths: The same counts on the host, which is what the bucket, the
            trim and the comparison of two axes are decided from.

    """

    t: jax.Array
    bucket: int
    active: jax.Array
    lengths: np.ndarray

    @classmethod
    def over(
        cls,
        lengths: jax.Array,
        *,
        bucket: int | None = None,
        host: np.ndarray | None = None,
    ) -> Horizon:
        """Return the axis a column of per-policy lengths stands for.

        ``host`` is the same counts read on the host, and is given exactly
        where ``lengths`` is an argument of a program being traced: the cells
        are then the trace's and the counts behind them are the batch's,
        known before the program was built.
        """
        counts = lengths.astype(_POSITION_TYPE)
        # On the host, whether or not a trace is open. A bucket is the width
        # of an array and an array's width is not a number a compiled program
        # can be handed: it is settled before the program is built, which is
        # what the axis stage settles the period counts for.
        with jax.ensure_compile_time_eval():
            read = (
                np.asarray(host, dtype=np.int64)
                if host is not None
                else np.asarray(counts, dtype=np.int64)
            )
        if bucket is not None:
            width = bucket
        elif read.size:
            width = bucket_of(int(read.max()))
        else:
            # A book of no policies has no longest timeline to round up, and
            # the narrowest width on the grid is as good as any: every array
            # over it has no rows at all.
            width = BUCKETS[0]
        return cls(counts, width, _index(width) < counts[:, None], read)

    def agrees_with(self, other: Horizon) -> bool:
        """Return whether two axes are the same timeline, policy by policy.

        **Lengths, not buckets.** A bucket is this engine's padding and no
        part of the model: the schedule family sizes one from a boundary
        count and an arriving column from its own cells, so two columns of
        exactly twelve periods can stand in a bucket of twenty-four and one
        of twelve. They are the same timeline, and the operation that
        combines them is an ordinary line.

        Asked of the host counts, because it is asked while a program is
        being built and two traced arrays have no values to compare then.
        """
        return bool(np.array_equal(self.lengths, other.lengths))


def _index(bucket: int) -> jax.Array:
    """Return the position of every cell of one bucket, as a row."""
    return jnp.arange(bucket, dtype=_POSITION_TYPE)[None, :]


def periods_of(value: Value) -> Horizon:
    """Return one per-period value's axis, refusing a value that carries none.

    Raises:
        AssertionError: If a list-shaped value reached here without an axis.
            A per-period value with no horizon is a defect in whatever built
            it, not a refusal about the model, and it fails loudly here
            rather than being padded against a guess.

    """
    if value.horizon is None:  # pragma: no cover -- a defect, not a refusal
        message = f"a per-period {value.dtype} value carries no horizon"
        raise AssertionError(message)
    return value.horizon


def spread(value: Value, horizon: Horizon) -> jax.Array:
    """Return one operand's cells over this axis, repeating a per-policy value.

    11.1.18's broadcast: policy ``i``'s scalar is repeated to the length of
    policy ``i``'s list. A row rather than a filled rectangle, because every
    arithmetic this is handed to broadcasts a row itself and a filled one
    would be the same numbers in ``bucket`` times the memory. A per-period
    value already standing in a narrower bucket is widened, so that what comes
    back is over the axis it was asked for.
    """
    if value.shape != "list":
        return value.array[:, None]
    return widen(value.array, horizon.bucket)


def widen(cells: jax.Array, bucket: int) -> jax.Array:
    """Return one rectangle padded out to a wider bucket.

    With the carrier's own zero, which is what an arriving column's padding
    already is -- and which nothing reads, because every operation that could
    masks to its own neutral element first.
    """
    held = cells.shape[-1]
    if held >= bucket:
        return cells
    return jnp.pad(cells, ((0, 0), (0, bucket - held)))


class Aligned(NamedTuple):
    """Several operands put on one axis, and what shape their answer takes."""

    arrays: tuple[jax.Array, ...]
    shape: Shape
    horizon: Horizon | None


def aligned(*values: Value) -> Aligned:
    """Return the operands on one axis, refusing two timelines that differ.

    11.1.18: two lists must have equal lengths within each policy, and a
    scalar repeats to the list's length. An engine that padded the shorter of
    two lists would be inventing periods the model never wrote, and one that
    truncated the longer would be dropping periods it did.

    Raises:
        DomainRefused: If two per-period operands are not the same timeline.

    """
    found = [one.horizon for one in values if one.shape == "list"]
    if not found:
        return Aligned(tuple(one.array for one in values), "scalar", None)
    axis = found[0]
    if axis is None:  # pragma: no cover -- a per-period value always carries one
        message = "a per-period operand reached alignment with no horizon"
        raise AssertionError(message)
    for other in found[1:]:
        if other is None:  # pragma: no cover -- as above
            message = "a per-period operand reached alignment with no horizon"
            raise AssertionError(message)
        if not axis.agrees_with(other):
            raise DomainRefused(
                what=(
                    "two per-period operands of this line have different "
                    "numbers of periods within a policy"
                ),
                move=(
                    "bring the two columns onto one projection axis: this "
                    "vocabulary neither pads the shorter nor truncates the "
                    "longer"
                ),
                clause=_SHAPES,
            )
        if other.bucket > axis.bucket:
            axis = other
    return Aligned(tuple(spread(one, axis) for one in values), "list", axis)


def unknown_on(
    values: tuple[Value, ...], axis: Aligned, *, nulls: bool | None = None
) -> jax.Array | None:
    """Return where any of ``values`` has no truth value, over ``axis``.

    Each operand's unknown cells (``Value.unknown``) are put on the axis the
    operands were aligned on, as their values were, and joined. None where
    no operand has any. With ``nulls`` True only the cells that are a
    per-policy logical result's nulls are joined (``Value.unknown_is_null``),
    with False only a NaN comparison's unknowns, and with None both.

    **Over a per-period axis the answer is the whole rectangle**, a policy's
    own unknown repeated to every one of its periods (11.1.18), because
    ``Value.unknown`` is held in its array's own shape. :func:`spread` hands
    back a per-policy operand as one column for arithmetic to broadcast, and
    a mask kept in that form was later widened as though it were a run one
    period long: a per-policy NaN beside a whole-number, text, date or flag
    run reached period 0 and was read as false from period 1 on.
    """
    found = None
    for value in values:
        if value.unknown is None:
            continue
        if nulls is not None and value.unknown_is_null != nulls:
            continue
        held = Value(value.unknown, "bool", value.shape, "bool", value.horizon)
        if axis.horizon is None:
            cells = held.array
        else:
            cells = spread(held, axis.horizon)
            cells = jnp.broadcast_to(cells, (cells.shape[0], axis.horizon.bucket))
        found = cells if found is None else found | cells
    return found


def mask_to_neutral(value: Value, horizon: Horizon, neutral: float) -> Value:
    """Return the value with every cell past the horizon at the neutral element.

    The neutral is the operation's own: 0 for a sum, 1 for a product, and the
    identity of whatever the fold is. A cell past the horizon then contributes
    nothing, so the answer at every real position is the answer the policy's
    own periods give.
    """
    cells = spread(value, horizon)
    return replace(
        value,
        array=jnp.where(horizon.active, cells, jnp.asarray(neutral, cells.dtype)),
        shape="list",
        horizon=horizon,
    )


def boundary(horizon: Horizon, offset: int) -> jax.Array:
    """Return the cells a shift of ``offset`` exposes, for each policy.

    True where ``position + offset`` is not a period of that policy: before
    the first, or at or past that policy's own last. **The policy's own**, not
    the bucket's -- a ``next_period`` that filled at the bucket's edge would
    read a padded cell as the last period of every policy short of it.
    """
    landing = _index(horizon.bucket) + offset
    return (landing < 0) | (landing >= horizon.t[:, None])


def resolve_position(horizon: Horizon, k: jax.Array) -> tuple[jax.Array, jax.Array]:
    """Return the cell one signed position names per policy, and whether it exists.

    11.1.22's rule: a non-negative ``k`` is the position itself and a negative
    one counts back from that policy's own length, so ``-1`` is the last
    period the policy has rather than the last cell of the bucket.
    """
    signed = k.astype(jnp.int64)
    length = horizon.t.astype(jnp.int64)
    position = jnp.where(signed >= 0, signed, length + signed)
    return position, (position >= 0) & (position < length)


def trim(value: Value, horizon: Horizon) -> list[np.ndarray]:
    """Return each policy's own periods, cut out of the bucket.

    One array per policy rather than one Polars column: a text cell leaves as
    an interned code and a calendar day as a count of days, and putting those
    back is the publication's business and needs the run's own dictionary.
    What belongs here is the cut.

    The horizon is passed rather than read off the value, because what a
    caller cuts to is not always the axis the value was built on: a boundary
    sequence is one cell longer than the period values beside it, and both
    are trimmed from the same bucket.
    """
    cells = np.asarray(value.array)
    lengths = horizon.lengths
    return [cells[row, : int(lengths[row])] for row in range(cells.shape[0])]
