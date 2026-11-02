# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A compiled rollforward in the artifact: one node, and its states visible.

The framework escalates from a closed form to a state machine exactly when a
within-period charge depends on the running balance -- a cost of insurance on
the net amount at risk, a benefit base that ratchets to a fund's high-water
mark. The artifact has to show that escalation as structure, because it is the
whole justification for it.

The models below are the shipped rollforward patterns in miniature: the
single-state separate-account fund, the multi-state GMDB ratchet with its
cross-state read, and the GMWB-style lapse stop. They are written here rather
than imported so that a test can read one state or two out of them, which the
patterns' own scripts do at the end of a projection they print.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

import gaspatchio
from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.graph_builder import CalcGraph
from gaspatchio.frame.graph.graph_models import (
    ROLLFORWARD_NAMESPACE,
    ROLLFORWARD_OPERATIONS,
    STATE_NAMESPACE,
)
from gaspatchio.frame.graph.validate import validate_artifact
from gaspatchio.frame.lowering import artefacts
from gaspatchio.rollforward import compile_rollforward

if TYPE_CHECKING:
    from collections.abc import Iterator

# How many periods each pattern projects. Small enough to stay fast, long
# enough for the ratchet to fire twice and for the withdrawal to exhaust the
# fund, which is what makes each fixture the pattern it is named after.
_PERIODS = 24


