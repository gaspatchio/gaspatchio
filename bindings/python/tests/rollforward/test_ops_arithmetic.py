# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Op classes — arithmetic family (Add, Subtract, Charge)."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.rollforward._ops import (
    Add,
    Apply,
    Charge,
    Floor,
    Grow,
    Op,
    Subtract,
)
from gaspatchio_core.rollforward._refs import StateRef


class TestAdd:
    def test_construction(self) -> None:
        op = Add(
            target=StateRef(state="av", point="post_premium"),
            expr=pl.col("premium"),
            label="Premium",
        )
        assert op.target.state == "av"
        assert op.label == "Premium"
        assert isinstance(op, Op)

    def test_equality_via_canonical_string(self) -> None:
        # Polars overloads pl.Expr.__eq__ to return another Expr, so the
        # dataclass auto-generated __eq__ raises TypeError on Ops with pl.Expr
        # fields. IR comparison goes through str(expr) in _canonical.py instead.
        a = Add(target=StateRef(state="av", point="eop"), expr=pl.col("x"), label="L")
        b = Add(target=StateRef(state="av", point="eop"), expr=pl.col("x"), label="L")
        assert a.target == b.target
        assert a.label == b.label
        assert str(a.expr) == str(b.expr)

    def test_label_can_be_none(self) -> None:
        op = Add(target=StateRef(state="av", point="eop"), expr=pl.col("x"), label=None)
        assert op.label is None

    def test_is_frozen(self) -> None:
        op = Add(target=StateRef(state="av", point="eop"), expr=pl.col("x"), label="L")
        with pytest.raises(Exception):
            op.label = "new"  # type: ignore[misc]


class TestSubtract:
    def test_construction(self) -> None:
        op = Subtract(
            target=StateRef(state="av", point="after_payment"),
            expr=pl.col("withdrawal"),
            label="Withdrawal",
        )
        assert op.label == "Withdrawal"
        assert isinstance(op, Op)


class TestCharge:
    def test_construction(self) -> None:
        op = Charge(
            target=StateRef(state="av", point="eop"),
            rate=pl.col("expense_rate"),
            label="Expenses",
        )
        assert op.label == "Expenses"
        assert isinstance(op, Op)


class TestVerify:
    def test_floor_with_non_eop_target_warns_via_verify(self) -> None:
        # Floor is permitted at any point, no validation failure
        Floor(target=StateRef(state="av", point="post_coi"), value=0.0).verify()

    def test_charge_with_negative_rate_literal_raises_in_verify(self) -> None:
        op = Charge(
            target=StateRef(state="av", point="eop"),
            rate=pl.lit(-0.05),  # negative literal — almost certainly a bug
            label="Bad",
        )
        with pytest.raises(ValueError, match="negative literal rate"):
            op.verify()

    def test_grow_with_zero_rate_literal_is_allowed(self) -> None:
        # 0% growth is meaningful (e.g., locked-in zero curve)
        op = Grow(
            target=StateRef(state="av", point="eop"),
            rate=pl.lit(0.0),
            label="Locked zero",
        )
        op.verify()

    def test_apply_verify_is_noop(self) -> None:
        # Apply's body is the user's responsibility; verify() doesn't peek inside
        op = Apply(
            target=StateRef(state="av", point="eop"),
            body=pl.col("av"),
            label="Custom",
        )
        op.verify()
