# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The checks an admitted operation owes, and the moment each can be answered.

Nothing here is inferred from an identifier. Each admitted operation declares
the checks its own contract states -- ``to_integer`` owes integrality and
range, a comparison owes finiteness, an integer arithmetic owes the range its
type carries -- and each check runs at the earliest stage its operand allows.
An operand that is an input or a literal is checkable before anything is
compiled, which makes the answer an ``inputs`` refusal and the run one that
never started. An operand a calculation produced is checkable only once the
calculation has run, which makes it a bounded flag carried through the trace
and read at completion, with every output withheld.

**A flag is a count and a first location, never every intermediate.** The
alternative -- carrying each failing cell's whole context out of the trace --
is the shape that makes a check cost as much as the calculation. What a
reader needs is which column, how many cells, and one of them to look at.

**And the counting is done where the mask is.** A compiled program
hands back, for every check it carried, those two numbers and nothing else --
how many cells the mask caught, and the first of them (:func:`tallied`) --
stacked for every check into one array. The masks themselves were most of
what a batch sent back: on level 4 when this was measured, 142 checks and
4.8 KB a policy against 0.7 KB of the columns a fold reads, and on a card
reading them was most of what the loop waited on. Level 4 now carries 134
checks, 4.1 KB of masks a policy (``tests/test_tallies.py``): its duration
keys became whole numbers, which took eight range checks away, and its
recurrence's widening is now on the record, which turned one into
``to_float.exact``. A coarse flag's count is of the cells its in-trace
test caught, and its mask and operands come back only where that count is
above nought, for the exact judgement below.

**A flag is held to the cells that are periods.** A per-period operation runs
over a rectangle padded up to a bucket, and the cells past a policy's own
horizon carry whatever a position-local formula put there -- a divisor of
nought, a half that is not whole, a magnitude past a range. A check read over
those cells refuses a model on a position nobody wrote, which is a refusal
about the width of a bucket the modeller never chose. So every flag a node
raised is held to that node's own horizon before it is read, in one place --
:func:`to_the_horizon`, called by the plan once per node. It is done there
rather than at each :func:`flag` call because a check can be raised before the
horizon is known: an operand widened to a double flags at ±2⁵³ inside
``carried_to``, several frames before the operation that will align it has
run. A lowering therefore cannot forget, because a lowering is not asked.

**Coarse flags are re-judged on the host.** Two integer operations cannot be
tested exactly inside a trace whose widest type is the one being tested
(:mod:`gaspatchio_jax.typed` says why). Their flags over-approximate, and the
cells they catch have their operands brought back as Python integers, whose
range is the machine's memory. So the in-trace test is cheap, the answer is
exact, and the cost falls on the cells that looked wrong rather than on the
book.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Final, Literal

import jax.numpy as jnp
import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    import jax

__all__ = [
    "CHECKS",
    "Carried",
    "Check",
    "FlagBook",
    "Flagged",
    "Stage",
    "about",
    "flag",
    "outside_i64",
    "recording",
    "spelled_position",
    "tallied",
    "to_the_horizon",
]

Stage = Literal["tree", "inputs", "completion"]

# The exact judgements a coarse flag defers to the host. Named rather than
# spelled at each call site, because the completion stage dispatches on them.
Judgement = Literal["mul", "pow"]


@dataclass(frozen=True, slots=True)
class Check:
    """One thing an operation promises about its own operands.

    Attributes:
        name: What the report calls it. Read by the coverage manifest, so it
            is part of what this engine publishes about an identifier.
        clause: The section of the specification that states it.
        what: The actuarial thing, in one sentence, with a place for the
            column and the count the report fills in.
        move: The next move, in one sentence.

    """

    name: str
    clause: str
    what: str
    move: str

    def stage_for(self, *, operand_is_computed: bool) -> Stage:
        """Return the earliest stage this check can be answered at.

        An input or a literal is there before anything runs, so the answer is
        a refusal that costs nothing. A computed operand is not, and the run
        has to reach the end for the flag to be readable -- which is why the
        two groups close with different sentences.
        """
        return "completion" if operand_is_computed else "inputs"


