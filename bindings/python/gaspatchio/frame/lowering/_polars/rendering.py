# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the framework's quotient kernels back as the operators they compute.

``/``, ``//`` and ``%`` over numbers lower to the ``ieee_div``,
``ieee_floordiv`` and ``ieee_mod`` kernels, because Polars' own float
operators multiply by a single divisor's reciprocal instead of dividing. The
kernels are an engine detail of *how* the division runs; the calculation is
still the one the model wrote. So wherever the package writes an engine
rendering down for a reader or into a record -- the walk-through in an
audit export, the engine-native text a fingerprint is taken over -- a kernel
call is written as Polars writes the operator it computes::

    col("x").<plugin>:ieee_div([dyn int: 12])   ->   [(col("x")) / (dyn int: 12)]

Two reasons, both about the record rather than the engine. A reader of a
walk-through sees the formula, not the name of a Rust function. And a
record whose text moved because the engine started dividing correctly
would announce a change to every model that divides by anything, when the
calculation those models describe has not changed at all.

The rewrite reads text, not a parse tree: it walks back from the kernel's
method dot over one balanced receiver -- a bracketed group, a call, a
method chain, a quoted string, a typed literal -- and forward over the
kernel's single argument. What it cannot read it leaves as it was, which
says more than it means to and never less.

The list kernels a reader reaches through an operator or a method are
written the same way for the record a reader opens -- the walk-through and
the ``gaspatchio_lowered`` facet, not the fingerprint text -- by
:func:`kernels_as_operations`: ``list_pow`` as ``.pow``, ``list_clip`` as
``.clip``, and ``list_conditional`` as the ``.when(...).then(...)
.otherwise(...)`` it evaluates. And the library path in front of any plugin
is replaced by a placeholder (:func:`without_plugin_library_paths`).

