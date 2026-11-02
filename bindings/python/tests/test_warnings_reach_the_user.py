# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What a user must hear unasked arrives as a ``GaspatchioWarning``, once.

The package mutes its own log records when it is used as a library, because
a library speaks only when asked. Some of what it logged was not chatter: a
request it answered another way, a result it could not deliver in full, a
hazard in the numbers. Each of those is now raised through Python's
``warnings`` as a ``GaspatchioWarning``, located at the caller's line, and
is no longer logged as well -- so it is shown whether or not the logs are
on, and said through one channel.

The re-registration warning, the slow-pattern notice, the artifact's
missing payloads and the hole a fold cannot account for are pinned beside
the code they belong to. These are the rest.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import runpy
import subprocess
import sys
import threading
import types
import warnings
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, cast

import polars as pl
import pytest
from loguru import logger

import gaspatchio
from gaspatchio import Curve, GaspatchioWarning
from gaspatchio.assumptions import _api, list_tables
from gaspatchio.assumptions._dimensions import ComputedDimension
from gaspatchio.assumptions._strategies import (
    ExtendOverflow,
    FillForward,
    LinearInterpolate,
)
from gaspatchio.frame.graph.expr_analyzer import extract_dependencies
from gaspatchio.frame.graph.filter_handler import DataFrameFilter

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextmanager
def _heard() -> Iterator[tuple[list[warnings.WarningMessage], list[str]]]:
    """Record the gaspatchio warnings raised, and the log records written, inside."""
    logged: list[str] = []
    sink_id = logger.add(
        lambda message: logged.append(message.record["message"]), level="WARNING"
    )
    raised: list[warnings.WarningMessage] = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            yield raised, logged
        raised.extend(w for w in caught if issubclass(w.category, GaspatchioWarning))
    finally:
        logger.remove(sink_id)


def _said_once(
    raised: list[warnings.WarningMessage], logged: list[str], words: str
) -> str:
    """Return the one warning saying ``words``, raised here and never logged."""
    (warning,) = [w for w in raised if words in str(w.message)]
    assert warning.filename == __file__, "the warning names this file's line"
    assert [line for line in logged if words in line] == []
    return str(warning.message)


def test_cubic_interpolation_says_it_used_linear() -> None:
    """A different method than asked for is not a silent substitution."""
    gappy = pl.DataFrame({"age": [40, 41, 42], "value": [0.1, None, 0.3]})

    with _heard() as (raised, logged):
        LinearInterpolate(method="cubic").apply(gappy)

    message = _said_once(raised, logged, "linear interpolation is used instead")
    assert 'method="linear"' in message  # how to choose it deliberately


def test_a_forward_fill_limit_says_it_is_not_applied() -> None:
    """The limit asked for is ignored, and the user is told so."""
    gappy = pl.DataFrame({"age": [40, 41, 42], "value": [0.1, None, None]})

    with _heard() as (raised, logged):
        FillForward(limit=1).apply(gappy)

    message = _said_once(raised, logged, "Forward fill limit (1) is not implemented")
    assert "Leave limit unset" in message


def test_an_overflow_with_nowhere_to_start_says_it_was_not_extended() -> None:
    """No numeric neighbour to extend from, so the table stays short, out loud."""
    table = pl.DataFrame({"duration": ["Ult."], "value": [0.5]})

    with _heard() as (raised, logged):
        ExtendOverflow(column="Ult.").apply(table, "duration")

    message = _said_once(raised, logged, "Cannot determine starting point")
    assert "from_value=" in message


def test_a_computed_dimension_says_it_overwrites_a_column() -> None:
    """A source column replaced by a computed one of the same name is named."""
    source = pl.DataFrame({"age": [40, 41], "rate": [0.1, 0.2]})

    with _heard() as (raised, logged):
        ComputedDimension(expression=pl.col("age") + 1, name="age").validate(source)

    _said_once(raised, logged, "Column 'age' already exists")


