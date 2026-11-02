# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The two payload sections nothing emits, and the evidence the schema holds them.

Section 17 of ``spec/graph-artifact/v0-preview.md`` reserves two payload
sections: ``state_graph``, for a product declared as states and the
intensities of the transitions between them, and ``nested_valuation``, for a
valuation evaluated inside the projection by an inner model. Nothing in this
package emits either one, and a seat that has never been filled is a claim
rather than a fact.

This module is what turns the claim into evidence. Each section has one
hand-built example artifact beside it, and the tests here do three things with
them: they show that :func:`validate_artifact` accepts each artifact whole,
they read the fields the section exists to carry, and they show that a
deliberately broken variant of each is *refused* -- because an acceptance no
document can fail is not an acceptance. Nothing here is closed with
``additionalProperties``, so a payload the schema did not define would validate
by default; the refusals are what prove these two are defined.

Both readings go through the same door. An acceptance is
``validate_artifact(...).ok``, which is the schema the artifact's own
identifier resolves to *and* the structural checks a schema of this kind
cannot reach; a refusal is read off that reader's schema-layer findings, at
the field each one names. The examples therefore carry ids in namespaces this
preview has not reserved, a null ``column`` on each payload node and null
dtype and shape metadata beside it, and every structural check holds for them
as section 17 describes them.

The examples are hand-built for the same reason the annex's is: no producer
writes either kind, so there is nothing to export. Every ``sha256:`` digest in
them is a well-formed placeholder rather than a digest taken under the byte
grammar of section 12.1, and nothing here asserts a digest's value.

``state_graph_example.json`` is a three-state disability cohort -- ``active``,
``disabled``, ``dead`` -- with four transitions: incidence and recovery
between the two living states, and a mortality intensity out of each of them.
Three states admit six ordered pairs and only four transitions, because
``dead`` is absorbing: an outgoing edge from it would be a resurrection, and
the topology rule every multi-state product obeys is that at least one state
is terminal. The intensities are annual, which is what ``time_axis`` records
alongside the length of a period, and ``basis`` names the columns the
intensities were fitted on -- the reader's answer to whether two policies
share a set of transition rates.

``nested_valuation_example.json`` is a guarantee reserve struck by an inner
stochastic model: the outer artifact carries the inner graph's fingerprint,
the interface across the boundary, and the context the inner values mean
something under. The context is key and value rather than a fixed field list,
so a producer that later carries the seed and the generator beside the measure
and the path count adds them without a schema change -- which is the whole
point of writing the seat before there is anything to sit in it.

An example artifact is only evidence while it looks like something a producer
would write. The transition intensities of the multistate example are table
lookups, and a lookup is one operation this producer already emits, so the
attributes those calls carry are not a matter of taste: they are read off a
live export here rather than invented, and a table's identity travels on the
call as ``table_fingerprint`` -- which is what makes a rate auditable back to
the basis it came from.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.rollforward import compile_rollforward

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_GOLDENS = Path(__file__).parent / "goldens"

# Where the specification reserves the two sections, so that the document and
# the fixtures standing as its evidence can be read against each other rather
# than trusted to agree.
_SPECIFICATION = (
    Path(__file__).resolve().parents[4] / "spec" / "graph-artifact" / "v0-preview.md"
)

# Long enough for the rollforward below to run, short enough to stay out of
# the way: nothing here projects anything, it reads what was recorded of one.
_PERIODS = 6

# Where each payload sits in its own example, so a test naming a broken field
# names the path a reader would follow to it. Both examples open on arriving
# columns, and the first of them is where a payload that claims no kind is put
# to see the document refuse it.
_STATE_GRAPH_NODE = 5
_NESTED_NODE = 3
_ARRIVING_NODE = 0


def _load(name: str) -> dict[str, Any]:
    """Return the example artifact ``name`` from the goldens directory."""
    artifact: dict[str, Any] = json.loads((_GOLDENS / name).read_text("utf-8"))
    return artifact


def _rejections(artifact: dict[str, Any]) -> list[list[str | int]]:
    """Return the path of every field the artifact reader's schema layer refuses.

    What each parametrised case below asserts is *which field is wrong*, and
    that is unchanged by where the reading comes from: these paths are what
    they were when the published schema was read directly. The reader reports
    a schema refusal at an RFC 6901 JSON pointer, so each pointer is walked
    back against the document it came from -- an array index arriving as an
    integer and an object key as a string, decided by what is actually there
    rather than by whether a segment looks like a number.
    """
    return [
        _path_into(artifact, finding.where)
        for finding in validate_artifact(artifact).findings
        if finding.section == "schema"
    ]


