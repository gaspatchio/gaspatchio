# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Integration test: per-policy column-name projection produces identical results to scalar.

Uses 4 policies with different terms (5, 10, 15, 20 years).
Compares uniform 240-month projection (with maturity masking) against per-policy
column-name projection (which under the new API also resolves to uniform-max +
maturity masking — see ref/38-projection-axis spec §3 settled position 3).

Both must produce numerically identical cashflow results.
"""

import datetime
import math

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gaspatchio_core import (
    ActuarialFrame,
    get_default_mode,
    set_default_mode,
    when,
)


VALUATION_DATE = datetime.date(2025, 1, 1)


def build_model_uniform(mp: pl.DataFrame, projection_months: int = 240) -> pl.DataFrame:
    """Build a simplified L3-style model with uniform projection + maturity masking."""
    af = ActuarialFrame(mp)

    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value=projection_months,
        frequency="monthly",
    )
    # proj_dates is no longer eager; assign explicitly so downstream attribute
    # access (af.proj_dates) keeps working.
    af.proj_dates = af.projection.period_dates()

    # Month index
    af.month = (af.proj_dates.dt.year() - VALUATION_DATE.year) * 12 + (
        af.proj_dates.dt.month() - VALUATION_DATE.month
    )

    # Mortality and survival (simplified: flat 0.001/month)
    af.mort_rate = af.month * 0 + 0.001
    af.survival = af.mort_rate.projection.cumulative_survival()
    af.survival_bop = af.survival.projection.previous_period(fill_value=1.0)

    # Maturity boundary masking (the pattern per-policy projection eliminates)
    af.maturity_month = af.policy_term * 12
    af.pols_if = (
        when(af.month < af.maturity_month)
        .then(af.survival_bop * af.policy_count)
        .otherwise(0.0)
    )
    af.pols_death = af.pols_if * af.mort_rate

    # Simple cashflows
    af.premium = af.pols_if * 100.0
    af.claims = af.pols_death * 50000.0
    af.net_cf = af.premium - af.claims

    return af.collect()


def build_model_variable(mp: pl.DataFrame) -> pl.DataFrame:
    """Build the same model with per-policy column-name projection.

    A column ``until_value`` with a ``term_*`` horizon auto-selects the jagged
    (per_policy) path, so each policy projects only over its own term and the
    list columns are variable-length (no zero tail past maturity). The maturity
    masking is therefore a no-op here — there is no dead tail to zero.
    """
    # Compute remaining term in months
    mp = mp.with_columns((pl.col("policy_term") * 12).alias("remaining_term_months"))
    af = ActuarialFrame(mp)

    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value="remaining_term_months",
        frequency="monthly",
    )
    af.proj_dates = af.projection.period_dates()

    # Month index
    af.month = (af.proj_dates.dt.year() - VALUATION_DATE.year) * 12 + (
        af.proj_dates.dt.month() - VALUATION_DATE.month
    )

    # Mortality and survival (same as uniform)
    af.mort_rate = af.month * 0 + 0.001
    af.survival = af.mort_rate.projection.cumulative_survival()
    af.survival_bop = af.survival.projection.previous_period(fill_value=1.0)

    # Per-policy maturity masking. Under the new API, until_value="column" gives
    # uniform-max n_periods (= max policy_term across all rows), so we still need
    # to mask each policy's tail to zero past its own maturity.
    af.maturity_month = af.policy_term * 12
    af.pols_if = (
        when(af.month < af.maturity_month)
        .then(af.survival_bop * af.policy_count)
        .otherwise(0.0)
    )
    af.pols_death = af.pols_if * af.mort_rate

    # Simple cashflows
    af.premium = af.pols_if * 100.0
    af.claims = af.pols_death * 50000.0
    af.net_cf = af.premium - af.claims

    return af.collect()


@pytest.fixture()
def model_points():
    """4 policies with different terms, same structure as L3 Mini-VA."""
    return pl.DataFrame(
        {
            "policy_id": ["A", "B", "C", "D"],
            "policy_term": [5, 10, 15, 20],
            "policy_count": [100.0, 100.0, 100.0, 100.0],
        }
    )


def _assert_live_periods_match(uniform_vals, variable_vals, *, ctx: str) -> None:
    """Jagged ``variable_vals`` equals ``uniform_vals`` over its (shorter) live
    horizon, and the uniform tail past that horizon is zero (the dead tail that
    jagged simply omits). This is the jagged<->uniform economic equivalence.
    """
    k = len(variable_vals)
    assert k <= len(uniform_vals), f"{ctx}: variable longer than uniform"
    for i in range(k):
        assert abs(uniform_vals[i] - variable_vals[i]) < 1e-10, (
            f"{ctx}, t={i}: uniform={uniform_vals[i]}, variable={variable_vals[i]}"
        )
    for i in range(k, len(uniform_vals)):
        assert abs(uniform_vals[i]) < 1e-10, (
            f"{ctx}: uniform dead-tail not zero at t={i}: {uniform_vals[i]}"
        )


class TestVariableProjectionEquivalence:
    """Jagged (column until_value, now the default) reconciles with uniform.

    ``build_model_uniform`` uses a scalar ``until_value`` -> uniform grid;
    ``build_model_variable`` uses a column -> jagged (auto-default). Jagged
    projects each policy over only its own term, so its lists are shorter; the
    economics must be identical: live periods match element-wise, the uniform
    masked tail is zero, and portfolio totals reconcile exactly.
    """

    def test_cashflows_match(self, model_points):
        """Live-period cashflows match; uniform's masked tail is zero."""
        uniform = build_model_uniform(model_points, projection_months=240)
        variable = build_model_variable(model_points)

        for col in ["premium", "claims", "net_cf"]:
            for row_idx in range(4):
                _assert_live_periods_match(
                    uniform[col][row_idx].to_list(),
                    variable[col][row_idx].to_list(),
                    ctx=f"row={row_idx}, col={col}",
                )

    def test_jagged_is_leaner_but_totals_reconcile(self, model_points):
        """Jagged omits the zero tail (fewer elements) yet totals match exactly."""
        uniform = build_model_uniform(model_points, projection_months=240)
        variable = build_model_variable(model_points)

        # Jagged projects each policy only to its own term -> strictly fewer
        # elements than the uniform 240-wide grid (terms are 5/10/15/20y).
        assert (
            variable["net_cf"].list.len().sum() < uniform["net_cf"].list.len().sum()
        )
        # ...but the portfolio economics reconcile exactly (the omitted tail
        # summed to zero).
        u_total = uniform["net_cf"].list.sum().sum()
        v_total = variable["net_cf"].list.sum().sum()
        assert abs(u_total - v_total) < 1e-6

    def test_pols_if_match(self, model_points):
        """In-force policy counts match over each policy's live horizon."""
        uniform = build_model_uniform(model_points, projection_months=240)
        variable = build_model_variable(model_points)

        for row_idx in range(4):
            _assert_live_periods_match(
                uniform["pols_if"][row_idx].to_list(),
                variable["pols_if"][row_idx].to_list(),
                ctx=f"pols_if row={row_idx}",
            )


