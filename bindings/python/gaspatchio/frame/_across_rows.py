# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A read across rows, refused where the frame a model runs on is not the whole book.

A policy's value is a function of its own data and the model, and of nothing
else. A Polars expression that reads across the rows -- a ``sum``, a
``mean``, a ``rank``, a ``cum_sum``, a ``rolling_*``, an ``over`` window, a
count of the rows -- answers from **the rows in the frame**. Run over the
whole book that is the book's figure: an expense allocated by share of sum
assured totals the expense. But the frame is not always the book:

- **in a batch runner** -- ``run_aggregated``, ``run_to_parquet`` -- cutting
  the book into more than one batch, the rows are the batch, so the share is
  of the batch's sum assured and the allocation totals the expense once per
  batch. ``batch_size="auto"`` sizes the batch from the machine's memory, so
  two laptops would return two totals for one model and one book;
- **on a scenario axis** -- ``ScenarioRun``, ``for_each_scenario``, or
  ``with_scenarios`` -- the rows are every scenario's copy of every policy,
  so the share is of every scenario's sum assured together, at any batch size.

So the read is refused there, at the line that writes it, naming the read
and the two ways to write the figure the model means: computed before the run
as a model-point column the model reads, or the book run in one batch. Where
the frame is the book -- ``collect()`` on a frame with no scenario axis, a
batch runner whose one batch holds every policy -- the read is the
portfolio-level work the author wrote, and stands.

On a scenario axis whose policies are not cut into batches the frame is
every scenario's copy of the whole book, so a read **inside a window whose
partition includes the scenario** -- ``pl.col("sa").sum().over("scenario_id")``,
or ``.over(["scenario_id", "product"])`` -- answers from one scenario's own
book and stands. Any other read stays refused there, at any
number of scenarios per batch, and its refusal names the partitioned form;
with the policies cut into batches the partitioned read is the batch's too,
and is refused with the rest.

A shared projection grid sized from the rows is the same read: its length is
the youngest issue age, the longest term, the largest number of years among
the rows in the frame (``projection.set(..., per_policy=False)`` and the
horizons that collapse onto one grid). It is refused where a read across
rows is, by the same rule and the same sentence
(:func:`refuse_a_grid_sized_from_the_rows`), and stands where the frame is
the book.

What is read is the Polars the author wrote: a plain expression assigned to
the frame, a plain fragment used as an operand inside a framework formula,
and a fragment written through ``polars_native()``. The framework's own
vocabulary answers one policy at a time by construction. Which plan
functions read across rows is the row-operation guard's measured table
(``frame/_row_operations.py``), plus ``pl.len()``, the count of the rows.
A Python function -- ``map_batches``, ``map_elements``, ``rolling_map`` --
cannot be read at all, since Polars will not hand its body over, so it is
refused wherever a read across rows would be, whatever it declares; a
plugin is taken at its own declaration, and one registered with
``is_elementwise=False`` is a read across rows.

**Work done outside the frame, brought back into a batch.** A model can
also collect its frame, work on the values in plain Polars and build a new
frame over the result -- ``ActuarialFrame(df)``, with or without
``continue_from=``. That work is outside the frame's record, so nothing
above reads it. In a batch runner cutting the book into more than one
batch the runner holds the batch, and so it judges the frame the model
builds against it (:func:`refuse_values_from_outside_the_batch`): values
that are the batch's own pass; a DataFrame holding a column the batch did
not hold, a batch column whose values changed, or other rows is refused,
because what a DataFrame holds is values and not the expressions that made
them, and a read across rows among them cannot be told from a per-row
join. A ``LazyFrame`` still carries its expressions, so it is judged on
its plan: it must be built over the batch's own values, and no step or
expression in it may read across rows. A table in memory the plan joins
is read as a side table; values the model computed from the batch's rows
before it handed them over as such a table are not seen. A scenario plan
whose batch holds more than one scenario is judged the same way, against
the crossed frame it hands the model: whole policies do not excuse a batch
that crosses scenarios, since every scenario's copy of the book is in it.
A scenario plan running one scenario a batch judges nothing here, and nor
does a run whose one batch holds every policy. ``with_scenarios`` crossing
the book with more than one scenario hands back such a frame on its own,
with no runner around the model: the crossing is held
(:func:`hold_a_crossing`), and a frame built over values that carry its
axis and its columns is judged against it the same way.
"""

from __future__ import annotations

import json
import warnings
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

import numpy as np
import polars as pl
from polars.exceptions import PanicException

from gaspatchio._semantic.ir import EngineNative, walk
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
from gaspatchio.frame._row_operations import _rebuilt, _row_operations, _walk
from gaspatchio.frame.lowering.ingress import NATIVE_REFS
from gaspatchio.frame.plan_writes import root_table, scanned_tables

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator


@dataclass(frozen=True, slots=True)
class NotTheBook:
    """Why the frame a model is running on now is not the whole book.

    ``on_a_scenario_axis`` is the scenario case, which no batch size cures;
    ``cut`` says, in the runner's own terms, how the book was cut; ``batch``
    is the batch's own values, where a batch runner cut the book, which a
    frame the model builds from values that left the frame is judged
    against; on a scenario plan it is the crossed frame's plan, where the
    batch holds more than one scenario, read when a rebuild is judged.
    """

    on_a_scenario_axis: bool
    cut: str
    batch: pl.DataFrame | pl.LazyFrame | None = field(
        default=None, compare=False, repr=False
    )


class ReadAcrossRowsError(ValueError):
    """A read across rows refused where the frame a model runs on is not the book.

    A ``ValueError``, as every refusal here always was, carrying ``read``:
    the read the refusal names, in the words it names it -- ``sum on
    col("sa")``, a grid sized from the rows, an injected column -- so that a
    door which can run the whole book instead (``run-single-policy``) can
    say which read sent it there.
    """

    def __init__(self, message: str, *, read: str | None = None) -> None:
        """Hold the refusal's message and the read it names."""
        super().__init__(message)
        self.read = read


_NOT_THE_BOOK: ContextVar[NotTheBook | None] = ContextVar(
    "gaspatchio_frame_is_not_the_book", default=None
)

# The columns of the book a batch runner or a scenario plan was handed, set
# while it runs the model. A frame built inside that block keeps them
# (``ActuarialFrame._book_columns``), so the record it writes is told which
# columns the policy data carried, as ``gspio calc-graph`` tells it -- and a
# column the setup made in Polars is a hole there, as it is on the command
# line, rather than a field of the book.
_THE_RUN_S_BOOK: ContextVar[frozenset[str] | None] = ContextVar(
    "gaspatchio_the_run_s_book", default=None
)

# The plan node Polars writes for ``pl.len()``: the count of the rows, which
# is the batch's count in a batch and every scenario's on a scenario axis.
_ROW_COUNT: Final = "Len"


