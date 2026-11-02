# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: What a write to a frame's query plan defined, read off Polars' plan
# ABOUTME: And which arriving columns hold values another frame calculated
"""Two things a frame cannot see in its own calculation log.

Both happen outside the log, and both leave a frame whose account of a
column is no longer what the column holds. This module reads the evidence
for each. Nothing here decides what the frame says about it; the frame
asks, and states what it is told.

**A write past the recording doors.** Every door the frame offers --
assignment, ``with_columns``, ``join``, ``rename`` and the rest -- sets the
query plan and logs what it set. A model can still assign ``af._df``
itself, and that write leaves no log entry. Where it writes a column the
frame had accounted for, a calculation it logged or a column the data
arrived with, the frame's account of that column stops being true:
``collect()`` returns what the write computed, and the formula the frame
shows is the one it replaced. :func:`read_plan_write` reads the plan before
and after the write and says which columns the write defined.

It reads Polars' own plan, through the traverser Polars keeps for its GPU
engine, and it reads the plan *unoptimised*. The optimiser fuses
consecutive ``with_columns`` steps, so the optimised plan would credit the
write with the columns the step before it defined. The traverser carries a
version, and :data:`PLAN_VERSION` is the one this reader was written
against. A plan of another version, a step the reader does not know, or a
plan that is not the old plan with steps added -- compared on its steps,
its text, the memory of every table it scans and what every expression
Polars' reader can show holds -- is reported as unreadable, and the caller
stops vouching for every column the frame accounted for rather than
guessing which of them moved. A plan that does not resolve at all is
reported as such: ``collect()`` refuses it, and there is no column for
anybody to read. The reader never raises. What it cannot read is a finding
for the caller to state, never an error in the line that wrote the plan.

**Values another frame calculated.** ``ActuarialFrame(df)`` over a
DataFrame that came out of another frame's ``collect()`` starts a new log,
and every column arrives as if the data had supplied it. A Polars
DataFrame carries no mark to say otherwise, and ``with_columns`` hands back
a new object, so neither a marker nor the object survives the reshaping a
setup step does. The memory does. A column is an Arrow array, and a column
nobody touched keeps the buffers the earlier collect produced through
``with_columns``, ``rename`` and ``select``. While those values are held --
by the earlier frame, which keeps them for ``continue_from=`` to check a
returning column against, or by the caller, as the DataFrame the collect
handed back -- that memory belongs to them and to nothing else, so a column
found in it is proof of where its values came from rather than a
coincidence of numbers. :class:`ComputedValues` indexes that memory, one
collect at a time and only when somebody asks.

What each reading cannot see is stated beside it.
"""

from __future__ import annotations

import json
import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

import polars as pl
from loguru import logger
from polars.exceptions import PanicException, PolarsError
from polars.interchange.protocol import CompatLevel

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from polars._plr import NodeTraverser

__all__ = [
    "PLAN_VERSION",
    "ColumnWritten",
    "ComputedValues",
    "Origin",
    "PlanReading",
    "PlanWrite",
    "ValuesAccount",
    "outputs_of",
    "plan_version",
    "read_plan_write",
    "root_table",
    "tables_in",
]

# The major version of Polars' plan traverser this reader was written
# against. The traverser reports its own version, and a plan of any other
# major is read as unreadable rather than walked: a step this reader takes
# for a filter could mean something else in a version it has not met.
PLAN_VERSION: Final = 14

# The steps that define columns by expression, and the field of the step that
# holds the expressions defining them.
_DEFINING_STEPS: Final[dict[str, str]] = {"HStack": "exprs", "Select": "expr"}

# Steps that define no column: they keep, drop, reorder, filter or repeat
# rows, or keep only some columns.
_ROW_STEPS: Final = frozenset(
    {"Cache", "Distinct", "Filter", "SimpleProjection", "Slice", "Sort"}
)

# Steps that bring columns in beside their first input's: a join's right-hand
# columns, a horizontal concatenation's other parts. Every name the step's
# output holds that its first input does not is a column the step defined.
# Polars refuses a name that collides, so these are new names -- unless the
# same write dropped the name first, and then the step put a column back
# under it that the frame's account does not describe.
_ADDING_STEPS: Final = frozenset({"HConcat", "Join"})

# The functions that leave a column's values as they were: a mark that the
# column is sorted, whichever way, and taking every row from the first. A
# column handed back through them under its own name is a column handed back
# unchanged, as it is through a cast to the type it already has. Matched on
# the function's name, or on the name and its amounts.
_KEEPING_FUNCTIONS: Final = frozenset({("set_sorted",), ("gather_every", 0, 1)})

# The functions that move a column's rows without computing a value: turned
# upside down, moved down or up with nulls in the rows left behind, or every
# nth row kept. Applied alike to every column a step's input holds, each under
# its own name, they move whole rows, and a row still holds its own values.
_ROW_MOVES: Final = frozenset({"gather_every", "reverse", "shift"})

# The functions behind a ``MapFunction`` step that bring columns in the same
# way: a row index, a struct's fields, and a sortedness hint, which brings
# none. Exploding, unpivoting and every other function reshape or rewrite what
# they touch, and are unknown here. A step in none of these tables is unknown,
# and an unknown step makes the write unreadable.
_ADDING_FUNCTIONS: Final = frozenset({"hint_sorted", "row_index", "unnest"})


@dataclass(frozen=True, slots=True)
class PlanWrite:
    """What one write past the recording doors did to a frame's plan.

    Attributes:
        resolves: False where the new plan does not resolve. ``collect()``
            refuses such a plan, so no column holds anything a reader could
            be misled by.
        readable: False where the reader could not tell which columns the
            write defined: a plan of another version, a step it does not
            know, or a plan that is not the old one with steps added.
        wrote: The columns the write's own steps defined, where readable. A
            step that hands a column back unchanged -- ``pl.col("x")`` under
            its own name -- defines nothing.
        holds: The columns the new plan holds, or None where even that could
            not be read.
        schema: The type of each column the new plan holds, read in the same
            pass as ``holds``, or None where it could not be read.
        reading: The new plan, read, for the frame to keep: the next write
            past the doors starts from this plan, and need not read it again.
        rescanned: True where the new plan is nothing but a table in memory --
            values handed over in place of a plan, such as
            ``af._df.collect().lazy()``.

    """

    resolves: bool
    readable: bool
    wrote: frozenset[str] = frozenset()
    holds: frozenset[str] | None = None
    schema: Mapping[str, pl.DataType] | None = None
    reading: PlanReading | None = None
    rescanned: bool = False

    def overwritten(self, accounted: Iterable[str]) -> frozenset[str]:
        """Return which of ``accounted`` the write left the frame unable to vouch for.

        ``accounted`` is every column the frame could account for just
        before the write: a calculation it logged, or a column the data
        arrived with. A readable write leaves unvouched exactly the ones it
        defined that the plan still holds. An unreadable one leaves every
        one of them the plan still holds, because the frame cannot say
        which moved and will not guess. A plan that does not resolve leaves
        none: nothing can be collected from it.

        Args:
            accounted: The columns the frame accounted for before the write.

        Returns:
            The accounted columns whose account the write made untrue, or
            may have.

        """
        if not self.resolves:
            return frozenset()
        known = frozenset(accounted)
        held = known if self.holds is None else known & self.holds
        if not self.readable:
            return held
        return held & self.wrote


