# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What one node of an exported artifact says, and what it no longer says.

A node is one account of one column, and the format names the fields that
account is made of. These tests hold the export to that record: the fields
it must carry, the fields it must not, and the claims an absent field is
allowed to stand for.
"""

from __future__ import annotations

import datetime
import json
from copy import deepcopy
from inspect import currentframe
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple, get_args

import jsonschema
import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.calculations import RecordOrigin
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.artifact import (
    document_digest_of,
    refusal_for_a_number_json_cannot_hold,
)
from gaspatchio.frame.graph.graph_models import GraphNode, Provenance
from gaspatchio.rollforward import compile_rollforward
from gaspatchio.schemas import load_schema

if TYPE_CHECKING:
    from collections.abc import Callable

# The node record's fields in the order the format tabulates them. Every
# field the format defines for a node of this shape is here, and every one
# of them is written.
_NODE_FIELDS = (
    "id",
    "column",
    "version",
    "kind",
    "dtype",
    "shape",
    "provenance",
    "formula",
    "reads",
    "reads_assumptions",
    "engines",
    "tier",
    "local_fingerprint",
    "fingerprint",
    "in_final_schema",
    "materialized_at",
    "source_location",
    "facets",
)


def _artifact(frame: ActuarialFrame) -> dict[str, Any]:
    """Return ``frame``'s exported artifact, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export())
    return artifact


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def _artifact_for_a_two_column_model() -> dict[str, Any]:
    """Return the artifact for two arriving columns and one calculation over them."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return _artifact(frame)


def _artifact_for_a_model_that_redefines_policies_in_force() -> dict[str, Any]:
    """Return the artifact for a model that writes one column twice.

    The second write is what the frame ends up holding; the first is the
    history that makes a change report possible at all.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "initial_policies": [1_000.0, 2_500.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    frame.policies_in_force = frame.initial_policies - 1.0
    frame.policies_in_force = frame.policies_in_force * (1.0 - frame.mortality_rate)
    return _artifact(frame)


def _artifact_for_a_renaming_model() -> dict[str, Any]:
    """Return the artifact for a model that renames a vendor field, then uses it."""
    frame = ActuarialFrame(
        pl.DataFrame({"Issue Age": [30, 45], "sum_assured": [100_000.0, 250_000.0]})
    )
    frame = frame.rename({"Issue Age": "issue_age"})
    frame.death_claims = frame.sum_assured * 0.001_23
    return _artifact(frame)


def _artifact_for_a_model_using_a_multi_column_call() -> dict[str, Any]:
    """Return the artifact for a model that defines two columns in one call."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "annual_premium": [450.0, 1_200.0],
                "sum_assured": [100_000.0, 250_000.0],
            }
        )
    )
    frame = frame.with_columns(
        (pl.col("annual_premium") * 0.05).alias("expenses"),
        (pl.col("sum_assured") * 0.001_23).alias("death_claims"),
    )
    return _artifact(frame)


def _artifact_for_a_model_joining_expense_parameters() -> dict[str, Any]:
    """Return the artifact for a model whose expense rate arrives by join."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "product_code": ["TERM", "TERM"],
                "annual_premium": [450.0, 1_200.0],
            }
        )
    )
    frame = frame.join(
        pl.DataFrame({"product_code": ["TERM"], "expense_rate": [0.05]}),
        on="product_code",
    )
    frame.expenses = frame.annual_premium * frame.expense_rate
    return _artifact(frame)


def _artifact_for_a_model_with_a_projection_timeline() -> dict[str, Any]:
    """Return the artifact for a model that stamps a projection timeline."""
    frame = ActuarialFrame(
        pl.DataFrame({"issue_age": [30, 45], "sum_assured": [100_000.0, 250_000.0]})
    )
    frame = frame.projection.set(
        valuation_date=datetime.date(2026, 1, 1),
        until="term_years",
        until_value=2,
        frequency="annual",
    )
    frame.attained_age = frame.issue_age + frame.month // 12
    return _artifact(frame)


