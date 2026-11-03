# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: CLI commands for the Gaspatchio actuarial modeling framework.
# ABOUTME: Provides model execution, data inspection, and knowledge discovery commands.
# ruff: noqa: T201, PLR0913, E501, F841, BLE001, FBT001, RSE102, D400, D415, C901, PLR0912, PLR0915, B904, FBT002
"""CLI commands for the Gaspatchio actuarial modeling framework."""

import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import get_close_matches
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Final, NoReturn, cast

import polars as pl
import typer
from dotenv import load_dotenv
from loguru import logger
from rich.markup import escape
from rich.padding import Padding
from rich.text import Text

from ._git_operand import (
    CommittedFile,
    CommittedFileError,
    is_git_operand,
    read_committed,
)
from ._internal import __version__ as rust_core_version
from ._lfs import LfsPointer, parse_lfs_pointer
from ._output_target import no_place_for_a_file
from ._shown import python_literal, shown, spelled, terminal_console
from ._table_inference import (
    CodeExamples,
    TableDescription,
    ValueColumnError,
    build_describe_response,
    describe_table,
)
from ._version import package_version
from .api import APIConnectionError, KnowledgeAPIClient, postprocess
from .assumptions import Table

# The seam. All of it is core -- importing it loads no engine's dependencies,
# which is the property the clean-process test holds the package to -- and it
# reaches the graph package this module already imports, so none of these is
# a lazy import waiting to happen.
from .engines import EngineBrokenError, EngineNotInstalledError, engine_named
from .engines.compare import compare_results
from .engines.protocol import ParquetSink, read_manifest, write_with_manifest
from .engines.reference import (
    _final_schema_manifest,
    _ManifestWithheldError,
    _reference_from_collection,
)
from .engines.report import EngineRefusal
from .errors.policy_locator import telling_the_policy_id_column
from .frame import run_model as frame_run_model
from .frame.base import _frame_over_the_book
from .frame.graph import (
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    diff_artifacts,
    node_accounting,
    validate_artifact,
    verify_artifact,
)
from .frame.graph._model_files import book_from_file, git_output
from .frame.graph.diff import (
    _formulas_said,
    _library_moved,
    _results_file_moved,
    _results_not_compared,
    results_file_recorded,
)
from .frame.graph.diff_results import recorded_results, roots_of, with_values
from .frame.graph.filter_handler import rows_the_filter_keeps
from .frame.graph.html_export import (
    WROTE_THE_ARTIFACT,
    WROTE_THE_REPORT,
    ViewerNotInstalledError,
    render_html,
)
from .frame.graph.policies import (
    PolicySelectionError,
    SelectedPolicy,
    refuse_over_the_ceiling,
    select_policies,
)
from .frame.graph.portfolio import PortfolioFold, PortfolioFoldError
from .frame.graph.row_identity import (
    pin_each_entry,
    stamp_the_book,
    without_the_stamp,
)
from .frame.graph.tiers import _census_of_document
from .frame.graph.xlsx_export import _NotOnTheAxisError, render_xlsx
from .graph_cli import graph_app
from .runner import (  # Changed to relative import
    _ID_COLUMN_CANDIDATES,
    ModelRunConfig,
    PolicyNotFoundError,
    RunMetrics,
    _model_failure_message,
    _resolve_id_column,
    load_model_from_path,
    transpose_single_policy_result,
)
from .runner import (
    run_model as run_model_func,
)
from .runner import (
    run_single_policy as run_single_policy_func,
)
from .scenarios._graph_export import (
    ScenarioDoorError,
    each_entry_names_its_scenario,
    open_the_script,
    run_the_plan,
    the_grid,
)
from .scenarios._portfolio_export import fold_the_book
from .scenarios._with_scenarios import scenario_axis_columns
from .tutorial_cli import tutorial_app
from .util import read_model_points

if TYPE_CHECKING:
    from loguru import Record

    from .engines.compare import CompareReport
    from .engines.protocol import Engine, NodeStatus, ResultManifest
    from .frame import ActuarialFrame
    from .frame.graph import (
        DiffReport,
        LineValues,
        TierCensus,
        ValidationReport,
        ValuesReport,
        VerificationReport,
    )
    from .runner import ModelRunResult

_MODEL_MODE_HELP = (
    "Diagnostics: debug traces and profiles; optimize skips profiling. "
    "Both run on Polars."
)

# Shared CLI parameter contracts; defaults stay with each command.
_FIRST_COLUMNS_OPTION = typer.Option(
    "--first-n",
    "-f",
    help="Number of first columns to display",
    min=1,
    rich_help_panel="Display Options",
)

_LAST_COLUMNS_OPTION = typer.Option(
    "--last-n",
    "-l",
    help="Number of last columns to display",
    min=1,
    rich_help_panel="Display Options",
)

_START_COLUMN_OPTION = typer.Option(
    "--start-at",
    "-s",
    help="Starting column index (0-based)",
    min=0,
    rich_help_panel="Display Options",
)

_DISPLAY_ROWS_OPTION = typer.Option(
    "--rows",
    "-r",
    help="Number of rows to display",
    min=1,
    rich_help_panel="Display Options",
)

_MODEL_RESULTS_OPTION = typer.Option(
    "--results",
    "--output-file",
    "-o",
    help="Save calculated values to Parquet instead of displaying the frame",
    rich_help_panel="Output Options",
)


class ConformanceProfile(StrEnum):
    """Which conformance profile an exported artifact claims for itself.

    ``audit`` is the envelope, the node record, the edges and the identity
    fields -- what a reviewer or a supervisor reads. ``executable`` is that
    same document with the calculation itself written onto it, which is what
    a second implementation would evaluate the model from.
    """

    AUDIT = "audit"
    EXECUTABLE = "executable"


# What the artifact commands say with their exit status, so that a pipeline
# step can branch on it. Zero is the quiet answer: the artifact conforms, or
# nothing moved. One is the command having an answer worth reading. Two is
# the command never reaching an answer at all -- an unreadable file, or two
# documents there is no way to compare -- which is not a verdict about a
# model and must not be read as one.
_EXIT_REPORTED = 1
_EXIT_UNREADABLE = 2

# What ``calc-graph`` says when the policies it was asked for are not a set of
# model points it can honestly carry: an id the book does not hold, a slice
# that lands on nothing, a column it cannot order the book by, a document over
# the ceiling -- and what ``run-single-policy`` says when its one policy
# cannot be found, for the same reason. Its own status rather than the general failure above, because
# nothing ran: the model never started, and a caller branching on the status
# should be able to tell "your command line named nothing" from "your model
# raised".
_EXIT_REFUSED_SELECTION = 3

# What ``compare`` says when the question could not be answered from the
# values in hand: a line that fails the reduced test with a read absent might
# still pass the full rule, and a required result no file carries is not
# agreement either. Its own status rather than 1, because a pipeline branching
# on "the two engines differ" must not branch the same way on "this comparison
# could not tell", which is a file to write with --every-node rather than a
# model to fix. ``verify`` says it for the same reason, where a check asked
# for has nothing recorded to check against: a results file the audit file
# names no digest for is not a results file that agrees.
_EXIT_INDETERMINATE = 4

# How many bytes a calculation-graph document may weigh before ``calc-graph``
# refuses to write it. Twenty-five mebibytes, and the guard is over the
# assembled document rather than over a count of policies because per-policy
# bytes vary by model -- a projection over 241 periods costs several times
# what one over 83 does. What it protects is whoever opens the file: a page
# that will not open is not made smaller by being on disk.
MAX_DOCUMENT_BYTES: Final[int] = 25 * 1024 * 1024

# Load .env file if present (before any env var reads)
load_dotenv()

# What a log message carries while a results manifest is being read. The export
# the manifest takes reports its progress as every export does, and a command
# whose output is the model's results prints none of it; a warning or an
# error still reaches the terminal.
_READING_A_MANIFEST: Final = "reading_a_results_manifest"
_WARNING_LEVEL: Final = logger.level("WARNING").no


def _reaches_the_terminal(message: "Record") -> bool:
    """Return whether a log message is printed, which is all of them but one kind."""
    return message["level"].no >= _WARNING_LEVEL or not message["extra"].get(
        _READING_A_MANIFEST
    )


# The command line is an application, so it turns on the package's own log
# records, which the package mutes when it is imported as a library.
logger.enable("gaspatchio")

# Set default logging level to INFO
logger.remove()  # Remove default handler
logger.add(
    sys.stderr,
    level=os.environ.get("LOGURU_LEVEL", "INFO"),
    filter=_reaches_the_terminal,
)  # Add handler with level from env var

# Rich console for better output. Both consoles spell out any control
# character in what they print, because most of what they print -- column
# names, node ids, policy ids, file names -- came out of a file someone else
# may have written, and an escape sequence in one would otherwise drive the
# reader's terminal.
console = terminal_console()
# Human-facing degradation notices go to stderr so stdout stays pure JSON
# for the agents that parse it. So does every refusal: stdout carries the
# command's own document and nothing else, with --json and without.
err_console = terminal_console(stderr=True)

# At or above this status the API answered but the endpoint itself failed —
# a different situation from an unreachable API (no status at all).
_HTTP_SERVER_ERROR = 500


def _answer_fallback_note(status_code: int) -> str:
    """Build the machine-readable note carried on a fallback search response."""
    return (
        f"answer synthesis unavailable (HTTP {status_code}); these are search "
        "results for the same query — retry --answer later"
    )


def _print_answer_fallback_notice(status_code: int) -> None:
    """Tell the human on stderr that search results stand in for the answer."""
    err_console.print(
        f"[yellow]Answer synthesis is unavailable[/yellow] (HTTP {status_code} "
        "from the API). Search still works — showing search results for the "
        "same query instead."
    )


app = typer.Typer(
    name="gspio",
    help="""Gaspatchio CLI for running actuarial models and discovering knowledge.

This CLI serves three purposes:
1. Execute actuarial models (run-model, run-single-policy)
2. Audit a run from the file it writes (calc-graph, verify, diff, graph,
   sheet, compare, validate)
3. Search documentation and actuarial knowledge (docs, knowledge)

[bold]When building a model and you need to find:[/bold]
• How to use a Gaspatchio feature → [cyan]gspio docs "your question"[/cyan]
• Actuarial concepts or regulations → [cyan]gspio knowledge "your question"[/cyan]

[bold yellow]IMPORTANT: Always prefer search results (default) over \
--answer.[/bold yellow]
Search returns multiple excerpts you can evaluate against your
current context. Reserve --answer for quick summaries only when
you don't need to weigh multiple options.

[bold green]Examples:[/bold green]
    gspio docs "cumulative survival probability"              # ← preferred
    gspio docs "projection accessor methods"                  # ← preferred
    gspio docs "how do I shift time?" --answer                # ← only for summaries
    gspio knowledge "IFRS 17 contractual service margin"      # ← preferred
    gspio knowledge "what is risk adjustment?" --answer       # ← only for summaries
    gspio run-model model.py data.parquet --mode debug
    gspio run-single-policy model.py data.parquet "POL001"
""",
    add_completion=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)
app.add_typer(tutorial_app, name="tutorial")
app.add_typer(graph_app, name="graph", rich_help_panel="Audit")


def mode_complete() -> list[str]:
    """Autocomplete for execution modes."""
    return ["debug", "optimize"]


def _known_mode(value: str) -> str:
    """Refuse a ``--mode`` that is not one of the two, rather than run debug."""
    modes = mode_complete()
    if value in modes:
        return value
    close = get_close_matches(value, modes, n=1)
    hint = f" Did you mean {close[0]!r}?" if close else ""
    msg = (
        f"{value!r} is not a mode: the modes are 'debug' (traces and profiles) "
        f"and 'optimize' (skips profiling), and both give the same numbers.{hint}"
    )
    raise typer.BadParameter(msg)


# The names a book's policy column is found under when none is given: the
# runner's own candidates, in its order, so that the help names what it reads.
_ID_CANDIDATES_HELP: Final = (
    f"{', '.join(_ID_COLUMN_CANDIDATES[:-1])} or {_ID_COLUMN_CANDIDATES[-1]}, "
    "the first the book carries, in any case"
)

# The option a results writer is told its rows' identity by. Repeatable, as
# compare's is: the policy column, then a scenario column, where the
# runner's own resolution would not find them.
_RECORDED_IDENTITY_OPTION = typer.Option(
    "--policy-id-column",
    help=(
        "The policy ID column the results file records as each row's "
        f"identity. Omitted: {_ID_CANDIDATES_HELP}; with none of them the "
        "results record no row identity. Give it again for a second column, "
        "such as a scenario's"
    ),
    rich_help_panel="Output Options",
)


@app.command(
    name="run-model",
    help="Execute an actuarial model from a file",
    rich_help_panel="Model Execution",
)
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
    every_node: Annotated[
        bool,
        typer.Option(
            "--every-node",
            help=(
                "Write every value-bearing node's column, by node id, with "
                "the result manifest in the file's metadata -- the reference "
                "side of gspio compare"
            ),
            rich_help_panel="Output Options",
        ),
    ] = False,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help=_MODEL_MODE_HELP,
            autocompletion=mode_complete,
            callback=_known_mode,
            rich_help_panel="Execution Options",
        ),
    ] = "debug",
    policy_id_column: Annotated[list[str] | None, _RECORDED_IDENTITY_OPTION] = None,
    first_n: Annotated[int, _FIRST_COLUMNS_OPTION] = 5,
    last_n: Annotated[int, _LAST_COLUMNS_OPTION] = 10,
    start_at: Annotated[int, _START_COLUMN_OPTION] = 0,
    rows: Annotated[int, _DISPLAY_ROWS_OPTION] = 15,
    output_file: Annotated[Path | None, _MODEL_RESULTS_OPTION] = None,
) -> None:
    """Execute an actuarial model from a file.

    [bold green]Example:[/bold green]
        gspio run-model model_calculation.py model-points.parquet

    [bold]Column display options:[/bold]
        -s: Start at column index (0-based)
        -f: Show first n columns (from start position if -s specified)
        -l: Show last n columns
    """
    # The results go into a directory that is there, checked before the model
    # runs rather than after it has.
    _refuse_an_output_with_no_place(("--results", output_file))
    # Show progress spinner
    with console.status("[bold green]Loading model and data..."):
        config = ModelRunConfig(
            directory=code_path.parent,
            model_file=code_path.name,
            model_points_file=str(model_points_path),
            mode=mode,  # type: ignore[arg-type]
            # The first identity column names a policy a refusal is about.
            id_column_name=policy_id_column[0] if policy_id_column else None,
        )
    # Call the imported run_model directly
    model_run = run_model_func(config)

    # Check if the model run failed
    if model_run.status == "error":
        # Display the error message
        print(spelled(str(model_run.error_message), lines=True), file=sys.stderr)
        sys.exit(1)

    # Apply column selection and display logic
    result_df = model_run.result
    metrics = model_run.metrics

    # Output metrics at TRACE level
    if metrics is not None:
        _log_metrics(metrics)

    # Ensure we have a result dataframe
    if result_df is None:
        logger.error("Model run completed but produced no result dataframe")
        sys.exit(1)

    if every_node:
        # Every value-bearing node under its node id, rather than the model's
        # own schema: a column written twice is two columns here, and a
        # compiled rollforward's balance is one, because that is what the
        # other side of a comparison needs in order to take a line's scale
        # from the values it reads.
        result_df = _every_node_result(model_run, output_file, policy_id_column or None)
        if output_file is not None:
            return

    # The results, with the manifest saying which model, which book and
    # which versions produced them -- or one line saying why there is none.
    if output_file is not None:
        _save_results(
            result_df,
            output_file,
            model_run.frame,
            book=model_points_path,
            told_id_column=policy_id_column or None,
        )
        console.print(f"[bold green]Results saved to {shown(output_file)}[/bold green]")
        return

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
            print(spelled(str(result_df), lines=True))
        else:
            print(spelled(str(result_df.select(final_cols_to_print)), lines=True))


# Why a results file went out without a manifest, where the run handed back
# no frame holding its calculation log: nothing then says which calculation
# made the columns, and a manifest naming a model would be a guess.
_NO_CALCULATION_LOG = (
    "the frame this run finished on holds no calculation log, so nothing can "
    "say which model produced these values. Build the columns on the frame "
    "main() is handed, or bring values back with "
    "ActuarialFrame(df, continue_from=af)."
)


def _columns_the_file_carries(path: Path) -> list[str]:
    """Return the model points file's columns, read the way the run read the file.

    The one fact about a run the finished frame cannot supply. A model that
    rebuilds its frame in setup comes back holding names the file never
    carried, and only a caller that read the file can tell those apart from
    the book's own. ``calc-graph`` hands its exporter the names of the file
    it read, so both commands fold a rebuilt frame alike. Both read the file
    through :func:`~gaspatchio.util.read_model_points`, so a CSV book's
    columns are typed alike by both -- inferred from its first 10,000 rows --
    and one book is one input to either command.
    """
    return read_model_points(path).collect_schema().names()


def _save_results(
    values: pl.DataFrame,
    path: Path,
    frame: "ActuarialFrame | None",
    *,
    book: Path | Sequence[str],
    told_id_column: str | Sequence[str] | None = None,
) -> GraphExporter | None:
    """Write the results with a manifest saying what produced them, or say why not.

    The manifest is what lets a results file answer "same model, same data,
    same library?" without being asked: the model's fingerprint, the book's
    digest and the versions, in the Parquet footer beside the columns the
    model wrote under their own names. Where the run cannot vouch for one of
    those -- a frame holding no calculation log, a graph that cannot state
    its fingerprint, a book the export could not digest -- the values are
    written as plain Parquet and one line says why. A file that claims
    nothing is honest; one that names the wrong model is not.

    **The values reach the disk whatever the manifest meets**, because they
    are the output of a run that may have taken an hour. Everything the
    manifest needs is read inside one guard, the book's columns included. A
    refusal the manifest step names keeps its plain line; anything else is a
    defect, so its line is red, names the exception, and the traceback goes
    to the log.

    Args:
        values: The results, exactly as they are written.
        path: Where they are written.
        frame: The frame the run finished on, or None where it handed back none.
        book: The model points file the run read, or the columns of it where
            the command has read the file already.
        told_id_column: The policy id column the command line named, if it
            named one; otherwise the runner's own resolution decides (see
            :func:`_the_row_identity`).

    Returns:
        The exporter the manifest was read through, for a command that goes
        on to write the audit file of the same run and should not take the
        book's digest twice; None where no exporter could be built.

    """
    exporter: GraphExporter | None = None
    try:
        exporter = _exporter_for_a_manifest(frame, book)
        with logger.contextualize(**{_READING_A_MANIFEST: True}):
            manifest = _final_schema_manifest(
                exporter,
                values,
                row_identity=_the_row_identity(values, told_id_column, _axis_of(frame)),
            )
    except _ManifestWithheldError as withheld:
        _save_without_a_manifest(values, path, str(withheld))
        return exporter
    except Exception as failed:  # the values are kept whatever the manifest meets
        values.write_parquet(path)
        said = " ".join(str(failed).split())
        err_console.print(
            "[red]Saved without a manifest: building it failed with "
            f"{type(failed).__name__}: {escape(said)}[/red]"
        )
        logger.opt(exception=failed).error(
            "The results manifest could not be built, and the results were "
            "written without one. The traceback says where it failed."
        )
        return exporter
    write_with_manifest(values, manifest, path)
    if told_id_column and manifest.row_identity is None:
        told = [told_id_column] if isinstance(told_id_column, str) else told_id_column
        console.print(f"[yellow]{escape(_no_identity_recorded(told))}[/yellow]")
    return exporter


def _exporter_for_a_manifest(
    frame: "ActuarialFrame | None", book: Path | Sequence[str]
) -> GraphExporter:
    """Return an exporter over the frame the run finished on, told the book's columns.

    Raises:
        _ManifestWithheldError: Where the run handed back no frame holding its
            calculation log, so no manifest could name the model.

    """
    if frame is None:
        raise _ManifestWithheldError(_NO_CALCULATION_LOG)
    columns = _columns_the_file_carries(book) if isinstance(book, Path) else list(book)
    try:
        return GraphExporter(frame, data_columns=columns)
    except ValueError as empty:
        raise _ManifestWithheldError(_NO_CALCULATION_LOG) from empty


def _the_row_identity(
    written: pl.DataFrame,
    told: str | Sequence[str] | None,
    axis: Sequence[str] = (),
) -> tuple[str, ...] | None:
    """Return the columns that name each row of the results once, as the run resolved them.

    The policy-id column is the one the runner resolves when it selects a
    policy: the column the command line named, else the first of the names
    it reads as a policy identifier (``policy_id``, ``point_id``, ...) and no
    other -- matched exactly and then ignoring case. Where that column names
    each row once, it is the identity. A scenario run names each policy once
    per scenario, so where the results carry a column the run records as its
    scenario axis -- ``axis``, read from the calculation log or the artifact,
    whatever the axis was called -- the policy column and that column
    together are the identity, again only where they name each row once.

    Two or more columns named on the command line are the identity as named,
    where they name each row once. Otherwise there is none, and the manifest
    says so: a comparison of the file then has to show that two files' rows
    are in one order before it pairs them by position, or be told the columns
    to pair them by.
    """
    named = [told] if isinstance(told, str) else list(told or [])
    if len(named) > 1:
        columns = [_column_named(written, one) for one in named]
        resolved = tuple(column for column in columns if column is not None)
        if len(resolved) != len(named):
            return None
        return _naming_each_row_once(written, [resolved])
    try:
        policy = _resolve_id_column(written.columns, named[0] if named else None)
    except PolicyNotFoundError:
        return None
    candidates = [(policy,)] + [
        (policy, column)
        for column in axis
        if column in written.columns and column != policy
    ]
    return _naming_each_row_once(written, candidates)


