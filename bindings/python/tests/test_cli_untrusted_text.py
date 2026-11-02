# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A name out of someone else's file reaches the reader as text, never as an action.

``gspio describe`` and ``gspio graph`` print names a file supplied -- a
column of a model-point extract, a node id in an audit file, the file's own
name -- and ``describe`` writes them into Python a reader or an agent runs
next. Three things used to act on such a name instead of showing it:

* the suggested snippet, which pasted the name between quotes, so a name
  holding a quote closed the literal and ran what followed it;
* the terminal, which obeyed the escape sequences the name carried (a window
  title, a clipboard write, a line erased); and
* Rich markup, which made ``[link=...]`` a live link and raised
  ``MarkupError`` on ``[/bogus]``.

Each test below fails on the base these fixes were made against.
"""

from __future__ import annotations

import ast
import io
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from rich.console import Console
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio._shown import python_literal, shown, spelled, terminal_console
from gaspatchio.cli import app
from gaspatchio.engines import REGISTERED_ENGINES, register_engine
from gaspatchio.frame.graph import GraphExporter
from tests.engines.test_compare_results_files import MODEL_SRC, _TwinEngine

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

runner = CliRunner()

# A call that leaves a file behind if it ever runs.
_CANARY_DOUBLE = '__import__("pathlib").Path("CANARY").write_text("ran")'
_CANARY_SINGLE = "__import__('pathlib').Path('CANARY').write_text('ran')"

# Names that close the literal they are pasted into, then run the canary.
_LIST_COLUMN = f'x").list.len(), {_CANARY_DOUBLE}, pl.col("x'
_FILE_NAME = f'a" if {_CANARY_DOUBLE} else "a.parquet'
_KEY_SINGLE = f"k': {_CANARY_SINGLE}, # "
_KEY_DOUBLE = f'k": {_CANARY_DOUBLE}, # '

# What the terminal would act on: a window title (OSC 0), a clipboard write
# (OSC 52), an erased line, a C1 control introducer, and Rich markup.
_TERMINAL = (
    "rider\x1b]0;TITLE\x07\x1b]52;c;Q0xJUA==\x07\x1b[2K\x1b[1A\x9b"
    "[link=https://example.invalid/phish]docs[/link][bold green]FAKE-OK[/]"
)
_ACTING = ("\x1b", "\x07", "\x9b", "\r")


def _run_snippet(
    code: str, where: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Run a snippet the way a reader would, in ``where``; keep each expression's value.

    A bare expression statement -- ``df.select(...).head()`` -- is bound to
    ``_out_<n>`` so the test can see what the snippet read.
    """
    tree = ast.parse(code)
    outputs = 0
    for index, statement in enumerate(tree.body):
        if isinstance(statement, ast.Expr):
            outputs += 1
            target = ast.Name(id=f"_out_{outputs}", ctx=ast.Store())
            tree.body[index] = ast.Assign(targets=[target], value=statement.value)
    ast.fix_missing_locations(tree)
    monkeypatch.chdir(where)
    namespace: dict[str, Any] = {}
    exec(compile(tree, "suggested", "exec"), namespace)  # noqa: S102 -- running the snippet is the test
    return namespace