def _artifact(frame: ActuarialFrame) -> dict[str, Any]:
    """Return ``frame``'s exported artifact, parsed back from the wire."""
    exported: dict[str, Any] = json.loads(GraphExporter(frame).export())
    return exported


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def _of_kind(artifact: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Return every node of ``artifact`` giving an account of ``kind``."""
    return [node for node in artifact["nodes"] if node["kind"] == kind]


def _narrowed(artifact: dict[str, Any], target: str) -> dict[str, tuple[str, str]]:
    """Return how ``target`` read each of the things it reads, by source id.

    The relationship is on the edge and the narrowing beside it on the
    reading node, so a test asking "how did this read the rate?" reads the
    facet. Keyed by source, because that is the question -- which of the
    things this node reads was folded, and which was only consulted.
    """
    carried = _node(artifact, target)["facets"]["gaspatchio_column_transformation"]
    return {
        read["source"]: (
            read["transformations"][0]["type"],
            read["transformations"][0]["subtype"],
        )
        for read in carried["reads"]
    }


def _timeline(frame: ActuarialFrame) -> ActuarialFrame:
    """Return ``frame`` with the projection timeline the patterns run over."""
    return frame.projection.set(
        start_date=datetime.date(2025, 1, 31),
        n_periods=_PERIODS,
        frequency="monthly",
    )


def _the_single_state_fund_pattern() -> ActuarialFrame:
    """Return a separate-account fund: grow with the return, take the M&E charge.

    ``AV_eop = max(AV_bop * (1 + fund_return) * (1 - me_charge), 0)`` -- the
    simplest variable-annuity building block, three operations over one state.
    """
    frame = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "fund_return": [[0.01] * _PERIODS],
            "me_charge": [[0.001] * _PERIODS],
        }
    )
    frame = _timeline(frame)
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    (
        builder["fund_value"]
        .grow(frame["fund_return"], label="fund_return")
        .charge(frame["me_charge"], label="me_charge")
        .floor(value=0.0)
    )
    frame.account_value = compile_rollforward(builder).expr_for("fund_value")
    return frame


def _the_multistate_ratchet_pattern() -> ActuarialFrame:
    """Return a GMDB whose benefit base ratchets to the fund's high-water mark.

    The ratchet reads the fund's own end-of-period balance inside the same
    period (``pl.col("account_value@eop")``), which is the cross-state read the
    kernel resolves against the live state vector: no column on the frame ever
    holds it.
    """
    anniversary = [(period + 1) % 12 == 0 for period in range(_PERIODS)]
    frame = ActuarialFrame(
        {
            "fund_init": [100_000.0],
            "gmdb_init": [100_000.0],
            "fund_return": [[0.008] * _PERIODS],
            "anniversary": [anniversary],
        }
    )
    frame = _timeline(frame)
    builder = frame.projection.rollforward(
        states={
            "account_value": frame["fund_init"],
            "benefit_base": frame["gmdb_init"],
        }
    )
    builder["account_value"].grow(frame["fund_return"], label="fund_growth")
    builder["benefit_base"].ratchet(
        to=pl.col("account_value@eop"),
        when=frame["anniversary"],
        label="gmdb_ratchet",
    )
    compiled = compile_rollforward(builder)
    frame.fund = compiled.expr_for("account_value")
    frame.gmdb = compiled.expr_for("benefit_base")
    return frame


def _the_lapse_stop_pattern() -> ActuarialFrame:
    """Return a GMWB-style projection that terminates when the fund is exhausted.

    Two states read out of one compilation, which is what the artifact has to
    show as one kernel run rather than two.
    """
    frame = ActuarialFrame(
        {
            "av_init": [50_000.0],
            "guarantee_init": [50_000.0],
            "withdrawal": [[6_000.0] * _PERIODS],
        }
    )
    frame = _timeline(frame)
    builder = frame.projection.rollforward(
        states={
            "account_value": frame["av_init"],
            "guaranteed_base": frame["guarantee_init"],
        },
        lapse_when_all_non_positive=("account_value",),
    )
    builder["account_value"].subtract(frame["withdrawal"], label="withdrawal")
    builder["guaranteed_base"].subtract(frame["withdrawal"], label="drawdown")
    compiled = compile_rollforward(builder)
    frame.fund = compiled.expr_for("account_value")
    frame.remaining_guarantee = compiled.expr_for("guaranteed_base")
    return frame


def _the_wrapped_extraction_pattern() -> ActuarialFrame:
    """Return a fund whose extraction disappears into an expression of its own.

    ``pl.concat_list`` prepends the opening balance to the projected fund, so
    the record keeps no call carrying the compilation's identity -- only a
    reference to the hidden struct column the frame materialises for the
    kernel. That name is the second of the two doors a model reaches a
    compilation through, and it is the door section 16 carves out for a
    producer that cannot reach the compiled artefact.
    """
    frame = ActuarialFrame(
        {"av_init": [100_000.0], "opening": [[1.0]], "rate": [[0.01] * _PERIODS]}
    )
    frame = _timeline(frame)
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    builder["fund_value"].grow(frame["rate"], label="growth")
    compiled = compile_rollforward(builder)
    frame.with_opening = pl.concat_list(
        [pl.col("opening"), compiled.expr_for("fund_value")]
    )
    return frame


@pytest.fixture(scope="module")
def single_state_fund() -> dict[str, Any]:
    """Return the artifact for the single-state separate-account fund."""
    return _artifact(_the_single_state_fund_pattern())


@pytest.fixture(scope="module")
def multistate_ratchet() -> dict[str, Any]:
    """Return the artifact for the multi-state GMDB ratchet."""
    return _artifact(_the_multistate_ratchet_pattern())


@pytest.fixture(scope="module")
def lapse_stop() -> dict[str, Any]:
    """Return the artifact for the GMWB-style lapse stop."""
    return _artifact(_the_lapse_stop_pattern())


# --- the compilation is one node --------------------------------------------


def test_a_compilation_is_one_node_the_extractions_read(
    single_state_fund: dict[str, Any],
) -> None:
    """One compilation, one node, and the line reading a state reads that node."""
    (compilation,) = _of_kind(single_state_fund, "rollforward")

    assert compilation["states"] == ["fund_value"]
    assert _node(single_state_fund, "account_value@1")["reads"] == [compilation["id"]]


def test_two_extractions_from_one_compilation_read_one_parent(
    lapse_stop: dict[str, Any],
) -> None:
    """One kernel run is one node, however many states are pulled out of it."""
    compilations = {node["id"] for node in _of_kind(lapse_stop, "rollforward")}
    readers = [
        node for node in lapse_stop["nodes"] if set(node["reads"]) & compilations
    ]

    assert len(compilations) == 1
    assert len(readers) == 2
    assert {tuple(node["reads"]) for node in readers} == {tuple(compilations)}


def test_the_parent_is_the_compiled_artefacts_own_identity(
    single_state_fund: dict[str, Any],
) -> None:
    """The node is named by the compilation, not by the line that reached it."""
    (compilation,) = _of_kind(single_state_fund, "rollforward")

    assert compilation["id"].startswith("rollforward:")
    assert compilation["local_fingerprint"].startswith("sha256:")
    assert compilation["fingerprint"].startswith("sha256:")


def test_the_compilation_is_not_an_account_of_a_column(
    single_state_fund: dict[str, Any],
) -> None:
    """It is one state machine, and no statement in the model defines it."""
    (compilation,) = _of_kind(single_state_fund, "rollforward")

    assert compilation["column"] is None
    assert compilation["version"] is None
    assert compilation["formula"] is None
    assert compilation["source_location"] is None
    assert compilation["provenance"] == "rollforward"


def test_the_compilation_has_something_to_execute_and_says_so(
    single_state_fund: dict[str, Any],
) -> None:
    """A tier is stated on it, because unlike a leaf it computes something.

    The claim is about the vocabulary rather than the payload: the compiled
    state machine is not in the audit profile, and the tier never said it was.
    """
    (compilation,) = _of_kind(single_state_fund, "rollforward")

    assert compilation["tier"] == "core"
    # And it makes no claim about engines: its tree is the compilation's
    # identity rather than its recipe, so an empty array -- which would say
    # the state machine reaches into none -- is not a claim it can support.
    assert "engines" not in compilation
    assert "engines" not in _node(single_state_fund, "state:fund_value@eop")


# --- the running balance the escalation exists for --------------------------


def test_the_running_balance_is_something_the_artifact_can_point_at(
    multistate_ratchet: dict[str, Any],
) -> None:
    """Before this, a ratchet on a fund's high-water mark said it read a mask.

    True of the arguments and false of the calculation: the fund's own
    end-of-period balance is what the benefit base is ratcheted to, and the
    kernel computes it from the balance it is carrying rather than from any
    column. Without a node for it the artifact had nowhere to point.
    """
    (compilation,) = _of_kind(multistate_ratchet, "rollforward")

    states = [read for read in compilation["reads"] if read.startswith("state:")]

    assert "state:account_value@eop" in states


def test_a_state_is_not_a_column(multistate_ratchet: dict[str, Any]) -> None:
    """Nothing on the frame holds it, nothing supplies it, and it reads nothing."""
    state = _node(multistate_ratchet, "state:account_value@eop")

    assert state["kind"] == "state"
    assert state["column"] is None
    assert state["version"] is None
    assert state["provenance"] is None
    assert state["reads"] == []
    assert state["tier"] is None


def test_the_states_a_compilation_declares_are_not_the_states_it_reads(
    multistate_ratchet: dict[str, Any], lapse_stop: dict[str, Any]
) -> None:
    """Declaring a state and consulting its balance are two different claims.

    A ratchet reads the balance it is about to change and the fund's, so both
    of that compilation's states are read. A withdrawal takes a flat amount:
    six thousand is six thousand whatever the account value, so nothing there
    reads a running balance and no state node is minted at all -- while both
    states are still declared, and both are still what the machine carries.
    """
    (ratchet,) = _of_kind(multistate_ratchet, "rollforward")
    (withdrawal,) = _of_kind(lapse_stop, "rollforward")

    assert ratchet["states"] == ["account_value", "benefit_base"]
    assert {node["id"] for node in _of_kind(multistate_ratchet, "state")} == {
        "state:account_value@eop",
        "state:benefit_base@eop",
    }

    assert withdrawal["states"] == ["account_value", "guaranteed_base"]
    assert _of_kind(lapse_stop, "state") == []
    assert not [read for read in withdrawal["reads"] if read.startswith("state:")]


def test_a_state_read_is_an_edge_from_the_compilation_that_owns_it(
    multistate_ratchet: dict[str, Any],
) -> None:
    """The rule fires here and nowhere else: nothing but a compilation reads one."""
    (compilation,) = _of_kind(multistate_ratchet, "rollforward")

    state_edges = [
        edge
        for edge in multistate_ratchet["edges"]
        if edge["source"].startswith("state:")
    ]
    narrowed = _narrowed(multistate_ratchet, compilation["id"])

    assert state_edges
    assert {edge["target"] for edge in state_edges} == {compilation["id"]}
    assert {edge["relationship"] for edge in state_edges} == {"DIRECT"}
    assert {narrowed[edge["source"]] for edge in state_edges} == {
        ("DIRECT", "TRANSFORMATION")
    }


# --- what the compilation reads, stated once --------------------------------


def test_the_columns_a_compilation_consumes_hang_off_the_compilation(
    multistate_ratchet: dict[str, Any],
) -> None:
    """Stated once on the machine rather than restated on every line reading it.

    The fund return is one column the compilation takes. Before the node
    existed both extractions claimed it, so a model reading two states
    reported one growth assumption twice.
    """
    (compilation,) = _of_kind(multistate_ratchet, "rollforward")

    assert compilation["reads"].count("fund_return") == 1
    assert _node(multistate_ratchet, "fund@1")["reads"] == [compilation["id"]]
    assert _node(multistate_ratchet, "gmdb@1")["reads"] == [compilation["id"]]


def test_an_extraction_wrapped_in_arithmetic_still_reads_the_compilation() -> None:
    """A model that scales a state reads the compilation and the scale, not the rates.

    The extraction does not have to be the whole right-hand side. Descending
    past it would put the compilation's own growth rate in the lineage of a
    column that never touched it -- and put it there under the name of an
    ordinary operand, where a reader would have no way to tell.
    """
    frame = ActuarialFrame(
        {"av_init": [100_000.0], "rate": [[0.01] * _PERIODS], "unit_count": [12.0]}
    )
    frame = _timeline(frame)
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    builder["fund_value"].grow(frame["rate"], label="growth")
    frame.scaled_fund = (
        compile_rollforward(builder).expr_for("fund_value") * frame.unit_count
    )

    artifact = _artifact(frame)
    (compilation,) = _of_kind(artifact, "rollforward")

    assert _node(artifact, "scaled_fund@1")["reads"] == [
        compilation["id"],
        "unit_count",
    ]
    assert "rate" in compilation["reads"]


def test_an_operand_of_the_recurrence_is_read_by_every_later_period(
    single_state_fund: dict[str, Any],
) -> None:
    """A rollforward is a linear recurrence, so its operands are an accumulation.

    A charge rate multiplied into one period's balance is inside every balance
    after it, which is what AGGREGATION says and TRANSFORMATION would not.
    """
    (compilation,) = _of_kind(single_state_fund, "rollforward")

    into_it = _narrowed(single_state_fund, compilation["id"])

    assert into_it["me_charge"] == ("DIRECT", "AGGREGATION")
    assert into_it["fund_return"] == ("DIRECT", "AGGREGATION")


def test_every_read_the_compilation_states_carries_an_edge(
    multistate_ratchet: dict[str, Any],
) -> None:
    """One edge per entry of the target's reads, on this node like any other."""
    (compilation,) = _of_kind(multistate_ratchet, "rollforward")

    into_it = [
        edge["source"]
        for edge in multistate_ratchet["edges"]
        if edge["target"] == compilation["id"]
    ]

    assert into_it == compilation["reads"]


@pytest.mark.parametrize(
    "pattern",
    ["single_state_fund", "multistate_ratchet", "lapse_stop"],
    ids=["single_state_fund", "multistate_ratchet", "lapse_stop"],
)
def test_no_node_reads_nothing_while_its_formula_names_a_reference(
    pattern: str, request: pytest.FixtureRequest
) -> None:
    """The kernel's own column used to be dropped, leaving a blank account.

    A node whose formula names something and whose ``reads`` is empty is a
    lineage claim the artifact cannot support, in the one document whose whole
    purpose is that it can be checked. Every node in a rollforward model that
    has a formula at all now says what it read.
    """
    artifact: dict[str, Any] = request.getfixturevalue(pattern)

    silent = [
        node["id"]
        for node in artifact["nodes"]
        if node["formula"] is not None and not node["reads"]
    ]

    assert silent == []


# --- the reserved namespaces ------------------------------------------------


@pytest.fixture(
    params=[
        f"{STATE_NAMESPACE}fund_value@eop",
        f"{ROLLFORWARD_NAMESPACE}7be2aa108f31",
    ],
    ids=["state", "rollforward"],
)
def reserved(request: pytest.FixtureRequest) -> str:
    """Return a column name in each reserved namespace, spelled as the format does.

    One of each, because the rule is the namespace's and not one namespace's:
    a producer that guarded ``state:`` and let ``rollforward:`` through would
    be enforcing half a sentence of section 8.1.
    """
    return str(request.param)


def test_a_column_may_not_be_produced_into_a_reserved_namespace(
    reserved: str,
) -> None:
    """A column named into one is refused whatever the model did with it.

    The refusal is about the name and not about a collision. Nothing in this
    model compiles a rollforward at all, so no id is contended for -- and the
    column is still refused, because a reader taking ``state:premium@bop``
    for a running balance would be reading the artifact correctly.
    """
    frame = ActuarialFrame({"premium": [100.0], reserved: [1.0]})
    frame.doubled = frame.premium * 2

    with pytest.raises(ValueError, match=re.escape(f"The column {reserved!r}")):
        _artifact(frame)


def test_a_column_assigned_into_a_reserved_namespace_is_refused(
    reserved: str,
) -> None:
    """An ordinal on the end does not take a name out of the namespace it begins in."""
    frame = ActuarialFrame({"premium": [100.0]})
    frame[reserved] = frame.premium * 2

    with pytest.raises(ValueError, match=re.escape(f"The column {reserved!r}")):
        _artifact(frame)


def test_a_hole_punched_under_a_reserved_namespace_is_refused(
    reserved: str,
) -> None:
    """The third door: a column written straight into the plan, past every record.

    A hole is the account the graph gives of a column nothing explains, and
    it is still a node whose id would sit in a reserved namespace. Refusing
    it costs the model nothing it can have wanted: a column of the author's
    own named this way was never readable as theirs.
    """
    frame = ActuarialFrame({"premium": [100.0]})
    frame.doubled = frame.premium * 2
    frame._df = frame._df.with_columns(  # noqa: SLF001 — the bypass that mints a hole
        (pl.col("premium") * 3).alias(reserved)
    )

    with pytest.raises(ValueError, match=re.escape(f"The column {reserved!r}")):
        _artifact(frame)


def test_a_column_contending_with_a_live_state_is_refused_by_name() -> None:
    """The shape that used to be the only one refused, still refused.

    Here a compilation really does want the id, so before the rule was
    enforced categorically this was the one case that raised. It is now the
    same refusal as the three above, and it fires when the column is minted
    rather than when the state arrives to find it there.
    """
    frame = ActuarialFrame({"av_init": [100_000.0], "state:fund_value@eop": [1.0]})
    frame = _timeline(frame)
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    builder["fund_value"].grow(frame["state:fund_value@eop"])
    frame.account_value = compile_rollforward(builder).expr_for("fund_value")

    with pytest.raises(
        ValueError, match=re.escape("The column 'state:fund_value@eop'")
    ):
        _artifact(frame)


def test_two_compilations_declaring_one_state_name_are_refused() -> None:
    """The namespace names the state, so sharing the node would share a balance.

    Named the way its author named it: they wrote ``states={"fund": ...}``,
    so a refusal asking them to rename ``fund@eop`` would send them looking
    for a string their model does not contain.
    """
    frame = ActuarialFrame(
        {"first_init": [100.0], "second_init": [200.0], "rate": [[0.01] * _PERIODS]}
    )
    frame = _timeline(frame)
    for column, opening in (("first", "first_init"), ("second", "second_init")):
        builder = frame.projection.rollforward(states={"fund": frame[opening]})
        builder["fund"].grow(frame["rate"])
        frame[column] = compile_rollforward(builder).expr_for("fund")

    with pytest.raises(
        ValueError,
        match=re.escape("both carry a running state 'fund' (read as 'fund@eop')"),
    ):
        _artifact(frame)


def test_one_reserved_id_may_not_stand_for_two_compilations() -> None:
    """Two state machines reported as one is the loss the id guard exists for.

    A compilation's node id carries twelve hex characters of its published
    fingerprint, and two compilations agreeing across those twelve are two
    kernel runs the graph cannot tell apart. Merging them would hand the
    second one's reads to the first, so it is refused by id instead.
    """
    graph = CalcGraph()
    shared = "a" * 12
    schedule = f"sha256:{'5' * 64}"
    graph._compilation((f"sha256:{shared}{'1' * 52}", schedule), (), {})  # noqa: SLF001 — the guard under test

    with pytest.raises(ValueError, match=re.escape(f"node id 'rollforward:{shared}'")):
        graph._compilation((f"sha256:{shared}{'2' * 52}", schedule), (), {})  # noqa: SLF001


def test_two_compilations_in_one_model_are_two_nodes() -> None:
    """One node per compilation, and each extraction reads its own."""
    frame = ActuarialFrame(
        {"first_init": [100.0], "second_init": [200.0], "rate": [[0.01] * _PERIODS]}
    )
    frame = _timeline(frame)
    for column, opening in (("first", "first_init"), ("second", "second_init")):
        builder = frame.projection.rollforward(states={column: frame[opening]})
        builder[column].grow(frame["rate"])
        frame[column] = compile_rollforward(builder).expr_for(column)

    artifact = _artifact(frame)
    compilations = _of_kind(artifact, "rollforward")

    assert len({node["id"] for node in compilations}) == 2
    assert _node(artifact, "first@1")["reads"] != _node(artifact, "second@1")["reads"]


# --- the artifact still validates -------------------------------------------


def _every_artifact() -> Iterator[dict[str, Any]]:
    """Yield each pattern's artifact, for the checks that hold across all of them."""
    yield _artifact(_the_single_state_fund_pattern())
    yield _artifact(_the_multistate_ratchet_pattern())
    yield _artifact(_the_lapse_stop_pattern())


def test_a_rollforward_model_conforms_to_the_published_schema() -> None:
    """The kinds, the namespaces and the states field are what the schema says."""
    import jsonschema

    from gaspatchio.schemas import load_schema

    validator = jsonschema.Draft202012Validator(load_schema())

    for artifact in _every_artifact():
        assert list(validator.iter_errors(artifact)) == []


def test_a_compilation_out_of_reach_keeps_its_identity_and_claims_no_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which states a machine declares is a fact about the compiled artefact.

    A graph folded where the compiler never ran -- a log that travelled, a
    worker that rebuilt nothing -- can still say which compilation was read
    and what the record said it reads, because the record carries both. What
    it cannot say is the declared state list, and an empty array there would
    claim a state machine with no states in it.
    """
    frame = _the_single_state_fund_pattern()
    monkeypatch.setattr(artefacts, "_ROLLFORWARDS", {})

    artifact = _artifact(frame)
    (compilation,) = _of_kind(artifact, "rollforward")

    assert "states" not in compilation
    assert compilation["id"].startswith("rollforward:")
    assert "state:fund_value@eop" in compilation["reads"]
    assert _node(artifact, "account_value@1")["reads"] == [compilation["id"]]


def test_a_wrapped_extraction_out_of_reach_loses_the_compilation_it_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second door does not survive a process the compilation is not in.

    A line whose whole right-hand side is the extraction carries the
    compilation's identity in the expression itself and survives the test
    above. A line that *wrapped* it keeps only the name of the scratch column
    the kernel works in, and that name carries sixteen hex characters of a
    sixty-four character identity: enough to recognise the door, not enough
    to stand for what came through it.

    So the reference is dropped rather than resolved -- no compilation node,
    no running state, and the wrapping line reads whatever else it names and
    not the compilation. Section 16 carves this out beside the ``states``
    omission and for the same reason. What the alternative costs is the point:
    binding the scratch name would mint a hole, which puts a column no
    statement of the author's ever wrote in front of a reviewer as one the
    model cannot account for.
    """
    frame = _the_wrapped_extraction_pattern()
    monkeypatch.setattr(artefacts, "_ROLLFORWARDS", {})

    artifact = _artifact(frame)
    wrapping = _node(artifact, "with_opening@1")

    assert _of_kind(artifact, "rollforward") == []
    assert _of_kind(artifact, "state") == []
    assert wrapping["reads"] == ["opening"]
    assert _of_kind(artifact, "hole") == []
    # The line still states what its author wrote, extraction and all: what
    # is absent is the binding, not the account of the calculation.
    assert "expr_for" in (wrapping["formula"] or "")


def test_a_wrapped_extraction_in_reach_reads_the_compilation_and_the_rest() -> None:
    """The same model in a process holding the compilation, for the contrast.

    The carve-out above is a degraded producer's answer and not the format's
    ordinary one: where the compiled artefact is reachable the scratch name
    resolves, and section 16's unconditional sentence holds -- the wrapping
    line reads the compilation and whatever else it names.
    """
    artifact = _artifact(_the_wrapped_extraction_pattern())
    (compilation,) = _of_kind(artifact, "rollforward")

    assert _node(artifact, "with_opening@1")["reads"] == [
        "opening",
        compilation["id"],
    ]


def test_the_states_field_is_carried_by_compilations_and_nothing_else(
    multistate_ratchet: dict[str, Any],
) -> None:
    """An absent field is no claim; only the node with an answer writes one."""
    wearing_it = {
        node["kind"] for node in multistate_ratchet["nodes"] if "states" in node
    }

    assert wearing_it == {"rollforward"}


def _increment_pattern(
    build: Any, states: dict[str, Any] | None = None
) -> ActuarialFrame:
    """Return a one-state fund whose movements ``build`` writes.

    The three expression-bearing operations are read rather than answered
    from the operation, so a test of that reading needs to write one movement
    at a time. This is the fixture that lets it.
    """
    frame = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "base_init": [100_000.0],
            "amount": [[100.0] * _PERIODS],
        }
    )
    frame = _timeline(frame)
    declared = states or {"av": frame["av_init"]}
    builder = frame.projection.rollforward(states=declared)
    build(frame, builder)
    frame.result = compile_rollforward(builder).expr_for(next(iter(declared)))
    return frame