def _artifact_for_a_model_deriving_a_date() -> dict[str, Any]:
    """Return the artifact for a model that derives an anniversary date."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "issue_date": [datetime.date(2026, 1, 1), datetime.date(2026, 6, 1)],
                "sum_assured": [100_000.0, 250_000.0],
            }
        )
    )
    frame.death_claims = frame.sum_assured * 0.001_23
    frame.date.add_duration(frame.issue_date, "1y", new_col_name="first_anniversary")
    return _artifact(frame)


def _artifact_for_a_model_reading_a_compiled_rollforward() -> dict[str, Any]:
    """Return the artifact for a model whose fund comes from a compiled rollforward."""
    return _artifact(_a_model_reading_a_compiled_rollforward())


def _a_model_reading_a_compiled_rollforward() -> ActuarialFrame:
    """Return a model whose fund value comes out of a compiled rollforward.

    Held apart from the export above so that the same model can be asked
    for both profiles: what the compilation's node may say about itself
    is a question the ``executable`` profile answers differently.
    """
    frame = ActuarialFrame(
        {"opening_balance": [100.0], "growth_rate": [0.05], "term_months": [3]}
    )
    frame = frame.projection.set(
        valuation_date=datetime.date(2026, 1, 31),
        until="term_months",
        until_value="term_months",
        frequency="monthly",
        per_policy=True,
    )
    builder = frame.projection.rollforward(states={"account": frame["opening_balance"]})
    builder["account"].grow(frame["growth_rate"])
    frame.account_value = compile_rollforward(builder).expr_for("account")
    return frame


def _artifact_for_a_model_injecting_simulated_deaths() -> dict[str, Any]:
    """Return the artifact for a model handed a whole column of values at a line."""
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))
    frame.simulated_deaths = pl.Series("simulated_deaths", [0, 1, 0])
    return _artifact(frame)


def _artifact_for_a_model_reaching_into_an_engine() -> dict[str, Any]:
    """Return the artifact for a model carrying one engine's own expression text."""
    frame = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    frame.running_total = pl.col("sum_assured").cum_sum()
    return _artifact(frame)


def _artifact_for_a_model_with_a_column_nothing_accounts_for() -> dict[str, Any]:
    """Return the artifact for a model holding a column no recording door saw."""
    frame = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    frame.death_claims = frame.sum_assured * 0.001_23
    frame._df = frame._df.with_columns(  # noqa: SLF001 — writing the plan past every recording door is what mints a hole
        (pl.col("sum_assured") * 0.02).alias("lapse_reserve")
    )
    return _artifact(frame)


# --- which definition of the column this is ---------------------------------


def test_a_definition_says_which_definition_it_is() -> None:
    """Two writes of one name are two nodes, and each says which write it was."""
    artifact = _artifact_for_a_model_that_redefines_policies_in_force()

    versions = {node["id"]: node["version"] for node in artifact["nodes"]}

    assert versions["policies_in_force@1"] == 1
    assert versions["policies_in_force@2"] == 2


def test_a_column_nothing_defined_carries_no_version() -> None:
    """An arriving column has no ordinal to give, and says null rather than one."""
    artifact = _artifact_for_a_two_column_model()

    arriving = _node(artifact, "sum_assured")

    assert arriving["version"] is None
    assert arriving["kind"] == "input"


def test_a_column_nothing_accounts_for_carries_no_version_either() -> None:
    """Nothing defined a hole, so the field that says which definition is null."""
    artifact = _artifact_for_a_model_with_a_column_nothing_accounts_for()

    unexplained = _node(artifact, "lapse_reserve")

    assert unexplained["kind"] == "hole"
    assert unexplained["version"] is None


# --- where the values came from, or which door defined them -----------------


def test_the_node_says_which_door_its_definition_came_through() -> None:
    """A rename and an assignment are different acts, and the record says which."""
    artifact = _artifact_for_a_renaming_model()

    assert _node(artifact, "issue_age@1")["provenance"] == "rename"
    assert _node(artifact, "death_claims@1")["provenance"] == "assignment"


def test_an_arriving_column_says_where_it_arrived_from() -> None:
    """One field, one question: a leaf answers it with the data it came out of.

    The record used to answer this twice -- once for a column that
    arrived and once for a column the frame defined -- with each
    definition writing null into the other's field. Between them the two
    were near-disjoint, and the null was the answer far more often than
    not; one field asking one question is what the pair was for.
    """
    artifact = _artifact_for_a_two_column_model()

    assert _node(artifact, "sum_assured")["provenance"] == "model_points"


