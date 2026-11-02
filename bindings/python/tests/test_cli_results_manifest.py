# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A results file the CLI writes says what produced it, without being asked.

A reviewer handed a results file asks: same model, same data -- would the
library this ran on give the same answer? The file can only take that
question if it names the model (its fingerprint), the book (its content
digest) and the library versions. ``gspio run-model --results`` writes them
into the Parquet footer as a result manifest, beside the columns the modeller
wrote under the names they wrote them.

Where the run cannot vouch for one of those facts, the file is written
without a manifest and the command says why in one line: a file that claims
nothing is honest, and one that claims the wrong model is not.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from importlib.metadata import version
from typing import TYPE_CHECKING, Any, NoReturn

import polars as pl
import pytest
from rich.console import Console
from typer.testing import CliRunner

from gaspatchio import _internal
from gaspatchio.cli import app
from gaspatchio.engines.protocol import digest_of_inputs, read_manifest

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

MODEL_SRC = "def main(af):\n    af.result = af.amount * 2\n    return af\n"

# A setup step the model template teaches: collect, reshape in Polars, and
# rebuild the frame from the DataFrame. The rebuilt frame cannot tell the
# columns the file carried from the ones the setup made; only a caller that
# read the file can, and the two CLI routes both read it.
REBUILT_MODEL_SRC = """
import polars as pl
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.expected_claims = af.sum_assured * af.mortality_rate
    mp = af.collect()
    mp = mp.with_columns(pl.col("annual_premium").alias("premium"))
    af = ActuarialFrame(mp)
    af.profit = af.premium - af.expected_claims
    return af
"""

# A model that hands back a frame built from bare values: its columns are
# right, and nothing on the frame says which calculation made them. Run under
# optimize, which collects: debug mode profiles, and Polars has nothing to
# time in a plan that is only the values it was handed.
NO_LOG_MODEL_SRC = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.result = af.amount * 2
    return ActuarialFrame(af.collect())