def test_a_svensson_fit_with_a_non_positive_rate_says_so() -> None:
    """A fitted curve whose long or short end is not positive is a hazard."""
    rates = [-0.030, -0.031, -0.032, -0.033, -0.034, -0.035, -0.036, -0.037]

    with _heard() as (raised, logged):
        Curve.fit_svensson(tenors=[1, 2, 3, 5, 7, 10, 15, 20], rates=rates)

    _said_once(raised, logged, "The Svensson fit gave")


def test_a_svensson_curve_built_with_a_non_positive_b0_says_so() -> None:
    """The constructor's warning is a GaspatchioWarning too, at the caller's line."""
    with _heard() as (raised, logged):
        Curve.from_svensson(b0=-0.01, b1=0.0, b2=0.0, b3=0.0, tau1=1.0, tau2=5.0)

    _said_once(raised, logged, "Svensson b0=-0.01 is non-positive")


def test_an_ill_conditioned_smith_wilson_fit_says_so_once() -> None:
    """The system the curve is built from is named; the candidates are not."""
    knots = [0.1 * i for i in range(1, 201)]
    rates = [0.03 + 0.0001 * i for i in range(200)]

    with _heard() as (raised, logged):
        Curve.fit_smith_wilson(tenors=knots, rates=rates, ufr=0.042, alpha=0.05)

    _said_once(raised, logged, "is ill-conditioned")


def test_a_calibration_says_nothing_about_alphas_it_did_not_choose() -> None:
    """A rejected candidate's conditioning is the search's business, not the user's."""
    knots = [0.1 * i for i in range(1, 201)]
    rates = [0.03 + 0.0001 * i for i in range(200)]

    with _heard() as (raised, _logged):
        Curve.fit_smith_wilson(tenors=knots, rates=rates, ufr=0.042, llp=20)

    assert raised == []


def test_a_filter_that_cannot_be_applied_says_every_row_is_kept() -> None:
    """An export asked for a subset and got the whole book: that is said."""
    frame = pl.DataFrame({"policy_id": [1, 2], "year": [2024, 2025]})

    with _heard() as (raised, logged):
        kept = DataFrameFilter(frame).apply_filter("this is not an expression (")

    assert kept.height == frame.height
    message = _said_once(raised, logged, "so every row is kept")
    assert "pl.col('year') == 2025" in message  # what a filter looks like


def test_dependencies_that_cannot_be_read_are_not_returned_in_silence() -> None:
    """An empty dependency list that is a failure, not a fact, says so."""

    class _Meta:
        def root_names(self) -> list[str]:
            msg = "this expression cannot be walked"
            raise ValueError(msg)

    class _Unwalkable:
        meta = _Meta()

    with _heard() as (raised, logged):
        found = extract_dependencies(cast("pl.Expr", _Unwalkable()))

    assert found == []
    message = _said_once(raised, logged, "so none are returned")
    assert "pl.col(" in message