@contextmanager
def frame_is_not_the_book(
    *,
    on_a_scenario_axis: bool,
    cut: str,
    batch: pl.DataFrame | pl.LazyFrame | None = None,
    book: Iterable[str] | None = None,
) -> Iterator[None]:
    """Run a model, inside this block, over a frame that is not the whole book.

    A batch runner opens it around each call of the model where it cuts the
    book into more than one batch, and a scenario plan around every call.

    Args:
        on_a_scenario_axis: Whether the frame carries a scenario axis.
        cut: How the runner cut the book, in its own terms, for the refusal.
        batch: The batch's own values, where a batch runner cut the book;
            the crossed frame's plan, where a scenario plan's batch holds
            more than one scenario.
        book: The columns of the book the run was handed, where the caller
            knows them (:func:`the_run_s_book`).

    Yields:
        Nothing; the block runs with the setting in force.

    """
    token = _NOT_THE_BOOK.set(
        NotTheBook(on_a_scenario_axis=on_a_scenario_axis, cut=cut, batch=batch)
    )
    try:
        if book is None:
            yield
        else:
            with the_run_s_book(book):
                yield
    finally:
        _NOT_THE_BOOK.reset(token)


@contextmanager
def the_run_s_book(columns: Iterable[str]) -> Iterator[None]:
    """Run a model, inside this block, over a book whose columns the caller knows.

    Every frame built inside the block keeps the columns, and its record is
    told them: a name the frame arrived holding that the book never had is
    a hole there, carrying the stamp of its values, whichever door ran the
    model.

    Args:
        columns: The columns the book carried when the run was handed it.

    Yields:
        Nothing; the block runs with the setting in force.

    """
    token = _THE_RUN_S_BOOK.set(frozenset(columns))
    try:
        yield
    finally:
        _THE_RUN_S_BOOK.reset(token)


def book_of_the_run() -> frozenset[str] | None:
    """Return the columns of the book the model is being run over, where known."""
    return _THE_RUN_S_BOOK.get()


def batches_cut(*, runner: str, n_policies: int, batch_size: int | str) -> str:
    """Say how a batch runner cut a book, for a refusal to quote.

    Args:
        runner: The runner's public name.
        n_policies: The book's policy count.
        batch_size: The batch size as the caller stated it.

    Returns:
        The clause, such as ``run_aggregated cuts the 8 policies into batches
        of 3``.

    """
    if batch_size == "auto":
        return (
            f"{runner} cuts the {n_policies} policies into batches sized from "
            "this machine's memory (batch_size='auto')"
        )
    return f"{runner} cuts the {n_policies} policies into batches of {batch_size}"


@contextmanager
def one_batch_of_several(
    *,
    runner: str,
    n_policies: int,
    batch_size: int | str,
    first: int,
    batch: pl.DataFrame,
) -> Iterator[None]:
    """Run a model, inside this block, over one batch of a batch runner's book.

    The book's columns are in force either way (:func:`the_run_s_book`).
    Where the runner's first batch holds every policy the frame is the book
    and nothing else is; otherwise the frame is one batch of several, and
    the batch is held for what the model builds to be judged against.

    Args:
        runner: The runner's public name.
        n_policies: The book's policy count.
        batch_size: The batch size as the caller stated it.
        first: How many policies the runner's first batch holds.
        batch: The batch the model is about to run over, as a DataFrame.

    Yields:
        Nothing; the block runs with the settings in force.

    """
    if first >= n_policies:
        with the_run_s_book(batch.columns):
            yield
        return
    with frame_is_not_the_book(
        on_a_scenario_axis=False,
        cut=batches_cut(runner=runner, n_policies=n_policies, batch_size=batch_size),
        batch=batch,
        book=batch.columns,
    ):
        yield


# What a scenario plan's refusal says of the frame it hands the model.
ON_A_SCENARIO_PLAN: Final = (
    "a scenario plan runs the model over every scenario's copy of the book, "
    "crossed on a scenario axis"
)


def refuse_a_read_across_rows(
    frame: object, value: object, *, selection: bool = False
) -> None:
    """Refuse ``value`` where it reads across rows and the frame is not the book.

    On a scenario axis whose policies are whole, a read inside a window
    whose partition includes the scenario column stays inside one
    scenario's book, and stands.

    A filter's condition is held to the same rule (``selection``): which
    policies are valued would otherwise turn on which other policies share
    the run -- the policies above the batch's mean sum assured, not the
    book's.

    Args:
        frame: The frame being assigned to, or filtered.
        value: What the model is assigning, or the condition it filters on.
        selection: Whether ``value`` is a filter's condition.

    Raises:
        ValueError: Where ``value`` holds a read across rows and either a
            runner has said the frame is not the whole book, or the frame
            carries a scenario axis.

    """
    found = next(_reads_across_rows(value), None)
    if found is None:
        return
    where = _not_the_book(frame)
    if where is None:
        return
    axis = _the_axis_column(frame) if where.on_a_scenario_axis else None
    if axis is not None:
        found = next(_reads_across_rows(value, outside=axis), None)
        if found is None:
            return
    method, operand = found
    read = (
        f"the filter's condition, {method} on {operand}"
        if selection
        else f"{method} on {operand}"
    )
    raise ReadAcrossRowsError(
        _refusal(method, operand, where, axis=axis, selection=selection), read=read
    )


def refuse_an_injection_the_rows_cannot_take(
    frame: object, value: object, *, selection: bool = False
) -> None:
    """Refuse an injected column that cannot be paired with the rows the frame holds.

    A column of values handed over wholesale -- a ``pl.Series``, a NumPy
    array, ``pl.lit(Series)``, a fixed ``pl.int_range`` -- lands on the rows
    by position: its second value belongs to the second row (spec 12.3).
    Where a runner has cut the book, the rows are not the book's, so the
    values would be paired with whichever policies share the batch, and on
    a one-row frame Polars' streaming engine repeats the row to the
    injection's length; it is refused there whatever its length. Anywhere
    else it is refused where its length is not the frame's row count, which
    is the one pairing position can make. One value is a constant, and
    stands anywhere.

    Args:
        frame: The frame being assigned to, or filtered.
        value: What the model is assigning, or the condition it filters on.
        selection: Whether ``value`` is a filter's condition.

    Raises:
        ValueError: Where ``value`` holds an injected column of more than
            one value, and either a runner has cut the book or the frame's
            row count is not the injection's length.

    """
    found = _rows_of_its_own(value)
    if found is None:
        return
    what, length = found
    where = _NOT_THE_BOOK.get()
    landing = (
        "the filter's condition holds" if selection else "the column assigned holds"
    )
    landing = f"{landing} {length} values handed over wholesale ({what})"
    if where is not None and not where.on_a_scenario_axis:
        msg = (
            f"{landing}, and an injected column lands on the rows by position, "
            "one value a row; here the frame is not the "
            f"whole book: {where.cut}. Its values would be paired with whichever "
            "policies share the batch, so each policy's value would depend on "
            "which others share its run. Bring the values in as a model-point "
            "column -- model_points.with_columns(pl.Series('draw', draws)) before "
            "the run, or joined by policy id -- or run the book in one batch -- "
            "af.collect(), or a batch_size of at least the number of policies."
        )
        raise ReadAcrossRowsError(
            msg, read=f"an injected column of {length} values ({what})"
        )
    height = _rows_in(frame)
    if height is None or height == length:
        return
    rows = "1 row" if height == 1 else f"{height} rows"
    msg = (
        f"{landing}, and an injected column lands on the rows by position, one "
        f"value a row, but this frame holds {rows}, so "
        "its values cannot be paired with the policies"
        + (
            " -- Polars' streaming engine would copy the one row once for each value"
            if height == 1
            else ""
        )
        + ". Inject one value for each row the frame holds, in the frame's "
        "order, or bring the values in as a model-point column joined by "
        "policy id."
    )
    raise ValueError(msg)


