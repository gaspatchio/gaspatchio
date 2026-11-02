# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A filter on a rollforward's state chooses rows on it, and records the choice.

``af.filter(compiled.expr_for("av").list.get(0) > 0)`` reads the run's hidden
struct column, which only the door every expression enters by puts on the
plan. The filter did not go through that door, so on the tree before this
the collect failed with ``ColumnNotFoundError: '__rollforward_<fp>'`` in both
Polars engines. Now the filter puts the run on the plan first, keeps the
policies whose opening account value is positive, and records its step by
the tree the state was built from: the selection reads the compiled
rollforward's node, never its hidden column. A replay applies the selection
to the book before it projects, and a rollforward's state is calculated, so
the executable profile refuses the step by name, as it refuses a filter on
any calculated column (spec section 7.6).

The hand values: each policy's account value at the end of its first month
is its opening balance plus one month's premium, 100 + 10 = 110 for P001,
-50 + 10 = -40 for P002 and 20 + 10 = 30 for P003, so P002 is the one
dropped.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.frame.graph import GraphExporter, validate_artifact

_ENGINES = ("streaming", "in-memory")


def _projected() -> ActuarialFrame:
    af = ActuarialFrame(
        {
            "policy_id": ["P001", "P002", "P003"],
            "init": [100.0, -50.0, 20.0],
            "term_months": [2, 3, 2],
            "premium": [[10.0, 10.0], [10.0, 10.0, 10.0], [10.0, 10.0]],
        }
    )
    return af.projection.set(
        valuation_date=dt.date(2025, 1, 31),
        until="term_months",
        until_value="term_months",
        frequency="monthly",
        per_policy=True,
    )


def _on_the_state(*, assign_after: bool = False) -> ActuarialFrame:
    af = _projected()
    builder = af.projection.rollforward(states={"av": af["init"]})
    builder["av"].add(af["premium"])
    compiled = compile_rollforward(builder)
    af = af.filter(compiled.expr_for("av").list.get(0) > 0)
    if assign_after:
        af.av = compiled.expr_for("av")
    af.y = af.init * 2.0
    return af


def _on_the_assigned_state() -> ActuarialFrame:
    af = _projected()
    builder = af.projection.rollforward(states={"av": af["init"]})
    builder["av"].add(af["premium"])
    af.av = compile_rollforward(builder).expr_for("av")
    af = af.filter(af.av.list.get(0) > 0)
    af.y = af.init * 2.0
    return af


def _audit(af: ActuarialFrame) -> dict[str, Any]:
    return json.loads(GraphExporter(af).export(profile="audit"))


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_filter_on_a_state_keeps_the_policies_it_holds_for(engine: str) -> None:
    out = _on_the_state().collect(engine=engine)  # type: ignore[arg-type]
    assert out["policy_id"].to_list() == ["P001", "P003"]
    assert out["y"].to_list() == [200.0, 40.0]
    assert not [name for name in out.columns if name.startswith("__rollforward")]


@pytest.mark.parametrize("engine", _ENGINES)
def test_the_state_assigned_after_the_filter_is_the_run_the_filter_read(
    engine: str,
) -> None:
    out = _on_the_state(assign_after=True).collect(engine=engine)  # type: ignore[arg-type]
    assert out["policy_id"].to_list() == ["P001", "P003"]
    assert out["av"].to_list() == [[110.0, 120.0], [30.0, 40.0]]


def test_the_step_is_recorded_by_the_state_s_tree_not_its_hidden_column() -> None:
    document = _audit(_on_the_state())
    (step,) = document["selection"]
    (run,) = [n["id"] for n in document["nodes"] if n["id"].startswith("rollforward:")]
    assert step["kind"] == "filter"
    assert step["tier"] == "core"
    assert step["reads"] == [run]
    state = step["expr"]["left"]["args"][0]
    assert state["name"] == "rollforward.state"
    assert state["attrs"]["state"] == "av"
    assert "__rollforward" not in json.dumps(step)
    assert validate_artifact(document).findings == ()


def test_a_filter_on_a_state_moves_both_fingerprints() -> None:
    def kept_over(threshold: float) -> tuple[str, str]:
        af = _projected()
        builder = af.projection.rollforward(states={"av": af["init"]})
        builder["av"].add(af["premium"])
        af = af.filter(
            compile_rollforward(builder).expr_for("av").list.get(0) > threshold
        )
        af.y = af.init * 2.0
        document = _audit(af)
        return document["graph_fingerprint"], document["formulas_fingerprint"]

    at_zero, at_fifty = kept_over(0.0), kept_over(50.0)
    assert at_zero[0] != at_fifty[0]
    assert at_zero[1] != at_fifty[1]


@pytest.mark.parametrize(
    ("model", "reads"),
    [
        (_on_the_state, "on the rollforward state 'av' (rollforward:"),
        (_on_the_assigned_state, "on 'av@1'"),
    ],
    ids=["the state", "the assigned state"],
)
def test_the_executable_profile_refuses_the_step_by_name(
    model: Any,  # noqa: ANN401
    reads: str,
) -> None:
    """A replay selects from the book before it projects; a state is not on it."""
    with pytest.raises(ValueError, match="which the model calculates") as refused:
        GraphExporter(model()).export(profile="executable")
    message = str(refused.value)
    assert message.startswith("selection:1 (")
    assert "test_selection_on_a_rollforward_state.py:" in message
    assert reads in message
    assert "outside the core vocabulary" not in message


def test_a_step_on_two_states_of_one_run_names_both() -> None:
    """The run's node id is a fingerprint; the states are the author's words."""
    af = _projected()
    builder = af.projection.rollforward(states={"av": af["init"], "fund": af["init"]})
    builder["av"].add(af["premium"])
    builder["fund"].add(af["premium"])
    compiled = compile_rollforward(builder)
    af = af.filter(
        (compiled.expr_for("av").list.get(0) > 0)
        & (compiled.expr_for("fund").list.get(1) > 0)
    )
    af.y = af.init * 2.0
    with pytest.raises(ValueError, match="which the model calculates") as refused:
        GraphExporter(af).export(profile="executable")
    message = str(refused.value)
    assert "on the rollforward states 'av' and 'fund' (rollforward:" in message
    assert "test_selection_on_a_rollforward_state.py:" in message
