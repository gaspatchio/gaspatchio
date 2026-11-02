# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Whether the document is the file the producer wrote.

The fingerprint chain answers a different question, and answers it well: is
this the same calculation? An identity moves when the computation moves and
at no other time, which is why an as-written ``formula`` is no part of any
node's canonical bytes. The consequence is exact and was live -- a quotation
edited after export leaves every fingerprint valid, every propagation check
clean and every local-fingerprint recomputation clean, under both profiles --
and the second test below is that consequence, pinned rather than described,
so the reason the seal exists cannot quietly stop being true.

``document_digest`` is the other question, asked separately: a hash over the
document's own canonical serialization, this member excluded and everything
else -- ``created_at`` included, because it seals a written record rather than
an identity -- inside it.

**This is tamper-evidence and not tamper-proofing**, and the two tests that
say so sit beside each other. A tampered document is caught by its own seal.
A tampered document that is *re-sealed* is internally consistent and the
standalone file cannot catch it at all; what catches that one is a record
filed elsewhere naming the digest the original carried, and a filed change
report is such a record.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import (
    DOCUMENT_DIGEST_FIELD,
    SEAL_BY_DEFAULT,
    GraphExporter,
    diff_artifacts,
    document_digest_of,
    validate_artifact,
)

if TYPE_CHECKING:
    from gaspatchio.frame.graph import ValidationReport

# What a reader is told when the file is not the one that was sealed. The
# sentence is read back rather than the whole message, so that the wording can
# be improved without the test having to be rewritten, and so that a refusal
# arriving for some other reason cannot pass for this one.
_NOT_THE_PRODUCERS_FILE = "This is not the file the producer wrote"

# What a reader is told when there is no seal to check. Under
# `gaspatchio-graph/v0-preview.2` the member is required, so an unsealed
# document draws this remark from the semantic reading *and* a refusal from
# the schema; the remark is still what names the question that went
# unanswered rather than the shape that is missing.
_NO_SEAL = "carries no 'document_digest'"

# How the schema refuses that same document, which is the half of the seal
# that moved with the identifier: required on emission now.
_SEAL_REQUIRED = "'document_digest' is a required property"


def _a_valuation(rate: float = 0.001_23) -> ActuarialFrame:
    """Return a one-line model whose quotation is worth tampering with."""
    frame = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    frame.death_claims = frame.sum_assured * rate
    return frame


def _exported(*, seal: bool, rate: float = 0.001_23) -> dict[str, Any]:
    """Return one export of that model, sealed or not, as a parsed document."""
    return json.loads(GraphExporter(_a_valuation(rate)).export(seal=seal))


def _with_the_quotation_edited(document: dict[str, Any]) -> dict[str, Any]:
    """Return the document with one node's as-written formula rewritten.

    The edit a reviewer would never see: the numbers in the model are what
    they were, every operand the node reads is what it read, and only the
    text a supervisor reads to understand the calculation has moved.
    """
    edited = copy.deepcopy(document)
    for node in edited["nodes"]:
        if node.get("formula"):
            node["formula"] = "sum_assured * 0.99999"
            return edited
    msg = "the fixture model exported no node carrying a formula"
    raise AssertionError(msg)


def _errors(report: ValidationReport) -> list[str]:
    """Return the messages of every finding that refuses the artifact."""
    return [
        finding.message for finding in report.findings if finding.severity == "error"
    ]


def _warnings(report: ValidationReport) -> list[str]:
    """Return the messages of every finding worth reading but not refusing."""
    return [
        finding.message for finding in report.findings if finding.severity == "warning"
    ]


# --- the hole this closes, and the closing of it -----------------------------


def test_a_quotation_edited_on_an_unsealed_document_is_still_invisible() -> None:
    """The hole, pinned: the identity chain cannot see an edited formula.

    This is not a defect being tolerated. ``formula`` is deliberately outside
    every node's canonical bytes so that an identity moves when the
    computation moves and at no other time, and this test states the price of
    that decision rather than complaining about it. The price is exactly why
    there is a second field.

    Read on the findings rather than on ``ok``, and the reason is the change
    that made this file's subject required. An unsealed document is refused
    by the schema now, so ``ok`` would be false on both sides for a reason
    that has nothing to do with the edit. What is being pinned is that the
    two readings are the *same* reading: the edit adds no finding and moves
    no identity, which is invisibility stated at the width the claim is made.
    """
    document = _exported(seal=False)
    tampered = _with_the_quotation_edited(document)

    before = validate_artifact(document, deep=True)
    after = validate_artifact(tampered, deep=True)

    assert _errors(after) == _errors(before)
    assert _warnings(after) == _warnings(before)
    assert tampered["graph_fingerprint"] == document["graph_fingerprint"]
    assert [node["fingerprint"] for node in tampered["nodes"]] == [
        node["fingerprint"] for node in document["nodes"]
    ]


def test_a_quotation_edited_on_a_sealed_document_is_refused_by_name() -> None:
    """Clean before the edit, and the named refusal after it."""
    document = _exported(seal=True)
    tampered = _with_the_quotation_edited(document)

    assert validate_artifact(document, deep=True).ok

    after = validate_artifact(tampered, deep=True)
    assert not after.ok
    assert any(_NOT_THE_PRODUCERS_FILE in message for message in _errors(after))