def _column_named(written: pl.DataFrame, told: str) -> str | None:
    """Return the column a name on the command line means: exact, then ignoring case."""
    if told in written.columns:
        return told
    return {column.lower(): column for column in written.columns}.get(told.lower())


def _naming_each_row_once(
    written: pl.DataFrame, candidates: Sequence[tuple[str, ...]]
) -> tuple[str, ...] | None:
    """Return the first of the candidate identities that names each row once."""
    for identity in candidates:
        if written.select(identity).unique().height == written.height:
            return identity
    return None


def _no_identity_recorded(told: Sequence[str]) -> str:
    """Return the line a writer prints where the columns it was told name no row once."""
    return (
        f"The results record no row identity: {', '.join(told)} did not "
        "name each row once, or is not one of the columns. A comparison of "
        "this file will ask for the columns to pair its rows on."
    )


def _injected_inputs(document: dict[str, Any]) -> tuple[str, ...]:
    """Return the columns an artifact records as handed to the model, not read from the book."""
    return tuple(
        str(node["column"])
        for node in document.get("nodes") or []
        if node.get("kind") == "input" and node.get("provenance") == "injected"
    )


def _axis_of(frame: "ActuarialFrame | None") -> tuple[str, ...]:
    """Return the scenario axis the frame's calculation log records, if any."""
    return () if frame is None else scenario_axis_columns(frame)


def _save_without_a_manifest(values: pl.DataFrame, path: Path, why: str) -> None:
    """Write the results as plain Parquet, and say in one line why there is no manifest."""
    values.write_parquet(path)
    console.print(f"[yellow]Saved without a manifest: {escape(why)}[/yellow]")


def _every_node_result(
    model_run: "ModelRunResult",
    output_file: Path | None,
    told_id_column: Sequence[str] | None = None,
) -> pl.DataFrame:
    """Return the run's every-node reference frame, writing it where asked.

    Node-to-column pairing reads the calculation log and the defensive
    snapshot that collection/profile already completed. Retained definitions
    belong to that same execution; no second full collection is needed. The
    row identity is resolved over the finished frame's own columns, as a
    final-schema results file's is, and travels into the file beside the
    nodes.
    """
    frame = model_run.frame
    if frame is None:
        err_console.print(
            "[red]This run did not hand back the frame it finished on, so "
            "there is no calculation log to bind node ids to columns.[/red]"
        )
        raise typer.Exit(_EXIT_UNREADABLE)

    finished = model_run.result
    identity = (
        None
        if finished is None
        else _the_row_identity(finished, told_id_column, _axis_of(frame))
    )
    if told_id_column and identity is None:
        console.print(
            f"[yellow]{escape(_no_identity_recorded(told_id_column))}[/yellow]"
        )
    reference, manifest = _reference_from_collection(
        frame, every_node=True, row_identity=identity
    )
    if output_file is not None:
        write_with_manifest(reference, manifest, output_file)
        console.print(
            f"[bold green]Results saved to {shown(output_file)}[/bold green] "
            f"({_counted(len(manifest.columns), 'node')}, every-node)"
        )
    return reference


@app.command(
    name="run-single-policy",
    help=(
        "Execute an actuarial model for a single policy.\n\n"
        "The policy runs alone; where the model reads across rows -- a share of "
        "the book's sum assured, a grid sized from the rows -- the whole book "
        "runs and the policy is selected from it, and the command says so.\n\n"
        "For a spreadsheet of one policy -- every column it computed, period "
        "by period, each with its formula -- run gspio calc-graph model.py "
        "data.parquet --policies id:ID --xlsx policy.xlsx"
    ),
    rich_help_panel="Model Execution",
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
            help=_MODEL_MODE_HELP,
            autocompletion=mode_complete,
            callback=_known_mode,
            rich_help_panel="Execution Options",
        ),
    ] = "debug",
    policy_id_column: Annotated[
        str | None,
        typer.Option(
            "--policy-id-column",
            help=(
                f"Name of the policy ID column. Omitted: {_ID_CANDIDATES_HELP}; "
                "a book keyed by another column is refused, naming these"
            ),
            rich_help_panel="Execution Options",
        ),
    ] = None,
    first_n: Annotated[int, _FIRST_COLUMNS_OPTION] = 5,
    last_n: Annotated[int, _LAST_COLUMNS_OPTION] = 10,
    start_at: Annotated[int, _START_COLUMN_OPTION] = 0,
    rows: Annotated[int, _DISPLAY_ROWS_OPTION] = 15,
    output_file: Annotated[Path | None, _MODEL_RESULTS_OPTION] = None,
) -> None:
    """Execute an actuarial model for a single policy ID.

    [bold green]Example:[/bold green]
        gspio run-single-policy model_calculation.py model-points.parquet 1

    [bold]Column display options:[/bold]
        -s: Start at column index (0-based)
        -f: Show first n columns (from start position if -s specified)
        -l: Show last n columns
    """
    _refuse_an_output_with_no_place(("--results", output_file))
    with console.status(
        f"[bold green]Loading model for policy {policy_id}...",
    ) as status:
        config = ModelRunConfig(
            directory=code_path.parent,
            model_file=code_path.name,
            model_points_file=str(model_points_path),
            mode=mode,  # type: ignore[arg-type]
            id_column_name=policy_id_column,
        )
    # Call the imported run_single_policy. A policy the book cannot be asked
    # for -- no identifier column, or an id the column does not hold -- is a
    # refusal of the command line, said as one sentence with the next move,
    # not a traceback through the runner: the model never started.
    try:
        model_run = run_single_policy_func(config, policy_id)
    except PolicyNotFoundError as refusal:
        err_console.print(f"[red]{escape(str(refusal))}[/red]")
        raise typer.Exit(_EXIT_REFUSED_SELECTION) from None

    # Check if the model run failed
    if model_run.status == "error":
        # Display the error message
        print(spelled(str(model_run.error_message), lines=True), file=sys.stderr)
        sys.exit(1)

    # The model read across rows, so the policy was selected from a run of
    # the whole book rather than run alone, and the command says so.
    if model_run.route is not None:
        console.print(f"[yellow]{escape(model_run.route)}.[/yellow]")

    if model_run.errors:
        logger.error(f"Errors occurred during single policy run: {model_run.errors}")
    elif model_run.result is not None and not model_run.result.is_empty():
        # One policy's results, with the manifest saying which model, which
        # book -- that policy's own rows -- and which versions produced them.
        if output_file is not None:
            _save_results(
                model_run.result,
                output_file,
                model_run.frame,
                book=model_points_path,
                told_id_column=policy_id_column,
            )
            console.print(
                f"[bold green]Results saved to {shown(output_file)}[/bold green]"
            )
            return

        # Transpose and print the result for better visibility of list columns
        transposed_result = transpose_single_policy_result(model_run.result)

        # Log metrics
        if model_run.metrics is not None:
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
                print(spelled(str(transposed_result), lines=True))
            else:
                print(
                    spelled(
                        str(transposed_result.select(final_transposed_cols_to_print)),
                        lines=True,
                    )
                )
    else:
        logger.warning("Single policy run completed but produced no result.")


def get_versions() -> tuple[str, str]:
    """Get both Python package and Rust core library versions."""
    return package_version(), rust_core_version


def version_callback(value: bool) -> None:
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
) -> None:
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


@app.command(
    name="describe",
    help="Describe the structure of a data file",
    rich_help_panel="Data Inspection",
)
def describe(
    file_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the data file (.csv, .parquet, or .xlsx)",
            # Checked by describe itself, so a file it cannot read is one
            # sentence and status 2 rather than a usage panel; and left as
            # typed, so a broken link can be named as the link it is.
            readable=False,
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
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Output structured JSON for LLM consumption",
            rich_help_panel="Output Options",
        ),
    ] = False,
) -> None:
    """Describe the structure of a data file.

    Analyzes a data file and displays information about its structure, including
    row count, column information, and potential dimension configuration.
    Automatically detects value columns and table format.

    A file it cannot read -- one that does not exist, a directory, an
    extension it has no reader for, a Git LFS pointer, or a file its reader
    refuses -- is answered with one sentence on stderr and exit status
    [bold]2[/bold].

    [bold green]Example:[/bold green]
        gspio describe data.parquet
        gspio describe data.csv --value-column custom_rate
        gspio describe data.parquet --json
    """
    df = _read_or_refuse(file_path)
    file_path = file_path.resolve()
    with console.status("[bold green]Analyzing file..."):
        try:
            description = describe_table(df, file_path, value_column)
        except ValueColumnError as exc:
            raise typer.BadParameter(spelled(str(exc))) from exc

        if json_output:
            response = build_describe_response(description, _code_examples(description))
            print(response.model_dump_json(indent=2))
            return

        _print_description(description)


# The extensions describe has a reader for, and what each says it read the
# file as when the read fails.
_DESCRIBE_READS_AS: Final = {
    ".parquet": "Parquet",
    ".csv": "CSV",
    ".xlsx": "an Excel workbook",
    ".xls": "an Excel workbook",
}

# A Git LFS pointer is under 1024 bytes, so a file's first 1024 are enough
# to recognise one.
_LFS_POINTER_BYTES: Final = 1024


def _read_or_refuse(file_path: Path) -> pl.DataFrame:
    """Read the file describe was given, or say in one sentence why not and stop.

    A file describe cannot read is not a finding about the file's contents,
    so it exits with the status the artifact commands give a file they
    cannot read, and the sentence goes to stderr: under ``--json`` stdout is
    a document or nothing. A read the reader itself refuses is answered for
    every way it can fail, with the reader's own reason, which is the
    diagnosis -- a traceback would put that reason on its last line.
    """
    refusal = _why_describe_cannot_read(file_path)
    if refusal is None:
        try:
            with console.status("[bold green]Reading file..."):
                return _read_data_file(file_path)
        except Exception as error:  # every way a read can fail, not a list of them
            # Polars writes its diagnosis as the first paragraph, and after a
            # blank line any advice about its own arguments, which a describe
            # caller cannot pass. A missing optional reader's paragraph is two
            # lines, the second the command that installs it, so the whole
            # paragraph is kept and read as one line.
            diagnosis = str(error).strip().split("\n\n", 1)[0]
            reason = " ".join(diagnosis.split()) or type(error).__name__
            read_as = _DESCRIBE_READS_AS[file_path.suffix.lower()]
            refusal = (
                # A missing reader's own words name the install command.
                f"{file_path.absolute()} could not be read as {read_as}: {reason}"
                if isinstance(error, ImportError)
                else f"{file_path.absolute()} could not be read as {read_as} "
                f"({reason}); re-export or re-download the file."
            )
    err_console.print(
        spelled(refusal), style="red", markup=False, highlight=False, soft_wrap=True
    )
    raise typer.Exit(_EXIT_UNREADABLE)


def _why_describe_cannot_read(file_path: Path) -> str | None:
    """Return why describe cannot read ``file_path`` before any reader runs, if it cannot.

    The path is named as typed, made absolute and not resolved, so a link is
    named as the link the user gave.
    """
    shown = file_path.absolute()
    return _why_no_data_file_is_named(file_path, shown) or _why_it_holds_no_data(
        file_path, shown
    )


def _why_no_data_file_is_named(file_path: Path, shown: Path) -> str | None:
    """Return why the path names no data file describe has a reader for, if it does not."""
    if file_path.is_symlink() and not file_path.exists():
        target = Path(os.path.normpath(shown.parent / file_path.readlink()))
        return (
            f"{shown} is a symbolic link to {target}, which does not exist; "
            "point the link at the data file, or name the file itself."
        )
    if not file_path.exists():
        return f"{shown} does not exist; check the path."
    if file_path.is_dir():
        return f"{shown} is a directory; name one data file inside it."
    if file_path.suffix.lower() not in _DESCRIBE_READS_AS:
        kind = (
            f"a {file_path.suffix} file"
            if file_path.suffix
            else "a file with no extension"
        )
        return (
            f"{shown} is {kind}, and describe reads .parquet, .csv, .xlsx and "
            ".xls files; convert it to one of those, or rename it if it is one."
        )
    return None


def _why_it_holds_no_data(file_path: Path, shown: Path) -> str | None:
    """Return why the file holds no data to read, if it cannot be opened or is a pointer.

    Its opening bytes are read once and handed to the Git LFS recogniser
    before any reader sees the file.
    """
    try:
        with file_path.open("rb") as handle:
            opening = handle.read(_LFS_POINTER_BYTES)
    except OSError as error:
        return (
            f"{shown} could not be opened ({error.strerror or error}); check "
            "that it is a file and that you have permission to read it."
        )
    pointer = parse_lfs_pointer(opening)
    if pointer is not None:
        return (
            f"{shown} is a Git LFS pointer to {pointer.size:,} bytes of data, not "
            "the data itself; run git lfs pull in the repository it came from "
            "to fetch it."
        )
    return None


def _read_data_file(file_path: Path) -> pl.DataFrame:
    """Read the file the user named, choosing the reader by its extension.

    The extension is one of those ``_DESCRIBE_READS_AS`` names: an Excel
    workbook is all that is left after Parquet and CSV.
    """
    if file_path.suffix.lower() == ".parquet":
        return pl.read_parquet(file_path)
    if file_path.suffix.lower() == ".csv":
        return pl.read_csv(file_path, infer_schema_length=10000)
    return pl.read_excel(file_path)


def _nested_read_back_example(file_path: Path, nested: list[str]) -> str:
    """Return a runnable snippet for reading a projection-output file back.

    Uses the file's *name*, not its resolved path: ``resolve_path=True`` on the
    CLI argument makes the absolute path long enough that Rich wraps it
    mid-statement, which produces syntactically invalid Python.

    A zero-column file has no nested columns either, so the explode line is
    omitted rather than indexing into an empty list.

    Every name is written as a Python string literal that reads back as that
    name (:func:`python_literal`): a column name or a file name holding a
    quote once closed the literal and ran whatever followed it.
    """
    lines = [
        "import polars as pl",
        "",
        f"df = pl.read_parquet({python_literal(file_path.name)})",
    ]
    if nested:
        lengths = ",\n    ".join(
            f"pl.col({python_literal(name)}).list.len()"
            f".alias({python_literal(f'{name}_n_periods')})"
            for name in nested
        )
        first = python_literal(nested[0])
        lines += [
            "",
            "# Per-period columns, one list per policy.",
            f"df.select(\n    {lengths}\n).head()",
            "",
            "# Explode one to inspect it period by period",
            f"df.select({first}).explode({first}).head(12)",
        ]
    return "\n".join(lines)


def _model_point_example(file_path: Path) -> str:
    """Return a runnable snippet for loading a model-point extract."""
    file_ext = file_path.suffix.lower()
    name = python_literal(file_path.name)
    if file_ext == ".parquet":
        read_fn = f"pl.read_parquet({name})"
    elif file_ext == ".csv":
        read_fn = f"pl.read_csv({name}, infer_schema_length=10000)"
    else:
        read_fn = f"pl.read_excel({name})"
    return (
        f"import polars as pl\n"
        f"from gaspatchio import ActuarialFrame\n\n"
        f"mp = {read_fn}\n"
        f"af = ActuarialFrame(mp)"
    )


def _code_examples(description: TableDescription) -> CodeExamples:
    """Build both snippets the payload might offer; the rules pick between them."""
    file_path = description.file_path
    nested = [detail.name for detail in description.list_columns]
    return CodeExamples(
        read_back=_nested_read_back_example(file_path, nested),
        model_points=_model_point_example(file_path),
    )


# One phrase per rule, used twice: on its own after "inferred:", and with
# "won" after it on the runner-up line. Two spellings of one rule would be two
# places to correct when a rule moves.
_VALUE_RULE_IN_WORDS: Final = {
    "wording": "the leftmost numeric column whose header names a rate",
    "dtype_and_position": "the last numeric column",
    "last_column": "the last column",
}


def _print_value_column_verdict(description: TableDescription) -> None:
    """Say what kind of name the value column just printed is, on every answer.

    The `--json` payload has always carried this as `value_column_source`; the
    console said nothing at all unless two columns tied, so a reader could not
    tell a column of their file from a name it will only have after a melt,
    and could not tell which of the three rules had answered. It is printed on
    every answer now, not only on a tie: "the rule that chose" is the thing a
    reader checks the guess against, and a guess nobody can check is the one
    that goes into a valuation unnoticed.

    Nothing is printed where there is no value column -- a model-point extract
    or a file with no table in it -- because those surfaces say so in their
    own words before reaching here.
    """
    if not description.resolved_value_column:
        return
    source = description.value_column_source
    if source == "declared":
        console.print("[dim]declared: the column you named with --value-column.[/dim]")
        return
    if source == "after_melt":
        melted = ", ".join(map(shown, description.melt_columns)) or "the wide columns"
        console.print(
            f"[dim]after melting: not a column of the file — it is the column "
            f"you will have once {melted} are melted into one.[/dim]",
            highlight=False,
        )
        return
    how = _VALUE_RULE_IN_WORDS.get(description.value_column_rule, "one was chosen")
    console.print(f"[dim]inferred: {how}.[/dim]")


def _print_model_point_verdict(description: TableDescription) -> None:
    """Say a file is a model-point extract, and offer the frame it loads into.

    No `Table(...)`, no value column and no key columns: this command used to
    offer all three for a model-point file, name a premium or an expense as
    the rate, key the table on the other twelve columns, and then fail to
    build the very table it had just printed. The `--json` payload has said
    `model_points` on these files all along.
    """
    console.print(
        "\n[yellow]This is a model-point extract: one row per policy, and no "
        "rate to look up.[/yellow]",
    )
    console.print("\n[bold]Code Example:[/bold]")
    _print_code(_model_point_example(description.file_path))


def _print_code(code: str) -> None:
    """Print a snippet for a reader to copy out and run, exactly as written.

    Code is not markup: a name the snippet carries as a string literal --
    ``"[/bogus]"`` is a legal column name -- would otherwise be read as a tag,
    and a long line wrapped by the console is no longer the statement it was.
    """
    console.print(
        f"```python\n{code}\n```", markup=False, highlight=False, soft_wrap=True
    )


def _print_value_column_ambiguity(description: TableDescription) -> None:
    """Say that the value column was a choice, where it was one.

    A rate grid split by sex and smoker status is the commonest shape in the
    book, and on `core/benches/fixtures/mortality.csv` this command used to
    print `Value column: FS` and key the table on the other three mortality
    rates without a word. `PRINCIPLES.md` asks for a clear statement naming
    the ambiguity and the fix rather than a silent pick, so the candidates and
    the flag are both named. Nothing is printed where the rule had one answer
    or the user declared the column.

    It says what the rule could not rule out, not that each column named could
    be the rate. A third of these lines name a column the `--json` payload of
    the same command calls a key — `duration` beside `mort_scalar` — and
    "duration could be the mortality scalar" is not something this command
    knows. The membership stays whatever the wording is: a numeric key that
    matches a rate wording is still in the running, and this line is the only
    thing that tells the reader it was.

    `core/benches/fixtures/lapse_rates.parquet` used to be the example here —
    the rule picked the String id column `lapse_id` over the `lapse_rate`
    beside it, and this line was all that said so. It is not an example any
    more: rule 1 only looks at numeric columns now, `lapse_rate` answers on
    its own, and there is no tie left on that file to report.
    """
    if not description.resolved_value_column:
        return
    if not description.value_column_is_ambiguous:
        return
    candidates = ", ".join(map(shown, description.value_column_candidates))
    how = _VALUE_RULE_IN_WORDS.get(description.value_column_rule, "one was chosen")
    console.print(
        f"[yellow]Guessed from the "
        f"{len(description.value_column_candidates)} columns the rule could "
        f"not rule out ({candidates}) — {how} won. It matches on headers and "
        f"dtypes, not on the data, so a key column can be among them. "
        f"Pass --value-column NAME to say which one it is.[/yellow]",
        highlight=False,
    )