def _suggested(path: Path) -> str:
    """Return the snippet ``describe --json`` offers for ``path``."""
    result = runner.invoke(app, ["describe", str(path), "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)["suggested_code"]


def _console_snippet(path: Path) -> str:
    """Return the last Code Example ``describe`` prints for ``path``."""
    result = runner.invoke(app, ["describe", str(path)], terminal_width=400)
    assert result.exit_code == 0, result.output
    return result.stdout.rsplit("```python\n", 1)[1].split("\n```", 1)[0]


# --- the suggested snippet ----------------------------------------------------


def test_a_column_name_in_the_read_back_snippet_is_read_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The results-file snippet reads the hostile column, and runs nothing it names."""
    path = tmp_path / "inforce.parquet"
    pl.DataFrame(
        {
            "policy_id": ["a", "b"],
            _LIST_COLUMN: [[1.0, 2.0], [3.0]],
            "x": [[1.0], [2.0]],
        }
    ).write_parquet(path)

    namespace = _run_snippet(_suggested(path), tmp_path, monkeypatch)

    assert not (tmp_path / "CANARY").exists()
    lengths, exploded = namespace["_out_1"], namespace["_out_2"]
    assert lengths[f"{_LIST_COLUMN}_n_periods"].to_list() == [2, 1]
    assert exploded[_LIST_COLUMN].to_list() == [1.0, 2.0, 3.0]


@pytest.mark.parametrize(
    "frame",
    [
        pl.DataFrame({"policy_id": ["a"], "x": [[1.0]]}),
        pl.DataFrame(
            {
                "policy_id": ["a", "b"],
                "age": [40, 50],
                "sum_assured": [1e5, 2e5],
                "premium": [10.0, 20.0],
                "sex": ["M", "F"],
            }
        ),
    ],
    ids=["results", "model-points"],
)
def test_a_file_name_in_the_snippet_is_read_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frame: pl.DataFrame
) -> None:
    """A file named so as to close the literal is opened by that name."""
    path = tmp_path / _FILE_NAME
    frame.write_parquet(path)

    namespace = _run_snippet(_suggested(path), tmp_path, monkeypatch)

    assert not (tmp_path / "CANARY").exists()
    read = namespace["df"] if "df" in namespace else namespace["mp"]
    assert read.equals(frame)


def test_a_key_column_in_the_analysis_snippet_is_read_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``describe --json``'s Table(...) names the hostile key, and runs nothing."""
    path = tmp_path / "mort.parquet"
    frame = pl.DataFrame(
        {"age": [40, 41, 42], _KEY_SINGLE: ["a", "b", "c"], "rate": [0.1, 0.2, 0.3]}
    )
    frame.write_parquet(path)
    code = _suggested(path).replace('"path/to/your/data.csv"', repr(path.name))

    namespace = _run_snippet(code, tmp_path, monkeypatch)

    assert not (tmp_path / "CANARY").exists()
    af = ActuarialFrame(pl.DataFrame({"a": [41], "k": ["b"]}))
    af.r = namespace["table"].lookup(**{"age": af.a, _KEY_SINGLE: af.k})
    assert af.collect()["r"].to_list() == [0.2]


@pytest.mark.parametrize("hostile", ["key", "file"])
def test_the_console_table_snippet_reads_what_it_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hostile: str
) -> None:
    """The console's own Table(...) snippet names the file and its keys as literals."""
    key = _KEY_DOUBLE if hostile == "key" else "band"
    path = tmp_path / (_FILE_NAME if hostile == "file" else "mort.parquet")
    pl.DataFrame(
        {"age": [40, 41, 42], key: ["a", "b", "c"], "rate": [0.1, 0.2, 0.3]}
    ).write_parquet(path)

    namespace = _run_snippet(_console_snippet(path), tmp_path, monkeypatch)

    assert not (tmp_path / "CANARY").exists()
    assert set(namespace["table"].dimensions) == {"age", key}


# --- the terminal and Rich markup ---------------------------------------------


@pytest.fixture
def hostile_audit(tmp_path: Path) -> Path:
    """Return an honest export whose input column name carries escapes and markup."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1", "P2"],
                _TERMINAL: [1.0, 2.0],
                f"{_TERMINAL} unread": [0.0, 0.0],
            }
        )
    )
    af.doubled = af[_TERMINAL] * 2.0
    af.total = af.doubled + 1.0
    written = tmp_path / "audit.json"
    written.write_text(GraphExporter(af).export())
    return written


def _says_without_acting(text: str) -> None:
    """Assert ``text`` holds no character a terminal acts on, and shows the name.

    Compared with the console's own line breaks taken out, since where Rich
    folds a long name is the terminal's choice and not the message.
    """
    for character in _ACTING:
        assert character not in text, repr(character)
    unwrapped = "".join(text.split())
    assert "\\x1b]52;c;Q0xJUA==" in unwrapped
    assert "[link=https://example.invalid/phish]docs[/link]" in unwrapped


@pytest.mark.parametrize(
    "question",
    [
        ["unused"],
        ["dependents", _TERMINAL],
        ["precedents", "doubled"],
        ["trace", "total"],
        ["affected", _TERMINAL],
    ],
    ids=["unused", "dependents", "precedents", "trace", "affected"],
)
def test_graph_shows_a_hostile_name_without_obeying_it(
    hostile_audit: Path, question: list[str]
) -> None:
    """Every ``gspio graph`` answer that names the column spells it out."""
    result = runner.invoke(
        app,
        ["graph", question[0], str(hostile_audit), *question[1:]],
        terminal_width=400,
    )

    assert result.exit_code == 0, result.output
    _says_without_acting(result.stdout)


@pytest.mark.parametrize("shape", ["model-points", "results"])
def test_describe_shows_a_hostile_column_without_obeying_it(
    tmp_path: Path, shape: str
) -> None:
    """``describe`` prints a hostile column name, in the sample table and the lists."""
    path = tmp_path / "book.parquet"
    values = [[1.0, 2.0], [3.0, 4.0]] if shape == "results" else [1.0, 2.0]
    pl.DataFrame(
        {"policy_id": ["P1", "P2"], "age": [40, 50], _TERMINAL: values}
    ).write_parquet(path)

    result = runner.invoke(app, ["describe", str(path)], terminal_width=400)

    assert result.exit_code == 0, result.output
    for character in _ACTING:
        assert character not in result.stdout, repr(character)
    # The sample table shortens a long name; what it keeps is spelled out.
    assert "rider\\x1b]0;TITLE" in "".join(result.stdout.split())


@pytest.mark.parametrize(
    "frame",
    [
        pl.DataFrame({"policy_id": ["a"], "[/bogus]": [[1.0, 2.0]], "v": [[1.0]]}),
        pl.DataFrame({"age": [1, 2], "[/bogus]": [0.1, 0.2]}),
    ],
    ids=["per-period-column", "value-column"],
)
def test_describe_prints_a_closing_tag_as_text(
    tmp_path: Path, frame: pl.DataFrame
) -> None:
    """A column named ``[/bogus]`` used to raise MarkupError mid-command."""
    path = tmp_path / "file.parquet"
    frame.write_parquet(path)

    result = runner.invoke(app, ["describe", str(path)])

    assert result.exit_code == 0, result.output
    assert "[/bogus]" in result.stdout


# --- paths, messages and printed frames -------------------------------------

# A directory chain whose path, printed whole, is Rich markup: a link, a style,
# and a closing tag that matches nothing open, which raised MarkupError.
_DIRECTORIES = ("[link=x.invalid]docs[", "link][bold green]FAKE-OK[", "bogus]")
_AS_TEXT = "[link=x.invalid]docs[/link][bold green]FAKE-OK[/bogus]"


@pytest.fixture
def hostile_dir(tmp_path: Path) -> Path:
    """Return a directory whose path reads as markup when printed whole."""
    where = tmp_path.joinpath(*_DIRECTORIES)
    where.mkdir(parents=True)
    return where


@pytest.fixture
def twin() -> Iterator[None]:
    """Register an engine that runs the twin model, for one test."""
    engines = dict(REGISTERED_ENGINES)
    register_engine("twin", lambda: _TwinEngine(2.0))
    yield
    REGISTERED_ENGINES.clear()
    REGISTERED_ENGINES.update(engines)


@pytest.fixture
def model_and_book(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return the twin model, a book whose text cells drive a terminal, its artifact."""
    model = tmp_path / "model.py"
    model.write_text(MODEL_SRC)
    book = tmp_path / "book.parquet"
    pl.DataFrame(
        {
            "policy_id": ["P-1", "P-2"],
            "note": ["a\x1b]52;c;Q0xJUA==\x07", "b\x1b]0;TITLE\x07\x1b[2K"],
            "amount": [2.0, 3.0],
        }
    ).write_parquet(book)
    artifact = tmp_path / "artifact.json"
    made = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(book),
            "--profile",
            "executable",
            "-o",
            str(artifact),
        ],
    )
    assert made.exit_code == 0, made.output
    return model, book, artifact


