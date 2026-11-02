# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Command-line utilities that parse, check and update docstring examples."""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer

# Assume these modules and classes will exist and be importable
from .parse import GaspatchioDocstringParser
from .validate import GaspatchioEvalExample

# Try to import pytest, handle if not available for basic commands
try:
    import pytest
except ImportError:
    pytest = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from .models import DocstringCodeExample, GaspatchioDocstring

app = typer.Typer(
    help=(
        "Gaspatchio Docstring Utilities.\n\nPolars DataFrame print formatting is "
        "now standardized for all docstring example checks (wide tables, no "
        "wrapping, long strings). This can be globally overridden by calling "
        "GaspatchioDocstringParser.set_polars_print_config(...) before running "
        "checks.\n\nCode block execution now supports multi-line blocks: the last "
        "line is evaluated if it's an expression, otherwise the whole block is "
        "executed."
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=False,
)

# The parameters more than one command declares, declared once. Defaults stay
# with each command.
_ROOT_DIR_ARGUMENT = typer.Argument(
    help="Root directory to scan. Ignored if --file is used.",
    exists=True,
    file_okay=False,
    dir_okay=True,
    readable=True,
    show_default=False,
)

# parse and run-print-check select their docstrings the same way.
_FILE_OPTION = typer.Option(
    "--file",
    help="Target a single Python file.",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    show_default=False,
)
_METHOD_OPTION = typer.Option(
    "--method",
    help=(
        "Target a specific method/function (e.g., 'ClassName.method'). "
        "Applied after file/dir parsing."
    ),
    show_default=False,
)

# lint and update hand the method on to pytest as its -k pattern.
_PYTEST_METHOD_OPTION = typer.Option(
    "--method",
    "-k",
    help="Target a specific method/function (pytest -k pattern).",
    show_default=False,
)


@app.command()
def parse(
    *,
    root_dir: Annotated[
        Path | None,
        typer.Argument(
            help="Root directory to scan for Python files. Ignored if --file is used.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            show_default=False,
        ),
    ] = None,
    target_file: Annotated[Path | None, _FILE_OPTION] = None,
    target_method: Annotated[str | None, _METHOD_OPTION] = None,
    output_file: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="JSON output file path. Prints to stdout if not provided.",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Parse Gaspatchio docstrings and output them as JSON."""
    if not root_dir and not target_file:
        typer.echo(
            typer.style(
                "Error: Either root_dir argument or --file option must be provided.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    parser = GaspatchioDocstringParser()
    docstrings: list[GaspatchioDocstring] = []

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
            f"Filtered {original_count} docstrings down to {len(docstrings)} "
            f"matching method '*{target_method}*' in {filter_target_name}"
        )

    docstrings_json = [d.model_dump() for d in docstrings]

    if not docstrings_json:
        typer.echo(
            typer.style(
                "No docstrings found or matched the criteria.", fg=typer.colors.YELLOW
            )
        )
        # Allow empty output if no docstrings are found: don't exit with an
        # error, just proceed to output empty if applicable.

    if output_file:
        with output_file.open("w") as f:
            json.dump(docstrings_json, f, indent=2)
        typer.echo(f"Docstrings saved to {output_file}")
    elif docstrings_json:  # Only print to stdout if there's something to print
        typer.echo(json.dumps(docstrings_json, indent=2))
    # If not output_file and not docstrings_json, nothing is printed, which is fine.


@app.command(name="run-print-check")
def run_print_check_command(
    *,
    root_dir: Annotated[Path | None, _ROOT_DIR_ARGUMENT] = None,
    target_file: Annotated[Path | None, _FILE_OPTION] = None,
    target_method: Annotated[str | None, _METHOD_OPTION] = None,
) -> None:
    """Parse and run execution checks (doctest & custom) for examples.

    Polars DataFrame print formatting is standardized (see app help).
    Code block execution supports multi-line blocks and last-line eval.
    """
    if not root_dir and not target_file:
        typer.echo(
            typer.style(
                "Error: Either root_dir argument or --file option must be provided.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    # --- BEGIN NEW LINTING STEP ---
    if pytest is None:
        typer.echo(
            typer.style(
                (
                    "Warning: pytest is not installed. Structural linting of "
                    "docstrings (e.g., for legacy formats) will be skipped."
                ),
                fg=typer.colors.YELLOW,
            )
        )
    else:
        path_to_check: str
        if target_file:
            path_to_check = str(target_file)
        elif root_dir:
            path_to_check = str(root_dir)
        else:
            # This case should ideally not be reached due to the initial check,
            # but as a safeguard:
            typer.echo(
                typer.style(
                    "Error: No target path specified for structural lint check.",
                    fg=typer.colors.RED,
                )
            )
            raise typer.Exit(code=1)

        typer.echo(
            typer.style(
                (
                    "\\n--- Running Structural Docstring Lint Check on: "
                    f"{path_to_check} ---"
                ),
                fg=typer.colors.BLUE,
                bold=True,
            )
        )
        lint_pytest_args: list[str] = [
            "-m",
            "gaspatchio_docstring_structure_check",  # Only structural checks
            path_to_check,
        ]
        if target_method:  # If a method is targeted, apply -k to the lint check as well
            typer.echo(
                f"Structural lint check focusing on method/context: '*{target_method}*'"
            )
            lint_pytest_args.extend(["-k", target_method])

        # Optionally, make pytest quieter if it passes, e.g., by adding "-q"
        # or "--tb=no"

        # pytest.main reports its failures, usage errors included, as an exit
        # code rather than by raising
        lint_exit_code = int(pytest.main(lint_pytest_args))

        if lint_exit_code == pytest.ExitCode.OK:
            typer.echo(
                typer.style("Structural lint checks passed.", fg=typer.colors.GREEN)
            )
        elif lint_exit_code == pytest.ExitCode.NO_TESTS_COLLECTED:
            typer.echo(
                typer.style(
                    (
                        "No items found for structural lint check (this is "
                        "usually OK if scope is narrow)."
                    ),
                    fg=typer.colors.YELLOW,
                )
            )
        else:
            typer.echo(
                typer.style(
                    (
                        "Structural docstring lint checks FAILED (e.g., legacy "
                        "'>>>' examples found or other issues). Pytest exited "
                        f"with code {lint_exit_code}. Review output above and "
                        "convert examples to Markdown format if necessary."
                    ),
                    fg=typer.colors.RED,
                    bold=True,
                )
            )
            raise typer.Exit(code=lint_exit_code)
    typer.echo(  # Add a blank line for separation before execution checks start
        ""
    )
    # --- END NEW LINTING STEP ---

    # Configure logging for the parser module to show DEBUG messages
    parser_logger = logging.getLogger("gaspatchio.examples.docstrings.parse")
    if not parser_logger.handlers:  # Add handler only if none are configured
        stream_handler = logging.StreamHandler()
        # Basic formatter, customize if needed
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        stream_handler.setFormatter(formatter)
        parser_logger.addHandler(stream_handler)
    parser_logger.setLevel(logging.DEBUG)

    parser = GaspatchioDocstringParser()
    parsed_docstrings: list[GaspatchioDocstring] = []

    if target_file:
        typer.echo(f"Checking examples in single file: {target_file}")
        parsed_docstrings = parser.process_file(target_file)
    elif root_dir:
        typer.echo(f"Checking examples in directory: {root_dir}")
        parsed_docstrings = parser.process_files(root_dir)

    if not parsed_docstrings:
        typer.echo(typer.style("No docstrings found to check.", fg=typer.colors.YELLOW))
        raise typer.Exit(code=0)

    all_examples: list[DocstringCodeExample] = []
    for docstring_obj in parsed_docstrings:
        all_examples.extend(docstring_obj.examples)

    typer.echo(
        "DEBUG: Total examples found by parser before any filtering: "
        f"{len(all_examples)}"
    )
    for i, ex in enumerate(all_examples):
        typer.echo(f"DEBUG: Example {i} object_context: {ex.object_context}")

    if target_method:
        original_count = len(all_examples)
        typer.echo(f"DEBUG: Filtering for method: '{target_method}'")
        # Filter based on the end of the object_context, to be more flexible
        # like pytest's -k often is for Class.method patterns.
        all_examples = [
            ex for ex in all_examples if ex.object_context.endswith(target_method)
        ]
        filter_target_name = str(target_file) if target_file else str(root_dir)
        typer.echo(
            f"Filtered {original_count} examples down to {len(all_examples)} "
            f"matching method '*{target_method}*' in {filter_target_name}"
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
    error_details: list[str] = []

    typer.echo(f"Found {len(all_examples)} examples to check.")

    for example in all_examples:
        total_examples_checked += 1
        global_vars: dict[str, Any] = {}  # Placeholder for future global context
        errors = eval_example_checker.check_example(example, global_vars=global_vars)
        if errors:
            total_errors_found += (
                1  # Count as one example with errors, not number of error messages
            )
            error_header = (
                f"Errors in {example.object_context} - Example "
                f"#{example.example_index} "
                f"(File: {example.raw_source_location[0]}, "
                f"Line: {example.raw_source_location[1]}):"
            )
            error_details.append(
                typer.style(error_header, fg=typer.colors.RED, bold=True)
            )
            error_details.extend(f"- {error_msg}" for error_msg in errors)
        else:
            pass  # Example passed

    if error_details:
        typer.echo("\\n--- Error Summary ---")
        for detail in error_details:
            typer.echo(detail)

    if total_errors_found > 0:
        summary_message = (
            f"\\nFound issues in {total_errors_found} out of "
            f"{total_examples_checked} examples checked."
        )
        typer.echo(typer.style(summary_message, fg=typer.colors.RED, bold=True))
        raise typer.Exit(code=1)
    summary_message = (
        f"\\nAll {total_examples_checked} examples checked passed execution checks."
    )
    typer.echo(typer.style(summary_message, fg=typer.colors.GREEN, bold=True))


@app.command()
def lint(
    *,
    root_dir: Annotated[Path | None, _ROOT_DIR_ARGUMENT] = None,
    target_file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            help="Target a single Python file for linting.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            show_default=False,
        ),
    ] = None,
    target_method: Annotated[str | None, _PYTEST_METHOD_OPTION] = None,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            "-x",
            help="Enable strict mode (pytest -x: stop on first failure).",
        ),
    ] = False,
) -> None:
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
                (
                    "Error: Either root_dir argument or --file option must be "
                    "provided for linting."
                ),
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

    pytest_args = [
        "-m",
        "gaspatchio_docstring_example or gaspatchio_docstring_structure_check",
        path_to_lint,
    ]
    if target_method:
        pytest_args.extend(["-k", target_method])
    if strict:
        pytest_args.append("-x")

    # pytest.main reports its failures as an exit code rather than by raising,
    # and the parser logs and skips a file it cannot read
    exit_code = int(pytest.main(pytest_args))

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

    if exit_code == pytest.ExitCode.OK:
        typer.echo(typer.style("Lint checks passed.", fg=typer.colors.GREEN, bold=True))
    elif exit_code == pytest.ExitCode.NO_TESTS_COLLECTED:
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
    *,
    root_dir: Annotated[Path | None, _ROOT_DIR_ARGUMENT] = None,
    target_file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            help="Target a single Python file for update.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            show_default=False,
        ),
    ] = None,
    target_method: Annotated[str | None, _PYTEST_METHOD_OPTION] = None,
) -> None:
    """Update Gaspatchio docstring example outputs in-place using pytest.

    Polars DataFrame print formatting is standardized (see app help).
    Code block execution supports multi-line blocks and last-line eval.
    """
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
                (
                    "Error: Either root_dir argument or --file option must be "
                    "provided for update."
                ),
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

    # pytest.main reports its failures as an exit code rather than by raising
    exit_code = int(pytest.main(pytest_args))

    if exit_code == pytest.ExitCode.OK:
        typer.echo(
            typer.style(
                "Docstring examples update process completed successfully.",
                fg=typer.colors.GREEN,
                bold=True,
            )
        )
    elif exit_code == pytest.ExitCode.NO_TESTS_COLLECTED:
        typer.echo(
            typer.style(
                "No docstring examples found to update.", fg=typer.colors.YELLOW
            )
        )
    else:
        typer.echo(
            typer.style(
                (
                    "Docstring examples update process failed or had issues. "
                    f"Pytest exited with code {exit_code}"
                ),
                fg=typer.colors.RED,
                bold=True,
            )
        )
        # For update, a non-zero exit might indicate test failures even if update
        # was attempted. Depending on desired behavior, may or may not raise
        # typer.Exit(code=exit_code). The spec implies raising an error if pytest
        # doesn't return OK or NO_TESTS_COLLECTED
        raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
