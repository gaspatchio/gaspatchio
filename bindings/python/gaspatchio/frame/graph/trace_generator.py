# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The walk-through beside a formula: what it may say, and what it may not.

A trace is three lines -- the formula, the numbers put into it, the number
that came out -- and its whole value is that a reader can check the middle
line by eye. So the middle line has to be one a reader *could* check, which
rules out one thing this module is careful about.

**A value stands in the walk-through only where a single value stands in
the calculation.** A line that folds a column down the model-point file --
``af.total_claims = af.expected_claims.polars_native().sum()`` -- ran over every policy,
and the sampled policy's own number put inside that fold reads as
arithmetic nobody can do: ``(500).sum()`` reaching 5,950. Those steps say
what was folded and over how many model points instead. The caller
decides which lines those are, by asking the engine whether the expression
reduces the frame's rows to one value; this module renders the answer.

The same rule leaves the neighbouring case alone. A reduction along one
policy's own periods -- the present value that sums that policy's own
discounted cashflows -- ran over values the sampled row holds in full, so
substituting them states nothing untrue and the walk-through keeps it.

**A per-period line is walked through as the timeline it is.** One line of
a projection computes eighty-four months in one closed form, and showing
month zero's arithmetic for it is the same misrepresentation in a milder
key: true of one period, silent about the other eighty-three, and silent
about which period a reader is looking at. So a per-period operand is
substituted as its run of values and the step says how many periods it
covers -- and a reader who wants one period asks for it, at which point
the step names the period it is showing.

**And a named operation says what it means.** A substitution shows the
arithmetic of a line and nothing else, which for ``a * b - c`` is the whole
of it and for ``.cumulative_survival()`` is almost none of it. So a step
whose operation the format names carries one sentence saying what that
operation did, parameterised by the node's own configuration and the run in
front of the reader. The sentences live in ``trace_voice``, which answers
for every identifier the format owns.

That sentence is written **whether or not the line substitutes anything**.
A column that arrived from a join and a column the projection axis minted
read no column at all, so there was nothing to put a number into and the
step they would have ridden on was never written -- which left the two
operations the specification states semantics for saying nothing in any
document, with their sentences reachable only from the table. A node whose
operation the format names emits its step, with the rendered formula or the
operation's own name as the expression and never an invented number.

Beside that, two lines a reader would otherwise have to work out by
squinting at the numbers: the run's own shape (how long, where it starts
and ends, which way it moves, whether anything in it is not a number or
has gone negative), and, where something in that shape is anomalous, one
pointer at the period it happens in, with the rule that selected it stated
in the same sentence. Where nothing is anomalous there is no pointer.
Silence is a statement here, and inventing a hotspot would waste the
reader's attention on the model that is fine.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Final

from .trace_voice import (
    OVER_A_GROUP,
    folded_down_the_model_points,
    over_the_model_points,
    sentence_for,
    why_a_folded_operand_is_not_substituted,
    why_no_substitution,
)
from .value_extractor import spelled_for_the_wire

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio._semantic.ir import OpNode

# How many of a run's opening values are printed before the ellipsis. Three
# and the last is enough to see a level, a direction and an endpoint, which
# is what the shape line then states exactly.
_HEAD: Final[int] = 3

# Below this size a number is printed to six decimal places rather than to
# six significant figures, so that it never prints in exponent form:
# 0.00001234 reads as 0.000012, not as 1.234e-05.
_FIXED_POINT_BELOW: Final[float] = 0.01

# The mark standing for the periods a rendering does not print. Two dots
# rather than three so that it cannot be read as the Python ellipsis a
# value sample writes when its own window ends early.
_ELIDED: Final[str] = "‥"

# What separates the readings on a shape line. One glyph, so that a reader
# scanning a column of these lines sees the same fields in the same places.
_FIELD: Final[str] = " · "

# Which way a run moves, from the strongest reading to the weakest. A run
# that never moves is flat rather than rising: calling it either arrow
# would be a false statement about a column that is doing nothing, which is
# itself worth seeing.
_RISING: Final[str] = "↑"
_FALLING: Final[str] = "↓"
_FLAT: Final[str] = "flat"
_MIXED: Final[str] = "mixed"

