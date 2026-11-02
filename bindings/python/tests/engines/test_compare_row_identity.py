# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Two results files are paired policy by policy, never by a guess at their order.

Every results file the commands write records the columns that name its rows:
the policy-id column the runner resolves, and the scenario column beside it
where a scenario axis crossed the book. ``gspio compare`` pairs two files'
rows by that identity. A file that records none -- one written before this,
or an engine's whose book named no policy column -- is paired by position
only where the order is shown: the column the other side records is in the
same order on both, or both read one book. Anything else is refused, naming
``--policy-id-column``, because a pairing by position that is wrong still
returns a verdict: the same policies in another order "disagree", and two
books whose values happen to line up "agree".
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.engines.compare import compare_results
from gaspatchio.engines.protocol import (
    ResultManifest,
    read_manifest,
    write_with_manifest,
)

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

MODEL_SRC = "def main(af):\n    af.result = af.amount * 2\n    return af\n"

SCENARIO_MODEL_SRC = """
import polars as pl


def main(af, params=None):
    del params
    af.shocked = af.amount * pl.when(pl.col("scenario_id") == "UP").then(1.5).otherwise(
        1.0
    )
    return af
"""

SCENARIO_SCRIPT_SRC = """
from gaspatchio import ScenarioRun
from gaspatchio.scenarios import Sum

import model


SCENARIO_RUN = ScenarioRun(
    shocks={"BASE": [], "UP": []},
    aggregations=(Sum("shocked").alias("shocked").over("scenario_id"),),
)
MODEL_FN = model.main
"""

BOOK = pl.DataFrame({"policy_id": ["P-1", "P-2", "P-3"], "amount": [2.0, 3.0, 5.0]})


def _invoked(*arguments: str | Path) -> tuple[int, str]:
    result = runner.invoke(app, [str(argument) for argument in arguments])
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        result.output
    )
    return result.exit_code, " ".join(result.output.split())


def _model_and_books(tmp_path: Path, source: str = MODEL_SRC) -> tuple[Path, Path]:
    """Write the model, the book and the artifact; return the model and the book.

    The reordered book is the same policies with the same values, sorted the
    other way -- a re-extract of one in-force, which is the case a comparison
    must answer "agree" to.
    """
    model = tmp_path / "model.py"
    model.write_text(source)
    BOOK.write_parquet(tmp_path / "book.parquet")
    BOOK.reverse().write_parquet(tmp_path / "reordered.parquet")
    status, said = _invoked(
        "calc-graph",
        model,
        tmp_path / "book.parquet",
        "--profile",
        "executable",
        "-o",
        tmp_path / "artifact.json",
    )
    assert status == 0, said
    return model, tmp_path / "book.parquet"


def _results(tmp_path: Path, model: Path, book: str, name: str, *extra: str) -> Path:
    out = tmp_path / f"{name}.parquet"
    status, said = _invoked("run-model", model, tmp_path / book, *extra, "-o", out)
    assert status == 0, said
    return out


def _without_identity(path: Path, name: str) -> Path:
    """Rewrite a results file as one written before the identity was recorded."""
    legacy = path.with_name(f"{name}.parquet")
    manifest = replace(read_manifest(path), row_identity=None)
    write_with_manifest(pl.read_parquet(path), manifest, legacy)
    return legacy


@pytest.mark.parametrize("scope", [(), ("--every-node",)])
def test_the_same_policies_in_another_order_are_paired_by_identity_and_agree(
    tmp_path: Path, scope: tuple[str, ...]
) -> None:
    """On the base this compared by position and reported *disagree*."""
    model, _ = _model_and_books(tmp_path)
    before = _results(tmp_path, model, "book.parquet", "before", *scope)
    after = _results(tmp_path, model, "reordered.parquet", "after", *scope)

    assert read_manifest(before).row_identity == ("policy_id",)
    assert read_manifest(after).row_identity == ("policy_id",)
    status, said = _invoked("compare", tmp_path / "artifact.json", before, after)

    assert status == 0, said
    assert "before.parquet and after.parquet agree" in said
    assert "rows matched by identity on policy_id" in said


def test_a_file_without_identity_beside_a_reordered_one_refuses_naming_the_flag(
    tmp_path: Path,
) -> None:
    model, _ = _model_and_books(tmp_path)
    before = _without_identity(
        _results(tmp_path, model, "book.parquet", "written"), "legacy"
    )
    after = _results(tmp_path, model, "reordered.parquet", "after")

    status, said = _invoked("compare", tmp_path / "artifact.json", before, after)

    assert status == 2, said
    assert "These two results cannot be compared" in said
    assert "'policy_id' in different orders" in said
    assert "row 1 is P-1 in one and P-3 in the other" in said
    assert "--policy-id-column policy_id" in said

    status, said = _invoked(
        "compare",
        tmp_path / "artifact.json",
        before,
        after,
        "--policy-id-column",
        "policy_id",
    )
    assert status == 0, said
    assert "rows matched by identity on policy_id" in said