def _increments(frame: ActuarialFrame) -> list[dict[str, Any]] | None:
    """Return the movements the one compilation in ``frame`` reports."""
    artifact = _artifact(frame)
    (compilation,) = _of_kind(artifact, "rollforward")
    carried: list[dict[str, Any]] | None = compilation.get("increments")
    return carried


def test_a_compilation_reports_its_movements_in_the_order_they_apply(
    single_state_fund: dict[str, Any],
) -> None:
    """Grow, then charge, then floor -- the roll-forward, as the artifact holds it.

    The order is the calculation: the charge is struck on the balance the
    growth left. A reader given the movements unordered would be given a set
    of things that happened and not a roll-forward.
    """
    (compilation,) = _of_kind(single_state_fund, "rollforward")

    assert compilation["increments"] == [
        {
            "ordinal": 1,
            "label": "fund_return",
            "operation": "Grow",
            "target": "fund_value@eop",
            "reads_running_balance": True,
        },
        {
            "ordinal": 2,
            "label": "me_charge",
            "operation": "Charge",
            "target": "fund_value@eop",
            "reads_running_balance": True,
        },
        {
            "ordinal": 3,
            "label": None,
            "operation": "Floor",
            "target": "fund_value@eop",
            "reads_running_balance": True,
        },
    ]


