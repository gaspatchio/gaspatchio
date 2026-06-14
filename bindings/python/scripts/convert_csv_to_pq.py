# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import polars as pl
import typer

app = typer.Typer()


def convert_file(file_path: Path) -> None:
    """Convert a single CSV file to Parquet format."""
    if not file_path.suffix.lower() == ".csv":
        typer.echo(f"Skipping {file_path}: not a CSV file")
        return

    output_path = file_path.with_suffix(".parquet")

    df = pl.read_csv(file_path, infer_schema_length=10000)
    df.write_parquet(output_path)
    typer.echo(f"✨ Converted {file_path} to {output_path}")


@app.command()
def convert(
    path: Path = typer.Argument(
        ..., help="Path to CSV file or directory containing CSV files", exists=True
    ),
):
    """Convert CSV file(s) to Parquet format."""
    if path.is_file():
        convert_file(path)
    elif path.is_dir():
        csv_files = list(path.glob("*.csv"))
        if not csv_files:
            typer.echo(f"No CSV files found in {path}")
            raise typer.Exit(1)

        for csv_file in csv_files:
            convert_file(csv_file)

        typer.echo(f"Converted {len(csv_files)} CSV files to Parquet format")
    else:
        typer.echo(f"Error: {path} is neither a valid file nor directory")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
