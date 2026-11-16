# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A name read at two periods in one formula says both periods.

``prev(x) + next(x)`` used to reach the file as one read of ``x`` with no
``offset`` -- and no offset is how the file says "the period being
computed". So the file stated a same-period read for a formula that reads
no same period, and an actuary tracing it from the file alone was pointed
at the wrong cell. Now each value read states its own distance: one
``TRANSFORMATION`` entry per distance, the period being computed first and
then the distances in order. A name whose value reads all agree is written
exactly as before.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Final

import polars as pl

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter, validate_artifact

_FACET: Final[str] = "gaspatchio_column_transformation"
_NOW: Final[dict[str, str]] = {"type": "DIRECT", "subtype": "TRANSFORMATION"}


def _shifted(offset: int) -> dict[str, Any]:
    return {**_NOW, "offset": offset}


def _the_model() -> ActuarialFrame:
    """Return a six-month frame reading one column at several periods at once."""
    frame = ActuarialFrame(pl.DataFrame({"policy_id": ["A"], "base": [100.0]}))
    af = frame.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=6, frequency="monthly"
    )
    af.x = af.base + af.month
    af.prev_and_next = af.x.projection.previous_period() + af.x.projection.next_period()
    af.prev_and_now = af.x.projection.previous_period() + af.x
    af.two_back_and_one_back = (
        af.x.projection.at_period(-2) + af.x.projection.previous_period()
    )
    af.now_twice = af.x + af.x
    af.tested_now_read_back = (
        when(af.x > 0).then(af.x.projection.previous_period()).otherwise(0.0)
    )
    af.back_and_running = af.x.projection.previous_period() + af.x.cum_sum()
    return af


def _exported() -> dict[str, Any]:
    artifact: dict[str, Any] = json.loads(GraphExporter(_the_model()).export())
    return artifact


def _narrowings(artifact: dict[str, Any], node_id: str) -> list[dict[str, Any]]:
    (node,) = [entry for entry in artifact["nodes"] if entry["id"] == node_id]
    (read,) = node["facets"][_FACET]["reads"]
    assert read["source"] == "x@1"
    narrowings: list[dict[str, Any]] = read["transformations"]
    return narrowings


def test_a_read_one_back_and_one_ahead_states_both() -> None:
    """``prev(x) + next(x)`` is two reads, at -1 and +1, and says so."""
    assert _narrowings(_exported(), "prev_and_next@1") == [_shifted(-1), _shifted(1)]


def test_a_read_one_back_and_now_states_both() -> None:
    """``prev(x) + x`` reads this period and the last: the period now comes first."""
    assert _narrowings(_exported(), "prev_and_now@1") == [_NOW, _shifted(-1)]


def test_two_shifts_back_are_stated_in_order() -> None:
    """``at_period(-2) + prev(x)``: each distance quoted, nearer the past first."""
    assert _narrowings(_exported(), "two_back_and_one_back@1") == [
        _shifted(-2),
        _shifted(-1),
    ]


def test_a_name_read_twice_at_one_period_is_written_as_before() -> None:
    """``x + x`` is one read of this period: one entry, no offset."""
    assert _narrowings(_exported(), "now_twice@1") == [_NOW]


def test_a_value_read_back_beside_a_test_read_now_states_its_own_period() -> None:
    """The value came from t-1; the test that chose it is not a value read.

    A conditional's test reads ``x`` at the period being computed, but an
    offset says which period a value came from, and the only value read of
    ``x`` here is one period back.
    """
    assert _narrowings(_exported(), "tested_now_read_back@1") == [_shifted(-1)]


def test_a_shifted_read_beside_a_fold_keeps_its_offset() -> None:
    """``prev(x) + cum_sum(x)``: the shifted value read keeps -1 beside the fold."""
    assert _narrowings(_exported(), "back_and_running@1") == [
        _shifted(-1),
        {
            "type": "DIRECT",
            "subtype": "AGGREGATION",
            "periods": {"from": "first", "to": 0},
        },
    ]


def test_the_file_still_validates() -> None:
    """Several entries of one narrowing are what the facet's array is for."""
    report = validate_artifact(_exported())
    assert report.ok, [finding.message for finding in report.findings]
