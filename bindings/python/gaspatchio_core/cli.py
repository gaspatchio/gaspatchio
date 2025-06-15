import os
import sys
from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from loguru import logger
from rich.console import Console

from .runner import (  # Changed to relative import
    ModelRunConfig,
    transpose_single_policy_result,
)
from .runner import (
    run_model as run_model_func,
)
from .runner import (
    run_single_policy as run_single_policy_func,
)

# Set default logging level to INFO
logger.remove()  # Remove default handler
logger.add(
    sys.stderr,
    level=os.environ.get("LOGURU_LEVEL", "INFO"),
)  # Add handler with level from env var

# Rich console for better output
console = Console()

app = typer.Typer(
    name="gprun",
    help="Gaspatchio CLI for running actuarial models with high performance",
    add_completion=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)


def validate_file_path(path: str) -> Path:
    """Validate that a file exists and return Path object."""
    p = Path(path)
    if not p.exists():
        raise typer.BadParameter(f"File not found: {path}")
    return p


def mode_complete() -> list[str]:
    """Autocomplete for execution modes."""
    return ["debug", "optimize"]


@app.command(name="run-model", help="Execute an actuarial model from a file")
def run_model(
    code_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the model code file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    model_points_path: Annotated[
        Path,
        typer.Argument(
            help="Path to model points file (.parquet or .csv)",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help="Execution mode: 'debug' or 'optimize'",
            autocompletion=mode_complete,
            rich_help_panel="Execution Options",
        ),
    ] = "debug",
    first_n: Annotated[
        int,
        typer.Option(
            "--first-n",
            "-f",
            help="Number of first columns to display",
            min=1,
            rich_help_panel="Display Options",
        ),
    ] = 5,
    last_n: Annotated[
        int,
        typer.Option(
            "--last-n",
            "-l",
            help="Number of last columns to display",
            min=1,
            rich_help_panel="Display Options",
        ),
    ] = 10,
    start_at: Annotated[
        int,
        typer.Option(
            "--start-at",
            "-s",
            help="Starting column index (0-based)",
            min=0,
            rich_help_panel="Display Options",
        ),
    ] = 0,
    rows: Annotated[
        int,
        typer.Option(
            "--rows",
            "-r",
            help="Number of rows to display",
            min=1,
            rich_help_panel="Display Options",
        ),
    ] = 15,
):
    """Execute an actuarial model from a file.

    [bold green]Example:[/bold green]
        gprun run-model model_calculation.py model-points.parquet

    [bold]Column display options:[/bold]
        -s: Start at column index (0-based)
        -f: Show first n columns (from start position if -s specified)
        -l: Show last n columns
    """
    # Show progress spinner
    with console.status("[bold green]Loading model and data...") as status:
        config = ModelRunConfig(
            directory=code_path.parent,
            model_file=code_path.name,
            model_points_file=model_points_path.name,
            mode=mode,
        )
    # Call the imported run_model directly
    model_run = run_model_func(config)

    # Check if the model run failed
    if model_run.status == "error":
        # Display the error message
        print(model_run.error_message, file=sys.stderr)
        sys.exit(1)

    # Apply column selection and display logic
    result_df = model_run.result
    metrics = model_run.metrics

    # Output metrics at TRACE level
    logger.trace("\n=== Model Run Metrics ===")
    logger.trace(f"Total time: {metrics.total_time_s:.2f} seconds")
    logger.trace("\nProfile Info:")
    with pl.Config(tbl_cols=-1, tbl_rows=-1, tbl_width_chars=1500, fmt_str_lengths=100):
        logger.trace(metrics.profile_info)
    if metrics.tracked_column_order:
        logger.trace("\nTracked Column Order:")
        logger.trace(metrics.tracked_column_order)
    logger.trace("=====================\n")

    # Determine column order - use tracked order from metrics if available
    tracked_column_order = (
        getattr(model_run.metrics, "tracked_column_order", None) or []
    )
    final_result_columns = result_df.columns

    # Use tracked order, but only columns that actually exist in the final df
    available_ordered_columns = [
        col for col in tracked_column_order if col in final_result_columns
    ]
    # Add any columns present in final df but not in tracked_order
    available_ordered_columns.extend(
        [col for col in final_result_columns if col not in available_ordered_columns],
    )

    # Calculate columns to print based on -s, -f and -l
    # Apply starting position if specified
    columns_from_start = (
        available_ordered_columns[start_at:]
        if start_at > 0
        else available_ordered_columns
    )

    # Get first n columns from the starting position
    first_cols = columns_from_start[:first_n]
    # Get last n columns from the original list (not affected by start_at)
    last_cols = available_ordered_columns[-last_n:]

    # Ensure columns are unique if first_n + last_n > total columns
    combined_unique_cols_set = set(first_cols)
    combined_unique_cols = first_cols + [
        col for col in last_cols if col not in combined_unique_cols_set
    ]

    # Ensure selected columns actually exist
    if not combined_unique_cols:
        final_cols_to_print = available_ordered_columns
    else:
        final_cols_to_print = [
            col for col in combined_unique_cols if col in result_df.columns
        ]

    # Configure Polars display and print
    with pl.Config(
        tbl_cols=-1,
        tbl_rows=rows,
        tbl_width_chars=1500,
        fmt_str_lengths=30,
    ):
        print("\nResult (Columns filtered by -f/-l):")
        if not final_cols_to_print:
            logger.warning(
                "No columns selected or available to display based on -f/-l settings.",
            )
            print(result_df)
        else:
            print(result_df.select(final_cols_to_print))


