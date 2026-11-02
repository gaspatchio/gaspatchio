# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``capture_validation_context``'s source-location enrichment.

The decorator walks the call stack to find whoever called the decorated
function, then stamps that frame's location onto the raised
``ValidationError``. When that caller sits at module scope, the interpreter
names its frame ``"<module>"`` -- a machine label for "no enclosing scope",
not a function a reader could open and look at. This suite pins that the
label is normalized to ``None`` before it reaches ``SourceLocation``, the
same contract ``frame_utils.get_source_location()`` already applies on its
own capture path, and that the rendered message says nothing about scope
when it is unknown rather than reporting the label as if it were one.

The scenarios below run as real top-level script execution (``runpy`` against
a script written to ``tmp_path``) rather than a plain function call: a pytest
test body is itself a function, so calling the decorated helper directly from
a test would only ever produce the test's own name, never the interpreter's
module-level sentinel. Running a real script is the only way to reach a
frame that is genuinely at module scope.
"""

from __future__ import annotations

import runpy
from typing import TYPE_CHECKING

import pytest

from gaspatchio.errors.formatter import ValidationErrorFormatter
from gaspatchio.errors.validation import ValidationError

if TYPE_CHECKING:
    from pathlib import Path

_HELPER_SOURCE = """\
from types import SimpleNamespace
from gaspatchio.errors.validation import ValidationError, capture_validation_context


@capture_validation_context
def _check(frame):
    raise ValidationError("invalid option: nope")


"""


def _run_fixture(tmp_path: Path, call_site: str) -> ValidationError:
    """Execute a tiny script at true module scope and return its captured error.

    ``call_site`` is appended verbatim after the decorated helper, so the
    caller controls whether ``_check`` is invoked directly at module level
    or from inside a nested function.
    """
    script = tmp_path / "fixture.py"
    script.write_text(_HELPER_SOURCE + call_site)

    with pytest.raises(ValidationError) as exc_info:
        runpy.run_path(str(script), run_name="fixture")
    return exc_info.value


def test_module_level_call_reports_no_function_name(tmp_path: Path):
    """A validation error raised at true module scope has no enclosing scope."""
    error = _run_fixture(tmp_path, '_check(SimpleNamespace(_mode="debug"))\n')

    assert error.source_location is not None
    assert error.source_location.function_name is None


def test_in_function_call_reports_the_real_function_name(tmp_path: Path):
    """The same error, raised inside a function, names that function."""
    error = _run_fixture(
        tmp_path,
        "def run_validation():\n"
        '    _check(SimpleNamespace(_mode="debug"))\n'
        "\n\n"
        "run_validation()\n",
    )

    assert error.source_location is not None
    assert error.source_location.function_name == "run_validation"


def test_module_level_error_renders_with_no_function_line(tmp_path: Path):
    """End to end: the rendered message says nothing about scope, not a guess."""
    error = _run_fixture(tmp_path, '_check(SimpleNamespace(_mode="debug"))\n')

    message = ValidationErrorFormatter(error).format_error()

    assert "Function:" not in message
    assert "<module>" not in message
    assert "module level" not in message


def test_in_function_error_renders_the_function_line(tmp_path: Path):
    """End to end: a scope that is genuinely known is reported, not withheld."""
    error = _run_fixture(
        tmp_path,
        "def run_validation():\n"
        '    _check(SimpleNamespace(_mode="debug"))\n'
        "\n\n"
        "run_validation()\n",
    )

    message = ValidationErrorFormatter(error).format_error()

    assert "Function: run_validation" in message
