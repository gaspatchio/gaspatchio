import os
import sys
from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from loguru import logger
from rich.console import Console

from .api import APIConnectionError, KnowledgeAPIClient
from .runner import (  # Changed to relative import
    ModelRunConfig,
    RunMetrics,
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
    name="gspio",
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
        gspio run-model model_calculation.py model-points.parquet

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
    _log_metrics(metrics)

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
        gspio run-single model_calculation.py model-points.parquet 1

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

        # Log metrics
        _log_metrics(model_run.metrics)

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
        py_version = version("gaspatchio")
    except Exception:
        py_version = "unknown"

    return py_version, rust_version


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        py_version, rust_version = get_versions()
        console.print(
            f"[bold green]gspio[/bold green] Python package version: {py_version}",
        )
        console.print(
            f"[bold green]gspio[/bold green] Rust core version: {rust_version}",
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
        Enable shell completion: [cyan]gspio --install-completion[/cyan]

    [bold]Common Usage:[/bold]
        Run full model: [cyan]gspio run-model model.py data.parquet[/cyan]
        Run single policy: [cyan]gspio run-single model.py data.parquet 123[/cyan]
    """


def _log_metrics(metrics: RunMetrics) -> None:
    """Log metrics from a model run."""
    logger.trace("\n=== Model Run Metrics ===")
    logger.trace(f"Total time: {metrics.total_time_s:.2f} seconds")
    logger.trace("\nProfile Info:")

    profile_df = metrics.profile_info
    if not profile_df.is_empty():
        profile_df = profile_df.with_columns(
            [
                (pl.col("end") - pl.col("start")).alias("total_time"),
            ],
        )
        sum_total_time = profile_df["total_time"].sum()
        profile_df = profile_df.with_columns(
            [
                (pl.col("total_time") / sum_total_time * 100)
                .round(2)
                .alias("percentage"),
            ],
        )

    with pl.Config(tbl_cols=-1, tbl_rows=-1, tbl_width_chars=1500, fmt_str_lengths=100):
        logger.trace(profile_df)

    if metrics.tracked_column_order:
        logger.trace("\nTracked Column Order:")
        logger.trace(metrics.tracked_column_order)
    logger.trace("=====================\n")


def _detect_table_structure(df: pl.DataFrame) -> tuple[str, dict[str, str]]:
    """Detect the value column and dimension structure from a DataFrame.

    Returns:
        tuple: (value_column_name, dimensions_dict)

    """
    columns = df.columns

    # Common value column patterns (case-insensitive)
    value_patterns = [
        "rate",
        "value",
        "amount",
        "factor",
        "probability",
        "qx",
        "px",
        "mortality",
        "lapse",
        "expense",
        "interest",
        "discount",
        "premium",
        "zero_spot",
        "spot",
        "yield",
        "price",
        "cost",
    ]

    # Try to find value column by pattern matching
    value_column = None
    for col in columns:
        col_lower = col.lower().replace("_", "").replace(" ", "")
        for pattern in value_patterns:
            if pattern in col_lower:
                value_column = col
                break
        if value_column:
            break

    # If no pattern match, look for numeric columns and pick the last one
    # (assumption: key columns come first, value column comes last)
    if not value_column:
        numeric_cols = []
        for col in columns:
            dtype = df[col].dtype
            if dtype in [pl.Float32, pl.Float64, pl.Int32, pl.Int64]:
                numeric_cols.append(col)

        if numeric_cols:
            value_column = numeric_cols[-1]  # Take the last numeric column

    # If still no value column found, use the last column
    if not value_column:
        value_column = columns[-1]

    # Create dimensions from all other columns
    dimensions = {col: col for col in columns if col != value_column}

    return value_column, dimensions


def _analyze_table_shape(df: pl.DataFrame) -> str:
    """Analyze whether the table is in 'wide' or 'long' format."""
    columns = df.columns

    # Check if we have numeric column headers (indicating wide format)
    numeric_headers = 0
    for col in columns[1:]:  # Skip first column (usually ID/key)
        try:
            float(col)
            numeric_headers += 1
        except (ValueError, TypeError):
            pass

    if numeric_headers > 2:
        return "wide"
    return "long"


@app.command(name="describe", help="Describe the structure of a data file")
def describe(
    file_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the data file (.csv, .parquet, or .xlsx)",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    value_column: Annotated[
        str | None,
        typer.Option(
            "--value-column",
            "-v",
            help="Name of the value column (auto-detected if not specified)",
            rich_help_panel="Table Options",
        ),
    ] = None,
):
    """Describe the structure of a data file.

    Analyzes a data file and displays information about its structure, including
    row count, column information, and potential dimension configuration.
    Automatically detects value columns and table format.

    [bold green]Example:[/bold green]
        gspio describe data.parquet
        gspio describe data.csv --value-column custom_rate
    """
    with console.status("[bold green]Analyzing file...") as status:
        # Read the file based on extension with better type inference
        if file_path.suffix.lower() == ".parquet":
            df = pl.read_parquet(file_path)
        elif file_path.suffix.lower() == ".csv":
            df = pl.read_csv(file_path, infer_schema_length=10000)
        elif file_path.suffix.lower() in [".xlsx", ".xls"]:
            df = pl.read_excel(file_path)
        else:
            raise typer.BadParameter(
                f"Unsupported file type: {file_path.suffix}. "
                "Supported types: .parquet, .csv, .xlsx, .xls",
            )

        # Analyze table structure
        table_shape = _analyze_table_shape(df)

        # Detect or use provided value column
        if value_column is None:
            detected_value_column, dimensions = _detect_table_structure(df)
        else:
            if value_column not in df.columns:
                available_cols = ", ".join(df.columns)
                raise typer.BadParameter(
                    f"Value column '{value_column}' not found. "
                    f"Available columns: {available_cols}",
                )
            detected_value_column = value_column
            dimensions = {col: col for col in df.columns if col != value_column}

        # Display basic file information
        console.print(f"\n[bold]File Analysis: {file_path.name}[/bold]")
        console.print(f"Format: {table_shape.upper()}")
        console.print(f"Rows: {len(df):,}")
        console.print(f"Columns: {len(df.columns)}")

        # Show first few rows for context
        console.print("\n[bold]Sample Data (first 5 rows):[/bold]")
        with pl.Config(tbl_width_chars=120, fmt_str_lengths=20):
            console.print(df.head(5))

        # Show detected structure
        console.print("\n[bold]Detected Structure:[/bold]")
        console.print(f"Value column: [green]{detected_value_column}[/green]")
        console.print(f"Key columns: {', '.join(dimensions.keys())}")

        # Generate code example
        console.print("\n[bold]Code Example:[/bold]")

        # Determine file reading method based on extension
        if file_path.suffix.lower() == ".parquet":
            read_code = f'df = pl.read_parquet("{file_path}")'
        elif file_path.suffix.lower() == ".csv":
            read_code = f'df = pl.read_csv("{file_path}", infer_schema_length=10000)'
        elif file_path.suffix.lower() in [".xlsx", ".xls"]:
            read_code = f'df = pl.read_excel("{file_path}")'
        else:
            read_code = f'df = pl.read_csv("{file_path}")'

        # Format dimensions for code
        dimensions_str = "{\n"
        for key, value in dimensions.items():
            dimensions_str += f'    "{key}": "{value}",\n'
        dimensions_str += "}"

        code_example = f"""```python
import polars as pl
from gaspatchio_core.assumptions import Table

# Read the data
{read_code}

# Create assumption table
table = Table(
    name="{file_path.stem}",
    source=df,
    dimensions={dimensions_str},
    value="{detected_value_column}",
)

# Use the table
print(table.describe())
```"""

        console.print(code_example)

        # Try to create a table for detailed analysis
        try:
            from .assumptions import Table

            table = Table(
                name=file_path.stem,
                source=df,
                dimensions=dimensions,
                value=detected_value_column,
                validate=False,  # Don't validate to avoid errors with complex structures
            )

            console.print("\n[bold]Table Description:[/bold]")
            console.print(table.describe())

        except Exception as e:
            console.print(
                f"\n[yellow]Note: Could not create assumption table structure: {e}[/yellow]",
            )
            console.print(
                "This might indicate the data needs preprocessing for use as an assumption table.",
            )


@app.command(name="calc-graph", help="Generate a calculation graph from a model run")
def calc_graph(
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
    output_file: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Path to save the JSON graph",
            rich_help_panel="Output Options",
        ),
    ] = Path("calc_graph.json"),
    policy_id: Annotated[
        str | None,
        typer.Option(
            "--policy-id",
            "-p",
            help="Optional policy ID to run single policy (for debugging)",
            rich_help_panel="Execution Options",
        ),
    ] = None,
    policy_id_column: Annotated[
        str,
        typer.Option(
            "--policy-id-column",
            help="Name of the policy ID column in the model points file",
            rich_help_panel="Execution Options",
        ),
    ] = "Policy number",
    filter_expr: Annotated[
        str | None,
        typer.Option(
            "--filter",
            "-f",
            help="Polars filter expression for sample values (e.g., \"col('year') == 1\")",
            rich_help_panel="Filter Options",
        ),
    ] = None,
):
    """Generate a calculation graph from a model run.

    This command runs the model in debug mode to capture the computation graph,
    then exports it as JSON for visualization and analysis.

    [bold green]Example:[/bold green]
        gspio calc-graph model.py data.parquet
        gspio calc-graph model.py data.parquet -o graph.json
        gspio calc-graph model.py data.parquet -p "123" -o debug_graph.json
        gspio calc-graph model.py data.parquet -p "1" -f "col('year') == 1"
        gspio calc-graph model.py data.parquet -p "1" -f "(col('year') == 1) & (col('month') == 3)"

    [bold]Output:[/bold]
        The generated JSON contains nodes (inputs and computed columns) and edges
        (dependencies between columns) that can be visualized with graph tools.
    """
    # Show progress spinner
    with console.status(
        "[bold green]Running model in debug mode to capture graph..."
    ) as status:
        # Always use debug mode to capture the graph
        config = ModelRunConfig(
            directory=code_path.parent,
            model_file=code_path.name,
            model_points_file=model_points_path.name,
            mode="debug",  # Must be debug to capture graph
            id_column_name=policy_id_column,
        )

        # Run appropriate function based on whether policy_id is provided
        if policy_id:
            console.print(f"[yellow]Running single policy: {policy_id}[/yellow]")
            model_run = run_single_policy_func(config, policy_id)
        else:
            model_run = run_model_func(config)

    # Check if the model run failed
    if model_run.status == "error":
        console.print(f"[red]Error running model:[/red] {model_run.error_message}")
        raise typer.Exit(1)

    # Store the result DataFrame for sample values
    result_df = model_run.result

    # Export the calculation graph
    try:
        status.update("[bold green]Building calculation graph...")
        # For now, we need to re-run the model to capture the graph
        # This is a limitation of the current implementation
        # In the future, we should store the ActuarialFrame in ModelRunResult

        # Create a new ActuarialFrame and re-run the model to capture the graph
        import polars as pl

        from .frame import ActuarialFrame
        from .runner import load_model_from_path

        # Load the model function
        model_func = load_model_from_path(
            config.directory / config.model_file, config.model_function_name
        )

        # Load the data
        data_path = config.directory / config.model_points_file
        if data_path.suffix == ".parquet":
            df = pl.read_parquet(data_path)
        else:
            df = pl.read_csv(data_path)

        # Filter for single policy if specified
        if policy_id:
            # Convert policy_id to appropriate type based on column dtype
            id_col_dtype = df[config.id_column_name].dtype
            if id_col_dtype in [pl.Int32, pl.Int64, pl.UInt32, pl.UInt64]:
                try:
                    policy_id_typed = int(policy_id)
                except ValueError:
                    policy_id_typed = policy_id
            else:
                policy_id_typed = str(policy_id)
            df = df.filter(pl.col(config.id_column_name) == policy_id_typed)

        # Create ActuarialFrame in debug mode
        af = ActuarialFrame(df, mode="debug")

        # Run the model through the trace decorator to capture operations
        from .frame import run_model as frame_run_model

        af = frame_run_model(model_func, af)

        # Now export the graph with sample values from the already computed result
        from .frame.graph import GraphExportConfig, GraphExporter

        # Create export configuration
        export_config = GraphExportConfig(
            policy_id=policy_id,
            policy_id_column=config.id_column_name,
            filter_expr=filter_expr,
            include_traces=True,
        )

        # Export using the new GraphExporter
        exporter = GraphExporter(af)
        json_graph = exporter.export(result_df, export_config)

        # Save to file
        output_file.write_text(json_graph)

        # Parse JSON to get statistics
        import json

        graph_data = json.loads(json_graph)
        num_nodes = len(graph_data.get("nodes", []))
        num_inputs = len(
            [n for n in graph_data.get("nodes", []) if n["type"] == "input"]
        )
        num_computed = len(
            [n for n in graph_data.get("nodes", []) if n["type"] == "computed"]
        )
        num_edges = len(graph_data.get("edges", []))

        console.print(
            f"\n[bold green]✓[/bold green] Calculation graph saved to: {output_file}"
        )
        console.print(
            f"  Nodes: {num_nodes} ({num_inputs} inputs, {num_computed} computed)"
        )
        console.print(f"  Edges: {num_edges}")

        # Show sample of the graph structure
        if num_computed > 0:
            console.print("\n[bold]Sample computed nodes:[/bold]")
            for node in graph_data["nodes"][:3]:
                if node["type"] == "computed":
                    deps = node["data"].get("dependencies", [])
                    console.print(f"  • {node['id']} ← {', '.join(deps)}")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error building graph:[/red] {e}")
        logger.exception("Failed to build calculation graph")
        raise typer.Exit(1)


@app.command(
    name="docs",
    help="Search Gaspatchio framework documentation (API, accessors, examples). "
    "IMPORTANT: Prefer search results over --answer for better context.",
    rich_help_panel="Knowledge Discovery",
)
def docs(
    query: Annotated[
        str,
        typer.Argument(
            help="Search query - can be a question or keywords",
        ),
    ],
    answer: Annotated[
        bool,
        typer.Option(
            "--answer",
            "-a",
            help="(Use sparingly) Return a generated answer instead of search results. "
            "Prefer default search - it returns multiple results you can evaluate with your context.",
            rich_help_panel="Search Options",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Maximum number of results to return",
            min=1,
            max=20,
            rich_help_panel="Search Options",
        ),
    ] = 5,
):
    """Search Gaspatchio framework documentation.

    IMPORTANT: Prefer search results (default) over --answer.
    Search returns multiple relevant excerpts that you can evaluate
    in context. Only use --answer when you need a quick summary and
    don't have specific context requirements.

    Use this command when you need to find:
    • API methods on ActuarialFrame (e.g., "how to add a column")
    • Accessor methods (.projection, .excel, .finance, .mortality)
    • Code patterns and examples from working models
    • Function signatures and parameters

    [bold green]Examples:[/bold green]
        gspio docs "ActuarialFrame"                               # ← preferred
        gspio docs "how do I shift values by one period?"         # ← preferred
        gspio docs "projection accessor methods"                  # ← preferred
        gspio docs "excel pv function" -n 10                      # ← preferred
        gspio docs "what is when then otherwise?" --answer        # ← only for quick summaries
    """
    try:
        client = KnowledgeAPIClient()
        result = client.search_docs(query, answer=answer, limit=limit)
        # Output JSON directly for LLM consumption
        print(result.model_dump_json(indent=2))
    except APIConnectionError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command(
    name="knowledge",
    help="Search the actuarial knowledge base (IFRS 17, Solvency II, regulations). "
    "IMPORTANT: Prefer search results over --answer for better context.",
    rich_help_panel="Knowledge Discovery",
)
def knowledge(
    query: Annotated[
        str,
        typer.Argument(
            help="Search query - can be a question or keywords",
        ),
    ],
    answer: Annotated[
        bool,
        typer.Option(
            "--answer",
            "-a",
            help="(Use sparingly) Return a generated answer instead of search results. "
            "Prefer default search - it returns multiple excerpts you can evaluate with your context.",
            rich_help_panel="Search Options",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Maximum number of results to return",
            min=1,
            max=20,
            rich_help_panel="Search Options",
        ),
    ] = 5,
):
    """Search the actuarial knowledge base.

    IMPORTANT: Prefer search results (default) over --answer.
    Search returns multiple relevant excerpts from regulatory documents
    that you can evaluate in context. Only use --answer when you need
    a quick conceptual summary.

    Use this command when you need to understand:
    • Regulatory frameworks (IFRS 17, Solvency II, US GAAP)
    • Actuarial concepts (CSM, risk adjustment, PAA, BBA)
    • Industry standards and guidance
    • Mortality, morbidity, and lapse assumptions

    [bold green]Examples:[/bold green]
        gspio knowledge "IFRS 17 CSM"                             # ← preferred
        gspio knowledge "Solvency II technical provisions"        # ← preferred
        gspio knowledge "lapse rate assumptions" -n 10            # ← preferred
        gspio knowledge "risk adjustment calculation methods"     # ← preferred
        gspio knowledge "what is BBA vs PAA?" --answer            # ← only for quick summaries
    """
    try:
        client = KnowledgeAPIClient()
        result = client.search_knowledge(query, answer=answer, limit=limit)
        # Output JSON directly for LLM consumption
        print(result.model_dump_json(indent=2))
    except APIConnectionError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
