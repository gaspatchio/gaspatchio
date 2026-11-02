# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An artifact that admits to a hole is still a conforming artifact.

A hole is the one thing a model can say about itself that reads like a
failure: a column it finishes holding and cannot account for. The temptation
is to treat the document carrying one as broken, and that would be exactly
backwards. The model whose account of itself has a gap and says so is the
model behaving well; the format's job is to carry the admission, and the
validator's job is to accept it.

So this is a release condition rather than a unit test. The artifact names
the column, gives the one reason a producer can defend, and points at what
closes it -- and the validator, recomputing the digests rather than reading
them, says the document holds together. If either half ever stops being
true, a model that told the truth about itself would be refused by its own
reader for telling it (*Audit by default*).

``test_artifact_holes.py`` owns what the holes section says. This file owns
what happens when a reader takes a document carrying one seriously.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import polars as pl

from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact

# Where a reader who meets an unaccounted-for column is pointed. Written out
# here rather than imported from the producer: the URI is part of what the
# format promises a consumer, so a test that read it from the same constant
# the export writes would agree with any value at all.
_CLOSES_WITH = "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3#holes"

_Profile = Literal["audit", "executable"]


def _a_model_that_writes_past_the_recording_door() -> ActuarialFrame:
    """Return a frame holding one column nothing in the model accounts for.

    ``reserve_override`` lands in the query plan, and so in the schema the
    plan resolves to, without the framework ever seeing an assignment to
    record. It is the one way a user reaches this state on purpose, and it
    is also what an unrecorded step inside the framework would look like.
    The bypass is the same one ``test_artifact_holes.py`` uses to mint a
    hole; it is written out here because the profile is a parameter of the
    claim this file makes and is not of that one.
    """
    frame = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    frame.death_claims = frame.sum_assured * 0.001_23
    frame._df = frame._df.with_columns(  # noqa: SLF001 — writing the plan past every recording door is what mints a hole
        (pl.col("sum_assured") * 0.02).alias("reserve_override")
    )
    return frame


def _export_a_model_that_writes_past_the_recording_door(
    profile: _Profile = "audit",
) -> dict[str, Any]:
    """Return the artifact that model exports under one profile."""
    exported = GraphExporter(_a_model_that_writes_past_the_recording_door()).export(
        profile=profile
    )
    artifact: dict[str, Any] = json.loads(exported)
    return artifact


def test_a_column_written_past_the_recording_door_is_a_loud_hole() -> None:
    """A release condition: the artifact says so, and the validator accepts it."""
    artifact = _export_a_model_that_writes_past_the_recording_door()

    assert artifact["holes"] == [
        {
            "column": "reserve_override",
            "reason": "unrecorded",
            "closes_with": _CLOSES_WITH,
        }
    ]

    report = validate_artifact(artifact, deep=True)

    assert report.ok, "\n".join(finding.message for finding in report.findings)


def test_the_admission_conforms_under_the_executable_profile() -> None:
    """The profile that carries the calculation carries the gap in it too.

    Under ``executable`` the deep reading recomputes every node's identity
    from the operation tree beside it. A hole has no tree -- the absence of
    one is its whole content -- so this is where a validator that assumed
    every node could be re-hashed would refuse the honest document.
    """
    artifact = _export_a_model_that_writes_past_the_recording_door("executable")
    report = validate_artifact(artifact, deep=True)

    assert artifact["holes"] == [
        {
            "column": "reserve_override",
            "reason": "unrecorded",
            "closes_with": _CLOSES_WITH,
        }
    ]
    assert report.ok, "\n".join(finding.message for finding in report.findings)


def test_the_hole_does_not_cost_the_columns_beside_it_their_account() -> None:
    """One unexplained column is one unexplained column, not a spoiled file.

    The reason a hole is worth carrying at all is that the rest of the model
    still says what it does. A document that answered "something here is
    unaccounted for" by weakening every other claim in it would be no more
    use to a reviewer than no document.
    """
    artifact = _export_a_model_that_writes_past_the_recording_door()

    (claims,) = [node for node in artifact["nodes"] if node["column"] == "death_claims"]

    assert claims["kind"] == "computed"
    # The right-hand side as its author wrote it, down to the name the frame
    # was bound to on the line above and the digit grouping in the rate --
    # which is the whole point of carrying the sentence rather than the
    # engine's rendering of it.
    assert claims["formula"] == "frame.sum_assured * 0.001_23"
    assert claims["reads"] == ["sum_assured"]
