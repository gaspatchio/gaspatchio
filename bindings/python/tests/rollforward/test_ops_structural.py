# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Op classes — structural family (Ratchet, Floor, Apply)."""

from __future__ import annotations

import polars as pl

from gaspatchio_core.rollforward._ops import Apply, Floor, Op, Ratchet
from gaspatchio_core.rollforward._refs import StateRef


class TestRatchet:
    def test_construction(self) -> None:
        op = Ratchet(
            target=StateRef(state="guarantee", point="eop"),
            to=pl.col("av_post_growth"),
            when=pl.col("anniversary_mask"),
            label="GMDB ratchet",
        )
        assert op.label == "GMDB ratchet"
        assert isinstance(op, Op)

    def test_when_can_be_none_for_unconditional_ratchet(self) -> None:
        # HWM-style lookback ratchet — no gate
        op = Ratchet(
            target=StateRef(state="hwm", point="eop"),
            to=pl.col("av_eop"),
            when=None,
            label="HWM",
        )
        assert op.when is None


class TestFloor:
    def test_construction(self) -> None:
        op = Floor(target=StateRef(state="av", point="eop"), value=0.0)
        assert op.value == 0.0
        assert isinstance(op, Op)


class TestApply:
    def test_construction(self) -> None:
        # Apply is the escape hatch — body is any pl.Expr
        op = Apply(
            target=StateRef(state="av", point="eop"),
            body=pl.col("av") + pl.col("adjustment"),
            label="Custom adjustment",
        )
        assert op.label == "Custom adjustment"
        assert isinstance(op, Op)
