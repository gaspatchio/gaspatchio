# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve extrapolation beyond the knot range (#31).

``log_linear`` clamped the log-discount-factor LEVEL outside the knot range,
so beyond the last knot the discount factor stopped decaying — a flat 5% curve
returned ~1.64% at 30y, carrying a 30-year cashflow at ~2.7x its true value —
and below the first knot the implied spot blew up as ``t`` shrank. The
``extrapolation`` parameter existed the whole time: declared, defaulted,
serialised across the plugin boundary, and read by nothing.

Now: ``"flat"`` (default) holds the boundary knot's **spot rate** — what
"flat" has always meant for ``linear``/``pchip``, whose knots ARE rates.
``"forward"`` holds the last segment's forward rate, the market-consistent
choice for long-tail discounting. Unknown values raise; rate-space methods
reject ``"forward"`` rather than ignoring it.

Expectations are computed from the growth-factor identity
``(1 + spot_T)^T = (1 + r_n)^{t_n} * F^{T - t_n}``, independent of the
implementation's log-DF arithmetic.
"""

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.curves import Curve

TENORS = [5.0, 10.0]
FLAT_RATES = [0.05, 0.05]
SLOPED_RATES = [0.04, 0.05]


def _curve(rates: list[float], mode: str) -> Curve:
    return Curve.from_zero_rates(
        tenors=TENORS,
        rates=rates,
        interpolation="log_linear",
        extrapolation=mode,
    )


def _kernel_spot(curve: Curve, t: float) -> float:
    """Evaluate through the Rust kernel via the frame path."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "t": [[t]]}))
    af.spot = curve.spot_rate(af.t)
    return af.collect()["spot"].to_list()[0][0]


@pytest.mark.parametrize("mode", ["flat", "forward"])
def test_flat_curve_stays_flat_at_30y(mode: str) -> None:
    """The reported collapse: ~1.64% from a flat 5% curve. Never again."""
    curve = _curve(FLAT_RATES, mode)
    assert curve.spot_rate(30.0) == pytest.approx(0.05, abs=1e-12)
    assert _kernel_spot(curve, 30.0) == pytest.approx(0.05, abs=1e-12)


@pytest.mark.parametrize("mode", ["flat", "forward"])
def test_below_first_knot_holds_the_first_spot(mode: str) -> None:
    """The old level clamp read 5%@5y as (1.05)^5 - 1 = 27.6% at t=1."""
    curve = _curve(FLAT_RATES, mode)
    assert curve.spot_rate(1.0) == pytest.approx(0.05, abs=1e-12)
    assert _kernel_spot(curve, 1.0) == pytest.approx(0.05, abs=1e-12)


def test_flat_holds_the_last_spot_on_a_sloped_curve() -> None:
    """Flat means the last knot's spot, not the last log-DF level."""
    curve = _curve(SLOPED_RATES, "flat")
    assert curve.spot_rate(30.0) == pytest.approx(0.05, abs=1e-12)


def test_forward_matches_the_growth_factor_identity() -> None:
    """(1+spot_30)^30 = (1.05)^10 * F^20, F = (1.05^10 / 1.04^5)^(1/5)."""
    curve = _curve(SLOPED_RATES, "forward")
    f_growth = (1.05**10 / 1.04**5) ** (1.0 / 5.0)
    expected = (1.05**10 * f_growth**20) ** (1.0 / 30.0) - 1.0
    assert curve.spot_rate(30.0) == pytest.approx(expected, abs=1e-12)
    assert _kernel_spot(curve, 30.0) == pytest.approx(expected, abs=1e-12)
    assert curve.spot_rate(30.0) > 0.05  # an upward tail extrapolates above flat


def test_eager_and_kernel_paths_agree() -> None:
    """One convention, two code paths — they must never drift."""
    for mode in ("flat", "forward"):
        curve = _curve(SLOPED_RATES, mode)
        for t in (0.5, 2.0, 7.5, 10.0, 20.0, 40.0, 70.0):
            assert _kernel_spot(curve, t) == pytest.approx(
                curve.spot_rate(t), abs=1e-12
            ), f"mode={mode} t={t}"


def test_interior_interpolation_unchanged_by_mode() -> None:
    """The fix only changes behaviour outside the knot range."""
    flat = _curve(SLOPED_RATES, "flat").spot_rate(7.5)
    fwd = _curve(SLOPED_RATES, "forward").spot_rate(7.5)
    assert flat == pytest.approx(fwd, abs=1e-15)