def test_an_edit_and_a_reseal_is_caught_by_the_report_that_cited_the_original() -> None:
    """The limit, and what answers it: a filed record naming the digest.

    A seal inside a document is a digest whoever edits the document can take
    again, so a re-sealed forgery validates clean -- the first assertion --
    and no reading of the standalone file will ever say otherwise. What says
    otherwise is a change report filed when the original was read, which
    recorded the seal the original carried.
    """
    original = _exported(seal=True)
    filed = diff_artifacts(original, _exported(seal=True, rate=0.002_04)).to_dict()

    forged = _with_the_quotation_edited(original)
    forged[DOCUMENT_DIGEST_FIELD] = document_digest_of(forged)

    # Self-consistent, and the file alone cannot tell.
    assert validate_artifact(forged, deep=True).ok

    # The record filed at the time can.
    cited = filed["compared"]["before"][DOCUMENT_DIGEST_FIELD]
    assert cited == original[DOCUMENT_DIGEST_FIELD]
    assert cited != forged[DOCUMENT_DIGEST_FIELD]


# --- what the seal is taken over ---------------------------------------------


def test_a_stranger_recomputes_the_seal_from_the_specification_alone() -> None:
    """The blind-consumer bar: five lines of standard library, nothing imported.

    Nothing in this function touches the framework. It is the recipe grammar
    of section 12.3 applied to the document with the seal lifted out, written
    the way section 13 spells it, and reaching the published digest is what
    makes the field checkable by a reader who has never met this package.
    """
    document = _exported(seal=True)

    body = {
        name: value for name, value in document.items() if name != DOCUMENT_DIGEST_FIELD
    }
    bytes_ = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")

    assert document[DOCUMENT_DIGEST_FIELD] == (
        "sha256:" + hashlib.sha256(bytes_).hexdigest()
    )


def test_the_seal_excludes_itself_and_nothing_else() -> None:
    """One member is lifted out, and every other one is inside.

    Excluding the seal is what makes it recomputable at all. Excluding
    anything further would make it a second identity rather than a seal, and
    the document already carries an identity.
    """
    document = _exported(seal=True)
    stated = document[DOCUMENT_DIGEST_FIELD]

    assert document_digest_of(document) == stated

    for member in ("created_at", "producer", "model", "nodes", "edges", "facets"):
        moved = copy.deepcopy(document)
        moved[member] = None if member != "nodes" else []
        assert document_digest_of(moved) != stated, member


def test_the_seal_covers_when_the_record_was_written_and_the_identity_does_not() -> (
    None
):
    """Two exports of one untouched model: one calculation, two records.

    The two fields answer two questions, and this is where the difference is
    visible. ``graph_fingerprint`` holds because the calculation held.
    ``document_digest`` moves because ``created_at`` moved, and a seal over a
    written record that ignored when it was written would be sealing
    something other than the record.
    """
    first = _exported(seal=True)
    second = copy.deepcopy(first)
    second["created_at"] = "2027-01-01T00:00:00Z"
    second[DOCUMENT_DIGEST_FIELD] = document_digest_of(second)

    assert second["graph_fingerprint"] == first["graph_fingerprint"]
    assert second[DOCUMENT_DIGEST_FIELD] != first[DOCUMENT_DIGEST_FIELD]


# --- what a reader is told, and how loudly ------------------------------------


def test_a_document_with_no_seal_is_refused_and_told_what_it_is_missing() -> None:
    """The half of the seal that moved the identifier, said in both voices.

    Under `gaspatchio-graph/v0-preview.1` the member was optional and its
    absence was a remark. Under `v0-preview.2` it is required, and a document
    written without one stops validating -- which is the break section 14.1's
    line exists to announce. Both readings still speak: the schema names the
    member that is missing, and the semantic layer names the question that
    went unanswered, which is the half a reader acts on.
    """
    report = validate_artifact(_exported(seal=False), deep=True)

    assert not report.ok
    assert any(_SEAL_REQUIRED in message for message in _errors(report))
    assert any(_NO_SEAL in message for message in _warnings(report))


def test_a_seal_that_is_not_a_stamped_digest_is_refused_by_shape() -> None:
    """A seal nobody can parse is a seal nobody can check."""
    document = _exported(seal=True)
    document[DOCUMENT_DIGEST_FIELD] = "not-a-digest"

    report = validate_artifact(document, deep=True)

    assert not report.ok
    assert any("not a stamped content hash" in message for message in _errors(report))