def _rows_of_its_own(value: object) -> tuple[str, int] | None:  # noqa: PLR0911 -- one return per kind of container
    """Return what in ``value`` is a column of several values of its own, and how many.

    A Series or an array of rank one or more is one; so is any part of a
    Polars expression that reads no column and answers more than one value
    -- ``pl.lit(Series)``, a fixed ``pl.int_range`` -- whether assigned
    itself, written inside a raw expression, or used as an operand in a
    framework formula.
    """
    if isinstance(value, pl.Series):
        return ("a pl.Series", value.len()) if value.len() > 1 else None
    if isinstance(value, np.ndarray):
        if value.ndim == 0 or value.shape[0] <= 1:
            return None
        return "a NumPy array", int(value.shape[0])
    if isinstance(value, pl.Expr) and not isinstance(value, ProxyAwareExpr):
        return _a_part_of_its_own_length(value)
    node = getattr(value, "_node", None)
    if node is None:
        return None
    for leaf in walk(node):
        if isinstance(leaf, EngineNative):
            held = NATIVE_REFS.get(id(leaf))
            if held is not None:
                found = _a_part_of_its_own_length(held[1])
                if found is not None:
                    return found
    return None


def _a_part_of_its_own_length(expr: pl.Expr) -> tuple[str, int] | None:  # noqa: PLR0911 -- each unreadable step answers None
    """Return the first part of ``expr`` reading no column and answering several values.

    Walked through Polars' own account of each node's inputs; a part that
    reads no column is evaluated on its own to count what it answers. A
    count of the rows (``pl.len()``) is not a length of its own, and is left
    to the read-across-rows rule.
    """
    try:
        roots = expr.meta.root_names()
    except Exception:  # noqa: BLE001 -- unreadable, left to the other rules
        return None
    if not roots:
        if _counts_the_rows(expr):
            return None
        try:
            height = pl.select(expr).height
        except Exception:  # noqa: BLE001 -- not a column of its own
            return None
        return (f"written as {_shortened(str(expr))}", height) if height > 1 else None
    try:
        inputs = expr.meta.pop()
    except Exception:  # noqa: BLE001 -- nothing further to walk
        return None
    for one in inputs:
        found = _a_part_of_its_own_length(one)
        if found is not None:
            return found
    return None


# How much of an expression a refusal quotes before it stops.
_QUOTED: Final = 80


def _shortened(text: str) -> str:
    """Return an expression's text as a refusal quotes it: whole, or its start."""
    return text if len(text) <= _QUOTED else f"{text[: _QUOTED - 3]}..."


def _rows_in(frame: object) -> int | None:
    """Return how many rows the frame holds, or None where its plan cannot say."""
    plan = getattr(frame, "_df", None)
    if not isinstance(plan, pl.LazyFrame | pl.DataFrame):
        return None
    try:
        counted = plan.lazy().select(pl.len()).collect(engine="in-memory")
    except Exception:  # noqa: BLE001 -- a plan that does not run says so itself
        return None
    return int(counted.item())


def refuse_a_grid_sized_from_the_rows(frame: object, *, grid: str, route: str) -> None:
    """Refuse a shared projection grid sized from the rows, where they are not the book.

    The grid's length is read from the rows in the frame, so it is a read
    across rows (:func:`refuse_a_read_across_rows`) and is refused where one
    is: in a batch runner cutting the book into more than one batch, and on
    a scenario axis. No partition answers it: one grid serves every row.

    Args:
        frame: The frame the projection axis is being declared on.
        grid: The declaration and what in the rows sizes it, for the refusal.
        route: The first way out, in the declaration's own terms: the
            per-policy axis where the horizon has one, or the grid's length
            taken over the book before the run and stated as a number.

    Raises:
        ValueError: Where the frame is not the whole book.

    """
    where = _not_the_book(frame)
    if where is None:
        return
    rows, one_batch = _the_rows_and_the_one_batch(where)
    msg = (
        f"{grid}, and here the frame is not the whole book: {where.cut}. A grid "
        "sized from the rows answers from the rows in the frame, and here those "
        f"are {rows}. A policy's value must not depend on which other policies "
        f"share its run. {route} -- {one_batch}."
    )
    raise ReadAcrossRowsError(msg, read=grid)


def refuse_values_from_outside_the_batch(data: object, *, continue_from: bool) -> None:
    """Refuse a frame the model builds, in a batch, over values the batch did not hold.

    Read where a model builds a frame of its own -- ``ActuarialFrame(df)``,
    with or without ``continue_from=`` -- while a batch runner has cut the
    book into more than one batch, or while a scenario plan runs a batch
    holding more than one scenario (judged against the crossed frame). A
    DataFrame (or a dict of columns) is values, so it passes only where it
    is the batch's own: no column the batch did not hold, every column equal
    to the batch's row for row, and the batch's rows. A LazyFrame is judged
    on its plan: built over the batch's own values, with no step or
    expression reading across rows.

    Args:
        data: What the model handed the constructor.
        continue_from: Whether it also named the frame the values came from.

    Raises:
        ValueError: Where the values are not the batch's own and the runner
            cut the book into more than one batch, naming what differs and
            the four ways to write the model so that it does not.

    """
    where = _NOT_THE_BOOK.get()
    if where is None:
        _judge_against_the_crossings(data, continue_from=continue_from)
        return
    if where.batch is None:
        return
    held = _beyond(data, where.batch, noun="the batch")
    if held is None:
        return
    found, lazy = held
    raise ReadAcrossRowsError(
        _rebuild_refusal(found, where, lazy=lazy, continue_from=continue_from),
        read=_the_read(found, lazy=lazy, noun="the batch"),
    )


def _the_read(found: str, *, lazy: bool, noun: str) -> str:
    """Name a refused rebuild, as the refusal's ``read`` carries it."""
    if lazy:
        return f"ActuarialFrame(plan) over a plan that {found}"
    return f"ActuarialFrame(df) over values {noun} did not hold: it {found}"


