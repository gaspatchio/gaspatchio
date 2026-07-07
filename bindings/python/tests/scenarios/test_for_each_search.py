# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for batch_size="auto" driven by the measured streaming-batch search.
# ABOUTME: Covers selection recording and checksum-equivalence vs a manual batch.
"""Test the measured streaming-batch search behind ``batch_size='auto'``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import Sum, for_each_scenario

if TYPE_CHECKING:
    from gaspatchio_core.scenarios._result import ScenarioResult


def _af(n_policies: int = 200) -> ActuarialFrame:
    """Build a small ActuarialFrame with a constant value column."""
    return ActuarialFrame(
        pl.DataFrame({"policy_id": range(n_policies), "v": [1.0] * n_policies})
    )


def _model_fn(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """Double the value column into ``payoff``."""
    af.payoff = af.v * 2.0
    return af


def _checksum(res: ScenarioResult) -> float:
    """Sum every non-key column of the partitioned output for a stable checksum."""
    frame = res.aggregations["total"]
    return round(
        sum(float(frame[c].sum()) for c in frame.columns if c != "scenario_id"), 6
    )


def test_auto_search_resolves_and_records_selection() -> None:
    """An auto run resolves via the search and records the probe ladder."""
    r = for_each_scenario(
        _af(),
        scenarios=list(range(1, 41)),
        model_fn=_model_fn,
        aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
        batch_size="auto",
    )
    assert r.batch_size_resolution == "auto_search"
    assert r.selection is not None
    assert r.selection.engine in ("streaming", "in-memory")
    assert len(r.selection.probed) >= 1
    streaming_batches = [p.batch for p in r.selection.probed if p.engine == "streaming"]
    assert streaming_batches[0] == 1


def test_auto_search_matches_manual_checksum() -> None:
    """The auto search produces a bit-equivalent result to a manual batch size."""
    agg = (Sum("payoff").alias("total").over("scenario_id"),)
    auto = for_each_scenario(
        _af(),
        scenarios=list(range(1, 41)),
        model_fn=_model_fn,
        aggregations=agg,
        batch_size="auto",
    )
    manual = for_each_scenario(
        _af(),
        scenarios=list(range(1, 41)),
        model_fn=_model_fn,
        aggregations=agg,
        batch_size=8,
    )
    assert _checksum(auto) == _checksum(manual)


def test_master_seed_forces_engine_only_search():
    """master_seed forces batch_size=1; the search becomes an engine-only choice."""
    r = for_each_scenario(
        _af(),
        scenarios=list(range(1, 11)),
        model_fn=_model_fn,
        aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
        batch_size="auto",
        master_seed=123,
    )
    assert r.batch_size == 1
    assert r.batch_size_resolution == "auto_search"
    assert r.selection is not None
    assert r.selection.reason == "forced_b1"
    assert {p.engine for p in r.selection.probed} == {"streaming", "in-memory"}


def test_single_scenario_uses_in_memory_floor():
    """N==1 runs once on the in-memory floor (no search, no spurious raise)."""
    r = for_each_scenario(
        _af(),
        scenarios=[1],
        model_fn=_model_fn,
        aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
        batch_size="auto",
    )
    assert r.batch_size == 1
    assert r.selection is not None
    assert r.selection.reason == "single_scenario"
    assert r.selection.engine == "in-memory"
    # 200 policies * payoff 2.0 = 400 for the single scenario.
    assert _checksum(r) == 400.0


def test_forced_b1_raises_when_neither_engine_fits(monkeypatch):
    """Forced-b1 with a remainder that no engine fits raises the hard ceiling."""
    import pytest

    from gaspatchio_core.scenarios import _for_each
    from gaspatchio_core.scenarios._memory import IrreducibleCellError

    monkeypatch.setattr(_for_each, "memory_budget_bytes", lambda *a, **k: 1)  # 1-byte budget
    with pytest.raises(IrreducibleCellError):
        for_each_scenario(
            _af(),
            scenarios=list(range(1, 6)),  # N=5 > 2 probed -> remainder exists
            model_fn=_model_fn,
            aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
            batch_size="auto",
            master_seed=7,
        )


def test_auto_search_hard_ceiling_raises_when_remainder_cannot_fit(monkeypatch):
    """Auto path: a remainder that no streaming rung nor the in-mem floor fits raises."""
    import pytest

    from gaspatchio_core.scenarios import _for_each
    from gaspatchio_core.scenarios._memory import IrreducibleCellError

    monkeypatch.setattr(_for_each, "memory_budget_bytes", lambda *a, **k: 1)  # 1-byte budget
    with pytest.raises(IrreducibleCellError):
        for_each_scenario(
            _af(),
            scenarios=list(range(1, 6)),  # N=5: probes leave an un-folded remainder
            model_fn=_model_fn,
            aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
            batch_size="auto",
        )


def _patch_constant_peak(monkeypatch, peak_mb: float) -> None:
    """Make every batch collect report a fixed synthetic transient peak.

    Collections still run for real (tiny frames), so folds stay correct; only
    the measured peak is synthetic, which lets a test place each ladder rung
    deterministically above or below the budget.
    """
    from gaspatchio_core.scenarios import _for_each

    real = _for_each._collect_with_peak  # noqa: SLF001

    def fake(lazy, *, engine=None):
        frame, _ = real(lazy, engine=engine)
        return frame, int(peak_mb * 1024**2)

    monkeypatch.setattr(_for_each, "_collect_with_peak", fake)


def test_gate_skips_rung_predicted_over_budget(monkeypatch):
    """A rung whose linearly-extrapolated peak busts the budget is never probed.

    This is the kernel-OOM regression guard: with b=1 measured at 100 MB against a
    200 MB budget, b=4 predicts 400 MB * 1.3 > 200 MB. The old search ran that
    probe anyway (and died when the real rung exceeded physical memory); the gate
    must stop the ladder at b=1 without ever launching b=4.
    """
    from gaspatchio_core.scenarios import _for_each

    _patch_constant_peak(monkeypatch, 100.0)  # every collect "peaks" at 100 MB
    monkeypatch.setattr(
        _for_each, "memory_budget_bytes", lambda *a, **k: 200 * 1024**2
    )  # 100*1.3 <= 200 fits; predicted 400*1.3 > 200 must gate b=4

    r = for_each_scenario(
        _af(),
        scenarios=list(range(1, 41)),
        model_fn=_model_fn,
        aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
        batch_size="auto",
    )
    assert r.selection is not None
    streaming = [p for p in r.selection.probed if p.engine == "streaming"]
    assert [p.batch for p in streaming] == [1]  # b=4 was gated, not probed
    assert r.batch_size == 1
    assert r.selection.engine == "streaming"
    # 40 scenarios * 200 policies * payoff 2.0 -- the run still completes correctly.
    assert _checksum(r) == 40 * 400.0


def test_gate_allows_rungs_predicted_within_budget(monkeypatch):
    """A generous budget gates nothing: the full ladder is still probed."""
    from gaspatchio_core.scenarios import _for_each

    _patch_constant_peak(monkeypatch, 100.0)
    monkeypatch.setattr(
        _for_each, "memory_budget_bytes", lambda *a, **k: 10 * 1024**3
    )  # 10 GB: every predicted rung fits

    r = for_each_scenario(
        _af(),
        scenarios=list(range(1, 41)),  # ladder for n=40 -> [1, 4, 16]
        model_fn=_model_fn,
        aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
        batch_size="auto",
    )
    assert r.selection is not None
    streaming = [p.batch for p in r.selection.probed if p.engine == "streaming"]
    assert streaming == [1, 4, 16]
    assert _checksum(r) == 40 * 400.0


def test_gate_prediction_includes_streaming_batch_inflation(monkeypatch):
    """The gate predicts super-linearly: linear-alone would probe, inflated skips.

    Field regression guard: on the CI 10sc x 100K cell, b=1 measured ~1.3 GB
    against a 7.7 GB budget -- a bare linear gate predicted b=4 within budget and
    launched a probe that demanded ~11.5 GB (8.6x the b=1 rung; Polars #20786
    cross-join inflation) and killed the 16 GB runner. With peak=100 MB and a
    1 GB budget, linear predicts 100*4*1.3 = 520 MB (would probe b=4); inflated
    predicts 100*4*3.0*1.3 = 1560 MB (must skip).
    """
    from gaspatchio_core.scenarios import _for_each

    _patch_constant_peak(monkeypatch, 100.0)
    monkeypatch.setattr(
        _for_each, "memory_budget_bytes", lambda *a, **k: 1024**3
    )  # 1 GB: fits b=1 (100*1.3), passes a bare-linear b=4 gate, fails the inflated one

    r = for_each_scenario(
        _af(),
        scenarios=list(range(1, 41)),
        model_fn=_model_fn,
        aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
        batch_size="auto",
    )
    assert r.selection is not None
    streaming = [p.batch for p in r.selection.probed if p.engine == "streaming"]
    assert streaming == [1]  # b=4 gated by the inflation factor, never probed
    assert r.batch_size == 1
    assert _checksum(r) == 40 * 400.0