def test_two_files_recording_no_identity_over_two_books_refuse(tmp_path: Path) -> None:
    model, _ = _model_and_books(tmp_path)
    before = _without_identity(
        _results(tmp_path, model, "book.parquet", "one"), "legacy_one"
    )
    after = _without_identity(
        _results(tmp_path, model, "reordered.parquet", "two"), "legacy_two"
    )

    status, said = _invoked("compare", tmp_path / "artifact.json", before, after)

    assert status == 2, said
    assert "Neither file records which columns name its rows" in said
    assert "--policy-id-column <column>" in said


def test_a_legacy_pair_in_one_order_still_compares_by_position(tmp_path: Path) -> None:
    """Both sides read one book, and the book's digest is over its rows in order."""
    model, _ = _model_and_books(tmp_path)
    before = _without_identity(
        _results(tmp_path, model, "book.parquet", "one"), "legacy_one"
    )
    after = _without_identity(
        _results(tmp_path, model, "book.parquet", "two"), "legacy_two"
    )

    status, said = _invoked("compare", tmp_path / "artifact.json", before, after)

    assert status == 0, said
    assert "rows matched by position, one book in one order · the same book" in said


def test_a_legacy_identity_written_as_one_name_is_read_as_that_column(
    tmp_path: Path,
) -> None:
    model, _ = _model_and_books(tmp_path)
    written = _results(tmp_path, model, "book.parquet", "written")
    legacy = tmp_path / "legacy.parquet"
    metadata = read_manifest(written).to_metadata()
    metadata["gaspatchio.row_identity"] = '"policy_id"'
    pl.read_parquet(written).write_parquet(legacy, metadata=metadata)

    assert read_manifest(legacy).row_identity == ("policy_id",)

    metadata["gaspatchio.row_identity"] = "[]"
    pl.read_parquet(written).write_parquet(legacy, metadata=metadata)
    with pytest.raises(ValueError, match="row_identity"):
        read_manifest(legacy)


def test_a_scenario_run_records_the_policy_and_the_scenario_column(
    tmp_path: Path,
) -> None:
    """Each policy is on one row per scenario, so the identity is the pair.

    On the base the policy column named no row once, so the file recorded no
    identity, and the reordered book's results were compared by position.
    """
    model = tmp_path / "model.py"
    model.write_text(SCENARIO_MODEL_SRC)
    script = tmp_path / "run_scenarios.py"
    script.write_text(SCENARIO_SCRIPT_SRC)
    BOOK.write_parquet(tmp_path / "book.parquet")
    BOOK.reverse().write_parquet(tmp_path / "reordered.parquet")
    for book in ("book", "reordered"):
        status, said = _invoked(
            "calc-graph",
            model,
            tmp_path / f"{book}.parquet",
            "--profile",
            "executable",
            "-o",
            tmp_path / f"{book}.json",
            "--scenarios",
            script,
            "--results",
            tmp_path / f"{book}.results.parquet",
        )
        assert status == 0, said
        assert read_manifest(tmp_path / f"{book}.results.parquet").row_identity == (
            "policy_id",
            "scenario_id",
        )

    status, said = _invoked(
        "compare",
        tmp_path / "book.json",
        tmp_path / "book.results.parquet",
        tmp_path / "reordered.results.parquet",
    )

    assert status == 0, said
    assert "rows matched by identity on policy_id, scenario_id" in said


def test_run_model_records_the_column_it_is_told(tmp_path: Path) -> None:
    model, _ = _model_and_books(tmp_path)
    BOOK.rename({"policy_id": "contract"}).write_parquet(tmp_path / "keyed.parquet")

    unnamed = _results(tmp_path, model, "keyed.parquet", "unnamed")
    named = _results(
        tmp_path, model, "keyed.parquet", "named", "--policy-id-column", "contract"
    )
    every = _results(
        tmp_path,
        model,
        "keyed.parquet",
        "every",
        "--every-node",
        "--policy-id-column",
        "contract",
    )

    assert read_manifest(unnamed).row_identity is None
    assert read_manifest(named).row_identity == ("contract",)
    assert read_manifest(every).row_identity == ("contract",)


# --- the rule, over frames ---------------------------------------------------

FINGERPRINT = "sha256:" + "ab" * 32


