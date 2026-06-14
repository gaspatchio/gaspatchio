# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for the for_each_scenario streaming-convergence on_batch hook.
# ABOUTME: Covers BatchSnapshot, probe isolation, partials, fail-open, progress.
"""Test the streaming-convergence ``on_batch`` framework hook."""

from __future__ import annotations

import math
import sys

import polars as pl
import pytest
from loguru import logger

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import (
    BatchSnapshot,
    PeriodQuantile,
    PeriodSum,
    Sum,
    for_each_scenario,
)


@pytest.fixture
def af() -> ActuarialFrame:
    """Three-policy ActuarialFrame used across the streaming suite."""
    return ActuarialFrame({"policy_id": [1, 2, 3], "premium": [100.0, 200.0, 300.0]})


def _value_model(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """Add a ``v`` column equal to ``premium`` (per-scenario, identical)."""
    return af.with_columns(pl.col("premium").alias("v"))


def test_frame_count_and_final_scenarios_done(af: ActuarialFrame) -> None:
    """on_batch fires ceil(n/batch) times; final snapshot's scenarios_done == n."""
    snaps: list[BatchSnapshot] = []
    n = 10
    batch_size = 3
    for_each_scenario(
        af,
        scenarios=[f"S{i}" for i in range(n)],
        model_fn=_value_model,
        aggregations=(Sum("v").alias("total"),),
        batch_size=batch_size,
        on_batch=snaps.append,
    )
    assert len(snaps) == math.ceil(n / batch_size)
    assert snaps[-1].scenarios_done == n
    assert snaps[-1].total_scenarios == n
    # batch_idx is the 0-based enumerate index.
    assert [s.batch_idx for s in snaps] == list(range(len(snaps)))
    # scenarios_done is cumulative and monotonic in batch-sized steps.
    assert [s.scenarios_done for s in snaps] == [3, 6, 9, 10]


def test_in_memory_request_reaches_collect(
    af: ActuarialFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resolved 'in-memory' batch must collect in-memory, not degrade to auto (#4)."""
    from gaspatchio_core.scenarios import _for_each

    seen: list[str | None] = []
    orig = _for_each._collect_with_peak  # noqa: SLF001

    def _spy(lazy: object, *, engine: str | None = None) -> object:
        seen.append(engine)
        return orig(lazy, engine=engine)

    monkeypatch.setattr(_for_each, "_collect_with_peak", _spy)
    # A single scenario takes the single_scenario path -> winner_engine="in-memory".
    for_each_scenario(
        af,
        scenarios=["S0"],
        model_fn=_value_model,
        aggregations=(Sum("v").alias("total"),),
    )
    assert "in-memory" in seen  # the request reached collect
    assert None not in seen  # it did NOT silently degrade to lazy.collect() = auto


def _product_model(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """cf[t] = value * (t+1) for t in 0..1 — a 2-period list column."""
    return af.with_columns(
        pl.concat_list([pl.col("value"), pl.col("value") * 2]).alias("cf"),
    )


def test_for_each_vector_over_tidy_and_reconciles() -> None:
    """for_each_scenario vector .over() is tidy and reconciles to the total (#6)."""
    af = ActuarialFrame(
        {
            "policy_id": [1, 2, 3, 4],
            "product": ["A", "A", "B", "B"],
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )
    parted = for_each_scenario(
        af,
        scenarios=["S0", "S1"],
        model_fn=_product_model,
        aggregations=(PeriodSum("cf").alias("cf").over("product"),),
        batch_size=1,
    )
    total = for_each_scenario(
        af,
        scenarios=["S0", "S1"],
        model_fn=_product_model,
        aggregations=(PeriodSum("cf").alias("cf"),),
        batch_size=1,
    )
    tidy = parted.aggregations["cf"]
    assert tidy.columns == ["product", "period", "cf"]
    recon = tidy.group_by("period").agg(pl.col("cf").sum()).sort("period")
    assert recon["cf"].to_list() == total.aggregations["cf"].tolist()


def test_for_each_period_quantile_over_not_supported() -> None:
    """PeriodQuantile.over() is deferred on for_each_scenario too (#6)."""
    af = ActuarialFrame(
        {"policy_id": [1, 2], "product": ["A", "B"], "value": [1.0, 2.0]}
    )
    with pytest.raises(NotImplementedError, match="PeriodQuantile"):
        for_each_scenario(
            af,
            scenarios=["S0"],
            model_fn=_product_model,
            aggregations=(PeriodQuantile("cf").alias("q").over("product"),),
        )


def test_auto_search_probes_fold_and_count_honestly(af: ActuarialFrame) -> None:
    """Under batch_size='auto' the search probes do real work and fold exactly once.

    The measured streaming-batch search runs its ladder rungs as real folded
    passes (no throwaway probes), so every batch -- probe or remainder -- fires
    on_batch. ``scenarios_done`` is strictly increasing, never exceeds n, the
    first probe folds exactly one scenario (the b=1 rung), and the final
    snapshot reaches exactly n (no double-counting).
    """
    snaps: list[BatchSnapshot] = []
    n = 8
    for_each_scenario(
        af,
        scenarios=[f"S{i}" for i in range(n)],
        model_fn=_value_model,
        aggregations=(Sum("v").alias("total"),),
        batch_size="auto",
        on_batch=snaps.append,
    )
    counts = [s.scenarios_done for s in snaps]
    # scenarios_done is strictly increasing and never exceeds n.
    assert all(0 < c <= n for c in counts)
    assert counts == sorted(counts)
    assert len(set(counts)) == len(counts)
    # First rung of the ladder is b=1, so the first fold counts exactly one.
    assert counts[0] == 1
    # Final fold reaches exactly n -- nothing re-folded or double-counted.
    assert counts[-1] == n


def test_running_partial_is_bit_exact(af: ActuarialFrame) -> None:
    """Running 'dist' partial after K batches == from-scratch K-scenario run.

    Uses a partitioned aggregator (``.over("scenario_id")``) whose snapshot
    output is a per-scenario DataFrame. The partial after K batches must be
    bit-identical to running the first K scenarios from scratch. Order-
    independent for ``.over`` (we sort), so the comparison is non-flaky.
    """
    snaps: list[BatchSnapshot] = []
    n = 9
    batch_size = 3
    sids = [f"S{i}" for i in range(n)]
    for_each_scenario(
        af,
        scenarios=sids,
        model_fn=_value_model,
        aggregations=(Sum("v").alias("dist").over("scenario_id"),),
        batch_size=batch_size,
        on_batch=snaps.append,
    )

    # After the k-th batch (0-based), scenarios_done == (k+1) * batch_size.
    for k, snap in enumerate(snaps):
        prefix_count = snap.scenarios_done
        scratch = for_each_scenario(
            af,
            scenarios=sids[:prefix_count],
            model_fn=_value_model,
            aggregations=(Sum("v").alias("dist").over("scenario_id"),),
            batch_size=batch_size,
        )
        running = snap.outputs["dist"].sort("scenario_id")
        from_scratch = scratch.aggregations["dist"].sort("scenario_id")
        assert running.equals(from_scratch), (
            f"batch {k}: running partial diverged from a "
            f"{prefix_count}-scenario from-scratch run"
        )


def test_raising_on_batch_does_not_abort(af: ActuarialFrame) -> None:
    """An on_batch that raises must NOT abort the run; result is still correct."""
    calls = {"n": 0}

    def _boom(_snap: BatchSnapshot) -> None:
        calls["n"] += 1
        msg = "user hook exploded"
        raise RuntimeError(msg)

    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=_value_model,
        aggregations=(Sum("v").alias("total"),),
        batch_size=1,
        on_batch=_boom,
    )
    # 3 scenarios at batch_size=1 -> 3 batches -> 3 (failed) hook calls.
    assert calls["n"] == 3
    # Run completed and produced the correct aggregate despite every hook raising.
    assert result.aggregations["total"] == pytest.approx(1800.0)
    assert result.n_scenarios == 3


def test_serial_path_fires_once_per_scenario(af: ActuarialFrame) -> None:
    """master_seed + batch_size=1 fires the hook once per scenario, 1,2,3,..."""
    snaps: list[BatchSnapshot] = []
    sids = ["X", "Y", "Z"]
    for_each_scenario(
        af,
        scenarios=sids,
        model_fn=_value_model,
        aggregations=(Sum("v").alias("total"),),
        master_seed=123,
        batch_size=1,
        on_batch=snaps.append,
    )
    assert len(snaps) == len(sids)
    assert [s.scenarios_done for s in snaps] == [1, 2, 3]


def test_progress_installs_default_logging_hook(
    af: ActuarialFrame,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """progress=True logs a 'scenarios done/total' line via loguru per batch."""
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

    captured = capsys.readouterr()
    assert "scenarios" in captured.err
    # 6 scenarios / batch 2 -> 3 batches -> final line reports 6/6.
    assert "6/6" in captured.err


def test_user_on_batch_wins_over_progress(af: ActuarialFrame) -> None:
    """If both progress=True and on_batch are set, the user's on_batch wins."""
    snaps: list[BatchSnapshot] = []
    for_each_scenario(
        af,
        scenarios=[f"S{i}" for i in range(6)],
        model_fn=_value_model,
        aggregations=(Sum("v").alias("total"),),
        batch_size=2,
        progress=True,
        on_batch=snaps.append,
    )
    # User hook fired for every real batch (the default progress hook did not
    # replace it).
    assert len(snaps) == 3
    assert snaps[-1].scenarios_done == 6


def test_no_on_batch_no_progress_unchanged(af: ActuarialFrame) -> None:
    """Without on_batch/progress, behaviour and ScenarioResult are unchanged."""
    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=_value_model,
        aggregations=(Sum("v").alias("total"),),
        batch_size=1,
    )
    assert result.aggregations["total"] == pytest.approx(1800.0)
    assert result.n_scenarios == 3
    assert result.batch_size == 1
    assert result.batch_size_resolution == "manual"
