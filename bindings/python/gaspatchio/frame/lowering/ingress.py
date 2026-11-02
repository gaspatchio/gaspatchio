# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The door every operand walks through on its way into the op-tree.

An operator dunder on a proxy sees whatever the model author wrote on the
other side of the ``*``: another proxy, a raw Polars expression handed back
by an accessor or a ``Table.lookup``, or a plain Python number. ``to_node``
turns each of those into exactly one ``OpNode`` so the dunder itself never
has to know which it got:

- a proxy (``ColumnProxy``, ``ExpressionProxy``, ``ConditionExpression``)
  contributes the node it already carries -- the op-tree stays one tree,
  not a tree per proxy;
- a raw ``pl.Expr`` becomes an ``EngineNative`` node, because the framework
  has no semantic view of an expression somebody else built;
- a Python sequence every member of which is a scalar the op-tree can
  spell -- ``[45, 50, 55]``, the age boundaries of a banded lookup --
  becomes a ``Lit`` holding those values, so the tree identifies the band
  by what is in it;
- a true/false flag, a whole number, a decimal or text becomes a ``Lit``
  holding that value, and a fixed-point ``Decimal`` one holding the number
  it denotes (a whole number where it has no places, else the double);
- anything else becomes an ``EngineNative`` over ``pl.lit(value)``. A
  ``datetime.date``, a NumPy array: the op-tree has no
  literal form for any of them, so the operand reaches the tree as the
  engine's own text and the framework keeps no semantic view of it. **A
  calendar date written into a formula is the ordinary case that lands
  here**, and it is named rather than left under "anything else" because
  a valuation date, an issue date and an anniversary test are not edge
  cases in an actuarial model -- see :func:`to_node`, which says the same
  thing at the branch that does it.

``Lit`` rejects a non-finite float at construction, so
``af.account_value * float("nan")`` raises at the line the author wrote it
on rather than silently seeding NaN through a projection. A caller that is
only *asking* whether the tree could hold a value -- the recognisers in
``frame/lowering/methods.py``, deciding which operation a method call is --
asks through :func:`recordable_node`, which answers no instead of raising.
Refusing to record a value is not the same as refusing to compute it.