def test_an_operation_with_no_field_for_a_name_carries_a_null_label(
    single_state_fund: dict[str, Any],
) -> None:
    """``Floor`` has no ``label`` field at all, and null is the claim for that.

    Not an omitted member and not an invented caption: the producer looked,
    and the movement has no name. Null carries that meaning everywhere else
    in the record and carries it here.
    """
    (compilation,) = _of_kind(single_state_fund, "rollforward")
    (floor,) = [
        increment
        for increment in compilation["increments"]
        if increment["operation"] == "Floor"
    ]

    assert floor["label"] is None


def test_the_movements_of_two_states_each_name_the_balance_they_land_on(
    multistate_ratchet: dict[str, Any],
) -> None:
    """``target`` is the state reference and not the reserved id built round it.

    The ratchet pattern moves two balances, and a reader asking which of them
    a movement lands on reads this rather than working it out from the order.
    """
    (compilation,) = _of_kind(multistate_ratchet, "rollforward")

    assert [
        (increment["operation"], increment["target"])
        for increment in compilation["increments"]
    ] == [("Grow", "account_value@eop"), ("Ratchet", "benefit_base@eop")]


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        pytest.param(lambda frame: frame["amount"], False, id="an input column"),
        pytest.param(lambda _: pl.col("av@eop"), True, id="its own closing balance"),
        pytest.param(lambda _: pl.col("av@bop"), True, id="its own opening balance"),
    ],
)
def test_an_added_amount_is_read_for_the_balance_it_lands_on(
    amount: Any, expected: bool
) -> None:
    """``Add`` is one of the three whose expression *is* the amount.

    So the answer is a reading of what that expression names, and never a
    constant per operation. The opening-balance case is the one that
    separates the two possible readings: ``av@bop`` is not the reference
    ``av@eop`` the movement targets, but it is the same *balance*, and an
    amount read off it depends on the balance being changed. Comparing
    references rather than states would answer false there -- on exactly the
    movement the member exists to show.
    """
    frame = _increment_pattern(lambda f, b: b["av"].add(amount(f), label="movement"))

    assert _increments(frame) == [
        {
            "ordinal": 1,
            "label": "movement",
            "operation": "Add",
            "target": "av@eop",
            "reads_running_balance": expected,
        }
    ]


def test_an_amount_read_off_a_different_balance_does_not_read_this_one() -> None:
    """A cross-state read is a read of some balance and not of *this* one.

    The member answers whether this movement's amount depends on the balance
    it is changing. A movement on the benefit base whose amount is the fund's
    closing balance depends on the fund, and the escalation it justifies is
    the fund's rather than the base's.
    """
    frame = ActuarialFrame({"av_init": [100_000.0], "base_init": [100_000.0]})
    frame = _timeline(frame)
    builder = frame.projection.rollforward(
        states={"av": frame["av_init"], "base": frame["base_init"]}
    )
    builder["base"].add(pl.col("av@eop"), label="tracks_the_fund")
    frame.result = compile_rollforward(builder).expr_for("base")

    assert _increments(frame) == [
        {
            "ordinal": 1,
            "label": "tracks_the_fund",
            "operation": "Add",
            "target": "base@eop",
            "reads_running_balance": False,
        }
    ]


def test_two_movements_under_one_label_leave_the_summary_unwritten() -> None:
    """The compilation still compiles; what it does not get is a summary.

    Uniqueness is required of the document and not imposed on the compiler.
    A model whose labels collide runs exactly as it did, and the producer
    declines to write an array a reader could not cite one movement of --
    rather than writing one its own validator would refuse.
    """
    colliding = _artifact(
        _increment_pattern(
            lambda f, b: (
                b["av"].add(f["amount"], label="same").add(f["amount"], label="same")
            )
        )
    )
    (compilation,) = _of_kind(colliding, "rollforward")

    assert "increments" not in compilation
    assert compilation["states"] == ["av"]
    assert validate_artifact(colliding).ok

    # The same two movements under two names, so that the absence above is
    # the collision and not the shape of the model.
    named = _artifact(
        _increment_pattern(
            lambda f, b: (
                b["av"].add(f["amount"], label="first").add(f["amount"], label="second")
            )
        )
    )
    (summarised,) = _of_kind(named, "rollforward")

    assert [increment["label"] for increment in summarised["increments"]] == [
        "first",
        "second",
    ]


def test_an_empty_label_leaves_the_summary_unwritten() -> None:
    """``""`` is not a name, and a producer writes no record its validator refuses.

    The record requires a label to be non-empty where it is present, so a
    compilation carrying one is in the same position as one whose labels
    collide: the summary goes unwritten and everything else about the node
    stands.
    """
    unnamed = _artifact(
        _increment_pattern(lambda f, b: b["av"].add(f["amount"], label=""))
    )
    (compilation,) = _of_kind(unnamed, "rollforward")

    assert "increments" not in compilation
    assert validate_artifact(unnamed).ok

    # The same movement under a name, so that the absence above is the empty
    # label and not the operation.
    named = _artifact(
        _increment_pattern(lambda f, b: b["av"].add(f["amount"], label="premium"))
    )
    (summarised,) = _of_kind(named, "rollforward")

    assert summarised["increments"][0]["label"] == "premium"


def test_the_increments_field_is_carried_by_compilations_and_nothing_else(
    multistate_ratchet: dict[str, Any],
) -> None:
    """An absent field is no claim; only the node with an answer writes one."""
    wearing_it = {
        node["kind"] for node in multistate_ratchet["nodes"] if "increments" in node
    }

    assert wearing_it == {"rollforward"}


