# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The calculation-record vocabulary: what the durable calculation log stores.

Every column an ``ActuarialFrame`` computes reduces, by assignment time, to
one semantic node (see ``gaspatchio._semantic.ir``) and the Polars
expression ``lower_polars`` derives from it. ``CalculationRecord`` is the
one shape that holds both together, alongside where the column's defining
statement lives in the user's own source, and where the calculation itself
came from. ``BoundaryRecord`` marks the one event that mints no column at
all -- a materialization -- and ``OverwriteRecord`` the one that defines a
column the frame cannot read -- a write straight into its query plan -- so
the log stays one append-only sequence (``LogEntry``) instead of several
things a reader has to reconcile.

Two things this module is deliberately narrow about:

- **These are engine-room records, not the audit artifact.**
  ``CalculationRecord.expr`` holds a live Polars expression -- a real engine
  object that never leaves the process. The engine-free artifact a reviewer
  or a regulator actually reads (formula text, dtype, a stable fingerprint,
  no live engine object) is folded out of these records by
  ``gaspatchio.frame.graph`` and reached as ``af.graph``; this module only
  defines what the frame keeps in memory while a model runs.
- **Nothing here writes to a frame.** Every dataclass below is plain data,
  and ``capture_source_span`` only reads the call stack and the source of
  whatever module is calling it. Deciding *when* a record gets minted, what
  ``operation_id`` and ``origin`` it gets, and appending it to a frame's own
  log belongs to ``ActuarialFrame._record_calculation`` in
  ``gaspatchio.frame.base``.

``capture_source_span`` is the one function here with real behavior. Given
nothing but the live call stack, it walks past every frame the framework or
the interpreter contributes -- ``is_framework_or_interpreter_file``, the rule
the error locators follow too -- and hands the first frame outside it to the
``executing`` library, which maps a frame's live bytecode position back to
the exact AST statement responsible for it. That resolution is what lets a
plain ``af.column = ...`` line report itself correctly even though that text
never appears anywhere near where this function actually gets called from
(deep inside an assignment dunder), what lets a helper function's own
assignment report the helper's line rather than whatever line called the
helper, and what lets a multi-line conditional chain wrapped in parentheses
be captured whole rather than truncated to one physical line.

