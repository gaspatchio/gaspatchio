import os
import shutil
from pathlib import Path

import typer

app = typer.Typer()

# List of files to dump (update with your actual files)
FILES_TO_DUMP = [
    Path(__file__).parent.parent / "gaspatchio_core/accessors/excel.py",
    Path(__file__).parent.parent / "tests/accessors/test_excel.py",
    Path(__file__).parent.parent.parent.parent / "ref/01-dsl/dsl-design.md",
    Path(__file__).parent.parent / "gaspatchio_core/frame/base.py",
    Path(__file__).parent.parent / "gaspatchio_core/registry.py",
    Path(__file__).parent.parent / "gaspatchio_core/column/column_proxy.py",
    Path(__file__).parent.parent / "gaspatchio_core/column/expression_proxy.py",
    Path(__file__).parent.parent / "gaspatchio_core/column/dispatch.py",
    Path(__file__).parent.parent.parent.parent.parent
    / "gaspatchio-models/models/my-model/model_calculation.py",
    Path(__file__).parent.parent / "gaspatchio_core/functions/vector.py",
    Path(__file__).parent.parent / "gaspatchio_core/runner.py",
]


@app.command()
def dump_docs(
    output_dir: Path = typer.Option(
        Path(os.path.expanduser("~/projects/temp/gs-files")),
        help="Directory to dump files to",
        exists=False,
        file_okay=False,
        dir_okay=True,
        writable=True,
    ),
):
    """Copy a set of files to the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if not FILES_TO_DUMP:
        typer.echo("FILES_TO_DUMP is empty. Add files to dump.")
        raise typer.Exit(1)
    for src in FILES_TO_DUMP:
        if not src.exists():
            typer.echo(f"[WARN] File not found: {src}")
            continue
        dest = output_dir / src.name
        shutil.copy2(src, dest)
        typer.echo(f"[OK] {src} -> {dest}")


if __name__ == "__main__":
    app()
