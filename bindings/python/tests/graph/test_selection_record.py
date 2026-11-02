# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Choosing which policies a model values is part of its record (spec section 7.6).

``af.filter(...)`` and semi and anti joins used to leave ``graph_fingerprint``,
``formulas_fingerprint`` and ``book.digest`` where they were whatever they
selected, a replay of the executable artifact valued the policies the model
left out, and ``gspio verify`` agreed with a book in which a policy had
lapsed once the model dropped the status column. Each test here fails on the
tree before the ruling and passes after it.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter, diff_artifacts, validate_artifact
from gaspatchio.frame.graph.verify import verify_artifact

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# Four policies, one of them lapsed: the shape of the adversarial review's
# model (scratch/w5-adv/m1), reduced to what the record has to see.
_BOOK = {
    "policy_id": ["P1", "P2", "P3", "P4"],
    "status": ["IF", "IF", "IF", "LAPSED"],
    "issue_age": [30, 45, 60, 52],
    "sum_assured": [100_000.0, 250_000.0, 50_000.0, 80_000.0],
    "product": ["T10", "T5", "T2", "T3"],
}


def _document(
    select: Callable[[ActuarialFrame], ActuarialFrame],
    *,
    profile: str = "audit",
    drop_status: bool = False,
) -> dict[str, Any]:
    af = ActuarialFrame(pl.DataFrame(_BOOK))
    af = select(af)
    af.premium = af.sum_assured * 0.002
    if drop_status:
        af = af.drop("status")
    return json.loads(GraphExporter(af).export(profile=profile))  # type: ignore[arg-type]


def apply_selection(document: dict[str, Any], book: pl.DataFrame) -> pl.DataFrame:
    """Replay the document's recorded selection over a book, as an engine does."""
    from gaspatchio.engines.format import apply_selection as replay

    return replay(document, book)


def _identities(document: dict[str, Any]) -> tuple[str, str]:
    return document["graph_fingerprint"], document["formulas_fingerprint"]


_VARIANTS: dict[str, Callable[[ActuarialFrame], ActuarialFrame]] = {
    "no selection": lambda af: af,
    "in force": lambda af: af.filter(pl.col("status") == "IF"),
    "lapsed": lambda af: af.filter(pl.col("status") == "LAPSED"),
    "age under 50": lambda af: af.filter(pl.col("issue_age") < 50),
    "age under 55": lambda af: af.filter(pl.col("issue_age") < 55),
    "in a set": lambda af: af.filter(pl.col("status").is_in(["IF", "LAPSED"])),
    "semi join": lambda af: af.join(
        pl.DataFrame({"product": ["T10", "T5"]}), on="product", how="semi"
    ),
    "anti join": lambda af: af.join(
        pl.DataFrame({"product": ["T10", "T5"]}), on="product", how="anti"
    ),
}


def test_every_selection_moves_both_fingerprints() -> None:
    """Each variant changes only which policies are valued, and is its own model."""
    seen = {name: _identities(_document(select)) for name, select in _VARIANTS.items()}
    graphs = [graph for graph, _ in seen.values()]
    formulas = [formula for _, formula in seen.values()]
    assert len(set(graphs)) == len(_VARIANTS), seen
    assert len(set(formulas)) == len(_VARIANTS), seen


def test_a_model_that_selects_nothing_keeps_its_digests_and_carries_no_member() -> None:
    """No published digest moves for a model that does not select."""
    plain = _document(_VARIANTS["no selection"])
    assert "selection" not in plain
    af = ActuarialFrame(pl.DataFrame(_BOOK))
    af.premium = af.sum_assured * 0.002
    again = json.loads(GraphExporter(af).export())
    assert _identities(plain) == _identities(again)


def test_a_polars_predicate_and_the_frame_s_own_record_one_step() -> None:
    """``pl.col("status") == "IF"`` and ``af.status == "IF"`` are one predicate."""
    raw = _document(lambda af: af.filter(pl.col("status") == "IF"))
    own = _document(lambda af: af.filter(af.status == "IF"))
    assert _identities(raw) == _identities(own)
    (step,) = raw["selection"]
    assert step["id"] == "selection:1"
    assert step["kind"] == "filter"
    assert step["tier"] == "core"
    assert step["reads"] == ["status"]
    assert step["expr"] == {
        "op": "binop",
        "kind": "eq",
        "left": {"op": "col", "name": "status"},
        "right": {"op": "lit", "value": "IF"},
    }


