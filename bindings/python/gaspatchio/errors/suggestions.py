# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Advice for a failed calculation, chosen by facts rather than by wording.

Each family below is selected by something the framework already holds:
the exception's class, the op-tree the failing column was written as, the
lowering that op-tree already built, and the dtypes the graph holds for
the definitions that formula read. None is selected by a substring of the
message the user is about to read: polars quotes the user's own column
names in its refusals, so a family chosen that way is a family chosen by
what the actuary happened to call a column.

A class is polars' too, but it is a type rather than a sentence and does
not reword between releases without a deprecation; the lowering and the
dtypes are the framework's own, and each carries its reason at the
constant that names it. What no fact selects earns no advice -- an
attempt converges on the family it is pointed at, so pointing at a guessed
one costs more than pointing at none.

A class is not always enough on its own. Polars hands back everything one
of this repository's own kernels refuses as a ``ComputeError``, which
names no subject, so ``af.a ** af.b`` on a jagged pair said nothing where
``af.a * af.b`` on the same pair said three useful things. The kernel's
own symbol in the lowering (``_LIST_KERNELS``) is what the router reads
instead, and the operand dtypes then say which clash it was.

One string is still parsed: the missing column's NAME
(``_extract_column_name``). A column that is not on the frame is not a
node on the graph, so there is nothing structural to read the name off;
that residue is named here rather than left to be discovered.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, ClassVar, Final, NamedTuple

import polars as pl

from gaspatchio._dtypes import UNKNOWN
from gaspatchio._semantic.ir import Call, Col, walk

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.frame.calculations import CalculationRecord

    from .formatter import GraphFacts

# The graph's own dtype names, grouped by what a clash between them earns.
# The vocabulary is closed and the framework's (_dtypes.py),
# not an engine's display string, which is what makes a test against it a
# fact rather than a reading of a sentence.
_NUMERIC_DTYPES: Final[frozenset[str]] = frozenset({"i64", "f64"})
_TEMPORAL_DTYPES: Final[frozenset[str]] = frozenset({"date", "datetime"})
_LIST_DTYPE_PREFIX: Final[str] = "list["

# Two column names that open with the same this-many characters are scored
# as at least a 0.7 match by the did-you-mean search.
_SHARED_PREFIX = 3

# The op-tree calls that ARE an assumption-table read: the lookup itself,
# and the convention-aware read of a mortality basis that stands for one.
# frame/graph/edges.py names the same two, for the same reason -- both are
# the tree's vocabulary rather than the engine's.
_LOOKUP_CALLS: Final[frozenset[str]] = frozenset({"lookup", "mortality.at"})

# The op-tree call that parses text into a date. A verb that does date
# ARITHMETIC (date.offset_by, excel.edate) is not a parse and does not
# earn the format advice.
_PARSE_CALLS: Final[frozenset[str]] = frozenset({"str.to_date"})

# What a failed text-to-date parse earns. Two lines where the retired
# chain had four: its third named the same two example formats line one
# already carries, and its fourth told the reader to convert Excel serial
# dates with map_elements, which this framework's performance rules forbid
# and which excel.from_excel_serial already does properly.
_DATE_PARSE_ADVICE: Final[tuple[str, ...]] = (
    "Check date format matches your data (e.g., '%Y-%m-%d', '%m/%d/%Y')",
    "Use .str.to_datetime() with format parameter",
)


# The engine's own names for an indexed read, as they appear in the
# serialised expression -- `{"function": {"ListExpr": {"Get": <bool>}}}`
# for a row's own list, `{"ArrayExpr": {"Get": <bool>}}` for a fixed-width
# array -- each with the call the actuary wrote and the word for what the
# row holds. Both raise the same `ComputeError: get index is out of
# bounds` when the index leaves the row, and both take the same two
# remedies, so both are answered; the spelling is carried because an
# actuary whose column is an array has no `.list.get` in the formula to
# pass a flag to.
#
# The payload is `null_on_oob`, and it is the whole of the question: a
# read with it FALSE raises where the index leaves the row's own values,
# and a read with it TRUE reads a null and cannot raise out of bounds at
# all. `list.first()`/`list.last()` and their `arr` siblings are
# `get(0, null_on_oob=True)` and `get(-1, null_on_oob=True)`, so a formula
# that merely CONTAINS an indexed read is not a formula that can fail this
# way -- reading the flag rather than the variant's presence is what keeps
# this family off failures it cannot describe. Named here so the one place
# that depends on polars' serialisation vocabulary is the constant rather
# than the branch.
#
# Four spellings, not two. The same read written INSIDE `list.eval` --
# `af.cashflow.polars_native().list.eval(pl.element().get(7))` -- raises
# the identical `ComputeError: get index is out of bounds` and serialises
# as `{"Eval": {"expr": ..., "evaluation": {"Gather": {... "null_on_oob":
# <bool>}}, "variant": ...}}`, with the same flag under a different key.
# It went unanswered for as long as this family read only the `function`
# slot, which is a distinction the actuary who wrote the read cannot see.
# Its two entries are keyed by the `variant` the `Eval` node carries,
# because that -- not the `Gather` -- is what says whether the row holds a
# list or a fixed-width array.
#
# `bound` is what the read has to stay inside, and it differs in kind
# between the two shapes rather than only in wording. A list's is the
# number of elements THAT ROW holds and varies row to row; an `Array`
# column has one fixed width declared for every row, which still bounds
# the read on a row whose value is null (its length is null, the width is
# not). `length` is the call that counts it, quoted in the remedy because
# that count is where the unsigned wrap lives. `from_projection` is
# whether a projection could have built the values at all:
# `projection.set(...)` materialises `List` columns, never `Array`, so
# offering the grid as a cause to check under an array read offers a cause
# that cannot be the one.
class _Spelling(NamedTuple):
    """How one spelling of an indexed read is spoken back to the actuary."""

    call: str
    holds: str
    bound: str
    length: str
    from_projection: bool