# What a run whose direction cannot be read says instead. **A run that
# never moves and a run nobody can measure are two different facts**, and
# ``flat`` is the first of them: the module's own constant block calls it a
# positive claim about a column that is doing nothing. A run of dates, a
# run of masks, a banded label -- none of them is a level, and the two
# endpoints a shape line prints beside this token are years apart on the
# first of the three. So the direction field says it has nothing to read
# rather than reading zero.
_UNREADABLE: Final[str] = "no direction to read"

# What a run holding no numbers says where the two counts of numbers would
# otherwise go. **The same reading as the direction field beside it.** "0
# without a number" over a run of boundary dates says that no period of it
# is missing a number, which a reader takes as every period holding one --
# a positive claim about a column that holds none. A run whose periods are
# *all* genuinely empty is a different thing and keeps its count: "every
# period holds no number" is true, useful, and what the pointer says as
# well. A run holding some labels and some holes is this one -- it holds no
# numbers -- and its holes are counted beside this as empty periods, which
# is what they are.
_NO_NUMBERS: Final[str] = "no numbers in this run to count"

# How much of a run's whole period-to-period movement one move has to be
# before it is worth pointing at. Half means no smooth ramp ever qualifies
# -- every move of a straight line is a small share of the total -- and a
# single break that dominates the timeline always does. The bar is stated
# in the pointer's own sentence, so a reader is never left guessing what
# "largest" was measured against.
_DOMINATES: Final[float] = 0.5

# How many period-to-period moves a run needs before "more than half of all
# the movement" says anything. A two-period run has one move, which is
# always the whole of the movement and points at nothing; three is the
# shortest run where the share can separate one break from a ramp. The bar
# is stated in the pointer's own sentence for the same reason the share is.
_MOVES_TO_READ: Final[int] = 3

# How many compiled column-name patterns are kept. A model's widest line
# reads a handful of columns and a whole model a few hundred distinct
# names, so this holds the working set of an export without growing with
# the number of lines walked through.
_NAMES_CACHED: Final[int] = 512


@dataclass(frozen=True, slots=True)
class FoldReading:
    """What folds in one node's expression, as a walk-through has to take it.

    Three answers rather than one, because a walk-through has two different
    questions to put and they used to be answered by the same flag.

    ``outermost`` is what the *line* is: whether this node's own result is
    one value for the whole frame. It is what a step may announce, because
    it is what a reader compares against the result printed two lines below
    it. A fold *inside* a line that still answers once per policy is not
    this -- ``af.share = af.claims / af.claims.polars_native().sum()`` reaches the
    sampled
    policy's own share, and a step announcing a fold there contradicts the
    result under it.

    ``over_the_model_points``, ``over_a_group`` and
    ``over_an_unnamed_population`` are what may be *substituted*: the
    columns read inside something that folded, which the sampled policy's
    own value does not stand for even where the line around them answers
    once per policy. They are kept apart because a total over the export's
    rows and a total over one product are different populations, and naming
    either by the other's name is the falsehood this reading exists to
    avoid.

    The third of them is the population **nobody could read** -- an
    aggregate the caller's probe could not place, because the engine's own
    account of the expression was in a spelling this build does not speak.
    It is a separate answer rather than a fallback to the widest one, since
    filing it under the export's rows would print exactly the claim the
    split exists to stop, and would print it in the case where least is
    known.
    """

    outermost: bool = False
    over_the_model_points: tuple[str, ...] = ()
    over_a_group: tuple[str, ...] = ()
    over_an_unnamed_population: tuple[str, ...] = ()


# The reading for a line the fold probe was never put to -- one whose
# formula reaches into no engine, and so one that cannot fold anything.
# A module-level value rather than a default built at each call, so that
# the signature's default is a thing rather than a call.
NOTHING_FOLDED: Final[FoldReading] = FoldReading()