def test_a_column_nothing_accounts_for_has_no_provenance_at_all() -> None:
    """A hole's whole account of itself is that it has none, and null says so."""
    artifact = _artifact_for_a_model_with_a_column_nothing_accounts_for()

    unexplained = _node(artifact, "lapse_reserve")

    assert unexplained["kind"] == "hole"
    assert unexplained["provenance"] is None


@pytest.mark.parametrize(
    ("build", "node_id", "door"),
    [
        (_artifact_for_a_two_column_model, "death_claims@1", "assignment"),
        (_artifact_for_a_model_using_a_multi_column_call, "expenses@1", "batch"),
        (_artifact_for_a_renaming_model, "issue_age@1", "rename"),
        (_artifact_for_a_model_joining_expense_parameters, "expense_rate@1", "join"),
        (_artifact_for_a_model_with_a_projection_timeline, "month@1", "projection"),
        (_artifact_for_a_model_deriving_a_date, "first_anniversary@1", "date"),
    ],
    ids=["assignment", "batch", "rename", "join", "projection", "date"],
)
def test_every_door_the_producer_records_reaches_the_wire_under_its_own_name(
    build: Callable[[], dict[str, Any]], node_id: str, door: str
) -> None:
    """Each way a column can get onto a frame arrives as the door it came through.

    One model per door, because the doors are not variations on one call:
    a batch, a join, a timeline configuration and a date derivation each
    reach the log by their own route, and a sweep that exercised only the
    two easiest to write would leave the other four to be taken on trust.

    The doors survive the merge as first-class provenance values: nothing
    is translated on the way to the wire, because the two vocabularies
    were built to meet.
    """
    assert _node(build(), node_id)["provenance"] == door


def test_the_door_the_format_reserves_for_a_rollforward_is_the_compilations_own() -> (
    None
):
    """The compilation wears it; the line that reads a state back out does not.

    The format defines a ``rollforward`` door for a compiled rollforward's
    own within-period bookkeeping, and the node standing for the whole
    compilation is what comes through it: nothing in the model's source
    writes that node, which is exactly what makes its door neither an
    assignment nor any of the others. What the author actually wrote is
    the line extracting one state, and that is a plain assignment and
    recorded as one -- so the two doors have to stay apart on the wire as
    well as in the vocabulary.
    """
    artifact = _artifact_for_a_model_reading_a_compiled_rollforward()

    (compilation,) = [n for n in artifact["nodes"] if n["kind"] == "rollforward"]

    assert compilation["provenance"] == "rollforward"
    assert _node(artifact, "account_value@1")["provenance"] == "assignment"


def test_the_provenances_the_producer_records_are_the_ones_the_format_names() -> None:
    """One vocabulary, written down twice, and the two are checked against each other.

    The producer's own list and the published schema's enum have to be the
    same set, and until now that agreement lived only in prose. A value
    added to one and not the other is an artifact the schema rejects, or a
    value the schema allows that nothing can produce.

    The producer's list is a union of two the fold still keeps apart: the
    recording doors, which come off a calculation record, and the places a
    column's values arrive from. Eleven between them, none dropped by the
    merge, and the union is checked here rather than the enum alone --
    otherwise the enum could grow a member the recorder can never reach.
    """
    published = load_schema()["$defs"]["node"]["properties"]["provenance"]["enum"]
    arrivals = {"model_points", "assumptions", "injected"}

    assert {value.value for value in Provenance} == set(published) - {None}
    assert set(get_args(RecordOrigin)) | arrivals == {
        value.value for value in Provenance
    }


# --- what the record stops carrying -----------------------------------------


def test_the_node_record_stops_carrying_a_display_label() -> None:
    """A label built from engine text is engine text under another name."""
    artifact = _artifact_for_a_two_column_model()

    assert all("label" not in node for node in artifact["nodes"])
    assert "label" not in GraphNode.model_fields


def test_the_node_record_carries_one_dependency_list_not_two() -> None:
    """Two parallel accounts of what a node read are two accounts that can disagree."""
    artifact = _artifact_for_a_two_column_model()

    assert all("dependencies" not in node for node in artifact["nodes"])
    assert _node(artifact, "death_claims@1")["reads"] == [
        "sum_assured",
        "mortality_rate",
    ]


