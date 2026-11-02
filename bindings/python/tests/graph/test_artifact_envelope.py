# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The envelope an exported calculation graph arrives in.

A bare list of nodes and edges says nothing about which model it came from,
which schema it conforms to, or whether a reader is holding the same model it
read last quarter. The envelope of ``spec/graph-artifact/v0-preview.md`` is
where all of that is stated, and these tests are what hold the export to it.

Every test names the claim the envelope makes rather than the value this
particular model happens to produce: what is asserted is that the field is
there and means what the specification says, not that a two-column term
model hashes to any given digest.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.artifact import build_artifact
from gaspatchio.frame.graph.facets import (
    PRODUCER_URI,
    SCHEMA_URL_TEMPLATE,
    FacetLedger,
    facet,
)
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.frame.graph.graph_models import GraphExportConfig, ModelIdentity

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# The envelope's own members, in the order section 7 tabulates them.
_ENVELOPE_MEMBERS = (
    "schema",
    "profile",
    "fingerprint_algorithm",
    "producer",
    "created_at",
    "model",
    "graph_fingerprint",
    # Beside the model's identity, the same fold with its data left out: the
    # figure that says whether any formula moved.
    "formulas_fingerprint",
    # Beside the model's identity, the book's: which data the model was
    # built over, by content, where the fingerprint says which model.
    "book",
    "facets_used",
    "facets_required",
    "nodes",
    "edges",
    "assumptions",
    "holes",
    "boundaries",
    # Beside the two above it, because it is the same thing they are: an
    # array of the envelope's own, with a subsection of section 7 to itself.
    "sources",
    "enrichment",
    # Beside the member it is the head of: the axis the values are read
    # along, and ``enrichment`` is its first entry with ``why`` left off.
    "policies",
    "facets",
    # Last, which is where the producer writes it and the only place it could
    # be: a seal is taken over a finished record.
    "document_digest",
)

# A validator reports a missing member against the object that should have
# carried it, so the field's own name is in the message rather than the path.
# This is what reads it back out, so that a refusal can be named by field.
_MISSING_MEMBER = re.compile(r"^'(?P<field>[^']+)' is a required property$")


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


def _exported_artifact_for_a_two_column_model() -> dict[str, Any]:
    """Return the exported artifact for that model, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(_two_column_model()).export())
    return artifact


def _three_policy_model() -> ActuarialFrame:
    """Return the same calculation over three policies, each one identifiable."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "Policy number": ["P1", "P2", "P3"],
                "sum_assured": [100_000.0, 250_000.0, 500_000.0],
                "mortality_rate": [0.001_23, 0.002_04, 0.003_11],
            }
        )
    )
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return frame


def _fields_the_schema_refuses(artifact: dict[str, Any]) -> dict[str, set[str]]:
    """Return, per envelope member, the exact set of fields the schema refuses.

    Named by field rather than by container, because the container is what
    every refusal has in common: an assertion that a refusal lies *somewhere*
    inside ``nodes`` passes just as happily with the node record corrupted as
    with it correct. Keyed by the envelope member the refusal lies inside, so
    an empty mapping is the statement that the artifact conforms.
    """
    import jsonschema

    from gaspatchio.schemas import load_schema

    validator = jsonschema.Draft202012Validator(load_schema())
    refused: dict[str, set[str]] = {}
    for error in validator.iter_errors(artifact):
        named = [step for step in error.absolute_path if isinstance(step, str)]
        missing = _MISSING_MEMBER.match(error.message)
        if missing is not None:
            field = missing["field"]
        else:
            field = named[-1] if len(named) > 1 else error.message
        refused.setdefault(named[0] if named else "", set()).add(field)
    return refused


# --- what the envelope says about itself ------------------------------------


