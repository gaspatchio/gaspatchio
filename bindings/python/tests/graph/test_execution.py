# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An internally valid account can still lack the means to execute it."""

from __future__ import annotations

import datetime
import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import (
    GraphExporter,
    document_digest_of,
    inspect_execution,
    validate_artifact,
)
from gaspatchio.frame.graph.execution import ExecutionFinding, _inspect_compilation
from gaspatchio.frame.lowering import artefacts
from gaspatchio.rollforward import RollforwardBuilder, compile_rollforward
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from pathlib import Path


def _export(frame: ActuarialFrame, *, include_tables: bool = True) -> dict[str, Any]:
    return json.loads(
        GraphExporter(frame).export(profile="executable", include_tables=include_tables)
    )


def _simple() -> dict[str, Any]:
    frame = ActuarialFrame({"amount": [1.0, 2.0], "unused": [3, 4]})
    frame.total = frame.amount * 2.0
    frame.total = frame.total + 1.0
    return _export(frame)


def _lookup() -> dict[str, Any]:
    frame = ActuarialFrame({"age": [40, 41]})
    table = Table(
        name="mortality",
        source=pl.DataFrame({"age": [40, 41], "rate": [0.1, 0.2]}),
        dimensions={"age": "age"},
        value="rate",
    )
    frame.qx = table.lookup(age=frame.age)
    frame.age_copy = frame.age * 1.0
    return _export(frame)


def _machine() -> dict[str, Any]:
    frame = ActuarialFrame({"initial": [100.0], "rate": [[0.1, 0.2]]})
    schedule = Schedule.from_calendar_grid(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="1M"
    )
    builder = RollforwardBuilder(states={"fund": frame.initial}, schedule=schedule)
    builder["fund"].grow(frame.rate, label="interest")
    frame.fund = compile_rollforward(builder).expr_for("fund")
    return _export(frame)


def _reseal(artifact: dict[str, Any]) -> None:
    """Model a producer exporting different optional payload metadata."""
    artifact["document_digest"] = document_digest_of(artifact)
    assert validate_artifact(artifact, deep=True).ok


def _reseal_an_edited_machine(artifact: dict[str, Any]) -> list[ExecutionFinding]:
    """Reseal a document whose compiled machine was edited, and read the machine.

    The body is published under the identity the producer compiled, so the
    deep reading refuses it before anything is inspected (spec 12.1): an edited
    machine is never run. What the execution reading would also say of such a
    body -- which a second producer could publish under its own identity --
    is read off the compilation inspection directly.
    """
    artifact["document_digest"] = document_digest_of(artifact)
    (fingerprint,) = artifact["facets"]["gaspatchio_rollforward_ir"]["compilations"]
    report = inspect_execution(artifact)
    assert not report.validation.ok
    assert any(
        finding.severity == "error" and finding.where.endswith(fingerprint)
        for finding in report.validation.findings
    )
    by_id = {node["id"]: node for node in artifact["nodes"]}
    (node,) = [node for node in artifact["nodes"] if node["kind"] == "rollforward"]
    return list(
        _inspect_compilation(node, artifact, artifact["assumptions"], {}, by_id)
    )


def test_complete_artifact_leaves_consumer_claims_unchecked() -> None:
    report = inspect_execution(_simple())
    assert report.validation.ok
    assert report.checks == {
        "artifact_validity": "passed",
        "portable_structure": "passed",
        "declared_payloads": "passed",
        "operation_semantics": "not_checked",
        "input_values": "not_checked",
        "backend_support": "not_checked",
        "numerical_conformance": "not_checked",
    }
    assert json.loads(json.dumps(report.to_dict()))["checks"] == report.checks
    assert {item.column for item in report.required_inputs} == {"amount", "unused"}


def test_exact_roots_follow_historical_reads_and_do_not_include_unused_inputs() -> None:
    artifact = _simple()
    report = inspect_execution(artifact, roots=["total@2"])
    assert report.roots == ("total@2",)
    assert report.reachable == ("amount", "total@1", "total@2")
    assert [item.node_id for item in report.required_inputs] == ["amount"]
    assert inspect_execution(artifact, roots=["total@1"]).reachable == (
        "amount",
        "total@1",
    )
    assert inspect_execution(artifact, roots=[]).reachable == ()
    unknown = inspect_execution(artifact, roots=["total"])
    assert unknown.findings[0].code == "unknown_root"
    assert unknown.checks["declared_payloads"] == "blocked"


