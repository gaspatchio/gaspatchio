# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for what ``capture_validation_context`` does to the error it catches.

The decorator's job is to turn a plain ``ValueError`` from a validation
helper into a ``ValidationError`` carrying the caller's line -- the line in
the model that passed the bad value, not the line in the framework that
found it. That conversion sat inside a ``try`` whose own ``except`` caught
the enhanced raise and re-raised the original, so it never once reached a
caller; only the branch that mutates an already-typed ``ValidationError``
survived, because mutation happens before the swallowed raise.

These tests drive the conversion end to end: each of the three error types
the decorator catches, the mode that switches enhancement off, a caller
with no readable source file (a notebook cell, an ``exec``-compiled
snippet), and the already-typed error that only needs a location.

The ``TypeError`` and ``KeyError`` cases carry the edge worth stating
plainly: ``ValidationError`` subclasses ``ValueError`` alone, so what the
conversion hands back is narrower than what went in, and a caller who
catches either of those types by name no longer catches it.

Enhancement is gated on the error mode, read from ``AF_ERROR_MODE`` --
``enhanced`` and ``debug`` enhance, ``basic`` and ``off`` do not -- so each
test sets it explicitly rather than inheriting whatever the session left
behind.
"""

from __future__ import annotations

import pytest

from gaspatchio.errors import ValidationError, capture_validation_context


@capture_validation_context
def _rejects(value: int) -> int:
    if value < 0:
        msg = f"Invalid value: {value}"
        raise ValueError(msg)
    return value


@capture_validation_context
def _rejects_the_type(value: object) -> None:
    msg = f"Invalid type: {type(value).__name__}"
    raise TypeError(msg)


@capture_validation_context
def _looks_up(rates: dict[str, float], key: str) -> float:
    return rates[key]


def test_enhanced_mode_converts_a_plain_error_and_points_at_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")
    with pytest.raises(ValidationError) as excinfo:
        _rejects(-1)  # this line is the location the error must carry
    err = excinfo.value
    assert isinstance(err.__cause__, ValueError)
    assert err.source_location is not None
    assert err.source_location.file_path.endswith("test_validation_context.py")
    assert (
        err.source_location.function_name
        == "test_enhanced_mode_converts_a_plain_error_and_points_at_the_caller"
    )
    assert "_rejects(-1)" in (err.source_location.source_line or "")
    assert err.context.provided_value == "-1"


def test_enhanced_mode_converts_a_type_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``TypeError`` is converted too, and the conversion narrows the catch.

    ``ValidationError`` subclasses ``ValueError`` alone, so a caller who
    wrote ``except TypeError`` around the call no longer catches what comes
    out -- which is the reason this conversion is pinned rather than left
    to the ``ValueError`` case to imply.
    """
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")
    with pytest.raises(ValidationError) as excinfo:
        _rejects_the_type(object())
    err = excinfo.value
    assert isinstance(err.__cause__, TypeError)
    assert not isinstance(err, TypeError)
    assert err.source_location is not None
    assert (
        err.source_location.function_name == "test_enhanced_mode_converts_a_type_error"
    )


def test_enhanced_mode_converts_a_key_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing lookup key is converted on the same terms.

    ``KeyError`` is what a rate lookup against a table raises, and the same
    narrowing applies: ``except KeyError`` no longer catches it.
    """
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")
    with pytest.raises(ValidationError) as excinfo:
        _looks_up({"male": 0.001}, "female")
    err = excinfo.value
    assert isinstance(err.__cause__, KeyError)
    assert not isinstance(err, KeyError)
    assert err.source_location is not None
    assert (
        err.source_location.function_name == "test_enhanced_mode_converts_a_key_error"
    )


def test_off_mode_leaves_the_original_error_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AF_ERROR_MODE", "off")
    with pytest.raises(ValueError, match="Invalid value: -1") as excinfo:
        _rejects(-1)
    # ValidationError is a ValueError, so the type has to be checked directly.
    assert not isinstance(excinfo.value, ValidationError)


def test_a_caller_with_no_source_file_is_still_enhanced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")
    namespace: dict[str, object] = {"_rejects": _rejects}
    code = compile("_rejects(-1)\n", "<snippet>", "exec")
    with pytest.raises(ValidationError) as excinfo:
        exec(code, namespace)  # noqa: S102 -- the point is a frame with no file
    assert excinfo.value.source_location is not None
    assert excinfo.value.source_location.source_line is None


def test_an_existing_validation_error_gains_a_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An already-typed error is located, not rewritten.

    It keeps its identity -- the same object, carrying the same message,
    with no cause chained under it -- because there is nothing to convert:
    it is already the type the caller will catch. All it lacked was the
    line that passed the value.
    """
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")
    original = ValidationError("already typed")

    @capture_validation_context
    def _raises_validation_error() -> None:
        raise original

    with pytest.raises(ValidationError) as excinfo:
        _raises_validation_error()
    assert excinfo.value is original
    assert excinfo.value.args[0] == "already typed"
    assert excinfo.value.__cause__ is None
    assert excinfo.value.source_location is not None