def test_the_artifact_names_the_schema_it_conforms_to() -> None:
    """The identifier a consumer resolves, the profile claimed, the byte grammar."""
    artifact = _exported_artifact_for_a_two_column_model()

    assert artifact["schema"] == "gaspatchio-graph/v0-preview.3"
    assert artifact["profile"] == "audit"
    assert artifact["fingerprint_algorithm"] == "gspv0-preview-3"


def test_the_artifact_says_what_wrote_it_and_when() -> None:
    """A record with no producer and no timestamp is a record nobody can place."""
    artifact = _exported_artifact_for_a_two_column_model()

    assert artifact["producer"]["name"] == "gaspatchio"
    assert artifact["producer"]["version"] == version("gaspatchio")
    datetime.fromisoformat(artifact["created_at"])  # raises if it is not RFC 3339
    assert artifact["created_at"].endswith("Z")


def test_every_envelope_section_is_present_even_when_empty() -> None:
    """Required means present: an empty section is a claim, not a missing value."""
    artifact = _exported_artifact_for_a_two_column_model()

    for section in ("nodes", "edges", "assumptions", "holes", "boundaries"):
        assert section in artifact, section
    assert artifact["facets"] == {}
    assert artifact["facets_used"] == ["gaspatchio_column_transformation"]
    assert artifact["facets_required"] == []


def test_the_envelope_carries_exactly_the_members_the_specification_defines() -> None:
    """Twenty-one members, in the order a reader meets them in section 7."""
    artifact = _exported_artifact_for_a_two_column_model()

    assert tuple(artifact) == _ENVELOPE_MEMBERS


def test_the_whole_model_has_one_identity_a_reader_can_compare() -> None:
    """One string standing for the model, so "nothing changed" can be checked."""
    artifact = _exported_artifact_for_a_two_column_model()

    assert artifact["graph_fingerprint"].startswith("sha256:")
    assert (
        artifact["graph_fingerprint"]
        == (_exported_artifact_for_a_two_column_model()["graph_fingerprint"])
    )


def test_the_envelope_validates_against_the_published_schema() -> None:
    """The schema refuses nothing this producer writes, and an empty set says so.

    An empty mapping rather than a bare "it validates": this guard is keyed
    by field name so that anything the export writes that stops meaning what
    the schema says it means arrives here as a name nobody expected, instead
    of hiding behind "somewhere inside nodes".

    Nothing is a tolerated absence any more. The edge record, the
    materialization ordinal and the execution tier were each named here in
    turn while the field behind them was still being written, and each name
    left the set on the change that filled it rather than being kept as an
    exception.
    """
    refused = _fields_the_schema_refuses(_exported_artifact_for_a_two_column_model())

    assert refused == {}


def test_a_node_field_that_stopped_meaning_what_it_says_is_caught() -> None:
    """The guard above bites: a corrupted field arrives as its own name.

    ``kind`` is the account the node gives of its column, and it is drawn
    from a closed vocabulary. A value outside it is the shape of regression
    this envelope's only conformance test has to catch, so the catching is
    asserted rather than assumed.
    """
    artifact = _exported_artifact_for_a_two_column_model()
    artifact["nodes"][0]["kind"] = "banana"

    refused = _fields_the_schema_refuses(artifact)

    assert refused == {"nodes": {"kind"}}


# --- what the envelope says about the model ---------------------------------


def test_the_artifact_says_which_model_it_is_an_account_of(tmp_path: Path) -> None:
    """Where the model was read from, and what the policy data was.

    A block stated by hand names its source by a path relative to a root the
    export cannot know, so the export is told that root: it is where every
    node's location is written against too.
    """
    identity = ModelIdentity(
        label="term-assurance",
        source_path="models/term_assurance.py",
        source_sha="sha256:" + "a" * 64,
        git={"commit": "4f1c9a02d0d7c7a4a5f0f1b6c2d3e4f5a6b7c8d9", "dirty": False},
        model_points={
            "path": "data/term_assurance.parquet",
            "fingerprint": "sha256:" + "b" * 64,
        },
    )

    artifact = build_artifact(
        fold(_two_column_model()),
        config=GraphExportConfig(model=identity),
        source_root=tmp_path,
    )

    assert artifact["model"]["label"] == "term-assurance"
    assert artifact["model"]["source_path"] == "models/term_assurance.py"
    assert artifact["model"]["git"]["dirty"] is False
    assert artifact["model"]["model_points"]["path"] == "data/term_assurance.parquet"