_INDEXED_READS: Final[dict[str, _Spelling]] = {
    "ArrayExpr": _Spelling(
        call=".arr.get",
        holds="array",
        bound="the column's own fixed width",
        length="`.arr.len()`",
        from_projection=False,
    ),
    "ListExpr": _Spelling(
        call=".list.get",
        holds="list",
        bound="the number of elements that row holds",
        length="`.list.len()`",
        from_projection=True,
    ),
    "EvalArray": _Spelling(
        call="pl.element().get",
        holds="array",
        bound="the column's own fixed width",
        length="`.arr.len()`",
        from_projection=False,
    ),
    "EvalList": _Spelling(
        call="pl.element().get",
        holds="list",
        bound="the number of elements that row holds",
        length="`.list.len()`",
        from_projection=True,
    ),
}
_INDEXED_GET_VARIANT: Final[str] = "Get"
_INDEXED_GET_RAISES: Final[bool] = False
_CORE_INDEXED_READS: Final[frozenset[str]] = frozenset({"list.get"})

# The `Eval` node's own keys, and the two `variant` spellings it gives the
# thing being walked: the bare string `"List"`, and `"Array"` as the key of
# a dict carrying its own payload. Read as "which of the two", never
# parsed further.
_SERIALISED_EVAL_OVER: Final[str] = "expr"
_SERIALISED_EVALUATION: Final[str] = "evaluation"
_SERIALISED_EVAL_VARIANT: Final[str] = "variant"
_SERIALISED_GATHER: Final[str] = "Gather"
_SERIALISED_NULL_ON_OOB: Final[str] = "null_on_oob"
_EVAL_VARIANTS: Final[dict[str, str]] = {"Array": "EvalArray", "List": "EvalList"}

# The key the serialised form gives a function node's operands. The list
# a raising read took its element from is the FIRST of them, which is how
# the advice names a real column instead of an example one.
_SERIALISED_OPERANDS: Final[str] = "input"
_SERIALISED_FUNCTION: Final[str] = "function"
_SERIALISED_COLUMN: Final[str] = "Column"

# The framework's OWN elementwise list kernels, by the symbol the lowering
# names them with in the serialised plan (`{"FfiPlugin": {"symbol":
# "list_pow"}}`). Each walks two or more per-row lists together, so each
# refuses when the lists it was handed do not line up -- `**` raises
# `ComputeError: mismatched inner list lengths for list_pow` where the
# identical mismatch written with `*` raises polars' `ShapeError`.
#
# The class is therefore not what says "a length clash" for these: polars
# hands a plugin's refusal back as a `ComputeError`, which carries no
# subject at all, and the family that answered the `*` spelling printed
# nothing for the `**` one. The symbol is the fact instead. It is the
# framework's own name for its own kernel, lowered by
# `frame/lowering/_polars/plugins.py` and read back here out of polars'
# structured plan rather than out of any sentence -- a stronger guarantee
# than the class, because this repository owns both ends of it.
_LIST_KERNELS: Final[frozenset[str]] = frozenset(
    {
        "accumulate",
        "ieee_div",
        "ieee_floordiv",
        "ieee_mod",
        "list_clip",
        "list_conditional",
        "list_pow",
    },
)
_SERIALISED_PLUGIN: Final[str] = "FfiPlugin"
_SERIALISED_SYMBOL: Final[str] = "symbol"

# The graph's dtype names whose VALUES are numbers, list or not. A kernel
# handed `list[f64]` and `str` refused over a type, and the element type is
# what its arithmetic touched, so the cast line is owed to that clash
# exactly as it is owed to `f64` beside `str`.
_NUMERIC_ELEMENTS: Final[frozenset[str]] = frozenset(
    {*_NUMERIC_DTYPES, *(f"{_LIST_DTYPE_PREFIX}{inner}]" for inner in _NUMERIC_DTYPES)},
)


def _call_in(node: OpNode, names: frozenset[str]) -> Call | None:
    """Return the first call within ``node`` whose name is one of ``names``.

    The whole tree is walked rather than only its root: ``af.rate =
    table.lookup(age=af.age) * 12`` is a lookup with a multiply on top of
    it, and the refusal the engine raised came from the lookup.
    """
    for current in walk(node):
        if isinstance(current, Call) and current.name in names:
            return current
    return None