def _check(name: str, clause: str, what: str, move: str) -> tuple[str, Check]:
    """Return one inventory row, keyed by its own name."""
    return name, Check(name=name, clause=clause, what=what, move=move)


# The inventory: every check the lowered families owe, each with the clause
# that states it.
#
# **A miss under raise is two findings, not one.** A basis that has no row for
# a key is short a row and a basis whose row is there with nothing in its
# answer cell is short a rate -- section 11.1.24 makes both a miss -- and a
# reader handed one sentence for both has to open the payload to find out
# which. The pre-flight path told them apart from the start; these two rows
# are what lets the completion path, where the flag is read rather than the
# key, say the same two things.
CHECKS: Final[dict[str, Check]] = dict(
    (
        _check(
            "i64.range",
            "11.1.25",
            "an integer result outside the range i64 carries",
            "rescale the calculation, or carry the value as f64 where its "
            "magnitude is what matters and its last digit is not",
        ),
        _check(
            "mixed.2p53",
            "11.1.25",
            "an integer beyond 2^53 met a floating-point operand, where "
            "converting it would lose the integer",
            "keep the calculation in integers, or rescale so the magnitudes "
            "meet inside the range a double names every whole number in",
        ),
        _check(
            "floordiv.zero_divisor",
            "11.1.25",
            "an integer division by zero, which the clause makes a null "
            "rather than a number",
            "guard the divisor with a when/then, so the model says what a "
            "zero denominator means here",
        ),
        _check(
            "to_integer.integral",
            "11.1.23",
            "a value to_integer cannot carry: not finite, not whole, or "
            "outside the range i64 carries",
            "round or floor the value first, so the record says which way "
            "the model went",
        ),
        _check(
            "to_float.exact",
            "11.1.38",
            "an integer outside 2^53, where widening to a double would make "
            "two identifiers read as one",
            "keep the value an integer, or carry its digits with to_text",
        ),
        _check(
            "predicate.stored_f64",
            "11.1.18",
            "a stored floating-point predicate whose value is neither 0.0 nor 1.0",
            "compare in the condition itself, so the truth value is a "
            "predicate rather than a number standing for one",
        ),
        _check(
            "cut.nan",
            "11.1.4",
            "a NaN, which lies in no interval of the band, so its band is a "
            "null, which this engine does not carry",
            "test for the NaN with is_nan before banding, and say in the model "
            "what it means, or run this model on Polars, which answers the null",
        ),
        _check(
            "comparison.unknown",
            "11.1.26",
            "a comparison with a NaN operand, which has no truth value, read "
            "where the answer would be a null -- a stored flag, text, a whole "
            "number or a date chosen by it -- which this engine does not carry",
            "test for the NaN with is_nan and say in the model what it means, "
            "or run this model on Polars, which answers the null",
        ),
        _check(
            "pow.integer_exponent",
            "11.1.25",
            "an integer power whose exponent is outside [0, 2^32-1], which "
            "the integer clause does not promise",
            "write to_float() on either operand -- base.to_float() ** exponent, "
            "or base ** exponent.to_float() -- so the power is the "
            "floating-point one, where the clause states the wider domain",
        ),
        _check(
            "str.to_date.strict",
            "11.1.7",
            "text the stated format does not fit, under a strict parse",
            "widen the format, or set strict false so the unparsed text "
            "becomes null and the model says it may",
        ),
        _check(
            "list_get.bounds",
            "11.1.22",
            "a position outside the periods that policy has",
            "guard the position against the policy's own period count",
        ),
        _check(
            "prospective_value.rate",
            "11.1.21",
            "a discount rate at or below -1, where the factor is not a discount at all",
            "check the rate basis: a rate of -1 discounts to nothing and "
            "anything below it changes the sign of the value",
        ),
        _check(
            "rollforward.finite",
            "16.1",
            "a state of the compiled rollforward that stopped being finite",
            "check the step that produced it: a balance leaving the finite "
            "numbers is a modelling defect rather than a large answer",
        ),
        _check(
            "lookup.miss_raise",
            "11.1.24",
            "a key the base does not carry, under a miss policy of raise",
            "extend the base, or state a miss policy the model means",
        ),
        _check(
            "lookup.key_range",
            "11.1.24",
            "a key read on a numeric column of the basis that is not a number "
            "the basis could carry: not finite, or past the interval this "
            "clause states a matching over",
            "guard the key with a when/then, so the model says what it means "
            "where the key is not a number the basis could carry",
        ),
        _check(
            "lookup.blank_answer",
            "11.1.24",
            "a key the base carries a row for, whose answer cell is blank or "
            "is not a finite number, under a miss policy of raise",
            "fill the cells the model's own keys reach, or state a miss "
            "policy that says what a blank one means",
        ),
        _check(
            "join.unmatched",
            "11.1.2",
            "a left key the right side does not carry",
            "extend the right side, or say in the model what an unmatched key means",
        ),
        _check(
            "join.blank_arriving",
            "11.1.2",
            "a matched right-side row whose arriving cell carries no value, in a "
            "column this engine holds no absent value for",
            "fill the right side's blank cells, or say in the model what an "
            "arriving column with nothing in it means",
        ),
        _check(
            "to_monthly.rate",
            "11.1.29",
            "an annual rate below -1, which has no twelfth root",
            "check the rate basis: a rate below -1 has no monthly equivalent",
        ),
        _check(
            "discount.zero_factor",
            "11.1.29",
            "a discount over a factor of nought, which this clause makes a null "
            "rather than a number",
            "guard the rate with a when/then, so the model says what a factor of "
            "nought means here",
        ),
        _check(
            "present_value.period",
            "11.1.29",
            "a cashflow valued below one period out, which this clause makes a "
            "null rather than a number",
            "guard the period with a when/then, or use finance.discount, whose "
            "clause states an answer there",
        ),
        _check(
            "discount_factor.rate",
            "11.1.30",
            "a spot rate at or below -1, where the factor is not a discount",
            "check the rate basis the curve was built on",
        ),
        _check(
            "reduction.no_periods",
            "11.1.15",
            "a policy with no periods for mean, min or max to fold, which these "
            "clauses answer with a null",
            "guard the fold with a when/then on the policy's own period count, "
            "so the model says what it means where there are none",
        ),
        _check(
            "excel.round.scale",
            "11.1.35",
            "a value that scales past 2^52 at the stated digits, where a decimal "
            "tie is no longer decidable in a double",
            "round at fewer digits, or rescale the calculation",
        ),
        _check(
            "excel.round.sixteenth",
            "11.1.35",
            "a value within a few units of its last binary place of the point "
            "where its fifteen digits turn into a half, which binary arithmetic "
            "cannot place on one side or the other",
            "run this line on the reference producer, which reads the decimal "
            "digits exactly, or round at another number of digits",
        ),
        _check(
            "excel.pv.periods",
            "11.1.35",
            "an annuity over a negative number of periods, which is outside this entry",
            "check the period count the model passed",
        ),
        _check(
            "excel.irr.bracket",
            "11.1.36",
            "a cashflow stream with no root inside the bracket this clause "
            "states, which it answers with a null",
            "check the stream: a root outside [-0.9, 1] is outside this entry's "
            "bounded domain",
        ),
        _check(
            "excel.irr.no_sign_change",
            "11.1.36",
            "a cashflow stream that never changes sign, which no rate sets to nothing",
            "check the stream: a rate of return needs a cashflow paid and a "
            "cashflow received",
        ),
        _check(
            "excel.irr.several_roots",
            "11.1.36",
            "a cashflow stream that changes sign more than once, which has "
            "more than one rate and which this clause states no choice between",
            "split the stream, or value it at a rate the model states",
        ),
        _check(
            "excel.serial.epoch",
            "11.1.33",
            "a spreadsheet serial below 1, which this clause reads as no date at all",
            "guard the serial with a when/then, so the model says what a serial "
            "below the epoch means",
        ),
        _check(
            "pow.list_exponent_sign",
            "11.1.25",
            "a negative per-policy base raised to a per-period exponent, which "
            "this clause puts outside itself",
            "write the base as the per-period column the power means, or keep "
            "the sign out of the base",
        ),
    )
)