@dataclass
class TraceStep:
    """Represents a single step in a calculation trace."""

    step: int
    expr: str
    values: dict[str, float | int | str | None] | None = None
    result: float | int | str | None = None
    shape: str | None = None
    pointer: str | None = None
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        The one place a step's numbers leave the walk-through, so the one
        place a NaN or an infinity among them is spelled as section 10's
        sentinel: the walk-through measured them as floats, and the document
        carries them as the strings JSON can hold.
        """
        d: dict[str, Any] = {"step": self.step, "expr": self.expr}
        if self.values is not None:
            d["values"] = spelled_for_the_wire(self.values)
        if self.result is not None:
            d["result"] = spelled_for_the_wire(self.result)
        if self.shape is not None:
            d["shape"] = self.shape
        if self.pointer is not None:
            d["pointer"] = self.pointer
        if self.comment is not None:
            d["comment"] = self.comment
        return d


def _model_points(population: int | None) -> str:
    """Return how the population a fold ran over is named in a sentence.

    Written once because two lines say it -- what was folded, and why no
    number is shown -- and a reader meeting two different counts in one
    step would be right to distrust both.

    A count of None is the case where the caller could not say how many
    rows it saw. "The model points" without a number is still the true
    statement; inventing a count would not be.
    """
    if population is None:
        return "the model points"
    return f"{population} model points"


def _window(period: int | None, periods: int) -> str:
    """Return what a step says about which periods it is showing.

    Always something, and that is the point: a walk-through of one period
    of a run that has eighty-four leaves a reader to assume which one, and
    the assumption a reader makes -- the first -- is right only until
    somebody pins a different one.
    """
    if period is None:
        return f"({periods} periods)"
    return f"(period {period} of {periods})"


def _which_period(period: int | None, periods: int) -> str:
    """Return which single period of a run one value stands for.

    Said in the default case as much as in the pinned one. The first period
    is what a walk-through has always named there, and naming it is the
    difference between a reader knowing that and assuming it.
    """
    return f"period {period if period is not None else 0} of {periods}"


def _is_number(value: Any) -> bool:  # noqa: ANN401 -- a sampled value is any of them
    """Whether a sampled value is a number the shape line can measure.

    A NaN is not one. It is the float a period holds where a division
    reached zero over zero, and it answers False to every comparison, so a
    reading that let it through would report the run on both sides of it as
    mixed. The shape line already counts it under "without a number", which
    is the same reading said once.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and not (isinstance(value, float) and math.isnan(value))
    )


def _not_a_number(values: list[Any]) -> list[int]:
    """Return the periods holding a value that is not a number, in order.

    A null and a NaN are both counted: a period with no value and a period
    whose value is the result of dividing zero by zero are two different
    bugs and one reading -- there is no number there — and a shape line
    that counted only one of them would be silent about a run that is half
    missing.
    """
    return [
        index
        for index, value in enumerate(values)
        if value is None or (isinstance(value, float) and math.isnan(value))
    ]


def _negative(values: list[Any]) -> list[int]:
    """Return the periods holding a negative value, in order."""
    return [
        index for index, value in enumerate(values) if _is_number(value) and value < 0
    ]


def _empty_periods(missing: list[int]) -> str:
    """Return how many periods of a run holding no numbers are empty at all.

    Said only beside :data:`_NO_NUMBERS`, and it is the half of the old
    reading that was true. Four of a banded label's seven periods holding
    nothing is worth a reader's attention; "without a number" was simply the
    wrong name for it beside a run where no period has one.

    A NaN counts as an empty period, which is the reading
    :func:`_not_a_number` takes and the reading the pointer beside this
    field states in words: a period holding neither a number nor a value.
    """
    periods = "period" if len(missing) == 1 else "periods"
    return f"{len(missing)} empty {periods} (first at t={missing[0]})"


def _counts_of_numbers(values: list[Any]) -> list[str]:
    """Return the shape line's counts of numbers, in its own field order.

    Both of them are readings of numbers. A run of period boundary dates, a
    run of masks, a run of banded labels holds none, so both counts come
    back zero -- and a zero here is not an absence of a reading but a
    reading: "no period is missing a number" is how a reader takes it, of a
    column where no period has one. That is the ``flat`` falsehood in a
    different field, and the answer is the same one: say there is nothing to
    count.

    **Whether the run holds a number is the whole of that question.**
    Whether any period of it is empty is a different one, and asking the two
    together sent every non-numeric run carrying a single hole back to the
    counting branch: a seven-period banded label with four empty periods
    printed "4 without a number" where all seven have none, and "0 negative"
    read off a run of strings, on the same line as a direction field saying
    -- correctly -- that it has none to read. Label and date columns acquire
    holes the ordinary way, through a conditional or a left join, so that is
    the common shape rather than an exotic one. The holes are still counted,
    under the name of what they are.

    **A run of holes is not that run.** Where *every* period is genuinely
    empty, the count of the periods without a number is the true reading of
    it and it stays: it is what the pointer beside it names first. A run
    with no periods at all keeps that reading too, having nothing to name.
    """
    missing = _not_a_number(values)
    every_period_empty = bool(values) and len(missing) == len(values)
    if not every_period_empty and not any(_is_number(value) for value in values):
        return [_NO_NUMBERS, _empty_periods(missing)] if missing else [_NO_NUMBERS]
    negative = _negative(values)
    return [
        f"{len(missing)} without a number"
        + (f" (first at t={missing[0]})" if missing else ""),
        f"{len(negative)} negative"
        + (f" (first at t={negative[0]})" if negative else ""),
    ]