def _reads_a_list(dtypes: frozenset[str]) -> bool:
    """Whether a length clash reads as a jagged-list clash.

    True when the graph named a ``list[...]`` operand, and true as well
    when it named nothing at all -- a question the graph could not answer
    should cost this family its refinement, not its advice. False only
    where the graph did answer and no operand is a list, which is a height
    clash and belongs to no family here.
    """
    return not dtypes or any(dtype.startswith(_LIST_DTYPE_PREFIX) for dtype in dtypes)


def _indexed_read_that_raises(function: object) -> str | None:
    """Return the accessor of one serialised read that can raise, or ``None``.

    Answers about the node's own ``function`` slot -- which polars fills
    with its own enum names -- and about the ``null_on_oob`` flag that
    slot carries. A column the actuary called ``ListExpr`` arrives as the
    string VALUE of a ``Column`` key and can never be the key tested here,
    which is what keeps this a question about the calculation rather than
    about a name someone chose.

    The answer is the key itself rather than a yes, because the advice
    quotes the call the formula holds and the two spellings are not
    interchangeable to the actuary reading it back.

    A variant shaped in any other way answers ``None``. The family cannot
    then say the read is one that raises, and a family that cannot say so
    has nothing to offer the failure.
    """
    if not isinstance(function, dict):
        return None
    for accessor in _INDEXED_READS:
        variant = function.get(accessor)
        if (
            isinstance(variant, dict)
            and variant.get(_INDEXED_GET_VARIANT) is _INDEXED_GET_RAISES
        ):
            return accessor
    return None


def _list_read_from(node: dict[str, object]) -> str | None:
    """Return the column an indexed read took its values from, if it names one.

    The same first operand carries the name for a list read and for an
    array one -- ``{"input": [{"Column": "cashflow"}, ...]}`` either way.
    ``None`` where the values were themselves computed
    (a native ``list.head(3)`` followed by a native ``list.get(5)``), which
    leaves no name for the advice to offer back.
    """
    operands = node.get(_SERIALISED_OPERANDS)
    if not isinstance(operands, list) or not operands:
        return None
    indexed = operands[0]
    if not isinstance(indexed, dict):
        return None
    named = indexed.get(_SERIALISED_COLUMN)
    return named if isinstance(named, str) else None


def _eval_read_that_raises(node: dict[str, object]) -> tuple[str, str | None] | None:
    """Return an ``Eval`` body's raising read and the column it walked, or ``None``.

    An ``Eval`` node is the serialised form of ``list.eval`` /
    ``arr.eval``: ``expr`` is the thing being walked, ``evaluation`` is
    what runs per element, and ``variant`` says which of the two it is.
    The read this family answers appears as a ``Gather`` in the
    ``evaluation`` slot carrying the same ``null_on_oob`` flag a direct
    read carries, and it is read exactly the same way round -- FALSE
    raises, TRUE cannot.

    The column is taken from ``expr`` rather than from the ``Gather``,
    because the ``Gather`` indexes ``Element`` and names nothing. A walked
    value the formula computed (``list.head(1).list.eval(...)``) puts a
    function there instead of a column and answers ``None`` for the name,
    which leaves the advice unnamed rather than borrowing an input's.

    ``None`` for anything that is not this shape -- an ``Agg`` in the
    ``evaluation`` slot is ``pl.element().first()``, which reads a null and
    cannot raise out of bounds at all.
    """
    evaluation = node.get(_SERIALISED_EVALUATION)
    if not isinstance(evaluation, dict):
        return None
    gather = evaluation.get(_SERIALISED_GATHER)
    if (
        not isinstance(gather, dict)
        or gather.get(_SERIALISED_NULL_ON_OOB) is not _INDEXED_GET_RAISES
    ):
        return None
    variant = node.get(_SERIALISED_EVAL_VARIANT)
    named_variant = variant if isinstance(variant, str) else None
    if isinstance(variant, dict):
        named_variant = next((key for key in variant if key in _EVAL_VARIANTS), None)
    if named_variant is None or named_variant not in _EVAL_VARIANTS:
        return None
    walked = node.get(_SERIALISED_EVAL_OVER)
    name = walked.get(_SERIALISED_COLUMN) if isinstance(walked, dict) else None
    return _EVAL_VARIANTS[named_variant], name if isinstance(name, str) else None


def _a_list_kernel_refused(expr: pl.Expr) -> bool:
    """Whether the failing formula was lowered onto one of the framework's own kernels.

    Asked of the lowering rather than of the message, and answered by the
    kernel's own symbol (:data:`_LIST_KERNELS`). What it establishes is
    narrow and is the whole of what the router needs: the thing that
    refused was a kernel this repository wrote, which walks per-row lists
    elementwise, so the refusal is a clash between the operands it was
    handed. WHICH clash -- lengths that do not line up, or a type its
    arithmetic cannot take -- is then read off the operand dtypes, exactly
    as it is for the classes that name a type as their subject.

    ``False`` on an expression polars declines to serialise, which is the
    same silence that costs nothing everywhere else in this module.
    """
    try:
        plan = json.loads(expr.meta.serialize(format="json"))
    except (pl.exceptions.PolarsError, ValueError, TypeError, AttributeError):
        return False
    pending: list[object] = [plan]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            plugin = current.get(_SERIALISED_PLUGIN)
            if isinstance(plugin, dict) and plugin.get(_SERIALISED_SYMBOL) in (
                _LIST_KERNELS
            ):
                return True
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return False