def test_a_semi_join_records_its_right_side_and_the_document_carries_it() -> None:
    document = _document(_VARIANTS["semi join"])
    (step,) = document["selection"]
    assert step["kind"] == "semi"
    assert step["expr"]["attrs"]["how"] == "semi"
    assert step["right_fingerprint"] == step["expr"]["attrs"]["right_fingerprint"]
    carried = [
        entry
        for entry in document["assumptions"]
        if entry["kind"] == "join" and entry["fingerprint"] == step["right_fingerprint"]
    ]
    assert len(carried) == 1
    assert carried[0]["payload"]["rows"] == [["T10"], ["T5"]]


def test_a_semi_join_s_right_side_is_data_and_its_kind_is_logic() -> None:
    """Section 12.6's mask reaches a selecting join exactly as it reaches a join."""

    def matched(products: list[str], how: str) -> tuple[str, str]:
        return _identities(
            _document(
                lambda af: af.join(
                    pl.DataFrame({"product": products}), on="product", how=how
                )
            )
        )

    semi_a, semi_b, anti_a = (
        matched(["T10", "T5"], "semi"),
        matched(["T10"], "semi"),
        matched(["T10", "T5"], "anti"),
    )
    assert semi_a[0] != semi_b[0]
    assert semi_a[1] == semi_b[1]
    assert semi_a[1] != anti_a[1]


def test_a_predicate_s_reads_join_the_book_even_where_the_model_drops_them() -> None:
    kept = _document(_VARIANTS["in force"], drop_status=True)
    assert "status" in kept["book"]["columns"]
    unselected = _document(_VARIANTS["no selection"], drop_status=True)
    assert "status" not in unselected["book"]["columns"]


def test_verify_disagrees_with_a_book_in_which_a_policy_has_lapsed(
    tmp_path: Path,
) -> None:
    """The adversarial review's m13, as a test: P2 lapses, the model drops status."""
    document = _document(_VARIANTS["in force"], drop_status=True)
    audit = tmp_path / "a.audit.json"
    audit.write_text(json.dumps(document))
    lapsed = pl.DataFrame(_BOOK).with_columns(
        pl.when(pl.col("policy_id") == "P2")
        .then(pl.lit("LAPSED"))
        .otherwise(pl.col("status"))
        .alias("status")
    )
    as_recorded = tmp_path / "mp.parquet"
    pl.DataFrame(_BOOK).write_parquet(as_recorded)
    moved = tmp_path / "mp_p2_lapsed.parquet"
    lapsed.write_parquet(moved)

    agrees = verify_artifact(audit, model_points=as_recorded)
    differs = verify_artifact(audit, model_points=moved)

    by_name = {check.name: check.outcome for check in differs.checks}
    assert {check.name: check.outcome for check in agrees.checks}["book"] == "agree"
    assert by_name["book"] == "disagree"


def test_a_column_no_line_reads_still_cannot_move_the_book() -> None:
    """Section 7.5's rule holds: only what a line or a step reads is the book.

    A revision to a column nothing reads and the finished frame drops leaves
    the book where it was; one to the column the in-force filter reads moves
    it, though the finished frame drops that column too.
    """

    def book_over(book: dict[str, list[object]]) -> str:
        af = ActuarialFrame(pl.DataFrame(book)).filter(pl.col("status") == "IF")
        af.premium = af.sum_assured * 0.002
        af = af.drop("status").drop("issue_age")
        return json.loads(GraphExporter(af).export())["book"]["digest"]

    recorded = book_over(_BOOK)
    unread_moved = book_over({**_BOOK, "issue_age": [31, 46, 61, 53]})
    status_moved = book_over({**_BOOK, "status": ["IF", "LAPSED", "IF", "LAPSED"]})
    assert unread_moved == recorded
    assert status_moved != recorded


def test_a_predicate_binds_to_the_definition_live_when_the_step_was_taken() -> None:
    af = ActuarialFrame(pl.DataFrame(_BOOK))
    af.band = af.issue_age * 1
    af = af.filter(af.band < 50)
    af.band = af.issue_age * 2
    document = json.loads(GraphExporter(af).export())
    assert document["selection"][0]["reads"] == ["band@1"]


