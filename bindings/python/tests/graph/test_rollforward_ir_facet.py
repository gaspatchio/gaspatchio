# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The compiled state machine in the file: the operations, not only the identity.

The audit profile carries a compilation's identity, what it reads, the states
it declares and every line that read it. That is enough to follow a model and
not enough to run one: the fingerprint on the node is an identity, and a
reader holding it cannot get from there to "the cost of insurance is struck on
the net amount at risk, before the credited rate, rounded to the cent".

This is the record that closes that gap, and the models below are the shapes
that make the gap matter: a universal-life account value charged on the amount
at risk while a benefit base ratchets to its high-water mark, a fund whose
opening value is an expression the tree did not build, and a machine that
stops when the contract does.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    State,
    WhenThen,
)
from gaspatchio.frame.graph import GraphExporter, fold, local_fingerprint
from gaspatchio.frame.graph.artifact import PROFILE_EXECUTABLE, _envelope_facets
from gaspatchio.frame.graph.facets import FacetLedger
from gaspatchio.frame.graph.graph_models import ROLLFORWARD_FINGERPRINT_ATTR
from gaspatchio.frame.graph.op_json import op_node_from_json, op_node_to_json
from gaspatchio.frame.graph.rollforward_ir import (
    FACET_NAME,
    rollforward_ir_facet,
    rollforward_ir_for,
)
from gaspatchio.frame.lowering import artefacts
from gaspatchio.rollforward import compile_rollforward

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import OpNode

# Long enough for the anniversary ratchet to fire twice, short enough to stay
# out of the way: nothing here executes the kernel, it reads what was compiled.
_PERIODS = 24


def _timeline(frame: ActuarialFrame) -> ActuarialFrame:
    """Return ``frame`` with the projection timeline these machines run on."""
    return frame.projection.set(
        start_date=datetime.date(2025, 1, 31),
        n_periods=_PERIODS,
        frequency="monthly",
    )


def _the_multistate_ratchet_pattern() -> tuple[ActuarialFrame, dict[str, Any]]:
    """Return a universal-life account value beside the benefit base it drives.

    The account value is credited, then charged a cost of insurance on the net
    amount at risk; the benefit base ratchets on each anniversary to the fund's
    own end-of-period balance. Both reads are of a running balance no column on
    the frame holds, which is the whole reason the model escalated to a state
    machine at all.
    """
    anniversary = [(period + 1) % 12 == 0 for period in range(_PERIODS)]
    frame = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "gmdb_init": [100_000.0],
            "credited_rate": [[0.003] * _PERIODS],
            "coi_rate": [[0.0004] * _PERIODS],
            "death_benefit": [[250_000.0] * _PERIODS],
            "anniversary": [anniversary],
        }
    )
    frame = _timeline(frame)
    builder = frame.projection.rollforward(
        states={
            "account_value": frame["av_init"],
            "benefit_base": frame["gmdb_init"],
        },
        track_increments=True,
    )
    builder["account_value"].grow(frame["credited_rate"], label="interest").deduct_nar(
        frame["coi_rate"], death_benefit=frame["death_benefit"], label="coi"
    )
    builder["benefit_base"].ratchet(
        to=pl.col("account_value@eop"),
        when=frame["anniversary"],
        label="gmdb_ratchet",
    )
    compiled = compile_rollforward(builder)
    frame.fund = compiled.expr_for("account_value")
    frame.gmdb = compiled.expr_for("benefit_base")
    return frame, rollforward_ir_facet(compiled)


