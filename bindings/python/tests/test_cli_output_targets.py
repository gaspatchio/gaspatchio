# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Every gspio output flag refuses, by name, a path with no place to go.
# ABOUTME: A missing directory, a directory that is a file, a path that is a directory.
"""Every file a gspio command writes is refused by its flag where it cannot go.

``gspio run-model ... -o report/results.parquet`` with no ``report/`` ran the
whole model and then raised a traceback; ``-o`` naming a directory did the
same; ``run-artifact --aggregate -o report/totals.json`` quietly created
``report/``; ``diff --html`` and ``calc-graph --html`` naming a directory raised
after other files were written. No command creates a directory for its output
file, so every output flag is asked, before the command runs anything, whether
the path has a place to go, and is refused by name with status 2 where it has
not.

``tutorial init`` is scaffolding rather than an output file: it creates its
destination and the directories above it, as it always has. Only the two
destinations that raised a traceback -- one inside a file, and a file given
with ``--force`` -- are refused by name.

The report commands -- validate, diff, compare, verify and the ``graph``
questions -- say their verdict first and then refuse the storing, because
a verdict reached and not stored is a job unfinished rather than a refusal
(``test_cli_artifact.py`` holds that order); the refusal still names the flag
and writes nothing.

``test_every_output_flag_is_probed_here`` reads the flags off the command
tree, so an output flag added later without a case here fails.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest
import typer
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.engines import REGISTERED_ENGINES, register_engine
from tests.engines.test_aggregating import _artifact as _executable_artifact
from tests.engines.test_aggregating import _spec
from tests.test_cli_artifact import MODEL_SRC, _needle, _unwrapped

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from gaspatchio.engines.protocol import NodeStatus

runner = CliRunner()

# A command line, given the fixture's files and the path the output flag names.
type _CommandLine = Callable[[dict[str, Path], str], list[str]]


class _NeverRuns:
    """An engine that fails the test if a refused output lets it start."""

    name = "never-runs"
    version = "0.0.0-test"

    def validate_tree(self, document: dict[str, object]) -> tuple[NodeStatus, ...]:  # noqa: ARG002 -- the protocol's parameter
        return ()

    def run(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError  # the output was refused before the engine started

    def aggregate(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError  # the output was refused before the engine started


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Write, once, what the commands below read: a model, a book, an audit file."""
    here = tmp_path_factory.mktemp("made")
    model = here / "model.py"
    model.write_text(MODEL_SRC)
    book = here / "model_points.parquet"
    pl.DataFrame(
        {"policy_id": ["A", "B"], "sum_assured": [100_000.0, 50_000.0]}
    ).write_parquet(book)
    audit = here / "model.audit.json"
    results = here / "results.parquet"
    reference = here / "reference.parquet"
    for argv in (
        [
            "calc-graph",
            str(model),
            str(book),
            "-o",
            str(audit),
            "--results",
            str(results),
        ],
        ["run-model", str(model), str(book), "--every-node", "-o", str(reference)],
    ):
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, result.output
    executable, inputs = _executable_artifact(here)
    spec = _spec(here, [{"alias": "bel", "kind": "Sum", "column": "pv"}])
    a_file = here / "a_file"
    a_file.write_text("not a directory")
    return {
        "model": model,
        "book": book,
        "audit": audit,
        "reference": reference,
        "executable": executable,
        "inputs": inputs,
        "spec": spec,
        "a_file": a_file,
    }


@pytest.fixture
def never_runs() -> Iterator[None]:
    """Register an engine that must not start, for one test, then forget it."""
    engines = dict(REGISTERED_ENGINES)
    register_engine("never-runs", _NeverRuns)
    yield
    REGISTERED_ENGINES.clear()
    REGISTERED_ENGINES.update(engines)