def test_input_forms_and_invalid_document_do_not_bypass_deep_validation(
    tmp_path: Path,
) -> None:
    artifact = _simple()
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact))
    expected = inspect_execution(artifact).to_dict()
    assert inspect_execution(path).to_dict() == expected
    assert inspect_execution(path.read_text()).to_dict() == expected
    artifact["graph_fingerprint"] = "sha256:" + "0" * 64
    report = inspect_execution(artifact)
    assert report.checks["artifact_validity"] == "failed"
    assert report.checks["portable_structure"] == "blocked"
    assert not report.reachable
    assert not inspect_execution("[]").validation.ok


def test_audit_profile_does_not_claim_payload_closure() -> None:
    frame = ActuarialFrame({"amount": [1.0]})
    frame.total = frame.amount * 2.0
    report = inspect_execution(GraphExporter(frame).export())
    assert report.validation.ok
    assert report.checks["portable_structure"] == "failed"
    assert report.checks["declared_payloads"] == "blocked"


def test_native_branch_is_refused_only_when_reachable() -> None:
    frame = ActuarialFrame({"amount": [[1.0, 2.0]]})
    frame.total = frame.amount * 2.0
    frame.first = frame.amount.polars_native().list.head(1)
    artifact = _export(frame)
    assert inspect_execution(artifact).checks["portable_structure"] == "failed"
    assert (
        inspect_execution(artifact, roots=["total@1"]).checks["portable_structure"]
        == "passed"
    )


def test_external_payload_fills_an_omission_without_rewriting_the_artifact() -> None:
    artifact = _lookup()
    entry = artifact["assumptions"][0]
    key = (entry["kind"], entry["name"], entry["fingerprint"])
    payload = entry["payload"]
    entry["payload"] = {"omitted": "unavailable"}
    _reseal(artifact)
    before = deepcopy(artifact)
    report = inspect_execution(artifact)
    assert report.validation.ok
    assert report.checks["declared_payloads"] == "failed"
    finding = next(item for item in report.findings if item.code == "missing_payload")
    assert key[1] in finding.message
    assert key[2] in finding.message
    assert "qx@1" in finding.where
    supplied = inspect_execution(artifact, payloads={key: payload})
    assert supplied.checks["declared_payloads"] == "passed"
    assert supplied.validation == report.validation
    assert artifact == before
    wrong = inspect_execution(
        artifact, payloads={(key[0], "another_name", key[2]): payload}
    )
    assert wrong.checks["declared_payloads"] == "failed"


def test_one_source_read_under_two_roles_is_two_bases() -> None:
    """The same file keyed two ways carries two fingerprints, and both payloads.

    A table's fingerprint is taken over its canonical form, answer column last
    (spec section 12.3), so the roles are part of the content: the two readings
    can no longer share one digest, and neither payload is withheld as
    ambiguous.
    """
    source = pl.DataFrame({"left": [1.0, 2.0], "right": [10.0, 20.0]})
    by_left = Table(
        name="execution_roles_by_left",
        source=source,
        dimensions={"left": "left"},
        value="right",
        storage_mode="hash",
    )
    by_right = Table(
        name="execution_roles_by_right",
        source=source,
        dimensions={"right": "right"},
        value="left",
        storage_mode="hash",
    )
    frame = ActuarialFrame({"left": [1.0], "right": [20.0]})
    frame.answer_by_left = by_left.lookup(left=frame.left)
    frame.answer_by_right = by_right.lookup(right=frame.right)

    result = frame.collect()
    assert result["answer_by_left"].to_list() == [10.0]
    assert result["answer_by_right"].to_list() == [2.0]

    artifact = _export(frame)
    entries = {entry["name"]: entry for entry in artifact["assumptions"]}
    assert (
        entries["execution_roles_by_left"]["fingerprint"]
        != entries["execution_roles_by_right"]["fingerprint"]
    )
    assert entries["execution_roles_by_left"]["fingerprint"] == by_left.fingerprint()
    assert entries["execution_roles_by_right"]["fingerprint"] == by_right.fingerprint()
    assert all("omitted" not in entry["payload"] for entry in entries.values())
    assert validate_artifact(artifact, deep=True).ok

    inspection = inspect_execution(artifact)
    assert inspection.checks["portable_structure"] == "passed"
    assert inspection.checks["declared_payloads"] == "passed"
    assert len(entries) == 2