def test_the_node_record_carries_no_period_reference() -> None:
    """Timing is read off a node's own structure, so no field restates it.

    The one node whose timing genuinely cannot be read is the one carrying
    an engine's own expression text -- and what that node says about itself
    is which engine it needs, which is a field the format defines.
    """
    artifact = _artifact_for_a_model_reaching_into_an_engine()

    assert all("period_reference" not in node for node in artifact["nodes"])
    assert _node(artifact, "running_total@1")["engines"] == ["polars"]


# --- what an absent field is allowed to claim -------------------------------


def test_a_leaf_makes_no_engine_claim_because_it_has_no_formula_to_make_one_about() -> (
    None
):
    """An empty engines array is a claim, and a leaf has no tree to claim it of.

    A column that arrived and a column nothing accounts for both have no
    formula. Writing "this node is engine-free" against either would be
    answering a question that was never asked of it; leaving the field out
    says nothing, which is the truth.
    """
    arriving = _artifact_for_a_two_column_model()
    unexplained = _artifact_for_a_model_with_a_column_nothing_accounts_for()

    assert "engines" not in _node(arriving, "sum_assured")
    assert "engines" not in _node(unexplained, "lapse_reserve")
    assert _node(arriving, "death_claims@1")["engines"] == []


def test_an_injected_input_makes_no_engine_claim_either() -> None:
    """It is data at a known line, not a formula, whatever door recorded it."""
    artifact = _artifact_for_a_model_injecting_simulated_deaths()

    assert "engines" not in _node(artifact, "simulated_deaths@1")


# --- the shapes of node the format defines ----------------------------------


def test_a_column_of_values_handed_over_at_a_line_is_an_input_that_says_so() -> None:
    """Located data: a source rather than a derivation, and the line it arrived at."""
    artifact = _artifact_for_a_model_injecting_simulated_deaths()

    injected = _node(artifact, "simulated_deaths@1")

    assert injected["kind"] == "input"
    assert injected["provenance"] == "injected"
    assert injected["formula"] is None
    assert injected["source_location"] is not None


def test_whether_a_node_is_the_answer_or_its_history_is_a_named_field() -> None:
    """The superseded definition is history, and says so rather than implying it."""
    artifact = _artifact_for_a_model_that_redefines_policies_in_force()

    assert _node(artifact, "policies_in_force@1")["in_final_schema"] is False
    assert _node(artifact, "policies_in_force@2")["in_final_schema"] is True


def test_the_node_record_states_its_fields_in_the_order_the_format_tabulates_them() -> (
    None
):
    """A reader meeting the record in the format's own order reads it once, in order."""
    artifact = _artifact_for_a_two_column_model()

    computed = _node(artifact, "death_claims@1")

    assert tuple(computed) == _NODE_FIELDS
    assert tuple(_node(artifact, "sum_assured")) == tuple(
        field for field in _NODE_FIELDS if field != "engines"
    )


# --- the states the merged field no longer lets a producer write ------------

# A field a mutation removes rather than nulls. An absent field and a null
# are different claims, and half the rules below turn on which of the two a
# record makes.
_ABSENT: Final = object()


def _refused_at(artifact: dict[str, Any]) -> set[str]:
    """Return a JSON pointer for everything the published schema refuses.

    A pointer rather than a message, because what these tests pin is
    *which* claim was refused. A mutation that makes a node illegal in two
    ways at once -- a reserved kind without its payload, say -- would
    otherwise pass a test that only asked whether something was wrong.
    """
    validator = jsonschema.Draft202012Validator(load_schema())
    return {
        "/".join(str(step) for step in error.absolute_path)
        for error in validator.iter_errors(artifact)
    }


def _saying(artifact: dict[str, Any], node_id: str, **claims: Any) -> dict[str, Any]:
    """Return ``artifact`` with one node's fields overwritten by ``claims``.

    A field given ``_ABSENT`` is removed rather than nulled: an absent
    field and a null are different claims, and half the rules below turn
    on which of the two a record makes.
    """
    document = deepcopy(artifact)
    (node,) = [n for n in document["nodes"] if n["id"] == node_id]
    for field, claim in claims.items():
        if claim is _ABSENT:
            node.pop(field, None)
        else:
            node[field] = claim
    return document


