# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the accessor registry."""

import copy

import pytest

from gaspatchio.accessors.base import BaseColumnAccessor, BaseFrameAccessor

# Import the items to test
from gaspatchio.frame.registry import (
    _ACCESSOR_REGISTRY,
    _FRAME_DECLARED_ACCESSORS,
    list_registered_accessors,
    register_accessor,
)

# Save the real registry state once at import time
_ORIGINAL_REGISTRY = copy.deepcopy(_ACCESSOR_REGISTRY)


# --- Test Setup ---
def setup_function(function):
    """Reset the registry to a clean state before each test."""
    _ACCESSOR_REGISTRY.clear()


def teardown_function(function):
    """Restore the original registry after each test."""
    _ACCESSOR_REGISTRY.clear()
    _ACCESSOR_REGISTRY.update(copy.deepcopy(_ORIGINAL_REGISTRY))


# --- Base Dummy Accessor Classes ---
# These inherit from the real base classes so they pass the new validation.


class DummyFrameAccessor(BaseFrameAccessor):
    def __init__(self, parent):
        self._frame = parent


class DummyColumnAccessor(BaseColumnAccessor):
    def __init__(self, parent):
        self._proxy = parent


# --- Test Cases: original registration behaviour ---


def test_register_frame_accessor():
    """Test registering a frame accessor."""

    @register_accessor("dummy_frame", kind="frame")
    class TestFrameAcc(DummyFrameAccessor):
        pass

    assert "dummy_frame" in _ACCESSOR_REGISTRY
    # Access nested dict
    assert "frame" in _ACCESSOR_REGISTRY["dummy_frame"]
    assert _ACCESSOR_REGISTRY["dummy_frame"]["frame"] is TestFrameAcc


def test_register_column_accessor():
    """Test registering a column accessor (default kind)."""

    @register_accessor("dummy_col")
    class TestColAcc(DummyColumnAccessor):
        pass

    assert "dummy_col" in _ACCESSOR_REGISTRY
    # Access nested dict
    assert "column" in _ACCESSOR_REGISTRY["dummy_col"]
    assert _ACCESSOR_REGISTRY["dummy_col"]["column"] is TestColAcc


def test_register_column_accessor_explicit():
    """Test registering a column accessor explicitly."""

    @register_accessor("dummy_col_explicit", kind="column")
    class TestColAccExplicit(DummyColumnAccessor):
        pass

    assert "dummy_col_explicit" in _ACCESSOR_REGISTRY
    # Access nested dict
    assert "column" in _ACCESSOR_REGISTRY["dummy_col_explicit"]
    assert _ACCESSOR_REGISTRY["dummy_col_explicit"]["column"] is TestColAccExplicit


def test_register_invalid_kind():
    """Test that registering with an invalid kind raises ValueError."""
    with pytest.raises(ValueError, match="Accessor kind must be 'frame' or 'column'"):

        @register_accessor("invalid_kind_acc", kind="invalid")
        class InvalidKindAcc:
            pass

    assert "invalid_kind_acc" not in _ACCESSOR_REGISTRY


# --- Task 1: Idempotent Same-Class Registration ---


def test_register_same_class_is_idempotent():
    """Re-registering the exact same class object with same name+kind succeeds silently."""

    class MyFrameAcc(DummyFrameAccessor):
        pass

    # Register the first time.
    register_accessor("idempotent_frame", kind="frame")(MyFrameAcc)
    # Register the same class object a second time — must not raise.
    register_accessor("idempotent_frame", kind="frame")(MyFrameAcc)

    assert _ACCESSOR_REGISTRY["idempotent_frame"]["frame"] is MyFrameAcc


def test_register_different_class_same_name_raises():
    """Registering a different class with the same name+kind raises ValueError naming both."""

    @register_accessor("conflict_col", kind="column")
    class FirstAcc(DummyColumnAccessor):
        pass

    with pytest.raises(ValueError) as exc_info:

        @register_accessor("conflict_col", kind="column")
        class SecondAcc(DummyColumnAccessor):
            pass

    message = str(exc_info.value)
    assert "FirstAcc" in message
    assert "SecondAcc" in message
    # Original class is preserved
    assert _ACCESSOR_REGISTRY["conflict_col"]["column"] is FirstAcc