def test_a_model_run_that_named_nothing_says_so_rather_than_inventing_it() -> None:
    """Every member of the version block may be null, and null is the honest answer."""
    artifact = _exported_artifact_for_a_two_column_model()

    assert set(artifact["model"]) == {
        "label",
        "source_path",
        "source_sha",
        "git",
        "model_points",
    }
    assert all(value is None for value in artifact["model"].values())


def test_the_wire_node_is_flat_and_names_the_account_it_gives() -> None:
    """``kind`` is the account of the column; ``provenance`` is where it came from."""
    artifact = _exported_artifact_for_a_two_column_model()
    nodes = {node["id"]: node for node in artifact["nodes"]}

    assert nodes["sum_assured"]["kind"] == "input"
    assert nodes["death_claims@1"]["kind"] == "computed"
    assert nodes["death_claims@1"]["provenance"] == "assignment"
    assert nodes["death_claims@1"]["column"] == "death_claims"
    assert nodes["death_claims@1"]["reads"] == ["sum_assured", "mortality_rate"]
    assert nodes["sum_assured"]["formula"] is None
    assert nodes["death_claims@1"]["formula"] is not None
    assert "data" not in nodes["death_claims@1"]
    assert "label" not in nodes["death_claims@1"]


def test_every_node_carries_the_two_identities_a_change_report_is_read_from() -> None:
    """What this node computes, and what it computes together with everything above."""
    artifact = _exported_artifact_for_a_two_column_model()

    for node in artifact["nodes"]:
        assert node["local_fingerprint"].startswith("sha256:"), node["id"]
        assert node["fingerprint"].startswith("sha256:"), node["id"]


def test_an_artifact_carrying_no_values_says_so_rather_than_leaving_it_open() -> None:
    """A value sample means nothing without the context it was taken under."""
    artifact = _exported_artifact_for_a_two_column_model()

    assert artifact["enrichment"] is None


def test_a_node_in_an_artifact_with_no_values_carries_no_place_for_one() -> None:
    """Absent and null are different claims, so the unasked question is not answered.

    ``enrichment: null`` says this artifact carries no value samples. A node
    saying "the value sample is null" beside it would be answering a question
    the envelope has already closed, and a reader would be right to read it
    as a sample that was looked for and not found.
    """
    artifact = _exported_artifact_for_a_two_column_model()

    assert artifact["enrichment"] is None
    for node in artifact["nodes"]:
        assert "value_sample" not in node, node["id"]
        assert "trace" not in node, node["id"]


def test_values_read_from_the_frame_travel_with_the_context_they_mean_under() -> None:
    """One evaluation context for the whole artifact, stated once."""
    frame = _two_column_model()

    artifact = json.loads(
        GraphExporter(frame).export(
            frame.collect(), GraphExportConfig(include_traces=False)
        )
    )

    assert artifact["enrichment"] == {
        "policy_id": None,
        "aggregation": None,
        "periods": None,
        "filter": None,
    }


def test_the_context_names_the_policy_the_samples_were_actually_read_from() -> None:
    """A sample nobody asked a policy for is still one policy's, and it says which.

    Nothing was passed to pick a policy, so the samples are the first row's
    -- three policies in the frame, one of them in the artifact. Saying null
    there would say the values were not taken from one policy, which is the
    one thing that is never true of them.
    """
    frame = _three_policy_model()

    artifact = json.loads(
        GraphExporter(frame).export(
            frame.collect(), GraphExportConfig(include_traces=False)
        )
    )

    assert artifact["enrichment"]["policy_id"] == "P1"


