# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""User-vs-framework frame classification must anchor to the installed package.

A bare ``/gaspatchio/`` substring also matches user model files that merely
live under a directory called gaspatchio — the documented multi-repo
workspace layout — which silently drops the user's source line from error
messages and expression lineage. These tests pin the anchoring.

A file's name and the names of the directories above it decide nothing
either. The framework has modules called ``validation.py`` and
``runner.py``; a model kept in a file of the same name is still the
user's, and so is a model under pytest's own temporary directory or a
directory called ``env``. Each is located by the path its frame recorded.

Both walks that look for the model author's line ask one question,
``is_framework_or_interpreter_file``: the error locators, and the capture of
each calculation's source line. The interpreter's own code -- its standard
library, ``unittest`` and ``asyncio`` included, its installed packages and
its frozen modules -- is passed over like the framework's, and paths are
compared on the platform's own rules, so the answer holds on Windows too.
"""

from __future__ import annotations

import asyncio
import importlib.util
import linecache
import ntpath
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

import gaspatchio
import gaspatchio.errors.validation
import gaspatchio.frame.base
from gaspatchio.errors import ValidationError, raise_validation_error
from gaspatchio.errors.frame_utils import is_user_code_frame

if TYPE_CHECKING:
    from types import ModuleType

# The documented workspace shape: the framework repo and the user's models
# both live under a parent directory named gaspatchio.
USER_MODEL_PATHS = [
    "/Users/x/projects/gaspatchio/gaspatchio-models/models/term/model.py",
    "/home/x/gaspatchio/errors/model.py",
    "/work/gaspatchio/frame/my_model.py",
]

# A model file may be called anything, including the name of one of the
# framework's own modules.
NAMED_LIKE_THE_FRAMEWORK = [
    f"/Users/x/models/term/{name}"
    for name in (
        "validation.py",
        "runner.py",
        "execution.py",
        "formatter.py",
        "formatting_errors.py",
        "tracing.py",
        "metadata.py",
        "boundary.py",
    )
]

# And it may sit under a directory whose name reads like a tool's.
UNDER_DIRECTORIES_NAMED_LIKE_TOOLING = [
    "/home/x/env/term/model.py",
    "/work/acme/_internal/pricing.py",
    "/work/acme/tests/unittests/test_term.py",
    "/private/var/folders/ab/T/pytest-of-x/pytest-7/test_term0/model.py",
]


class TestIsUserCodeFrame:
    """The error-message classifier."""

    def test_user_models_under_gaspatchio_named_dirs_are_user_code(self):
        """A directory named gaspatchio does not make a file framework code."""
        for path in USER_MODEL_PATHS:
            assert is_user_code_frame(path), path

    def test_framework_modules_are_internal(self):
        """The framework's own files must still classify as internal."""
        assert not is_user_code_frame(gaspatchio.frame.base.__file__)
        assert not is_user_code_frame(gaspatchio.errors.validation.__file__)

    @pytest.mark.parametrize("path", NAMED_LIKE_THE_FRAMEWORK)
    def test_a_file_named_like_a_framework_module_is_user_code(self, path):
        """The name is not the path: the framework's own copy lives elsewhere."""
        assert is_user_code_frame(path)

    @pytest.mark.parametrize("path", UNDER_DIRECTORIES_NAMED_LIKE_TOOLING)
    def test_a_directory_name_does_not_make_a_file_framework_code(self, path):
        """Only the package and installed packages are not the user's."""
        assert is_user_code_frame(path)

    def test_installed_and_frozen_code_is_not_user_code(self):
        """Third-party code and the interpreter's frozen modules are not the user's."""
        assert not is_user_code_frame(pl.__file__)
        assert not is_user_code_frame("<frozen importlib._bootstrap>")


