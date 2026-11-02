# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The profile that carries the calculation itself, not only the account of it.

The audit profile states what every column is, what it read, and what the
identity of each of those things is. A reader holding it can follow the model
and cannot run it: ``formula`` is the sentence the author typed, and a sentence
is not something a second implementation evaluates.

The executable profile is where that gap closes. Every node with an operation
tree carries it, in the encoding ``op_json.py`` writes, so a consumer parses
the tree, hashes what it parsed, and reaches the ``local_fingerprint`` the same
node already carries. That is the difference between a file that asks to be
trusted and one that checks itself (*No vendor lock-in, by construction*).

The layer is marked unstable in the file itself, and these tests hold the
warning to being in every place a consumer might read it rather than only in
the specification a consumer might not have.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter, fold, local_fingerprint
from gaspatchio.frame.graph.artifact import (
    PROFILE_AUDIT,
    PROFILE_EXECUTABLE,
    _expr_of,
    _tier_of,
)
from gaspatchio.frame.graph.op_json import op_node_from_json
from gaspatchio.rollforward import compile_rollforward
from gaspatchio.schemas import load_schema

if TYPE_CHECKING:
    from collections.abc import Iterator

# Where the specification states the warning, so that the document and the
# two things a consumer actually holds -- the schema and this producer's own
# docstring -- can be read against each other rather than trusted to agree.
_SPECIFICATION = (
    Path(__file__).resolve().parents[4] / "spec" / "graph-artifact" / "v0-preview.md"
)

# The two profiles, as the exporter's own parameter spells them. Named here
# rather than imported from the producer's constants so that a helper below
# can be annotated with the pair a caller may actually pass.
_Profile = Literal["audit", "executable"]

# Long enough for one anniversary, short enough to stay out of the way:
# nothing here runs a projection, it reads what was recorded of one.
_PERIODS = 12

# The seven node types the byte grammar of section 12.1 tags, which are the
# seven the schema enumerates and the seven this encoding writes.
_NODE_SHAPES = ("col", "lit", "binop", "call", "when_then", "state", "engine_native")


def _two_column_model() -> ActuarialFrame:
    """Return a model with two arriving columns and one calculation over them."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return frame


def _a_model_covering_every_node_type() -> ActuarialFrame:
    """Return a model whose trees between them reach all seven node types.

    A column reference and a literal in the first arithmetic, a conditional
    over a comparison, a sequence literal, an accessor call carrying a typed
    offset, a fragment in one engine's own expression language, and a
    compiled rollforward -- whose own read of its running balance is the
    state reference, the one node type no formula written by hand produces.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0, 500_000.0],
                "av_init": [10_000.0, 20_000.0, 30_000.0],
                "credited_rate": [[0.003] * _PERIODS] * 3,
            }
        )
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 31),
        n_periods=_PERIODS,
        frequency="monthly",
    )
    frame.death_claims = frame.sum_assured * 0.001_23
    frame.ceded_claims = (
        when(frame.sum_assured > 200_000.0).then(frame.death_claims).otherwise(0.0)
    )
    frame.select_loaded_claims = frame.death_claims * [1.5, 1.25, 1.0]
    frame.prior_period_claims = frame.select_loaded_claims.projection.at_period(-1)
    frame.running_total = pl.col("sum_assured").cum_sum()
    builder = frame.projection.rollforward(states={"account_value": frame["av_init"]})
    builder["account_value"].grow(frame["credited_rate"], label="interest")
    frame.fund = compile_rollforward(builder).expr_for("account_value")
    return frame


def _artifact(frame: ActuarialFrame, *, profile: _Profile = "audit") -> dict[str, Any]:
    """Return ``frame``'s exported artifact, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export(profile=profile))
    return artifact


def _artifact_for_a_two_column_model(*, profile: _Profile = "audit") -> dict[str, Any]:
    """Return the artifact for two arriving columns and one calculation over them."""
    return _artifact(_two_column_model(), profile=profile)


def _artifact_for_a_model_covering_every_node_type(
    *, profile: _Profile = "audit"
) -> dict[str, Any]:
    """Return the artifact for the model that reaches all seven node types."""
    return _artifact(_a_model_covering_every_node_type(), profile=profile)


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found: list[dict[str, Any]] = [
        node for node in artifact["nodes"] if node["id"] == node_id
    ]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def _every_subtree(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield ``payload`` and every operation tree written inside it."""
    yield payload
    for value in payload.values():
        if isinstance(value, dict) and "op" in value:
            yield from _every_subtree(value)
        elif isinstance(value, list):
            for member in value:
                if isinstance(member, dict) and "op" in member:
                    yield from _every_subtree(member)


