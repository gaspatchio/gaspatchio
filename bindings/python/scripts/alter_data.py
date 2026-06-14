#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Script to rename columns in parquet files.
"""

from pathlib import Path
from typing import Optional

import polars as pl
import typer

app = typer.Typer(help="Rename columns in parquet files")


@app.command()
def rename_column(
    input_file: Path = typer.Argument(..., help="Input parquet file path"),
    old_name: str = typer.Argument(..., help="Current column name to rename"),
    new_name: str = typer.Argument(..., help="New column name"),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path (defaults to input file)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be changed without saving"
    ),
) -> None:
    """Rename a column in a parquet file."""

    # Validate input file exists
    if not input_file.exists():
        typer.echo(f"Error: Input file {input_file} does not exist", err=True)
        raise typer.Exit(1)

    # Set output file to input file if not specified
    if output_file is None:
        output_file = input_file

    try:
        # Load the parquet file
        typer.echo(f"Loading parquet file: {input_file}")
        df = pl.read_parquet(input_file)

        # Check if the column exists
        if old_name not in df.columns:
            typer.echo(f"Error: Column '{old_name}' not found in the file", err=True)
            typer.echo(f"Available columns: {', '.join(df.columns)}")
            raise typer.Exit(1)

        # Check if new name already exists
        if new_name in df.columns and new_name != old_name:
            typer.echo(
                f"Error: Column '{new_name}' already exists in the file", err=True
            )
            raise typer.Exit(1)

        # Show current schema
        typer.echo("\nCurrent schema:")
        for col, dtype in zip(df.columns, df.dtypes):
            marker = " -> " if col == old_name else "    "
            typer.echo(f"{marker}{col}: {dtype}")

        if dry_run:
            typer.echo(f"\n[DRY RUN] Would rename column '{old_name}' to '{new_name}'")
            typer.echo(f"[DRY RUN] Would save to: {output_file}")
            return

        # Rename the column
        df_renamed = df.rename({old_name: new_name})

        # Save the modified dataframe
        typer.echo(f"\nRenaming column '{old_name}' to '{new_name}'")
        df_renamed.write_parquet(output_file)

        typer.echo(f"✅ Successfully saved modified file to: {output_file}")
        typer.echo(f"Rows: {len(df_renamed)}, Columns: {len(df_renamed.columns)}")

    except Exception as e:
        typer.echo(f"Error processing file: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def inspect(
    file_path: Path = typer.Argument(..., help="Parquet file to inspect"),
    show_sample: bool = typer.Option(False, "--sample", help="Show first 5 rows"),
) -> None:
    """Inspect the schema and contents of a parquet file."""

    if not file_path.exists():
        typer.echo(f"Error: File {file_path} does not exist", err=True)
        raise typer.Exit(1)

    try:
        df = pl.read_parquet(file_path)

        typer.echo(f"File: {file_path}")
        typer.echo(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
        typer.echo("\nSchema:")

        for col, dtype in zip(df.columns, df.dtypes):
            typer.echo(f"  {col}: {dtype}")

        if show_sample and len(df) > 0:
            typer.echo("\nFirst 5 rows:")
            typer.echo(str(df.head()))

    except Exception as e:
        typer.echo(f"Error reading file: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