def test_a_redefined_column_a_step_reads_is_an_inherited_selection_change() -> None:
    def model(factor: int) -> dict[str, Any]:
        af = ActuarialFrame(pl.DataFrame(_BOOK))
        af.band = af.issue_age * factor
        af = af.filter(af.band < 100)
        return json.loads(GraphExporter(af).export())

    report = diff_artifacts(model(1), model(2))
    selection = [
        change for change in report.calculations if change.node == "selection:1"
    ]
    assert [(change.kind, change.change_origin) for change in selection] == [
        ("changed", "inherited")
    ]


def test_diff_reports_a_changed_in_force_definition_as_a_calculation_change() -> None:
    report = diff_artifacts(
        _document(_VARIANTS["age under 50"]), _document(_VARIANTS["age under 55"])
    )
    assert [
        (change.node, change.column, change.kind, change.change_origin)
        for change in report.calculations
    ] == [("selection:1", None, "changed", "self")]
    assert report.drift


def test_diff_adds_and_removes_a_selection_step() -> None:
    added = diff_artifacts(
        _document(_VARIANTS["no selection"]), _document(_VARIANTS["in force"])
    )
    removed = diff_artifacts(
        _document(_VARIANTS["in force"]), _document(_VARIANTS["no selection"])
    )
    assert [(c.node, c.kind) for c in added.calculations] == [("selection:1", "added")]
    assert [(c.node, c.kind) for c in removed.calculations] == [
        ("selection:1", "removed")
    ]


def test_diff_puts_a_moved_model_source_on_a_line_of_its_own() -> None:
    before, after = _document(_VARIANTS["in force"]), _document(_VARIANTS["in force"])
    before["model"]["source_path"] = after["model"]["source_path"] = "model.py"
    before["model"]["source_sha"] = "sha256:" + "a" * 64
    after["model"]["source_sha"] = "sha256:" + "b" * 64
    report = diff_artifacts(before, after)
    assert report.source is not None
    assert report.source.to_dict() == {
        "path": "model.py",
        "before": "sha256:" + "a" * 64,
        "after": "sha256:" + "b" * 64,
        "modules": [],
    }
    assert report.to_dict()["source"]["after"] == "sha256:" + "b" * 64
    # Stated, never counted: the fingerprints say whether a calculation moved.
    assert not report.drift


def test_validation_recomputes_both_fingerprints_with_the_selection() -> None:
    for profile in ("audit", "executable"):
        document = _document(_VARIANTS["in force"], profile=profile)
        assert validate_artifact(document, deep=True).ok, profile


def test_validation_refuses_a_selection_step_that_was_edited() -> None:
    document = _document(_VARIANTS["in force"])
    document["selection"][0]["expr"]["right"]["value"] = "LAPSED"
    report = validate_artifact(document)
    assert not report.ok
    assert any(
        finding.where == "/selection/0" and "local_fingerprint" in finding.message
        for finding in report.findings
    )


def test_validation_refuses_a_graph_fingerprint_taken_without_the_selection() -> None:
    selected = _document(_VARIANTS["in force"])
    unselected = _document(_VARIANTS["no selection"])
    selected["graph_fingerprint"] = unselected["graph_fingerprint"]
    findings = validate_artifact(selected, deep=True).findings
    assert any("graph_fingerprint" in finding.message for finding in findings)


def test_a_column_named_into_the_selection_namespace_is_refused() -> None:
    af = ActuarialFrame(pl.DataFrame({"selection:1": [1.0]}))
    af["x"] = af["selection:1"] * 2
    with pytest.raises(ValueError, match="reserved 'selection:' namespace"):
        GraphExporter(af).export()


def test_the_executable_profile_refuses_a_predicate_outside_the_core_vocabulary() -> (
    None
):
    with pytest.raises(ValueError, match=r"selection:1 .*outside the core vocabulary"):
        _document(
            lambda af: af.filter(pl.col("status").str.starts_with("I")),
            profile="executable",
        )
    # The audit record still carries it, as the engine's own text.
    audit = _document(lambda af: af.filter(pl.col("status").str.starts_with("I")))
    assert audit["selection"][0]["tier"] == "engine_native"


def test_the_executable_profile_refuses_a_predicate_over_a_calculated_column() -> None:
    def select(af: ActuarialFrame) -> ActuarialFrame:
        af.band = af.issue_age // 10
        return af.filter(af.band < 5)

    with pytest.raises(ValueError, match="calculates rather than reads from the book"):
        _document(select, profile="executable")


