# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Timing conventions for ``deduct_nar``.

The net amount at risk can be measured where the COI is charged, or at the
end of the period when the death benefit is actually paid. Both are
mainstream universal life conventions and they disagree once the credited
rate is non-zero — silently, since both produce plausible account values.

The end-of-period figures here are cross-checked against an independent
closed-form solve, so these tests fail if the kernel's algebra drifts.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.rollforward._compile import compile_rollforward

N = 5
FACE = 500_000.0
AV0 = 10_000.0
PREMIUM = 2_500.0
CREDITED = 0.03
COI_DISCOUNT = 0.03
COI_RATE = 0.002


def af_col(name: str) -> pl.Expr:
    """Bare column ref — Op args must be pl.col(...), not compound exprs."""
    return pl.col(name)


def _project(**deduct_kwargs: object) -> list[float]:
    """Run a 5-period UL account value, passing kwargs through to deduct_nar."""
    af = ActuarialFrame(
        {
            "av_init": [AV0],
            "premium": [[PREMIUM] * N],
            "coi_rate": [[COI_RATE] * N],
            "face": [FACE],
            "credited": [[CREDITED] * N],
            "coi_discount": [[COI_DISCOUNT] * N],
            "zero_rate": [[0.0] * N],
        },
    )
    af = af.projection.set(
        start_date=date(2025, 12, 31), n_periods=N, frequency="annual"
    )
    b = af.projection.rollforward(states={"av": af["av_init"]})
    b["av"].add(af["premium"], label="premium")
    b["av"].deduct_nar(af["coi_rate"], death_benefit=af["face"], **deduct_kwargs)  # type: ignore[arg-type]
    b["av"].grow(af["credited"], label="interest")
    af.av = compile_rollforward(b).expr_for("av")
    return af.collect().get_column("av").to_list()[0]


def _closed_form_end_of_period() -> list[float]:
    """Independent solve of the end-of-period convention.

    NAR is measured against the accumulated balance, so the COI and the
    balance are mutually dependent:

        NAR = (face - av*accum) / (1 - coi_rate*accum*v)
        COI = coi_rate * NAR * v
    """
    v = 1.0 / (1.0 + COI_DISCOUNT)
    accum = 1.0 + CREDITED
    av = AV0
    out = []
    for _ in range(N):
        after_premium = av + PREMIUM
        nar = (FACE - after_premium * accum) / (1 - COI_RATE * accum * v)
        av = (after_premium - COI_RATE * nar * v) * accum
        out.append(av)
    return out


def _closed_form_beginning_of_period() -> list[float]:
    """Independent solve of the default convention: NAR where the charge lands."""
    av = AV0
    out = []
    for _ in range(N):
        after_premium = av + PREMIUM
        av = (after_premium - COI_RATE * (FACE - after_premium)) * (1.0 + CREDITED)
        out.append(av)
    return out


class TestBeginningOfPeriodIsTheDefault:
    """The default convention must not shift under anyone's feet."""

    def test_default_matches_closed_form(self) -> None:
        for got, want in zip(
            _project(), _closed_form_beginning_of_period(), strict=True
        ):
            assert got == pytest.approx(want, rel=1e-12)

    def test_default_is_explicit_beginning_of_period(self) -> None:
        assert _project() == _project(nar_timing="beginning_of_period")


class TestEndOfPeriod:
    """NAR measured against the accumulated balance, COI discounted back."""

    def test_matches_independent_closed_form(self) -> None:
        got = _project(
            nar_timing="end_of_period",
            coi_discount_rate=af_col("coi_discount"),
            credited_rate=af_col("credited"),
        )
        for g, want in zip(got, _closed_form_end_of_period(), strict=True):
            assert g == pytest.approx(want, rel=1e-12)

    def test_differs_from_default_and_compounds(self) -> None:
        bop = _project()
        eop = _project(
            nar_timing="end_of_period",
            coi_discount_rate=af_col("coi_discount"),
            credited_rate=af_col("credited"),
        )
        # Charging a discounted COI leaves more in the account.
        assert eop[0] > bop[0]
        # And the divergence widens — it is not a one-off rounding difference.
        gaps = [abs(e - b) for e, b in zip(eop, bop, strict=True)]
        assert gaps == sorted(gaps)
        assert gaps[-1] > gaps[0] * 3

    def test_zero_rates_degenerate_to_a_simultaneous_solve(self) -> None:
        """With both rates zero the discount vanishes but the solve remains.

        NAR = (face - av) / (1 - coi_rate) — still not the same as the
        beginning-of-period form, which does not solve at all. This is why
        the convention is named rather than inferred from the rates.
        """
        got = _project(
            nar_timing="end_of_period",
            coi_discount_rate=af_col("zero_rate"),
            credited_rate=af_col("zero_rate"),
        )
        av = AV0
        want = []
        for _ in range(N):
            after_premium = av + PREMIUM
            coi = COI_RATE * ((FACE - after_premium) / (1 - COI_RATE))
            # The separate grow() step still credits interest; only the COI
            # solve was told the rates are zero.
            av = (after_premium - coi) * (1.0 + CREDITED)
            want.append(av)
        for g, w in zip(got, want, strict=True):
            assert g == pytest.approx(w, rel=1e-12)


class TestRefusesIncoherentArguments:
    """Sharp knives: refuse to run rather than silently ignore an argument."""

    def test_unknown_timing_names_the_valid_options(self) -> None:
        with pytest.raises(ValueError, match="nar_timing must be one of"):
            _project(nar_timing="middle_of_period")

    @pytest.mark.parametrize("kwarg", ["coi_discount_rate", "credited_rate"])
    def test_rates_without_end_of_period_are_refused(self, kwarg: str) -> None:
        with pytest.raises(ValueError, match='nar_timing="end_of_period"'):
            _project(**{kwarg: af_col("credited")})

    @pytest.mark.parametrize(
        ("supplied", "named"),
        [
            ({}, "coi_discount_rate and credited_rate"),
            ({"coi_discount_rate": "coi_disc"}, "credited_rate"),
            ({"credited_rate": "credited"}, "coi_discount_rate"),
        ],
    )
    def test_end_of_period_without_its_rates_is_refused(
        self,
        supplied: dict[str, str],
        named: str,
    ) -> None:
        """Omitting a rate must not silently select a different convention.

        Both factors default to 1.0 in the kernel, which degenerates to the
        simultaneous solve — a third real convention this API does not expose.
        A missing argument would therefore produce a different answer rather
        than an error, so the error names exactly which rate is absent.
        """
        with pytest.raises(ValueError, match=named):
            _project(
                nar_timing="end_of_period",
                **{k: af_col(v) for k, v in supplied.items()},
            )

    def test_the_refusal_explains_what_the_default_would_have_done(self) -> None:
        with pytest.raises(ValueError, match="simultaneous-solve convention"):
            _project(nar_timing="end_of_period")