def test_supplied_payload_is_verified_even_beside_a_valid_inline_one() -> None:
    artifact = _lookup()
    entry = artifact["assumptions"][0]
    key = (entry["kind"], entry["name"], entry["fingerprint"])
    bad = deepcopy(entry["payload"])
    bad["rows"][0][-1] = 0.9
    report = inspect_execution(artifact, payloads={key: bad})
    assert report.validation.ok
    assert any(item.code == "unverified_payload" for item in report.findings)
    good = entry["payload"]
    entry["payload"] = bad
    report = inspect_execution(artifact, payloads={key: good})
    assert not report.validation.ok


def test_facet_schedule_dependency_is_found_without_usage_metadata() -> None:
    artifact = _machine()
    for node in artifact["nodes"]:
        node["reads_assumptions"] = []
    artifact["assumptions"] = []
    _reseal(artifact)
    report = inspect_execution(artifact)
    assert report.validation.ok
    assert any(
        item.code == "missing_assumption" and "/schedule" in item.where
        for item in report.findings
    )


def test_missing_compilation_cannot_borrow_from_the_producer_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = _machine()
    assert inspect_execution(artifact).checks["portable_structure"] == "passed"
    monkeypatch.setattr(artefacts, "_ROLLFORWARDS", {})
    monkeypatch.setattr(artefacts, "_SCHEDULES", {})
    assert inspect_execution(artifact).checks["declared_payloads"] == "passed"
    artifact["facets"].pop("gaspatchio_rollforward_ir")
    artifact["facets_used"].remove("gaspatchio_rollforward_ir")
    _reseal(artifact)
    report = inspect_execution(artifact)
    assert any(item.code == "missing_compilation_facet" for item in report.findings)


def test_whole_rollforward_struct_binds_to_its_compilation() -> None:
    """The raw struct extraction reads the machine, as state extractions do."""
    frame = ActuarialFrame({"initial": [100.0], "rate": [[0.1, 0.2]]})
    schedule = Schedule.from_calendar_grid(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="1M"
    )
    builder = RollforwardBuilder(states={"fund": frame.initial}, schedule=schedule)
    builder["fund"].grow(frame.rate, label="interest")
    frame.machine = compile_rollforward(builder).plugin_expr()
    frame = frame.drop("machine")

    artifact = _export(frame)
    assert validate_artifact(artifact, deep=True).ok
    report = inspect_execution(artifact, roots=["machine@1"])

    assert report.checks["portable_structure"] == "passed"
    assert not any(item.code == "read_binding_mismatch" for item in report.findings)


@pytest.mark.parametrize("field", ["init", "operand", "contract_boundary"])
def test_native_trees_inside_compilation_are_not_hidden_by_its_core_label(
    field: str,
) -> None:
    artifact = _machine()
    body = next(
        iter(artifact["facets"]["gaspatchio_rollforward_ir"]["compilations"].values())
    )
    native = {"op": "engine_native", "engine": "polars", "text": "opaque", "deps": []}
    if field == "init":
        body["states"][0]["init"] = native
    elif field == "operand":
        body["increments"][0]["operands"][0] = native
    else:
        body[field] = native
    findings = _reseal_an_edited_machine(artifact)
    assert any(
        item.code == "nonportable_expression" and "/facets/" in item.where
        for item in findings
    )


@pytest.mark.parametrize(
    "body", [{}, {"states": None}, {"states": [], "increments": [None]}]
)
def test_incomplete_optional_compilation_is_not_treated_as_an_empty_machine(
    body: dict[str, Any],
) -> None:
    artifact = _machine()
    compilations = artifact["facets"]["gaspatchio_rollforward_ir"]["compilations"]
    compilations[next(iter(compilations))] = body
    findings = _reseal_an_edited_machine(artifact)
    assert any(item.check == "portable_structure" for item in findings)