An ``EngineNative`` node's ``text`` is the engine's own rendering of the
expression, and that rendering names a compiled plugin by the absolute path
of the library holding it. The path is a fact about the machine, not about
the calculation, so ``native_node`` takes it out before the node is built --
see :func:`_without_machine_paths`. The deliberate door, where an author
asks for an engine expression by name rather than handing one in, is
``_authoring/escape.py``.
"""

from __future__ import annotations

import datetime
import decimal
import numbers
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Final, cast, get_args

import polars as pl

from gaspatchio._dtypes import I64_MAX, I64_MIN
from gaspatchio._semantic.ir import EngineNative, Lit, OpNode

if TYPE_CHECKING:
    from collections.abc import Iterator
from gaspatchio.frame.lowering._polars.expressions import literal_expression
from gaspatchio.frame.lowering._polars.rendering import (
    quotients_as_operators,
    without_plugin_library_paths,
)
from gaspatchio.frame.lowering.value_reads import mark_hidden_reads, reads_inside

# Whether a date operand becomes a literal in the op-tree, or falls through
# to an engine fragment as it did before the tag existed.
#
# True from `gspv0-preview-2`, and the reason it was ever False is the byte
# grammar rather than the code. A date literal encodes under tag 0x16, and a
# new tag is a change to the grammar section 12.1 publishes -- which moves
# `fingerprint_algorithm`, for any grammar change at all and however small.
# Emitting one while that token still read `gspv0-preview-1` would have put
# bytes of the new grammar inside a document announcing the old one, which is
# the single thing the token exists to make impossible. So the encoder, the
# wire form and every refusal around them landed first and were covered
# directly, and this one name turned the emission on in the commit that moved
# the token with it.
#
# The switch reaches a date and nothing else. An instant is tested before it
# below -- `datetime.datetime` is a subclass of `datetime.date` -- and takes
# the engine path whatever this reads, because the tree grammar mints no tag
# for one. A date inside a sequence literal stays refused for its own reason,
# which section 12.1 gives.
DATE_LITERALS_BY_DEFAULT: Final[bool] = True

# The seven node classes, as a tuple isinstance can take. OpNode is a
# union of exactly these; deriving the tuple from the union rather than
# retyping it means an eighth member could never be missed here.
_OP_NODE_TYPES: tuple[type, ...] = get_args(OpNode)

# id(EngineNative node) -> (that same node, its held runtime pl.Expr).
#
# Keyed by identity rather than by the node's own structural equality:
# two EngineNative nodes can carry identical engine/text/deps and still
# wrap genuinely different runtime objects, so value-equality would risk
# resolving one node to another node's expression.
#
# The node is stored alongside the expression purely to keep the node
# alive for as long as this entry exists. id() values are only guaranteed
# unique among currently-live objects; if this dict held only the
# expression, nothing would keep the node itself alive, and once garbage
# collected its id could be reused by a later, unrelated object -- which
# would then silently resolve to this stale entry's expression. Holding
# the node here is what makes the key stable for the entry's lifetime.
#
# Consequence, stated rather than hidden: entries are never evicted, so a
# long-lived process that ingests many distinct raw expressions grows this
# table monotonically. One entry per raw expression that becomes an
# operand -- a model build ingests hundreds, not millions -- and the
# alternative (a weak reference to the node) is exactly the design this
# table rejects, because it reintroduces the id-recycling collision.
NATIVE_REFS: dict[int, tuple[EngineNative, pl.Expr]] = {}

# The engine-native leaves that entered as an author's raw Polars operand --
# ``af.x * pl.col("t").shift(1)`` -- through :func:`to_node`, keyed like
# ``NATIVE_REFS`` (whose held node keeps the id stable). The explicit escape,
# ``polars_native()``, mints its node through :func:`native_node` directly
# and is never marked: it is the door an author opens on purpose, with its
# own refusals. A frame reads the mark when such a formula is assigned to
# it, to refuse a raw fragment that runs a row operation down a per-period
# column -- across the policies -- exactly as it refuses the same fragment
# assigned on its own (see ``frame/_row_operations.py``).
RAW_OPERANDS: set[int] = set()


def raw_operand_expr(node: EngineNative) -> pl.Expr | None:
    """Return the raw Polars expression ``node`` stands for, if an author wrote it.

    ``None`` for a node the explicit escape minted, or one this process does
    not hold.
    """
    if id(node) not in RAW_OPERANDS:
        return None
    entry = NATIVE_REFS.get(id(node))
    if entry is None or entry[0] is not node:
        return None
    return entry[1]


def _without_machine_paths(text: str) -> str:
    """Return ``text`` with any plugin library path replaced by a placeholder.

    ``EngineNative.text`` is written verbatim into the exported artifact and
    folded into the calculation's fingerprint, so anything machine-local in
    it makes the same model record differently on two machines -- and a
    record that varies by machine identifies the machine rather than the
    calculation. The symbol the plugin exports is kept, because that is the
    part that says which calculation ran.

    Examples:
        >>> rendered = (
        ...     'col("v")./opt/env/gaspatchio'
        ...     "/_internal.cpython-313-darwin.so:list_pow([])"
        ... )
        >>> _without_machine_paths(rendered)
        'col("v").<plugin>:list_pow([])'

    """
    return without_plugin_library_paths(text)


def native_node(expr: pl.Expr, deps: tuple[str, ...] | None = None) -> EngineNative:
    """Wrap a raw Polars expression as an ``EngineNative`` node.

    Records the node and the expression together in ``NATIVE_REFS`` so
    ``lower_polars`` can resolve the node back to the very object this call
    was handed -- two structurally identical expressions stay two distinct
    nodes.

    ``deps`` declares the column names the expression reads, which is the
    only thing the framework can still say about it once the semantics are
    opaque. Left unstated, it is taken from ``expr.meta.root_names()``, and
    an expression that refuses to report its roots contributes none -- the
    door the operator dunders walk through cannot refuse an operand the
    author has already written. A caller that can refuse -- the explicit
    escape, where the author asked for this -- resolves ``deps`` itself and
    passes them here rather than accepting that silence.

    The node's ``text`` is the engine's rendering with any plugin library
    path taken out of it, and the framework's quotient kernels written as the
    operators they compute; see :func:`_without_machine_paths` and
    :func:`~gaspatchio.frame.lowering._polars.rendering.quotients_as_operators`.
    The text is folded into the calculation's fingerprint, and dividing
    exactly did not change the calculation a model describes.

    That text is Polars' display, and the display leaves a plugin's
    arguments out -- a table lookup's table name and content hash among
    them. So a plan holding a table, mortality, curve or schedule read is
    marked here (:mod:`~gaspatchio.frame.lowering.value_reads`), and an
    ActuarialFrame refuses the marked node where an assignment records it:
    a fingerprint taken over this text could not move when the table did.
    Marked rather than refused, because the same node is built for an
    operand on a raw Polars frame, which that rule does not reach.
    """
    if deps is None:
        try:
            deps = tuple(expr.meta.root_names())
        except (AttributeError, RuntimeError):
            # meta inspection is best-effort: a plugin expression can refuse to
            # report its roots. An empty deps tuple understates the reads rather
            # than inventing them.
            deps = ()
    text = quotients_as_operators(_without_machine_paths(str(expr)))
    node = EngineNative(engine="polars", text=text, deps=deps)
    NATIVE_REFS[id(node)] = (node, expr)
    mark_hidden_reads(node, reads_inside(expr))
    return node


class IntegerLiteralPastI64Error(ValueError):
    """A whole number in a formula, or in a call's setting, that no ``i64`` holds.

    A ``ValueError`` because it is one -- a value the tree has no literal
    for -- and a class of its own because, unlike a NaN, it is not declined
    by :func:`recordable_node`. A NaN handed to a method keeps the engine's
    own meaning on the engine path. A whole number past ``i64`` has none the
    record could carry: section 12.1 writes a whole number as an ``i64``, and
    the engine answered null (``af.pid == 2**64 - 1`` on an ``Int64``
    column) or a type the vocabulary does not name (``Int128`` out of a
    ``when``). So it is refused at the line it was written on, wherever it
    was written.
    """


def past_i64_literal_message(value: int, where: str = "") -> str:
    """Explain that a whole-number literal has no ``i64`` name, and the two moves.

    ``where`` is empty for a literal on its own and names the position for
    one in a sequence, as :func:`~gaspatchio._semantic.ir.non_finite_literal_message`
    does for a NaN.
    """
    return (
        f"The integer literal {value}{where} is outside the signed 64-bit "
        "range, and a formula cannot hold it.\n"
        "\n"
        "Every integer in a calculation graph is an i64, a literal as much as "
        f"a column, and outside [{I64_MIN}, {I64_MAX}] there is no whole "
        "number to write it as: the engine would answer null, or a type the "
        "record does not name, where the line reads as a number.\n"
        "\n"
        "If it is an identifier, compare its digits as text -- "
        f'af.policy_id.to_text() == "{value}". If it is a quantity, write it '
        f"as a decimal literal -- {float(value)!r} -- where its magnitude "
        "matters and its last digits do not."
    )


def past_i64_setting_message(value: int, operation: str, setting: str) -> str:
    """Explain that a call's whole-number setting has no ``i64`` name."""
    return (
        f"The integer {value} given as {operation}'s {setting!r} is outside "
        "the signed 64-bit range, and the record cannot hold it.\n"
        "\n"
        "Every whole number in a calculation graph is an i64, a call's "
        f"setting as much as a column, and outside [{I64_MIN}, {I64_MAX}] "
        "there is none to write it as. Give the setting a value inside that "
        "range."
    )


