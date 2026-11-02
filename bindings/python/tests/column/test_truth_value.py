# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A column has no truth value, and no longer pretends to have one.

``when(af.a and af.b)`` is the line this file exists for. Python's ``and``
asks its left operand for a single true or false; a column holds one answer
per policy and cannot give one. While the question was answerable the
expression quietly evaluated to ``af.b`` alone, so every policy the first
test excluded was paid anyway -- no exception, no warning, and an exported
record showing a well-formed one-column predicate, which is the worst
combination available: the audit trail reads correctly while the number is
wrong.

Both halves of the surface are exercised, because they are not one class.
``ColumnProxy`` and ``ExpressionProxy`` inherit the refusal from the
generated surface; ``ConditionExpression`` -- what a comparison returns, and
so what ``(af.age > 60) and (af.sa > 1000000)`` asks the question of -- is
not built on that surface and states the refusal itself.

The element-wise operators are pinned beside the refusals, because a
refusal that left ``&`` broken would have closed the only door out.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

# The frame from the reading: policy 2 passes `b` and fails `a`, so `and`
# and `&` disagree about it and the disagreement is one payment.
_TWO_FLAGS = {"a": [True, False], "b": [True, True], "x": [1.0, 2.0]}

_NO_TRUTH_VALUE = "no single true-or-false value"


def _flags() -> ActuarialFrame:
    """Return the two-policy frame whose second policy separates & from and."""
    return ActuarialFrame(pl.DataFrame(_TWO_FLAGS))


def _lives() -> ActuarialFrame:
    """Return a frame whose comparisons disagree on the second life."""
    return ActuarialFrame(
        pl.DataFrame({"age": [70, 50], "sum_assured": [2e6, 2e6], "x": [1.0, 2.0]})
    )


# --- the refusal, on each of the three things a model author writes ----------


def test_a_column_refuses_every_spelling_of_the_question() -> None:
    """``bool``, ``and``, ``or``, ``not``, ``if`` and ``assert`` all raise."""
    frame = _flags()

    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        bool(frame.a)
    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        _ = frame.a and frame.b
    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        _ = frame.a or frame.b
    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        _ = not frame.a
    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        if frame.a:
            pass
    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        assert frame.a


def test_a_comparison_refuses_every_spelling_of_the_question() -> None:
    """The predicate a comparison returns has no truth value either."""
    frame = _lives()
    over_sixty = frame.age > 60
    large = frame.sum_assured > 1e6

    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        bool(over_sixty)
    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        _ = over_sixty and large
    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        _ = over_sixty or large
    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        _ = not over_sixty
    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        if over_sixty:
            pass
    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        assert over_sixty


def test_an_unfinished_expression_refuses_the_question() -> None:
    """A formula still being built is a column's worth of answers too."""
    frame = _flags()

    with pytest.raises(TypeError, match=_NO_TRUTH_VALUE):
        bool(frame.x * 2)


def test_the_refusal_names_the_operators_that_do_the_work() -> None:
    """Actuarial concept, then the next move -- the error-message contract."""
    frame = _flags()

    with pytest.raises(TypeError) as raised:
        _ = frame.a and frame.b

    message = str(raised.value)
    assert "one answer per policy" in message
    assert "&" in message
    assert "when(<test>).then(<value>).otherwise(<other value>)" in message


# --- the door the refusal points at, which has to still open -----------------


def test_the_element_wise_operators_answer_policy_by_policy() -> None:
    """``&``, ``|`` and ``~`` are what the refusal sends the author to."""
    frame = _flags()

    frame.both = frame.a & frame.b
    frame.either = frame.a | frame.b
    frame.neither = ~frame.a

    result = frame.collect()
    assert result["both"].to_list() == [True, False]
    assert result["either"].to_list() == [True, True]
    assert result["neither"].to_list() == [False, True]


def test_the_conditional_pays_the_policies_the_test_selects() -> None:
    """The reading's own line, with the answer ``and`` could not give.

    ``when(af.a and af.b)`` paid both policies. ``when(af.a & af.b)`` pays
    the first and not the second, which is what the two flags say.
    """
    frame = _flags()

    frame.paid = when(frame.a & frame.b).then(frame.x).otherwise(0.0)

    assert frame.collect()["paid"].to_list() == [1.0, 0.0]


def test_bracketed_comparisons_combine_the_way_the_refusal_says() -> None:
    """``(af.age > 60) & (af.sum_assured > 1e6)`` selects the older life only."""
    frame = _lives()

    frame.selected = when((frame.age > 60) & (frame.sum_assured > 1e6)).then(
        frame.x
    ).otherwise(0.0)

    assert frame.collect()["selected"].to_list() == [1.0, 0.0]
