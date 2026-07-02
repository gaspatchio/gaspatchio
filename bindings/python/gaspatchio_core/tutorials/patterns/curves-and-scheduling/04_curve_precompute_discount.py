# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Production discounting: pre-compute the DF vector once, broadcast it.

Discounting a projected cashflow stream against a yield curve is the core of any
BEL / PV calculation. The naive way — calling ``curve.discount_factor(af.t)`` on
a list *column* — works for a single-policy debug check but falls back to
``map_elements`` internally (~14x slower; defeats vectorisation), which the
framework's performance rules forbid for a portfolio run. This is the GSP-116
footgun.

The production pattern sidesteps it entirely. The curve is static and, on a
shared uniform schedule, **every policy shares the same ``t`` grid** — so the
discount-factor vector is identical for all policies. Compute it **once** in
Python from ``Schedule.cumulative_year_fractions()``, then broadcast it as a
Polars list literal: zero per-row work, no ``map_elements`` in the lazy graph.

  t_years = sched.cumulative_year_fractions()          # Python list[float]
  disc    = curve.discount_factor(t_years)             # computed ONCE -> list[float]
  af.discount_factor = pl.lit(disc, dtype=pl.List(...)) # broadcast literal
  af.pv = (af.net_cf * af.discount_factor).list.sum()  # element-wise, vectorised

This script proves the broadcast PV is correct by reconstructing it
independently in plain Python from the same DF vector and the same known
``net_cf`` — no Gaspatchio involved in the oracle.

A clean ``uv run python 04_curve_precompute_discount.py`` (exit 0, asserts pass)
is the test.

Reference: Hull, *Options, Futures & Other Derivatives* (present-value
discounting); EIOPA risk-free term structure (the curve input). The
pre-compute-and-broadcast rule is the map_elements-avoiding path documented in
``skills/gaspatchio-model-building/references/curves-and-scheduling.md`` (GSP-116).
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core import ActuarialFrame, Curve, Schedule

VALUATION_DATE = date(2025, 1, 31)  # month-end anchor
PROJECTION_MONTHS = 12  # one year, monthly


def main() -> None:
    # Static curve — an illustrative EUR-style zero curve.
    curve = Curve.from_zero_rates(
        tenors=[1.0, 5.0, 10.0, 20.0, 30.0],
        rates=[0.028, 0.033, 0.037, 0.039, 0.040],
    )

    # Shared monthly schedule for the projection horizon. Every policy uses
    # this same grid, so the discount-factor vector is computed once.
    sched = Schedule.from_calendar_grid(
        start_date=VALUATION_DATE,
        n_periods=PROJECTION_MONTHS,
        frequency="1M",
    )

    # --- pre-compute the discount-factor vector ONCE (GSP-116-safe path) -
    # cumulative_year_fractions() is a Python list[float] of length
    # n_periods + 1 = [0, 1/12, 2/12, ...]; discount_factor on a Python list
    # is pure and fast — NO map_elements, computed entirely outside the frame.
    t_years = sched.cumulative_year_fractions()  # list[float], len = n+1
    disc = curve.discount_factor(t_years)  # list[float], computed ONCE
    n = len(disc)

    # A known per-period net cashflow vector — ramps so the PV is non-trivial
    # (a flat vector would make the assertion weak). Length must match disc.
    net_cf_vec = [100.0 - 2.0 * t for t in range(n)]

    # Two policies that share the grid: both carry the same net_cf list. The
    # discount-factor literal broadcasts to every row at zero per-row cost.
    frame = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "net_cf": [net_cf_vec, net_cf_vec],
        },
    )
    af = ActuarialFrame(frame)

    # Broadcast the pre-computed DF vector as a list literal — every row gets
    # the same vector with no per-row computation. THIS is the production path.
    af.discount_factor = pl.lit(disc, dtype=pl.List(pl.Float64))
    af.pv = (af.net_cf * af.discount_factor).list.sum()

    # NOTE — the map_elements footgun we deliberately AVOID:
    #   af.t = af.projection.t_years()
    #   af.discount_factor = curve.discount_factor(af.t)  # list-column -> map_elements
    # That inline list-column form reads nicely but pulls map_elements into the
    # lazy graph (~14x slower; banned for portfolio runs). Pre-compute instead.

    out = af.collect()
    pv_broadcast = out["pv"].to_list()

    # --- independent Python oracle: same DF vector, same net_cf ----------
    # No ActuarialFrame, no Polars expression — a plain dot product.
    pv_oracle = sum(cf * df for cf, df in zip(net_cf_vec, disc, strict=True))

    for pid, pv in zip(out["policy_id"].to_list(), pv_broadcast, strict=True):
        assert abs(pv - pv_oracle) < 1e-9, (
            f"policy {pid}: broadcast PV {pv} != Python dot-product {pv_oracle}"
        )

    # Both policies share the grid and cashflow, so their PVs are identical.
    assert pv_broadcast[0] == pv_broadcast[1], (
        f"shared-grid policies should share PV; got {pv_broadcast}"
    )

    print("Curve pre-compute discounting — broadcast PV == Python dot product")
    print(f"  Projection periods   : {n}  (n_periods + 1)")
    print(f"  t_years[:4]          : {[round(t, 4) for t in t_years[:4]]} ...")
    print(f"  discount_factor[:4]  : {[round(d, 6) for d in disc[:4]]} ...")
    print(f"  Broadcast PV (policy 1): {pv_broadcast[0]:.6f}")
    print(f"  Python oracle PV       : {pv_oracle:.6f}")


if __name__ == "__main__":
    main()