# Whether the literal being read is compared against a column still wider
# than ``i64`` (:func:`compared_against_a_wide_column`).
_COMPARED_WIDE: ContextVar[bool] = ContextVar("_COMPARED_WIDE", default=False)


@contextmanager
def compared_against_a_wide_column() -> Iterator[None]:
    """Admit a whole number past ``i64`` while the operand of one comparison is read.

    A column still wider than ``i64`` -- an identifier past it, which the
    frame keeps in the width it arrived in -- is outside the portable domain,
    and the record refuses it; the frame still compares it, exactly, in its
    own width, because a comparison reads a value by its digits and cannot
    wrap it. ``af.pid == 2**64 - 1`` is therefore admitted, as a comparison
    or a membership test against such a column, and refused everywhere else.
    """
    token = _COMPARED_WIDE.set(True)
    try:
        yield
    finally:
        _COMPARED_WIDE.reset(token)


def within_i64(value: int, where: str = "") -> int:
    """Return ``value`` where an ``i64`` holds it, and refuse it where none does.

    Inside :func:`compared_against_a_wide_column` it is returned whatever its
    size: the column it is compared with is wider than ``i64`` too.

    Raises:
        IntegerLiteralPastI64Error: If ``value`` lies outside ``[-2**63,
            2**63 - 1]`` and is not compared against a column that wide.

    """
    if I64_MIN <= value <= I64_MAX or _COMPARED_WIDE.get():
        return value
    raise IntegerLiteralPastI64Error(past_i64_literal_message(value, where))


