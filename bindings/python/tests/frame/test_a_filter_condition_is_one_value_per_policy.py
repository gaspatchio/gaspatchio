# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A filter's condition is one value per policy; a per-period one is refused.

A selection chooses which policies a model values: a policy is kept or
dropped in every period at once. ``af.filter(af.x > 0)`` with ``x`` holding a
value per period has an answer for every period instead, and on the tree
before this it reached Polars, which failed with ``SchemaError: could not
evaluate '>' comparison between series 'x' of dtype: List(Float64) and series
'literal'`` (or, for a per-period null test, ``filter predicate must be of type
Boolean, got List(Boolean)``), naming neither the filter nor the move. Now
``af.filter`` refuses it where it is written, names the per-period read, and
names the frame's declared reductions to one value per policy, each of which
runs and records a core step.

The hand values, with ``x`` = [1, -1], [2, 3] and [-1, 2]: the first period's
value is positive for P1 and P2, every period's for P2 alone, and some
period's for all three.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable


def _projected() -> ActuarialFrame:
    af = ActuarialFrame(
        {
            "policy_id": ["P1", "P2", "P3"],
            "term_months": [2, 2, 2],
            "x": [[1.0, -1.0], [2.0, 3.0], [-1.0, 2.0]],
            "init": [100.0, -50.0, 20.0],
            "premium": [[10.0, 10.0], [10.0, 10.0], [10.0, 10.0]],
        }
    )
    return af.projection.set(
        valuation_date=dt.date(2025, 1, 31),
        until="term_months",
        until_value="term_months",
        frequency="monthly",
        per_policy=True,
    )


def _state(af: ActuarialFrame) -> Any:  # noqa: ANN401 -- the state's Polars expression
    builder = af.projection.rollforward(states={"av": af["init"]})
    builder["av"].add(af["premium"])
    return compile_rollforward(builder).expr_for("av")


_PER_PERIOD: dict[str, tuple[Callable[[ActuarialFrame], Any], str, str]] = {
    "a comparison": (lambda af: af.x > 0, "'x' holds", "af.x"),
    "Polars' own words": (lambda _af: pl.col("x") > 0, "'x' holds", "af.x"),
    "a null test": (lambda af: af.x.is_not_null(), "'x' holds", "af.x"),
    "the period index": (lambda af: af.month > 0, "'month' holds", "af.month"),
    "beside a per-policy test": (
        lambda af: (af.init > 0) & (af.x > 0),
        "'x' holds",
        "af.x",
    ),
    "a rollforward's state": (
        lambda af: _state(af) > 0,
        "the rollforward state 'av' holds",
        'compiled.expr_for("av")',
    ),
}


@pytest.mark.parametrize("case", list(_PER_PERIOD), ids=list(_PER_PERIOD))
def test_a_per_period_condition_is_refused_where_it_is_written(case: str) -> None:
    condition, named, written = _PER_PERIOD[case]
    af = _projected()
    with pytest.raises(ValueError, match="keeps or drops whole policies") as refused:
        af.filter(condition(af))
    message = str(refused.value)
    assert message.startswith(
        "af.filter() keeps or drops whole policies, so its condition must be "
        "one value per policy, and this one answers once a period, because "
    )
    assert f"{named} one value per period." in message
    for form in (".list.get(0) > 0", ".list.min() > 0", ".list.max() > 0"):
        assert f"{written}{form}" in message
    assert "model points before the frame is built" in message
    assert "when(...)" in message


def test_a_refused_condition_leaves_the_frame_choosing_nothing() -> None:
    af = _projected()
    with pytest.raises(ValueError, match="keeps or drops whole policies"):
        af.filter(af.x > 0)
    af.y = af.init * 2.0
    assert af.collect()["policy_id"].to_list() == ["P1", "P2", "P3"]
    assert "selection" not in json.loads(GraphExporter(af).export(profile="audit"))


_PER_POLICY: dict[str, tuple[Callable[[ActuarialFrame], Any], list[str]]] = {
    "the first period": (lambda af: af.x.list.get(0) > 0, ["P1", "P2"]),
    "every period": (lambda af: af.x.list.min() > 0, ["P2"]),
    "any period": (lambda af: af.x.list.max() > 0, ["P1", "P2", "P3"]),
}


@pytest.mark.parametrize("case", list(_PER_POLICY), ids=list(_PER_POLICY))
def test_each_named_reduction_chooses_policies_and_records_a_core_step(
    case: str,
) -> None:
    condition, kept = _PER_POLICY[case]
    af = _projected()
    af = af.filter(condition(af))
    af.y = af.init * 2.0
    assert af.collect()["policy_id"].to_list() == kept
    (step,) = json.loads(GraphExporter(af).export(profile="audit"))["selection"]
    assert step["tier"] == "core"
    assert step["reads"] == ["x"]
    assert json.loads(GraphExporter(af).export(profile="executable"))["selection"]


def test_a_per_policy_condition_still_chooses_its_policies() -> None:
    af = _projected()
    af = af.filter(af.init > 0)
    assert af.collect()["policy_id"].to_list() == ["P1", "P3"]
