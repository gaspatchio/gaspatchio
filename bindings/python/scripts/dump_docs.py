# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
from pathlib import Path

import typer

app = typer.Typer()

# List of files to dump (update with your actual files)
FILES_TO_DUMP = [
    Path(__file__).parent.parent / "gaspatchio/accessors/excel.py",
    Path(__file__).parent.parent / "tests/accessors/test_excel.py",
    Path(__file__).parent.parent.parent.parent / "ref/01-dsl/dsl-design.md",
    Path(__file__).parent.parent / "gaspatchio/frame/base.py",
    Path(__file__).parent.parent / "gaspatchio/registry.py",
    Path(__file__).parent.parent / "gaspatchio/column/column_proxy.py",
    Path(__file__).parent.parent / "gaspatchio/column/expression_proxy.py",
    Path(__file__).parent.parent / "gaspatchio/column/dispatch.py",
    Path(__file__).parent.parent.parent.parent.parent
    / "gaspatchio-models/models/my-model/model_calculation.py",
    Path(__file__).parent.parent / "gaspatchio/functions/vector.py",
    Path(__file__).parent.parent / "gaspatchio/runner.py",
    Path(__file__).parent.parent.parent.parent / "ref/ARCHITECTURE_SUMMARY.md",
    Path(__file__).parent.parent / "README.md",
    Path(__file__).parent.parent / "gaspatchio/assumptions/_api.py",
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