def _print_description(description: TableDescription) -> None:
    """Print what was inferred about the file, for a person to read."""
    file_path = description.file_path
    df = description.frame

    # Display basic file information. Every name printed below came out of
    # the file, so each goes through `shown`: a column called `[/bogus]` once
    # raised MarkupError here, and one carrying `[link=...]` became a live link.
    console.print(
        f"\n[bold]File Analysis: {shown(file_path.name)}[/bold]", highlight=False
    )
    console.print(f"Format: {description.reported_shape.upper().replace('_', ' ')}")
    console.print(f"Rows: {len(df):,}")
    console.print(f"Columns: {len(df.columns)}")

    # Show first few rows for context
    console.print("\n[bold]Sample Data (first 5 rows):[/bold]")
    with pl.Config(tbl_width_chars=120, fmt_str_lengths=20):
        sample = str(df.head(5))
    console.print(spelled(sample, lines=True), markup=False, highlight=False)

    # Per-period columns first: the verdict has to arrive before the table
    # structure, or a reader scanning for "Value column" takes a value that
    # does not apply to this file and stops reading.
    if description.list_columns:
        console.print("\n[bold]Per-period Columns (projection output):[/bold]")
        for detail in description.list_columns:
            extent = (
                f"lengths {detail.min_length}-{detail.max_length}"
                if detail.max_length
                else "nested"
            )
            console.print(
                f"  [green]{shown(detail.name)}[/green]  "
                f"{shown(detail.inner_dtype)}  {extent}",
                highlight=False,
            )

    if description.is_projection_output:
        console.print(
            "\n[yellow]This file contains per-period columns, so it is "
            "projection output rather than an assumption table.[/yellow]",
        )
        if description.scalar_frame.width:
            console.print(
                f"Scalar columns present: "
                f"{', '.join(map(shown, description.scalar_frame.columns))}. "
                "Pass --value-column to describe them as a table anyway.",
                highlight=False,
            )
        # Stop rather than suggesting assumption-table code for a results
        # file: registration cannot succeed on nested dtypes.
        console.print("\n[bold]Code Example:[/bold]")
        nested = [detail.name for detail in description.list_columns]
        _print_code(_nested_read_back_example(file_path, nested))
        return

    if description.is_model_points:
        _print_model_point_verdict(description)
        return

    # Show detected structure. Every name here is the one `describe_table`
    # resolved, which is the one `--json` reports: the console used to answer
    # from `detect_table_structure` alone and disagree with the payload on 85
    # of this repository's 136 tracked data files.
    console.print("\n[bold]Detected Structure:[/bold]")
    console.print(
        f"Value column: [green]{shown(description.resolved_value_column)}[/green]",
        highlight=False,
    )
    _print_value_column_verdict(description)
    _print_value_column_ambiguity(description)
    console.print(
        f"Key columns: {', '.join(map(shown, description.dimensions))}",
        highlight=False,
    )

    # Generate code example
    console.print("\n[bold]Code Example:[/bold]")

    # A wide table's value column is the post-melt `value`, which no snippet
    # naming the file's own columns can hand to `Table(...)`. The analysis's
    # own suggestion is the one that melts, and it is what `--json` already
    # offers, so the two surfaces offer the same next move rather than the
    # console offering one that cannot run.
    if description.value_column_source == "after_melt":
        _print_code(description.analysis.suggest_table_config())
        return

    # Determine file reading method based on extension. Every name in the
    # snippet is a Python literal of the name, never the name pasted between
    # quotes, so a name holding a quote cannot end the string and run on.
    path = python_literal(str(file_path))
    if file_path.suffix.lower() == ".parquet":
        read_code = f"df = pl.read_parquet({path})"
    elif file_path.suffix.lower() == ".csv":
        read_code = f"df = pl.read_csv({path}, infer_schema_length=10000)"
    elif file_path.suffix.lower() in [".xlsx", ".xls"]:
        read_code = f"df = pl.read_excel({path})"
    else:
        read_code = f"df = pl.read_csv({path})"

    # Format dimensions for code
    dimensions_str = "{\n"
    for key, value in description.dimensions.items():
        dimensions_str += f"    {python_literal(key)}: {python_literal(value)},\n"
    dimensions_str += "}"

    code_example = f"""import polars as pl
from gaspatchio.assumptions import Table

# Read the data
{read_code}

# Create assumption table
table = Table(
    name={python_literal(file_path.stem)},
    source=df,
    dimensions={dimensions_str},
    value={python_literal(description.resolved_value_column)},
)

# Use the table
print(table.describe())"""

    _print_code(code_example)

    # Try to create a table for detailed analysis. Unreachable for files
    # with list columns — those return above, because registration cannot
    # succeed on List dtypes and letting it fail leaked a storage-layer
    # message that read like a data problem.
    try:
        table = Table(
            name=file_path.stem,
            source=df,
            dimensions=description.dimensions,
            value=description.resolved_value_column,
            validate=False,  # Don't validate to avoid errors with complex structures
        )

        console.print("\n[bold]Table Description:[/bold]")
        console.print(shown(table.describe(), lines=True), highlight=False)

    except Exception as e:
        console.print(
            "\n[yellow]Note: Could not create assumption table structure: "
            f"{shown(e, lines=True)}[/yellow]",
        )
        console.print(
            "This might indicate the data needs preprocessing for use as an assumption table.",
        )


def _announce_the_axis(selection: Sequence[SelectedPolicy]) -> None:
    """Say which model points this run will carry values for, before it starts.

    A run over a book of a thousand takes long enough that being told
    afterwards which single row it sampled is being told too late. One
    policy gets the sentence it always got -- the first row is where the
    data happened to put it, not a policy anybody chose -- and several get
    their count and the reason the first of them is there, which is the
    reason the rest are there too.

    The model runs the book either way, so nothing here says otherwise: a
    selection chooses what is sampled, not what is computed.
    """
    if len(selection) == 1:
        console.print(f"[yellow]One policy: {shown(selection[0].why)}.[/yellow]")
        return
    console.print(
        f"[yellow]{len(selection):,} policies, {shown(selection[0].why)} "
        "first.[/yellow]"
    )


def _the_runs_own_record(output_file: Path) -> Path:
    """Return where a scenario run's own record is written beside its artifact.

    ``<base>.run.audit.json``, where ``<base>`` is the artifact's name less
    its extension and less a trailing ``.audit``: ``model.audit.json`` and
    ``model.json`` both put the record at ``model.run.audit.json``. Appending
    ``.audit.json`` to the artifact's name, as the export did, gave an
    artifact named the way the docs name one a ``model.audit.audit.json``
    beside it. Nothing reads the record by this name: the artifact names it
    by path and digest.
    """
    base = output_file.name.removesuffix(output_file.suffix)
    base = base.removesuffix(".audit") or base
    return output_file.with_name(f"{base}.run.audit.json")


def _announce_the_folds(folds: Sequence[PortfolioFold]) -> None:
    """Say which folds of the book the document will carry, and over what.

    Said after the fold rather than before it, because unlike a selection a
    fold is not known until the accumulators have been resolved against the
    frame -- and unlike a selection it costs a second run of the model,
    which is the thing worth reporting. Each entry's own sentence is what is
    printed, so what the terminal says and what the document says are one
    sentence rather than two that usually agree.
    """
    for fold in folds:
        console.print(f"[yellow]Folded: {shown(fold.why)}.[/yellow]")


# How many calculations at one tier the tier line names before it says how
# many more there are. Enough to find the lines to read on a model that has
# a few; af.graph.tiers() holds every one of them.
_NAMED_AT_A_TIER: Final = 5


def _tier_line(census: "TierCensus") -> str:
    """Return the census as the one line the summary prints under the node count.

    Every tier is stated, a zero included, and the calculations at each tier
    other than ``core`` are named after its count -- the first five, and how
    many more beyond them. The ``core`` calculations are counted and never
    named: they are the ones a reader has no reason to go looking for.
    """
    stated = ", ".join(
        (
            f"{len(census.core)} core",
            _named_at("engine_native", census.engine_native),
            _named_at("opaque", census.opaque),
        )
    )
    return f"Calculations by tier: {stated}"


def _unaccounted_line(holes: list[dict[str, Any]]) -> str | None:
    """Return the line naming each column the document cannot account for.

    Each by name, with the reason the document gives it -- ``overwritten``,
    ``rebuilt`` or ``unrecorded`` -- the first five and how many more beyond
    them, as the tier line names its calculations. None where there are
    none, so a model that accounts for every column prints nothing here.
    """
    named = [
        f"{hole.get('column')} ({hole.get('reason')})"
        for hole in holes
        if isinstance(hole, dict)
    ]
    if not named:
        return None
    listed = ", ".join(named[:_NAMED_AT_A_TIER])
    beyond = len(named) - _NAMED_AT_A_TIER
    if beyond > 0:
        listed = f"{listed}, and {beyond} more"
    return f"Unaccounted for: {listed}"


def _named_at(tier: str, node_ids: tuple[str, ...]) -> str:
    """Return one tier's count, and the calculations at it where there are any."""
    count = f"{len(node_ids)} {tier}"
    if not node_ids:
        return count
    listed = ", ".join(node_ids[:_NAMED_AT_A_TIER])
    beyond = len(node_ids) - _NAMED_AT_A_TIER
    if beyond > 0:
        listed = f"{listed}, and {beyond} more"
    return f"{count} ({listed})"


def _refuse_an_output_with_no_place(*outputs: tuple[str, Path | None]) -> None:
    """Refuse, before anything is written, an output that has no place to go.

    ``gspio sheet -o report/policy.xlsx`` with no ``report/`` raised a
    ``FileNotFoundError`` traceback, ``run-model -o`` did so after the whole
    model had run, and ``calc-graph --xlsx`` did so after the artifact was
    already on disk, leaving half a run's files behind; an ``-o`` naming a
    directory failed the same ways. No command creates a directory for its
    output, so every output a command was given is checked here, before the
    model runs or a byte is written, and a missing directory, a directory
    that is a file, or a path that is itself a directory is a usage error,
    refused by the flag that named it (:func:`no_place_for_a_file`).
    """
    for flag, path in outputs:
        if path is None:
            continue
        why = no_place_for_a_file(flag, path)
        if why is not None:
            err_console.print(f"[red]{escape(why)}[/red]")
            raise typer.Exit(_EXIT_UNREADABLE)