def _unwrapped(text: str) -> str:
    """Return ``text`` with every run of whitespace collapsed to one space.

    The same words are wrapped three different ways -- a markdown paragraph,
    an indented docstring, one long JSON string -- so a comparison that kept
    the line breaks would be comparing the wrapping rather than the warning.
    """
    return " ".join(text.split())


def _the_unstable_warning() -> str:
    """Return the two sentences the schema states after its UNSTABLE. marker."""
    described = load_schema()["$defs"]["expr"]["description"]
    first, second, *_ = described.removeprefix("UNSTABLE.").strip().split(". ")
    return f"{first}. {second}."


def _schema_refusals(artifact: dict[str, Any]) -> list[str]:
    """Return the message of every validation error the published schema raises."""
    import jsonschema

    validator = jsonschema.Draft202012Validator(load_schema())
    return [
        f"{list(error.absolute_path)}: {error.message}"
        for error in validator.iter_errors(artifact)
    ]


# --- which profile carries what ---------------------------------------------


def test_the_default_export_carries_no_operation_tree() -> None:
    """What a reviewer reads is the account; the trees are asked for."""
    artifact = _artifact_for_a_two_column_model()

    assert artifact["profile"] == "audit"
    assert all("expr" not in node for node in artifact["nodes"])


def test_the_executable_export_carries_one_tree_per_computed_node() -> None:
    """The formula as the format spells it, beside the formula as it was typed."""
    artifact = _artifact_for_a_two_column_model(profile="executable")

    assert artifact["profile"] == "executable"
    assert _node(artifact, "death_claims@1")["expr"] == {
        "op": "binop",
        "kind": "mul",
        "left": {"op": "col", "name": "sum_assured"},
        "right": {"op": "col", "name": "mortality_rate"},
    }


def test_a_leaf_carries_no_tree_because_nothing_derives_it() -> None:
    """A column that arrived was not computed, so there is no tree to write."""
    artifact = _artifact_for_a_two_column_model(profile="executable")

    assert "expr" not in _node(artifact, "sum_assured")


def test_an_executable_artifact_is_also_a_conforming_audit_artifact() -> None:
    """Section 3: a consumer reading only the audit fields reads it correctly.

    Three members are set aside, and each is one by which two records of one
    calculation honestly differ. The timestamp is when each was written. The
    profile is what each one claims. And the seal is over the whole of each
    document -- these two differ in every tree the ``executable`` profile
    carries -- so two documents carry two seals.

    That third one is a format fact and not a test's convenience: an
    ``audit`` view derived from an ``executable`` document cannot carry the
    executable document's seal, because it is not that document. Section
    13.1's fourth limit says what a holder deriving one does about the
    member, and the first assertion pins that the two do differ, so setting
    it aside cannot quietly become setting aside a member that never moved.
    """
    audit = _artifact_for_a_two_column_model()
    executable = _artifact_for_a_two_column_model(profile="executable")

    assert audit["document_digest"] != executable["document_digest"]

    for artifact in (audit, executable):
        del artifact["created_at"]
        del artifact["profile"]
        del artifact["document_digest"]
    for node in executable["nodes"]:
        node.pop("expr", None)

    assert executable == audit


def test_the_published_schema_accepts_what_the_executable_profile_writes() -> None:
    """Every tree in the file, against the definition the schema publishes."""
    artifact = _artifact_for_a_model_covering_every_node_type(profile="executable")

    assert _schema_refusals(artifact) == []


# --- a tree that should be there and is not ---------------------------------


def test_a_node_that_computes_and_lost_its_tree_is_refused_by_both_fields() -> None:
    """The tier and the tree are read off one thing, so they refuse together.

    A fold that lost a tree is not a node with nothing to say. The tier
    would call it a leaf -- nothing to account for -- and the ``expr``
    would leave the calculation out of the file, and between them a reader
    would be told the column arrived with the data. Which of the two is
    asked for first decides nothing, which is the point: the absence is one
    absence and both name it.
    """
    graph = fold(_two_column_model())
    node = graph.nodes["death_claims@1"]
    del graph.op_trees["death_claims@1"]

    with pytest.raises(ValueError, match="no operation tree behind it"):
        _tier_of(graph, node)
    with pytest.raises(ValueError, match="no operation tree behind it"):
        _expr_of(graph, node, profile=PROFILE_EXECUTABLE)