@pytest.mark.parametrize(
    ("kind", "provenance", "contradicts"),
    [
        ("computed", "model_points", "a column both derived and arrived"),
        ("hole", "assumptions", "a hole whose values came from an assumption base"),
        ("input", "rename", "an arriving column that came through a rename door"),
        ("state", "join", "a running state that arrived from the side of a join"),
        ("input", None, "an input whose account of where it came from is silence"),
        ("rollforward", "assignment", "a state machine that a plain assignment wrote"),
        ("state_graph", "model_points", "declared states claiming to be policy data"),
    ],
    ids=[
        "computed-arrived",
        "hole-with-a-source",
        "input-through-a-door",
        "state-from-a-join",
        "input-saying-nothing",
        "rollforward-assigned",
        "state_graph-arrived",
    ],
)
def test_a_state_the_old_pair_allowed_is_refused_by_the_merged_field(
    kind: str, provenance: str | None, contradicts: str
) -> None:
    """Each of these validated under the two fields, and each contradicted the prose.

    The old shape admitted 252 ``(kind, source, origin)`` triples and ten
    occurred. The seven below are the ones that are not merely unused but
    *wrong* -- each contradicts something section 8, 16 or 17 states in
    words -- and under one field bound to ``kind`` each is refused rather
    than described.
    """
    artifact = _artifact_for_a_two_column_model()
    where = [node["id"] for node in artifact["nodes"]].index("death_claims@1")

    mutated = _saying(artifact, "death_claims@1", kind=kind, provenance=provenance)

    assert f"nodes/{where}/provenance" in _refused_at(mutated), contradicts


def test_every_provenance_the_producer_writes_is_one_its_kind_admits() -> None:
    """The constraint has to admit the producer's own output, or it is a bug.

    Bound to ``kind`` in both directions, a rule is only as good as the
    pairs it lets through, and a rule refusing a record this producer
    writes would be found by whichever model first wrote one rather than
    here.
    """
    artifacts = (
        _artifact_for_a_two_column_model(),
        _artifact_for_a_renaming_model(),
        _artifact_for_a_model_using_a_multi_column_call(),
        _artifact_for_a_model_joining_expense_parameters(),
        _artifact_for_a_model_with_a_projection_timeline(),
        _artifact_for_a_model_deriving_a_date(),
        _artifact_for_a_model_injecting_simulated_deaths(),
        _artifact_for_a_model_with_a_column_nothing_accounts_for(),
        _artifact_for_a_model_reading_a_compiled_rollforward(),
    )

    written = {
        (node["kind"], node["provenance"])
        for artifact in artifacts
        for node in artifact["nodes"]
    }

    assert all(_refused_at(artifact) == set() for artifact in artifacts)
    assert ("rollforward", "rollforward") in written
    assert ("state", None) in written
    assert ("hole", None) in written
    assert ("input", "injected") in written


# --- what a node may claim about its tier and the engines beside it ---------


@pytest.mark.parametrize(
    ("tier", "engines", "legal", "why"),
    [
        ("core", [], True, "engine-free, and says so -- what every core node writes"),
        ("core", ["polars"], False, "naming an engine contradicts the core claim"),
        (
            "engine_native",
            ["polars"],
            True,
            "the tier and the list agree -- what every engine-native node writes",
        ),
        (
            "engine_native",
            [],
            False,
            "a positive engine-free claim beside an engine-native tier",
        ),
        (
            "opaque",
            ["polars"],
            True,
            "a tree holding an engine fragment and an unclassifiable identifier",
        ),
        (
            "opaque",
            [],
            True,
            "a producer that walked the tree and found no declared fragment",
        ),
        (None, [], True, "true of a leaf, and useless: nothing in no tree reaches one"),
        (None, ["polars"], False, "a leaf naming the engines its absent text needs"),
    ],
    ids=[
        "core-empty",
        "core-named",
        "native-named",
        "native-empty",
        "opaque-named",
        "opaque-empty",
        "null-empty",
        "null-named",
    ],
)
def test_what_a_tier_and_an_engines_list_may_say_about_each_other(
    tier: str | None, engines: list[str], *, legal: bool, why: str
) -> None:
    """Eight of the twelve states, and the schema now agrees with section 8.3.

    ``tier`` has four values and ``engines`` three states -- absent,
    present and empty, present and non-empty -- so there are twelve. The
    four with ``engines`` absent are the profile's question and are below;
    these eight turn on nothing but the record itself, and every one of
    them validated before this rule landed.

    ``opaque`` with an engine named is the row worth stating twice. A tier
    is the weakest thing reached anywhere in a tree, so a tree holding
    both a Polars fragment and an identifier nothing can classify is
    opaque and still has a true engine to name. A rule reading "engines
    non-empty implies engine_native" would leave that producer three moves
    and all three bad, and the record is true.
    """
    artifact = _artifact_for_a_two_column_model()
    where = [node["id"] for node in artifact["nodes"]].index("death_claims@1")

    mutated = _saying(artifact, "death_claims@1", tier=tier, engines=engines)

    refused = _refused_at(mutated)
    assert (f"nodes/{where}/tier" not in refused) is legal, why