Every failure mode -- an unresolvable frame, source the interpreter cannot
read back (stdin, an ``exec``-compiled snippet, ``compile(..., '<string>')``,
a bare REPL, certain comprehension frames), an ambiguous AST match --
degrades to ``source=None``. A missing calculation is a smaller loss than a
model run that dies partway through recording one. A notebook cell is not
one of those cases: IPython registers cell source in ``linecache``, so a
cell resolves like a file.
"""

from __future__ import annotations

import ast
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import executing
from loguru import logger

from gaspatchio._source import SourceSpan, is_framework_or_interpreter_file

if TYPE_CHECKING:
    import types
    from collections.abc import Callable

    import polars as pl

    from gaspatchio._semantic.ir import OpNode

# Where one CalculationRecord's node came from:
#   assignment  -- a plain af.column = ... / af["column"] = ... call
#   batch       -- a column a single with_columns() call produced, whatever the
#                  number of columns that call defined alongside it
#   rollforward -- a compiled rollforward's own within-period state bookkeeping
#   rename      -- a renamed column's identity carried forward under a new name
#   join        -- a column arriving from the right side of a join
#   projection  -- the projection timeline's own configuration record
#   date        -- a column the date accessor derived onto a new frame
#   continuation -- a column that came back through `continue_from=` holding
#                  values the donor's calculations do not account for: data
#                  from outside the frame, located at the statement that
#                  brought it back in
RecordOrigin = Literal[
    "assignment",
    "batch",
    "rollforward",
    "rename",
    "join",
    "projection",
    "date",
    "continuation",
]


@dataclass(slots=True, frozen=True)
class MintedColumns:
    """The columns one derivation step made itself, and where they came from.

    A step that hands back a new frame -- the date accessor exploding a
    timeline out of a start and an end, say -- carries the calculation log
    onto that successor and, in the same call, records the columns it
    created for itself. Those two facts are one fact: the origin labels
    exactly these columns, and a column with no origin is not a column any
    step made.

    Holding them in one value is what keeps them one fact. Named
    separately, with a label that could be left out, a caller could hand
    over columns and let the label fall to whatever the default was --
    recording a plain assignment's provenance for a column no assignment
    ever wrote.

    ``source`` is where the step happened, said by a caller that already
    knows. The ordinary answer is None: :func:`capture_source_span` walks
    out of this framework's own frames to the line the modeller wrote, and
    that is the right answer whenever a model or a script made the call.
    It is the wrong answer when the call was made *on their behalf* -- an
    exporter running a scenario plan stands between the step and every
    line of theirs, so the walk leaves this framework into whatever
    library happens to sit below the exporter and names a line in it.
    Such a caller states the site instead of letting the walk guess at
    one, and the record then points where a reader can act.
    """

    origin: RecordOrigin
    columns: dict[str, tuple[OpNode, pl.Expr]]
    source: SourceSpan | None = None


@dataclass(slots=True)
class CalculationRecord:
    """One column's calculation: its node, its derived expression, and its origin.

    Mutable, unlike ``SourceSpan``/``BoundaryRecord`` -- a caller may know a
    record's cheaper fields before the more expensive ones (e.g. an
    incrementally-resolved ``dtype``) are available, and updates the same
    record in place rather than rebuilding it.
    """

    column: str
    # 1-based count of assignments this column has received so far:
    # death_claims's first assignment is ordinal 1, a later reassignment is 2.
    ordinal: int
    # One id per single-column assignment; one id SHARED across every
    # record a single multi-column with_columns() call produces.
    # Transaction boundaries are recorded as data here, never inferred
    # from adjacency later.
    operation_id: int
    node: OpNode
    # Derived from `node` by the lowering layer at assignment time --
    # stored here so replay never has to lower the same node twice.
    expr: pl.Expr
    dtype: pl.DataType | None
    source: SourceSpan | None
    origin: RecordOrigin


@dataclass(slots=True, frozen=True)
class BoundaryRecord:
    """A marker that no column was defined here -- something reset the frame's plan.

    ``position`` is this record's own index into the log, so a reader can
    locate it without a separate pass over everything before it.

    ``source`` is where the reset was asked for, captured at the call the
    same way a calculation's is and for a sharper reason. Freezing a plan
    is the one event that changes what every live column *is* without
    changing what any of them says: downstream of it a computed reserve
    behaves like a figure the model was handed. A reader who can see that a
    value was frozen but not where the freeze was written has to find the
    statement by reading the whole model. ``None`` wherever capture found
    nothing, which says the location was looked for rather than guessed at.
    """

    kind: Literal["materialization"]
    position: int
    source: SourceSpan | None


@dataclass(slots=True, frozen=True)
class OverwriteRecord:
    """A column the frame accounted for, written over past its recording doors.

    A model can assign the frame's query plan itself -- ``af._df = ...`` --
    and that write leaves no calculation behind. Where it defines a column
    the frame had accounted for, a calculation it logged or a column the
    data arrived with, the account stops being true: the column holds what
    the write computed, and the log says what it replaced. This entry is
    the frame saying so, at the position the write happened.

    It is a definition the frame saw and cannot read, so it takes the
    column's next ordinal, as an assignment would, and the calculation
    graph mints a hole for it under that version. A calculation written
    after it reads the hole, and the definition it replaced stays as
    history.

    ``readable`` is False where the frame could not read which columns the
    write defined, and recorded every column it accounted for that the plan
    still held rather than guess which moved. ``rescanned`` is True where
    the plan written was nothing but a table in memory -- values handed over
    in place of a plan, as ``af._df.collect().lazy()`` hands them -- which
    is a freeze the frame did not see rather than a calculation it could
    not read. ``dtype`` is the type the
    column holds after the write, read off the plan the write handed over,
    or None where that plan could not say. ``operation_id`` is shared by
    every column one write overwrote, as it is by the columns of one
    ``with_columns`` call. ``source`` is the line of the write, found the
    way a calculation's is.
    """

    column: str
    ordinal: int
    operation_id: int
    dtype: pl.DataType | None
    source: SourceSpan | None
    readable: bool = True
    rescanned: bool = False


# Which rows a selecting step keeps: those its predicate holds for, those a
# second table's key matches, or those it does not match.
SelectionKind = Literal["filter", "semi", "anti"]


@dataclass(slots=True, frozen=True)
class SelectionRecord:
    """One step that chose which policies the model values, kept for the record.

    ``af.filter(...)`` and a semi or anti join define no column, so no
    calculation records them -- and they are the first assumption a reviewer
    challenges: which policies are in this total? The frame keeps one of
    these per step, in the order the model took them, and the graph carries
    them into the document's ``selection`` list, both fingerprints, the
    book's columns and every replay.

    ``node`` is what the step decides with: the predicate's op-tree for a
    filter, and for a semi or anti join the ``join`` call that names the key,
    the join type and the right side's content identity. ``position`` is how
    many entries the calculation log held when the step was taken, so a
    predicate reading a column binds to the definition that column held then,
    as any formula's read does. ``source`` is the line. A join's right side
    is not held here: it is filed under its content identity when the join
    takes it, as any join's is, and the document carries it from there.
    """

    kind: SelectionKind
    node: OpNode
    position: int
    source: SourceSpan | None


# The append-only log's element type: a column's calculation, a marker that
# nothing was defined at that position, or a column written over past the
# doors that record. A boundary mints no column and an overwrite carries no
# calculation, so neither can be a CalculationRecord -- widening the log's
# element type is what lets one append-only sequence hold every kind of
# event truthfully.
LogEntry = CalculationRecord | BoundaryRecord | OverwriteRecord


# Which structural door a plan went through. Every name here is one call
# site that swaps the frame's plan without a replayable record: the six
# frame methods, the projection timeline's stamp, a date verb's stamp, and a
# compiled rollforward materialising its hidden state column.
StructuralKind = Literal[
    "filter",
    "sort",
    "select",
    "drop",
    "rename",
    "join",
    "projection",
    "date",
    "rollforward",
]


@dataclass(slots=True, frozen=True)
class StructuralOperation:
    """One structural operation a plan went through, kept replayable.

    ``kind`` names the door, and ``apply`` is the callable the frame ran its
    own plan through -- the very one, not a description of it, so running
    another plan through it performs the operation the frame performed. The
    callable closes over what the operation was given (a predicate, a sort
    key, a mapping, a right-hand table): immutable engine objects, or copies
    the frame took at the call.

    Held on a :class:`SealedWindow` so that a calculation named on the
    window's own baseline can be confirmed on the rows the operation kept:
    the candidate alone, over its clean prefix, run through the window's
    operations and collected on the replay's head. What that confirms, and
    why a calculation that collects there is not evidence, is
    ``search_collect_failure``'s.

    The callable is a closure a door built, which pickle cannot carry: it
    is dropped at pickle time, ``apply`` reads ``None`` on the other side,
    and a window replayed there declines to confirm through it rather than
    pretend (``confirmed_on_kept_rows``). A deep copy shares the object.
    Run a plan through the operation with ``applied_to``, which is where
    the missing callable is refused, so both the doors that build one and
    the replay that kept one meet that refusal in the same place.
    """

    kind: StructuralKind
    apply: Callable[[pl.LazyFrame], pl.LazyFrame] | None

    def applied_to(self, plan: pl.LazyFrame) -> pl.LazyFrame:
        """Return ``plan`` run through this operation, or refuse without a callable.

        A door-built operation always has its callable; one that came
        through a pickle never does, and there is nothing honest to run, so
        this raises rather than returning the plan unchanged. What that
        refusal means to a walk-back -- declining rather than pretending --
        is ``confirmed_on_kept_rows``'s.
        """
        if self.apply is None:
            msg = f"({self.kind}) came through a pickle without its callable"
            raise TypeError(msg)
        return self.apply(plan)

    def __reduce__(
        self,
    ) -> tuple[type[StructuralOperation], tuple[StructuralKind, None]]:
        """Pickle the kind alone; the closure stays behind."""
        return (StructuralOperation, (self.kind, None))

    def __deepcopy__(self, memo: dict[int, object]) -> StructuralOperation:
        """Share rather than copy: a frozen name and an immutable closure."""
        return self


def with_columns_operation(
    kind: StructuralKind, *exprs: pl.Expr, **named: pl.Expr
) -> StructuralOperation:
    """Return the operation that stamps ``exprs`` onto a plan, as the frame stamps them.

    The shape three doors share -- the projection timeline, a date verb's
    offset and a rollforward's hidden column each ``with_columns`` what they
    were given -- written once, so each site holds the callable it ran
    rather than a lambda closing over a loop variable.
    """

    def apply(plan: pl.LazyFrame) -> pl.LazyFrame:
        return plan.with_columns(*exprs, **named)

    return StructuralOperation(kind=kind, apply=apply)


@dataclass(slots=True, frozen=True)
class SealedWindow:
    """An attribution window a structural operation closed, kept replayable.

    A window is a run of calculations plus the plan they were applied to.
    ``filter``, ``sort``, ``select``, ``drop``, ``rename``, ``join``, the
    projection timeline, a date verb and a rollforward's materialisation all
    change the plan without leaving a replayable record, so a window cannot
    straddle one: a record from before such an operation, replayed on top of
    the plan from after it, would name the wrong column.

    What follows from that is that the window ENDS there, not that it stops
    being true. ``records`` applied to ``baseline`` reconstruct exactly the
    plan the frame held one step before the operation -- a plan the model
    really built. An error a replay reproduces against it, same class and
    same leading message line, is evidence about that baseline's rows --
    and the rows the operation went on to drop are among them, so a
    calculation that fails only there reproduces here and never raised in
    the plan the user collected. That is why the search reaches a sealed
    window only when no window ahead of it could be searched, and why a
    candidate it finds is confirmed on the rows ``operations`` keep before
    it is named; the rule and its reason are ``search_collect_failure``'s.
    Sealing is what keeps the window reachable once the cursor has moved
    past.

    ``operations`` are the structural operations the plan went through from
    this window's seal to the next window's baseline, in order: the one that
    sealed it, then every one that followed before another record landed.
    A second operation over an empty window is recorded here rather than
    lost, because the rows the plan keeps are the rows that survive all of
    them. ``records`` on ``baseline``, then each operation in turn, is the
    plan the next window opened over. The chain is bounded, the newest
    kept: a run of structural calls long enough to reach
    ``_MAX_WINDOW_OPERATIONS`` costs more to carry than the confirmation
    it buys, and the bound is stated where it is defined.

    ``records`` are the log's own objects, not copies: a record a later step
    sharpens (a dtype resolved after the fact) is sharpened here too,
    because it is the same record. ``baseline`` is a plan, never data --
    snapshots of one growing plan share their structure, so a model's sealed
    windows cost one plan between them rather than one each.
    """

    records: tuple[CalculationRecord, ...]
    baseline: pl.LazyFrame | None
    operations: tuple[StructuralOperation, ...] = ()


# Set to skip capture entirely and return `None` unconditionally, for a run
# that wants the calculation log's other bookkeeping without paying the
# frame-walk/AST cost on every assignment. Read fresh on every
# `capture_source_span` call rather than cached once at import: a
# module-level cache would only see whichever value was in effect the
# moment this module first got imported -- the same import-order fragility
# `gaspatchio.util`'s `_DEFAULT_MODE`/`_DEFAULT_VERBOSE`/`_DEFAULT_ERROR_MODE`
# globals already have. One `os.environ.get` call costs a dict lookup,
# negligible next to the walk it guards, and it keeps the switch toggleable
# within a single process (a test can flip it with no reload gymnastics).
_SOURCE_SPANS_ENV_VAR = "GASPATCHIO_SOURCE_SPANS"
_SOURCE_SPANS_OFF_VALUE = "off"

# What a module-level frame's code object calls itself. It marks the absence
# of an enclosing scope rather than naming one, so it is turned into `None`
# at capture and never reaches a record.
_MODULE_SCOPE_NAME = "<module>"


def capture_source_span() -> SourceSpan | None:
    """Capture the statement-scoped source span of the calculation being recorded.

    Walks the live call stack past every frame this framework's own
    machinery contributes, then resolves the first frame outside it to the
    AST statement it is currently executing. Never raises: any failure in
    the frame walk, the source resolution, or the AST parse degrades to
    ``None`` rather than breaking the assignment that asked for it.

    Set the ``GASPATCHIO_SOURCE_SPANS`` environment variable to ``"off"`` to
    skip capture entirely -- every call then returns ``None`` immediately,
    before the frame walk or any AST work runs. That switch costs an
    exported calculation graph its whole audit surface rather than only its
    locations: the as-written ``formula`` and ``source_location`` are both
    read off this span, so with it off every computed node reports null for
    both and the graph is left with its structure and its fingerprints and
    no readable calculation anywhere in it.
    """
    if os.environ.get(_SOURCE_SPANS_ENV_VAR) == _SOURCE_SPANS_OFF_VALUE:
        return None
    try:
        frame = _nearest_external_frame()
        if frame is None:
            return None
        return _span_from_frame(frame)
    except Exception as exc:  # noqa: BLE001 -- capture must never break the caller
        logger.trace(f"capture_source_span: degrading to None ({exc!r})")
        return None


def _nearest_external_frame() -> types.FrameType | None:
    """Return the nearest live frame outside the framework's own call chain."""
    frame: types.FrameType | None = sys._getframe(1)  # noqa: SLF001 -- intended use
    while frame is not None and _is_internal_frame(frame):
        frame = frame.f_back
    return frame


