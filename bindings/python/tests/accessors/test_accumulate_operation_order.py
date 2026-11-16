# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""``accumulate`` and a workbook's order of operations.

``accumulate`` steps ``state * multiplier + addend``: one multiply, then one
add, and no fused multiply-add. A workbook row written in exactly that form is
matched bit for bit. A row that divides the running value first --
``(V + CF) / (1 + i) * p`` -- has to be refactored into a multiplier and an
addend to use it, and the refactoring rounds differently: last-bit
differences, about as close to the exact value as the sheet's own order.

An agent reconciling a workbook could not tell which of the two it was
seeing, so the docstring now says so. These tests hold both halves of what it says, and the
note itself.
"""

from __future__ import annotations

import datetime
import random

import pytest

from gaspatchio import ActuarialFrame, when

PERIODS = 60
POLICIES = 200


def _book(seed: int) -> dict[str, list[list[float]]]:
    """Return per-policy rates, persistency and cashflows over 60 periods."""
    rng = random.Random(seed)  # noqa: S311 -- a reproducible sample, not a secret
    return {
        "i": [
            [rng.uniform(0.0, 0.01) for _ in range(PERIODS)] for _ in range(POLICIES)
        ],
        "p": [
            [rng.uniform(0.95, 1.0) for _ in range(PERIODS)] for _ in range(POLICIES)
        ],
        "cf": [
            [rng.uniform(-50.0, 100.0) for _ in range(PERIODS)] for _ in range(POLICIES)
        ],
    }


@pytest.mark.parametrize("reverse", [False, True])
def test_a_row_written_as_prev_times_m_plus_a_matches_a_hand_loop_bit_for_bit(
    reverse: bool,  # noqa: FBT001 -- pytest parameter
) -> None:
    """A sheet row ``=prev*m + a`` and ``accumulate`` agree in every bit."""
    book = _book(20261111)
    m = [[1.0 + r for r in row] for row in book["i"]]
    a = book["cf"]
    af = ActuarialFrame({"m": m, "a": a, "v0": [100.0] * POLICIES})
    af.v = af.m.projection.accumulate(
        initial=af.v0, multiplier=af.m, addend=af.a, reverse=reverse
    )
    got = af.collect()["v"].to_list()

    for row_m, row_a, row_got in zip(m, a, got, strict=True):
        order = range(PERIODS - 1, -1, -1) if reverse else range(PERIODS)
        state, want = 100.0, [0.0] * PERIODS
        for t in order:
            state = state * row_m[t] + row_a[t]
            want[t] = state
        assert row_got == want


def test_a_divide_first_row_differs_in_the_last_bits_only() -> None:
    """``(V + CF) / (1 + i) * p``, refactored, is close but not bit for bit.

    The docstring promises last-bit differences and points a strict
    comparison at an ulp or relative tolerance. This pins both: some values
    differ, none by more than 1e-12 relative after 60 steps back.
    """
    book = _book(20261110)
    af = ActuarialFrame(book)
    af.m = af.p / (1.0 + af.i)
    af.a = af.cf * af.p / (1.0 + af.i)
    af.v = af.m.projection.accumulate(
        initial=0.0, multiplier=af.m, addend=af.a, reverse=True
    )
    got = af.collect()["v"].to_list()

    differing, worst_rel = 0, 0.0
    for row_i, row_p, row_cf, row_got in zip(
        book["i"], book["p"], book["cf"], got, strict=True
    ):
        state = 0.0
        for t in range(PERIODS - 1, -1, -1):
            state = (state + row_cf[t]) / (1.0 + row_i[t]) * row_p[t]
            if row_got[t] != state:
                differing += 1
                worst_rel = max(worst_rel, abs(row_got[t] - state) / abs(state))

    assert differing > 0, (
        "the refactored order now matches bit for bit; update the docstring"
    )
    assert worst_rel <= 1e-12


def test_the_docstring_says_when_a_workbook_is_matched_exactly() -> None:
    """The note an agent reconciling against a workbook needs is on the method."""
    from gaspatchio.accessors.projection import ProjectionColumnAccessor

    doc = " ".join((ProjectionColumnAccessor.accumulate.__doc__ or "").split())
    assert "bit for bit only when the row is literally" in doc
    assert "(V + CF) / (1 + i) * p" in doc
    assert "unrolled" in doc
    assert "ulp" in doc


def test_the_unroll_advice_says_where_it_stops_working() -> None:
    """Unrolling is for short runs: the docstring gives the limit and its cost.

    A room's agent followed the advice to unroll one column per period on a
    2,947-period model and ran out of memory at 12 GB: each unrolled period
    is its own column, and memory grows with the square of the period count.
    """
    from gaspatchio.accessors.projection import ProjectionColumnAccessor

    doc = " ".join((ProjectionColumnAccessor.accumulate.__doc__ or "").split())
    assert "a few dozen periods" in doc
    assert "square of the period count" in doc
    assert "1.7 GB at 480" in doc


def _forces() -> list[float]:
    """Return 60 forces whose Euler step is stable, then 60 where it is not.

    A multi-state sheet stepping ``x + h * (c - mu * x)`` forward is unstable
    once ``h * mu`` passes 2: the step multiplier ``1 - h * mu`` is then below
    -1, and any rounding difference grows by its size every period.
    """
    return [3.0] * PERIODS + [36.0] * PERIODS  # h * mu = 0.25, then 3


def test_an_unstable_recurrence_holds_no_tolerance() -> None:
    """Once a multiplier exceeds 1 in size, the two orders part by far more than 1e-12.

    The sheet's row is ``x + h * (mu * s - mu * x)``, started at its fixed
    point ``s``, so the exact answer is ``s`` in every period. ``accumulate``
    takes the row as ``x * (1 - h * mu) + h * mu * s``. While
    ``|1 - h * mu| <= 1`` its rounding dies away; past that it grows, and a
    multi-state room found percent-level gaps on a workbook's late rows. So the
    docstring stopped promising the tolerance there.
    """
    h, s = 1.0 / 12.0, 0.3
    mu = _forces()
    af = ActuarialFrame({"mu": [mu], "x0": [s]})
    af.x = af.mu.projection.accumulate(
        initial=af.x0, multiplier=1.0 - h * af.mu, addend=h * af.mu * s
    )
    got = af.collect()["x"].to_list()[0]

    state, worst_stable, worst_unstable = s, 0.0, 0.0
    for t, rate in enumerate(mu):
        state = state + h * (rate * s - rate * state)
        rel = abs(got[t] - state) / abs(state)
        if abs(1.0 - h * rate) <= 1.0:
            worst_stable = max(worst_stable, rel)
        else:
            worst_unstable = max(worst_unstable, rel)

    assert worst_stable <= 1e-12
    assert worst_unstable > 1e-2, (
        "the unstable tail no longer diverges; revisit the note"
    )


def test_the_docstring_withdraws_the_tolerance_for_an_unstable_recurrence() -> None:
    """The note says when the tolerance holds, and what to say when it cannot."""
    from gaspatchio.accessors.projection import ProjectionColumnAccessor

    doc = " ".join((ProjectionColumnAccessor.accumulate.__doc__ or "").split())
    assert "at most 1 in size" in doc
    assert "no tolerance holds" in doc
    assert "rounding, not a result" in doc


def test_the_sheet_order_sweep_reproduces_an_unstable_sheet_bit_for_bit() -> None:
    """The recipe the docstring names matches a plain loop in every cell.

    Sweeping ``x[t] = x[t-1] + h * (c[t-1] - mu[t-1] * x[t-1])`` over the
    whole timeline once per period makes period ``k`` exact after ``k``
    sweeps; ``materialize()`` every 32 sweeps keeps the plan small. Held here
    across the unstable stretch, where ``accumulate`` parts from the sheet.
    """
    h, s = 1.0 / 12.0, 0.3
    mu = _forces()
    n = len(mu) - 1
    af = ActuarialFrame({"mu": [mu], "c": [[rate * s for rate in mu]], "x0": [s]})
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=n, frequency="monthly"
    )
    af.h = h
    af.mu_prev = af.mu.projection.previous_period()
    af.c_prev = af.c.projection.previous_period()
    af.x = when(af.month == 0).then(af.x0).otherwise(0.0)
    for sweep in range(n):
        prior = af.x.projection.previous_period()
        af.x = (
            when(af.month == 0)
            .then(af.x0)
            .otherwise(prior + af.h * (af.c_prev - af.mu_prev * prior))
        )
        if (sweep + 1) % 32 == 0:
            af.materialize()
    got = af.collect()["x"].to_list()[0]

    state, want = s, [s]
    for t in range(n):
        state = state + h * (mu[t] * s - mu[t] * state)
        want.append(state)
    assert got == want


def test_the_docstring_names_the_sweep_and_its_cost() -> None:
    """The recipe is offered for a handful of policies, with what it costs."""
    from gaspatchio.accessors.projection import ProjectionColumnAccessor

    doc = " ".join((ProjectionColumnAccessor.accumulate.__doc__ or "").split())
    assert "handful of policies" in doc
    assert "af.materialize()" in doc
    assert "it is not a way to run a book" in doc
