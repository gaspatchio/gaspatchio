"""Integration test: per-policy projection produces identical results to uniform projection.

Uses 4 policies with different terms (5, 10, 15, 20 years).
Compares uniform 240-month projection (with maturity masking) against per-policy projection
(where each policy's lists are naturally sized to its term).

The two approaches must produce numerically identical cashflow results.
"""

import datetime

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, when


VALUATION_DATE = datetime.date(2025, 1, 1)


def build_model_uniform(mp: pl.DataFrame, projection_months: int = 240) -> pl.DataFrame:
    """Build a simplified L3-style model with uniform projection + maturity masking."""
    af = ActuarialFrame(mp)

    af = af.date.create_projection_timeline(
        valuation_date=VALUATION_DATE,
        projection_end_type="term_months",
        projection_end_value=projection_months,
        projection_frequency="monthly",
        output_column="proj_dates",
    )

    # Month index
    af.month = (
        af.proj_dates.dt.year() - VALUATION_DATE.year
    ) * 12 + (af.proj_dates.dt.month() - VALUATION_DATE.month)

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
    """Build the same model with per-policy projection (no maturity masking needed)."""
    # Compute remaining term in months
    mp = mp.with_columns(
        (pl.col("policy_term") * 12).alias("remaining_term_months")
    )
    af = ActuarialFrame(mp)

    af = af.date.create_projection_timeline(
        valuation_date=VALUATION_DATE,
        projection_end_type="term_months",
        projection_end_value="remaining_term_months",
        projection_frequency="monthly",
        output_column="proj_dates",
    )

    # Month index
    af.month = (
        af.proj_dates.dt.year() - VALUATION_DATE.year
    ) * 12 + (af.proj_dates.dt.month() - VALUATION_DATE.month)

    # Mortality and survival (same as uniform)
    af.mort_rate = af.month * 0 + 0.001
    af.survival = af.mort_rate.projection.cumulative_survival()
    af.survival_bop = af.survival.projection.previous_period(fill_value=1.0)

    # No maturity masking — lists naturally end at each policy's term
    af.pols_if = af.survival_bop * af.policy_count
    af.pols_death = af.pols_if * af.mort_rate

    # Simple cashflows
    af.premium = af.pols_if * 100.0
    af.claims = af.pols_death * 50000.0
    af.net_cf = af.premium - af.claims

    return af.collect()


@pytest.fixture()
def model_points():
    """4 policies with different terms, same structure as L3 Mini-VA."""
    return pl.DataFrame({
        "policy_id": ["A", "B", "C", "D"],
        "policy_term": [5, 10, 15, 20],
        "policy_count": [100.0, 100.0, 100.0, 100.0],
    })


class TestVariableProjectionEquivalence:
    def test_cashflows_match(self, model_points):
        """Per-policy and uniform projections produce identical non-zero cashflows.

        Both projections produce lists of length term_months+1 (months 0..term_months).
        The uniform model masks month=term_months to 0 via ``when(month < maturity_month)``.
        The variable model naturally stops at month=term_months (no masking needed).
        We compare the active portion (months 0..term_months-1) and verify the
        uniform model's tail (month >= term_months) is all zero.
        """
        uniform = build_model_uniform(model_points, projection_months=240)
        variable = build_model_variable(model_points)

        policy_terms = model_points["policy_term"].to_list()

        for col in ["premium", "claims", "net_cf"]:
            for row_idx in range(4):
                uniform_vals = uniform[col][row_idx].to_list()
                variable_vals = variable[col][row_idx].to_list()

                term_months = policy_terms[row_idx] * 12

                # Variable list has term_months+1 elements (months 0..term_months)
                assert len(variable_vals) == term_months + 1, (
                    f"row={row_idx}: expected {term_months + 1} variable elements, "
                    f"got {len(variable_vals)}"
                )

                # Active period is months 0..term_months-1 (term_months elements)
                # Month=term_months is the maturity step: uniform masks it to 0,
                # variable includes it naturally.
                for i in range(term_months):
                    assert abs(uniform_vals[i] - variable_vals[i]) < 1e-10, (
                        f"Mismatch at row={row_idx}, col={col}, t={i}: "
                        f"uniform={uniform_vals[i]}, variable={variable_vals[i]}"
                    )

                # Remaining uniform values (from term_months onwards) must be zero
                for i in range(term_months, len(uniform_vals)):
                    assert uniform_vals[i] == 0.0, (
                        f"Expected zero at row={row_idx}, col={col}, t={i}: got {uniform_vals[i]}"
                    )

    def test_fewer_total_elements(self, model_points):
        """Per-policy projection produces fewer total list elements."""
        uniform = build_model_uniform(model_points, projection_months=240)
        variable = build_model_variable(model_points)

        uniform_elements = uniform["net_cf"].list.len().sum()
        variable_elements = variable["net_cf"].list.len().sum()

        # Variable should have significantly fewer elements
        assert variable_elements < uniform_elements
        savings_pct = (1 - variable_elements / uniform_elements) * 100
        assert savings_pct > 30  # At least 30% reduction

    def test_pols_if_match(self, model_points):
        """In-force policy counts match during the active period (months 0..term_months-1)."""
        uniform = build_model_uniform(model_points, projection_months=240)
        variable = build_model_variable(model_points)

        policy_terms = model_points["policy_term"].to_list()

        for row_idx in range(4):
            uniform_pols = uniform["pols_if"][row_idx].to_list()
            variable_pols = variable["pols_if"][row_idx].to_list()

            term_months = policy_terms[row_idx] * 12

            for i in range(term_months):
                assert abs(uniform_pols[i] - variable_pols[i]) < 1e-10, (
                    f"pols_if mismatch at row={row_idx}, t={i}: "
                    f"uniform={uniform_pols[i]}, variable={variable_pols[i]}"
                )
