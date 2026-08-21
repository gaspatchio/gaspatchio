# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""GSP-113: prospective_value invariance audit at truncation boundaries.

``prospective_value`` carries a timing convention (beginning/end of period)
and its reverse-cumsum implementation has classic off-by-one territory at the
ends of the series. This audit sweeps series lengths around the natural
length ``n`` of a reference cashflow — ``{1, 2, n-1, n, n+1, 2n}`` — under
both timing conventions, asserting against independently computed closed
forms and the defining identities:

* closed form:  ``PV_eop(t) = sum_{s>=t} CF[s] * v^(s-t+1)`` and
  ``PV_bop(t) = sum_{s>=t} CF[s] * v^(s-t)``
* backward recursion: ``PV_eop(t) = v * (CF(t) + PV_eop(t+1))`` and
  ``PV_bop(t) = CF(t) + v * PV_bop(t+1)``
* constant-rate timing identity: ``PV_eop(t) = PV_bop(t) * v`` at every t
* zero-padding invariance: appending zero cashflows never changes the PV of
  the earlier positions

Tolerances: closed forms are summed in a different association order than the
kernel's cumsum, so exact bit-equality is not required there — assertions use
``rel=1e-12``, far below any actuarial materiality but tight enough to catch
a misplaced period. The structural identities (recursion, padding) are
asserted at the same tolerance; padding is additionally expected to be exact
in practice.
"""

import pytest

from gaspatchio import ActuarialFrame

RATE = 0.05
V = 1.0 / (1.0 + RATE)

# Distinct values so a one-position shift can never alias to a pass.
BASE_CF = [100.0, 210.0, 330.0, 460.0]
N = len(BASE_CF)

TRUNCATIONS = [1, 2, N - 1, N, N + 1, 2 * N]
TIMINGS = ["beginning_of_period", "end_of_period"]


def series_at(length):
    """The reference series truncated or zero-extended to ``length`` periods."""
    return [BASE_CF[t] if t < N else 0.0 for t in range(length)]


def closed_form_pv(cashflows, timing):
    """Independent closed-form PV(t) for every t, per the documented contract."""
    shift = 1 if timing == "end_of_period" else 0
    return [
        sum(cf * V ** (s - t + shift) for s, cf in enumerate(cashflows) if s >= t)
        for t in range(len(cashflows))
    ]


def computed_pv(cashflows, timing, *, discount_factor=None):
    """Run prospective_value over a one-row frame and return PV as a list."""
    data = {"cashflow": [cashflows]}
    if discount_factor is not None:
        data["v_t"] = [discount_factor]
    af = ActuarialFrame(data)
    if discount_factor is not None:
        af.pv = af.cashflow.projection.prospective_value(
            discount_factor=af.v_t, timing=timing
        )
    else:
        af.pv = af.cashflow.projection.prospective_value(
            discount_rate=RATE, timing=timing
        )
    return af.collect()["pv"][0].to_list()


class TestTruncationBoundaries:
    """PV correctness for series lengths straddling the natural length."""

    @pytest.mark.parametrize("timing", TIMINGS)
    @pytest.mark.parametrize("length", TRUNCATIONS)
    def test_matches_closed_form(self, length, timing):
        """PV(t) matches the closed form at every t for every boundary length."""
        cashflows = series_at(length)
        pv = computed_pv(cashflows, timing)
        expected = closed_form_pv(cashflows, timing)

        assert len(pv) == length
        for t, (got, want) in enumerate(zip(pv, expected)):
            assert got == pytest.approx(want, rel=1e-12, abs=1e-9), (
                f"length={length} timing={timing} t={t}"
            )

    @pytest.mark.parametrize("timing", TIMINGS)
    @pytest.mark.parametrize("length", TRUNCATIONS)
    def test_backward_recursion_holds(self, length, timing):
        """PV satisfies its own defining recursion at every interior t."""
        cashflows = series_at(length)
        pv = computed_pv(cashflows, timing)

        for t in range(length - 1):
            if timing == "end_of_period":
                want = V * (cashflows[t] + pv[t + 1])
            else:
                want = cashflows[t] + V * pv[t + 1]
            assert pv[t] == pytest.approx(want, rel=1e-12, abs=1e-9), (
                f"recursion broken at t={t} (length={length}, timing={timing})"
            )

        # Terminal period: no tail, so PV is the lone cashflow (discounted
        # one period under end_of_period, undiscounted under beginning).
        terminal = cashflows[-1] * (V if timing == "end_of_period" else 1.0)
        assert pv[-1] == pytest.approx(terminal, rel=1e-12, abs=1e-9)

    @pytest.mark.parametrize("length", TRUNCATIONS)
    def test_eop_equals_bop_times_v(self, length):
        """Constant-rate identity: end_of_period = beginning_of_period * v, all t."""
        cashflows = series_at(length)
        pv_bop = computed_pv(cashflows, "beginning_of_period")
        pv_eop = computed_pv(cashflows, "end_of_period")

        for t, (eop, bop) in enumerate(zip(pv_eop, pv_bop)):
            assert eop == pytest.approx(bop * V, rel=1e-12, abs=1e-9), f"t={t}"

    def test_single_period_explicit(self):
        """The length-1 boundary, spelled out with literal expected values."""
        assert computed_pv([100.0], "beginning_of_period")[0] == pytest.approx(
            100.0, rel=1e-12
        )
        assert computed_pv([100.0], "end_of_period")[0] == pytest.approx(
            100.0 * V, rel=1e-12
        )

    @pytest.mark.parametrize("timing", TIMINGS)
    def test_zero_padding_is_invariant(self, timing):
        """Zero cashflows appended past n never change the first n PVs."""
        pv_natural = computed_pv(series_at(N), timing)
        pv_padded = computed_pv(series_at(2 * N), timing)

        for t in range(N):
            assert pv_padded[t] == pytest.approx(
                pv_natural[t], rel=1e-12, abs=1e-9
            ), f"padding changed PV at t={t} (timing={timing})"
        # The padded tail is a zero series: PV must be exactly zero there.
        assert all(x == 0.0 for x in pv_padded[N:])


class TestDiscountFactorAnchoring:
    """Factor-based PV agrees with rate-based PV at the same boundaries.

    The factor convention is timing-anchored (see the docstring contract):
    end_of_period factors are ``[v, v^2, ...]``, beginning_of_period factors
    are ``[1, v, v^2, ...]``. A one-period anchoring slip here is exactly the
    silent-valuation-error class this audit exists to catch.
    """

    @pytest.mark.parametrize("timing", TIMINGS)
    @pytest.mark.parametrize("length", [1, N, 2 * N])
    def test_factor_matches_rate(self, length, timing):
        cashflows = series_at(length)
        shift = 1 if timing == "end_of_period" else 0
        factors = [V ** (t + shift) for t in range(length)]

        pv_rate = computed_pv(cashflows, timing)
        pv_factor = computed_pv(cashflows, timing, discount_factor=factors)

        for t, (got, want) in enumerate(zip(pv_factor, pv_rate)):
            assert got == pytest.approx(want, rel=1e-12, abs=1e-9), (
                f"factor/rate mismatch at t={t} (length={length}, timing={timing})"
            )


class TestJaggedRows:
    """One frame, rows of different lengths — no cross-row offset leakage."""

    @pytest.mark.parametrize("timing", TIMINGS)
    def test_each_row_matches_its_own_closed_form(self, timing):
        lengths = [1, N, 2 * N]
        rows = [series_at(k) for k in lengths]
        af = ActuarialFrame({"cashflow": rows})
        af.pv = af.cashflow.projection.prospective_value(
            discount_rate=RATE, timing=timing
        )
        result = af.collect()

        for row, (length, cashflows) in enumerate(zip(lengths, rows)):
            pv = result["pv"][row].to_list()
            expected = closed_form_pv(cashflows, timing)
            assert len(pv) == length
            for t, (got, want) in enumerate(zip(pv, expected)):
                assert got == pytest.approx(want, rel=1e-12, abs=1e-9), (
                    f"row={row} t={t} (timing={timing})"
                )