@app.command(
    name="calc-graph",
    help="Generate a calculation graph from a model run",
    rich_help_panel="Audit",
)
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
            "--artifact",
            "--output",
            "-o",
            help="Save the calculation graph artifact as JSON",
            rich_help_panel="Output Options",
        ),
    ] = Path("calc_graph.json"),
    results_file: Annotated[
        Path | None,
        typer.Option(
            "--results",
            "--output-file",
            help=(
                "Also save the finished frame to this parquet file, and name "
                "it in the artifact by path and content hash"
            ),
            # Resolved, for the reason the model-points path is: the envelope
            # writes this file's path against the model's root, and a path
            # relative to whichever directory the command happened to run in
            # cannot be rewritten against anything until it is resolved.
            resolve_path=True,
            rich_help_panel="Output Options",
        ),
    ] = None,
    html: Annotated[
        Path | None,
        typer.Option(
            "--html",
            # The bracket is escaped because the help is rich markup, which
            # reads ``[viewer]`` as a style tag and prints "the gaspatchio
            # extra" -- the error path below escapes its sentence for the
            # same reason.
            help=(
                "Also write the viewer as one self-contained HTML page; "
                "needs the gaspatchio\\[viewer] extra"
            ),
            # Resolved for the reason the results file is: the path is written
            # down and printed back, and one that names whichever directory the
            # command happened to run in is a path that resolves on nobody
            # else's machine.
            resolve_path=True,
            rich_help_panel="Output Options",
        ),
    ] = None,
    xlsx: Annotated[
        Path | None,
        typer.Option(
            "--xlsx",
            help=(
                "Also lay the policies the artifact carries out as one .xlsx "
                "workbook: each policy's timeline with its formulas, its single "
                "values, the nodes, the edges and the assumption bases, every "
                "number the run's own double and nothing recalculating"
            ),
            resolve_path=True,
            rich_help_panel="Output Options",
        ),
    ] = None,
    policies: Annotated[
        list[str] | None,
        typer.Option(
            "--policies",
            help=(
                "Which model points the artifact carries values for, read by "
                "the term's own shape and first match winning: ':30', "
                "'3:40', '::10' and '-5:' are row positions, with Python's "
                "slice semantics; 'all' is every policy; 'spread:5@column' "
                "orders the book by one column and walks it at even spacing; "
                "'id:POL-000343' is one policy id verbatim, whatever it "
                "looks like; anything else is an id, or a comma-separated "
                "run of them. Real ids are strings and may collide with the "
                "forms above -- 'id:' is how a policy called '3:40' or 'all' "
                "is reached. Repeatable and unioned, keeping the first "
                "occurrence. This chooses what is sampled, never what is "
                "computed: the model runs the whole book either way. "
                "Default ':1', the first row of the book"
            ),
            rich_help_panel="Execution Options",
        ),
    ] = None,
    scenarios: Annotated[
        Path | None,
        typer.Option(
            "--scenarios",
            help=(
                "Export a scenario run instead of a plain one, over the run "
                "script at this path. The script declares SCENARIO_RUN (a "
                "ScenarioRun, or a function returning one) and MODEL_FN, and "
                "the exporter runs that plan -- the cross-join of policies x "
                "scenarios, once. Every entry of the policy axis then names "
                "its scenario in 'filter', and one assumption entry is "
                "carried per scenario curve. The frame names each policy "
                "once per scenario, so --policies <id> is refused there as "
                "an id with more than one answer: count rows with ':N' or "
                "narrow with --filter. The script is imported to reach its "
                "declarations, so put its own run under __main__"
            ),
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            rich_help_panel="Execution Options",
        ),
    ] = None,
    portfolio: Annotated[
        bool,
        typer.Option(
            "--portfolio",
            help=(
                "Also carry the book's own fold, as its own entry at the "
                "head of the policy axis. The accumulators are the model's "
                "own AGGREGATIONS, declared beside main() in the shape "
                "run_aggregated takes; a model declaring none is refused "
                "rather than folded by a guess"
            ),
            rich_help_panel="Execution Options",
        ),
    ] = False,
    portfolio_by: Annotated[
        list[str] | None,
        typer.Option(
            "--portfolio-by",
            help=(
                "Fold the book by this instead, written "
                "'<fold>:<column>,<column>' -- 'sum:pv_net_cf,net_cf'. "
                "Supplies the accumulators where the model declares none "
                "and overrides them where it does; asking implies "
                "--portfolio. Repeatable. A column holding one value per "
                "period takes the fold down its timeline and the entry "
                "records that it did"
            ),
            rich_help_panel="Execution Options",
        ),
    ] = None,
    policy_id: Annotated[
        str | None,
        typer.Option(
            "--policy-id",
            "-p",
            help="One policy ID, the older spelling of --policies <id>",
            rich_help_panel="Execution Options",
        ),
    ] = None,
    policy_id_column: Annotated[
        list[str] | None,
        typer.Option(
            "--policy-id-column",
            help=(
                f"Name of the policy ID column. Omitted: {_ID_CANDIDATES_HELP}; "
                "with none of them, policies are chosen by row position. Give "
                "it again for a second column, such as a scenario's, which the "
                "results file records as each row's identity with it"
            ),
            rich_help_panel="Execution Options",
        ),
    ] = None,
    max_size: Annotated[
        int,
        typer.Option(
            "--max-size",
            help=(
                "How many bytes the finished document may weigh. Measured "
                "over the assembled document rather than counted in "
                "policies, because per-policy bytes vary by model"
            ),
            rich_help_panel="Output Options",
        ),
    ] = MAX_DOCUMENT_BYTES,
    period: Annotated[
        int | None,
        typer.Option(
            "--period",
            help=(
                "Optional projection period to read per-period values at "
                "(0 is the first). Omitted, every period is shown"
            ),
            rich_help_panel="Execution Options",
        ),
    ] = None,
    branches: Annotated[
        bool,
        typer.Option(
            "--branches",
            help=(
                "Also state what each branch of a conditional would have "
                "held, and which one the condition chose. Off, a "
                "conditional's record names only the branch that fired"
            ),
            rich_help_panel="Execution Options",
        ),
    ] = False,
    filter_expr: Annotated[
        str | None,
        typer.Option(
            "--filter",
            "-f",
            help=(
                "Polars expression narrowing the rows the values are read "
                "off (e.g. \"col('year') == 1\"). Cut BEFORE --policies: the "
                "selection is made among the rows it keeps, so --policies 7 "
                '--filter \'col("scenario_id") == "BASE"\' reaches the one '
                "BASE row carrying 7. A cut naming a column the model "
                "computes rather than the book carries cannot be taken "
                "before the run, and then it narrows the finished frame and "
                "the selection is made over every row"
            ),
            rich_help_panel="Filter Options",
        ),
    ] = None,
    profile: Annotated[
        ConformanceProfile,
        typer.Option(
            "--profile",
            help=(
                "Which conformance profile the artifact claims: 'audit' is the "
                "account of the model, 'executable' adds the calculation itself"
            ),
            rich_help_panel="Output Options",
        ),
    ] = ConformanceProfile.AUDIT,
    include_source: Annotated[
        bool,
        typer.Option(
            "--source/--no-source",
            help=(
                "Whether the model's own text travels in the artifact, one "
                "entry per file its calculations were written in. Off keeps "
                "every path and fingerprint and records the text as withheld"
            ),
            rich_help_panel="Output Options",
        ),
    ] = True,
    include_versions: Annotated[
        bool,
        typer.Option(
            "--versions/--no-versions",
            help=(
                "Whether the artifact states the library versions that "
                "produced its values, and the installed packages the model "
                "imports. Off records them as withheld, for a document "
                "committed as a golden; with --scenarios, the run's own "
                "record withholds its versions too"
            ),
            rich_help_panel="Output Options",
        ),
    ] = True,
    retain_superseded: Annotated[
        bool,
        typer.Option(
            "--retain-superseded/--no-retain-superseded",
            help=(
                "Whether a column the model wrote over keeps what the replaced "
                "definition produced: the frame spends the memory to carry "
                "those values, the artifact writes them under 'retained: true'"
            ),
            rich_help_panel="Output Options",
        ),
    ] = True,
) -> None:
    """Generate a calculation graph from a model run.

    This command runs the model in debug mode to capture its calculation log,
    then exports it as JSON for visualization and analysis.

    ``--policies`` says which model points the artifact carries values for
    and ``--period`` narrows them to one point of the projection timeline.
    Either way the document says which, and a period the projection never
    reaches is refused with the length it actually runs to.

    **A term is read by its own shape, and the first match wins.** Whole-term
    Python slice grammar means row positions: ``:30`` is the first thirty
    rows, ``3:40`` rows three to thirty-nine, ``::10`` every tenth, ``-5:``
    the last five. ``all`` is every policy, subject to ``--max-size``. A term
    beginning ``spread:`` is ``spread:5@sum_assured``, which orders the book
    by one column and walks it at even spacing, ends included -- and that
    column is read from the model points as they arrive, because a selection
    is made before the model runs. ``id:POL-000343`` is one policy id taken
    verbatim. **Everything else is an id**, or a comma-separated run of them:
    ``--policies 1,7,42`` names three policies in that order.

    Deciding by shape and not by what the book holds is what keeps one
    command line meaning one thing on two books, and ``id:`` is what makes
    that safe. Real policy identifiers are strings -- ``POL-000343``,
    ``GB-2019-88231`` -- and nothing stops a book carrying one called
    ``3:40`` or ``all``; ``--policies id:3:40`` reaches it, and so does
    ``id:`` in front of an id with a comma in it. An id carried by more than
    one row is refused rather than resolved to the first.

    The option repeats and the results are unioned, keeping the first
    occurrence of a policy named twice. ``--policy-id 7`` is the older
    spelling of ``--policies 7`` and still works.

    **A selection chooses which policies are sampled, never which are
    computed.** The model runs the whole book whatever is selected, exactly
    as it does with no selection at all, so a twenty-policy export of a
    hundred-thousand-policy book costs what today's single-policy export of
    that book already costs. The reason is not speed: this document's whole
    claim is that every number on it is a quotation of a real run, and a
    model with a cross-row step -- a scenario axis is a cross-join on the
    model points, and a fold over it reads across rows -- would give one
    policy a different answer in a narrowed export from the answer the
    actuary's own run produced. A number that is only what it is because
    the export narrowed the book is not a quotation of anything.
    ``--filter`` is the option that narrows the rows, and the envelope
    records it on every entry of the axis; the two are different things and
    the document says them separately.

    Unpinned you always get the first thing: with no selection the artifact
    carries the first row of the file, which is not a representative policy
    but where the data happened to put it. Nothing here picks a policy for
    you -- no ranking column is inferred and no cohorts are built -- because
    a selection that picks badly is worse than a visibly arbitrary one.
    Every entry on the axis carries the sentence saying how it got there.
    With no ``--period`` a per-period column carries each policy's every
    period, which is what the document's ``periods: null`` states.

    **A scenario frame names each policy several times, and the selector
    says so.** A scenario axis in this framework is a cross-join on the
    model points, so a book of a thousand policies over three scenarios is
    three thousand rows and policy 7 is on three of them. ``--policies 7``
    is then refused as an id with more than one answer, which is right:
    taking the first would put the BASE row's numbers under a name the UP
    and DOWN rows answer to as well. Reach a row by counting -- ``--policies
    :1`` -- or narrow to the scenario you mean with ``--filter``, which the
    envelope records on every entry of the axis.

    ``--scenarios run_scenarios.py`` is how a scenario run gets an artifact
    at all. The model reads ``scenario_id`` and dispatches on it, but the
    *plan* is what cross-joins the axis, stacks the shocked bases and folds
    each scenario's total, so a command that ran the model alone would
    write a document with no scenario on it. The script is the one the
    modeller already writes, and the exporter runs its plan the way the
    script would -- the cross-join of policies by scenarios, once.

    **The script declares, the exporter reads**, exactly as a portfolio
    fold's ``AGGREGATIONS`` does. Two module-level names: ``SCENARIO_RUN``,
    the plan or a function of no arguments returning one, and ``MODEL_FN``,
    the function the plan is run against. A script declaring neither is
    refused by name -- which scenarios and which totals is the modeller's
    decision, and nothing here picks them. Reaching those names means
    importing the script, so whatever it does at module level happens
    first; putting its own sweep under ``if __name__ == "__main__":``
    leaves the declarations where this reads them and costs one run.

    **Every entry of the axis then carries its scenario** in the envelope's
    own ``filter``, the folds and the policies alike, and ``assumptions``
    carries one entry per scenario curve -- so a lookup proof's fingerprint
    chip names the table the selected scenario actually discounted with
    rather than the stack the run was built from. The scenario column
    itself is recorded as what it is: a column of values handed to the
    model at the line of the script that declares the plan, ``injected``
    rather than a field of a model-points file that never held it.

    **The totals come from the plan**, which is why ``--portfolio`` is
    refused beside ``--scenarios``: the plan's ``aggregations`` are what a
    sweep is read off and what its script prints, and a second fold by a
    second driver would put two answers to one question on one axis.

    The run also writes its own record beside the artifact --
    ``model.run.audit.json`` for ``-o model.audit.json`` or ``-o model.json``:
    which plan was run, which scenarios, what each folded -- and the
    envelope names that file by path and digest the way it names the
    results file and the model points. Two records of one run, tied
    together by content rather than by sitting in one directory.

    ``--portfolio`` adds the book's own fold to the head of that axis: one
    entry per fold, ``policy_id`` null because no policy is what it is an
    account of, and ``aggregation`` naming the fold. The accumulators come
    from the model -- an ``AGGREGATIONS`` tuple beside ``main``, the same
    shape ``run_aggregated`` takes -- and ``--portfolio-by
    sum:pv_net_cf,net_cf`` supplies them where the model declares none or
    overrides them where it does. A model declaring none and a bare
    ``--portfolio`` is refused by name: which columns a portfolio total is
    taken over is an actuarial decision, and a fold of every numeric output
    would publish a sum of a mortality rate.

    **The fold is the model's own, run over the whole book.** It is
    ``run_aggregated``'s result quoted, which means the model runs a second
    time -- in batches, so the fold of a book too large to hold is still a
    fold of the whole book. It is never a re-summation of the per-policy
    samples in the document: those are the handful of policies a reader
    asked for, and adding them up would publish a number that is nobody's
    under a name that says it is the book's. A column no accumulator covers
    carries null at the fold's position, because there is no portfolio
    value of a monthly mortality rate.

    ``Sum("pv_net_cf").over("scenario_id")`` folds each cut of the book
    separately and yields one entry per scenario, each stating its cut in
    the envelope's own ``filter``. The fold reads the whole book whatever
    ``--filter`` narrowed the samples to, and each entry says which it was.

    ``--results`` (also ``--output-file``) writes the finished frame to Parquet the way
    ``run-model`` does and names it in the artifact by path and content
    hash, so one run produces both the numbers and the account of them.
    Without it nothing is written and the document names no results.

    ``--profile executable`` writes the operation tree of every node that has
    one, which is what a second implementation would evaluate the model from.
    The default is the profile a reviewer reads.

    The model's own text travels with the account of it, one entry per file
    the calculations were written in, so a reader who has followed a node to
    ``model.py:520`` can read line 520. ``--no-source`` keeps every path and
    every fingerprint and records the text as withheld, which is a decision
    the file states rather than a gap a reader has to notice.

    The artifact states what produced its values -- the core and its
    compiled extension, each by version, the extension's sha256, Polars,
    Python and the platform, the six a results file's manifest states -- and
    each installed package the model imports, by version. ``--no-versions``
    records them as withheld, which is what a document committed as a golden
    wants: the strings name one machine's build. A model outside a git
    working tree, or one git could not answer for, is said so in one line as
    the file is written, and the document's ``model.git`` says which.

    A column this model writes twice carries what the replaced definition
    produced, and says so: the frame holds those values through its collect,
    the document writes them under ``retained: true``, and a reviewer with
    the file and no frame can ask what the column held before the override.
    ``--no-retain-superseded`` declines both halves -- nothing is carried,
    and the superseded definitions are written as history with no values.

    ``--branches`` answers "what would this have been if the condition had
    gone the other way?" A conditional's walk-through names the branch that
    fired and the other branch is in no column of the finished frame, so
    each one is evaluated for the declared policy and written beside the
    sample, with the branch the condition chose named. It is off by default
    because it costs an evaluation of both branches of every conditional.

    [bold green]Example:[/bold green]
        gspio calc-graph model.py data.parquet
        gspio calc-graph model.py data.parquet --artifact graph.json
        gspio calc-graph model.py data.parquet --branches
        gspio calc-graph model.py data.parquet --policies id:POL-7 --xlsx policy.xlsx
        gspio calc-graph model.py data.parquet --results results.parquet
        gspio calc-graph model.py data.parquet --profile executable
        gspio calc-graph model.py data.parquet --no-source
        gspio calc-graph model.py data.parquet --no-versions
        gspio calc-graph model.py data.parquet --no-retain-superseded
        gspio calc-graph model.py data.parquet --policies 1,7,42
        gspio calc-graph model.py data.parquet --policies :30
        gspio calc-graph model.py data.parquet --policies spread:5@sum_assured
        gspio calc-graph model.py data.parquet --policies all --max-size 52428800
        gspio calc-graph model.py data.parquet --portfolio
        gspio calc-graph model.py data.parquet --portfolio-by sum:pv_net_cf,net_cf
        gspio calc-graph model.py data.parquet --scenarios run_scenarios.py
        gspio calc-graph model.py data.parquet --scenarios run_scenarios.py --policies :3
        gspio calc-graph model.py data.parquet -p "123" -o debug_graph.json
        gspio calc-graph model.py data.parquet -p "123" --period 37
        gspio calc-graph model.py data.parquet -p "1" -f "col('year') == 1"
        gspio calc-graph model.py data.parquet -p "1" -f "(col('year') == 1) & (col('month') == 3)"

    [bold]Output:[/bold]
        The generated JSON contains nodes (inputs and computed columns) and edges
        (dependencies between columns) that can be visualized with graph tools.
    """
    # Every file this run writes goes into a directory that is there, checked
    # before the model starts: a workbook refused after the artifact was
    # written leaves half a run's files behind.
    _refuse_an_output_with_no_place(
        ("--artifact", output_file),
        ("--results", results_file),
        ("--html", html),
        ("--xlsx", xlsx),
    )
    # The model runs ONCE, here. The graph is an account of the same
    # execution the values were read off, which is the only way the two can
    # be filed together: an export ties a superseded definition's values to
    # the frame its own collect produced, by identity and not by shape, so a
    # document built from a second run of the same model carries no retained
    # definition at all -- whatever either lever is set to.
    config = ModelRunConfig(
        directory=code_path.parent,
        model_file=code_path.name,
        model_points_file=str(model_points_path),
        mode="debug",  # Must be debug to capture graph
        # The first identity column names a policy; a second, a scenario's,
        # is recorded with it in the results file, as run-model records it.
        id_column_name=policy_id_column[0] if policy_id_column else None,
    )
    data_path = config.directory / config.model_points_file

    # ``--policy-id 7`` is the older spelling of ``--policies 7``, so it
    # joins the list rather than sitting beside it: two ways of naming a
    # policy that reached the selector by two routes would be two selectors.
    # It goes first because it is the one a caller typed as the main pin.
    asked = [policy_id, *(policies or [])] if policy_id else list(policies or [])

    # Two folds of one book would be two answers to one question. A
    # scenario run folds through the plan's own aggregations -- which is
    # where a sweep's totals come from and what its script prints -- so a
    # --portfolio beside it would put a second set of entries on the axis,
    # taken by a second driver, under names a reader could not tell apart.
    if scenarios is not None and (portfolio or portfolio_by):
        err_console.print(
            "[red]"
            + escape(
                "--scenarios already folds the book: the plan's own "
                "aggregations are the totals a sweep is read off, and they "
                "become the fold entries on the policy axis. --portfolio "
                "would fold it a second time with a second set of "
                "accumulators, and the axis would carry two answers to one "
                "question. Declare the totals you want in the plan's "
                "aggregations=, or export without --scenarios to fold the "
                "book on its own."
            )
            + "[/red]"
        )
        raise typer.Exit(_EXIT_REFUSED_SELECTION)

    # The exporter the results file's manifest was read through, where one
    # was written: the document below goes through it too, so both files
    # state one fingerprint and the book is digested once.
    exporter: GraphExporter | None = None
    # A refusal raised by the run names the policy by the column the export
    # was told, as run-model's does (errors/policy_locator.py).
    with (
        console.status(
            "[bold green]Running model in debug mode to capture graph..."
        ) as status,
        telling_the_policy_id_column(config.id_column_name),
    ):
        try:
            # Read as ``gspio run-model`` and ``gspio verify`` read it, by
            # the one reader all three call: the book's digest is taken over
            # this frame, and a run over the file, or a reviewer holding it,
            # has to reach the same frame from it.
            df = book_from_file(data_path)

            # The plan, where one was named, read before anything runs: the
            # selection is made over the rows the run will have, and on a
            # scenario run those are the cross-join's rather than the
            # book's. Nothing of the model has started yet, so a script
            # that declares no plan is refused having spent nothing.
            declared = open_the_script(scenarios) if scenarios else None
            model_func = (
                None
                if declared is not None
                else load_model_from_path(
                    config.directory / config.model_file,
                    config.model_function_name,
                )
            )

            # Resolve the policy-ID column (honour an explicit name, else
            # auto-detect). A book that names no policy at all can still be
            # walked by row position, so a failure here is only fatal where
            # the selection asks about an identity.
            named_column: str | None
            try:
                id_column = _resolve_id_column(df.columns, config.id_column_name)
                named_column = id_column
            except ValueError:
                id_column = config.id_column_name or "Policy number"
                named_column = None

            # What the selector chooses among, and what the sentences call
            # it. A scenario run's frame is the cross-join, so the rows are
            # the grid's and the source names the axis that made them --
            # otherwise a refusal would say "3,000 rows of
            # model_points.parquet" about a file holding a thousand.
            #
            # Stamped, because a selection made over these rows has to be
            # findable in the frame the model hands back: the stamp is the
            # only thing that survives a model that sorts, and without it a
            # row position carried across the run is how one policy's
            # numbers end up under another policy's name.
            stamped = stamp_the_book(df)
            rows = stamped if declared is None else the_grid(declared, df)
            source_of_rows = (
                data_path.name
                if declared is None
                else f"{data_path.name} x {len(declared.scenario_ids)} scenarios"
            )
            # The cut first, then the selection. ``--filter`` says which
            # rows are behind a value, so an id resolved over rows the
            # filter has already thrown away answers a question nobody
            # asked -- which is how the duplicate-id refusal came to
            # recommend the very filter that resolves it. A cut naming a
            # column the model has not computed yet cannot be taken here at
            # all, and then the selection is made over every row and the
            # filter narrows the finished frame as it always has.
            kept = rows_the_filter_keeps(rows, filter_expr)
            selection = select_policies(
                asked,
                book=rows,
                id_column=named_column,
                source=source_of_rows,
                kept=kept,
                cut=None if kept is None else filter_expr,
            )
            selection = (
                each_entry_names_its_scenario(selection, rows)
                if declared is not None
                else pin_each_entry(selection, rows)
            )
            # **The selection chooses which policies are sampled and never
            # which are computed.** The model runs the book, exactly as it
            # does with no selection at all, because this document's whole
            # claim is that every number on it is a quotation of a real run
            # -- and a value that is only what it is because the export
            # narrowed the book is not that quotation. A model with a
            # cross-row step would give policy 291 one answer in a
            # two-policy export and another in the run the actuary did.
            # The member for a narrowed run is ``--filter``, which the
            # envelope records on every entry of the axis.
            _announce_the_axis(selection)

            # The frame this document is an account of, and the only one the
            # command builds. ``retain_superseded`` here is the memory lever:
            # off, a replaced definition's values are never carried through
            # the collect below, so there is nothing for the export to write
            # however it is asked.
            folds: tuple[PortfolioFold, ...] = ()
            audit_file: Path | None = None
            if declared is not None:
                status.update("[bold green]Running the scenario plan...")
                # The plan, run the way the script runs it: the cross-join
                # of policies against scenarios, once, and then the plan's
                # own fold. The audit record lands beside the artifact
                # rather than under a timestamped run id, so the two records
                # of one run are found together and the envelope can name
                # the one by the other.
                audit_file = _the_runs_own_record(output_file)
                run = run_the_plan(
                    declared,
                    book=stamped,
                    audit_path=audit_file,
                    retain_superseded=retain_superseded,
                    source=data_path.name,
                    period=period,
                    versions="recorded" if include_versions else "withheld",
                )
                af, result_df, folds = run.frame, run.values, run.folds
                audit_file = run.audit_path
                _announce_the_folds(folds)
            else:
                assert model_func is not None  # noqa: S101 — the branch above owns the other case
                af = _frame_over_the_book(
                    stamped, mode="debug", retain_superseded=retain_superseded
                )
                af = frame_run_model(model_func, af)
                result_df = af.collect()

            # The numbers, where they were asked for, out of the same
            # execution the account below is of. Written before the
            # identity block is built, because that block stamps this file
            # by its content and cannot stamp a file that is not there yet.
            # The stamp comes off first: it is this export's scaffolding
            # for finding a selected row again, and a results file carrying
            # it would be handing the modeller a column their model never
            # wrote and their next run would not have. The manifest goes in
            # with the values, so the block below stamps a file that already
            # says which model and which book produced it.
            if results_file is not None:
                exporter = _save_results(
                    without_the_stamp(result_df),
                    results_file,
                    af,
                    book=df.columns,
                    told_id_column=policy_id_column or None,
                )

            # The book's own fold, where one was asked for. After the run
            # because the accumulators are read against the frame the run
            # produced -- whether a column exists at all, and whether it
            # holds one value per policy or one per period -- and a typo
            # told here has not yet spent a second pass of the model.
            if (portfolio or portfolio_by) and model_func is not None:
                status.update("[bold green]Folding the book...")
                folds = fold_the_book(
                    model_func,
                    book=df,
                    finished=without_the_stamp(result_df),
                    asked=portfolio_by or (),
                    model_file=code_path.name,
                    source=data_path.name,
                    period=period,
                )
                _announce_the_folds(folds)
        except (
            PolicySelectionError,
            PortfolioFoldError,
            ScenarioDoorError,
        ) as refusal:
            # Ahead of the broad catch below, because a selection that names
            # no honest set of model points is not a model that failed to
            # run: the model never started, and a refusal reported as a run
            # failure sends a reader into the model looking for a defect
            # that is in the command line. A fold nobody declared is the
            # same kind of thing said about the other axis.
            err_console.print(f"[red]{escape(str(refusal))}[/red]")
            raise typer.Exit(_EXIT_REFUSED_SELECTION)
        except Exception as error:  # one answer for every way a run can fail
            logger.debug("Model execution failed with {}", type(error).__name__)
            err_console.print(
                f"[red]Error running model:[/red] "
                f"{shown(_model_failure_message(error, mode=config.mode), lines=True)}"
            )
            raise typer.Exit(1)

        status.update("[bold green]Building calculation graph...")
        try:
            # Create export configuration. The model identity travels with it: an
            # artifact that cannot say which file it is an account of, at which
            # revision, over which policy data, and — where this run wrote
            # one — into which results file, is one nobody can place a
            # quarter later. It is the helper a Python export calls, so the
            # two routes write one account of one model.
            identity = ModelIdentity.of(
                code_path,
                model_points=data_path,
                results=results_file,
                audit=audit_file,
                scenarios=scenarios,
            )
            export_config = GraphExportConfig(
                model=identity,
                policy_id=selection[0].policy_id,
                policies=selection,
                folds=folds,
                policy_id_column=id_column,
                period=period,
                filter_expr=filter_expr,
                include_traces=True,
                branches=branches,
            )

            # Export using the new GraphExporter. The profile is spelled out at
            # the call rather than handed through as a value, so that the two
            # names the format defines are the two names this file writes.
            # ``retain_superseded`` is the document lever beside the frame's
            # memory one, and this command asks both the same question.
            # The columns the file carried, which is the one thing about
            # this run the finished frame cannot be asked. A model that
            # rebuilds its frame from a bare constructor comes back holding
            # names the data never had and no log to explain them; without
            # this the export would write every one of them as a field of
            # the model points, which is a lineage the file cannot support.
            # No ``source_root``: the identity carries the root its own paths
            # were written against, and the export writes every node's
            # location against it, so a node's location and the file the
            # envelope names it in are two statements a reader resolves the
            # same way, from wherever they have put the model. The exporter
            # the results file's manifest was read through is reused, so the
            # book is digested once for both files.
            if exporter is None:
                exporter = GraphExporter(af, data_columns=df.columns)
            json_graph = exporter.export(
                result_df,
                export_config,
                profile=(
                    "executable"
                    if profile is ConformanceProfile.EXECUTABLE
                    else "audit"
                ),
                include_source=include_source,
                retain_superseded=retain_superseded,
                versions="recorded" if include_versions else "withheld",
            )

            # The ceiling, over the assembled document and before it is
            # written. In bytes rather than in policies, because per-policy
            # bytes vary by model: a projection over 241 periods costs
            # several times what one over 83 does, so a count of policies
            # would be a guard set to the wrong number on every model but
            # the one it was chosen on.
            refuse_over_the_ceiling(len(json_graph.encode()), max_size)

            # Save to file
            output_file.write_text(json_graph)

            # Parse JSON to get statistics
            artifact = json.loads(json_graph)
            graph_nodes = artifact.get("nodes", [])
            computed_nodes = [n for n in graph_nodes if n["kind"] == "computed"]
            num_edges = len(artifact.get("edges", []))
            # The two summary lines, read off the document here so that one
            # they cannot read -- a node of a kind the format does not define,
            # a calculation with no tier -- is refused by name below rather
            # than miscounted.
            node_line = node_accounting(graph_nodes)
            census = _census_of_document(graph_nodes)
            unaccounted = _unaccounted_line(artifact.get("holes", []))
        except PolicySelectionError as refusal:
            err_console.print(f"[red]{escape(str(refusal))}[/red]")
            raise typer.Exit(_EXIT_REFUSED_SELECTION)
        except ValueError as e:
            # Escaped, because a refusal names columns and nodes, and a column
            # name can hold the square brackets rich reads as markup.
            err_console.print(f"[red]Error:[/red] {escape(str(e))}")
            raise typer.Exit(1)
        except Exception as e:
            err_console.print(f"[red]Unexpected error building graph:[/red] {shown(e)}")
            logger.exception("Failed to build calculation graph")
            raise typer.Exit(1)

    # The page, when one was asked for. Outside the block above for two
    # reasons: a 2 MB write does not belong under a spinner, and the refusal
    # below carries an exit code of its own, which the broad ``except
    # Exception`` up there would otherwise catch -- ``typer.Exit`` is a
    # ``RuntimeError`` -- and re-report as a failure to build the graph.
    if html is not None:
        # UTF-8 whatever the platform's own encoding, because the page says
        # it is: the licence notices it ends with hold characters that a
        # Windows code page writes as other bytes, or cannot write at all.
        try:
            html.write_text(
                render_html(json_graph, title=code_path.stem), encoding="utf-8"
            )
        except ViewerNotInstalledError as missing:
            # Escaped before printing: the sentence names the extra as
            # ``gaspatchio[viewer]``, and rich reads square brackets as markup.
            # Unescaped, the one thing this message exists to say would reach
            # the terminal as ``pip install "gaspatchio"``.
            err_console.print(f"[red]{escape(str(missing) + WROTE_THE_ARTIFACT)}[/red]")
            raise typer.Exit(2)

    # The workbook, laid out from the document just written rather than from
    # the frame, so the two cannot disagree; the results file this run wrote
    # is checked against it on the way, and its README says so.
    if xlsx is not None:
        try:
            xlsx.write_bytes(render_xlsx(json_graph, results=results_file))
        except ValueError as refused:
            err_console.print(
                f"[red]{escape(str(refused))} The JSON artifact was written; the "
                "workbook was not.[/red]"
            )
            raise typer.Exit(1) from None

    console.print(
        f"\n[bold green]✓[/bold green] Calculation graph saved to: {shown(output_file)}"
    )
    if results_file is not None:
        console.print(
            f"[bold green]Results saved to {shown(results_file)}[/bold green]"
        )
    if html is not None:
        console.print(f"[bold green]Page saved to {shown(html)}[/bold green]")
    if xlsx is not None:
        console.print(f"[bold green]Workbook saved to {shown(xlsx)}[/bold green]")
    # Every node, under every kind the document writes, so the parts add up
    # to the total. A model holding columns it cannot account for is the one
    # thing here nobody should have to find by subtracting the other counts.
    console.print(f"  {node_line}")
    # And every calculation at the tier the file gives it. Nothing
    # unaccounted for does not mean every line is in the format's own
    # vocabulary: a line written in an engine's own expression language is
    # accounted for, and still runs on that engine alone. Read off the
    # document's nodes, as the line above is, so both lines say what the file
    # says. Escaped, since a node id carries a column name and a column name
    # can hold the square brackets rich reads as markup.
    console.print(f"  {escape(_tier_line(census))}")
    # And which columns are unaccounted for, by name and with what the frame
    # saw of each, where there are any: the count above says how many, and
    # this says which line of the model to open. Escaped, as the line above.
    if unaccounted:
        console.print(f"  {escape(unaccounted)}")
    console.print(f"  Edges: {num_edges}")
    console.print(f"  Profile: {profile.value}")

    # Show sample of the graph structure. Filtered before it is sliced:
    # taking the first three nodes and then keeping the computed ones
    # prints this header with nothing under it on any model whose first
    # three nodes all happen to be columns its data arrived with.
    #
    # What each one reads is the node's own ``reads``, the member the
    # document writes: the summary says what the file says, and a line that
    # reads no column says so in a word rather than trailing off.
    if computed_nodes:
        console.print("\n[bold]Sample computed nodes:[/bold]")
        for node in computed_nodes[:3]:
            reads = ", ".join(node.get("reads", [])) or "nothing"
            console.print(f"  • {escape(node['id'])} ← {escape(reads)}")