# What the reader logs, with the exception it caught, when it reports a plan
# as unreadable rather than raise into the model's line.
_UNREAD: Final[str] = (
    "The plan reader could not read {what}, so the write is recorded as "
    "unreadable and goes ahead as it would have."
)


def read_plan_write(
    before: pl.LazyFrame,
    after: pl.LazyFrame,
    *,
    before_reading: PlanReading | None = None,
) -> PlanWrite:
    """Return what writing ``after`` over ``before`` defined, as the plan says.

    ``before`` is the plan the frame held and ``after`` the one written over
    it. Never raises: a plan that cannot be read is reported as unreadable,
    and a plan that does not resolve as such, so that the write that
    produced it goes ahead exactly as it always has.

    ``after`` is read as ``before`` with steps added. The steps they share
    are compared by kind, by the plan's own text -- every expression, every
    join key -- by the memory of every table in memory they scan, a join's
    right-hand table included, and by what each expression Polars' reader
    can show holds: every value written as a literal, a column of values
    included, and every parameter, such as a rounding's places or a running
    total's direction, which the text shortens, rounds or leaves out. So a
    plan rebuilt in the same shape over other values or other formulas is
    not taken for the plan the frame held. The added steps are then read for
    the columns they define:
    the names their expressions write, and the names a join, a horizontal
    concatenation, a row index or an unnested struct brings in beside its
    first input's.

    **What it cannot see.** Only the two plans it is handed: a write that
    never reaches the frame's own setter is not read at all. A step that
    reorders, filters or moves whole rows defines no column -- a sort, and
    ``reverse()``, ``shift()`` or ``gather_every()`` of the whole frame --
    and neither does one that hands a column back under its own name, as it
    was, only marked sorted or cast to the type it has. The same move made
    to some columns and not others defines each column it moves. An
    expression Polars' reader has no view of -- a list function, a plugin
    such as an assumption lookup, a cut, a Python function -- is compared on
    its text alone, so a difference inside one that the text does not print,
    such as which table a lookup reads or a cut's breaks, is not seen.

    Args:
        before: The plan the frame held before the write.
        after: The plan the write handed it.
        before_reading: ``before``, already read, where the frame kept the
            reading from the write that made it. Read here otherwise.

    Returns:
        A :class:`PlanWrite` saying whether the new plan resolves, whether
        the reader could read it, which columns its new steps defined, and
        which columns it holds, with the new plan's reading.

    """
    try:
        schema = dict(after.collect_schema())
    except (PolarsError, PanicException):
        return PlanWrite(resolves=False, readable=False)
    except Exception:  # noqa: BLE001 -- the reader never raises into the model's line
        logger.opt(exception=True).debug(_UNREAD, what="the written plan's schema")
        return PlanWrite(resolves=True, readable=False)
    holds = frozenset(schema)
    try:
        reading = read_plan(after)
    except (Exception, PanicException):  # noqa: BLE001 -- as above
        logger.opt(exception=True).debug(_UNREAD, what="the written plan")
        return PlanWrite(resolves=True, readable=False, holds=holds, schema=schema)
    rescanned = [kind for kind, _node, _index in reading.steps] == ["DataFrameScan"]
    try:
        held = read_plan(before) if before_reading is None else before_reading
        wrote = _columns_defined(held, reading)
    except (Exception, PanicException):  # noqa: BLE001 -- as above
        logger.opt(exception=True).debug(_UNREAD, what="the columns the write defined")
        wrote = None
    return PlanWrite(
        resolves=True,
        readable=wrote is not None,
        wrote=frozenset() if wrote is None else wrote,
        holds=holds,
        schema=schema,
        reading=reading,
        rescanned=rescanned,
    )


@dataclass(frozen=True, slots=True)
class PlanReading:
    """One plan, read once: its steps down its first inputs, and its text.

    Attributes:
        traverser: Polars' traverser over the plan as written, unoptimised.
        steps: Each step from the top of the plan down its first inputs, as
            its kind, its node and its index in the traverser: a step's
            first input is the frame it was applied to, so these are the
            history of the frame a write adds to.
        text: The plan's own unoptimised text, line by line: every
            expression and every join key, though not which table in memory
            a scan reads, nor every value or parameter an expression holds,
            which :func:`_held_by_step` reads off the plan itself.
        held: What :func:`_held_by_step` read, once it has: it is read only
            when a write's plan is compared with this one, and then kept,
            because the frame keeps this reading for its next write.

    """

    traverser: NodeTraverser
    steps: tuple[tuple[str, Any, int], ...]
    text: tuple[str, ...]
    held: list[tuple[tuple[object, ...], ...]] = field(
        default_factory=list, compare=False, repr=False
    )


def read_plan(plan: pl.LazyFrame) -> PlanReading:
    """Return ``plan`` read once, for a write over it to be compared with.

    Raises:
        Exception: Whatever Polars raises for a plan it cannot walk; the
            callers here take that as a plan they cannot read.

    """
    traverser = _traverser(plan)
    root = traverser.get_node()
    steps: list[tuple[str, Any, int]] = []
    while True:
        index = traverser.get_node()
        node = traverser.view_current_node()
        steps.append((type(node).__name__, node, index))
        inputs = traverser.get_inputs()
        if not inputs:
            break
        traverser.set_node(inputs[0])
    traverser.set_node(root)
    text = tuple(plan.explain(optimized=False).splitlines())
    return PlanReading(traverser=traverser, steps=tuple(steps), text=text)


def tables_in(plan: pl.LazyFrame) -> tuple[pl.DataFrame, ...]:
    """Return every table in memory ``plan`` scans, read without running it.

    The tables a plan holds as values -- ``pl.DataFrame.lazy()``, a
    ``LazyFrame`` built from a dict -- rather than a file it reads when it
    runs. Empty where the plan scans none, and where Polars' traverser
    cannot walk it: what cannot be read is not found, which says less and
    never says wrong.
    """
    try:
        traverser = _traverser(plan)
        found: list[pl.DataFrame] = []
        pending = [traverser.get_node()]
        while pending:
            traverser.set_node(pending.pop())
            node = traverser.view_current_node()
            if type(node).__name__ == "DataFrameScan":
                found.append(pl.DataFrame._from_pydf(node.df))  # noqa: SLF001 -- as in _scanned
            pending.extend(reversed(traverser.get_inputs()))
    except (Exception, PanicException):  # noqa: BLE001 -- unreadable, so nothing found
        logger.debug("A plan's tables in memory could not be read.")
        return ()
    return tuple(found)