# What a column reference looks like in the engine's own rendering, whole.
# Both of the wrapper's closing characters belong to the wrapper, and a
# pattern is the only way to say so: a bare strip of the trailing quote and
# bracket cannot tell the one that closes ``col("age")`` from the one that
# closes ``.then("Yes")``. The name is whatever is not the quote that ends
# it, so a name holding a bracket -- ``col("claims (gross)")`` -- survives.
_DOUBLE_QUOTED_COLUMN: Final[re.Pattern[str]] = re.compile(r'col\("([^"]*)"\)')
_SINGLE_QUOTED_COLUMN: Final[re.Pattern[str]] = re.compile(r"col\('([^']*)'\)")


@lru_cache(maxsize=_NAMES_CACHED)
def _name_here(name: str) -> re.Pattern[str]:
    """Return the pattern matching one column name where it stands as a name.

    Bounded on both sides by what cannot be part of a name, so ``a`` is the
    operand in ``a * b`` and is text in ``mean``. A plain text replacement
    did not make that distinction and put the sampled value in the middle of
    the operation the fold sentence beside it was pointing at.

    Cached because a projection substitutes the same handful of names on
    every one of its lines, and compiling the same pattern a hundred times
    is work an export does not need to do.
    """
    return re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")


def _direction(values: list[Any]) -> str:
    """Return which way a run moves, over the periods that hold a number.

    Non-numeric periods are stepped over rather than breaking the reading:
    a fund that is missing one month has still risen or fallen across the
    months it has, and reporting that run as mixed would hide the trend
    behind a hole. A NaN is stepped over as a null is, which is what
    :func:`_is_number` already says it is.

    **A run with fewer than two numbers in it has no direction, and that is
    not the same as never moving.** A run of period boundary dates, a run of
    masks, a run of banded labels: none of them is a level, and ``flat`` --
    which this module defines as a positive claim about a column doing
    nothing -- would be a false reading of every one of them. Those say they
    have no direction to read. ``flat`` stays for a run of numbers that does
    not move.
    """
    numbers = [value for value in values if _is_number(value)]
    if len(numbers) < 2:  # noqa: PLR2004 -- one number is nothing to compare
        return _UNREADABLE
    steps = [b - a for a, b in pairwise(numbers)]
    if all(step == 0 for step in steps):
        return _FLAT
    if all(step >= 0 for step in steps):
        return _RISING
    if all(step <= 0 for step in steps):
        return _FALLING
    return _MIXED


def _hotspot(values: list[Any]) -> str | None:
    """Return one pointer at the period worth looking at, or None.

    Three readings, strongest first, and only one is ever written: a
    reader given three pointers has to decide which matters, which is the
    work the pointer exists to do for them.

    A period holding no number comes first -- everything downstream of it
    is arithmetic over a hole. A sign change comes next, because a reserve
    or an account value crossing zero is a thing that happened rather than
    a thing that drifted. Last, one period-to-period move that is more than
    half of all the movement in the run: a smooth ramp never qualifies, and
    a single break always does.

    **That last reading needs a run long enough to be a reading.** A
    two-period run has one move, and one move is always the whole of the
    movement, so every such run would carry a pointer at the only thing it
    does. The share is taken over :data:`_MOVES_TO_READ` moves or more, and
    the pointer's own sentence says so.

    **None where nothing qualifies**, which is a statement rather than an
    omission. A model whose timeline is unremarkable should read as one.
    """
    missing = _not_a_number(values)
    if missing:
        return (
            f"no value at t={missing[0]} (the first period holding neither "
            "a number nor a value at all)"
        )
    numbers = [
        (index, value) for index, value in enumerate(values) if _is_number(value)
    ]
    for (_, before), (index, after) in pairwise(numbers):
        if (before < 0) != (after < 0):
            return (
                f"first sign change at t={index} (the first period whose "
                "sign differs from the period before it)"
            )
    steps = [
        (index, abs(after - before))
        for (_, before), (index, after) in pairwise(numbers)
    ]
    total = sum(step for _, step in steps)
    if len(steps) < _MOVES_TO_READ or total == 0:
        return None
    index, largest = max(steps, key=lambda step: step[1])
    if largest <= _DOMINATES * total:
        return None
    return (
        f"largest single-period move at t={index} (more than half of all "
        "the period-to-period movement in this run, a reading taken only "
        f"over {_MOVES_TO_READ} moves or more)"
    )