@app.command(
    name="run-artifact",
    help="Run an executable artifact on a discovered engine and write the result",
    rich_help_panel="Model Execution",
)
def run_artifact(
    artifact_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the executable artifact JSON file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    inputs_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help=(
                "The book: a Parquet file whose columns include every input "
                "node's column"
            ),
        ),
    ],
    *,
    engine: Annotated[
        str,
        typer.Option(
            "--engine",
            help=(
                "An installed artifact engine, for example jax. "
                "JAX device selection follows JAX configuration."
            ),
        ),
    ],
    output_file: Annotated[
        Path | None,
        typer.Option(
            "--results",
            "--output",
            "-o",
            resolve_path=True,
            help=(
                "Save calculated values and their result manifest to Parquet "
                "(default results.parquet); with --aggregate, the totals and "
                "their record to JSON (default results.json)"
            ),
        ),
    ] = None,
    every_node: Annotated[
        bool,
        typer.Option(
            "--every-node",
            help=(
                "Write every value-bearing node's column, by node id, rather "
                "than the final schema"
            ),
        ),
    ] = False,
    aggregate: Annotated[
        Path | None,
        typer.Option(
            "--aggregate",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help=(
                "Fold the book into the aggregators this JSON file lists -- "
                "each one's canonical form, its alias and an optional 'over' -- "
                "and write the totals rather than the rows"
            ),
        ),
    ] = None,
    align: Annotated[
        str | None,
        typer.Option(
            "--align",
            help=(
                "With --aggregate: 'duration' folds an inception-aligned "
                "artifact by policy duration, as run_aggregated's align does"
            ),
        ),
    ] = None,
    policy_id_column: Annotated[list[str] | None, _RECORDED_IDENTITY_OPTION] = None,
) -> None:
    """Run one artifact over one book on a second engine.

    The artifact is the whole of what the engine reads: the calculations, the
    types, the assumption bases it was run against. The book need not be the
    one the artifact was exported from -- a quarter's new in-force file
    against last quarter's model is the ordinary case -- and the result
    states which book it was, beside the artifact's own fingerprint, so a
    later comparison knows what it is comparing.

    [bold]--every-node[/bold] writes every value-bearing node's column under
    its node id, which is what an agreement run compares: the scale a line is
    judged against needs the values of the nodes it reads, and a final-schema
    file does not carry them.

    Nothing partial is ever left on disk. Each batch is staged beside the
    destination as it finishes, where nothing reads it, and the rename of the
    finished file into place is the publication -- so a run that refuses at
    completion, or is interrupted, leaves the destination as it found it and
    nothing beside it.

    [bold]--aggregate SPEC.json[/bold] folds the book on the engine into the
    aggregators the file lists and never writes a row: a JSON array whose
    entries are each aggregator's canonical form beside its alias -- for
    example [dim]{"alias": "bel", "kind": "Sum", "column": "pv_net_cf"}[/dim] --
    with [dim]"over": ["product_id"][/dim] to partition one, as .over() does.
    The result is JSON: the record run_aggregated's audit= writes, carrying
    each alias's value, what each value is, the artifact's fingerprint, the
    book's digest and the engine with every version it ran under.

    The exit status is the answer: [bold]0[/bold] where the run published,
    [bold]1[/bold] where the engine refused and printed its report, and
    [bold]2[/bold] where there was no engine to run on, or no place to write
    the result -- a directory that does not exist, or a path that is one --
    which is refused before the engine starts.

    [bold green]Example:[/bold green]
        gspio run-artifact artifact.json book.parquet --engine jax
        gspio run-artifact artifact.json book.parquet --engine jax -o q1.parquet
        gspio run-artifact artifact.json book.parquet --engine jax --every-node
        gspio run-artifact artifact.json book.parquet --engine jax --aggregate spec.json
    """
    if align is not None and aggregate is None:
        err_console.print(
            "[red]--align says how --aggregate totals periods across policies, "
            "and there is no --aggregate here; drop --align, or aggregate.[/red]"
        )
        raise typer.Exit(_EXIT_UNREADABLE)
    # The file this run writes, the default included, goes into a directory
    # that is there: checked before the engine spends anything, and never
    # created for it.
    output_file = (
        output_file
        or Path("results.parquet" if aggregate is None else "results.json").resolve()
    )
    _refuse_an_output_with_no_place(("--results", output_file))

    document = _artifact_document(artifact_path)

    try:
        inputs = pl.read_parquet(inputs_path)
    except Exception as error:
        err_console.print(
            f"[red]{shown(inputs_path)} could not be read as a book:[/red] "
            f"{shown(error)}"
        )
        raise typer.Exit(_EXIT_UNREADABLE)

    try:
        found = engine_named(engine)
    except (EngineNotInstalledError, EngineBrokenError) as missing:
        # Escaped before printing, for the viewer's reason: the sentence names
        # the extra as ``gaspatchio[jax]`` and rich reads square brackets as
        # markup of its own.
        err_console.print(f"[red]{escape(str(missing))}[/red]")
        raise typer.Exit(_EXIT_UNREADABLE)

    if aggregate is not None:
        _aggregate_artifact(
            document,
            inputs,
            found,
            engine=engine,
            spec_path=aggregate,
            output_file=output_file,
            every_node=every_node,
            align=align,
        )
        return

    # The engine is handed the artifact and the book, and neither names a
    # policy's identity column; the book this command read does, resolved as
    # every other results writer resolves it, and the sink states it in the
    # manifest wherever the engine's columns carry it. The scenario half is
    # what the artifact records as handed to the model -- an injected input.
    # Columns named on the command line that name no row once are refused
    # here, before the engine has spent anything.
    identity = _the_row_identity(
        inputs, policy_id_column or None, _injected_inputs(document)
    )
    if policy_id_column and identity is None:
        err_console.print(
            f"[red]{escape(_no_identity_recorded(policy_id_column))}[/red]"
        )
        raise typer.Exit(_EXIT_UNREADABLE)
    sink = ParquetSink(output_file, row_identity=identity)
    try:
        result = found.run(document, inputs, sink, every_node=every_node)
    except EngineRefusal as refused:
        # The engine abandons its own sink; this is the backstop, because
        # "nothing partial is left on disk" is a promise this command makes
        # to the reader and not one it delegates.
        sink.abandon()
        console.print(refused.report.render(), markup=False)
        raise typer.Exit(_EXIT_REPORTED)

    for note in result.report.notes:
        console.print(f"  {note}", markup=False)
    console.print(
        f"[bold green]Results saved to {shown(output_file)}[/bold green] "
        f"({_counted(len(result.manifest.columns), 'column')}, "
        f"{shown(result.manifest.scope)})"
    )


def _aggregate_artifact(
    document: dict[str, Any],
    inputs: pl.DataFrame,
    found: "Engine",
    *,
    engine: str,
    spec_path: Path,
    output_file: Path,
    every_node: bool,
    align: str | None,
) -> None:
    """Fold one book into the aggregators a spec lists, and write their record.

    The spec is the aggregators' own canonical forms, each beside its alias
    and an optional ``over``, rebuilt through the aggregator registry -- the
    same objects ``run_aggregated`` is handed in Python. What is written is
    the record ``run_aggregated``'s ``audit=`` writes, so a total folded here
    and one folded from a model file are read, compared and placed the same
    way: the values, what each value is, the artifact's fingerprint, the book
    and the engine with every version it ran under.

    The alignment guard is ``run_aggregated``'s, asked of the document rather
    than of a frame, and it is asked before the engine is: an inception-
    aligned artifact folded by index is a total across calendar months that
    no reader asked for.
    """
    from .engines.aggregation import aggregating  # noqa: PLC0415 -- folding only
    from .scenarios import parse_aggregations  # noqa: PLC0415 -- as above
    from .scenarios._aggregated import (  # noqa: PLC0415 -- as above
        _alias_of,
        _check_document_origin,
        _with_audit_record,
    )

    if every_node:
        err_console.print(
            "[red]--every-node writes every node's rows and --aggregate writes "
            "totals and no rows; ask for one of the two.[/red]"
        )
        raise typer.Exit(_EXIT_UNREADABLE)
    if align not in (None, "calendar", "duration"):
        err_console.print(
            f"[red]--align is 'calendar' or 'duration', as run_aggregated's align "
            f"is; got {shown(repr(align))}.[/red]"
        )
        raise typer.Exit(_EXIT_UNREADABLE)
    try:
        spec = json.loads(spec_path.read_text())
        aggregations = parse_aggregations(spec)
    # Every way a spec can fail to become aggregators is the spec's, so every
    # one is this door's "unreadable" rather than a traceback on the status
    # this command keeps for an engine's refusal.
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        err_console.print(
            f"[red]{shown(spec_path)} could not be read as a list of aggregators:[/red] "
            f"{escape(str(error))}"
        )
        raise typer.Exit(_EXIT_UNREADABLE) from None
    try:
        _check_document_origin(document, align)
    except ValueError as refused:
        err_console.print(f"[red]{escape(str(refused))}[/red]")
        raise typer.Exit(_EXIT_REPORTED) from None

    try:
        result = aggregating(found, engine).aggregate(document, inputs, aggregations)
    except EngineRefusal as refused:
        console.print(refused.report.render(), markup=False)
        raise typer.Exit(_EXIT_REPORTED) from None

    stamp = result.produced_by.graph_fingerprint if result.produced_by else None
    _with_audit_record(
        result,
        audit=output_file,
        aliases=[_alias_of(one) for one in aggregations],
        aggregations=aggregations,
        model_points=inputs,
        stamps={stamp},
    )
    notes = result.produced_by.notes if result.produced_by else ()
    for note in notes:
        console.print(f"  {note}", markup=False)
    policies = "policy" if result.n_policies == 1 else "policies"
    console.print(
        f"[bold green]Aggregates saved to {shown(output_file)}[/bold green] "
        f"({_counted(len(aggregations), 'aggregation')} over "
        f"{result.n_policies} {policies}, {shown(engine)})"
    )


def _counted(number: int, noun: str) -> str:
    """Return the number and the noun, pluralised the ordinary way."""
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _what_it_is(document: object) -> str:
    """Name what a file turned out to hold, in the words JSON uses for it.

    Someone who handed over the wrong file is told what the file is, not only
    that it is not what was wanted -- which is the difference between knowing
    to reach for the export and reading the sentence again.
    """
    if document is None:
        return "JSON null"
    if isinstance(document, bool):
        return "a JSON boolean"
    if isinstance(document, int | float):
        return "a JSON number"
    if isinstance(document, str):
        return "a JSON string"
    if isinstance(document, list):
        return "a JSON array"
    return f"a JSON {type(document).__name__}"


def _artifact_document(path: Path) -> dict[str, Any]:
    """Read one artifact off disk, or say which file did not read and stop.

    Both commands below hold a path by the time anything can go wrong with
    it, and one of them holds two, so the message names the file rather than
    leaving the caller to work out which of them it was about.

    Three things can be wrong with a file and all three are the same answer:
    it is not text, it is not JSON, or it is JSON of some shape other than
    the object an artifact is. Each leaves here rather than reaching a
    reading, because a reading handed something that is not an artifact
    either falls over inside the library or -- worse, and this is what a
    top-level string used to do -- reads the text a second time as though it
    named another file and pronounces a finding against a model on the
    strength of it. Neither is a verdict, so neither is allowed to look like
    one.

    Getting the bytes off the disk is answered by the class that answers it:
    a file the operating system would not hand over. What the bytes are --
    a Git LFS pointer, or not text at all -- is :func:`_text_in`, and turning
    the text into a document is :func:`_artifact_in`. A file a revision
    committed passes through both too, so the two are held to one test.
    """
    return _artifact_in(_artifact_text(path), named=str(path))


def _artifact_text(path: Path) -> str:
    """Read one artifact's text off disk, or say that the file did not read and stop."""
    try:
        data = path.read_bytes()
    except OSError as error:
        err_console.print(f"[red]{shown(path)} could not be read:[/red] {shown(error)}")
        raise typer.Exit(_EXIT_UNREADABLE)
    # Newlines as a text-mode read gives them, which is how a file on disk has
    # always been read here.
    return _text_in(data, named=str(path)).replace("\r\n", "\n").replace("\r", "\n")


def _text_in(data: bytes, *, named: str, committed: CommittedFile | None = None) -> str:
    """Return the text an artifact's bytes hold, or say they hold none and stop.

    A Git LFS pointer is said to be one, with what fetches the file it stands
    for: on disk, a checkout made without Git LFS; at a revision, the file
    that revision keeps in LFS storage, named by ``committed``. Read as JSON a
    pointer is merely not JSON, which names the wrong problem. Bytes that are
    not UTF-8 -- which JSON is, rather than the platform's own encoding -- are
    not the text an artifact is.
    """
    pointer = parse_lfs_pointer(data)
    if pointer is not None:
        err_console.print(f"[red]{escape(_lfs_said(named, pointer, committed))}[/red]")
        raise typer.Exit(_EXIT_UNREADABLE)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        _refuse_bytes(named, error)


def _lfs_said(named: str, pointer: LfsPointer, committed: CommittedFile | None) -> str:
    """Return the sentence for a Git LFS pointer where an artifact was expected.

    Worded for every command that reads an artifact -- validate, verify,
    compare, run-artifact and diff -- so it names the file the pointer stands
    for rather than calling it an audit file.
    """
    stored = f"sha256 {pointer.oid}, {pointer.size} bytes"
    if committed is None:
        return (
            f"{named} is a Git LFS pointer, not the file it stands for ({stored}): "
            "it was checked out without Git LFS, and git lfs pull fetches it."
        )
    return (
        f"{named} is a Git LFS pointer, not the file it stands for: that revision "
        f"stores the file in Git LFS ({stored}). Write it out with {committed.show} "
        "| git lfs smudge > file and compare that file."
    )


def _refuse_bytes(named: str, error: UnicodeDecodeError) -> NoReturn:
    """Say that ``named`` holds bytes rather than the text an artifact is, and stop."""
    err_console.print(
        f"[red]{shown(named)} holds bytes rather than text, so there is no "
        f"artifact here to read:[/red] {shown(error)}"
    )
    raise typer.Exit(_EXIT_UNREADABLE)


def _artifact_in(text: str, *, named: str) -> dict[str, Any]:
    """Return the artifact document ``text`` holds, or say that ``named`` holds none.

    **Turning the text into a document is answered for every way it can
    fail**, named or not, because the only thing that can be a verdict is a
    document -- so a parse that produced none has the same answer whichever
    route it left by, and a route nobody enumerated would otherwise escape as
    a traceback on the status this surface keeps for a finding against a
    model. A file nested deeper than the parser goes is exactly that: JSON by
    grammar, no document by outcome.

    ``named`` is what the refusal calls the text's source: a path, or a path
    at a revision.
    """
    try:
        document = json.loads(text)
    except Exception as error:  # every way of not getting a document, not three
        err_console.print(
            f"[red]{shown(named)} could not be read as an artifact document, so "
            f"there is no artifact here to read:[/red] {shown(error)}"
        )
        raise typer.Exit(_EXIT_UNREADABLE) from None

    if not isinstance(document, dict):
        err_console.print(
            f"[red]{shown(named)} holds {_what_it_is(document)}, and an artifact "
            f"is a JSON object, so there is no artifact here to read.[/red]"
        )
        raise typer.Exit(_EXIT_UNREADABLE)
    return cast("dict[str, Any]", document)


def _store_report(
    payload: dict[str, Any],
    *,
    json_output: bool,
    output_file: Path | None,
) -> None:
    """Write the report as JSON wherever the caller asked for it, if anywhere.

    A terminal is for a person. Anything downstream reads the stored file,
    which is the report's own JSON and not something scraped off a console.

    The reading is already said by the time this runs, so a path that will
    not take the file costs the storing and not the answer. The status is 2,
    which here means the command did not finish the job it was given: a
    verdict reached and not stored is not a refusal, and 1 -- the code this
    surface keeps for a finding against a model -- would say it was.
    """
    if json_output:
        print(json.dumps(payload, indent=2))
    if output_file is None:
        return
    why = no_place_for_a_file("--output-file", output_file)
    if why is not None:
        err_console.print(
            f"[red]The report was reached but not stored: {escape(why)}[/red]"
        )
        raise typer.Exit(_EXIT_UNREADABLE)
    try:
        output_file.write_text(json.dumps(payload, indent=2))
    except OSError as error:
        err_console.print(
            f"[red]The report was reached but not stored at "
            f"{shown(output_file)}:[/red] {shown(error)}"
        )
        raise typer.Exit(_EXIT_UNREADABLE)


def _print_validation_report(path: Path, report: "ValidationReport") -> None:
    """Print what one reading of one artifact found.

    Every finding already says what is wrong in the model's own terms and
    what the next move is. This prints them: a second wording of an error the
    framework has already written is a second thing that has to stay true.
    """
    errors = [f for f in report.findings if f.severity == "error"]
    warnings = [f for f in report.findings if f.severity == "warning"]
    if report.ok:
        stated = shown(report.schema or "no schema identifier")
        console.print(
            f"\n[bold green]✓[/bold green] {shown(path.name)} conforms to {stated}"
        )
    else:
        console.print(
            f"\n[bold red]✗[/bold red] {shown(path.name)} is refused: "
            f"{_counted(len(errors), 'error')}"
        )
    console.print(f"  Read: {', '.join(report.sections) or 'nothing'}")
    if warnings:
        console.print(f"  {_counted(len(warnings), 'warning')} beside that")
    for finding in report.findings:
        colour = "red" if finding.severity == "error" else "yellow"
        console.print(
            f"\n  [{colour}]{finding.severity}[/{colour}] "
            f"[bold]{shown(finding.where)}[/bold]  ({shown(finding.section)})"
        )
        # Text rather than a formatted string: a finding names node ids,
        # JSON pointers and column names, any of which can carry brackets a
        # console would otherwise read as its own formatting. Padding rather
        # than a leading indent: these messages run to several lines, and a
        # continuation line at column zero reads as a new finding.
        console.print(Padding(Text(finding.message), (0, 0, 0, 4)))


def _print_diff_report(
    before: str,
    after: str,
    report: "DiffReport",
    *,
    results_not_compared: str | None,
    results_moved: str,
    library_moved: str | None = None,
) -> None:
    """Print what moved between two artifacts, the model kept apart from the data.

    ``before`` and ``after`` are what the two are called: a file's name, or a
    file's name at the revision that committed it.

    A results file one run named and the other did not was not compared, and
    the report carries no entry for it. The line saying so comes last,
    whatever else moved, because it is about what the report could not cover.

    Where something moved and both documents carry a formulas-only
    fingerprint, the first line under the headline compares the two: equal
    says no formula changed and names the data that did, different says a
    formula changed. A document written before the figure gets no such line.

    Where the two documents record different library versions, one line
    under the headline says which. It is context, never a finding: no entry
    in the report, and no part of the exit status.
    """
    if not report.drift:
        console.print(
            f"\n[bold green]✓[/bold green] nothing moved between "
            f"{escape(before)} and {escape(after)}"
        )
        _print_library_moved(library_moved)
        _print_source_moved(report)
        _print_results_not_compared(results_not_compared)
        return

    console.print(
        f"\n[bold yellow]![/bold yellow] something moved between "
        f"{escape(before)} and {escape(after)}"
    )
    formulas = _formulas_said(report)
    if formulas is not None:
        console.print(f"  {formulas}", markup=False)
    _print_library_moved(library_moved)
    _print_source_moved(report)
    console.print(
        f"\n[bold]Calculations:[/bold] {_counted(len(report.calculations), 'change')}"
    )
    for change in report.calculations:
        origin = f"  ({change.change_origin})" if change.change_origin else ""
        console.print(f"  {change.kind:<8} {change.node}{origin}", markup=False)
        if change.renamed_from is not None:
            console.print(f"           from {change.renamed_from}", markup=False)
        # A shared fingerprint is a pairing and never a rename: fingerprints
        # are not unique by design, so the report hints and the command says
        # so rather than printing the hint as though it were a finding.
        if change.fingerprint_equal_to is not None:
            console.print(
                f"           same fingerprint as {change.fingerprint_equal_to} "
                "(a hint, not a rename)",
                markup=False,
            )
        if change.values_equal_to is not None:
            console.print(
                f"           same values as {change.values_equal_to} "
                "(a hint, not a rename)",
                markup=False,
            )
    console.print(f"\n[bold]Data:[/bold] {_counted(len(report.data), 'change')}")
    for moved in report.data:
        console.print(
            f"  {moved.kind:<13} {moved.name or '(unnamed)'}  "
            f"{moved.before or '-'} → {moved.after or '-'}",
            markup=False,
        )
        # An entry that could not be compared is drift for the reason it
        # gives, and a line of two dashes would not say which. A results
        # file's digest moves with its writer as well as with its numbers, so
        # its entry says which step tells the two apart. Padded rather than
        # indented, as validate prints a finding: both run to several lines.
        said = moved.reason
        if said is None and moved.kind == "results":
            said = results_moved
        if said is not None:
            console.print(Padding(Text(said), (0, 0, 0, 16)))
    _print_results_not_compared(results_not_compared)


def _the_values(
    report: "DiffReport",
    earlier: "_DiffSide",
    later: "_DiffSide",
    *,
    named: tuple[Path, Path] | None,
    skipped: bool,
    told: list[str] | None,
) -> tuple["DiffReport", str | None]:
    """Return the report with its values read beside it, and why not where they were not.

    Named files are read, or the command exits 2 with the reason: the caller
    asked for those two and nothing else answers. Otherwise the files the two
    audit files record are read where both record one and each is still where
    it was written, with the checksum recorded; where they are not, the report
    is the audit files' alone and the sentence says why. Where neither audit
    file records a results file there is nothing to say, and where only one
    does, the report's own line already says so.
    """
    if skipped:
        return report, None
    documents = (earlier.document, later.document)
    if named is not None:
        try:
            return with_values(report, documents, named, row_identity=told), None
        except ValueError as error:
            err_console.print(
                "[red]These results cannot be read beside these audit files:[/red] "
                f"{escape(str(error))}"
            )
            raise typer.Exit(_EXIT_UNREADABLE) from None
    if any(results_file_recorded(document)[1] is None for document in documents):
        return report, None
    found = [
        recorded_results(side.document, side.roots, side=which)
        for side, which in ((earlier, "earlier"), (later, "later"))
    ]
    reasons = [one for one in found if isinstance(one, str)]
    if reasons:
        return report, (
            f"The values were not compared: {'; and '.join(reasons)}. Name the two "
            "results files with --results EARLIER LATER to compare them."
        )
    files = (Path(str(found[0])), Path(str(found[1])))
    try:
        return with_values(
            report, documents, files, row_identity=told, recorded=True
        ), None
    except ValueError as error:
        return report, f"The values were not compared: {error}"


# How many line names a headline count prints before it says how many more.
_NAMED_LINES: Final[int] = 8