def _is_internal_frame(frame: types.FrameType) -> bool:
    """Return whether ``frame`` runs the framework's code or the interpreter's.

    ``is_framework_or_interpreter_file`` decides, the rule the error
    locators follow too, so a source span and an error's location draw the
    line between the model author's code and everyone else's in one place.
    """
    return is_framework_or_interpreter_file(frame.f_code.co_filename)


def _span_from_frame(frame: types.FrameType) -> SourceSpan | None:
    """Resolve one external frame to the statement it is currently executing.

    ``None`` whenever the resolution is not unambiguous: no statement found
    for the frame's line (no retrievable source -- stdin, an
    ``exec``-compiled snippet, ``compile(..., '<string>')``, a bare REPL;
    a notebook cell is not one of these, since IPython registers its source
    in ``linecache``), or more than one candidate statement (a
    semicolon-separated compound line ``executing`` could not disambiguate
    further).
    """
    execution = executing.Source.executing(frame)
    statements = execution.statements
    if len(statements) != 1:
        return None
    (statement,) = statements
    source = execution.source
    if not source.text:
        return None
    statement_text = _source_segment(source, statement)
    if not statement_text:
        return None
    written_value = _written_value(statement)
    rhs_text = (
        _source_segment(source, written_value) if written_value is not None else None
    )
    end_line = (
        statement.end_lineno if statement.end_lineno is not None else statement.lineno
    )
    return SourceSpan(
        file=frame.f_code.co_filename,
        line=statement.lineno,
        end_line=end_line,
        function=_enclosing_function(frame),
        statement=statement_text,
        rhs=rhs_text,
        target_literal=_target_literal(statement),
    )