def _beyond(
    data: object, batch: pl.DataFrame | pl.LazyFrame, *, noun: str
) -> tuple[str, bool] | None:
    """Say what ``data`` holds that ``batch`` did not, and whether it is a plan.

    None where the values, or the plan, are the batch's own -- or where
    ``data`` is neither a table nor a plan, which is not judged.
    """
    if isinstance(data, pl.LazyFrame):
        read = _what_the_plan_does_beyond_the_batch(
            data, _the_batch_s_table(batch), noun=noun
        )
        if read is not None and isinstance(batch, pl.LazyFrame):
            # A scenario plan's crossed frame is a plan over the book: a plan
            # the model builds over the crossed values, collected, is judged
            # against them instead.
            read = _what_the_plan_does_beyond_the_batch(
                data, batch.collect(engine="in-memory"), noun=noun
            )
        return None if read is None else (read, True)
    if isinstance(data, dict):
        data = pl.DataFrame(data)
    if not isinstance(data, pl.DataFrame):
        return None
    if isinstance(batch, pl.LazyFrame):
        # A scenario plan's crossed frame, collected only now a rebuild is judged.
        batch = batch.collect(engine="in-memory")
    differs = _how_the_values_differ(data, batch, noun=noun)
    return None if differs is None else (differs, False)


@dataclass(frozen=True, slots=True)
class _Crossing:
    """A book ``with_scenarios`` crossed with more than one scenario.

    ``plan`` is the crossed frame's plan as ``with_scenarios`` handed it
    back, ``column`` the axis it crossed on, ``scenarios`` the labels on it
    and ``columns`` the crossed frame's columns. ``tables`` are the tables in
    memory the plan scans -- the book's and the axis' -- which a plan the
    model builds on the crossed frame scans too.
    """

    column: str
    scenarios: frozenset[object]
    columns: frozenset[str]
    plan: pl.LazyFrame = field(compare=False, repr=False)
    tables: tuple[pl.DataFrame, ...] = field(compare=False, repr=False)


# How many crossings are held. A model is run over the crossing it was just
# handed; a script running a sweep beside a sweep has a handful. Each holds a
# plan over its book, not the crossed values.
_CROSSINGS_HELD: Final = 8
_CROSSINGS: deque[_Crossing] = deque(maxlen=_CROSSINGS_HELD)

# What a refusal under ``with_scenarios`` calls the frame it judges against.
_THE_CROSSED_FRAME: Final = "the crossed frame"


def hold_a_crossing(
    plan: pl.LazyFrame,
    *,
    column: str,
    scenarios: Iterable[object],
    columns: Iterable[str],
) -> None:
    """Hold a book ``with_scenarios`` crossed, for a rebuild to be judged against.

    A frame crossed with one scenario is that scenario's whole book, and is
    not held.

    Args:
        plan: The crossed frame's plan, as handed back.
        column: The scenario axis column.
        scenarios: The scenario labels crossed.
        columns: The crossed frame's columns.

    """
    labels = frozenset(scenarios)
    if len(labels) < 2:  # noqa: PLR2004 -- one scenario is the whole book
        return
    _CROSSINGS.append(
        _Crossing(
            column=column,
            scenarios=labels,
            columns=frozenset(columns),
            plan=plan,
            tables=tuple(scanned_tables(plan)),
        )
    )


def _carries(table: pl.DataFrame, crossing: _Crossing) -> bool:
    """Return whether a table carries ``crossing``'s values.

    It holds the crossing's every column, its axis among them, with more
    than one of its scenarios and no other label on the axis. A summary that
    kept the axis and dropped the book's columns carries none.
    """
    if not crossing.columns <= set(table.columns):
        return False
    on_the_axis = frozenset(table.get_column(crossing.column).unique().to_list())
    return len(on_the_axis) > 1 and on_the_axis <= crossing.scenarios


def _built_over(plan: pl.LazyFrame, crossing: _Crossing) -> bool:
    """Return whether a plan is built over ``crossing``.

    It scans the crossing's own tables -- the book and the axis the crossed
    plan is built over -- and holds the crossing's every column; or it is
    built over a table that carries the crossing's values.
    """
    _kind, table = root_table(plan)
    if table is None:
        return False
    if _carries(table, crossing):
        return True
    try:
        names = set(plan.collect_schema().names())
    except (Exception, PanicException):  # noqa: BLE001 -- the constructor says
        return False
    if not crossing.columns <= names or not crossing.tables:
        return False
    scanned = scanned_tables(plan)
    return all(any(one.equals(theirs) for theirs in scanned) for one in crossing.tables)


def _crossings_holding(data: object) -> list[_Crossing]:
    """Return the held crossings ``data`` carries or is built over, newest first."""
    if not _CROSSINGS:
        return []
    if isinstance(data, dict):
        try:
            data = pl.DataFrame(data)
        except (Exception, PanicException):  # noqa: BLE001 -- the constructor says
            return []
    if isinstance(data, pl.DataFrame):
        return [c for c in reversed(_CROSSINGS) if _carries(data, c)]
    if isinstance(data, pl.LazyFrame):
        return [c for c in reversed(_CROSSINGS) if _built_over(data, c)]
    return []


# Set while the framework builds a crossed frame of its own: a new crossing
# of a book already crossed is not a rebuild over the old one.
_CROSSING_NOW: ContextVar[bool] = ContextVar("gaspatchio_crossing_now", default=False)


@contextmanager
def crossing_a_book() -> Iterator[None]:
    """Build, inside this block, the frame a cross-join hands back, unjudged.

    Yields:
        Nothing; the block runs with the setting in force.

    """
    token = _CROSSING_NOW.set(True)
    try:
        yield
    finally:
        _CROSSING_NOW.reset(token)


def _judge_against_the_crossings(data: object, *, continue_from: bool) -> None:
    """Refuse a frame built over a crossing's values that the crossing did not hold.

    Judged against every held crossing ``data`` carries, newest first: the
    values pass where they are any one's own.
    """
    if _CROSSING_NOW.get():
        return
    crossings = _crossings_holding(data)
    first: tuple[_Crossing, str, bool] | None = None
    for crossing in crossings:
        held = _beyond(data, crossing.plan, noun=_THE_CROSSED_FRAME)
        if held is None:
            return
        if first is None:
            first = (crossing, *held)
    if first is None:
        return
    crossing, found, lazy = first
    raise ReadAcrossRowsError(
        _crossing_refusal(found, crossing, lazy=lazy, continue_from=continue_from),
        read=_the_read(found, lazy=lazy, noun=_THE_CROSSED_FRAME),
    )


def _crossing_refusal(
    found: str, crossing: _Crossing, *, lazy: bool, continue_from: bool
) -> str:
    """Say what the frame the model built holds, and the two ways to write it."""
    if lazy:
        built = "ActuarialFrame(plan)"
        why = (
            "A plan that reads across rows answers from the rows in it, and "
            "here those are every scenario's copy of every policy"
        )
    else:
        built = (
            "ActuarialFrame(df, continue_from=af)"
            if continue_from
            else "ActuarialFrame(df)"
        )
        why = (
            "Work done on values that left the frame is outside its record, so "
            "this run cannot see whether it read across the rows -- a DataFrame "
            "holds values, not the expressions that made them -- and here the "
            "rows are every scenario's copy of every policy"
        )
    return (
        f"{built} is built over values the crossed frame did not hold: it "
        f"{found}. Here the frame is not the whole book: with_scenarios crossed "
        f"the book with {len(crossing.scenarios)} scenarios on "
        f"{crossing.column!r}, so the frame holds every scenario's copy of "
        f"every policy. {why}, so a read across them would answer from every "
        "scenario's book together, and each policy's value on how many "
        "scenarios were crossed. Whole policies do not excuse a frame that "
        "crosses scenarios. Compute the column on the book before "
        "with_scenarios crosses it, as a model-point column the model reads; "
        "or bring a side table in through the frame -- af.join(table, "
        "on='product') -- so the record follows the join."
    )


