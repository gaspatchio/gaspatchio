# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test the cgroup-aware memory budget seam."""

from __future__ import annotations

import pytest


def test_memory_budget_bytes_is_cgroup_aware(monkeypatch):
    from gaspatchio_core.scenarios import _auto_batch, _memory

    # memory_budget_bytes must route through _memory.memory_budget (cgroup-aware),
    # NOT psutil.virtual_memory().available directly.
    seen = {}

    def fake_budget(fraction, **kw):
        seen["fraction"] = fraction
        return 4_000_000_000

    monkeypatch.setattr(_memory, "memory_budget", fake_budget)
    out = _auto_batch.memory_budget_bytes(target_memory_fraction=0.5)
    assert out == 4_000_000_000
    assert seen["fraction"] == 0.5


def _patch_budget(monkeypatch, budget_bytes):
    from gaspatchio_core.scenarios import _auto_batch

    monkeypatch.setattr(_auto_batch, "memory_budget_bytes", lambda _f: budget_bytes)


def test_size_to_budget_clamps_to_n_items(monkeypatch):
    from gaspatchio_core.scenarios._auto_batch import size_to_budget

    _patch_budget(monkeypatch, 10_000_000_000)  # huge budget
    assert size_to_budget(1000, 50) == 50  # whole portfolio fits in one batch


def test_size_to_budget_is_budget_bound(monkeypatch):
    from gaspatchio_core.scenarios._auto_batch import size_to_budget

    # budget=1300, per_cell=100, margin=1.3 -> denom=130 -> B=10
    _patch_budget(monkeypatch, 1300)
    assert size_to_budget(100, 1000, safety_margin=1.3) == 10


def test_size_to_budget_margin_shrinks_b(monkeypatch):
    from gaspatchio_core.scenarios._auto_batch import size_to_budget

    _patch_budget(monkeypatch, 1000)
    assert size_to_budget(100, 1000, safety_margin=1.0) == 10
    assert size_to_budget(100, 1000, safety_margin=2.0) == 5


def test_size_to_budget_runs_single_item_that_fits_raw(monkeypatch):
    from gaspatchio_core.scenarios._auto_batch import size_to_budget

    # one 100-byte item fits the raw budget of 120, but 100*1.3=130 > 120 -> still B=1
    _patch_budget(monkeypatch, 120)
    assert size_to_budget(100, 10, safety_margin=1.3) == 1


def test_size_to_budget_raises_when_one_item_exceeds_raw(monkeypatch):
    from gaspatchio_core.scenarios import _memory
    from gaspatchio_core.scenarios._auto_batch import size_to_budget

    _patch_budget(monkeypatch, 50)  # one 100-byte item exceeds even the raw budget
    with pytest.raises(_memory.IrreducibleCellError):
        size_to_budget(100, 10)


def test_bounded_seed_size_caps_at_sample_cap():
    from gaspatchio_core.scenarios._auto_batch import bounded_seed_size
    from gaspatchio_core.scenarios._memory import DEFAULTS

    # Large n: the seed is CAPPED, never 10% of n (which would OOM as one collect).
    assert bounded_seed_size(10_000_000) == DEFAULTS.seed_sample_cap
    assert bounded_seed_size(10_000_000) < 10_000_000 // 10


def test_bounded_seed_size_uses_ten_percent_for_small_n():
    from gaspatchio_core.scenarios._auto_batch import bounded_seed_size

    assert bounded_seed_size(1000) == 100  # 10% when that is below the cap


def test_bounded_seed_size_at_least_one():
    from gaspatchio_core.scenarios._auto_batch import bounded_seed_size

    assert bounded_seed_size(1) == 1
    assert bounded_seed_size(5) == 1  # 5 // 10 == 0 -> floored to 1