def _enclosing_function(frame: types.FrameType) -> str | None:
    """Return the scope ``frame`` is executing in, or None at module level.

    Read from the frame's own code object, which qualifies the name through
    whatever it is nested in -- a method reports ``Projection.run`` rather
    than the bare ``run`` it shares with every other class in the file, and
    a closure reports ``main.<locals>.helper``. Both are what a reader
    needs to find the line; a bare name sends them searching.

    A module-level frame names itself ``"<module>"``. That is the
    interpreter's placeholder for "no enclosing scope", not a scope, so it
    becomes ``None`` here -- once, at capture, so no renderer downstream has
    to know the sentinel exists.
    """
    qualified_name = frame.f_code.co_qualname
    return None if qualified_name == _MODULE_SCOPE_NAME else qualified_name


def _source_segment(source: executing.Source, node: ast.stmt | ast.expr) -> str | None:
    """Return the source text ``node`` was parsed from.

    Returns what ``ast.get_source_segment(source.text, node)`` returns, and
    is deliberately not that call. The standard-library helper re-splits the
    source from the top of the file every time it runs, so reading one
    statement costs however far down the file that statement sits -- and
    capture reads two of them, the statement and its right-hand side, on
    every single assignment. A model whose columns are defined two hundred
    lines in pays two hundred lines of re-scanning, twice per column, to
    return text the process is already holding.

    ``executing`` has already split the same file into ``source.lines`` and
    keeps it for the life of the process, so the segment is a direct index
    into that list: the same characters, at a cost set by the length of the
    statement rather than by its position in the file.

    The contract, stated exactly:

    - ``None`` when the node carries no end position, which is what
      ``ast.get_source_segment`` returns for the same node.
    - ``None`` when the node names a line the split source does not have.
      This is the one place the two answers differ: the standard library
      raises ``IndexError`` there. A node can outrun its source whenever the
      file shrinks between one read and the next, and reporting nothing is
      the more useful answer on a path whose whole job is to describe a
      calculation, not to police the file.
    - Otherwise the segment. A column offset that falls inside a multi-byte
      character -- reachable only when the source and the node disagree, the
      same way -- raises ``UnicodeDecodeError``, exactly as the standard
      library does on that input. The caller, ``capture_source_span``, is
      where that is turned back into ``None``; this function is not itself a
      never-raises boundary and has no other caller.
    """
    end_lineno = node.end_lineno
    end_col_offset = node.end_col_offset
    if end_lineno is None or end_col_offset is None:
        return None
    lines = source.lines
    if end_lineno > len(lines):
        return None
    # Column offsets count bytes rather than characters, so the slice has
    # to happen on the encoded line -- what the standard-library helper
    # does, and the difference between correct and truncated on any line
    # holding a non-ASCII character.
    first = lines[node.lineno - 1].encode()[node.col_offset :]
    if end_lineno == node.lineno:
        return first[: end_col_offset - node.col_offset].decode()
    last = lines[end_lineno - 1].encode()[:end_col_offset]
    # `source.lines` holds the file's lines with their endings stripped and
    # `source.text` is those same lines joined back together, so rejoining a
    # range of them reproduces the text the file's own parse ran on --
    # including for a file written with carriage returns, which arrives here
    # already normalised.
    return "\n".join(
        [first.decode(), *lines[node.lineno : end_lineno - 1], last.decode()]
    )


