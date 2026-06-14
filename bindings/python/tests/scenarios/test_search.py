# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the pure streaming-batch search selector (build_ladder + decide_winner)."""

from __future__ import annotations

import pytest

from gaspatchio_core.scenarios._memory import IrreducibleCellError
from gaspatchio_core.scenarios._result import ProbeResult
from gaspatchio_core.scenarios._search import build_ladder, decide_winner


def _probe(
    batch: int,
    per_sc: float,
    peak: float,
    engine: str = "streaming",
) -> ProbeResult:
    return ProbeResult(
        batch=batch, engine=engine, per_sc_s=per_sc, peak_mb=peak, fits=True  # type: ignore[arg-type]
    )


def test_build_ladder_caps_at_n_and_ceiling() -> None:
    """build_ladder returns only rungs <= min(n_scenarios, ceiling)."""
    assert build_ladder(n_scenarios=1000, ladder=(1, 4, 16, 64), ceiling=256) == [
        1, 4, 16, 64
    ]
    assert build_ladder(n_scenarios=10, ladder=(1, 4, 16, 64), ceiling=256) == [1, 4]
    assert build_ladder(n_scenarios=2, ladder=(1, 4, 16, 64), ceiling=256) == [1]
    assert build_ladder(n_scenarios=1000, ladder=(1, 4, 16, 64), ceiling=8) == [1, 4]


def test_decide_winner_picks_fastest_fitting() -> None:
    """decide_winner picks the rung with the lowest per_sc_s among those that fit."""
    probed = [
        _probe(1, 0.50, 100),
        _probe(4, 0.20, 300),
        _probe(16, 0.05, 900),
        _probe(64, 0.06, 3000),
    ]
    win = decide_winner(probed, budget_mb=8000, safety_margin=1.3, floor=None)
    assert win.engine == "streaming"
    assert win.batch == 16
    assert win.reason == "fastest_fitting"


def test_decide_winner_excludes_over_budget_rungs() -> None:
    """Rungs whose peak * margin exceeds the budget are excluded from consideration."""
    probed = [
        _probe(1, 0.50, 100),
        _probe(4, 0.20, 300),
        _probe(16, 0.05, 5000),
    ]
    win = decide_winner(probed, budget_mb=4000, safety_margin=1.3, floor=None)
    assert win.batch == 4
    assert win.reason == "fastest_fitting"


def test_decide_winner_uses_floor_when_no_streaming_fits() -> None:
    """Falls to the in-memory floor when all streaming rungs exceed the budget."""
    probed = [_probe(1, 0.50, 9000)]
    floor = ProbeResult(
        batch=1, engine="in-memory", per_sc_s=1.2, peak_mb=4000, fits=True
    )
    win = decide_winner(probed, budget_mb=6000, safety_margin=1.3, floor=floor)
    assert win.engine == "in-memory"
    assert win.batch == 1
    assert win.reason == "floor"


def test_decide_winner_raises_when_nothing_fits() -> None:
    """IrreducibleCellError raised when neither streaming nor the floor fits."""
    probed = [_probe(1, 0.50, 9000)]
    floor = ProbeResult(
        batch=1, engine="in-memory", per_sc_s=1.2, peak_mb=9000, fits=False
    )
    with pytest.raises(IrreducibleCellError):
        decide_winner(probed, budget_mb=6000, safety_margin=1.3, floor=floor)