"""


def _model_and_book(
    tmp_path: Path, source: str = MODEL_SRC, book: pl.DataFrame | None = None
) -> tuple[Path, Path]:
    model = tmp_path / "model.py"
    model.write_text(source)
    points = tmp_path / "book.parquet"
    (
        pl.DataFrame({"policy_id": ["P-1", "P-2"], "amount": [2.0, 3.0]})
        if book is None
        else book
    ).write_parquet(points)
    return model, points


def _audit_file(tmp_path: Path, model: Path, points: Path) -> dict[str, Any]:
    artifact = tmp_path / "audit.json"
    result = runner.invoke(
        app, ["calc-graph", str(model), str(points), "-o", str(artifact)]
    )
    assert result.exit_code == 0, result.output
    document: dict[str, Any] = json.loads(artifact.read_text())
    return document


@pytest.mark.parametrize("mode", ["debug", "optimize"])
@pytest.mark.parametrize("flag", ["--results", "--output-file", "-o"])
def test_run_model_results_carry_a_manifest_under_the_models_own_names(
    tmp_path: Path, mode: str, flag: str
) -> None:
    model, points = _model_and_book(tmp_path)
    out = tmp_path / "results.parquet"

    result = runner.invoke(
        app, ["run-model", str(model), str(points), "--mode", mode, flag, str(out)]
    )

    assert result.exit_code == 0, result.output
    assert pl.read_parquet(out).columns == ["policy_id", "amount", "result"]
    manifest = read_manifest(out)
    assert manifest.scope == "final-schema"
    assert manifest.columns == {
        "policy_id": "policy_id",
        "amount": "amount",
        "result@1": "result",
    }
    assert manifest.dtypes == {"policy_id": "str", "amount": "f64", "result@1": "f64"}
    assert manifest.producer == "polars"
    # The column the runner resolves as the policy identifier, named in the
    # file so a comparison pairs its rows by it rather than by position.
    assert manifest.row_identity == ("policy_id",)
    assert manifest.versions["core_version"] == version("gaspatchio")
    assert manifest.versions["extension_version"] == _internal.__version__
    assert manifest.versions["polars_version"] == pl.__version__
    assert manifest.versions["extension_sha256"].startswith("sha256:")


def test_run_model_names_the_model_and_book_its_audit_file_names(
    tmp_path: Path,
) -> None:
    model, points = _model_and_book(tmp_path)
    out = tmp_path / "results.parquet"

    result = runner.invoke(app, ["run-model", str(model), str(points), "-o", str(out)])

    assert result.exit_code == 0, result.output
    manifest = read_manifest(out)
    document = _audit_file(tmp_path, model, points)
    assert manifest.graph_fingerprint == document["graph_fingerprint"]
    assert manifest.inputs_digest == document["book"]["digest"]


def test_a_csv_book_is_one_input_to_run_model_and_calc_graph(tmp_path: Path) -> None:
    """A CSV's column types come from the rows read, and both commands read alike.

    A column empty for its first 150 rows is typed from the values after them
    only by a reader that reads that far. ``run-model`` and ``calc-graph`` read
    the book through one reader, so the results file and the audit file state
    one type for it, one fingerprint and one book digest.
    """
    points = tmp_path / "book.csv"
    pl.DataFrame(
        {
            "policy_id": [f"P-{row}" for row in range(300)],
            "amount": [2.0] * 300,
            "rider": [None] * 150 + [1.5] * 150,
        }
    ).write_csv(points)
    model = tmp_path / "model.py"
    model.write_text(MODEL_SRC)
    out = tmp_path / "results.parquet"

    result = runner.invoke(app, ["run-model", str(model), str(points), "-o", str(out)])

    assert result.exit_code == 0, result.output
    manifest = read_manifest(out)
    document = _audit_file(tmp_path, model, points)
    assert manifest.dtypes["rider"] == "f64"
    assert {node["id"]: node["dtype"] for node in document["nodes"]}["rider"] == "f64"
    assert manifest.graph_fingerprint == document["graph_fingerprint"]
    assert manifest.inputs_digest == document["book"]["digest"]


def test_a_model_that_rebuilds_its_frame_states_its_audit_files_fingerprint(
    tmp_path: Path,
) -> None:
    book = pl.DataFrame(
        {
            "policy_id": [1, 2, 3],
            "sum_assured": [100_000.0, 250_000.0, 500_000.0],
            "annual_premium": [500.0, 1_200.0, 3_000.0],
            "mortality_rate": [0.001, 0.002, 0.005],
        }
    )
    model, points = _model_and_book(tmp_path, REBUILT_MODEL_SRC, book)
    out = tmp_path / "results.parquet"

    result = runner.invoke(app, ["run-model", str(model), str(points), "-o", str(out)])

    assert result.exit_code == 0, result.output
    manifest = read_manifest(out)
    document = _audit_file(tmp_path, model, points)
    assert manifest.graph_fingerprint == document["graph_fingerprint"]
    assert manifest.inputs_digest == document["book"]["digest"]
    holes = {hole["column"] for hole in document["holes"]}
    assert {"expected_claims", "premium"} <= holes
    assert manifest.columns["premium"] == "premium"


def test_a_frame_holding_no_calculation_log_is_saved_without_a_manifest(
    tmp_path: Path,
) -> None:
    model, points = _model_and_book(tmp_path, NO_LOG_MODEL_SRC)
    out = tmp_path / "results.parquet"

    result = runner.invoke(
        app,
        ["run-model", str(model), str(points), "--mode", "optimize", "-o", str(out)],
    )

    assert result.exit_code == 0, result.output
    said = " ".join(result.output.split())
    assert "Saved without a manifest: the frame this run finished on" in said
    assert "holds no calculation log" in said
    assert pl.read_parquet(out)["result"].to_list() == [4.0, 6.0]
    with pytest.raises(ValueError, match="carries no"):
        read_manifest(out)


def test_an_unsigned_book_column_that_fits_is_the_i64_book_it_holds(
    tmp_path: Path,
) -> None:
    """A UInt64 book column whose values fit is digested as the i64 it is read as.

    The run reads the book lazily, so the column keeps its width while the
    plan is built; its values are in hand where the book is digested, and
    there it is read as the frame's door reads one whose values it holds
    (section 10). It used to be saved without a manifest, "UInt64 has no
    name"; now the manifest names it ``i64`` and states the very digest the
    same numbers written as Int64 take.
    """
    unsigned = tmp_path / "unsigned"
    signed = tmp_path / "signed"
    unsigned.mkdir()
    signed.mkdir()
    manifests = []
    for where, dtype in ((unsigned, pl.UInt64), (signed, pl.Int64)):
        book = pl.DataFrame(
            {"policy_id": pl.Series([7, 8], dtype=dtype), "amount": [2.0, 3.0]}
        )
        model, points = _model_and_book(where, MODEL_SRC, book)
        out = where / "results.parquet"
        result = runner.invoke(
            app, ["run-model", str(model), str(points), "-o", str(out)]
        )
        assert result.exit_code == 0, result.output
        assert "without a manifest" not in result.output
        assert pl.read_parquet(out)["result"].to_list() == [4.0, 6.0]
        manifests.append(read_manifest(out))

    from_unsigned, from_signed = manifests
    assert from_unsigned.dtypes["policy_id"] == "i64"
    assert from_unsigned.inputs_digest == from_signed.inputs_digest
    assert from_unsigned.graph_fingerprint == from_signed.graph_fingerprint


@pytest.mark.parametrize(
    ("values", "written_as"),
    [([7, 8], pl.Int64), ([2**64 - 1, 8], pl.UInt64)],
    ids=["fits", "past i64"],
)
def test_a_wide_book_column_no_line_reads_is_written_as_the_dataframe_door_reads_it(
    tmp_path: Path, values: list[int], written_as: type[pl.DataType]
) -> None:
    """The run scans the book, so it reads it as a plan; its results are judged.

    A ``UInt64`` policy number the model never reads came back ``UInt64`` in
    the results file, where the same book handed over as a DataFrame came
    back ``Int64``. It is judged on its values when the run is collected, as
    the DataFrame door judges it: ``Int64`` where every value fits, its own
    width with every digit where one does not.
    """
    book = pl.DataFrame(
        {"policy_id": pl.Series(values, dtype=pl.UInt64), "amount": [2.0, 3.0]}
    )
    model, points = _model_and_book(tmp_path, MODEL_SRC, book)
    out = tmp_path / "results.parquet"

    result = runner.invoke(app, ["run-model", str(model), str(points), "-o", str(out)])

    assert result.exit_code == 0, result.output
    written = pl.read_parquet(out)
    assert written.schema["policy_id"] == written_as
    assert written["policy_id"].to_list() == values


def test_a_computed_column_named_from_its_values_still_gets_its_manifest(
    tmp_path: Path,
) -> None:
    source = MODEL_SRC.replace(
        "    return af\n",
        "    af.lives = af.amount.polars_native().cast(pl.UInt64)\n    return af\n",
    )
    model, points = _model_and_book(tmp_path, "import polars as pl\n" + source)
    out = tmp_path / "results.parquet"

    result = runner.invoke(app, ["run-model", str(model), str(points), "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert "without a manifest" not in result.output
    manifest = read_manifest(out)
    document = _audit_file(tmp_path, model, points)
    assert manifest.graph_fingerprint == document["graph_fingerprint"]
    assert manifest.inputs_digest == document["book"]["digest"]
    assert manifest.dtypes["lives@1"] == "i64"


def test_a_value_no_i64_carries_withholds_the_fingerprint_and_says_how_to_keep_it(
    tmp_path: Path,
) -> None:
    book = pl.DataFrame(
        {"policy_id": pl.Series([2**64 - 1, 8], dtype=pl.UInt64), "amount": [2.0, 3.0]}
    )
    model, points = _model_and_book(tmp_path, MODEL_SRC, book)
    out = tmp_path / "results.parquet"

    result = runner.invoke(app, ["run-model", str(model), str(points), "-o", str(out)])

    assert result.exit_code == 0, result.output
    said = " ".join(result.output.split())
    assert (
        "Saved without a manifest: the model's fingerprint cannot be taken: "
        "Column 'policy_id' holds 18446744073709551615"
    ) in said
    assert "Keep the digits by holding the column as text -- .to_text()" in said
    with pytest.raises(ValueError, match="carries no"):
        read_manifest(out)


# --- calc-graph: the manifest and the audit file of one run ------------------


def _calc_graph(
    tmp_path: Path, model: Path, points: Path, *extra: str
) -> tuple[dict[str, Any], Path]:
    artifact = tmp_path / "audit.json"
    out = tmp_path / "results.parquet"
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(points),
            "-o",
            str(artifact),
            "--results",
            str(out),
            *extra,
        ],
    )
    assert result.exit_code == 0, result.output
    document: dict[str, Any] = json.loads(artifact.read_text())
    return document, out


def test_calc_graph_results_state_the_fingerprint_and_book_the_audit_file_states(
    tmp_path: Path,
) -> None:
    model, points = _model_and_book(tmp_path)

    document, out = _calc_graph(tmp_path, model, points)

    manifest = read_manifest(out)
    assert manifest.graph_fingerprint == document["graph_fingerprint"]
    assert manifest.inputs_digest == document["book"]["digest"]
    assert manifest.scope == "final-schema"
    assert manifest.producer == "polars"
    assert manifest.columns == {
        "policy_id": "policy_id",
        "amount": "amount",
        "result@1": "result",
    }
    assert pl.read_parquet(out).columns == ["policy_id", "amount", "result"]


def test_calc_graph_stamps_the_results_file_with_its_manifest_already_inside(
    tmp_path: Path,
) -> None:
    model, points = _model_and_book(tmp_path)

    document, out = _calc_graph(tmp_path, model, points)

    stamped = document["model"]["results"]["fingerprint"]
    assert stamped == f"sha256:{hashlib.sha256(out.read_bytes()).hexdigest()}"
    assert read_manifest(out).graph_fingerprint == document["graph_fingerprint"]


def test_calc_graph_takes_the_book_s_digest_once_for_both_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gaspatchio.frame.graph import artifact

    taken: list[list[str]] = []
    real = artifact.digest_of_inputs

    def counted(frame: pl.DataFrame, columns: list[str]) -> str:
        taken.append(list(columns))
        return real(frame, columns)

    monkeypatch.setattr(artifact, "digest_of_inputs", counted)
    model, points = _model_and_book(tmp_path)

    document, out = _calc_graph(tmp_path, model, points)

    assert taken == [["amount", "policy_id"]]
    assert read_manifest(out).inputs_digest == document["book"]["digest"]


def test_calc_graph_names_the_row_identity_it_resolved(tmp_path: Path) -> None:
    """Told or resolved, the policy column is the identity the file records.

    The resolution is the runner's: the column named on the command line, or
    else one of the names it reads as a policy identifier and no other. A book
    keyed by a column outside those names records none unless it is named.
    """
    model, points = _model_and_book(tmp_path)

    _, told = _calc_graph(tmp_path, model, points, "--policy-id-column", "policy_id")
    assert read_manifest(told).row_identity == ("policy_id",)

    _, resolved = _calc_graph(tmp_path, model, points)
    assert read_manifest(resolved).row_identity == ("policy_id",)

    book = pl.DataFrame({"contract": ["C-1", "C-2"], "amount": [2.0, 3.0]})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    model, points = _model_and_book(elsewhere, MODEL_SRC, book)
    _, unnamed = _calc_graph(elsewhere, model, points)
    assert read_manifest(unnamed).row_identity is None
    _, named = _calc_graph(elsewhere, model, points, "--policy-id-column", "contract")
    assert read_manifest(named).row_identity == ("contract",)


def test_calc_graph_takes_a_second_identity_column_as_run_model_does(
    tmp_path: Path,
) -> None:
    """``--policy-id-column`` repeats on calc-graph as on run-model and compare.

    A book whose rows a policy and a scenario name together could not say so
    to calc-graph, which took the option once: a second use was refused.
    """
    book = pl.DataFrame(
        {
            "policy_id": ["P-1", "P-1", "P-2"],
            "cohort": ["A", "B", "A"],
            "amount": [2.0, 3.0, 4.0],
        }
    )
    model, points = _model_and_book(tmp_path, MODEL_SRC, book)

    _, out = _calc_graph(
        tmp_path,
        model,
        points,
        "--policy-id-column",
        "policy_id",
        "--policy-id-column",
        "cohort",
    )

    assert read_manifest(out).row_identity == ("policy_id", "cohort")


def test_a_policy_column_naming_a_row_twice_is_not_stated_as_the_row_identity(
    tmp_path: Path,
) -> None:
    book = pl.DataFrame({"policy_id": ["P-1", "P-1"], "amount": [2.0, 3.0]})
    model, points = _model_and_book(tmp_path, MODEL_SRC, book)

    _, out = _calc_graph(tmp_path, model, points, "--policy-id-column", "policy_id")

    assert read_manifest(out).row_identity is None


# --- a manifest that fails for a reason nobody named -------------------------


def _printing_in_colour(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Point the commands' two consoles at one buffer that keeps their colours.

    stdout's and stderr's both: a notice is printed on stdout, and a line
    saying something went wrong on stderr, as every refusal is.
    """
    from gaspatchio import cli

    printed = io.StringIO()
    for name in ("console", "err_console"):
        monkeypatch.setattr(
            cli, name, Console(file=printed, force_terminal=True, width=400)
        )
    return printed


