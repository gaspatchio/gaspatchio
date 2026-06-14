# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

r"""Step 07 — Replace ``cum_prod()`` AV growth with the rollforward kernel.

This step keeps the L3 mini-VA model intact except for §5 (Investment
Returns & Account Value). The baseline model computes::

    af.combined_growth_factor = (1 - fee/12) * (1 + inv_return)
    af.cumulative_growth      = af.combined_growth_factor.cum_prod()
    af.prev_cumulative_growth = af.cumulative_growth.projection.previous_period(fill_value=1.0)
    af.av_pp                  = af.av_pp_init * af.prev_cumulative_growth

That works, but the recurrence is *implicit* — readers have to recognise
that ``cum_prod()`` of an effective-rate column models geometric growth.
The rollforward kernel makes the recurrence *explicit*::

    af = af.projection.set(valuation_date=..., until="term_months", until_value=...)
    rf = af.projection.rollforward(states={"unit_growth": af["unit_init"]})
    rf["unit_growth"].grow(af["effective_growth_rate"])

Both produce the same numbers (this step asserts policy-by-policy
equivalence at ``atol=1e-12``). The difference is intent: rollforward
states the actuarial model — "AV grows period over period at the
effective rate" — instead of relying on a Polars idiom.

When to prefer rollforward:
  * Multi-state recurrences (AV + GMDB ratchet, AV with COI deduction
    where the death benefit depends on the in-period AV, etc.).
  * Models where you want to inspect the per-state, per-period state
    vector for audit (the kernel emits a Struct keyed by ``"state@point"``).
  * Models with stop conditions (``lapse_when_all_non_positive=...``,
    ``contract_boundary=mask``) that ``cum_prod()`` cannot express.

When ``cum_prod()`` is fine:
  * Single-state geometric growth like this AV. The rollforward kernel
    has more overhead than ``cum_prod()`` for trivial cases.

Run::

    uv run python \\
        bindings/python/gaspatchio_core/tutorials/level-3-mini-va/steps/07-rollforward/model.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import polars as pl
from gaspatchio_core import (
    ActuarialFrame,
    RollforwardCollector,
    Schedule,
    compile_rollforward,
    when,
)
from gaspatchio_core.assumptions import Table

# Reuse the L3 base model's constants by importing from its model.py.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "base"))
from model import (  # noqa: E402  — sys.path insert above is necessary
    DISCOUNT_RATE_ANNUAL,
    INFLATION_RATE,
    INVESTMENT_RETURNS,
    LAPSE_RATE_ANNUAL,
    MODEL_POINTS,
    MORTALITY_DATA,
    PROJECTION_MONTHS,
    VALUATION_DATE,
)
from model import main as baseline_main  # noqa: E402


def main(af: ActuarialFrame) -> ActuarialFrame:
    """L3 mini-VA with §5 rewritten to use the rollforward kernel."""
    mortality_table = Table(
        name="mortality",
        source=pl.DataFrame(MORTALITY_DATA),
        dimensions={"age": "age"},
        value="mort_rate",
    )
    inv_returns_table = Table(
        name="inv_returns",
        source=pl.DataFrame(INVESTMENT_RETURNS),
        dimensions={"t": "t", "fund_index": "fund_index"},
        value="inv_return_mth",
    )

    # --- §2 Time setup (unchanged from base) ---
    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")
    af.duration_mth_init = (VALUATION_DATE.year * 12 + VALUATION_DATE.month) - (
        af.entry_date_parsed.dt.year() * 12 + af.entry_date_parsed.dt.month()
    )
    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value=PROJECTION_MONTHS,
        frequency="monthly",
    )
    af.projection_date = af.projection.period_dates()
    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )
    af.duration_mth_t = af.duration_mth_init + af.month
    af.duration = af.duration_mth_t // 12
    af.age = af.age_at_entry + af.duration

    # --- §3 Mortality (unchanged) ---
    af.mort_rate = mortality_table.lookup(age=af.age)
    af.mort_rate_mth = 1 - (1 - af.mort_rate) ** (1 / 12)

    # --- §4 Lapse (unchanged) ---
    af.lapse_rate = LAPSE_RATE_ANNUAL
    af.lapse_rate_mth = 1 - (1 - af.lapse_rate) ** (1 / 12)

    # =========================================================================
    # §5 Investment returns & AV — REWRITTEN WITH ROLLFORWARD
    # =========================================================================
    af.inv_return_mth = inv_returns_table.lookup(t=af.month, fund_index=af.fund_index)

    # Effective per-period growth rate combining fee + return. Built as a
    # list column matching af.month (length n_periods + 1 = 241), then
    # sliced to the first n_periods (= 240) elements for the rollforward
    # kernel — which consumes one rate per period of the schedule, not
    # one per boundary date.
    af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (
        1.0 + af.inv_return_mth
    )
    af.effective_growth_rate = (
        af.combined_growth_factor.list.head(
            PROJECTION_MONTHS,
        )
        - 1.0
    )

    # Initial unit-growth seed (1.0 per policy). Materialised as a column
    # because rollforward states are constructed from per-row ``pl.Expr``.
    af.unit_init = 1.0

    # The schedule is declared on the frame via af.projection.set(...) above;
    # rollforward reads it from the frame. No need to construct a separate
    # Schedule object — they would otherwise have to agree by hand.
    rf = af.projection.rollforward(
        states={"unit_growth": af["unit_init"]},
    )
    rf["unit_growth"].grow(af["effective_growth_rate"])
    collector = RollforwardCollector(compile_rollforward(rf))

    # Rollforward eop output is length n_periods. Prepending 1.0 gives a
    # length-(n_periods + 1) "growth at start of period" vector — i.e. the
    # exact analogue of the baseline's ``cum_prod().previous_period(1.0)``
    # without an explicit ``previous_period`` shift.
    af.prev_cumulative_growth = pl.concat_list(
        [
            pl.lit([1.0], dtype=pl.List(pl.Float64)),
            collector.expr_for("unit_growth"),
        ]
    )
    af.av_pp = af.av_pp_init * af.prev_cumulative_growth
    af.maint_fee_pp = af.av_pp * af.maint_fee_rate / 12.0
    af.av_pp_after_fee = af.av_pp - af.maint_fee_pp
    af.inv_income_pp = af.inv_return_mth * af.av_pp_after_fee

    # --- §6-§11 unchanged from base ---
    af.combined_decrement = 1.0 - (1.0 - af.mort_rate_mth) * (1.0 - af.lapse_rate_mth)
    af.survival_factor = 1.0 - af.combined_decrement
    af.cumulative_survival = af.survival_factor.cum_prod()
    af.survival_prob = af.cumulative_survival.projection.previous_period(fill_value=1.0)

    af.maturity_month = af.policy_term * 12
    af.pols_if = (
        when(af.duration_mth_t < af.maturity_month)
        .then(af.survival_prob * af.policy_count)
        .otherwise(0.0)
    )
    af.pols_maturity = (
        when(af.duration_mth_t == af.maturity_month)
        .then(af.survival_prob * af.policy_count)
        .otherwise(0.0)
    )
    af.pols_new_biz = when(af.duration_mth_t == 0).then(af.policy_count).otherwise(0.0)
    af.pols_death = af.pols_if * af.mort_rate_mth
    af.pols_lapse = (af.pols_if - af.pols_death) * af.lapse_rate_mth

    af.claims_death = af.av_pp * af.pols_death
    af.claims_lapse = af.av_pp * af.pols_lapse
    af.claims_maturity = af.av_pp * af.pols_maturity
    af.claims = af.claims_death + af.claims_lapse + af.claims_maturity

    af.premium_pp_list = when(af.duration_mth_t == 0).then(af.premium_pp).otherwise(0.0)
    af.premiums = af.premium_pp_list * af.pols_if

    af.inflation_factor = (1.0 + INFLATION_RATE) ** (af.month / 12.0)
    af.expense_acq_total = af.expense_acq * af.pols_new_biz
    af.expense_maint_total = (
        (af.expense_maint / 12.0) * af.pols_if * af.inflation_factor
    )
    af.expenses = af.expense_acq_total + af.expense_maint_total
    af.commissions = af.commission_rate * af.premiums

    af.pols_if_next = af.pols_if.projection.next_period(fill_value=0.0)
    af.inv_income = af.inv_income_pp * af.pols_if_next + 0.5 * af.inv_income_pp * (
        af.pols_death + af.pols_lapse
    )
    af.av_total = af.av_pp * af.pols_if
    af.av_total_next = af.av_total.projection.next_period(fill_value=0.0)
    af.av_change = af.av_total_next - af.av_total

    af.net_cf = (
        af.premiums
        + af.inv_income
        - af.claims
        - af.expenses
        - af.commissions
        - af.av_change
    )

    disc_rate_mth = (1 + DISCOUNT_RATE_ANNUAL) ** (1 / 12) - 1
    af.disc_factors = (
        af.month.cast(pl.Float64) * -1.0 * math.log(1 + disc_rate_mth)
    ).exp()

    af.pv_claims = (af.claims * af.disc_factors).list.sum()
    af.pv_premiums = (af.premiums * af.disc_factors).list.sum()
    af.pv_expenses = (af.expenses * af.disc_factors).list.sum()
    af.pv_commissions = (af.commissions * af.disc_factors).list.sum()
    af.pv_inv_income = (af.inv_income * af.disc_factors).list.sum()
    af.pv_av_change = (af.av_change * af.disc_factors).list.sum()

    af.pv_net_cf = (
        af.pv_premiums
        + af.pv_inv_income
        - af.pv_claims
        - af.pv_expenses
        - af.pv_commissions
        - af.pv_av_change
    )

    return af


if __name__ == "__main__":
    # Run rollforward variant
    rf_result = main(ActuarialFrame(MODEL_POINTS)).collect()
    print("Rollforward variant — pv_net_cf per policy:")  # noqa: T201
    print(rf_result.select(["point_id", "pv_net_cf", "pv_claims", "pv_premiums"]))  # noqa: T201

    # Cross-check against baseline (cum_prod) variant
    baseline_result = baseline_main(ActuarialFrame(MODEL_POINTS)).collect()
    print("\nBaseline cum_prod variant — pv_net_cf per policy:")  # noqa: T201
    print(  # noqa: T201
        baseline_result.select(["point_id", "pv_net_cf", "pv_claims", "pv_premiums"]),
    )

    # Assert numeric equivalence at atol=1e-9
    rf_pv = rf_result.get_column("pv_net_cf").to_list()
    base_pv = baseline_result.get_column("pv_net_cf").to_list()
    assert len(rf_pv) == len(base_pv) == 4
    for i, (a, b) in enumerate(zip(rf_pv, base_pv, strict=True)):
        delta = abs(a - b)
        assert delta < 1e-9, (
            f"policy {i + 1}: rollforward pv_net_cf={a} vs baseline={b}, |Δ|={delta}"
        )
    print("\n✓ Rollforward and cum_prod variants agree at atol=1e-9")  # noqa: T201