@dataclass(frozen=True, slots=True)
class Flagged:
    """One check's findings over one operation's cells.

    Attributes:
        name: The check, keyed into :data:`CHECKS`.
        where: The node or column the flag is about.
        mask: True at every cell the in-trace test caught.
        judgement: The exact test the host applies to the caught cells, for
            the two coarse flags, or None where the mask is already exact.
        operands: What that exact test is applied to, in the order it takes.
        note: The sentence this finding reports where it is not a refusal at
            all, and None where it is. A join whose right side carries an
            empty text cell is the case: the column is null there and a read
            keyed on it is a miss (section 11.1.24), which is worth saying and
            is not a reason to withhold a result. It travels as a flag rather
            than as a count read off the trace, because inside a compiled
            program there is no count to read.

    """

    name: str
    where: str
    mask: jax.Array
    judgement: Judgement | None = None
    operands: tuple[jax.Array, ...] = ()
    note: str | None = None

    def caught(self) -> list[int]:
        """Return the flat positions the mask caught, in order."""
        return [int(position) for position in np.flatnonzero(np.asarray(self.mask))]

    def carried(self) -> Carried:
        """Return this check as the reader of a compiled program's answers needs it."""
        return Carried(
            name=self.name,
            where=self.where,
            shape=tuple(self.mask.shape),
            judgement=self.judgement,
            note=self.note,
        )

    def confirmed(self) -> list[int]:
        """Return the positions that are genuinely wrong, judging coarse flags exactly.

        A flag with no judgement is already exact and every caught position
        stands. A coarse one has its caught cells' operands brought back as
        Python integers, where the arithmetic has no range to leave, and only
        the positions whose exact answer is outside ``i64`` survive.

        **Each caught cell is judged against its own operands.** A per-policy
        operand of a per-period product stands in the rectangle as one cell a
        policy, repeated along the periods (11.1.18), so it is read where the
        caught cell stands. Read at the cell's flat position in the operand
        as stored, a policy's cell was set against another policy's value: a
        product that had left ``i64`` could be judged inside it and published
        wrapped, and a cell past the operand's own length was no cell at all.
        """
        positions = self.caught()
        if self.judgement is None or not positions:
            return positions
        shape = tuple(self.mask.shape)
        left, right = (
            np.broadcast_to(np.asarray(operand), shape).flat[positions]
            for operand in self.operands
        )
        return [
            position
            for position, one, other in zip(positions, left, right, strict=True)
            if outside_i64(self.judgement, int(one), int(other))
        ]