def test_a_seal_spelled_in_uppercase_hex_is_refused_for_its_shape() -> None:
    """The stamp form is lowercase, and a seal in some other form is unreadable.

    Uppercase hex is a digest a reader can decode and is not the way this
    format stamps one -- section 13.1 step 4 says sixty-four lowercase hex
    digits, as section 2 does for every other digest here. Both readings
    refuse at the same grade, so nothing a consumer *does* moves; what moves
    is what the reader is told. "This is not the file the producer wrote" is
    a claim about a file that may be untouched, and the file in hand has not
    been shown to be anything of the sort: what was measured is that its
    seal is not written the way a seal is written.
    """
    document = _exported(seal=True)
    stamped = document[DOCUMENT_DIGEST_FIELD]
    document[DOCUMENT_DIGEST_FIELD] = (
        "sha256:" + stamped.removeprefix("sha256:").upper()
    )

    report = validate_artifact(document, deep=True)

    assert not report.ok
    assert any("not a stamped content hash" in message for message in _errors(report))
    assert not any(_NOT_THE_PRODUCERS_FILE in message for message in _errors(report))


def test_a_seal_stamped_the_way_the_format_writes_one_is_read_and_not_refused() -> None:
    """The other direction of the same reading, so the shape check cannot overreach.

    A refusal keyed on spelling is one bad character away from refusing the
    documents this producer writes, and the seal it writes is the lowercase
    stamp the section describes.
    """
    document = _exported(seal=True)
    stamped = document[DOCUMENT_DIGEST_FIELD]

    assert stamped == stamped.lower()
    assert validate_artifact(document, deep=True).ok


def test_a_document_the_grammar_refuses_is_reported_rather_than_raised() -> None:
    """A report, never an exception, which is this validator's whole posture.

    A bare non-finite float is outside the JSON grammar as well as outside
    the canonical serialization, so a document holding one cannot be sealed
    and cannot honestly be read -- and a reader meets that as a finding
    naming the reading they did not get.
    """
    document = _exported(seal=True)
    document["enrichment"] = {"policy_id": float("nan")}

    report = validate_artifact(document, deep=True)

    assert not report.ok
    assert any("could not be recomputed" in message for message in _errors(report))


def test_the_seal_is_read_before_anything_else_the_deep_reading_recomputes() -> None:
    """The reading that says whether the document is the one the rest describes."""
    document = _exported(seal=True)
    document[DOCUMENT_DIGEST_FIELD] = "sha256:" + "0" * 64

    report = validate_artifact(document, deep=True)

    assert _NOT_THE_PRODUCERS_FILE in report.findings[0].message
    assert (report.findings[0].section, report.findings[0].where) == (
        "semantic",
        "envelope",
    )


def test_a_shallow_reading_never_recomputes_the_seal() -> None:
    """``deep`` is what turns "the producer says so" into a check, here too."""
    tampered = _with_the_quotation_edited(_exported(seal=True))

    assert validate_artifact(tampered).ok
    assert not validate_artifact(tampered, deep=True).ok


# --- what the wire carries, and what it does not yet --------------------------


def test_everything_this_producer_exports_carries_a_seal_unless_it_is_refused() -> None:
    """The emission was written, covered, and turned on with the token.

    The format's users were owed one loud change to what a document carries
    rather than several quiet ones, so the default waited for the commit that
    moved the byte grammar and the schema identifier together, and the flip
    was this one name.

    A caller who wants an unsealed document still has one, which is what the
    third assertion is for: deriving one document from another is the case
    section 13.1's fourth limit is about, and a holder doing that needs to be
    able to write a record that does not claim to be the file a producer
    wrote.
    """
    assert SEAL_BY_DEFAULT is True
    assert DOCUMENT_DIGEST_FIELD in _exported(seal=SEAL_BY_DEFAULT)
    assert DOCUMENT_DIGEST_FIELD not in _exported(seal=False)
    assert DOCUMENT_DIGEST_FIELD in _exported(seal=True)


def test_the_seal_is_written_last_because_it_is_taken_over_a_finished_record() -> None:
    """Seventeen members where there were sixteen, and the seal closes them."""
    plain = _exported(seal=False)
    sealed = _exported(seal=True)

    assert list(sealed) == [*plain, DOCUMENT_DIGEST_FIELD]


# --- the citation chain -------------------------------------------------------


def test_the_change_report_records_the_seal_and_never_compares_it() -> None:
    """Two exports of one untouched model: two seals, and no drift.

    The seal joins ``created_at`` and the producer version as description.
    A report that read a moved seal as drift would fire on every pair of
    exports ever taken, which is a report a reviewer learns to ignore.
    """
    before = _exported(seal=True)
    after = copy.deepcopy(before)
    after["created_at"] = "2027-01-01T00:00:00Z"
    after[DOCUMENT_DIGEST_FIELD] = document_digest_of(after)

    report = diff_artifacts(before, after)

    assert report.drift is False
    assert report.calculations == ()
    earlier, later = report.compared
    assert earlier.document_digest == before[DOCUMENT_DIGEST_FIELD]
    assert later.document_digest == after[DOCUMENT_DIGEST_FIELD]
    assert earlier.document_digest != later.document_digest


def test_a_report_about_unsealed_documents_says_so_rather_than_inventing_one() -> None:
    """None is the answer for a document that carried no seal."""
    report = diff_artifacts(_exported(seal=False), _exported(seal=False))

    assert [document.document_digest for document in report.compared] == [None, None]
    assert report.to_dict()["compared"]["before"][DOCUMENT_DIGEST_FIELD] is None