def _sequence_literal(value: object) -> Lit | None:
    """Return the literal a Python sequence of scalars stands for, or ``None``.

    A ``list`` or ``tuple`` whose every member is a ``bool``, ``int``,
    ``float`` or ``str`` is a value the op-tree can spell in full, so it
    spells it. One member it cannot -- a date, a NumPy scalar, a nested
    list -- and the whole sequence keeps the engine-native path, because a
    literal the tree could only half hold would identify the band by half
    its contents.
    """
    if not isinstance(value, (list, tuple)):
        return None
    members = tuple(value)
    if all(isinstance(member, (bool, int, float, str)) for member in members):
        for position, member in enumerate(members):
            if isinstance(member, int) and not isinstance(member, bool):
                within_i64(member, f" at position {position} of a sequence")
        return Lit(members)
    return None


def refuse_an_unfinished_chain(value: object) -> None:
    """Refuse a ``when()`` chain with no ``.otherwise()`` in its own words.

    It has no value to stand for, and left to the literal door below it was
    refused in Polars' words about a literal it cannot make.
    """
    unfinished = getattr(value, "_refuse_unfinished", None)
    if unfinished is not None:
        unfinished()


def _a_number(value: numbers.Real | decimal.Decimal) -> Lit:
    """Return the literal a real number or a fixed-point decimal stands for.

    A real number is its double. A ``Decimal`` is read as the number it
    denotes, as a book column of one is where it enters the frame: written
    with no places (``Decimal("12")``) the whole number, otherwise the double
    nearest it. A non-finite one is refused by ``Lit`` as a float would be.
    """
    if isinstance(value, decimal.Decimal):
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent >= 0:
            return Lit(within_i64(int(value)))
    return Lit(float(value))