def test_a_leaf_that_never_had_a_tree_is_not_refused_for_lacking_one() -> None:
    """The refusal is about a lost tree, not about every node without one."""
    graph = fold(_two_column_model())
    node = graph.nodes["sum_assured"]

    assert _tier_of(graph, node) is None
    assert _expr_of(graph, node, profile=PROFILE_EXECUTABLE) is None
    assert _expr_of(graph, node, profile=PROFILE_AUDIT) is None


# --- the file checks itself -------------------------------------------------


def test_every_tree_in_the_file_reproduces_the_node_s_own_stamp() -> None:
    """The executable profile is what makes an artifact self-authenticating."""
    artifact = _artifact_for_a_model_covering_every_node_type(profile="executable")

    stamped = 0
    for node in artifact["nodes"]:
        if "expr" not in node:
            continue
        rebuilt = op_node_from_json(node["expr"])
        assert f"sha256:{local_fingerprint(rebuilt).hex()}" == node["local_fingerprint"]
        stamped += 1

    assert stamped


def test_a_date_the_frame_verb_offset_authenticates_itself() -> None:
    """The bar a node has to clear before its tier means anything.

    ``af.date.add_duration("entry_date", "12mo")`` is a line an actuary
    writes and an operation the format's own vocabulary names, so the file
    owes a reader the tree rather than an assurance about it: parse what is
    written, hash what was parsed, reach the stamp the node already carries.
    A node whose tree said one thing and whose digest was taken over another
    would read ``core`` and still be unrunnable.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {"entry_date": [datetime.date(2026, 1, 1), datetime.date(2026, 6, 1)]}
        )
    )
    frame.date.add_duration("entry_date", "12mo", new_col_name="anniversary")
    node = _node(_artifact(frame, profile="executable"), "anniversary@1")

    rebuilt = op_node_from_json(node["expr"])

    assert node["tier"] == "core"
    assert f"sha256:{local_fingerprint(rebuilt).hex()}" == node["local_fingerprint"]


def test_a_present_value_the_frame_verb_built_authenticates_itself() -> None:
    """The same bar, at the accessor that discounts rather than dates.

    ``af.finance.present_value("cashflow", "rate", "period")`` is a
    reserving line, and ``finance.present_value`` is an identifier the
    format's vocabulary lists, so what the file owes a reader is the tree:
    parse what is written, hash what was parsed, reach the stamp the node
    already carries. A discounted cashflow reading ``core`` off a tree its
    own digest was not taken over would be the one claim in this format a
    valuation reader cannot afford to have to check by hand.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "cashflow": [1_000.0, 2_000.0],
                "rate": [0.05, 0.04],
                "period": [1, 2],
            }
        )
    )
    frame.pv = frame.finance.present_value("cashflow", "rate", "period")
    node = _node(_artifact(frame, profile="executable"), "pv@1")

    rebuilt = op_node_from_json(node["expr"])

    assert node["tier"] == "core"
    assert f"sha256:{local_fingerprint(rebuilt).hex()}" == node["local_fingerprint"]


def test_a_duration_held_at_its_tables_last_row_authenticates_itself() -> None:
    """The same bar, at an operation an actuary reaches by an engine method name.

    ``af.duration.clip(0, 14)`` is the line a select table's last row makes
    necessary, and ``clip`` is an identifier the format's vocabulary lists,
    so what the file owes a reader is the tree: parse what is written, hash
    what was parsed, reach the stamp the node already carries. The bounds
    are in that tree and therefore in that stamp, which is what makes a cap
    that moved from 14 to 24 between two quarters a change the identity can
    see.
    """
    frame = ActuarialFrame(pl.DataFrame({"duration": [3, 20, 40]}))
    frame.duration_capped = frame.duration.clip(0, 14)
    node = _node(_artifact(frame, profile="executable"), "duration_capped@1")

    rebuilt = op_node_from_json(node["expr"])

    assert node["tier"] == "core"
    assert f"sha256:{local_fingerprint(rebuilt).hex()}" == node["local_fingerprint"]


