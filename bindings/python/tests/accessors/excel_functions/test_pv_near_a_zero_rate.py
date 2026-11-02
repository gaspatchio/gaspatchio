# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``excel.pv`` meets 11.1.35's 1e-12 at every nonzero rate, however near nought.

The kernel took ``(1 + r) ** -n``, and ``1 + r`` rounds away the rate's last
digits near nought: 8.9e-5 relative wrong at ``r = 1e-12`` (360 payments of
100 and a future value of 1000), and a step of 0.044 where it switched to the
flat form below ``1e-12`` (audit D1-P11). The kernel now takes the factor as
``exp(-n log1p(r))`` and the paid-off fraction as ``-expm1(-n log1p(r))``; the
flat form is the answer at a rate of nought only.

Needs the core extension built from the kernel this lands with.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

import polars as pl

from gaspatchio import ActuarialFrame

RATES = [1e-15, -1e-13, 9.99e-13, 1e-12, 1e-9, 1e-5, 0.0]


def _exact(rate: float, timing: int) -> float:
    """Return the present value by 80-digit decimals over the doubles' values."""
    with localcontext() as context:
        context.prec = 80
        r, payment, future = Decimal(rate), Decimal(100), Decimal(1000)
        if r == 0:
            return float(-(payment * 360 + future))
        v = (1 + r) ** -360
        return float(-(payment * (1 + r * timing) * (1 - v) / r + future * v))


def test_the_present_value_meets_its_bound_near_a_zero_rate() -> None:
    rows = len(RATES)
    af = ActuarialFrame(
        pl.DataFrame({"r": RATES, "n": [360.0] * rows, "p": [100.0] * rows})
    )
    af.end = af.r.excel.pv(af.n, af.p, fv=1000.0)
    af.due = af.r.excel.pv(af.n, af.p, fv=1000.0, typ=1)
    out = af.collect()
    for column, timing in (("end", 0), ("due", 1)):
        for got, rate in zip(out[column].to_list(), RATES, strict=True):
            want = _exact(rate, timing)
            assert abs(got - want) <= 1e-12 * abs(want), (column, rate, got, want)


def test_no_step_where_the_flat_form_used_to_begin() -> None:
    af = ActuarialFrame(
        pl.DataFrame({"r": [9.99e-13, 1e-12], "n": [360.0] * 2, "p": [100.0] * 2})
    )
    af.v = af.r.excel.pv(af.n, af.p, fv=1000.0)
    below, at = af.collect()["v"].to_list()
    assert abs(below - at) < 1e-6