def test_the_published_operations_are_the_ten_the_compiler_applies() -> None:
    """The wire enum is the compiler's own vocabulary, and this holds the two together.

    Publishing the compiler's class names couples the format to them: a
    rename is a format change carrying a change-log line rather than a
    refactor. That cost is only paid honestly if the two lists cannot drift
    apart quietly, which is what this checks.
    """
    from gaspatchio.rollforward import _ops

    concrete = {
        name
        for name, value in vars(_ops).items()
        if isinstance(value, type)
        and issubclass(value, _ops.Op)
        and value is not _ops.Op
    }

    assert concrete == set(ROLLFORWARD_OPERATIONS)
    assert len(ROLLFORWARD_OPERATIONS) == len(set(ROLLFORWARD_OPERATIONS)) == 10


def test_the_schema_holds_the_summary_to_the_vocabulary_it_publishes(
    single_state_fund: dict[str, Any],
) -> None:
    """Four refusals, each of a document this producer would never write.

    An operation outside the ten, an empty array where the field should have
    been omitted, an empty label, and a key the format does not define. The
    schema is what refuses each; the producer's own omission rule is what
    keeps it from meeting one.
    """
    for edit in (
        lambda increment: increment.update(operation="Multiply"),
        lambda increment: increment.update(label=""),
        lambda increment: increment.update(surprise=1),
    ):
        document = copy.deepcopy(single_state_fund)
        (compilation,) = _of_kind(document, "rollforward")
        edit(compilation["increments"][0])
        result = validate_artifact(document)
        assert not result.ok
        assert any(finding.section == "schema" for finding in result.findings)

    emptied = copy.deepcopy(single_state_fund)
    (compilation,) = _of_kind(emptied, "rollforward")
    compilation["increments"] = []
    assert not validate_artifact(emptied).ok


def test_an_ordinal_that_does_not_restate_its_position_is_refused(
    single_state_fund: dict[str, Any],
) -> None:
    """The array order is normative and the ordinal restates it.

    A restatement is only worth carrying if it is checked. A reader citing
    "increment 3" of a document whose third movement says it is the fifth is
    reading one movement and citing another.
    """
    document = copy.deepcopy(single_state_fund)
    (compilation,) = _of_kind(document, "rollforward")
    compilation["increments"][1]["ordinal"] = 5

    result = validate_artifact(document)

    assert not result.ok
    (finding,) = [
        found
        for found in result.findings
        if found.section == "semantic" and "numbered" in found.message
    ]
    assert finding.where == compilation["id"]
    assert "[1, 5, 3]" in finding.message


def test_a_label_shared_by_two_movements_is_refused_in_the_document(
    single_state_fund: dict[str, Any],
) -> None:
    """JSON Schema has no cross-item uniqueness, so the semantic layer carries it.

    Stating it in the schema's voice would be stating it nowhere. The
    finding names both positions, because "a duplicate label" without them
    leaves a reader to find the pair themselves.
    """
    document = copy.deepcopy(single_state_fund)
    (compilation,) = _of_kind(document, "rollforward")
    compilation["increments"][1]["label"] = "fund_return"

    result = validate_artifact(document)

    assert not result.ok
    (finding,) = [
        found
        for found in result.findings
        if found.section == "semantic" and "labelled" in found.message
    ]
    assert "'fund_return'" in finding.message
    assert "increments 1, 2" in finding.message


# --- the column that materialises a running balance --------------------------


def _a_plain_model() -> ActuarialFrame:
    """Return a model that never escalated to a state machine."""
    frame = ActuarialFrame({"sum_assured": [100_000.0], "mortality_rate": [0.01]})
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return frame


@pytest.mark.parametrize("profile", ["audit", "executable"])
def test_each_extraction_states_the_balance_it_materialises(profile: str) -> None:
    """Both states of the ratchet say which balance each of them holds.

    The column is the running balance written onto the frame, and until it
    said so the only thing tying the two together was the formula's own
    text -- which section 8.2 declares free-form and no consumer may parse.
    Both profiles, because the ``audit`` reader asks this question as much
    as the ``executable`` one does.
    """
    exported: dict[str, Any] = json.loads(
        GraphExporter(_the_multistate_ratchet_pattern()).export(profile=profile)
    )
    (compilation,) = _of_kind(exported, "rollforward")

    assert _node(exported, "fund@1")["extracts"] == {
        "compilation": compilation["id"],
        "state": "account_value@eop",
    }
    assert _node(exported, "gmdb@1")["extracts"] == {
        "compilation": compilation["id"],
        "state": "benefit_base@eop",
    }


def test_a_single_state_pattern_states_its_one_balance(
    single_state_fund: dict[str, Any],
) -> None:
    """One state is the ordinary case, and it carries the object it is."""
    (compilation,) = _of_kind(single_state_fund, "rollforward")

    assert _node(single_state_fund, "account_value@1")["extracts"] == {
        "compilation": compilation["id"],
        "state": "fund_value@eop",
    }


def test_the_state_named_is_the_reference_and_not_the_reserved_id(
    multistate_ratchet: dict[str, Any],
) -> None:
    """A running state is named by the state, as an increment's target is."""
    extracted = _node(multistate_ratchet, "fund@1")["extracts"]
    (compilation,) = _of_kind(multistate_ratchet, "rollforward")

    assert not extracted["state"].startswith(STATE_NAMESPACE)
    assert f"{STATE_NAMESPACE}{extracted['state']}" in {
        node["id"] for node in multistate_ratchet["nodes"]
    }
    assert extracted["state"] in {
        increment["target"] for increment in compilation["increments"]
    }


def test_a_column_that_extracts_nothing_states_nothing(
    multistate_ratchet: dict[str, Any],
) -> None:
    """Absent on every column of a model that never reached a state machine.

    Asked of both: the timeline's own columns inside the ratchet model,
    which sit beside a compilation and extract none of it, and an ordinary
    calculation in a model that has no compilation at all.
    """
    plain: dict[str, Any] = json.loads(GraphExporter(_a_plain_model()).export())

    assert "extracts" not in _node(plain, "death_claims@1")
    assert "extracts" not in _node(multistate_ratchet, "month@1")
    assert [
        node["id"] for node in multistate_ratchet["nodes"] if "extracts" in node
    ] == ["fund@1", "gmdb@1"]


def test_a_line_that_wraps_two_extractions_states_both_balances() -> None:
    """One formula may materialise two balances, and then it carries the array.

    The single case is the object it is rather than an array of one: a
    reader of a column that holds one balance should not index past a
    wrapper to reach it, and one holding two is reading a list because
    there are two.
    """
    frame = ActuarialFrame(
        {
            "fund_init": [100_000.0],
            "gmdb_init": [100_000.0],
            "fund_return": [[0.008] * _PERIODS],
        }
    )
    frame = _timeline(frame)
    builder = frame.projection.rollforward(
        states={
            "account_value": frame["fund_init"],
            "benefit_base": frame["gmdb_init"],
        }
    )
    builder["account_value"].grow(frame["fund_return"], label="fund_growth")
    builder["benefit_base"].grow(frame["fund_return"], label="base_growth")
    compiled = compile_rollforward(builder)
    frame.fund = compiled.expr_for("account_value")
    frame.total = compiled.expr_for("account_value") + compiled.expr_for("benefit_base")
    exported: dict[str, Any] = json.loads(GraphExporter(frame).export())
    (compilation,) = _of_kind(exported, "rollforward")

    assert _node(exported, "fund@1")["extracts"] == {
        "compilation": compilation["id"],
        "state": "account_value@eop",
    }
    assert _node(exported, "total@1")["extracts"] == [
        {"compilation": compilation["id"], "state": "account_value@eop"},
        {"compilation": compilation["id"], "state": "benefit_base@eop"},
    ]