def _the_loaded_opening_value_pattern(
    batch_axes: tuple[str, ...] = ("policy",),
) -> tuple[ActuarialFrame, dict[str, Any]]:
    """Return a fund opening at a loaded premium and stopping at surrender.

    Every expression an operation takes has to be a bare column reference,
    and so does the contract boundary -- both reach the compiler's one
    single-column check and it refuses anything else -- so a state's opening
    value is the only place a machine carries an expression the tree did not
    build. This one does, and it stops at a boundary that is a column like
    any other.

    ``batch_axes`` is a parameter because ``canonical_form()`` folds a field
    left at its engine default out of the identity, and this is the one such
    field: a machine at every default names fewer keys than a compiled
    identity can move on. A caller checking that every field has a place in
    the record asks for a second axis, so that the conditional key is there
    to be checked.
    """
    frame = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "load": [0.95],
            "fund_return": [[0.01] * _PERIODS],
            "surrendered": [[False] * _PERIODS],
        }
    )
    frame = _timeline(frame)
    builder = frame.projection.rollforward(
        states={"fund_value": pl.col("av_init") * pl.col("load")},
        lapse_when_all_non_positive=("fund_value",),
        contract_boundary=frame["surrendered"],
        batch_axes=batch_axes,
    )
    builder["fund_value"].grow(frame["fund_return"], label="growth").round(decimals=2)
    compiled = compile_rollforward(builder)
    frame.fund = compiled.expr_for("fund_value")
    return frame, rollforward_ir_facet(compiled)


def _a_fund_rounded_to(decimals: int) -> dict[str, Any]:
    """Return the facet for a fund rounded inside the recursion to ``decimals``."""
    frame = ActuarialFrame({"av_init": [100_000.0], "fund_return": [[0.01] * _PERIODS]})
    frame = _timeline(frame)
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    builder["fund_value"].grow(frame["fund_return"]).round(decimals=decimals)
    return rollforward_ir_facet(compile_rollforward(builder))


def _the_only_compilation(facet: dict[str, Any]) -> dict[str, Any]:
    """Return the one machine a payload carries, refusing a payload of two."""
    (compilation,) = facet["compilations"].values()
    assert isinstance(compilation, dict)
    return compilation


def _increment(compilation: dict[str, Any], label: str) -> dict[str, Any]:
    """Return the one operation of ``compilation`` carrying ``label``."""
    found = [
        increment
        for increment in compilation["increments"]
        if increment["label"] == label
    ]
    assert found, (
        f"{label!r} is not in {[i['label'] for i in compilation['increments']]}"
    )
    return found[0]


# --- what the machine actually applies ---------------------------------------


def test_the_facet_carries_the_increments_the_kernel_actually_applies() -> None:
    """Every operation, in the order the kernel applies them, under its own name."""
    _, compilation = _the_multistate_ratchet_pattern()

    labels = [increment["label"] for increment in compilation["increments"]]

    assert labels == ["interest", "coi", "gmdb_ratchet"]
    assert [increment["operation"] for increment in compilation["increments"]] == [
        "Grow",
        "DeductNAR",
        "Ratchet",
    ]


def test_a_charge_on_the_net_amount_at_risk_shows_the_balance_it_reads() -> None:
    """The account-value term is in the calculation and in no argument.

    ``coi_rate * (death_benefit - account_value)``: the kernel takes that third
    term off the balance it is carrying, so a record listing only the arguments
    would say the charge reads a rate and a benefit and nothing else -- true of
    the call, false of the calculation.
    """
    _, compilation = _the_multistate_ratchet_pattern()
    coi = _increment(compilation, "coi")

    assert coi["reads_running_balance"] is True
    assert {"op": "state", "name": "account_value@eop"} in coi["operands"]


def test_a_ratchet_shows_the_other_balance_it_is_measured_against() -> None:
    """A cross-state read is a state operand, not a column nothing supplies.

    ``pl.col("account_value@eop")`` is a column name by convention only: the
    kernel resolves it against the live state vector and no frame ever holds
    it.
    """
    _, compilation = _the_multistate_ratchet_pattern()
    ratchet = _increment(compilation, "gmdb_ratchet")

    assert {"op": "state", "name": "account_value@eop"} in ratchet["operands"]
    assert {"op": "col", "name": "anniversary"} in ratchet["operands"]
    assert ratchet["target"] == "benefit_base@eop"


def test_an_operation_that_takes_a_flat_amount_claims_no_balance_read() -> None:
    """A withdrawal of six thousand is six thousand whatever the balance is."""
    frame = ActuarialFrame(
        {"av_init": [50_000.0], "withdrawal": [[6_000.0] * _PERIODS]}
    )
    frame = _timeline(frame)
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    builder["fund_value"].subtract(frame["withdrawal"], label="withdrawal")

    compilation = rollforward_ir_facet(compile_rollforward(builder))
    (drawdown,) = compilation["increments"]

    assert drawdown["reads_running_balance"] is False
    assert drawdown["operands"] == [{"op": "col", "name": "withdrawal"}]