@dataclass(frozen=True, slots=True)
class Carried:
    """One check a compiled program carries, as the reader of its answers needs it.

    A program hands back numbers -- each check's count and first caught cell,
    and a coarse check's mask and operands -- and none of them says which
    check it is, what it is about, or how a position in it is spelled. That
    is settled while the program is traced, and kept here with the program.

    Attributes:
        name: The check, keyed into :data:`CHECKS`.
        where: The node or column the check is about.
        shape: The shape of its mask -- one cell a policy, or policies by
            periods -- which a flat position is read against, exactly as it
            was when the mask itself came back. Fixed for a program, which is
            built for one batch's shape.
        judgement: The exact test the host applies to a coarse check's caught
            cells, or None where the count is already exact.
        note: The sentence this check reports where it is not a refusal, and
            None where it is.

    """

    name: str
    where: str
    shape: tuple[int, ...]
    judgement: Judgement | None = None
    note: str | None = None

    def judged(self, mask: jax.Array, operands: Sequence[jax.Array]) -> list[int]:
        """Return the cells a coarse check genuinely caught, judged as it always was.

        Its mask and operands, read back because the card counted a caught
        cell, go through :meth:`Flagged.confirmed` unchanged: the in-trace
        test over-approximates, and only the host's integers are exact.
        """
        return Flagged(
            name=self.name,
            where=self.where,
            mask=mask,
            judgement=self.judgement,
            operands=tuple(operands),
            note=self.note,
        ).confirmed()