class TestOneRuleForBothWalks:
    """The error locators and the lineage capture ask one question."""

    def test_the_lineage_capture_asks_the_same_question(self):
        """A frame the capture walks past is exactly one the locators pass over."""
        from gaspatchio.frame import calculations

        here = sys._getframe()  # noqa: SLF001 -- the frame of this test
        assert not calculations._is_internal_frame(here)  # noqa: SLF001
        assert is_user_code_frame(here.f_code.co_filename)

    def test_the_framework_and_the_interpreter_are_passed_over(self):
        """Framework, standard library, installed packages, frozen modules."""
        from gaspatchio._source import is_framework_or_interpreter_file

        for filename in (
            gaspatchio.frame.base.__file__,
            unittest.case.__file__,
            asyncio.events.__file__,
            pl.__file__,
            "<frozen importlib._bootstrap>",
            "<frozen importlib._bootstrap_external>",
            "<frozen runpy>",
            "/opt/elsewhere/lib/python3.13/site-packages/vendored/model.py",
            "/opt/elsewhere/lib/python3/dist-packages/vendored/model.py",
        ):
            assert is_framework_or_interpreter_file(filename), filename

    def test_everything_else_is_the_users(self):
        """A model, an exec'd snippet, a notebook cell, an editable package."""
        from gaspatchio._source import is_framework_or_interpreter_file

        tutorial = Path(gaspatchio.__file__).parent / "tutorials" / "x" / "model.py"
        for filename in (
            *USER_MODEL_PATHS,
            *NAMED_LIKE_THE_FRAMEWORK,
            *UNDER_DIRECTORIES_NAMED_LIKE_TOOLING,
            "<string>",
            "<stdin>",
            "<ipython-input-3-a1b2c3d4e5f6>",
            "/work/proj/.venv/src/acme_models/model.py",
            "/usr/src/app/model.py",
            str(tutorial),
        ):
            assert not is_framework_or_interpreter_file(filename), filename


class TestWindowsPaths:
    """The rule holds on Windows' own path rules, asked here through ntpath."""

    @pytest.fixture
    def windows(self):
        from gaspatchio._source import CodeLocations

        return CodeLocations.of(
            ntpath,
            package=[r"C:\Python313\Lib\site-packages\gaspatchio"],
            interpreter=[r"C:\Python313\Lib", r"C:\proj\.venv\Lib\site-packages"],
        )

    @pytest.mark.parametrize(
        "filename",
        [
            r"C:\Python313\Lib\site-packages\gaspatchio\frame\base.py",
            r"c:\python313\lib\unittest\case.py",
            "C:/Python313/Lib/asyncio/events.py",
            r"C:\proj\.venv\Lib\site-packages\polars\frame.py",
            r"D:\other\Site-Packages\vendored\model.py",
            "<frozen importlib._bootstrap>",
        ],
    )
    def test_installed_code_is_passed_over(self, windows, filename):
        """Compared whole, case-folded, on either separator."""
        assert windows.holds_framework_or_interpreter_code(filename)

    @pytest.mark.parametrize(
        "filename",
        [
            r"C:\proj\models\term\validation.py",
            "C:/proj/models/term/runner.py",
            r"C:\proj\.venv\src\acme_models\model.py",
            r"C:\Python313\Lib\site-packages\gaspatchio\tutorials\l1\model.py",
            "<ipython-input-3-a1b2c3d4e5f6>",
        ],
    )
    def test_a_model_is_the_users(self, windows, filename):
        """Wherever it is kept, and whatever separators its path is written in."""
        assert not windows.holds_framework_or_interpreter_code(filename)


# A model's own check of a parameter. The raise is on line 6, and that line
# is where the error must say it came from.
_CHECK_TERM = """\
from gaspatchio.errors import raise_validation_error


def check_term(term):
    if term <= 0:
        raise_validation_error("policy term must be positive", provided_value=term)
"""
_RAISING_LINE = 6