def _artifact() -> dict[str, Any]:
    return {
        "graph_fingerprint": FINGERPRINT,
        "nodes": [
            {
                "id": "policy_id",
                "column": "policy_id",
                "kind": "input",
                "dtype": "str",
                "shape": "scalar",
                "reads": [],
            },
            {
                "id": "net@1",
                "column": "net",
                "kind": "computed",
                "dtype": "f64",
                "shape": "scalar",
                "reads": [],
                "in_final_schema": True,
            },
        ],
    }


def _manifest(
    identity: tuple[str, ...] | None, book: str = "sha256:" + "11" * 32
) -> ResultManifest:
    return ResultManifest(
        scope="final-schema",
        columns={"net@1": "net@1"},
        dtypes={"net@1": "f64"},
        row_identity=identity,
        graph_fingerprint=FINGERPRINT,
        inputs_digest=book,
        producer="polars",
        versions={},
    )


def test_two_books_lining_up_by_position_are_not_called_agreement() -> None:
    """On the base this returned *agree*: P-2's answer held against P-1's."""
    before = pl.DataFrame({"policy_id": ["P-1", "P-2"], "net@1": [10.0, 20.0]})
    after = pl.DataFrame({"policy_id": ["P-2", "P-1"], "net@1": [10.0, 20.0]})

    with pytest.raises(ValueError, match="--policy-id-column"):
        compare_results(
            _artifact(),
            before,
            after,
            before_manifest=_manifest(None),
            after_manifest=_manifest(None, book="sha256:" + "22" * 32),
        )

    report = compare_results(
        _artifact(),
        before,
        after,
        before_manifest=_manifest(None),
        after_manifest=_manifest(None, book="sha256:" + "22" * 32),
        row_identity=["policy_id"],
    )
    assert report.rows_matched_by == "identity"
    assert report.verdict == "disagree"


def test_one_side_s_identity_in_the_same_order_on_the_other_shows_the_order() -> None:
    frame = pl.DataFrame({"policy_id": ["P-1", "P-2"], "net@1": [10.0, 20.0]})

    report = compare_results(
        _artifact(),
        frame,
        frame,
        before_manifest=_manifest(("policy_id",)),
        after_manifest=_manifest(None, book="sha256:" + "22" * 32),
    )

    assert report.rows_matched_by == "position"
    assert report.rows_matched_on == ("policy_id",)
    assert report.to_dict()["rows_matched_on"] == ["policy_id"]


def test_two_recorded_identities_that_differ_refuse() -> None:
    frame = pl.DataFrame(
        {"policy_id": ["P-1", "P-2"], "point": [1, 2], "net@1": [10.0, 20.0]}
    )

    with pytest.raises(ValueError, match="'policy_id' and the after results by"):
        compare_results(
            _artifact(),
            frame,
            frame,
            before_manifest=_manifest(("policy_id",)),
            after_manifest=_manifest(("point",)),
        )


def test_a_recorded_identity_the_file_does_not_carry_refuses() -> None:
    frame = pl.DataFrame({"net@1": [10.0, 20.0]})

    with pytest.raises(ValueError, match="carry no policy_id column"):
        compare_results(
            _artifact(),
            frame,
            frame,
            before_manifest=_manifest(("policy_id",)),
            after_manifest=_manifest(("policy_id",)),
        )


def test_a_composite_identity_names_the_repeated_pair_it_refuses() -> None:
    frame = pl.DataFrame(
        {
            "policy_id": ["P-1", "P-1"],
            "scenario_id": ["BASE", "BASE"],
            "net@1": [10.0, 20.0],
        }
    )

    with pytest.raises(ValueError, match=r"\(P-1, BASE\) more than once"):
        compare_results(
            _artifact(),
            frame,
            frame,
            before_manifest=_manifest(("policy_id", "scenario_id")),
            after_manifest=_manifest(("policy_id", "scenario_id")),
        )


def test_a_row_count_refusal_names_what_pairs_rows() -> None:
    frame = pl.DataFrame({"policy_id": ["P-1", "P-2"], "net@1": [10.0, 20.0]})

    with pytest.raises(ValueError, match="hold 2 rows") as refused:
        compare_results(
            _artifact(),
            frame,
            frame.head(1),
            before_manifest=_manifest(("policy_id",)),
            after_manifest=_manifest(("policy_id",)),
        )

    said = str(refused.value)
    assert "--policy-id-column" in said
    assert "manifests" not in said


# --- a scenario axis under a name of the modeller's own ----------------------

RENAMED_AXIS_MODEL_SRC = """
from gaspatchio.scenarios import with_scenarios


def main(af):
    af = with_scenarios(af, ["BASE", "UP"], scenario_column="stress")
    af.result = af.amount * 2
    return af
"""