def test_a_registry_that_cannot_be_read_lists_no_tables_out_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty list that means "could not look" is not "nothing registered"."""

    class _Unreadable:
        def list_tables(self) -> list[str]:
            msg = "the registry is gone"
            raise RuntimeError(msg)

    monkeypatch.setattr(_api, "PyAssumptionTableRegistry", _Unreadable)

    with _heard() as (raised, logged):
        names = list_tables()

    assert names == []
    message = _said_once(raised, logged, "could not read the table registry")
    assert "reinstall gaspatchio" in message


def test_a_day_count_slow_path_the_framework_chose_raises_nothing() -> None:
    """The framework's own map_elements() call is not the user's to hear about."""
    from gaspatchio.schedule._day_count import Actual365Fixed
    from gaspatchio.schedule._schedule import Schedule

    frame = pl.DataFrame({"contract_inception": [date(2024, 3, 15)]})
    schedule = Schedule.from_inception(
        inception_column="contract_inception",
        n_periods=2,
        frequency="1M",
        day_count=Actual365Fixed(),
    )

    with _heard() as (raised, _logged):
        frame.with_columns(yfs=schedule.year_fractions_expr())

    assert raised == []


# --- one rule for where a warning lands --------------------------------------
#
# A warning is located by the rule every frame walk follows,
# is_framework_or_interpreter_file, so it lands where an error's location and a
# calculation's source line would: a model run in place under the package's
# tutorials is the user's, and so is the line that ran it.

_PACKAGE = Path(gaspatchio.__file__).parent

_RE_REGISTERS = (
    "import polars as pl\n"
    "from gaspatchio.assumptions import Table\n"
    "\n"
    'first = pl.DataFrame({"age": [40, 41], "rate": [0.001, 0.0011]})\n'
    'second = pl.DataFrame({"age": [40, 41], "rate": [0.002, 0.0022]})\n'
    'Table(name="in_place", source=first, dimensions={"age": "age"}, value="rate")\n'
    'Table(name="in_place", source=second, dimensions={"age": "age"}, value="rate")\n'
)


def test_a_tutorial_run_in_place_is_named_at_its_own_line() -> None:
    """A model under tutorials/ is model code: the warning lands on its line."""
    model = str(_PACKAGE / "tutorials" / "in-place" / "base" / "model.py")
    code = compile(_RE_REGISTERS, model, "exec")  # nothing is written to disk

    with _heard() as (raised, _logged):
        exec(code, {"__name__": "model"})  # noqa: S102 -- a tutorial run in place

    (warning,) = [w for w in raised if "re-registered" in str(w.message)]
    assert (warning.filename, warning.lineno) == (model, 7)


@pytest.mark.parametrize(
    "namespace",
    [
        pytest.param({}, id="globals-of-its-own"),
        pytest.param(
            types.ModuleType("gaspatchio.frame._on_its_own").__dict__,
            id="globals-with-no-loader",
        ),
    ],
)
def test_with_no_line_of_the_users_on_the_stack_the_warning_says_so(
    namespace: dict[str, object],
) -> None:
    """Raised by the framework running on its own, it names gaspatchio's line."""
    site = str(_PACKAGE / "frame" / "_on_its_own.py")
    exec(  # noqa: S102 -- framework code with nobody's code above it
        compile(
            "from gaspatchio._warning import warn\n"
            "\n"
            "\n"
            "def run():\n"
            '    warn("a table moved while the export ran")\n',
            site,
            "exec",
        ),
        namespace,
    )
    worker = threading.Thread(target=namespace["run"])

    with _heard() as (raised, _logged):
        worker.start()
        worker.join()

    (warning,) = raised
    assert (warning.filename, warning.lineno) == (site, 5)
    assert "No line of your own code" in str(warning.message)


# --- a warning never raises, whatever ran the user's code ---------------------
#
# Handed a module's globals, warnings.warn_explicit() asks the module's loader
# for the line's source, and raises where the loader cannot answer. Jupyter and
# IPython run a cell in globals whose loader is None, as runpy.run_path runs a
# script; python -m runs a module whose loader answers for the module's own
# name, not for __main__; a module whose file has gone since it was imported
# has no source to give. Each of those is still warned at the user's line.

_SECOND_TABLE_AT = 7  # the line of _RE_REGISTERS that re-registers the table


def _re_registers(name: str) -> str:
    """Return the re-registration, under a table name no other test uses."""
    return _RE_REGISTERS.replace('"in_place"', f'"{name}"')