def root_table(plan: pl.LazyFrame) -> tuple[str, pl.DataFrame | None]:
    """Return what ``plan`` is built over: the step at the end of its first inputs.

    A frame's plan is the data it was built over with steps on top, each
    step applied to its first input; following first inputs down reaches
    that data. Returned as the step's kind and, where it is a table in
    memory, the table itself, read without running the plan -- a file scan
    or any other source comes back with no table. ``("unreadable", None)``
    where Polars' traverser cannot walk the plan.
    """
    try:
        traverser = _traverser(plan)
        while True:
            inputs = traverser.get_inputs()
            if not inputs:
                break
            traverser.set_node(inputs[0])
        node = traverser.view_current_node()
    except (Exception, PanicException):  # noqa: BLE001 -- unreadable, said so
        logger.debug("A plan's root could not be read.")
        return "unreadable", None
    kind = type(node).__name__
    if kind == "DataFrameScan":
        return kind, pl.DataFrame._from_pydf(node.df)  # noqa: SLF001 -- as in _scanned
    return kind, None


def scanned_tables(plan: pl.LazyFrame) -> list[pl.DataFrame]:
    """Return every table in memory ``plan`` scans, first inputs first.

    Read off Polars' traverser without running the plan; empty where it
    cannot walk the plan.
    """
    try:
        traverser = _traverser(plan)
        found: list[pl.DataFrame] = []
        pending = [traverser.get_node()]
        while pending:
            traverser.set_node(pending.pop())
            node = traverser.view_current_node()
            if type(node).__name__ == "DataFrameScan":
                found.append(pl.DataFrame._from_pydf(node.df))  # noqa: SLF001 -- as in root_table
            pending.extend(reversed(traverser.get_inputs()))
    except (Exception, PanicException):  # noqa: BLE001 -- unreadable, said so
        logger.debug("A plan's tables could not be read.")
        return []
    return found


def plan_version() -> tuple[int, int]:
    """Return the version of Polars' plan traverser in this process."""
    return _traverser(pl.LazyFrame()).version()


def _traverser(plan: pl.LazyFrame) -> NodeTraverser:
    """Return a traverser over ``plan`` as written, before any optimisation."""
    unoptimised = pl.QueryOptFlags.none()._pyoptflags  # noqa: SLF001 -- no public door
    return plan._ldf.with_optimizations(unoptimised).visit()  # noqa: SLF001 -- as above


def _columns_defined(before: PlanReading, after: PlanReading) -> frozenset[str] | None:
    """Return the columns the steps ``after`` adds over ``before`` defined.

    None where the answer cannot be read: another plan version, a step not
    in the tables above, or an ``after`` that is not ``before`` with steps
    added -- a different plan, or the same shape of plan over other values
    or other formulas.
    """
    if after.traverser.version()[0] != PLAN_VERSION:
        return None
    added = len(after.steps) - len(before.steps)
    if added < 0 or not _the_same_history(before, after, added):
        return None
    defined: set[str] = set()
    for kind, node, index in after.steps[:added]:
        named = _defined_by(after.traverser, kind, node, index)
        if named is None:
            return None
        defined |= named
    return frozenset(defined)


def _the_same_history(before: PlanReading, after: PlanReading, added: int) -> bool:
    """Return whether ``after``, below its ``added`` steps, is ``before``.

    Three readings, each of which a rebuilt plan can pass alone: the steps'
    kinds, the plan's text, which prints every expression and join key, and
    what the shared steps hold (:func:`_held_by_step`) -- the memory of
    every table in memory they scan, and the values and parameters of every
    expression Polars' reader can show, which the text names by their
    columns, shortens, rounds or leaves out. ``before``'s text must stand
    whole in ``after``'s, indented as one block, as a plan's text stands in
    the text of a plan built on it.
    """
    if [kind for kind, _node, _index in after.steps[added:]] != [
        kind for kind, _node, _index in before.steps
    ]:
        return False
    if not _stands_in(before.text, after.text):
        return False
    held, holds = _held_by_step(before), _held_by_step(after)[added:]
    return len(held) == len(holds) and all(
        _alike(mine, theirs) for mine, theirs in zip(held, holds, strict=True)
    )


def _alike(mine: tuple[object, ...], theirs: tuple[object, ...]) -> bool:
    """Return whether two steps hold alike: the same things, in the same order."""
    if len(mine) != len(theirs):
        return False
    for one, other in zip(mine, theirs, strict=True):
        if isinstance(one, _HeldValues) and isinstance(other, _HeldValues):
            if not one.matches(other):
                return False
        elif one != other:
            return False
    return True


def _stands_in(inner: tuple[str, ...], outer: tuple[str, ...]) -> bool:
    """Return whether ``inner`` is a block of ``outer``'s lines, indented as one."""
    if not inner:
        return True
    first = inner[0]
    for start in range(len(outer) - len(inner) + 1):
        line = outer[start]
        if not line.endswith(first):
            continue
        indent = line[: len(line) - len(first)]
        if indent.strip():
            continue
        if all(
            outer[start + offset] == indent + inner[offset]
            for offset in range(len(inner))
        ):
            return True
    return False


def _held_by_step(reading: PlanReading) -> tuple[tuple[object, ...], ...]:
    """Return what each step of ``reading`` holds, in the order of its steps.

    A step holds its own expressions, and every plan below it other than the
    first -- a join's right-hand side, a concatenation's other parts -- with
    theirs and the tables in memory they scan. Two plans whose steps hold
    alike are one history below the steps one adds. Read once per reading.
    """
    if reading.held:
        return reading.held[0]
    traverser = reading.traverser
    by_step: list[tuple[object, ...]] = []
    for _kind, node, index in reading.steps:
        found: list[object] = []
        _hold_step(traverser, node, found)
        traverser.set_node(index)
        for other in traverser.get_inputs()[1:]:
            _hold_below(traverser, other, found)
        by_step.append(tuple(found))
    reading.held.append(tuple(by_step))
    return reading.held[0]


def _hold_below(traverser: NodeTraverser, index: int, found: list[object]) -> None:
    """Add what every step of the plan under ``index`` holds to ``found``.

    In the order a walk down first inputs before later ones meets them, so
    that two plans of one shape list what they hold in the same order.
    """
    pending = [index]
    while pending:
        current = pending.pop()
        traverser.set_node(current)
        _hold_step(traverser, traverser.view_current_node(), found)
        traverser.set_node(current)
        pending.extend(reversed(traverser.get_inputs()))