def test_register_duplicate_name():
    """Test that registering a duplicate name and kind raises ValueError."""

    @register_accessor("duplicate_name", kind="frame")
    class FirstAcc(DummyFrameAccessor):
        pass

    # Attempt to register a DIFFERENT class with the SAME name+kind
    with pytest.raises(ValueError) as exc_info:

        @register_accessor("duplicate_name", kind="frame")
        class SecondAcc(DummyFrameAccessor):
            pass

    message = str(exc_info.value)
    assert "FirstAcc" in message
    assert "SecondAcc" in message

    # Ensure only the first one is actually registered and kind is correct
    assert len(_ACCESSOR_REGISTRY) == 1
    assert "duplicate_name" in _ACCESSOR_REGISTRY
    assert len(_ACCESSOR_REGISTRY["duplicate_name"]) == 1
    assert "frame" in _ACCESSOR_REGISTRY["duplicate_name"]
    assert _ACCESSOR_REGISTRY["duplicate_name"]["frame"] is FirstAcc


# --- Task 2: Registration Validation ---


def test_register_frame_accessor_without_base_raises():
    """Registering kind='frame' without BaseFrameAccessor raises TypeError."""

    class NotAFrameAccessor:
        def __init__(self, parent):
            pass

    with pytest.raises(TypeError) as exc_info:
        register_accessor("bad_frame", kind="frame")(NotAFrameAccessor)

    message = str(exc_info.value)
    assert "BaseFrameAccessor" in message
    assert "NotAFrameAccessor" in message


def test_register_column_accessor_without_base_raises():
    """Registering kind='column' without BaseColumnAccessor raises TypeError."""

    class NotAColumnAccessor:
        def __init__(self, parent):
            pass

    with pytest.raises(TypeError) as exc_info:
        register_accessor("bad_column", kind="column")(NotAColumnAccessor)

    message = str(exc_info.value)
    assert "BaseColumnAccessor" in message
    assert "NotAColumnAccessor" in message


def test_register_valid_frame_accessor_subclass():
    """A class that inherits BaseFrameAccessor registers successfully."""

    @register_accessor("valid_frame", kind="frame")
    class ValidFrameAcc(BaseFrameAccessor):
        def __init__(self, frame):
            super().__init__(frame)

    assert _ACCESSOR_REGISTRY["valid_frame"]["frame"] is ValidFrameAcc


def test_register_valid_column_accessor_subclass():
    """A class that inherits BaseColumnAccessor registers successfully."""

    @register_accessor("valid_column", kind="column")
    class ValidColumnAcc(BaseColumnAccessor):
        def __init__(self, proxy):
            super().__init__(proxy)

    assert _ACCESSOR_REGISTRY["valid_column"]["column"] is ValidColumnAcc


# --- Task 3: list_registered_accessors() ---


def test_list_registered_accessors_returns_copy():
    """list_registered_accessors returns a shallow copy, not the real dict."""

    @register_accessor("listed_frame", kind="frame")
    class ListedFrameAcc(BaseFrameAccessor):
        def __init__(self, frame):
            super().__init__(frame)

    result = list_registered_accessors()
    assert "listed_frame" in result
    assert result["listed_frame"]["frame"] is ListedFrameAcc

    # Mutations to the returned dict must not affect the real registry.
    result["listed_frame"]["frame"] = None
    assert _ACCESSOR_REGISTRY["listed_frame"]["frame"] is ListedFrameAcc


def test_list_registered_accessors_empty():
    """list_registered_accessors returns an empty dict when registry is empty."""
    result = list_registered_accessors()
    assert result == {}


def test_list_registered_accessors_multiple_entries():
    """list_registered_accessors reflects all currently registered accessors."""

    @register_accessor("multi_frame", kind="frame")
    class MultiFrameAcc(BaseFrameAccessor):
        def __init__(self, frame):
            super().__init__(frame)

    @register_accessor("multi_col", kind="column")
    class MultiColAcc(BaseColumnAccessor):
        def __init__(self, proxy):
            super().__init__(proxy)

    result = list_registered_accessors()
    assert "multi_frame" in result
    assert "multi_col" in result
    assert result["multi_frame"]["frame"] is MultiFrameAcc
    assert result["multi_col"]["column"] is MultiColAcc


