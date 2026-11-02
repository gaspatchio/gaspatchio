# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A model run from plain Python is quiet, and ``gspio`` keeps its logging.

gaspatchio logs through loguru, whose default handler writes every level
from DEBUG up to stderr until something removes it. The CLI replaced it with
a handler at INFO, so ``gspio`` was quiet enough, but a script or a notebook
that imported gaspatchio printed the library's DEBUG lines -- six for one
assumption table, dozens for a model. The package now mutes its own records
when it is imported, as loguru advises a library to, and the CLI turns them
back on.

What a user must hear unasked is not a log record. A table re-registered
with different data, or a slow pattern in the user's own code, is raised as
a ``GaspatchioWarning`` through Python's ``warnings``: shown by default at
the user's own line, silenced by the usual filter, and said once, through
that one channel, under ``gspio`` as in a script.

Each case runs in a process of its own. Loguru's state is process-wide, and
this suite turns the package's records on for itself (``conftest.py``), so
only a fresh interpreter shows what a user's script sees.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import TYPE_CHECKING

import polars as pl
import pytest

if TYPE_CHECKING:
    from pathlib import Path

# One assumption table, looked up and collected: the smallest model that logs.
_IMPORTS = """\
import polars as pl
from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
"""
_ONE_TABLE = """\
rates = pl.DataFrame({"age": [40, 41], "rate": [0.001, 0.0011]})
mort = Table(name="mort", source=rates, dimensions={"age": "age"}, value="rate")
af = ActuarialFrame(pl.DataFrame({"age": [40, 41]}))
af.q = mort.lookup(age=af.age)
af.collect()
"""

# The same calculation as a model file, for gspio to run.
_MODEL = """\
import polars as pl
from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table


def main(af: ActuarialFrame, params=None) -> ActuarialFrame:
    rates = pl.DataFrame({"age": [40, 41], "rate": [0.001, 0.0011]})
    mort = Table(name="mort", source=rates, dimensions={"age": "age"}, value="rate")
    af.q = mort.lookup(age=af.age)
    return af
"""

# A line gaspatchio logs at DEBUG for every table it builds, one it logs at
# INFO when gspio finishes a run, and one it logs at TRACE when a debug run
# is verbose.
_A_DEBUG_LINE = "Registered table 'mort'"
_AN_INFO_LINE = "Full model run finished"
_A_VERBOSE_TRACE_LINE = "Computation Graph:"


def _environment(**settings: str) -> dict[str, str]:
    """Return this process's environment, the two log switches set as given."""
    inherited = {
        name: value
        for name, value in os.environ.items()
        if name not in {"LOGURU_LEVEL", "GASPATCHIO_VERBOSE"}
    }
    return {**inherited, **settings}


def _python(source: str, **settings: str) -> subprocess.CompletedProcess[str]:
    """Run ``source`` in a fresh interpreter, as a user's script."""
    return subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        env=_environment(**settings),
        check=False,
    )


def _gspio(*arguments: str | Path, **settings: str) -> subprocess.CompletedProcess[str]:
    """Run the CLI in a process of its own."""
    return subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
        [sys.executable, "-m", "gaspatchio.cli", *(str(one) for one in arguments)],
        capture_output=True,
        text=True,
        env=_environment(**settings),
        check=False,
    )


def _model_and_book(tmp_path: Path) -> tuple[Path, Path]:
    model = tmp_path / "model.py"
    model.write_text(_MODEL)
    book = tmp_path / "book.parquet"
    pl.DataFrame({"policy_id": ["P-1", "P-2"], "age": [40, 41]}).write_parquet(book)
    return model, book


def test_library_use_writes_nothing_to_stderr() -> None:
    """Building a table and collecting a frame says nothing unless asked."""
    run = _python(_IMPORTS + _ONE_TABLE)

    assert run.returncode == 0, run.stderr
    assert run.stderr == ""


def test_loguru_level_does_not_ask_the_library_to_speak() -> None:
    """LOGURU_LEVEL sets loguru's own handler; it is not a request to gaspatchio."""
    run = _python(_IMPORTS + _ONE_TABLE, LOGURU_LEVEL="TRACE")

    assert run.returncode == 0, run.stderr
    assert run.stderr == ""


def test_a_script_can_turn_the_logs_on() -> None:
    """``logger.enable("gaspatchio")``, after the import, is loguru's switch."""
    enable = "from loguru import logger\n\nlogger.enable('gaspatchio')\n"

    run = _python(_IMPORTS + enable + _ONE_TABLE)

    assert run.returncode == 0, run.stderr
    assert _A_DEBUG_LINE in run.stderr


def test_gspio_logs_from_info_up_by_default(tmp_path: Path) -> None:
    """The command line keeps the logging it showed: INFO, and not DEBUG."""
    model, book = _model_and_book(tmp_path)

    run = _gspio("run-model", model, book, "-o", tmp_path / "results.parquet")

    assert run.returncode == 0, run.stdout + run.stderr
    assert _AN_INFO_LINE in run.stderr
    assert _A_DEBUG_LINE not in run.stderr


def test_gspio_still_reads_loguru_level_and_gaspatchio_verbose(tmp_path: Path) -> None:
    """The two switches AGENTS.md documents for gspio both still work."""
    model, book = _model_and_book(tmp_path)
    command = (
        "run-model",
        model,
        book,
        "--mode",
        "debug",
        "-o",
        tmp_path / "r.parquet",
    )

    verbose = _gspio(*command, LOGURU_LEVEL="TRACE", GASPATCHIO_VERBOSE="true")
    terse = _gspio(*command, LOGURU_LEVEL="TRACE", GASPATCHIO_VERBOSE="false")

    assert verbose.returncode == 0, verbose.stdout + verbose.stderr
    assert terse.returncode == 0, terse.stdout + terse.stderr
    assert _A_DEBUG_LINE in verbose.stderr
    assert _A_DEBUG_LINE in terse.stderr
    assert _A_VERBOSE_TRACE_LINE in verbose.stderr
    assert _A_VERBOSE_TRACE_LINE not in terse.stderr