def _command_lines() -> dict[str, tuple[str, _CommandLine]]:
    """Return each output flag's command line, by case id, beside the flag it names."""

    def run(f: dict[str, Path], *rest: str) -> list[str]:
        return [str(f["model"]), str(f["book"]), *rest]

    def audit(f: dict[str, Path]) -> str:
        return str(f["audit"])

    def artifact(f: dict[str, Path], *rest: str) -> list[str]:
        engine = ["--engine", "never-runs"]
        return [str(f["executable"]), str(f["inputs"]), *engine, *rest]

    def staged(f: dict[str, Path]) -> str:
        return str(f["a_file"].parent / "staged.audit.json")

    return {
        "run-model --results": (
            "--results",
            lambda f, t: ["run-model", *run(f, "-o", t)],
        ),
        "run-model --every-node --results": (
            "--results",
            lambda f, t: ["run-model", *run(f, "--every-node", "-o", t)],
        ),
        "run-single-policy --results": (
            "--results",
            lambda f, t: ["run-single-policy", *run(f, "A", "-o", t)],
        ),
        "calc-graph --artifact": (
            "--artifact",
            lambda f, t: ["calc-graph", *run(f, "-o", t)],
        ),
        "calc-graph --results": (
            "--results",
            lambda f, t: ["calc-graph", *run(f, "-o", staged(f), "--results", t)],
        ),
        "calc-graph --html": (
            "--html",
            lambda f, t: ["calc-graph", *run(f, "-o", staged(f), "--html", t)],
        ),
        "calc-graph --xlsx": (
            "--xlsx",
            lambda f, t: ["calc-graph", *run(f, "-o", staged(f), "--xlsx", t)],
        ),
        "run-artifact --results": (
            "--results",
            lambda f, t: ["run-artifact", *artifact(f, "-o", t)],
        ),
        "run-artifact --aggregate --results": (
            "--results",
            lambda f, t: [
                "run-artifact",
                *artifact(f, "--aggregate", str(f["spec"]), "-o", t),
            ],
        ),
        "validate --output-file": (
            "--output-file",
            lambda f, t: ["validate", audit(f), "-o", t],
        ),
        "diff --output-file": (
            "--output-file",
            lambda f, t: ["diff", audit(f), audit(f), "-o", t],
        ),
        "diff --html": (
            "--html",
            lambda f, t: ["diff", audit(f), audit(f), "--html", t],
        ),
        "compare --output-file": (
            "--output-file",
            lambda f, t: [
                "compare",
                audit(f),
                str(f["reference"]),
                str(f["reference"]),
                "-o",
                t,
            ],
        ),
        "verify --output-file": (
            "--output-file",
            lambda f, t: ["verify", audit(f), "-o", t],
        ),
        "sheet --output": ("--output", lambda f, t: ["sheet", audit(f), "-o", t]),
        **{
            f"graph {question} --output-file": (
                "--output-file",
                lambda f, t, q=question, c=column: [
                    "graph",
                    q,
                    audit(f),
                    *c,
                    "-o",
                    t,
                ],
            )
            for question, column in (
                ("precedents", ["death_claims"]),
                ("dependents", ["sum_assured"]),
                ("trace", ["death_claims"]),
                ("affected", ["sum_assured"]),
                ("unused", []),
                ("holes", []),
                ("tiers", []),
            )
        },
    }


_COMMAND_LINES = _command_lines()

# Where each kind of path with no place to go points, from the fixture's own
# directory: a directory that is not there, the directory itself, and a file
# under a file.
_NO_PLACE: dict[str, Callable[[dict[str, Path]], Path]] = {
    "missing directory": lambda f: f["a_file"].parent / "no_such_directory" / "out",
    "a directory": lambda f: f["a_file"].parent,
    "under a file": lambda f: f["a_file"] / "out",
}


def _model_run(made: dict[str, Path]) -> list[str]:
    """Return the model and the book, as a run command's two arguments."""
    return [str(made["model"]), str(made["book"])]


def _everything_in(made: dict[str, Path]) -> dict[str, bytes]:
    """Return every file under the fixture's directory, by path, with its bytes."""
    root = made["a_file"].parent
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.mark.usefixtures("never_runs")
@pytest.mark.parametrize("where", list(_NO_PLACE))
@pytest.mark.parametrize("case", list(_COMMAND_LINES))
def test_an_output_with_no_place_to_go_is_refused_by_its_flag(
    made: dict[str, Path], case: str, where: str
) -> None:
    """Exit 2, the flag and the path named, no traceback, and not one byte written."""
    flag, command_line = _COMMAND_LINES[case]
    target = _NO_PLACE[where](made)
    before = _everything_in(made)

    result = runner.invoke(app, command_line(made, str(target)))

    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    said = _unwrapped(result.stderr)
    assert _needle(f"{flag} names") in said, result.stderr
    assert _needle("so nothing was written") in said, result.stderr
    assert _everything_in(made) == before
    assert not (made["a_file"].parent / "no_such_directory").exists()


