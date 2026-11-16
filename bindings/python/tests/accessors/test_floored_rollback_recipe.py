# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A floored backward recursion has a core form, and ``accumulate`` names it.

``V[t] = MAX(0, (V[t+1] + cf[t]) / (1 + i[t]))`` -- a reserve zeroised when
it turns negative -- is not linear, so ``accumulate`` cannot carry it. The
``accumulate`` docstring used to stop there ("1.0 has no named form"), and an
agent believed it and built an accessor. The rollforward builder carries a
floor, and run over reversed lists it is the backward recursion: reverse the
cashflow and the one-period discount less one, add, grow, floor, and reverse
the balance back. Held here against a plain loop.
"""

from __future__ import annotations

import datetime
import random

import polars as pl

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.accessors.projection import ProjectionColumnAccessor

PERIODS = 12
POLICIES = 5


def _book() -> pl.DataFrame:
    rng = random.Random(20261111)  # noqa: S311 -- a reproducible sample, not a secret
    return pl.DataFrame(
        {
            "opening": [0.0] * POLICIES,
            "cf": [
                [rng.uniform(-100.0, 60.0) for _ in range(PERIODS)]
                for _ in range(POLICIES)
            ],
            "i": [[0.04] * PERIODS for _ in range(POLICIES)],
        }
    )


def _loop(cf: list[float], i: list[float]) -> list[float]:
    """Return the workbook's column: each row reads the row below, floored at nought."""
    reserve, out = 0.0, [0.0] * PERIODS
    for t in range(PERIODS - 1, -1, -1):
        reserve = max(0.0, (reserve + cf[t]) / (1.0 + i[t]))
        out[t] = reserve
    return out


def test_the_floored_rollback_recipe_matches_a_plain_loop() -> None:
    book = _book()
    af = ActuarialFrame(book).projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=PERIODS, frequency="monthly"
    )
    af.cf_back = af.cf.list.reverse()
    af.discount_less_one = (1.0 / (1.0 + af.i) - 1.0).list.reverse()
    plan = af.projection.rollforward(states={"reserve": af["opening"]})
    plan["reserve"].add(af["cf_back"], label="cashflow").grow(
        af["discount_less_one"], label="discount"
    ).floor(value=0.0)
    af.reserve_back = compile_rollforward(plan).expr_for("reserve")
    af.reserve = af.reserve_back.list.reverse()
    got = af.collect()["reserve"].to_list()

    floored = 0
    for cf, i, row in zip(book["cf"].to_list(), book["i"].to_list(), got, strict=True):
        want = _loop(cf, i)
        floored += sum(1 for value in want if value == 0.0)
        for a, b in zip(row, want, strict=True):
            assert abs(a - b) <= 1e-12 * max(1.0, abs(b))
    assert floored > 0, "the floor never bit, so this proves nothing about it"
    tiers = af.graph.tiers()
    assert tiers.engine_native == ()
    assert tiers.opaque == ()


def test_accumulate_points_a_floored_rollback_at_the_recipe() -> None:
    doc = " ".join((ProjectionColumnAccessor.accumulate.__doc__ or "").split())
    assert "has no named form" not in doc
    assert "floor(value=" in doc
    assert "list.reverse()" in doc
