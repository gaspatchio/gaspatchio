# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Assigning to a name the frame already uses refuses, and says what to write.

``ActuarialFrame`` carries 33 public names. Five are accessors, and the
accessor guard already closed those: ``af.date = ...`` refuses, names the
accessor, and points at ``af["date"] = ...``. The other 28 were outside that guard's
reach, and fell into ``object.__setattr__``:

* **25 swallowed the assignment.** The expression was stored on the
  instance, no column was minted, ``collect()`` returned a frame without
  it, and nothing was raised. ``sum``, ``count``, ``min``, ``max`` and
  ``product`` are ordinary model-point field names, so ``af.sum = ...``
  was a line an actuary could reasonably write and watch do nothing. The
  worst was ``collect``: silent at the assignment, and surfacing much
  later as ``TypeError: 'ExpressionProxy' object is not callable`` when
  the frame was collected, naming neither the column meant nor the line
  that wrote it.
* **3 refused with the wrong sentence.** ``columns``, ``dtypes`` and
  ``schema`` are read-only properties, so Python answered ``property
  'columns' of 'ActuarialFrame' object has no setter`` -- which says
  nothing about columns, which is exactly what the accessor guard was written
  to stop.

Now every one of the 33 refuses, in the accessor guard's voice: the name,
that no column was created, and ``af["<name>"] = ...`` as the door. The
last clause says what the name already is -- a method, or a property --
where the accessor guard's says where ``af.<name>`` reads to.

Pinned here: every swallowed name refusing, parametrised over the whole
set rather than a favourite few; ``collect`` refusing at the assignment
rather than at the call; the three properties carrying the new sentence;
the bracket form still writing and reading a column called ``sum``,
including on a frame that arrived with one; an accessor name still
answering with the accessor guard's own sentence; internal attribute setting still
working; and ordinary column assignment and reassignment untouched.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

# The five accessor names, which the accessor guard answers for and this one does
# not reach. Every other public name on the class is this guard's set.
ACCESSOR_NAMES = frozenset({"date", "excel", "finance", "graph", "projection"})

# The three read-only properties. They refused before this change too, with
# Python's own sentence; what changed for them is only what the user reads.
PROPERTY_NAMES = ["columns", "dtypes", "schema"]

# The 25 that swallowed the assignment. Spelled out rather than read off
# the class, so that a name leaving the public surface is a test failure
# and not a silently shorter parametrisation. ``test_the_set_is_the_whole
# _public_surface`` below pins the two against each other.
SWALLOWED_NAMES = [
    "collect",
    "count",
    "drop",
    "fill_series",
    "filter",
    "get_column_order",
    "join",
    "materialize",
    "max",
    "mean",
    "median",
    "min",
    "pipe",
    "product",
    "profile",
    "quantile",
    "rename",
    "select",
    "show_query_plan",
    "sort",
    "std",
    "sum",
    "trace",
    "var",
    "with_columns",
]


def _frame() -> ActuarialFrame:
    """Two policies, one column, no reserved name among them."""
    return ActuarialFrame(pl.DataFrame({"premium": [10.0, 20.0]}))


def test_the_set_is_the_whole_public_surface() -> None:
    """The three lists above account for every public name on the class.

    A method added to ``ActuarialFrame`` joins the guard's set the day it
    lands -- the predicate is the class, not a list -- and this is what
    says so out loud rather than leaving the parametrisations to quietly
    cover less of the surface than they claim.
    """
    public = {name for name in dir(ActuarialFrame) if not name.startswith("_")}

    assert public == ACCESSOR_NAMES | set(PROPERTY_NAMES) | set(SWALLOWED_NAMES)
    assert len(public) == 33


@pytest.mark.parametrize("name", SWALLOWED_NAMES)
def test_a_name_the_frame_already_uses_refuses(name: str) -> None:
    """The refusal names it, says no column was created, and gives the door."""
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    message = str(excinfo.value)
    assert f"'{name}' is a name ActuarialFrame already uses" in message
    assert "created no column" in message
    assert f"af['{name}'] = ..." in message
    assert f"af.{name} is the frame's own {name}() method." in message


@pytest.mark.parametrize("name", SWALLOWED_NAMES)
def test_the_refusal_leaves_no_shadow_behind(name: str) -> None:
    """No column, no instance attribute, and the method still answers."""
    af = _frame()

    with pytest.raises(AttributeError):
        setattr(af, name, pl.lit(1.0))

    assert name not in af.__dict__
    assert name not in af.columns
    assert callable(getattr(af, name))