# The builtin a model writes a column through when the name is only known
# at run time, and where in its call the expression sits. `setattr` is
# recognised by the name it is called under: an attribute call
# (`monkeypatch.setattr(...)`) is a different function that happens to
# share a word, and a keyword or starred call is not the three-argument
# shape whose third argument is a column's value.
_SETATTR = "setattr"
_SETATTR_ARGUMENTS = 3
_SETATTR_VALUE = 2


def _written_value(statement: ast.stmt) -> ast.expr | None:
    """Return the node holding the expression the author wrote, or None.

    Two statements write a column from an expression the author typed, and
    the artifact's ``formula`` is that expression's own text either way.
    One is the plain ``af.claims = ...`` assignment. The other is
    ``setattr(af, name, ...)``, which is what a model reaches for when the
    column's name is only known at run time -- one column per basis, per
    scenario, per table -- because Python's attribute syntax has no dynamic
    form.

    That second shape parses to a call, not an assignment, so a reading
    that recognised only assignments would return nothing for it: the tier
    classifier works from the operation tree and would still say ``core``,
    leaving the artifact claiming a fully portable calculation with no
    readable account of it anywhere. The value argument is that account,
    written by the author, in the same characters an assignment would have
    carried.

    An assignment gives up its right-hand side only when every target it
    writes is a column of a frame. The two shapes that qualify are the ones
    ``_target_literal`` distinguishes between -- ``af.claims = ...`` and
    ``af[name] = ...`` -- and each names one column whose value is the
    expression beside it. A tuple target (``af.a, af.b = x, y``) does not:
    one right-hand side is shared by both columns and computes neither on
    its own. Nor does a name target (``af = af.with_columns(...)``,
    ``af = af.projection.set(...)``), whose value is a whole call that
    mints columns rather than an expression that is any one of them.
    Reported against a single column either would be text that does not
    compute the number beside it -- the reason
    ``graph_builder._as_written`` gives for reading the ``assignment`` door
    alone -- so the rule is applied once, here, where both of that field's
    readers see it: the exported ``formula`` and the error block's quoted
    line.

    Anything else -- an augmented assignment, a bare call that is not this
    builtin -- has no single written expression behind it and returns None,
    which is what the null in the artifact then means.
    """
    if isinstance(statement, ast.Assign):
        if not all(_is_column_target(target) for target in statement.targets):
            return None
        return statement.value
    call = statement.value if isinstance(statement, ast.Expr) else None
    if not isinstance(call, ast.Call) or not _is_setattr_call(call):
        return None
    return call.args[_SETATTR_VALUE]


