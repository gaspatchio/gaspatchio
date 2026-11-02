# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Core ActuarialFrame implementation for actuarial modeling
# ABOUTME: Main DataFrame wrapper over a Polars LazyFrame with a durable calculation log
# ruff: noqa: E501, TID252, N806
# type: ignore[return-value, attr-defined, arg-type, assignment, override, misc]
"""Core ActuarialFrame implementation for actuarial modeling."""

from __future__ import annotations

import json
import keyword
import numbers
from collections.abc import Iterator
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Final
from weakref import ref

import numpy as np
import polars as pl
from loguru import logger

from gaspatchio._dtypes import (
    holds_a_decimal,
    series_with_signed_zeros_as_zero,
    wider_than_i64_at,
    with_integers_as_i64,
)
from gaspatchio._identity import content_sha_of, injected_content_sha_of
from gaspatchio._semantic.ir import BinOp, Call, Col, EngineNative, Lit, WhenThen, walk
from gaspatchio._semantic.join_keys import join_on_attribute, unwritable_join_keys
from gaspatchio._shape import _resolve_expr_output_dtype
from gaspatchio._source import display_filename
from gaspatchio.engines.report import RunReport, RunSummary, _stating

# Import types
# Import proxies
from ..column import ColumnProxy, ConditionExpression, ExpressionProxy
from ..column.proxy_aware_expr import ProxyAwareExpr

# Import error handling
from ..errors import _handle_execution_error, _handle_plan_lowering_panic

# ADDED: Import registry
from ..frame.registry import (
    _ACCESSOR_REGISTRY,
    _FRAME_DECLARED_ACCESSORS,
    _frame_attribute_kind,
)

# Import telemetry for apply/map warnings
# Import utilities
from ..rollforward import _registry
from ..util import get_default_mode, get_default_verbose, get_error_mode

# What a write past the frame's own doors defined, and which arriving columns
# hold values another frame calculated.
from ._across_rows import (
    book_of_the_run,
    refuse_a_read_across_rows,
    refuse_an_injection_the_rows_cannot_take,
    refuse_values_from_outside_the_batch,
)
from ._row_choosing import per_period_condition_refusal, row_choosing_refusal
from ._row_operations import (
    refuse_a_raw_fragment_over_periods,
    refuse_a_row_operation_over_periods,
)

# ADDED: Import the durable calculation log — how it is written, and the
# record vocabulary it writes
from .calculation_log import (
    _RETAINED_PREFIX,
    _CalculationLogMixin,
    _kernel_scratch_prefix,
    _refuse_reserved_column_names,
    _retained_column_name,
    _RunScan,
    _working_columns,
)
from .calculations import (
    BoundaryRecord,
    CalculationRecord,
    MintedColumns,
    OverwriteRecord,
    SealedWindow,
    SelectionRecord,
    StructuralOperation,
    capture_source_span,
    with_columns_operation,
)
from .graph.calc_graph import GraphFrameAccessor

# The plugin wrappers live with the Polars lowerings; that is their one home.
from .lowering._polars import plugins
from .lowering._polars.expressions import literal_expression
from .lowering.artefacts import register_join_right
from .lowering.context import context_for
from .lowering.ingress import refuse_an_unfinished_chain, to_node, within_i64
from .lowering.polars import lower_polars
from .lowering.rules.rollforward import run_reading_wide_inputs_as_i64
from .lowering.value_reads import refuse_a_value_read_inside_a_fragment
from .plan_writes import (
    ColumnWritten,
    ComputedValues,
    Origin,
    PlanReading,
    ValuesAccount,
    outputs_of,
    read_plan_write,
    tables_in,
)

# ADDED: Import the traced-run entry point
from .tracing import build_trace_decorator, log_query_plan

if TYPE_CHECKING:
    # Keep TYPE_CHECKING block for potential future forward refs if needed
    from collections.abc import Callable, Iterable, Mapping  # trace and select
    from weakref import ReferenceType

    from gaspatchio._semantic.ir import OpNode
    from gaspatchio._source import SourceSpan
    from gaspatchio.frame.lowering.context import LoweringContext
    from gaspatchio.typing import IntoExprColumn

    # Add forward references for accessors used in type hints
    from ..accessors.date import DateFrameAccessor
    from ..accessors.excel import ExcelFrameAccessor
    from ..accessors.finance import FinanceFrameAccessor
    from ..accessors.projection_frame import ProjectionFrameAccessor
    from ..engines.protocol import EngineResult
    from .calculations import LogEntry


# TODO: Move _DEFAULT_THREADS to util? For now, define locally or assume 0.  # noqa: TD002, TD003, FIX002
_DEFAULT_THREADS = 0

# Below this column count the lazy plan is shallow enough that a deep
# ``collect_schema()`` is already cheap, so incremental schema maintenance on
# assignment is not worth its overhead (matches column/shape.py's probe gate).
_INCREMENTAL_SCHEMA_MIN_COLS = 16

# The three names Polars answers to. Anything else at ``collect(engine=)``
# is a second engine's name, looked for through ``gaspatchio.engines``.
# Spelled once here so the door and its refusal cannot come apart.
_POLARS_ENGINES: tuple[str, ...] = ("streaming", "in-memory", "auto")

# The values this process's collects produced, indexed only when a frame is
# built over a DataFrame and asks which of its columns another frame
# calculated. One for the process, because the memory it indexes is.
_COMPUTED_VALUES: Final = ComputedValues()

# Set while the framework builds a frame over the book a caller handed it --
# the command line's run of a model, a batch of a batched run, an export's
# own run. That DataFrame is the run's data on the caller's own word, so it
# is not searched for values another frame calculated.
_OVER_THE_BOOK: ContextVar[bool] = ContextVar("gaspatchio_over_the_book", default=False)


# Set while a batched runner builds a frame over one batch of a book whose
# wide integer columns it has already judged over the whole book (section 10).
# Such a frame does not judge them again over the batch's own values when it
# is collected: one batch of a column that does not fit would otherwise come
# back Int64 and the next UInt64.
_JUDGED_OVER_THE_BOOK: ContextVar[bool] = ContextVar(
    "gaspatchio_judged_over_the_book", default=False
)


def _frame_over_the_book(
    data: pl.DataFrame | pl.LazyFrame,
    *,
    mode: str | None = None,
    retain_superseded: bool = True,
    judged: bool = False,
) -> ActuarialFrame:
    """Build the frame the framework runs a model over, from the book it was handed.

    Exactly ``ActuarialFrame(data, ...)``, less one check: a DataFrame a
    model hands the constructor is searched for columns another frame
    calculated (see :func:`_calculated_elsewhere`), and the book a caller
    handed the framework to run is not. It is the run's data by the caller's
    own word, and a batch cut from it is the same book. ``judged`` says the
    caller has read the book's wide integer columns over the whole book
    already, so a batch handed over as a plan is not judged again when it is
    collected.
    """
    token = _OVER_THE_BOOK.set(True)
    judged_token = _JUDGED_OVER_THE_BOOK.set(judged)
    try:
        return ActuarialFrame(data, mode=mode, retain_superseded=retain_superseded)
    finally:
        _JUDGED_OVER_THE_BOOK.reset(judged_token)
        _OVER_THE_BOOK.reset(token)


def _calculated_elsewhere(data: pl.DataFrame) -> dict[str, Origin]:
    """Return each column of ``data`` whose values a calculation on another frame made.

    Found by memory, not by value: a column counts only where it still holds
    the very buffers a collect of another frame produced for a column that
    frame calculated, while that frame or its caller still holds those
    values, and where those buffers are none of that frame's arriving
    columns. See
    :class:`~gaspatchio.frame.plan_writes.ComputedValues` for what that can
    and cannot see. Nothing is looked for in the book the framework itself
    was handed to run.

    The check never fails the construction that asked: a failure in it is
    logged, and the frame is built with nothing found.
    """
    if _OVER_THE_BOOK.get():
        return {}
    try:
        return _COMPUTED_VALUES.computed(data)
    except Exception:  # noqa: BLE001 -- a check never fails a construction
        logger.opt(exception=True).debug(
            "Could not check which arriving columns another frame calculated; "
            "the frame is built with every column taken as data."
        )
        return {}


def _values_account(frame: ActuarialFrame) -> Callable[[], ValuesAccount]:
    """Return how to account, later, for the values ``frame`` has just collected.

    Which of their columns a calculation on the frame produced, with the
    definition and its line, and which arrived with its data -- as they
    stood at this collect, which is what the values are. Read when a check
    first needs it, and not at all where none does. The function holds the
    frame's log and its arriving set, never the frame, so a frame that was
    a temporary can be let go while its values are still found.

    A column the frame itself arrived holding that another frame calculated
    is accounted to that other frame's definition, so a frame rebuilt from a
    rebuilt one still names where the values were made. A column of values
    handed over wholesale arrived, as a column of the data did, and a column
    written over past the frame's doors is neither.

    The data the frame was built over is held too, until the check reads
    it, because it says more than the arriving set does: a column the model
    dropped or renamed away has left that set, and a calculation that handed
    it back unchanged still holds its memory, which is the data's.
    """
    log = frame._calculations  # noqa: SLF001 -- the frame's own log
    logged = len(log)
    arrived = frame._initial_columns  # noqa: SLF001 -- as above
    rebuilt = frame._rebuilt  # noqa: SLF001 -- as above
    book = frame._arrival_data  # noqa: SLF001 -- as above

    def account() -> ValuesAccount:
        from .graph.graph_builder import (  # noqa: PLC0415 — import cycle
            _is_injection,
        )
        from .graph.graph_utils import source_location  # noqa: PLC0415 — as above

        live: dict[str, CalculationRecord | OverwriteRecord] = {}
        for entry in log[:logged]:
            if isinstance(entry, CalculationRecord | OverwriteRecord):
                live[entry.column] = entry
        defined = {
            column: origin for column, origin in rebuilt.items() if column not in live
        }
        handed = {column for column in arrived if column not in live}
        for column, entry in live.items():
            if isinstance(entry, OverwriteRecord):
                continue
            if _is_injection(entry.node):
                handed.add(column)
                continue
            defined[column] = Origin(
                node_id=f"{column}@{entry.ordinal}",
                source_location=source_location(entry.source),
            )
        data = tuple(
            series
            for table in (() if book is None else tables_in(book))
            for series in table.iter_columns()
            if series.name not in rebuilt
        )
        return ValuesAccount(defined=defined, arrived=frozenset(handed), data=data)

    return account


# The order each kind of join keeps where its caller names none: the frame's
# own rows first and where they were, deterministically. A left or inner
# join is a lookup, and "left_right" keeps the rows as the book holds them
# and a row the other table matches more than once gets its matches in the
# order that table lists them: "left" alone keeps the rows but hands a
# row's several matches back in a different order from run to run. A full,
# right or cross join also brings rows of the other table's, and
# "left_right" puts them after the frame's, in their own order. A semi or
# anti join only keeps some of the frame's rows, each once, and "left" keeps
# those in place. Measured under the streaming engine cutting the frame into
# 1000-row morsels (Polars 1.42.1): each setting gives one answer run after
# run, where Polars' own default gave a different one every run.
_ORDER_KEPT_BY_JOIN: Final[dict[str, str]] = {
    "left": "left_right",
    "inner": "left_right",
    "full": "left_right",
    "outer": "left_right",
    "right": "left_right",
    "cross": "left_right",
    "semi": "left",
    "anti": "left",
}


# The join types that choose rows rather than bring columns: each is recorded
# as a selection step (see ``SelectionRecord``).
_SELECTING_JOINS: Final[frozenset[str]] = frozenset({"semi", "anti"})


def _order_kept_by(how: str) -> str:
    """Return the ``maintain_order`` that keeps the frame's rows, or refuse the kind.

    Raises:
        ValueError: If the join kind is not one the frame knows how to keep
            its rows in order through.

    """
    order = _ORDER_KEPT_BY_JOIN.get(how)
    if order is None:
        kinds = ", ".join(sorted({*_ORDER_KEPT_BY_JOIN} - {"outer"}))
        msg = (
            f"Cannot join how={how!r}: the frame keeps its rows in their order "
            "through a join, so the output and the book it is digested as are "
            f"the same from run to run, and knows how to for {kinds} joins. Use "
            "one of those, or name the row order yourself with maintain_order=."
        )
        raise ValueError(msg)
    return order


def _given_keys(keys: object) -> list[object]:
    """Return one side's join keys as a list, however the caller wrote them."""
    if keys is None:
        return []
    if isinstance(keys, (list, tuple)):
        return list(keys)
    return [keys]


def _refuse_a_join_the_record_cannot_carry(
    this_frame: dict[str, pl.DataType],
    other_table: pl.LazyFrame,
    keys: tuple[object, object, object],
) -> None:
    """Refuse a join before it changes anything, naming the key and the move.

    ``keys`` is the call's ``on``, ``left_on`` and ``right_on``. Three things
    a join's record cannot carry are refused in plain words while the frame
    is still as it was, rather than left to fail half way through the join:

    - **a key that is not a column's name** -- an expression, a proxy -- since
      the record names the columns each row was matched on;
    - **a name the record cannot write** -- one holding ``,`` or ``=``, or an
      empty one -- since it would read back as other keys;
    - **a column of lists** -- a projected column holds one value per period,
      and a join matches each row once, on one value.

    A key either side does not hold is left to Polars, whose own refusal
    names it; the frame is untouched by then all the same.

    Raises:
        TypeError: If a key is not a column name.
        ValueError: If a key's name cannot be recorded, or it holds lists.

    """
    on, left_on, right_on = keys
    for key in (*_given_keys(on), *_given_keys(left_on), *_given_keys(right_on)):
        if not isinstance(key, str):
            msg = (
                f"Cannot join on {key}: a join takes its key columns by name, so "
                "that its record can say which columns matched each row. Pass the "
                'column\'s name -- on="product_code" -- and where the key is a '
                "calculation, write it to a column of its own first "
                "(af.product_key = ...) and join on that name."
            )
            raise TypeError(msg)
    named = [
        [key for key in _given_keys(side) if isinstance(key, str)] for side in keys
    ]
    unwritable = unwritable_join_keys(*named)
    if unwritable:
        listed_names = ", ".join(repr(name) for name in unwritable)
        msg = (
            f"Cannot join on {listed_names}: the join's record lists its key columns in "
            "one line of text, separated by ',' and by '=', so a key whose name "
            "holds either character -- or has no name at all -- would be "
            "recorded as other keys, and the lineage of every column the join "
            "brings in would name columns the model never matched on. Rename "
            "the column before joining, on this frame (af.rename({...})) and on "
            "the other table, and join on the new name."
        )
        raise ValueError(msg)
    other = other_table.collect_schema()
    sides = (
        (_given_keys(left_on if on is None else on), this_frame),
        (_given_keys(right_on if on is None else on), other),
    )
    listed = [
        name
        for names, schema in sides
        for name in names
        if isinstance(schema.get(str(name)), (pl.List, pl.Array))
    ]
    if listed:
        msg = (
            f"Cannot join on {listed[0]!r}: it holds one value per projection "
            "period, and a join matches each row once, on one value, so a column "
            "of lists cannot be its key. Join on the policy-level column the "
            "period one is derived from, before the projection; or look the "
            "value up period by period with a Table (Table.lookup), whose keys "
            "may be period columns."
        )
        raise ValueError(msg)


# What a left join's unmatched key may mean, by the name 11.1.2 records it under.
_MISS_POLICIES: Final[tuple[str, ...]] = ("raise", "null")


def _refuse_an_unused_miss_policy(how: str, on_missing: object) -> None:
    """Refuse a miss policy that is not one, or that this join type would not read.

    Raises:
        ValueError: If ``on_missing`` is neither ``"raise"`` nor ``"null"``, or
            is ``"null"`` on a join that is not a left join.

    """
    if on_missing not in _MISS_POLICIES:
        msg = (
            f"on_missing={on_missing!r} is not a miss policy a join takes: "
            '"raise" refuses a policy whose key matches no row of the other '
            'table, and "null" keeps it with null in every column the join '
            "brings. To stand a number in for a miss, keep the null and fill "
            "it on the next line (af.rate = af.rate.fill_null(0.0))."
        )
        raise ValueError(msg)
    if on_missing == "null" and how != "left":
        msg = (
            f'on_missing="null" is a left join\'s, and this is a {how} join, '
            "which already says what an unmatched key means: an inner join "
            "drops the policy, a semi or anti join selects by the key, and a "
            "full or right join keeps the other table's rows. Drop "
            'on_missing, or write how="left".'
        )
        raise ValueError(msg)


def _refuse_an_unmatched_key(
    this_frame: pl.LazyFrame,
    other_table: pl.LazyFrame,
    keys: tuple[object, object, object],
    where: SourceSpan | None,
) -> None:
    """Refuse a left join one of whose policies' keys matches no row, by name.

    A policy left without its parameters takes null in every arriving column,
    and every fold that skips nulls then leaves it out of the total without a
    word -- a book key ``"Term20"`` against a table holding ``"TERM20"`` took
    one policy out of a portfolio sum. A null key matches no row and is a
    miss, as it is for ``Table.lookup``.

    Raises:
        ValueError: If any policy's key matches no row of the other table.

    """
    on, left_on, right_on = keys
    left_keys = [str(key) for key in _given_keys(left_on if on is None else on)]
    right_keys = [str(key) for key in _given_keys(right_on if on is None else on)]
    if not left_keys:
        return
    row = "__gaspatchio_join_row"
    # The other table's key tuples, under this frame's key names, tested by
    # membership rather than by a second join: the check is about the join
    # the caller wrote, and adds none of its own to the plan.
    held = (
        other_table.select(
            pl.struct(
                [
                    pl.col(theirs).alias(ours)
                    for ours, theirs in zip(left_keys, right_keys, strict=True)
                ]
            ).alias(row)
        )
        .unique()
        .collect()
        .get_column(row)
    )
    missed = (
        this_frame.select(left_keys)
        .with_row_index(row)
        .filter(
            pl.any_horizontal([pl.col(key).is_null() for key in left_keys])
            | ~pl.struct(left_keys).is_in(held.implode())
        )
        .collect()
    )
    if missed.height == 0:
        return
    total = this_frame.select(pl.len()).collect().item()
    first = missed.row(0, named=True)
    key = ", ".join(f"{name}={first[name]!r}" for name in left_keys)
    at = f" at {display_filename(where.file)}:{where.line}" if where is not None else ""
    policies = "policy" if total == 1 else "policies"
    msg = (
        f"The join on {', '.join(map(repr, left_keys))}{at} found no row in the "
        f"other table for {missed.height} of {total} {policies} -- the first at "
        f"row {first[row]} (from 0), {key}. Under a left join a policy with no row "
        "would take null "
        "for every column the join brings, and every total that skips nulls "
        "would leave it out without a word. Correct the key, or add the row to "
        "the other table; or, where a missing row means nothing applies -- an "
        'optional rider -- pass on_missing="null" and fill the null the line '
        "after (af.rate = af.rate.fill_null(0.0))."
    )
    raise ValueError(msg)


def _right_side_fingerprint(other: pl.DataFrame | pl.LazyFrame) -> str | None:
    """Return a content identity for a join's right-side table, and retain it.

    ``content_sha_of`` is the framework's one content-identity primitive,
    the same one an assumption table takes over its own source
    (``Table.fingerprint``): put the rows in a deterministic order, encode
    the values under the published content grammar, hash the bytes. Two
    loads of the same table in different row orders therefore fingerprint
    identically, and a single changed cell changes the hash -- which is
    what makes the join record answer "which version of the expense table
    was this run against?".

    **The right side is put in a canonical form first**, as a ``Table`` is:
    its columns ascending by name, then its rows sorted by every column in
    that order. The order the caller's frame listed its columns in is how
    it was laid out, not what it holds, so it reaches no byte, and the same
    expense table handed over with two columns swapped fingerprints the
    same. The one difference from ``Table``'s form: a ``Table`` puts its
    answer column last and sorts by its dimension columns, which are unique
    keys and so give a total order. A join's right side has no answer column
    and no such guarantee -- join keys may repeat -- so the sort is over
    every column instead. Rows that tie under that are identical rows, which
    encode identically either way.

    Because the two callers order and project differently, **a join
    fingerprint and a ``Table.fingerprint()`` are never comparable**, even
    over the same file: the Table hashes its dimensions-plus-value
    projection, this hashes the whole right side. Each answers "is this the
    same table as last quarter's run?", neither answers "are these two
    tables the same?".

    **And the frame that was hashed is kept, so the artifact can carry it.**
    The hash answers "which version of that table?" and answers "which
    table?" for nobody -- a second implementation holding the record and no
    right side can read what the join did and cannot do it. So the sorted
    frame goes to ``register_join_right`` under the identity just taken, and
    the exporter reads it back there and writes it into the artifact's
    assumptions directory beside the lookup tables (section 11.1.2 of the
    specification). The frame filed is the sorted one and not the caller's,
    because the artifact must inline exactly the frame its declared
    fingerprint was taken over; that module states what the retention costs.

    ``None`` in two cases, both honest rather than convenient:

    - a **lazy** right side, where taking a content hash would mean
      collecting the very frame that was handed over lazily precisely so
      it would not be. Hashing the query plan instead was rejected: two
      lazy frames over different in-memory data share one plan text, so
      that fingerprint would fail to change when the data did, which is
      worse than not claiming one.
    - a frame the sort or the serialisation refuses (a nested column with
      no ordering, an instant section 12.3 refuses by name). A missing
      fingerprint is a smaller loss than a join that dies while trying to
      describe itself. It is said at WARNING, with the refusal's own words,
      as a hole whose values cannot be stamped is: the record's null says
      only that no identity was taken, and the log says why.

    Nothing is retained in either case: there is no identity to file one
    under, and the record says the right side was lazy rather than implying
    a table the reader could go and look for.
    """
    if not isinstance(other, pl.DataFrame):
        return None
    try:
        columns = sorted(other.columns)
        sorted_right = other.select(columns).sort(columns)
        return register_join_right(sorted_right, content_sha_of(sorted_right))
    except Exception as exc:  # noqa: BLE001 — describing the table must never break the join
        said = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        logger.warning(
            f"The join's right side ({', '.join(other.columns)}) is recorded with "
            f"no content identity: it could not be hashed ({said}). The record "
            "carries a null right_fingerprint and none of its values, so a "
            "change to this table moves no fingerprint; the join itself ran "
            "as written. Convert or drop the column the refusal names before "
            "the join, and the right side is identified and carried."
        )
        return None


def _holds_python_objects(dtype: pl.DataType) -> bool:
    """Return whether ``dtype`` has an ``Object`` anywhere inside it.

    The dtype of a column is a tree, not a label: ``List`` and ``Array``
    each wrap one inner dtype, a ``Struct`` wraps one per field, and any of
    those may itself be nested again. Reading only the outermost node lets
    ``List(Object)`` and ``Array(Object, k)`` through a check meant to stop
    Python objects becoming a column -- and both are shapes a Series can
    really hold: imploding an object column produces the first, and the
    two-dimensional object array a simulation can hand back produces the
    second.

    The two nested shapes fail differently past this door, and only one of
    them fails in a way a model author could act on. The injection stamp
    encodes the values under the content grammar. Inside a list, that
    encoding refuses the Object cleanly, naming the column -- a message
    about a type the calculation graph has no name for, which is at least
    a message. Inside a fixed-width array it never gets that far: the
    encoding first casts the array to a list, and that cast panics inside
    Rust. What reaches the author then is a message about an unwrapped
    option in an array module, which says nothing whatever about the
    column they assigned -- and it arrives as a ``PanicException``, which
    is not an ``Exception``, so a caller catching one does not catch it.
    Walking the dtype here turns both into one refusal, at the line that
    wrote the column, in the words of the model rather than of the engine.

    ``Struct`` is walked for the same reason even though Polars will not
    currently build a Series over a struct holding an Object -- the
    constructor refuses one -- because a check that stops at struct fields
    is a hole nobody finds until a run meets it.
    """
    if dtype == pl.Object:
        return True
    if isinstance(dtype, pl.List | pl.Array):
        return _holds_python_objects(dtype.inner)
    if isinstance(dtype, pl.Struct):
        return any(_holds_python_objects(field.dtype) for field in dtype.fields)
    return False


def _injected_values(value: Any) -> tuple[pl.Series, str] | None:  # noqa: ANN401
    """Return the injected column ``value`` is, under a fixed name, and how it arrived.

    ``None`` for everything that is a formula rather than data.

    Two containers carry a whole column of values into an assignment, and
    both are data: a ``pl.Series``, and the NumPy array a simulation
    actually hands back — ``rng.binomial(...)`` returns an array, not a
    series. Polars builds the same column from either, so they are stamped
    over the same bytes and only ``origin`` tells them apart.

    Array-shaped means ``numpy.ndarray`` of rank one or more, and nothing
    else. ``pl.lit`` spreads a 1-D array across the rows one value at a
    time, and lands a 2-D one as a fixed-width ``Array`` column, a row per
    policy: both are columns of data. A rank-0 array is not one — it holds
    a single number, which ``pl.lit`` broadcasts to every row exactly as
    it broadcasts a float, so stamping it here would record a count of one
    against a column of n. It takes the literal path instead. Nor is a
    Python list a column: that becomes one list-valued literal repeated on
    every row, which is a formula's operand rather than data. NumPy is a
    hard dependency of the package and is already imported at ``import
    gaspatchio``, so naming the type outright costs nothing and says
    exactly what is meant.

    The series' own name is not part of what gets hashed — the column's
    name is the assignment key — so both are handed back renamed to a
    fixed ``injected``.
    """
    if isinstance(value, pl.Series):
        series = value.rename("injected")
        if holds_a_decimal(series.dtype):
            # Stamped over the values the run reads: a fixed-point decimal
            # enters as the number it denotes, as a book column of one does.
            series = with_integers_as_i64(series.to_frame()).to_series()
        return series, "series"
    if isinstance(value, np.ndarray) and value.ndim > 0:
        return pl.Series("injected", value), "array"
    return None


def _injection_as_it_enters(value: Any) -> Any:  # noqa: ANN401
    """Return ``value`` with a negative zero written as zero, where it is injected data.

    A column handed over wholesale -- a ``pl.Series`` or a NumPy array of
    rank one or more -- is data, and spec section 12.3 hashes data with a
    negative zero written as zero. So that its stamp has one answer, the
    zero is written that way where the column enters the frame, before it
    is stamped or read: ``sign`` and ``to_text`` see ``+0.0``. Anything
    else is handed back as it stands -- a literal in a formula keeps its
    sign (section 12.1).
    """
    if isinstance(value, pl.Series):
        return series_with_signed_zeros_as_zero(value)
    if (
        isinstance(value, np.ndarray)
        and value.ndim > 0
        and value.dtype.kind == "f"
        and bool(np.any((value == 0) & np.signbit(value)))
    ):
        return np.where(value == 0, value.dtype.type(0), value)
    return value


def _select_definitions(
    frame: ActuarialFrame,
    schema: Mapping[str, pl.DataType],
    positional: list[tuple[Any, pl.Expr]],
    named: dict[str, tuple[Any, pl.Expr]],
) -> dict[str, tuple[OpNode, pl.Expr]]:
    """Return the columns one ``select`` calculates, each with its op-tree and expression.

    Each argument as the caller wrote it beside the expression it became,
    read over ``schema``, the columns the frame held, by the rule a write
    straight into the plan is read by (:func:`~.plan_writes.outputs_of`). A
    column handed back as it stands -- a bare reference, a selection of
    columns as they are, a column under its own name, only marked sorted or
    cast to the type it has -- is carried and defined by nothing. Every
    other output is a definition, whichever name it stands under, and its
    op-tree is built from what the caller wrote, as an assignment's is: a
    column of the frame's own formula is core, a Polars expression is
    Polars' own line.

    Raises:
        ValueError: If one expression written over a selection of columns
            calculates, renames or copies any of them: there is no one name
            to record it under. The message names each column and the
            expression to write for it.

    """
    defined: dict[str, tuple[OpNode, pl.Expr]] = {}
    for value, expr in positional:
        if expr.meta.is_column_selection(allow_aliasing=False):
            continue  # columns handed back as they stand
        outputs = _outputs_or_none(schema, expr)
        if _hands_back_each(outputs, expr):
            continue
        if expr.meta.has_multiple_outputs():
            raise ValueError(_several_columns_refusal(outputs))
        name = expr.meta.output_name()
        defined[name] = (_assignment_node(value, column=name), expr)
    for name, (value, expr) in named.items():
        if isinstance(value, str):
            if value != name:
                defined[name] = (
                    _assignment_node(frame[value], column=name),
                    expr.alias(name),
                )
            continue
        aliased = expr.alias(name)
        if _hands_back_each(_outputs_or_none(schema, aliased), aliased):
            continue
        defined[name] = (_assignment_node(value, column=name), aliased)
    return defined


def _outputs_or_none(
    schema: Mapping[str, pl.DataType], expr: pl.Expr
) -> tuple[ColumnWritten, ...] | None:
    """Return what ``expr`` writes over ``schema``, or None where it cannot be read."""
    try:
        return outputs_of(schema, expr)
    except Exception:  # noqa: BLE001 -- the select itself resolved; this only reads it
        logger.opt(exception=True).debug(
            "A select's expression could not be read over the frame's columns."
        )
        return None