class _RaisingReads(NamedTuple):
    """The indexed reads in one failing formula that could have raised.

    ``accessors`` holds the serialised keys of the reads found, so the
    advice can quote ``.list.get`` or ``.arr.get`` as the formula wrote
    it; where this is built at all it holds at least one. ``lists`` holds
    the columns those reads named, and may be empty -- a read of a list
    the formula computed names nothing the advice can point at.
    """

    accessors: frozenset[str]
    lists: frozenset[str]


def _reads_whose_index_can_raise(expr: pl.Expr, node: OpNode) -> _RaisingReads | None:
    """Return the raising indexed reads a failing formula holds, or ``None``.

    ``None`` says the failing calculation performs no indexed read that
    could have raised at all, so this family is not the one to answer it.
    A pair says it does: the accessors those reads were written with, and
    the columns they named -- empty where the list was computed rather
    than named, and larger than one where the formula indexed more than
    one list, neither of which leaves a single column the advice can
    honestly point at.

    ``record.expr`` is the lowering the assignment already built, so the
    question is asked of the engine that will run it rather than of the
    message it refused with. It has to be asked that way round: an
    ``af.cashflow.polars_native().list.get(...)`` reaches the op-tree as an
    ``EngineNative`` escape hatch, whose ``text`` ``_semantic/ir.py``
    declares opaque outside the named engine -- so the honest reading is
    polars' own structured one, where a function is a key and every name
    the actuary chose is a value. The name this returns is therefore read
    off the read's own operand, never off the message. For a single core
    list.get, the op-tree supplies the receiver name hidden by lowering's
    null checks. It is carried into the advice as TEXT: no family is
    chosen by it. An unnamed read alongside a named one leaves the whole
    formula unnamed rather than attributing both reads to that column.

    Silence on refusal is deliberate and costs nothing: an expression
    polars declines to serialise (a ``map_elements`` closure with no
    pickler) reaches the same empty advice it reached before this family
    existed.
    """
    try:
        plan = json.loads(expr.meta.serialize(format="json"))
    except (pl.exceptions.PolarsError, ValueError, TypeError, AttributeError):
        return None
    reads: list[tuple[str, str | None]] = []
    pending: list[object] = [plan]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            accessor = _indexed_read_that_raises(current.get(_SERIALISED_FUNCTION))
            if accessor is not None:
                reads.append((accessor, _list_read_from(current)))
            walked = _eval_read_that_raises(current)
            if walked is not None:
                reads.append(walked)
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    if not reads:
        return None
    # Core list.get wraps its values in null checks. When the lowering has
    # exactly one raising read, its core receiver still names those values.
    # Do not borrow a column from an index operand or a computed receiver.
    if reads == [("ListExpr", None)]:
        match _call_in(node, _CORE_INDEXED_READS):
            case Call(args=(Col(name=name), _), attrs=()):
                reads[0] = ("ListExpr", name)
    return _RaisingReads(
        accessors=frozenset(accessor for accessor, _ in reads),
        lists=(
            frozenset(name for _, name in reads if name is not None)
            if all(name is not None for _, name in reads)
            else frozenset()
        ),
    )


def _spoken(accessors: frozenset[str], field: str) -> str:
    """Join one field of the spellings found, in order, saying each word once.

    ``.list.get`` and a ``pl.element().get`` inside ``list.eval`` are two
    spellings of a read over the same thing, so a formula holding both
    would otherwise be told the index must be inside the "list or list".
    """
    seen = [getattr(_INDEXED_READS[accessor], field) for accessor in sorted(accessors)]
    return " or ".join(dict.fromkeys(seen))