def to_node(value: object) -> OpNode:  # noqa: PLR0911
    """Turn one operand into the op-tree node that stands for it.

    A ``Decimal`` is the number it denotes: written with no places, the
    whole number; otherwise the double nearest it.

    A value the op-tree has no literal form for -- a ``datetime.date``, a
    NumPy array -- becomes an ``EngineNative`` node over
    ``pl.lit(value)`` rather than being refused: the framework loses its
    semantic view of that operand, which is exactly what ``EngineNative``
    is for, and *Meet you where you are* says accept the value the author
    already has.

    A sequence of scalars is a literal like any other, so it enters as one
    rather than as engine text. The engine's text for a long sequence is
    its abbreviated *display* of the values, not the values, so two bands
    differing only in the middle used to reach the tree as one thing.

    A number from outside the standard library -- ``numpy.int32`` from a
    model-point array, ``numpy.int64`` from a period count -- is a literal
    like any other, so it is narrowed to the plain ``int``/``float`` the
    op-tree carries rather than being treated as an opaque object. Letting
    it through as ``EngineNative`` would lose its literal form, cost an
    ingress-table entry that is never freed, and make two formulas that
    wrote the same number compare unequal.

    A whole number no ``i64`` holds is refused here, where the author wrote
    it (:func:`within_i64`): the record has no name for it, and the engine
    answered null or a type the vocabulary does not name.

    Raises:
        ValueError: If ``value`` is a non-finite float -- see ``ir.Lit``.
        IntegerLiteralPastI64Error: If ``value`` is a whole number, or a
            sequence holds one, outside ``[-2**63, 2**63 - 1]``.
        TypeError: If ``value`` carries a ``_node`` attribute that is not
            an op-tree node.

    """
    # Eight returns rather than seven: each one is a distinct kind of
    # operand the op-tree has a distinct answer for, and collapsing any
    # two of them would be collapsing two meanings.
    if isinstance(value, _OP_NODE_TYPES):
        # Already a node. A frame-level method, where a string genuinely
        # names a column -- ``af.finance.discount_factor("rate", "month",
        # "v_t")`` -- resolves that name to a ``Col`` itself and hands the
        # node through here.
        return cast("OpNode", value)
    node = getattr(value, "_node", None)
    if node is not None:
        if not isinstance(node, _OP_NODE_TYPES):
            msg = (
                f"{type(value).__name__}._node is a "
                f"{type(node).__name__}, not an op-tree node. Only the "
                "proxy types may carry a '_node' attribute."
            )
            raise TypeError(msg)
        # The isinstance above is the guarantee; the cast only tells the
        # type checker so, because it cannot follow a tuple of types built
        # at run time from the union itself.
        return cast("OpNode", node)
    refuse_an_unfinished_chain(value)
    if isinstance(value, pl.Expr):
        # An author's raw fragment, marked as such: see ``RAW_OPERANDS``.
        raw = native_node(value)
        RAW_OPERANDS.add(id(raw))
        return raw
    # The instant is tested before the date, here as at the encoder and at
    # ``Lit``'s own door, because ``datetime.datetime`` is a subclass of
    # ``datetime.date``. An instant has no tag in this grammar, so it takes
    # the engine path whatever this switch says.
    if (
        DATE_LITERALS_BY_DEFAULT
        and isinstance(value, datetime.date)
        and not isinstance(value, datetime.datetime)
    ):
        return Lit(value)
    if isinstance(value, (bool, str)):
        return Lit(value)
    # bool is an Integral, so it has to be caught above this. Narrowing to
    # the built-in int/float rather than storing the original object keeps
    # the literal's own type out of the op-tree: numpy.int64(12) and 12
    # are the same literal and should be the same node.
    if isinstance(value, numbers.Integral):
        return Lit(within_i64(int(value)))
    if isinstance(value, (numbers.Real, decimal.Decimal)):
        return _a_number(value)
    sequence = _sequence_literal(value)
    if sequence is not None:
        return sequence
    return native_node(literal_expression(value))


def recordable_node(value: object) -> OpNode | None:
    """Return the node standing for ``value``, or ``None`` if it cannot be one.

    The same question :func:`to_node` answers, asked by a caller that has
    somewhere else to leave the call. ``to_node`` refuses a non-finite float
    by raising, and at an operator dunder that is the right answer: the
    author wrote ``* float("nan")`` into a formula and nothing downstream of
    it is worth computing.

    It is the wrong answer to a method recogniser, which is asking whether
    an argument can be *recorded* and not whether the model may run.
    ``af.rate.fill_null(float("nan"))`` is a value the engine puts where a
    null was; the vocabulary has no literal for it, and the honest response
    to that is the one an unrecognised argument form already gets -- decline
    the operation, leave the call exactly where it stood before the
    vocabulary reached for it, and let the node record the engine fragment
    it is.

    **Only ``ValueError`` is answered here, and what separates the two is
    what each says about the argument.** A ``ValueError`` is ``to_node``
    reading the value and finding it one the tree has no literal for --
    a judgement about this argument, and one a caller with somewhere else
    to leave the call can act on. A ``TypeError`` is ``to_node`` unable to
    read it at all: the object announces an op-tree node by carrying a
    ``_node`` attribute, and what it carries is not one. That is not
    necessarily this package's own proxy -- ``to_node`` duck-types on the
    attribute, so any object with a ``_node`` reaches that branch -- but it
    is an argument whose own account of itself does not hold, and a
    silently declined operation is the wrong response to a contradiction.
    Letting it through leaves it where every argument form the recogniser
    cannot read already lands: ``fill_null(set())`` declines here too and
    then raises ``TypeError`` at the dispatch door, which is the same
    outcome at the same line.
    """
    try:
        node = to_node(value)
    except IntegerLiteralPastI64Error:
        raise
    except ValueError:
        return None
    return node