def _lines_named(nodes: "Sequence[str]") -> str:
    """Return a few line names, then how many more, or "none"."""
    if not nodes:
        return "none"
    shown = ", ".join(nodes[:_NAMED_LINES])
    more = len(nodes) - _NAMED_LINES
    return shown if more <= 0 else f"{shown} and {more} more"


def _ranked(lines: "Sequence[LineValues]") -> "list[LineValues]":
    """Return the moved lines in the order the comparison page ranks them.

    Moves out of zero first, then the finite relative moves largest first,
    then the moves no ratio describes -- a value of an exact type, a NaN, a
    length -- in the later artifact's order.
    """
    moved = [line for line in lines if line.moved]

    def rank(line: "LineValues") -> tuple[int, float]:
        if line.from_zero:
            return (0, 0.0)
        if line.max_relative is not None:
            return (1, -line.max_relative)
        return (2, 0.0)

    return sorted(moved, key=rank)


def _percent(ratio: float) -> str:
    """Return a relative move as a percentage to three figures, as the page writes it."""
    return f"{ratio * 100:.3g}%"


def _moved_said(line: "LineValues") -> str:
    """Return how far one line moved, and where, as one line of text."""
    parts = [f"{line.policies_moved} of {line.policies_compared} policies"]
    if line.first_period_moved is not None:
        parts.append(f"from period {line.first_period_moved}")
    if line.max_abs is not None:
        parts.append(f"max |change| {_measured(line.max_abs)}")
    worst = line.worst
    if worst is not None:
        where = worst.policy if worst.policy is not None else f"row {worst.row}"
        if worst.period is not None:
            where = f"{where}, period {worst.period}"
        values = f"{worst.to_dict()['before']} → {worst.to_dict()['after']}"
        if line.from_zero:
            parts.append(f"from 0 at {where} ({values})")
        elif line.max_relative is not None:
            parts.append(f"largest {_percent(line.max_relative)} at {where} ({values})")
        else:
            parts.append(f"first at {where} ({values})")
    if line.length_moved is not None:
        length = line.length_moved
        parts.append(
            f"timeline length differs on {length.policies} policies "
            f"({length.policy}: {length.before} → {length.after})"
        )
    if line.within_band:
        parts.append("within the band, indistinguishable from arithmetic (§11.1.12)")
    elif line.within_band is None and line.max_relative is not None:
        parts.append("the band cannot be decided: a value it reads is not in the files")
    return " · ".join(parts)


def _print_values(report: "DiffReport", *, floor: float) -> None:
    """Print what the two runs' numbers did, where the results files were read.

    The headline first, by kind of change -- edited lines that moved and that
    moved no number, inherited lines that moved and whose numbers held, lines
    that moved under definitions that did not, and why -- then every moved
    line, largest relative move first. ``floor`` leaves the smaller moves out
    of the list and says how many; it never reaches the JSON.
    """
    values = report.values
    if values is None:
        return
    head = values.headline()
    rows = values.rows
    on = (
        f"by identity on {', '.join(rows.on)}"
        if rows.matched_by == "identity"
        else "by position, one book in one order"
    )
    before_file, after_file = values.results
    read = (
        "the files the audit files record"
        if before_file.read == "recorded"
        else "the files named"
    )
    console.print(
        f"\n[bold]Values:[/bold] {rows.paired} "
        f"{'policy' if rows.paired == 1 else 'policies'} compared, rows "
        f"matched {escape(on)}"
    )
    console.print(
        f"  read from {Path(before_file.path).name} and {Path(after_file.path).name}, "
        f"{read}",
        markup=False,
    )
    edited, inherited = head["edited"], head["inherited"]
    console.print(
        f"  edited       {len(edited['moved'])} moved; moved no number: "
        f"{_lines_named(edited['moved_no_number'])}",
        markup=False,
    )
    console.print(
        f"  inherited    {len(inherited['moved'])} moved; identity only: "
        f"{_lines_named(inherited['identity_only'])}",
        markup=False,
    )
    unmoved = head["unmoved_definitions"]
    moved_under = [node for nodes in unmoved.values() for node in nodes]
    console.print(
        "  unmoved definitions: "
        + (
            f"{len(moved_under)} moved, the cause the record states: "
            + _causes_said(values)
            if moved_under
            else "no number moved"
        ),
        markup=False,
    )
    if head["within_band"]:
        console.print(
            f"  within the band: {_lines_named(head['within_band'])}", markup=False
        )
    if head["not_carried"]:
        console.print(
            "  not in both results files, so not compared: "
            f"{_lines_named(head['not_carried'])}",
            markup=False,
        )
    console.print(
        f"  policies: {rows.joined.count} joined"
        + (f" ({', '.join(rows.joined.policies)})" if rows.joined.count else "")
        + f", {rows.left.count} left"
        + (f" ({', '.join(rows.left.policies)})" if rows.left.count else ""),
        markup=False,
    )
    if values.periods.reason is not None:
        console.print(Padding(Text(values.periods.reason), (0, 0, 0, 2)))
    unexplained = [
        line.node
        for line in values.lines
        if line.cause == "unexplained" and line.within_band is not True
    ]
    if unexplained:
        console.print(
            Padding(
                Text(
                    f"{_lines_named(unexplained)} moved under definitions that did "
                    "not, beyond the band, over the same book and the same producer: "
                    "nothing in the record explains it. A column written over around "
                    "the frame's own account of it does this. To find the line, run "
                    "the model again from its audit file with gspio run-artifact … "
                    "--every-node and compare that with the model's own run."
                ),
                (1, 0, 0, 2),
            )
        )

    ranked = _ranked(values.lines)
    cut = floor / 100
    shown = [
        line
        for line in ranked
        if line.from_zero or line.max_relative is None or line.max_relative >= cut
    ]
    if shown:
        console.print("\n  [bold]Moved, largest relative move first:[/bold]")
    for line in shown:
        said = line.change or "definition unmoved"
        console.print(f"    {line.node}  ({said})", markup=False)
        console.print(Padding(Text(_moved_said(line)), (0, 0, 0, 6)))
    hidden = len(ranked) - len(shown)
    if hidden:
        console.print(
            f"  {_counted(hidden, 'moved line')} under the floor of {floor}% not shown",
            markup=False,
        )


def _causes_said(values: "ValuesReport") -> str:
    """Return each cause the moved lines carry, with how many, a hole by its name."""
    counted: dict[str, int] = {}
    for line in values.lines:
        if line.cause is None:
            continue
        said = (
            f"hole {', '.join(line.holes)}"
            if line.cause == "hole" and line.holes
            else line.cause
        )
        counted[said] = counted.get(said, 0) + 1
    return "; ".join(f"{said} ({count})" for said, count in counted.items())


def _print_library_moved(line: str | None) -> None:
    """Print the line naming what moved in the library, where it moved."""
    if line is not None:
        console.print(f"  {line}", markup=False)


def _print_source_moved(report: "DiffReport") -> None:
    """Print the lines saying the model's own files moved, where they did.

    On lines of their own and never counted as drift: a reformatted model or
    a comment in a helper module moves the file and no calculation, and the
    fingerprints are what say whether a calculation moved. What the lines give
    a reviewer is that the files they would open are not the ones the earlier
    run recorded.
    """
    moved = report.source
    if moved is None:
        return
    if moved.before != moved.after:
        named = f" {moved.path}" if moved.path else ""
        console.print(
            f"  model source{named} moved: {moved.before} → {moved.after} "
            "(the model file's own bytes; the calculations below say whether any "
            "calculation moved with them)",
            markup=False,
        )
    for module in moved.modules:
        console.print(
            f"  helper module {module.path} moved: {module.before or 'no stamp'} "
            f"→ {module.after or 'no stamp'} (the module's own bytes, stated and "
            "not counted; the calculations below say whether any calculation "
            "moved with them)",
            markup=False,
        )


def _print_results_not_compared(sentence: str | None) -> None:
    """Print the line saying the results files were not compared, where there is one."""
    if sentence is not None:
        console.print()
        console.print(Padding(Text(sentence), (0, 0, 0, 2)))


def _measured(value: float | None) -> str:
    """Return one measured number in a width a column of them lines up in."""
    return "-" if value is None else f"{value:.3g}"


def _rows_matched(report: "CompareReport") -> str:
    """Return how the two files' rows were paired, and on what, as one phrase."""
    on = ", ".join(report.rows_matched_on)
    if report.rows_matched_by == "identity":
        return f"rows matched by identity on {on}"
    if on:
        return f"rows matched by position, {on} in one order on both"
    return "rows matched by position, one book in one order"


def _print_compare_report(before: Path, after: Path, report: "CompareReport") -> None:
    """Print what two runs of one artifact came to, and what that rested on.

    The three things a reader has to know before the lines mean anything:
    which scope the two files were written under, whether they read the same
    book, and whether rows were matched by identity or by position. A
    conformance claim needs the same book; a comparison over two books is
    still a comparison and is printed as one rather than quietly presented as
    the other.
    """
    colour = {"agree": "green", "disagree": "red", "indeterminate": "yellow"}[
        report.verdict
    ]
    mark = {"agree": "✓", "disagree": "✗", "indeterminate": "?"}[report.verdict]
    console.print(
        f"\n[bold {colour}]{mark}[/bold {colour}] {shown(before.name)} and "
        f"{shown(after.name)} {report.verdict}"
    )
    console.print(
        f"  {report.scope} · {_rows_matched(report)} · "
        + ("the same book" if report.same_inputs else "two books"),
        markup=False,
    )
    console.print(f"  {report.before.producer} → {report.after.producer}", markup=False)

    if report.missing:
        console.print(
            f"\n[bold]Not carried:[/bold] {_counted(len(report.missing), 'result')}"
        )
        for node, side in report.missing:
            console.print(f"  {node} · absent from the {side} results", markup=False)

    if not report.lines:
        return
    console.print(f"\n[bold]Lines:[/bold] {_counted(len(report.lines), 'node')}")
    for line in report.lines:
        floor = "strict floor held" if line.strict_floor else "over the strict floor"
        console.print(
            f"  {line.node_id} · max |a-b| {_measured(line.max_abs)} · "
            f"max ratio {_measured(line.max_ratio)} · "
            f"scale {_measured(line.scale)} · {line.verdict} · {floor}",
            markup=False,
        )
        if line.reads_absent:
            bound = (
                ""
                if line.lower_bound is None
                else f"; a scale of {_measured(line.lower_bound)} would decide it"
            )
            console.print(
                f"           reads not in reach: {', '.join(line.reads_absent)}{bound}",
                markup=False,
            )
        if line.exact_class is not None and line.verdict != "agree":
            console.print(
                f"           parted on {line.exact_class}, which is exact",
                markup=False,
            )


def _print_node_status(engine: str, statuses: "Sequence[NodeStatus]") -> None:
    """Print what one engine can do with each node of one artifact.

    The condition travels with the status, never the status alone: "lowered
    off the trace" is true of an operation whose operands are inputs and false
    of the same identifier with a computed operand, and a table stating the
    identifier by itself would be stating a portability that does not hold.
    """
    counted = {"lowered": 0, "lowered-off-trace": 0, "refused": 0}
    console.print(f"\n[bold]On {shown(engine)}:[/bold]")
    for status in statuses:
        counted[status.status] = counted.get(status.status, 0) + 1
        colour = {
            "lowered": "green",
            "lowered-off-trace": "yellow",
            "refused": "red",
        }.get(status.status, "white")
        console.print(
            f"  [{colour}]{status.status:<18}[/{colour}]" + escape(status.node_id)
        )
        if status.condition is not None:
            clause = status.clause or "no clause"
            console.print(
                Padding(Text(f"{status.condition} ({clause})"), (0, 0, 0, 22))
            )
    console.print(
        f"  {_counted(len(statuses), 'node')} read: "
        f"{counted['lowered']} lowered, "
        f"{counted['lowered-off-trace']} lowered off the trace, "
        f"{counted['refused']} refused"
    )


@app.command(
    name="validate",
    help="Check a calculation-graph artifact against its schema and its own structure",
    rich_help_panel="Audit",
)
def validate(
    artifact_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the artifact JSON file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    deep: Annotated[
        bool,
        typer.Option(
            "--deep",
            help="Recompute the artifact's own digests instead of reading them",
            rich_help_panel="Reading Options",
        ),
    ] = False,
    engine: Annotated[
        str | None,
        typer.Option(
            "--engine",
            help=(
                "Read the portability section against this engine. There is no "
                "default: 'can this run somewhere else' is not a question until "
                "somewhere else has a name"
            ),
            rich_help_panel="Reading Options",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Output structured JSON for LLM consumption",
            rich_help_panel="Output Options",
        ),
    ] = False,
    output_file: Annotated[
        Path | None,
        typer.Option(
            "--output-file",
            "-o",
            help="Save the report as JSON to this path",
            rich_help_panel="Output Options",
        ),
    ] = None,
) -> None:
    """Check an artifact against its schema and against its own structure.

    The exit status is the answer, so a pipeline step can branch on it
    without reading anything: [bold]0[/bold] where the artifact may be read,
    [bold]1[/bold] where a finding refuses it, and [bold]2[/bold] where the
    file could not be read at all -- which is a different situation from an
    invalid artifact and is kept apart from it.

    A warning is not a refusal. Something the producer left in a state worth
    mentioning is still a document that means what it says, and the exit
    status stays 0.

    [bold green]Example:[/bold green]
        gspio validate artifact.json
        gspio validate artifact.json --deep
        gspio validate artifact.json --engine duckdb
        gspio validate artifact.json --json
        gspio validate artifact.json --output-file validation.json
    """
    document = _artifact_document(artifact_path)
    report = validate_artifact(document, deep=deep, engine=engine)

    if not json_output:
        _print_validation_report(artifact_path, report)

    payload = report.to_dict()
    refused = not report.ok
    if engine is not None:
        # The reading runs whatever the output format, because the exit status
        # is the answer either way. What the format decides is where it is
        # said: to a terminal, or into the document -- and the document has to
        # carry it, or a stored report and the status beside it would disagree
        # about whether anything refused.
        reading = _read_against_the_engine(document, engine, printing=not json_output)
        payload["engine"] = reading
        refused = bool(reading["refused"]) or refused

    _store_report(payload, json_output=json_output, output_file=output_file)

    if refused:
        raise typer.Exit(_EXIT_REPORTED)


def _read_against_the_engine(
    document: dict[str, Any], engine: str, *, printing: bool
) -> dict[str, Any]:
    """Return what one named engine can do with this artifact, if it is here.

    The portability section above is read against the name whether or not an
    engine of that name is installed, because what it records is what the
    producer claimed. This is the other half: an engine that is here answers
    for itself, node by node, from the same capability the runtime applies --
    so the reading cannot say "lowered" of a form the run would refuse.

    The same facts come back whether or not they were printed, so the stored
    document says exactly what the terminal said and the exit status agrees
    with both. An absent engine is not a refusal: the document is what it is,
    and nothing here read it.
    """
    try:
        found = engine_named(engine)
    except (EngineNotInstalledError, EngineBrokenError) as missing:
        if printing:
            console.print(
                f"\n  No engine named {shown(engine)} is available here; the "
                "portability section was read against the name only."
            )
        return {
            "name": engine,
            "available": False,
            "why": str(missing),
            "nodes": [],
            "refused": 0,
            "read": False,
        }

    statuses = found.validate_tree(document)
    if printing:
        _print_node_status(engine, statuses)
    return {
        "name": engine,
        "available": True,
        "version": getattr(found, "version", None),
        "nodes": [
            {
                "node_id": status.node_id,
                "status": status.status,
                "condition": status.condition,
                "clause": status.clause,
            }
            for status in statuses
        ],
        "refused": sum(1 for status in statuses if status.status == "refused"),
        "read": True,
    }


# The two output options a reading of artifacts offers, declared once and
# named. Typer reads an annotation, so a named one is the same declaration in
# one place rather than two -- which is what a second command offering the
# same two options should cost.
_JsonOutput = Annotated[
    bool,
    typer.Option(
        "--json",
        "-j",
        help="Output structured JSON for LLM consumption",
        rich_help_panel="Output Options",
    ),
]
_ReportFile = Annotated[
    Path | None,
    typer.Option(
        "--output-file",
        "-o",
        help="Save the report as JSON to this path",
        rich_help_panel="Output Options",
    ),
]


@dataclass(frozen=True, slots=True)
class _DiffSide:
    """One side of ``diff``, read: what the report calls it, its text, its document.

    The text is kept because the page carries it: the bytes the comparison
    read, rather than a second reading of a file that may have moved since.
    """

    name: str
    stem: str
    text: str
    document: dict[str, Any]
    label: str
    roots: tuple[Path, ...] = ()


def _diff_side(operand: str) -> _DiffSide:
    """Read one side of ``diff``: a path, or ``git:REV:path`` for a committed file.

    Both reach one gate, so an audit file a revision committed is held to
    exactly what one on disk is held to: text, JSON, and the object an
    artifact is. Every refusal on the way names the side it is about and
    exits 2, the status this command keeps for a comparison it could not make.

    An operand that begins ``git:`` is read from the repository the current
    directory sits in, whatever files sit beside it: what was compared has to
    be plain from the command line. ``./git:...`` names a file of that name.
    """
    if not is_git_operand(operand):
        # Resolved, so a refusal names the file the same way wherever the
        # command was run from.
        path = Path(operand).resolve()
        text = _artifact_text(path)
        document = _artifact_in(text, named=str(path))
        # The page names a file as the command line did, not by its resolved
        # path: a page is passed around, and the path the author typed is the
        # one a reader can follow without the author's directories.
        return _DiffSide(
            path.name,
            path.stem,
            text,
            document,
            label=operand,
            roots=tuple(roots_of(path, document)),
        )
    try:
        committed = read_committed(operand, Path.cwd())
    except CommittedFileError as refused:
        err_console.print(f"[red]{escape(str(refused))}[/red]")
        raise typer.Exit(_EXIT_UNREADABLE) from None
    text = _text_in(committed.data, named=committed.named, committed=committed)
    # A revision's audit file names its results file against the repository's
    # root, and the file itself is on disk if anywhere: a results file is not
    # usually committed. Its checksum decides whether what is there is it.
    toplevel = git_output(Path.cwd(), "rev-parse", "--show-toplevel")
    return _DiffSide(
        committed.name,
        committed.stem,
        text,
        _artifact_in(text, named=committed.named),
        label=committed.named,
        roots=() if toplevel is None else (Path(toplevel),),
    )