def _indexed_read_advice(reads: _RaisingReads, *, projected: bool | None) -> list[str]:
    """Return the advice for a calculation that reads an element by index.

    Every clause here is true of every shape that reaches this family, and
    that set is wider than the projection the family was first written
    for. A ragged list read straight off a model-point extract has no
    timeline; a grid built from a whole term (``until="term_years"`` of
    20) is ONE axis shared by every policy rather than a horizon each;
    ``list.get(-5)`` runs off
    the START; and where a raising read stands beside a kernel refusal in
    the same formula, nothing structural says which of the two broke. So
    the first line states the read's own contract rather than declaring
    what happened, and the projection is offered last as a cause to check
    IF the values came from one -- never as the diagnosis.

    The first line gives the ARITHMETIC of the boundary rather than a
    condition to check, because the boundary is where this failure lives:
    an actuary reads a list of three at the count of three, which raises,
    and a clause about a list "shorter than the index" answers no to
    exactly that shape and sends the next attempt past the fix.

    It names the bound per spelling rather than once, because the two
    bounds are different facts. A list's is the number of elements that
    row holds. An ``Array``'s is the column's own fixed width, declared
    once for every row -- which is why the clause that used to say "one
    less than that row's own length" was not merely imprecise on an array
    but wrong on the row whose value is null, where the row has no length
    at all and the declared width still bounds the read. And on a row
    holding no elements, "one less" is minus one and names nothing, so
    that row is stated outright: it is the row every remedy below has to
    survive.

    The remedies were run before they were advised, on a list and on an
    array, and they are given in the order they survive. A
    ``when/then/otherwise`` wrapped around the read does NOT work, because
    polars evaluates both branches and the guarded read raises anyway.
    Moving the condition inside the read clamps the index and does work --
    but only where every row holds an element, because an empty row has no
    valid index to clamp to: the ``len() - 1`` an actuary writes for "the
    last one" is -1 there, which reaches back past the start. (The frame
    reads ``.list.len()``'s unsigned count as the ``i64`` it fits, so that
    subtraction goes negative rather than wrapping to 18446744073709551615.)
    So ``null_on_oob=True`` leads and the clamp carries its condition:
    advice that steers into a read with no index is worse than advice that
    steers nowhere.

    ``reads.lists`` names the list the read was taken from where exactly
    one is named, so the remedy is written against a column the frame
    actually has. Where the formula indexed several lists, or a computed
    one, no single column is the subject and the lines say so by naming
    none. ``reads.accessors`` supplies the spelling, so an ``.arr.get``
    failure is not answered about a ``.list.get`` the formula never wrote.

    The projection line is offered only where it could be true, and two
    facts withhold it. An ``Array`` read is one: ``projection.set(...)``
    materialises ``List`` columns, so a fixed-width array never came from
    a grid and the line named a cause that cannot be the cause. A frame
    carrying no projection schedule is the other -- ``GraphFacts.projected``
    brings that from the call site, which holds the frame this router is
    not given -- and ``None`` there is nobody having asked, which costs the
    refinement and keeps the line.

    Three lines is a ceiling rather than a taste: the panel prints
    ``suggestions[:3]`` (``errors/formatter.py``), so a fourth would be
    built, counted by a test and never read by anybody. Two is what the
    family gives where the projection cannot be the cause.
    """
    named = f" into `{next(iter(reads.lists))}`" if len(reads.lists) == 1 else ""
    holds = _spoken(reads.accessors, "holds")
    bound = _spoken(reads.accessors, "bound")
    length = _spoken(reads.accessors, "length")
    calls = " or ".join(
        f"`{_INDEXED_READS[accessor].call}(...)`"
        for accessor in sorted(reads.accessors)
    )
    advice = [
        (
            f"The index{named} must be inside the {holds} the read is taken "
            f"from: the last valid index is one less than {bound}, so {calls} "
            "raises as soon as the index reaches it - three elements are read "
            "at 0, 1 or 2 and raise at 3, and a row holding none raises at "
            "every index - and where a negative index reaches back past the "
            "start."
        ),
        (
            f"Pass `null_on_oob=True` to {calls} - through `.polars_native()` "
            "where the line does not use it already, which records it as "
            "engine_native, a line only Polars runs - and the read returns a "
            "null on every row the index misses, a row holding no elements "
            "included; handle those nulls downstream. A `when(...).then(...)` "
            "AROUND the read still raises, because polars evaluates both "
            "branches, so a clamp has to go INSIDE the read - and clamp only "
            "where every row holds an element, because a row holding none has "
            f"no index to clamp to: {length} is 0 there, and `len() - 1` is -1, "
            "which reaches back past the start."
        ),
    ]
    if projected is not False and any(
        _INDEXED_READS[accessor].from_projection for accessor in reads.accessors
    ):
        advice.append(
            f"If that {holds} came from a projection, check the grid it was "
            "built to: `af.projection.set(...)`'s `until`/`until_value` size "
            "it, and a per-policy timeline gives each policy a length of its "
            "own.",
        )
    return advice