@app.command(
    name="run-single-policy",
    help="Execute an actuarial model for a single policy",
)
def run_single_policy(
    code_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the model code file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    model_points_path: Annotated[
        Path,
        typer.Argument(
            help="Path to model points file (.parquet or .csv)",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    policy_id: Annotated[str, typer.Argument(help="Policy ID to run the model for")],
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help="Execution mode: 'debug' or 'optimize'",
            autocompletion=mode_complete,
            rich_help_panel="Execution Options",
        ),
    ] = "debug",
    policy_id_column: Annotated[
        str,
        typer.Option(
            "--policy-id-column",
            help="Name of the policy ID column in the model points file",
            rich_help_panel="Execution Options",
        ),
    ] = "Policy number",
    first_n: Annotated[
        int,
        typer.Option(
            "--first-n",
            "-f",
            help="Number of first columns to display",
            min=1,
            rich_help_panel="Display Options",
        ),
    ] = 5,
    last_n: Annotated[
        int,
        typer.Option(
            "--last-n",
            "-l",
            help="Number of last columns to display",
            min=1,
            rich_help_panel="Display Options",
        ),
    ] = 10,
    start_at: Annotated[
        int,
        typer.Option(
            "--start-at",
            "-s",
            help="Starting column index (0-based)",
            min=0,
            rich_help_panel="Display Options",
        ),
    ] = 0,
    rows: Annotated[
        int,
        typer.Option(
            "--rows",
            "-r",
            help="Number of rows to display",
            min=1,
            rich_help_panel="Display Options",
        ),
    ] = 15,
):
    """Execute an actuarial model for a single policy ID.

    [bold green]Example:[/bold green]
        gprun run-single model_calculation.py model-points.parquet 1

    [bold]Column display options:[/bold]
        -s: Start at column index (0-based)
        -f: Show first n columns (from start position if -s specified)
        -l: Show last n columns
    """
    with console.status(
        f"[bold green]Loading model for policy {policy_id}...",
    ) as status:
        config = ModelRunConfig(
            directory=code_path.parent,
            model_file=code_path.name,
            model_points_file=model_points_path.name,
            mode=mode,
            id_column_name=policy_id_column,
        )
    # Call the imported run_single_policy
    model_run = run_single_policy_func(config, policy_id)

    # Check if the model run failed
    if model_run.status == "error":
        # Display the error message
        print(model_run.error_message, file=sys.stderr)
        sys.exit(1)

    if model_run.errors:
        logger.error(f"Errors occurred during single policy run: {model_run.errors}")
    elif model_run.result is not None and not model_run.result.is_empty():
        # Transpose and print the result for better visibility of list columns
        transposed_result = transpose_single_policy_result(model_run.result)

        # Use tracked column order from metrics if available, otherwise fall back to transposed columns
        tracked_column_order = (
            getattr(model_run.metrics, "tracked_column_order", None) or []
        )
        transposed_columns = transposed_result.columns

        # Use tracked order, but only columns that actually exist in the transposed result
        available_ordered_columns = [
            col for col in tracked_column_order if col in transposed_columns
        ]
        # Add any columns present in transposed result but not in tracked_order
        available_ordered_columns.extend(
            [col for col in transposed_columns if col not in available_ordered_columns],
        )

        # Calculate columns to print based on -s, -f and -l using the tracked order
        # Apply starting position if specified
        columns_from_start = (
            available_ordered_columns[start_at:]
            if start_at > 0
            else available_ordered_columns
        )

        # Get first n columns from the starting position
        first_transposed_cols = columns_from_start[:first_n]
        # Get last n columns from the original list (not affected by start_at)
        last_transposed_cols = available_ordered_columns[-last_n:]

        combined_transposed_set = set(first_transposed_cols)
        final_transposed_cols_to_print = first_transposed_cols + [
            col for col in last_transposed_cols if col not in combined_transposed_set
        ]

        # Configure Polars display and print
        with pl.Config(
            tbl_cols=-1,
            tbl_rows=rows,
            tbl_width_chars=1500,
            fmt_str_lengths=30,
        ):
            print("\nTransposed Result (Columns filtered by -f/-l):")
            if not final_transposed_cols_to_print:
                logger.warning(
                    "No columns selected or available to display based on -f/-l settings.",
                )
                print(transposed_result)
            else:
                print(transposed_result.select(final_transposed_cols_to_print))
    else:
        logger.warning("Single policy run completed but produced no result.")


def get_versions() -> tuple[str, str]:
    """Get both Python package and Rust core library versions."""
    from importlib.metadata import version

    from ._internal import __version__ as rust_version

    try:
        py_version = version("gaspatchio-core")
    except Exception:
        py_version = "unknown"

    return py_version, rust_version


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        py_version, rust_version = get_versions()
        console.print(
            f"[bold green]gprun[/bold green] Python package version: {py_version}",
        )
        console.print(
            f"[bold green]gprun[/bold green] Rust core version: {rust_version}",
        )
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
):
    """
    [bold green]Gaspatchio CLI[/bold green] - High-performance actuarial modeling

    Run actuarial models with Rust-powered performance and Python simplicity.

    [bold]Getting Started:[/bold]
        Enable shell completion: [cyan]gprun --install-completion[/cyan]

    [bold]Common Usage:[/bold]
        Run full model: [cyan]gprun run-model model.py data.parquet[/cyan]
        Run single policy: [cyan]gprun run-single model.py data.parquet 123[/cyan]
    """


if __name__ == "__main__":
    app()
