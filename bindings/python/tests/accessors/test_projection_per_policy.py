# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for per-policy (jagged) projection timelines.

``af.projection.set(..., per_policy=True)`` with a per-policy ``until_value``
column produces variable-length list columns — each policy projects only as
long as its own horizon, recovering the compute/memory of the pre-#104
``create_projection_timeline`` behaviour while keeping the new projection API.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, when

VALUATION = date(2025, 1, 1)


def _project_premiums(*, per_policy: bool) -> float:
    """Project a term-bounded premium cashflow; return the portfolio total.

    Mirrors the L4/L5 pattern: derive ``month`` from the projection dates, pay a
    flat premium only while in force (``month <= remaining_term_months``).
    Uniform zeroes the dead tail; jagged omits it. Totals must match exactly.
    """
    af = ActuarialFrame(
        {"policy_id": ["a", "b", "c"], "remaining_term_months": [3, 6, 12]}
    )
    af = af.projection.set(
        valuation_date=VALUATION,
        until="term_months",
        until_value="remaining_term_months",
        frequency="monthly",
        per_policy=per_policy,
    )
    af.projection_date = af.projection.period_dates()
    af.month = (af.projection_date.dt.year() - VALUATION.year) * 12 + (
        af.projection_date.dt.month() - VALUATION.month
    )
    af.premium = when(af.month <= af.remaining_term_months).then(100.0).otherwise(0.0)
    result = af.collect()
    return sum(result["premium"].list.sum().to_list())


class TestPerPolicyJaggedTimeline:
    """per_policy=True yields variable-length per-policy timelines."""

    def test_period_dates_length_varies_per_policy(self) -> None:
        """Each policy's timeline length equals its own horizon + 1."""
        # Two policies with different remaining horizons.
        af = ActuarialFrame(
            {"policy_id": ["short", "long"], "remaining_term_months": [12, 24]}
        )
        af = af.projection.set(
            valuation_date=VALUATION,
            until="term_months",
            until_value="remaining_term_months",
            frequency="monthly",
            per_policy=True,
        )
        af.projection_date = af.projection.period_dates()
        result = af.collect()

        lengths = result["projection_date"].list.len().to_list()
        # closed="both" -> n_periods + 1 boundary dates per policy.
        assert lengths == [13, 25]

    def test_num_proj_months_is_per_policy(self) -> None:
        """The eager num_proj_months stamp is per-policy, not portfolio-wide."""
        af = ActuarialFrame(
            {"policy_id": ["short", "long"], "remaining_term_months": [12, 24]}
        )
        af = af.projection.set(
            valuation_date=VALUATION,
            until="term_months",
            until_value="remaining_term_months",
            frequency="monthly",
            per_policy=True,
        )
        result = af.collect()
        assert result["num_proj_months"].to_list() == [13, 25]


class TestPerPolicyGuardrails:
    """per_policy schedules flow into rollforward as jagged timelines."""

    def test_rollforward_accepts_per_policy_schedule(self) -> None:
        """rollforward() supports jagged (per_policy) schedules — each policy
        projects only its own horizon. The kernel derives per-policy period
        counts from the input-list lengths, so a shared period axis is not
        required (this was previously rejected with a ValueError).
        """
        af = ActuarialFrame({"policy_id": ["P1"], "remaining_term_months": [12]})
        af = af.projection.set(
            valuation_date=VALUATION,
            until="term_months",
            until_value="remaining_term_months",
            frequency="monthly",
            per_policy=True,
        )
        # No longer raises; returns a usable builder on a jagged frame.
        builder = af.projection.rollforward(
            states={"av": af["remaining_term_months"]}
        )
        assert builder is not None

    def test_per_policy_requires_column_until_value(self) -> None:
        """per_policy=True needs a per-policy column until_value, not a scalar."""
        af = ActuarialFrame({"policy_id": ["P1"]})
        with pytest.raises(ValueError, match="column name"):
            af.projection.set(
                valuation_date=VALUATION,
                until="term_months",
                until_value=24,  # scalar — not a per-policy column
                frequency="monthly",
                per_policy=True,
            )