def test_discount_factor_no_longer_stalls() -> None:
    """The defect in DF terms: DF(30) was 0.607 against a correct 0.223."""
    curve = _curve(FLAT_RATES, "flat")
    df30 = curve.discount_factor(30.0)
    assert df30 == pytest.approx(1.05**-30, abs=1e-12)
    assert df30 < 0.25, f"DF(30) stalled at {df30} — the #31 collapse"


def test_default_is_flat() -> None:
    """Omitting the parameter keeps the (corrected) flat behaviour."""
    curve = Curve.from_zero_rates(
        tenors=TENORS, rates=FLAT_RATES, interpolation="log_linear"
    )
    assert curve.extrapolation == "flat"
    assert curve.spot_rate(30.0) == pytest.approx(0.05, abs=1e-12)


def test_unknown_extrapolation_raises_at_construction() -> None:
    """The error arrives on the constructor line, not at collect()."""
    with pytest.raises(ValueError, match="parabolic"):
        _curve(FLAT_RATES, "parabolic")


def test_forward_requires_log_linear() -> None:
    """Rate-space knots reject "forward" instead of silently ignoring it."""
    with pytest.raises(ValueError, match="log_linear"):
        Curve.from_zero_rates(
            tenors=TENORS,
            rates=FLAT_RATES,
            interpolation="linear",
            extrapolation="forward",
        )


def test_forward_changes_the_source_sha_and_flat_preserves_it() -> None:
    """Audit by default: behaviour change must change the identity stamp.

    And the default must NOT change it — every existing curve keeps the sha
    it had before this parameter became live.
    """
    base = Curve.from_zero_rates(
        tenors=TENORS, rates=SLOPED_RATES, interpolation="log_linear"
    )
    explicit_flat = _curve(SLOPED_RATES, "flat")
    forward = _curve(SLOPED_RATES, "forward")

    assert explicit_flat.source_sha() == base.source_sha()
    assert forward.source_sha() != base.source_sha()
    assert "extrapolation" not in base.canonical_form()
    assert forward.canonical_form()["extrapolation"] == "forward"


def test_shifts_preserve_extrapolation() -> None:
    """A stressed forward curve must stay a forward curve.

    The shift helpers used to reconstruct with a hand-written field list
    that dropped ``extrapolation`` — a parallel-shifted "forward" curve
    silently became "flat", changing every long-tail discount factor in the
    stressed valuation while leaving the base run correct.
    """
    base = _curve(SLOPED_RATES, "forward")
    parallel = base.shift_parallel(bps=100)
    key_rate = base.key_rate_shift(tenor=10.0, bps=25)
    assert parallel.extrapolation == "forward"
    assert key_rate.extrapolation == "forward"
    # And the tail behaves like a forward curve: on an upward-sloping curve
    # the extrapolated 30y spot sits above the flat clamp at the last knot.
    assert parallel.spot_rate(30.0) > parallel.spot_rate(10.0)
    # The identity stamp must still record the mode after a shift.
    assert parallel.canonical_form()["extrapolation"] == "forward"


def test_direct_construction_validates_like_the_classmethods() -> None:
    """Curve(...) cannot smuggle in a mode the classmethods would reject."""
    day_count = Curve.from_zero_rates(tenors=TENORS, rates=FLAT_RATES).day_count
    with pytest.raises(ValueError, match="parabolic"):
        Curve(
            tenors=(5.0, 10.0),
            rates=(0.05, 0.05),
            day_count=day_count,
            interpolation="log_linear",
            extrapolation="parabolic",
        )
    with pytest.raises(ValueError, match="log_linear"):
        Curve(
            tenors=(5.0, 10.0),
            rates=(0.05, 0.05),
            day_count=day_count,
            interpolation="linear",
            extrapolation="forward",
        )


def test_regression_pin_the_exact_reported_number() -> None:
    """0.0164 must never come back from a flat 5% curve at 30y.

    The broken value was exp(-log_df_10 / 30) - 1 = 1.0500...^(1/3) - 1.
    """
    broken = math.exp(10 * math.log(1.05) / 30.0) - 1.0
    assert broken == pytest.approx(0.0164, abs=1e-4)  # documents the old value
    curve = _curve(FLAT_RATES, "flat")
    assert curve.spot_rate(30.0) != pytest.approx(broken, abs=1e-6)
