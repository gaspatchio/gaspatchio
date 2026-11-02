# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Assigning to a registered accessor name refuses, and says what to write.

``af.date = <value>`` used to fall through the column-assignment path --
the path excludes every name in ``_ACCESSOR_REGISTRY`` -- and reach
``object.__setattr__``. For the five accessors the frame declares as
properties that raised Python's own ``property 'date' of 'ActuarialFrame'
object has no setter``, which says nothing about columns; for any other
registered accessor name it stored an instance attribute, minted no
column, and left later reads returning the stored value instead of the
accessor. Neither told an actuary that the column they wrote was never
created.

Now the seam refuses first, for every name in the registry, and the
refusal names the accessor, says no column was created, and gives
``af["date"] = ...`` as the door that works.

The refusal's last clause is keyed on the KIND registered under the name,
because that is what decides where ``af.<name>`` goes. ``__getattr__``
returns a FRAME accessor and nothing else does, so a name carrying only a
COLUMN accessor reaches no accessor through ``af.<name>``: it raises the
did-you-mean ``AttributeError``, or returns the user's own column where
the frame carries one. Naming the frame accessor for a column-kind
registration promised a destination that raises, which is why the clause
now says ``af.<column>.<name>`` for that kind.

Pinned here: the refusal for every registered name; the bracket form still
minting a column of that name and reading back; the accessor still
answering after a refused assignment; names that merely resemble an
accessor unaffected; a custom registered accessor -- frame kind and
column kind -- refusing the same way, which is the shape whose silent
shadow this closes; the last clause against every kind a name can carry,
with and without a real column of that name on the frame; and an entry
carrying neither kind, which only a direct write to the registry makes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.accessors.base import BaseColumnAccessor, BaseFrameAccessor
from gaspatchio.frame.registry import (
    _ACCESSOR_REGISTRY,
    _FRAME_DECLARED_ACCESSORS,
    register_accessor,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

# The five accessors the framework itself registers, each refused as a column name.
# Spelled out rather than read off the registry at collection time: other
# test modules register accessors of their own into the same global registry
# and do not take them out again, so a parametrisation read from it would be
# a different list depending on what else the run had imported. What the
# registry holds when a test RUNS is pinned instead, by
# ``test_every_name_in_the_registry_refuses`` below.
REGISTERED = ["date", "excel", "finance", "graph", "projection"]


def _frame() -> ActuarialFrame:
    """Two policies, one column, no accessor name among them."""
    return ActuarialFrame(pl.DataFrame({"premium": [10.0, 20.0]}))


@pytest.mark.parametrize("name", REGISTERED)
def test_assigning_to_a_registered_accessor_name_refuses(name: str) -> None:
    """The refusal names the accessor, the outcome, and the door that works."""
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    message = str(excinfo.value)
    assert f"'{name}' is a registered accessor name" in message
    assert "created no column" in message
    assert f"af['{name}'] = ..." in message
    assert af.columns == ["premium"]
    assert af.collect().columns == ["premium"]


def test_every_name_in_the_registry_refuses() -> None:
    """The predicate is the registry, whatever is in it when this runs.

    ``REGISTERED`` above is the framework's own five; this is the general
    claim, and it covers a sixth accessor the day one lands as well as the
    accessors other test modules leave behind them.
    """
    for name in sorted(_ACCESSOR_REGISTRY):
        af = _frame()

        with pytest.raises(AttributeError) as excinfo:
            setattr(af, name, pl.lit(1.0))

        assert f"'{name}' is a registered accessor name" in str(excinfo.value)
        assert name not in af.columns
        assert name not in af.__dict__


def test_the_framework_registers_the_five_the_ruling_names() -> None:
    """``REGISTERED`` is a subset of the registry, not a copy of it."""
    assert set(REGISTERED) <= set(_ACCESSOR_REGISTRY)


@pytest.mark.parametrize("name", REGISTERED)
def test_the_accessor_still_answers_after_a_refused_assignment(name: str) -> None:
    """The refusal leaves nothing behind: no shadow, and the accessor stands."""
    af = _frame()
    before = type(getattr(af, name)).__name__

    with pytest.raises(AttributeError):
        setattr(af, name, pl.lit(1.0))

    assert type(getattr(af, name)).__name__ == before
    assert name not in af.columns


@pytest.mark.parametrize("name", REGISTERED)
def test_the_bracket_form_still_mints_the_column_and_reads_back(name: str) -> None:
    """``af["date"] = ...`` is the door, and it is unchanged."""
    af = _frame()

    af[name] = pl.lit(1.5)

    assert af.columns == ["premium", name]
    assert af.collect()[name][0] == 1.5
    # The accessor keeps winning attribute access, which is why the bracket
    # form is the door in the first place.
    assert type(getattr(af, name)).__name__.endswith("Accessor")


@pytest.mark.parametrize(
    "name", ["date_of_birth", "projection_year", "graph_id", "financed", "excel_id"]
)
def test_a_name_that_merely_resembles_an_accessor_is_unaffected(name: str) -> None:
    """Only the registry decides; a look-alike is an ordinary column name."""
    af = _frame()

    setattr(af, name, pl.lit(2.5))

    assert af.columns == ["premium", name]
    assert af.collect()[name][0] == 2.5


def test_a_column_that_arrived_named_for_an_accessor_is_not_touched() -> None:
    """The refusal creates nothing and destroys nothing.

    A model whose points really do carry a ``date`` column still has it,
    reached and rewritten through the brackets.
    """
    af = ActuarialFrame(pl.DataFrame({"date": [1.0], "premium": [2.0]}))

    with pytest.raises(AttributeError):
        af.date = pl.lit(9.0)

    assert af.collect()["date"][0] == 1.0
    af["date"] = pl.lit(9.0)
    assert af.collect()["date"][0] == 9.0


@pytest.fixture
def custom_frame_accessor() -> Iterator[str]:
    """Register a frame accessor under a name of its own, then take it away."""
    name = "pinstripe"

    @register_accessor(name, kind="frame")
    class _Pinstripe(BaseFrameAccessor):
        """A frame accessor that exists only for this test."""

        def __init__(self, frame: ActuarialFrame) -> None:
            self._frame = frame

    yield name
    _ACCESSOR_REGISTRY.pop(name, None)


@pytest.fixture
def custom_column_accessor() -> Iterator[str]:
    """Register a column accessor under a name of its own, then take it away."""
    name = "pinbadge"

    @register_accessor(name, kind="column")
    class _Pinbadge(BaseColumnAccessor):
        """A column accessor that exists only for this test."""

        def __init__(self, proxy: Any) -> None:  # noqa: ANN401 -- any proxy
            self._proxy = proxy

    yield name
    _ACCESSOR_REGISTRY.pop(name, None)


@pytest.fixture
def custom_dual_accessor() -> Iterator[str]:
    """Register BOTH kinds under one name, the shape the five built-ins have.

    Four of the framework's five carry a frame accessor and a column
    accessor under the same name; ``graph`` carries only a frame one. A
    third-party registration can do the same, so the refusal has to be
    true of it.
    """
    name = "pinboth"

    @register_accessor(name, kind="frame")
    class _PinbothFrame(BaseFrameAccessor):
        """The frame half."""

        def __init__(self, frame: ActuarialFrame) -> None:
            self._frame = frame

    @register_accessor(name, kind="column")
    class _PinbothColumn(BaseColumnAccessor):
        """The column half."""

        def __init__(self, proxy: Any) -> None:  # noqa: ANN401 -- any proxy
            self._proxy = proxy

    yield name
    _ACCESSOR_REGISTRY.pop(name, None)


def test_a_custom_frame_accessor_name_refuses_rather_than_shadowing(
    custom_frame_accessor: str,
) -> None:
    """The shape the accessor guard is about: a silent shadow, now a refusal.

    At the parent this assignment succeeded, stored the expression on the
    instance, minted no column, and left ``af.pinstripe`` returning the
    stored ``pl.Expr`` where the accessor had been.
    """
    name = custom_frame_accessor
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    assert f"'{name}' is a registered accessor name" in str(excinfo.value)
    assert name not in af.__dict__
    assert af.collect().columns == ["premium"]
    assert type(getattr(af, name)).__name__ == "_Pinstripe"


def test_a_custom_column_accessor_name_refuses_too(
    custom_column_accessor: str,
) -> None:
    """The registry is the whole predicate, both kinds of accessor in it.

    A column-kind registration is enough to send a frame-level assignment
    down the same fall-through, so it is enough to earn the same refusal;
    the bracket form remains the way to write a column of that name.
    """
    name = custom_column_accessor
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    assert f"'{name}' is a registered accessor name" in str(excinfo.value)
    assert name not in af.__dict__

    other = _frame()
    other[name] = pl.lit(3.0)
    assert other.collect()[name][0] == 3.0


# ---------------------------------------------------------------------------
# The last clause: where ``af.<name>`` actually goes, for each kind.
#
# A refusal that tells an actuary where to go next has to be right about
# where that is. The clause said "af.<name> goes on reaching the accessor"
# for every registered name; it is true only where a FRAME accessor is
# registered under it.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", REGISTERED)
def test_the_refusal_names_the_frame_accessor_and_af_name_reaches_it(
    name: str,
) -> None:
    """For the framework's five, the clause is true and the read proves it."""
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    assert f"af.{name} goes on reaching the frame accessor" in str(excinfo.value)
    assert type(getattr(af, name)).__name__.endswith("FrameAccessor")


@pytest.mark.parametrize("name", REGISTERED)
def test_the_clause_holds_where_a_real_column_of_that_name_is_on_the_frame(
    name: str,
) -> None:
    """A frame accessor still wins the read, so the clause stays true."""
    af = ActuarialFrame(pl.DataFrame({name: [1.0, 2.0], "premium": [10.0, 20.0]}))

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(9.0))

    assert f"af.{name} goes on reaching the frame accessor" in str(excinfo.value)
    assert type(getattr(af, name)).__name__.endswith("FrameAccessor")
    # And the refusal fired BEFORE the existing-column branch: the column
    # is untouched rather than reassigned. That order is what the seam's
    # resolution-order note states.
    assert af.collect()[name][0] == 1.0