def _load(path: Path) -> ModuleType:
    """Import the model file at ``path`` under a name of its own."""
    spec = importlib.util.spec_from_file_location(f"_located_{path.stem}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raised_from(path: Path) -> ValidationError:
    """Write the model's check to ``path``, run it, and return what it raised."""
    path.write_text(_CHECK_TERM)
    module = _load(path)
    with pytest.raises(ValidationError) as caught:
        module.check_term(0)
    return caught.value


class TestRaiseValidationErrorLocation:
    """``raise_validation_error`` names the line that raised it, whatever the file."""

    @pytest.mark.parametrize(
        "file_name", ["validation.py", "runner.py", "execution.py", "pricing.py"]
    )
    def test_the_location_is_the_raising_line_whatever_the_file_is_called(
        self, file_name: str
    ) -> None:
        """Two identical files, two names, one answer: the line that raised."""
        # Outside pytest's own temporary directory, so the name is the only
        # thing that differs between the cases.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / file_name
            location = _raised_from(path).source_location

            assert location is not None
            assert location.file_path == str(path)
            assert location.line_number == _RAISING_LINE
            assert location.function_name == "check_term"

    def test_a_model_under_pytests_temporary_directory_is_located(
        self, tmp_path: Path
    ) -> None:
        """A model a test writes to ``tmp_path`` is the model's, not pytest's."""
        path = tmp_path / "pricing.py"
        location = _raised_from(path).source_location

        assert location is not None
        assert location.file_path == str(path)
        assert location.line_number == _RAISING_LINE


class TestTheWalkPassesTheInterpreter:
    """An error raised through the interpreter's own frames names the user's line."""

    def test_a_check_called_through_unittest_names_the_test_not_unittest(self):
        """A check unittest calls from its own frames names the test's line.

        The test expects a different error, so the ValidationError comes
        back out through unittest's ``assertRaises`` rather than being
        swallowed by it.
        """
        case = unittest.TestCase()

        with pytest.raises(ValidationError) as caught:
            case.assertRaises(  # noqa: PT027 -- unittest's own frames are the subject
                KeyError, raise_validation_error, "term must be positive"
            )

        location = caught.value.source_location
        assert location is not None
        assert location.file_path == __file__
        assert "case.assertRaises(" in (location.source_line or "")

    def test_a_notebook_cell_run_by_asyncio_is_named_not_the_event_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cell is the user's code, even with the event loop's frames above it."""
        cell = "<ipython-input-7-0123456789ab>"
        source = (
            "async def check():\n    raise_validation_error('term must be positive')\n"
        )
        # A notebook registers its cells with linecache, as this does.
        monkeypatch.setitem(
            linecache.cache,
            cell,
            (len(source), None, source.splitlines(keepends=True), cell),
        )
        namespace = {"raise_validation_error": raise_validation_error}
        exec(compile(source, cell, "exec"), namespace)  # noqa: S102 -- a stand-in cell

        with pytest.raises(ValidationError) as caught:
            asyncio.run(namespace["check"]())

        location = caught.value.source_location
        assert location is not None
        assert (location.file_path, location.line_number) == (cell, 2)


class TestAModelIsLocatedWhereverItIsKept:
    """A model's own check names its own line, whatever directory holds it."""

    @pytest.mark.parametrize(
        "directory",
        [
            Path(".venv") / "src" / "acme_models",  # an editable install
            Path("env") / "term",
        ],
    )
    def test_the_raising_line_is_named(self, tmp_path: Path, directory: Path) -> None:
        """An editable package under a virtual environment is code its author edits."""
        path = tmp_path / directory / "check.py"
        path.parent.mkdir(parents=True)
        location = _raised_from(path).source_location

        assert location is not None
        assert (location.file_path, location.line_number) == (str(path), _RAISING_LINE)

    def test_gspio_names_the_models_line(self, tmp_path: Path) -> None:
        """Under gspio, a model kept as env/validation.py is named at its own line."""
        model = tmp_path / "env" / "validation.py"
        model.parent.mkdir()
        model.write_text(
            "import polars as pl\n"
            "\n"
            "from gaspatchio import ActuarialFrame\n"
            "\n"
            "\n"
            "def main(af: ActuarialFrame, params=None) -> ActuarialFrame:\n"
            "    af.premium = af.age * 10.0\n"
            '    af.commission = pl.col("premum") * 0.1\n'
            "    return af\n"
        )
        book = tmp_path / "book.parquet"
        pl.DataFrame({"policy_id": ["P-1"], "age": [40]}).write_parquet(book)

        run = subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
            [
                sys.executable,
                "-m",
                "gaspatchio.cli",
                "run-model",
                str(model),
                str(book),
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "COLUMNS": "400"},
            check=False,
        )

        assert run.returncode == 1
        assert f"Location: {model}:8" in run.stdout + run.stderr