def test_a_third_party_exporter_may_still_state_a_tier_and_no_engines() -> None:
    """The ``audit`` profile is what the optional field was written for.

    Section 8.3 makes ``engines`` optional so that an exporter which
    cannot see which engines a fragment needs can leave it out and say
    nothing, rather than emit an empty array and say something false. An
    ``audit`` artifact stating a tier and no engines is exactly that
    exporter, and both hand-built examples this package publishes carry
    such a record.
    """
    artifact = _artifact_for_a_two_column_model()

    mutated = _saying(artifact, "death_claims@1", engines=_ABSENT)

    assert mutated["profile"] == "audit"
    assert _refused_at(mutated) == set()


def test_where_the_tree_is_in_the_file_the_engines_claim_is_required() -> None:
    """In ``executable`` the list is a walk of a document the producer holds.

    A core node holds no engine fragment by the definition of its tier, so
    the empty array is true of it; an engine-native node holds at least
    one, and section 12.1 requires each fragment to name its engine, so
    the list is read off the tree rather than discovered. Where the
    evidence is in the file, the claim is required.
    """
    frame = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    frame.death_claims = frame.sum_assured * 0.001_23
    artifact = json.loads(GraphExporter(frame).export(profile="executable"))
    where = [node["id"] for node in artifact["nodes"]].index("death_claims@1")

    silent = _saying(artifact, "death_claims@1", engines=_ABSENT)

    assert _refused_at(artifact) == set()
    assert f"nodes/{where}" in _refused_at(silent)


def test_a_compilation_states_a_tier_over_a_tree_that_is_not_its_recipe() -> None:
    """And the ``executable`` requirement does not reach it, which is deliberate.

    A compiled rollforward's tree is the single call ``rollforward``
    carrying the compilation's own identity -- section 11.2 says the tier
    it earns is a statement about the vocabulary and not about the
    payload. So a walk of that tree reaches nothing the state machine's
    own expressions reach, and the only claim the profile rule could force
    out of the node is the empty array section 8.3 declines to require: a
    positive statement of engine-freedom about a machine this file does
    not carry.

    Stated as a test because the producer writes such a record today, and
    a rule reading "any core tier carries engines" refuses it.
    """
    artifact = _artifact_for_a_model_reading_a_compiled_rollforward()
    executable = json.loads(
        GraphExporter(_a_model_reading_a_compiled_rollforward()).export(
            profile="executable"
        )
    )

    (compilation,) = [n for n in executable["nodes"] if n["kind"] == "rollforward"]

    assert compilation["tier"] == "core"
    assert "engines" not in compilation
    assert _refused_at(executable) == set()
    assert _refused_at(artifact) == set()


# --- what the column holds, read off the type rather than restated ----------


