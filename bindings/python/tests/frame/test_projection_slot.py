# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for ActuarialFrame._projection slot — preservation through frame operations."""

# ruff: noqa: S101, SLF001, D102, E501

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.schedule import Schedule


def _make_sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


class TestProjectionSlot:
    """The _projection slot exists on every ActuarialFrame and starts as None."""

    def test_default_is_none(self) -> None:
        af = ActuarialFrame({"id": ["P1"]})
        assert af._projection is None

    def test_set_via_helper(self) -> None:
        """The internal _set_projection helper updates the slot and returns a new frame."""
        af = ActuarialFrame({"id": ["P1"]})
        sched = _make_sched()
        new_af = af._set_projection(sched)
        # New frame has the slot; original unchanged
        assert new_af._projection is sched
        assert af._projection is None

    def test_preserved_through_with_columns(self) -> None:
        """with_columns returns a new frame that preserves the projection slot."""
        af = ActuarialFrame({"id": ["P1"], "x": [1.0]})
        sched = _make_sched()
        af = af._set_projection(sched)
        af2 = af.with_columns(pl.col("x").alias("y"))
        assert af2._projection is sched