def _the_batch_s_table(batch: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
    """Return the table in memory a plan over the batch is built over.

    A batch runner's batch is that table. A scenario plan's crossed frame
    is a plan over the book -- the book's table crossed with the batch's
    scenarios, a step that reads no row but its own -- so a plan the model
    builds on the frame it was handed is built over the book's table.
    """
    if isinstance(batch, pl.DataFrame):
        return batch
    _kind, table = root_table(batch)
    return table if table is not None else batch.collect(engine="in-memory")


# How many column names a refusal quotes before it counts the rest.
_NAMED: Final = 3


def _names(columns: list[str]) -> str:
    """Return a few column names as a reader would quote them."""
    shown = ", ".join(repr(column) for column in columns[:_NAMED])
    rest = len(columns) - _NAMED
    return shown if rest <= 0 else f"{shown} and {rest} more"


def _how_the_values_differ(
    values: pl.DataFrame, batch: pl.DataFrame, *, noun: str = "the batch"
) -> str | None:
    """Say how ``values`` are not the batch's own, or None where they are.

    A column the batch did not hold, other rows, or a batch column whose
    values moved, row for row: each is work the runner did not see. Types
    are not compared, only values, so the batch's own values read back
    through a collect pass whatever width they came back in.
    """
    added = [column for column in values.columns if column not in batch.columns]
    if added:
        return f"holds {_names(added)}, which {noun} did not hold"
    if values.height != batch.height:
        return f"holds {values.height} rows where {noun} holds {batch.height}"
    moved = [
        column
        for column in values.columns
        if not values.get_column(column).equals(
            batch.get_column(column), check_dtypes=False
        )
    ]
    if moved:
        return f"holds {_names(moved)} with values other than {noun}'s, row for row"
    return None


def _what_the_plan_does_beyond_the_batch(
    plan: pl.LazyFrame, batch: pl.DataFrame, *, noun: str = "the batch"
) -> str | None:
    """Say what a plan does that makes it more than the batch's own rows, or None.

    Built over a table in memory that is the batch's own values -- the
    frame the runner handed the model, and every step on it -- and with no
    step or expression reading across rows, a plan computes each policy
    from its own row and passes. Anything Polars cannot hand over to be
    read is said to be unreadable, and refused with the rest.
    """
    kind, table = root_table(plan)
    if table is None:
        return (
            "is built over something other than a table in memory "
            f"({_SOURCES.get(kind, kind)}), not over {noun}"
        )
    differs = _how_the_values_differ(table, batch, noun=noun)
    if differs is not None:
        return f"is built over a table in memory that {differs}"
    try:
        text: str | None = plan.explain(optimized=False)
    except (Exception, PanicException):  # noqa: BLE001 -- read below instead
        text = None
    if text is not None and text in _READINGS:
        return _READINGS[text]
    found = _read_the_plan(plan)
    if text is not None:
        if len(_READINGS) >= _READINGS_HELD:
            _READINGS.pop(next(iter(_READINGS)))
        _READINGS[text] = found
    return found


# What each plan read so far was found to do, by the plan's own unoptimised
# text. Reading a plan means having Polars write it out, and it writes every
# table in memory the plan scans with it -- the batch itself, about 0.4 s
# for 100,000 policies of 14 columns -- while the text names the steps and
# every expression and leaves the tables out, at about a millisecond. A batch
# runner hands the model the same plan over each batch, so the plan is read
# once a run and its text recognised after; the batch's own values are
# compared every time, above. What a plan does across rows is a property of
# its steps and expressions, which the text states, never of the values it
# scans.
_READINGS: dict[str, str | None] = {}
_READINGS_HELD: Final = 64


def _read_the_plan(plan: pl.LazyFrame) -> str | None:
    """Return what a plan's steps and expressions do across rows, off Polars' plan."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            written = plan.serialize(format="json")
    except (Exception, PanicException):  # noqa: BLE001 -- unreadable, said so
        return (
            "holds a step Polars cannot hand over to be read, such as a Python function"
        )
    return next(_steps_across_rows(json.loads(_without_tables(written))), None)


# How Polars writes the values of a table in memory a plan scans.
_TABLE_BYTES: Final = '"df":['


def _without_tables(written: str) -> str:
    """Return a plan written by Polars with every table it scans left out.

    A table's values are written as one array of byte values -- tens of
    megabytes for a batch -- which nothing here reads, and parsing them would
    cost more than the rest of the plan together. Each is replaced by a null
    before the plan is parsed. The array holds nothing but digits and commas,
    so its first closing bracket ends it.
    """
    kept: list[str] = []
    at = 0
    while (start := written.find(_TABLE_BYTES, at)) != -1:
        end = written.find("]", start)
        kept.append(written[at:start])
        kept.append('"df":null')
        at = end + 1
    kept.append(written[at:])
    return "".join(kept)


# What a plan built over something other than a table in memory reads from.
_SOURCES: Final[dict[str, str]] = {
    "Scan": "a file",
    "PythonScan": "a Python source",
    "unreadable": "a plan Polars cannot walk",
}

# Plan steps that read across the rows, or bring in rows the batch did not
# hold, whatever their expressions say.
_ROW_STEPS: Final[dict[str, str]] = {
    "GroupBy": "groups the rows (group_by)",
    "Distinct": "keeps one row of each value (unique)",
    "Slice": "keeps a slice of the rows (head, tail or slice)",
    "Union": "stacks other rows onto the batch's (concat)",
    "HConcat": "pairs the batch's rows by position with another frame's",
    "ExtContext": "reads another frame's rows as its context (with_context)",
}

# Map steps that keep each policy on its own rows: a rename, and reshapes of
# one row's own values. Any other is refused, a row index among them, since
# its numbers are positions in the batch.
_ONE_ROW_MAPS: Final = frozenset({"Rename", "Explode", "Unnest", "Unpivot"})

# The joins that keep the batch's rows and bring nothing in beside them but
# the matching side's columns.
_ONE_ROW_JOINS: Final = frozenset({"Left", "Inner", "Semi", "Anti", "Cross", "AsOf"})

# Each step whose expressions are read, and the fields they sit in.
_EXPRESSION_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "HStack": ("exprs",),
    "Select": ("expr",),
    "Filter": ("predicate",),
    "Join": ("left_on", "right_on", "predicates"),
}

# Steps that only pass their input on, or are sources.
_PASSING_STEPS: Final = frozenset({"Cache", "Sort", "DataFrameScan", "Scan", "IR"})


def _steps_across_rows(node: object) -> Iterator[str]:
    """Yield what each step of a plan does across rows, top first."""
    if not isinstance(node, dict) or len(node) != 1:
        return
    ((kind, body),) = node.items()
    if not isinstance(body, dict):
        return
    whole = _what_the_step_does(kind, body)
    if whole is not None:
        yield whole
        return
    for name in _EXPRESSION_FIELDS.get(kind, ()):
        held = body.get(name)
        for expression in held if isinstance(held, list) else [held]:
            if expression is not None:
                yield from _expression_across_rows(expression)
    # A plan Polars has already resolved once keeps what was written under
    # ``dsl``, beside the resolution, and that is what is read.
    for name in ("input", "input_left", "input_right", "dsl"):
        yield from _steps_across_rows(body.get(name))


def _what_the_step_does(kind: str, body: dict[str, object]) -> str | None:
    """Say what one step does to the rows as a whole, or None where it keeps them."""
    if kind in _ROW_STEPS:
        return _ROW_STEPS[kind]
    reader = _STEP_READERS.get(kind)
    if reader is not None:
        return reader(body)
    if kind in _EXPRESSION_FIELDS or kind in _PASSING_STEPS:
        return None
    return f"runs a step that is not read here ({kind})"


def _a_map(body: dict[str, object]) -> str | None:
    """Say what a map step does to the rows, or None for a rename or a reshape."""
    name = _named(body.get("function"))
    if name in _ONE_ROW_MAPS:
        return None
    if name == "RowIndex":
        return "numbers the rows (with_row_index)"
    return f"runs a step that is not read here ({name or 'unknown'})"


def _a_sort(body: dict[str, object]) -> str | None:
    """Say what a sort does to the rows: nothing, unless it keeps its first few."""
    if body.get("slice") is None:
        return None
    return "keeps the first rows of a sort (top_k or head)"


def _a_join(body: dict[str, object]) -> str | None:
    """Say what a join does to the rows, or None where it keeps the batch's."""
    options = body.get("options")
    args = options.get("args") if isinstance(options, dict) else None
    how = _named(args.get("how") if isinstance(args, dict) else None)
    if how in _ONE_ROW_JOINS:
        return None
    return f"joins {how.lower() or 'in a way not read here'}, bringing in rows"


_STEP_READERS: Final[dict[str, Callable[[dict[str, object]], str | None]]] = {
    "MapFunction": _a_map,
    "Sort": _a_sort,
    "Join": _a_join,
}


def _named(setting: object) -> str:
    """Return the name Polars writes a setting under: itself, or its one key."""
    if isinstance(setting, str):
        return setting
    if isinstance(setting, dict):
        return str(next(iter(setting), ""))
    return ""


def _expression_across_rows(expression: object) -> Iterator[str]:
    """Yield the reads across rows one expression of a plan holds."""
    rebuilt = _rebuilt(expression)
    if rebuilt is None:
        for method, _operand in _walk(expression):
            yield f"reads across the rows -- {method}"
        return
    for method, operand in _in_the_plan(rebuilt):
        yield f"reads across the rows -- {method} on {operand}"


def _rebuild_refusal(
    found: str, where: NotTheBook, *, lazy: bool, continue_from: bool = False
) -> str:
    """Say what the frame the model built holds, and the four ways to write it."""
    if lazy:
        built = "ActuarialFrame(plan)"
        why = (
            "A plan that reads across rows answers from the rows in it, and "
            "here those are the batch"
        )
    else:
        built = (
            "ActuarialFrame(df, continue_from=af)"
            if continue_from
            else "ActuarialFrame(df)"
        )
        why = (
            "Work done on values that left the frame is outside its record, so "
            "this run cannot see whether it read across the rows -- a DataFrame "
            "holds values, not the expressions that made them -- and here the "
            "rows are the batch"
        )
    if where.on_a_scenario_axis:
        return (
            f"{built} is built over values the batch did not hold: it {found}. "
            f"Here the frame is not the whole book: {where.cut}, and this batch "
            f"holds more than one scenario. {why} -- every scenario's copy of "
            "every policy in the batch -- so a read across them would answer "
            "from several scenarios' books together, and each policy's value "
            "on how many scenarios share its batch. Whole policies do not "
            "excuse a batch that crosses scenarios. Compute the column on the "
            "book before the run, as a model-point column the model reads; "
            "bring a side table in through the frame -- af.join(table, "
            "on='product') -- so the record follows the join; or run one "
            "scenario a batch -- batch_size=1 -- where the frame is that "
            "scenario's whole book."
        )
    return (
        f"{built} is built over values the batch did not hold: it {found}. "
        f"Here the frame is not the whole book: {where.cut}. {why}, so each "
        "policy's value could depend on which other policies share its "
        "batch, and the total on the batch size. Bring a side table in "
        "through the frame -- af.join(table, on='product') -- so the record "
        "follows the join and a policy whose key the table lacks is refused by "
        "name (on_missing='null' keeps it, as a null to fill); compute the "
        "column on the book before the run, as "
        "a model-point column the model reads; run the book in one batch -- "
        "af.collect(), or a batch_size of at least the number of policies; "
        'or let the JAX engine run it -- engine="jax" -- which runs the setup '
        "over the whole book before it cuts the batches."
    )


def _not_the_book(frame: object) -> NotTheBook | None:
    """Return why the frame is not the whole book, or None where it is."""
    where = _NOT_THE_BOOK.get()
    if where is None and _on_a_scenario_axis(frame):
        where = NotTheBook(
            on_a_scenario_axis=True,
            cut="this frame carries a scenario axis",
        )
    return where


def _the_axis_column(frame: object) -> str:
    """Return the column a scenario axis is read by: the frame's own, or the plan's."""
    from gaspatchio.scenarios._with_scenarios import (  # noqa: PLC0415 -- cycle
        SCENARIO_COLUMN,
        scenario_axis_columns,
    )

    try:
        columns = scenario_axis_columns(frame)  # type: ignore[arg-type]
    except AttributeError:
        columns = ()
    return columns[0] if len(columns) == 1 else SCENARIO_COLUMN


def _reads_across_rows(
    value: object, *, outside: str | None = None
) -> Iterator[tuple[str, str]]:
    """Yield each read across rows in ``value``, as the method and its operand.

    ``outside`` names a scenario column: a read inside a window whose
    partition includes it is within one scenario's own book, and is not
    yielded.
    """
    if isinstance(value, pl.Expr) and not isinstance(value, ProxyAwareExpr):
        yield from _in_the_plan(value, outside=outside)
        return
    node = getattr(value, "_node", None)
    if node is None:
        return
    for leaf in walk(node):
        if isinstance(leaf, EngineNative):
            held = NATIVE_REFS.get(id(leaf))
            if held is not None:
                yield from _in_the_plan(held[1], outside=outside)


def _in_the_plan(
    expr: pl.Expr, *, outside: str | None = None
) -> Iterator[tuple[str, str]]:
    """Yield the reads across rows one Polars expression's plan holds."""
    windows: dict[str, str] = {}
    keys: list[pl.Expr] = []
    if outside is not None:
        expr, windows, keys = _without_the_scenario_windows(expr, outside)
    for searched in (expr, *keys):
        for method, operand in _row_operations(searched):
            yield method, _as_written(str(operand), windows)
        for method, opaque in _functions_not_read(searched):
            yield method, _as_written(opaque, windows)
        if _counts_the_rows(searched):
            yield "len", "the frame's rows"


# What a refusal calls a Python function in a plan: Polars writes
# ``map_batches``, ``map_elements`` and ``rolling_map`` alike, as a function
# it will not hand over to be read.
PYTHON_FUNCTION: Final = "a Python function (map_batches, map_elements or rolling_map)"

# The flag Polars sets on a function that answers each row from that row
# alone -- ``is_elementwise=True`` -- as its plan writes it.
_ROW_SEPARABLE: Final = "ROW_SEPARABLE"


def _functions_not_read(expr: pl.Expr) -> Iterator[tuple[str, str]]:
    """Yield each function in ``expr`` this guard cannot see inside, with its operand.

    A Python function is opaque: Polars runs it over whatever rows the frame
    holds, and nothing in the plan says whether it reads one row or all of
    them -- a ``map_batches`` that ranks is the ``rank()`` the guard refuses,
    written where the guard cannot see it. Polars hands such a plan over only
    where ``cloudpickle`` is installed, and then names the function without
    its body; the answer here does not depend on which, so every Python
    function is yielded, whatever it declares. A plugin is read by its own
    declaration: one registered as elementwise answers each row from that
    row, and one registered as not reads the rows together, as an
    aggregation does. Inside ``list.eval(...)`` the rows are one policy's own
    elements, and nothing there is yielded.
    """
    try:
        tree = json.loads(expr.meta.serialize(format="json"))
    except Exception:  # noqa: BLE001 -- unreadable: find the part that is not
        found = _the_part_polars_will_not_hand_over(expr)
        if found is not None:
            yield PYTHON_FUNCTION, found
        return
    yield from _opaque_nodes(tree)


def _the_part_polars_will_not_hand_over(expr: pl.Expr) -> str | None:
    """Return the operand of the innermost part of ``expr`` Polars cannot write out.

    Walked through Polars' own account of each node's inputs
    (``meta.pop()``): the node whose inputs all write out and which itself
    does not is the Python function, and what it is applied to is its
    operand.
    """
    try:
        inputs = expr.meta.pop()
    except Exception:  # noqa: BLE001 -- nothing further to walk
        return str(expr)
    for one in inputs:
        try:
            one.meta.serialize(format="json")
        except Exception:  # noqa: BLE001 -- the function is further in
            return _the_part_polars_will_not_hand_over(one)
    return str(inputs[0]) if inputs else str(expr)


def _opaque_nodes(node: object) -> Iterator[tuple[str, str]]:
    """Yield the Python functions and the plugins over the rows in one plan node."""
    if isinstance(node, list):
        for child in node:
            yield from _opaque_nodes(child)
        return
    if not isinstance(node, dict):
        return
    for kind, body in node.items():
        if kind == "Eval" and isinstance(body, dict):
            # One policy's own list, unless the cumulative variant.
            variant = body.get("variant")
            if isinstance(variant, dict) and "Cumulative" in variant:
                yield from _opaque_nodes(body.get("expr"))
            continue
        if kind == "AnonymousFunction" and isinstance(body, dict):
            yield PYTHON_FUNCTION, _operand_of(body)
            continue
        plugin = _a_plugin_over_the_rows(kind, body)
        if plugin is not None and isinstance(body, dict):
            yield plugin, _operand_of(body)
        yield from _opaque_nodes(body)


def _a_plugin_over_the_rows(kind: str, body: object) -> str | None:
    """Name a plugin call registered as reading the rows together, or None."""
    if kind != "Function" or not isinstance(body, dict):
        return None
    function = body.get("function")
    plugin = function.get("FfiPlugin") if isinstance(function, dict) else None
    if not isinstance(plugin, dict):
        return None
    flags = plugin.get("flags")
    declared = flags.get("flags") if isinstance(flags, dict) else None
    if isinstance(declared, str) and _ROW_SEPARABLE in declared:
        return None
    return (
        f"the plugin function {plugin.get('symbol')!r}, registered with "
        "is_elementwise=False,"
    )


def _operand_of(body: dict[str, object]) -> str:
    """Return what a function node is applied to, as a refusal quotes it."""
    inputs = body.get("input")
    first = inputs[0] if isinstance(inputs, list) and inputs else None
    rebuilt = _rebuilt(first)
    return "the frame's rows" if rebuilt is None else str(rebuilt)


# What a window partitioned by the scenario stands as once it is taken out of
# the plan: a column of this name, which reads no row, numbered so a refusal
# can write the window back as the author wrote it.
_A_SCENARIO_WINDOW: Final = "__gaspatchio_scenario_window_{}__"


def _without_the_scenario_windows(
    expr: pl.Expr, column: str
) -> tuple[pl.Expr, dict[str, str], list[pl.Expr]]:
    """Return ``expr`` with every window partitioned by ``column`` taken out.

    Such a window answers from rows of one scenario -- that scenario's copy
    of the book, or a part of it where the partition names further keys
    (``.over(["scenario_id", "product"])``) -- which on a scenario axis whose
    policies are whole stays inside one scenario's book: the reads inside it
    stand. Only a window whose partition includes that column, mapped back
    onto its rows (Polars' default), is taken out; a window's ordering
    expression stays in the plan, so a read across rows inside it is still
    found, and so does any further partition key that is an expression
    rather than a column, handed back beside the plan to be searched too.
    Each window taken out stands as a column named for it, and the map
    beside the plan says what each was. A plan Polars will not hand back is
    left whole, so nothing in it is admitted.
    """
    try:
        tree = json.loads(expr.meta.serialize(format="json"))
    except Exception:  # noqa: BLE001 -- an unserialisable plan is left alone
        return expr, {}, []
    windows: dict[str, str] = {}
    kept: list[object] = []
    taken = _taken_out(tree, column, windows, kept)
    if not windows:
        return expr, {}, []
    rebuilt = _rebuilt(taken)
    keys = [one for key in kept if (one := _rebuilt(key)) is not None]
    if rebuilt is None or len(keys) != len(kept):
        return expr, {}, []
    return rebuilt, windows, keys


def _taken_out(
    node: object, column: str, windows: dict[str, str], kept: list[object]
) -> object:
    """Return a plan node with each window partitioned by ``column`` out.

    A further partition key that is not a bare column is appended to
    ``kept``, so the reads across rows it holds are still searched.
    """
    if isinstance(node, list):
        return [_taken_out(child, column, windows, kept) for child in node]
    if not isinstance(node, dict):
        return node
    window = node.get("Over") if len(node) == 1 else None
    keys = window.get("partition_by") if isinstance(window, dict) else None
    if (
        isinstance(window, dict)
        and isinstance(keys, list)
        and {"Column": column} in keys
        and window.get("mapping") == "GroupsToRows"
    ):
        expressions = [
            _taken_out(key, column, windows, kept)
            for key in keys
            if not (isinstance(key, dict) and set(key) == {"Column"})
        ]
        kept.extend(expressions)
        ordered = window.get("order_by")
        if isinstance(ordered, list) and ordered:
            return _taken_out(ordered[0], column, windows, kept)
        name = _A_SCENARIO_WINDOW.format(len(windows))
        original = _rebuilt(node)
        windows[name] = str(original) if original is not None else "a window"
        return {"Column": name}
    return {
        key: _taken_out(child, column, windows, kept) for key, child in node.items()
    }


def _as_written(rendered: str, windows: dict[str, str]) -> str:
    """Write each window a plan stood in for back as the author wrote it."""
    for name, original in windows.items():
        rendered = rendered.replace(f'col("{name}")', original)
    return rendered


def _counts_the_rows(expr: pl.Expr) -> bool:
    """Return whether the plan holds ``pl.len()``, the count of the rows.

    Walked through Polars' own account of each node's inputs
    (``meta.pop()``), so a column or an alias that happens to be called
    ``Len`` is not taken for one. Inside ``list.eval(...)`` the rows are one
    policy's own elements, so a count there is the per-period count and only
    the list the evaluation runs over is looked into.
    """
    try:
        tree = json.loads(expr.meta.serialize(format="json"))
        inputs = expr.meta.pop()
    except Exception:  # noqa: BLE001 -- an unserialisable plan is left alone
        return False
    if tree == _ROW_COUNT:
        return True
    evaluated = tree.get("Eval") if isinstance(tree, dict) else None
    if isinstance(evaluated, dict) and evaluated.get("variant") == "List":
        over = _rebuilt(evaluated.get("expr"))
        return over is not None and _counts_the_rows(over)
    return any(_counts_the_rows(one) for one in inputs)


def _on_a_scenario_axis(frame: object) -> bool:
    """Return whether ``frame``'s record holds a scenario axis it was crossed with."""
    from gaspatchio.scenarios._with_scenarios import (  # noqa: PLC0415 -- cycle
        scenario_axis_columns,
    )

    try:
        return bool(scenario_axis_columns(frame))  # type: ignore[arg-type]
    except AttributeError:
        return False


def _the_rows_and_the_one_batch(where: NotTheBook) -> tuple[str, str]:
    """Say whose rows a read answers from here, and how to run the book in one batch."""
    if where.on_a_scenario_axis:
        return (
            (
                "every scenario's copy of every policy, so it answers from every "
                "scenario's rows together, at any batch size"
            ),
            (
                "or run the model over the book alone, in one batch with no "
                "scenario axis -- af.collect() over the model points"
            ),
        )
    return (
        (
            "the batch, so each policy's value would depend on which other "
            "policies share its batch, and the total on the batch size"
        ),
        (
            "or run the book in one batch -- af.collect(), or a batch_size of "
            "at least the number of policies"
        ),
    )


def _refusal(
    method: str,
    operand: str,
    where: NotTheBook,
    *,
    axis: str | None,
    selection: bool = False,
) -> str:
    """Say what the read would answer here, and the ways to write the figure."""
    if selection:
        return _selection_refusal(method, operand, where, axis=axis)
    rows, one_batch = _the_rows_and_the_one_batch(where)
    per_scenario = (
        ""
        if axis is None
        else (
            " For each scenario's own figure, partition the read by the "
            f"scenario -- pl.col('sum_assured').sum().over({axis!r}) -- which "
            "answers from that scenario's copy of the book alone."
        )
    )
    return (
        f"{_what_it_does(method, operand)}, and here the "
        f"frame is not the whole book: {where.cut}. A read across rows answers "
        f"from the rows in the frame, and here those are {rows}. A policy's "
        "value must not depend on which other policies share its run. Compute "
        "a figure across the book before the run, as a model-point column the "
        "model reads -- model_points.with_columns((pl.col('sum_assured') / "
        "pl.col('sum_assured').sum()).alias('sa_share')) -- "
        f"{one_batch}.{per_scenario}{_written_readably(method)}"
    )


def _what_it_does(method: str, operand: str) -> str:
    """Say what a read does to the rows: what it reads, or that it cannot be read."""
    if method == PYTHON_FUNCTION:
        return (
            f"{method} on {operand} cannot be read -- Polars will not hand its "
            "body over -- so nothing here can tell whether it answers each row "
            "from that row alone or reads across the rows of the frame"
        )
    if method.startswith("the plugin function"):
        return (
            f"{method} on {operand} is declared to read the rows of the frame together"
        )
    return f"{method} on {operand} reads across the rows of the frame"


def _what_the_condition_does(method: str, operand: str) -> str:
    """Say what a filter's condition does to the rows, as its refusal opens."""
    if method == PYTHON_FUNCTION or method.startswith("the plugin function"):
        return f"The filter's condition holds {_what_it_does(method, operand)}"
    return (
        f"The filter's condition reads across the rows of the frame -- {method} "
        f"on {operand}"
    )


def _written_readably(method: str) -> str:
    """Return the further route for a read this guard cannot see inside."""
    if method == PYTHON_FUNCTION:
        return (
            " Or write the calculation in Polars' own expressions, which "
            "this run reads and lets stand wherever they read one row."
        )
    if method.startswith("the plugin function"):
        return (
            " Or, where the plugin answers each row from that row alone, "
            "register it with is_elementwise=True."
        )
    return ""


def _selection_refusal(
    method: str,
    operand: str,
    where: NotTheBook,
    *,
    axis: str | None,
) -> str:
    """Say what a filter's read across rows would choose here, and the ways out."""
    rows, one_batch = _the_rows_and_the_one_batch(where)
    per_scenario = (
        ""
        if axis is None
        else (
            " To choose within each scenario's own book, partition the read by "
            f"the scenario -- pl.col('sum_assured').mean().over({axis!r})."
        )
    )
    return (
        f"{_what_the_condition_does(method, operand)} -- and here the frame "
        f"is not the whole book: {where.cut}. "
        f"A read across rows answers from the rows in the frame, and here those "
        f"are {rows}. Whether a policy is valued must not depend on which other "
        "policies share its run. Compute the figure across the book before the "
        "run, as a model-point column the filter compares with -- "
        "model_points.with_columns(pl.col('sum_assured').mean()"
        ".alias('mean_sa')), then af.filter(af.sum_assured > af.mean_sa) -- "
        f"{one_batch}.{per_scenario}{_written_readably(method)}"
    )


__all__ = [
    "ON_A_SCENARIO_PLAN",
    "NotTheBook",
    "ReadAcrossRowsError",
    "batches_cut",
    "book_of_the_run",
    "crossing_a_book",
    "frame_is_not_the_book",
    "hold_a_crossing",
    "one_batch_of_several",
    "refuse_a_grid_sized_from_the_rows",
    "refuse_a_read_across_rows",
    "refuse_an_injection_the_rows_cannot_take",
    "refuse_values_from_outside_the_batch",
    "the_run_s_book",
]