def _hands_back_each(outputs: tuple[ColumnWritten, ...] | None, expr: pl.Expr) -> bool:
    """Return whether every column ``expr`` writes is a column as it stands.

    Read off ``outputs`` where the plan reader read them. Where it could not,
    off the expression alone: a column under its own name, and nothing else.
    """
    if outputs is not None:
        return all(column.kept == column.name for column in outputs)
    meta = expr.meta
    if meta.has_multiple_outputs():
        return False
    name = meta.output_name()
    return meta.is_column_selection(allow_aliasing=True) and meta.root_names() == [name]


def _refuse_a_column_replaced_under_an_inherited_name(
    held: Callable[[], Mapping[str, pl.DataType]],
    expr: pl.Expr,
    *,
    door: str,
    aliasable: bool,
) -> None:
    """Refuse an unnamed calculation that would overwrite the column it reads.

    An expression given no name of its own -- no ``.alias(...)``, no keyword
    -- is named by Polars after the first column it reads. Handed to
    ``with_columns`` or ``select``, its answer then lands *on* that column:
    ``af.with_columns(table.lookup(age=af.age))`` writes the rate over
    ``age``, and every later ``af.age`` reads the rate. Nothing raises, the
    record files ``age`` as a calculation reading the table, and the line
    reads as though it added a column. So a calculation that would replace
    a column the frame holds must say which column it writes.

    Only an inherited name is read. A name the author gave -- an alias,
    even one that repeats the column's own name -- is the reassignment
    idiom, stated. A column handed back as it stands (``pl.col("age")``,
    one only marked sorted or cast to the type it has) replaces nothing, by
    the rule ``select`` carries columns by (:func:`_hands_back_each`). An
    expression whose name is not a column it reads -- a literal, an
    injected series -- and one that names several columns at once, which
    each door judges by its own rule, are left alone.

    ``held`` hands back the columns the frame holds before the door writes.
    It is asked only for an expression that has inherited the name of a
    column it reads, so an ordinary ``with_columns`` resolves no schema here.
    ``aliasable`` says whether the value the author wrote has Polars'
    ``.alias``: a framework formula does not, so its refusal names only the
    door's own way to name a column.

    Raises:
        ValueError: If ``expr`` has no name of its own, Polars names it after
            a column it reads, the frame holds that column, and the
            expression calculates rather than carrying the column.

    """
    meta = expr.meta
    if meta.has_multiple_outputs() or not meta.eq(meta.undo_aliases()):
        return
    try:
        name = meta.output_name()
    except Exception:  # noqa: BLE001 -- each door refuses an unnamed output its own way
        return
    if name not in meta.root_names():
        return
    schema = held()
    if name not in schema or _hands_back_each(_outputs_or_none(schema, expr), expr):
        return
    quoted = _quoted_name(name)
    if door == "select":
        new_column = "select(..., <new_column>=<expression>)"
        same_column = f"select(..., {name}=<expression>)"
    else:
        new_column = "af.<new_column> = <expression>"
        same_column = f"af[{quoted}] = <expression>"
    if aliasable:
        new_column += f', or <expression>.alias("<new_column>") inside {door}()'
        same_column += f", or .alias({quoted})"
    msg = (
        f"This {door}() would overwrite the column {quoted} without saying so. "
        "The expression has no name of its own, so Polars names its answer "
        f"after the first column it reads, {quoted}, and the answer replaces "
        f"that column: every later read of {quoted} would get this "
        "calculation instead of the values the frame holds now. Name the "
        f"column it writes: {new_column}. If replacing {quoted} is what you "
        f"mean, say so: {same_column}."
    )
    raise ValueError(msg)


# How many columns a refusal names, and writes an expression for, before it
# says how many more there are.
_NAMED_IN_A_REFUSAL: Final = 3


def _several_columns_refusal(outputs: tuple[ColumnWritten, ...] | None) -> str:
    """Return the refusal for one select expression writing several columns.

    Names the columns it writes, read over the frame's own as Polars
    expands it, and the expression to write for each: a rename or a copy
    where that is all it does, the calculation spelt for each column where
    the plan reader can spell it, and a template where it cannot. Polars'
    own rendering of the expression is never quoted.
    """
    if not outputs:
        return (
            "One expression in this select writes several columns at once, and "
            "the frame could not tell which over the columns it holds. The frame "
            "records each column a select calculates under a name of its own: "
            "write one expression per column, each ending in .alias(...) with "
            "the name of the column it writes."
        )
    names = _first_few([column.name for column in outputs])
    if all(column.kept is not None for column in outputs):
        renamed = {
            str(column.kept): column.name
            for column in outputs
            if column.kept != column.name
        }
        return (
            "One expression in this select only renames or copies columns: it "
            f"writes {names}. The frame records a column a select writes under "
            "a new name as that name's definition, one expression at a time. "
            f"To rename them, use af.rename({_renaming(renamed)}); to copy "
            "them beside the columns they come from, write one aliased "
            f"expression per column: {_expressions_for(outputs)}."
        )
    count = len(outputs)
    many = "a column" if count == 1 else f"{count} columns"
    return (
        "One expression in this select is written over a selection of columns, "
        f"and calculates {many}: {names}. The frame records each column a "
        "select calculates under a name of its own, so write one expression "
        f"per column: {_expressions_for(outputs)}."
    )


def _first_few(items: list[str]) -> str:
    """Return ``items`` joined by commas, the first few of them and how many more."""
    shown = ", ".join(items[:_NAMED_IN_A_REFUSAL])
    more = len(items) - _NAMED_IN_A_REFUSAL
    return shown if more <= 0 else f"{shown} and {more} more"


def _renaming(renamed: dict[str, str]) -> str:
    """Return a rename's mapping as Python, the first few pairs and how many more."""
    pairs = [
        f"{_quoted_name(old)}: {_quoted_name(new)}" for old, new in renamed.items()
    ]
    more = len(pairs) - _NAMED_IN_A_REFUSAL
    shown = "{" + ", ".join(pairs[:_NAMED_IN_A_REFUSAL]) + "}"
    return shown if more <= 0 else f"{shown} -- and {more} more like them --"


def _expressions_for(outputs: tuple[ColumnWritten, ...]) -> str:
    """Return the expression to write for each column, the first few and how many more."""
    written = [_expression_for(column) for column in outputs]
    shown = ", ".join(written[:_NAMED_IN_A_REFUSAL])
    more = len(written) - _NAMED_IN_A_REFUSAL
    return shown if more <= 0 else f"{shown}, and {more} more, one for each column"


def _expression_for(column: ColumnWritten) -> str:
    """Return the expression that writes one column on its own, as Python."""
    name = _quoted_name(column.name)
    if column.kept == column.name:
        return f"pl.col({name})"
    if column.kept is not None:
        return f"pl.col({_quoted_name(column.kept)}).alias({name})"
    if column.written is not None:
        return f"{column.written}.alias({name})"
    reads = ", ".join(f"pl.col({_quoted_name(read)})" for read in column.reads)
    on = f" on {reads}" if reads else ""
    return f"<the calculation{on}>.alias({name})"


def _a_comparison_read_as_one(value: object, frame: ActuarialFrame) -> object:
    """Return a per-policy comparison a lookup handed back as the test it is.

    ``af.r = af.age > 60`` stores the 0.0 or 1.0 indicator (11.1.26), and the
    same test over a table lookup -- ``af.r = table.lookup(age=af.age) > 60``
    -- stored ``True`` or ``False``, typed ``bool`` in the record, because
    the lookup hands its comparison back as a bound Polars expression marked
    a comparison. That mark names the test the frame stores as a column's,
    so it is stored the same way; anything else is handed back as it came.
    """
    if not isinstance(value, ProxyAwareExpr) or value._kind_explicit != "comparison":  # noqa: SLF001
        return value
    node = value.__dict__.get("_node")
    if not isinstance(node, BinOp):
        return value
    return ConditionExpression._from_node(node, frame)  # noqa: SLF001


def _the_name_it_was_given(value: object) -> str | None:
    """Return the name a comparison a lookup handed back was given, or None.

    ``af.with_columns((table.lookup(age=af.age) > 60).alias("over_60"))``
    names the column on the Polars expression the lookup handed back; the
    test it is rebuilt as carries no name, so the batch door read the
    indicator under the lookup's key column -- and refused it for writing
    over that column without saying so. The name is read before the rebuild
    and given back after it.
    """
    if not isinstance(value, ProxyAwareExpr) or value._kind_explicit != "comparison":  # noqa: SLF001
        return None
    try:
        if value.meta.undo_aliases().meta.eq(value):
            return None
        return value.meta.output_name()
    except pl.exceptions.ComputeError:
        return None


def _quoted_name(name: str) -> str:
    """Return a column name as a double-quoted Python string."""
    return json.dumps(name, ensure_ascii=False)


def _assignment_node(value: Any, *, column: str) -> OpNode:  # noqa: ANN401
    """Return the op-tree node standing for one assigned value.

    Everything an assignment can be handed is already an operand somewhere
    else in the framework, so this defers to the same ingress door operator
    dunders use — a proxy contributes the node it carries, a raw Polars
    expression becomes engine-native, a number becomes a literal.

    The one shape the operand door never sees is a whole column of values
    handed over wholesale. A ``pl.Series``, and the NumPy array a
    stochastic model hands back, are data rather than a formula: there is
    no tree that derives either, and wrapping one as an engine-native node
    would both invent a calculation that does not exist and pin the values
    in the ingress table for the life of the process. Worse for an array,
    whose engine-native text renders as ``Series[literal]`` whatever it
    holds: every array assignment in the framework would fingerprint
    alike. It is recorded as the injection it is, stamped with a content
    hash of what was injected.

    That hash is paid on every injecting assignment and scales with the
    rows — about 5 ms per 100,000 Float64 values — so an injection written
    inside a per-scenario loop pays it once per scenario. Hoist it out of the
    loop if the same values are being injected each time.

    A rank-0 array is not a column handed over wholesale, whatever its
    type says: it holds one number, which Polars broadcasts to every row.
    It is unwrapped to that number so it becomes the same literal
    ``np.float64(3.0)`` and a plain ``3.0`` already become — one value,
    one node, however it was spelt.

    ``column`` is the name the assignment gave the values. It is not part
    of the stamp — the series' own name is deliberately kept out of that,
    so the same values stamp alike whatever they arrived as — but a
    refusal has to name the column the author actually wrote rather than
    the placeholder the values are hashed under.

    Raises:
        TypeError: If the values are Python objects, at the top of the
            dtype or nested anywhere inside it, which cannot be a column
            of a model.
        UnmappedDtypeError: If the values have a type the artifact's own
            vocabulary cannot name, which is refused naming ``column``.
    """
    injected = _injected_values(value)
    if injected is not None:
        series, origin = injected
        if _holds_python_objects(series.dtype):
            msg = (
                f"Cannot assign a column of dtype {series.dtype}: a column "
                "holding Python objects, at any depth, is not a column of a "
                "model -- there is no value to project, discount or stamp, so "
                "nothing could later say which data the run used. Convert the "
                "values to a concrete dtype (a float, an integer, a string, a "
                "date) before assigning them."
            )
            raise TypeError(msg)

        # The values are the identity: two models handed different data
        # under one column name are two models, and an injection reads
        # nothing, so no upstream fingerprint can carry the difference for
        # it.
        stamp = injected_content_sha_of(series, column)
        return Call(
            "injected",
            args=(),
            attrs=(("content", stamp), ("origin", origin)),
        )
    if isinstance(value, np.ndarray):
        # Rank 0, necessarily: every other rank was taken above as data.
        # ``item()`` is what makes the array and the number it holds one
        # node rather than two ways of writing the same literal.
        return to_node(value.item())
    node = to_node(value)
    # A table, mortality, curve or schedule read inlined into an engine
    # fragment would leave the fingerprint unable to see it (spec Annex A.2).
    refuse_a_value_read_inside_a_fragment(node, column=column)
    return node


def _check_continuable(data: Any, donor: Any) -> None:  # noqa: ANN401
    """Refuse a ``continue_from=`` this frame could not honestly carry.

    Three things have to be true before the door opens, and each refusal
    names the move that opens it. The donor has to be a frame with a
    history to carry; there has to be something coming back; and what comes
    back has to be values rather than a plan, because the promise
    ``continue_from`` makes is about what each column *holds*, and an
    unexecuted plan holds nothing to check. That last one is the sharp
    edge: accepting a plan here would mean inheriting lineage on the
    strength of a comparison against values a later collect need not
    reproduce.

    Raises:
        TypeError: If ``donor`` is not an ActuarialFrame, or if the values
            are an unexecuted plan.
        ValueError: If the donor holds no data, or nothing was handed back.

    """
    if not isinstance(donor, ActuarialFrame):
        msg = (
            f"continue_from= takes the ActuarialFrame these values came out of, "
            f"not {type(donor).__name__}. Pass the frame you collected: "
            "ActuarialFrame(df, continue_from=af)."
        )
        raise TypeError(msg)
    if donor._collected_values is None:  # noqa: SLF001 -- the donor's own values
        msg = (
            "Cannot continue from that frame: it holds no data of its own to "
            "check these values against. continue_from= carries a column's "
            "calculations only where the column still holds the numbers those "
            "calculations produced, and this frame has not collected since its "
            "plan last changed -- so there is nothing to compare. Collect it, "
            "work on what it hands back, and continue from it: "
            "df = af.collect(); ...; ActuarialFrame(df, continue_from=af)."
        )
        raise ValueError(msg)
    if data is None:
        msg = (
            "continue_from= needs the values that left the frame. Pass them as "
            "the first argument: ActuarialFrame(df, continue_from=af)."
        )
        raise ValueError(msg)
    if isinstance(data, pl.LazyFrame):
        msg = (
            "Cannot continue from a plan that has not run. continue_from= "
            "carries a column's lineage only where its values are the ones the "
            "donor's calculations account for, and an unexecuted LazyFrame has "
            "no values to compare. Collect it first: "
            "ActuarialFrame(plan.collect(), continue_from=af)."
        )
        raise TypeError(msg)


def _root_names(expr: pl.Expr) -> list[str]:
    """Return the columns an expression reads, or none where it cannot say."""
    try:
        return expr.meta.root_names()
    except Exception:  # noqa: BLE001 — meta inspection is best-effort
        return []


def _start_of_operation(log: list[LogEntry], at: int) -> int:
    """Return the first log position of the call that wrote the entry at ``at``.

    Every record of one call carries the call's operation id, so the call
    starts at the first position carrying it.
    """
    entry = log[at]
    if not isinstance(entry, CalculationRecord):
        return at
    for before in range(at + 1):
        candidate = log[before]
        if (
            isinstance(candidate, CalculationRecord)
            and candidate.operation_id == entry.operation_id
        ):
            return before
    return at


def _where(record: CalculationRecord | OverwriteRecord) -> str:
    """Return " at <file>:<line>" for where a record was written, or nothing."""
    span = record.source
    if span is None:
        return ""
    return f" at {display_filename(span.file)}:{span.line}"


def _moved_input_refusal(
    first: CalculationRecord, moved: CalculationRecord | OverwriteRecord
) -> str:
    """Say why a read of a rollforward whose input moved is refused, and the move.

    ``first`` is the record where the frame first read the rollforward, and
    ``moved`` the one that wrote one of its inputs again after it -- a
    calculation, or a write over the input straight into the query plan.
    """
    column = moved.column
    if isinstance(moved, OverwriteRecord):
        how = "written again straight into the query plan"
    elif moved.origin == "rename" and isinstance(moved.node, Col):
        how = f"replaced by {moved.node.name!r}, renamed onto it,"
    else:
        how = "written again"
    return (
        f"This line reads a compiled rollforward whose input {column!r} was "
        f"{how}{_where(moved)} after the frame first read the rollforward"
        f"{_where(first)}. A frame runs a compiled rollforward once, over its "
        "inputs as they stood at that first read -- the calculation graph it "
        "exports binds the rollforward there, and an engine evaluates it once "
        f"-- so this line would answer for the earlier {column!r} while "
        "reading as if it used the later one. To read that run, write this "
        f"line before {column!r} is written again. For a run over the later "
        "values, write them under a name of their own and compile a "
        f"rollforward that reads that column, or write {column!r} before the "
        "frame first reads the rollforward. A rewrite is taken to leave the "
        "values as they were only where that is plain from how it is written: "
        f"af[{column!r}] itself, af[{column!r}] times one in the same type, or "
        "projection.set stamping the same timeline again."
    )


def _is_a_bare_reference_to(expr: pl.Expr, column: str) -> bool:
    """Return whether ``expr`` is ``column`` itself, under any alias."""
    try:
        inner = expr.meta.undo_aliases()
        return inner.meta.is_column() and inner.meta.output_name() == column
    except Exception:  # noqa: BLE001 — meta inspection is best-effort
        return False


def _is_times_one(node: OpNode, column: str) -> bool:
    """Return whether ``node`` is ``column`` multiplied by the number one."""
    match node:
        case (
            BinOp(op="mul", left=Col(name=name), right=Lit(value=value))
            | BinOp(op="mul", left=Lit(value=value), right=Col(name=name))
        ):
            return name == column and type(value) in {int, float} and value == 1
        case _:
            return False


def _dtype_from(expr: pl.Expr, column: str, dtype: pl.DataType) -> pl.DataType | None:
    """Return the type ``expr`` gives where ``column`` holds ``dtype``, if it can say."""
    try:
        schema = pl.LazyFrame(schema={column: dtype}).select(expr.alias(column))
        return schema.collect_schema()[column]
    except Exception:  # noqa: BLE001 — a type it cannot work out proves nothing
        return None


def _accessor_read_destination(name: str, kinds: dict[str, type]) -> str:
    """Say where ``af.<name>`` goes, for the accessor kinds registered.

    ``__getattr__`` returns a FRAME accessor under a registered name and
    nothing else does, so a name carrying only a COLUMN accessor reaches no
    accessor through ``af.<name>``: it raises the did-you-mean
    ``AttributeError``, or hands back the user's own column where the frame
    carries one. A column accessor hangs off a column instead. The refusal
    in ``__setattr__`` tells an actuary where to go next, so it has to be
    right about where that is, for every kind a name can be registered
    under. An entry carrying neither kind is reachable only by writing to
    the registry directly, and is told the one thing still true of it.

    The CLASS answers before the registry does, because that is the order a
    read resolves in. The five names in ``_FRAME_DECLARED_ACCESSORS`` are
    declared properties that hand back their frame accessor whatever the
    registry holds -- empty ``_ACCESSOR_REGISTRY["date"]`` and ``af.date``
    is still ``DateFrameAccessor`` -- so the registry kinds are not what
    decides their clause. Any OTHER name the class carries wins attribute
    access over an accessor of the same name, so ``af.<name>`` reaches the
    method or property, not the accessor; ``register_accessor`` refuses a
    frame accessor under such a name, and a direct write to the registry
    that gets one there anyway is told what the read really reaches.
    """
    if name in _FRAME_DECLARED_ACCESSORS:
        return f"af.{name} goes on reaching the frame accessor."
    declared = getattr(ActuarialFrame, name, None)
    if declared is not None:
        return _frame_attribute_kind(name, declared)
    if "frame" in kinds:
        return f"af.{name} goes on reaching the frame accessor."
    if "column" in kinds:
        return (
            f"'{name}' is a column accessor, reached as "
            f"af.<column>.{name}, not as af.{name}."
        )
    return f"af.{name} reaches no accessor."


class _AggregationResult:
    """Base class for aggregation results that provides convenient scalar access."""

    def __init__(self, df: pl.DataFrame) -> None:
        self._df = df

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401
        """Return the scalar value directly for convenience."""
        return self._df[key][0]

    def __repr__(self) -> str:
        return repr(self._df)

    def __str__(self) -> str:
        return str(self._df)

    @property
    def to_frame(self) -> pl.DataFrame:
        """Allow access to the underlying DataFrame if needed."""
        return self._df


class MaxResult(_AggregationResult):
    """Result wrapper for max() method that provides convenient scalar access."""


class MinResult(_AggregationResult):
    """Result wrapper for min() method that provides convenient scalar access."""


class MeanResult(_AggregationResult):
    """Result wrapper for mean() method that provides convenient scalar access."""


class StdResult(_AggregationResult):
    """Result wrapper for std() method that provides convenient scalar access."""


class VarResult(_AggregationResult):
    """Result wrapper for var() method that provides convenient scalar access."""


class MedianResult(_AggregationResult):
    """Result wrapper for median() method that provides convenient scalar access."""


class SumResult(_AggregationResult):
    """Result wrapper for sum() method that provides convenient scalar access."""


class CountResult(_AggregationResult):
    """Result wrapper for count() method that provides convenient scalar access."""


class ProductResult(_AggregationResult):
    """Result wrapper for product() method that provides convenient scalar access."""


class QuantileResult(_AggregationResult):
    """Result wrapper for quantile() method that provides convenient scalar access."""


# The nine whole-frame aggregations below differ in the plan they build and
# in the wrapper they hand back; the refusal on a frame with no plan, and
# the collect that turns a one-row LazyFrame into the eager frame a caller
# reads, are the same thing said nine times. They are said here once. The
# verb is the one the message names, so each refusal reads exactly as it
# always did.
def _aggregate[ResultT: _AggregationResult](
    frame: ActuarialFrame,
    verb: str,
    result: type[ResultT],
    plan: Callable[[pl.LazyFrame], pl.LazyFrame],
) -> ResultT:
    """Run one whole-frame aggregation and wrap the single row it returns."""
    source = frame._df  # noqa: SLF001 -- the frame this aggregates
    if source is None:
        msg = f"Cannot compute {verb} on an uninitialized ActuarialFrame."
        raise ValueError(msg)
    # A whole-frame aggregation answers for the model's columns. The plan
    # also carries the rollforward kernel's scratch struct and the output of
    # any definition a later write replaced, and a row of totals with either
    # of those in it is a row nobody asked for -- one of them is not even a
    # number.
    hidden = (_kernel_scratch_prefix(), _RETAINED_PREFIX)
    working = [
        name for name in source.collect_schema().names() if name.startswith(hidden)
    ]
    if working:
        source = source.drop(working)
    return result(plan(source).collect())


def _per_period_read(node: OpNode, context: LoweringContext) -> tuple[str, str] | None:
    """Return the first read under ``node`` that holds a value per period.

    A read under a reduction to one value per policy (``list.get``,
    ``list.min``) is not one, and a compiled rollforward's state is named by
    its state rather than by the columns the run reads.
    """
    from .lowering.polars import shape_of  # noqa: PLC0415 -- import cycle

    if isinstance(node, Call) and node.name == "rollforward.state":
        return "state", str(dict(node.attrs).get("state"))
    if isinstance(node, Col):
        shaped = context.shape_of_column(node.name)
        return ("column", node.name) if shaped == "list" else None
    try:
        if shape_of(node, context) != "list":
            return None
    except (TypeError, ValueError, pl.exceptions.PolarsError):
        return None
    children: tuple[OpNode, ...] = ()
    if isinstance(node, BinOp):
        children = (node.left, node.right)
    elif isinstance(node, Call):
        children = node.args
    elif isinstance(node, WhenThen):
        children = (node.cond, node.then, node.otherwise)
    return next(
        (found for child in children if (found := _per_period_read(child, context))),
        None,
    )


# The note an eager door adds when the plan it was handed already did not
# resolve: the error is an earlier line's, named in the message above it.
_NOT_RUN = (
    "{door}() was not run: the plan stopped resolving at an earlier line, "
    "named above, and that line is the one to fix."
)


def _resolves(plan: pl.LazyFrame) -> bool:
    """Say whether a plan's schema resolves."""
    try:
        plan.collect_schema()
    except Exception:  # noqa: BLE001 -- any failure to resolve is the answer
        return False
    return True