def tallied(masks: Sequence[jax.Array]) -> jax.Array:
    """Return each mask's count of caught cells and its first caught cell, as one array.

    The two numbers a finding reports about a check, counted where the mask
    is computed rather than on the host: how many cells it caught,
    ``sum(mask)``, and the first of them in row-major order, ``argmax`` of
    the mask laid flat -- the position ``np.flatnonzero(mask)[0]`` names,
    which a policy and a period are read off against the mask's shape. One
    array for every mask, so a batch's checks cross back as one small read
    rather than a mask of the batch's size each.

    **The first position means something only where the count is above
    nought.** ``argmax`` of a mask that caught nothing is nought, which is
    also where a mask whose first cell was caught points, so the count is
    what tells the two apart and a reader reads it first. A cell is caught
    where the mask is not false, as ``np.flatnonzero`` reads one.

    **Counted together, a policy's row at a time.** Checks of one cell a
    policy are stacked and counted as one block. A check over policies by
    periods is counted along each policy's row first -- in a byte where a
    row holds at most :data:`_BYTE` periods -- and the rows of every check of
    one shape are then read together: the first caught cell is the first
    caught period of the first row that caught any, which is ``argmax`` of
    the mask laid flat, to the cell. Counted one mask at a time and laid
    flat, level 4's 142 checks (134 today) made its program half as large
    again and its batch dearer to compile and to run on a laptop than the
    host's scan of every mask had been (see :func:`_counted_by_rows`).

    Returns:
        An ``int64`` array of two rows -- the counts, then the first
        positions -- with one column per mask, in the order given.

    """
    narrow: dict[int, list[tuple[int, jax.Array]]] = {}
    wide: dict[tuple[int, ...], list[tuple[int, jax.Array]]] = {}
    empty: list[int] = []
    for at, mask in enumerate(masks):
        cells = jnp.asarray(mask).astype(bool)
        if not cells.size:
            # A book of no policies, or a policy of no periods: nothing to catch.
            empty.append(at)
            continue
        rows = (
            cells.reshape(cells.shape[0], -1)
            if cells.ndim > 1
            else cells.reshape(-1, 1)
        )
        if rows.shape[1] == 1:
            narrow.setdefault(rows.shape[0], []).append((at, rows[:, 0]))
        else:
            wide.setdefault(rows.shape, []).append((at, rows))
    order = [*empty]
    counts = [jnp.zeros(len(empty), dtype=jnp.int64)]
    firsts = [jnp.zeros(len(empty), dtype=jnp.int64)]
    for group, count in (
        *((members, _counted_together) for members in narrow.values()),
        *((members, _counted_by_rows) for members in wide.values()),
    ):
        caught, first = count([cells for _at, cells in group])
        order.extend(at for at, _cells in group)
        counts.append(caught)
        firsts.append(first)
    tallies = jnp.stack([jnp.concatenate(counts), jnp.concatenate(firsts)])
    return tallies[:, np.argsort(np.asarray(order, dtype=np.int64))]


def _counted_together(vectors: Sequence[jax.Array]) -> tuple[jax.Array, jax.Array]:
    """Return the counts and first caught cells of checks of one cell a policy."""
    block = jnp.stack(vectors)
    return (
        jnp.sum(block, axis=1, dtype=jnp.int64),
        jnp.argmax(block, axis=1).astype(jnp.int64),
    )


