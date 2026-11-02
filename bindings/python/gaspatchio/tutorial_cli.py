# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""CLI subcommands for managing gaspatchio tutorials.

Provides list, init, and verify commands so users can get started
with tutorials regardless of how gaspatchio was installed.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ._shown import shown, terminal_console
from .tutorials import get_tutorials_dir

console = terminal_console()
err_console = terminal_console(stderr=True)

# A destination the copy cannot be made at is a usage error, the status every
# gspio command gives a path on its command line that it cannot use.
_EXIT_USAGE = 2

# The file every copy carries, saying this command made it. ``--force``
# deletes a directory only while this file is in it: the one directory it
# can know is a tutorial copy is one it wrote itself.
_MARKER = ".gspio-tutorial"

# How many of a refused directory's entries the refusal names.
_ENTRIES_NAMED = 3

tutorial_app = typer.Typer(
    name="tutorial",
    help="List, initialize, and verify gaspatchio tutorials.",
)

# Level metadata: (directory_name, short_description)
LEVELS: list[tuple[str, str]] = [
    (
        "level-1-hello-world",
        "Hello World — term life portfolio, column arithmetic, when/then",
    ),
    (
        "level-2-assumptions",
        "Assumptions — mortality/lapse table lookups, multi-dimension tables",
    ),
    (
        "level-3-mini-va",
        "Mini Variable Annuity — account values, guarantees, dynamic lapse",
    ),
    (
        "level-4-lifelib",
        "Reconciled Lifelib — production model reconciled to 0.0000% vs lifelib",
    ),
    (
        "level-5-scenarios",
        "Scenarios — parameter shocks, sensitivity analysis, stress testing",
    ),
]

# Pattern collections: (directory_name, short_description). Worked API patterns,
# not sequential levels — they live under patterns/, have no base/ subdirectory,
# and hold numbered self-asserting scripts instead of a single model.py.
PATTERNS: list[tuple[str, str]] = [
    (
        "patterns/rollforward-patterns",
        "Rollforward — stateful recursion: fund growth, GMDB ratchet, lapse stop",
    ),
]


def _is_pattern(dir_name: str) -> bool:
    """Return True if a resolved directory name is a pattern collection."""
    return dir_name.startswith("patterns/")


def _resolve_level(name: str) -> str:
    """Normalize a tutorial name to its directory name.

    Accepts 'level-1', '1', 'level-1-hello-world', a pattern collection name
    ('rollforward-patterns'), or its full path ('patterns/rollforward-patterns').

    Parameters
    ----------
    name : str
        User-provided tutorial identifier.

    Returns
    -------
    str
        The canonical directory name (e.g. 'level-1-hello-world' or
        'patterns/rollforward-patterns').

    Raises
    ------
    typer.BadParameter
        If the name cannot be resolved to a known tutorial.

    """
    # Exact match
    for dir_name, _ in LEVELS + PATTERNS:
        if name == dir_name:
            return dir_name

    # Pattern collections by bare name: 'rollforward-patterns'
    for dir_name, _ in PATTERNS:
        if dir_name == f"patterns/{name}":
            return dir_name

    # Short forms: 'level-1' or '1'
    stripped = name.removeprefix("level-")
    for dir_name, _ in LEVELS:
        if dir_name.startswith(f"level-{stripped}-"):
            return dir_name

    levels = ", ".join(f"level-{i + 1}" for i in range(len(LEVELS)))
    patterns = ", ".join(d.removeprefix("patterns/") for d, _ in PATTERNS)
    msg = f"Unknown tutorial: '{name}'. Available: {levels}, {patterns}"
    raise typer.BadParameter(msg)


def _verify_pattern(pattern_dir: Path) -> None:
    """Run every numbered script in a pattern collection.

    The scripts assert internally against closed-form or hand-computed
    expectations, so a clean exit is a real verification.

    Parameters
    ----------
    pattern_dir : Path
        The pattern collection directory (e.g. .../patterns/rollforward-patterns).

    Raises
    ------
    typer.Exit
        Code 1 if any script fails; code 0 after all scripts pass.

    """
    scripts = sorted(pattern_dir.glob("[0-9][0-9]_*.py"))
    if not scripts:
        console.print(f"[red]No numbered scripts found in {shown(pattern_dir)}[/red]")
        raise typer.Exit(code=1)

    for script in scripts:
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=str(pattern_dir),
            check=False,
        )
        if result.returncode != 0:
            console.print(
                f"[red]FAIL: {shown(script.name)}[/red]\n"
                f"{shown(result.stderr, lines=True)}"
            )
            raise typer.Exit(code=1)
        console.print(f"[green]PASS: {script.name}[/green]")

    raise typer.Exit(code=0)


