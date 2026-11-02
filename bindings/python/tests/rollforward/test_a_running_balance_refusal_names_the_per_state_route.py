# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Arithmetic over a running balance is refused with a move that can be made.

A rollforward op reads one bare column per period. Arithmetic over input
columns is refused with "work the expression out as a column of the frame
first", which is a move an actuary can make. A ``state@point`` read is a
running balance the machine computes: it has no column until the machine has
run, so the same advice names the impossible. That shape is nearly always a
probability moving between states -- healthy to sick at an intensity -- and
the route that works there is one ``accumulate()`` per state, so the refusal
names it. The route itself is run here to show it is a move that works.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward


def _two_state_builder(amount: pl.Expr) -> object:
    af = ActuarialFrame(
        pl.DataFrame({"p0": [1.0], "p1": [0.0], "h_mu01": [[0.01] * 3]})
    )
    af = af.projection.set(
        start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    b = af.projection.rollforward(states={"p0": af["p0"], "p1": af["p1"]})
    b["p0"].charge(af["h_mu01"])
    b["p1"].add(amount)
    return b


def _refusal(amount: pl.Expr) -> str:
    with pytest.raises(NotImplementedError) as refused:
        compile_rollforward(_two_state_builder(amount))  # type: ignore[arg-type]
    return str(refused.value)


def test_a_transfer_between_states_names_the_per_state_accumulate_route() -> None:
    msg = _refusal(pl.col("p0@bop") * pl.col("h_mu01"))
    assert "is an expression over 2 of them" in msg
    assert "'p0@bop' is a running balance the machine itself computes" in msg
    assert "no column until it has run" in msg
    assert "one projection.accumulate() per state" in msg
    assert "Work the expression out as a column of the frame" not in msg


def test_a_wrapped_balance_read_names_the_same_route() -> None:
    msg = _refusal(pl.col("p0@bop") * 0.01)
    assert "rather than a bare reference to 'p0@bop'" in msg
    assert "'p0@bop' is a running balance" in msg
    assert "Work the wrapping out as a column of the frame" not in msg


def test_arithmetic_over_input_columns_keeps_its_own_move() -> None:
    msg = _refusal(pl.col("h_mu01") * pl.col("h_mu01"))
    assert "Work the expression out as a column of the frame" in msg
    assert "running balance" not in msg


def test_the_route_the_refusal_names_runs() -> None:
    """Healthy then sick, each one accumulate(), equal to a plain Euler loop."""
    h, n, mu01, mu02, mu12 = 0.1, 20, 0.05, 0.01, 0.20
    af = ActuarialFrame(pl.DataFrame({"policy_id": ["A"]}))
    af = af.projection.set(n_periods=n, step_years=h)
    af.one = af.step * 0 + 1.0
    af.p0_after = af.one.projection.accumulate(
        initial=1.0, multiplier=1 - h * (mu01 + mu02), addend=0.0 * af.one
    )
    af.p0 = af.p0_after.projection.previous_period(fill_value=1.0)
    af.p1_after = af.one.projection.accumulate(
        initial=0.0, multiplier=1 - h * mu12, addend=h * mu01 * af.p0
    )
    af.p1 = af.p1_after.projection.previous_period(fill_value=0.0)
    out = af.collect()
    p0, p1 = [1.0], [0.0]
    for _ in range(n):
        p0.append(p0[-1] * (1 - h * (mu01 + mu02)))
        p1.append(p1[-1] * (1 - h * mu12) + h * mu01 * p0[-2])
    assert out["p0"].to_list()[0] == p0
    assert out["p1"].to_list()[0] == p1
    assert af.graph.tiers().engine_native == ()
