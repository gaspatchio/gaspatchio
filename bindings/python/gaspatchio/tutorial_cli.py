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
from rich.console import Console
from rich.table import Table

from .tutorials import get_tutorials_dir

console = Console()

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
        console.print(f"[red]No numbered scripts found in {pattern_dir}[/red]")
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
            console.print(f"[red]FAIL: {script.name}[/red]\n{result.stderr}")
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
        bool, typer.Option("--force", "-f", help="Overwrite destination if it exists")
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
        console.print(f"[red]Tutorial source not found: {source}[/red]")
        raise typer.Exit(code=1)

    dest_resolved = dest.resolve()

    if dest_resolved.exists() and not force:
        console.print(f"[red]Destination already exists: {dest_resolved}[/red]")
        console.print("Use --force to overwrite.")
        raise typer.Exit(code=1)

    if dest_resolved.exists() and force:
        shutil.rmtree(dest_resolved)

    shutil.copytree(source, dest_resolved, ignore=shutil.ignore_patterns("__pycache__"))
    console.print(f"[green]Tutorial copied to: {dest_resolved}[/green]\n")
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  cd {dest}")
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
        console.print(f"[red]Model failed to run:[/red]\n{result.stderr}")
        raise typer.Exit(code=1)

    actual = result.stdout.strip()

    if actual == expected:
        console.print(f"[green]PASS: {dir_name} output matches expected[/green]")
        raise typer.Exit(code=0)

    console.print(f"[red]FAIL: {dir_name} output does not match expected[/red]\n")
    console.print("[bold]Expected:[/bold]")
    console.print(expected)
    console.print("\n[bold]Actual:[/bold]")
    console.print(actual)
    raise typer.Exit(code=1)
