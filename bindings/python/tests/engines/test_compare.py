# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What two engines agreeing means, and when the question cannot be answered.

The rule is section 11.1.12's: two finite results agree when their difference is within
1e-12 of the line's scale, where the scale is the largest magnitude among
the node's own values and the values of every node it reads, over that
policy's whole timeline, on both sides. Integers, booleans, dates, strings,
lengths, null positions, the class of a NaN and the sign of an infinity are
exact; the sign of a zero is not compared.

The third verdict is what a final-schema file makes necessary. The scale
needs the reads and a final-schema file does not carry them, so a line that
fails the reduced test with a read absent is *indeterminate* -- printed with
the scale those reads would have to supply -- and never a disagreement.
"""

from __future__ import annotations

import json
import math
from typing import Any

import polars as pl
import pytest

from gaspatchio.engines.compare import CompareReport, LineComparison, compare_results
from gaspatchio.engines.protocol import ResultManifest

FINGERPRINT = "sha256:" + "ab" * 32
OTHER_FINGERPRINT = "sha256:" + "cd" * 32
BOOK = "sha256:" + "11" * 32
OTHER_BOOK = "sha256:" + "22" * 32
ID = ("policy_id",)


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_physical_carriers_cannot_disagree_with_a_sealed_frame(
    *, nested: bool, reverse: bool
) -> None:
    from gaspatchio import ActuarialFrame
    from gaspatchio.engines.reference import polars_reference
    from gaspatchio.frame.graph import GraphExporter

    af = ActuarialFrame(pl.DataFrame({"amount": [[10.0]] if nested else [10.0]}))
    af.reserve = af.amount * 2
    artifact = json.loads(GraphExporter(af).export(profile="executable"))
    reference, manifest = polars_reference(af, every_node=True)
    candidate = reference.with_columns(
        pl.Series("reserve@1", [[999]] if nested else [999])
    )
    before, after = (candidate, reference) if reverse else (reference, candidate)
    with pytest.raises(ValueError, match=r"reserve@1.*f64"):
        compare_results(
            artifact, before, after, before_manifest=manifest, after_manifest=manifest
        )


@pytest.mark.parametrize("forged", [False, True])
def test_large_integer_one_apart_is_exact_despite_a_manifest(*, forged: bool) -> None:
    artifact = _artifact([_node("a", "i64", kind="input", final=True)])
    manifest = _manifest("every-node", {"a": "a"}, {"a": "f64" if forged else "i64"})
    before = pl.DataFrame({"a": [10**12]})
    after = pl.DataFrame({"a": [10**12 + 1]})
    if forged:
        with pytest.raises(ValueError, match=r"a.*i64"):
            compare_results(
                artifact,
                before,
                after,
                before_manifest=manifest,
                after_manifest=manifest,
            )
    else:
        assert (
            compare_results(
                artifact,
                before,
                after,
                before_manifest=manifest,
                after_manifest=manifest,
            ).verdict
            == "disagree"
        )


@pytest.mark.parametrize("kind", ["computed", "state"])
@pytest.mark.parametrize("omitted", ["both", "before", "physical"])
def test_every_node_requirements_come_from_the_artifact(
    kind: str, omitted: str
) -> None:
    artifact = _artifact(
        [_node("a", "i64", kind="input"), _node("old@1", "i64", kind=kind)]
    )
    frame = pl.DataFrame({"a": [1], "old@1": [2]})
    full = _manifest(
        "every-node", {"a": "a", "old@1": "old@1"}, {"a": "i64", "old@1": "i64"}
    )
    short = _manifest("every-node", {"a": "a"}, {"a": "i64"})
    report = compare_results(
        artifact,
        frame.drop("old@1"),
        frame,
        before_manifest=full if omitted == "physical" else short,
        after_manifest=short if omitted == "both" else full,
    )
    assert ("old@1", "before") in report.missing
    assert (("old@1", "after") in report.missing) == (omitted == "both")
    assert report.verdict == "indeterminate"


def _node(
    node_id: str,
    dtype: str,
    *,
    reads: tuple[str, ...] = (),
    final: bool = False,
    kind: str = "computed",
) -> dict[str, Any]:
    column, _, version = node_id.partition("@")
    return {
        "id": node_id,
        "column": column,
        "version": int(version) if version else None,
        "kind": kind,
        "dtype": dtype,
        "shape": "list" if dtype.startswith("list[") else "scalar",
        "reads": list(reads),
        "in_final_schema": final,
    }


def _artifact(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "gaspatchio-graph/v0-preview.3",
        "profile": "executable",
        "graph_fingerprint": FINGERPRINT,
        "nodes": nodes,
    }


# The five-node shape the agreement cases are argued over: three arriving
# columns, a net that reads two of them, and a present value that reads the
# net. Only the last two are in the model's final schema.
FIVE_NODES = [
    _node("policy_id", "i64", kind="input"),
    _node("a", "f64", kind="input"),
    _node("b", "f64", kind="input"),
    _node("net@1", "f64", reads=("a", "b"), final=True),
    _node("pv@1", "f64", reads=("net@1",), final=True),
]


def _manifest(  # noqa: PLR0913 -- one parameter per field a manifest states
    scope: str,
    columns: dict[str, str],
    dtypes: dict[str, str],
    *,
    producer: str = "polars",
    fingerprint: str = FINGERPRINT,
    book: str = BOOK,
    identity: tuple[str, ...] | None = None,
) -> ResultManifest:
    return ResultManifest(
        scope=scope,  # type: ignore[arg-type]
        columns=columns,
        dtypes=dtypes,
        row_identity=identity,
        graph_fingerprint=fingerprint,
        inputs_digest=book,
        producer=producer,
        versions={},
    )


def _named(
    columns: list[str], dtypes: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    return {name: name for name in columns}, {name: dtypes[name] for name in columns}


def line_for(report: CompareReport, node_id: str) -> LineComparison:
    lines = [one for one in report.lines if one.node_id == node_id]
    assert lines, f"no line for {node_id}"
    return lines[0]


@pytest.mark.parametrize("depth", [0, 1, 2, 3])
def test_logical_integer_normalization_keeps_widths_and_nested_shapes(
    depth: int,
) -> None:
    values: list[Any] = [17]
    physical: pl.DataType | type[pl.DataType] = pl.Int32
    dtype = "i64"
    for _ in range(depth):
        values = [values]
        physical = pl.List(physical)
        dtype = f"list[{dtype}]"
    frame = pl.DataFrame({"a": pl.Series(values, dtype=physical)})
    artifact = _artifact([_node("a", dtype, kind="input")])
    manifest = _manifest("every-node", {"a": "a"}, {"a": dtype})
    assert (
        compare_results(
            artifact, frame, frame, before_manifest=manifest, after_manifest=manifest
        ).verdict
        == "agree"
    )


@pytest.mark.parametrize("shape", ["scalar", "list"])
@pytest.mark.parametrize("reverse", [False, True])
def test_integer_contract_refuses_physical_floats(shape: str, *, reverse: bool) -> None:
    dtype = "i64" if shape == "scalar" else "list[i64]"
    artifact = _artifact([_node("a", dtype, kind="input")])
    manifest = _manifest("every-node", {"a": "a"}, {"a": dtype})
    integer = pl.DataFrame({"a": [10**12] if shape == "scalar" else [[10**12]]})
    floating = pl.DataFrame(
        {"a": [float(10**12)] if shape == "scalar" else [[float(10**12)]]}
    )
    before, after = (floating, integer) if reverse else (integer, floating)
    with pytest.raises(ValueError, match=r"a.*i64"):
        compare_results(
            artifact, before, after, before_manifest=manifest, after_manifest=manifest
        )


@pytest.mark.parametrize("reverse", [False, True])
def test_a_contradictory_manifest_on_either_side_refuses(*, reverse: bool) -> None:
    from dataclasses import replace

    manifest = _manifest("every-node", {"a": "a"}, {"a": "i64"})
    forged = replace(manifest, dtypes={"a": "f64"})
    before, after = (forged, manifest) if reverse else (manifest, forged)
    frame = pl.DataFrame({"a": [10**12]})
    with pytest.raises(ValueError, match=r"a.*i64"):
        compare_results(
            _artifact([_node("a", "i64", kind="input")]),
            frame,
            frame,
            before_manifest=before,
            after_manifest=after,
        )


def test_nested_floats_compare_cells_and_lengths() -> None:
    assert (
        _one_line("list[list[f64]]", [[[1.0, 2.0]]], [[[1.0, 3.0]]]).verdict
        == "disagree"
    )
    assert (
        _one_line("list[list[f64]]", [[[1.0, 2.0]]], [[[1.0]]]).exact_class == "length"
    )


def test_nested_reads_supply_the_same_policy_scale() -> None:
    artifact = _artifact(
        [
            _node("a", "list[list[f64]]", kind="input"),
            _node("net", "f64", reads=("a",)),
        ]
    )
    before = pl.DataFrame({"a": [[[1e6]]], "net": [0.0]})
    after = pl.DataFrame({"a": [[[1e6]]], "net": [1e-7]})
    manifest = _manifest(
        "every-node", {"a": "a", "net": "net"}, {"a": "list[list[f64]]", "net": "f64"}
    )
    report = compare_results(
        artifact, before, after, before_manifest=manifest, after_manifest=manifest
    )
    assert line_for(report, "net").verdict == "agree"
    assert line_for(report, "net").scale == 1e6


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "physical",
        "metadata",
        "unsupported",
        "ambiguous",
        "missing",
        "schedule",
        "operation",
        "target",
    ],
)
@pytest.mark.parametrize("pattern", ["fund", "ratchet"])
@pytest.mark.parametrize("idle", [False, True])
def test_state_contract_comes_from_its_compilation(
    mutation: str, pattern: str, *, idle: bool
) -> None:
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[4]
        / f"engines/jax/tests/models/patterns/{pattern}.artifact.json"
    )
    artifact = json.loads(path.read_text())
    state = next(node for node in artifact["nodes"] if node["kind"] == "state")
    body = next(
        iter(artifact["facets"]["gaspatchio_rollforward_ir"]["compilations"].values())
    )
    # An idle declared state still has a type even when no update reads it.
    if idle:
        body["increments"] = []
    if mutation == "unsupported":
        body["engine_binding"] = "polars"
    elif mutation == "missing":
        body["states"] = []
    elif mutation == "ambiguous":
        owner = next(
            node for node in artifact["nodes"] if node["kind"] == "rollforward"
        )
        artifact["nodes"].append({**owner, "id": "other-owner"})
    elif mutation == "schedule":
        schedule = next(
            entry for entry in artifact["assumptions"] if entry["kind"] == "schedule"
        )
        schedule["payload"]["frequency"] = "1Y"
    elif mutation in {"operation", "target"}:
        body["increments"] = [
            {
                "operation": "Grow" if mutation == "target" else "Invented",
                "operands": [{"op": "state", "name": "not-declared@bop"}] * 2,
                "target": "not-declared@eop",
                "settings": {"round_charge": None},
            }
        ]
    node_id = state["id"]
    frame = pl.DataFrame({node_id: [[1]] if mutation == "physical" else [[1.0]]})
    manifest = _manifest(
        "every-node",
        {node_id: node_id},
        {node_id: "f64" if mutation == "metadata" else "unknown"},
        fingerprint=artifact["graph_fingerprint"],
    )
    if mutation == "none":
        report = compare_results(
            artifact, frame, frame, before_manifest=manifest, after_manifest=manifest
        )
        assert line_for(report, node_id).verdict == "agree"
    else:
        with pytest.raises(ValueError, match=node_id):
            compare_results(
                artifact,
                frame,
                frame,
                before_manifest=manifest,
                after_manifest=manifest,
            )


def test_the_scale_is_the_line_s_over_that_policy() -> None:
    # policy 0: a = b = 17000 and the net cancels to nothing, so a difference
    # of 7e-10 is 4.1e-14 of the line. policy 1: the same difference against
    # operands of 1 is 7e-10 of it, and no policy lends another its allowance.
    dtypes = {
        "policy_id": "i64",
        "a": "f64",
        "b": "f64",
        "net@1": "f64",
        "pv@1": "f64",
    }
    columns, kept = _named(["policy_id", "a", "b", "net@1", "pv@1"], dtypes)
    before = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "a": [17000.0, 1.0],
            "b": [17000.0, 1.0],
            "net@1": [0.0, 0.0],
            "pv@1": [0.0, 0.0],
        }
    )
    after = before.with_columns(pl.Series("net@1", [7e-10, 7e-10]))

    report = compare_results(
        _artifact(FIVE_NODES),
        before,
        after,
        before_manifest=_manifest("every-node", columns, kept),
        after_manifest=_manifest("every-node", columns, kept, producer="jax"),
    )

    net = line_for(report, "net@1")
    assert net.verdict == "disagree"
    assert net.max_ratio == pytest.approx(7e-10)
    assert net.scale == pytest.approx(1.0)
    assert net.reads_absent == ()
    assert report.verdict == "disagree"


def test_a_result_the_scope_requires_but_a_file_lacks_is_missing_and_never_agree() -> (
    None
):
    dtypes = {"net@1": "f64", "pv@1": "f64"}
    frame = pl.DataFrame({"policy_id": [1, 2], "net@1": [1.0, 2.0], "pv@1": [3.0, 4.0]})
    before_columns, before_kept = _named(["net@1", "pv@1"], dtypes)
    after_columns, after_kept = _named(["net@1"], dtypes)

    report = compare_results(
        _artifact(FIVE_NODES),
        frame,
        frame.drop("pv@1"),
        before_manifest=_manifest("final-schema", before_columns, before_kept),
        after_manifest=_manifest("final-schema", after_columns, after_kept),
    )

    assert report.missing == (("pv@1", "after"),)
    assert report.verdict == "indeterminate"


def test_an_empty_scope_cannot_agree() -> None:
    frame = pl.DataFrame({"policy_id": [1, 2]})

    report = compare_results(
        _artifact(FIVE_NODES),
        frame,
        frame,
        before_manifest=_manifest("final-schema", {}, {}),
        after_manifest=_manifest("final-schema", {}, {}),
    )

    assert report.lines == ()
    assert {node for node, _ in report.missing} == {"net@1", "pv@1"}
    assert report.verdict == "indeterminate"


def test_a_read_absent_on_one_side_reduces_the_scale_on_both() -> None:
    # `a` is in the before file and not the after one. A read on one side
    # cannot supply the other's magnitude, so it is out of the scale for both
    # and the line says which read it lost.
    dtypes = {"a": "f64", "b": "f64", "net@1": "f64"}
    before = pl.DataFrame(
        {"policy_id": [1], "a": [17000.0], "b": [1.0], "net@1": [0.0]}
    )
    after = pl.DataFrame({"policy_id": [1], "b": [1.0], "net@1": [1e-13]})
    before_columns, before_kept = _named(["a", "b", "net@1"], dtypes)
    after_columns, after_kept = _named(["b", "net@1"], dtypes)

    report = compare_results(
        _artifact(FIVE_NODES),
        before,
        after,
        before_manifest=_manifest("every-node", before_columns, before_kept),
        after_manifest=_manifest("every-node", after_columns, after_kept),
    )

    net = line_for(report, "net@1")
    assert net.reads_absent == ("a",)
    assert net.scale == pytest.approx(1.0)
    assert net.verdict == "agree"


def test_reads_absent_makes_a_failing_line_indeterminate_not_a_disagreement() -> None:
    dtypes = {"net@1": "f64"}
    columns, kept = _named(["net@1"], dtypes)
    before = pl.DataFrame({"policy_id": [1], "net@1": [0.0]})
    after = pl.DataFrame({"policy_id": [1], "net@1": [7e-10]})

    report = compare_results(
        _artifact(FIVE_NODES),
        before,
        after,
        before_manifest=_manifest("every-node", columns, kept),
        after_manifest=_manifest("every-node", columns, kept),
    )

    net = line_for(report, "net@1")
    assert net.reads_absent == ("a", "b")
    assert net.verdict == "indeterminate"
    assert net.lower_bound == pytest.approx(7e-10 / 1e-12)
    assert report.verdict == "indeterminate"


def test_a_passing_reduced_line_agrees_because_a_larger_scale_could_only_help() -> None:
    dtypes = {"net@1": "f64"}
    columns, kept = _named(["net@1"], dtypes)
    before = pl.DataFrame({"policy_id": [1], "net@1": [1000.0]})
    after = pl.DataFrame({"policy_id": [1], "net@1": [1000.0 + 1e-10]})

    report = compare_results(
        _artifact(FIVE_NODES[:-1]),
        before,
        after,
        before_manifest=_manifest("final-schema", columns, kept),
        after_manifest=_manifest("final-schema", columns, kept),
    )

    net = line_for(report, "net@1")
    assert net.reads_absent == ("a", "b")
    assert net.verdict == "agree"
    assert net.lower_bound is None
    assert report.verdict == "agree"


def _one_line(
    dtype: str, before_values: list[Any], after_values: list[Any]
) -> LineComparison:
    nodes = [_node("policy_id", "i64", kind="input"), _node("x@1", dtype, final=True)]
    columns, kept = _named(["x@1"], {"x@1": dtype})
    ids = list(range(1, len(before_values) + 1))
    report = compare_results(
        _artifact(nodes),
        pl.DataFrame(
            {"policy_id": ids, "x@1": before_values},
            schema_overrides={"x@1": pl.Float64} if dtype == "f64" else None,
        ),
        pl.DataFrame(
            {"policy_id": ids, "x@1": after_values},
            schema_overrides={"x@1": pl.Float64} if dtype == "f64" else None,
        ),
        before_manifest=_manifest("final-schema", columns, kept),
        after_manifest=_manifest("final-schema", columns, kept),
    )
    return line_for(report, "x@1")


def test_exact_classes_compare_exactly() -> None:
    assert _one_line("i64", [7], [8]).verdict == "disagree"
    assert _one_line("i64", [7], [8]).exact_class == "i64"
    assert _one_line("i64", [7], [7]).verdict == "agree"

    lists = _one_line("list[i64]", [[1, 2, 3]], [[1, 2, 4]])
    assert lists.verdict == "disagree"
    assert lists.exact_class == "list[i64]"

    assert _one_line("bool", [True], [False]).verdict == "disagree"
    assert _one_line("str", ["a"], ["b"]).verdict == "disagree"

    assert _one_line("f64", [math.nan], [math.nan]).verdict == "agree"
    inf = _one_line("f64", [math.inf], [-math.inf])
    assert inf.verdict == "disagree"
    assert inf.exact_class == "inf-sign"
    nan_against_value = _one_line("f64", [math.nan], [1.0])
    assert nan_against_value.verdict == "disagree"
    assert nan_against_value.exact_class == "nan-class"

    assert _one_line("f64", [-0.0], [0.0]).verdict == "agree"

    lengths = _one_line("list[f64]", [[1.0, 2.0]], [[1.0]])
    assert lengths.verdict == "disagree"
    assert lengths.exact_class == "length"

    nulls = _one_line("f64", [None], [1.0])
    assert nulls.verdict == "disagree"
    assert nulls.exact_class == "null-positions"


def test_a_line_decided_exactly_reports_no_magnitude() -> None:
    # Two integers one apart are not "zero apart to the last place", which is
    # what a 0.0 here would read as. They parted, and how far apart they were
    # is not a question this rule asks.
    off_by_one = _one_line("i64", [7], [8])
    assert off_by_one.verdict == "disagree"
    assert off_by_one.max_abs is None
    assert off_by_one.to_dict()["max_abs"] is None
    assert json.loads(json.dumps(off_by_one.to_dict()))["max_abs"] is None

    parted_on_an_aspect = _one_line("f64", [math.inf], [-math.inf])
    assert parted_on_an_aspect.max_abs is None

    # A float line the band decided still reports the magnitude it decided on.
    measured = _one_line("f64", [1000.0], [1000.5])
    assert measured.exact_class is None
    assert measured.max_abs == pytest.approx(0.5)


def test_rows_are_matched_by_identity_and_duplicates_refuse() -> None:
    dtypes = {"net@1": "f64"}
    columns, kept = _named(["net@1"], dtypes)
    before = pl.DataFrame({"policy_id": [1, 2], "net@1": [10.0, 20.0]})
    reordered = pl.DataFrame({"policy_id": [2, 1], "net@1": [20.0, 10.0]})

    report = compare_results(
        _artifact(FIVE_NODES),
        before,
        reordered,
        before_manifest=_manifest("final-schema", columns, kept, identity=ID),
        after_manifest=_manifest("final-schema", columns, kept, identity=ID),
    )
    assert report.rows_matched_by == "identity"
    assert report.rows_matched_on == ID
    assert line_for(report, "net@1").verdict == "agree"

    duplicated = pl.DataFrame({"policy_id": [1, 1], "net@1": [10.0, 20.0]})
    with pytest.raises(ValueError, match="1"):
        compare_results(
            _artifact(FIVE_NODES),
            before,
            duplicated,
            before_manifest=_manifest("final-schema", columns, kept, identity=ID),
            after_manifest=_manifest("final-schema", columns, kept, identity=ID),
        )

    dropped = pl.DataFrame({"policy_id": [1, 3], "net@1": [10.0, 20.0]})
    with pytest.raises(ValueError, match="2"):
        compare_results(
            _artifact(FIVE_NODES),
            before,
            dropped,
            before_manifest=_manifest("final-schema", columns, kept, identity=ID),
            after_manifest=_manifest("final-schema", columns, kept, identity=ID),
        )


def test_rows_are_matched_by_position_when_no_identity_is_named() -> None:
    dtypes = {"net@1": "f64"}
    columns, kept = _named(["net@1"], dtypes)
    frame = pl.DataFrame({"net@1": [10.0, 20.0]})

    report = compare_results(
        _artifact(FIVE_NODES),
        frame,
        frame,
        before_manifest=_manifest("final-schema", columns, kept),
        after_manifest=_manifest("final-schema", columns, kept),
    )

    assert report.rows_matched_by == "position"
    assert line_for(report, "net@1").verdict == "agree"


def test_row_counts_that_differ_are_refused() -> None:
    dtypes = {"net@1": "f64"}
    columns, kept = _named(["net@1"], dtypes)
    with pytest.raises(ValueError, match="2 row"):
        compare_results(
            _artifact(FIVE_NODES),
            pl.DataFrame({"net@1": [10.0, 20.0]}),
            pl.DataFrame({"net@1": [10.0]}),
            before_manifest=_manifest("final-schema", columns, kept),
            after_manifest=_manifest("final-schema", columns, kept),
        )


def test_a_manifest_not_bound_to_the_artifact_is_refused() -> None:
    dtypes = {"net@1": "f64"}
    columns, kept = _named(["net@1"], dtypes)
    frame = pl.DataFrame({"policy_id": [1], "net@1": [1.0]})

    with pytest.raises(ValueError, match="not of this artifact") as caught:
        compare_results(
            _artifact(FIVE_NODES),
            frame,
            frame,
            before_manifest=_manifest("final-schema", columns, kept),
            after_manifest=_manifest(
                "final-schema", columns, kept, fingerprint=OTHER_FINGERPRINT
            ),
        )

    assert FINGERPRINT in str(caught.value)
    assert OTHER_FINGERPRINT in str(caught.value)


def test_two_scopes_cannot_be_compared() -> None:
    dtypes = {"net@1": "f64"}
    columns, kept = _named(["net@1"], dtypes)
    frame = pl.DataFrame({"policy_id": [1], "net@1": [1.0]})

    with pytest.raises(ValueError, match="every-node"):
        compare_results(
            _artifact(FIVE_NODES),
            frame,
            frame,
            before_manifest=_manifest("final-schema", columns, kept),
            after_manifest=_manifest("every-node", columns, kept),
        )


def test_different_books_are_stated_not_hidden() -> None:
    dtypes = {"net@1": "f64", "pv@1": "f64"}
    columns, kept = _named(["net@1", "pv@1"], dtypes)
    frame = pl.DataFrame({"policy_id": [1], "net@1": [1.0], "pv@1": [2.0]})

    report = compare_results(
        _artifact(FIVE_NODES),
        frame,
        frame,
        before_manifest=_manifest("final-schema", columns, kept, identity=ID),
        after_manifest=_manifest(
            "final-schema", columns, kept, book=OTHER_BOOK, identity=ID
        ),
    )

    assert report.same_inputs is False
    assert report.verdict == "agree"
    assert report.to_dict()["same_inputs"] is False


def test_the_report_round_trips_through_json() -> None:
    dtypes = {"net@1": "f64", "pv@1": "f64"}
    columns, kept = _named(["net@1", "pv@1"], dtypes)
    frame = pl.DataFrame({"policy_id": [1], "net@1": [1.0], "pv@1": [2.0]})

    report = compare_results(
        _artifact(FIVE_NODES),
        frame,
        frame,
        before_manifest=_manifest("final-schema", columns, kept, identity=ID),
        after_manifest=_manifest(
            "final-schema", columns, kept, producer="jax", identity=ID
        ),
    )

    read = json.loads(json.dumps(report.to_dict()))
    assert read["report_version"] == "gaspatchio-graph-compare/v0-preview.2"
    assert read["artifact_fingerprint"] == FINGERPRINT
    assert read["scope"] == "final-schema"
    assert read["rows_matched_by"] == "identity"
    assert read["rows_matched_on"] == ["policy_id"]
    assert {one["node_id"] for one in read["lines"]} == {"net@1", "pv@1"}
    assert all(one["strict_floor"] for one in read["lines"])


def test_the_strict_floor_is_kept_beside_the_ratio() -> None:
    # The fixed floor -- 1e-10 plus 1e-12 of the reference, the same on every
    # line -- fails on a difference the line's scale forgives, which is exactly
    # the cancellation case: both readings are printed.
    dtypes = {
        "policy_id": "i64",
        "a": "f64",
        "b": "f64",
        "net@1": "f64",
    }
    columns, kept = _named(["policy_id", "a", "b", "net@1"], dtypes)
    before = pl.DataFrame(
        {"policy_id": [1], "a": [17000.0], "b": [17000.0], "net@1": [0.0]}
    )
    after = before.with_columns(pl.Series("net@1", [7e-9]))

    report = compare_results(
        _artifact(FIVE_NODES),
        before,
        after,
        before_manifest=_manifest("every-node", columns, kept),
        after_manifest=_manifest("every-node", columns, kept),
    )

    net = line_for(report, "net@1")
    assert net.verdict == "agree"
    assert net.strict_floor is False
    assert net.max_ratio == pytest.approx(7e-9 / 17000.0)
