# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Op classes — time-aware family (Grow, GrowCapped, DeductNAR)."""

from __future__ import annotations

import polars as pl

from gaspatchio_core.rollforward._ops import DeductNAR, Grow, GrowCapped, Op
from gaspatchio_core.rollforward._refs import StateRef


class TestGrow:
    def test_construction(self) -> None:
        op = Grow(
            target=StateRef(state="av", point="eop"),
            rate=pl.col("interest_rate"),
            label="Interest",
        )
        assert op.label == "Interest"
        assert isinstance(op, Op)


class TestGrowCapped:
    def test_construction(self) -> None:
        op = GrowCapped(
            target=StateRef(state="av", point="eop"),
            rate=pl.col("index_return"),
            floor=pl.lit(0.0),
            cap=pl.lit(0.10),
            label="Indexed credit",
        )
        assert op.label == "Indexed credit"
        assert isinstance(op, Op)


class TestDeductNAR:
    def test_construction(self) -> None:
        op = DeductNAR(
            target=StateRef(state="av", point="post_coi"),
            coi_rate=pl.col("coi_rate"),
            death_benefit=pl.col("sum_assured"),
            label="COI",
        )
        assert op.label == "COI"
        assert isinstance(op, Op)
