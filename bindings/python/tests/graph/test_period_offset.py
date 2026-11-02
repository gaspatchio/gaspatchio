# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A read across periods says which period it read.

"This month's reserve reads last month's -- show me which cell." Until the
read carries the distance, the file answers that by pointing at the same
cell, and a same-period proof is a wrong proof rather than an absent one.

So a read made through one of the three period shifts carries ``offset``
in the narrowing facet: the distance from the row being computed, negative
a prior period and positive a later one. The tests below are that claim
from both ends -- the three shifts stating theirs, every other read stating
none, the validator refusing the three ways it can be mis-stated, and the
digests unmoved, because a facet is outside the canonical bytes and a field
that moved a fingerprint would have changed what the model is.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Final

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact

# The digest of the model below, measured on the producer that had never
# heard of ``offset``. It is pinned here rather than recomputed because
# that is the whole claim: a facet sits outside the canonical bytes, so a
# read that gained a distance is the same calculation it was before.
_GRAPH_FINGERPRINT: Final[str] = (
    "sha256:4fb94289cb3b5905f28e092e159d5943280948e74b3b84f828c1fab5e0216a38"
)

_FACET: Final[str] = "gaspatchio_column_transformation"


def _the_model() -> ActuarialFrame:
    """Return a six-month reserve run holding one of each kind of read.

    A survival curve folded across the whole run, a reserve carried on it,
    and then the same reserve read one period back, one period ahead and
    two periods back -- which is the movement an actuary writes when a
    rollforward has to line this period's balance up against the last.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["A"],
                "opening_reserve": [1_000.0],
                "annual_decrement": [0.012],
            }
        )
    )
    af = frame.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=6, frequency="monthly"
    )
    af.monthly_decrement = (af.annual_decrement / 12).projection.broadcast_to_periods(
        like=af.month
    )
    af.survival = af.monthly_decrement.projection.cumulative_survival()
    af.reserve = af.opening_reserve * af.survival
    af.reserve_prev = af.reserve.projection.previous_period(fill_value=0.0)
    af.reserve_next = af.reserve.projection.next_period(fill_value=0.0)
    af.reserve_two_back = af.reserve.projection.at_period(-2)
    af.movement = af.reserve - af.reserve_prev
    return af


def _exported() -> dict[str, Any]:
    """Return the artifact that model exports, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(_the_model()).export())
    return artifact


def _narrowings(artifact: dict[str, Any], node_id: str) -> list[dict[str, Any]]:
    """Return the narrowings one node carries, in its own ``reads`` order."""
    (node,) = [entry for entry in artifact["nodes"] if entry["id"] == node_id]
    return [
        narrowing
        for read in node["facets"][_FACET]["reads"]
        for narrowing in read["transformations"]
    ]


# --- the three shifts state their distance ----------------------------------


def test_a_previous_period_read_says_it_read_one_period_back() -> None:
    """t-1 is -1, and it is the identifier that fixes it rather than the call."""
    assert _narrowings(_exported(), "reserve_prev@1") == [
        {"type": "DIRECT", "subtype": "TRANSFORMATION", "offset": -1}
    ]


def test_a_next_period_read_says_it_read_one_period_ahead() -> None:
    """t+1 is +1: the sign the projection accessor already asks for."""
    assert _narrowings(_exported(), "reserve_next@1") == [
        {"type": "DIRECT", "subtype": "TRANSFORMATION", "offset": 1}
    ]


def test_an_at_period_read_quotes_the_relative_period_the_call_stated() -> None:
    """The distance is the operation's own attribute, not a distance derived.

    ``relative_period`` is what the executable profile's operation tree
    serialises for this call, and it is what the facet quotes. Two periods
    back rather than one is the case that tells a quoted value from a
    guessed one: nothing in the vocabulary fixes this call at -1.
    """
    assert _narrowings(_exported(), "reserve_two_back@1") == [
        {"type": "DIRECT", "subtype": "TRANSFORMATION", "offset": -2}
    ]


# --- and every other read states none ----------------------------------------


def test_an_ordinary_read_carries_no_offset_at_all() -> None:
    """A read of the period being computed says so by saying nothing.

    Never a zero. Two spellings of the commonest read in any model would
    leave a consumer with two shapes to recognise for one fact, and the
    absence is already the statement.
    """
    ordinary = _narrowings(_exported(), "movement@1")

    assert ordinary == [
        {"type": "DIRECT", "subtype": "TRANSFORMATION"},
        {"type": "DIRECT", "subtype": "TRANSFORMATION"},
    ]
    assert all("offset" not in narrowing for narrowing in ordinary)


def test_a_cumulative_read_carries_no_offset_either() -> None:
    """A fold reads its whole run, and a single distance would contradict it.

    ``cumulative_survival`` consumes every period of the decrement it is
    handed, which is what ``AGGREGATION`` says: the value is in every later
    period's answer rather than in one period's, so there is no one period
    to name.
    """
    cumulative = _narrowings(_exported(), "survival@1")

    # What it states instead is its window (section 9): under the accessor's
    # default opening of 1.0, period t reads the decrements of 0..t-1.
    assert cumulative == [
        {
            "type": "DIRECT",
            "subtype": "AGGREGATION",
            "periods": {"from": "first", "to": -1},
        }
    ]
    assert "offset" not in cumulative[0]