# --- The name is judged where it is written, not quoted back later ---
#
# Two shapes reached the registry and were only complained about much
# later, in ActuarialFrame's assignment refusal, in a sentence that was
# wrong about them:
#
#   * a FRAME accessor under a name ActuarialFrame already carries. The
#     class attribute wins attribute access, so `af.collect` is the
#     method and the accessor is unreachable by any spelling -- while the
#     refusal said "af.collect goes on reaching the frame accessor".
#   * a name that is not a Python identifier, or is a keyword. The
#     refusal printed `af.not an identifier = ...` and `af.class = ...`
#     back as spellings to avoid, neither of which anyone can write.
#
# Both are refused at the point the name is chosen now.

_FRAME_METHOD_NAMES = ["collect", "filter", "max", "sum", "with_columns"]
_FRAME_PROPERTY_NAMES = ["columns", "dtypes", "schema"]
_NOT_IDENTIFIERS = ["not an identifier", "3bad", "", "has-a-hyphen", "dotted.name"]
_PYTHON_KEYWORDS = ["class", "def", "return", "None"]


@pytest.mark.parametrize("name", _FRAME_METHOD_NAMES)
def test_a_frame_accessor_under_a_method_the_frame_carries_is_refused(name: str):
    """The class attribute would win, so the accessor could never answer."""
    with pytest.raises(ValueError, match="would never reach the accessor") as exc_info:

        @register_accessor(name, kind="frame")
        class Shadowing(BaseFrameAccessor):
            def __init__(self, frame) -> None:
                super().__init__(frame)

    message = str(exc_info.value)
    assert "Shadowing" in message
    assert f"af.{name} would never reach the accessor" in message
    assert f"af.{name} is the frame's own {name}() method." in message
    assert name not in _ACCESSOR_REGISTRY


@pytest.mark.parametrize("name", _FRAME_PROPERTY_NAMES)
def test_a_frame_accessor_under_a_property_the_frame_carries_is_refused(name: str):
    """The last clause says which of the two the class attribute is."""
    with pytest.raises(ValueError, match="would never reach the accessor") as exc_info:

        @register_accessor(name, kind="frame")
        class Shadowing(BaseFrameAccessor):
            def __init__(self, frame) -> None:
                super().__init__(frame)

    message = str(exc_info.value)
    assert f"af.{name} is the frame's own {name} property." in message
    assert name not in _ACCESSOR_REGISTRY


def test_every_public_name_the_frame_carries_is_refused_except_its_own_five():
    """The predicate is the class, so a method added later is covered too."""
    from gaspatchio import ActuarialFrame

    refused: list[str] = []
    accepted: list[str] = []
    for name in sorted(n for n in dir(ActuarialFrame) if not n.startswith("_")):
        try:

            @register_accessor(name, kind="frame")
            class Shadowing(BaseFrameAccessor):
                def __init__(self, frame) -> None:
                    super().__init__(frame)

        except ValueError:
            refused.append(name)
        else:
            accepted.append(name)
        _ACCESSOR_REGISTRY.pop(name, None)

    assert accepted == sorted(_FRAME_DECLARED_ACCESSORS)
    assert len(refused) == 28
    assert "collect" in refused


@pytest.mark.parametrize("name", sorted(_FRAME_DECLARED_ACCESSORS))
def test_the_five_the_frame_declares_as_accessor_properties_are_accepted(name: str):
    """Their class attribute IS the accessor, so they shadow nothing.

    This is how the framework's own five arrive in the registry; refusing
    them would refuse the package's own import.
    """

    @register_accessor(name, kind="frame")
    class Declared(BaseFrameAccessor):
        def __init__(self, frame) -> None:
            super().__init__(frame)

    assert _ACCESSOR_REGISTRY[name]["frame"] is Declared