class ErrorSuggestionEngine:
    """Choose the advice for one failed calculation from what the framework knows."""

    # Common actuarial typos and their corrections
    ACTUARIAL_TYPOS: ClassVar[dict[str, str]] = {
        "premiun": "premium",
        "premiums": "premium",
        "premiuns": "premium",
        "assmuption": "assumption",
        "assumtion": "assumption",
        "benifits": "benefits",
        "benfit": "benefit",
        "poliy": "policy",
        "polciies": "policies",
        "poilcy": "policy",
        "cliam": "claim",
        "claimes": "claims",
        "cliams": "claims",
        "exposrue": "exposure",
        "experiance": "experience",
        "decrement": "decrements",
        "incrment": "increment",
        "mortaliy": "mortality",
        "morality": "mortality",  # Common confusion
        "lapses": "lapse",
        "laspse": "lapse",
        "intrest": "interest",
        "discout": "discount",
        "acturial": "actuarial",
        "data": "date",  # Very common typo
    }

    def suggest_fixes(
        self,
        exception: Exception,
        record: CalculationRecord | None,
        available_columns: list[str],
        facts: GraphFacts | None = None,
    ) -> list[str]:
        """Return the advice for one failure, keyed on class, lowering and dtypes.

        Args:
            exception: The exception that was raised.
            record: The calculation the failure was attributed to, or
                ``None`` where nothing was attributed to one.
            available_columns: The columns the frame held when it failed.
            facts: What the graph says the failing definition read, from
                :func:`gaspatchio.errors.formatter.graph_facts`; ``None``
                where the caller never asked the graph.

        Returns:
            The advice lines, the family's own first and its
            dtype-specific refinement last; empty where no fact selects a
            family.

        """
        if isinstance(exception, pl.exceptions.ColumnNotFoundError):
            return self._suggest_column_fixes(
                str(exception).lower(),
                available_columns,
            )
        if record is None:
            # Nothing was attributed, so there is no lowering to read and
            # no operands to ask the graph about. The class alone cannot
            # separate a strict cast from a strict date parse from an
            # arithmetic clash, and those families' advice contradict each
            # other -- so none is given rather than one guessed.
            return []
        return self._suggest_from_the_record(exception, record, facts)

    def _suggest_from_what_the_calculation_is(
        self,
        record: CalculationRecord,
    ) -> list[str] | None:
        """Return the family the whole calculation's own verb names, or ``None``.

        Two verbs say what a formula IS rather than what it contains: a
        read of an assumption table, and a parse of text into a date.
        Neither is refined by an operand dtype and neither yields to the
        class the engine raised, so both are settled before anything else
        is asked. An indexed read is NOT one of them -- it is a part of a
        formula, not its subject -- and is asked at the end of
        :meth:`_suggest_from_the_record`, where the reason sits beside it.
        """
        lookup = _call_in(record.node, _LOOKUP_CALLS)
        if lookup is not None:
            return self._suggest_lookup_fixes(lookup)
        if _call_in(record.node, _PARSE_CALLS) is not None:
            return list(_DATE_PARSE_ADVICE)
        return None

    def _suggest_from_the_record(
        self,
        exception: Exception,
        record: CalculationRecord,
        facts: GraphFacts | None,
    ) -> list[str]:
        """Choose a family for an attributed failure: identity first, then dtypes.

        What the calculation IS is asked first, because it outranks what
        the engine happened to raise on it: a lookup that fails is a lookup
        problem whether the engine called it a ``ComputeError`` or
        something else.

        The framework's own list kernels are asked next, ahead of the
        classes, and for the same reason. ``af.a * af.b`` on a jagged pair
        raises polars' ``ShapeError`` and is answered below; the identical
        mismatch written ``af.a ** af.b`` goes through this repository's
        ``list_pow``, comes back as a ``ComputeError`` carrying no subject
        at all, and used to be answered with nothing. One failure told two
        different stories because of which operator the actuary reached
        for. The kernel's own symbol says the operands clashed; the operand
        dtypes say which clash it was.
        """
        identity = self._suggest_from_what_the_calculation_is(record)
        if identity is not None:
            return identity
        reading = () if facts is None or facts.reading is None else facts.reading
        # "unknown" is the graph saying it never determined a type, which
        # is silence and not a type to route on.
        dtypes = frozenset(
            operand.dtype for operand in reading if operand.dtype != UNKNOWN
        )
        if _a_list_kernel_refused(record.expr):
            return self._suggest_kernel_fixes(dtypes)
        by_class = self._suggest_from_the_class(exception, dtypes)
        if by_class is not None:
            return by_class
        # Asked after the classes above and not with the lookup and the
        # parse, because an indexed read is a PART of a formula rather
        # than what the formula is: a length clash on
        # An indexed cashflow times af.curve is still a jagged clash, and
        # the class that names a subject answers first. What is left when
        # none of them does is the shape this family exists for -- the
        # admitted ComputeError polars raises when `.list.get` runs off the
        # end of the list a row holds, or `.arr.get` past a fixed width.
        # The question is about the read that CAN raise, not about any
        # indexed read in the formula: a `null_on_oob=True` read never can,
        # and answering for one meant answering a failure it had nothing to
        # do with.
        indexed = _reads_whose_index_can_raise(record.expr, record.node)
        if indexed is not None:
            return _indexed_read_advice(
                indexed,
                projected=None if facts is None else facts.projected,
            )
        # An attributed failure whose class carries no subject of its own
        # and whose lowering names no family: a ComputeError from somewhere
        # the graph has no vocabulary for.
        # Silence here is the same decision as the one above -- the families
        # that remain contradict each other, so none is guessed -- and it is
        # the branch a reader is most likely to land in, which is why it is
        # written down rather than left as a fall-through.
        return []

    def _suggest_from_the_class(
        self,
        exception: Exception,
        dtypes: frozenset[str],
    ) -> list[str] | None:
        """Return the family the exception's own class names, or ``None`` for neither.

        Three of the classes ``_ATTRIBUTABLE_ERRORS`` (``errors/boundary.py``)
        admits carry a subject of their own, and each is refined by what the
        graph says the formula read. ``None`` says the class named nothing,
        which is what a ``ComputeError`` does: it is the class polars hands
        back for everything from a plugin's refusal to an index off the end
        of a row's list, so the lowering is asked instead.
        """
        if isinstance(exception, pl.exceptions.ShapeError):
            return self._suggest_list_length_fixes() if _reads_a_list(dtypes) else []
        if isinstance(exception, pl.exceptions.SchemaError):
            return self._suggest_declared_type_fixes()
        # This is the member whose subject is a type, so it is the one the
        # operand dtypes can answer.
        if isinstance(exception, pl.exceptions.InvalidOperationError):
            return self._suggest_type_fixes(dtypes)
        return None

    def _suggest_kernel_fixes(self, dtypes: frozenset[str]) -> list[str]:
        """Choose which clash one of the framework's own list kernels refused over.

        These kernels walk their operands elementwise down each row's own
        list, so a refusal is about the operands they were handed and the
        graph's dtypes say which of the two ways they can disagree it was.

        A ``str`` standing where the arithmetic wanted numbers is a type
        clash and earns the cast line, which is the same answer the same
        pair earns from a class whose subject IS a type -- ``list[f64] **
        str`` has a string used as an exponent whatever the class polars
        chose to hand it back under. ``_NUMERIC_ELEMENTS`` counts
        ``list[f64]`` as numbers for that test because the element type is
        what the kernel's arithmetic touched.

        Anything else with a list operand is a length clash, which is the
        one these kernels are written to refuse: ``growth_factor`` holding
        one element where ``fund_value`` holds two is exactly the jagged
        pair the family below describes. No list operand at all, and the
        graph having answered, leaves nothing this router can say.
        """
        if "str" in dtypes and dtypes & _NUMERIC_ELEMENTS:
            return self._suggest_type_fixes(dtypes)
        return self._suggest_list_length_fixes() if _reads_a_list(dtypes) else []

    def _suggest_column_fixes(
        self,
        error_msg: str,
        available_columns: list[str],
    ) -> list[str]:
        """Suggest fixes for column not found errors."""
        suggestions: list[str] = []

        # Extract the missing column name
        missing_col = self._extract_column_name(error_msg)
        if not missing_col:
            return suggestions

        # Check for common actuarial typos first
        if missing_col in self.ACTUARIAL_TYPOS:
            correct_col = self.ACTUARIAL_TYPOS[missing_col]
            if correct_col in available_columns:
                suggestions.append(
                    f"Did you mean '{correct_col}'? (common actuarial typo)",
                )
            else:
                suggestions.append(
                    f"'{missing_col}' is a common typo for '{correct_col}'",
                )

        # Find similar columns using edit distance
        similar_cols = self._find_similar_columns(missing_col, available_columns)
        if similar_cols:
            best_match = similar_cols[0]
            suggestions.append(f"Did you mean '{best_match}'? (similar column found)")

            # If there are multiple good matches, mention them
            if len(similar_cols) > 1:
                other_matches = similar_cols[1:3]  # Show up to 2 more
                others = ", ".join(f"'{col}'" for col in other_matches)
                suggestions.append(f"Other similar columns: {others}")

        # Check for common patterns
        if missing_col.endswith("_id") and not any(
            col.endswith("_id") for col in available_columns
        ):
            suggestions.append(
                "No ID columns found - check if you need to join additional data",
            )

        if missing_col.startswith("calc_") and not any(
            col.startswith("calc_") for col in available_columns
        ):
            suggestions.append(
                "No calculated columns found - ensure calculations are "
                "defined before use",
            )

        return suggestions

    def _suggest_type_fixes(self, dtypes: frozenset[str]) -> list[str]:
        """Suggest fixes for a dtype clash, refined by the operands' own types.

        ``dtypes`` is what the graph holds for the definitions the failing
        formula read, so a column called ``valuation_date`` that holds
        ``f64`` is a number here and is answered as one.

        The cast line counts a ``list[f64]`` among the numbers
        (``_NUMERIC_ELEMENTS``), because a string beside a per-period
        column of numbers is the same mistake as a string beside one
        number and takes the same cast; the axis the numbers sit on is not
        what refused.
        """
        suggestions = [
            "Ensure all expressions have consistent types",
            "Consider using .cast() to explicitly set types",
        ]

        if "str" in dtypes and dtypes & _NUMERIC_ELEMENTS:
            suggestions.append(
                "Try converting strings to numbers with .cast(pl.Float64) "
                "or .cast(pl.Int64)",
            )

        elif dtypes & _TEMPORAL_DTYPES:
            suggestions.append(
                "Date/time type issues - use .str.to_datetime() or .cast(pl.Date)",
            )

        elif "bool" in dtypes:
            suggestions.append(
                "Boolean type mismatch - ensure conditions return True/False",
            )

        elif dtypes >= _NUMERIC_DTYPES:
            suggestions.append(
                "Mix of integers and floats - consider using .cast(pl.Float64) "
                "for consistency",
            )

        return suggestions

    def _suggest_declared_type_fixes(self) -> list[str]:
        """Suggest fixes for a value whose type is not the type declared for it.

        This family answers a ``SchemaError``, and what it replaced was
        three lines about joins: check the join keys, cast before joining,
        verify the column names. This router answers one shape -- a column
        assignment that failed at collect -- and a column assignment does
        not join. The one calculation in this framework's vocabulary that
        does is a ``Table.lookup``, and that is answered by identity before
        any class is asked (``_suggest_from_what_the_calculation_is``), so
        by the time this is reached the join advice named an operation the
        failing calculation cannot contain. A
        ``map_elements(..., return_dtype=pl.Float64)`` whose body returns a
        string was told to check its join keys.

        What a ``SchemaError`` here IS: the values a calculation produced
        do not have the type something was told they would. Two shapes
        reach it and both are named, because which one this is is not a
        fact the router holds -- a declared output type that the values
        contradict (``return_dtype=``, the dtype an escape hatch names),
        and two branches of one expression that polars will not find a
        common type for.
        """
        return [
            (
                "The values this calculation produced do not have the type it "
                "was declared to produce."
            ),
            (
                "Where the type was DECLARED - `return_dtype=` on a "
                "`map_elements`, the dtype an escape hatch names - either "
                "declare the type the values really have, or cast them to the "
                "declared one inside the calculation. A `map_elements` is also "
                "the slow path here: a Polars expression over the whole column "
                "is both faster and typed by the engine rather than by you."
            ),
            (
                "Where two branches have to agree - `when/then/otherwise`, a "
                "concatenation - cast both sides to one type before combining "
                "them; polars will not choose a common type across a mismatch "
                "it cannot widen."
            ),
        ]

    def _suggest_list_length_fixes(self) -> list[str]:
        """Suggest fixes for list-length mismatches.

        Almost always a jagged (per-policy) projection column combined with a
        fixed-width / portfolio-max list (yield curve, discount vector, or
        externally-built assumption vector).
        """
        return [
            (
                "List lengths differ across rows — usually a jagged (per-policy) "
                "projection column combined with a fixed-width list (e.g. a "
                "portfolio-wide yield/discount curve or assumption vector)."
            ),
            (
                "Trim the fixed-width list to each policy's own horizon before the "
                "arithmetic, e.g. `curve.polars_native().list.head("
                "af.month.polars_native().list.len())`. Written through "
                "`.polars_native()`, the line records as engine_native: it runs "
                "only on Polars, and so does every calculation that reads it "
                "(`af.graph.tiers()` names them)."
            ),
            (
                "Or build a rectangular grid: pass `per_policy=False` to "
                "`af.projection.set(...)` so every policy shares one period axis."
            ),
        ]

    def _suggest_lookup_fixes(self, call: Call) -> list[str]:
        """Suggest fixes for a failure inside an assumption-table read.

        The table is named from the call's own identity attribute -- the
        one the lowering already carries so the graph can say which base a
        column came from -- and not from a column whose name happens to
        contain the word "assumption".
        """
        suggestions = [
            "Check assumption key matches exactly (case-sensitive)",
            "Verify assumption table is loaded correctly",
        ]

        # `is not None` rather than a truth test: a table whose name is the
        # empty string still has a coverage problem, and the line's move --
        # extend it, or pass on_missing= -- does not depend on the name
        # reading well. A truth test dropped the line for `""` and kept it
        # for `"0"`, which is a distinction the reader cannot see.
        table = dict(call.attrs).get("table")
        if table is not None:
            suggestions.append(
                f"Table {table!r} must cover every key the projection reaches "
                "- extend it, or pass on_missing= a fill value",
            )

        return suggestions

    def _extract_column_name(self, error_msg: str) -> str | None:
        """
        Extract column name from error message.

        The one string this module still parses, and the reason is
        structural: a column that is not on the frame is not a node on the
        graph, so there is nothing to read the name off but the refusal
        that names it.

        Args:
            error_msg: The error message to parse

        Returns:
            Extracted column name or None if not found

        """
        # Common patterns for column names in error messages
        patterns = [
            r"column '([^']+)' (?:does not exist|not found)",
            r"column \"([^\"]+)\" (?:does not exist|not found)",
            r"column ([a-zA-Z_][a-zA-Z0-9_]*) (?:does not exist|not found)",
            r"columnnotfound: ([a-zA-Z_][a-zA-Z0-9_]*)",
            r"key '([^']+)' not found",
            r"cannot find column '([^']+)'",
            r"unknown column: ([a-zA-Z_][a-zA-Z0-9_]*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, error_msg, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _find_similar_columns(
        self,
        target_col: str,
        available_columns: list[str],
        threshold: float = 0.6,
    ) -> list[str]:
        """
        Find columns similar to target using edit distance.

        Args:
            target_col: The target column name to match
            available_columns: List of available column names
            threshold: Minimum similarity ratio (0-1)

        Returns:
            List of similar column names, sorted by similarity (best first)

        """
        if not available_columns:
            return []

        similarities = []
        target_lower = target_col.lower()

        for col in available_columns:
            col_lower = col.lower()

            # Calculate similarity ratio
            ratio = SequenceMatcher(None, target_lower, col_lower).ratio()

            # Boost score for exact case-insensitive matches
            if target_lower == col_lower:
                ratio = 1.0
            # Boost score for substring matches
            elif target_lower in col_lower or col_lower in target_lower:
                ratio = max(ratio, 0.8)
            # Boost score for similar prefixes/suffixes
            elif (
                target_lower.startswith(col_lower[:_SHARED_PREFIX])
                and len(col_lower) >= _SHARED_PREFIX
            ) or (
                col_lower.startswith(target_lower[:_SHARED_PREFIX])
                and len(target_lower) >= _SHARED_PREFIX
            ):
                ratio = max(ratio, 0.7)

            if ratio >= threshold:
                similarities.append((col, ratio))

        # Sort by similarity (highest first) and return column names
        similarities.sort(key=lambda x: x[1], reverse=True)
        return [col for col, _ in similarities[:5]]  # Return top 5 matches