def _path_into(document: dict[str, Any], pointer: str) -> list[str | int]:
    """Return the steps ``pointer`` takes through ``document``.

    ``"envelope"`` is the artifact as a whole, which is no steps at all.
    """
    if pointer == "envelope":
        return []
    steps: list[str | int] = []
    here: Any = document
    for segment in pointer.split("/")[1:]:
        key = segment.replace("~1", "/").replace("~0", "~")
        if isinstance(here, list):
            entries: list[Any] = here
            index = int(key)
            steps.append(index)
            here = entries[index] if index < len(entries) else None
        else:
            mapping: dict[str, Any] = here if isinstance(here, dict) else {}
            steps.append(key)
            here = mapping.get(key)
    return steps


def _a_model_reaching_every_kind_the_producer_emits() -> ActuarialFrame:
    """Return a model carrying an input, a calculation, and a state machine.

    The state machine is what makes the model worth exporting here: a compiled
    rollforward is the nearest thing this producer writes to a state graph, so
    a model carrying one is where a leaked ``state_graph`` node would show up.
    """
    frame = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "fund_return": [[0.01] * _PERIODS],
            "me_charge": [[0.001] * _PERIODS],
        }
    )
    frame = frame.projection.set(
        start_date=datetime.date(2025, 1, 31),
        n_periods=_PERIODS,
        frequency="monthly",
    )
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    (
        builder["fund_value"]
        .grow(frame["fund_return"], label="fund_return")
        .charge(frame["me_charge"], label="me_charge")
    )
    frame.account_value = compile_rollforward(builder).expr_for("fund_value")
    return frame


def _the_attributes_the_producer_writes_on_one_lookup() -> tuple[str, ...]:
    """Return the attribute names a real ``Table.lookup()`` is exported with.

    Read off a live export rather than named here, so that the example
    artifacts below are held to what this producer writes and not to what a
    hand-built fixture happened to make up. One bare lookup is the case that
    matters: it lowers to a core ``call``, and the call is where the table's
    identity rides.
    """
    table = Table(
        name="reserved_sections_probe_mortality",
        source=pl.DataFrame(
            {"attained_age": [45, 46, 47], "mu": [0.0011, 0.0013, 0.0015]}
        ),
        dimensions={"attained_age": "attained_age"},
        value="mu",
    )
    frame = ActuarialFrame({"attained_age": [45, 46]})
    frame.mortality_rate = table.lookup(attained_age=frame.attained_age)
    artifact: dict[str, Any] = json.loads(
        GraphExporter(frame).export(profile="executable")
    )
    (node,) = [n for n in artifact["nodes"] if n["column"] == "mortality_rate"]

    assert node["expr"]["op"] == "call"
    assert node["expr"]["name"] == "lookup"
    return tuple(node["expr"]["attrs"])