def test_the_declared_set_is_exactly_the_properties_handing_back_an_accessor():
    """``_FRAME_DECLARED_ACCESSORS`` is a claim about the class; check it.

    The exemption is spelled out rather than derived, so this pins the
    spelling against the class it describes: every name in the set is a
    property on ``ActuarialFrame`` whose value is a frame accessor, and
    no other public property is.
    """
    import polars as pl

    from gaspatchio import ActuarialFrame

    # Restore the real registry: the declared properties read it first.
    _ACCESSOR_REGISTRY.update(copy.deepcopy(_ORIGINAL_REGISTRY))
    af = ActuarialFrame(pl.DataFrame({"premium": [1.0]}))

    handing_back_an_accessor = {
        name
        for name in dir(ActuarialFrame)
        if not name.startswith("_")
        and isinstance(getattr(ActuarialFrame, name, None), property)
        and isinstance(getattr(af, name), BaseFrameAccessor)
    }
    assert handing_back_an_accessor == set(_FRAME_DECLARED_ACCESSORS)


def test_a_column_accessor_under_a_name_the_frame_carries_is_accepted():
    """The refusal is about the FRAME's names, and a column proxy is not it.

    ``af.<column>.collect`` is a door the frame's own ``collect()`` does
    not stand in, so a column accessor under that name is reachable and
    is left alone.
    """

    @register_accessor("collect", kind="column")
    class OnTheColumn(BaseColumnAccessor):
        def __init__(self, proxy) -> None:
            super().__init__(proxy)

    assert _ACCESSOR_REGISTRY["collect"]["column"] is OnTheColumn


@pytest.mark.parametrize("name", _NOT_IDENTIFIERS)
def test_a_name_that_is_not_an_identifier_is_refused(name: str):
    """An accessor is reached after a dot; this name has no such spelling."""
    with pytest.raises(ValueError, match="not a Python identifier") as exc_info:

        @register_accessor(name, kind="frame")
        class Unwritable(BaseFrameAccessor):
            def __init__(self, frame) -> None:
                super().__init__(frame)

    message = str(exc_info.value)
    assert "not a Python identifier" in message
    assert "str.isidentifier()" in message
    # And it does not quote the spelling nobody can write back at them,
    # which is what the assignment refusal used to do.
    assert f"af.{name} = ..." not in message
    assert name not in _ACCESSOR_REGISTRY


@pytest.mark.parametrize("name", _PYTHON_KEYWORDS)
def test_a_python_keyword_is_refused(name: str):
    """``af.class`` is a SyntaxError, so the name never had a door."""
    with pytest.raises(ValueError, match="is a Python keyword") as exc_info:

        @register_accessor(name, kind="frame")
        class Unwritable(BaseFrameAccessor):
            def __init__(self, frame) -> None:
                super().__init__(frame)

    message = str(exc_info.value)
    assert "is a Python keyword" in message
    assert f"af.{name} = ..." not in message
    assert name not in _ACCESSOR_REGISTRY


def test_the_name_is_checked_before_the_decorator_runs():
    """Like the *kind* check beside it: the factory call is where it lands."""
    with pytest.raises(ValueError, match="not a Python identifier"):
        register_accessor("not an identifier", kind="frame")
    with pytest.raises(ValueError, match="is a Python keyword"):
        register_accessor("class", kind="column")

    assert "not an identifier" not in _ACCESSOR_REGISTRY
    assert "class" not in _ACCESSOR_REGISTRY


# --- Tests that require the real (uncleared) registry state ---


class TestBuiltinAccessors:
    """Tests that rely on built-in accessors being imported and registered."""

    def test_contains_builtin_accessors(self):
        """Should include built-in accessors like finance and projection."""
        result = list_registered_accessors()
        assert "finance" in result
        assert "projection" in result
        assert "column" in result["finance"]
        assert "frame" in result["finance"]


# --- An accessor needs no constructor of its own ---
#
# Both bases implement the constructor every accessor shares: it binds the
# frame, or the column, the accessor was reached from. They also marked it
# abstract, so an accessor that only adds methods could not be built, and
# the constructor that calls ``super().__init__()`` and nothing else was the
# only way through it.