def test_the_context_states_the_filter_the_samples_were_read_under() -> None:
    """A filtered sample is a different number, so the filter travels with it.

    The frame is cut down before a value is read out of it, which moves both
    which rows survive and which policy is first among them. An artifact that
    carried the number without the cut would hand a reader a figure they
    could not reproduce from the model it names.
    """
    frame = _three_policy_model()

    artifact = json.loads(
        GraphExporter(frame).export(
            frame.collect(),
            GraphExportConfig(
                include_traces=False, filter_expr="col('sum_assured') > 200000"
            ),
        )
    )

    assert artifact["enrichment"]["filter"] == "col('sum_assured') > 200000"
    assert artifact["enrichment"]["policy_id"] == "P2"


def test_a_policy_asked_for_and_not_in_the_frame_is_refused_not_stood_in_for() -> None:
    """The context names one policy, so the values have to be that policy's.

    Reading the first row instead would hand a reader one policy's numbers
    under another policy's name, checkable against nothing and wrong in a way
    no field of the artifact records. The refusal is the loud lookup miss the
    framework already uses when a policy is asked for and is not there.
    """
    frame = _three_policy_model()

    with pytest.raises(ValueError, match="P9") as raised:
        GraphExporter(frame).export(
            frame.collect(),
            GraphExportConfig(include_traces=False, policy_id="P9"),
        )

    message = str(raised.value)
    assert "Policy number" in message
    assert "P1" in message


def _a_book_whose_policy_numbers_are_text() -> ActuarialFrame:
    """Return a model whose ids are digits held in a column of strings.

    The shape a model-point file arrives in more often than not: the policy
    number reads as a number and is stored as text, because it has leading
    zeros somewhere in the book or because that is what the extract wrote.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "Policy number": ["1", "2", "3"],
                "sum_assured": [100_000.0, 250_000.0, 500_000.0],
                "mortality_rate": [0.001_23, 0.002_04, 0.003_11],
            }
        )
    )
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return frame


def _a_book_whose_policy_numbers_are_whole_numbers() -> ActuarialFrame:
    """Return the same model with the ids held as integers."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "Policy number": [1, 2, 3],
                "sum_assured": [100_000.0, 250_000.0, 500_000.0],
                "mortality_rate": [0.001_23, 0.002_04, 0.003_11],
            }
        )
    )
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return frame


def _pinned(frame: ActuarialFrame, policy_id: str) -> dict[str, Any]:
    """Return the artifact one model exports with its samples pinned to a policy."""
    return json.loads(  # type: ignore[no-any-return]
        GraphExporter(frame).export(
            frame.collect(), GraphExportConfig(policy_id=policy_id)
        )
    )


def test_a_policy_number_held_as_text_is_matched_as_the_text_it_is() -> None:
    """A numeric id against a column of strings had no values reach the file.

    The id was coerced to an integer before the match, and an integer put
    against a column of strings is a comparison the engine refuses to make.
    The refusal arrived one column at a time, was caught as "no sample for
    this column", and the document came out with no values, no traces and no
    enrichment context -- while the policy asked for was sitting in the file.
    """
    artifact = _pinned(_a_book_whose_policy_numbers_are_text(), "2")

    nodes = {node["id"]: node for node in artifact["nodes"]}
    assert artifact["enrichment"]["policy_id"] == "2"
    assert nodes["death_claims@1"]["value_sample"] == pytest.approx(510.0)
    assert nodes["death_claims@1"]["trace"]


def test_a_policy_number_held_as_a_whole_number_is_matched_as_one() -> None:
    """UNCHANGED, deliberately: an integer column reads the id as an integer."""
    artifact = _pinned(_a_book_whose_policy_numbers_are_whole_numbers(), "2")

    nodes = {node["id"]: node for node in artifact["nodes"]}
    assert artifact["enrichment"]["policy_id"] == "2"
    assert nodes["death_claims@1"]["value_sample"] == pytest.approx(510.0)


