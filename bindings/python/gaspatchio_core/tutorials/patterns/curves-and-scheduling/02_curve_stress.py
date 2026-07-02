# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Stress a curve — parallel and key-rate shifts — without mutating the base.

Interest-rate stress is a regulatory staple: Solvency II's interest-rate SCR is
a parallel up/down shift of the risk-free curve; ALM desks run *key-rate*
sensitivities, bumping one tenor at a time to measure the duration contribution
of each segment of the curve. ``Curve`` exposes both as pure transforms that
return a **new** curve and leave the original untouched — so a stress run can
never silently corrupt the base valuation.

This script proves three things, each grounded from ``curves/_curve.py`` /
``curves/_shift.py``:

  - ``shift_parallel(bps=100)`` moves **every** knot rate by exactly +0.01
    (100 bps = 1 percentage point = ``bps / 10_000``; ``_shift.py``).
  - The **original** curve is unchanged after the shift — re-query a knot and
    confirm it still returns the base rate (immutability of a frozen dataclass).
  - ``key_rate_shift`` requires the ``tenor`` to be an **exact knot**; a
    non-knot tenor raises ``ValueError`` (``_shift.py`` guard). We catch it and
    assert — fractional / interpolated key-rate shifts are not yet supported.

A clean ``uv run python 02_curve_stress.py`` (exit 0, asserts pass) is the test.

Reference: EIOPA / Solvency II interest-rate sub-module (parallel curve shocks);
Hull, *Options, Futures & Other Derivatives* (key-rate / partial durations).
Source of truth for the shift semantics: ``gaspatchio_core/curves/_shift.py``.
"""

from __future__ import annotations

from gaspatchio_core import Curve

TENORS = [1.0, 5.0, 10.0, 20.0, 30.0]
ZERO_RATES = [0.028, 0.033, 0.037, 0.039, 0.040]

ONE_BP = 0.0001  # one basis point as a decimal rate


def main() -> None:
    curve = Curve.from_zero_rates(tenors=TENORS, rates=ZERO_RATES)

    # --- parallel shift: +100bp moves every knot rate by exactly +0.01 ---
    up100 = curve.shift_parallel(bps=100)
    for tenor, base_rate in zip(TENORS, ZERO_RATES, strict=True):
        shifted = up100.spot_rate(tenor)
        assert abs(shifted - (base_rate + 100 * ONE_BP)) < 1e-12, (
            f"+100bp at {tenor}y: {shifted} != {base_rate} + 0.01"
        )

    # --- immutability: the ORIGINAL curve is untouched -------------------
    # Re-query the base curve after the shift. A frozen dataclass returns a
    # new instance from every stress; the base valuation can never be
    # corrupted by a downstream scenario.
    for tenor, base_rate in zip(TENORS, ZERO_RATES, strict=True):
        assert curve.spot_rate(tenor) == base_rate, (
            f"original curve mutated at {tenor}y: "
            f"{curve.spot_rate(tenor)} != {base_rate}"
        )

    # --- key-rate shift: bump ONE real knot, hold the rest ---------------
    kr10 = curve.key_rate_shift(tenor=10.0, bps=25)
    idx_10 = TENORS.index(10.0)
    for i, (tenor, base_rate) in enumerate(zip(TENORS, ZERO_RATES, strict=True)):
        expected = base_rate + 25 * ONE_BP if i == idx_10 else base_rate
        assert abs(kr10.spot_rate(tenor) - expected) < 1e-12, (
            f"key-rate 10y +25bp leaked to {tenor}y: "
            f"{kr10.spot_rate(tenor)} != {expected}"
        )

    # --- key-rate shift on a NON-knot tenor raises -----------------------
    # 7.0 is between the 5y and 10y knots but is not itself a knot. The
    # implementation rejects it rather than guessing an interpolated bump.
    raised = False
    message = ""
    try:
        curve.key_rate_shift(tenor=7.0, bps=25)
    except ValueError as exc:
        raised = True
        message = str(exc)
    assert raised, "key_rate_shift on a non-knot tenor must raise ValueError"
    assert "not in curve" in message, f"unexpected message: {message}"

    print("Curve stress — shifts compose, the base curve is immutable")
    print(f"  Base rates           : {ZERO_RATES}")
    print(f"  +100bp parallel      : {[round(up100.spot_rate(t), 4) for t in TENORS]}")
    print(f"  10y +25bp key-rate   : {[round(kr10.spot_rate(t), 4) for t in TENORS]}")
    print(f"  Base after shifts    : {[curve.spot_rate(t) for t in TENORS]}  (unchanged)")
    print("  key_rate_shift(7.0)  : raised ValueError (non-knot tenor)")


if __name__ == "__main__":
    main()
