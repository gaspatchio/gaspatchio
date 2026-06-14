# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""State-handle method chaining tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._ops import Add, Charge, Subtract
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def builder() -> RollforwardBuilder:
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )
    return RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)


class TestAdd:
    def test_add_emits_op_with_default_eop_target(
        self,
        builder: RollforwardBuilder,
    ) -> None:
        builder["av"].add(pl.col("premium"), label="Premium")
        assert len(builder._transitions) == 1
        op = builder._transitions[0]
        assert isinstance(op, Add)
        assert op.target.state == "av"
        assert op.target.point == "eop"
        assert op.label == "Premium"

    def test_chained_add_calls_all_emit(self, builder: RollforwardBuilder) -> None:
        builder["av"].add(pl.col("p1"), label="A").add(pl.col("p2"), label="B")
        assert len(builder._transitions) == 2
        assert builder._transitions[0].label == "A"
        assert builder._transitions[1].label == "B"


class TestSubtract:
    def test_subtract_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].subtract(pl.col("withdrawal"), label="W")
        assert isinstance(builder._transitions[0], Subtract)


class TestCharge:
    def test_charge_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].charge(pl.col("expense"), label="E")
        assert isinstance(builder._transitions[0], Charge)


class TestUnknownState:
    def test_indexing_unknown_state_raises(self, builder: RollforwardBuilder) -> None:
        with pytest.raises(KeyError, match="unknown state 'guarantee'"):
            builder["guarantee"].add(pl.col("x"))


from gaspatchio_core.rollforward._ops import (  # noqa: E402
    Apply,
    DeductNAR,
    Floor,
    Grow,
    GrowCapped,
    Ratchet,
)


class TestGrow:
    def test_grow_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].grow(pl.col("rate"), label="Interest")
        assert isinstance(builder._transitions[0], Grow)


class TestGrowCapped:
    def test_grow_capped_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].grow_capped(
            pl.col("rate"),
            floor=pl.lit(0.0),
            cap=pl.lit(0.10),
            label="IUL",
        )
        op = builder._transitions[0]
        assert isinstance(op, GrowCapped)
        assert op.label == "IUL"


class TestDeductNAR:
    def test_deduct_nar_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].deduct_nar(
            pl.col("coi_rate"),
            death_benefit=pl.col("db"),
            label="COI",
        )
        op = builder._transitions[0]
        assert isinstance(op, DeductNAR)


class TestRatchet:
    def test_ratchet_with_when_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].ratchet(
            to=pl.col("hwm"),
            when=pl.col("anniversary"),
            label="R",
        )
        op = builder._transitions[0]
        assert isinstance(op, Ratchet)
        assert op.when is not None

    def test_ratchet_without_when_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].ratchet(to=pl.col("hwm"), label="HWM")
        assert builder._transitions[0].when is None


class TestFloor:
    def test_floor_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].floor(0.0)
        assert isinstance(builder._transitions[0], Floor)
        assert builder._transitions[0].value == 0.0


class TestApply:
    def test_apply_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].apply(pl.col("av") + pl.col("custom"), label="Custom")
        op = builder._transitions[0]
        assert isinstance(op, Apply)
        assert op.label == "Custom"