def _movement_records(
    operation: str, amount: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the audit summary and executable record of one movement."""
    frame = ActuarialFrame(
        {
            "av_init": [50_000.0],
            "base_init": [50_000.0],
            "amount": [[100.0] * _PERIODS],
        }
    )
    frame = _timeline(frame)
    builder = frame.projection.rollforward(
        states={"av": frame["av_init"], "base": frame["base_init"]}
    )
    getattr(builder["av"], operation)(pl.col(amount), label="movement")
    compiled = compile_rollforward(builder)
    frame.result = compiled.expr_for("av")

    artifact = json.loads(GraphExporter(frame).export())
    (compilation,) = [
        node for node in artifact["nodes"] if node["kind"] == "rollforward"
    ]
    (summary,) = compilation["increments"]
    (executable,) = rollforward_ir_facet(compiled)["increments"]
    return summary, executable


@pytest.mark.parametrize("operation", ["add", "subtract"])
@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        pytest.param("amount", False, id="input"),
        pytest.param("av@bop", True, id="own-bop"),
        pytest.param("av@eop", True, id="own-eop"),
        pytest.param("base@bop", False, id="other-bop"),
        pytest.param("base@eop", False, id="other-eop"),
    ],
)
def test_explicit_amount_metadata_agrees_across_both_records(
    operation: str, amount: str, *, expected: bool
) -> None:
    """Add and Subtract read their classified amount, at either point.

    Apply would be the third, and no artifact carries one: the kernel has no
    evaluation for it, so ``compile_rollforward`` refuses it before there is
    a compilation to describe (``tests/rollforward/test_kernel_multi_state.py``).
    """
    summary, executable = _movement_records(operation, amount)
    expected_operand = {
        "op": "state" if "@" in amount else "col",
        "name": amount,
    }

    assert summary["reads_running_balance"] is expected
    assert executable["reads_running_balance"] is expected
    assert executable["operands"] == [expected_operand]
    assert {
        "label": summary["label"],
        "operation": summary["operation"],
        "target": summary["target"],
        "reads_running_balance": summary["reads_running_balance"],
    } == {
        key: executable[key]
        for key in ("label", "operation", "target", "reads_running_balance")
    }


def test_implicit_balance_metadata_keeps_the_charge_operand_tree() -> None:
    """Charge still appends its target state because its shape consumes it."""
    summary, executable = _movement_records("charge", "amount")

    assert summary["reads_running_balance"] is True
    assert executable["reads_running_balance"] is True
    assert executable["operands"] == [
        {"op": "col", "name": "amount"},
        {"op": "state", "name": "av@eop"},
    ]


def test_a_state_carries_the_value_it_opens_from() -> None:
    """Where the recursion starts is half of what makes it reproducible."""
    _, compilation = _the_multistate_ratchet_pattern()

    assert compilation["states"] == [
        {"name": "account_value", "init": {"op": "col", "name": "av_init"}},
        {"name": "benefit_base", "init": {"op": "col", "name": "gmdb_init"}},
    ]


def test_an_opening_value_the_tree_did_not_build_says_so() -> None:
    """The one expression a machine carries whole travels as what it is.

    The compiler refuses a compound expression everywhere else, so no
    increment carries one and the opening value is the only place this node
    type reaches a machine at all. The record says the text is one engine's,
    carries the calculation itself, and names the columns it declares it
    reads, rather than passing any of it off as a column reference.
    """
    _, compilation = _the_loaded_opening_value_pattern()
    (fund,) = compilation["states"]

    assert fund["init"]["op"] == "engine_native"
    assert fund["init"]["engine"] == "polars"
    assert fund["init"]["text"] == '[(col("av_init")) * (col("load"))]'
    assert fund["init"]["deps"] == ["av_init", "load"]


def test_an_expression_the_tree_did_not_build_reaches_only_the_opening_value() -> None:
    """An operation and the contract boundary are refused at the same check.

    What makes the opening value the *only* place: an operation's expression
    and the stopping test both go through the compiler's single-column
    check, and it refuses a compound one from either, naming which field it
    was. So "no increment carries an engine-native node, and no boundary
    does either" is a property of the compiler rather than a reading of the
    two machines above.
    """
    frame = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "load": [0.95],
            "fund_return": [[0.01] * _PERIODS],
            "surrendered": [[False] * _PERIODS],
            "matured": [[False] * _PERIODS],
        }
    )
    frame = _timeline(frame)

    on_an_operation = frame.projection.rollforward(
        states={"fund_value": frame["av_init"]}
    )
    on_an_operation["fund_value"].grow(
        pl.col("fund_return") * pl.col("load"), label="growth"
    )
    with pytest.raises(
        NotImplementedError, match=r"Grow\.rate is an expression over 2 of them"
    ):
        compile_rollforward(on_an_operation)

    on_the_boundary = frame.projection.rollforward(
        states={"fund_value": frame["av_init"]},
        contract_boundary=(pl.col("surrendered") | pl.col("matured")),
    )
    on_the_boundary["fund_value"].grow(frame["fund_return"], label="growth")
    with pytest.raises(
        NotImplementedError,
        match=r"contract_boundary is an expression over 2 of them",
    ):
        compile_rollforward(on_the_boundary)


def test_the_stopping_conditions_travel_with_the_machine() -> None:
    """A machine that stops and one that runs on are two different machines."""
    _, compilation = _the_loaded_opening_value_pattern()

    assert compilation["lapse_when_all_non_positive"] == ["fund_value"]
    assert compilation["contract_boundary"] == {"op": "col", "name": "surrendered"}


def test_two_machines_differing_only_in_a_rounding_precision_are_two_records() -> None:
    """Rounding inside the recursion compounds, so the precision is the model.

    Neither precision is an expression, so a record carrying only the
    operations' expressions would print these two identically while the
    compiler gives them two identities.
    """
    to_the_cent = _a_fund_rounded_to(2)
    to_the_pound = _a_fund_rounded_to(0)

    assert to_the_cent != to_the_pound
    assert to_the_cent["increments"][-1]["settings"] == {"decimals": 2}
    assert to_the_pound["increments"][-1]["settings"] == {"decimals": 0}


def test_an_optional_assumption_the_operation_was_not_given_is_stated_absent() -> None:
    """Operands are positional, so a missing one has to be named somewhere.

    The cost of insurance under the beginning-of-period convention takes no
    discount rate and no credited rate. Saying so is what stops a reader
    counting three operands and having to work out which three they are.
    """
    _, compilation = _the_multistate_ratchet_pattern()
    coi = _increment(compilation, "coi")

    assert coi["settings"] == {
        "nar_timing": "beginning_of_period",
        "coi_discount_rate": None,
        "credited_rate": None,
        "corridor_factor": None,
        "round_charge": None,
    }


def test_every_field_the_compiled_identity_covers_has_a_place_in_the_record() -> None:
    """The compiled identity is the published body, less its schedule, and only that.

    The guard that keeps the projection complete now holds by construction:
    the fingerprint is the section 12.3 recipe-grammar hash of the body the
    record carries, less the ``schedule`` member (spec 12.1), so a field folded
    into the identity with nowhere in this record to land cannot exist. It
    runs on a machine with a second batch axis so that every field is in the
    body with a value of its own. The schedule the machine runs on is in the
    record too, and is outside the identity: the fingerprint is the machine
    alone (spec 16).
    """
    from gaspatchio.rollforward._canonical import compiled_identity

    frame, compilation = _the_loaded_opening_value_pattern(
        batch_axes=("policy", "scenario")
    )
    ((fingerprint, body),) = rollforward_ir_for(fold(frame))["compilations"].items()
    compiled = artefacts.rollforward_for(fingerprint, body["schedule"])

    assert compiled.canonical_form() == {
        key: value for key, value in compilation.items() if key != "schedule"
    }
    assert compiled.canonical_form()["batch_axes"] == ["policy", "scenario"]
    assert "schedule" in compilation
    assert compiled_identity(body) == fingerprint == compiled.fingerprint()


# --- the payload, and where it rides -----------------------------------------


def test_the_machine_is_keyed_by_the_identity_its_node_carries() -> None:
    """One key per compilation, and it is the string the node already names."""
    frame, _ = _the_multistate_ratchet_pattern()
    graph = fold(frame)
    payload = rollforward_ir_for(graph)

    assert payload is not None
    ((fingerprint, _),) = payload["compilations"].items()
    assert [
        node.id for node in graph.nodes.values() if node.kind.value == "rollforward"
    ] == [f"rollforward:{fingerprint.removeprefix('sha256:')[:12]}"]


def test_a_model_with_no_state_machine_carries_nothing_to_say() -> None:
    """Nothing to say is not an empty machine, so no facet is written at all."""
    frame = ActuarialFrame({"sum_assured": [100.0], "death_rate": [0.01]})
    frame.death_claims = frame.sum_assured * frame.death_rate

    assert rollforward_ir_for(fold(frame)) is None


def test_a_compilation_out_of_reach_is_left_out_rather_than_named_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record here is a reading of the compiled artefact and of nothing else.

    The node keeps its identity, its reads and the lines that read it, which
    is what the record itself holds. The machine behind it is not in the
    record, so a graph folded where the compiler never ran has nothing to
    project -- and an entry with an empty body would say a state machine
    that does nothing.
    """
    frame, _ = _the_multistate_ratchet_pattern()
    monkeypatch.setattr(artefacts, "_ROLLFORWARDS", {})

    assert rollforward_ir_for(fold(frame)) is None


def test_the_executable_profile_announces_the_facet_without_requiring_it() -> None:
    """Announced where it is emitted, and never something a consumer must know.

    The compilation's node carries its identity, its reads and its declared
    states whether or not this facet is understood, so a consumer meeting a
    name it does not know here has lost the recipe rather than the record.
    """
    frame, _ = _the_multistate_ratchet_pattern()
    ledger = FacetLedger(used=set(), required=set())

    facets = _envelope_facets(fold(frame), ledger, profile=PROFILE_EXECUTABLE)

    assert list(facets) == [FACET_NAME]
    assert facets[FACET_NAME]["_producer"].startswith("https://")
    assert FACET_NAME in facets[FACET_NAME]["_schemaURL"]
    assert "compilations" in facets[FACET_NAME]
    assert ledger.as_lists() == ([FACET_NAME], [])


def test_an_exported_executable_artifact_carries_the_machine_it_compiled() -> None:
    """The whole path, from a model with a state machine to the file itself.

    The tests either side of this one hold the two ends: the one above
    builds the payload and checks it is announced, without exporting
    anything, and the one below exports the profile that does not carry it.
    Neither opens a file in the profile that does. What a consumer opens is
    a file, and what it has to find there is the machine keyed by the
    identity the compilation's own node names -- reached from the node it
    already holds, out of the same document, with the operations the machine
    applies and the configuration each one takes still on them.

    ``nar_timing`` is the sentence this record exists for: a cost of
    insurance struck on the balance the period opened at is a different
    charge from one struck after the period's credit, and a reader holding
    only the compiled fingerprint could not tell which one ran.
    """
    frame, _ = _the_multistate_ratchet_pattern()

    artifact: dict[str, Any] = json.loads(
        GraphExporter(frame).export(profile="executable")
    )

    ((fingerprint, machine),) = artifact["facets"][FACET_NAME]["compilations"].items()
    (node,) = [n for n in artifact["nodes"] if n["kind"] == "rollforward"]
    assert FACET_NAME in artifact["facets_used"]
    assert artifact["facets_required"] == []
    assert node["expr"]["attrs"][ROLLFORWARD_FINGERPRINT_ATTR] == fingerprint
    assert [increment["label"] for increment in machine["increments"]] == [
        "interest",
        "coi",
        "gmdb_ratchet",
    ]
    assert all("settings" in increment for increment in machine["increments"])
    assert machine["increments"][1]["settings"]["nar_timing"] == "beginning_of_period"


def test_the_audit_profile_carries_no_intermediate_representation() -> None:
    """What a reviewer reads is the record; the machine rides one profile up."""
    frame, _ = _the_multistate_ratchet_pattern()
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export())

    assert FACET_NAME not in artifact["facets"]
    assert FACET_NAME not in artifact["facets_used"]