def test_a_rename_on_the_way_in_is_still_the_book_column() -> None:
    def select(af: ActuarialFrame) -> ActuarialFrame:
        af = af.rename({"status": "in_force_status"})
        return af.filter(af.in_force_status == "IF")

    document = _document(select, profile="executable")
    replayed = apply_selection(document, pl.DataFrame(_BOOK))
    assert replayed["policy_id"].to_list() == ["P1", "P2", "P3"]


@pytest.mark.parametrize(
    ("name", "kept"),
    [
        ("no selection", ["P1", "P2", "P3", "P4"]),
        ("in force", ["P1", "P2", "P3"]),
        ("age under 50", ["P1", "P2"]),
        ("in a set", ["P1", "P2", "P3", "P4"]),
        ("semi join", ["P1", "P2"]),
        ("anti join", ["P3", "P4"]),
    ],
)
def test_a_replay_values_exactly_the_policies_the_model_valued(
    name: str, kept: list[str]
) -> None:
    select = _VARIANTS[name]
    af = select(ActuarialFrame(pl.DataFrame(_BOOK)))
    af.premium = af.sum_assured * 0.002
    model = af.collect()["policy_id"].to_list()
    document = json.loads(GraphExporter(af).export(profile="executable"))
    replayed = apply_selection(document, pl.DataFrame(_BOOK))["policy_id"].to_list()
    assert model == kept
    assert replayed == kept


def test_a_null_predicate_keeps_nothing_on_the_replay_as_in_the_model() -> None:
    book = pl.DataFrame({"policy_id": ["P1", "P2"], "status": ["IF", None]})
    af = ActuarialFrame(book).filter(pl.col("status") == "IF")
    af.one = af.policy_id.is_not_null()
    document = json.loads(GraphExporter(af).export(profile="executable"))
    assert apply_selection(document, book)["policy_id"].to_list() == ["P1"]
    assert af.collect()["policy_id"].to_list() == ["P1"]


def test_filter_takes_a_condition_built_from_the_frame() -> None:
    """``af.filter(af.status == "IF")`` used to raise 'invalid predicate'."""
    af = ActuarialFrame(pl.DataFrame(_BOOK))
    af = af.filter(af.status == "IF")
    assert af.collect()["policy_id"].to_list() == ["P1", "P2", "P3"]


def test_filter_refuses_what_is_not_a_condition() -> None:
    af = ActuarialFrame(pl.DataFrame(_BOOK))
    with pytest.raises(TypeError, match="filter\\(\\) takes a condition"):
        af.filter("status == 'IF'")  # type: ignore[arg-type]


def test_the_phase_one_rebuild_route_is_unchanged() -> None:
    """Filtering the collected book and building a new frame records no step.

    The rebuilt frame is the book: it never held the other policies, so its
    book digest moves and no selection is recorded.
    """
    af = ActuarialFrame(pl.DataFrame(_BOOK))
    rebuilt = ActuarialFrame(af.collect().filter(pl.col("status") == "IF"))
    rebuilt.premium = rebuilt.sum_assured * 0.002
    document = json.loads(GraphExporter(rebuilt).export())
    plain = _document(_VARIANTS["no selection"])
    assert "selection" not in document
    assert document["graph_fingerprint"] == plain["graph_fingerprint"]
    assert document["book"]["digest"] != plain["book"]["digest"]


def test_a_mask_and_a_selection_are_two_different_models() -> None:
    """The ruling's alternative route stays recorded, and is not the selection."""

    def masked(af: ActuarialFrame) -> ActuarialFrame:
        af.in_force = when(af.status == "IF").then(1.0).otherwise(0.0)
        return af

    assert _identities(_document(masked)) != _identities(
        _document(_VARIANTS["in force"])
    )


_MODEL = """
import polars as pl
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame, params=None) -> ActuarialFrame:
    af = af.filter(pl.col("status") == "IF")
    af.premium = af.sum_assured * 0.002
    return af
"""