@tutorial_app.command()
def list() -> None:  # noqa: A001
    """List available tutorial levels."""
    tutorials_dir = get_tutorials_dir()
    table = Table(title="Gaspatchio Tutorials")
    table.add_column("Level", style="cyan")
    table.add_column("Description")
    table.add_column("Status")

    for dir_name, description in LEVELS:
        level_dir = tutorials_dir / dir_name / "base"
        status = "[green]ready[/green]" if level_dir.exists() else "[red]missing[/red]"
        short_name = dir_name.split("-")[0] + "-" + dir_name.split("-")[1]
        table.add_row(short_name, description, status)

    for dir_name, description in PATTERNS:
        is_ready = (tutorials_dir / dir_name).exists()
        status = "[green]ready[/green]" if is_ready else "[red]missing[/red]"
        table.add_row(dir_name.removeprefix("patterns/"), description, status)

    console.print(table)
    console.print("\n[bold]Get started:[/bold] gspio tutorial init level-1")
    console.print(
        "[bold]API patterns:[/bold] gspio tutorial init rollforward-patterns\n"
    )


def _no_place_for_a_tutorial(dest: Path, resolved: Path, *, force: bool) -> str | None:
    """Return why a tutorial cannot be copied to ``dest``, or None where it can.

    A destination inside a file has no directory to be made in, and a file
    given with ``--force`` would be deleted as though it were a tutorial's
    directory. Both raised a traceback; every other destination is created,
    parents included, or refused for existing without ``--force``.
    """
    blocker = next((parent for parent in resolved.parents if parent.exists()), None)
    if blocker is not None and not blocker.is_dir():
        return (
            f"--dest names {dest}, which is inside {blocker}, a file rather "
            "than a directory, so nothing was written. Name a destination "
            "that is not inside a file."
        )
    if force and resolved.exists() and not resolved.is_dir():
        return (
            f"--dest names {dest}, which is a file, so nothing was written: "
            "--force replaces a tutorial's directory, never a file. Name a "
            "directory, or one that does not exist yet."
        )
    if force and resolved.is_dir():
        return _not_a_tutorial_copy(dest, resolved)
    return None


def _not_a_tutorial_copy(dest: Path, resolved: Path) -> str | None:
    """Return why ``--force`` must not delete the directory ``dest``, or None.

    ``--force`` deletes the destination before it copies, so it replaces a
    directory only where nothing can be lost by it: one that is empty, or a
    copy this command made, which carries the ``.gspio-tutorial`` marker it
    writes. Telling a tutorial copy apart by what it holds -- a ``model.py``
    and a ``data/`` -- would also match a model of the user's own. Even a
    marked copy is kept where it now holds ``.git``, a repository's history,
    or where it is the directory the command was run from, or holds it.
    """
    entries = sorted(entry.name for entry in resolved.iterdir())
    if not entries:
        return None
    kept = "so nothing was deleted or written"
    if ".git" in entries:
        return (
            f"--dest names {dest}, which holds .git, a repository's history, "
            f"{kept}: --force never replaces a repository. Name a new --dest."
        )
    here = Path.cwd().resolve()
    if resolved == here or resolved in here.parents:
        return (
            f"--dest names {dest}, which is the directory this command runs in "
            f"or holds it, {kept}. Name a new --dest."
        )
    if _MARKER not in entries:
        named = ", ".join(entries[:_ENTRIES_NAMED])
        more = len(entries) - _ENTRIES_NAMED
        held = f"{named} and {more} more" if more > 0 else named
        return (
            f"--dest names {dest}, which gspio tutorial init did not make: it "
            f"holds {held}, and no {_MARKER} marker, {kept}. --force replaces "
            "only an empty directory or a tutorial copy this command made. Name "
            f"a new --dest, or empty {dest} yourself if nothing in it is needed."
        )
    return None