def _every_lookup(tree: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield every ``lookup`` call written anywhere inside an operation tree."""
    if tree.get("op") == "call" and tree.get("name") == "lookup":
        yield tree
    for value in tree.values():
        if isinstance(value, dict) and "op" in value:
            yield from _every_lookup(value)
        elif isinstance(value, list):
            for member in value:
                if isinstance(member, dict) and "op" in member:
                    yield from _every_lookup(member)


def _the_intensities_lookups(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every lookup the multistate example's transition rates make."""
    (node,) = [n for n in artifact["nodes"] if n["kind"] == "state_graph"]
    return [
        lookup
        for transition in node["state_graph"]["transitions"]
        for lookup in _every_lookup(transition["intensity"])
    ]


# --- the multistate section --------------------------------------------------


def test_a_hand_built_multistate_artifact_is_accepted() -> None:
    """The format holds a state graph today, without a change tomorrow."""
    assert validate_artifact(_load("state_graph_example.json")).ok


def test_the_multistate_payload_holds_a_transition_intensity_as_a_tree() -> None:
    """An intensity is an operation tree, not a rendering of one.

    A transition rate written as text would be a sentence a second
    implementation cannot evaluate, and the whole reason the section exists is
    that the rate between two states is a calculation like any other.
    """
    artifact = _load("state_graph_example.json")
    (node,) = [n for n in artifact["nodes"] if n["kind"] == "state_graph"]
    transition = node["state_graph"]["transitions"][0]

    assert transition["from"] == "active"
    assert transition["to"] == "disabled"
    assert transition["intensity"]["op"] in {"col", "call", "binop"}


def test_the_multistate_payload_names_its_axis_and_the_basis_it_was_fitted_on() -> None:
    """Two rates and a period length are three different numbers.

    With a constant intensity an annual rate and a monthly one give the same
    answer, so a payload that left the basis of the rate unsaid would carry a
    valuation error no test of it could find.
    """
    artifact = _load("state_graph_example.json")
    (node,) = [n for n in artifact["nodes"] if n["kind"] == "state_graph"]
    payload = node["state_graph"]

    assert payload["states"] == ["active", "disabled", "dead"]
    assert payload["time_axis"]["intensity_basis"] == "annual"
    assert payload["time_axis"]["frequency"] == "monthly"
    assert payload["basis"] == ["issue_age", "sex", "occ_class"]


_TIME_AXIS = ["nodes", _STATE_GRAPH_NODE, "state_graph", "time_axis"]


def _on_a_step_axis(**axis: object) -> dict[str, Any]:
    """Return the multi-state example with its time axis replaced by ``axis``."""
    artifact = _load("state_graph_example.json")
    artifact["nodes"][_STATE_GRAPH_NODE]["state_graph"]["time_axis"] = {
        "periods": None,
        "intensity_basis": "annual",
        **axis,
    }
    return artifact


@pytest.mark.parametrize(
    "step", [{"step_years": 0.1}, {"steps_per_year": 12}], ids=lambda s: next(iter(s))
)
def test_a_product_on_a_fixed_step_axis_names_its_step(step: dict[str, object]) -> None:
    """A teaching sheet's product steps 0.1 years, and the axis says so.

    11.1.1's fourth form has no calendar cadence, so the period an annual
    intensity is converted on is the step the model laid, written as it was
    declared, and ``frequency`` is null.
    """
    artifact = _on_a_step_axis(frequency=None, **step)
    assert not [path for path in _rejections(artifact) if path[:4] == _TIME_AXIS]


@pytest.mark.parametrize(
    "axis",
    [
        {"frequency": None},
        {"frequency": None, "step_years": 0.1, "steps_per_year": 10},
        {"frequency": "monthly", "steps_per_year": 12},
    ],
    ids=["no_period_at_all", "both_spellings_of_a_step", "a_cadence_and_a_step"],
)
def test_a_time_axis_states_its_period_one_way(axis: dict[str, object]) -> None:
    assert _TIME_AXIS in _rejections(_on_a_step_axis(**axis))


def test_the_multistate_payload_reaches_the_bases_its_intensities_read() -> None:
    """The join from a transition rate to the table it was looked up in."""
    artifact = _load("state_graph_example.json")
    (node,) = [n for n in artifact["nodes"] if n["kind"] == "state_graph"]
    named = {entry["name"] for entry in artifact["assumptions"]}

    assert node["reads_assumptions"]
    assert set(node["reads_assumptions"]) <= named


def test_the_examples_lookups_carry_the_attributes_a_real_lookup_carries() -> None:
    """A fixture that invents an encoding is evidence of nothing.

    The point of standing an example beside a reserved section is that the
    payload can hold what a producer will one day write. An intensity whose
    lookup carried keys this producer never writes would be evidence about
    the fixture instead, so the key set is taken from a live export.
    """
    written = _the_attributes_the_producer_writes_on_one_lookup()
    lookups = _the_intensities_lookups(_load("state_graph_example.json"))

    assert "table_fingerprint" in written
    assert lookups
    for lookup in lookups:
        assert tuple(lookup["attrs"]) == written


def test_every_intensity_reaches_the_basis_it_was_looked_up_in_by_identity() -> None:
    """A rate is auditable when the table it came from is named and pinned.

    The name says which basis; the fingerprint says which version of it. A
    transition intensity carrying the name alone would leave a reviewer
    holding a rate that two quarters of the same table both answer to.
    """
    artifact = _load("state_graph_example.json")
    pinned = {entry["name"]: entry["fingerprint"] for entry in artifact["assumptions"]}

    for lookup in _the_intensities_lookups(artifact):
        attrs = lookup["attrs"]
        assert attrs["table"] in pinned
        assert attrs["table_fingerprint"] == pinned[attrs["table"]]


def test_every_state_a_transition_names_is_a_state_the_payload_declares() -> None:
    """A transition out of a state nothing declared is a graph with a hole."""
    artifact = _load("state_graph_example.json")
    (node,) = [n for n in artifact["nodes"] if n["kind"] == "state_graph"]
    payload = node["state_graph"]
    declared = set(payload["states"])

    for transition in payload["transitions"]:
        assert transition["from"] in declared
        assert transition["to"] in declared
    leaving = {transition["from"] for transition in payload["transitions"]}
    assert declared - leaving == {"dead"}


# --- the nested-valuation section --------------------------------------------


def test_a_hand_built_nested_valuation_artifact_is_accepted() -> None:
    """The format holds an inner valuation today, without a change tomorrow."""
    assert validate_artifact(_load("nested_valuation_example.json")).ok


def test_the_nested_payload_names_its_inner_interface_and_its_context() -> None:
    """State in, value out, and the measure the value was taken under."""
    artifact = _load("nested_valuation_example.json")
    (node,) = [n for n in artifact["nodes"] if n["kind"] == "nested_valuation"]
    payload = node["nested_valuation"]

    assert payload["interface"]["outputs"] == ["present_value_of_guarantee"]
    assert payload["context"]["measure"] == "risk_neutral"
    assert payload["context"]["paths"] == 1000
    assert payload["graph_fingerprint"].startswith("sha256:")


def test_the_nested_context_carries_what_a_later_producer_would_add() -> None:
    """Key and value, so randomness reaches the record without a schema change.

    An inner valuation is a Monte Carlo answer, and a Monte Carlo answer that
    does not say what generated its paths cannot be reproduced. The context
    holds the seed and the generator the day a producer has them.
    """
    artifact = _load("nested_valuation_example.json")
    (node,) = [n for n in artifact["nodes"] if n["kind"] == "nested_valuation"]

    assert validate_artifact(artifact).ok
    assert node["nested_valuation"]["context"]["seed"] == 20260830
    assert node["nested_valuation"]["context"]["generator"] == "pcg64"


def test_every_column_the_inner_interface_takes_is_a_node_of_the_outer_graph() -> None:
    """The boundary joins: what goes in is something the outer model holds."""
    artifact = _load("nested_valuation_example.json")
    (node,) = [n for n in artifact["nodes"] if n["kind"] == "nested_valuation"]
    columns = {n["column"] for n in artifact["nodes"] if n["column"] is not None}

    assert set(node["nested_valuation"]["interface"]["inputs"]) <= columns
    assert node["reads"] == node["nested_valuation"]["interface"]["inputs"]


# --- what a wrong payload costs ----------------------------------------------


def _break_the_intensity(artifact: dict[str, Any]) -> None:
    """Write a transition rate as text rather than as an operation tree."""
    node = artifact["nodes"][_STATE_GRAPH_NODE]
    node["state_graph"]["transitions"][0]["intensity"] = "0.0041 * loading"


def _break_the_transition(artifact: dict[str, Any]) -> None:
    """Leave a transition without the state it goes to."""
    del artifact["nodes"][_STATE_GRAPH_NODE]["state_graph"]["transitions"][0]["to"]


def _break_the_state_graph_seat(artifact: dict[str, Any]) -> None:
    """Claim the kind and carry none of the payload it stands for."""
    del artifact["nodes"][_STATE_GRAPH_NODE]["state_graph"]


def _break_the_interface(artifact: dict[str, Any]) -> None:
    """Write one output rather than the run of them."""
    payload = artifact["nodes"][_NESTED_NODE]["nested_valuation"]
    payload["interface"]["outputs"] = "present_value_of_guarantee"


def _break_the_context(artifact: dict[str, Any]) -> None:
    """Nest a document where the context takes one value."""
    payload = artifact["nodes"][_NESTED_NODE]["nested_valuation"]
    payload["context"]["measure"] = {"name": "risk_neutral"}


def _break_the_nested_seat(artifact: dict[str, Any]) -> None:
    """Claim the kind and carry none of the payload it stands for."""
    del artifact["nodes"][_NESTED_NODE]["nested_valuation"]


def _empty_the_transitions(artifact: dict[str, Any]) -> None:
    """Declare a set of states and no move between any two of them."""
    artifact["nodes"][_STATE_GRAPH_NODE]["state_graph"]["transitions"] = []


def _put_the_state_graph_payload_on_an_arriving_column(
    artifact: dict[str, Any],
) -> None:
    """Carry the payload on a node whose account says it holds no product."""
    artifact["nodes"][_ARRIVING_NODE]["state_graph"] = artifact["nodes"][
        _STATE_GRAPH_NODE
    ]["state_graph"]


def _put_the_nested_payload_on_an_arriving_column(artifact: dict[str, Any]) -> None:
    """Carry the payload on a node whose account says it holds no inner model."""
    artifact["nodes"][_ARRIVING_NODE]["nested_valuation"] = artifact["nodes"][
        _NESTED_NODE
    ]["nested_valuation"]


@pytest.mark.parametrize(
    ("example", "damage", "field"),
    [
        pytest.param(
            "state_graph_example.json",
            _break_the_intensity,
            ["nodes", _STATE_GRAPH_NODE, "state_graph", "transitions", 0, "intensity"],
            id="an_intensity_rendered_as_text",
        ),
        pytest.param(
            "state_graph_example.json",
            _break_the_transition,
            ["nodes", _STATE_GRAPH_NODE, "state_graph", "transitions", 0],
            id="a_transition_going_nowhere",
        ),
        pytest.param(
            "state_graph_example.json",
            _break_the_state_graph_seat,
            ["nodes", _STATE_GRAPH_NODE],
            id="a_state_graph_kind_carrying_no_state_graph",
        ),
        pytest.param(
            "nested_valuation_example.json",
            _break_the_interface,
            ["nodes", _NESTED_NODE, "nested_valuation", "interface", "outputs"],
            id="one_output_written_as_a_name_not_a_run",
        ),
        pytest.param(
            "nested_valuation_example.json",
            _break_the_context,
            ["nodes", _NESTED_NODE, "nested_valuation", "context", "measure"],
            id="a_context_entry_holding_a_document",
        ),
        pytest.param(
            "nested_valuation_example.json",
            _break_the_nested_seat,
            ["nodes", _NESTED_NODE],
            id="a_nested_valuation_kind_carrying_no_nested_valuation",
        ),
        pytest.param(
            "state_graph_example.json",
            _empty_the_transitions,
            ["nodes", _STATE_GRAPH_NODE, "state_graph", "transitions"],
            id="states_with_no_move_between_any_two_of_them",
        ),
        pytest.param(
            "state_graph_example.json",
            _put_the_state_graph_payload_on_an_arriving_column,
            ["nodes", _ARRIVING_NODE],
            id="a_state_graph_payload_on_a_node_that_claims_no_product",
        ),
        pytest.param(
            "nested_valuation_example.json",
            _put_the_nested_payload_on_an_arriving_column,
            ["nodes", _ARRIVING_NODE],
            id="a_nested_valuation_payload_on_a_node_that_claims_no_inner_model",
        ),
    ],
)
def test_a_payload_the_section_defines_is_held_to_what_it_defines(
    example: str,
    damage: Callable[[dict[str, Any]], None],
    field: list[str | int],
) -> None:
    """Each break is refused at the field that was broken.

    Nothing in this schema is closed, so a payload it did not define would
    pass whatever was written into it. These are what say the two sections
    were defined rather than merely left room for.

    The last two run the binding the other way. A kind without its payload is
    the obvious break; a payload on a node whose kind does not claim it is the
    quiet one, because a consumer that reads ``kind`` to decide what a node
    holds would never look, and a product declared where nothing says a
    product was declared is worse than one declared badly.
    """
    artifact = _load(example)
    damage(artifact)

    assert field in _rejections(artifact)


# --- and nothing writes either one -------------------------------------------


def test_nothing_in_the_package_emits_either_kind_yet() -> None:
    """Stated as a test so the claim in the specification stays true."""
    frame = _a_model_reaching_every_kind_the_producer_emits()
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export())
    kinds = {node["kind"] for node in artifact["nodes"]}

    assert {"input", "computed", "rollforward", "state"} <= kinds
    assert not kinds & {"state_graph", "nested_valuation"}
    for node in artifact["nodes"]:
        assert "state_graph" not in node
        assert "nested_valuation" not in node


def test_the_specification_names_both_example_artifacts() -> None:
    """A reader of section 17 is pointed at the evidence, by its path."""
    specification = _SPECIFICATION.read_text("utf-8")
    reserved = specification.split("## 17. Reserved payload sections")[1]
    section = reserved.split("\n## ")[0]

    assert "state_graph_example.json" in section
    assert "nested_valuation_example.json" in section
