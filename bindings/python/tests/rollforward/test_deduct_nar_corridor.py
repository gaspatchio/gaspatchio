# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The regulatory corridor test on ``deduct_nar``.

Real universal life products define the death benefit as at least a corridor
factor times the account value — IRC §7702's cash-value-accumulation test and
its equivalents elsewhere. So ``DB = MAX(face, y * AV)``, and the amount at
risk follows.

Without it, a well-funded policy's amount at risk goes **negative**: the COI
becomes a credit to the account, the larger account makes the amount at risk
more negative, and nothing bounds the loop. That is the failure this exists to
stop, so it is tested directly rather than only through the happy path.

Every expectation here is solved independently in Python from the closed forms
in the docstring of ``DeductNAR``, so these fail if the kernel's algebra drifts.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward._compile import compile_rollforward

if TYPE_CHECKING:
    import polars as pl

N = 6
FACE = 500_000.0
CREDITED = 0.05
COI_DISCOUNT = 0.03
COI_RATE = 0.004
YOUNG_FACTOR = 2.5  # corridor factor at younger ages
LEVEL_FACTOR = 1.0  # what the tables decay to at advanced ages

THIN_AV = 10_000.0  # nowhere near the face amount
FUNDED_AV = 300_000.0  # close enough that the corridor binds
OVERFUNDED_AV = 600_000.0  # past the face amount — negative NAR without a corridor


def project(
    *,
    av0: float,
    corridor: float | None,
    timing: str = "end_of_period",
) -> list[float]:
    """Run an account value with a COI deduction, optionally with a corridor."""
    af = ActuarialFrame(
        {
            "av_init": [av0],
            "coi_rate": [[COI_RATE] * N],
            "face": [FACE],
            "credited": [[CREDITED] * N],
            "coi_discount": [[COI_DISCOUNT] * N],
            "corridor": [[corridor if corridor is not None else 1.0] * N],
        },
    )
    af = af.projection.set(
        start_date=date(2025, 12, 31), n_periods=N, frequency="annual"
    )
    b = af.projection.rollforward(states={"av": af["av_init"]})
    rates: dict[str, pl.Expr] = {}
    if timing == "end_of_period":
        rates = {
            "coi_discount_rate": af["coi_discount"],
            "credited_rate": af["credited"],
        }
    b["av"].deduct_nar(
        af["coi_rate"],
        death_benefit=af["face"],
        nar_timing=timing,
        corridor_factor=af["corridor"] if corridor is not None else None,
        **rates,
    )
    b["av"].grow(af["credited"], label="interest")
    af.av = compile_rollforward(b).expr_for("av")
    values: list[float] = af.collect().get_column("av").to_list()[0]
    return values


def closed_form(
    *, av0: float, corridor: float | None
) -> tuple[list[float], list[float]]:
    """Independent end-of-period solve. Returns (account values, amounts at risk)."""
    v = 1.0 / (1.0 + COI_DISCOUNT)
    accum = 1.0 + CREDITED
    av = av0
    avs, nars = [], []
    for _ in range(N):
        accumulated = av * accum
        nar_face = (FACE - accumulated) / (1.0 - COI_RATE * accum * v)
        if corridor is None:
            nar = nar_face
        else:
            y1 = corridor - 1.0
            nar_corr = (y1 * accumulated) / (1.0 + y1 * COI_RATE * accum * v)
            nar = max(nar_face, nar_corr)
        av = (av - COI_RATE * nar * v) * accum
        avs.append(av)
        nars.append(nar)
    return avs, nars


class TestCorridorIsInertWhenItDoesNotBind:
    """A thinly funded policy must be unaffected by supplying the factor."""

    def test_matches_the_no_corridor_run(self) -> None:
        with_corridor = project(av0=THIN_AV, corridor=YOUNG_FACTOR)
        without = project(av0=THIN_AV, corridor=None)
        assert with_corridor == pytest.approx(without, rel=1e-12)

    def test_the_fixed_branch_is_the_binding_one(self) -> None:
        _, nars = closed_form(av0=THIN_AV, corridor=YOUNG_FACTOR)
        _, face_only = closed_form(av0=THIN_AV, corridor=None)
        assert nars == pytest.approx(face_only)
        # And by a wide margin, which is why it never surfaced in testing.
        assert face_only[0] > 400_000