class TestAutoDefault:
    """Jagged is the default; per_policy=False opts out to a uniform grid."""

    def test_column_term_until_value_defaults_to_jagged(self) -> None:
        """A column until_value with a term_* horizon auto-selects jagged."""
        af = ActuarialFrame({"policy_id": ["a", "b"], "remaining_term_months": [12, 24]})
        af = af.projection.set(
            valuation_date=VALUATION,
            until="term_months",
            until_value="remaining_term_months",
            frequency="monthly",
            # per_policy defaults to None -> auto -> jagged
        )
        assert af._projection._kind == "per_policy_grid"  # noqa: SLF001
        assert af.collect()["num_proj_months"].to_list() == [13, 25]

    def test_per_policy_false_opts_out_to_uniform(self) -> None:
        """per_policy=False forces a uniform grid sized to the longest policy."""
        af = ActuarialFrame({"policy_id": ["a", "b"], "remaining_term_months": [12, 24]})
        af = af.projection.set(
            valuation_date=VALUATION,
            until="term_months",
            until_value="remaining_term_months",
            frequency="monthly",
            per_policy=False,
        )
        assert af._projection._kind == "from_calendar_grid"  # noqa: SLF001
        assert af.collect()["num_proj_months"].to_list() == [25, 25]


class TestPerPolicyReconciliation:
    """Jagged economic outputs must equal the uniform answer key."""

    def test_term_bounded_cashflow_total_matches_uniform(self) -> None:
        """Jagged economic totals reconcile with the uniform answer key."""
        uniform_total = _project_premiums(per_policy=False)
        jagged_total = _project_premiums(per_policy=True)
        # 100 per in-force month, months 0..term inclusive: (3+1)+(6+1)+(12+1)=24
        assert uniform_total == pytest.approx(24 * 100.0)
        assert jagged_total == pytest.approx(uniform_total)


class TestJaggedAccessors:
    """Schedule accessors (year_fractions/anniversary/masks) on jagged grids."""

    @staticmethod
    def _jagged(terms: list[int | None]) -> ActuarialFrame:
        af = ActuarialFrame({"pid": list(range(len(terms))), "term_months": terms})
        return af.projection.set(
            valuation_date=VALUATION,
            until="term_months",
            until_value="term_months",
            frequency="monthly",  # column term_* -> auto jagged
        )

    def test_year_fractions_per_policy_length(self) -> None:
        af = self._jagged([12, 24])
        af.yf = af.projection.year_fractions()
        assert [len(x) for x in af.collect()["yf"].to_list()] == [12, 24]

    def test_t_years_per_policy_length(self) -> None:
        af = self._jagged([12, 24])
        af.ty = af.projection.t_years()
        rows = af.collect()["ty"].to_list()
        assert [len(x) for x in rows] == [13, 25]
        assert rows[0][-1] == pytest.approx(1.0)  # 12 months == 1 year

    def test_anniversary_mask_per_policy_length(self) -> None:
        af = self._jagged([24, 12])
        af.an = af.projection.anniversary_mask()
        rows = af.collect()["an"].to_list()
        assert [len(x) for x in rows] == [24, 12]
        # 24-month policy: anniversaries at months 12 and 24 (indices 11, 23).
        assert [i for i, v in enumerate(rows[0]) if v] == [11, 23]

    def test_negative_term_yields_empty_mask(self) -> None:
        af = self._jagged([12, -3])
        af.m = af.projection.is_in_force()
        assert [len(x) for x in af.collect()["m"].to_list()] == [12, 0]

    def test_null_term_yields_empty_mask(self) -> None:
        af = self._jagged([12, None])
        af.m = af.projection.is_in_force()
        rows = af.collect()["m"].to_list()
        # null term clamps to an empty mask, not a null element.
        assert [None if x is None else len(x) for x in rows] == [12, 0]

    def test_end_date_column_rejected_on_jagged(self) -> None:
        af = self._jagged([12, 12])
        with pytest.raises(ValueError, match="end_date_column is not supported"):
            af.projection.is_in_force(end_date_column="term_months")
        with pytest.raises(ValueError, match="end_date_column is not supported"):
            af.projection.contract_boundary(end_date_column="term_months")

    def test_t_years_per_policy_length_for_discounting(self) -> None:
        """t_years() yields per-policy cumulative year fractions (length =
        per-policy boundaries) — the input to per-period discounting via
        af.finance.discount_factor on jagged frames."""
        af = self._jagged([12, 24])
        af.ty = af.projection.t_years()
        rows = af.collect()["ty"].to_list()
        assert [len(x) for x in rows] == [13, 25]
        assert rows[0][0] == pytest.approx(0.0)
        assert rows[0][12] == pytest.approx(1.0)  # 12 months -> 1.0 year