@st.composite
def _portfolios(draw):
    """A random portfolio: 1-6 policies, integer terms in years, positive counts."""
    n = draw(st.integers(min_value=1, max_value=6))
    terms = draw(st.lists(st.integers(min_value=1, max_value=30), min_size=n, max_size=n))
    counts = draw(
        st.lists(
            st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )
    return terms, counts


def _mp(terms_years: list[int], counts: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "policy_id": [str(i) for i in range(len(terms_years))],
            "policy_term": terms_years,
            "policy_count": counts,
        }
    )


class TestJaggedUniformProperty:
    """Property-based differential test — the core invariant of the whole
    feature: jagged (per-policy) projection must reconcile with the uniform
    grid for ANY portfolio. Live periods match element-wise, the uniform dead
    tail is zero, and portfolio totals are identical.
    """

    @settings(max_examples=40, deadline=None)
    @given(_portfolios())
    def test_jagged_equals_uniform(self, portfolio: tuple[list[int], list[float]]) -> None:
        terms_years, counts = portfolio
        mp = _mp(terms_years, counts)
        uniform = build_model_uniform(mp, projection_months=max(terms_years) * 12)
        variable = build_model_variable(mp)

        for col in ("premium", "claims", "net_cf", "pols_if"):
            for i in range(len(terms_years)):
                u = uniform[col][i].to_list()
                v = variable[col][i].to_list()
                assert len(v) <= len(u)
                for t in range(len(v)):
                    assert math.isclose(u[t], v[t], rel_tol=1e-9, abs_tol=1e-9), (
                        f"{col} policy={i} t={t}: uniform={u[t]} variable={v[t]}"
                    )
                for t in range(len(v), len(u)):
                    assert abs(u[t]) < 1e-9, f"uniform dead tail not zero: {col} i={i} t={t}"
            u_tot = uniform[col].list.sum().sum()
            v_tot = variable[col].list.sum().sum()
            assert math.isclose(u_tot, v_tot, rel_tol=1e-9, abs_tol=1e-6), (
                f"total mismatch {col}: uniform={u_tot} variable={v_tot}"
            )

    @settings(max_examples=30, deadline=None)
    @given(st.lists(st.integers(min_value=0, max_value=30), min_size=1, max_size=6))
    def test_jagged_no_crash_including_zero_term(self, terms_years: list[int]) -> None:
        """Includes 0-term (already-matured) policies — must not crash."""
        out = build_model_variable(_mp(terms_years, [100.0] * len(terms_years)))
        assert out.height == len(terms_years)

    def test_jagged_model_runs_in_optimize_mode(self) -> None:
        """The jagged model must collect in optimize mode (no map_elements
        FATAL) — the discount/curve regression was optimize-only."""
        prev = get_default_mode()
        try:
            set_default_mode("optimize")
            out = build_model_variable(_mp([5, 10, 20], [100.0, 100.0, 100.0]))
            assert out.height == 3
        finally:
            set_default_mode(prev)