def _logged_errors() -> tuple[list[str], int]:
    """Collect every error the logger writes, traceback included."""
    from loguru import logger

    written: list[str] = []
    return written, logger.add(written.append, level="ERROR")


@pytest.mark.parametrize(
    ("where", "failure"),
    [
        ("_final_schema_manifest", RuntimeError("the manifest step broke")),
        ("_columns_the_file_carries", OSError("the model points went away")),
    ],
)
def test_an_unexpected_failure_keeps_the_values_says_so_in_red_and_logs_why(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    where: str,
    failure: Exception,
) -> None:
    from loguru import logger

    from gaspatchio import cli

    def broken(*_: object, **__: object) -> NoReturn:
        raise failure

    monkeypatch.setattr(cli, where, broken)
    printed = _printing_in_colour(monkeypatch)
    errors, sink = _logged_errors()
    model, points = _model_and_book(tmp_path)
    out = tmp_path / "results.parquet"

    try:
        result = runner.invoke(
            app, ["run-model", str(model), str(points), "-o", str(out)]
        )
    finally:
        logger.remove(sink)

    assert result.exit_code == 0, result.output
    assert pl.read_parquet(out)["result"].to_list() == [4.0, 6.0]
    with pytest.raises(ValueError, match="carries no"):
        read_manifest(out)
    line = next(one for one in printed.getvalue().splitlines() if "manifest" in one)
    assert "\x1b[31m" in line
    assert f"building it failed with {type(failure).__name__}: {failure}" in line
    assert any("Traceback" in one and str(failure) in one for one in errors)