def _minimal_clean(formula: str) -> str:
    """Return one rendered expression as a walk-through's first line shows it.

    Simple string replacements rather than a parse: the engine's rendering is
    read for a reader's benefit and never for a machine's, so nothing here
    has to reconstruct what it meant.

    **The column wrapper is matched whole.** ``col("profit")`` closes on two
    characters, a quote and a bracket, and stripping the opening ``col("``
    and then every ``")`` that followed it took the closing quote and
    bracket off every *string literal* in the same line -- so
    ``.then("Yes").otherwise("No")`` reached a reader as
    ``.then("Yes.otherwise("No``, and ``== ("M")`` as ``== ("M``. The
    literal is the half of a conditional an actuary opens the walk-through
    to find, so the wrapper is matched as one pattern and a literal is left
    as the model wrote it.

    Written at module level rather than on the generator because a second
    reader holds one of these lines up against the rendering beside it
    (:mod:`gaspatchio.frame.graph.validate`), and two implementations of one
    transform inside one package would eventually disagree -- with the one
    that disagreed being whichever nobody was running when the corpus was
    taken. Nothing here reads the state of a walk-through in progress.
    """
    clean = formula

    # Remove Polars column syntax, wrapper and both of its closing characters
    clean = _DOUBLE_QUOTED_COLUMN.sub(r"\1", clean)
    clean = _SINGLE_QUOTED_COLUMN.sub(r"\1", clean)

    # Remove type hints
    clean = clean.replace("dyn int: ", "")
    clean = clean.replace("dyn float: ", "")
    clean = clean.replace("dyn str: ", "")

    # Clean up list/array notation
    clean = clean.replace("[(", "(").replace(")]", ")")
    clean = clean.replace("[", "").replace("]", "")

    # Remove method calls that don't affect the visual representation
    clean = clean.replace(".eval()", "")
    # The list namespace and nothing longer: ``.list.len()`` reads as
    # ``.len()``, and a name that merely begins with ``list`` is left whole.
    clean = clean.replace(".list.", ".")
    clean = clean.replace(".element()", "")

    # Simplify common operations
    if ".clip(" in clean:
        # Simple handling of clip - just show it was clipped
        clean = clean.split(".clip(")[0] + " [clipped]"

    if "lookup_by_table_and_hash" in clean:
        # Simplify lookup operations
        clean = clean.split(".lookup_by_table_and_hash")[0] + " [lookup]"

    # Clean up extra spaces
    while "  " in clean:
        clean = clean.replace("  ", " ")

    return clean.strip()