def test_a_custom_frame_accessor_earns_the_same_clause(
    custom_frame_accessor: str,
) -> None:
    """The predicate is the kind, not the framework's own list."""
    name = custom_frame_accessor
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    assert f"af.{name} goes on reaching the frame accessor" in str(excinfo.value)
    assert type(getattr(af, name)).__name__ == "_Pinstripe"


def test_a_name_carrying_both_kinds_is_named_for_its_frame_accessor(
    custom_dual_accessor: str,
) -> None:
    """Both kinds under one name: ``af.<name>`` is the frame accessor."""
    name = custom_dual_accessor
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    assert f"af.{name} goes on reaching the frame accessor" in str(excinfo.value)
    assert type(getattr(af, name)).__name__ == "_PinbothFrame"
    assert type(getattr(af.premium, name)).__name__ == "_PinbothColumn"


def test_a_column_kind_name_is_not_promised_an_accessor_af_name_cannot_reach(
    custom_column_accessor: str,
) -> None:
    """The clause this closes: it promised a destination that raises.

    ``register_accessor("pinbadge", kind="column")`` puts the name in the
    registry, so the assignment refuses -- but ``af.pinbadge`` reaches no
    accessor at all. It raises the did-you-mean ``AttributeError``, which
    is what the old clause sent the reader into.
    """
    name = custom_column_accessor
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    message = str(excinfo.value)
    assert f"af.{name} goes on reaching" not in message
    assert f"'{name}' is a column accessor" in message
    assert f"reached as af.<column>.{name}" in message

    with pytest.raises(AttributeError) as read_error:
        getattr(af, name)
    assert f"object has no attribute '{name}'" in str(read_error.value)