def test_an_age_band_authenticates_itself_with_its_breakpoints_in_the_stamp() -> None:
    """The same bar, at the operation whose identity is the values written into it.

    A band is its breakpoints and its labels; an engine's rendering of them
    abbreviates the middle away, so the tree holds them as sequence
    literals. What the file then owes a reader is the round trip: parse
    what is written, hash what was parsed, reach the stamp the node already
    carries -- which is what makes a band whose middle breakpoint moved a
    change the identity can see.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [35, 45, 55]}))
    frame.is_young = frame.age.cut([40.0, 50.0], labels=["young", "mid", "old"]) == (
        "young"
    )
    node = _node(_artifact(frame, profile="executable"), "is_young@1")

    rebuilt = op_node_from_json(node["expr"])

    assert node["tier"] == "core"
    assert f"sha256:{local_fingerprint(rebuilt).hex()}" == node["local_fingerprint"]


def test_a_parsed_entry_date_authenticates_itself_with_its_format() -> None:
    """The same bar, at the line most projections open with.

    ``af.entry_date.str.to_date("%Y/%m/%d")`` turns an administration
    system's text into dates, and the format is the whole of what makes one
    parse different from another. The round trip is what makes that
    claim checkable: parse what is written, hash what was parsed, reach the
    stamp the node already carries -- with the format inside it, so two
    models reading the same column under different formats can no longer be
    one document.
    """
    frame = ActuarialFrame(pl.DataFrame({"entry_date": ["2024/01/15", "2024/02/15"]}))
    frame.entry_date_parsed = frame.entry_date.str.to_date("%Y/%m/%d")
    node = _node(_artifact(frame, profile="executable"), "entry_date_parsed@1")

    rebuilt = op_node_from_json(node["expr"])

    assert node["tier"] == "core"
    assert f"sha256:{local_fingerprint(rebuilt).hex()}" == node["local_fingerprint"]


def test_the_trees_between_them_reach_every_node_type_the_format_tags() -> None:
    """A round-trip over six of the seven would prove the seventh nothing."""
    artifact = _artifact_for_a_model_covering_every_node_type(profile="executable")

    written = {
        subtree["op"]
        for node in artifact["nodes"]
        if "expr" in node
        for subtree in _every_subtree(node["expr"])
    }

    assert written == set(_NODE_SHAPES)


# --- what the schema says the layer is --------------------------------------


def test_the_schema_says_the_layer_is_unstable() -> None:
    """A consumer holding the schema is told before it depends on anything."""
    schema = load_schema()

    assert schema["$defs"]["expr"]["description"].startswith("UNSTABLE.")


def test_the_schema_defines_all_seven_shapes_rather_than_only_naming_them() -> None:
    """A definition that stopped at the tag would validate a tree of nothing."""
    schema = load_schema()

    shapes = schema["$defs"]["expr"]["oneOf"]

    assert [shape["properties"]["op"]["const"] for shape in shapes] == list(
        _NODE_SHAPES
    )
    assert schema["$defs"]["expr"]["properties"]["op"]["enum"] == list(_NODE_SHAPES)
    assert all("required" in shape for shape in shapes)


@pytest.mark.parametrize(
    "tree",
    [
        pytest.param({"op": "col"}, id="a_column_reference_naming_no_column"),
        pytest.param(
            {"op": "binop", "kind": "mul", "left": {"op": "col", "name": "a"}},
            id="a_binary_operation_with_one_operand",
        ),
        pytest.param(
            {"op": "lit", "value": 1, "values": [1]}, id="a_literal_in_both_forms"
        ),
        pytest.param({"op": "lit"}, id="a_literal_naming_no_value"),
        pytest.param(
            {
                "op": "binop",
                "kind": "nand",
                "left": {"op": "col", "name": "a"},
                "right": {"op": "col", "name": "b"},
            },
            id="an_operator_outside_the_closed_vocabulary",
        ),
        pytest.param({"op": "matrix", "name": "x"}, id="an_eighth_node_type"),
        pytest.param(
            {"op": "engine_native", "text": "x"}, id="a_fragment_naming_no_engine"
        ),
    ],
)
def test_the_schema_refuses_a_tree_the_decoder_would_refuse(
    tree: dict[str, Any],
) -> None:
    """The document and the decoder draw the same line, so neither is the only guard."""
    artifact = _artifact_for_a_two_column_model(profile="executable")
    _node(artifact, "death_claims@1")["expr"] = tree

    assert _schema_refusals(artifact)


def test_the_same_warning_stands_in_the_schema_the_document_and_the_producer() -> None:
    """A consumer holds one of the three, so the words have to be in all of them.

    Read out of the schema rather than restated here: a consumer that fetched
    the schema and nothing else has to be told, and a warning that lived only
    in a document nobody downloaded would be a warning nobody read.
    """
    warning = _the_unstable_warning()

    assert "another engine runs the model from" in warning
    assert warning in _unwrapped(_SPECIFICATION.read_text("utf-8"))
    assert GraphExporter.export.__doc__ is not None
    assert warning in _unwrapped(GraphExporter.export.__doc__)