def test_a_scenario_axis_is_read_from_the_record_whatever_it_is_called(
    tmp_path: Path,
) -> None:
    """``with_scenarios(scenario_column="stress")`` is the scenario half."""
    model = tmp_path / "model.py"
    model.write_text(RENAMED_AXIS_MODEL_SRC)
    BOOK.write_parquet(tmp_path / "book.parquet")

    final = _results(tmp_path, model, "book.parquet", "final")
    every = _results(tmp_path, model, "book.parquet", "every", "--every-node")

    assert read_manifest(final).row_identity == ("policy_id", "stress")
    assert read_manifest(every).row_identity == ("policy_id", "stress")


def test_only_the_cross_join_s_record_is_read_as_a_scenario_axis() -> None:
    """A table joined on, or a column the model assigned, is not an axis."""
    from gaspatchio import ActuarialFrame  # noqa: PLC0415 -- this test's own frame
    from gaspatchio.scenarios import with_scenarios  # noqa: PLC0415 -- as above
    from gaspatchio.scenarios._with_scenarios import (  # noqa: PLC0415 -- as above
        scenario_axis_columns,
    )

    af = ActuarialFrame(BOOK)
    af.label = pl.Series(["a", "b", "c"])
    af = af.join(
        pl.DataFrame({"policy_id": ["P-1", "P-2", "P-3"], "band": [1, 2, 3]}),
        on="policy_id",
    )
    assert scenario_axis_columns(af) == ()

    af = with_scenarios(af, ["BASE", "UP"], scenario_column="stress")
    assert scenario_axis_columns(af) == ("stress",)


# --- run-artifact is told the identity as run-model is ------------------------


class _PassThroughEngine:
    """An engine that hands the book back with the model's one line computed.

    Its manifest states no row identity, as an engine's does: neither the
    artifact nor the book says which column identifies a policy, and the
    command that read the book is what resolves it.
    """

    name = "passthrough"
    version = "0.0.0-test"

    def validate_tree(self, document: dict[str, Any]) -> tuple[Any, ...]:  # noqa: ARG002 -- the protocol's parameter
        return ()

    def run(
        self,
        document: dict[str, Any],
        inputs: pl.DataFrame,
        sink: Any,  # noqa: ANN401 -- the protocol's sink
        *,
        every_node: bool = False,  # noqa: ARG002 -- final schema only
    ) -> Any:  # noqa: ANN401 -- the protocol's result
        from gaspatchio.engines.protocol import digest_of_inputs  # noqa: PLC0415
        from gaspatchio.engines.report import RunReport  # noqa: PLC0415
        from gaspatchio.frame.graph.artifact import book_columns  # noqa: PLC0415

        written = inputs.with_columns((pl.col("amount") * 2).alias("result"))
        sink.open(
            ResultManifest(
                scope="final-schema",
                columns={column: column for column in written.columns},
                dtypes={column: "str" for column in written.columns},
                row_identity=None,
                graph_fingerprint=document["graph_fingerprint"],
                inputs_digest=digest_of_inputs(inputs, book_columns(document["nodes"])),
                producer=self.name,
                versions={},
            )
        )
        sink.write_batch(written)
        return sink.publish(RunReport(refusals=()))


def test_run_artifact_records_the_identity_it_is_told(tmp_path: Path) -> None:
    from gaspatchio.engines import register_engine  # noqa: PLC0415

    register_engine("passthrough", _PassThroughEngine)
    model, _ = _model_and_books(tmp_path)
    keyed = tmp_path / "keyed.parquet"
    BOOK.rename({"policy_id": "contract"}).with_columns(
        pl.lit("BASE").alias("stress")
    ).write_parquet(keyed)
    artifact = tmp_path / "artifact.json"

    def run(name: str, *extra: str) -> tuple[int, str, Path]:
        out = tmp_path / f"{name}.parquet"
        status, said = _invoked(
            "run-artifact",
            artifact,
            keyed,
            "--engine",
            "passthrough",
            "-o",
            out,
            *extra,
        )
        return status, said, out

    status, said, unnamed = run("unnamed")
    assert status == 0, said
    assert read_manifest(unnamed).row_identity is None

    status, said, named = run("named", "--policy-id-column", "contract")
    assert status == 0, said
    assert read_manifest(named).row_identity == ("contract",)

    status, said, pair = run(
        "pair", "--policy-id-column", "contract", "--policy-id-column", "stress"
    )
    assert status == 0, said
    assert read_manifest(pair).row_identity == ("contract", "stress")

    status, said, _ = run("absent", "--policy-id-column", "policy_number")
    assert status == 2, said
    assert "record no row identity: policy_number" in said