@app.command(
    name="diff",
    short_help="Compare two calculation-graph artifacts and report what moved",
    help=(
        "Compare two calculation-graph artifacts and report what moved.\n\n"
        "Each artifact is a path, or git:REV:path for the audit file as revision "
        "REV committed it, read from the repository without a checkout or a "
        "second run of the model:\n\n"
        "  gspio diff git:v2026.Q2:model.audit.json model.audit.json\n\n"
        "The path after the revision is read from the repository's root, as git "
        "show reads it; begin it with ./ to read it from the current directory. "
        "From a subdirectory, a path that names a file both ways is refused, with "
        "the spelling of each."
    ),
    rich_help_panel="Audit",
)
def diff(
    before: Annotated[
        str,
        typer.Argument(
            help="The earlier artifact: a path, or git:REV:path",
            show_default=False,
        ),
    ],
    after: Annotated[
        str,
        typer.Argument(
            help="The later artifact: a path, or git:REV:path",
            show_default=False,
        ),
    ],
    json_output: _JsonOutput = False,
    output_file: _ReportFile = None,
    html: Annotated[
        Path | None,
        typer.Option(
            "--html",
            # Escaped for the reason calc-graph's --html help is.
            help=(
                "Also write one self-contained HTML page carrying both "
                "artifacts, which derives the difference in the page; "
                "needs the gaspatchio\\[viewer] extra"
            ),
            # Resolved for the reason calc-graph's is: the path is written
            # down and printed back, and one that names whichever directory
            # the command happened to run in resolves on nobody else's machine.
            resolve_path=True,
            rich_help_panel="Output Options",
        ),
    ] = None,
    results: Annotated[
        tuple[Path, Path] | None,
        typer.Option(
            "--results",
            help=(
                "The two runs' results files, earlier first, read in place of "
                "the ones the audit files record: which lines' numbers moved, "
                "in how many policies, and by how much"
            ),
            show_default=False,
            rich_help_panel="Results",
        ),
    ] = None,
    no_results: Annotated[
        bool,
        typer.Option(
            "--no-results",
            help="Compare the two audit files alone, reading no results file",
            rich_help_panel="Results",
        ),
    ] = False,
    policy_id_column: Annotated[
        list[str] | None,
        typer.Option(
            "--policy-id-column",
            help=(
                "A column naming a policy in both results files, over whatever "
                "they record; give it again for a second column, such as a "
                "scenario's"
            ),
            rich_help_panel="Results",
        ),
    ] = None,
    floor: Annotated[
        float,
        typer.Option(
            "--floor",
            help=(
                "Leave out of the printed list a moved line whose largest "
                "relative move is under this percentage; the JSON keeps every "
                "line"
            ),
            min=0.0,
            rich_help_panel="Results",
        ),
    ] = 0.0,
) -> None:
    """Compare two artifacts of one model and report what moved.

    Two exports of an untouched model differ, because one of them was written
    later. What this reports is what a valuation committee asks about: which
    calculations were edited, and which numbers can no longer be what they
    were because the data underneath them was re-sourced.

    Where both audit files record the checksum of the results file their run
    wrote, those two are compared as well, and a results file that differs is
    reported under data. Its checksum moves with the library versions and
    platform that wrote the file as well as with its numbers. Where only one
    of the two records one, a line says they were not compared.

    [bold]What moved, and by how much.[/bold] Where both audit files record a
    results file and each is still where it was written, with the checksum
    recorded, the two files are read and the report gains its values: for
    each line the two runs share, whether its numbers moved, in how many
    policies, from which period, the largest move and the policy and period
    it is at. A value has moved when it is unequal; a move inside the
    specification's band (1e-12 of the line's scale) is still listed, and
    labelled as indistinguishable from arithmetic. Edited lines that moved no
    number, and inherited lines whose numbers held, are named. Policies are
    paired by the identity the files record or by [bold]--policy-id-column[/bold],
    and those in only one book are counted as joined or left. Where the files
    cannot be read, a line says why. [bold]--results EARLIER LATER[/bold] names
    two files instead, and [bold]--no-results[/bold] reads none. A line whose
    definition did not move and whose numbers did, beyond the band, with no
    new book and no new producer to explain it, is drift.

    [bold]--html[/bold] writes the same comparison as a page. The page carries
    both documents and derives what moved from them; it is handed no report,
    so what it marks and what this prints are two readings of one definition
    rather than one reading printed twice. A report read as text says which
    columns moved; a page opens one of them and puts the two proofs side by
    side.

    [bold]Either side can be an audit file a past revision committed[/bold],
    written [bold]git:REV:path[/bold]: where a team commits the audit file
    beside the model, the earlier quarter's is read straight out of the
    repository's history, with no checkout and no second run of the model.
    The revision is looked up in the repository the current directory sits
    in, and the path is read from that repository's root, as git show reads
    it; a path that begins ./ or ../ is read from the current directory
    instead. From a subdirectory, a plain path that names a file there too is
    refused rather than read from the root, with the spelling that reads each.
    A file on disk whose name begins git: is named ./git:..., because
    what was compared has to be plain from the command line rather than
    depend on which files sat beside it. A revision git does not know, a path
    it holds no file at, a directory outside any repository and a file there
    that is not an artifact each exit 2 with a sentence naming the revision
    and the path. A Git LFS pointer, at a revision or on disk, is refused as
    one, with the command that fetches the file it stands for. Running an old
    revision's model is another matter: it needs the revision's whole tree,
    which git worktree add gives it, and then [bold]gspio calc-graph[/bold]
    exports it.

    The exit status is the answer: [bold]0[/bold] where nothing the report
    covers moved, [bold]1[/bold] where something did -- calculation or data
    alike, because a run over a replaced in-force file moves no formula and
    still moves every number -- and [bold]2[/bold] where the two could not be
    compared at all, which is not a finding about either model, or two
    results files named with [bold]--results[/bold] could not be read beside
    them, or [bold]--html[/bold] names a page with no place to go, which is
    refused before anything is read or written.

    [bold green]Example:[/bold green]
        gspio diff q1_artifact.json q2_artifact.json
        gspio diff q1_artifact.json q2_artifact.json --results q1.parquet q2.parquet
        gspio diff q1_artifact.json q2_artifact.json --json
        gspio diff q1_artifact.json q2_artifact.json --output-file drift.json
        gspio diff q1_artifact.json q2_artifact.json --html drift.html
        gspio diff git:v2026.Q2:model.audit.json model.audit.json
    """
    if results is not None and no_results:
        err_console.print(
            "[red]--results and --no-results ask for opposite things:[/red] name "
            "the two results files to read, or say to read none."
        )
        raise typer.Exit(_EXIT_UNREADABLE)
    # The page goes into a directory that is there, checked before the report
    # is stored, so a page refused never leaves the report written without it.
    _refuse_an_output_with_no_place(("--html", html))
    earlier = _diff_side(before)
    later = _diff_side(after)

    try:
        report = diff_artifacts(earlier.document, later.document)
    except ValueError as error:
        err_console.print(
            f"[red]These two artifacts cannot be compared:[/red] {shown(error)}"
        )
        raise typer.Exit(_EXIT_UNREADABLE)

    report, unread = _the_values(
        report,
        earlier,
        later,
        named=results,
        skipped=no_results,
        told=policy_id_column or None,
    )

    if not json_output:
        _print_diff_report(
            earlier.name,
            later.name,
            report,
            results_not_compared=_results_not_compared(
                earlier.document, later.document
            ),
            results_moved=_results_file_moved(
                earlier.document, later.document, read=report.values is not None
            ),
            library_moved=_library_moved(earlier.document, later.document),
        )
        _print_values(report, floor=floor)
    if unread is not None:
        # Beside --json, stdout is the report alone, so the sentence is stderr's.
        (err_console if json_output else console).print(
            Padding(Text(unread), (1, 0, 0, 2))
        )
    _store_report(report.to_dict(), json_output=json_output, output_file=output_file)

    if html is not None:
        # The later document first, because it is the one the page's views are
        # drawn from: a reader opens a comparison to look at where the model
        # stands now, with what it was beside it. The two travel as they were
        # read -- a file's text, or the blob a revision holds -- so the seal the
        # page shows is a seal over bytes the reader can take back out of it.
        try:
            html.write_text(
                render_html(
                    later.text,
                    second=earlier.text,
                    title=f"{later.stem} vs {earlier.stem}",
                    label=later.label,
                    second_label=earlier.label,
                    movement=(
                        None
                        if report.values is None
                        else json.dumps(report.values.to_dict(), separators=(",", ":"))
                    ),
                ),
                encoding="utf-8",  # as calc-graph writes its page, and why
            )
        except ViewerNotInstalledError as missing:
            # Escaped before printing, for calc-graph's reason: the sentence
            # names the extra as ``gaspatchio[viewer]`` and rich reads square
            # brackets as markup.
            err_console.print(f"[red]{escape(str(missing) + WROTE_THE_REPORT)}[/red]")
            raise typer.Exit(_EXIT_UNREADABLE)
        # Beside --json, stdout is the report alone, so the notice is stderr's.
        notice = err_console if json_output else console
        notice.print(f"[bold green]Page saved to {shown(html)}[/bold green]")

    if report.drift:
        raise typer.Exit(_EXIT_REPORTED)