def test_the_door_a_column_kind_refusal_names_is_the_one_that_answers(
    custom_column_accessor: str,
) -> None:
    """``af.<column>.<name>`` reaches it, which is what the clause now says."""
    name = custom_column_accessor
    af = _frame()

    assert type(getattr(af.premium, name)).__name__ == "_Pinbadge"


def test_a_real_column_of_that_name_does_not_make_the_old_clause_true(
    custom_column_accessor: str,
) -> None:
    """With a column of the name, ``af.<name>`` is that column, not an accessor.

    This is the misleading half: the read succeeds, so nothing raises, and
    an actuary who followed "goes on reaching the accessor" would have
    been handed their own column's proxy instead.
    """
    name = custom_column_accessor
    af = ActuarialFrame(pl.DataFrame({name: [1.0, 2.0], "premium": [10.0, 20.0]}))

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(9.0))

    message = str(excinfo.value)
    assert f"af.{name} goes on reaching" not in message
    assert f"'{name}' is a column accessor" in message

    assert type(getattr(af, name)).__name__ == "ColumnProxy"
    assert af.collect()[name][0] == 1.0
    af[name] = pl.lit(9.0)
    assert af.collect()[name][0] == 9.0


@pytest.fixture
def kindless_registry_entry() -> Iterator[str]:
    """Put a name in the registry carrying no accessor at all, then take it out.

    ``register_accessor`` mints only ``frame`` and ``column`` entries, so
    this shape reaches the registry only by writing to it -- which a
    third-party package doing its own bookkeeping can do, and which the
    refusal below is what it meets.
    """
    name = "pinhole"
    _ACCESSOR_REGISTRY[name] = {}
    yield name
    _ACCESSOR_REGISTRY.pop(name, None)