class TraceGenerator:
    """Generates calculation traces for computed nodes.

    This simplified version avoids regex and complex parsing, focusing on
    showing the formula, value substitution, and final result.
    """

    def __init__(
        self,
        dependency_values: dict[str, Any],
        *,
        population: int | None = None,
        period: int | None = None,
    ) -> None:
        """
        Initialize with dependency values.

        Args:
            dependency_values: Map of column names to their sample values.
                A per-period column's entry is the whole run of values, not
                the window a sample prints: the walk-through has things to
                say about the run as a whole that the window would have
                thrown away.
            population: How many model points the export read its values
                from -- the rows left after any filter, since a filtered
                export folded fewer of them. None where the caller cannot
                say, which is stated rather than guessed at.
            period: The projection period a walk-through of a per-period
                line is pinned to, or None to walk through every period at
                once. Either way the step says which, so that no reader has
                to assume.

        """
        self.dependency_values = dependency_values
        self.population = population
        self.period = period

    def generate_trace(
        self,
        formula: str,
        dependencies: list[str],
        result_value: object,
        *,
        folds: FoldReading = NOTHING_FOLDED,
        tree: OpNode | None = None,
    ) -> list[dict[str, Any]]:
        """
        Generate a simplified trace for a computed formula.

        This shows:
        1. The cleaned formula
        2. The formula with values substituted (if dependencies exist)
        3. The final result

        Args:
            formula: The raw formula string from the calculation record
            dependencies: List of dependency column names
            result_value: The final computed value, per-period columns
                whole -- the window this walk-through prints is taken here
                rather than before it, so that the run's own shape is still
                readable
            folds: What folds in this line, as :class:`FoldReading` states
                it. Where the line's own result is a fold, step two names
                what was folded and over how many model points and
                substitutes nothing: no one policy's value stands inside a
                fold that ran over every policy. Where the fold is only
                *inside* the line, the line keeps its walk-through and the
                folded operands keep their names.
            tree: The node's own operation tree, where it has one. What
                the substitution step reads to say what the operation
                means -- the arithmetic shows how a formula written with
                operators works, and says almost nothing about what a
                named operation did.

        Returns:
            List of TraceStep dictionaries

        """
        trace_steps = []
        periods = len(result_value) if isinstance(result_value, list) else None

        # Step 1: Show cleaned formula
        clean_formula = _minimal_clean(formula)
        trace_steps.append(TraceStep(step=1, expr=clean_formula).to_dict())

        if folds.outermost:
            trace_steps.append(
                self._fold_step(folds.over_the_model_points or dependencies)
            )
        # Step 2: the values put into the formula, what the operation means,
        # or both. Reached whether or not this line reads a column, because
        # what a named operation *did* is worth saying about a line that
        # substitutes nothing -- a column that arrived from a join and a
        # column the projection axis minted both read nothing at all, and
        # both were silent in every document this package writes while the
        # sentence for them sat unreachable in the table.
        else:
            substituted = self._substitution_step(
                clean_formula,
                dependencies,
                periods,
                sentence_for(tree, periods),
                self._withheld(folds),
            )
            if substituted is not None:
                trace_steps.append(substituted)

        # Final step: Show the result
        trace_steps.append(
            self._result_step(len(trace_steps) + 1, result_value, periods)
        )

        return trace_steps

    def _withheld(self, folds: FoldReading) -> dict[str, str | None]:
        """Return each operand no number may stand for, and what folded it.

        A column read inside a fold is one the sampled policy's own value
        does not stand for, whatever the line around it does. Which
        population it was folded over is carried alongside, because a total
        over the export's rows and a total over one product are different
        statements and the sentence has to make the right one.

        A column read inside both -- a whole-book total and a group total in
        one line -- is named by the wider of the two, which is the export.

        **None is the population nobody could read**, and it is carried as
        its own value rather than resolved to the widest one. The operand is
        still named as folded, which is what the reader needs; whose rows it
        folded over is the part this export cannot say, and a sentence that
        said "all the model points" there would be inventing the one fact
        the probe came back without.
        """
        withheld: dict[str, str | None] = {
            name: over_the_model_points(_model_points(self.population))
            for name in folds.over_the_model_points
        }
        for name in folds.over_a_group:
            withheld.setdefault(name, OVER_A_GROUP)
        for name in folds.over_an_unnamed_population:
            withheld.setdefault(name, None)
        return withheld

    def _substitution_step(
        self,
        clean_formula: str,
        dependencies: list[str],
        periods: int | None,
        sentence: str | None,
        withheld: dict[str, str | None],
    ) -> dict[str, Any] | None:
        """Return the step that puts the sampled values into the formula.

        A per-period operand goes in as its run of values rather than as
        one period of it, because a scalar times a run is the framework's
        own core idiom and the walk-through should show it as itself. A
        per-policy operand goes in as the number it is. Where a period is
        pinned, every per-period operand narrows to that period's own
        value, which is what a reader zooming in asked for.

        **A pinned period narrows nothing on a line that folds the periods
        away.** The present value of a whole cashflow run is one number per
        policy, and it was reached from every period of that run: putting
        one period of it inside the fold would be the model-point falsehood
        over again with the axes swapped. So the period narrows a step only
        where the step's own result has periods to narrow.

        **An operand inside a fold keeps its name.** ``withheld`` is what
        the caller found folded somewhere in the expression; those operands
        are left standing as they are written, and the step says which they
        were and over what they folded. The rest of the line is substituted
        as it always was, because the rest of the line is the sampled
        policy's own.

        **A name is replaced where it stands as a name and nowhere else.**
        ``a`` sits inside ``mean``, and a plain text replacement put the
        sampled value in the middle of it -- ``c.mean()`` came out as
        ``c.me(1)n()``, on exactly the operand the fold sentence beside it
        tells the reader to go and look at. The substitution is bounded by
        what can be part of a name, so a column is replaced where a reader
        would read it as one.

        Returns None where the step would say nothing at all: nothing
        substituted, nothing withheld, and no sentence to speak.
        """
        pinned = self.period if periods is not None else None
        expr_with_values = clean_formula
        values_used: dict[str, float | int | str | None] = {}

        # Sort dependencies by length (longest first) to avoid partial replacements
        sorted_deps = sorted(dependencies, key=len, reverse=True)

        for dep in sorted_deps:
            if dep in self.dependency_values and dep not in withheld:
                value = self.dependency_values[dep]
                formatted_value = self._format_value(value, pinned)

                # The column name where it stands as a name: bounded by
                # something that cannot be part of one, so `a` inside `mean`
                # is text and `a` beside an operator is the operand. Wrapped
                # in parentheses to maintain expression structure, and its
                # backslashes doubled so a value carrying one is put in as
                # itself rather than read as a group reference.
                substituted = f"({formatted_value})".replace("\\", "\\\\")
                expr_with_values, replaced = _name_here(dep).subn(
                    substituted, expr_with_values
                )
                if replaced:
                    values_used[dep] = self._operand_record(value, pinned)

        comment = self._comment(sentence, withheld)
        if not values_used and comment is None:
            return None
        if periods is not None:
            expr_with_values = f"{expr_with_values}  {_window(pinned, periods)}"
        return TraceStep(
            step=2,
            expr=expr_with_values,
            values=values_used or None,
            comment=comment,
        ).to_dict()

    def _comment(
        self, sentence: str | None, withheld: dict[str, str | None]
    ) -> str | None:
        """Return what this step says beside its arithmetic, or nothing.

        Two things may be said and both are sentences: what the operation
        means, and which operands carry no number because they folded. Said
        in that order, because the first is what the line did and the second
        is a note about how this walk-through of it reads.

        Operands are grouped by the population that folded them, ``None``
        -- the population nobody could read -- being one of those groups
        rather than a missing entry: the operands under it get a sentence
        that names them and stops short of whose rows they folded over.
        """
        said = [sentence] if sentence else []
        for over in dict.fromkeys(withheld.values()):
            folded = [name for name, scope in withheld.items() if scope == over]
            said.append(why_a_folded_operand_is_not_substituted(folded, over))
        return " ".join(said) or None

    def _result_step(
        self,
        step: int,
        result_value: Any,  # noqa: ANN401 -- one sampled value, of whatever type it holds
        periods: int | None,
    ) -> dict[str, Any]:
        """Return the last step: what the calculation reached.

        For a per-policy column, the number. For a per-period column, the
        run as a whole, its shape stated exactly beside it, and -- only
        where something in that shape is worth looking at -- one pointer at
        the period it happens in.

        ``result`` stays one value even there, because it is the field a
        reader's tools compare against the sample beside it. Which period
        that one value is, is said rather than left to be assumed.
        """
        if periods is None:
            return TraceStep(
                step=step,
                expr=self._format_value(result_value, None),
                result=result_value,
            ).to_dict()
        return TraceStep(
            step=step,
            expr=f"{self._format_value(result_value, self.period)}  "
            f"{_window(self.period, periods)}",
            result=self._at_period(result_value, self.period),
            shape=self._shape_line(result_value, periods),
            pointer=_hotspot(result_value),
            comment=f"``result`` is {_which_period(self.period, periods)}.",
        ).to_dict()

    def _shape_line(self, values: list[Any], periods: int) -> str:
        """Return the run's own shape, in one line, in a fixed field order.

        Length, where it starts, where it ends, which way it moves, how
        many periods hold no number, how many hold a negative one. It is
        the endpoint-and-sanity check an actuary does by eye on a printed
        projection, done once and stated, so that "month 12 is on fire" is
        visible without anybody naming a period to go and look at.
        """
        fields = [
            f"{periods} periods",
            f"first {self._format_scalar(values[0]) if values else 'none'}",
            f"last {self._format_scalar(values[-1]) if values else 'none'}",
            _direction(values),
            *_counts_of_numbers(values),
        ]
        return _FIELD.join(fields)

    def _fold_step(self, folded: Sequence[str]) -> dict[str, Any]:
        """Return the step for a line that folds down the model-point file.

        Two sentences, and neither of them is a substitution. The first
        names what was folded and the population it was folded over, which
        is what a reader needs and is the whole of what this export can
        honestly say about the operand. The second says why no numbers are
        there, because a step that simply went quiet reads as a producer
        that ran out of things to write rather than one that declined to
        write something untrue.

        ``folded`` is what the fold actually read, not the line's whole
        dependency list: a line reading four columns of which one was
        summed has three operands that were never folded, and naming them
        here would say something false about each of them.

        The population is the rows this export read, not "the book": a
        filtered export folded the rows the filter left, and the envelope's
        own filter is stated beside these values for the same reason.
        """
        return TraceStep(
            step=2,
            expr=folded_down_the_model_points(folded, _model_points(self.population)),
            comment=why_no_substitution(),
        ).to_dict()

    def _format_value(
        self,
        value: Any,  # noqa: ANN401 -- one sampled value, of whatever type it holds
        period: int | None,
    ) -> str:
        """Format a value for display in the trace.

        A per-period value renders as the run it is -- its opening values,
        the mark for the periods between, and where it ends -- unless a
        period is pinned, when it renders as that period's own value. The
        per-policy path is untouched: a number formats the way it always
        did, and the arithmetic shape of a per-policy walk-through with it.
        """
        if isinstance(value, list):
            return self._format_run(value, period)
        return self._format_scalar(value)

    def _format_run(self, value: list[Any], period: int | None) -> str:
        """Format a per-period value: one period of it, or the run of it."""
        if not value:
            return "[]"
        if period is not None:
            return self._format_scalar(self._at_period(value, period))
        if len(value) <= _HEAD + 1:
            shown = [self._format_scalar(item) for item in value]
        else:
            shown = [self._format_scalar(item) for item in value[:_HEAD]]
            shown += [_ELIDED, self._format_scalar(value[-1])]
        return "[" + ", ".join(shown) + "]"

    def _format_scalar(
        self,
        value: Any,  # noqa: ANN401 -- one sampled value, of whatever type it holds
    ) -> str:
        """Format one value -- never a run of them -- for display."""
        if isinstance(value, float):
            # Format floats nicely
            if abs(value) < _FIXED_POINT_BELOW and value != 0:
                return f"{value:.6f}".rstrip("0").rstrip(".")
            return f"{value:.6g}"
        if value is None:
            return "null"
        return str(value)

    def _at_period(self, value: Any, period: int | None) -> Any:  # noqa: ANN401 -- one sampled value
        """Return one period's own value, or None past the end of the run.

        A row whose own timeline is shorter than the pinned period reaches
        nowhere at that period, and null is the truth about it. Which
        period is being read is stated by every line that prints one, and
        the first period is what an unpinned run reports.
        """
        if not isinstance(value, list):
            return value
        index = period if period is not None else 0
        return value[index] if index < len(value) else None

    def _operand_record(
        self,
        value: Any,  # noqa: ANN401 -- one sampled value, of whatever type it holds
        period: int | None,
    ) -> float | int | str | None:
        """Return what the values map holds for one operand.

        A per-policy operand holds its number, which is what a reader
        checking the arithmetic needs. A per-period operand holds the
        rendering of its own run, with its own length beside it: the map
        would otherwise either carry an eighty-four-month timeline per
        operand or carry one period of it with nothing saying which.
        """
        if not isinstance(value, list):
            return value  # type: ignore[no-any-return]
        if period is not None:
            return self._at_period(value, period)  # type: ignore[no-any-return]
        return f"{self._format_run(value, None)} {_window(None, len(value))}"