def _prints_the_path(output: str) -> None:
    """Assert the hostile path reached the reader as the text it is."""
    assert "".join(_AS_TEXT.split()) in "".join(output.split())


@pytest.mark.parametrize(
    "command", ["calc-graph", "run-model", "run-single-policy", "run-artifact"]
)
def test_a_saved_line_prints_a_hostile_path_as_text(
    hostile_dir: Path,
    model_and_book: tuple[Path, Path, Path],
    twin: None,  # noqa: ARG001 -- the fixture registers the engine
    command: str,
) -> None:
    """``... saved to <path>`` raised MarkupError on a path that reads as markup."""
    model, book, artifact = model_and_book
    arguments = {
        "calc-graph": [
            *("calc-graph", model, book, "--profile", "executable"),
            *("-o", hostile_dir / "a.json", "--results", hostile_dir / "r.parquet"),
        ],
        "run-model": ["run-model", model, book, "--output-file", hostile_dir / "m"],
        "run-single-policy": [
            *("run-single-policy", model, book, "P-1"),
            *("--output-file", hostile_dir / "s.parquet"),
        ],
        "run-artifact": [
            *("run-artifact", artifact, book, "--engine", "twin"),
            *("-o", hostile_dir / "t.parquet"),
        ],
    }[command]

    result = runner.invoke(app, [str(one) for one in arguments], terminal_width=400)

    assert result.exit_code == 0, result.output
    _prints_the_path(result.output)