def test_declared_only_assumption_still_requires_values() -> None:
    artifact = _lookup()
    entry = artifact["assumptions"][0]
    entry["payload"] = {"omitted": "unavailable"}
    artifact["nodes"][-1]["reads_assumptions"] = [entry["name"]]
    _reseal(artifact)
    report = inspect_execution(artifact, roots=["age_copy@1"])
    assert report.checks["declared_payloads"] == "failed"
    assert any(item.code == "missing_payload" for item in report.findings)


def test_facet_cannot_smuggle_a_read_outside_the_versioned_dependency_graph() -> None:
    artifact = _machine()
    body = next(
        iter(artifact["facets"]["gaspatchio_rollforward_ir"]["compilations"].values())
    )
    body["states"][0]["init"] = {"op": "col", "name": "undeclared_input"}
    findings = _reseal_an_edited_machine(artifact)
    assert any(item.code == "read_binding_mismatch" for item in findings)


def test_foreign_facet_version_and_internal_state_root_are_explicit_refusals() -> None:
    artifact = _machine()
    state_id = next(node["id"] for node in artifact["nodes"] if node["kind"] == "state")
    report = inspect_execution(artifact, roots=[state_id])
    assert any(item.code == "internal_state_root" for item in report.findings)
    facet = artifact["facets"]["gaspatchio_rollforward_ir"]
    facet["_schemaURL"] = "https://example.org/another-schema.json"
    _reseal(artifact)
    report = inspect_execution(artifact)
    assert any(item.code == "unknown_compilation_format" for item in report.findings)
    assert report.checks["declared_payloads"] == "failed"


def test_a_core_call_is_not_a_signature_or_domain_certificate() -> None:
    frame = ActuarialFrame({"periods": [[1.0, 2.0], [3.0]], "indicator": [0.5, 1.0]})
    frame.result = frame.periods * frame.indicator
    report = inspect_execution(_export(frame))
    assert report.checks["portable_structure"] == "passed"
    assert report.checks["input_values"] == "not_checked"
    assert report.checks["backend_support"] == "not_checked"


@pytest.mark.parametrize("field", ["dtype", "shape"])
def test_unknown_input_interface_is_named(field: str) -> None:
    artifact = _simple()
    leaf = artifact["nodes"][0]
    # Section 10 permits ``unknown`` on the model's history and nowhere else,
    # and the validator holds a document to that -- so the leaf here is one
    # the model renamed or dropped, which is the shape an arriving column of
    # a type this vocabulary cannot name actually reaches. The inspector is
    # asking the other question, and asks it of every input leaf: this is a
    # column it would have to be handed, and the file does not say what to
    # hand it.
    leaf["in_final_schema"] = False
    leaf[field] = "unknown"
    _reseal(artifact)
    report = inspect_execution(artifact)
    assert any(item.code == f"input_{field}_unknown" for item in report.findings)


def test_internal_hole_is_not_a_supplied_input() -> None:
    frame = ActuarialFrame({"amount": [1.0]})
    frame.total = frame.amount * 2.0
    plan = frame._df  # noqa: SLF001 -- deliberately bypass recording to create a hole
    assert plan is not None
    frame._df = plan.with_columns(pl.lit(1.0).alias("missing"))  # noqa: SLF001
    artifact = _export(frame)
    report = inspect_execution(artifact)
    assert report.validation.ok
    assert any(item.code == "unavailable_calculation" for item in report.findings)
    assert "missing" not in {item.column for item in report.required_inputs}


def _unrecorded(*, dropped: bool) -> dict[str, Any]:
    """Return an artifact whose calculation reads a column nothing recorded."""
    frame = ActuarialFrame({"amount": [1.0]})
    plan = frame._df  # noqa: SLF001 -- deliberately bypass recording to create a hole
    assert plan is not None
    frame._df = plan.with_columns((pl.col("amount") * 2.0).alias("extra"))  # noqa: SLF001
    frame.total = frame["extra"] + 1.0
    if dropped:
        frame = frame.drop("extra")
    return _export(frame)


@pytest.mark.parametrize("dropped", [False, True], ids=["held", "dropped"])
def test_an_unrecorded_hole_is_told_the_move_that_records_it(*, dropped: bool) -> None:
    """Exporting again records nothing: the move is to record it or load it."""
    [hole] = [
        item
        for item in inspect_execution(_unrecorded(dropped=dropped)).findings
        if item.code == "unavailable_calculation"
    ]

    assert hole.where == "/nodes/extra"
    assert hole.move is not None
    assert "af['extra'] = ..." in hole.move
    assert "model points" in hole.move
    assert "payloads" not in hole.move
    assert "'extra'" in hole.message