def test_the_sampled_policy_is_still_found_again_after_a_filter(tmp_path: Path) -> None:
    """Section 7.4 holds: a selected row is found again by identity, never counted to.

    P1 is lapsed here, so the finished frame's first row is P2. The default
    selection (row 0 of the book) is refused as a policy the model does not
    keep, and a policy named by its identifier is quoted with its own numbers.
    """
    from typer.testing import CliRunner

    from gaspatchio.cli import app

    book = pl.DataFrame({**_BOOK, "status": ["LAPSED", "IF", "IF", "IF"]})
    (tmp_path / "model.py").write_text(_MODEL)
    book.write_parquet(tmp_path / "mp.parquet")
    runner = CliRunner()

    def export(*extra: str) -> object:
        return runner.invoke(
            app,
            [
                "calc-graph",
                str(tmp_path / "model.py"),
                str(tmp_path / "mp.parquet"),
                "-o",
                str(tmp_path / "a.audit.json"),
                *extra,
            ],
        )

    refused = export()
    named = export("--policies", "P3", "--policy-id-column", "policy_id")

    assert refused.exit_code != 0  # type: ignore[attr-defined]
    assert named.exit_code == 0, named.output  # type: ignore[attr-defined]
    document = json.loads((tmp_path / "a.audit.json").read_text())
    premium = next(node for node in document["nodes"] if node["id"] == "premium@1")
    assert document["enrichment"]["policy_id"] == "P3"
    assert math.isclose(premium["value_sample"], 100.0)
    assert document["selection"][0]["kind"] == "filter"


# A model whose only step is choosing which policies it values is a model:
# section 7.6 makes the selection a member of the record, and nothing in
# section 7 asks a document for a calculated node. Before, the exporter refused
# it as "No calculations found".
_ONLY: dict[str, Callable[[ActuarialFrame], ActuarialFrame]] = {
    "in force": lambda af: af.filter(af.status == "IF"),
    "lapsed": lambda af: af.filter(af.status == "LAPSED"),
    "semi join": _VARIANTS["semi join"],
}


@pytest.mark.parametrize("profile", ["audit", "executable"])
@pytest.mark.parametrize("name", list(_ONLY))
def test_a_model_that_only_selects_is_exported_with_its_selection(
    name: str, profile: str
) -> None:
    af = _ONLY[name](ActuarialFrame(pl.DataFrame(_BOOK)))
    document = json.loads(GraphExporter(af).export(profile=profile))  # type: ignore[arg-type]
    assert {node["kind"] for node in document["nodes"]} == {"input"}
    assert document["edges"] == []
    (step,) = document["selection"]
    assert step["tier"] == "core"
    assert validate_artifact(document).findings == ()


def _frame() -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame(_BOOK))


def test_models_that_only_select_are_told_apart_by_what_they_select() -> None:
    seen = {
        name: _identities(json.loads(GraphExporter(select(_frame())).export()))
        for name, select in _ONLY.items()
    }
    assert len({graph for graph, _ in seen.values()}) == len(_ONLY)
    assert len({formulas for _, formulas in seen.values()}) == len(_ONLY)


def test_a_replay_of_a_model_that_only_selects_keeps_its_policies() -> None:
    af = _ONLY["in force"](ActuarialFrame(pl.DataFrame(_BOOK)))
    document = json.loads(GraphExporter(af).export(profile="executable"))
    replayed = apply_selection(document, pl.DataFrame(_BOOK))
    assert replayed["policy_id"].to_list() == ["P1", "P2", "P3"]
    assert af.collect()["policy_id"].to_list() == ["P1", "P2", "P3"]


def test_a_frame_that_neither_calculates_nor_selects_is_still_refused() -> None:
    with pytest.raises(ValueError, match="No calculations found"):
        GraphExporter(ActuarialFrame(pl.DataFrame(_BOOK))).export()


_ONLY_SELECTS = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame, params=None) -> ActuarialFrame:
    return af.filter(af.status == "IF")
"""


def test_calc_graph_writes_a_model_that_only_selects_with_its_results(
    tmp_path: Path,
) -> None:
    from typer.testing import CliRunner

    from gaspatchio.cli import app

    (tmp_path / "model.py").write_text(_ONLY_SELECTS)
    pl.DataFrame(_BOOK).write_parquet(tmp_path / "mp.parquet")
    ran = CliRunner().invoke(
        app,
        [
            "calc-graph",
            str(tmp_path / "model.py"),
            str(tmp_path / "mp.parquet"),
            "-o",
            str(tmp_path / "a.audit.json"),
            "--results",
            str(tmp_path / "r.parquet"),
        ],
    )
    assert ran.exit_code == 0, ran.output
    document = json.loads((tmp_path / "a.audit.json").read_text())
    assert document["selection"][0]["reads"] == ["status"]
    assert document["model"]["results"]["fingerprint"].startswith("sha256:")
    assert pl.read_parquet(tmp_path / "r.parquet")["policy_id"].to_list() == [
        "P1",
        "P2",
        "P3",
    ]
