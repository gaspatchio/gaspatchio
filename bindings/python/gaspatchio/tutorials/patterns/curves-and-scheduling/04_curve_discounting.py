# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve discounting: read the curve through the recorded door.

Discounting a projected cashflow stream against a yield curve is the core of any
BEL / PV calculation. Call ``curve.discount_factor()`` on a **tracked time
column** and you get both halves at once. It is a recorded core-tier operation:
the audit artifact grows an assumption entry holding the curve's canonical form
and publishing its digest as that entry's ``fingerprint``, and under the
``executable`` profile the node the model leaves behind carries the same string
on its ``expr.attrs.curve``, so a reader can re-hash the knots the numbers were
discounted on. And it lowers through the ``curve_eval`` and ``list_pow`` Rust
kernels — one pass over the list column, no ``map_elements`` anywhere in the
lazy graph.

  af.t_years         = af.projection.t_years()            # tracked time column
  af.discount_factor = curve.discount_factor(af.t_years)  # recorded + kernel-lowered
  af.pv              = (af.net_cf * af.discount_factor).list.sum()

**Measured at portfolio scale** — 10,000 policies on a shared monthly grid of
120 periods, whole model end-to-end through ``.collect()`` on the streaming
engine (the one ``collect()`` uses), on a sixteen-thread laptop with eight
physical cores: the recorded door takes ~28 ms. Hand-rolling the same
discounting through ``map_elements`` takes ~0.63 s to ~1.44 s on that job —
about 21x to 48x slower — and where in that range you land is set by the Python
callable you wrote, not by the framework: a plain-Python hand-roll with the
segment table hoisted out of the callable costs ~0.63 s, handing the row
straight to the curve ~0.97 s, and re-deriving the spot rate in Python, as the
``oracle_spot()`` below does, ~1.41 s. That is the cost the recorded operation
removes.

**The fair in-model figure is the like-for-like one: under 2x.** A model has a
projection either way, so hold ``projection.set`` and ``t_years()`` equal and
vary only the discounting: that like-for-like broadcast then takes ~17 ms
against the door's ~28 ms, and the multiple reads 1.6x-1.9x at every scale
measured (1.60x-1.88x at 10,000 x 120, 1.90x-1.94x at 100,000 x 120, 1.71x-1.74x
at 10,000 x 360). Every one of those is a **streaming, sixteen-thread** figure,
and it is the engine and the threads it travels on: on the in-memory engine the
same comparison reads 10.0x-15.5x, and pinned to one thread ~10.6x, because the
door parallelises about 4x and the broadcast it is divided by does not. It is the
fair figure — the comparison a model actually faces — not a robust one, so quote
it with its engine and its thread count. The escape hatch as written below builds
no projection at all — the bare broadcast — and so reads ~9 ms, which books the
projection scaffolding to the curve read.

Of the two whole-script figures — the door against that bare broadcast — each is
stable on **one** axis: the ratio (3.3x at 10,000 x 120, 3.6x at 100,000 x 120,
3.4x at 10,000 x 360) holds across scale on one machine at one engine and load,
while the delta (~20 ms, ~196 ms, ~55 ms on those same three) is what reproduces
across machines at a fixed scale. Neither is a portable band, so re-time on the
job you actually run. Threads land very unevenly across the four rows: the door
parallelises 4.0x out of eight physical cores — pinned with
``POLARS_MAX_THREADS=1`` it reads ~110-113 ms here against ~28 ms on sixteen,
and the whole-script ratio goes to 13x-16x — while the bare broadcast and the
``map_elements`` row gain nothing measurable and the like-for-like broadcast is
*faster* pinned, ~10.7 ms against ~17.5 ms. So the multiple you see is set by the
engine and by how many cores the door gets. Ten milliseconds on a
ten-thousand-policy run, a tenth of a second at a hundred thousand, is not a
reason to give up the record.

**The escape hatch, kept below and labelled.** On a shared uniform grid every
policy has the same ``t`` vector, so the discount factors can be computed once
outside the frame and handed over as a Polars list literal. This script asserts
that the two paths give the identical PV — it is a speed choice, never an
answer. The audit cost is the whole of the difference: ``pl.lit(...)`` reads no
column of the model and names no assumption base, so nothing in the artifact
ties those numbers to the curve — no assumption entry, no ``fingerprint``,
nothing for next quarter's comparison to attribute a movement to — and the
artifact validator warns on precisely that shape.

The PV is proved here against a plain-Python oracle that re-derives the spot
rate by hand (linear on the knot rates, flat outside the grid), raises
``(1 + r)^(-t)`` itself, and dots it with the same ``net_cf`` — no Gaspatchio
anywhere in the check.

A clean ``uv run python 04_curve_discounting.py`` (exit 0, asserts pass) is the
test.

Reference: Hull, *Options, Futures & Other Derivatives* (present-value
discounting); EIOPA risk-free term structure (the curve input). Steering and the
audit cost of the escape hatch:
``skills/gaspatchio-model-building/references/curves-and-scheduling.md``.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio import ActuarialFrame, Curve, Schedule

VALUATION_DATE = date(2025, 1, 31)  # month-end anchor
PROJECTION_MONTHS = 120  # ten years, monthly — crosses the 1y, 5y and 10y knots

TENORS = [1.0, 5.0, 10.0, 20.0, 30.0]
RATES = [0.028, 0.033, 0.037, 0.039, 0.040]