@tutorial_app.command()
def init(
    level: Annotated[
        str,
        typer.Argument(
            help="Tutorial level (e.g. 'level-1', '1', 'level-1-hello-world')"
        ),
    ],
    dest: Annotated[
        Path,
        typer.Option("--dest", "-d", help="Destination directory"),
    ] = Path("my-first-model"),
    force: Annotated[  # noqa: FBT002
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Replace the destination if it is empty or a tutorial copy "
            "this command made; any other directory is refused",
        ),
    ] = False,
) -> None:
    """Copy a tutorial into your working directory."""
    dir_name = _resolve_level(level)
    tutorials_dir = get_tutorials_dir()
    # Levels copy their base/ variant; pattern collections are the directory.
    source = (
        tutorials_dir / dir_name
        if _is_pattern(dir_name)
        else tutorials_dir / dir_name / "base"
    )

    if not source.exists():
        console.print(f"[red]Tutorial source not found: {shown(source)}[/red]")
        raise typer.Exit(code=1)

    dest_resolved = dest.resolve()
    # Scaffolding is this command's job, so the destination and any directory
    # above it are created. Two destinations cannot be copied to at all, and
    # are refused by name rather than met with a traceback.
    refusal = _no_place_for_a_tutorial(dest, dest_resolved, force=force)
    if refusal is not None:
        err_console.print(f"[red]{shown(refusal)}[/red]")
        raise typer.Exit(code=_EXIT_USAGE)

    if dest_resolved.exists() and not force:
        console.print(f"[red]Destination already exists: {shown(dest_resolved)}[/red]")
        console.print(
            "Use --force to replace it, if it is empty or a copy this command made."
        )
        raise typer.Exit(code=1)

    # An empty directory is copied into rather than deleted and made again,
    # so a shell standing in it is still standing in it afterwards.
    if dest_resolved.exists() and force and any(dest_resolved.iterdir()):
        shutil.rmtree(dest_resolved)

    shutil.copytree(
        source,
        dest_resolved,
        ignore=shutil.ignore_patterns("__pycache__"),
        dirs_exist_ok=True,
    )
    (dest_resolved / _MARKER).write_text(
        f"Copied by gspio tutorial init {dir_name}. gspio tutorial init --force "
        "replaces this directory only while this file is in it.\n",
        encoding="utf-8",
    )
    console.print(f"[green]Tutorial copied to: {shown(dest_resolved)}[/green]\n")
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  cd {shown(dest)}")
    if _is_pattern(dir_name):
        scripts = sorted(source.glob("[0-9][0-9]_*.py"))
        first = f"uv run python {scripts[0].name}   # then " if scripts else ""
        console.print(f"  {first}see README.md\n")
    else:
        console.print("  uv run python model.py\n")


@tutorial_app.command()
def verify(
    level: Annotated[str, typer.Argument(help="Tutorial level to verify")],
) -> None:
    """Run a tutorial model and verify its output matches expected."""
    dir_name = _resolve_level(level)
    tutorials_dir = get_tutorials_dir()

    if _is_pattern(dir_name):
        _verify_pattern(tutorials_dir / dir_name)
        return

    base_dir = tutorials_dir / dir_name / "base"

    expected_file = base_dir / "expected_output.txt"
    if not expected_file.exists():
        console.print(f"[red]No expected_output.txt found for {dir_name}[/red]")
        raise typer.Exit(code=1)

    model_file = base_dir / "model.py"
    if not model_file.exists():
        console.print(f"[red]No model.py found for {dir_name}[/red]")
        raise typer.Exit(code=1)

    expected = expected_file.read_text().strip()

    result = subprocess.run(  # noqa: S603
        [sys.executable, str(model_file)],
        capture_output=True,
        text=True,
        cwd=str(base_dir),
        check=False,
    )

    if result.returncode != 0:
        console.print(
            f"[red]Model failed to run:[/red]\n{shown(result.stderr, lines=True)}"
        )
        raise typer.Exit(code=1)

    actual = result.stdout.strip()

    if actual == expected:
        console.print(f"[green]PASS: {dir_name} output matches expected[/green]")
        raise typer.Exit(code=0)

    console.print(f"[red]FAIL: {dir_name} output does not match expected[/red]\n")
    console.print("[bold]Expected:[/bold]")
    console.print(expected, markup=False, highlight=False)
    console.print("\n[bold]Actual:[/bold]")
    console.print(actual, markup=False, highlight=False)
    raise typer.Exit(code=1)