def test_a_column_accessor_without_a_constructor_of_its_own_runs():
    """The base binds the column; the accessor only adds what it computes."""
    import polars as pl

    from gaspatchio import ActuarialFrame

    _ACCESSOR_REGISTRY.update(copy.deepcopy(_ORIGINAL_REGISTRY))

    @register_accessor("risk", kind="column")
    class RiskAccessor(BaseColumnAccessor):
        def double(self):
            return self._proxy * 2

    af = ActuarialFrame(pl.DataFrame({"x": [1.0, 2.0]}))
    af.y = af.x.risk.double()

    assert af.collect()["y"].to_list() == [2.0, 4.0]


def test_a_frame_accessor_without_a_constructor_of_its_own_runs():
    """The base binds the frame; the accessor only adds what it computes."""
    import polars as pl

    from gaspatchio import ActuarialFrame

    _ACCESSOR_REGISTRY.update(copy.deepcopy(_ORIGINAL_REGISTRY))

    @register_accessor("reporting", kind="frame")
    class ReportingAccessor(BaseFrameAccessor):
        def add_net_cashflow(self):
            af = self._frame
            af.net_cf = af.premiums - af.claims
            return af

    af = ActuarialFrame(pl.DataFrame({"premiums": [10.0], "claims": [4.0]}))
    af.reporting.add_net_cashflow()

    assert af.collect()["net_cf"].to_list() == [6.0]


def test_an_accessor_that_keeps_its_own_constructor_still_runs():
    """The constructor the extending guide writes keeps working unchanged."""
    import polars as pl

    from gaspatchio import ActuarialFrame

    _ACCESSOR_REGISTRY.update(copy.deepcopy(_ORIGINAL_REGISTRY))

    @register_accessor("risk", kind="column")
    class RiskAccessor(BaseColumnAccessor):
        def __init__(self, proxy) -> None:
            super().__init__(proxy)

        def double(self):
            return self._proxy * 2

    af = ActuarialFrame(pl.DataFrame({"x": [1.0, 2.0]}))
    af.y = af.x.risk.double()

    assert af.collect()["y"].to_list() == [2.0, 4.0]


# --- An accessor that cannot be built says why ---
#
# A column accessor is built the first time it is reached. Its constructor's
# own error used to come back as an AttributeError, which hasattr() and
# getattr(..., default) read as "no such accessor": a bug in the accessor
# looked like a missing name.


@pytest.mark.parametrize("reach", ["column", "expression"])
def test_a_constructor_that_raises_lets_its_own_error_through(reach: str):
    """The constructor's error arrives as raised, with a note naming the accessor."""
    import polars as pl

    from gaspatchio import ActuarialFrame

    _ACCESSOR_REGISTRY.update(copy.deepcopy(_ORIGINAL_REGISTRY))

    @register_accessor("broken", kind="column")
    class BrokenAccessor(BaseColumnAccessor):
        def __init__(self, _proxy) -> None:
            msg = "this accessor cannot be built"
            raise ValueError(msg)

    af = ActuarialFrame(pl.DataFrame({"x": [1.0, 2.0]}))
    proxy = af.x if reach == "column" else af.x * 2

    with pytest.raises(ValueError, match="cannot be built") as caught:
        _ = proxy.broken
    assert any("'broken'" in note for note in caught.value.__notes__)

    # And hasattr() no longer reads the bug as a missing accessor.
    with pytest.raises(ValueError, match="cannot be built"):
        hasattr(proxy, "broken")


def test_an_attribute_error_in_a_constructor_is_not_read_as_a_missing_accessor():
    """hasattr() swallows the constructor's AttributeError, but not a TypeError."""
    import polars as pl

    from gaspatchio import ActuarialFrame

    _ACCESSOR_REGISTRY.update(copy.deepcopy(_ORIGINAL_REGISTRY))

    @register_accessor("misspelt", kind="column")
    class MisspeltAccessor(BaseColumnAccessor):
        def __init__(self, proxy) -> None:
            super().__init__(proxy)
            self.scale = self._proxy.nme  # a typo for a column

    af = ActuarialFrame(pl.DataFrame({"x": [1.0, 2.0]}))

    with pytest.raises(TypeError, match="'misspelt'") as caught:
        _ = af.x.misspelt
    assert isinstance(caught.value.__cause__, AttributeError)
    with pytest.raises(TypeError, match="'misspelt'"):
        hasattr(af.x, "misspelt")