# --- what a user must hear arrives as a warning, once ------------------------

# A table registered twice under one name with different data; the second
# registration is the line the warning names.
_REREGISTERS = """\
import polars as pl
from gaspatchio.assumptions import Table

first = pl.DataFrame({"age": [40, 41], "rate": [0.001, 0.0011]})
second = pl.DataFrame({"age": [40, 41], "rate": [0.002, 0.0022]})
Table(name="mort", source=first, dimensions={"age": "age"}, value="rate")
Table(name="mort", source=second, dimensions={"age": "age"}, value="rate")
"""
_REREGISTERED_AT = 7

# A slow pattern in the user's own code. The function is one Polars cannot
# translate, so Polars' own warning about map_elements stays out of it.
_SLOW_PATTERN = """\
import math

import gaspatchio
import polars as pl

frame = pl.DataFrame({"x": [4, 9]})
frame.select(pl.col("x").map_elements(lambda v: math.gcd(v, 6), return_dtype=pl.Int64))
"""
_SLOW_AT = 7

# Both, inside a model's main(), for gspio to run.
_MODEL_THAT_WARNS = """\
import math

import polars as pl
from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table


def main(af: ActuarialFrame, params=None) -> ActuarialFrame:
    first = pl.DataFrame({"age": [40, 41], "rate": [0.001, 0.0011]})
    second = pl.DataFrame({"age": [40, 41], "rate": [0.002, 0.0022]})
    Table(name="mort", source=first, dimensions={"age": "age"}, value="rate")
    mort = Table(name="mort", source=second, dimensions={"age": "age"}, value="rate")
    af.q = mort.lookup(age=af.age)
    af.gcd = af.age.map_elements(lambda v: math.gcd(v, 6), return_dtype=pl.Int64)
    return af
"""

_REREGISTERED = "was re-registered with different data"
_SLOW = "PerformanceWarning: map_elements() runs <lambda> once for every value"

# How loguru writes a record: the time, then the level between bars.
_A_LOG_LINE = re.compile(r" \| (TRACE|DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL) +\| ")


def _script(
    tmp_path: Path, source: str
) -> tuple[Path, subprocess.CompletedProcess[str]]:
    """Run ``source`` as a script file in a fresh interpreter."""
    script = tmp_path / "script.py"
    script.write_text(source)
    run = subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=_environment(),
        check=False,
    )
    return script, run


def _logged(stderr: str) -> list[str]:
    """Return the lines of ``stderr`` that loguru wrote."""
    return [line for line in stderr.splitlines() if _A_LOG_LINE.search(line)]


def test_a_re_registered_table_is_a_gaspatchio_warning_and_not_a_log_line(
    tmp_path: Path,
) -> None:
    """Shown by default, at the script's own line, and by no other channel."""
    script, run = _script(tmp_path, _REREGISTERS)

    assert run.returncode == 0, run.stderr
    warning, source_line = run.stderr.splitlines()
    assert warning.startswith(
        f"{script}:{_REREGISTERED_AT}: GaspatchioWarning: Assumption table "
        f"'mort' {_REREGISTERED}."
    )
    assert source_line.strip().startswith('Table(name="mort", source=second')
    assert _logged(run.stderr) == []


def test_a_slow_pattern_is_a_performance_warning_and_not_a_log_line(
    tmp_path: Path,
) -> None:
    """The user's own map_elements() is named at their line, and never logged."""
    script, run = _script(tmp_path, _SLOW_PATTERN)

    assert run.returncode == 0, run.stderr
    warning, source_line = run.stderr.splitlines()
    assert warning.startswith(f"{script}:{_SLOW_AT}: {_SLOW}")
    assert "map_elements(lambda v: math.gcd(v, 6)" in source_line
    assert _logged(run.stderr) == []


def test_one_filter_on_gaspatchio_warning_silences_both(tmp_path: Path) -> None:
    """The filter the package docstring gives reaches the slow-pattern notice too."""
    _script_path, run = _script(
        tmp_path,
        "import warnings\n"
        "import gaspatchio\n"
        'warnings.filterwarnings("ignore", category=gaspatchio.GaspatchioWarning)\n'
        + _REREGISTERS
        + _SLOW_PATTERN,
    )

    assert run.returncode == 0, run.stderr
    assert run.stderr == ""


@pytest.mark.parametrize("level", [None, "TRACE"])
def test_gspio_says_each_warning_once(tmp_path: Path, level: str | None) -> None:
    """The CLI turns the logs on, and a warning is still said once, not twice."""
    model = tmp_path / "model.py"
    model.write_text(_MODEL_THAT_WARNS)
    book = tmp_path / "book.parquet"
    pl.DataFrame({"policy_id": ["P-1", "P-2"], "age": [40, 41]}).write_parquet(book)

    settings = {} if level is None else {"LOGURU_LEVEL": level}
    run = _gspio("run-model", model, book, **settings)

    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stderr.count(_REREGISTERED) == 1
    assert run.stderr.count("PerformanceWarning:") == 1
    assert f"{model}:12: GaspatchioWarning" in run.stderr
    assert f"{model}:14: {_SLOW}" in run.stderr
    assert [
        line
        for line in _logged(run.stderr)
        if _REREGISTERED in line or "MAP_ELEMENTS_PERFORMANCE_ISSUE" in line
    ] == []