@pytest.mark.parametrize(
    "model",
    [
        _a_book_whose_policy_numbers_are_text,
        _a_book_whose_policy_numbers_are_whole_numbers,
    ],
)
def test_an_id_the_file_does_not_carry_is_refused_whichever_type_it_holds(
    model: Callable[[], ActuarialFrame],
) -> None:
    """A pin that cannot be honoured says so, rather than emptying the document.

    A document with every sample absent reads as a model that computed
    nothing. What happened is that one thing the caller asked for was not
    there, and that is what the reader has to be told.
    """
    with pytest.raises(ValueError, match="9") as raised:
        _pinned(model(), "9")

    assert "Policy number" in str(raised.value)


def test_a_profile_the_format_does_not_define_is_refused_rather_than_stamped() -> None:
    """Two profiles, and the field is what a consumer decides how to read by.

    Stamping a third name would put the whole document behind a word no
    consumer has a reading for, which is worse than refusing to write it:
    the fields would all be there and nothing would say which of them a
    reader was entitled to expect. What the two are is in the refusal, so
    the caller is told the answer rather than only told they are wrong.
    """
    with pytest.raises(ValueError, match="not a conformance profile") as raised:
        build_artifact(fold(_two_column_model()), profile="ledger")

    message = str(raised.value)
    assert "'audit'" in message
    assert "'executable'" in message


# --- facets -----------------------------------------------------------------


def test_an_unknown_facet_survives_a_round_trip() -> None:
    """A consumer that cannot read a facet must still hand it on unchanged."""
    artifact = _exported_artifact_for_a_two_column_model()
    artifact["facets"]["acme_review_state"] = {
        "_producer": "https://acme.example/lineage",
        "_schemaURL": "https://acme.example/schemas/review_state.json",
        "signed_off_by": "chief actuary",
    }

    assert (
        json.loads(json.dumps(artifact))["facets"]["acme_review_state"]["signed_off_by"]
        == "chief actuary"
    )


def test_a_facet_is_recorded_in_used_and_only_in_required_when_it_changes_meaning() -> (
    None
):
    """Announced either way; required only when the artifact needs it to be read."""
    ledger = FacetLedger(used=set(), required=set())

    ledger.record("gaspatchio_lowered")
    ledger.record("gaspatchio_rollforward_ir", required=True)
    used, required = ledger.as_lists()

    assert used == ["gaspatchio_lowered", "gaspatchio_rollforward_ir"]
    assert required == ["gaspatchio_rollforward_ir"]


def test_a_required_facet_is_still_one_a_consumer_is_told_it_will_meet() -> None:
    """Required is a subset of used, however the two were recorded."""
    ledger = FacetLedger(used=set(), required=set())

    ledger.record("gaspatchio_rollforward_ir", required=True)
    ledger.record("gaspatchio_rollforward_ir")
    used, required = ledger.as_lists()

    assert used == ["gaspatchio_rollforward_ir"]
    assert required == ["gaspatchio_rollforward_ir"]


def test_a_facet_carries_who_produced_it_and_which_schema_reads_it() -> None:
    """Two opaque identifiers a validator must not fetch, on every facet."""
    wrapped = facet("gaspatchio_lowered", {"engine": "polars", "text": "col(x) * 2"})

    assert wrapped["_producer"] == PRODUCER_URI
    assert wrapped["_schemaURL"] == SCHEMA_URL_TEMPLATE.format(
        name="gaspatchio_lowered"
    )
    assert wrapped["engine"] == "polars"


def test_a_payload_that_stamps_its_own_producer_is_refused() -> None:
    """Restamping another producer's facet would put our name on their record."""
    with pytest.raises(ValueError, match="_producer"):
        facet("acme_review_state", {"_producer": "https://acme.example/lineage"})