# --- the encoding both this facet and the executable profile are written in ---


_EVERY_NODE_TYPE: list[OpNode] = [
    Col("sum_assured"),
    Lit(30),
    Lit(0.05),
    Lit(value=True),
    Lit("annuity"),
    Lit((0.0, 18.0, 65.0)),
    BinOp("mul", Col("sum_assured"), Col("death_rate")),
    Call("at_period", args=(Col("reserve"),), attrs=(("offset", -1),)),
    Call("rollforward", args=(), attrs=(("fingerprint", "sha256:7be2aa10"),)),
    WhenThen(Col("is_anniversary"), Col("step_up"), Lit(0.0)),
    State("account_value@eop"),
    EngineNative(engine="polars", text='[(col("a")) * (2.0)]', deps=("a",)),
]


@pytest.mark.parametrize("node", _EVERY_NODE_TYPE, ids=lambda node: type(node).__name__)
def test_a_tree_written_out_and_read_back_is_the_same_tree(node: OpNode) -> None:
    """Through JSON and back, including the identity the artifact stamps on it."""
    written = op_node_to_json(node)
    parsed = op_node_from_json(json.loads(json.dumps(written)))

    assert parsed == node
    assert op_node_to_json(parsed) == written
    assert local_fingerprint(parsed) == local_fingerprint(node)


