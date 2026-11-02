# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Frame-only adaptation preserves invocation and refuses unused scenario inputs."""

from __future__ import annotations

from typing import Literal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import ScenarioRun, Sum, as_scenario_model, for_each_scenario


@pytest.mark.parametrize("mode", ["debug", "optimize"])
@pytest.mark.parametrize("successor", [False, True])
def test_adapter_calls_once_and_preserves_frame_return_contract(
    mode: Literal["debug", "optimize"], *, successor: bool
) -> None:
    af = ActuarialFrame({"amount": [2.0]}, mode=mode)
    calls: list[ActuarialFrame] = []
    returned = ActuarialFrame({"value": [4.0]}, mode=mode)

    def model(frame: ActuarialFrame) -> ActuarialFrame | None:
        calls.append(frame)
        frame.value = frame.amount * 2
        return returned if successor else None

    result = as_scenario_model(model)(af, tables={}, drivers={})
    assert calls == [af]
    assert result is (returned if successor else af)
    assert result.graph.last_run is None


@pytest.mark.parametrize("mode", ["debug", "optimize"])
def test_model_body_typeerror_is_not_retried(
    mode: Literal["debug", "optimize"],
) -> None:
    calls = 0
    error = TypeError("from inside the model")

    def model(_frame: ActuarialFrame) -> ActuarialFrame:
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(TypeError) as caught:
        as_scenario_model(model)(
            ActuarialFrame({"a": [1]}, mode=mode), tables={}, drivers={}
        )
    assert caught.value is error
    assert calls == 1


@pytest.mark.parametrize("supplied", ["tables", "drivers", "both"])
def test_adapter_refuses_scenario_inputs_before_calling_model(supplied: str) -> None:
    table = Table(
        name="mortality",
        source=pl.DataFrame({"age": [50], "rate": [0.01]}),
        dimensions={"age": "age"},
        value="rate",
    )
    calls: list[ActuarialFrame] = []

    def model(frame: ActuarialFrame) -> ActuarialFrame:
        calls.append(frame)
        return frame

    with pytest.raises(ValueError, match="cannot ignore nonempty"):
        as_scenario_model(model)(
            ActuarialFrame({"age": [50]}),
            tables={"mortality": table} if supplied in {"tables", "both"} else {},
            drivers={"rng_seed": 123} if supplied in {"drivers", "both"} else {},
        )
    assert calls == []


def test_frame_model_reads_the_scenario_axis_in_bounded_batches() -> None:
    calls = 0

    def model(frame: ActuarialFrame) -> None:
        nonlocal calls
        frame.value = frame.amount * frame.scenario_id
        calls += 1

    result = for_each_scenario(
        ActuarialFrame({"amount": [2.0, 3.0]}),
        [1, 2, 3],
        as_scenario_model(model),
        aggregations=[Sum("value").alias("total")],
        batch_size=2,
        capture_graph_fingerprint=False,
    )
    assert result.aggregations["total"] == 30.0
    assert calls == 2


def test_a_shocks_plan_refuses_the_three_argument_door_naming_the_move() -> None:
    """A shocks plan runs the frame-only model; an adapted door model is refused."""
    calls: list[ActuarialFrame] = []

    def model(frame: ActuarialFrame) -> ActuarialFrame:
        calls.append(frame)
        return frame

    plan = ScenarioRun(
        shocks={"base": []},
        aggregations=(Sum("amount").alias("total"),),
        master_seed=123,
    )
    with pytest.raises(TypeError, match=r"plan\.run\(af, model\.main\)"):
        plan.run(
            ActuarialFrame({"amount": [2.0]}), as_scenario_model(model), batch_size=1
        )
    assert calls == []


def test_a_seeded_plan_hands_each_scenario_its_seed_as_a_column() -> None:
    """The seed reaches the frame-only model as data, at any batch size."""
    from gaspatchio.scenarios._for_each import _per_scenario_seed

    def model(frame: ActuarialFrame) -> ActuarialFrame:
        frame.seed_value = frame.rng_seed * 1.0
        return frame

    plan = ScenarioRun(
        shocks={"a": [], "b": [], "c": []},
        aggregations=(Sum("seed_value").alias("seed").over("scenario_id"),),
        master_seed=123,
    )
    for batch_size in (1, 2, 3):
        result = plan.run(
            ActuarialFrame({"amount": [2.0]}), model, batch_size=batch_size
        )
        seen = dict(result.aggregations["seed"].iter_rows())
        assert seen == {
            sid: float(_per_scenario_seed(123, sid)) for sid in ("a", "b", "c")
        }