@pytest.mark.parametrize("case", ["book", "aggregators", "damaged-manifest"])
def test_a_read_error_prints_a_hostile_path_and_value_as_text(
    hostile_dir: Path,
    model_and_book: tuple[Path, Path, Path],
    twin: None,  # noqa: ARG001 -- the fixture registers the engine
    tmp_path: Path,
    case: str,
) -> None:
    """A file that does not read is named, with what it holds, as text: exit 2."""
    model, book, artifact = model_and_book
    unread = hostile_dir / "unread"
    if case == "book":
        unread.write_text("not a parquet file")
        arguments = ["run-artifact", artifact, unread, "--engine", "twin"]
    elif case == "aggregators":
        unread.write_text("{")
        arguments = ["run-artifact", artifact, book, "--engine", "twin"]
        arguments.extend(["--aggregate", unread])
    else:
        results = tmp_path / "results.parquet"
        made = runner.invoke(
            app, ["run-model", str(model), str(book), "--results", str(results)]
        )
        assert made.exit_code == 0, made.output
        # Beside the hostile directory rather than in it: Polars reads a path
        # holding '[' as a glob, so the member's own value is what is tested.
        damaged = tmp_path / "damaged.parquet"
        metadata = dict(pl.read_parquet_metadata(results))
        metadata["gaspatchio.scope"] = f'"{_AS_TEXT}"'
        pl.read_parquet(results).write_parquet(damaged, metadata=metadata)
        arguments = ["compare", artifact, results, damaged]

    result = runner.invoke(app, [str(one) for one in arguments], terminal_width=400)

    assert result.exit_code == 2, result.output
    _prints_the_path(result.output)


@pytest.mark.parametrize("command", ["run-model", "run-single-policy"])
def test_a_printed_frame_spells_what_its_text_cells_would_do_to_a_terminal(
    model_and_book: tuple[Path, Path, Path], command: str
) -> None:
    """The frame went to the terminal through print(), escape sequences and all."""
    model, book, _ = model_and_book
    arguments = [command, str(model), str(book)]
    if command == "run-single-policy":
        arguments.append("P-2")

    result = runner.invoke(app, arguments, terminal_width=400)

    assert result.exit_code == 0, result.output
    for character in _ACTING:
        assert character not in result.stdout, repr(character)
    assert "\\x1b" in result.stdout


def test_a_model_error_on_stderr_spells_a_name_s_control_characters(
    tmp_path: Path, model_and_book: tuple[Path, Path, Path]
) -> None:
    """A failing model's message names the column it read, escapes spelled."""
    _, book, _ = model_and_book
    model = tmp_path / "failing.py"
    model.write_text(
        "def main(af):\n"
        "    af.total = af['rider\\x1b]0;TITLE\\x07'] * 2\n"
        "    return af\n"
    )

    result = runner.invoke(app, ["run-model", str(model), str(book)])

    assert result.exit_code == 1
    for character in _ACTING:
        assert character not in result.stderr, repr(character)
    assert "rider\\x1b]0;TITLE" in result.stderr


# --- the helpers --------------------------------------------------------------


def test_the_helpers_leave_an_ordinary_name_as_it_was() -> None:
    """No output moves for a name holding nothing a reader's tools would act on."""
    for name in ("pv_net_cf", "Issue Age", "qx@2", "é", "rate (annual)"):
        assert spelled(name) == name
        assert python_literal(name) == f'"{name}"'
    assert shown("pv_net_cf") == "pv_net_cf"


@pytest.mark.parametrize(
    "name", ['a"b', "a'b", "a\"'b", "x\x1by", "line\nbreak", "\u202e", "\\"]
)
def test_a_python_literal_reads_back_as_the_name(name: str) -> None:
    assert ast.literal_eval(python_literal(name)) == name


def test_spelled_writes_each_control_as_python_does() -> None:
    assert spelled("a\x1b[2K\x07\r\n\t\x7f\x9b") == "a\\x1b[2K\\x07\\r\\n\\t\\x7f\\x9b"
    assert spelled("a\nb\x1b", lines=True) == "a\nb\\x1b"


def test_the_terminal_console_keeps_its_own_styling_and_spells_the_rest() -> None:
    """Rich's own escape codes reach a terminal; a name's never do."""
    console = Console(file=io.StringIO(), force_terminal=True, width=400)
    # The hook terminal_console() installs, on a console that is a terminal.
    console.push_render_hook(terminal_console()._render_hooks[0])  # noqa: SLF001

    console.print(f"[bold]ok[/bold] {shown(_TERMINAL)}", highlight=False)
    console.print(_TERMINAL, markup=False, highlight=False)
    written = console.file.getvalue()  # type: ignore[attr-defined]

    assert "\x1b[1mok" in written  # the console's own bold
    assert "\x1b]52" not in written
    assert "\x1b]0;" not in written
    assert "\x1b]8;" not in written  # no hyperlink was made
    assert "\\x1b]52;c;Q0xJUA==" in written
