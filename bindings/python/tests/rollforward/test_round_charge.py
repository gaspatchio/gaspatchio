# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for gh#92 — round_charge rounds the individual flow, not the state.
# ABOUTME: Covers charge/grow/deduct_nar placement semantics and verify() bounds.

"""``round_charge`` reproduces the spreadsheet ROUND placement (gh#92).

Spreadsheets round **individual charges** inside the recursion and leave the
running balance unrounded — ``s -= ROUND(coi, 2)`` — where ``state.round(2)``
rounds the balance and discards the sub-cent residue every period. The two
agree only while the balance is an exact multiple of the rounding unit.
"""

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.rollforward._ops import DeductNAR, Grow


def _frame(**cols: object) -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], **cols}))
    n = max(
        len(v[0]) if isinstance(v, list) and isinstance(v[0], list) else 1
        for v in cols.values()
    )
    return af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=n, frequency="1Y"
    )


def test_charge_round_charge_matches_excel_placement() -> None:
    """``s -= ROUND(s * rate, 2)``; the state carries residue forward.

    t1: 1000 * 0.033333 = 33.333 -> 33.33; s = 966.67
    t2: 966.67 * 0.033333 = 32.2221... -> 32.22; s = 934.45
    """
    af = _frame(av_init=[1000.0], rate=[[0.033333, 0.033333]])
    b = af.projection.rollforward(states={"av": af["av_init"]})
    b["av"].charge(af["rate"], round_charge=2, label="Fee")

    af.eop = compile_rollforward(b).expr_for("av")
    out = af.collect()
    assert out["eop"][0][0] == pytest.approx(966.67, abs=1e-9)
    assert out["eop"][0][1] == pytest.approx(934.45, abs=1e-9)


def test_grow_round_charge_rounds_the_credit() -> None:
    """``s += ROUND(s * rate, 2)``: 1000 * 0.0333333 -> 33.33 credited."""
    af = _frame(av_init=[1000.0], rate=[[0.0333333]])
    b = af.projection.rollforward(states={"av": af["av_init"]})
    b["av"].grow(af["rate"], round_charge=2, label="Interest")

    af.eop = compile_rollforward(b).expr_for("av")
    out = af.collect()
    assert out["eop"][0][0] == pytest.approx(1033.33, abs=1e-9)


def test_deduct_nar_round_charge_bop() -> None:
    """BOP: NAR = 10000 - 1000 = 9000; ROUND(9000 * 0.0012345, 2) = 11.11."""
    af = _frame(av_init=[1000.0], coi=[[0.0012345]], db=[[10000.0]])
    b = af.projection.rollforward(states={"av": af["av_init"]})
    b["av"].deduct_nar(af["coi"], death_benefit=af["db"], round_charge=2, label="COI")

    af.eop = compile_rollforward(b).expr_for("av")
    out = af.collect()
    # Unrounded charge would leave 988.8895; the rounded charge leaves the
    # residue on the state, exactly as the sheet does.
    assert out["eop"][0][0] == pytest.approx(988.89, abs=1e-9)


def test_round_charge_differs_from_state_round() -> None:
    """The two placements diverge once the balance carries residue.

    round_charge keeps the state unrounded (sub-cent residue survives to
    open the next period); state.round discards it. After two periods the
    outputs differ — the difference gh#92 quantified at 2.9e-11 over 111
    years on the Type A workbook, guaranteed nonzero here by construction.
    """

    def build(*, rounded_charge: bool) -> float:
        af = _frame(av_init=[1000.005], rate=[[0.033333, 0.033333]])
        b = af.projection.rollforward(states={"av": af["av_init"]})
        if rounded_charge:
            b["av"].charge(af["rate"], round_charge=2, label="Fee")
        else:
            b["av"].charge(af["rate"], label="Fee")
            b["av"].round(2)
        af.eop = compile_rollforward(b).expr_for("av")
        return float(af.collect()["eop"][0][1])

    charge_placement = build(rounded_charge=True)
    state_placement = build(rounded_charge=False)
    assert charge_placement != state_placement


def test_round_charge_type_is_validated() -> None:
    """A non-int precision is refused at construction, not at Rust deserialization.

    2.0 and True both survive the range check (bool is an int subclass) and
    would otherwise travel to the kernel's Option<i32>, failing far from the
    user's line with a serde error that never names round_charge.
    """
    with pytest.raises(TypeError, match="round_charge"):
        Grow(target=None, rate=pl.lit(0.1), round_charge=2.0).verify()  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="round_charge"):
        Grow(target=None, rate=pl.lit(0.1), round_charge=True).verify()  # type: ignore[arg-type]


def test_round_charge_bounds_are_validated() -> None:
    """Out-of-range precision is refused at construction, as Round does."""
    with pytest.raises(ValueError, match="round_charge"):
        Grow(target=None, rate=pl.lit(0.1), round_charge=99).verify()  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="round_charge"):
        DeductNAR(
            target=None,  # type: ignore[arg-type]
            coi_rate=pl.lit(0.001),
            death_benefit=pl.lit(10000.0),
            round_charge=-99,
        ).verify()