def test_a_movement_pulled_back_out_states_no_balance() -> None:
    """An increment is a signed movement, and a movement is not a balance.

    The call carries a label and no state, so the producer holds no state
    reference to write. Deriving one from the compilation's own summary
    would put the movement in front of a reader as the balance it landed
    on, which is a different quantity and a wrong claim in the one document
    whose purpose is to be checked.
    """
    frame = ActuarialFrame({"av_init": [100.0], "premium": [[10.0] * _PERIODS]})
    frame = _timeline(frame)
    builder = frame.projection.rollforward(
        states={"fund_value": frame["av_init"]}, track_increments=True
    )
    builder["fund_value"].add(frame["premium"], label="premium")
    frame.paid_in = compile_rollforward(builder).increment_for("premium")
    exported: dict[str, Any] = json.loads(GraphExporter(frame).export())

    assert "extracts" not in _node(exported, "paid_in@1")
    assert (
        _of_kind(exported, "rollforward")[0]["id"]
        in _node(exported, "paid_in@1")["reads"]
    )


def test_a_wrapping_line_that_loses_the_call_states_no_balance() -> None:
    """No call, no state reference, and the producer says nothing rather than guess.

    Section 16's own carve-out, from the other end: a line reaching a
    compilation through the kernel's scratch column keeps a truncation of
    the compilation's identity and nothing of which state came back.
    """
    exported: dict[str, Any] = json.loads(
        GraphExporter(_the_wrapped_extraction_pattern()).export()
    )

    assert "extracts" not in _node(exported, "with_opening@1")


def test_a_column_naming_a_compilation_it_does_not_read_is_refused(
    multistate_ratchet: dict[str, Any],
) -> None:
    """``extracts`` and the ``reads`` entry are one claim said twice.

    The ``reads`` entry is what an edge walk follows; this field is what
    says which balance came back along it. A column pointing a reader at a
    node its own edges do not connect it to is worse than one saying
    nothing at all.
    """
    document = copy.deepcopy(multistate_ratchet)
    _node(document, "fund@1")["extracts"]["compilation"] = (
        f"{ROLLFORWARD_NAMESPACE}000000000000"
    )

    result = validate_artifact(document)

    assert not result.ok
    (finding,) = [
        found
        for found in result.findings
        if found.section == "semantic" and "is not among what it reads" in found.message
    ]
    assert finding.where == "fund@1"
    assert "'account_value@eop'" in finding.message


def test_a_column_naming_a_balance_the_compilation_does_not_carry_is_refused(
    multistate_ratchet: dict[str, Any],
) -> None:
    """A compilation carries the balances it declares and no others.

    The state before the ``@`` is read the same way the compiler reads it
    on the way in, so a reference naming a state no ``states`` entry holds
    is a column claiming a balance nothing in the document carries.
    """
    document = copy.deepcopy(multistate_ratchet)
    _node(document, "gmdb@1")["extracts"]["state"] = "surrender_value@eop"

    result = validate_artifact(document)

    assert not result.ok
    (finding,) = [
        found
        for found in result.findings
        if found.section == "semantic" and "declares" in found.message
    ]
    assert finding.where == "gmdb@1"
    assert "'surrender_value'" in finding.message


def test_a_compilation_that_declares_no_states_is_checked_against_nothing(
    multistate_ratchet: dict[str, Any],
) -> None:
    """A producer that could not reach the compiled artefact omits ``states``.

    Reading that absence as an empty list would refuse the one document the
    omission exists for, so the second reading is skipped rather than
    answered.
    """
    document = copy.deepcopy(multistate_ratchet)
    (compilation,) = _of_kind(document, "rollforward")
    del compilation["states"]
    _node(document, "gmdb@1")["extracts"]["state"] = "surrender_value@eop"

    assert validate_artifact(document).ok


# --- what the compilation moved ---------------------------------------------
#
# A rollforward's audit artefact is a movement schedule: an opening balance,
# each signed movement under the name the step was declared by, a closing
# balance, per period. The summary above says which movements a chain applies;
# this says what each of them came to. The producer reaches them by re-tracking
# the registered compilation over the finished frame, so the model is untouched
# and the tracked compilation's own identity is never written anywhere.


def _with_values(frame: ActuarialFrame) -> dict[str, Any]:
    """Return ``frame``'s artifact exported with the values it finished with.

    The fixtures above export the structure alone, which is all the summary
    needs. An amount is enrichment, and enrichment is read only under an
    evaluation context -- so the cases below run the model and hand the
    finished frame over, which is what every real export does.
    """
    exported: dict[str, Any] = json.loads(
        GraphExporter(frame).export(result_df=frame.collect())
    )
    return exported


@pytest.fixture(scope="module")
def fund_with_values() -> dict[str, Any]:
    """The single-state fund, exported with what it came to."""
    return _with_values(_the_single_state_fund_pattern())


@pytest.fixture(scope="module")
def ratchet_with_values() -> dict[str, Any]:
    """The multi-state ratchet, exported with what it came to."""
    return _with_values(_the_multistate_ratchet_pattern())