class TestCorridorBindsWhenWellFunded:
    def test_matches_the_independent_solve(self) -> None:
        got = project(av0=FUNDED_AV, corridor=YOUNG_FACTOR)
        want, _ = closed_form(av0=FUNDED_AV, corridor=YOUNG_FACTOR)
        assert got == pytest.approx(want, rel=1e-12)

    def test_it_actually_binds_and_changes_the_answer(self) -> None:
        """Guard against a test that would pass with the feature removed."""
        _, nars = closed_form(av0=FUNDED_AV, corridor=YOUNG_FACTOR)
        _, face_only = closed_form(av0=FUNDED_AV, corridor=None)
        assert all(c > f for c, f in zip(nars, face_only, strict=True))
        with_corridor = project(av0=FUNDED_AV, corridor=YOUNG_FACTOR)
        without = project(av0=FUNDED_AV, corridor=None)
        assert with_corridor[0] != pytest.approx(without[0])

    def test_a_larger_factor_charges_more(self) -> None:
        """The corridor raises the benefit, so it raises the amount at risk."""
        _, low = closed_form(av0=FUNDED_AV, corridor=1.5)
        _, high = closed_form(av0=FUNDED_AV, corridor=YOUNG_FACTOR)
        assert all(h > lo for h, lo in zip(high, low, strict=True))


class TestTheCorridorIsSelfLimiting:
    """The proportional branch is negative feedback — that is the whole point."""

    def test_a_well_funded_policy_stays_finite(self) -> None:
        avs = project(av0=FUNDED_AV, corridor=YOUNG_FACTOR)
        assert all(a > 0 for a in avs)
        # Growth is bounded by the credited rate; no runaway.
        assert avs[-1] < FUNDED_AV * (1.0 + CREDITED) ** N

    def test_the_charge_is_never_a_credit(self) -> None:
        _, nars = closed_form(av0=FUNDED_AV, corridor=YOUNG_FACTOR)
        assert all(n >= 0 for n in nars)

    def test_factor_of_one_floors_the_amount_at_risk_at_zero(self) -> None:
        """``y = 1.0`` is what the tables decay to, and it means "no corridor".

        ``DB = MAX(face, 1.0 * AV)`` still keeps the amount at risk
        non-negative, which is what stops the runaway at advanced ages.
        """
        avs = project(av0=OVERFUNDED_AV, corridor=LEVEL_FACTOR)
        # No amount at risk, so no charge — the account simply accumulates.
        want = [OVERFUNDED_AV * (1.0 + CREDITED) ** (t + 1) for t in range(N)]
        assert avs == pytest.approx(want, rel=1e-12)


class TestNegativeAmountAtRiskIsRefused:
    """Sharp knives: a negative amount at risk is not a number to return."""

    def test_an_overfunded_policy_without_a_corridor_raises(self) -> None:
        with pytest.raises(Exception, match="net amount at risk is negative"):
            project(av0=OVERFUNDED_AV, corridor=None)

    def test_the_message_names_the_period_and_both_figures(self) -> None:
        with pytest.raises(Exception) as excinfo:
            project(av0=OVERFUNDED_AV, corridor=None)
        msg = str(excinfo.value)
        assert "period 0" in msg
        assert "500000.00" in msg  # the death benefit
        assert "corridor_factor=" in msg  # names the fix

    def test_the_same_policy_is_fine_with_a_corridor(self) -> None:
        avs = project(av0=OVERFUNDED_AV, corridor=YOUNG_FACTOR)
        assert all(a > 0 for a in avs)


class TestBeginningOfPeriodCorridor:
    """The corridor applies to both conventions, not only the solved one."""

    def test_matches_the_independent_solve(self) -> None:
        got = project(
            av0=FUNDED_AV, corridor=YOUNG_FACTOR, timing="beginning_of_period"
        )
        av, want = FUNDED_AV, []
        for _ in range(N):
            # No solve here: benefit and balance are read at the same point.
            nar = max(FACE - av, (YOUNG_FACTOR - 1.0) * av)
            av = (av - COI_RATE * nar) * (1.0 + CREDITED)
            want.append(av)
        assert got == pytest.approx(want, rel=1e-12)

    def test_negative_amount_at_risk_is_refused_here_too(self) -> None:
        with pytest.raises(Exception, match="net amount at risk is negative"):
            project(av0=OVERFUNDED_AV, corridor=None, timing="beginning_of_period")


class TestAuditTrail:
    """A corridor changes the model, so it must change the fingerprint."""

    def _fingerprint(self, corridor: float | None) -> str:
        af = ActuarialFrame(
            {
                "av_init": [THIN_AV],
                "coi_rate": [[COI_RATE] * N],
                "face": [FACE],
                "corridor": [[YOUNG_FACTOR] * N],
            },
        )
        af = af.projection.set(
            start_date=date(2025, 12, 31), n_periods=N, frequency="annual"
        )
        b = af.projection.rollforward(states={"av": af["av_init"]})
        b["av"].deduct_nar(
            af["coi_rate"],
            death_benefit=af["face"],
            corridor_factor=af["corridor"] if corridor is not None else None,
        )
        return compile_rollforward(b).fingerprint()

    def test_supplying_a_corridor_changes_the_fingerprint(self) -> None:
        assert self._fingerprint(YOUNG_FACTOR) != self._fingerprint(None)