def test_a_missing_directory_is_named_with_the_command_that_makes_it(
    made: dict[str, Path],
) -> None:
    """The move is ``mkdir -p`` on the directory; gspio does not make it itself."""
    folder = made["a_file"].parent / "no_such_directory"

    result = runner.invoke(
        app,
        ["run-model", *_model_run(made), "-o", str(folder / "r.parquet")],
    )

    assert result.exit_code == 2, result.output
    said = _unwrapped(result.stderr)
    assert _needle(f"--results names r.parquet in {folder}") in said
    assert _needle(f"mkdir -p {folder}") in said
    assert not folder.exists()


def test_a_report_with_no_place_to_go_is_still_said_first(
    made: dict[str, Path],
) -> None:
    """The verdict is on stdout whole; the refusal of the storing is on stderr."""
    folder = str(made["a_file"].parent)

    result = runner.invoke(
        app, ["validate", str(made["audit"]), "--json", "-o", folder]
    )

    assert result.exit_code == 2, result.output
    assert '"ok": true' in result.stdout
    said = _unwrapped(result.stderr)
    assert _needle("The report was reached but not stored: --output-file names") in said


def test_an_output_that_is_an_existing_file_is_still_written_over(
    tmp_path: Path, made: dict[str, Path]
) -> None:
    """Only a path with no place to go is refused: a file there is replaced."""
    target = tmp_path / "results.parquet"
    target.write_text("last quarter's")

    result = runner.invoke(app, ["run-model", *_model_run(made), "-o", str(target)])

    assert result.exit_code == 0, result.output
    assert pl.read_parquet(target).height == 2


def _the_output_options() -> set[tuple[str, str]]:
    """Return every (command, flag) whose path is written rather than read."""
    found: set[tuple[str, str]] = set()

    def walk(command: object, prefix: tuple[str, ...]) -> None:
        for name, sub in (getattr(command, "commands", None) or {}).items():
            walk(sub, (*prefix, name))
        for param in getattr(command, "params", ()):
            kind = param.type
            is_a_path = hasattr(kind, "exists") and hasattr(kind, "dir_okay")
            if param.param_type_name == "option" and is_a_path and not kind.exists:
                found.add((" ".join(prefix), param.opts[0]))

    walk(typer.main.get_command(app), ())
    return found


# Path options that a command reads rather than writes; every other path
# option is an output and has a case above.
_READ_NOT_WRITTEN = {("graph unused", "--keep-from")}


def test_every_output_flag_is_probed_here() -> None:
    probed = {
        (case.split(" --")[0], flag) for case, (flag, _) in _COMMAND_LINES.items()
    } | {("tutorial init", "--dest")}

    assert _the_output_options() - _READ_NOT_WRITTEN == probed


# --- gspio tutorial init ---------------------------------------------------------
#
# Scaffolding is this command's job: it creates its destination and any
# directory above it, and refuses an existing one without --force, as it always
# has. Only the two destinations that raised a traceback are refused by name.


@pytest.mark.parametrize("force", [False, True], ids=["plain", "force"])
@pytest.mark.parametrize("depth", [1, 2], ids=["in-a-file", "deeper"])
def test_tutorial_init_refuses_a_destination_inside_a_file(
    tmp_path: Path, depth: int, *, force: bool
) -> None:
    """A path through a file has no directory to be made in: exit 2, by name."""
    a_file = tmp_path / "a_file"
    a_file.write_text("keep me")
    dest = a_file.joinpath(*["level-one"] * depth)

    result = runner.invoke(
        app,
        ["tutorial", "init", "level-1", "--dest", str(dest), *(["-f"] * force)],
    )

    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    said = _unwrapped(result.stderr)
    assert _needle(f"--dest names {dest}, which is inside {a_file}") in said
    assert _needle("a file rather than a directory, so nothing was written") in said
    assert a_file.read_text() == "keep me"


def test_tutorial_init_force_never_deletes_a_file(tmp_path: Path) -> None:
    """--force replaces a tutorial's directory; a file is refused, and kept."""
    a_file = tmp_path / "a_file"
    a_file.write_text("keep me")

    result = runner.invoke(
        app, ["tutorial", "init", "level-1", "--dest", str(a_file), "--force"]
    )

    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    said = _unwrapped(result.stderr)
    assert _needle(f"--dest names {a_file}, which is a file") in said
    assert _needle("--force replaces a tutorial's directory, never a file") in said
    assert a_file.read_text() == "keep me"