def test_collect_refuses_at_the_assignment_not_at_the_call() -> None:
    """The one that used to fail a screen later, with no column named.

    Before this change ``af.collect = <expression>`` stored the proxy over
    the method and said nothing; the frame then died on the next
    ``af.collect()`` with ``TypeError: 'ExpressionProxy' object is not
    callable``, which names neither the column meant nor the line that
    wrote it. The failure now lands on the line that caused it.
    """
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        af.collect = af.premium * 2  # type: ignore[method-assign, assignment]

    assert "'collect' is a name ActuarialFrame already uses" in str(excinfo.value)
    # And the frame is still a frame: collect() answers, with no stray column.
    assert af.collect().columns == ["premium"]


@pytest.mark.parametrize("name", PROPERTY_NAMES)
def test_a_property_name_refuses_with_the_new_sentence(name: str) -> None:
    """These already refused; Python's sentence said nothing about columns."""
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    message = str(excinfo.value)
    assert f"'{name}' is a name ActuarialFrame already uses" in message
    assert "created no column" in message
    assert f"af['{name}'] = ..." in message
    assert f"af.{name} is the frame's own {name} property." in message
    assert "has no setter" not in message


@pytest.mark.parametrize("name", PROPERTY_NAMES)
def test_a_property_still_reads_after_a_refused_assignment(name: str) -> None:
    """The refusal changed the sentence, not the behaviour."""
    af = _frame()

    with pytest.raises(AttributeError):
        setattr(af, name, pl.lit(1.0))

    assert getattr(af, name) == getattr(_frame(), name)


def test_the_bracket_form_still_writes_and_reads_a_column_called_sum() -> None:
    """``sum`` is an ordinary model-point field name, and brackets are the door."""
    af = _frame()

    af["sum"] = af.premium * 10

    assert af["sum"].name == "sum"
    assert af.columns == ["premium", "sum"]
    assert af.collect()["sum"].to_list() == [100.0, 200.0]


def test_a_frame_that_arrived_with_a_sum_column_keeps_it() -> None:
    """The refusal creates nothing and destroys nothing.

    ``af.sum`` READS as a conflict on such a frame rather than as the
    column, so the write refuses to match. Brackets answer on both sides.
    """
    af = ActuarialFrame(pl.DataFrame({"sum": [5.0], "premium": [10.0]}))

    with pytest.raises(AttributeError) as excinfo:
        af.sum = pl.lit(9.0)  # type: ignore[method-assign, assignment]

    assert "'sum' is a name ActuarialFrame already uses" in str(excinfo.value)
    assert af.collect()["sum"].to_list() == [5.0]

    af["sum"] = pl.lit(9.0)
    assert af.collect()["sum"].to_list() == [9.0]


def test_an_accessor_name_still_refuses_with_the_accessor_guard_s_sentence() -> None:
    """The accessor guard sits above this one and answers for its five names first."""
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        af.projection = pl.lit(1.0)  # type: ignore[assignment]

    message = str(excinfo.value)
    assert "'projection' is a registered accessor name" in message
    assert "af.projection goes on reaching the frame accessor" in message
    assert "ActuarialFrame already uses" not in message


def test_internal_attribute_setting_still_works() -> None:
    """Underscore names never reach the guard; the frame's own writes stand."""
    af = _frame()

    af._mode = "debug"  # noqa: SLF001 -- the internals under test
    af._verbose = True  # noqa: SLF001 -- the internals under test

    assert af._mode == "debug"  # noqa: SLF001 -- the internals under test
    assert af._verbose is True  # noqa: SLF001 -- the internals under test
    # And an underscore name the frame does not know is still refused by the
    # branch that always refused it, not by this guard.
    with pytest.raises(AttributeError) as excinfo:
        af._not_a_frame_internal = 1  # noqa: SLF001 -- not a known internal

    assert "is not a valid attribute name" in str(excinfo.value)


def test_ordinary_column_assignment_and_reassignment_still_work() -> None:
    """The guard is keyed on the class, so an ordinary name is untouched."""
    af = _frame()

    af.claims = af.premium * 2
    assert af.collect()["claims"].to_list() == [20.0, 40.0]

    af.claims = af.premium * 3
    assert af.collect()["claims"].to_list() == [30.0, 60.0]
    assert af.columns == ["premium", "claims"]