def test_an_entry_carrying_neither_kind_is_told_it_reaches_no_accessor(
    kindless_registry_entry: str,
) -> None:
    """The clause for a name the registry holds and no accessor answers to.

    The predicate is the registry, so the assignment still refuses; there
    is no frame accessor to go on reaching and no column accessor to hang
    off a column, and the clause says the one thing left that is true.
    ``af.<name>`` really does reach nothing -- the did-you-mean
    ``AttributeError`` is what a read gets -- and the bracket form still
    writes a column of that name.
    """
    name = kindless_registry_entry
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    message = str(excinfo.value)
    assert f"af.{name} reaches no accessor." in message
    assert f"af.{name} goes on reaching" not in message
    assert f"'{name}' is a column accessor" not in message

    with pytest.raises(AttributeError) as read_error:
        getattr(af, name)
    assert f"object has no attribute '{name}'" in str(read_error.value)

    other = _frame()
    other[name] = pl.lit(4.0)
    assert other.collect()[name][0] == 4.0


# ---------------------------------------------------------------------------
# The five the frame declares as properties of its own.
#
# ``ActuarialFrame.date`` is a property that hands back the frame accessor
# and falls back to importing the built-in class, so it answers whatever
# ``_ACCESSOR_REGISTRY`` holds. The destination clause used to read the
# registry alone and go wrong about exactly that: take away only ``date``'s
# frame kind and it said the name was reachable only as
# ``af.<column>.date`` while ``af.date`` still returned
# ``DateFrameAccessor``; empty the entry and it said the name reached no
# accessor while all five still answered. These names are declared OUTSIDE
# the registry, and the clause says so.
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_restored() -> Iterator[None]:
    """Give the entries for the five back exactly as they were found."""
    saved = {name: dict(_ACCESSOR_REGISTRY[name]) for name in _FRAME_DECLARED_ACCESSORS}
    yield
    for name, kinds in saved.items():
        _ACCESSOR_REGISTRY[name] = kinds


def test_a_declared_accessor_keeps_its_clause_when_its_frame_kind_is_taken_away(
    registry_restored: None,
) -> None:
    """Only ``date``'s frame kind removed: the property still answers."""
    _ = registry_restored
    _ACCESSOR_REGISTRY["date"].pop("frame", None)
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        af.date = pl.lit(1.0)

    message = str(excinfo.value)
    assert "af.date goes on reaching the frame accessor" in message
    assert "'date' is a column accessor" not in message
    assert type(af.date).__name__ == "DateFrameAccessor"