def _python(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run this interpreter with ``arguments``, in a process of its own."""
    return subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
        [sys.executable, *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_script_run_by_runpy_is_warned_at_its_line(tmp_path: Path) -> None:
    """runpy.run_path runs a script in globals with no loader."""
    script = tmp_path / "model.py"
    script.write_text(_re_registers("run_by_runpy"))

    with _heard() as (raised, _logged):
        runpy.run_path(str(script), run_name="__main__")

    (warning,) = [w for w in raised if "re-registered" in str(w.message)]
    assert (warning.filename, warning.lineno) == (str(script), _SECOND_TABLE_AT)
    shown = warnings.formatwarning(
        warning.message, warning.category, warning.filename, warning.lineno
    )
    assert 'Table(name="run_by_runpy", source=second' in shown


def test_a_notebook_cell_is_warned_at_its_line() -> None:
    """Jupyter and IPython run a cell in a fresh module's globals: no loader."""
    cell = types.ModuleType("__main__").__dict__
    code = compile(_re_registers("in_a_cell"), "<ipython-input-3-a1b2c3>", "exec")

    with _heard() as (raised, _logged):
        exec(code, cell)  # noqa: S102 -- a cell, run as a notebook runs one

    (warning,) = [w for w in raised if "re-registered" in str(w.message)]
    assert (warning.filename, warning.lineno) == (
        "<ipython-input-3-a1b2c3>",
        _SECOND_TABLE_AT,
    )


def test_a_module_whose_spec_has_no_loader_is_warned_at_its_line() -> None:
    """A module made from a spec that names no loader."""
    module = types.ModuleType("made_from_a_spec")
    module.__spec__ = importlib.machinery.ModuleSpec("made_from_a_spec", None)
    code = compile(_re_registers("spec_without_loader"), "<made>", "exec")

    with _heard() as (raised, _logged):
        exec(code, module.__dict__)  # noqa: S102 -- the module's own code

    (warning,) = [w for w in raised if "re-registered" in str(w.message)]
    assert (warning.filename, warning.lineno) == ("<made>", _SECOND_TABLE_AT)


def test_a_module_whose_file_has_gone_is_warned_at_its_line(tmp_path: Path) -> None:
    """Imported, then its file removed: the loader has no source to give."""
    path = tmp_path / "moved_model.py"
    path.write_text(
        "from gaspatchio.assumptions import Table\n"
        "\n"
        'BY_AGE = {"age": "age"}\n'
        "\n"
        "def run(first, second):\n"
        '    Table(name="moved", source=first, dimensions=BY_AGE, value="rate")\n'
        '    Table(name="moved", source=second, dimensions=BY_AGE, value="rate")\n'
    )
    spec = importlib.util.spec_from_file_location("moved_model", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path.unlink()

    with _heard() as (raised, _logged):
        module.run(
            pl.DataFrame({"age": [40, 41], "rate": [0.001, 0.0011]}),
            pl.DataFrame({"age": [40, 41], "rate": [0.002, 0.0022]}),
        )

    (warning,) = [w for w in raised if "re-registered" in str(w.message)]
    assert (warning.filename, warning.lineno) == (str(path), 7)


def test_a_module_run_with_python_dash_m_is_warned_at_its_line(
    tmp_path: Path,
) -> None:
    """Under python -m it runs as __main__, a name its loader cannot answer for."""
    package = tmp_path / "models"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "term.py").write_text(_re_registers("run_with_dash_m"))

    run = _python("-m", "models.term", cwd=tmp_path)

    assert run.returncode == 0, run.stderr
    warning = f"{Path('models', 'term.py')}:{_SECOND_TABLE_AT}: GaspatchioWarning:"
    assert warning in run.stderr
    assert 'Table(name="run_with_dash_m", source=second' in run.stderr


def test_a_script_run_with_deprecations_as_errors_is_warned_at_its_line(
    tmp_path: Path,
) -> None:
    """A script's loader with no spec is a deprecation, raised under -W error."""
    script = tmp_path / "model.py"
    script.write_text(_re_registers("deprecations_as_errors"))

    run = _python("-W", "error::DeprecationWarning", str(script), cwd=tmp_path)

    assert run.returncode == 0, run.stderr
    assert f"{script}:{_SECOND_TABLE_AT}: GaspatchioWarning:" in run.stderr


def test_level_2_then_its_first_step_through_runpy_warns_at_the_step() -> None:
    """Level 2's base model, then its first step, in one process."""
    level_2 = _PACKAGE / "tutorials" / "level-2-assumptions"
    base = level_2 / "base" / "model.py"
    step = level_2 / "steps" / "01-multi-dimension" / "model.py"

    run = _python(
        "-c",
        "import runpy\n"
        f"runpy.run_path({str(base)!r}, run_name='__main__')\n"
        f"runpy.run_path({str(step)!r}, run_name='__main__')\n",
        cwd=level_2,
    )

    assert run.returncode == 0, run.stderr
    assert f"{step}:76: GaspatchioWarning: Assumption table 'mortality'" in run.stderr
