# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The rollforward scan: the two shipped patterns, and what the subset refuses.

The acceptance is the two patterns of the rollforward tutorial, each run
through this engine and through Polars and compared node by node to 1e-12 of scale --
and it is a *measurement*: the compared set is computed from the artifact
rather than listed here, and the run prints the set's size and the worst ratio
so a reader of the log holds the number rather than a claim about it.

**The reference is taken fresh, and the command is named.** From
``bindings/python``'s own tutorials through the **core** venv's ``gspio``::

    gspio run-model --every-node <pattern .py> <pattern model points> -o <file>

which writes one column per value-bearing node, keyed by node id -- the
compiled rollforward's running balances among them, through the exporter's own
re-track -- with the result manifest in the Parquet file's own metadata. The
artifacts and books beside this file come from ``tests/models/export.py``,
which runs the same venv's ``gspio calc-graph`` over the same two files.
"""

from __future__ import annotations

import copy
import json
import subprocess
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from gaspatchio.engines import engine_named
from gaspatchio.engines.compare import compare_results
from gaspatchio.engines.protocol import VALUE_BEARING, FrameSink, read_manifest
from gaspatchio.engines.report import EngineRefusal
from gaspatchio_jax.lowerings import REFUSED
from gaspatchio_jax.lowerings.rollforward import (
    _ADMITTED,
    FACET,
    body_of,
    outside_the_subset,
)
from tests.conftest import PROJECT
from tests.models.export import PATTERNS, PATTERNS_FOLDER, TUTORIALS

if TYPE_CHECKING:
    from pathlib import Path

    from gaspatchio.engines.protocol import ResultManifest

MODELS = PROJECT / "tests/models/patterns"
CORE = PROJECT.parents[1] / "bindings/python"
CORE_GSPIO = CORE / ".venv/bin/gspio"

# The two goldens section 17 stands behind, in the repository rather than in
# the wheel: they are the only artifacts anywhere that carry one of the two
# kinds this engine refuses by name, and what a reader is owed is the sentence
# the engine says about the record those files hold.
GOLDENS = CORE / "tests/graph/goldens"

# What each pattern's artifact carries, measured at the keyboard and stated so
# that a model that quietly shrank fails here rather than passing on a smaller
# set. The step counts are the schedules', and are read from the artifact in
# the test rather than compared against these.
NODES = {"fund": 10, "ratchet": 13}

# The four operation names 16.1 states are *not* in its list, quoted from the
# subsection itself. The list is closed, and a closed list is only worth
# having if something fails when it opens.
OUTSIDE_THE_LIST = ("GrowCapped", "DeductNAR", "Round", "Apply")


def _artifact(pattern: str) -> dict[str, Any]:
    """Return one committed executable artifact."""
    read: dict[str, Any] = json.loads(
        (MODELS / f"{pattern}.artifact.json").read_text(encoding="utf-8")
    )
    return read


def _book(pattern: str) -> pl.DataFrame:
    """Return the model points both sides read."""
    return pl.read_parquet(MODELS / f"{pattern}.book.parquet")


def _compilation(artifact: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return the one machine an artifact carries, by its own identity."""
    compilations = artifact["facets"][FACET]["compilations"]
    fingerprint = next(iter(compilations))
    body: dict[str, Any] = compilations[fingerprint]
    return fingerprint, body


def _periods(artifact: dict[str, Any]) -> int:
    """Return the step count the machine's schedule supplies, off the document."""
    _fingerprint, body = _compilation(artifact)
    entry = next(
        one
        for one in artifact["assumptions"]
        if one["kind"] == "schedule" and one["fingerprint"] == body["schedule"]
    )
    return int(entry["payload"]["n_periods"])


def _value_bearing(artifact: dict[str, Any]) -> set[str]:
    """Return every node id an ``every-node`` result is required to carry.

    Computed from the artifact rather than listed: a compiled rollforward's
    running balance is a value and the bare compilation node is not -- it is
    one state machine that every extraction from it reads.
    """
    return {
        str(node["id"])
        for node in artifact["nodes"]
        if node.get("kind") in VALUE_BEARING
    }