def _joined(*, lazy: bool = False) -> dict[str, Any]:
    """Return a joined model's executable artifact.

    The shape the measurement filed against §11.1.2: a column that arrived
    from a second table, with a calculation resting on it. The right side
    used to be out of band, so a consumer holding this file could read
    what the join did and could not do it.
    """
    frame = ActuarialFrame({"policy_id": [1, 2], "product_code": ["TERM", "WL"]})
    right = pl.DataFrame(
        {"product_code": ["TERM", "WL"], "expense_loading": [0.05, 0.08]}
    )
    frame = frame.join(right.lazy() if lazy else right, on="product_code")
    frame.expenses = frame.expense_loading * 1_000.0
    return _export(frame)


def test_a_joined_model_resolves_its_right_side_from_the_file() -> None:
    """The executable profile is self-contained for a joined model (section 11.1.2)."""
    report = inspect_execution(_joined())

    assert report.checks["declared_payloads"] == "passed"
    assert not report.findings


def test_a_deleted_right_side_is_reported_as_a_missing_assumption() -> None:
    """The node names an entry; an artifact without it resolves to none."""
    artifact = _joined()
    artifact["assumptions"] = [
        entry for entry in artifact["assumptions"] if entry["kind"] != "join"
    ]
    _reseal(artifact)

    report = inspect_execution(artifact)

    assert report.checks["declared_payloads"] == "failed"
    assert [item.code for item in report.findings] == ["missing_assumption"]


def test_an_edited_right_side_fails_the_re_hash_the_entry_invites() -> None:
    """A payload that hashes to something else is not the table the run used.

    Caught where every inline payload is caught: the document itself is
    invalid, so the payload check is blocked behind that verdict rather than
    reporting a second time on the same fact.
    """
    artifact = _joined()
    entry = next(item for item in artifact["assumptions"] if item["kind"] == "join")
    columns = [column["dtype"] for column in entry["payload"]["columns"]]
    entry["payload"]["rows"][0][columns.index("f64")] += 0.01
    artifact["document_digest"] = document_digest_of(artifact)

    report = inspect_execution(artifact)

    assert not report.validation.ok
    assert any(
        finding.severity == "error" and "/assumptions/" in finding.where
        for finding in report.validation.findings
    )
    assert report.checks["declared_payloads"] == "blocked"


def test_a_lazy_right_side_is_the_one_join_the_file_cannot_answer_for() -> None:
    """No identity was taken, so there is no entry and none is asked for."""
    report = inspect_execution(_joined(lazy=True))

    assert report.checks["declared_payloads"] == "failed"
    finding = next(
        item for item in report.findings if item.code == "join_data_unavailable"
    )
    assert "lazily" in finding.message


def test_a_floored_machine_is_complete_though_its_floor_carries_no_label() -> None:
    """A structural step has no name, and a reading that demanded one refused it.

    Section 16.2 says outright that a ``Floor`` and a ``Round`` carry no label
    field -- a floor is a constraint on the balance rather than a movement
    anyone booked -- and names such a step by the reserved ``{kind}@{ordinal}``
    instead. The published schema admits the null, the producer writes it, and
    this reading required a string: every rollforward with a floor in it came
    back *incomplete*, which is the one shape of the teaching model this
    framework ships.
    """
    frame = ActuarialFrame({"initial": [100.0], "rate": [[0.1, -0.9]]})
    schedule = Schedule.from_calendar_grid(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="1M"
    )
    builder = RollforwardBuilder(states={"fund": frame.initial}, schedule=schedule)
    builder["fund"].grow(frame.rate, label="interest")
    builder["fund"].floor(value=20.0)
    frame.fund = compile_rollforward(builder).expr_for("fund")
    artifact = _export(frame)

    body = next(
        iter(artifact["facets"]["gaspatchio_rollforward_ir"]["compilations"].values())
    )
    assert body["increments"][1]["label"] is None

    report = inspect_execution(artifact)

    assert report.checks["portable_structure"] == "passed"
    assert not [
        item for item in report.findings if item.code == "incomplete_compilation"
    ]