def test_only_the_three_shifts_carry_one() -> None:
    """Three reads in this model read another period, and three carry a distance."""
    artifact = _exported()
    carried = [
        narrowing
        for node in artifact["nodes"]
        for read in node.get("facets", {}).get(_FACET, {}).get("reads", [])
        for narrowing in read["transformations"]
    ]

    assert [narrowing["offset"] for narrowing in carried if "offset" in narrowing] == [
        -1,
        1,
        -2,
    ]
    assert sum("offset" not in narrowing for narrowing in carried) == 7


def test_the_core_edge_is_untouched_by_any_of_it() -> None:
    """The offset travels beside the edge, never on it.

    Section 9 puts how a read was narrowed on the reading node, and this is
    one more narrowing rather than a new relationship: an impact cone drawn
    through these edges is the cone it was before.
    """
    artifact = _exported()

    assert all(
        set(edge) == {"source", "target", "relationship"} for edge in artifact["edges"]
    )


# --- and no digest moves for any of it ---------------------------------------


def test_stating_the_period_moves_no_fingerprint() -> None:
    """A facet is outside the canonical bytes, so this is the same calculation.

    The digest below was taken on the producer before ``offset`` existed. A
    field that moved it would be saying the model changed when what changed
    is what the file says about it -- and every quarter-on-quarter
    comparison drawn on these digests would have reported a difference
    nobody made.
    """
    artifact = _exported()

    assert artifact["graph_fingerprint"] == _GRAPH_FINGERPRINT


# --- the three ways it can be mis-stated, and the three refusals --------------


def _with_offset(artifact: dict[str, Any], node_id: str, stated: Any) -> dict[str, Any]:  # noqa: ANN401
    """Return the artifact with one read's ``offset`` replaced by ``stated``."""
    (node,) = [entry for entry in artifact["nodes"] if entry["id"] == node_id]
    node["facets"][_FACET]["reads"][0]["transformations"][0]["offset"] = stated
    return artifact


def _refusals(artifact: dict[str, Any]) -> list[str]:
    """Return the error-grade messages the facet reading draws.

    Filtered to the semantic reading on purpose. A zero and a fractional
    distance are refused twice over -- the published schema declares
    ``offset`` an integer that is not zero, so it refuses them before any
    of this runs -- and what these tests are about is the reading that
    states the rule in the model's own terms.
    """
    report = validate_artifact(artifact)
    return [
        finding.message
        for finding in report.findings
        if finding.severity == "error" and finding.section == "semantic"
    ]


def _schema_refuses(artifact: dict[str, Any]) -> bool:
    """Return whether the published schema refuses the document as it stands."""
    return any(
        finding.section == "schema" and finding.severity == "error"
        for finding in validate_artifact(artifact).findings
    )


def test_an_offset_that_is_not_a_whole_number_is_refused() -> None:
    """A distance in periods is a count of periods, and a null is not 'none'."""
    half = _refusals(_with_offset(_exported(), "reserve_prev@1", 1.5))
    absent = _refusals(_with_offset(_exported(), "reserve_prev@1", None))

    assert half, "a fractional offset drew no refusal"
    assert "an offset is a whole number of periods" in half[0]
    assert "which period a read read is the producer's to say" in half[0]
    assert absent, "a null offset drew no refusal"
    assert "A null is not 'no offset' either" in absent[0]
    assert _schema_refuses(_with_offset(_exported(), "reserve_prev@1", 1.5))


def test_an_offset_of_zero_periods_is_refused() -> None:
    """The period being computed is said by the absence, and only by it."""
    refused = _refusals(_with_offset(_exported(), "reserve_prev@1", 0))

    assert refused, "an offset of zero drew no refusal"
    assert "states an ``offset`` of 0" in refused[0]
    assert "that is said by carrying no ``offset`` at all" in refused[0]
    assert _schema_refuses(_with_offset(_exported(), "reserve_prev@1", 0))


def test_an_offset_beside_a_narrowing_that_is_not_a_transformation_is_refused() -> None:
    """An offset says a value came from a period, so it needs a value to have come.

    ``survival@1``'s read is an ``AGGREGATION``: the decrement is folded
    across the whole run rather than taken from one period of it. A
    distance written beside that narrowing is a claim the narrowing beside
    it contradicts, and the file does not say which of the two is wrong.
    """
    refused = _refusals(_with_offset(_exported(), "survival@1", -1))

    assert refused, "an offset on an aggregation drew no refusal"
    assert "an offset goes with 'TRANSFORMATION' and with nothing else" in refused[0]
    assert "'AGGREGATION'" in refused[0]


def test_a_well_stated_offset_is_accepted() -> None:
    """The refusals above bite on the mis-statement rather than on the field."""
    assert validate_artifact(_exported()).ok