def _is_setattr_call(call: ast.Call) -> bool:
    """Return whether ``call`` is the builtin writing one column from one value.

    Four things have to hold, and each rules out a call that would
    otherwise hand back text that is not a column's formula. The function
    is called under the builtin's own bare name, so that an attribute call
    sharing the word (``monkeypatch.setattr(...)``) is not mistaken for it.
    It takes no keywords and exactly the three arguments the builtin takes,
    so a call of some other arity is not read positionally. And none of
    those arguments is starred, since ``*rest`` is the name of a sequence
    rather than the expression a column was computed from.
    """
    return (
        isinstance(call.func, ast.Name)
        and call.func.id == _SETATTR
        and not call.keywords
        and len(call.args) == _SETATTR_ARGUMENTS
        and not any(isinstance(argument, ast.Starred) for argument in call.args)
    )


def _target_literal(statement: ast.stmt) -> bool:
    """Return whether ``statement``'s assignment target(s) name their column literally.

    A static property of the parsed statement, independent of the frame it
    came from: an ``ast.Attribute`` target (``af.foo = ...``) always names
    its column literally, since Python attribute syntax has no dynamic
    form. An ``ast.Subscript`` target (``af["foo"] = ...``) is literal only
    when its key is itself a string constant -- ``af[name] = ...`` inside a
    loop is not, because the actual column name is not visible in the
    statement's own text. Anything else (not an assignment at all, or an
    assignment whose target is neither shape) is conservatively False.
    """
    if not isinstance(statement, ast.Assign):
        return False
    return all(_is_literal_target(target) for target in statement.targets)


def _is_column_target(target: ast.expr) -> bool:
    """Return whether one assignment target names a column of a frame.

    The two shapes a column is written through, whether or not the name is
    visible in the text: an attribute (``af.claims``) and a subscript
    (``af["claims"]``, ``af[name]``). A tuple target and a bare name are
    neither, and the statement's right-hand side is then not one column's
    expression -- which is what ``_written_value`` reads this for.
    """
    return isinstance(target, ast.Attribute | ast.Subscript)


def _is_literal_target(target: ast.expr) -> bool:
    """Return whether one assignment target names its column literally."""
    if isinstance(target, ast.Attribute):
        return True
    if isinstance(target, ast.Subscript):
        return isinstance(target.slice, ast.Constant) and isinstance(
            target.slice.value, str
        )
    return False


__all__ = [
    "BoundaryRecord",
    "CalculationRecord",
    "LogEntry",
    "MintedColumns",
    "OverwriteRecord",
    "RecordOrigin",
    "SealedWindow",
    "SelectionKind",
    "SelectionRecord",
    "SourceSpan",
    "StructuralKind",
    "StructuralOperation",
    "capture_source_span",
    "with_columns_operation",
]
