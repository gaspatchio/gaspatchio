# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Rounding inside the rollforward recursion.

Source models built in spreadsheets round to cents at every step, and that
rounding opens the next period. Rounding only the final answer is a different
calculation — these tests pin the difference so it cannot be optimised away.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward._compile import compile_rollforward

N = 6
INIT = 1_000.0
RATE = 0.0333  # deliberately produces sub-cent digits every period


def _project(*, rounded: bool, decimals: int = 2) -> list[float]:
    """Grow a balance for N periods, optionally rounding inside the recursion."""
    af = ActuarialFrame({"init": [INIT], "rate": [[RATE] * N]})
    af = af.projection.set(
        start_date=date(2025, 12, 31), n_periods=N, frequency="annual"
    )
    b = af.projection.rollforward(states={"av": af["init"]})
    b["av"].grow(af["rate"], label="interest")
    if rounded:
        b["av"].round(decimals)
    af.av = compile_rollforward(b).expr_for("av")
    return af.collect().get_column("av").to_list()[0]


class TestRoundingCompounds:
    """Rounding inside the recursion is not the same as rounding the answer."""

    def test_every_period_lands_on_a_cent(self) -> None:
        for value in _project(rounded=True):
            assert value == pytest.approx(round(value, 2), abs=1e-9)

    def test_matches_a_hand_walked_recursion(self) -> None:
        want, balance = [], INIT
        for _ in range(N):
            balance = round(balance * (1 + RATE), 2)
            want.append(balance)
        assert _project(rounded=True) == pytest.approx(want, abs=1e-9)

    def test_intermediate_balances_diverge_and_the_gap_widens(self) -> None:
        """One period's rounding opens the next, so the error accumulates."""
        rounded = _project(rounded=True)
        unrounded = _project(rounded=False)
        gaps = [abs(r - u) for r, u in zip(rounded, unrounded, strict=True)]
        assert gaps[-1] > gaps[0]

    def test_a_long_projection_diverges_by_more_than_a_cent(self) -> None:
        """Needs a long horizon — over six periods the drift stays sub-cent.

        This is why rounding cannot be deferred to the final answer: it is
        invisible early and material late, which is exactly the failure mode a
        short smoke test would miss.
        """
        periods = 30
        af = ActuarialFrame({"init": [INIT], "rate": [[RATE] * periods]})
        af = af.projection.set(
            start_date=date(2025, 12, 31), n_periods=periods, frequency="annual"
        )
        b = af.projection.rollforward(states={"av": af["init"]})
        b["av"].grow(af["rate"], label="interest")
        b["av"].round(2)
        af.av = compile_rollforward(b).expr_for("av")
        got = af.collect().get_column("av").to_list()[0][-1]

        unrounded = INIT
        for _ in range(periods):
            unrounded *= 1 + RATE

        assert abs(got - round(unrounded, 2)) >= 0.01


class TestExcelTieBreaking:
    """Half away from zero, matching Excel's ROUND — not banker's rounding."""

    @pytest.mark.parametrize(
        ("value", "want"),
        [(0.125, 0.13), (0.135, 0.14), (-0.125, -0.13), (2.675, 2.68)],
    )
    def test_exact_halves_round_away_from_zero(self, value: float, want: float) -> None:
        af = ActuarialFrame({"init": [value], "zero": [[0.0]]})
        af = af.projection.set(
            start_date=date(2025, 12, 31), n_periods=1, frequency="annual"
        )
        b = af.projection.rollforward(states={"s": af["init"]})
        b["s"].grow(af["zero"])
        b["s"].round(2)
        af.s = compile_rollforward(b).expr_for("s")
        got = af.collect().get_column("s").to_list()[0][0]
        assert got == pytest.approx(want, abs=1e-9)

    def test_polars_would_disagree(self) -> None:
        """Guards the choice: banker's rounding gives a different answer."""
        banker = pl.select(pl.lit(0.125).round(2)).item()
        assert banker == pytest.approx(0.12, abs=1e-9)  # half-to-even


class TestDecimalsArgument:
    """Places other than cents, and the refusal."""

    def test_zero_decimals_rounds_to_units(self) -> None:
        af = ActuarialFrame({"init": [10.6], "zero": [[0.0]]})
        af = af.projection.set(
            start_date=date(2025, 12, 31), n_periods=1, frequency="annual"
        )
        b = af.projection.rollforward(states={"s": af["init"]})
        b["s"].grow(af["zero"])
        b["s"].round(0)
        af.s = compile_rollforward(b).expr_for("s")
        assert af.collect().get_column("s").to_list()[0][0] == pytest.approx(11.0)

    def test_negative_decimals_round_to_tens(self) -> None:
        af = ActuarialFrame({"init": [1_234.0], "zero": [[0.0]]})
        af = af.projection.set(
            start_date=date(2025, 12, 31), n_periods=1, frequency="annual"
        )
        b = af.projection.rollforward(states={"s": af["init"]})
        b["s"].grow(af["zero"])
        b["s"].round(-2)
        af.s = compile_rollforward(b).expr_for("s")
        assert af.collect().get_column("s").to_list()[0][0] == pytest.approx(1_200.0)

    def test_absurd_precision_is_refused_by_name(self) -> None:
        af = ActuarialFrame({"init": [1.0], "zero": [[0.0]]})
        af = af.projection.set(
            start_date=date(2025, 12, 31), n_periods=1, frequency="annual"
        )
        b = af.projection.rollforward(states={"s": af["init"]})
        with pytest.raises(ValueError, match="decimals must be between"):
            b["s"].round(40)