def test_the_record_no_longer_restates_the_type_as_a_second_field() -> None:
    """``value_kind`` was a function of ``dtype`` on every record ever written.

    Its whole rule was three tests and a default: null gives unknown,
    ``bool`` or ``list[bool]`` gives a selection, everything else gives a
    quantity. Two fields free to disagree is what a document whose claim
    is that it can be checked must not carry, and a restatement is not a
    facet either: a facet is for something the format does not define, and
    this is something it defines twice.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"sum_assured": [100_000.0, 250_000.0], "smoker": [True, False]})
    )
    frame.death_claims = frame.sum_assured * 0.001_23
    artifact = _artifact(frame)

    assert all("value_kind" not in node for node in artifact["nodes"])
    assert _node(artifact, "smoker")["dtype"] == "bool"
    assert _node(artifact, "sum_assured")["dtype"] == "f64"


def test_a_bare_comparison_is_why_the_type_vocabulary_carries_the_caveat() -> None:
    """A selection can arrive as a numeric mask, and no field could tell you.

    ``af.plain_bool = af.sum_assured > 1.5`` produces a column the finished
    frame holds as ``Float64``: a 0/1 mask that is a selection to a reader
    and a quantity to the type vocabulary. The removed field said ``value``
    of it, so nothing was lost -- but a reader who takes ``bool`` to mean
    selection and infers ``f64`` to mean quantity is wrong about every bare
    comparison this framework writes, which is why section 10 states the
    second half of the rule rather than leaving it to be inferred.
    """
    frame = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    frame.plain_bool = frame.sum_assured > 1.5

    artifact = _artifact(frame)

    assert _node(artifact, "plain_bool@1")["dtype"] == "f64"
    assert frame.collect().schema["plain_bool"] == pl.Float64


def test_folding_the_field_away_moves_no_digest_on_a_leaf() -> None:
    """A leaf's ``dtype`` *is* in its canonical bytes, and it did not move.

    This is the one field of the five where the question is real. The
    canonical bytes of a leaf are its tag, its name and its ``dtype``
    (section 12.1), so a fold that had changed what ``dtype`` reports would
    have moved every leaf's ``local_fingerprint`` and the graph digest with
    it. What the fold changed is that the record stops carrying a second
    field derived from ``dtype`` -- the type itself is untouched, and the
    digest a leaf's bytes reach is checked here against the value section
    12.5 publishes for the corpus leaf of the same name and type.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"sum_assured": [100_000.0, 250_000.0, 500_000.0]})
    )
    frame.death_claims = frame.sum_assured * 0.001_23

    arriving = _node(_artifact(frame), "sum_assured")

    assert arriving["dtype"] == "f64"
    assert arriving["local_fingerprint"] == (
        "sha256:b643510e5bc2884efbc56ffc1b90fca82f7cc07abb692dd75abb3cf7d1f60b38"
    )


# --- where the model is written, and whose disk it was read off ---------------


class _LocatedModel(NamedTuple):
    """One model and the line its one calculation is written on.

    The line travels with the frame because that is what these assertions
    are about: a ``source_location`` nobody can point back at the statement
    that caused it is a location nobody can check.
    """

    frame: ActuarialFrame
    line: int


def _a_located_model() -> _LocatedModel:
    """Return a one-calculation model beside the line that calculation is on."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    line = currentframe().f_lineno + 1  # type: ignore[union-attr]
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return _LocatedModel(frame, line)


def test_a_source_location_is_written_against_its_checkout_when_no_root_is_named() -> (
    None
):
    """With no root named, the root is the checkout the model's file sits in.

    The default once named the file on the machine that ran the model, which
    section 7 rules out: no absolute path appears anywhere in the artifact.
    """
    model = _a_located_model()

    located = _node(_artifact(model.frame), "death_claims@1")["source_location"]

    assert located == (
        f"bindings/python/tests/graph/test_artifact_node_record.py:{model.line}"
    )


def test_a_named_root_is_taken_off_the_front_of_every_location() -> None:
    """What a published document wants: where in a repository, not whose disk.

    A reader comparing two runs of one model taken on two machines should be
    comparing the model, and an absolute path is the field that would differ
    without either calculation having moved.
    """
    model = _a_located_model()
    root = Path(__file__).resolve().parents[4]

    published = json.loads(GraphExporter(model.frame).export(source_root=root))

    located = _node(published, "death_claims@1")["source_location"]
    assert located == (
        f"bindings/python/tests/graph/test_artifact_node_record.py:{model.line}"
    )


def test_a_location_outside_the_named_root_is_written_with_dot_dot_segments() -> None:
    """A model reaching outside the tree is a fact, and ``..`` is how it is kept.

    Truncating it would be a path pointing where the calculation was not
    written; leaving it absolute would put the exporting machine's own
    layout back into a document whose whole root exists to keep it out. A
    reader holding the root resolves this one exactly as the run did.
    """
    model = _a_located_model()

    published = json.loads(
        GraphExporter(model.frame).export(source_root=Path(__file__).parent / "nowhere")
    )

    located = _node(published, "death_claims@1")["source_location"]
    assert located == f"../{Path(__file__).name}:{model.line}"


def test_the_rewrite_happens_under_the_seal_and_not_after_it() -> None:
    """The seal covers the location the document publishes, not the one it had.

    This is the whole reason the root is a producer setting rather than
    something a publishing script does to a written file: a document whose
    locations were rewritten after the export carries a digest over bytes
    nobody holds, and its own deep reading refuses it.
    """
    model = _a_located_model()
    root = Path(__file__).resolve().parents[4]

    published = json.loads(GraphExporter(model.frame).export(source_root=root))

    assert not published["nodes"][-1]["source_location"].startswith("/")
    assert published["document_digest"] == document_digest_of(published)
    assert validate_artifact(published, deep=True).ok


# --- a NaN and an infinity travel as section 10 spells them ------------------


_NON_FINITE_MODEL: Final[str] = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.ratio = af.numerator / af.denominator
    return af
"""