def _counted_by_rows(grids: Sequence[jax.Array]) -> tuple[jax.Array, jax.Array]:
    """Return the counts and first caught cells of checks over policies by periods.

    **A policy's periods first, then the policies.** XLA's CPU reduces along
    a row in wide vector steps, and across a whole mask one cell at a time.
    On the Intel laptop, one level-4 batch of 65,536 policies returning the
    two columns a fold reads took 2.06 s with every mask summed and
    ``argmax``-ed laid flat, 0.82 to 0.94 s with every mask handed back and
    scanned on the host, and 0.87 to 1.01 s counted this way, all three
    measured on 2026-09-25. Each check is still one full reduction
    -- its rows' counts -- and the slice of one row; what the checks of one
    shape share is a few small reductions over those counts, where laid flat
    each check was two full reductions, a sum and an ``argmax``. That keeps
    the program near the size it was: level 4's fold program, built for
    65,536 policies, is 9,091 optimised instructions against 8,185 before
    checks were counted on the card and 12,607 laid flat, and built for
    4,096, 8,823 against 7,885 and 12,103.
    """
    width = grids[0].shape[1]
    per_row = jnp.stack(
        [
            jnp.sum(rows, axis=1, dtype=jnp.uint8 if width <= _BYTE else jnp.int32)
            for rows in grids
        ]
    )
    row = jnp.argmax(per_row > 0, axis=1)
    column = jnp.argmax(
        jnp.stack([rows[row[at]] for at, rows in enumerate(grids)]), axis=1
    )
    return (
        jnp.sum(per_row, axis=1, dtype=jnp.int64),
        row.astype(jnp.int64) * width + column.astype(jnp.int64),
    )


# The most periods a row's count can reach and still be held in a byte.
_BYTE: Final = 255


def outside_i64(judgement: Judgement, left: int, right: int) -> bool:
    """Return whether the exact answer is outside ``i64``, without overbuilding it.

    A product of two int64 values has at most 128 bits, so it is taken
    outright. A **power** has no such bound -- ``2 ** 2**31`` is a quarter of a
    gigabyte of digits, and a coarse flag catches exactly the cells whose
    answers are large -- so it is decided by magnitude first and computed only
    where magnitude cannot decide:

    * a base of -1, 0 or 1 never leaves the type, whatever the exponent;
    * otherwise the answer's magnitude is between ``2**((b-1)*n)`` and
      ``2**(b*n)`` for ``b`` the base's bit length and ``n`` the exponent, so a
      lower bound at or above 2⁶⁴ is outside and an upper bound at or below
      2⁶² is inside, both without an integer being built;
    * between the two, the exponent is small enough that the bounds are within
      a factor of two of each other, which caps what is computed at 127 bits.

    The boundary that makes this worth the care is ``(-2) ** 63``, which is
    exactly ``INT64_MIN`` and therefore *inside* the type -- a magnitude rule
    alone would refuse it.
    """
    if judgement == "mul":
        return not _inside_i64(left * right)
    return _power_outside_i64(left, right)


def _power_outside_i64(base: int, exponent: int) -> bool:
    """Return whether ``base ** exponent`` is outside ``i64``, by magnitude first."""
    if exponent < 0 or -1 <= base <= 1:
        # A negative exponent is refused before this by pow's own check, and a
        # base of -1, 0 or 1 answers -1, 0 or 1 whatever the exponent is.
        return False
    bits = abs(base).bit_length()
    if (bits - 1) * exponent >= _ABOVE_THE_TYPE:
        return True
    if bits * exponent <= _INSIDE_THE_TYPE:
        return False
    return not _inside_i64(base**exponent)


def _inside_i64(value: int) -> bool:
    """Return whether one exact integer fits the signed 64-bit range."""
    return -(2**63) <= value <= 2**63 - 1


# A magnitude of 2**64 or more is outside i64 whatever its sign; a magnitude of
# 2**62 or less is inside it. Between them the exact answer is taken, and the
# two bounds are close enough that what is taken has at most 127 bits.
_ABOVE_THE_TYPE: Final = 64
_INSIDE_THE_TYPE: Final = 62


@dataclass(slots=True)
class FlagBook:
    """Every flag one run carried, in the order the trace raised them."""

    entries: list[Flagged] = field(default_factory=list)