@pytest.fixture(scope="module")
def references(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Return each pattern's fresh every-node Polars answers, by node id."""
    written = tmp_path_factory.mktemp("patterns")
    for pattern, (source, points) in PATTERNS.items():
        out = written / f"{pattern}.parquet"
        finished = subprocess.run(  # noqa: S603 -- the core's own venv and tutorials
            [
                str(CORE_GSPIO),
                "run-model",
                "--every-node",
                str(CORE / TUTORIALS / PATTERNS_FOLDER / source),
                str(CORE / TUTORIALS / PATTERNS_FOLDER / points),
                "-o",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
            cwd=CORE,
        )
        assert finished.returncode == 0, finished.stdout + finished.stderr
        assert out.exists()
    return {pattern: written / f"{pattern}.parquet" for pattern in PATTERNS}


@pytest.mark.parametrize("pattern", ["fund", "ratchet"])
def test_the_compared_node_set_is_the_value_bearing_set_and_every_line_agrees(
    pattern: str, references: dict[str, Path]
) -> None:
    """Both patterns, node by node, against the producer's own every-node answers.

    The compared set first, because a comparison over a set that quietly
    shrank agrees about nothing: what is asserted is that every value-bearing
    node the artifact carries -- the running balances among them -- is on both
    sides, and only then that every line agrees.
    """
    artifact = _artifact(pattern)
    reference = pl.read_parquet(references[pattern])
    manifest: ResultManifest = read_manifest(references[pattern])
    result = engine_named("jax").run(
        artifact, _book(pattern), FrameSink(), every_node=True
    )
    expected_ids = _value_bearing(artifact)
    assert set(result.manifest.columns) == expected_ids
    assert set(manifest.columns) == expected_ids
    assert len(expected_ids) == NODES[pattern]
    # The artifact normalizes physical Int32 inputs to its i64 carrier.
    # Every other physical dtype must match; all values compare exactly.
    declared = {node["id"]: node["dtype"] for node in artifact["nodes"]}
    for node_id in expected_ids:
        left = reference[node_id].dtype
        right = result.columns[node_id].dtype
        if left != right:
            assert (left, right, declared[node_id]) in (
                (pl.Int32, pl.Int64, "i64"),
                (pl.List(pl.Int32), pl.List(pl.Int64), "list[i64]"),
            )
    columns = sorted(expected_ids)
    assert_frame_equal(
        reference.select(columns),
        result.columns.select(columns),
        check_dtypes=False,
        check_exact=True,
    )
    report = compare_results(
        artifact,
        reference,
        result.columns,
        before_manifest=manifest,
        after_manifest=result.manifest,
    )
    assert report.missing == ()
    assert report.same_inputs
    disagreeing = [one for one in report.lines if one.verdict != "agree"]
    assert report.verdict == "agree", disagreeing
    # The worst of the lines that *have* a ratio. A line the exact classes
    # decided -- a Boolean mask, a calendar date -- reports none at all, and
    # naming one of those as the worst would record a node no arithmetic ran
    # through.
    measured = [one for one in report.lines if one.max_ratio is not None]
    at = max(measured, key=lambda one: one.max_ratio or 0.0)
    worst = at.max_ratio or 0.0
    print(  # noqa: T201 -- the measurement is the point of this test
        f"{pattern}: {len(report.lines)} lines ({len(measured)} with a ratio), "
        f"scope {report.scope}, rows by {report.rows_matched_by}, "
        f"{_periods(artifact)} periods, worst ratio {worst:.6e} at {at.node_id}"
    )
    recorded = _recorded(pattern)
    assert at.node_id == recorded["node"], (at.node_id, recorded["node"])
    assert worst <= recorded["ratio"], (worst, recorded["ratio"])


def _recorded(pattern: str) -> dict[str, Any]:
    """Return what ``agreement.json`` records as this pattern's worst line."""
    read: dict[str, dict[str, dict[str, Any]]] = json.loads(
        (PROJECT / "agreement.json").read_text(encoding="utf-8")
    )
    return read["models"][pattern]


@pytest.mark.parametrize("pattern", ["fund", "ratchet"])
def test_every_balance_is_the_machine_s_own_number_of_periods(pattern: str) -> None:
    """The step count is the schedule's, and no operand or sidecar supplies one.

    These patterns have operand widths equal to their schedules. The scalar
    operand witness below separately rules out sizing from operand lengths.
    """
    artifact = _artifact(pattern)
    result = engine_named("jax").run(
        artifact, _book(pattern), FrameSink(), every_node=True
    )
    periods = _periods(artifact)
    balances = [
        node_id for node_id in result.manifest.columns if node_id.startswith("state:")
    ]
    assert balances
    for node_id in balances:
        assert result.columns[node_id].list.len().to_list() == [periods] * (
            result.columns.height
        )


def test_an_infinite_state_refuses_at_completion_naming_the_step() -> None:
    """A balance that stops being finite withholds the run, and says where.

    The falsification this engine's rollforward is measured by. The opening balance is
    ``1e308`` -- a number, and finite -- and the fund grows by its own value
    in the first period, which leaves the finite numbers at the first step of
    the chain. Nothing about the *book* is outside anything: the refusal can
    only come from the check the scan carries at every step, and what it has
    to name is the compilation and which of its steps produced the value.
    """
    artifact = _artifact("fund")
    fingerprint, body = _compilation(artifact)
    book = _book("fund")
    periods = _periods(artifact)
    broken = book.with_columns(
        pl.lit(1e308).alias("av_init"),
        pl.Series("fund_return", [[1.0] * periods] * book.height),
    )
    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(artifact, broken, FrameSink())
    rendered = refused.value.report.render()
    assert "rollforward.finite" in rendered
    assert fingerprint in rendered
    assert f"step 1 of {len(body['increments'])} (Grow on av@eop)" in rendered
    # Completion and not the door: the run did all of the work and published
    # none of it, which is a different fact from a run that never started.
    assert refused.value.report.closing_sentence() == "No results were published."


def _published_case(bundle: str, case_id: str) -> dict[str, Any]:
    """Return one of the kit's own published cases, as it ships it."""
    from tests.conftest import vectors_directory

    cases = json.loads((vectors_directory() / bundle).read_text(encoding="utf-8"))[
        "cases"
    ]
    found: dict[str, Any] = next(one for one in cases if one["id"] == case_id)
    return copy.deepcopy(found)


def _rekeyed(case: dict[str, Any]) -> dict[str, Any]:
    """Return a case whose edited machine is published under its own identity.

    A compiled machine's identity is the recipe-grammar hash of the body the
    file publishes, less its schedule (spec section 12.1), so a body edited in
    place no longer hashes to its key and the validator refuses the file for
    that before any engine reads it. A test about what the engine does with
    such a machine moves the key -- and every place the case names it -- to
    the edited body's own identity, as a producer compiling that machine
    would have written it.
    """
    from gaspatchio.rollforward._canonical import compiled_identity

    ((old, body),) = case["compilations"].items()
    new = compiled_identity(body)
    text = json.dumps(case).replace(old, new)
    text = text.replace(f"rollforward:{old[7:19]}", f"rollforward:{new[7:19]}")
    moved: dict[str, Any] = json.loads(text)
    return moved


def test_a_state_read_at_the_beginning_of_the_period_refuses_by_name() -> None:
    """16.1 states a portable value for the end of period and for nothing else.

    A beginning-of-period balance is a real quantity and the carry is holding
    one, which is exactly why this has to be a refusal rather than an answer:
    an engine that handed it back would be publishing a number no portable
    contract states, under a door that does state one.

    Built through the vector runner's own adapter over one of the kit's
    published machines, because a point is inside a node's operation tree:
    editing the attribute on an exported artifact moves that node's identity
    and the artifact would then refuse for its digests rather than for the
    thing this test is about.
    """
    from gaspatchio_jax.vectors import normalise

    case = _published_case("rollforward.json", "rollforward-bounded-state")
    case["expr"]["attrs"]["point"] = "bop"
    built = normalise(case, "rollforward.json")
    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(built.document, built.inputs, FrameSink())
    rendered = refused.value.report.render()
    assert "point" in rendered
    assert "eop" in rendered
    assert "16.1" in rendered
    assert refused.value.report.closing_sentence() == "Nothing was computed."


def test_a_tracked_compilation_refuses_in_the_tree_group_by_name() -> None:
    """16.2's machine is not 16.1's, and the reader is told before the book is read.

    Through the adapter again, and for the same reason the beginning-of-period
    read is: a facet is inside the document's own seal (§13.1), so a machine
    edited on an exported artifact leaves a file the validator refuses for its
    digest rather than for its tracking.
    """
    from gaspatchio_jax.vectors import normalise

    case = _published_case("rollforward.json", "rollforward-bounded-state")
    fingerprint = case["expr"]["attrs"]["fingerprint"]
    case["compilations"][fingerprint]["track_increments"] = True
    built = normalise(_rekeyed(case), "rollforward.json")
    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(built.document, built.inputs, FrameSink())
    rendered = refused.value.report.render()
    assert "tracks what each step moved" in rendered
    assert "16.1" in rendered
    assert refused.value.report.closing_sentence() == "Nothing was computed."


def test_the_three_refused_identifiers_carry_a_sentence_and_a_clause() -> None:
    """Refused *by name*, which is a different thing from not yet reached.

    ``rollforward.struct`` has no portable output contract at all (§16.3);
    ``state_graph`` and ``nested_valuation`` are payloads section 17 designs
    and nothing emits, so there is no portable calculation behind either. A
    reader deciding whether to wait for this engine needs to be able to tell
    those from an identifier nobody has got to yet, and the row says which.
    """
    from gaspatchio_jax.plan import _records, _status_of

    assert REFUSED["rollforward.struct"][1] == "16.3"
    assert "Struct" in REFUSED["rollforward.struct"][0]
    for kind in ("state_graph", "nested_valuation"):
        golden = json.loads(
            (GOLDENS / f"{kind}_example.json").read_text(encoding="utf-8")
        )
        records = _records(golden)
        node_id = next(one for one in records if one.startswith(f"{kind}:"))
        status = _status_of(records[node_id], records, golden)
        assert status.status == "refused"
        assert status.clause == "17"
        assert "nothing emits one" in (status.condition or "")


def test_the_operations_this_subset_admits_are_the_six_it_names() -> None:
    """The list is closed, and 16.1 names the four that stay outside it."""
    assert set(_ADMITTED) == {
        "Add",
        "Subtract",
        "Charge",
        "Grow",
        "Floor",
        "Ratchet",
    }
    assert not set(_ADMITTED) & set(OUTSIDE_THE_LIST)


@pytest.mark.parametrize("pattern", ["fund", "ratchet"])
def test_each_shipped_pattern_s_machine_is_inside_the_subset(pattern: str) -> None:
    """The gate says yes to the two machines the tutorial teaches."""
    _fingerprint, body = _compilation(_artifact(pattern))
    assert outside_the_subset(body) is None


def test_a_machine_the_file_does_not_carry_refuses_rather_than_being_guessed() -> None:
    """A fingerprint is an identity and not a recipe (§16).

    Asked of the compilation node's own status, because that is where the
    question is answered: a document whose facet has been emptied is a
    document whose seal no longer holds, and it would refuse for that first.
    """
    from gaspatchio_jax.plan import _records, _status_of

    artifact = copy.deepcopy(_artifact("fund"))
    artifact["facets"][FACET]["compilations"] = {}
    records = _records(artifact)
    node_id = next(one for one in records if one.startswith("rollforward:"))
    status = _status_of(records[node_id], records, artifact)
    assert status.status == "refused"
    assert status.clause == "16.1"
    assert "carries no machine under" in (status.condition or "")
    assert body_of(artifact, "sha256:nothing") is None


def test_a_structural_finding_about_a_machine_here_is_not_a_second_fact() -> None:
    """One facet, two readings, and the engine acts on its own.

    ``outside_the_subset`` is 16.1's own list of conditions and is the
    stricter of the two readings. A producer-side structural finding about
    the same bytes would hand a reader a refusal whose next move -- export the
    artifact again -- produces the identical document, so it is not passed on.
    Everything else the producer says about the facet is.
    """
    from gaspatchio.engines.report import Refusal
    from gaspatchio_jax.plan import _read_here

    artifact = _artifact("fund")
    fingerprint, _body = _compilation(artifact)
    where = f"/facets/{FACET}/compilations/{fingerprint}"

    def one(at: str, clause: str) -> Refusal:
        return Refusal(
            group="tree", where=at, count=None, what="", move="", clause=clause
        )

    assert _read_here(one(where, "portable_structure"), artifact) is True
    assert _read_here(one(where, "declared_payloads"), artifact) is False
    assert _read_here(one("/nodes", "portable_structure"), artifact) is False


def test_internal_bop_balances_run_and_share_one_scan(monkeypatch) -> None:
    """A BOP operand reads the opening, while EOP exposes the finished period."""
    from gaspatchio_jax.lowerings import rollforward
    from gaspatchio_jax.vectors import normalise

    case = _published_case("rollforward.json", "rollforward-bounded-state")
    body = next(iter(case["compilations"].values()))
    body["increments"][0]["operands"] = [{"op": "state", "name": "fund@bop"}]
    built = normalise(_rekeyed(case), "rollforward.json")
    scans = []
    original = rollforward.lax.scan

    # The spy forwards lax.scan's polymorphic pytree signature unchanged.
    def scan(function, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 -- forwards polymorphic lax.scan pytrees
        if function.__module__ == rollforward.__name__:
            scans.append(function)
        return original(function, *args, **kwargs)

    monkeypatch.setattr(rollforward.lax, "scan", scan)
    result = engine_named("jax").run(
        built.document, built.inputs, FrameSink(), every_node=True
    )
    assert set(result.manifest.columns) == _value_bearing(built.document)
    assert result.columns["state:fund@bop"].to_list() == [
        [100.0, 180.0],
        [200.0, 380.0],
    ]
    expected = [[180.0, 288.0], [380.0, 760.0]]
    assert result.columns["state:fund@eop"].to_list() == expected
    assert result.columns["answer@1"].to_list() == expected
    assert len(scans) == 1


@pytest.mark.parametrize(
    ("name", "scalar"),
    [
        ("initial", True),
        ("credit", True),
        ("credit", False),
        ("rate", True),
        ("rate", False),
    ],
)
@pytest.mark.parametrize("carrier", ["bool", "i64"])
def test_non_f64_openings_and_ordinary_operands_refuse_at_inspection(
    name: str, carrier: str, *, scalar: bool
) -> None:
    """The artifact already declares the wrong carrier before values arrive."""
    from gaspatchio_jax.vectors import normalise

    case = _published_case("rollforward.json", "rollforward-bounded-state")
    value = True if carrier == "bool" else 1
    case["inputs"][name] = {
        "dtype": carrier if scalar else f"list[{carrier}]",
        "values": [value, value] if scalar else [[value, value], [value, value]],
    }
    built = normalise(case, "rollforward.json")
    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(built.document, built.inputs, FrameSink())
    findings = refused.value.report.refusals
    assert findings
    assert all(one.group == "tree" for one in findings)
    assert any(one.clause == "16.1" and name in one.what for one in findings)
    assert "f64" in refused.value.report.render()


def test_every_node_includes_a_declared_unconsulted_state() -> None:
    """A sealed state leaf outside the machine's read list still has a value."""
    from gaspatchio.engines.format import inspect_execution
    from gaspatchio_jax.vectors import _sealed, _state_node, normalise

    case = _published_case("rollforward.json", "rollforward-bounded-state")
    body = next(iter(case["compilations"].values()))
    body["states"].append({"name": "idle", "init": {"op": "col", "name": "initial"}})
    built = normalise(_rekeyed(case), "rollforward.json")
    built.document["nodes"].insert(0, _state_node("state:idle@eop"))
    document = _sealed(built.document)
    inspection = inspect_execution(document)
    assert all(
        inspection.checks[name] == "passed"
        for name in ("artifact_validity", "portable_structure", "declared_payloads")
    )
    assert (
        inspect_execution(document, roots=["state:idle@eop"]).checks[
            "portable_structure"
        ]
        == "failed"
    )
    result = engine_named("jax").run(
        document, built.inputs, FrameSink(), every_node=True
    )
    assert set(result.manifest.columns) == _value_bearing(document)
    assert result.columns["state:idle@eop"].to_list() == [
        [100.0, 100.0],
        [200.0, 200.0],
    ]


def test_scalar_operands_still_run_the_nonzero_schedule() -> None:
    """There is no list operand from which a fallback could recover T."""
    from gaspatchio_jax.vectors import normalise

    case = _published_case("rollforward.json", "rollforward-bounded-state")
    case["inputs"]["credit"] = {"dtype": "f64", "values": [10.0, 5.0]}
    case["inputs"]["rate"] = {"dtype": "f64", "values": [0.0, 0.0]}
    built = normalise(case, "rollforward.json")
    result = engine_named("jax").run(built.document, built.inputs, FrameSink())
    assert _periods(built.document) == 2
    assert result.columns["answer"].to_list() == [[110.0, 120.0], [205.0, 210.0]]


@pytest.mark.parametrize("gate", [True, False, [False, True] * 30])
def test_ratchet_accepts_scalar_and_list_boolean_gates(
    *, gate: bool | list[bool]
) -> None:
    from gaspatchio_jax.vectors import normalise

    case = _published_case("rollforward.json", "rollforward-ratchet-at-the-anniversary")
    case["inputs"]["fund_init"]["values"] = [200000.0]
    case["inputs"]["rate"] = {"dtype": "f64", "values": [0.0]}
    case["inputs"]["anniv"] = {
        "dtype": "bool" if isinstance(gate, bool) else "list[bool]",
        "values": [gate],
    }
    built = normalise(case, "rollforward.json")
    result = engine_named("jax").run(built.document, built.inputs, FrameSink())
    expected = (
        [200000.0] * 60
        if gate is True
        else [100000.0] * 60
        if gate is False
        else [100000.0, *([200000.0] * 59)]
    )
    assert result.columns["answer"].to_list() == [expected]


@pytest.mark.parametrize("carrier", ["f64", "i64"])
def test_ratchet_refuses_numeric_gates_at_inspection(carrier: str) -> None:
    from gaspatchio_jax.vectors import normalise

    case = _published_case("rollforward.json", "rollforward-ratchet-at-the-anniversary")
    case["inputs"]["anniv"] = {
        "dtype": carrier,
        "values": [1.0 if carrier == "f64" else 1],
    }
    built = normalise(case, "rollforward.json")
    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(built.document, built.inputs, FrameSink())
    assert any(
        one.group == "tree"
        and one.clause == "16.1"
        and "anniv" in one.what
        and "bool" in one.what
        for one in refused.value.report.refusals
    )


def test_a_shared_state_name_does_not_choose_the_first_machine() -> None:
    """Ownership requires a unique declaring identity, including unused states."""
    from gaspatchio_jax.plan import ExecutionPlan, _records, _status_of

    document = _artifact("fund")
    fingerprint, body = _compilation(document)
    second = "sha256:" + "f" * 64
    document["facets"][FACET]["compilations"][second] = copy.deepcopy(body)
    machine = copy.deepcopy(
        next(node for node in document["nodes"] if node["kind"] == "rollforward")
    )
    machine["id"] = "rollforward:ffffffffffff"
    machine["expr"]["attrs"]["fingerprint"] = second
    document["nodes"].append(machine)
    records = _records(document)
    state = next(record for record in records.values() if record.kind == "state")
    status = _status_of(state, records, document)
    assert status.status == "refused"
    assert status.clause == "16.1"
    assert "unique" in status.condition
    assert fingerprint != second
    plan = ExecutionPlan.stage_inspect(_artifact("fund"))
    plan.document = document
    plan.records = records
    assert plan.tree_of(state) is None


def test_publication_cannot_silently_omit_a_requested_value() -> None:
    from gaspatchio_jax.plan import ExecutionPlan

    plan = ExecutionPlan.stage_inspect(_artifact("fund"), every_node=True)
    plan.order = tuple(node for node in plan.order if not node.startswith("state:"))
    with pytest.raises(AssertionError, match="state:av@eop"):
        plan.published_nodes({})


def test_a_schedule_outside_the_subset_is_refused_at_inspection_as_by_the_run() -> None:
    """``validate --engine jax`` names what ``run-artifact`` will refuse (W5 A-F12).

    A machine on a per-policy grid is outside 16.1's two schedule forms, and
    the run refuses the running state and the line that reads it. Inspection
    lowered both, so a CI job gating on ``gspio validate --engine jax`` passed
    a model ``run-artifact`` then refused. The inspection now holds the body
    and its schedule to the same check, read off the file alone: the same two
    nodes, the same sentence, the same clause.
    """
    from gaspatchio.frame.graph.validate import _payload_digest
    from gaspatchio_jax.engine import JaxEngine
    from gaspatchio_jax.vectors import _sealed, normalise

    built = normalise(
        _published_case("rollforward.json", "rollforward-bounded-state"),
        "rollforward.json",
    )
    stated = next(
        one for one in built.document["assumptions"] if one["kind"] == "schedule"
    )
    payload = {
        "kind": "per_policy_grid",
        "n_periods": 2,
        "frequency": "1M",
        "anchor": None,
    }
    fingerprint, why = _payload_digest("schedule", payload)
    assert why is None, why
    document = json.loads(
        json.dumps(built.document).replace(stated["fingerprint"], fingerprint)
    )
    next(one for one in document["assumptions"] if one["kind"] == "schedule")[
        "payload"
    ] = payload
    document = _sealed(document)

    inspected = {
        one.node_id: (one.condition, one.clause)
        for one in JaxEngine().validate_tree(document)
        if one.status == "refused"
    }
    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(document, built.inputs, FrameSink())
    run = {one.where: (one.what, one.clause) for one in refused.value.report.refusals}

    assert set(run) == {"state:fund@eop", "answer@1"}
    assert inspected == run
    assert all("kind='per_policy_grid'" in what for what, _ in run.values())