# A step's links to the plans it reads, which are positions in one plan's
# reading and so are compared by walking them rather than as numbers.
_STEP_LINKS: Final = frozenset({"input", "input_left", "input_right", "inputs"})

# An expression's links to the expressions it reads, likewise.
_EXPRESSION_LINKS: Final = (
    "expr",
    "left",
    "right",
    "input",
    "idx",
    "by",
    "arguments",
    "predicate",
    "truthy",
    "falsy",
    "offset",
    "length",
    "function",
    "partition_by",
    "order_by",
)


# Each kind of view's fields, read off the kind once rather than off every
# view: its settings and values, and the links it reads other expressions by.
_FIELDS: dict[type, tuple[tuple[str, ...], tuple[str, ...]]] = {}


def _fields_of(
    view: object, links: Iterable[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return a view's own fields, sorted, and those of ``links`` it has, in order."""
    kind = type(view)
    known = _FIELDS.get(kind)
    if known is None:
        names = [name for name in dir(kind) if not name.startswith("_")]
        linked = tuple(name for name in links if name in names)
        known = _FIELDS[kind] = (
            tuple(sorted(name for name in names if name not in linked)),
            linked,
        )
    return known


def _hold_step(
    traverser: NodeTraverser,
    node: Any,  # noqa: ANN401 -- a plan step
    found: list[object],
) -> None:
    """Add what one step holds to ``found``: its table, settings and expressions."""
    found.append(type(node).__name__)
    own, _links = _fields_of(node, _STEP_LINKS)
    for name in own:
        value = getattr(node, name)
        if name == "df":
            found.append(_scanned(value))
            continue
        roots = _expression_roots(value)
        if roots is not None:
            for root in roots:
                _hold_expression(traverser, root, found)
            continue
        shown = _shown(value)
        if shown is not None:
            found.append((name, shown))


def _expression_roots(value: Any) -> list[int] | None:  # noqa: ANN401 -- a step's field
    """Return the expressions ``value`` holds, or None where it holds none."""
    items: list[Any] = list(value) if isinstance(value, list | tuple) else [value]
    if not items or any(type(item).__name__ != "PyExprIR" for item in items):
        return None
    return [item.node for item in items]


def _hold_expression(traverser: NodeTraverser, root: int, found: list[object]) -> None:
    """Add what one expression holds: each node's kind, parameters and values.

    An expression Polars' reader has no view of -- a list function, a
    plugin, a Python function -- is held as that it was met, and the text
    is all that compares it.
    """
    pending = [root]
    while pending:
        try:
            view = traverser.view_expression(pending.pop())
        except NotImplementedError as unshown:
            found.append(("unshown", str(unshown)))
            continue
        kind = type(view).__name__
        found.append(kind)
        own, links = _fields_of(view, _EXPRESSION_LINKS)
        for name in own:
            value = getattr(view, name)
            if kind == "Literal" and type(value).__name__ == "PySeries":
                found.append(_HeldValues(pl.Series._from_pyseries(value)))  # noqa: SLF001 -- the reader's own handle
                continue
            shown = _shown(value)
            if shown is not None:
                found.append((name, shown))
        pending.extend(reversed(_links_of(view, links)))


def _links_of(view: Any, links: tuple[str, ...]) -> list[int]:  # noqa: ANN401 -- an expression's view
    """Return the expressions one expression reads, in the order it reads them."""
    read: list[int] = []
    for name in links:
        value = getattr(view, name)
        if isinstance(value, int) and not isinstance(value, bool):
            read.append(value)
        elif isinstance(value, list | tuple):
            read.extend(
                item
                for item in value
                if isinstance(item, int) and not isinstance(item, bool)
            )
    return read


def _shown(value: object) -> str | None:
    """Return a setting or value as Polars states it, or None where that names memory.

    Every setting and value the reader shows is plain -- numbers, names,
    flags, types, the lists and tuples they make -- and its ``repr`` states
    it exactly. An object the reader hands over as itself states only where
    it sits in memory, which differs between two readings of one plan, so
    it is not compared at all and the text answers for it.
    """
    shown = repr(value)
    return None if " at 0x" in shown else shown


class _HeldValues:
    """A column of values an expression holds as a literal, for comparing.

    The text names it and nothing else. Two are alike where they occupy the
    same memory, which a plan built on another shares with it, or else
    where they hold the same values -- so a plan rebuilt over values handed
    over again reads as the plan it was, and one over other values does not.
    """

    __slots__ = ("identity", "values")

    def __init__(self, values: pl.Series) -> None:
        """Hold ``values``, and where Polars states it, the memory they occupy."""
        self.values = values
        self.identity = _native_identity(values)

    def matches(self, other: _HeldValues) -> bool:
        """Return whether ``other`` holds the same values as this does."""
        mine, theirs = self.values, other.values
        if mine.dtype != theirs.dtype or mine.len() != theirs.len():
            return False
        if self.identity is not None and self.identity == other.identity:
            return True
        return mine.equals(theirs, check_dtypes=True, check_names=True)


def _scanned(handle: Any) -> tuple[object, ...]:  # noqa: ANN401 -- the traverser's own handle
    """Return what identifies a scanned DataFrame: its height, schema and memory.

    The memory is read only where Polars states it itself, for the columns
    of a primitive kind, so that reading a write never loads Arrow. A
    DataFrame with no such column is compared on its height and schema.
    """
    frame = pl.DataFrame._from_pydf(handle)  # noqa: SLF001 -- the scan hands back Polars' own handle
    memory = tuple(
        _native_identity(frame.to_series(index)) for index in range(frame.width)
    )
    return (frame.height, tuple(frame.schema.items()), memory)


def _defined_by(
    traverser: NodeTraverser,
    kind: str,
    node: Any,  # noqa: ANN401 -- a plan step
    index: int,
) -> set[str] | None:
    """Return the columns one added step defined, or None for a step not known here."""
    if kind in _ROW_STEPS:
        return set()
    if kind in _ADDING_STEPS or (
        kind == "MapFunction" and node.function[0] in _ADDING_FUNCTIONS
    ):
        return _names_added(traverser, index)
    field_name = _DEFINING_STEPS.get(kind)
    if field_name is None:
        return None
    expressions = getattr(node, field_name)
    schema = _input_schema(traverser, index)
    if _moves_whole_rows(traverser, expressions, schema):
        return set()
    return {
        str(expression.output_name)
        for expression in expressions
        if _column_kept(traverser, expression.node, schema)
        != str(expression.output_name)
    }


def _input_schema(traverser: NodeTraverser, index: int) -> dict[str, pl.DataType]:
    """Return the types of the columns a step reads from its first input."""
    traverser.set_node(index)
    inputs = traverser.get_inputs()
    if not inputs:
        return {}
    traverser.set_node(inputs[0])
    return dict(traverser.get_schema())


def _column_kept(
    traverser: NodeTraverser, expression: int, schema: Mapping[str, pl.DataType]
) -> str | None:
    """Return the column whose values an expression is, unchanged, or None.

    The column itself, the column through a function that keeps every value
    where it was (:data:`_KEEPING_FUNCTIONS`), or the column cast to the
    type ``schema`` says it already has. Anything else computes its output,
    and so does an expression the traverser has no view of -- ``list.eval``
    is one -- which is all this needs to know of it. The one rule both doors
    that take a write read a column handed back by: a write past the
    recording doors, and ``select``.
    """
    try:
        view = traverser.view_expression(expression)
    except NotImplementedError:
        return None
    kind = type(view).__name__
    if kind == "Column":
        return str(view.name)
    if kind == "Cast":
        column = _column_kept(traverser, view.expr, schema)
        return (
            column if column is not None and schema.get(column) == view.dtype else None
        )
    if kind != "Function" or len(view.input) != 1:
        return None
    function = tuple(view.function_data)
    if function[:1] in _KEEPING_FUNCTIONS or function in _KEEPING_FUNCTIONS:
        return _column_kept(traverser, view.input[0], schema)
    return None


@dataclass(frozen=True, slots=True)
class ColumnWritten:
    """One column an expression writes, as the plan reader reads it.

    Attributes:
        name: The name the column is written under.
        kept: The column whose values it is, unchanged -- under its own name
            or another -- or None where the expression computes its values.
        written: The expression for this one column, as Python a model can
            write, or None where the reader cannot spell it.
        reads: The columns the expression reads, in the order it reads them.

    """

    name: str
    kept: str | None
    written: str | None
    reads: tuple[str, ...]


def outputs_of(
    schema: Mapping[str, pl.DataType], expression: pl.Expr
) -> tuple[ColumnWritten, ...]:
    """Return each column one expression writes over a frame of ``schema``.

    Read as a write past the recording doors is read (:func:`read_plan_write`),
    over the columns ``schema`` names, so a door that takes expressions
    directly hands back exactly what that reader hands back: a selector or
    ``pl.all()`` expanded to the columns it selects, each output with the
    column it is, unchanged, or with the calculation it is.

    Read over the columns the expression names where it names them all,
    which costs tens of microseconds, and over every column ``schema``
    holds only where it selects columns by kind or pattern, or names one
    the narrower reading cannot resolve: building an empty frame of a
    hundred columns to read it over costs about a millisecond.

    Raises:
        Exception: Whatever Polars raises for an expression that does not
            resolve over ``schema``.

    """
    named = _columns_named(schema, expression)
    if named is not None:
        try:
            return _outputs_over(named, expression)
        except Exception:  # noqa: BLE001 -- read again over every column below
            logger.debug("A select's expression is read over every column.")
    return _outputs_over(schema, expression)


def _columns_named(
    schema: Mapping[str, pl.DataType], expression: pl.Expr
) -> dict[str, pl.DataType] | None:
    """Return the columns of ``schema`` an expression names, or None if it selects."""
    meta = expression.meta
    if meta.has_multiple_outputs():
        return None
    names = meta.root_names()
    if any(name not in schema for name in names):
        return None
    return {name: schema[name] for name in names}


def _outputs_over(
    schema: Mapping[str, pl.DataType], expression: pl.Expr
) -> tuple[ColumnWritten, ...]:
    """Return each column one expression writes, over an empty frame of ``schema``."""
    traverser = _traverser(pl.LazyFrame(schema=dict(schema)).select(expression))
    step = traverser.view_current_node()
    return tuple(
        ColumnWritten(
            name=str(output.output_name),
            kept=_column_kept(traverser, output.node, schema),
            written=_written(traverser, output.node),
            reads=_reads(traverser, output.node),
        )
        for output in step.expr
    )


# The operators an expression's view names, as Python writes them.
_OPERATORS: Final[dict[str, str]] = {
    "Plus": "+",
    "Minus": "-",
    "Multiply": "*",
    "TrueDivide": "/",
    "FloorDivide": "//",
    "Modulus": "%",
    "Eq": "==",
    "NotEq": "!=",
    "Gt": ">",
    "GtEq": ">=",
    "Lt": "<",
    "LtEq": "<=",
    "And": "&",
    "Or": "|",
    "Xor": "^",
}

# The functions of one column and no parameter, which Python writes as a method.
_PLAIN_METHODS: Final = frozenset(
    {"abs", "ceil", "exp", "floor", "is_nan", "is_not_null", "is_null", "sign", "sqrt"}
)

# The casts Python writes without saying how strict: Polars' own default.
_STRICT_CAST: Final = 0
_LENIENT_CAST: Final = 1


def _written(traverser: NodeTraverser, expression: int) -> str | None:
    """Return one expression as Python a model can write, or None where it cannot.

    Spelt from the reader's view of it -- after Polars has resolved its
    types, so a number may read ``2.0`` where the model wrote ``2`` -- for
    columns, plain values, arithmetic and comparisons, conditionals, casts
    and a few functions. Anything else is not spelt rather than spelt wrong.
    """
    try:
        view = traverser.view_expression(expression)
    except NotImplementedError:
        return None
    spell = _SPELLINGS.get(type(view).__name__)
    return None if spell is None else spell(traverser, view)


def _written_column(_traverser: NodeTraverser, view: Any) -> str | None:  # noqa: ANN401 -- an expression's view
    """Return a column as Python."""
    return f"pl.col({_quoted(str(view.name))})"


def _written_literal(_traverser: NodeTraverser, view: Any) -> str | None:  # noqa: ANN401 -- an expression's view
    """Return a plain value standing alone as Python, or None."""
    value = _plain(view.value)
    return None if value is None else f"pl.lit({value})"


def _written_operation(traverser: NodeTraverser, view: Any) -> str | None:  # noqa: ANN401 -- an expression's view
    """Return an operator between two expressions as Python, or None."""
    operator = _OPERATORS.get(str(view.op).rsplit(".", 1)[-1])
    left, right = (_operand(traverser, link) for link in (view.left, view.right))
    if operator is None or left is None or right is None:
        return None
    if left.startswith("pl.") or right.startswith("pl."):
        return f"({left} {operator} {right})"
    return None


def _written_conditional(traverser: NodeTraverser, view: Any) -> str | None:  # noqa: ANN401 -- an expression's view
    """Return a when/then/otherwise as Python, or None."""
    parts = [
        _written(traverser, link) for link in (view.predicate, view.truthy, view.falsy)
    ]
    if None in parts:
        return None
    when, then, otherwise = parts
    return f"pl.when({when}).then({then}).otherwise({otherwise})"


def _operand(traverser: NodeTraverser, expression: int) -> str | None:
    """Return an operand as Python: a plain value where it is one, else as written."""
    try:
        view = traverser.view_expression(expression)
    except NotImplementedError:
        return None
    if type(view).__name__ == "Literal":
        return _plain(view.value)
    return _written(traverser, expression)


def _written_cast(traverser: NodeTraverser, view: Any) -> str | None:  # noqa: ANN401 -- an expression's view
    """Return a cast to a type of one plain name as Python, or None."""
    inner = _written(traverser, view.expr)
    dtype = repr(view.dtype)
    if inner is None or not dtype.isidentifier():
        return None
    if view.options == _STRICT_CAST:
        return f"{inner}.cast(pl.{dtype})"
    if view.options == _LENIENT_CAST:
        return f"{inner}.cast(pl.{dtype}, strict=False)"
    return None


def _written_function(traverser: NodeTraverser, view: Any) -> str | None:  # noqa: ANN401 -- an expression's view
    """Return one of a few functions of one column as Python, or None."""
    function = tuple(view.function_data)
    name = str(function[0]).rsplit(".", 1)[-1].lower()
    links = list(view.input)
    first = _written(traverser, links[0]) if links else None
    if first is None:
        return None
    if len(links) == 1:
        return _written_method(name, function, first)
    if (
        len(links) == _OPERAND_FUNCTION
        and len(function) == 1
        and name in {"pow", "fill_null"}
    ):
        operand = _operand(traverser, links[1])
        return None if operand is None else f"{first}.{name}({operand})"
    return None


def _written_method(name: str, function: tuple[object, ...], first: str) -> str | None:
    """Return a function of one column and its parameters as Python, or None."""
    prefix = {"negate": "-", "not": "~"}.get(name)
    if prefix is not None and len(function) == 1:
        return f"({prefix}{first})"
    if name in _PLAIN_METHODS and len(function) == 1:
        return f"{first}.{name}()"
    if name == "round" and len(function) == _ROUND_PARTS:
        _round, places, mode = function
        how = "" if mode == "half_to_even" else f", mode={_quoted(str(mode))}"
        return f"{first}.round({places}{how})"
    return None


# A function of a column and one operand: ``pow`` and ``fill_null``.
_OPERAND_FUNCTION: Final = 2

# A rounding's parts as the reader states them: the name, the places, the mode.
_ROUND_PARTS: Final = 3

# How each kind of expression the reader shows is spelt in Python.
_SPELLINGS: Final[dict[str, Callable[[NodeTraverser, Any], str | None]]] = {
    "Column": _written_column,
    "Literal": _written_literal,
    "BinaryExpr": _written_operation,
    "Ternary": _written_conditional,
    "Cast": _written_cast,
    "Function": _written_function,
}


def _plain(value: object) -> str | None:
    """Return a plain value as Python writes it, or None for any other."""
    if value is None or isinstance(value, bool | int | float):
        return repr(value)
    if isinstance(value, str):
        return _quoted(value)
    return None


def _quoted(text: str) -> str:
    """Return ``text`` as a double-quoted Python string, as the docs write names."""
    return json.dumps(text, ensure_ascii=False)


def _reads(traverser: NodeTraverser, expression: int) -> tuple[str, ...]:
    """Return the columns one expression reads, first read first, each once."""
    reads: list[str] = []
    pending = [expression]
    while pending:
        try:
            view = traverser.view_expression(pending.pop())
        except NotImplementedError:
            continue
        if type(view).__name__ == "Column" and str(view.name) not in reads:
            reads.append(str(view.name))
        _own, links = _fields_of(view, _EXPRESSION_LINKS)
        pending.extend(reversed(_links_of(view, links)))
    return tuple(reads)


def _moves_whole_rows(
    traverser: NodeTraverser,
    expressions: Iterable[Any],
    schema: Mapping[str, pl.DataType],
) -> bool:
    """Return whether a step moves every row of its input, and computes nothing.

    True where every expression is one row move (:data:`_ROW_MOVES`), the
    same move with the same amounts, of the column of its own name, and the
    step's expressions name every column of its input. That is
    ``LazyFrame.reverse()``, ``shift()`` and ``gather_every()`` as Polars
    writes them: every row moves and every column with it, so each row still
    holds its own values, as after a sort. One column moved alone, or
    columns moved apart, leave rows holding values of other rows.
    """
    moved: list[str] = []
    alike: tuple[object, ...] | None = None
    try:
        for expression in expressions:
            output = str(expression.output_name)
            view = traverser.view_expression(expression.node)
            if type(view).__name__ != "Function":
                return False
            function = tuple(view.function_data)
            column, *amounts = view.input
            if (
                function[0] not in _ROW_MOVES
                or _column_kept(traverser, column, schema) != output
            ):
                return False
            move = (function, *(_literal(traverser, amount) for amount in amounts))
            if None in move or (alike is not None and move != alike):
                return False
            alike = move
            moved.append(output)
    except NotImplementedError:
        return False
    return bool(moved) and moved == list(schema)


def _literal(traverser: NodeTraverser, expression: int) -> tuple[str, str] | None:
    """Return a literal expression's value and type, or None for any other."""
    view = traverser.view_expression(expression)
    if type(view).__name__ != "Literal":
        return None
    return (repr(view.value), str(view.dtype))


def _names_added(traverser: NodeTraverser, index: int) -> set[str] | None:
    """Return the names a step's output holds that its first input does not."""
    traverser.set_node(index)
    held = set(traverser.get_schema())
    inputs = traverser.get_inputs()
    if not inputs:
        return None
    traverser.set_node(inputs[0])
    return held - set(traverser.get_schema())


# --- Values another frame calculated ------------------------------------------

# One chunk's identity. A chunk of a primitive kind -- a number, a flag, a
# date, a category -- is identified by Polars' own account of its values
# buffer and its validity bitmap, which reads no data and loads nothing. The
# bitmap is part of it: a conditional can hand back a column's values buffer
# under new nulls, and those are other values. A chunk of any other kind is
# exported to Arrow, which states the address of every buffer under it, its
# children's included. A column's identity is its chunks' in order.
_Chunk = tuple[object, ...]
_Identity = tuple[_Chunk, ...]

# The key a column is indexed under: its type, its length and where its
# first value sits -- for a primitive kind, the address Polars states for
# it, which costs a few microseconds and loads nothing; for any other kind,
# the buffers Arrow names under a one-value slice. Enough to find every
# candidate; a candidate is confirmed on the whole identity, validity
# bitmaps included, before anything is said.
_Key = tuple[str, int, tuple[object, ...]]

# Arrow's newest layout, so that every Polars type exports its own buffers
# rather than a converted copy. A copy has an address of its own, and an
# identity taken from one would match nothing.
_NEWEST: Final = CompatLevel.newest()


def _native_chunk(chunk: pl.Series) -> _Chunk | None:
    """Return a primitive chunk's identity as Polars states it, or None."""
    try:
        values = chunk._get_buffer_info()  # noqa: SLF001 -- Polars' own account of the buffer
    except TypeError:
        return None
    validity = chunk._get_buffers()["validity"]  # noqa: SLF001 -- as above
    bitmap = None if validity is None else validity._get_buffer_info()  # noqa: SLF001
    return ("native", str(chunk.dtype), values, bitmap)


def _addresses(array: Any) -> tuple[int | None, ...]:  # noqa: ANN401 -- a pyarrow array
    """Return the address of every buffer under ``array``, None for an absent one."""
    return tuple(
        None if buffer is None else int(buffer.address) for buffer in array.buffers()
    )


def _chunk_identity(chunk: pl.Series) -> _Chunk:
    """Return one chunk's identity, from Polars where it can say and Arrow otherwise."""
    native = _native_chunk(chunk)
    if native is not None:
        return native
    array = chunk.to_arrow(compat_level=_NEWEST)
    return ("arrow", str(array.type), int(array.offset), len(array), _addresses(array))


def _holds_memory(chunk: _Chunk) -> bool:
    """Return whether a chunk's identity names memory of its own.

    A column of nulls has no buffer, and an empty chunk's buffer may be one
    every empty chunk shares, so neither identifies anything.
    """
    if chunk[0] == "native":
        values = chunk[2]
        return isinstance(values, tuple) and bool(values[2])
    addresses = chunk[-1]
    return isinstance(addresses, tuple) and any(item is not None for item in addresses)


def _identity(series: pl.Series) -> _Identity | None:
    """Return the memory ``series`` occupies, chunk by chunk, or None for none.

    Taken chunk by chunk because exporting a column of several chunks joins
    them into new memory, and new memory matches nothing. None for an empty
    column and for one with no buffer at all, and None too for a column that
    cannot be read this way, such as a column of Python objects: what cannot
    be identified is not found, which says less and never says wrong.
    """
    if series.len() == 0:
        return None
    try:
        chunks = tuple(_chunk_identity(chunk) for chunk in series.get_chunks())
    except (Exception, PanicException):  # noqa: BLE001 -- unidentifiable, so not found
        logger.debug(f"Column {series.name!r} has no memory identity to compare.")
        return None
    if not any(_holds_memory(chunk) for chunk in chunks):
        return None
    return chunks


def _native_identity(series: pl.Series) -> _Identity | None:
    """Return a primitive column's identity as Polars states it, or None for another."""
    found: list[_Chunk] = []
    try:
        for chunk in series.get_chunks():
            native = _native_chunk(chunk)
            if native is None:
                return None
            found.append(native)
    except (Exception, PanicException):  # noqa: BLE001 -- unidentifiable, so not compared
        return None
    return tuple(found)


def _key(series: pl.Series) -> _Key | None:
    """Return the key ``series`` is looked up under, or None where it has none."""
    if series.len() == 0:
        return None
    first = series.slice(0, 1)
    try:
        values = first._get_buffer_info()  # noqa: SLF001 -- as in _native_chunk
    except TypeError:
        values = None
    except (Exception, PanicException):  # noqa: BLE001 -- as in _identity
        return None
    if values is not None:
        return (str(series.dtype), series.len(), ("native", values))
    try:
        addresses = _addresses(first.to_arrow(compat_level=_NEWEST))
    except (Exception, PanicException):  # noqa: BLE001 -- as in _identity
        return None
    if all(address is None for address in addresses):
        return None
    return (str(series.dtype), series.len(), ("arrow", addresses))


@dataclass(frozen=True, slots=True)
class Origin:
    """Where a column's values were calculated: the definition, and its line.

    Attributes:
        node_id: The calculation graph's id for the definition that produced
            the values, such as ``"reserve@1"``.
        source_location: Where that definition was written, as ``file:line``,
            or None where it could not be resolved.

    """

    node_id: str
    source_location: str | None = None


@dataclass(frozen=True, slots=True)
class ValuesAccount:
    """How a frame accounts for the columns of the values its last collect produced.

    Attributes:
        defined: Each column a calculation on the frame produced, with where
            that calculation was written.
        arrived: Each column the frame's data arrived with.
        data: The columns of the data the frame was built over, as it was
            handed them, whether or not the model kept them -- less any
            column a calculation on another frame produced. Whatever memory
            a calculated column shares with one of them is the data's.

    """

    defined: Mapping[str, Origin]
    arrived: frozenset[str] = field(default_factory=frozenset)
    data: tuple[pl.Series, ...] = ()


@dataclass(slots=True)
class _Entry:
    """One column of one earlier frame's values, under its key."""

    values: weakref.ref[pl.DataFrame]
    column: str
    origin: Origin | None  # None: the column arrived with that frame's data
    identity: _Identity | None = None


class ComputedValues:
    """The memory live frames' collected values occupy, indexed by first value.

    A frame notes its values as it collects them, which costs nothing: what
    each column is, and where its buffers are, is worked out the first time
    somebody asks, once for that frame, and kept until its values are
    released. :meth:`computed` then costs one lookup per column it is asked
    about.

    **How long values are found.** For as long as somebody holds them: the
    frame, which keeps its copy until its plan next moves, or the caller,
    for as long as they hold the DataFrame the collect handed back. The
    frame's copy is kept here for as long as the caller's DataFrame lives,
    so a frame that was a temporary -- ``ActuarialFrame(model().collect())``
    -- is still found. The copy is a container over the caller's own
    buffers, so keeping it costs no second copy of the values.

    **What it cannot see.** Only shared memory counts, so values that were
    copied -- filtered, sorted, joined, cast, rechunked, sliced, or written
    out and read back -- are not found, and neither are values nobody holds
    any longer, or values from another process. A column whose memory is
    also a column of the data that frame was built over is never reported,
    whether or not the model kept that column: a calculation that handed
    back an input unchanged produced the data's own values, and values that
    are the data's are the data's. A one-row column
    is held by Polars as a single value and copied whenever it is read, so
    it is not found either.
    """

    def __init__(self) -> None:
        """Start with nothing noted and nothing indexed."""
        # Noted values not yet indexed, by identity. Each leaves on its own
        # when its values are released, so holding many results costs a
        # later note nothing.
        self._noted: dict[
            int, tuple[weakref.ref[pl.DataFrame], Callable[[], ValuesAccount]]
        ] = {}
        # Values kept for as long as the DataFrame their collect handed back
        # is alive, by the identity of the values.
        self._kept: dict[int, pl.DataFrame] = {}
        self._entries: dict[_Key, list[_Entry]] = {}
        self._indexed: dict[int, list[tuple[_Key, bool]]] = {}
        # How many calculated columns of each type are indexed. A column of a
        # type no calculated column has cannot hold a calculation's memory,
        # so a check never reads one.
        self._calculated_types: dict[str, int] = {}

    def note(
        self,
        values: pl.DataFrame,
        account: Callable[[], ValuesAccount],
        *,
        kept_while: pl.DataFrame | None = None,
    ) -> None:
        """Keep ``values`` for a later check, with how to account for its columns.

        Nothing is read now. ``account`` is called once, the first time a
        check needs these values, and not at all if none does. It is held
        until then, so it should hold nothing that would keep a frame alive.

        Args:
            values: The values a collect produced, as the frame holds them.
            account: Returns which of their columns the frame calculated and
                which arrived with its data, as they stood at the collect.
            kept_while: The DataFrame the collect handed its caller, if any.
                ``values`` is kept for as long as it lives, whatever the
                frame does with its own copy.

        """
        token = id(values)
        self._noted[token] = (
            weakref.ref(values, lambda _gone: self._noted.pop(token, None)),
            account,
        )
        if kept_while is not None:
            self._kept[token] = values
            weakref.finalize(kept_while, self._kept.pop, token, None)

    def remember(self, values: pl.DataFrame, account: ValuesAccount) -> None:
        """Index ``values`` now, under ``account``.

        Values with no calculated column index nothing: a column found only
        among a frame's arriving columns is never reported, so such values
        could only ever say no. For the same reason an arriving column, and
        a column of the data the frame was built over, is indexed only where
        it is of a type one of the frame's calculated columns has, since
        only then could the two share memory. A column of that data is
        indexed under the same values, so that it speaks for the same frame
        (:meth:`_index_the_data`). Indexing the same values twice indexes
        them once.

        Args:
            values: The values a collect produced, as the frame holds them.
            account: Which of their columns the frame calculated and which
                arrived with its data.

        """
        token = id(values)
        if token in self._indexed:
            return
        schema = values.schema
        calculated = {
            str(schema[column]) for column in account.defined if column in schema
        }
        if not calculated:
            return
        ref = weakref.ref(values)
        keys: list[tuple[_Key, bool]] = []
        for column, dtype in schema.items():
            origin = account.defined.get(column)
            if origin is None and (
                column not in account.arrived or str(dtype) not in calculated
            ):
                continue
            key = _key(values.get_column(column))
            if key is None:
                continue
            self._entries.setdefault(key, []).append(_Entry(ref, column, origin))
            keys.append((key, origin is not None))
            if origin is not None:
                self._calculated_types[key[0]] = (
                    self._calculated_types.get(key[0], 0) + 1
                )
        keys.extend(self._index_the_data(ref, account.data, keys, calculated))
        self._indexed[token] = keys
        weakref.finalize(values, self._forget, token, ref)

    def _index_the_data(
        self,
        ref: weakref.ref[pl.DataFrame],
        data: tuple[pl.Series, ...],
        keys: list[tuple[_Key, bool]],
        calculated: set[str],
    ) -> list[tuple[_Key, bool]]:
        """Index the columns of a frame's data under its values, and return their keys.

        Only a column that starts where one of the values' calculated
        columns does, since only that one can speak for the data against a
        calculation; its memory is read now, because the values do not
        hold it.
        """
        shared = {key for key, is_calculated in keys if is_calculated}
        indexed: list[tuple[_Key, bool]] = []
        for series in data:
            if str(series.dtype) not in calculated:
                continue
            key = _key(series)
            if key is None or key not in shared:
                continue
            identity = _identity(series)
            if identity is None:
                continue
            self._entries.setdefault(key, []).append(
                _Entry(ref, series.name, None, identity)
            )
            indexed.append((key, False))
        return indexed

    def computed(self, data: pl.DataFrame) -> dict[str, Origin]:
        """Return each column of ``data`` whose values a live frame calculated.

        A column is reported where its memory is a calculated column's of
        one earlier frame and none of that frame's arriving columns. Where
        two calculated columns qualify, the one under the same name is
        preferred, so that a column renamed in Polars is reported against
        the definition it came from and an untouched one against its own.
        A column of a type no indexed calculation has is not read at all.

        Args:
            data: The DataFrame a new frame is being built over.

        Returns:
            Each such column, with the definition its values came from.

        """
        self._index_what_was_noted()
        if not self._calculated_types:
            return {}
        found: dict[str, Origin] = {}
        for column, dtype in data.schema.items():
            if str(dtype) not in self._calculated_types:
                continue
            series = data.get_column(column)
            key = _key(series)
            entries = self._entries.get(key) if key is not None else None
            if not entries:
                continue
            origin = _origin_of(column, series, entries)
            if origin is not None:
                found[column] = origin
        return found

    def _index_what_was_noted(self) -> None:
        """Index every noted set of values that is still held, once each.

        A frame whose account cannot be read is left out rather than allowed
        to fail the construction that asked: the check reports less, and the
        frame being built is built.
        """
        noted, self._noted = list(self._noted.values()), {}
        for ref, account in noted:
            values = ref()
            if values is None:
                continue
            try:
                described = account()
            except Exception:  # noqa: BLE001 -- a check never fails a construction
                logger.opt(exception=True).debug(
                    "A collected frame's columns could not be accounted for; "
                    "its values are left out of the check."
                )
                continue
            self.remember(values, described)

    def _forget(self, token: int, ref: weakref.ref[pl.DataFrame]) -> None:
        """Drop one set of values' entries, once its values have been released."""
        for key, calculated in self._indexed.pop(token, []):
            kept = [
                entry for entry in self._entries.get(key, []) if entry.values is not ref
            ]
            if kept:
                self._entries[key] = kept
            else:
                self._entries.pop(key, None)
            if calculated:
                remaining = self._calculated_types.get(key[0], 0) - 1
                if remaining > 0:
                    self._calculated_types[key[0]] = remaining
                else:
                    self._calculated_types.pop(key[0], None)


def _origin_of(column: str, series: pl.Series, entries: list[_Entry]) -> Origin | None:
    """Return the definition ``series``'s values came from, or None.

    Each candidate is confirmed on the column's whole identity, chunk by
    chunk, and judged within its own frame: a frame that holds this memory
    as one of its arriving columns says the values are its data's, whatever
    else it calculated from them.
    """
    whole = _identity(series)
    if whole is None:
        return None
    verdicts: dict[int, list[_Entry]] = {}
    for entry in entries:
        values = entry.values()
        if values is None:
            continue
        if entry.identity is None:
            entry.identity = _identity(values.get_column(entry.column))
        if entry.identity == whole:
            verdicts.setdefault(id(entry.values), []).append(entry)
    calculated = [
        entry
        for confirmed in verdicts.values()
        if all(entry.origin is not None for entry in confirmed)
        for entry in confirmed
    ]
    if not calculated:
        return None
    same_name = [entry for entry in calculated if entry.column == column]
    chosen = (same_name or calculated)[0]
    return chosen.origin
