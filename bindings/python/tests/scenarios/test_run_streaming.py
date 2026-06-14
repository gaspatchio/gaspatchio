# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Streaming/progress tests for ScenarioRun.run + BatchSnapshot progress type.
# ABOUTME: Covers _fmt_duration, snapshot properties, progress hook, n_batches, channel.
"""Tests for ScenarioRun streaming + the BatchSnapshot progress type."""

from __future__ import annotations

import math
import sys

import polars as pl
import pytest
from loguru import logger

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import (
    BatchSnapshot,
    ScenarioRun,
    Sum,
    for_each_scenario,
)
from gaspatchio_core.scenarios._for_each import _fmt_duration


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (5.0, "5s"),
        (45.0, "45s"),
        (90.0, "1m30s"),
        (192.0, "3m12s"),
        (3840.0, "1h04m"),
    ],
)
def test_fmt_duration(seconds: float, expected: str) -> None:
    """_fmt_duration renders durations as '45s', '3m12s', '1h04m'."""
    assert _fmt_duration(seconds) == expected


def _snap(done: int, total: int, elapsed: float) -> BatchSnapshot:
    return BatchSnapshot(
        batch_idx=0,
        scenarios_done=done,
        total_scenarios=total,
        outputs={},
        peak_rss_mb=None,
        elapsed_s=elapsed,
    )


def test_snapshot_fraction_done() -> None:
    """fraction_done is scenarios_done / total, guarded for the empty-run case."""
    assert _snap(25, 100, 1.0).fraction_done == 0.25
    assert _snap(0, 0, 1.0).fraction_done == 0.0  # guard: empty run


def test_snapshot_eta_s() -> None:
    """eta_s is None before any progress, 0 at completion, linear otherwise."""
    assert _snap(25, 100, 1.0).eta_s == pytest.approx(3.0)  # 1s for 25% -> 3s left
    assert _snap(0, 100, 1.0).eta_s is None  # no progress yet -> unknown
    assert _snap(100, 100, 5.0).eta_s == 0.0  # done -> nothing remaining


def test_snapshot_throughput() -> None:
    """Throughput is scenarios/second; None when no time has elapsed."""
    assert _snap(50, 100, 2.0).throughput == pytest.approx(25.0)
    assert _snap(10, 100, 0.0).throughput is None  # no elapsed time -> unknown


@pytest.fixture
def af() -> ActuarialFrame:
    """Three-policy frame; _value_model adds `v` = premium."""
    return ActuarialFrame({"policy_id": [1, 2, 3], "premium": [100.0, 200.0, 300.0]})


def _value_model(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """Add a ``v`` column equal to ``premium`` (identical across scenarios)."""
    return af.with_columns(pl.col("premium").alias("v"))


def test_progress_logs_percent_and_eta(
    af: ActuarialFrame, capsys: pytest.CaptureFixture[str]
) -> None:
    """progress=True logs percent and ETA on each batch; final batch shows N/N."""
    sink_id = logger.add(sys.stderr, level="INFO", format="{message}")
    try:
        for_each_scenario(
            af,
            scenarios=[f"S{i}" for i in range(6)],
            model_fn=_value_model,
            aggregations=(Sum("v").alias("total"),),
            batch_size=2,
            progress=True,
        )
    finally:
        logger.remove(sink_id)
    err = capsys.readouterr().err
    assert "%" in err  # percent shown every batch
    assert "ETA" in err  # ETA shown on the non-final batches
    assert "6/6" in err  # final batch still reports counts


def test_result_reports_n_batches(af: ActuarialFrame) -> None:
    """n_batches equals ceil(n_scenarios / batch_size) for an explicit batch size."""
    res = for_each_scenario(
        af,
        scenarios=[f"S{i}" for i in range(7)],
        model_fn=_value_model,
        aggregations=(Sum("v").alias("total"),),
        batch_size=3,
    )
    assert res.n_batches == math.ceil(7 / 3)  # batches [3, 3, 1] -> 3
    assert res.wall_time_s > 0


def test_scenariorun_streams(af: ActuarialFrame) -> None:
    """on_batch fires once per batch via ScenarioRun.run; final snapshot is complete."""
    plan = ScenarioRun(
        shocks={f"S{i}": [] for i in range(6)},
        base_tables={},
        aggregations=(Sum("v").alias("total"),),
    )
    snaps: list[BatchSnapshot] = []
    plan.run(af, _value_model, batch_size=2, on_batch=snaps.append)
    assert len(snaps) == 3
    assert snaps[-1].scenarios_done == 6


def test_scenariorun_streaming_is_live_channel_only(af: ActuarialFrame) -> None:
    """on_batch must not change the run's identity (live channel only)."""
    plan = ScenarioRun(
        shocks={f"S{i}": [] for i in range(4)},
        base_tables={},
        aggregations=(Sum("v").alias("total"),),
    )
    quiet = plan.run(af, _value_model, batch_size=2)
    streamed = plan.run(af, _value_model, batch_size=2, on_batch=lambda _s: None)
    assert quiet.plan_sha == streamed.plan_sha == plan.source_sha()


def test_live_run_elapsed_is_monotonic_and_completes(af: ActuarialFrame) -> None:
    """elapsed_s is positive and non-decreasing; final snapshot is complete."""
    snaps: list[BatchSnapshot] = []
    for_each_scenario(
        af,
        scenarios=[f"S{i}" for i in range(6)],
        model_fn=_value_model,
        aggregations=(Sum("v").alias("total"),),
        batch_size=2,
        on_batch=snaps.append,
    )
    assert len(snaps) == 3
    assert all(s.elapsed_s > 0 for s in snaps)
    elapsed = [s.elapsed_s for s in snaps]
    assert elapsed == sorted(elapsed)  # non-decreasing
    assert snaps[-1].fraction_done == 1.0
    assert snaps[-1].eta_s == 0.0


def test_scenariorun_raising_on_batch_does_not_abort(af: ActuarialFrame) -> None:
    """A raising on_batch must NOT abort ScenarioRun.run; result is still correct."""
    plan = ScenarioRun(
        shocks={f"S{i}": [] for i in range(3)},
        base_tables={},
        aggregations=(Sum("v").alias("total"),),
    )
    calls = {"n": 0}

    def _boom(_snap: BatchSnapshot) -> None:
        calls["n"] += 1
        msg = "hook exploded"
        raise RuntimeError(msg)

    res = plan.run(af, _value_model, batch_size=1, on_batch=_boom)
    assert calls["n"] == 3  # 3 scenarios at batch_size=1 -> 3 (failed) hook calls
    assert res.aggregations["total"] == pytest.approx(1800.0)  # 600 per scenario x 3