class TestMustFixHardening:
    """Edge cases hardened after jagged became the default."""

    def test_num_proj_months_is_signed_no_underflow(self) -> None:
        """num_proj_months must be a signed int so `num_proj_months - k` can go
        negative instead of underflowing the unsigned list.len()."""
        af = ActuarialFrame({"pid": [0, 1], "term_months": [12, 24]})
        af = af.projection.set(
            valuation_date=VALUATION,
            until="term_months",
            until_value="term_months",
            frequency="monthly",
        )
        df = af.collect()
        assert df["num_proj_months"].dtype == pl.Int32
        sub = df.select((pl.col("num_proj_months") - 13).alias("s"))["s"].to_list()
        assert sub == [0, 12]  # not [0, 18446744073709551607]

    def test_with_period_positive_index_does_not_grow_short_policies(self) -> None:
        """A fixed positive period index must not append a phantom value to
        policies shorter than that index."""
        af = ActuarialFrame({"pid": [0, 1, 2], "term_months": [4, 7, 3]})
        af = af.projection.set(
            valuation_date=VALUATION,
            until="term_months",
            until_value="term_months",
            frequency="monthly",
        )
        af.prem = pl.int_ranges(0, pl.col("num_proj_months") - 1).list.eval(
            pl.lit(1.0)
        )
        before = [len(x) for x in af.collect()["prem"].to_list()]
        af.adj = af.prem.projection.with_period(4, value=0.0)
        after = [len(x) for x in af.collect()["adj"].to_list()]
        assert before == after == [4, 7, 3]

    def test_term_months_weekly_frequency_rejected(self) -> None:
        """term_* horizons with a sub-month cadence are ambiguous -> rejected."""
        af = ActuarialFrame({"pid": [0], "term_months": [12]})
        with pytest.raises(ValueError, match="month-aligned frequency"):
            af.projection.set(
                valuation_date=VALUATION,
                until="term_months",
                until_value="term_months",
                frequency="weekly",
            )

    def test_with_period_negative_oor_does_not_grow_short_policies(self) -> None:
        """A negative period index out of range for a short (jagged) policy must
        leave that row unchanged, not grow/corrupt it."""
        af = ActuarialFrame({"pid": [0, 1], "term_months": [2, 5]})
        af = af.projection.set(
            valuation_date=VALUATION,
            until="term_months",
            until_value="term_months",
            frequency="monthly",
        )
        af.prem = pl.int_ranges(0, pl.col("num_proj_months") - 1).list.eval(
            pl.lit(100.0)
        )
        before = [len(x) for x in af.collect()["prem"].to_list()]
        af.adj = af.prem.projection.with_period(-3, value=5.0)
        after = af.collect()["adj"].to_list()
        assert [len(x) for x in after] == before == [2, 5]
        assert after[0] == [100.0, 100.0]  # len-2 row: -3 is OOR -> unchanged
        # len-5 row: -3 IS in range -> third-from-last replaced.
        assert after[1] == [100.0, 100.0, 5.0, 100.0, 100.0]
