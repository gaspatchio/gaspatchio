import json
from pathlib import Path
from typing import List, Optional, cast

import typer

from .models import DocstringCodeExample, GaspatchioDocstring

# Assume these modules and classes will exist and be importable
from .parse import GaspatchioDocstringParser
from .validate import GaspatchioEvalExample

# Try to import pytest, handle if not available for basic commands
try:
    import pytest
except ImportError:
    pytest = None  # type: ignore

app = typer.Typer(
    help="Gaspatchio Docstring Utilities.\n\nPolars DataFrame print formatting is now standardized for all docstring example checks (wide tables, no wrapping, long strings). This can be globally overridden by calling GaspatchioDocstringParser.set_polars_print_config(...) before running checks.\n\nCode block execution now supports multi-line blocks: the last line is evaluated if it's an expression, otherwise the whole block is executed.",
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=False,
)


@app.command()
def parse(
    root_dir: Optional[Path] = typer.Argument(
        None,
        help="Root directory to scan for Python files. Ignored if --file is used.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        show_default=False,
    ),
    target_file: Optional[Path] = typer.Option(
        None,
        "--file",
        help="Target a single Python file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        show_default=False,
    ),
    target_method: Optional[str] = typer.Option(
        None,
        "--method",
        help="Target a specific method/function (e.g., 'ClassName.method'). Applied after file/dir parsing.",
        show_default=False,
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--out",
        help="JSON output file path. Prints to stdout if not provided.",
        show_default=False,
    ),
):
    """Parses Gaspatchio docstrings and outputs them as JSON."""
    if not root_dir and not target_file:
        typer.echo(
            typer.style(
                "Error: Either root_dir argument or --file option must be provided.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    parser = GaspatchioDocstringParser()
    docstrings: List[GaspatchioDocstring] = []

    if target_file:
        typer.echo(f"Parsing single file: {target_file}")
        docstrings = parser.process_file(target_file)
    elif root_dir:  # root_dir is Optional, so check it
        typer.echo(f"Parsing directory: {root_dir}")
        docstrings = parser.process_files(root_dir)

    if target_method:
        original_count = len(docstrings)
        docstrings = [d for d in docstrings if target_method in d.object_path]
        filter_target_name = str(target_file) if target_file else str(root_dir)
        typer.echo(
            f"Filtered {original_count} docstrings down to {len(docstrings)} matching method '*{target_method}*' in {filter_target_name}"
        )

    docstrings_json = [d.model_dump() for d in docstrings]

    if not docstrings_json:
        typer.echo(
            typer.style(
                "No docstrings found or matched the criteria.", fg=typer.colors.YELLOW
            )
        )
        # Allow empty output if no docstrings are found, don't exit with error
        # raise typer.Exit(code=0) # No, just proceed to output empty if applicable

    if output_file:
        with open(output_file, "w") as f:
            json.dump(docstrings_json, f, indent=2)
        typer.echo(f"Docstrings saved to {output_file}")
    elif docstrings_json:  # Only print to stdout if there's something to print
        typer.echo(json.dumps(docstrings_json, indent=2))
    # If not output_file and not docstrings_json, nothing is printed, which is fine.


@app.command(name="run-print-check")
def run_print_check_command(
    root_dir: Optional[Path] = typer.Argument(
        None,
        help="Root directory to scan. Ignored if --file is used.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        show_default=False,
    ),
    target_file: Optional[Path] = typer.Option(
        None,
        "--file",
        help="Target a single Python file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        show_default=False,
    ),
    target_method: Optional[str] = typer.Option(
        None,
        "--method",
        help="Target a specific method/function (e.g., 'ClassName.method'). Applied after file/dir parsing.",
        show_default=False,
    ),
):
    """Parses and runs execution checks (doctest & custom) for examples.\n\nPolars DataFrame print formatting is standardized (see app help).\nCode block execution supports multi-line blocks and last-line eval.\n"""
    if not root_dir and not target_file:
        typer.echo(
            typer.style(
                "Error: Either root_dir argument or --file option must be provided.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    parser = GaspatchioDocstringParser()
    parsed_docstrings: List[GaspatchioDocstring] = []

    if target_file:
        typer.echo(f"Checking examples in single file: {target_file}")
        parsed_docstrings = parser.process_file(target_file)
    elif root_dir:
        typer.echo(f"Checking examples in directory: {root_dir}")
        parsed_docstrings = parser.process_files(root_dir)

    if not parsed_docstrings:
        typer.echo(typer.style("No docstrings found to check.", fg=typer.colors.YELLOW))
        raise typer.Exit(code=0)

    all_examples: List[DocstringCodeExample] = []
    for docstring_obj in parsed_docstrings:
        for example_obj in docstring_obj.examples:
            # Ensure parent_docstring is linked for context
            example_obj.parent_docstring = docstring_obj
            all_examples.append(example_obj)

    if target_method:
        original_count = len(all_examples)
        all_examples = [ex for ex in all_examples if target_method in ex.object_context]
        filter_target_name = str(target_file) if target_file else str(root_dir)
        typer.echo(
            f"Filtered {original_count} examples down to {len(all_examples)} matching method '*{target_method}*' in {filter_target_name}"
        )

    if not all_examples:
        typer.echo(
            typer.style(
                "No examples found or matched the criteria to check.",
                fg=typer.colors.YELLOW,
            )
        )
        raise typer.Exit(code=0)

    eval_example_checker = GaspatchioEvalExample(update_examples_mode=False)
    total_examples_checked = 0
    total_errors_found = 0
    error_details: List[str] = []

    typer.echo(f"Found {len(all_examples)} examples to check.")

    for example in all_examples:
        total_examples_checked += 1
        global_vars = {}  # Placeholder for future global context
        errors = eval_example_checker.check_example(example, global_vars=global_vars)
        if errors:
            total_errors_found += (
                1  # Count as one example with errors, not number of error messages
            )
            error_header = f"Errors in {example.object_context} - Example #{example.example_index} (File: {example.raw_source_location[0]}, Line: {example.raw_source_location[1]}):"
            error_details.append(
                typer.style(error_header, fg=typer.colors.RED, bold=True)
            )
            for error_msg in errors:
                error_details.append(f"- {error_msg}")
        else:
            pass  # Example passed

    if error_details:
        typer.echo("\\n--- Error Summary ---")
        for detail in error_details:
            typer.echo(detail)

    if total_errors_found > 0:
        summary_message = f"\\nFound issues in {total_errors_found} out of {total_examples_checked} examples checked."
        typer.echo(typer.style(summary_message, fg=typer.colors.RED, bold=True))
        raise typer.Exit(code=1)
    else:
        summary_message = (
            f"\\nAll {total_examples_checked} examples checked passed execution checks."
        )
        typer.echo(typer.style(summary_message, fg=typer.colors.GREEN, bold=True))


@app.command()
def lint(
    root_dir: Optional[Path] = typer.Argument(
        None,
        help="Root directory to scan. Ignored if --file is used.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        show_default=False,
    ),
    target_file: Optional[Path] = typer.Option(
        None,
        "--file",
        help="Target a single Python file for linting.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        show_default=False,
    ),
    target_method: Optional[str] = typer.Option(
        None,
        "--method",
        "-k",
        help="Target a specific method/function (pytest -k pattern).",
        show_default=False,
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        "-x",
        help="Enable strict mode (pytest -x: stop on first failure).",
    ),
):
    """Lints and validates Gaspatchio docstring examples using pytest."""
    if pytest is None:
        typer.echo(
            typer.style(
                "Error: pytest is not installed. Linting via pytest is unavailable.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    if not root_dir and not target_file:
        typer.echo(
            typer.style(
                "Error: Either root_dir argument or --file option must be provided for linting.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    path_to_lint = str(target_file) if target_file else str(root_dir)
    typer.echo(
        f"Running comprehensive lint and validation for examples in: {path_to_lint}"
    )
    if target_method:
        typer.echo(f"Focusing on method/context: '*{target_method}*'")

    pytest_args = ["-m", "gaspatchio_docstring_example", path_to_lint]
    if target_method:
        pytest_args.extend(["-k", target_method])
    if strict:
        pytest_args.append("-x")

    try:
        # Pytest expects list of strings. Cast to avoid mypy complaint if pytest is None (though guarded).
        exit_code_val = pytest.main(cast(List[str], pytest_args))
        # Map pytest.ExitCode enum to integer if necessary for typer.Exit
        exit_code = int(exit_code_val)

        # Print summary of examples linted
        parser = GaspatchioDocstringParser()
        if target_file:
            docstrings = parser.process_file(target_file)
        elif root_dir:
            docstrings = parser.process_files(root_dir)
        else:
            docstrings = []
        total_examples = sum(len(d.examples) for d in docstrings)
        typer.echo(f"Linted {total_examples} docstring example(s) successfully.")

    except Exception as e:  # pylint: disable=broad-except
        typer.echo(typer.style(f"Error invoking pytest: {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    if exit_code == 0:  # pytest.ExitCode.OK
        typer.echo(typer.style("Lint checks passed.", fg=typer.colors.GREEN, bold=True))
    elif exit_code == 5:  # pytest.ExitCode.NO_TESTS_COLLECTED
        typer.echo(
            typer.style("No docstring examples found to lint.", fg=typer.colors.YELLOW)
        )
    else:
        typer.echo(
            typer.style(
                f"Lint checks failed. Pytest exited with code {exit_code}",
                fg=typer.colors.RED,
                bold=True,
            )
        )
        raise typer.Exit(code=exit_code)


@app.command()
def update(
    root_dir: Optional[Path] = typer.Argument(
        None,
        help="Root directory to scan. Ignored if --file is used.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        show_default=False,
    ),
    target_file: Optional[Path] = typer.Option(
        None,
        "--file",
        help="Target a single Python file for update.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        show_default=False,
    ),
    target_method: Optional[str] = typer.Option(
        None,
        "--method",
        "-k",
        help="Target a specific method/function (pytest -k pattern).",
        show_default=False,
    ),
):
    """Updates Gaspatchio docstring example outputs in-place using pytest.\n\nPolars DataFrame print formatting is standardized (see app help).\nCode block execution supports multi-line blocks and last-line eval.\n"""
    if pytest is None:
        typer.echo(
            typer.style(
                "Error: pytest is not installed. Updating via pytest is unavailable.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    if not root_dir and not target_file:
        typer.echo(
            typer.style(
                "Error: Either root_dir argument or --file option must be provided for update.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    path_to_update = str(target_file) if target_file else str(root_dir)
    typer.echo(f"Running example updates for examples in: {path_to_update}")
    if target_method:
        typer.echo(f"Focusing on method/context: '*{target_method}*' for update")

    pytest_args = [
        "-m",
        "gaspatchio_docstring_example",
        "--gp-update-examples",
        path_to_update,
    ]
    if target_method:
        pytest_args.extend(["-k", target_method])

    try:
        exit_code_val = pytest.main(cast(List[str], pytest_args))
        exit_code = int(exit_code_val)
    except Exception as e:  # pylint: disable=broad-except
        typer.echo(
            typer.style(f"Error invoking pytest for update: {e}", fg=typer.colors.RED)
        )
        raise typer.Exit(code=1)

    if exit_code == 0:  # pytest.ExitCode.OK
        typer.echo(
            typer.style(
                "Docstring examples update process completed successfully.",
                fg=typer.colors.GREEN,
                bold=True,
            )
        )
    elif exit_code == 5:  # pytest.ExitCode.NO_TESTS_COLLECTED
        typer.echo(
            typer.style(
                "No docstring examples found to update.", fg=typer.colors.YELLOW
            )
        )
    else:
        typer.echo(
            typer.style(
                f"Docstring examples update process failed or had issues. Pytest exited with code {exit_code}",
                fg=typer.colors.RED,
                bold=True,
            )
        )
        # For update, a non-zero exit might indicate test failures even if update was attempted.
        # Depending on desired behavior, may or may not raise typer.Exit(code=exit_code)
        # The spec implies raising an error if pytest doesn't return OK or NO_TESTS_COLLECTED
        raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
