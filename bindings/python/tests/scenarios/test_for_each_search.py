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