class ActuarialFrame(_CalculationLogMixin):
    """A lazy, chainable, and traceable DataFrame for actuarial modeling.

    The ActuarialFrame provides a high-level API for common actuarial
    calculations and data manipulations, leveraging Polars LazyFrames for
    performance. It supports tracing of operations for optimization and
    introspection, and provides convenient accessors for specialized
    functionality (e.g., date, finance, excel operations).

    Args:
        data (dict | polars.DataFrame | polars.LazyFrame | None, optional): Initial data to populate the frame.
            Can be a Python dictionary, a Polars DataFrame, or a Polars LazyFrame.
            If None, an empty frame is initialized. Defaults to None.
        mode (str | None, optional): The operational mode: "run", "optimize", or "debug".
            - "run": Executes operations eagerly.
            - "optimize": Runs the model without the traced-run diagnostics.
            - "debug": Provides more verbose output.
            Defaults to the global default mode (`get_default_mode`).
        verbose (bool | None, optional): Enables or disables verbose logging.
            Defaults to the global default verbosity (`get_default_verbose`).
        threads (int | None, optional): Number of threads for parallel operations.
            Defaults to a system-dependent value or `_DEFAULT_THREADS`.

    Attributes:
        date (DateFrameAccessor): Accessor for date-related operations.
        excel (ExcelFrameAccessor): Accessor for Excel-like operations.
        finance (FinanceFrameAccessor): Accessor for financial calculations.
        graph (GraphFrameAccessor): Accessor for the model's calculation graph.
        projection (ProjectionFrameAccessor): Accessor for the projection axis.
        columns (list[str]): A list of column names in their current order.

    These five accessor names are reserved: a data column of the same name is
    still reached as `af["date"]`, never as `af.date`. See `__getattr__`.

    Examples:
        **Initialization and Basic Operations**

        >>> from gaspatchio import ActuarialFrame
        >>> data = {
        ...     "policy_id": [1, 1, 2, 2, 3],
        ...     "inception_date": [
        ...         "2020-01-01",
        ...         "2020-01-01",
        ...         "2021-05-10",
        ...         "2021-05-10",
        ...         "2022-02-20",
        ...     ],
        ...     "premium": [100, 150, 200, 50, 300],
        ...     "claims": [0, 50, 10, 0, 120],
        ... }
        >>> af = ActuarialFrame(data)
        >>> af["loss_ratio"] = af["claims"] / af["premium"]
        >>> result = af.collect()
        >>> print(result.head(3))
        shape: (3, 5)
        ┌───────────┬────────────────┬─────────┬────────┬────────────┐
        │ policy_id ┆ inception_date ┆ premium ┆ claims ┆ loss_ratio │
        │ ---       ┆ ---            ┆ ---     ┆ ---    ┆ ---        │
        │ i64       ┆ str            ┆ i64     ┆ i64    ┆ f64        │
        ╞═══════════╪════════════════╪═════════╪════════╪════════════╡
        │ 1         ┆ 2020-01-01     ┆ 100     ┆ 0      ┆ 0.0        │
        │ 1         ┆ 2020-01-01     ┆ 150     ┆ 50     ┆ 0.333333   │
        │ 2         ┆ 2021-05-10     ┆ 200     ┆ 10     ┆ 0.05       │
        └───────────┴────────────────┴─────────┴────────┴────────────┘

        **Using `sum` over a group**

        >>> af = ActuarialFrame(data)
        >>> af["total_premium_per_policy"] = (
        ...     af["premium"].polars_native().sum().polars_native().over("policy_id")
        ... )
        >>> result_with_sum = af.collect()
        >>> print(result_with_sum)
        shape: (5, 5)
        ┌───────────┬────────────────┬─────────┬────────┬──────────────────────────┐
        │ policy_id ┆ inception_date ┆ premium ┆ claims ┆ total_premium_per_policy │
        │ ---       ┆ ---            ┆ ---     ┆ ---    ┆ ---                      │
        │ i64       ┆ str            ┆ i64     ┆ i64    ┆ i64                      │
        ╞═══════════╪════════════════╪═════════╪════════╪══════════════════════════╡
        │ 1         ┆ 2020-01-01     ┆ 100     ┆ 0      ┆ 250                      │
        │ 1         ┆ 2020-01-01     ┆ 150     ┆ 50     ┆ 250                      │
        │ 2         ┆ 2021-05-10     ┆ 200     ┆ 10     ┆ 250                      │
        │ 2         ┆ 2021-05-10     ┆ 50      ┆ 0      ┆ 250                      │
        │ 3         ┆ 2022-02-20     ┆ 300     ┆ 120    ┆ 300                      │
        └───────────┴────────────────┴─────────┴────────┴──────────────────────────┘

        **Using an accessor (e.g., date accessor)**

        Assume 'inception_date' needs to be parsed to a date type first.
        For simplicity, let's imagine it's already a date type for this example.
        (Actual parsing would use `af["inception_date"].str.to_date("%Y-%m-%d")` or similar)

        >>> # If 'inception_date' was a date type:
        >>> # af["inception_year"] = af.date.year("inception_date")
        >>> # af_with_year = af.collect()
        >>> # print(af_with_year.select(["policy_id", "inception_year"]))

    """

    # ADDED: Accessor instance caches
    _date_accessor_instance: DateFrameAccessor | None = None
    _excel_accessor_instance: ExcelFrameAccessor | None = None
    _finance_accessor_instance: FinanceFrameAccessor | None = None
    _projection_accessor_instance: ProjectionFrameAccessor | None = None
    _graph_accessor_instance: GraphFrameAccessor | None = None
    # The plan a write past the doors left, read, under the generation it was
    # read at; see the ``_df`` setter. None until such a write, and set back
    # to None by every door that replaces the plan.
    _plan_reading: tuple[int, PlanReading] | None = None

    def __init__(  # noqa: PLR0913, PLR0915 — one parameter per thing a caller may say about the frame, one statement per field of its record
        self,
        data=None,
        mode=None,
        verbose=None,
        threads=None,
        *,
        continue_from=None,
        retain_superseded: bool = True,
    ) -> None:
        """Initialize the ActuarialFrame with optional data, mode, and configuration.

        ``continue_from`` names the frame these values came out of, and is
        how a DataFrame that genuinely left the model comes back carrying
        what the model already knew about it. Reach for it where the values
        had to leave -- a numpy generator, an enrichment routine that only
        speaks Polars -- and for nothing else: to freeze a setup the frame
        never actually left, :meth:`materialize` is the shorter way to say
        the same thing.

        A column keeps the calculation that made it only where it still
        holds that calculation's values; a column the trip changed, and a
        column the trip added, is recorded as data arriving at the
        boundary. See :meth:`_continue_from_donor` for the whole contract
        and the refusals. Without the keyword, a DataFrame handed here is a
        new model whose columns arrived with the data -- except a column
        holding values a calculation on another frame produced, while that
        frame or the caller of its ``collect()`` still holds them. The new
        frame cannot account for that column, because the calculation
        behind its values did not come with them, and ``af.graph.holes()``
        names it as ``rebuilt``.

        Examples:
            Take the values out to a generator and bring them back:

            >>> import numpy as np
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> af = ActuarialFrame({"sum_assured": [100.0, 200.0]})
            >>> af.q_mort = af.sum_assured * 0.0
            >>> values = af.collect()
            >>> rng = np.random.default_rng(0)
            >>> values = values.with_columns(
            ...     pl.Series("died", rng.binomial(1, 0.5, len(values)))
            ... )
            >>> af = ActuarialFrame(values, continue_from=af)
            >>> af.claims = af.sum_assured * af.died
            >>> af.collect().columns
            ['sum_assured', 'q_mort', 'died', 'claims']

            Leave the keyword off, and the columns the model calculated come
            back as values the new frame cannot account for:

            >>> rebuilt = ActuarialFrame(af.collect())
            >>> [(hole.column, hole.reason) for hole in rebuilt.graph.holes()]
            [('q_mort', 'rebuilt'), ('claims', 'rebuilt')]

        ``retain_superseded`` says whether a column written twice keeps the
        output of the definition that was written over, so that an export can
        say what the column held before the override. On by default, because
        "what was this before?" is a question a reviewer asks and the graph
        already names the version it would otherwise be unable to show.

        **This is the memory lever, and it is the only one.** Off, nothing is
        aliased into the plan, nothing extra is collected and nothing is held
        on the frame afterwards -- the cost is not paid rather than paid and
        discarded. Retention was measured at 42.9 MB per retained list
        column at 100,000 policies, and +616 MB of peak for ten of them; a
        model that writes no column twice pays
        nothing either way, which is nearly every model::

            af = ActuarialFrame(model_points, retain_superseded=False)

        The export surface has a switch of the same name
        (``GraphExporter.export``) and it is a different question: **this one
        governs memory, that one governs the document.** Off here, superseded
        definitions are written as history with no values and no ``retained``
        whatever the exporter is asked for, because there is nothing to
        write. On here and off there, the values exist and the export
        declines them -- and releases them. On in both, the superseded
        definition carries its own number and declares that it was retained.

        The setting travels where a frame is carried one step further on: a
        cross-joined scenario axis keeps it. It does not travel through a
        round trip out of the model and back -- ``ActuarialFrame(values,
        continue_from=af)`` -- because the values that came back were
        collected without it and there is nothing to carry; say it again on
        the way in if the frame that leaves had it off.

        **Two column-name prefixes belong to the frame.** ``__rollforward_``
        and ``__gaspatchio_retained__`` name the working columns it keeps in
        its plan -- a compiled rollforward's result, and the values of a
        definition a later assignment replaced -- and every result leaves
        them out. So a column of the data under either prefix is refused
        here, as one is at an assignment, a rename or a join: rename it
        before the frame is built.

        """
        self.__df: pl.LazyFrame | None = None
        self._column_order: list[str] = []
        # Maintain a fast set of attribute-eligible column names
        self._attr_columns_set: set[str] = set()
        self._schema: dict[str, pl.DataType] | None = None
        self._schema_generation: int = 0

        self._mode = mode if mode is not None else get_default_mode()
        self._verbose = verbose if verbose is not None else get_default_verbose()
        # Placeholder for threads, actual configuration might happen elsewhere or be removed
        self._threads = threads if threads is not None else _DEFAULT_THREADS

        # True once this frame has been through a traced run — the model
        # function ran under `--mode debug`, via the trace decorator, which
        # is the one place this is set. It selects the verbose diagnosis
        # panel on the error path, and it is sticky by design: the model
        # function has returned long before collect() fails.
        self._traced_run: bool = False

        # Projection metadata — populated by af.projection.set(...)
        self._projection: object | None = None

        # Excluded context, _operation_log
        self._show_query_plan = False  # Keep this simple flag

        if continue_from is not None:
            _check_continuable(data, continue_from)
        # In a batch runner that cut the book into more than one batch, a
        # frame the model builds over values that left the frame is judged
        # against the batch it was handed (``frame/_across_rows.py``). The
        # runner's own frame over the batch is the batch, and is not.
        if not _OVER_THE_BOOK.get():
            refuse_values_from_outside_the_batch(
                data, continue_from=continue_from is not None
            )

        # Every integer an i64 holds is read as Int64 where it arrives, so
        # the run computes in the width its record states (see
        # `with_integers_as_i64`): a narrow one widened, and a UInt64 or
        # 128-bit one where its values are in hand and every one fits. `data`
        # itself is left as handed over: the checks below that read it ask
        # about the caller's own values.
        # Whether the book's wide integer columns were judged on their
        # values where the frame was built. A DataFrame's were; a LazyFrame's
        # are judged when it is collected (`_book_columns_judged`), unless a
        # batched runner judged them over the whole book first.
        self._wide_judged: bool = (
            not isinstance(data, pl.LazyFrame) or _JUDGED_OVER_THE_BOOK.get()
        )
        if isinstance(data, pl.LazyFrame):
            self._set_plan(with_integers_as_i64(data))
            self._schema = self._df.collect_schema()
            self._column_order = list(self._schema.keys())
            self._refresh_attr_columns_set()
        elif isinstance(data, pl.DataFrame):
            self._set_plan(with_integers_as_i64(data).lazy())
            self._schema = self._df.collect_schema()
            self._column_order = list(self._schema.keys())
            self._refresh_attr_columns_set()
        elif isinstance(data, dict):
            self._set_plan(with_integers_as_i64(pl.DataFrame(data)).lazy())
            self._schema = self._df.collect_schema()
            self._column_order = list(self._schema.keys())
            self._refresh_attr_columns_set()
        elif data is not None:
            msg = "Data must be a Polars DataFrame, LazyFrame, or dictionary"
            raise TypeError(msg)
        # A column under one of the frame's own working prefixes would be
        # taken off every result by that prefix, so it is refused as it
        # arrives rather than lost at collect().
        _refuse_reserved_column_names(self._column_order, door="arrival")

        # --- The durable calculation log ---------------------------------
        # Append-only and permanent: every column this frame computes leaves
        # one record here, and nothing ever removes one. Initialised AFTER
        # the data branches above so `_initial_columns` can name the columns
        # the frame actually arrived with — the ones that are inputs rather
        # than calculations, and so have no record of their own.
        #
        # MEMORY CONTRACT. Nothing evicts from this list, and that is the
        # design rather than an oversight: the log IS the model's history,
        # and a model that ran successfully is exactly the one someone will
        # ask questions about afterwards (audit by default). What it costs
        # is bounded by how many times the model ASSIGNS, not by how many
        # policies it runs — a 12-column model over one policy and the same
        # model over ten million both hold the same handful of records.
        # Each record pins a lowered `pl.Expr` (a plan fragment, not data)
        # and a `SourceSpan` (three strings and two ints), and both live
        # exactly as long as the frame does. Long-lived frames in notebooks
        # and scenario loops therefore grow with the number of assignments
        # they have seen, which is the honest price of being able to answer
        # "how was this calculated?" at any point. What DOES bound the cost
        # of a failure is `_window_start`: the attribution window narrows on
        # every structural reset and every successful collect, so replay
        # only ever re-applies the tail. A structural reset keeps the window
        # it narrowed past rather than discarding it, in `_sealed_windows`,
        # and that list is bounded in its own right — see
        # `_seal_attribution_window`, which lives in
        # `gaspatchio.frame.calculation_log` with the rest of the log, and
        # so does the `_MAX_SEALED_WINDOWS` it reads. Each window it keeps
        # pins one more baseline plan, so a frame that has not yet
        # collected successfully can hold `_MAX_SEALED_WINDOWS` of them at
        # once; the first successful collect drops every one.
        self._calculations: list[LogEntry] = []
        # column name -> how many times it has been assigned so far.
        self._calculation_counts: dict[str, int] = {}
        # The id the next operation will be minted with. One operation is one
        # assignment call, however many columns it defines.
        self._next_operation_id: int = 0
        # Index into `_calculations` where the current attribution window
        # begins. Advancing this is how a structural reset or a successful
        # collect narrows attribution WITHOUT shortening the log.
        self._window_start: int = 0
        # The plan the current window replays from: snapshotted once, when
        # the window's first record is about to land.
        self._baseline_df: pl.LazyFrame | None = None
        # The windows structural operations have closed, oldest first, each
        # holding its own records and its own baseline. A closed window is
        # still replayable against the plan it opened over (see
        # `SealedWindow`); keeping it is what lets a failure that survives a
        # filter still name the column that caused it.
        self._sealed_windows: list[SealedWindow] = []
        # Every step that chose which rows the model values -- a filter, a
        # semi or an anti join -- in the order the model took them. None
        # defines a column, so none is a calculation; each still enters the
        # record, its fingerprints, the book's columns and every replay
        # (see ``SelectionRecord``). Carried with the log, entry for entry.
        self._selections: list[SelectionRecord] = []
        # What arrived: the columns, their names and types, and the data --
        # after the refusal above, because a frame that is not built has
        # nothing to say about its columns.
        self._note_what_arrived(data, continue_from=continue_from)
        # What the last collect handed back, held only while it is still
        # this frame's answer. See :meth:`collect` for the whole contract:
        # `_set_plan` drops it the moment the plan moves, so a
        # non-null here means "these values are what this log accounts
        # for", which is the one claim `continue_from=` is allowed to
        # verify a column against.
        self._collected_values: pl.DataFrame | None = None
        self._last_run: RunSummary | None = None
        # The output of each definition a later write replaced, carried
        # through the last collect under the hidden names of
        # :func:`_retained_column_name` and set aside off the frame that
        # collect handed back. Held on the same terms as the collected
        # values above and dropped by the same setter, because they are the
        # same claim: these are what this log accounts for. Null on every
        # model that never writes a column twice, which is most of them.
        self._retained_values: pl.DataFrame | None = None
        # The frame the last collect handed back, held weakly. It is what
        # ties the values above to a set of rows: an export is given a frame
        # by its caller, and the only honest answer to "are these the rows
        # that history came from?" is that it is the very object this frame
        # produced. Weak, because holding it would keep the caller's values
        # alive past their use and defeat the copy above; and if the caller
        # has let it go, so has the tie, which declines retention rather
        # than guessing.
        self._retained_for: ReferenceType[pl.DataFrame] | None = None
        # The hidden names this frame's plan carries a superseded definition
        # under, recorded as they are minted so that nothing has to resolve
        # a schema to find out whether there are any.
        self._retained_columns: set[str] = set()
        # Whether this frame carries a replaced definition's output at all.
        # Read at the assignment door, which is the only place the cost can
        # be declined rather than merely unspent later.
        self._retain_superseded: bool = retain_superseded
        # Where in the calculation log each compiled rollforward's struct was
        # last put on the plan. A state's increments and captures are read
        # from that struct, and they belong to the column only while it is
        # the run the column came from: put on before the column was
        # defined, and not dropped since. A struct dropped and put on again
        # is a later run, over whatever its inputs are by then.
        self._rollforward_runs: dict[str, int] = {}
        self._start_rollforward_reads()

        # Last, because it overwrites every field above that says what this
        # frame knows about itself: a continued frame's history is the
        # donor's history plus this step, not a fresh model that happens to
        # hold the same columns.
        if continue_from is not None:
            self._continue_from_donor(
                continue_from,
                held=data if isinstance(data, pl.DataFrame) else self._df.collect(),
            )

    def _note_what_arrived(
        self, data: object, *, continue_from: ActuarialFrame | None
    ) -> None:
        """Record what this constructor was handed: columns, names, types and data.

        Taken once, before anything is calculated, because each is the
        frame's account of the data the model is built over and every later
        step reads that account rather than the frame's current shape.
        """
        # Columns whose values a calculation on another frame produced,
        # arriving as if the data had supplied them. Looked for only in a
        # DataFrame -- the one thing that can hold another frame's collected
        # values -- and not on the way back through continue_from=, which
        # carries their calculations across itself. Taken off the arriving
        # set below, so the calculation graph reports each as a hole rather
        # than as a field of the data.
        self._rebuilt: dict[str, Origin] = (
            _calculated_elsewhere(data)
            if isinstance(data, pl.DataFrame) and continue_from is None
            else {}
        )
        # Less the columns another frame calculated: they arrived, and they
        # are not the data's, so the frame vouches for them as neither.
        self._initial_columns: frozenset[str] = frozenset(
            self._schema or ()
        ) - frozenset(self._rebuilt)
        # The same columns, under the names they arrived with. The two sets
        # start out equal and part company the moment a name moves:
        # `_initial_columns` follows a rename and shrinks with a drop, so the
        # frame can always tell an arriving column from one written later
        # under a name it no longer holds. This one never moves, so a model
        # that renamed its vendor columns on the way in can still say which
        # field of the source data each of its inputs was.
        self._arrival_names: frozenset[str] = self._initial_columns
        # The names handed to THIS constructor with no donor behind them,
        # which is narrower than either set above and is the one an export
        # needs in order to tell a rebuild from a derivation.
        # `_arrival_names` grows at every step that widens the frame -- a
        # cross-joined scenario axis, a projection timeline -- because
        # those arrivals are steps the log saw and can vouch for. This set
        # never does: the carry hands the donor's copy straight on, so on
        # an ordinary model it still names the columns of the data the run
        # was started over. A frame built by `ActuarialFrame(mp)` half way
        # through a model overwrites it with whatever that DataFrame held,
        # and that difference is the whole evidence that the setup step
        # rebuilt the frame and left the log behind. Every name handed over,
        # the columns another frame calculated among them, since this says
        # what the constructor was given.
        self._bare_arrivals: frozenset[str] = frozenset(self._schema or ())
        # And the types those same columns arrived with, taken at the same
        # moment and carried wherever the names above are carried. It never
        # moves either, for the reason they do not: a column the model
        # renamed away is gone from every later schema, so the type it
        # arrived under is a thing only this record still knows. Without it
        # the graph's leaf for a vendor field a model renamed can name the
        # field and not say what it held, which is a producer writing
        # `unknown` for a type it did meet.
        self._arrival_schema: dict[str, pl.DataType] = dict(self._schema or {})
        # And the data itself, as this constructor was handed it: the book
        # the model is built over. Held as the plan it arrived as, which is
        # the data the frame's own plan reads until a freeze or a return
        # through `continue_from=` replaces that plan; from then on, holding
        # it is what keeps the book the model started from. An export takes
        # a content digest of the columns the model reads out of it, which is
        # what lets two artifacts say whether they were built over the same
        # book without anybody passing the file in.
        self._arrival_data: pl.LazyFrame | None = self._df
        # The columns of the book a batch runner or a scenario plan was
        # handed, where this frame was built while one ran the model; None
        # where nobody watched the run begin. The record reads them as
        # ``gspio calc-graph`` hands them over, so a name this frame arrived
        # holding that the book never had is a hole, whichever door wrote the
        # record. Carried with the arrivals, through every step after.
        self._book_columns: frozenset[str] | None = book_of_the_run()

    def _continue_from_donor(
        self, donor: ActuarialFrame, *, held: pl.DataFrame
    ) -> None:
        """Take up ``donor``'s history for the values this frame was handed.

        The frame left, something outside it worked on the values, and this
        is the way back in. What crosses is the donor's calculation log, its
        arriving set, and its projection axis; between the two halves sits
        one materialization boundary, because a value that left as a recipe
        came back as a number.

        **A column inherits the donor's lineage only if it still holds the
        donor's values.** Every column the donor's last collect also produced
        is compared against it, value for value and dtype for dtype; the ones
        that match carry on saying what made them, and every other column --
        one the trip changed, one the trip added -- is recorded here as data
        arriving from outside, stamped with a hash of its values and located
        at the statement that brought it back. Nothing is matched by name
        alone: a node claiming a formula that no longer produces the number
        under it is a worse failure than the amnesia this door exists to fix.

        **The comparison reads the rows in the order they arrive, so a frame
        sorted or filtered outside comes back as data.** Every column whose
        values the reorder moved arrives as data, which is every column but
        one a permutation cannot change: a flat loading, a level rate, an
        all-true indicator compares equal after a whole-row reorder and
        keeps its definition, exactly as the rule above says it does. The
        loss on the rest is deliberate: from here a reorder and a rewrite
        are one observation -- two tables of numbers and no account of what
        happened between them -- and the carry states less rather than
        guessing which of the two it met.

        **The comparison is against the values the donor produced, never
        against a re-run of its plan.** Re-running looks equivalent and is
        not: a Phase-1 left join is free to hand back the same rows in a
        different order, so a second execution of a setup that changed
        nothing disagrees with the first on every row of every column. That
        would report a whole model as arriving data -- the amnesia this door
        exists to fix, arrived at the long way round -- and pay a content
        stamp per column for the privilege.

        Args:
            donor: The frame these values came out of.
            held: Those values, in hand. The frame's own plan is a scan over
                them either way; taking them as an argument is what keeps
                the ordinary case (a DataFrame handed straight in) free of a
                second pass over the data.

        Raises:
            ValueError: If this frame shares no column name with what the
                donor collected, which is a stranger rather than a return.

        """
        accounted_for = donor._collected_values  # the donor's own values
        assert accounted_for is not None  # noqa: S101 -- _check_continuable ran first

        shared = [
            column for column in self._column_order if column in accounted_for.columns
        ]
        if not shared:
            msg = (
                f"Cannot continue from that frame: none of the columns you are "
                f"handing back ({', '.join(self._column_order) or 'none'}) is a "
                f"column it collected ({', '.join(accounted_for.columns) or 'none'}). "
                "continue_from= carries the calculations behind values that left "
                "this model and are coming back to it; for data from somewhere "
                "else, build a new ActuarialFrame(df)."
            )
            raise ValueError(msg)

        inherited = {
            column
            for column in shared
            if held[column].equals(accounted_for[column], check_dtypes=True)
        }
        arrivals: dict[str, tuple[OpNode, pl.Expr]] = {
            column: (_assignment_node(held[column], column=column), pl.col(column))
            for column in self._column_order
            if column not in inherited
        }

        donor._carry_calculation_log(
            self,
            MintedColumns(origin="continuation", columns=arrivals)
            if arrivals
            else None,
            boundary=BoundaryRecord(
                kind="materialization",
                # Restated by the carry; see its docstring.
                position=0,
                source=capture_source_span(),
            ),
        )
        # The projection axis is part of what the frame knew, and a timeline
        # does not stop being this model's timeline because its values spent
        # a step in Polars. Carried after the log, alongside it.
        self._projection = donor._projection
        self._advance_window_cursor()

    @property
    def _df(self) -> pl.LazyFrame | None:
        """The underlying Polars LazyFrame."""
        return self.__df

    @_df.setter
    def _df(self, new_df: pl.LazyFrame | None) -> None:
        """Take a plan written straight onto the frame, and log what it overwrote.

        Every door the frame offers sets its plan through :meth:`_set_plan`
        and logs what it set. This setter is the route left to a model that
        assigns ``af._df`` itself -- a Polars chain, ``af.pipe(f)`` -- and a
        write that way logs nothing of its own. Where it defines a column the
        frame had accounted for, a calculation it logged or a column the data
        arrived with, the frame's account of that column stops being true.
        So the write is read before the plan is taken
        (:func:`~gaspatchio.frame.plan_writes.read_plan_write`), and each such
        column is logged as overwritten at the line that wrote it, which the
        calculation graph reports as a hole. A column the write adds under a
        new name overwrites nothing: nothing accounts for it, and the graph
        reports it as unrecorded, as it always has.

        Reading the write never fails it. A plan the reader cannot read is
        logged as overwriting every column the frame accounted for that the
        plan still holds, rather than none; a plan that does not resolve is
        taken as it always was, for ``collect()`` to refuse.

        Reading a plan costs in proportion to its length, so the reading of
        the plan a write leaves is kept, and the next write straight after
        it starts from that reading rather than reading the plan again. Any
        other door that sets the plan lets it go. Each write still reads
        the plan it leaves -- about 12 ms on the level-4 tutorial model,
        since Polars converts the whole plan whenever it is asked about any
        of it -- so a loop of writes costs more with every turn. Writing
        many columns in one ``with_columns`` is one write. No door of the
        frame comes here: assignment, ``select``, ``with_columns`` and the
        accessors set the plan through :meth:`_set_plan` and read nothing.
        """
        before = self.__df
        accounted = (
            frozenset()
            if before is None or new_df is None or new_df is before
            else self._accounted_columns()
        )
        if not accounted or new_df is None:
            self._set_plan(new_df)
            return
        kept = self._plan_reading
        written = read_plan_write(
            before,
            new_df,
            before_reading=(
                kept[1]
                if kept is not None and kept[0] == self._schema_generation
                else None
            ),
        )
        overwritten = written.overwritten(accounted)
        self._set_plan(new_df)
        if written.reading is not None:
            object.__setattr__(
                self, "_plan_reading", (self._schema_generation, written.reading)
            )
        if written.schema is not None:
            # Read in the same pass, so the schema the plan now holds is not
            # resolved a second time on the next read.
            self._schema = dict(written.schema)
        if overwritten:
            # In the order the plan holds them, so the log reads as the frame
            # does; by name where the plan's order could not be read.
            order = {name: index for index, name in enumerate(written.schema or ())}
            self._record_overwrites(
                sorted(
                    overwritten, key=lambda name: (order.get(name, len(order)), name)
                ),
                readable=written.readable,
                schema=written.schema,
                rescanned=written.rescanned,
            )

    def _set_plan(self, new_df: pl.LazyFrame | None) -> None:
        """Replace _df, refresh the cached schema, bump the generation counter.

        Every door of the frame sets its plan here, and logs what it set; the
        ``_df`` setter is the route left to a write that logs nothing, and it
        sets the plan here too once it has read what the write overwrote.
        Nothing else writes the plan's storage -- a test bounds the direct
        writes to ``__df`` to this method and ``__init__``.

        If the new plan is invalid (e.g. references a nonexistent column),
        ``collect_schema`` will raise.  We swallow that exception and leave
        ``_schema`` at its last known-good value, preserving Polars' lazy-
        evaluation contract: invalid plans only become hard errors at
        ``.collect()`` time.  The generation counter is still bumped so that
        any reader knows the plan has changed.

        The last collect's values are dropped here, and this is the one
        place they are. They are kept only as an answer to "what does this
        frame's log account for?", and a plan that has moved is a log that
        accounts for something else — so the reference goes the moment the
        plan does, both to keep the claim true and to bound what a frame
        holds on to. The superseded definitions that collect set aside go
        with them, and for the same reason: they are the same answer to the
        same question, one step further back. ``object.__setattr__`` because
        this runs during ``__init__``, before the attribute exists.
        """
        object.__setattr__(self, "_collected_values", None)
        object.__setattr__(self, "_last_run", None)
        object.__setattr__(self, "_retained_values", None)
        object.__setattr__(self, "_retained_for", None)
        # The reading of the plan a write past the doors left, kept for the
        # next such write to start from. It is a reading of this plan only.
        object.__setattr__(self, "_plan_reading", None)
        self.__df = new_df
        if new_df is None:
            self._schema = None
        else:
            # Defer schema resolution. Resolving the whole (growing) plan on
            # every assignment is ~0.8ms/call on a real model plan and dominates
            # plan-build time. The lazy ``_schema`` property resolves on demand;
            # ``__setitem__`` updates the cache incrementally (cheap minimal
            # probe) so the deep resolve almost never fires on the hot path.
            object.__setattr__(self, "_schema_dirty", True)
        self._schema_generation += 1

    @property
    def _schema(self) -> dict[str, pl.DataType] | None:
        """Lazily-resolved, cached schema (deferred from :meth:`_set_plan`).

        A plan Polars cannot resolve keeps the last schema that did resolve,
        as :meth:`_set_plan` states: an invalid plan is an error at
        ``.collect()``, not here. What Polars said is logged at debug level.
        """
        d = object.__getattribute__(self, "__dict__")
        if d.get("_schema_dirty", False):
            df = self._df
            if df is not None:
                try:
                    object.__setattr__(self, "_schema_value", dict(df.collect_schema()))
                    object.__setattr__(self, "_schema_unresolved", False)
                except pl.exceptions.PolarsError as unresolved:
                    logger.debug(
                        f"The plan's schema does not resolve yet ({unresolved!r}); "
                        "the last schema that did is kept, and each assignment "
                        "types its own column into it, until it does."
                    )
                    object.__setattr__(self, "_schema_unresolved", True)
            object.__setattr__(self, "_schema_dirty", False)
        return d.get("_schema_value")

    @_schema.setter
    def _schema(self, value: dict[str, pl.DataType] | None) -> None:
        object.__setattr__(
            self, "_schema_value", dict(value) if value is not None else None
        )
        object.__setattr__(self, "_schema_dirty", False)
        object.__setattr__(self, "_schema_unresolved", False)

    def _refuse_a_door_past_a_break(self, door: str) -> None:
        """Raise an earlier line's break before a door that resolves the plan runs.

        ``projection.set``, ``select``, ``rename`` and ``drop`` resolve the
        whole plan's schema at their own line, so a fragment Polars could not
        type, written lines earlier, failed there -- in Polars' words, at a
        healthy line, naming no line at all. Where the plan already does not
        resolve before the door, the break is raised here instead, through the
        frame's error handler as a ``collect()`` raises it, naming the line
        that broke; the door adds nothing to the plan. A plan that resolves is
        left to the door, so an error the door's own expressions raise is
        still the door's. ``with_columns`` puts its batch in the plan first and
        records it, as its error path always has, and adds the same note.
        """
        if self._df is None or not self._schema_does_not_resolve():
            return
        try:
            self._df.collect_schema()
        except Exception as error:
            error.add_note(_NOT_RUN.format(door=door))
            _handle_execution_error(self, error)
            raise

    def _schema_does_not_resolve(self) -> bool:
        """Say whether the plan's schema failed to resolve the last time it was asked.

        A line Polars cannot type -- an engine fragment multiplying text by a
        number, a column that does not exist -- stays in the plan, so the whole
        plan stops resolving and the cached schema is the one from before that
        line. Every column written after it would then be read at its old type:
        a column recast to a number still read as text, a healthy line refused
        as text times a number. While that holds, each assignment types its
        own column against the cached schema and writes the answer in (as a
        frame of many columns always does), and a column it cannot type leaves
        the cache rather than standing there at a type the plan no longer
        holds. Asking resolves a plan that is waiting to be.
        """
        _ = self._schema
        return bool(
            object.__getattribute__(self, "__dict__").get("_schema_unresolved", False)
        )

    # Excluded accessor properties (.date, .finance)

    def __getitem__(self, key: str) -> ColumnProxy:
        """Allow df['column'] access, returning a ColumnProxy."""
        if isinstance(key, str):
            # Basic proxy creation, no strict checking here for now
            return ColumnProxy(key, self)
        msg = f"ActuarialFrame indices must be strings, not {type(key).__name__}"
        raise TypeError(msg)

    def __setitem__(self, key: str, value: Any) -> None:  # noqa: ANN401
        """Handle column assignment using df['column'] = value."""
        # Before anything moves, so a refused name leaves nothing to roll back.
        _refuse_reserved_column_names((key,), door="assignment")
        value = _injection_as_it_enters(value)
        # Registered up front because everything below reads the column
        # order (the incremental-schema gate counts it), and rolled back if
        # the assignment is refused: a column the frame never computed must
        # not survive in `columns` as a name that resolves to a proxy and
        # then disagrees with the collected frame's shape.
        column_is_new = key not in self._column_order
        # Which definition of `key` this statement is about to replace, or 0
        # where it replaces nothing. Read before the column order moves
        # below, because the test is whether the frame still HOLDS the
        # column: a name that was dropped and is being written again has a
        # record behind it and no column in the plan to carry forward.
        superseded = 0 if column_is_new else self._calculation_counts.get(key, 0)
        if column_is_new:
            self._column_order.append(key)
            self._refresh_attr_columns_set()
        try:
            self._refuse_a_row_operation_over_periods(value)
            expr = self._convert_to_expr(value)
            # Derived BEFORE the plan is mutated: a value the op-tree refuses
            # (a NaN literal — see ir.Lit) must not leave the live plan
            # already carrying a column the log has no record of.
            node = _assignment_node(value, column=key)
            # A column of values handed over wholesale lands on the rows by
            # position, so it is refused where the rows are not the ones it
            # was written for -- after the values themselves are accepted.
            refuse_an_injection_the_rows_cannot_take(self, value)

            # Incremental schema maintenance only pays off once the plan is deep
            # enough that the deferred deep resolve is expensive. On shallow
            # plans skip it entirely — leave the schema dirty for the lazy getter
            # (cheap to resolve when shallow) — so trivial frames keep their
            # original cost (e.g. a freshly-built chained when() over one column).
            do_incremental = (
                len(self._column_order) >= _INCREMENTAL_SCHEMA_MIN_COLS
                or self._schema_does_not_resolve()
            )

            # Resolve the new column's dtype cheaply against the CURRENT (clean)
            # schema BEFORE mutating _df, so we can extend the schema cache
            # incrementally rather than forcing a deep collect_schema in the
            # setter (~0.8ms/call on a real plan -> the plan-build bottleneck).
            new_dtype = self._resolve_assigned_dtype(expr) if do_incremental else None

            # The log is RECORD-ONLY metadata (calc-graph display, query-plan
            # logging, collect-error attribution). Every operation is applied
            # to _df exactly once here; collect()/profile() must never replay
            # the log on top of it — that would double-apply self-referential
            # assignments.
            self._open_attribution_window_if_needed()
            held = self._retained_alias_name(key, superseded)
            aliases = () if held is None else (pl.col(key).alias(held),)
            self._set_plan(self._df.with_columns(*aliases, expr.alias(key)))
            if held is not None:
                # Recorded after the plan took it, so that nothing downstream
                # goes looking for a column a refused assignment never wrote.
                self._retained_columns.add(held)
            # The durable record, minted in every mode: the log is what the
            # model is auditable FROM, not a debugging aid that a mode flag
            # switches off. Appended AFTER the successful apply, so a
            # rejected expression leaves no record the live plan never
            # received.
            self._record_calculation(
                key,
                node=node,
                expr=expr,
                dtype=new_dtype,
                operation_id=self._mint_operation_id(),
                origin="assignment",
                source=capture_source_span(),
            )

            # Incremental schema maintenance (clears the dirty flag the _df
            # setter just set). If skipped or the dtype could not be resolved
            # cheaply, the flag stays set and the lazy _schema getter resolves it
            # on demand.
            if do_incremental:
                self._apply_incremental_schema(key, new_dtype, carried=held)

            # Basic logging if needed, removed verbose _operation_log
            # if self._verbose: print(f"Set column '{key}'")  # noqa: ERA001
        except Exception as e:
            if column_is_new:
                self._column_order.remove(key)
                self._refresh_attr_columns_set()
            # AF_ERROR_MODE wins: under `off` the original exception reaches
            # the user unwrapped. The rollback above still runs -- that is
            # bookkeeping the frame owes itself, not error handling.
            if get_error_mode() == "off":
                raise
            # Use basic error re-raising, detailed handling is in _handle_execution_error.
            # The inner message is a sentence of its own, and most already
            # end in a full stop, so it is closed once rather than twice.
            inner = str(e).rstrip().removesuffix(".")
            msg = (
                f"Error setting column '{key}': {inner}. "
                f"Value type: {type(value).__name__}"
            )
            raise type(e)(msg) from e
        # No return self needed for __setitem__

    def _retained_alias_name(self, key: str, superseded: int) -> str | None:
        """Return the hidden name to carry a superseded definition's output under.

        A reassignment writes over the column, so the definition it replaces
        stops existing anywhere the moment this statement lands -- the graph
        keeps its node and its formula, and the values that node computed are
        gone. Aliasing the column here keeps them, and it is deliberately in
        the SAME ``with_columns`` as the overwrite: every expression in one
        call resolves against the frame as it stood before the call, so the
        alias holds what the superseded definition produced rather than what
        replaced it. That is the whole point -- a value read off the finished
        frame for a superseded definition would be the successor's number
        under the predecessor's formula.

        Nothing records it. It mints no calculation, no node and no entry in
        ``columns``; ``collect()`` takes it off the frame it hands back, and
        the calculation log's unaccounted-column reading ignores the prefix,
        so a model's own account of itself is exactly what it was.

        The cost is one column of the collected frame per superseded
        definition -- real memory, paid only by a model that writes a column
        twice -- and an export names it before it writes the values. None
        where nothing is being replaced, which is nearly every assignment
        every model makes; None where the frame was built with
        ``retain_superseded=False``, which is where that cost is declined
        rather than paid and thrown away; and None where the model already
        holds a column of that name rather than writing over somebody else's
        values.
        """
        if superseded < 1 or not self._retain_superseded:
            return None
        held = _retained_column_name(key, superseded)
        if held in self._column_order:
            logger.debug(
                f"Not retaining {key}@{superseded}: the frame already holds a "
                f"column called {held!r}."
            )
            return None
        return held

    def _resolve_assigned_dtype(self, expr: pl.Expr) -> pl.DataType | None:
        """Cheaply resolve the output dtype of an assigned expression.

        Uses the minimal-root-column probe (resolves against only the columns
        the expr references, ~20us) rather than a full-plan ``collect_schema``.
        Returns ``None`` if it can't be resolved cheaply, in which case the
        caller leaves the schema dirty for a later lazy resolve.
        """
        try:
            return _resolve_expr_output_dtype(self, expr)
        except Exception:  # noqa: BLE001
            return None

    def _apply_incremental_schema(
        self, key: str, new_dtype: pl.DataType | None, *, carried: str | None = None
    ) -> None:
        """Extend the cached schema with one resolved column, marking it clean.

        Bypasses the lazy getter (reads the raw cached dict) so it does not
        trigger a deep resolve of the plan we just appended to.

        ``carried`` is the hidden name the same statement aliased the
        replaced definition under, if it did. It is in the plan beside
        ``key``, holding the type that definition had, and a cache without it
        would tell a later join or select that the column was new.
        """
        if new_dtype is None:
            state = object.__getattribute__(self, "__dict__")
            if state.get("_schema_unresolved", False):
                # No deep resolve will answer for this column either: it is
                # unknown, which is what a reader is told, never its old type.
                held = state.get("_schema_value")
                if held is not None and key in held:
                    unknown = dict(held)
                    del unknown[key]
                    object.__setattr__(self, "_schema_value", unknown)
            return  # _schema_dirty stays True -> lazy getter resolves on demand
        cur = object.__getattribute__(self, "__dict__").get("_schema_value")
        new_schema = dict(cur) if cur is not None else {}
        if carried is not None:
            replaced = new_schema.get(key)
            if replaced is None:
                return  # the replaced type is unknown; resolve on demand
            new_schema[carried] = replaced
        new_schema[key] = new_dtype
        object.__setattr__(self, "_schema_value", new_schema)
        object.__setattr__(self, "_schema_dirty", False)

    def _start_rollforward_reads(self) -> None:
        """Start the frame's account of how its rollforward runs are read."""
        # The rollforward reads a state's increments or captures handed out,
        # by the identity of their nodes, each with the struct it reads. The
        # accessor has checked the run is the state's own, so an assignment
        # whose every read of a struct is one of these answers from that run
        # however it was written around: arithmetic, when/then/otherwise and
        # the accessor methods all take an operand's node as it is. Held
        # here, beside the node, so an id is never reused while it is a key.
        self._held_reads: dict[int, tuple[OpNode, str]] = {}
        # How far the log has been read for each run's first read and for an
        # input written after it, and the columns each record reads, so that
        # a read of a run looks only at what the log gained since the last.
        self._rollforward_scans: dict[str, _RunScan] = {}
        self._record_roots: dict[int, tuple[CalculationRecord, frozenset[str]]] = {}

    def _refuse_a_row_operation_over_periods(self, value: object) -> None:
        """Refuse a plain Polars row operation over a per-period column.

        On a frame with a projection timeline the rows are policies, so a
        ``shift``, ``cum_sum`` or fill written straight in Polars over a
        per-period column moves values between policies. A framework proxy
        and a producer's ``ProxyAwareExpr`` were built through the
        vocabulary, whose own doors decide this, and ``polars_native()`` is
        the escape an author opens on purpose; only a plain expression is
        read, and a plain fragment an author used as an operand inside a
        framework formula, which the operand door marked as raw. See
        ``frame/_row_operations.py``.
        """
        if isinstance(value, pl.Expr) and not isinstance(value, ProxyAwareExpr):
            refuse_a_row_operation_over_periods(self, value)
        else:
            node = getattr(value, "_node", None)
            if node is not None:
                refuse_a_raw_fragment_over_periods(self, node)
        # A read across rows is the book's figure only where the frame is the
        # book: a batch runner's batch, or a scenario axis, is not. See
        # ``frame/_across_rows.py``.
        refuse_a_read_across_rows(self, value)

    def _convert_to_expr(self, value: Any) -> pl.Expr:  # noqa: ANN401
        """Convert a value to a Polars expression."""
        if isinstance(value, ColumnProxy):
            return pl.col(value.name)
        if isinstance(value, ExpressionProxy):
            return self._ensure_rollforward_sources(
                self._lowered_against_this_frame(value),
                node=value._node,  # noqa: SLF001
            )
        named = _the_name_it_was_given(value)
        value = _a_comparison_read_as_one(value, self)
        if named is not None and isinstance(value, ConditionExpression):
            return self._convert_to_expr(value).alias(named)
        if isinstance(value, ConditionExpression):
            # Use _to_boolean_expr() which handles list vs scalar columns properly
            # For list columns, routes to list_conditional Rust plugin
            # For scalar columns, uses native Polars comparison cast to Float64
            if value._parent is None:  # noqa: SLF001
                # Built on no frame: its operands are typed by this one.
                value = ConditionExpression._from_node(value._node, self)  # noqa: SLF001
            return self._ensure_rollforward_sources(
                value._to_boolean_expr(),  # noqa: SLF001
                node=value._node,  # noqa: SLF001
            )
        if isinstance(value, pl.Expr):
            return self._ensure_rollforward_sources(value)
        # A when() chain with no .otherwise() has no value to store.
        refuse_an_unfinished_chain(value)
        # Strings, numpy arrays, and other types become literals; a whole
        # number becomes the Int64 the record names it (literal_expression),
        # and one no Int64 holds is refused as it is in a formula.
        if isinstance(value, numbers.Integral) and not isinstance(value, bool):
            within_i64(int(value))
        return literal_expression(value)

    def _lowered_against_this_frame(self, value: ExpressionProxy) -> pl.Expr:
        """Return a formula's expression, lowered against this frame if it had none.

        A formula built on no frame -- ``ExpressionProxy(expr, parent=None)``
        and what is composed on it -- was lowered blind to its operands'
        shapes and types: a per-period comparison in it reached Polars as a
        native comparison of a list, which Polars refused in its own words
        when the frame ran. Its types are known the moment it is assigned, so
        its tree is lowered here against this frame, the way the same line
        written on the frame's own columns is. A raw Polars expression has no
        tree to lower and is used as handed over.
        """
        node = value._node_cached  # noqa: SLF001
        if value._parent is not None or node is None:  # noqa: SLF001
            return value._expr  # noqa: SLF001
        return lower_polars(node, context_for(self))

    def _ensure_rollforward_sources(
        self, expr: pl.Expr, *, node: OpNode | None = None
    ) -> pl.Expr:
        """Materialise any hidden rollforward struct columns ``expr`` references.

        ``CompiledRollforward.expr_for`` returns ``pl.col("__rollforward_<fp>")
        .struct.field(...)`` — a reference to a struct column that exists only
        once this hook adds it. Materialising here, at the single point every
        expression enters the frame, is what guarantees the rollforward kernel
        runs ONCE no matter how many states or increments are extracted (the
        Polars optimiser stopped deduplicating plugin calls in 1.42, so the
        guarantee must be structural). ``collect()``/``profile()`` already
        strip ``__rollforward_*`` columns from the output.

        Idempotent and cheap: a no-op unless a rollforward has been compiled
        in this process AND the expression references a hidden column missing
        from the schema.

        A read of a rollforward the frame has read before is refused where
        one of its inputs was written again after that first read (see
        ``_refuse_a_run_over_moved_inputs``), except where ``node`` -- the
        op-tree of what is being assigned -- reads the struct only through
        reads a state's ``increments`` or ``captures`` handed out, which
        that accessor has already checked are the run the state came from.
        """
        if not _registry.has_entries() or self._df is None:
            return expr
        try:
            roots = expr.meta.root_names()
        except Exception:  # noqa: BLE001 — meta inspection is best-effort
            return expr
        hidden = [n for n in roots if n.startswith(_registry.HIDDEN_PREFIX)]
        if not hidden:
            return expr
        schema = self._schema
        known = set(schema) if schema is not None else set()
        held = self._structs_read_only_through_held_reads(node)
        for name in hidden:
            if name in known and name in held:
                continue
            self._refuse_a_run_over_moved_inputs(name, _registry.plugin_expr_for(name))
            if name in known:
                continue
            # A book column wider than i64 is read by the run as arithmetic
            # reads one (section 10); a frame holding none runs the kernel as
            # it was compiled.
            read = run_reading_wide_inputs_as_i64(name, schema or {})
            kernel = _registry.plugin_expr_for(name) if read is None else read
            hidden_expr = kernel.alias(name)
            materialise = with_columns_operation("rollforward", hidden_expr)
            # Materialising a hidden column changes the plan without
            # leaving a calculation record, so the current window cannot
            # straddle it: its records would replay against a baseline that
            # no longer matches. The window is sealed here — closed over the
            # plan it opened over, which stays replayable, with the
            # materialisation kept on it — and reopens over the
            # post-materialisation plan below (#39).
            self._seal_attribution_window(materialise)
            self._set_plan(materialise.applied_to(self._df))
            self._rollforward_runs[name] = len(self._calculations)
            self._open_attribution_window_if_needed()
        return expr

    def _structs_read_only_through_held_reads(self, node: OpNode | None) -> set[str]:
        """Return the structs ``node`` reads, if at all, only through held reads.

        A held read is one a state's ``increments`` or ``captures`` handed
        out, recognised by the identity of its node. A struct the tree also
        reaches any other way -- an ``expr_for`` or ``increment_for`` written
        beside it, or Polars text naming the struct -- is left out, so that
        read is judged as any other.
        """
        if node is None or not self._held_reads:
            return set()
        held: set[str] = set()
        other: set[str] = set()
        for part in walk(node):
            if isinstance(part, Call) and part.name.startswith("rollforward."):
                vouched = self._held_reads.get(id(part))
                if vouched is not None and vouched[0] is part:
                    held.add(vouched[1])
                else:
                    attrs = dict(part.attrs)
                    other.add(
                        _registry.hidden_column_name(
                            str(attrs["fingerprint"]), str(attrs["schedule"])
                        )
                    )
            elif isinstance(part, EngineNative):
                other.update(
                    dep for dep in part.deps if dep.startswith(_registry.HIDDEN_PREFIX)
                )
            elif isinstance(part, Col) and part.name.startswith(
                _registry.HIDDEN_PREFIX
            ):
                other.add(part.name)
        return held - other

    def _refuse_a_run_over_moved_inputs(self, name: str, kernel: pl.Expr) -> None:
        """Refuse a read of a rollforward one of whose inputs moved since its first.

        A frame runs a compiled rollforward once, over its inputs as they
        stood where the frame first read it: the calculation graph binds the
        compilation to those inputs there, as one node, and an engine
        evaluates it once. A line written after one of those inputs was
        written again reads as if it used the later values. With the run
        still on the plan it would be answered from the earlier ones; with
        the run gone -- after ``materialize()`` or a select -- a second run
        would answer it from the later ones, a run the graph has no node for
        and an engine would not reproduce. Either answer misleads, so the
        line is refused, naming the input and where each thing happened.

        "Since" means from the start of the call that first read it: a
        ``with_columns`` that writes an input and reads the rollforward in
        one call runs the rollforward over the input as it stood before the
        call, as every expression in one call reads the frame before it. A
        write that is itself a read of this run is not a move: a state
        written over the column its opening balance came from --
        ``af.av = compiled.expr_for("av")`` where ``states={"av": af["av"]}``
        -- holds the run, and no later read expects the run to start again
        from it.

        A write over an input straight into the query plan moves it as an
        assignment does: the frame logs it, and the run on the plan was
        computed over the input as it stood before it.

        ``name`` is the run's hidden column and ``kernel`` the call that
        computes it, whose operands are the inputs.

        Every record after the first read is judged, whatever door wrote it,
        and each is judged once: the log is only appended to, so a read of
        the run carries on from where the last one stopped (see
        ``_RunScan``), and a record's columns are worked out once.
        """
        log = self._calculations
        scan = self._rollforward_scans.get(name)
        if scan is None:
            # A struct this frame's lineage never put on the plan has no read
            # in the log yet: every read puts it on first, and a frame derived
            # from another carries where each struct went on.
            scan = self._rollforward_scans[name] = _RunScan(
                searched=0 if name in self._rollforward_runs else len(log)
            )
        first = scan.first
        if first is None:
            for at in range(scan.searched, len(log)):
                entry = log[at]
                if isinstance(entry, CalculationRecord) and name in self._roots_of(
                    entry
                ):
                    first = scan.first = entry
                    scan.checked = _start_of_operation(log, at)
                    break
            else:
                scan.searched = len(log)
                return
        moved = scan.moved
        if moved is None:
            reads = frozenset(_root_names(kernel))
            for at in range(scan.checked, len(log)):
                entry = log[at]
                if isinstance(entry, OverwriteRecord) and entry.column in reads:
                    moved = scan.moved = entry
                    break
                if (
                    isinstance(entry, CalculationRecord)
                    and entry.column in reads
                    and name not in self._roots_of(entry)
                    and not self._keeps_its_values(entry, at)
                ):
                    moved = scan.moved = entry
                    break
            else:
                scan.checked = len(log)
                return
        raise ValueError(_moved_input_refusal(first, moved))

    def _keeps_its_values(self, record: CalculationRecord, at: int) -> bool:
        """Return whether a rewrite at ``at`` provably leaves its column as it was.

        Three shapes, each plain from how it is written, and nothing that
        would need two formulas compared: the column itself, under any alias
        (``af.fee = af.fee``); the column times the number one where that
        keeps its type (``af.fee = af.fee * 1``), since multiplying by one
        changes no value of any type it keeps; and ``projection.set``
        stamping a column again with the very operation that stamped it last,
        over columns nothing has written in between. Anything else is taken
        to move the column.

        The first two are formulas the model wrote, so they are recognised
        only on an assignment or a ``with_columns``. A column another step
        put on the frame -- a projection's stamp, values handed back through
        ``continue_from=`` -- is recorded as a reference to itself in the
        plan that step built, which says nothing about whether it kept the
        values.
        """
        column = record.column
        written = record.origin in {"assignment", "batch"}
        if written and _is_a_bare_reference_to(record.expr, column):
            return True
        log = self._calculations
        start = _start_of_operation(log, at)
        before = next(
            (
                (position, entry)
                for position in range(start - 1, -1, -1)
                if isinstance(entry := log[position], CalculationRecord)
                and entry.column == column
            ),
            None,
        )
        if written and _is_times_one(record.node, column):
            dtype = (
                before[1].dtype
                if before is not None
                else self._arrival_schema.get(column)
            )
            return (
                dtype is not None and _dtype_from(record.expr, column, dtype) == dtype
            )
        if record.origin != "projection" or before is None:
            return False
        position, last = before
        if last.origin != "projection" or last.node != record.node:
            return False
        read = {part.name for part in walk(record.node) if isinstance(part, Col)}
        return not any(
            isinstance(entry, CalculationRecord) and entry.column in read
            for entry in log[_start_of_operation(log, position) : start]
        )

    def show_query_plan(self, enabled: bool = True) -> ActuarialFrame:  # noqa: FBT001, FBT002
        """Enable or disable query plan logging (basic implementation)."""
        # This only sets the flag. The rendering itself lives in
        # `_log_query_plan_if_requested` below, which reads it alongside
        # `_traced_run` and hands the calculation log to tracing.py.
        self._show_query_plan = enabled  # Keep flag for potential other uses
        logger.info(
            f"Query plan logging {'enabled' if enabled else 'disabled'} (via trace decorator)."
        )  # Basic feedback
        return self

    # ADDED: trace decorator method
    def trace(self, func: Callable) -> Callable:
        """Capture operations within a function call in optimize mode."""
        return build_trace_decorator(self)(func)

    def _log_query_plan_if_requested(self, final_df: pl.LazyFrame) -> None:
        """Render the calculation log as a query plan, when both gates are open.

        Two gates, both of which the user has to have opened deliberately:
        ``show_query_plan()`` asks for the plan at all, and ``_traced_run``
        says this was a ``--mode debug`` run. The second gate is what keeps
        an optimize-mode collect from paying for a plan nobody asked to
        read, which is the same line the retired computation graph drew
        (only its traced records ever reached this logging).
        """
        if not (self._show_query_plan and self._traced_run):
            return
        records = self._calculation_records()
        if not records:
            return
        log_query_plan(records, final_df)

    def collect(
        self,
        *,
        engine: str = "streaming",
    ) -> pl.DataFrame:
        """Execute and materialize the dataframe.

        ``collect`` is the public escape hatch from the lazy ``ActuarialFrame``
        graph to an eager :class:`polars.DataFrame`. Inside a model function
        the lazy form is usually what you want — Polars fuses the expressions
        and avoids intermediate materialisation. Reach for ``collect()`` when
        the calculation genuinely needs eager column arrays, most commonly
        when handing per-policy probabilities to a numpy RNG inside a
        stochastic scenario kernel.

        To freeze the work so far and **carry on modelling**, use
        :meth:`materialize` instead. ``ActuarialFrame(af.collect())`` does
        freeze the values, but the new frame starts empty of everything else
        the model had recorded — the calculation log, the projection axis,
        which columns were inputs. ``materialize()`` keeps all of it and
        hands back the same frame.

        When the values genuinely have to leave — a numpy generator, an
        enrichment routine that only speaks Polars — bring them back with
        ``ActuarialFrame(df, continue_from=af)`` rather than
        ``ActuarialFrame(df)``, and the columns the trip did not touch keep
        the calculations that made them.

        !!! note "What a collect leaves behind"
            The frame keeps a copy of what this call handed back until its
            plan next changes -- and, where the frame holds anything a
            calculation produced, the copy is kept beyond that for as long
            as you hold the DataFrame this call returned. That copy is what
            ``continue_from=`` checks a returning column against, and
            holding it is what makes the check a check: comparing against a
            second execution of the same plan would be comparing against
            rows a join is free to hand back in a different order. It is a
            copy rather than the caller's own object because Polars writes
            in place through that object — ``replace_column``,
            ``insert_column``, ``hstack(in_place=True)`` — and a check
            against values the caller can still edit is a column compared
            with itself rather than a verification. It is also how a frame
            built over these values without ``continue_from=`` tells which of
            its columns a calculation here produced, and names them as
            ``rebuilt`` holes. The copy is a container over the same arrow
            buffers — under two microseconds for fourteen columns of a
            million rows, and no second copy of the values — and it goes
            when the later of its two holders lets go: the frame at its next
            assignment, you when you drop the DataFrame.

        Args:
            engine: A Polars execution strategy or a discovered engine's name:
                - "streaming" (default): Process data in batches, falling back
                  to in-memory for unsupported operations.
                - "in-memory": Classic Polars in-memory execution.
                - "auto": Let Polars choose the engine.
                - "jax": Run the executable artifact with the optional JAX
                  engine. Requires the JAX extra; device selection follows JAX
                  configuration, not this argument.

                The frame's debug/optimize mode controls diagnostics, independently
                of this choice. After collection, ``af.graph.last_run`` reports the
                selected engine, result shape and any successful engine notes.

        Returns:
            Materialized DataFrame with all computations applied.

        Examples:
            Inside a stochastic model on ``for_each_scenario``'s drivers shape,
            seeded at ``batch_size=1`` (a seeded ``ScenarioRun`` hands the
            seed to a frame-only model as the ``rng_seed`` column instead):

            >>> import numpy as np
            >>> import polars as pl
            >>> def my_model(af, *, tables, drivers):
            ...     df = af.collect()  # materialise for numpy RNG access
            ...     rng = np.random.default_rng(drivers["rng_seed"])
            ...     deaths = rng.binomial(1, df["q_mort"].to_numpy())
            ...     return af.with_columns(pl.Series("died", deaths))

        """
        self._last_run = None
        if engine not in _POLARS_ENGINES:
            # Outside the try below, deliberately. A refusal the seam wrote is
            # already in the framework's voice and already names the next
            # move; the handler down there exists to make sense of what an
            # engine said about a plan, and re-dressing one of our own
            # sentences in it would bury the sentence the reader needs.
            return self._collect_on_engine(engine)
        try:
            if self._df is None:
                # Ensure an empty schema matching Polars behavior for empty LazyFrame.collect()
                return self._complete_collection(
                    pl.DataFrame(schema={}), polars_mode=engine
                )

            final_df = self._df
            # The calculation log is record-only: every recorded operation was
            # already applied to _df by the setter. Replaying it here would
            # apply self-referential assignments twice.
            self._log_query_plan_if_requested(final_df)

            # Strip hidden rollforward columns before collecting
            schema_names = final_df.collect_schema().names()
            scratch = _kernel_scratch_prefix()
            rollforward_cols = [c for c in schema_names if c.startswith(scratch)]
            if rollforward_cols:
                final_df = final_df.drop(rollforward_cols)

            result = final_df.collect(engine=engine)
            # No `else:` block, for profile()'s reason: the try wraps the whole
            # body so that a failure anywhere in it is attributed the same way.
            return self._complete_collection(result, polars_mode=engine)
        except Exception as e:  # noqa: BLE001
            _handle_execution_error(self, e)  # Will re-raise or format
        except BaseException as e:  # noqa: BLE001 — pyo3 panics bypass Exception (#54)
            _handle_plan_lowering_panic(
                self, e
            )  # Attributes schema panics; re-raises rest

    def _complete_collection(
        self,
        result: pl.DataFrame,
        *,
        engine: str = "polars",
        polars_mode: str | None = None,
        profiled: bool = False,
        from_engine: EngineResult | None = None,
    ) -> pl.DataFrame:
        """Settle the frame around one execution's values, whoever produced them.

        One function rather than two, because what a collect leaves behind is
        a contract and not a side effect: ``continue_from=`` verifies a
        returning column against it, an export reads the superseded
        definitions out of it, and the attribution window's cursor says which
        calculations a later failure may be attributed to. An engine's collect
        that settled two of the three would leave a frame that looked
        finished and answered one of those three questions wrongly.

        ``from_engine`` is what a second engine handed back beside the
        values: its report, and the manifest whose versions say what produced
        them. A Polars run passes none; its versions are this process's, and
        the summary reads them when asked rather than making every collect
        pay for them.
        """
        self._close_attribution_window()
        result = self._book_columns_judged(result)
        # Every superseded definition the model wrote came through this
        # one execution alongside the columns the frame still holds, and
        # comes straight back off it here. They are kept BESIDE the frame
        # rather than in it: an export reads them to say what a column
        # held before it was written over, and nobody modelling should
        # ever meet them among their own columns.
        result = self._set_aside_retained_definitions(result)
        # A container of this frame's own, over the caller's buffers: what
        # a re-entry verifies against has to be the values this call
        # produced, and the caller's object is not those values once an
        # in-place Polars call has written through it. See the note above.
        self._collected_values = result.clone()
        # And noted, so that a frame built over these values without
        # continue_from= can say which of its columns this frame calculated.
        # Nothing is read here; a frame that has calculated nothing has
        # nothing to say about them, and is not noted at all.
        if self._calculation_counts or self._rebuilt:
            _COMPUTED_VALUES.note(
                self._collected_values, _values_account(self), kept_while=result
            )
        summary = RunSummary(
            engine=engine,
            polars_mode=polars_mode,
            profiled=profiled,
            rows=result.height,
            columns=result.width,
            report=(
                RunReport(refusals=()) if from_engine is None else from_engine.report
            ),
        )
        self._last_run = (
            summary
            if from_engine is None
            else _stating(summary, from_engine.manifest.versions)
        )
        return result

    def _book_columns_judged(self, result: pl.DataFrame) -> pl.DataFrame:
        """Read a lazily handed book's wide columns as a DataFrame's door reads them.

        A book handed over as a DataFrame has its ``UInt64``, ``Int128`` and
        ``UInt128`` columns judged on their values where the frame is built:
        read as ``Int64`` where every value fits, kept in their width where
        one does not (section 10). A LazyFrame's values are not in hand
        there, so the same columns kept their width through the run, and a
        column no line read -- a policy number carried to the results --
        came back ``UInt64`` from the one door and ``Int64`` from the other.
        Its values are in hand here, so the rule is applied here, to the
        columns that arrived with the book and were not written over, and the
        two doors hand back one schema. A plan's own schema, before the run,
        still shows the width it arrived in: no values had been read to say
        otherwise. A column renamed on the way in holds the book's values
        under its new name, so it is read by the same rule: renamed, a
        policy number came back ``UInt64`` from the lazy door and ``Int64``
        from the other, while the record named it ``i64`` from both.
        """
        if self._wide_judged:
            return result
        moved = self._book_columns_renamed()
        arrived = [
            name
            for name, dtype in result.schema.items()
            if name in self._initial_columns
            and (self._calculation_counts.get(name, 0) == 0 or name in moved)
            and wider_than_i64_at(dtype) is not None
        ]
        if not arrived:
            return result
        return result.with_columns(with_integers_as_i64(result.select(arrived)))

    def _book_columns_renamed(self) -> frozenset[str]:
        """Return the names a book column reached by renames alone.

        Walked through the log in order: a rename of a name that still holds
        a book column holds it under the new name, and any other line that
        defines a name -- an assignment over it, a write straight into the
        plan -- leaves the name holding that line's values instead.
        """
        holds = set(self._arrival_names)
        for entry in self._calculations:
            if not isinstance(entry, CalculationRecord | OverwriteRecord):
                continue
            renamed = (
                isinstance(entry, CalculationRecord)
                and entry.origin == "rename"
                and isinstance(entry.node, Col)
                and entry.node.name in holds
            )
            if renamed:
                holds.add(entry.column)
            else:
                holds.discard(entry.column)
        return frozenset(holds)

    def _collect_on_engine(self, name: str) -> pl.DataFrame:
        """Fold the executable document and hand it to a discovered engine.

        The fold is values-free: ``GraphExporter.export`` with no result frame
        builds the graph without collecting, so nothing runs on Polars here.
        The engine is asked for every value-bearing node when the frame
        carries retained definitions, so the completion hook can set them
        aside exactly as a Polars collect would; otherwise for the final
        schema. Completion is the same hook both paths call.
        """
        from gaspatchio.engines import (  # noqa: PLC0415 — the seam imports nothing of the frame; the frame reaches it lazily
            engine_named,
        )
        from gaspatchio.engines.protocol import FrameSink  # noqa: PLC0415 — as above

        if self._df is None:
            return pl.DataFrame(schema={})

        engine = engine_named(name)
        document, inputs = self._for_an_engine()
        every = bool(self._retained_columns)
        result = engine.run(document, inputs, FrameSink(), every_node=every)
        frame = self._frame_from_engine_result(result, document, name, every_node=every)
        return self._complete_collection(frame, engine=name, from_engine=result)

    def _for_an_engine(self) -> tuple[dict[str, Any], pl.DataFrame]:
        """Return the executable document and the book an engine is handed.

        One method, because both doors that hand this frame to a second
        engine -- ``collect(engine=...)`` and ``run_aggregated(engine=...)``
        -- must hand it the same thing: the document folded values-free, and
        the columns this frame arrived with as the document names them. A
        book read from anywhere else -- the caller's model points before a
        setup phase reshaped them, say -- would be a second answer to "which
        book was this?", and the result manifest's ``inputs_digest`` would
        then describe different data depending on the door.
        """
        from gaspatchio.frame.graph import GraphExporter  # noqa: PLC0415 — as above

        # The book's digest is the engine's to take, over what it is handed:
        # the document leaves it, rather than pay for a pass over the book
        # that nothing reads.
        # Told the frame's own arrivals as its book: an engine is handed the
        # columns this frame arrived with (`_input_columns_for`), a column
        # the setup made among them, so each is an input it reads rather than
        # a hole with nothing to run -- which is how `engine="jax"` runs a
        # setup over the whole book before it cuts the batches.
        exporter = GraphExporter(self, data_columns=self._bare_arrivals)
        document = exporter._executable_for_an_engine()  # noqa: SLF001 -- the frame's own door
        if document.get("selection"):
            return document, self._book_for_a_selecting_engine(document)
        return document, self._input_columns_for(document)

    def _book_for_a_selecting_engine(self, document: dict[str, Any]) -> pl.DataFrame:
        """Return the book this frame was built over, for an engine that selects from it.

        A model that chose which policies it values hands the engine the book
        it chose them from, and the engine applies the recorded selection
        itself (section 7.6), exactly as ``gspio run-artifact`` does over the
        same file: the rows it values and the ``inputs_digest`` it records are
        then those of one replay, whichever door ran it. The columns are the
        ones the document requires, read from the data the frame was built
        over -- under the names they arrived with, before any rename, rewrite
        or drop -- so a selection on a column the model went on to drop is
        still made.

        Raises:
            EngineRefusal: If the frame holds no record of its book, or the
                document requires a column the book never held -- a scenario
                axis crossed onto it, a column handed over at a line.

        """
        from gaspatchio.engines.report import (  # noqa: PLC0415 — as above
            EngineRefusal,
            Refusal,
            RunReport,
        )
        from gaspatchio.frame.graph.execution import (  # noqa: PLC0415
            inspect_execution,
        )

        book = self._arrival_data
        held = book.collect_schema().names() if book is not None else []
        wanted = list(
            dict.fromkeys(
                requirement.column
                for requirement in inspect_execution(document).required_inputs
            )
        )
        absent = [column for column in wanted if column not in held]
        if book is None or absent:
            raise EngineRefusal(
                RunReport(
                    refusals=tuple(
                        Refusal(
                            group="inputs",
                            where=column,
                            count=None,
                            what=(
                                f"the model chose which policies it values, and "
                                f"{column!r} is not a column of the book it chose "
                                "them from, so the engine cannot make the same "
                                "choice over the same rows"
                            ),
                            move=(
                                "select the model points before building the "
                                "frame, or run gspio run-artifact over the book"
                            ),
                            clause="7.6",
                        )
                        for column in absent or ["the book"]
                    ),
                    notes=(),
                )
            )
        return book.select(wanted).collect()

    def _input_columns_for(self, document: dict[str, Any]) -> pl.DataFrame:
        """Return the arriving columns the document requires, or refuse by name.

        What is read is the frame's own record of what arrived, not its
        current schema: ``_initial_columns`` is the arriving set, following a
        rename and shrinking on a drop, and ``_calculation_counts`` says which
        of those names a calculation has since written over. A column whose
        current values are a later version is not the arrival the document's
        input node names, and the arrival's own values are gone -- retention
        carries a superseded *definition*, never the values a column arrived
        with. So the two ways a frame can no longer supply an input are one
        refusal: the column is gone, or what stands under that name is not
        what arrived.

        Filling it from the current column instead would put a computed
        number into an engine under the name of a model-point field, and the
        result would be a run nobody could attribute -- which is exactly the
        failure the whole seam exists to make impossible.
        """
        from gaspatchio.engines.report import (  # noqa: PLC0415 — as above
            EngineRefusal,
            Refusal,
            RunReport,
        )
        from gaspatchio.frame.graph.execution import (  # noqa: PLC0415
            inspect_execution,
        )

        required = inspect_execution(document).required_inputs
        held = self._df.collect_schema().names() if self._df is not None else []
        refusals: list[Refusal] = []
        wanted: list[str] = []
        for requirement in required:
            column = requirement.column
            if column not in held or column not in self._initial_columns:
                refusals.append(
                    Refusal(
                        group="inputs",
                        where=column,
                        count=None,
                        what=(
                            f"{column!r} arrived with the model points and the "
                            "frame no longer holds it -- it was renamed, "
                            "dropped or selected away"
                        ),
                        move=(
                            "run the engine on the frame the columns arrived "
                            f"on, or keep {column!r} under its own name"
                        ),
                        clause=requirement.node_id,
                    )
                )
                continue
            if self._calculation_counts.get(column, 0) > 0:
                refusals.append(
                    Refusal(
                        group="inputs",
                        where=column,
                        count=self._calculation_counts[column],
                        what=(
                            f"the model wrote over {column!r}, so what stands "
                            "under that name is a calculation rather than the "
                            "values the column arrived with"
                        ),
                        move=(
                            "write the calculation to a name of its own, so "
                            f"{column!r} keeps what arrived in it"
                        ),
                        clause=requirement.node_id,
                    )
                )
                continue
            wanted.append(column)
        if refusals:
            raise EngineRefusal(RunReport(refusals=tuple(refusals), notes=()))
        if self._df is None:  # pragma: no cover -- guarded by the caller
            return pl.DataFrame(schema={})
        return self._df.select(wanted).collect()

    def _frame_from_engine_result(
        self,
        result: EngineResult,
        document: dict[str, Any],
        engine: str,
        *,
        every_node: bool,
    ) -> pl.DataFrame:
        """Return the engine's node-keyed columns as the model's own schema.

        An engine answers about nodes and a caller asked about columns. The
        live definition of each name is that column; a definition the model
        wrote over goes back under the hidden name the frame's plan carried
        it under, so the completion hook sets it aside exactly as it does
        after a Polars collect. A state machine's balance and an arrival the
        model wrote over are no columns of this model and are left where they
        are.

        **Which node is which is read off the document, never off the id.**
        A node id is a column name and an ordinal joined by ``@``, and a
        column name may contain an ``@`` of its own -- an FX model writing
        ``spot@rate`` is not exotic. Splitting the id back apart guesses,
        and a guess here is a column that silently does not come back. The
        record already carries the three fields as fields, so they are read
        as fields.

        A manifest node the document does not carry cannot be placed at all.
        That is refused rather than dropped: an engine answering about a node
        this model never wrote is a disagreement about what was run, and the
        one thing it must not do is cost the caller a column without saying
        so.

        **Every refusal here is a completion refusal**, because by the time
        this runs the engine's ``run`` has returned: the work was done and
        what is being withheld is the publication of it. The tree group's
        closing sentence is "Nothing was computed.", which would be false --
        and the one claim a reader takes from a report is that sentence.

        A published frame with no columns at all is one refusal rather than
        one per manifest node. "The engine named this column and wrote none"
        is true of every name in that case and describes none of it: what
        happened is that no batch was published, and an empty book is still
        a batch with a schema.
        """
        from gaspatchio.engines.report import (  # noqa: PLC0415 — the frame reaches the seam lazily
            EngineRefusal,
            Refusal,
            RunReport,
        )

        if not result.columns.columns:
            raise EngineRefusal(
                RunReport(
                    refusals=(
                        Refusal(
                            group="completion",
                            where=engine,
                            count=None,
                            what=(
                                f"the {engine} engine published no batch, so "
                                "there are no values to place on this frame"
                            ),
                            move=(
                                "an engine publishes at least one batch -- "
                                "empty where the book is empty, carrying its "
                                "schema either way"
                            ),
                            clause=None,
                        ),
                    ),
                    notes=(),
                )
            )

        records = {
            str(node["id"]): node
            for node in (document.get("nodes") or [])
            if isinstance(node, dict) and node.get("id") is not None
        }
        live: dict[str, int] = dict(self._calculation_counts)
        select: list[pl.Expr] = []
        unplaceable: list[tuple[str, str]] = []
        for node_id, column_name in result.manifest.columns.items():
            record = records.get(node_id)
            if record is None:
                unplaceable.append(
                    (node_id, "the document this run was folded from has no such node")
                )
                continue
            if column_name not in result.columns.columns:
                unplaceable.append(
                    (node_id, f"the engine named column {column_name!r} and wrote none")
                )
                continue
            target = self._model_column_for(record, live, every_node=every_node)
            if target is None:
                continue
            select.append(pl.col(column_name).alias(target))
        if unplaceable:
            raise EngineRefusal(
                RunReport(
                    refusals=tuple(
                        Refusal(
                            group="completion",
                            where=node_id,
                            count=None,
                            what=(
                                f"the engine answered for {node_id!r} and "
                                f"{why}, so its values cannot be placed on "
                                "this frame"
                            ),
                            move=(
                                "run the engine on the document this frame "
                                "exports, or report the mismatch against the "
                                "engine's package"
                            ),
                            clause=None,
                        )
                        for node_id, why in unplaceable
                    ),
                    notes=(),
                )
            )
        frame = result.columns.select(select)
        ordered = [name for name in self._column_order if name in frame.columns]
        hidden = [name for name in frame.columns if name not in ordered]
        return frame.select([*ordered, *hidden])

    @staticmethod
    def _model_column_for(
        record: dict[str, Any], live: dict[str, int], *, every_node: bool
    ) -> str | None:
        """Return the name this node's values belong under, or None for no column.

        None is the ordinary answer for three of the five kinds a node record
        can carry: a running state and a compilation are not columns of the
        model at all, and an arrival the model later wrote over is a set of
        values no name on this frame stands for any more.
        """
        kind = record.get("kind")
        column = record.get("column")
        # A running state and a compilation carry `column: None` by
        # construction, so the two tests are one: no column named, or a kind
        # that is not a column of the model.
        if not isinstance(column, str) or kind not in ("input", "computed"):
            return None
        if kind == "input":
            return None if column in live else column
        version = record.get("version")
        if not isinstance(version, int):
            return None
        if version == live.get(column):
            return column
        if every_node and column in live:
            return _retained_column_name(column, version)
        return None

    def materialize(self, *, engine: str | None = None) -> ActuarialFrame:
        """Freeze the calculations so far into values, keeping the same frame.

        Everything up to this point stops being a recipe Polars re-derives on
        every collect and becomes data the rest of the model reads. Reach for
        it at the end of Phase 1, once the model points are joined, renamed
        and enriched, so the projection phase builds its plan on top of a
        finished setup rather than re-running it.

        This replaces the ``af = ActuarialFrame(af.collect())`` round-trip.
        That round-trip froze the values and threw away everything else the
        frame knew — how each column was calculated, which projection axis it
        was on, which columns were inputs. ``materialize`` keeps all of it:
        the calculation log survives intact, a column's assignment count
        carries on across the freeze, and the frame you called it on is the
        frame you get back.

        !!! note "When to use"
            * **End of setup:** After Phase 1's joins, renames, and derived
                policy attributes, so the projection is planned over settled
                model points.
            * **Long plans:** When a deep chain of dependent columns makes
                each ``collect()`` re-derive work that has not changed.

        This is the freeze for a frame that never leaves. Where the values
        genuinely have to go outside -- handed to a numpy generator, or to
        an enrichment routine that only speaks Polars -- ``collect()`` them
        and come back through ``ActuarialFrame(df, continue_from=af)``,
        which carries the same log across the same kind of boundary and
        records whatever the trip changed as data arriving at it.

        Args:
            engine: Execution engine, passed through to :meth:`collect`.
                Left unset, ``collect()``'s own default applies — the
                default is stated in one place, not two.

        Returns:
            This same frame, its plan now a scan over the frozen values.

        Raises:
            ValueError: If the frame holds no data to freeze.

        Examples:
            Freeze the setup phase before declaring the projection axis:

            >>> from gaspatchio import ActuarialFrame
            >>> af = ActuarialFrame({"annual_premium": [1200.0, 2400.0]})
            >>> af.monthly_premium = af.annual_premium / 12
            >>> af = af.materialize()
            >>> af.collect()["monthly_premium"].to_list()
            [100.0, 200.0]

        """
        if self._df is None:
            msg = "Cannot materialize an uninitialized ActuarialFrame."
            raise ValueError(msg)

        # collect() owns the engine default, the hidden-rollforward strip, the
        # error attribution, and the window close on success. Reusing it is
        # what keeps a failure here reported exactly as the same failure at a
        # plain collect() would be. It is also what settles the superseded
        # definitions written before this freeze: the values it set aside go
        # with the plan swap below, so a column written twice and then frozen
        # exports as history with no values, which is what a freeze made of
        # it.
        frozen = self.collect() if engine is None else self.collect(engine=engine)
        self._set_plan(frozen.lazy())
        # A boundary marks the one event that defines no column. Appended
        # AFTER the plan swap so its position is the log's own end, then
        # immediately closed over: a boundary sitting inside a window tail
        # would hand replay records from before the freeze to splice onto a
        # plan from after it (see ``_attribution_ops``'s invariant). The
        # close is also what puts this ``_df`` mutation behind an advanced
        # cursor, which is the contract every unrecorded plan change meets.
        # The span is captured here rather than derived later because the
        # only frame that knows where the freeze was asked for is this one,
        # and it has returned by the time anything reads the log.
        self._calculations.append(
            BoundaryRecord(
                kind="materialization",
                position=len(self._calculations),
                source=capture_source_span(),
            )
        )
        self._close_attribution_window()
        return self

    def profile(self) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Execute and materialize the dataframe with profiling, returning (result_df, profile_info)."""
        self._last_run = None
        try:
            if self._df is None:
                # Return empty dataframes for both result and profile
                return self._complete_collection(
                    pl.DataFrame(), profiled=True
                ), pl.DataFrame()

            final_df = self._df
            # See collect(): the log is record-only, never replayed here.
            self._log_query_plan_if_requested(final_df)

            # Strip hidden rollforward columns before profiling
            schema_names = final_df.collect_schema().names()
            scratch = _kernel_scratch_prefix()
            rollforward_cols = [c for c in schema_names if c.startswith(scratch)]
            if rollforward_cols:
                final_df = final_df.drop(rollforward_cols)

            # Use Polars profile to get both result and profile info
            result_df, profile_info = final_df.profile()
            return self._complete_collection(result_df, profiled=True), profile_info
        except Exception as e:  # noqa: BLE001
            _handle_execution_error(self, e)  # Will re-raise or format
        except BaseException as e:  # noqa: BLE001 — pyo3 panics bypass Exception (#54)
            _handle_plan_lowering_panic(
                self, e
            )  # Attributes schema panics; re-raises rest

    def _set_aside_retained_definitions(self, result: pl.DataFrame) -> pl.DataFrame:
        """Take the carried superseded definitions off ``result`` and keep them.

        They rode through the execution as ordinary columns, which is the
        whole economy of the thing: one collect answers for every definition
        the model wrote rather than one replay per definition it replaced.
        What comes back to the caller is the model's own schema, unchanged,
        and the values set aside here are what an export reads to say what a
        column held before it was written over.

        A container over the same buffers, so what is held on to is the
        retained columns themselves and nothing beside them. The ``_df``
        setter drops the lot the moment the plan moves, exactly as it drops
        the collected values: a plan that has moved is a log accounting for
        something else, and history read off a frame that is no longer this
        one would be history of a different model.
        """
        held = [name for name in result.columns if name.startswith(_RETAINED_PREFIX)]
        if not held:
            return result
        self._retained_values = result.select(held)
        handed_back = result.drop(held)
        # The tie between the two. What an export is given by its caller has
        # to be THIS frame, not merely a frame of the same height: rows from
        # one run beside history from another is the exact untruth retention
        # exists to prevent, and row counts coincide all the time.
        self._retained_for = ref(handed_back)
        return handed_back

    # Excluded: optimize, get_execution_stats

    def with_columns(self, *exprs: IntoExprColumn) -> ActuarialFrame:
        """Add columns to the DataFrame.

        Each expression writes the column it is named for. An expression with
        no name of its own is named by Polars after the first column it
        reads, so a calculation handed over unnamed would land on that
        column -- ``af.with_columns(table.lookup(age=af.age))`` would write
        the rate over ``age``. That is refused: name the column with
        ``af.<column> = <expression>`` or ``.alias(...)``. A column handed
        back as it stands is carried and replaces nothing.

        Raises:
            ValueError: If an expression has no name of its own and would
                overwrite the column it reads, naming that column and the
                two ways to say which column is meant.

        """
        if self._df is None:
            msg = "Cannot add columns to an uninitialized ActuarialFrame."
            raise ValueError(msg)
        # The plan as the batch found it: where it did not resolve either, a
        # failure below is an earlier line's break and not this batch's.
        found = self._df

        # The batch is in the plan and nothing has taken the log entry on
        # yet. True for exactly the window between the two, which is the
        # window the eager schema resolve below throws in.
        batch_unrecorded = False
        try:
            converted_exprs_dict = {}
            batch_nodes: dict[str, OpNode] = {}
            new_cols_order = []
            for given in exprs:
                e = _injection_as_it_enters(given)
                self._refuse_a_row_operation_over_periods(e)
                polars_expr = self._convert_to_expr(e)
                # Attempt to get output name for tracing and column order update
                try:
                    output_name = polars_expr.meta.output_name()
                except Exception:  # noqa: BLE001
                    # Fallback if name cannot be determined (e.g., literal) - needs careful handling
                    # For now, we might skip tracing unnamed expressions or require explicit naming/alias
                    # Let's assume expressions added via with_columns must have names for tracing
                    msg = f"Could not determine output name for expression: {polars_expr}. Use .alias()"
                    raise ValueError(msg) from None
                _refuse_reserved_column_names((output_name,), door="assignment")
                _refuse_a_column_replaced_under_an_inherited_name(
                    self._df.collect_schema,
                    polars_expr,
                    door="with_columns",
                    aliasable=isinstance(e, pl.Expr),
                )

                converted_exprs_dict[output_name] = polars_expr
                # Derived from what the caller wrote, not from the lowered
                # expression: a proxy contributes the op-tree it built.
                batch_nodes[output_name] = _assignment_node(e, column=output_name)
                refuse_an_injection_the_rows_cannot_take(self, e)
                if output_name not in self._column_order:
                    new_cols_order.append(output_name)

            # The log is record-only metadata — collect()/profile() never
            # replay it, so an operation that is recorded but not applied
            # would silently vanish.
            self._open_attribution_window_if_needed()
            self._set_plan(self._df.with_columns(**converted_exprs_dict))
            batch_unrecorded = True
            # Eager, unlike every other assignment door: this resolves the
            # whole plan's schema now, so a bad expression throws HERE and
            # not at collect().
            self._schema = self._df.collect_schema()
            # Down before the call and not after it: from here the recorder
            # owns the log entry, so a recorder that raises partway leaves a
            # half-recorded batch rather than one the handler mints a second
            # time, claiming its columns twice under two operation ids.
            batch_unrecorded = False
            self._record_batch_calculations(batch_nodes, converted_exprs_dict)
            self._column_order.extend(new_cols_order)
            self._refresh_attr_columns_set()

        except Exception as e:
            if batch_unrecorded:
                # The plan already carries this batch, so a log without it
                # describes a frame holding columns nothing accounts for —
                # the first kind of hole, latent only because the schema
                # assignment threw before the schema could advance to show
                # it. Recording here also hands replay the batch's aliases,
                # which is how the message names the one that broke instead
                # of printing all of them. The dtypes come off the last
                # schema that RESOLVED: the old type for an alias whose
                # name is in it, None for one whose name is not -- which
                # a name the frame itself holds can be, if nothing has
                # resolved the schema since the assignment that minted
                # it. What resolves it is enumerated once, in
                # _record_batch_calculations' docstring below; nothing
                # here restates that. The graph says the batch never
                # landed as `in_final_schema` either way.
                self._record_batch_calculations(batch_nodes, converted_exprs_dict)
                if not _resolves(found):
                    e.add_note(_NOT_RUN.format(door="with_columns"))
            # Same handler every other frame error goes through, and the
            # original exception rather than a rewrapped one: attribution
            # replay matches on the leading message line, so a framework
            # prefix in front of polars' own diagnosis would cost the batch
            # the attribution this door exists to give it.
            _handle_execution_error(self, e)
            raise
        return self

    def _record_batch_calculations(
        self, nodes: dict[str, OpNode], exprs: dict[str, pl.Expr]
    ) -> None:
        """Record one ``with_columns`` call in the durable log.

        Every column the call defines shares one operation id and one source
        span, because they came from one statement and one plan step. Dtypes
        come from the schema the call has already resolved, so they cost
        nothing extra here.

        The shared id is what keeps a batch replayable, and the window
        therefore holds on to it. Live, the batch is a single step in which
        every expression sees the pre-batch frame; replay reads the id back
        and re-applies the whole batch as one ``with_columns``, so an
        expression that read a sibling's old value is handed the old value
        again — exactly what Polars did.

        Also called from ``with_columns``'s error handler, for the batch
        that reached the plan and then failed the eager schema resolve.
        Nothing is different except the dtypes, and this is the one place
        that rule is written: the recorder's own ``self._schema`` read is
        the line it governs, and every other mention of it in the package
        and the tests points here instead of paraphrasing it.

        **What a failed batch records.** ``self._schema`` is the last
        schema that *resolved*, so each alias records whatever that
        schema holds for its name -- that name's old type where the
        schema holds it, ``None`` where it does not, which includes a
        name the frame itself holds if nothing has resolved the schema
        since the assignment that minted it. The graph reports these
        nodes as ``in_final_schema=False`` either way.

        **What resolves the schema.** Three writers, and they are the
        whole set: nothing else in this class writes ``_schema_value`` or
        clears ``_schema_dirty``. Each has a pin in
        ``tests/errors/test_with_columns_attribution.py``:

        - the ``_schema`` setter, which every path that replaces the plan
          and re-stamps the cache writes through. ``with_columns``'s own
          eager resolve is one such path, and is the one pinned, by the
          intervening-batch block of
          ``test_a_reused_alias_records_what_the_last_resolved_schema_holds``.
        - the ``_schema`` property, which resolves a dirty plan on a read
          and caches the result. Pinned by the schema-read block of the
          same test.
        - ``_apply_incremental_schema``, reached from ``__setitem__``
          only on the ``do_incremental`` branch -- the frame at least
          ``_INCREMENTAL_SCHEMA_MIN_COLS`` wide -- and only when the
          assigned dtype resolved cheaply. Both conditions pinned, by
          ``test_a_frame_wide_enough_to_advance_its_schema_types_the_reused_alias``
          and ``test_an_assignment_the_dtype_probe_declines_advances_no_schema``.

        So width decides whether the *assignment* advances the schema,
        never on its own which names the last resolved schema holds: a
        successful ``with_columns()`` before the failing batch resolves
        every name at any width, ``af.collect()`` resolves none at any
        width, and an assignment past that width whose dtype the probe
        declines advances nothing either.
        """
        operation_id = self._mint_operation_id()
        source = capture_source_span()
        schema = self._schema or {}
        for name, expr in exprs.items():
            self._record_calculation(
                name,
                node=nodes[name],
                expr=expr,
                dtype=schema.get(name),
                operation_id=operation_id,
                origin="batch",
                source=source,
            )

    def select(
        self,
        *exprs: IntoExprColumn | Iterable[IntoExprColumn],
        **named_exprs: IntoExprColumn,
    ) -> ActuarialFrame:
        """Select columns from the DataFrame.

        Accepts positional expressions (column names, proxies, or expressions) and
        keyword arguments for renamed/new expressions. One list, tuple or
        iterator of them is read as the columns it holds, as Polars reads it:
        ``af.select(["policy_id", "premium"])``.

        A column handed back as it stands -- a name, ``pl.col`` under its own
        name, ``pl.all()``, ``pl.exclude(...)`` or a type selector, and a
        column only marked sorted or cast to the type it has -- is carried,
        and records nothing, by the rule a write straight into the plan is
        read by. A column the select calculates is recorded as
        ``with_columns`` records one, at this line: under a name the frame
        holds, as that column's next definition, and under a new name, as its
        first.

        Args:
            *exprs: Columns or expressions to select, or one list of them.
            **named_exprs: Expressions to select with specific output names.

        Returns:
            The modified ActuarialFrame.

        Raises:
            ValueError: If one expression written over a selection of columns
                calculates, renames or copies any of them, such as
                ``pl.col("a", "b") * 2`` or ``pl.all().name.suffix("_out")``:
                there is no one name to record it under. The message names
                each column and the expression to write for it. Also if a
                positional expression with no name of its own calculates
                over a column and would inherit that column's name, as
                ``pl.col("term").cast(pl.Float64)`` does: name it with a
                keyword or ``.alias(...)``.

        """
        if self._df is None:
            msg = "Cannot select columns from an uninitialized ActuarialFrame."
            raise ValueError(msg)
        self._refuse_a_door_past_a_break("select")
        if len(exprs) == 1 and isinstance(exprs[0], list | tuple | Iterator):
            exprs = tuple(exprs[0])

        try:
            # In select(), bare strings are column NAMES (matching polars
            # semantics), not literals. Other types route through the
            # standard converter where strings → pl.lit.
            def _select_convert(value: Any) -> pl.Expr:  # noqa: ANN401
                if isinstance(value, str):
                    return pl.col(value)
                return self._convert_to_expr(value)

            # Convert positional and keyword arguments to Polars expressions
            converted_positional = [_select_convert(e) for e in exprs]
            for value, expr in zip(exprs, converted_positional, strict=True):
                _refuse_a_column_replaced_under_an_inherited_name(
                    self._df.collect_schema,
                    expr,
                    door="select",
                    aliasable=isinstance(value, pl.Expr),
                )
            converted_named = {
                name: _select_convert(e) for name, e in named_exprs.items()
            }

            # Combine positional and named arguments for the underlying select
            all_exprs_to_select = converted_positional + [
                expr.alias(name) for name, expr in converted_named.items()
            ]

            # Call underlying Polars select, through the callable the sealed
            # window keeps so a candidate can be confirmed on what it kept.
            def _selected(plan: pl.LazyFrame) -> pl.LazyFrame:
                return plan.select(all_exprs_to_select)

            # A name the select mints is one the model wrote; a name it only
            # carries through was on the frame already. Both read off the
            # plans themselves, before the frame moves, so a refused name
            # leaves the frame as it was.
            selected = _selected(self._df)
            schema = selected.collect_schema()
            held = dict(self._df.collect_schema())
            _refuse_reserved_column_names(
                (name for name in schema if name not in held), door="assignment"
            )
            # What the select calculates, read over the columns the frame
            # held and decided before the frame moves, so a refusal leaves it
            # as it was.
            defined = _select_definitions(
                self,
                held,
                list(zip(exprs, converted_positional, strict=True)),
                {
                    name: (named_exprs[name], expr)
                    for name, expr in converted_named.items()
                },
            )
            self._set_plan(selected)
            self._reset_attribution_window(StructuralOperation("select", _selected))

            # Update schema and column order AFTER execution
            self._schema = schema
            # Reconstruct column order based on the *new* schema from select,
            # less the frame's own working columns a select carries through:
            # they ride in the plan and are not columns of the model.
            working = set(_working_columns(schema.names()))
            self._column_order = [name for name in schema if name not in working]
            self._refresh_attr_columns_set()
            # After the window moved past the select, as a join records what
            # it brought: the select is replayed whole, as the structural step
            # it is, and never column by column.
            self._record_minted_columns(defined, origin="batch")

        except Exception as e:
            msg = f"Error selecting columns: {e}"
            raise type(e)(msg) from e
        return self

    def join(  # noqa: PLR0913 — mirrors pl.LazyFrame.join's own surface
        self,
        other: pl.DataFrame | pl.LazyFrame,
        on: str | list[str] | None = None,
        left_on: str | list[str] | None = None,
        right_on: str | list[str] | None = None,
        how: str = "left",
        maintain_order: str | None = None,
        *,
        on_missing: str = "raise",
    ) -> ActuarialFrame:
        """Join with another DataFrame without leaving the ActuarialFrame API.

        Enriches model points with assumption parameters, product lookups,
        expense tables, or any static data that should be attached per policy.
        This replaces the pattern of calling ``.collect()`` + raw Polars join
        + re-wrapping with ``ActuarialFrame()``.

        !!! note "When to use"
            * **Expense Parameters:** Attach product-level expense loadings,
                commission rates, or overhead allocations to each policy before
                projection.
            * **Product Configuration:** Join product parameter tables (riders,
                benefit features, premium patterns) onto model points by product code.
            * **Cohort Enrichment:** Add portfolio-level or cohort-level attributes
                (risk class, distribution channel) from external reference data.

        !!! note "Cost of the audit fingerprint"
            Every column arriving from the right side is recorded with a
            content fingerprint of the table it came from, so a reviewer can
            tell which version of the expense table a run used. Taking it
            sorts and serialises the whole right side once — negligible for
            the reference tables above, real for a right side of millions of
            rows. Pass a **LazyFrame** (``other.lazy()``, ``pl.scan_parquet(...)``)
            to skip it: a lazy right side records no fingerprint, because
            hashing it would mean collecting the frame you handed over lazily.
            A semi or anti join brings no column and chooses which policies
            the model values, so it is recorded as a selection step, with the
            same fingerprint of the table it matched against: a lazy right
            side records the step without one, and a replay of the artifact
            then refuses it by name.

        Parameters
        ----------
        other : pl.DataFrame | pl.LazyFrame
            The right-side table to join against.
        on : str | list[str] | None
            Column name(s) to join on (when both sides use the same name).
        left_on : str | list[str] | None
            Column name(s) on the left (this frame).
        right_on : str | list[str] | None
            Column name(s) on the right (other frame).
        how : str, default "left"
            Join type: "left", "inner", "full" (or "outer"), "right", "cross",
            "semi" or "anti".
        maintain_order : str | None, default None
            Row order through the join. **Left unset, the frame keeps its own
            rows where they were**: "left_right" for a left or inner join -- a
            lookup keeps the policies in the order the book holds them, as
            VLOOKUP does, and a policy the other table matches more than once
            gets its matches in the order that table lists them --
            "left_right" for a full, right or cross join,
            which puts the other table's rows after the frame's, in their own
            order, and "left" for a semi or anti join. That makes the output's
            row order the same from run to run, and with it the book digest an
            export records over a frame rebuilt from the join's result:
            without it, the streaming engine that ``collect()`` uses by default
            hands a join's rows back in a different order every run, and two
            runs over one file would compare as two books. A value you name
            always wins and is passed to Polars as it stands: "none" asks for
            Polars' faster unordered join, and "right" / "left_right" /
            "right_left" keep the order Polars says they do.
        on_missing : str, default "raise"
            What a **left** join does with a policy whose key matches no row
            of the other table -- a product code typed ``"Term20"`` against a
            table holding ``"TERM20"``, or a blank key. ``"raise"`` refuses
            the join where it is written, naming how many policies missed,
            the first of them and its key, as ``Table.lookup`` refuses a
            missing key. ``"null"`` keeps the policy with null in every
            column the join brings: the model has said that a missing row
            means "nothing here" -- an optional rider -- and a fold that
            skips nulls (``Sum``, ``Mean``, ``list.sum``) then leaves that
            policy out of the total unless the model fills it first
            (``af.rider_rate = af.rider_rate.fill_null(0.0)``). Other join
            types keep their own meaning of an unmatched key -- an inner
            join drops the policy, a semi or anti join selects by it -- and
            take only ``"raise"``.

        Returns
        -------
        ActuarialFrame
            Frame with columns from both sides.

        Raises
        ------
        TypeError
            If a key is not a column name -- an expression, say. The join's
            record names the columns each row was matched on, so a key is
            given by name; write a calculated key to a column first.
        ValueError
            If a key's name holds ``,`` or ``=`` or is empty, which the
            record cannot carry, or a key column holds lists -- a projected
            column's value per period -- which a join cannot match on.
            A left join under ``on_missing="raise"`` whose key matches no row
            of the other table is refused too, naming the count, the first
            policy and its key, and the two moves. Every refusal happens
            before the frame changes, and so does any
            error Polars raises resolving the join: a join that fails leaves
            the frame as it was.

        Examples
        --------
        **Attach expense parameters by product code**

        ```python
        import polars as pl
        from gaspatchio import ActuarialFrame

        expense_params = pl.DataFrame(
            {
                "product_code": ["TERM", "WL", "UL"],
                "expense_pct": [0.05, 0.08, 0.10],
            }
        )

        af = ActuarialFrame(
            {
                "policy_id": ["P001", "P002", "P003"],
                "product_code": ["TERM", "WL", "TERM"],
                "sum_assured": [100000, 200000, 150000],
            }
        )

        af = af.join(expense_params, on="product_code")

        print(af.collect())
        ```

        ```text
        shape: (3, 4)
        ┌───────────┬──────────────┬─────────────┬─────────────┐
        │ policy_id ┆ product_code ┆ sum_assured ┆ expense_pct │
        │ ---       ┆ ---          ┆ ---         ┆ ---         │
        │ str       ┆ str          ┆ i64         ┆ f64         │
        ╞═══════════╪══════════════╪═════════════╪═════════════╡
        │ P001      ┆ TERM         ┆ 100000      ┆ 0.05        │
        │ P002      ┆ WL           ┆ 200000      ┆ 0.08        │
        │ P003      ┆ TERM         ┆ 150000      ┆ 0.05        │
        └───────────┴──────────────┴─────────────┴─────────────┘
        ```
        """
        if self._df is None:
            msg = "Cannot join on an uninitialized ActuarialFrame."
            raise ValueError(msg)

        from gaspatchio._semantic.ir import Call  # noqa: PLC0415 — import cycle

        # The other table's integers arrive as the book's do, read as Int64.
        arrived = with_integers_as_i64(other)
        right = arrived.lazy() if isinstance(arrived, pl.DataFrame) else arrived
        _refuse_a_join_the_record_cannot_carry(
            self._schema or {}, right, (on, left_on, right_on)
        )
        _refuse_an_unused_miss_policy(how, on_missing)
        # What the join brought is what the schema gained, taken against the
        # schema as it stood a line earlier. The frame's column order is not
        # that set: a column written straight into the query plan is in the
        # schema and never reached the order, and so is the rollforward
        # kernel's own scratch column. Reading the order as "everything that
        # was already here" hands both of those to the join, which then
        # records them as having arrived from a table they never touched.
        columns_before = frozenset(self._schema or ())

        # Named by the caller wins, "none" included; otherwise the frame's own
        # rows stay first and where they were. Left to Polars, the streaming
        # engine can reorder them from run to run, so one book would digest
        # differently each time and two identical runs would compare as changed.
        order = maintain_order if maintain_order is not None else _order_kept_by(how)

        def _joined(plan: pl.LazyFrame) -> pl.LazyFrame:
            return plan.join(
                right,
                on=on,
                left_on=left_on,
                right_on=right_on,
                how=how,
                maintain_order=order,
            )

        # Everything that can fail is done before the frame changes: the joined
        # plan is resolved and its record built on the side, and only then put
        # in place. A join Polars refuses, or a right side the content grammar
        # cannot stamp, then leaves the frame exactly as it was, rather than
        # holding the other table's columns with no record of where they came
        # from.
        joined = _joined(self._df)
        schema = joined.collect_schema()
        new_cols = [c for c in schema if c not in columns_before]
        _refuse_reserved_column_names(new_cols, door="join")
        if how == "left" and on_missing == "raise":
            _refuse_an_unmatched_key(
                self._df, right, (on, left_on, right_on), capture_source_span()
            )
        # An arriving column was not computed by any expression on this frame,
        # so there is no formula to record -- the node says how it got here
        # (which keys, which join type, which right-side table) and the
        # expression is the plain post-join reference to the column itself.
        # That reference is the only expression that is true after the join,
        # and it is never replayed: `_record_minted_columns` advances the
        # cursor past everything it appends.
        #
        # Guarded on `new_cols` so a join that brings nothing (a right side
        # whose every column is a shared key) pays nothing here: there is no
        # node for a fingerprint to appear on. A semi or anti join brings
        # nothing too, and is recorded below as the selection it is. `other`
        # is untouched by the join above, so hashing it here is the same
        # bytes as before.
        minted: dict[str, tuple[Call, pl.Expr]] = {}
        if new_cols:
            # 11.1.2: a left join that keeps an unmatched policy says so on the
            # record; absent, the record's left join refused every miss.
            kept: tuple[tuple[str, str], ...] = (
                (("on_missing", "null"),)
                if how == "left" and on_missing == "null"
                else ()
            )
            node = Call(
                "join",
                args=(),
                attrs=(
                    ("on", join_on_attribute(on, left_on, right_on)),
                    ("how", how),
                    ("right_fingerprint", _right_side_fingerprint(other)),
                    *kept,
                ),
            )
            minted = {name: (node, pl.col(name)) for name in new_cols}

        # A semi or anti join brings no column and chooses rows: which policies
        # the model values. That is a selection, and it is recorded as one --
        # the same join call a column-bringing join records, its key, its type
        # and its right side's content identity, so a replay can take it again.
        # The right side is stamped here as any join's is, which files it for
        # the document to carry.
        selection = (
            SelectionRecord(
                kind="semi" if how == "semi" else "anti",
                node=Call(
                    "join",
                    args=(),
                    attrs=(
                        ("on", join_on_attribute(on, left_on, right_on)),
                        ("how", how),
                        ("right_fingerprint", _right_side_fingerprint(other)),
                    ),
                ),
                position=len(self._calculations),
                source=capture_source_span(),
            )
            if how in _SELECTING_JOINS
            else None
        )

        self._set_plan(joined)
        self._reset_attribution_window(StructuralOperation("join", _joined))
        self._schema = schema
        self._column_order.extend(new_cols)
        self._refresh_attr_columns_set()
        if minted:
            self._record_minted_columns(minted, origin="join")
        if selection is not None:
            self._selections.append(selection)
        return self

    def filter(
        self, predicate: pl.Expr | ConditionExpression | ExpressionProxy | ColumnProxy
    ) -> ActuarialFrame:
        """Keep the policies a condition holds for, and record the choice.

        Removes policies that don't match the condition. Commonly used to
        exclude lapsed, matured, or otherwise inactive policies before
        running a projection.

        **Which policies were valued is part of the model's record.** The
        step enters the audit artifact's ``selection`` list with its
        predicate, and moves ``graph_fingerprint`` and
        ``formulas_fingerprint``: a model that admits paid-up business this
        quarter is not the model that excluded it last quarter. The columns
        the predicate reads join the book's identity, so ``gspio verify``
        checks them even where the model drops them afterwards, and an
        engine replaying the artifact applies the same selection to the book
        before it projects.

        Write the condition the way a formula is written -- ``af.status ==
        "IF"`` -- or in Polars' own words -- ``pl.col("status") == "IF"``.
        Both record one predicate. A Polars condition outside the forms a
        predicate is recorded in (a string method, a cast, a window) is
        recorded as the engine's own text: the audit record still carries
        it, and an executable export refuses it, naming the line.

        Selecting the model points *before* the frame is built -- or
        collecting, filtering in Polars and building a new frame from the
        result -- is the other route. The frame then never held the other
        policies, so its book is the selected rows and the record carries no
        selection step.

        !!! note "When to use"
            * **In-Force Selection:** Filter to active policies (``status == "IF"``)
                before projection to exclude lapsed, surrendered, or matured business.
            * **Cohort Analysis:** Isolate a subset of policies by product, age band,
                or underwriting class for targeted analysis.

        Parameters
        ----------
        predicate : pl.Expr | ConditionExpression | ExpressionProxy | ColumnProxy
            The condition each policy must meet: a comparison built from the
            frame's columns, or a Boolean Polars expression.

        Returns
        -------
        ActuarialFrame
            Frame with only matching rows.

        Raises
        ------
        TypeError
            If ``predicate`` is neither a Polars expression nor a condition
            built from this frame's columns.
        ValueError
            If a Polars predicate reads an assumption table, curve or schedule
            inside an expression the record cannot see into; store the read
            as a column first and filter on that column. Also if the
            condition answers once a period rather than once a policy -- a
            filter keeps or drops whole policies -- naming the per-policy
            forms: ``af.x.list.get(0) > 0``, ``af.x.list.min() > 0`` or
            ``af.x.list.max() > 0``. Also if the condition reads across rows
            -- ``pl.col("sa") > pl.col("sa").mean()`` -- where the frame is
            not the whole book: a batch of a run cut into several, or a
            scenario axis (see ``frame/_across_rows.py``).

        Examples
        --------
        **Filter to in-force policies only**

        ```python
        import polars as pl
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame(
            {
                "policy_id": ["P001", "P002", "P003"],
                "status": ["IF", "LAPSED", "IF"],
                "premium": [1200, 800, 1500],
            }
        )

        af = af.filter(af.status == "IF")

        print(af.collect())
        ```

        ```text
        shape: (2, 3)
        ┌───────────┬────────┬─────────┐
        │ policy_id ┆ status ┆ premium │
        │ ---       ┆ ---    ┆ ---     │
        │ str       ┆ str    ┆ i64     │
        ╞═══════════╪════════╪═════════╡
        │ P001      ┆ IF     ┆ 1200    │
        │ P003      ┆ IF     ┆ 1500    │
        └───────────┴────────┴─────────┘
        ```
        """
        if self._df is None:
            msg = "Cannot filter an uninitialized ActuarialFrame."
            raise ValueError(msg)

        # A condition that reads across rows chooses from the rows in the
        # frame, which in a batch or on a scenario axis are not the book.
        refuse_a_read_across_rows(self, predicate, selection=True)
        refuse_an_injection_the_rows_cannot_take(self, predicate, selection=True)
        node, condition = self._selection_predicate(predicate)
        # A condition on a rollforward's state reads the run's hidden struct,
        # which only the door every expression enters by puts on the plan.
        # The filter enters by it too, so the run is on the plan before the
        # rows are chosen on it.
        condition = self._ensure_rollforward_sources(condition, node=node)
        self._refuse_a_condition_per_period(node)

        def _filtered(plan: pl.LazyFrame) -> pl.LazyFrame:
            return plan.filter(condition)

        self._set_plan(_filtered(self._df))
        self._reset_attribution_window(StructuralOperation("filter", _filtered))
        self._selections.append(
            SelectionRecord(
                kind="filter",
                node=node,
                position=len(self._calculations),
                source=capture_source_span(),
            )
        )
        return self

    def _refuse_a_condition_per_period(self, node: OpNode) -> None:
        """Refuse a filter condition that answers once a period, by sentence.

        A selection keeps or drops a whole policy, so its condition is one
        answer per policy. One that answers per period (``af.filter(af.x >
        0)`` with ``x`` per period) used to reach Polars, which failed with a
        comparison or predicate type error naming neither the filter nor the
        move. A shape the frame cannot resolve is left to run as written.

        Raises:
            ValueError: Naming the per-period column and the per-policy forms.

        """
        from .lowering.context import context_for  # noqa: PLC0415 -- import cycle
        from .lowering.polars import shape_of  # noqa: PLC0415 -- as above

        context = context_for(self)
        try:
            shape = shape_of(node, context)
        except (TypeError, ValueError, pl.exceptions.PolarsError) as unresolved:
            logger.trace(
                f"filter: the condition's shape did not resolve ({unresolved!r})"
            )
            return
        if shape != "list" or context is None:
            return
        raise ValueError(per_period_condition_refusal(_per_period_read(node, context)))

    def _selection_predicate(self, predicate: object) -> tuple[OpNode, pl.Expr]:
        """Return the op-tree a filter records, and the expression it runs.

        A condition built from the frame's columns carries its own tree, and
        what runs is that tree lowered, as an assignment's formula is. A
        Polars expression is read back into the tree where it is written in
        the forms a predicate takes (:func:`~.lowering.lift.lift_predicate`),
        and then the tree is what runs too, so the record is the calculation
        rather than an account of it; otherwise it is recorded as the
        engine's own text and runs as written.

        Raises:
            TypeError: If ``predicate`` is neither.
            ValueError: If a Polars predicate hides an assumption read.

        """
        from .lowering.context import context_for  # noqa: PLC0415 -- import cycle
        from .lowering.ingress import native_node  # noqa: PLC0415 -- as above
        from .lowering.lift import lift_predicate  # noqa: PLC0415 -- as above
        from .lowering.polars import lower_polars  # noqa: PLC0415 -- as above
        from .lowering.value_reads import hidden_reads  # noqa: PLC0415 -- as above

        # A Polars expression the framework built -- a rollforward's state,
        # ``compiled.expr_for("av").list.get(0) > 0`` -- carries its tree, and
        # is recorded by it as an assignment's formula is, rather than read
        # back from the engine's text, which names the run's hidden column.
        if (
            isinstance(predicate, ConditionExpression | ExpressionProxy | ColumnProxy)
            or getattr(predicate, "_node", None) is not None
        ):
            node = to_node(predicate)
            return node, lower_polars(node, context_for(self))
        if not isinstance(predicate, pl.Expr):
            msg = (
                f"filter() takes a condition, and was handed a "
                f"{type(predicate).__name__}. Write it from the frame's columns, "
                'af.filter(af.status == "IF"), or as a Polars expression, '
                'af.filter(pl.col("status") == "IF").'
            )
            raise TypeError(msg)
        lifted = lift_predicate(predicate)
        if lifted is not None:
            try:
                return lifted, lower_polars(lifted, context_for(self))
            except (TypeError, ValueError) as unlowered:
                logger.trace(
                    f"filter: a lifted predicate did not lower ({unlowered!r}); "
                    "it is recorded as the engine's own text"
                )
        native = native_node(predicate)
        reads = hidden_reads(native)
        if reads:
            listed = "; ".join(read.described() for read in reads)
            msg = (
                f"This filter's condition reads {listed} inside a Polars "
                "expression the framework cannot see into, so the model's "
                "fingerprint would not move when that basis did. Store the read "
                "as a column first -- af.rate = table.lookup(...) -- and filter "
                "on the column."
            )
            raise ValueError(msg)
        return native, predicate

    def rename(self, mapping: dict[str, str]) -> ActuarialFrame:
        """Rename columns to snake_case or actuarial conventions.

        Converts raw data column names (often from Excel or vendor systems)
        to the snake_case convention used throughout Gaspatchio models.
        Run this in Phase 1 (setup) before creating the projection timeline.

        !!! note "When to use"
            * **Data Ingestion:** Convert Excel-style column names
                (``"Issue Age"``, ``"Sum Assured"``) to snake_case for use
                as ActuarialFrame attributes.
            * **Vendor Data:** Standardise column names from different admin
                systems or data providers before building assumptions.

        Parameters
        ----------
        mapping : dict[str, str]
            Mapping of old name to new name.

        Returns
        -------
        ActuarialFrame
            Frame with renamed columns.

        Examples
        --------
        **Rename Excel-style columns to snake_case**

        ```python
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame(
            {
                "Policy Number": ["P001", "P002"],
                "Issue Age": [30, 45],
                "Sum Assured": [100000, 200000],
            }
        )

        af = af.rename(
            {
                "Policy Number": "policy_id",
                "Issue Age": "issue_age",
                "Sum Assured": "sum_assured",
            }
        )

        print(af.collect())
        ```

        ```text
        shape: (2, 3)
        ┌───────────┬───────────┬─────────────┐
        │ policy_id ┆ issue_age ┆ sum_assured │
        │ ---       ┆ ---       ┆ ---         │
        │ str       ┆ i64       ┆ i64         │
        ╞═══════════╪═══════════╪═════════════╡
        │ P001      ┆ 30        ┆ 100000      │
        │ P002      ┆ 45        ┆ 200000      │
        └───────────┴───────────┴─────────────┘
        ```
        """
        from gaspatchio._semantic.ir import Col  # noqa: PLC0415 — import cycle

        if self._df is None:
            msg = "Cannot rename columns on an uninitialized ActuarialFrame."
            raise ValueError(msg)
        self._refuse_a_door_past_a_break("rename")
        _refuse_reserved_column_names(mapping.values(), door="rename")

        # Taken while the old names are still the ones the schema holds:
        # after the move below, a column nothing accounts for can no longer
        # be recognised under the name it was unaccounted for by.
        unaccounted = self._unaccounted_columns()
        renamed_to = dict(mapping)

        def _renamed(plan: pl.LazyFrame) -> pl.LazyFrame:
            return plan.rename(renamed_to)

        self._set_plan(_renamed(self._df))
        self._reset_attribution_window(StructuralOperation("rename", _renamed))
        self._schema = self._df.collect_schema()
        self._column_order = [mapping.get(c, c) for c in self._column_order]
        # The arriving set is a set of names, and this is a name-move: an
        # input renamed away must be known by its new name afterwards, or
        # a column later written under the old one would be mistaken for
        # the data the model points supplied. The names the columns
        # arrived under do not move with it -- they are what they are --
        # and neither do the types, which is what lets the graph's leaf for
        # a renamed vendor field still state one.
        self._initial_columns = frozenset(
            mapping.get(column, column) for column in self._initial_columns
        )
        # A column the frame arrived holding that another frame calculated
        # is one this rename logs nothing for, so the new name is the
        # hole it was under the old one, and for the same reason. Added
        # rather than moved: a calculation written before the rename still
        # reads the old name, and reads the hole there.
        self._rebuilt = {
            **self._rebuilt,
            **{
                mapping[column]: origin
                for column, origin in self._rebuilt.items()
                if column in mapping and column in unaccounted
            },
        }
        self._refresh_attr_columns_set()
        # A rename is a name-move, so the new name's node is simply the column
        # it came from -- ``Col(old)``, never a fresh calculation. The
        # expression says the same thing in Polars: ``pl.col(old).alias(new)``
        # is exactly the move the frame performed, which makes it the one
        # honest expression for this record to hold.
        #
        # Unless the old name had no account of itself, in which case a
        # record of the move would manufacture one. The old name has left
        # the schema, so nothing seeds a hole for it any more, and the new
        # name would carry a record saying where it came from -- a column
        # the model cannot explain, exported under a name the frame never
        # held, as a field the model points supplied. Writing no record
        # leaves the new name in the schema, out of the log and out of the
        # arriving set, which is the hole it already was under the name the
        # frame now holds it by.
        self._record_minted_columns(
            {
                new: (Col(old), pl.col(old).alias(new))
                for old, new in mapping.items()
                if old not in unaccounted
            },
            origin="rename",
        )
        return self

    def drop(self, *columns: str) -> ActuarialFrame:
        """Remove columns from the frame.

        Drops intermediate or debug columns that are no longer needed.
        Commonly used at the end of a model to clean up temporary
        calculations before writing results.

        !!! note "When to use"
            * **Cleanup:** Remove intermediate calculation columns (flags,
                temporary rates) before writing final results to parquet.
            * **Memory:** Drop large columns that are no longer needed to
                reduce peak memory during collection.

        Parameters
        ----------
        *columns : str
            Column names to drop.

        Returns
        -------
        ActuarialFrame
            Frame without the specified columns.

        Examples
        --------
        **Remove temporary columns before output**

        ```python
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame(
            {
                "policy_id": ["P001"],
                "premium": [1200],
                "sum_assured": [100000],
                "temp_debug": [999],
            }
        )

        af = af.drop("temp_debug")

        print(af.collect())
        ```

        ```text
        shape: (1, 3)
        ┌───────────┬─────────┬─────────────┐
        │ policy_id ┆ premium ┆ sum_assured │
        │ ---       ┆ ---     ┆ ---         │
        │ str       ┆ i64     ┆ i64         │
        ╞═══════════╪═════════╪═════════════╡
        │ P001      ┆ 1200    ┆ 100000      │
        └───────────┴─────────┴─────────────┘
        ```
        """
        if self._df is None:
            msg = "Cannot drop columns from an uninitialized ActuarialFrame."
            raise ValueError(msg)
        self._refuse_a_door_past_a_break("drop")

        dropped = list(columns)

        def _dropped(plan: pl.LazyFrame) -> pl.LazyFrame:
            return plan.drop(dropped)

        self._set_plan(_dropped(self._df))
        self._reset_attribution_window(StructuralOperation("drop", _dropped))
        self._schema = self._df.collect_schema()
        self._column_order = [c for c in self._column_order if c not in columns]
        # A dropped input has stopped being one of the columns this frame
        # holds, so its name stops accounting for anything: write a column
        # into the plan under that name afterwards and it is a new column
        # nothing explains, not the field the model points supplied.
        #
        # `_arrival_names` is deliberately NOT shrunk alongside it. Records
        # written before the drop still read the dropped column by name,
        # and the graph seeds their source from the arrival names: take the
        # name out of both and every calculation that read it loses a
        # model-point input, reading instead a column the graph reports the
        # model as unable to account for, behind a warning that nothing
        # accounts for the name. The column left the schema; it did not
        # stop having arrived, and `_arrival_schema` is left whole for the
        # same reason: after this line the type a dropped column arrived
        # under is a thing no schema on this frame can be asked for.
        self._initial_columns -= frozenset(columns)
        self._refresh_attr_columns_set()
        return self

    def sort(
        self,
        by: str | list[str],
        *,
        descending: bool = False,
    ) -> ActuarialFrame:
        """Sort rows by one or more columns.

        Orders policies by a key column before projection or output.
        Useful for deterministic output ordering in reconciliation.

        !!! note "When to use"
            * **Reconciliation:** Sort by policy ID before comparing against
                a reference model to ensure row-by-row alignment.
            * **Reporting:** Order output by issue age, premium, or product
                code for presentation.

        Parameters
        ----------
        by : str | list[str]
            Column name(s) to sort by.
        descending : bool, default False
            Sort in descending order.

        Returns
        -------
        ActuarialFrame
            Sorted frame.

        Examples
        --------
        **Sort by issue age for reporting**

        ```python
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame(
            {
                "policy_id": ["P003", "P001", "P002"],
                "issue_age": [55, 30, 45],
                "premium": [1500, 1200, 800],
            }
        )

        af = af.sort("issue_age")

        print(af.collect())
        ```

        ```text
        shape: (3, 3)
        ┌───────────┬───────────┬─────────┐
        │ policy_id ┆ issue_age ┆ premium │
        │ ---       ┆ ---       ┆ ---     │
        │ str       ┆ i64       ┆ i64     │
        ╞═══════════╪═══════════╪═════════╡
        │ P001      ┆ 30        ┆ 1200    │
        │ P002      ┆ 45        ┆ 800     │
        │ P003      ┆ 55        ┆ 1500    │
        └───────────┴───────────┴─────────┘
        ```
        """
        if self._df is None:
            msg = "Cannot sort an uninitialized ActuarialFrame."
            raise ValueError(msg)

        keys = list(by) if isinstance(by, list) else by

        def _sorted(plan: pl.LazyFrame) -> pl.LazyFrame:
            return plan.sort(keys, descending=descending)

        self._set_plan(_sorted(self._df))
        self._reset_attribution_window(StructuralOperation("sort", _sorted))
        return self

    def pipe(
        self,
        func: Callable[..., ActuarialFrame | None],
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> ActuarialFrame:
        """Apply a function that accepts and returns an ActuarialFrame."""
        # Tracing should ideally happen *inside* the piped function if it uses frame ops
        # The pipe itself doesn't introduce new traceable operations at this level
        result = func(self, *args, **kwargs)
        if result is not None and not isinstance(result, ActuarialFrame):
            msg = f"Pipe function must return an ActuarialFrame or None, got {type(result)}"
            raise TypeError(msg)
        return result if result is not None else self

    # Excluded: Core function wrappers (fill_series, floor, round, etc.)
    # ADDED: Core function wrapper methods
    def fill_series(
        self,
        column: IntoExprColumn,
        start: int = 0,
        increment: int = 1,
    ) -> ExpressionProxy:
        """Apply fill_series using the core function."""
        expr = self._convert_to_expr(column)
        result_expr = plugins.fill_series(expr, start=start, increment=increment)
        return ExpressionProxy(result_expr, self)

    def get_column_order(self) -> list[str]:
        """Return the tracked order of columns."""
        # Try to get from schema if available and frame exists, otherwise use tracked order
        if self._df is not None and self._schema:
            # Schema might not reflect additions made during tracing until collect
            # Return the manually tracked order for consistency during tracing
            # return list(self._schema.keys())  # noqa: ERA001
            pass
        return self._column_order

    # Internal helper methods like _find_similar_columns belong with error handling

    # --- Accessor Properties ---
    # ADDED: Dynamic property for 'date' frame accessor
    @property
    def date(self) -> DateFrameAccessor:
        """Access date-related frame operations."""
        if self._date_accessor_instance is None:
            # Look up specifically for 'frame' kind using nested dict
            AccessorClass = _ACCESSOR_REGISTRY.get("date", {}).get("frame")
            if not AccessorClass:
                # Late import to ensure registration if registry was reset in tests
                try:
                    from ..accessors import (  # noqa: PLC0415 -- frame.base first loads from inside accessors.date (via frame.calculation_log); hoisted, this binds the half-built module and registers nothing
                        date as _date_mod,  # noqa: F401
                    )

                    AccessorClass = _ACCESSOR_REGISTRY.get("date", {}).get("frame")
                except Exception:  # noqa: BLE001
                    AccessorClass = None
                if not AccessorClass:
                    # Fallback to direct import of the built-in accessor class
                    try:
                        from ..accessors.date import (  # noqa: PLC0415 -- cycle: frame.base first loads from inside accessors.date; hoisted, `import gaspatchio` raises ImportError on the partially initialised module
                            DateFrameAccessor as _BuiltInDateAccessor,
                        )

                        AccessorClass = _BuiltInDateAccessor
                    except Exception:  # noqa: BLE001
                        msg = "No 'date' frame accessor registered or kind mismatch."
                        raise AttributeError(msg) from None
            # Use the class retrieved from the registry
            self._date_accessor_instance = AccessorClass(self)
        return self._date_accessor_instance

    # ADDED: Dynamic property for 'finance' frame accessor
    @property
    def finance(self) -> FinanceFrameAccessor:
        """Access finance-related frame operations."""
        if self._finance_accessor_instance is None:
            # Look up specifically for 'frame' kind using nested dict
            AccessorClass = _ACCESSOR_REGISTRY.get("finance", {}).get("frame")
            if not AccessorClass:
                try:
                    from ..accessors import (  # noqa: PLC0415 -- cycle: frame.base loads while gaspatchio.accessors initialises; hoisted, this accessor's registration raises during `import gaspatchio`
                        finance as _finance_mod,  # noqa: F401
                    )

                    AccessorClass = _ACCESSOR_REGISTRY.get("finance", {}).get("frame")
                except Exception:  # noqa: BLE001
                    AccessorClass = None
                if not AccessorClass:
                    try:
                        from ..accessors.finance import (  # noqa: PLC0415 -- cycle: frame.base loads while gaspatchio.accessors initialises; hoisted, this accessor's registration raises during `import gaspatchio`
                            FinanceFrameAccessor as _BuiltInFinanceAccessor,
                        )

                        AccessorClass = _BuiltInFinanceAccessor
                    except Exception:  # noqa: BLE001
                        msg = "No 'finance' frame accessor registered or kind mismatch."
                        raise AttributeError(msg) from None
            # Use the class retrieved from the registry
            self._finance_accessor_instance = AccessorClass(self)
        return self._finance_accessor_instance

    @property
    def excel(self) -> ExcelFrameAccessor:
        """Access excel-related frame operations."""
        if self._excel_accessor_instance is None:
            AccessorClass = _ACCESSOR_REGISTRY.get("excel", {}).get("frame")
            if not AccessorClass:
                try:
                    from ..accessors import (  # noqa: PLC0415 -- cycle: frame.base loads while gaspatchio.accessors initialises; hoisted, this accessor's registration raises during `import gaspatchio`
                        excel as _excel_mod,  # noqa: F401
                    )

                    AccessorClass = _ACCESSOR_REGISTRY.get("excel", {}).get("frame")
                except Exception:  # noqa: BLE001
                    AccessorClass = None
                if not AccessorClass:
                    try:
                        from ..accessors.excel import (  # noqa: PLC0415 -- cycle: frame.base loads while gaspatchio.accessors initialises; hoisted, this accessor's registration raises during `import gaspatchio`
                            ExcelFrameAccessor as _BuiltInExcelAccessor,
                        )

                        AccessorClass = _BuiltInExcelAccessor
                    except Exception:  # noqa: BLE001
                        msg = "No 'excel' frame accessor registered or kind mismatch."
                        raise AttributeError(msg) from None
            self._excel_accessor_instance = AccessorClass(self)
        return self._excel_accessor_instance

    @property
    def projection(self) -> ProjectionFrameAccessor:
        """Access projection setup and the rollforward builder for this frame.

        A declared property like its ``date``/``finance``/``excel`` siblings —
        not registry-``__getattr__`` — so the editor surface and runtime agree
        (gh#104).
        """
        if self._projection_accessor_instance is None:
            AccessorClass = _ACCESSOR_REGISTRY.get("projection", {}).get("frame")
            if not AccessorClass:
                try:
                    from ..accessors import (  # noqa: PLC0415 -- cycle: frame.base loads while gaspatchio.accessors initialises; hoisted, this accessor's registration raises during `import gaspatchio`
                        projection_frame as _projection_frame_mod,  # noqa: F401
                    )

                    AccessorClass = _ACCESSOR_REGISTRY.get("projection", {}).get(
                        "frame"
                    )
                except Exception:  # noqa: BLE001
                    AccessorClass = None
                if not AccessorClass:
                    try:
                        from ..accessors.projection_frame import (  # noqa: PLC0415 -- cycle: frame.base loads while gaspatchio.accessors initialises; hoisted, this accessor's registration raises during `import gaspatchio`
                            ProjectionFrameAccessor as _BuiltInProjectionAccessor,
                        )

                        AccessorClass = _BuiltInProjectionAccessor
                    except Exception:  # noqa: BLE001
                        msg = (
                            "No 'projection' frame accessor registered or "
                            "kind mismatch."
                        )
                        raise AttributeError(msg) from None
            self._projection_accessor_instance = AccessorClass(self)
        return self._projection_accessor_instance

    @property
    def graph(self) -> GraphFrameAccessor:
        """Access this frame's own account of how each of its columns was made.

        A declared property like its ``date``/``finance``/``excel`` siblings —
        not registry-``__getattr__`` — so the editor surface and runtime agree
        (gh#104). The accessor is built once and kept, because it caches the
        fold of this frame's calculation log behind it.
        """
        if self._graph_accessor_instance is None:
            AccessorClass = _ACCESSOR_REGISTRY.get("graph", {}).get("frame")
            if not AccessorClass:
                AccessorClass = GraphFrameAccessor
            self._graph_accessor_instance = AccessorClass(self)
        return self._graph_accessor_instance

    def max(self) -> MaxResult:
        """Calculate maximum values across all numeric columns.

        Returns a single-row frame containing the maximum value for each column.
        Essential for identifying outliers, validating data ranges, and determining
        upper bounds in actuarial calculations.

        !!! note "When to use"
            * **Data Validation:** Identify outliers in premium amounts, sum assured,
                or claim values that may require investigation.
            * **Experience Analysis:** Find maximum claim amounts, policy sizes, or
                ages in a portfolio for risk assessment.
            * **Regulatory Reporting:** Determine maximum exposure amounts for
                solvency calculations and stress testing.
            * **Pricing Boundaries:** Identify upper limits for age bands, benefit
                amounts, or policy terms in product design.

        Returns
        -------
        MaxResult
            A frame with one row containing maximum values for each column.

        Examples
        --------
        **Scalar Example: Portfolio Maximum Values**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "age": [25, 45, 67, 35],
            "sum_assured": [100000, 500000, 250000, 1000000],
            "annual_premium": [1200, 6000, 8500, 15000],
        }
        af = ActuarialFrame(data)
        max_values = af.max()
        print(max_values)
        print("Max age:", max_values["age"][0])
        print("Max sum assured:", max_values["sum_assured"][0])
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬─────┬─────────────┬────────────────┐
        │ policy_id ┆ age ┆ sum_assured ┆ annual_premium │
        │ ---       ┆ --- ┆ ---         ┆ ---            │
        │ str       ┆ i64 ┆ i64         ┆ i64            │
        ╞═══════════╪═════╪═════════════╪════════════════╡
        │ P004      ┆ 67  ┆ 1000000     ┆ 15000          │
        └───────────┴─────┴─────────────┴────────────────┘
        Max age: 67
        Max sum assured: 1000000
        ```

        **Vector Example: Maximum Monthly Claims**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "policy_year": [1, 2],
            "monthly_claims": [
                [0, 500, 0, 1200, 0, 0, 800, 0, 0, 0, 0, 2500],
                [0, 0, 3000, 0, 0, 1500, 0, 0, 0, 4000, 0, 0]
            ],
            "monthly_premiums": [
                [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000],
                [1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500]
            ]
        }
        af = ActuarialFrame(data)

        # Get maximum values to understand worst-case scenarios
        max_values = af.max()
        print(max_values)
        print("Max policy year:", max_values["policy_year"][0])
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬─────────────┬─────────────────────────────────────┬─────────────────────────────────────┐
        │ policy_id ┆ policy_year ┆ monthly_claims                      ┆ monthly_premiums                    │
        │ ---       ┆ ---         ┆ ---                                 ┆ ---                                 │
        │ str       ┆ i64         ┆ list[i64]                           ┆ list[i64]                           │
        ╞═══════════╪═════════════╪═════════════════════════════════════╪═════════════════════════════════════╡
        │ P002      ┆ 2           ┆ [0, 500, 3000, 1200, … 4000, 0, 0]  ┆ [1500, 1500, 1500, 1500, … 1500]    │
        └───────────┴─────────────┴─────────────────────────────────────┴─────────────────────────────────────┘
        Max policy year: 2
        ```
        """
        return _aggregate(self, "max", MaxResult, lambda plan: plan.max())

    def min(self) -> MinResult:
        """Calculate minimum values across all numeric columns.

        Returns a single-row frame containing the minimum value for each column.
        Essential for identifying baseline values, detecting anomalies, and establishing
        lower bounds in actuarial calculations.

        !!! note "When to use"
            * **Data Quality Checks:** Identify potential data errors like negative
                ages, zero premiums, or missing values coded as extreme minimums.
            * **Portfolio Analysis:** Find minimum entry ages, smallest policy sizes,
                or lowest premium amounts for market segmentation.
            * **Risk Assessment:** Determine minimum coverage levels, deductibles, or
                retention limits in reinsurance analysis.
            * **Product Design:** Establish minimum benefit guarantees, surrender values,
                or contribution limits for new products.

        Returns
        -------
        MinResult
            A frame with one row containing minimum values for each column.

        Examples
        --------
        **Scalar Example: Portfolio Minimum Values**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "age": [25, 45, 67, 35],
            "sum_assured": [100000, 500000, 250000, 1000000],
            "annual_premium": [1200, 6000, 8500, 15000],
        }
        af = ActuarialFrame(data)
        min_values = af.min()
        print(min_values)
        print("Min age:", min_values["age"])
        print("Min sum assured:", min_values["sum_assured"])
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬─────┬─────────────┬────────────────┐
        │ policy_id ┆ age ┆ sum_assured ┆ annual_premium │
        │ ---       ┆ --- ┆ ---         ┆ ---            │
        │ str       ┆ i64 ┆ i64         ┆ i64            │
        ╞═══════════╪═════╪═════════════╪════════════════╡
        │ P001      ┆ 25  ┆ 100000      ┆ 1200           │
        └───────────┴─────┴─────────────┴────────────────┘
        Min age: 25
        Min sum assured: 100000
        ```

        **Vector Example: Minimum Monthly Claims**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "policy_year": [1, 2],
            "monthly_claims": [
                [0, 500, 0, 1200, 0, 0, 800, 0, 0, 0, 0, 2500],
                [0, 0, 3000, 0, 0, 1500, 0, 0, 0, 4000, 0, 0]
            ],
            "monthly_retention": [
                [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000],
                [500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500]
            ]
        }
        af = ActuarialFrame(data)

        # Get minimum values to understand retention levels
        min_values = af.min()
        print(min_values)
        print("Min retention level:", min_values["monthly_retention"])
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬─────────────┬─────────────────────────────────────┬─────────────────────────────────────┐
        │ policy_id ┆ policy_year ┆ monthly_claims                      ┆ monthly_retention                   │
        │ ---       ┆ ---         ┆ ---                                 ┆ ---                                 │
        │ str       ┆ i64         ┆ list[i64]                           ┆ list[i64]                           │
        ╞═══════════╪═════════════╪═════════════════════════════════════╪═════════════════════════════════════╡
        │ P001      ┆ 1           ┆ [0, 0, 0, 0, … 0, 0, 0]             ┆ [500, 500, 500, 500, … 500]         │
        └───────────┴─────────────┴─────────────────────────────────────┴─────────────────────────────────────┘
        Min retention level: [500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500]
        ```
        """
        return _aggregate(self, "min", MinResult, lambda plan: plan.min())

    def mean(self) -> MeanResult:
        """Calculate mean values across all numeric columns.

        Returns a single-row frame containing the mean value for each numeric column.
        Essential for portfolio analysis, experience studies, and establishing
        benchmarks in actuarial calculations.

        !!! note "When to use"
            * **Experience Analysis:** Calculate average claim amounts, policy sizes,
                or premium levels for portfolio segmentation and pricing.
            * **Trend Analysis:** Determine average lapse rates, mortality rates, or
                expense ratios over observation periods.
            * **Benchmarking:** Establish portfolio averages for age, sum assured, or
                duration to compare against industry standards.
            * **Reserve Calculations:** Compute average policy values, benefit amounts,
                or reserve factors for grouped calculations.

        Returns
        -------
        MeanResult
            A frame with one row containing mean values for numeric columns.

        Examples
        --------
        **Scalar Example: Portfolio Averages**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "age": [25, 45, 67, 35],
            "sum_assured": [100000, 500000, 250000, 1000000],
            "annual_premium": [1200, 6000, 8500, 15000],
        }
        af = ActuarialFrame(data)
        mean_values = af.mean()
        print(mean_values)
        print("Average age:", mean_values["age"])
        print("Average sum assured:", mean_values["sum_assured"])
        ```

        ```text
        shape: (1, 3)
        ┌──────┬──────────────┬─────────────────┐
        │ age  ┆ sum_assured  ┆ annual_premium  │
        │ ---  ┆ ---          ┆ ---             │
        │ f64  ┆ f64          ┆ f64             │
        ╞══════╪══════════════╪═════════════════╡
        │ 43.0 ┆ 462500.0     ┆ 7425.0          │
        └──────┴──────────────┴─────────────────┘
        Average age: 43.0
        Average sum assured: 462500.0
        ```

        **Vector Example: Average Monthly Experience**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "policy_year": [1, 2],
            "monthly_claims": [
                [0, 500, 0, 1200, 0, 0, 800, 0, 0, 0, 0, 2500],
                [0, 0, 3000, 0, 0, 1500, 0, 0, 0, 4000, 0, 0]
            ],
            "monthly_lapses": [
                [2, 1, 3, 0, 1, 2, 1, 0, 1, 0, 2, 1],
                [1, 0, 2, 1, 0, 1, 0, 1, 0, 2, 1, 0]
            ]
        }
        af = ActuarialFrame(data)

        # Get average monthly experience
        mean_values = af.mean()
        print(mean_values)
        ```

        ```text
        shape: (1, 4)
        ┌─────────────┬───────────────────────────────┬──────────────────────────────┐
        │ policy_year ┆ monthly_claims                ┆ monthly_lapses               │
        │ ---         ┆ ---                           ┆ ---                          │
        │ f64         ┆ list[f64]                     ┆ list[f64]                    │
        ╞═════════════╪═══════════════════════════════╪══════════════════════════════╡
        │ 1.5         ┆ [0.0, 250.0, 1500.0, … 0.0]   ┆ [1.5, 0.5, 2.5, … 0.5]       │
        └─────────────┴───────────────────────────────┴──────────────────────────────┘
        ```
        """
        return _aggregate(self, "mean", MeanResult, lambda plan: plan.mean())

    def std(self, ddof: int = 1) -> StdResult:
        """Calculate standard deviation across all numeric columns.

        Returns a single-row frame containing the standard deviation for each numeric column.
        Essential for risk assessment, volatility analysis, and confidence interval
        calculations in actuarial modeling.

        !!! note "When to use"
            * **Risk Assessment:** Measure volatility in claim amounts, premium variations,
                or mortality experience for pricing and reserving.
            * **Experience Monitoring:** Quantify variability in lapse rates, expense ratios,
                or benefit utilization for assumption setting.
            * **Confidence Intervals:** Calculate standard errors for mortality estimates,
                reserve factors, or pricing assumptions.
            * **Portfolio Analysis:** Assess homogeneity of risk groups by comparing
                standard deviations across segments.

        Parameters
        ----------
        ddof : int, default 1
            Delta degrees of freedom. The divisor is N - ddof.

        Returns
        -------
        StdResult
            A frame with one row containing standard deviations for numeric columns.

        Examples
        --------
        **Scalar Example: Premium Volatility Analysis**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004", "P005"],
            "age_band": ["25-35", "25-35", "36-45", "36-45", "46-55"],
            "annual_premium": [1200, 1350, 3500, 3200, 8500],
            "sum_assured": [100000, 150000, 350000, 300000, 500000],
        }
        af = ActuarialFrame(data)
        std_values = af.std()
        print(std_values)
        print("Premium volatility:", std_values["annual_premium"])
        ```

        ```text
        shape: (1, 2)
        ┌──────────────────┬─────────────┐
        │ annual_premium   ┆ sum_assured │
        │ ---              ┆ ---         │
        │ f64              ┆ f64         │
        ╞══════════════════╪═════════════╡
        │ 2913.8           ┆ 158113.9    │
        └──────────────────┴─────────────┘
        Premium volatility: 2913.8
        ```

        **Vector Example: Monthly Claims Volatility**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "product": ["Term Life", "Whole Life"],
            "monthly_claims": [
                [0, 1000, 500, 2000, 0, 3000, 1500, 0, 2500, 1000, 0, 4000],
                [5000, 6000, 4500, 7000, 5500, 8000, 6500, 5000, 7500, 6000, 9000, 10000]
            ],
            "monthly_premiums": [
                [50000, 50000, 52000, 51000, 50000, 49000, 50000, 51000, 50000, 50000, 51000, 50000],
                [120000, 125000, 122000, 128000, 124000, 130000, 126000, 123000, 127000, 125000, 129000, 132000]
            ]
        }
        af = ActuarialFrame(data)

        # Calculate standard deviation for risk assessment
        std_values = af.std()
        print(std_values)
        print("Term Life claims volatility:", round(std_values["monthly_claims"][0], 2))
        print("Whole Life claims volatility:", round(std_values["monthly_claims"][1], 2))
        ```

        ```text
        shape: (1, 3)
        ┌────────────┬──────────────────────────────┬───────────────────────────────┐
        │ product    ┆ monthly_claims               ┆ monthly_premiums              │
        │ ---        ┆ ---                          ┆ ---                           │
        │ str        ┆ list[f64]                    ┆ list[f64]                     │
        ╞════════════╪══════════════════════════════╪═══════════════════════════════╡
        │ null       ┆ [1443.38, 1443.38]           ┆ [831.66, 3207.14]             │
        └────────────┴──────────────────────────────┴───────────────────────────────┘
        Term Life claims volatility: 1443.38
        Whole Life claims volatility: 1443.38
        ```
        """
        return _aggregate(self, "std", StdResult, lambda plan: plan.std(ddof=ddof))

    def var(self, ddof: int = 1) -> VarResult:
        """Calculate variance across all numeric columns.

        Returns a single-row frame containing the variance for each numeric column.
        Used for risk metrics, ANOVA calculations, and statistical modeling in
        actuarial applications.

        !!! note "When to use"
            * **Risk Metrics:** Calculate variance in loss ratios, combined ratios,
                or expense ratios for enterprise risk management.
            * **Statistical Testing:** Perform ANOVA on mortality rates, lapse rates,
                or claim frequencies across different cohorts.
            * **Credibility Theory:** Calculate variance components for Bühlmann
                credibility factors in experience rating.
            * **Asset-Liability Modeling:** Measure variance in investment returns,
                liability cash flows, or surplus positions.

        Parameters
        ----------
        ddof : int, default 1
            Delta degrees of freedom. The divisor is N - ddof.

        Returns
        -------
        VarResult
            A frame with one row containing variances for numeric columns.

        Examples
        --------
        **Scalar Example: Claims Variance Analysis**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "month": [1, 2, 3, 4, 5, 6],
            "claims_count": [45, 52, 38, 61, 43, 55],
            "claims_amount": [125000, 145000, 95000, 185000, 120000, 165000],
        }
        af = ActuarialFrame(data)
        var_values = af.var()
        print(var_values)
        print("Claims count variance:", var_values["claims_count"])
        print("Claims amount variance:", var_values["claims_amount"])
        ```

        ```text
        shape: (1, 3)
        ┌───────┬──────────────┬──────────────────┐
        │ month ┆ claims_count ┆ claims_amount    │
        │ ---   ┆ ---          ┆ ---              │
        │ f64   ┆ f64          ┆ f64              │
        ╞═══════╪══════════════╪══════════════════╡
        │ 3.5   ┆ 70.3         ┆ 1.091e9          │
        └───────┴──────────────┴──────────────────┘
        Claims count variance: 70.3
        Claims amount variance: 1091000000.0
        ```

        **Vector Example: Experience Variance Components**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "region": ["North", "South"],
            "quarterly_lapse_rates": [
                [0.025, 0.028, 0.022, 0.026],
                [0.031, 0.029, 0.033, 0.030]
            ],
            "quarterly_mortality_rates": [
                [0.0010, 0.0011, 0.0009, 0.0010],
                [0.0012, 0.0013, 0.0011, 0.0014]
            ]
        }
        af = ActuarialFrame(data)

        # Calculate variance for credibility analysis
        var_values = af.var()
        print(var_values)
        print("North region lapse variance:", var_values["quarterly_lapse_rates"][0])
        print("South region lapse variance:", var_values["quarterly_lapse_rates"][1])
        ```

        ```text
        shape: (1, 3)
        ┌────────────┬────────────────────────┬──────────────────────────────┐
        │ region     ┆ quarterly_lapse_rates  ┆ quarterly_mortality_rates    │
        │ ---        ┆ ---                    ┆ ---                          │
        │ str        ┆ list[f64]              ┆ list[f64]                    │
        ╞════════════╪════════════════════════╪══════════════════════════════╡
        │ null       ┆ [0.000007, 0.000003]   ┆ [0.0000000067, 0.0000000167] │
        └────────────┴────────────────────────┴──────────────────────────────┘
        North region lapse variance: 0.000007
        South region lapse variance: 0.000003
        ```
        """
        return _aggregate(self, "var", VarResult, lambda plan: plan.var(ddof=ddof))

    def median(self) -> MedianResult:
        """Calculate median values across all numeric columns.

        Returns a single-row frame containing the median value for each numeric column.
        Useful for robust central tendency measures that are less affected by outliers
        in actuarial data.

        !!! note "When to use"
            * **Robust Analysis:** Use median instead of mean when data contains outliers,
                such as large claims or extreme ages in the portfolio.
            * **Income Analysis:** Analyze median policyholder income or premium levels
                for market segmentation and product design.
            * **Experience Studies:** Calculate median time to claim, policy duration,
                or age at lapse for more representative measures.
            * **Pricing Benchmarks:** Determine median rates or factors when comparing
                across competitors or market segments.

        Returns
        -------
        MedianResult
            A frame with one row containing median values for numeric columns.

        Examples
        --------
        **Scalar Example: Median Policy Metrics**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004", "P005"],
            "duration_years": [1, 3, 5, 7, 15],
            "annual_premium": [1200, 3500, 2800, 4200, 12000],
            "age": [25, 35, 42, 38, 65],
        }
        af = ActuarialFrame(data)
        median_values = af.median()
        print(median_values)
        print("Median duration:", median_values["duration_years"])
        print("Median premium:", median_values["annual_premium"])
        ```

        ```text
        shape: (1, 3)
        ┌────────────────┬────────────────┬──────┐
        │ duration_years ┆ annual_premium ┆ age  │
        │ ---            ┆ ---            ┆ ---  │
        │ f64            ┆ f64            ┆ f64  │
        ╞════════════════╪════════════════╪══════╡
        │ 5.0            ┆ 3500.0         ┆ 38.0 │
        └────────────────┴────────────────┴──────┘
        Median duration: 5.0
        Median premium: 3500.0
        ```

        **Vector Example: Median Monthly Performance**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "agent": ["A001", "A002"],
            "monthly_sales": [
                [3, 5, 2, 8, 4, 6, 3, 7, 5, 4, 6, 9],
                [12, 15, 10, 18, 14, 16, 11, 20, 13, 17, 15, 22]
            ],
            "monthly_commission": [
                [450, 750, 300, 1200, 600, 900, 450, 1050, 750, 600, 900, 1350],
                [1800, 2250, 1500, 2700, 2100, 2400, 1650, 3000, 1950, 2550, 2250, 3300]
            ]
        }
        af = ActuarialFrame(data)

        # Calculate median for typical performance assessment
        median_values = af.median()
        print(median_values)
        print("Agent A001 median sales:", median_values["monthly_sales"][0])
        print("Agent A002 median sales:", median_values["monthly_sales"][1])
        ```

        ```text
        shape: (1, 3)
        ┌────────────┬────────────────────┬──────────────────────┐
        │ agent      ┆ monthly_sales      ┆ monthly_commission   │
        │ ---        ┆ ---                ┆ ---                  │
        │ str        ┆ list[f64]          ┆ list[f64]            │
        ╞════════════╪════════════════════╪══════════════════════╡
        │ null       ┆ [5.0, 15.0]        ┆ [750.0, 2250.0]      │
        └────────────┴────────────────────┴──────────────────────┘
        Agent A001 median sales: 5.0
        Agent A002 median sales: 15.0
        ```
        """
        return _aggregate(self, "median", MedianResult, lambda plan: plan.median())

    def sum(self) -> SumResult:
        """Calculate sum totals across all numeric columns.

        Returns a single-row frame containing the sum total for each numeric column.
        Critical for calculating portfolio totals, aggregate exposures, and overall
        metrics in actuarial reporting.

        !!! note "When to use"
            * **Portfolio Totals:** Calculate total sum assured, total premiums collected,
                or total claims paid for financial reporting.
            * **Exposure Analysis:** Sum total lives covered, total benefits, or total
                risk amounts for reinsurance and capital calculations.
            * **Revenue Reporting:** Aggregate premium income, fee revenue, or investment
                income across product lines or time periods.
            * **Claims Analysis:** Total claim counts, amounts paid, or reserves across
                different claim types or cohorts.

        Returns
        -------
        SumResult
            A frame with one row containing sum totals for numeric columns.

        Examples
        --------
        **Scalar Example: Portfolio Totals**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "product": ["Term", "Whole Life", "Universal", "Term", "Endowment"],
            "policies_inforce": [1250, 890, 445, 2100, 325],
            "annual_premium": [1500000, 3200000, 2100000, 2800000, 1900000],
            "sum_assured": [125000000, 89000000, 67000000, 315000000, 48000000],
        }
        af = ActuarialFrame(data)
        sum_values = af.sum()
        print(sum_values)
        print("Total policies:", sum_values["policies_inforce"])
        print("Total premium:", sum_values["annual_premium"])
        print("Total exposure:", sum_values["sum_assured"])
        ```

        ```text
        shape: (1, 3)
        ┌──────────────────┬────────────────┬─────────────┐
        │ policies_inforce ┆ annual_premium ┆ sum_assured │
        │ ---              ┆ ---            ┆ ---         │
        │ i64              ┆ i64            ┆ i64         │
        ╞══════════════════╪════════════════╪═════════════╡
        │ 5010             ┆ 11500000       ┆ 644000000   │
        └──────────────────┴────────────────┴─────────────┘
        Total policies: 5010
        Total premium: 11500000
        Total exposure: 644000000
        ```

        **Vector Example: Monthly Totals**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "branch": ["North", "South"],
            "monthly_new_business": [
                [120, 135, 110, 145, 130, 125, 140, 155, 135, 140, 130, 160],
                [95, 100, 90, 105, 110, 95, 100, 115, 105, 100, 95, 120]
            ],
            "monthly_premium": [
                [180000, 202500, 165000, 217500, 195000, 187500, 210000, 232500, 202500, 210000, 195000, 240000],
                [142500, 150000, 135000, 157500, 165000, 142500, 150000, 172500, 157500, 150000, 142500, 180000]
            ]
        }
        af = ActuarialFrame(data)

        # Get total new business and premiums
        sum_values = af.sum()
        print(sum_values)
        ```

        ```text
        shape: (1, 2)
        ┌───────────────────────────────────────┬───────────────────────────────────────┐
        │ monthly_new_business                  ┆ monthly_premium                       │
        │ ---                                   ┆ ---                                   │
        │ list[i64]                             ┆ list[i64]                             │
        ╞═══════════════════════════════════════╪═══════════════════════════════════════╡
        │ [215, 235, 200, 250, … 240, 225, 280] ┆ [322500, 352500, 300000, … 420000]    │
        └───────────────────────────────────────┴───────────────────────────────────────┘
        ```
        """
        return _aggregate(self, "sum", SumResult, lambda plan: plan.sum())

    def count(self) -> CountResult:
        """Count non-null values in each column.

        Returns a single-row frame containing the count of non-null values for each column.
        Essential for data quality assessment, completeness checks, and exposure
        calculations in actuarial analysis.

        !!! note "When to use"
            * **Data Quality:** Assess completeness of critical fields like policy ID,
                sum assured, or premium to identify missing data issues.
            * **Exposure Calculation:** Count policies, lives, or claims for exposure-based
                calculations in pricing and reserving.
            * **Cohort Analysis:** Determine size of different risk groups, age bands,
                or product segments for credibility assessment.
            * **Validation:** Verify record counts match expected values after data
                processing, joins, or filtering operations.

        Returns
        -------
        CountResult
            A frame with one row containing non-null counts for each column.

        Examples
        --------
        **Scalar Example: Data Completeness Check**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004", None],
            "age": [25, 45, None, 35, 52],
            "sum_assured": [100000, 500000, 250000, None, 300000],
            "status": ["Active", "Active", "Lapsed", "Active", "Active"],
        }
        af = ActuarialFrame(data)
        counts = af.count()
        print(counts)
        print("Complete policies:", counts["policy_id"])
        print("Complete ages:", counts["age"])
        print("Data completeness %:", counts["age"] / 5 * 100)
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬─────┬─────────────┬────────┐
        │ policy_id ┆ age ┆ sum_assured ┆ status │
        │ ---       ┆ --- ┆ ---         ┆ ---    │
        │ u32       ┆ u32 ┆ u32         ┆ u32    │
        ╞═══════════╪═════╪═════════════╪════════╡
        │ 4         ┆ 4   ┆ 4           ┆ 5      │
        └───────────┴─────┴─────────────┴────────┘
        Complete policies: 4
        Complete ages: 4
        Data completeness %: 80.0
        ```

        **Vector Example: Monthly Activity Counts**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "month": ["Jan", "Feb"],
            "daily_claims": [
                [5, 3, 0, 4, None, 2, 1, 0, 3, None, 4, 2, 0, 1, 5],
                [2, None, 3, 1, 0, 4, None, 2, 0, 3, 1, None, 4, 2, 0]
            ],
            "daily_lapses": [
                [1, 0, 0, 2, 1, 0, 0, 1, 0, 0, 1, 0, 2, 0, 1],
                [0, 1, 0, 0, 2, 0, 1, 0, 1, 0, 0, 1, 0, 2, 0]
            ]
        }
        af = ActuarialFrame(data)

        # Count valid daily observations
        counts = af.count()
        print(counts)
        ```

        ```text
        shape: (1, 3)
        ┌───────┬──────────────┬──────────────┐
        │ month ┆ daily_claims ┆ daily_lapses │
        │ ---   ┆ ---          ┆ ---          │
        │ u32   ┆ u32          ┆ u32          │
        ╞═══════╪══════════════╪══════════════╡
        │ 2     ┆ 2            ┆ 2            │
        └───────┴──────────────┴──────────────┘
        ```
        """
        return _aggregate(self, "count", CountResult, lambda plan: plan.count())

    def product(self) -> ProductResult:
        """Calculate the product of values in each numeric column.

        Returns a single-row frame containing the product of all values for each numeric column.
        Useful for compound calculations, probability chains, and multiplicative factors
        in actuarial modeling.

        !!! note "When to use"
            * **Compound Interest:** Calculate accumulated values using multiple period
                growth factors or discount factors.
            * **Probability Chains:** Multiply survival probabilities, persistency rates,
                or success rates across multiple periods.
            * **Factor Application:** Apply multiple adjustment factors, loading factors,
                or credibility factors in sequence.
            * **Index Calculations:** Compute cumulative index values from period-to-period
                change factors.

        Returns
        -------
        ProductResult
            A frame with one row containing products for numeric columns.

        Examples
        --------
        **Scalar Example: Survival Probability Chain**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "year": [1, 2, 3, 4, 5],
            "annual_survival": [0.999, 0.998, 0.997, 0.995, 0.993],
            "annual_persistency": [0.95, 0.92, 0.90, 0.88, 0.85],
        }
        af = ActuarialFrame(data)
        products = af.product()
        print(products)
        print("5-year survival probability:", round(products["annual_survival"], 6))
        print("5-year persistency:", round(products["annual_persistency"], 4))
        ```

        ```text
        shape: (1, 3)
        ┌──────┬─────────────────┬────────────────────┐
        │ year ┆ annual_survival ┆ annual_persistency │
        │ ---  ┆ ---             ┆ ---                │
        │ i64  ┆ f64             ┆ f64                │
        ╞══════╪═════════════════╪════════════════════╡
        │ 120  ┆ 0.982089        ┆ 0.59262            │
        └──────┴─────────────────┴────────────────────┘
        5-year survival probability: 0.982089
        5-year persistency: 0.5926
        ```

        **Vector Example: Discount Factor Chains**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "scenario": ["Base", "Stressed"],
            "monthly_discount": [
                [0.9992, 0.9992, 0.9992, 0.9992, 0.9992, 0.9992],
                [0.9990, 0.9990, 0.9990, 0.9990, 0.9990, 0.9990]
            ],
            "monthly_survival": [
                [0.9999, 0.9999, 0.9999, 0.9999, 0.9999, 0.9999],
                [0.9998, 0.9998, 0.9998, 0.9998, 0.9998, 0.9998]
            ]
        }
        af = ActuarialFrame(data)

        # Calculate cumulative factors
        products = af.product()
        print(products)
        ```

        ```text
        shape: (1, 3)
        ┌──────────┬──────────────────┬──────────────────┐
        │ scenario ┆ monthly_discount ┆ monthly_survival │
        │ ---      ┆ ---              ┆ ---              │
        │ str      ┆ list[f64]        ┆ list[f64]        │
        ╞══════════╪══════════════════╪══════════════════╡
        │ null     ┆ [0.9952, 0.9940] ┆ [0.9994, 0.9988] │
        └──────────┴──────────────────┴──────────────────┘
        ```
        """

        # Product is not available on LazyFrame, need to use select with expressions
        # Also need to handle non-numeric columns
        def _product_plan(plan: pl.LazyFrame) -> pl.LazyFrame:
            schema = plan.collect_schema()
            numeric_cols = [
                pl.col(name).product().alias(name)
                for name, dtype in schema.items()
                if dtype.is_numeric()
            ]

            # Add non-numeric columns as nulls to maintain consistent output
            non_numeric_cols = [
                pl.lit(None).alias(name)
                for name, dtype in schema.items()
                if not dtype.is_numeric()
            ]

            return plan.select(numeric_cols + non_numeric_cols).head(1)

        return _aggregate(self, "product", ProductResult, _product_plan)

    def quantile(
        self, quantile: float, interpolation: str = "nearest"
    ) -> QuantileResult:
        r"""Calculate quantile values across all numeric columns.

        Returns a single-row frame containing the specified quantile for each numeric column.
        Essential for risk assessment, percentile-based analysis, and regulatory reporting
        in actuarial applications.

        !!! note "When to use"
            * **Risk Assessment:** Calculate VaR (Value at Risk) at different confidence
                levels (e.g., 95th, 99th percentile) for solvency calculations.
            * **Experience Analysis:** Determine percentile thresholds for large claims,
                high-risk ages, or outlier detection in portfolios.
            * **Pricing Segmentation:** Identify quantile boundaries for premium bands,
                risk tiers, or underwriting categories.
            * **Regulatory Reporting:** Calculate required percentiles for stress testing,
                capital requirements, or reserve adequacy testing.

        Parameters
        ----------
        quantile : float
            Quantile value between 0 and 1 (e.g., 0.5 for median, 0.95 for 95th percentile).
        interpolation : str, default "nearest"
            Interpolation method: "nearest", "higher", "lower", "midpoint", or "linear".

        Returns
        -------
        QuantileResult
            A frame with one row containing quantile values for numeric columns.

        Examples
        --------
        **Scalar Example: Claims Distribution Analysis**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "claim_id": list(range(1, 101)),
            "claim_amount": [
                1000,
                1500,
                2000,
                2500,
                3000,
                3500,
                4000,
                5000,
                6000,
                7500,
                8000,
                9000,
                10000,
                12000,
                15000,
                18000,
                20000,
                25000,
                30000,
                35000,
                40000,
                45000,
                50000,
                60000,
                75000,
                85000,
                95000,
                100000,
                120000,
                150000,
            ]
            + [2000] * 70,
            "processing_days": list(range(5, 35)) + list(range(10, 80)),
        }
        af = ActuarialFrame(data)

        # Calculate key percentiles
        p90 = af.quantile(0.90)
        p95 = af.quantile(0.95)
        p99 = af.quantile(0.99)

        print("90th percentile:")
        print(p90)
        print("\\nClaim amount 90th percentile:", p90["claim_amount"])
        print("Claim amount 95th percentile:", p95["claim_amount"])
        print("Claim amount 99th percentile:", p99["claim_amount"])
        ```

        ```text
        90th percentile:
        shape: (1, 3)
        ┌──────────┬──────────────┬─────────────────┐
        │ claim_id ┆ claim_amount ┆ processing_days │
        │ ---      ┆ ---          ┆ ---             │
        │ f64      ┆ f64          ┆ f64             │
        ╞══════════╪══════════════╪═════════════════╡
        │ 90.0     ┆ 85000.0      ┆ 71.0            │
        └──────────┴──────────────┴─────────────────┘

        Claim amount 90th percentile: 85000.0
        Claim amount 95th percentile: 100000.0
        Claim amount 99th percentile: 150000.0
        ```

        **Vector Example: Portfolio Risk Percentiles**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "product": ["Term Life", "Whole Life"],
            "claim_amounts": [
                [10000, 15000, 20000, 25000, 30000, 35000, 40000, 50000, 75000, 100000,
                 150000, 200000, 250000, 300000, 500000, 750000, 1000000, 1500000, 2000000, 3000000],
                [50000, 75000, 100000, 125000, 150000, 175000, 200000, 250000, 300000, 400000,
                 500000, 600000, 750000, 900000, 1000000, 1250000, 1500000, 2000000, 2500000, 5000000]
            ]
        }
        af = ActuarialFrame(data)

        # Calculate 95th percentile for risk assessment
        var_95 = af.quantile(0.95)
        print("95% VaR by product:")
        print(var_95)
        ```

        ```text
        95% VaR by product:
        shape: (1, 2)
        ┌────────────┬──────────────────────────────────┐
        │ product    ┆ claim_amounts                    │
        │ ---        ┆ ---                              │
        │ str        ┆ list[f64]                        │
        ╞════════════╪══════════════════════════════════╡
        │ null       ┆ [2000000.0, 2500000.0]           │
        └────────────┴──────────────────────────────────┘
        ```
        """
        return _aggregate(
            self,
            "quantile",
            QuantileResult,
            lambda plan: plan.quantile(quantile, interpolation=interpolation),
        )

    # --- The attribute seam: how a name on a frame is resolved ---
    #
    # Three dunders decide what ``af.<name>`` means, and this is the whole
    # order. They stay on the class rather than moving to a module of their
    # own because ``__getattribute__`` runs on EVERY attribute access this
    # framework makes; one more Python call per access is a cost the
    # edit-run-refine loop would pay for nothing.
    #
    # READING ``af.name``:
    #   1. ``__getattribute__`` runs first. Underscore names take the fast
    #      path straight to ``object``. Otherwise, if the class carries the
    #      name AND the frame carries a column of that name, it refuses and
    #      points at ``af["name"]`` -- except for an accessor name, which
    #      wins. Anything the class carries is returned.
    #   2. ``__getattr__`` runs only when step 1 found nothing: accessors
    #      first, then the identifier/keyword/underscore policy, then the
    #      column, then the did-you-mean refusal.
    #
    # WRITING ``af.name = value``:
    #   3. ``__setattr__``, and the order is the answer. A registered
    #      accessor name that is not underscore-prefixed refuses FIRST
    #      (it used to fall through and shadow, silently), above every
    #      branch below, so it refuses even on a frame that carries a
    #      column of that name:
    #      ``af.date = ...`` there does not reassign the column, it
    #      raises, and ``af["date"] = ...`` is the door. Then a name the
    #      frame already holds as a column is reassigned on the frame.
    #      Then any OTHER public name the class carries refuses too, for
    #      the same reason and in the same sentence: it used to fall into
    #      ``object.__setattr__`` and shadow the method -- ``af.sum =
    #      ...`` minting no column and saying nothing -- and ``af.sum``
    #      already READS as a conflict on a frame carrying a column of
    #      that name, so the write matches the read. A known internal is
    #      stored on the instance. Any other valid identifier mints a
    #      column through ``__setitem__``. What the refusal says last
    #      depends on what the name IS: a frame accessor is reached
    #      through ``af.name``, a column accessor as
    #      ``af.some_column.name``, and a method or property is what the
    #      class already carries under that name.
    #
    # The reserved names are the accessors -- ``date``, ``excel``,
    # ``finance``, ``graph``, ``projection`` and anything else in
    # ``_ACCESSOR_REGISTRY`` -- plus Python keywords, plus every
    # underscore-prefixed name. For all of them ``af["name"]`` is the door,
    # reading and writing alike.

    def __getattr__(self, name: str) -> Any:  # noqa: C901, ANN401
        """Dynamically return accessors or provide pandas-style column attribute access.

        Attribute access is the ordinary way to reach a column --
        ``af.sum_assured`` -- and three kinds of name are not reachable that
        way. **The accessor names are reserved**: ``date``, ``excel``,
        ``finance``, ``graph`` and ``projection`` always resolve to the
        accessor, whatever the data carries. A model whose model points
        genuinely include a column called ``date`` still has it, reached as
        ``af["date"]``, and assigned as ``af["date"] = ...``. **Python
        keywords** are not identifiers you can write here (``af["class"]``).
        **Underscore-prefixed names** are the frame's own internals, never
        columns, so ``af._flag`` is refused and ``af["_flag"]`` is the
        spelling for a column of that name.
        """
        # Reserved accessor properties should always resolve via properties
        if name in {"date", "excel", "finance"}:
            return object.__getattribute__(self, name)
        # 1) Accessors precedence (existing behavior)
        kind_dict = _ACCESSOR_REGISTRY.get(name)
        if kind_dict and "frame" in kind_dict:
            AccessorClass = kind_dict.get("frame")
            if AccessorClass:
                accessor_instance = AccessorClass(self)
                # Cache accessor instance to avoid re-instantiation; do not cache columns
                object.__setattr__(self, name, accessor_instance)
                return accessor_instance

        # 2) Identifier validation
        if not isinstance(name, str) or not name.isidentifier():
            msg = f"'{name}' is not a valid attribute name"
            raise AttributeError(msg)
        # 3) Keyword rejection
        if keyword.iskeyword(name):
            msg = f"'{name}' is a Python keyword; use af['{name}'] instead"
            raise AttributeError(msg)
        # 4) Underscore/dunder names disallowed via attribute
        if name.startswith("_"):
            msg = f"'{name}' is not available via attribute access; use af['{name}']"
            raise AttributeError(msg)
        # 5) Conflicts with class attributes/properties/methods (skip if accessor name or reserved name)
        if hasattr(type(self), name):
            kind_dict2 = _ACCESSOR_REGISTRY.get(name)
            if not (kind_dict2 and ("frame" in kind_dict2)) and name not in {
                "date",
                "excel",
                "finance",
            }:
                msg = f"'{name}' conflicts with existing method/attribute; use af['{name}'] instead"
                raise AttributeError(msg)
        # 6) Column attribute access
        if name in self._attr_columns_set:
            return self[name]

        # 7) A Polars method that chooses rows other than by a recorded
        # condition: say why it is not a model step, never that it may be a
        # column the frame does not hold.
        refused = row_choosing_refusal(name)
        if refused is not None:
            raise AttributeError(refused)

        # 8) Unknown attribute: choose error style
        accessor_names = [
            n for n, kinds in _ACCESSOR_REGISTRY.items() if "frame" in kinds
        ]
        has_builtins = any(n in {"date", "excel", "finance"} for n in accessor_names)
        if accessor_names and not has_builtins:
            # In contexts where only custom frame accessors are present (tests patching registry)
            msg = f"No '{name}' frame accessor registered or attribute found."
            raise AttributeError(msg)
        msg = f"'{type(self).__name__}' object has no attribute '{name}'. If '{name}' is a column name, use af['{name}'] instead."
        raise AttributeError(msg)

    def __setattr__(self, name: str, value: Any) -> None:  # noqa: ANN401
        """Support attribute-style column assignment for eligible identifiers."""
        # An accessor name never reaches the column path below --
        # it is excluded there by name -- and further down
        # `object.__setattr__` either stores a shadow (no column minted,
        # later reads returning the stored value where the accessor was) or,
        # for the five accessors declared as properties, raises Python's own
        # "has no setter", which says nothing about columns. Both leave an
        # actuary who wrote `af.date = ...` believing a column exists.
        # Refuse, and say which door works. The predicate is the registry
        # itself, which is the set that fell through here.
        #
        # Where the last clause sends the reader depends on the KIND the
        # name is registered under, because that is what decides where
        # `af.<name>` goes. `__getattr__` returns a FRAME accessor and
        # nothing else does, so a name carrying only a COLUMN accessor
        # reaches no accessor through `af.<name>`: it raises the
        # did-you-mean AttributeError, or hands back the user's own column
        # where the frame carries one. A column accessor hangs off a
        # column -- `af.<column>.<name>` -- and that is what it is told.
        # A refusal that names the next move has to be right about it.
        #
        # Hoisting this check above the two branches below left each of
        # them with a registry test of its own that nothing can reach:
        # the column branch's `and name not in _ACCESSOR_REGISTRY` and the
        # attribute branch's `or name in _ACCESSOR_REGISTRY`. Both are
        # gone, so the seam tests the registry once.
        #
        # Underscore names are excluded, as they are on the two branches
        # below, because they are never column names: `af._flag = ...` is
        # refused further down whatever the registry holds, and the frame's
        # own internals are stored. Without the exclusion an entry under an
        # internal name -- `_ACCESSOR_REGISTRY["_df"] = {}`, which only a
        # direct write to the registry makes -- turned `self._df = ...`
        # inside `__init__` into this refusal, and no ActuarialFrame could
        # be built at all.
        if not name.startswith("_") and name in _ACCESSOR_REGISTRY:
            destination = _accessor_read_destination(name, _ACCESSOR_REGISTRY[name])
            msg = (
                f"'{name}' is a registered accessor name, so "
                f"af.{name} = ... created no column. Use "
                f"af['{name}'] = ... to write a column called "
                f"'{name}'; {destination}"
            )
            raise AttributeError(msg)
        # Reassignment of an existing eligible column must update the frame.
        # Without this check the hasattr guard below matches (reads of column
        # names resolve via __getattr__), so the value would be stored as an
        # instance attribute: collect() keeps the stale column while reads
        # return the shadow, and the two silently diverge.
        if not name.startswith("_"):
            try:
                attr_columns = object.__getattribute__(self, "_attr_columns_set")
            except AttributeError:
                attr_columns = None
            if (
                attr_columns is not None
                and name in attr_columns
                and not hasattr(type(self), name)
            ):
                self[name] = value
                return None
        # The accessor refusal above, again, for the names it cannot reach. It
        # is keyed on `_ACCESSOR_REGISTRY`; every OTHER public name the class
        # declares fell past it into `object.__setattr__` below, which stored
        # the expression on the instance, minted no column and said nothing.
        # `af.sum = af.a + af.b` is the shape -- `sum`, `count`, `min`, `max`
        # and `product` are ordinary model-point field names -- and the worst
        # of them is `collect`, whose shadow is silent at the assignment and
        # surfaces later as "'ExpressionProxy' object is not callable", naming
        # neither the column meant nor the line that wrote it. The three
        # read-only properties -- `columns`, `dtypes`, `schema` -- already
        # refused, with Python's own "has no setter", which says nothing about
        # columns; they arrive here for the sentence, not for the behaviour.
        #
        # The predicate is the class itself, so a method added later is
        # covered the day it lands. It sits BELOW the column-reassignment
        # branch on purpose: that branch's `not hasattr(type(self), name)`
        # is what sends a frame carrying a real column called `sum` here
        # rather than reassigning it, which matches how `af.sum` READS on
        # such a frame -- a conflict, not the column. Brackets are the door
        # on both sides.
        if not name.startswith("_") and hasattr(type(self), name):
            kind = _frame_attribute_kind(name, getattr(type(self), name, None))
            msg = (
                f"'{name}' is a name ActuarialFrame already uses, so "
                f"af.{name} = ... created no column. Use "
                f"af['{name}'] = ... to write a column called "
                f"'{name}'; {kind}"
            )
            raise AttributeError(msg)
        # Reserved/internal or existing attributes: normal behavior
        if hasattr(self, name) or hasattr(type(self), name):
            return object.__setattr__(self, name, value)

        # Allow setting known internal/private attributes
        if name.startswith("_"):
            # Known internal fields
            known_internal = {
                "_df",
                "_ActuarialFrame__df",
                "_column_order",
                "_attr_columns_set",
                "_schema",
                "_schema_generation",
                "_mode",
                "_verbose",
                "_threads",
                "_show_query_plan",
                "_traced_run",
                "_baseline_df",
                "_sealed_windows",
                "_selections",
                "_calculations",
                "_calculation_counts",
                "_next_operation_id",
                "_window_start",
                "_initial_columns",
                "_arrival_names",
                "_bare_arrivals",
                "_arrival_schema",
                "_arrival_data",
                "_book_columns",
                "_rebuilt",
                "_collected_values",
                "_last_run",
                "_retained_values",
                "_retained_for",
                "_retained_columns",
                "_retain_superseded",
                "_wide_judged",
                "_rollforward_runs",
                "_held_reads",
                "_rollforward_scans",
                "_record_roots",
                "_date_accessor_instance",
                "_excel_accessor_instance",
                "_finance_accessor_instance",
                "_projection",
            }
            if (name in known_internal) or hasattr(type(self), name):
                return object.__setattr__(self, name, value)
            # Otherwise underscore names are not valid for column assignment
            msg = f"'{name}' is not a valid attribute name; use af['{name}'] = ..."
            raise AttributeError(msg)

        # Enforce identifier policy for column assignment
        if (
            (not isinstance(name, str))
            or (not name.isidentifier())
            or keyword.iskeyword(name)
        ):
            msg = f"'{name}' is not a valid attribute name; use af['{name}'] = ..."
            raise AttributeError(msg)

        # Treat as column assignment and delegate to __setitem__
        self[name] = value
        return None

    def __getattribute__(self, name: str) -> Any:  # noqa: ANN401
        """Intercept attribute access to raise on method/attribute conflicts with columns."""
        # Allow internals fast-path
        if not isinstance(name, str) or name.startswith("_"):
            return object.__getattribute__(self, name)

        cls = type(self)
        # If the attribute exists on the class (method/property) AND is also an eligible column,
        # raise a clear conflict error to guide users to bracket notation.
        if hasattr(cls, name):
            # Accessor names should NOT raise conflict; they must win
            kind_dict = _ACCESSOR_REGISTRY.get(name)
            is_accessor_name = bool(kind_dict and ("frame" in kind_dict))
            # Reserved accessor property names should not raise either
            if name in {"date", "excel", "finance"}:
                return object.__getattribute__(self, name)
            try:
                attr_set = object.__getattribute__(self, "_attr_columns_set")
            except Exception:  # noqa: BLE001
                # Initialization edge-cases: defer to default behavior
                return object.__getattribute__(self, name)
            if (name in attr_set) and (not is_accessor_name):
                msg = f"'{name}' conflicts with existing method/attribute; use af['{name}'] instead"
                raise AttributeError(msg)
        return object.__getattribute__(self, name)

    # --- Dunder Methods ---

    # ADDED: columns property
    @property
    def columns(self) -> list[str]:
        """Return the names of the columns in the current order."""
        # Use the explicitly tracked order, as the underlying LazyFrame schema
        # might not reflect changes made via assign/with_columns until collect.
        # if self._df is not None:
        #     try:  # noqa: ERA001
        #         # Note: .columns on LazyFrame is okay, schema resolution is the expensive part
        #         return self._df.columns  # noqa: ERA001
        #     except Exception:  # noqa: ERA001
        #         pass # Fallback to tracked order if error  # noqa: ERA001
        return self._column_order

    @property
    def schema(self) -> pl.Schema:
        """Return every column this frame holds and the dtype of each.

        Read off the plan and never out of the data. The answer is
        ``LazyFrame.collect_schema()`` -- Polars resolves the types through
        the query without evaluating a row of it -- so asking a frame what
        shape it is in never runs a projection to find out, and never forces
        a collect for a question that was only ever about metadata.

        Names come back in the order :attr:`columns` reports them, which is
        the order the model wrote them in, so ``dict(zip(af.columns,
        af.dtypes))`` is this mapping. A frame holding no data at all has an
        empty schema, exactly as it has no columns.

        **The frame's own working is not in it.** Two kinds of column live in
        the plan without being columns of the model -- the rollforward
        kernel's scratch struct (:func:`_kernel_scratch_prefix`) and the
        output of a definition a later write replaced
        (:func:`_retained_column_name`) -- and neither is anything a model
        wrote or a reader can ask about. Leaving them in would break the zip
        above, which is not a cosmetic loss: the two lists would be different
        lengths and every column after the first hidden one would be paired
        with somebody else's type.

        **``schema`` is a reserved attribute name**, as ``columns`` is. A
        model whose data really does carry a column called ``schema`` still
        has it -- reach it as ``af["schema"]`` -- and ``af.schema`` refuses
        rather than quietly choosing which of the two was meant.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> af = ActuarialFrame(
            ...     pl.DataFrame({"sum_assured": [100_000.0], "issue_age": [45]})
            ... )
            >>> af.death_claims = af.sum_assured * 0.00123
            >>> af.schema["death_claims"]
            Float64

            A dtype is a fact about the plan, so a model can read one before
            anything is computed. A ``scenario_id`` holding labels names rate
            scenarios; one holding integers indexes simulations, and the two
            discount differently:

            >>> scenarios = ActuarialFrame(pl.DataFrame({"scenario_id": ["BASE"]}))
            >>> scenarios.schema.get("scenario_id") == pl.String
            True

            A label is a label however it was stored, so a criterion that
            means "this column holds labels" has to be written wide enough to
            say so: ``in (pl.String, pl.Categorical, pl.Enum)``. A
            low-cardinality label is exactly the column a writer
            dictionary-encodes, and ``pl.read_parquet`` hands that back as
            ``Categorical`` -- which ``== pl.String`` sends down the branch
            meant for something else, without a word about having done so.

        """
        resolved = self._schema
        if resolved is None:
            return pl.Schema()
        hidden = (_kernel_scratch_prefix(), _RETAINED_PREFIX)
        return pl.Schema(
            {
                name: dtype
                for name, dtype in resolved.items()
                if not name.startswith(hidden)
            }
        )

    @property
    def dtypes(self) -> list[pl.DataType]:
        """Return the dtype of every column, in :attr:`columns` order.

        The same reading as :attr:`schema`, taken positionally rather than by
        name -- and taken the same way, off the plan, with nothing evaluated.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> af = ActuarialFrame(
            ...     pl.DataFrame({"sum_assured": [100_000.0], "issue_age": [45]})
            ... )
            >>> af.dtypes
            [Float64, Int64]

        """
        return list(self.schema.values())

    def __dir__(self) -> list[str]:
        """Enhance dir() to include eligible column names and registered frame accessors."""
        attrs = set(super().__dir__())
        # Add methods from the underlying LazyFrame if available
        if hasattr(self, "_df") and self._df is not None:
            try:
                df_methods = [
                    attr for attr in dir(self._df) if not attr.startswith("_")
                ]
                attrs.update(df_methods)
            except Exception:  # noqa: BLE001, S110
                pass
        # Add registered frame accessor names
        accessor_names = [
            name for name, kinds in _ACCESSOR_REGISTRY.items() if "frame" in kinds
        ]
        attrs.update(accessor_names)
        # Add attribute-eligible column names
        attrs.update(self._attr_columns_set)
        return sorted(attrs)

    # --- Internal helpers ---
    def _refresh_attr_columns_set(self) -> None:
        """Recompute the set of columns that are valid for attribute access."""
        eligible: set[str] = set()
        for c in self._column_order:
            if (
                isinstance(c, str)
                and c.isidentifier()
                and (not keyword.iskeyword(c))
                and (not c.startswith("_"))
            ):
                eligible.add(c)
        self._attr_columns_set = eligible

    def __repr__(self) -> str:
        """Return a string representation of the ActuarialFrame."""
        if self._df is None:
            return "ActuarialFrame(uninitialized)"

        try:
            # The model's own columns, which is what the names beside the
            # count are: the plan also carries the rollforward kernel's
            # scratch struct and any superseded definition held for an
            # export, and counting those would print a number the column
            # list under it cannot account for.
            num_cols = len(self.schema)
            shape_info = f"shape: ({num_cols} columns)"

            # For better representation, show a sample of columns
            cols_preview = ", ".join(self._column_order[:5])
            if len(self._column_order) > 5:  # noqa: PLR2004
                cols_preview += ", ..."

            mode_info = f"mode: {self._mode}"

            return f"ActuarialFrame({shape_info}, cols: [{cols_preview}], {mode_info})"  # noqa: TRY300
        except Exception:  # noqa: BLE001
            # Fallback if we can't calculate schema
            return (
                f"ActuarialFrame(cols: {len(self._column_order)}, mode: {self._mode})"
            )


# What the API reference documents from this module.
__all__ = ["ActuarialFrame"]