def _a_book_with_non_finite_ratios() -> ActuarialFrame:
    """Return two policies whose ratio is an infinity and a NaN."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1", "P2", "P3"],
                "numerator": [1.0, 0.0, -1.0],
                "denominator": [0.0, 0.0, 0.0],
            }
        )
    )
    af.ratio = af.numerator / af.denominator
    return af


def test_a_non_finite_sample_is_written_as_its_sentinel_not_as_null() -> None:
    """``"Infinity"``, never null: null means no value, and this is one.

    The one-policy document wrote an infinity as null -- the serialiser's
    quiet default -- which states that the column held nothing, beside a
    walk-through that ended at a number. Section 10 spells it as a string.
    """
    af = _a_book_with_non_finite_ratios()
    published = json.loads(GraphExporter(af).export(af.collect()))
    (ratio,) = [node for node in published["nodes"] if node["column"] == "ratio"]

    assert ratio["value_sample"] == "Infinity"
    assert ratio["trace"][-1]["result"] == "Infinity"
    assert validate_artifact(published, deep=True).ok


def test_every_policy_on_the_axis_writes_its_non_finite_sample(tmp_path: Path) -> None:
    """``--policies all`` over an infinity and a NaN writes, and conforms.

    The axis carried the floats raw and the seal refused the whole document
    with "Out of range float values are not JSON compliant: inf", naming no
    node and no policy. ``--scenarios`` folds take the same path.
    """
    model = tmp_path / "model.py"
    model.write_text(_NON_FINITE_MODEL)
    points = tmp_path / "points.parquet"
    _a_book_with_non_finite_ratios().collect().select(
        "policy_id", "numerator", "denominator"
    ).write_parquet(points)
    out = tmp_path / "graph.json"
    result = CliRunner().invoke(
        app,
        ["calc-graph", str(model), str(points), "-o", str(out), "--policies", "all"],
    )

    assert result.exit_code == 0, result.output
    published = json.loads(out.read_text())
    (ratio,) = [node for node in published["nodes"] if node["column"] == "ratio"]
    assert ratio["value_sample"] == ["Infinity", "NaN", "-Infinity"]
    assert validate_artifact(published, deep=True).ok


def test_a_number_left_unspelled_is_refused_naming_its_node_and_context() -> None:
    """Whatever path still misses one is named: node, field, position, scenario."""
    document = {
        "policies": [
            {"policy_id": None, "why": 'scenario_id "BASE", folded by sum'},
            {"policy_id": None, "why": 'scenario_id "MORT_UP", folded by sum'},
        ],
        "nodes": [
            {"id": "tp01@1", "value_sample": [[1.0], [2.0]]},
            {"id": "tp02@1", "value_sample": [[1.0, 0.5], [0.5, float("inf")]]},
        ],
    }
    refused = refusal_for_a_number_json_cannot_hold(
        document, ValueError("Out of range float values are not JSON compliant: inf")
    )

    assert "'tp02@1'" in str(refused)
    assert "value_sample[1][1]" in str(refused)
    assert "MORT_UP" in str(refused)