def test_a_known_refusal_keeps_its_plain_line_and_logs_no_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from loguru import logger

    printed = _printing_in_colour(monkeypatch)
    errors, sink = _logged_errors()
    model, points = _model_and_book(tmp_path, NO_LOG_MODEL_SRC)
    out = tmp_path / "results.parquet"

    try:
        result = runner.invoke(
            app,
            ["run-model", str(model), str(points), "-m", "optimize", "-o", str(out)],
        )
    finally:
        logger.remove(sink)

    assert result.exit_code == 0, result.output
    line = next(one for one in printed.getvalue().splitlines() if "manifest" in one)
    assert "\x1b[31m" not in line
    assert "holds no calculation log" in line
    assert errors == []


# --- one policy's results -----------------------------------------------------


def test_one_policy_s_results_carry_the_manifest_of_that_policy_s_book(
    tmp_path: Path,
) -> None:
    model, points = _model_and_book(tmp_path)
    out = tmp_path / "one.parquet"

    result = runner.invoke(
        app,
        [
            "run-single-policy",
            str(model),
            str(points),
            "P-2",
            "--policy-id-column",
            "POLICY_ID",
            "--results",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert pl.read_parquet(out)["result"].to_list() == [6.0]
    manifest = read_manifest(out)
    one_policy = pl.read_parquet(points).filter(pl.col("policy_id") == "P-2")
    assert manifest.inputs_digest == digest_of_inputs(
        one_policy, ["amount", "policy_id"]
    )
    assert (
        manifest.graph_fingerprint
        == (_audit_file(tmp_path, model, points)["graph_fingerprint"])
    )
    assert manifest.columns == {
        "policy_id": "policy_id",
        "amount": "amount",
        "result@1": "result",
    }
    assert manifest.row_identity == ("policy_id",)


def test_one_policy_found_by_the_resolved_column_records_it_as_the_row_identity(
    tmp_path: Path,
) -> None:
    model, points = _model_and_book(tmp_path)
    out = tmp_path / "one.parquet"

    result = runner.invoke(
        app, ["run-single-policy", str(model), str(points), "P-1", "-o", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert read_manifest(out).row_identity == ("policy_id",)


def test_one_policy_s_results_say_why_where_no_manifest_can_be_written(
    tmp_path: Path,
) -> None:
    model, points = _model_and_book(tmp_path, NO_LOG_MODEL_SRC)
    out = tmp_path / "one.parquet"

    result = runner.invoke(
        app,
        [
            "run-single-policy",
            str(model),
            str(points),
            "P-1",
            "--mode",
            "optimize",
            "-o",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    said = " ".join(result.output.split())
    assert "Saved without a manifest: the frame this run finished on" in said
    assert pl.read_parquet(out)["result"].to_list() == [4.0]


# --- what the terminal is told while a manifest is read ------------------------


def _command(*arguments: str | Path) -> subprocess.CompletedProcess[str]:
    """Run the CLI in a process of its own, at the log level a user sees."""
    return subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
        [sys.executable, "-m", "gaspatchio.cli", *(str(one) for one in arguments)],
        capture_output=True,
        text=True,
        env={**os.environ, "LOGURU_LEVEL": "INFO"},
        check=False,
    )


def test_reading_a_results_manifest_prints_none_of_the_export_s_progress(
    tmp_path: Path,
) -> None:
    model, points = _model_and_book(tmp_path)

    run = _command("run-model", model, points, "-o", tmp_path / "results.parquet")

    assert run.returncode == 0, run.stdout + run.stderr
    assert "Full model run finished" in run.stderr
    assert "Building calculation graph" not in run.stderr
    assert "Graph built" not in run.stderr


def test_calc_graph_still_prints_its_own_export_s_progress_once(
    tmp_path: Path,
) -> None:
    model, points = _model_and_book(tmp_path)

    run = _command(
        "calc-graph",
        model,
        points,
        "-o",
        tmp_path / "audit.json",
        "--results",
        tmp_path / "results.parquet",
    )

    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stderr.count("Building calculation graph") == 1
    assert run.stderr.count("Graph built") == 1