def _movements(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return what the one compilation in ``artifact`` moved, key by key."""
    (compilation,) = _of_kind(artifact, "rollforward")
    moved: dict[str, Any] = compilation["movements"]
    return moved


def test_every_step_of_the_chain_carries_an_amount(
    fund_with_values: dict[str, Any],
) -> None:
    """Including the floor, which carries no label and is keyed by its ordinal.

    This is what lets a reader close ``closing = opening + sum of movements``
    with no residual term: a chain whose floor went untracked would put that
    floor's own amount -- the money the guarantee put back -- off the file, in
    exactly the model class that needs it.
    """
    moved = _movements(fund_with_values)

    assert list(moved) == ["fund_return", "me_charge", "floor@3"]
    assert all(len(amounts) == _PERIODS for amounts in moved.values())
    # This model's floor cannot bite: the balance is a product of
    # non-negative factors, so the guarantee never puts anything back and the
    # row reads zero all the way down. That is the truth about this model,
    # and it is a row rather than an absence.
    assert moved["floor@3"] == [0.0] * _PERIODS


def test_a_charge_is_negative_and_a_growth_is_positive(
    fund_with_values: dict[str, Any],
) -> None:
    """Signed as section 16.2 defines: what the step did to the balance."""
    moved = _movements(fund_with_values)

    assert all(amount > 0 for amount in moved["fund_return"])
    assert all(amount < 0 for amount in moved["me_charge"])


def test_the_state_node_carries_the_closing_balance(
    fund_with_values: dict[str, Any],
) -> None:
    """And it is the same balance the column that extracts it holds.

    The two are one series read twice -- the state is where the compilation's
    account of its own balance begins, and the column is that balance written
    onto the frame -- so a document where they differed would be a document
    disagreeing with itself about one number.
    """
    state = _node(fund_with_values, f"{STATE_NAMESPACE}fund_value@eop")

    assert (
        state["value_sample"]
        == _node(fund_with_values, "account_value@1")["value_sample"]
    )


def test_the_state_states_its_shape_and_leaves_its_type_alone(
    fund_with_values: dict[str, Any],
) -> None:
    """``shape`` moves because the producer read one; ``dtype`` must not.

    A running state is a leaf, and a leaf's type is inside its canonical bytes
    (section 12.1). Naming one here would move the state's two digests, the
    compilation's, and the ``graph_fingerprint`` of every model that ever
    compiled a rollforward -- for a reading that changes no calculation.
    """
    state = _node(fund_with_values, f"{STATE_NAMESPACE}fund_value@eop")

    assert state["shape"] == "list"
    assert state["dtype"] == "unknown"


def test_a_running_state_carries_its_balance_without_declaring_retention(
    fund_with_values: dict[str, Any],
) -> None:
    """The superseded-definition rule is about a column, and this is not one.

    ``in_final_schema`` is false on a running state by construction: nothing
    on the frame ever held it. Asking it to declare ``retained`` would ask a
    producer to say it had held aside a column that never existed.
    """
    state = _node(fund_with_values, f"{STATE_NAMESPACE}fund_value@eop")

    assert state["in_final_schema"] is False
    assert "retained" not in state
    assert validate_artifact(fund_with_values).ok


def test_the_waterfall_closes_on_the_document_s_own_numbers(
    fund_with_values: dict[str, Any],
) -> None:
    """``closing = opening + sum of movements``, every term of it quoted.

    Every term is the full double the run held (section 8), so the residual
    an honest document shows is the machine's own arithmetic over them. The
    budget is the one the wire needed while it rounded each term to six
    decimals -- half a decimal per term the identity adds, the opening, the
    closing and one per movement -- and a reader of a document written then
    still needs it.
    """
    moved = _movements(fund_with_values)
    balance = _node(fund_with_values, f"{STATE_NAMESPACE}fund_value@eop")[
        "value_sample"
    ]
    budget = (len(moved) + 2) * 5e-7

    for period in range(1, _PERIODS):
        total = sum(amounts[period] for amounts in moved.values())
        assert abs(balance[period] - (balance[period - 1] + total)) <= budget


def test_two_balances_carry_their_own_movements(
    ratchet_with_values: dict[str, Any],
) -> None:
    """A movement lands on a balance, and the ratchet lands on the other one.

    The anniversary is the whole point of the pattern: the benefit base steps
    up to the fund's high-water mark twelve months in and moves by nothing at
    all in between, and the eleven zeros are the file saying so rather than
    leaving the periods out.
    """
    moved = _movements(ratchet_with_values)
    anniversary = 11

    assert list(moved) == ["fund_growth", "gmdb_ratchet"]
    assert moved["gmdb_ratchet"][anniversary] > 0
    assert moved["gmdb_ratchet"][anniversary - 1] == 0.0
    assert moved["gmdb_ratchet"][anniversary + 1] == 0.0
    # And the base is the fund at the period it stepped up in.
    fund = _node(ratchet_with_values, f"{STATE_NAMESPACE}account_value@eop")
    base = _node(ratchet_with_values, f"{STATE_NAMESPACE}benefit_base@eop")
    assert base["value_sample"][anniversary] == pytest.approx(
        fund["value_sample"][anniversary]
    )


def test_the_tracked_compilation_s_own_identity_is_never_written() -> None:
    """The producer re-tracks; the node keeps the identity the model ran under.

    ``track_increments`` is inside a compiled rollforward's fingerprint, so
    the tracked compilation is a different compilation. A producer that let
    that identity onto the wire would publish a document naming a machine the
    model never compiled.
    """
    artifact = _with_values(_the_single_state_fund_pattern())
    (compilation,) = _of_kind(artifact, "rollforward")
    # The node names the compilation by a truncation of its own fingerprint,
    # which is how the registry is reached for the one the model ran.
    named = compilation["id"].removeprefix(ROLLFORWARD_NAMESPACE)
    # The registry is keyed by fingerprint and schedule, so another test in the
    # same process that compiled this pattern over another timeline holds a
    # second entry with this fingerprint. One fingerprint is one compilation.
    held_under = [
        (fingerprint, held)
        for (fingerprint, _schedule), held in artefacts._ROLLFORWARDS.items()  # noqa: SLF001 -- the registry under test
        if fingerprint.split(":", 1)[-1].startswith(named)
    ]
    assert len({fingerprint for fingerprint, _ in held_under}) == 1
    ran_under = held_under[0][1]
    tracked = compile_rollforward(
        dataclasses.replace(ran_under.ir, track_increments=True)
    )
    document = json.dumps(artifact)

    assert ran_under.ir.track_increments is False
    assert tracked.fingerprint() != ran_under.fingerprint()
    # The node names the machine the model ran; the tracked one appears
    # nowhere, neither whole nor in the truncation an id is built from.
    assert named in document
    assert tracked.fingerprint() not in document
    assert tracked.fingerprint().split(":", 1)[-1][: len(named)] not in document
    # And the movements are on the file all the same, which is the whole
    # point: the amounts came off a tracked run of the same machine.
    assert compilation["movements"]


def test_a_document_carrying_no_values_carries_no_movements() -> None:
    """Enrichment is absent rather than null where there is no context for it.

    ``movements`` is read only under the envelope's evaluation context, like
    the sample and the walk-through beside it, and a null on every node of a
    model that never escalated to a state machine would read as a producer
    that went looking for a waterfall inside a multiplication.
    """
    frame = _the_single_state_fund_pattern()
    document: dict[str, Any] = json.loads(GraphExporter(frame).export(result_df=None))
    (compilation,) = _of_kind(document, "rollforward")

    assert document["enrichment"] is None
    assert "movements" not in compilation
    assert "value_sample" not in compilation


def test_movements_that_are_not_the_steps_of_the_chain_are_refused(
    fund_with_values: dict[str, Any],
) -> None:
    """A member short of one step closes the identity on a number nobody named.

    The keys are the kernel's own -- the author's label, or
    ``{kind}@{ordinal}`` on a structural step -- so the document's two
    accounts of one chain are held to each other rather than being allowed to
    drift.
    """
    document = copy.deepcopy(fund_with_values)
    del _movements(document)["floor@3"]

    result = validate_artifact(document)

    assert not result.ok
    (finding,) = [
        found
        for found in result.findings
        if found.section == "semantic" and "movements" in found.message
    ]
    assert "'floor@3'" in finding.message


# --- the shipped patterns, and the axis the movements sit on -----------------
#
# The two patterns in ``gaspatchio/tutorials/patterns/rollforward-patterns``
# each carry a ``main(af)`` and a small model-point file, so the exporter runs
# them as it runs any other model. That is what makes this gap testable at all:
# before it, no shipped tutorial exported a rollforward and every claim about
# one was made against a model written inside a test.

_PATTERNS = Path(gaspatchio.__file__).parent / "tutorials/patterns/rollforward-patterns"


def _exported(model: str, points: str, out: Path, *extra: str) -> dict[str, Any]:
    """Run ``calc-graph`` over one shipped pattern and return its document."""
    result = CliRunner().invoke(
        app,
        [
            "calc-graph",
            str(_PATTERNS / model),
            str(_PATTERNS / points),
            "-o",
            str(out),
            *extra,
        ],
    )
    assert result.exit_code == 0, result.output
    document: dict[str, Any] = json.loads(out.read_text())
    assert validate_artifact(document).ok
    return document


@pytest.mark.parametrize(
    ("model", "points", "steps"),
    [
        ("01_single_state_fund.py", "01_model_points.parquet", 3),
        ("02_multistate_ratchet.py", "02_model_points.parquet", 2),
    ],
)
def test_a_shipped_pattern_exports_what_it_moved(
    tmp_path: Path, model: str, points: str, steps: int
) -> None:
    """Each pattern runs under the exporter and carries an amount per step."""
    document = _exported(model, points, tmp_path / "out.json")
    (compilation,) = _of_kind(document, "rollforward")

    assert len(compilation["increments"]) == steps
    assert len(compilation["movements"]) == steps


def test_the_axis_goes_inside_the_member(tmp_path: Path) -> None:
    """Two policies: one array per movement, not one mapping per policy.

    Which steps a chain has is a fact about the compilation and not about any
    policy, so a mapping per entry would let two entries of one axis disagree
    about it -- and would make a reader index a policy before they could name
    a movement.
    """
    document = _exported(
        "01_single_state_fund.py",
        "01_model_points.parquet",
        tmp_path / "out.json",
        "--policies",
        "all",
    )
    (compilation,) = _of_kind(document, "rollforward")
    carried = len(document["policies"])

    assert carried == 2
    assert list(compilation["movements"]) == ["fund_return", "me_charge", "floor@3"]
    for amounts in compilation["movements"].values():
        assert len(amounts) == carried
        assert all(len(one) == 12 for one in amounts)


def test_the_book_s_movement_is_the_sum_of_its_policies(tmp_path: Path) -> None:
    """A movement is additive, so the fold of the book is the fold of them.

    That identity is what makes a fold entry's waterfall mean anything: the
    book's movement schedule has to be the schedule of the policies in it,
    or a reader adding up the page would find the total is nobody's. The fold
    is the producer's own, over every row of the finished run, and this is it
    checked against the rows the document also carries.
    """
    document = _exported(
        "01_single_state_fund.py",
        "01_model_points.parquet",
        tmp_path / "out.json",
        "--policies",
        "all",
        "--portfolio-by",
        "sum:av",
    )
    (compilation,) = _of_kind(document, "rollforward")
    axis = document["policies"]
    (fold,) = [at for at, entry in enumerate(axis) if entry["policy_id"] is None]
    policies = [at for at, entry in enumerate(axis) if entry["policy_id"] is not None]

    assert axis[fold]["aggregation"] == "period_sum"
    budget = (len(policies) + 1) * 5e-7
    for amounts in compilation["movements"].values():
        for period in range(12):
            over_the_book = sum(amounts[at][period] for at in policies)
            assert abs(amounts[fold][period] - over_the_book) <= budget
    # And the balance the movements land on folds the same way.
    balance = _node(document, f"{STATE_NAMESPACE}av@eop")["value_sample"]
    for period in range(12):
        over_the_book = sum(balance[at][period] for at in policies)
        assert abs(balance[fold][period] - over_the_book) <= budget


# --- the movements are the run's --------------------------------------------
#
# The producer reads the amounts by re-tracking the registered compilation, and
# the kernel call names its operands by column name. A column name is not a
# value: a model that writes over an input after pulling its state back out
# leaves the finished frame holding something the machine never saw. So the
# re-track is bound to the versions the compilation read -- the graph's own
# account of what it read, one node id per column -- or it is declined, and the
# document says so rather than publishing a run nobody performed. A finding of
# the external review of 2026-09-20.


def _the_pattern_with_an_overwritten_input() -> ActuarialFrame:
    """Return the single-state fund with its growth rate doubled afterwards.

    The review's own reproduction, in miniature. ``account_value`` holds the
    run the 1% return produced; the line after it makes ``fund_return`` mean
    2%, and nothing carries what the column held before -- the assignment door
    retains a *definition* a later definition replaced, and the values a column
    arrived with were never one.
    """
    frame = _the_single_state_fund_pattern()
    frame.fund_return = frame.fund_return * 2.0
    return frame


def _the_pattern_with_a_superseded_input() -> ActuarialFrame:
    """Return the same shape with the overwritten input a *calculation*.

    The difference is the whole of what the producer can recover. Here the
    definition the machine read is one the model wrote, so the assignment door
    carried it aside when the next line replaced it, and the re-track has the
    values the compilation bound to evaluate against.
    """
    frame = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "base_return": [[0.01] * _PERIODS],
            "me_charge": [[0.001] * _PERIODS],
        }
    )
    frame = _timeline(frame)
    frame.fund_return = frame.base_return * 1.0
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    (
        builder["fund_value"]
        .grow(frame["fund_return"], label="fund_return")
        .charge(frame["me_charge"], label="me_charge")
    )
    frame.account_value = compile_rollforward(builder).expr_for("fund_value")
    frame.fund_return = frame.base_return * 2.0
    return frame


def _the_balance(artifact: dict[str, Any], state: str) -> Any:  # noqa: ANN401 — one sampled balance, of whatever the model held
    """Return the closing balance one running state carries."""
    return _node(artifact, f"{STATE_NAMESPACE}{state}")["value_sample"]


def test_an_overwritten_input_leaves_the_movements_off_the_file() -> None:
    """Re-tracking against an overwritten input, from the producer's end.

    Re-tracking by name here computes a whole movement schedule against a
    growth rate the machine never saw: the amounts, the closing balance and
    the check line over them all agree with each other, and none of them
    happened. The producer would rather say nothing.
    """
    document = _with_values(_the_pattern_with_an_overwritten_input())
    (compilation,) = _of_kind(document, "rollforward")

    assert compilation["increments"], "the machine itself is still described"
    assert "movements" not in compilation


def test_the_balance_a_declined_re_track_carries_is_the_run_s() -> None:
    """And it is the column the model wrote that balance into, not a re-track.

    A line assigning ``compiled.expr_for(...)`` IS that balance on the frame,
    so the run's own closing values are in the document whatever happened to
    the machine's inputs afterwards. Quoting them costs nothing and leaves the
    state node with the one number it exists to carry.
    """
    document = _with_values(_the_pattern_with_an_overwritten_input())
    untouched = _with_values(_the_single_state_fund_pattern())

    assert (
        _the_balance(document, "fund_value@eop")
        == _node(document, "account_value@1")["value_sample"]
    )
    # And it is the same run the model would have had without the last line.
    assert _the_balance(document, "fund_value@eop") == _the_balance(
        untouched, "fund_value@eop"
    )


def test_the_re_track_binds_to_the_definition_the_machine_read() -> None:
    """A superseded definition the frame carried is what the movements come off.

    The model grows at 1%, extracts, and then makes ``fund_return`` mean 2%.
    The definition the compilation bound is still in reach -- the assignment
    door carried it aside -- so the amounts are the 1% run's, and re-tracking
    by column name would have doubled every one of them.
    """
    document = _with_values(_the_pattern_with_a_superseded_input())
    (compilation,) = _of_kind(document, "rollforward")
    opening = 100_000.0

    assert compilation["movements"]["fund_return"][0] == pytest.approx(opening * 0.01)
    assert (
        _the_balance(document, "fund_value@eop")
        == _node(document, "account_value@1")["value_sample"]
    )
    assert validate_artifact(document).ok


def test_the_declined_amounts_are_explained_rather_than_missing() -> None:
    """A compilation that says what it applies and carries none of the amounts.

    That combination is honest and odd, and a reader meeting it would
    otherwise be left to derive the waterfall from the balances -- the
    identity solved for the terms nobody quoted, true by construction
    whatever the machine did. The validator says why instead.
    """
    document = _with_values(_the_pattern_with_an_overwritten_input())
    result = validate_artifact(document)
    (compilation,) = _of_kind(document, "rollforward")

    assert result.ok, "an absence is not a refusal"
    (finding,) = [
        found for found in result.findings if found.where == compilation["id"]
    ]
    assert finding.severity == "warning"
    assert "carries the amount of none of them" in finding.message
    assert "no longer on the finished frame" in finding.message


def test_a_state_whose_own_column_is_another_run_is_refused() -> None:
    """The falsification for a wrong re-track, and the one witness outside it.

    A producer that re-tracked against the wrong values writes a document
    every other reading in the format passes: the fingerprints hold, the axis
    is as long as the enrichment, and ``closing = opening + sum of movements``
    closes, because both sides were computed together on the wrong run. The
    column the model materialised the balance into was not, and it is what
    the two are held to.
    """
    document = json.loads(
        GraphExporter(_the_single_state_fund_pattern()).export(
            result_df=_the_single_state_fund_pattern().collect(), profile="executable"
        )
    )
    document = copy.deepcopy(document)
    balance = _node(document, f"{STATE_NAMESPACE}fund_value@eop")
    balance["value_sample"] = [round(one * 2, 6) for one in balance["value_sample"]]

    result = validate_artifact(document)

    assert not result.ok
    (finding,) = [
        found for found in result.findings if "one series read twice" in found.message
    ]
    assert finding.severity == "error"
    assert finding.where == f"{STATE_NAMESPACE}fund_value@eop"
    assert "'account_value@1'" in finding.message


def test_a_wrapped_extraction_is_not_read_as_the_balance() -> None:
    """``extracts`` says which compilation a formula reached, not that it IS it.

    A line adding one to a balance materialises it as honestly as a bare line
    does, and its column is a different quantity. Reading that column against
    the state would refuse an honest document over an arithmetic the model
    wrote on purpose, so the operation tree and not the record decides.
    """
    frame = ActuarialFrame({"av_init": [100_000.0], "fund_return": [[0.01] * _PERIODS]})
    frame = _timeline(frame)
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    builder["fund_value"].grow(frame["fund_return"], label="fund_return")
    compiled = compile_rollforward(builder)
    frame.account_value = compiled.expr_for("fund_value")
    frame.with_a_margin = compiled.expr_for("fund_value") + 1.0
    document = json.loads(
        GraphExporter(frame).export(result_df=frame.collect(), profile="executable")
    )
    wrapped = _node(document, "with_a_margin@1")

    assert wrapped["extracts"]["state"] == "fund_value@eop"
    assert wrapped["value_sample"] != _the_balance(document, "fund_value@eop")
    assert validate_artifact(document).ok


def test_a_document_carrying_no_operation_tree_is_not_asked() -> None:
    """The reading the ``executable`` profile earns and the ``audit`` one does not.

    Which columns ARE a balance and which wrapped one is a fact about the
    formula, and the audit profile carries no formula a consumer may read --
    ``formula`` is the author's own text and nothing may parse it. So a
    document with the trees on it is held to this and one without states
    nothing about it, which is the honest limit rather than a reading that
    guessed.
    """
    document = _with_values(_the_single_state_fund_pattern())
    balance = _node(document, f"{STATE_NAMESPACE}fund_value@eop")
    balance["value_sample"] = [round(one * 2, 6) for one in balance["value_sample"]]

    assert document["profile"] == "audit"
    assert all("expr" not in node for node in document["nodes"])
    assert validate_artifact(document).ok