A per-period Categorical or Enum column compared for equality reaches that
kernel as its codes (``on_codes_where_labelled`` in the lowering), and
:func:`labels_for_codes` writes the two operands back as the model wrote
them: ``plan == "A"``, not the conversion to codes that ran. A per-period
comparison of whole numbers or dates and times reaches it as the two values'
exact difference against nought, and :func:`exact_comparisons_as_written`
writes the two values back: ``duration > 1``, not the subtraction that ran.
"""

from __future__ import annotations

import json
import pickle
import re
from typing import TYPE_CHECKING

from gaspatchio.frame.lowering._polars.once import ANSWER_AS_WRITTEN, OPERAND_FIELD
from gaspatchio.frame.lowering._polars.plugins import conditional_kwargs
from gaspatchio.frame.lowering._polars.unknown import (
    AS_NULL_MARK,
    POISON_MARK,
    UNKNOWN_MARK,
)
from gaspatchio.frame.lowering._polars.validation import (
    ABSOLUTE_VALUE_PAST_I64_RULE,
    CLIP_PAST_2_53_RULE,
    REMAINING_SUM_PAST_I64_RULE,
    RUNNING_PRODUCT_PAST_I64_RULE,
    RUNNING_SUM_PAST_I64_RULE,
    SUM_PAST_I64_RULE,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    import polars as pl

# The kernel, as the rendering writes it after a method dot: optionally the
# placeholder the record puts where the library path was, then the symbol.
_KERNEL_CALL = re.compile(r"\.(?:<plugin>:)?ieee_(div|floordiv|mod)\(")

# Which operator each kernel computes, as Polars itself prints the operator.
_OPERATOR = {"div": "/", "floordiv": "//", "mod": "%"}

# The prefix Polars writes before a dynamically typed literal, with the sign
# of a negative one: ``dyn int: 12``, ``dyn float: -0.5``.
_TYPED_LITERAL_PREFIX = re.compile(r"dyn [a-z]+: -?$")

_PLACEHOLDER = "<plugin>:"
_OPENING = {")": "(", "]": "["}
_CLOSING = {"(": ")", "[": "]"}

# How a compiled plugin appears inside the engine's own rendering of an
# expression: the path of the shared library holding the symbol, then a
# colon, then the symbol -- ``col("v")./opt/env/gaspatchio/
# _internal.cpython-313-darwin.so:list_pow([dyn float: 2])``. The path is a
# fact about the machine that ran the model, not about the calculation: it
# carries a home directory, an install prefix, an interpreter version and a
# platform triple, every one of which differs between two people running the
# same model file. The pattern stops at the colon that introduces the symbol
# so the symbol survives.
#
# **It starts at the method dot the rendering itself writes**, which is the
# position a loaded library can appear in and the position nothing the author
# named can. Without that anchor the pattern matched any text shaped like a
# path: ``alias("a/b.so:c")``, ``alias("a/z.so:c")`` and ``alias("a/OTHER
# .so:c")`` are three different calculations, and all three scrubbed to one
# text and so to one fingerprint -- a scrub against machine-local detail that
# instead made three models identical. A struct field named the same way went
# the same way. The dot is what separates the two: the engine writes the
# library after a method dot, and an author's column, alias or field name is
# written where a path never is.
#
# Two shapes of path, because a library is not always named from the root. A
# rooted path keeps parentheses and spaces -- ``C:\Program Files (x86)\...``
# is an ordinary install path, and half a path is still a leaked path. A
# relative one stops at any bracket, which is what keeps the run from
# crossing out of a path and into the rendering around it. Both stop at a
# double quote, which keeps a column name whole: the engine renders a column
# as ``col("premium/month")`` and the record has to keep saying which column
# was read. The extension is matched without regard to case, so a ``.DLL``
# leaks no less than a ``.dll`` did.
#
# **A relative path never starts with a digit.** A decimal receiver is
# written with a dot of its own -- ``dyn float: 1.01.lib/python3.13/…so:
# list_pow`` -- and a relative run allowed to start after ``1.`` took the
# ``01.`` with it, so ``1.01 ** t`` and ``1.07 ** t`` scrubbed to one text.
# A path Polars writes relative to the prefix starts with ``lib`` or
# ``Lib``; a run starting at a digit is the tail of a number.
#
# What it cannot promise: an author who spells a column, alias or field name
# as a path written immediately after a dot has written the one shape a
# textual scrub cannot tell from the engine's own.
_PLUGIN_LIBRARY_PATH = re.compile(
    r"""(?<=\.)                       # the method dot the rendering writes
        (?:
            (?:/|[A-Za-z]:[\\/])[^:"]*?   # rooted: parens and spaces are ordinary
            |
            (?![0-9])[^:"()\[\]]*?      # relative: no digit first, no bracket
        )
        \.(?:so|dylib|dll|pyd)(?=:)   # the library suffix, then the symbol
    """,
    re.IGNORECASE | re.VERBOSE,
)

# What stands in for the library. Deliberately not a name anything could be
# mistaken for: a reader sees a placeholder, not a file that might exist.
_PLUGIN_LIBRARY_STANDIN = "<plugin>"


def without_plugin_library_paths(text: str) -> str:
    """Return ``text`` with every plugin library path replaced by ``<plugin>``.

    The one scrub for the path a rendering writes before a compiled plugin's
    symbol, whichever record the rendering is going into. A fingerprint takes
    it so that two machines stamp one calculation alike; a walk-through and
    the ``gaspatchio_lowered`` facet take it so that one tree reads the same
    wherever the package was installed. Polars writes the library rooted
    where it sits outside the running interpreter's prefix, and relative to
    that prefix where it sits inside it -- ``lib/python3.13/site-packages/
    gaspatchio/_internal...so`` for a wheel in a virtual environment -- so one
    model renders with either path depending only on the install, and a
    scrub that read the rooted shape alone left half a path in the text:
    ``duration.lib_conditional(...)`` and ``(1.lib) / (itm)``.

    Examples:
        >>> without_plugin_library_paths(
        ...     'col("v").lib/python3.13/site-packages/gaspatchio'
        ...     "/_internal.cpython-313-darwin.so:list_pow([])"
        ... )
        'col("v").<plugin>:list_pow([])'

    """
    return _PLUGIN_LIBRARY_PATH.sub(_PLUGIN_LIBRARY_STANDIN, text)


def quotients_as_operators(text: str) -> str:
    """Return ``text`` with each quotient-kernel call written as its operator.

    Examples:
        >>> quotients_as_operators('col("x").ieee_div([dyn int: 12])')
        '[(col("x")) / (dyn int: 12)]'
        >>> quotients_as_operators(
        ...     '[(col("a")) * (col("b"))].<plugin>:ieee_mod([dyn float: 0.5])'
        ... )
        '[([(col("a")) * (col("b"))]) % (dyn float: 0.5)]'
        >>> quotients_as_operators('col("price / unit")')
        'col("price / unit")'

    """
    searched_from = 0
    while True:
        found = _next_call(text, searched_from)
        if found is None:
            return text
        rewritten = _rewrite_one(text, found)
        if rewritten is None:
            # Unreadable here: keep it, and look past it for the next one.
            searched_from = found.end()
            continue
        text = rewritten
        searched_from = 0


def _next_call(text: str, start: int) -> re.Match[str] | None:
    """Find the next kernel call at or after ``start`` that is not inside a string."""
    for match in _KERNEL_CALL.finditer(text, start):
        if not _inside_string(text, match.start()):
            return match
    return None


def _inside_string(text: str, position: int) -> bool:
    """Whether ``position`` sits inside a double-quoted literal."""
    return text.count('"', 0, position) % 2 == 1


def _rewrite_one(text: str, call: re.Match[str]) -> str | None:
    """Rewrite the one kernel call ``call`` matched, or None if it cannot be read."""
    receiver_start = _receiver_start(text, call.start())
    if receiver_start is None or receiver_start == call.start():
        return None
    argument_open = call.end() - 1
    argument_close = _matching_forward(text, argument_open)
    if argument_close is None:
        return None
    argument = text[argument_open + 1 : argument_close]
    if argument.startswith("[") and _matching_forward(text, argument_open + 1) == (
        argument_close - 1
    ):
        argument = argument[1:-1]
    receiver = text[receiver_start : call.start()]
    operator = _OPERATOR[call.group(1)]
    written = f"[({receiver}) {operator} ({argument})]"
    return text[:receiver_start] + written + text[argument_close + 1 :]


def _receiver_start(text: str, end: int) -> int | None:  # noqa: C901 -- one walk, one case per token kind
    """Walk back from the kernel's method dot over one receiver to where it starts."""
    i = end
    while i > 0:
        c = text[i - 1]
        if c in _OPENING:
            opened = _matching_backward(text, i - 1)
            if opened is None:
                return None
            i = opened
        elif c == '"':
            opened = text.rfind('"', 0, i - 1)
            if opened < 0:
                return None
            i = opened
        elif c.isalnum() or c == "_":
            while i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"):
                i -= 1
        elif c == "." or (c in "+-" and i > 1 and text[i - 2] in "eE"):
            # A method dot, a decimal point, or an exponent's sign.
            i -= 1
        elif c == ":" and text[:i].endswith(_PLACEHOLDER):
            i -= len(_PLACEHOLDER)
        else:
            break
    literal = _TYPED_LITERAL_PREFIX.search(text, 0, i)
    if literal is not None and literal.end() == i:
        i = literal.start()
    return i


def _matching_backward(text: str, close: int) -> int | None:
    """Index of the bracket opening the one at ``close``, skipping strings."""
    depth = 0
    i = close
    while i >= 0:
        c = text[i]
        if c == '"':
            i = text.rfind('"', 0, i)
            if i < 0:
                return None
        elif c in _OPENING:
            depth += 1
        elif c in _CLOSING:
            depth -= 1
            if depth == 0:
                return i
        i -= 1
    return None


def _matching_forward(text: str, open_: int) -> int | None:
    """Index of the bracket closing the one at ``open_``, skipping strings."""
    depth = 0
    i = open_
    while i < len(text):
        c = text[i]
        if c == '"':
            i = text.find('"', i + 1)
            if i < 0:
                return None
        elif c in _CLOSING:
            depth += 1
        elif c in _OPENING:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


# A lowering that holds its operands once (``once.read_once``) and asks for
# them to be written back: how Polars renders the wrapper around the answer.
_STRUCT_OPEN = "as_struct("
_STRUCT_EVAL = ".struct.eval(["
_AS_WRITTEN_TAIL = f'.alias("{ANSWER_AS_WRITTEN}")'
_AS_WRITTEN_FIELD = f".struct.field_by_name({ANSWER_AS_WRITTEN})()"


def read_once_as_written(text: str) -> str:
    """Return ``text`` with each operand held once written back where it is read.

    A per-period comparison of whole numbers or dates, and a per-period clip
    of whole numbers by a bound read from a column, read each operand several
    times; written into the plan at each read, a nested line grew
    geometrically with its depth, so the lowering holds each operand once as
    a struct field (``once.read_once``). That is how it runs, not what the
    model wrote: here the wrapper is read as the answer, each field written
    as its operand, so the record reads as it did and every later rewrite
    finds the line it knows. Innermost first, so a wrapper inside an operand
    is written back before the operand is. A wrapper not shaped as the
    lowering writes it is left as it was.

    Examples:
        >>> read_once_as_written(
        ...     'as_struct(col("x").alias("operand_0")).struct.eval(['
        ...     '[(pl.field(["operand_0"])) + (pl.field(["operand_0"]))]'
        ...     '.alias("answer_as_written")].struct.field_by_name('
        ...     "answer_as_written)()"
        ... )
        '[(col("x")) + (col("x"))]'

    """
    end = len(text)
    while (start := text.rfind(_STRUCT_OPEN, 0, end)) >= 0:
        rewritten = _a_struct_written_back(text, start)
        if rewritten is None:
            end = start
            continue
        text = rewritten
        end = len(text)
    return text


def _a_struct_written_back(text: str, start: int) -> str | None:
    """Write back the wrapper at ``start``, or None if it is not one to write back."""
    if start > 0 and (text[start - 1].isalnum() or text[start - 1] in "._"):
        return None
    opened = start + len(_STRUCT_OPEN) - 1
    closed = _matching_forward(text, opened)
    if closed is None or not text.startswith(_STRUCT_EVAL, closed + 1):
        return None
    listed = closed + len(_STRUCT_EVAL)
    listed_close = _matching_forward(text, listed)
    if listed_close is None or not text.startswith(_AS_WRITTEN_FIELD, listed_close + 1):
        return None
    answer = text[listed + 1 : listed_close]
    if not answer.endswith(_AS_WRITTEN_TAIL):
        return None
    answer = answer[: -len(_AS_WRITTEN_TAIL)]
    for place, operand in enumerate(_top_level_parts(text[opened + 1 : closed])):
        tail = f'.alias("{OPERAND_FIELD.format(place)}")'
        if not operand.endswith(tail):
            return None
        field = f'pl.field(["{OPERAND_FIELD.format(place)}"])'
        answer = answer.replace(field, operand[: -len(tail)])
    return text[:start] + answer + text[listed_close + 1 + len(_AS_WRITTEN_FIELD) :]


# The NaN guards a comparison over doubles carries (``_polars/unknown.py``):
# how a NaN operand is answered as an unknown, not what the model wrote. Each
# piece ends in an alias no formula writes, so it is found by it.
_ALIAS = '.alias("{}")'
_POISON = _ALIAS.format(POISON_MARK)
_AS_NULL = _ALIAS.format(AS_NULL_MARK)
_UNKNOWN = _ALIAS.format(UNKNOWN_MARK)


def nan_guards_as_written(text: str) -> str:
    """Return ``text`` with each NaN guard taken off, the line left as written.

    Three pieces, each found by its mark: an unknown test standing in front
    of a selection, ``.when(<test>).then(<none>).otherwise(<selection>)``,
    read as the selection; a NaN term added to an answer, ``[(<answer>) +
    (<term>)]``, read as the answer; and an operand with its NaN read as a
    null, read as the operand. A piece not shaped as the lowering writes it
    is left as it was, which says more than it means to and never less.

    Examples:
        >>> nan_guards_as_written(
        ...     '[(col("a")) + (col("r").is_nan().alias("gaspatchio:nan_poison"))]'
        ... )
        'col("a")'

    """
    for mark, take_off in (
        (_UNKNOWN, _an_unknown_taken_off),
        (_POISON, _a_term_taken_off),
        (_AS_NULL, _a_null_reading_taken_off),
    ):
        position = 0
        while (found := text.find(mark, position)) >= 0:
            rewritten = take_off(text, found, found + len(mark))
            if rewritten is None:
                position = found + len(mark)
                continue
            text = rewritten
            position = 0
    return text


def _an_unknown_taken_off(text: str, _start: int, end: int) -> str | None:
    """Read ``.when(<test><mark>).then(<none>).otherwise(<chosen>)`` as the chosen."""
    if text[end : end + 1] != ")":
        return None
    opened = _matching_backward(text, end)
    if opened is None or text[opened - len(".when") : opened] != ".when":
        return None
    then = _call_after(text, end + 1, ".then(")
    otherwise = None if then is None else _call_after(text, then[1] + 1, ".otherwise(")
    if otherwise is None:
        return None
    chosen = text[otherwise[0] + 1 : otherwise[1]]
    return text[: opened - len(".when")] + chosen + text[otherwise[1] + 1 :]


def _a_term_taken_off(text: str, _start: int, end: int) -> str | None:
    """Read ``[(<answer>) + (<term><mark>)]`` as the answer."""
    if text[end : end + 2] != ")]":
        return None
    term = _matching_backward(text, end)
    plus = " + "
    if term is None or text[term - len(plus) - 1 : term] != ")" + plus:
        return None
    answer_close = term - len(plus) - 1
    answer = _matching_backward(text, answer_close)
    if answer is None or text[answer - 1 : answer] != "[":
        return None
    return text[: answer - 1] + text[answer + 1 : answer_close] + text[end + 2 :]


def _a_null_reading_taken_off(text: str, start: int, end: int) -> str | None:
    """Read an operand with its NaN read as a null as the operand."""
    if text[start - 1 : start] != ")":
        return None
    opened = _matching_backward(text, start - 1)
    if opened is None:
        return None
    if text[opened - len(".list.eval") : opened] == ".list.eval":
        return text[: opened - len(".list.eval")] + text[end:]
    return _a_policy_s_null_reading_taken_off(text, opened, end)


def _a_policy_s_null_reading_taken_off(text: str, opened: int, end: int) -> str | None:
    """Read Polars' ``.when(<test>).then(<value>).otherwise(null)`` as the value."""
    if text[opened - len(".otherwise") : opened] != ".otherwise":
        return None
    then_close = opened - len(".otherwise") - 1
    then_open = _matching_backward(text, then_close)
    if then_open is None or text[then_open - len(".then") : then_open] != ".then":
        return None
    when_close = then_open - len(".then") - 1
    when_open = _matching_backward(text, when_close)
    if when_open is None or text[when_open - len(".when") : when_open] != ".when":
        return None
    value = text[then_open + 1 : then_close]
    return text[: when_open - len(".when")] + value + text[end:]


def _call_after(text: str, at: int, call: str) -> tuple[int, int] | None:
    """Return the brackets of ``call`` written at ``at``, or None."""
    if not text.startswith(call, at):
        return None
    opened = at + len(call) - 1
    closed = _matching_forward(text, opened)
    return None if closed is None else (opened, closed)


# The three list kernels a model reaches through a line it wrote with an
# operator or a method, and which a rendering otherwise names by the Rust
# symbol: ``x ** list`` lowers to ``list_pow``, ``list.clip(lo, hi)`` to
# ``list_clip``, and ``when(...)`` over a per-period column to
# ``list_conditional``. A reader can find none of those three names in what
# they wrote, so each is written as Polars writes the operation it computes:
# ``.pow(...)``, ``.clip(...)``, and ``.when(...).then(...).otherwise(...)``.
_RENAMED_KERNEL = re.compile(r"\.(?:<plugin>:)?list_(pow|clip)\(")
_CONDITIONAL_CALL = re.compile(r"\.(?:<plugin>:)?list_conditional\(")

# The conditional kernel's comparison, which travels in its keyword
# arguments and never in its rendering, and how Polars writes each one.
_COMPARISON_WRITTEN = {
    "eq": "==",
    "ne": "!=",
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
}

# The keyword arguments as Polars hands them to the kernel: pickled at
# protocol 5 (``polars.plugins._serialize_kwargs``), so each of the six is a
# fixed run of bytes. Read by comparison, never by unpickling: a run that is
# not one of these six is a comparison this reading does not know, and the
# rendering keeps the kernel's own name.
_OPERATOR_OF_KWARGS = {
    pickle.dumps(conditional_kwargs(operator, unknown_is_nan=nan), protocol=5): operator
    for operator in _COMPARISON_WRITTEN
    for nan in (False, True)
}


def kernels_as_operations(text: str, comparisons: Sequence[str] | None) -> str:
    """Return ``text`` with each list kernel written as the operation it computes.

    ``comparisons`` are the conditional kernel's comparisons in the order
    the rendering writes its calls (:func:`conditional_comparisons`). They
    are not in the text, so where they were not read, or there is not one
    for every call, or one of them is a comparison this reading does not
    know, every conditional call keeps its name: a ``when`` written with the
    wrong comparison would be worse than the kernel's name.

    Examples:
        >>> kernels_as_operations(
        ...     'col("d").list_conditional([dyn int: 1, col("sa"), dyn float: 0])',
        ...     ["gt"],
        ... )
        '.when([(col("d")) > (dyn int: 1)]).then(col("sa")).otherwise(dyn float: 0)'
        >>> kernels_as_operations('col("b").<plugin>:list_pow([col("e")])', None)
        'col("b").pow([col("e")])'

    """
    text = _RENAMED_KERNEL.sub(
        lambda found: (
            found.group(0)
            if _inside_string(text, found.start())
            else f".{found.group(1)}("
        ),
        text,
    )
    text = checked_whole_numbers_as_written(text)
    text = comparisons_of_a_null_run_as_written(text)
    text, comparisons = exact_comparisons_as_written(text, comparisons)
    calls = [
        call
        for call in _CONDITIONAL_CALL.finditer(text)
        if not _inside_string(text, call.start())
    ]
    if (
        not calls
        or comparisons is None
        or len(comparisons) != len(calls)
        or any(one not in _COMPARISON_WRITTEN for one in comparisons)
    ):
        return text
    written = text
    for comparison in comparisons:
        call = next(
            (
                one
                for one in _CONDITIONAL_CALL.finditer(written)
                if not _inside_string(written, one.start())
            ),
            None,
        )
        rewritten = None if call is None else _when_for(written, call, comparison)
        if rewritten is None:
            # One call unreadable puts every later comparison against the
            # wrong call, so none of them is written.
            return text
        written = rewritten
    return written


# How the lowering writes a per-period comparison of two runs, as Polars
# renders it: the comparison is taken null for a policy whose right-hand run
# is null (``polars._null_where_the_run_is_null``), wrapped around the
# conditional kernel's call.
_NULL_RUN_GUARD = ".when("
_NULL_RUN_TEST = ".is_null()"
_NULL_RUN_ELSE = ".then(null).otherwise("


def comparisons_of_a_null_run_as_written(text: str) -> str:
    """Return ``text`` with each comparison's null-run guard taken off.

    The guard is how the comparison is computed, not what the model wrote:
    a policy with no right-hand run answers null, as one with no left-hand
    run already did inside the kernel. It is read only where it stands
    around a conditional kernel call that reads the guarded run, which the
    lowering writes and a model's own ``when`` over a run does not (that is
    a kernel call itself); anything else keeps the text it had.

    Examples:
        >>> comparisons_of_a_null_run_as_written(
        ...     '.when(col("g").is_null()).then(null).otherwise('
        ...     'col("a").list_conditional([col("g"), 1, 0]))'
        ... )
        'col("a").list_conditional([col("g"), 1, 0])'

    """
    position = 0
    while (start := text.find(_NULL_RUN_GUARD, position)) >= 0:
        position = start + 1
        if _inside_string(text, start):
            continue
        tested = _matching_forward(text, start + len(_NULL_RUN_GUARD) - 1)
        if tested is None:
            continue
        run = text[start + len(_NULL_RUN_GUARD) : tested]
        if not run.endswith(_NULL_RUN_TEST) or not text.startswith(
            _NULL_RUN_ELSE, tested + 1
        ):
            continue
        run = run.removesuffix(_NULL_RUN_TEST)
        opened = tested + len(_NULL_RUN_ELSE)
        closed = _matching_forward(text, opened)
        if closed is None:
            continue
        compared = text[opened + 1 : closed]
        if run not in compared or _CONDITIONAL_CALL.search(compared) is None:
            continue
        text = text[:start] + compared + text[closed + 1 :]
        position = start
    return text


# How the lowering writes an operation of whole numbers it checks for a value
# no answer holds -- a fold whose exact total is past ``i64``
# (``polars.whole_numbers_folded_exactly``), a per-period clip past 2**53
# (``rules.bounds``), the absolute value of -2**63 (``rules.maths``) -- as
# Polars renders it: the operation, taken where a
# check answers nought. The check carries one of these sentences, which
# nothing a model writes does.
_FOLD_RULES = (
    SUM_PAST_I64_RULE,
    RUNNING_SUM_PAST_I64_RULE,
    RUNNING_PRODUCT_PAST_I64_RULE,
    REMAINING_SUM_PAST_I64_RULE,
    CLIP_PAST_2_53_RULE,
    ABSOLUTE_VALUE_PAST_I64_RULE,
)
_CHECKED_AT_NOUGHT = ") == (dyn int: 0)]"
_TAKEN_WHERE_IT_PASSES = ".then("
_AND_NOTHING_ELSE = ".otherwise(null)"


def checked_whole_numbers_as_written(text: str) -> str:
    """Return ``text`` with each whole-number fold's or clip's range check taken off.

    The check is how an answer no type holds is refused, not what the model
    wrote; the operation it guards is. It is read only where its condition
    holds one of these sentences; anything else keeps the text it had.

    Examples:
        >>> rule = "whole numbers whose sum lies past the Int64 range"
        >>> checked_whole_numbers_as_written(
        ...     f'.when([(.when(ok).then("0").otherwise("{rule}")'
        ...     ".strict_cast(Int64)) == (dyn int: 0)])"
        ...     '.then(col("n").list.sum()).otherwise(null)'
        ... )
        'col("n").list.sum()'

    """
    position = 0
    while (start := text.find(_NULL_RUN_GUARD, position)) >= 0:
        position = start + 1
        if _inside_string(text, start):
            continue
        tested = _matching_forward(text, start + len(_NULL_RUN_GUARD) - 1)
        if tested is None:
            continue
        condition = text[start + len(_NULL_RUN_GUARD) : tested]
        if not condition.endswith(_CHECKED_AT_NOUGHT) or not any(
            rule in condition for rule in _FOLD_RULES
        ):
            continue
        if not text.startswith(_TAKEN_WHERE_IT_PASSES, tested + 1):
            continue
        opened = tested + len(_TAKEN_WHERE_IT_PASSES)
        closed = _matching_forward(text, opened)
        if closed is None or not text.startswith(_AND_NOTHING_ELSE, closed + 1):
            continue
        folded = text[opened + 1 : closed]
        text = text[:start] + folded + text[closed + 1 + len(_AND_NOTHING_ELSE) :]
        position = start
    return text


def _when_for(text: str, call: re.Match[str], comparison: str) -> str | None:
    """Rewrite one conditional-kernel call as the ``when`` it computes."""
    receiver_start = _receiver_start(text, call.start())
    if receiver_start is None or receiver_start == call.start():
        return None
    argument_open = call.end() - 1
    argument_close = _matching_forward(text, argument_open)
    if argument_close is None:
        return None
    argument = text[argument_open + 1 : argument_close]
    if not (
        argument.startswith("[")
        and _matching_forward(text, argument_open + 1) == argument_close - 1
    ):
        return None
    parts = _top_level_parts(argument[1:-1])
    if len(parts) != len(("right", "then", "otherwise")):
        return None
    right, then, otherwise = parts
    receiver, right = labels_for_codes(text[receiver_start : call.start()], right)
    written = (
        f".when([({receiver}) {_COMPARISON_WRITTEN[comparison]} ({right})])"
        f".then({then}).otherwise({otherwise})"
    )
    return text[:receiver_start] + written + text[argument_close + 1 :]


# How the lowering writes a per-period comparison it decides exactly
# (``frame/lowering/_polars/comparisons.py``), as Polars renders it: the two
# sides' difference in Int128, as a run of doubles, against a nought. A side
# is read as its count of units (``.to_physical()``), may be scaled to the
# finer of two units (``[(side) * (1000)]``), and a run on the right is
# taken only where its length agrees (``.when(...).then(side)...``).
_NOUGHT = "dyn float: 0"
_AS_DOUBLES = ".strict_cast(List(Float64))"
_IN_INT128 = (".strict_cast(List(Int128))", ".strict_cast(Int128)")
_AS_COUNT = ".to_physical()"
_SCALED = re.compile(r"\[\((?P<side>.+)\) \* \(\d+\)\]", re.DOTALL)


def exact_comparisons_as_written(
    text: str, comparisons: Sequence[str] | None
) -> tuple[str, Sequence[str] | None]:
    """Return ``text`` with each exactly decided comparison written as its two values.

    Two forms are read back, and each conditional call keeps its place in
    ``comparisons`` (one per call, in rendering order):

    - a run against a value: ``D.list_conditional([0, then, otherwise])``,
      where ``D`` is the difference, is written
      ``left.list_conditional([right, then, otherwise])``;
    - a run against a run: the kernel is first called over the two runs to
      check their lengths, selecting the difference either way, and then
      against nought. The pair is written as the one call it stands for,
      and the check's own comparison leaves ``comparisons``.

    Anything else -- a 128-bit value decided by its pieces, a form this
    reading does not know -- keeps the text it had.

    Examples:
        >>> exact_comparisons_as_written(
        ...     '[(col("d").strict_cast(List(Int128))) - (1.strict_cast(Int128))]'
        ...     ".strict_cast(List(Float64)).list_conditional("
        ...     '[dyn float: 0, col("sa"), dyn float: 0])',
        ...     ["gt"],
        ... )
        ('col("d").list_conditional([1, col("sa"), dyn float: 0])', ['gt'])

    """
    if comparisons is None:
        return text, comparisons
    order = list(comparisons)
    written = text
    position, index = 0, 0
    while (call := _next_conditional(written, position)) is not None:
        # Past the call's own name: a call inside its receiver came earlier in
        # the text and in ``comparisons``, and one inside its arguments later.
        position = call.end()
        read = _conditional_parts(written, call)
        if read is not None:
            start, receiver, parts, close = read
            collapsed = _a_run_against_a_run(written, call, read)
            sides = _difference_sides(receiver) if parts[0] == _NOUGHT else None
            if collapsed is not None and index + 1 < len(order):
                written = collapsed
                del order[index]
            elif sides is not None and len(parts) == len(("right", "then", "else")):
                head = f"{sides[0]}{call.group(0)}[{sides[1]}, {parts[1]}, {parts[2]}])"
                written = written[:start] + head + written[close + 1 :]
                position = start + len(sides[0]) + len(call.group(0))
        index += 1
    return written, order


def _next_conditional(text: str, position: int) -> re.Match[str] | None:
    """Return the first conditional-kernel call at or after ``position``."""
    return next(
        (
            one
            for one in _CONDITIONAL_CALL.finditer(text, position)
            if not _inside_string(text, one.start())
        ),
        None,
    )


def _conditional_parts(
    text: str, call: re.Match[str]
) -> tuple[int, str, list[str], int] | None:
    """Return a conditional call's receiver start and text, its parts, and its close."""
    start = _receiver_start(text, call.start())
    argument_open = call.end() - 1
    close = _matching_forward(text, argument_open)
    if start is None or start == call.start() or close is None:
        return None
    argument = text[argument_open + 1 : close]
    if not (
        argument.startswith("[")
        and _matching_forward(text, argument_open + 1) == close - 1
    ):
        return None
    return start, text[start : call.start()], _top_level_parts(argument[1:-1]), close


def _a_run_against_a_run(
    text: str, call: re.Match[str], read: tuple[int, str, list[str], int]
) -> str | None:
    """Return the length check and the comparison after it written as one call."""
    start, receiver, parts, close = read
    if len(parts) != len(("right", "then", "otherwise")) or parts[1] != parts[2]:
        return None
    if _difference_sides(parts[1]) is None:
        return None
    following = _CONDITIONAL_CALL.match(text, close + 1)
    if following is None:
        return None
    after = _conditional_parts(text, following)
    if after is None or len(after[2]) != len(parts) or after[2][0] != _NOUGHT:
        return None
    head = f"{receiver}{call.group(0)}[{parts[0]}, {after[2][1]}, {after[2][2]}])"
    return text[:start] + head + text[after[3] + 1 :]


def _difference_sides(text: str) -> tuple[str, str] | None:
    """Return the two values a rendered exact difference was taken between."""
    if not (text.startswith("[") and text.endswith("]" + _AS_DOUBLES)):
        return None
    close = _matching_forward(text, 0)
    if close != len(text) - len(_AS_DOUBLES) - 1:
        return None
    sides = _top_level_difference(text[1:close])
    if sides is None:
        return None
    left, right = (_counted_side(side) for side in sides)
    if left is None or right is None:
        return None
    return left, right


def _top_level_difference(text: str) -> tuple[str, str] | None:
    """Split ``(a) - (b)`` into ``a`` and ``b``, each a balanced group."""
    if not text.startswith("("):
        return None
    close = _matching_forward(text, 0)
    if close is None or not text.startswith(" - (", close + 1):
        return None
    other = close + len(" - (")
    if _matching_forward(text, other) != len(text) - 1:
        return None
    return text[1:close], text[other + 1 : -1]


def _counted_side(text: str) -> str | None:
    """Return a side as the model wrote it, its count, scale and width taken off."""
    if text.startswith(".when("):
        guarded = _matching_forward(text, len(".when(") - 1)
        if guarded is None or not text.startswith(".then(", guarded + 1):
            return None
        opened = guarded + len(".then(")
        closed = _matching_forward(text, opened)
        if closed is None:
            return None
        text = text[opened + 1 : closed]
    scaled = _SCALED.fullmatch(text)
    if scaled is not None and _matching_forward(text, 1) == len(scaled["side"]) + 2:
        text = scaled["side"]
    widened = next((one for one in _IN_INT128 if text.endswith(one)), None)
    if widened is None:
        return None
    return text.removesuffix(widened).removesuffix(_AS_COUNT)


# How the lowering writes a per-period Categorical or Enum equality for the
# conditional kernel, as Polars renders it. The column is read as its codes.
# The right-hand value is cast to the column's own dtype and read as its code,
# with -1 for a value none of the categories hold; a value per policy keeps a
# null a null, and a list per policy does that for each period. Each form
# holds the operand the model wrote exactly once in each place it appears, so
# reading it back is a match, never a guess -- and anything else keeps the
# text it had.
_CODES_DTYPE = r"(?:Categorical(?:\([^()]*\))?|Enum\(\[\.\.\.\]\))"
_AS_CODE = rf"\.cast\({_CODES_DTYPE}\)\.to_physical\(\)\.fill_null\(\[dyn int: -1\]\)"
_COLUMN_AS_CODES = ".to_physical()"
_RIGHT_AS_CODES = (
    # A value per policy, its null kept.
    re.compile(
        r"\.when\((?P<value>.+)\.is_null\(\)\)\.then\(null\)"
        rf"\.otherwise\((?P=value){_AS_CODE}\)",
        re.DOTALL,
    ),
    # A list per policy, each period's null kept.
    re.compile(
        r"(?P<value>.+)\.list\.eval\(\.when\(element\(\)\.is_null\(\)\)"
        rf"\.then\(null\)\.otherwise\(element\(\){_AS_CODE}\)\)",
        re.DOTALL,
    ),
    # One value the model wrote.
    re.compile(rf"(?P<value>.+){_AS_CODE}", re.DOTALL),
)


def labels_for_codes(receiver: str, right: str) -> tuple[str, str]:
    """Return a conditional's two operands as labels where they ran as codes.

    ``af.plan == "A"`` over a per-period Categorical column is handed to
    the kernel as the column's codes against the code ``"A"`` has in it,
    because codes cross the plugin boundary as plain integers and labels do
    not. That is how it ran, not what the model says, so a reader is shown
    the comparison the model wrote. Operands in any other form are
    returned as they came.

    Examples:
        >>> labels_for_codes(
        ...     'col("plan").to_physical()',
        ...     '"A".cast(Categorical).to_physical().fill_null([dyn int: -1])',
        ... )
        ('col("plan")', '"A"')
        >>> labels_for_codes('col("plan")', '"A"')
        ('col("plan")', '"A"')

    """
    if not receiver.endswith(_COLUMN_AS_CODES):
        return receiver, right
    for form in _RIGHT_AS_CODES:
        found = form.fullmatch(right)
        if found is not None:
            return receiver.removesuffix(_COLUMN_AS_CODES), found["value"]
    return receiver, right


def _top_level_parts(text: str) -> list[str]:
    """Split ``text`` at the commas no bracket or string encloses."""
    parts: list[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(text):
        c = text[i]
        if c == '"':
            closing = text.find('"', i + 1)
            i = len(text) if closing < 0 else closing
        elif c in _CLOSING:
            depth += 1
        elif c in _OPENING:
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
        i += 1
    parts.append(text[start:].strip())
    return parts


def _a_null_run_guard(node: dict[str, object]) -> object | None:
    """Return what a null-run guard selects, where ``node`` is one the text loses.

    The lowering wraps a per-period comparison or selection in ``when(run
    .is_null()).then(null).otherwise(selected)``, and
    :func:`comparisons_of_a_null_run_as_written` takes that guard off the
    text where ``selected`` reads the run and calls the conditional kernel.
    A run that is itself a selection -- the rest of a ``when`` chain --
    carries kernel calls of its own inside the guard's test, which the text
    no longer shows, so they leave ``comparisons`` with it. Anything else
    is None and is walked as it stands.
    """
    ternary = node.get("Ternary")
    if not isinstance(ternary, dict):
        return None
    test, chosen = ternary.get("predicate"), ternary.get("falsy")
    truthy = ternary.get("truthy")
    if not isinstance(test, dict) or truthy != {
        "Literal": {"Scalar": {"Null": "Null"}}
    }:
        return None
    function = test.get("Function")
    if not isinstance(function, dict) or function.get("function") != {
        "Boolean": "IsNull"
    }:
        return None
    inputs = function.get("input")
    if not isinstance(inputs, list) or len(inputs) != 1:
        return None
    chosen_text = json.dumps(chosen, sort_keys=True)
    if (
        json.dumps(inputs[0], sort_keys=True) not in chosen_text
        or '"symbol": "list_conditional"' not in chosen_text
    ):
        return None
    return chosen


def conditional_comparisons(expr: pl.Expr) -> tuple[str, ...] | None:
    """Return each conditional-kernel call's comparison, in rendering order.

    Read off the expression's own serialised tree, because the comparison
    is a keyword argument and the rendering never prints one. The order is
    the one the rendering writes the calls in: a method call renders its
    receiver first, then its own name, then its other arguments, and the
    walk below visits them the same way. None where the expression cannot
    be serialised -- a Python function inside it, say -- which leaves every
    conditional call under its own name.
    """
    try:
        tree = json.loads(expr.meta.serialize(format="json"))
    except Exception:  # noqa: BLE001 -- a reading for the record never fails the export; whatever the engine raises, the calls keep their names
        return None
    found: list[str] = []
    _comparisons_in(tree, found)
    return tuple(found)


def _comparisons_in(
    node: object, found: list[str], fields: dict[str, object] | None = None
) -> None:
    """Append the comparison of each conditional-kernel call under ``node``.

    A wrapper written back where its answer reads its operands
    (:func:`read_once_as_written`) is walked the same way: its answer, with
    each field read as the operand it holds, wherever and as often as the
    answer reads it.
    """
    if isinstance(node, list):
        for one in node:
            _comparisons_in(one, found, fields)
        return
    if not isinstance(node, dict) or _walked_as_written(node, found, fields):
        return
    guarded = _a_null_run_guard(node)
    if guarded is not None:
        _comparisons_in(guarded, found, fields)
        return
    function = node.get("Function")
    plugin = (
        function.get("function", {}).get("FfiPlugin")
        if isinstance(function, dict) and isinstance(function.get("function"), dict)
        else None
    )
    if isinstance(plugin, dict) and plugin.get("symbol") == "list_conditional":
        inputs = function.get("input") or []  # type: ignore[union-attr]
        if inputs:
            _comparisons_in(inputs[0], found, fields)
        kwargs = bytes(plugin.get("kwargs") or [])
        found.append(_OPERATOR_OF_KWARGS.get(kwargs, ""))
        for one in inputs[1:]:
            _comparisons_in(one, found, fields)
        return
    for value in node.values():
        _comparisons_in(value, found, fields)


def _walked_as_written(
    node: dict[str, object], found: list[str], fields: dict[str, object] | None
) -> bool:
    """Walk a field as its operand, or a held wrapper as its answer; say if done."""
    field = node.get("Field")
    if fields is not None and isinstance(field, list) and field and field[0] in fields:
        _comparisons_in(fields[field[0]], found, None)
        return True
    held = _held_once(node)
    if held is None:
        return False
    answer, operands = held
    _comparisons_in(answer, found, operands)
    return True


def _held_once(node: dict[str, object]) -> tuple[object, dict[str, object]] | None:
    """Return a written-back wrapper's answer and its operands by field, or None."""
    function = node.get("Function")
    if not isinstance(function, dict) or function.get("function") != {
        "StructExpr": {"FieldByName": ANSWER_AS_WRITTEN}
    }:
        return None
    inputs = function.get("input")
    evaluated = (
        inputs[0].get("StructEval")
        if isinstance(inputs, list) and inputs and isinstance(inputs[0], dict)
        else None
    )
    if not isinstance(evaluated, dict):
        return None
    made = evaluated.get("expr", {})
    built = made.get("Function", {}) if isinstance(made, dict) else {}
    operands: dict[str, object] = {}
    for part in built.get("input", []) if isinstance(built, dict) else []:
        alias = part.get("Alias") if isinstance(part, dict) else None
        if isinstance(alias, list) and len(alias) == 2:  # noqa: PLR2004 -- an alias is an expression and a name
            operands[alias[1]] = alias[0]
    answers = evaluated.get("evaluation")
    if not isinstance(answers, list) or len(answers) != 1:
        return None
    alias = answers[0].get("Alias") if isinstance(answers[0], dict) else None
    if not isinstance(alias, list) or len(alias) != 2:  # noqa: PLR2004 -- as above
        return None
    return alias[0], operands