@pytest.mark.parametrize("name", sorted(_FRAME_DECLARED_ACCESSORS))
def test_a_declared_accessor_keeps_its_clause_with_an_empty_registry_entry(
    name: str,
    registry_restored: None,
) -> None:
    """Every entry emptied: all five still resolve, and the clause says so."""
    _ = registry_restored
    for declared in _FRAME_DECLARED_ACCESSORS:
        _ACCESSOR_REGISTRY[declared] = {}
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    message = str(excinfo.value)
    assert f"af.{name} goes on reaching the frame accessor" in message
    assert f"af.{name} reaches no accessor" not in message
    assert type(getattr(af, name)).__name__.endswith("FrameAccessor")


# ---------------------------------------------------------------------------
# A registry entry under a name the frame carries, or under one of its own
# internals. ``register_accessor`` refuses a frame accessor under a name
# ``ActuarialFrame`` already carries, so both shapes below are reachable
# only by writing to the registry directly.
# ---------------------------------------------------------------------------


class _Overtaken(BaseFrameAccessor):
    """A frame accessor no spelling can reach."""

    def __init__(self, frame: ActuarialFrame) -> None:
        self._frame = frame


@pytest.fixture
def entry_under_a_frame_method() -> Iterator[str]:
    """Put a frame accessor under ``collect`` by hand, then take it out."""
    name = "collect"
    _ACCESSOR_REGISTRY[name] = {"frame": _Overtaken}
    yield name
    _ACCESSOR_REGISTRY.pop(name, None)


def test_an_entry_under_a_name_the_frame_carries_is_told_what_the_read_reaches(
    entry_under_a_frame_method: str,
) -> None:
    """The clause this closes: it promised an accessor the method hides.

    ``af.collect`` is the frame's own method -- the class attribute is
    found before ``__getattr__`` runs -- so the accessor in the registry
    answers to nothing, and the clause says what the read really is.
    """
    name = entry_under_a_frame_method
    af = _frame()

    with pytest.raises(AttributeError) as excinfo:
        setattr(af, name, pl.lit(1.0))

    message = str(excinfo.value)
    assert f"'{name}' is a registered accessor name" in message
    assert f"af.{name} goes on reaching" not in message
    assert f"af.{name} is the frame's own {name}() method." in message
    assert callable(getattr(af, name))


@pytest.mark.parametrize("name", ["_df", "_column_order", "_attr_columns_set"])
def test_an_entry_under_a_frame_internal_does_not_stop_a_frame_being_built(
    name: str,
) -> None:
    """The refusal used to fire inside ``__init__`` and block construction.

    ``_ACCESSOR_REGISTRY["_df"] = {}`` made ``self._df = ...`` meet the
    accessor-name refusal, so no ``ActuarialFrame`` could be built at all.
    Underscore names are never column names, which is why the two branches
    below this one already excluded them; this one does too.
    """
    _ACCESSOR_REGISTRY[name] = {}
    try:
        af = ActuarialFrame(pl.DataFrame({"premium": [10.0, 20.0]}))
        assert af.columns == ["premium"]
        assert af.collect()["premium"][0] == 10.0
    finally:
        _ACCESSOR_REGISTRY.pop(name, None)


def test_an_underscore_entry_still_refuses_and_says_the_underscore_sentence() -> None:
    """Exempting internals is not the same as letting the write through.

    An underscore name the frame does not own is still refused -- by the
    underscore branch, which is the one that has always answered for names
    of that shape.
    """
    name = "_pinhole"
    _ACCESSOR_REGISTRY[name] = {}
    try:
        af = _frame()
        with pytest.raises(AttributeError) as excinfo:
            setattr(af, name, pl.lit(1.0))
        message = str(excinfo.value)
        assert f"'{name}' is not a valid attribute name" in message
        assert f"af['{name}'] = ..." in message
        assert name not in af.columns
        assert af.collect().columns == ["premium"]
    finally:
        _ACCESSOR_REGISTRY.pop(name, None)