def oracle_spot(t: float) -> float:
    """Re-derive the zero rate at ``t`` in plain Python — no Gaspatchio.

    Linear on the knot rates between knots, flat outside the grid. This is the
    independent check on the curve, so it is written out rather than called.
    """
    if t <= TENORS[0]:
        return RATES[0]
    if t >= TENORS[-1]:
        return RATES[-1]
    for lo, hi, r_lo, r_hi in zip(
        TENORS[:-1], TENORS[1:], RATES[:-1], RATES[1:], strict=True
    ):
        if lo <= t <= hi:
            return r_lo + (r_hi - r_lo) * (t - lo) / (hi - lo)
    msg = f"t={t} fell outside every knot interval"  # pragma: no cover
    raise AssertionError(msg)  # pragma: no cover


def main() -> None:
    # Static curve — an illustrative EUR-style zero curve.
    curve = Curve.from_zero_rates(tenors=TENORS, rates=RATES)

    # A known per-period net cashflow vector — ramps so the PV is non-trivial
    # (a flat vector would make the assertion weak).
    n = PROJECTION_MONTHS + 1
    net_cf_vec = [100.0 - 0.5 * t for t in range(n)]

    frame = pl.DataFrame(
        {"policy_id": [1, 2], "net_cf": [net_cf_vec, net_cf_vec]},
        schema={"policy_id": pl.Int64, "net_cf": pl.List(pl.Float64)},
    )

    # --- the taught path: read the curve through the recorded door -------
    af = ActuarialFrame(frame)
    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value=PROJECTION_MONTHS,
        frequency="monthly",
    )
    # t_years() is the projection's own cumulative year fractions as a tracked
    # list column, length n_periods + 1. discount_factor() on it emits a
    # recorded curve.discount_factor node, publishing the curve's digest as the
    # assumption entry's fingerprint (and on the node's expr.attrs.curve under
    # the executable profile), and lowers to curve_eval + list_pow — one kernel
    # pass, no map_elements.
    af.t_years = af.projection.t_years()
    af.discount_factor = curve.discount_factor(af.t_years)
    af.pv = (af.net_cf * af.discount_factor).list.sum()

    out = af.collect()
    pv_recorded = out["pv"].to_list()
    t_years = out["t_years"].to_list()[0]
    disc_recorded = out["discount_factor"].to_list()[0]

    # --- independent plain-Python oracle ---------------------------------
    # Hand-rolled spot rate, hand-rolled compounding, hand-rolled dot product.
    disc_oracle = [(1.0 + oracle_spot(t)) ** (-t) for t in t_years]
    pv_oracle = sum(cf * df for cf, df in zip(net_cf_vec, disc_oracle, strict=True))

    worst_df = max(abs(a - b) for a, b in zip(disc_recorded, disc_oracle, strict=True))
    assert worst_df < 1e-12, (
        f"recorded discount factors diverge from the hand-derived curve by {worst_df}"
    )
    for pid, pv in zip(out["policy_id"].to_list(), pv_recorded, strict=True):
        assert abs(pv - pv_oracle) < 1e-9, (
            f"policy {pid}: recorded PV {pv} != Python oracle {pv_oracle}"
        )

    # Both policies share the grid and the cashflow, so their PVs are identical.
    assert pv_recorded[0] == pv_recorded[1], (
        f"shared-grid policies should share PV; got {pv_recorded}"
    )

    # --- ESCAPE HATCH: pre-compute in Python, broadcast as a literal -----
    # Faster (a shared grid means 121 curve evaluations instead of 1.21m at
    # portfolio scale) and numerically identical, asserted below.
    #
    # AUDIT COST: pl.lit() reads no column and names no assumption base, so
    # nothing in the artifact ties these numbers to the curve — no assumption
    # entry, no fingerprint, no way to attribute next quarter's movement — and
    # the artifact validator warns on exactly this shape. Reach for it only
    # when a measured bottleneck justifies giving up the record.
    sched = Schedule.from_calendar_grid(
        start_date=VALUATION_DATE,
        n_periods=PROJECTION_MONTHS,
        frequency="1M",
    )
    disc_precomputed = curve.discount_factor(sched.cumulative_year_fractions())
    af_hatch = ActuarialFrame(frame)
    af_hatch.discount_factor = pl.lit(disc_precomputed, dtype=pl.List(pl.Float64))
    af_hatch.pv = (af_hatch.net_cf * af_hatch.discount_factor).list.sum()
    pv_hatch = af_hatch.collect()["pv"].to_list()

    assert pv_hatch == pv_recorded, (
        "the escape hatch is a speed choice, not a different answer; "
        f"got {pv_hatch} against {pv_recorded}"
    )

    print("Curve discounting — recorded door == hand-derived Python oracle")
    print(f"  Projection periods     : {n}  (n_periods + 1)")
    print(f"  t_years[:4]            : {[round(t, 4) for t in t_years[:4]]} ...")
    print(f"  discount_factor[:4]    : {[round(d, 6) for d in disc_recorded[:4]]} ...")
    print(f"  Recorded PV (policy 1) : {pv_recorded[0]:.6f}")
    print(f"  Python oracle PV       : {pv_oracle:.6f}")
    print(f"  Escape-hatch PV        : {pv_hatch[0]:.6f}  (identical, unrecorded)")


if __name__ == "__main__":
    main()