def to_the_horizon(book: FlagBook, first: int, active: Sequence[jax.Array]) -> None:
    """Hold every flag raised since ``first`` to the cells that are periods.

    ``active`` is every per-period axis the node stood on -- its operands' and
    its answer's. A flag is held to the axes whose rectangle it is the shape
    of, **folded by union**: a node can stand on two axes of one rectangle and
    different period counts -- a boundary sequence is one cell longer than the
    period values beside it, and a bucket wide enough for both makes the two
    arrays the same shape -- and a cell that is a period under either of them
    is a cell somebody wrote. Only a cell that is padding under every one of
    them is padding, so a fold that kept one of the two would clear a real
    finding on nothing but the order the axes were offered in. A flag over one
    value per policy is the shape of none of them and is left alone, which is
    what it should be, because a per-policy value has no padding.

    The union is the safe direction and it is a choice: it can keep a cell
    that is padding under the axis the check was actually raised over, where
    an intersection would drop findings that are real.

    One place, and at the *end* of a node rather than at each raise, because a
    check can be raised before the horizon that governs it is known.
    """
    if not active:
        return
    periods: dict[tuple[int, ...], jax.Array] = {}
    for one in active:
        standing = periods.get(one.shape)
        periods[one.shape] = one if standing is None else standing | one
    for position in range(first, len(book.entries)):
        entry = book.entries[position]
        held = periods.get(entry.mask.shape)
        if held is None:
            continue
        book.entries[position] = replace(entry, mask=entry.mask & held)


def spelled_position(flat: int, shape: tuple[int, ...]) -> str:
    """Return where a caught cell is, as a reader would name it.

    A per-period check's cells are a rectangle of policies by periods, and a
    single number out of the flattened array is a cell ordinal rather than a
    row. A reader told "row 913" of a check over a hundred policies would go
    looking for a policy that is not there.
    """
    if len(shape) < _TWO_AXES:
        return f"row {flat}"
    return f"policy {flat // shape[1]}, period {flat % shape[1]}"


# One axis is policies; two are policies by periods.
_TWO_AXES: Final = 2


_CURRENT: contextvars.ContextVar[FlagBook | None] = contextvars.ContextVar(
    "gaspatchio_jax_flags", default=None
)

# Which node the trace is inside. A check is raised in an operand's own
# arithmetic, several frames below the node it belongs to, and the report has
# to name the node rather than the arithmetic.
_ABOUT: contextvars.ContextVar[str] = contextvars.ContextVar(
    "gaspatchio_jax_about", default=""
)


@contextmanager
def about(node_id: str) -> Iterator[None]:
    """Name the node every flag raised inside this block belongs to."""
    token = _ABOUT.set(node_id)
    try:
        yield
    finally:
        _ABOUT.reset(token)


@contextmanager
def recording() -> Iterator[FlagBook]:
    """Open a book for one run's flags, and close it however the run ends.

    A context rather than a parameter threaded through every lowering: a check
    is raised deep inside an operand's own arithmetic, and a signature that
    carried the book would put it on every function between here and there
    whether or not that function has anything to check.
    """
    book = FlagBook()
    token = _CURRENT.set(book)
    try:
        yield book
    finally:
        _CURRENT.reset(token)


def flag(  # noqa: PLR0913 -- one argument per thing a flag carries
    name: str,
    mask: jax.Array,
    *,
    where: str | None = None,
    judgement: Judgement | None = None,
    operands: tuple[jax.Array, ...] = (),
    note: str | None = None,
) -> None:
    """Record one check's findings over one operation's cells.

    Raises:
        LookupError: If ``name`` is not in the inventory. A check nobody
            declared is a check nobody can report on, and silently accepting
            one would put a finding in a run with no sentence to print for it.
        RuntimeError: If no run is open. A flag raised outside a run is a
            check nobody reads, which is worse than no check at all.

    """
    if name not in CHECKS:
        message = f"{name!r} is not a declared check"
        raise LookupError(message)
    book = _CURRENT.get()
    if book is None:
        message = f"the check {name!r} was raised outside a run"
        raise RuntimeError(message)
    book.entries.append(
        Flagged(
            name=name,
            where=where if where is not None else _ABOUT.get(),
            mask=mask,
            judgement=judgement,
            operands=operands,
            note=note,
        )
    )