@app.command(
    name="sheet",
    short_help="Lay an audit file's policies out as an .xlsx workbook",
    help=(
        "Lay an audit file's policies out as an .xlsx workbook a reviewer "
        "opens in Excel or LibreOffice, with no Python.\n\n"
        "README names the audit file by its digests and says which policy "
        "and why; Timeline has a row per period and a column per per-period "
        "calculation in the order the model made them, each headed by its "
        "formula and tier; Scalars, Nodes, Edges (with the periods each read "
        "reads) and Assumptions follow. A file carrying several policies "
        "gives each its own Timeline sheet. Every number is the double the "
        "audit file holds, written with every digit, and no cell holds a "
        "spreadsheet formula.\n\n"
        "The audit file is a path, or git:REV:path for the file as revision "
        "REV committed it. --results checks the results file the run wrote "
        "against the audit file, and the README says whether it agrees.\n\n"
        "Exit status: 0 written, 1 the audit file's seal does not hold or a "
        "sheet would pass Excel's limits, 2 the audit file could not be read "
        "or -o has no place to write the workbook (its directory does not "
        "exist, or -o names a directory), 3 --policy names no entry of the "
        "file's policy axis."
    ),
    rich_help_panel="Audit",
)
def sheet(
    artifact: Annotated[
        str,
        typer.Argument(
            help="The audit file: a path, or git:REV:path", show_default=False
        ),
    ],
    output_file: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Where to write the workbook; default <audit file name>.xlsx here",
            rich_help_panel="Output Options",
        ),
    ] = None,
    policy: Annotated[
        str | None,
        typer.Option(
            "--policy",
            "-p",
            help=(
                "The one policy to lay out, by the id the audit file names it "
                "under; omitted, every entry of its policy axis"
            ),
        ),
    ] = None,
    results: Annotated[
        Path | None,
        typer.Option(
            "--results",
            help="The results file the run wrote, checked against the audit file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
) -> None:
    """Lay an audit file's policies out as an .xlsx workbook.

    [bold green]Example:[/bold green]
        gspio sheet model.audit.json -o policy.xlsx
        gspio sheet model.audit.json --policy POL-000343 --results results.parquet
        gspio sheet git:v2026.Q2:model.audit.json -o q2_policy.xlsx
    """
    side = _diff_side(artifact)
    target = output_file if output_file is not None else Path(f"{side.stem}.xlsx")
    _refuse_an_output_with_no_place(("--output", target))
    try:
        workbook = render_xlsx(side.document, policy=policy, results=results)
    except _NotOnTheAxisError as refused:
        err_console.print(f"[red]{escape(str(refused))}[/red]")
        raise typer.Exit(_EXIT_REFUSED_SELECTION) from None
    except ValueError as refused:
        err_console.print(f"[red]{escape(str(refused))}[/red]")
        raise typer.Exit(_EXIT_REPORTED) from None
    target.write_bytes(workbook)
    console.print(f"[bold green]Workbook saved to {shown(target)}[/bold green]")


@app.command(
    name="compare",
    help="Compare two runs of one artifact and report whether they agree",
    rich_help_panel="Audit",
)
def compare(
    artifact_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the artifact both results are of",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    before_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the earlier results",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    after_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the later results",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    *,
    policy_id_column: Annotated[
        list[str] | None,
        typer.Option(
            "--policy-id-column",
            help=(
                "A column to pair the two files' rows on, over whatever their "
                "manifests record; give it again for a second column, such as "
                "a scenario's"
            ),
        ),
    ] = None,
    json_output: _JsonOutput = False,
    output_file: _ReportFile = None,
) -> None:
    """Report whether two engines agree on one model, line by line.

    Two finite results agree when their difference is within 1e-12 of the
    line's scale -- the largest magnitude among the node's own values and the
    values of every node it reads, over [bold]that policy's[/bold] whole
    timeline. A fixed floor cannot serve both a closing balance struck from
    operands near 17,000 and one struck from operands near 1, and this is
    what tells them apart. The fixed floor is printed beside the verdict
    anyway, as the strict floor -- within 1e-10 plus 1e-12 of the reference
    value, the same on every line -- so a reviewer who has compared runs by
    it before has that number too; it does not decide the verdict.

    [bold]Three verdicts, not two.[/bold] The scale needs the reads, and a
    final-schema file carries only the model's own schema. A line that passes
    the reduced test would pass any larger scale too, so that is agreement; a
    line that fails it with a read absent is undecided, printed with the
    scale those reads would have to supply. Write both sides with
    [bold]--every-node[/bold] and the full rule applies.

    The exit status is the answer: [bold]0[/bold] agree, [bold]1[/bold]
    disagree, [bold]4[/bold] undecided, and [bold]2[/bold] where the two
    could not be compared at all.

    [bold]Rows are paired by the identity the files record[/bold] -- the
    policy-id column, and the scenario column on a scenario run -- or by the
    columns [bold]--policy-id-column[/bold] names. By position only where the
    two show one order: the column one side records is in the same order on
    the other, or both read one book. Anything else is refused, because a
    pairing by position that is wrong still gives a verdict.

    [bold green]Example:[/bold green]
        gspio compare artifact.json polars.parquet jax.parquet
        gspio compare artifact.json polars.parquet jax.parquet --json
        gspio compare artifact.json q1.parquet q1-resorted.parquet --policy-id-column point_id
    """
    document = _artifact_document(artifact_path)

    frames: dict[str, pl.DataFrame] = {}
    manifests: dict[str, ResultManifest] = {}
    for side, path in (("before", before_path), ("after", after_path)):
        try:
            frames[side] = pl.read_parquet(path)
            manifests[side] = read_manifest(path)
        except Exception as error:
            err_console.print(
                f"[red]{shown(path)} is not a result this can read:[/red] "
                f"{shown(error)}"
            )
            raise typer.Exit(_EXIT_UNREADABLE)

    try:
        report = compare_results(
            document,
            frames["before"],
            frames["after"],
            before_manifest=manifests["before"],
            after_manifest=manifests["after"],
            row_identity=policy_id_column or None,
        )
    except ValueError as error:
        err_console.print(
            f"[red]These two results cannot be compared:[/red] {escape(str(error))}"
        )
        raise typer.Exit(_EXIT_UNREADABLE)

    if not json_output:
        _print_compare_report(before_path, after_path, report)
    _store_report(report.to_dict(), json_output=json_output, output_file=output_file)

    if report.verdict == "disagree":
        raise typer.Exit(_EXIT_REPORTED)
    if report.verdict == "indeterminate":
        raise typer.Exit(_EXIT_INDETERMINATE)


# How each outcome is marked on a terminal, beside the word that says it.
_OUTCOME_MARKS: Final[dict[str, str]] = {
    "agree": "[green]✓[/green]",
    "disagree": "[red]✗[/red]",
    "indeterminate": "[yellow]?[/yellow]",
    "not_asked": "[dim]-[/dim]",
}

# How each outcome reads on a terminal. The report and its JSON carry the
# tokens compare uses; a person reads a sentence.
_OUTCOME_SAID: Final[dict[str, str]] = {
    "agree": "agrees",
    "disagree": "differs",
    "indeterminate": "could not be checked",
    "not_asked": "not asked",
}


def _print_verification_report(path: Path, report: "VerificationReport") -> None:
    """Print what the checks come to, then each check on its own line.

    The first line names every check that differs, because that is what the
    status is about. Each check then says what it compared in the library's
    own words: a second wording would be a second thing to keep true.
    """
    differing = [check.name for check in report.checks if check.outcome == "disagree"]
    unchecked = [
        check.name for check in report.checks if check.outcome == "indeterminate"
    ]
    if differing:
        console.print(
            f"\n[bold red]✗[/bold red] {shown(path.name)} does not match: "
            f"{', '.join(map(shown, differing))}"
        )
    elif unchecked:
        console.print(
            f"\n[bold yellow]?[/bold yellow] Nothing differs from "
            f"{shown(path.name)}, and {', '.join(map(shown, unchecked))} could not "
            "be checked"
        )
    else:
        console.print(
            f"\n[bold green]✓[/bold green] Every check asked of "
            f"{shown(path.name)} agrees"
        )
    for check in report.checks:
        said, detail = _OUTCOME_SAID[check.outcome], check.detail
        if check.outcome == "not_asked":
            # "model_points  not asked" beside a --model-points the command was
            # given read as a flag ignored. Every line not asked opens with
            # the sentence saying why, so that sentence is the line's own.
            why, detail = _why_not_asked(detail)
            said = f"{said}: {escape(why)}"
        console.print(
            f"\n  {_OUTCOME_MARKS[check.outcome]} [bold]{shown(check.name)}[/bold]  "
            f"{said}  ({shown(check.against)})"
        )
        # Text rather than markup, and padded, as validate prints a finding:
        # a detail names files and digests, and runs to several lines.
        if detail:
            console.print(Padding(Text(detail), (0, 0, 0, 4)))


def _why_not_asked(detail: str) -> tuple[str, str]:
    """Split a line not asked into the sentence saying why and the rest.

    The library opens every such detail with one short sentence --
    "No results file was given.", "The book check decides." -- and the rest,
    where there is any, says what was found beside it.
    """
    why, _, rest = detail.partition(". ")
    why = why.removesuffix(".")
    return why[:1].lower() + why[1:], rest


_FILES_TO_CHECK = "Files to Check"


@app.command(
    name="verify",
    short_help=(
        "Check results, policy data, a model source and assumption tables "
        "against the audit file that records them"
    ),
    help=(
        "Check results, policy data, a model source with the modules it "
        "imports, and assumption tables against the audit file that records "
        "them.\n\n"
        "These checks decide, and one that cannot be made because the audit "
        "file records nothing to check it against is indeterminate:\n"
        "  seal: the audit file against its own document_digest.\n"
        "  results: the results file's sha256 against model.results.\n"
        "  book: the policy data's content against book.digest, where the "
        "audit file states one.\n"
        "  model_points: the policy data file's stamp, its sha256 against "
        "model.model_points, which decides in the book's place and only "
        "where no book digest is stated. It is never indeterminate: where "
        "neither is recorded, book is.\n"
        "  source_sha: the model source's sha256 against model.source_sha.\n"
        "  graph: given --model, the graph rebuilt from the files in hand "
        "against graph_fingerprint. The model is imported and run over "
        "--model-points (through --scenarios for a scenario plan's record) "
        "in a fresh interpreter, uncollected, as calc-graph builds it. A "
        "differing graph disagrees whatever the other lines say, naming each "
        "line whose own calculation moved, with its formula and line: a value "
        "read from a parameter file, a config, an environment variable or a "
        "module outside the model's folder enters there. The verdict holds in "
        "this environment. A model that cannot be rebuilt here, no "
        "--model-points, or a line that hands the engine a Python function or "
        "a compiled plugin is indeterminate, naming why.\n"
        "  scenarios: the scenario plan's run script against "
        "model.scenarios.\n"
        "  modules: each local module the model imports, the file of that "
        "name beside the model given, its sha256 against model.modules. "
        "model.modules is read off the import statements, so where the model "
        "or a module of it loads code by path (spec_from_file_location, "
        "exec_module, import_module, run_path, exec), the line names each "
        "call, file:line, and is indeterminate: that code could not be "
        "checked.\n"
        "  holes: the audit file's holes section, read wherever --model, "
        "--model-points or --assumptions is given. A column the record cannot "
        "account for reached it by name only, so what made its values is held "
        "by no check: the line names each hole and the columns resting on it, "
        "and is indeterminate. An empty section agrees.\n"
        "  assumptions: one line per recorded table, the file found for it "
        "read as that table, its fingerprint against the entry's, and one line "
        "that agrees where the audit file records none. A table the "
        "audit file records the model handed a frame rather than a file's path, "
        "with no file named for it, is not_asked. A difference disagrees only "
        "where the audit file names the file the table was a plain read of; "
        "a table whose recipe reshaped what it read, whose file is not found "
        "or cannot be read as it, or that was built from a frame and reads "
        "differently from the file matched to it, is indeterminate. Each join "
        "the model made has a line of its own, under the record's name for "
        "it (join:<digits>): the file given whose content is the joined frame "
        "agrees, and none doing so is indeterminate, never disagree.\n\n"
        "These add evidence: agree or disagree where there is something to "
        "compare, not_asked where there is not:\n"
        "  results_manifest: the model fingerprint and book digest the "
        "results file's own manifest states.\n"
        "  git: the HEAD of the checkout the model sits in, against "
        "model.git. Where the audit file says git could not state the "
        "revision, it is indeterminate, naming why, and holds nothing open.\n"
        "  versions: the library versions producer.versions records, against "
        "this process's and, given --results, the results file's manifest. "
        "It needs no file, and moves no exit status whatever it says: a "
        "library that moved is stated, and the files are decided above.\n\n"
        "A recorded dirty tree moves no exit status. git counts untracked "
        "files, so a results file written into the repository makes most "
        "exports dirty; the git line says so, and source_sha pins the model "
        "file itself.\n\n"
        "--assumptions takes a file or a directory of them, and can be given "
        "more than once. A table is found by the file the audit file records "
        "it was read from, else by its own name (NAME.parquet, NAME.csv); "
        "NAME=FILE names the file for table NAME, or for a join under its "
        "recorded name.\n\n"
        "Exit status, the first that applies: 2 a file could not be read, 1 a "
        "check other than versions disagrees, 4 a check that decides is "
        "indeterminate, 0 every check asked for agrees. --json writes each check as its name, what "
        "it is held against, its outcome and its detail."
    ),
    rich_help_panel="Audit",
)
def verify(
    artifact_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the audit file, the artifact JSON an export wrote",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    *,
    results: Annotated[
        Path | None,
        typer.Option(
            "--results",
            help=(
                "A results file. Its sha256 against model.results decides; its "
                "own result manifest, where it carries one, adds evidence"
            ),
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            rich_help_panel=_FILES_TO_CHECK,
        ),
    ] = None,
    model_points: Annotated[
        Path | None,
        typer.Option(
            "--model-points",
            help=(
                "A policy data file, .parquet or .csv. Its content against "
                "book.digest decides; where the audit file states no book "
                "digest, the file's own stamp against model.model_points "
                "decides instead"
            ),
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            rich_help_panel=_FILES_TO_CHECK,
        ),
    ] = None,
    model: Annotated[
        Path | None,
        typer.Option(
            "--model",
            help=(
                "A model source file. Its sha256 against model.source_sha "
                "decides, and so does each local module it imports, the file "
                "beside it against model.modules; the HEAD of the git checkout "
                "it sits in, where model.git records a revision, adds evidence"
            ),
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            rich_help_panel=_FILES_TO_CHECK,
        ),
    ] = None,
    assumptions: Annotated[
        list[str] | None,
        typer.Option(
            "--assumptions",
            help=(
                "An assumption table file, .parquet or .csv, or a directory of "
                "them; repeat for more. Each table the audit file records is "
                "found by the file it records the table read from, else by "
                "the table's name, and read as that table; its fingerprint "
                "against the entry's decides. NAME=FILE names the file for "
                "table NAME"
            ),
            rich_help_panel=_FILES_TO_CHECK,
        ),
    ] = None,
    scenarios: Annotated[
        Path | None,
        typer.Option(
            "--scenarios",
            help=(
                "The scenario plan's run script, for a scenario plan's audit "
                "file. Its sha256 against model.scenarios decides, and with "
                "--model the graph is rebuilt through the plan"
            ),
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            rich_help_panel=_FILES_TO_CHECK,
        ),
    ] = None,
    json_output: _JsonOutput = False,
    output_file: _ReportFile = None,
) -> None:
    """Check that the files in hand are the ones an audit file records.

    Is this file of results the one the model in front of you produced? The
    audit file records the evidence, and this reads it back: each file you
    name is held against the member that records it, one check per line.

    These checks decide:
    [bold]seal[/bold]: the audit file against its own document_digest.
    [bold]results[/bold]: the results file's sha256 against model.results.
    [bold]book[/bold]: the policy data's content against book.digest, where
    the audit file states one -- the same policies in another file are the
    same book.
    [bold]model_points[/bold]: the policy data file's stamp, its sha256
    against model.model_points, which decides in the book's place and only
    where no book digest is stated; beside a book digest it says whether the
    bytes match, for information. It is never indeterminate: where neither
    is recorded, book is.
    [bold]source_sha[/bold]: the model source's sha256 against
    model.source_sha.
    [bold]graph[/bold]: given --model, the graph the files in hand build,
    against graph_fingerprint. A file's sha256 says whether the file moved,
    not whether the numbers did: a scalar read with .item() from a parameter
    file, a JSON config, an environment variable, a module imported through
    sys.path from outside the model's folder or a scenario plan's shock factor
    each moves a formula while every recorded stamp agrees. So the model is
    imported and run over --model-points -- through the plan --scenarios
    names, for a scenario plan's record -- in a fresh interpreter, without
    collecting, as calc-graph builds it, and its graph fingerprinted. A graph
    that differs disagrees, whatever the other lines say, naming each line
    whose own calculation moved, with its formula and where it was written.
    The verdict is relative to this environment: the model's own code runs,
    with this Python, its packages and its environment variables, and needs
    the files the model reads where it reads them. A model that cannot be
    rebuilt here, a rebuild with no --model-points, and a line handing the
    engine a Python function (map_batches) or a compiled plugin -- whose body
    no fingerprint reads -- are indeterminate, named. A compiled rollforward
    enters the graph only by its identity, so a machine the file publishes
    that does not hash to it -- a floor or an operation edited after export
    and resealed -- disagrees first, naming the compilation.
    [bold]scenarios[/bold]: the scenario plan's run script, its sha256
    against model.scenarios.
    [bold]modules[/bold]: each local module the model imports -- the file
    of that name beside the model you name, which is the file running it
    would import -- its sha256 against model.modules. An edited helper fails
    as an edited model does. model.modules is read off the import
    statements, so a helper loaded by path -- spec_from_file_location,
    exec_module, import_module, run_path, exec -- is not on the record: the
    line names each such call as file:line and is indeterminate, rather
    than agreeing with nothing checked.
    [bold]holes[/bold]: the audit file's holes section, read wherever
    --model, --model-points or --assumptions is given. A column the record
    cannot account for -- a file joined after collect(), a write straight
    into the frame's query plan, a calculation on another frame -- reached
    it by name only, so what made its values is held by no check: the line
    names each hole, its reason and the columns resting on it, and is
    indeterminate.
    An empty section agrees.
    [bold]assumptions[/bold]: one line per assumption table the audit file
    records -- one line that agrees where it records none, since nothing
    recorded is nothing to check. The table is found among the files and
    directories you name,
    by the file the audit file records it was read from or else by its own
    name, and read as that table -- through its recorded keys and answer
    column, as Table reads it -- to the fingerprint Table.fingerprint()
    gives. A table the audit file records the model handed a frame rather
    than a file's path, with no file named for it, is not_asked: there is no file
    to hold it against. A difference disagrees only where the audit file
    names the file the table was a plain read of. A table whose recipe
    reshaped what it read (a column renamed, cast, melted, set or computed)
    is never read back from a file; one whose file is not found or cannot be
    read as it, or one built from a frame that reads differently from the
    file matched to it -- a filter in code and an edit to the file read
    alike -- is indeterminate. Each join the model made has a line of its
    own, under the record's name for it (join:<digits>): the file given
    whose content is the frame the model joined agrees, and none doing so is
    indeterminate -- the record names the frame's content, not a file.
    NAME=FILE names the file for table NAME, or for a join under its
    recorded name.

    These add evidence beside them, where there is some:
    [bold]results_manifest[/bold]: the model fingerprint and the book digest
    the results file's own manifest states, where it carries one.
    [bold]git[/bold]: the HEAD of the checkout the model sits in, where
    model.git records a revision, with the recorded dirty state said. A
    recorded dirty tree moves no exit status: git counts untracked files,
    so a results file written into the repository makes most exports dirty,
    and source_sha pins the model file itself. Where the audit file says
    git could not state the revision -- no git, a refused directory, no
    answer in time -- the line is indeterminate, naming git's reason, and
    holds nothing open.
    [bold]versions[/bold]: the library versions the audit file records
    produced its values -- core, extension, Polars, Python, the platform,
    the extension's sha256 and each installed package the model imports --
    against what this process runs, and, given --results, against the
    results file's own manifest, since one run states one set. It tells you
    whether re-running here would use the same library. It needs no file
    and moves no exit status, whatever it finds.

    Each check is agree, or disagree with both values named -- the words
    compare uses, and the same exit statuses. A check that decides and has
    nothing recorded to check against is indeterminate; a check that adds
    evidence and has nothing to compare is not_asked, as is any check whose
    file was not given. Every file checked is one you name, one in a
    directory you name, or a module beside the model file you name: a path
    the audit file records is printed and never opened.

    The exit status is the answer, and the first that applies wins:
    [bold]2[/bold] where a file could not be read, [bold]1[/bold] where a
    check other than versions disagrees, [bold]4[/bold] where a check that
    decides is indeterminate, and [bold]0[/bold] where every check asked for
    agrees. A check not asked moves nothing.

    [bold green]Example:[/bold green]
        gspio verify model.audit.json --results results.parquet
        gspio verify model.audit.json --model-points model_points.parquet
        gspio verify model.audit.json --model model.py --json
        gspio verify model.audit.json --model model.py --model-points model_points.parquet
        gspio verify sweep.audit.json --model model.py --model-points model_points.parquet --scenarios run_scenarios.py
        gspio verify model.audit.json --results results.parquet --model model.py
        gspio verify model.audit.json --assumptions assumptions/
        gspio verify model.audit.json --assumptions lapse=data/lapse_2026.csv
        gspio verify model.audit.json --results results.parquet -o verification.json
    """
    document = _artifact_document(artifact_path)
    try:
        report = verify_artifact(
            document,
            results=results,
            model_points=model_points,
            model=model,
            assumptions=assumptions,
            scenarios=scenarios,
        )
    except (OSError, ValueError) as unread:
        # Before any check is printed: a verdict reached over a file that
        # could not be read is not a verdict, and 1 would say it was.
        err_console.print(f"[red]{escape(str(unread))}[/red]")
        raise typer.Exit(_EXIT_UNREADABLE) from None

    if not json_output:
        _print_verification_report(artifact_path, report)
    _store_report(report.to_dict(), json_output=json_output, output_file=output_file)

    if report.verdict == "disagree":
        raise typer.Exit(_EXIT_REPORTED)
    if report.verdict == "indeterminate":
        raise typer.Exit(_EXIT_INDETERMINATE)


# The two options docs and knowledge share for how much of each result to print.
_MaxChars = Annotated[
    int,
    typer.Option(
        "--max-chars",
        help="Per-result text budget in characters; a longer text keeps a "
        "window around the first query match, with a marker naming --full. "
        "0 = unlimited.",
        min=0,
        rich_help_panel="Output Mode",
    ),
]
_FullTexts = Annotated[
    bool,
    typer.Option(
        "--full",
        help="Return complete result texts and keep near-duplicate hits "
        "(skips all client-side trimming).",
        rich_help_panel="Output Mode",
    ),
]


def _version_kwargs(docs_version: str | None) -> dict[str, str]:
    """``version=`` for the client only when --docs-version was given.

    Left out, the client asks for the installed gaspatchio's docs itself.
    """
    return {} if docs_version is None else {"version": docs_version}


def _say_version_note(note: str | None) -> None:
    """Say on stderr when the docs searched are not the version asked for.

    The JSON carries the same note for a reader of stdout.
    """
    if note:
        err_console.print(f"[yellow]{escape(note)}[/yellow]")


def _print_search(
    search: postprocess.SearchResponse,
    query: str,
    *,
    full: bool,
    max_chars: int,
    fallback_status: int | None,
    unmatched_note: str | None = None,
) -> None:
    """Print a search's results as the JSON the two search commands answer with.

    Trimmed unless asked for ``--full``. Where an answer was asked for and the
    API could not give one, the notice is said and the response notes it --
    here, once the fallback search has succeeded: printed earlier it would
    promise results that a failed search then never delivers. Where the search
    found nothing and ``unmatched_note`` says why, that is said on stderr and
    noted on the response too.
    """
    if not full:
        search = postprocess.trimmed(search, query, max_chars)
    if fallback_status is not None:
        _print_answer_fallback_notice(fallback_status)
        search = search.model_copy(
            update={"note": _answer_fallback_note(fallback_status)},
        )
    if unmatched_note is not None and not search.results:
        err_console.print(f"[yellow]{escape(unmatched_note)}[/yellow]")
        notes = [note for note in (search.note, unmatched_note) if note]
        search = search.model_copy(update={"note": " ".join(notes)})
    # Output JSON directly for LLM consumption
    print(search.model_dump_json(indent=2))


@app.command(
    name="docs",
    help="Search Gaspatchio framework documentation (API, accessors, examples). "
    "Use filters to narrow results. Run multiple searches to explore different angles.",
    rich_help_panel="Knowledge Discovery",
)
def docs(
    query: Annotated[
        str,
        typer.Argument(
            help="Search query - natural language question or keywords. "
            "Examples: 'cumulative survival', 'how to discount cash flows', "
            "'projection.previous_period'",
        ),
    ],
    answer: Annotated[
        bool,
        typer.Option(
            "--answer",
            "-a",
            help="(Use sparingly) Generate an answer using RAG instead of returning "
            "search results. Prefer search results - they let you evaluate multiple "
            "sources in your context.",
            rich_help_panel="Output Mode",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Number of results to return (default: 10 for search, 5 for answer)",
            min=1,
            max=50,
            rich_help_panel="Search Options",
        ),
    ] = 10,
    search_type: Annotated[
        str,
        typer.Option(
            "--search-type",
            "-s",
            help="Search algorithm: 'hybrid' (semantic + keyword, best for most queries), "
            "'semantic' (meaning-based, good for concepts), "
            "'keyword' (exact matching, good for function names)",
            rich_help_panel="Search Options",
        ),
    ] = "hybrid",
    content_type: Annotated[
        list[str] | None,
        typer.Option(
            "--content-type",
            "-t",
            help="Filter by content type. Can specify multiple times. "
            "Types: 'code_example' (working code), 'overview' (docstrings/descriptions), "
            "'when_to_use' (usage guidance), 'parameters' (function signatures)",
            rich_help_panel="Filters",
        ),
    ] = None,
    max_chars: _MaxChars = 1500,
    full: _FullTexts = False,
    docs_version: Annotated[
        str | None,
        typer.Option(
            "--docs-version",
            help="Search the docs of this gaspatchio version instead of the "
            "installed one, e.g. 0.9.0. The JSON's 'version' says which docs "
            "were searched.",
            rich_help_panel="Filters",
        ),
    ] = None,
) -> None:
    """Search Gaspatchio framework documentation.

    Searches the docs for the gaspatchio installed here, so an answer names
    the API this install has; --docs-version asks for another version's.

    [bold cyan]SEARCH STRATEGY:[/bold cyan]
    Run multiple targeted searches rather than one broad query.
    Each search returns different relevant excerpts you can evaluate.

    [bold cyan]WHAT YOU CAN FIND:[/bold cyan]
    • [green]API Methods[/green] - ActuarialFrame operations, column methods
    • [green]Accessors[/green] - .projection, .excel, .finance, .mortality, .date
    • [green]Code Examples[/green] - Working patterns from real models
    • [green]Function Signatures[/green] - Parameters, return types, defaults

    [bold cyan]CONTENT TYPES (-t filter):[/bold cyan]
    • [yellow]code_example[/yellow] - Executable code snippets (use for implementation)
    • [yellow]overview[/yellow] - Docstrings and descriptions (use for understanding)
    • [yellow]when_to_use[/yellow] - Usage guidance (use for choosing methods)
    • [yellow]parameters[/yellow] - Function signatures (use for API details)

    [bold cyan]SEARCH TYPES (-s):[/bold cyan]
    • [yellow]hybrid[/yellow] - Best for most queries (combines semantic + keyword)
    • [yellow]semantic[/yellow] - When searching by concept/meaning
    • [yellow]keyword[/yellow] - When searching for exact function/class names

    [bold green]EXAMPLES:[/bold green]
      [dim]# Find code examples for cumulative survival[/dim]
      gspio docs "cumulative survival" -t code_example

      [dim]# Search for all projection accessor methods[/dim]
      gspio docs "projection accessor" -n 20

      [dim]# Find exact function by name[/dim]
      gspio docs "previous_period" -s keyword

      [dim]# Get usage guidance for Excel functions[/dim]
      gspio docs "excel pv npv" -t when_to_use

      [dim]# Multiple searches to understand a feature[/dim]
      gspio docs "time shifting" -t overview        # understand concept
      gspio docs "time shifting" -t code_example    # see implementation

      [dim]# Generate a summary answer (use sparingly)[/dim]
      gspio docs "how do I discount cash flows?" --answer
    """
    try:
        client = KnowledgeAPIClient()
        fallback_status: int | None = None
        if answer:
            try:
                result = client.answer_docs(
                    query,
                    limit=limit,
                    search_type=search_type,
                    content_type=content_type,
                    **_version_kwargs(docs_version),
                )
            except APIConnectionError as e:
                # A server error on /answer means the synthesis path is down,
                # not the retrieval surface — degrade to search (#119). With
                # no status at all the whole API is unreachable: fail loudly.
                if e.status_code is None or e.status_code < _HTTP_SERVER_ERROR:
                    raise
                fallback_status = e.status_code
            else:
                _say_version_note(result.version_note)
                print(result.model_dump_json(indent=2))
                return
        search = client.search_docs(
            query,
            limit=limit,
            search_type=search_type,
            content_type=content_type,
            **_version_kwargs(docs_version),
        )
        _say_version_note(search.version_note)
        _print_search(
            search,
            query,
            full=full,
            max_chars=max_chars,
            fallback_status=fallback_status,
        )
    except APIConnectionError as e:
        err_console.print(f"[red]Error:[/red] {shown(e)}")
        raise typer.Exit(1)


@app.command(
    name="knowledge",
    help="Search actuarial knowledge base (IFRS 17, Solvency II, mortality, regulations). "
    "Use filters to search by jurisdiction, document type, or tags.",
    rich_help_panel="Knowledge Discovery",
)
def knowledge(
    query: Annotated[
        str,
        typer.Argument(
            help="Search query - natural language question or keywords. "
            "Examples: 'CSM amortization', 'risk adjustment calculation', "
            "'mortality improvement factors'",
        ),
    ],
    answer: Annotated[
        bool,
        typer.Option(
            "--answer",
            "-a",
            help="(Use sparingly) Generate an answer using RAG instead of returning "
            "search results. Prefer search results - they let you evaluate multiple "
            "regulatory sources in your context.",
            rich_help_panel="Output Mode",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Number of results to return (default: 10 for search, 5 for answer)",
            min=1,
            max=50,
            rich_help_panel="Search Options",
        ),
    ] = 10,
    search_type: Annotated[
        str,
        typer.Option(
            "--search-type",
            "-s",
            help="Search algorithm: 'hybrid' (semantic + keyword, best for most queries), "
            "'semantic' (meaning-based, good for concepts), "
            "'keyword' (exact matching, good for specific terms)",
            rich_help_panel="Search Options",
        ),
    ] = "hybrid",
    retrieval_mode: Annotated[
        str,
        typer.Option(
            "--retrieval-mode",
            "-r",
            help="How to retrieve content: 'chunks' (document sections, default), "
            "'summaries' (document summaries), 'hierarchical' (parent-child chunks)",
            rich_help_panel="Search Options",
        ),
    ] = "chunks",
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tag",
            "-T",
            help="Filter by tag; a result with any one of the tags given "
            "matches. Can specify multiple times. Tags: 'capital', 'gaap', "
            "'general', 'health', 'ifrs', 'ifrs17', 'life', 'naic', 'property', "
            "'reserve', 'solvency'. Case does not matter.",
            rich_help_panel="Filters",
        ),
    ] = None,
    jurisdiction: Annotated[
        str | None,
        typer.Option(
            "--jurisdiction",
            "-j",
            help="Filter by jurisdiction: 'international', 'eu', 'us', 'uk', "
            "'au'. Case does not matter.",
            rich_help_panel="Filters",
        ),
    ] = None,
    doc_type: Annotated[
        str | None,
        typer.Option(
            "--doc-type",
            "-d",
            help="Filter by document type, in any case: 'standard', 'regulation' "
            "(regulatory text), 'guidance' (implementation guides), 'practice-note' "
            "(practice notes), 'comment' (comment letters and responses)",
            rich_help_panel="Filters",
        ),
    ] = None,
    max_chars: _MaxChars = 1500,
    full: _FullTexts = False,
) -> None:
    """Search the actuarial knowledge base.

    [bold cyan]SEARCH STRATEGY:[/bold cyan]
    Use filters to narrow results to relevant jurisdictions and document types.
    Run multiple targeted searches to explore regulatory requirements from
    different angles. Combine tag and jurisdiction filters for precision; two
    tags widen a search, since a result with either one matches. A filter
    value the index does not use matches nothing, and the CLI says so.

    [bold cyan]KNOWLEDGE DOMAINS:[/bold cyan]
    • [green]IFRS 17[/green] - Insurance contracts standard (CSM, BBA, PAA, VFA)
    • [green]Solvency II[/green] - EU insurance regulation (SCR, MCR, technical provisions)
    • [green]US GAAP[/green] - US accounting standards (LDTI, targeted improvements)
    • [green]Mortality/Morbidity[/green] - Life tables, improvement factors, selection
    • [green]Assumptions[/green] - Lapse, expense, inflation, discount rates

    [bold cyan]TAGS (-T filter, any case):[/bold cyan]
    • [yellow]ifrs17[/yellow], [yellow]ifrs[/yellow], [yellow]gaap[/yellow] - Accounting standards
    • [yellow]solvency[/yellow], [yellow]capital[/yellow], [yellow]naic[/yellow] - Prudential regulation and capital
    • [yellow]life[/yellow], [yellow]health[/yellow], [yellow]property[/yellow], [yellow]general[/yellow] - Line of business
    • [yellow]reserve[/yellow] - Reserving
    Topics such as mortality, lapse, CSM or risk adjustment are not tags:
    put them in the query.

    [bold cyan]JURISDICTIONS (-j filter, any case):[/bold cyan]
    • [yellow]international[/yellow] - IASB/IAA standards
    • [yellow]eu[/yellow] - European Union (EIOPA, Solvency II)
    • [yellow]us[/yellow] - United States (NAIC, FASB, state regulations)
    • [yellow]uk[/yellow] - United Kingdom (PRA, FCA, IFoA)
    • [yellow]au[/yellow] - Australia (APRA, Actuaries Institute)

    [bold cyan]DOCUMENT TYPES (-d filter, any case):[/bold cyan]
    • [yellow]standard[/yellow] - Official standards
    • [yellow]regulation[/yellow] - Regulatory text
    • [yellow]guidance[/yellow] - Implementation guidance
    • [yellow]practice-note[/yellow] - Practice notes
    • [yellow]comment[/yellow] - Comment letters and responses

    [bold cyan]RETRIEVAL MODES (-r):[/bold cyan]
    • [yellow]chunks[/yellow] - Document sections (default, most detail)
    • [yellow]summaries[/yellow] - Document-level summaries (for overview)
    • [yellow]hierarchical[/yellow] - Parent context with child details

    [bold green]EXAMPLES:[/bold green]
      [dim]# Search IFRS 17 CSM guidance[/dim]
      gspio knowledge "CSM amortization" -T ifrs17

      [dim]# Find EU-specific Solvency II requirements[/dim]
      gspio knowledge "technical provisions" -j eu -T solvency

      [dim]# Search life mortality tables and improvement factors[/dim]
      gspio knowledge "mortality improvement" -T life -n 15

      [dim]# Get official standards only[/dim]
      gspio knowledge "risk adjustment" -d standard -T ifrs17

      [dim]# Compare jurisdictions with multiple searches[/dim]
      gspio knowledge "discount rates" -j eu     # EU approach
      gspio knowledge "discount rates" -j us     # US approach

      [dim]# Get document summaries for broad understanding[/dim]
      gspio knowledge "IFRS 17 overview" -r summaries

      [dim]# Generate a summary answer (use sparingly)[/dim]
      gspio knowledge "what is the difference between BBA and PAA?" --answer
    """
    unmatched_note = postprocess.unmatched_filters_note(
        tags=tags, jurisdiction=jurisdiction, doc_type=doc_type
    )
    try:
        client = KnowledgeAPIClient()
        fallback_status: int | None = None
        if answer:
            try:
                result = client.answer_knowledge(
                    query,
                    limit=limit,
                    search_type=search_type,
                    retrieval_mode=retrieval_mode,
                    tags=tags,
                    jurisdiction=jurisdiction,
                    doc_type=doc_type,
                )
            except APIConnectionError as e:
                # A server error on /answer means the synthesis path is down,
                # not the retrieval surface — degrade to search (#119). With
                # no status at all the whole API is unreachable: fail loudly.
                if e.status_code is None or e.status_code < _HTTP_SERVER_ERROR:
                    raise
                fallback_status = e.status_code
            else:
                if not result.sources and unmatched_note is not None:
                    # An answer drawn from no source is the model's own
                    # knowledge, not the index's: say which filter emptied it.
                    err_console.print(f"[yellow]{escape(unmatched_note)}[/yellow]")
                    result = result.model_copy(update={"note": unmatched_note})
                print(result.model_dump_json(indent=2))
                return
        search = client.search_knowledge(
            query,
            limit=limit,
            search_type=search_type,
            retrieval_mode=retrieval_mode,
            tags=tags,
            jurisdiction=jurisdiction,
            doc_type=doc_type,
        )
        _print_search(
            search,
            query,
            full=full,
            max_chars=max_chars,
            fallback_status=fallback_status,
            unmatched_note=unmatched_note,
        )
    except APIConnectionError as e:
        err_console.print(f"[red]Error:[/red] {shown(e)}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