def test_the_facet_round_trips_to_the_same_canonical_bytes() -> None:
    """Parsing the file back gives the same trees, so the same identity."""
    _, compilation = _the_multistate_ratchet_pattern()

    for increment in compilation["increments"]:
        for operand in increment["operands"]:
            parsed = op_node_from_json(operand)
            assert op_node_to_json(parsed) == operand
            assert local_fingerprint(parsed) == local_fingerprint(
                op_node_from_json(op_node_to_json(parsed))
            )


def test_a_literal_band_and_one_boundary_of_it_are_two_documents() -> None:
    """The sequence form is named apart, so neither collapses into the other."""
    assert op_node_to_json(Lit((18.0,))) == {"op": "lit", "values": [18.0]}
    assert op_node_to_json(Lit(18.0)) == {"op": "lit", "value": 18.0}


def test_a_node_type_this_vocabulary_does_not_hold_is_refused() -> None:
    """Seven node types, and a document naming an eighth was written elsewhere.

    Matched on the offending name rather than on one of the seven: the
    refusal lists all seven, so ``engine_native`` is in every unknown-node
    message and would pass this whether or not the message named what it met.
    """
    with pytest.raises(ValueError, match="matrix"):
        op_node_from_json({"op": "matrix", "name": "x"})


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"op": "lit", "value": 1, "values": [1]}, id="value and values"),
        pytest.param(
            {"op": "lit", "value": 1, "date": "2024-01-01"}, id="value and date"
        ),
        pytest.param(
            {"op": "lit", "values": [1], "date": "2024-01-01"}, id="values and date"
        ),
    ],
)
def test_a_literal_carrying_two_forms_at_once_is_refused(
    payload: dict[str, object],
) -> None:
    """One is a value, one a sequence and one a calendar day: exactly one.

    Any two of them together are two literals written as one node, and the
    document would have to be read by guessing which the producer meant.
    """
    with pytest.raises(ValueError, match="exactly one of"):
        op_node_from_json(payload)


def test_an_operator_outside_the_closed_vocabulary_is_refused() -> None:
    """Seven arithmetic, six comparison, two logical, and nothing else."""
    with pytest.raises(ValueError, match="closed"):
        op_node_from_json(
            {
                "op": "binop",
                "kind": "nand",
                "left": {"op": "col", "name": "a"},
                "right": {"op": "col", "name": "b"},
            }
        )


def test_a_declared_read_that_is_not_a_column_name_is_refused() -> None:
    """The refusal names ``deps``, the field a reader has to go and fix."""
    with pytest.raises(TypeError, match="'deps' carries 3"):
        op_node_from_json(
            {
                "op": "engine_native",
                "engine": "polars",
                "text": 'col("a") * 2.0',
                "deps": [3],
            }
        )


def test_a_call_configured_twice_over_is_refused_rather_than_half_written() -> None:
    """A JSON object holds a key once, so the second would displace the first."""
    with pytest.raises(ValueError, match="twice"):
        op_node_to_json(
            Call("at_period", args=(), attrs=(("offset", -1), ("offset", 1)))
        )