def test_tutorial_init_creates_the_directories_above_its_destination(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "work" / "tutorials" / "level-one"

    result = runner.invoke(app, ["tutorial", "init", "level-1", "--dest", str(dest)])

    assert result.exit_code == 0, result.output
    assert (dest / "model.py").exists()


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_tutorial_init_without_force_refuses_an_existing_destination_as_before(
    tmp_path: Path, kind: str
) -> None:
    dest = tmp_path / "level-one"
    if kind == "directory":
        dest.mkdir()
    else:
        dest.write_text("keep me")

    result = runner.invoke(app, ["tutorial", "init", "level-1", "--dest", str(dest)])

    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    assert _needle("Destination already exists") in _unwrapped(result.output)
    assert dest.exists()


def test_tutorial_init_force_replaces_a_copy_it_made(tmp_path: Path) -> None:
    """--force replaces a tutorial copy this command made, marker and all."""
    dest = tmp_path / "level-one"
    first = runner.invoke(app, ["tutorial", "init", "level-1", "--dest", str(dest)])
    assert first.exit_code == 0, first.output
    (dest / "old.txt").write_text("old")

    result = runner.invoke(
        app, ["tutorial", "init", "level-2", "--dest", str(dest), "--force"]
    )

    assert result.exit_code == 0, result.output
    assert (dest / "model.py").exists()
    assert (dest / ".gspio-tutorial").exists()
    assert not (dest / "old.txt").exists()


def test_tutorial_init_force_replaces_an_empty_directory(tmp_path: Path) -> None:
    dest = tmp_path / "level-one"
    dest.mkdir()

    result = runner.invoke(
        app, ["tutorial", "init", "level-1", "--dest", str(dest), "--force"]
    )

    assert result.exit_code == 0, result.output
    assert (dest / "model.py").exists()


def test_tutorial_init_force_never_deletes_a_directory_it_did_not_make(
    tmp_path: Path,
) -> None:
    """A directory of the user's own is refused by name, and kept whole."""
    dest = tmp_path / "my-project"
    (dest / "models").mkdir(parents=True)
    (dest / "models" / "reserve.py").write_text("keep me")
    (dest / "model.py").write_text("mine")

    result = runner.invoke(
        app, ["tutorial", "init", "level-1", "--dest", str(dest), "--force"]
    )

    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    said = _unwrapped(result.stderr)
    assert (
        _needle(f"--dest names {dest}, which gspio tutorial init did not make") in said
    )
    assert _needle("it holds model.py, models, and no .gspio-tutorial marker") in said
    assert (dest / "models" / "reserve.py").read_text() == "keep me"
    assert (dest / "model.py").read_text() == "mine"


def test_tutorial_init_force_never_deletes_a_repository(tmp_path: Path) -> None:
    """A copy that has become a repository keeps its history, marker or not."""
    dest = tmp_path / "level-one"
    assert (
        runner.invoke(
            app, ["tutorial", "init", "level-1", "--dest", str(dest)]
        ).exit_code
        == 0
    )
    (dest / ".git").mkdir()
    (dest / ".git" / "config").write_text("[core]")

    result = runner.invoke(
        app, ["tutorial", "init", "level-1", "--dest", str(dest), "--force"]
    )

    assert result.exit_code == 2, result.output
    assert _needle("which holds .git, a repository's history") in _unwrapped(
        result.stderr
    )
    assert (dest / ".git" / "config").read_text() == "[core]"


def test_tutorial_init_force_never_deletes_the_directory_it_runs_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--dest . names the working directory, which --force leaves alone."""
    dest = tmp_path / "level-one"
    assert (
        runner.invoke(
            app, ["tutorial", "init", "level-1", "--dest", str(dest)]
        ).exit_code
        == 0
    )
    (dest / "work").mkdir()
    (dest / "work" / "notes.txt").write_text("keep me")
    monkeypatch.chdir(dest / "work")

    for named in (".", ".."):
        result = runner.invoke(
            app, ["tutorial", "init", "level-1", "--dest", named, "--force"]
        )

        assert result.exit_code == 2, result.output
        assert _needle("which is the directory this command runs in") in _unwrapped(
            result.stderr
        )
    assert (dest / "work" / "notes.txt").read_text() == "keep me"
