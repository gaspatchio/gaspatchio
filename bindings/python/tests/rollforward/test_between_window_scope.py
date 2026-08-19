# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Regression tests for gh#101 — .between() windows are handle-scoped.
# ABOUTME: A plain b["state"] op defaults to eop even after a windowed chain.

"""``.between()`` scope belongs to the handle, not the builder (gh#101).

The docs promise: steps chained from a ``.between(p1, p2)`` handle land on
``p2``; steps on a plain ``b["state"]`` handle default to ``eop``. Before the
fix the window stuck to the builder, so the doc's own example silently
captured end-of-period values under the mid-chain point's name.
"""

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward


def _frame() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "av_init": [1000.0],
                "me_rate": [[0.1, 0.1, 0.1]],
                "fund_return": [[0.5, 0.5, 0.5]],
            }
        )
    )
    return af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=3, frequency="1Y"
    )


def test_docs_example_plain_handle_defaults_to_eop() -> None:
    """The multi-state doc's own example: the grow step lands on eop.

    charge 10% into post_charge, then grow 50% on a plain handle. Period 1:
    post_charge = 1000 * 0.9 = 900, eop = 900 * 1.5 = 1350. Before the fix
    both read 1350 — the grow silently landed on post_charge.
    """
    af = _frame()
    b = af.projection.rollforward(
        states={"av": af["av_init"]},
        points=("bop", "post_charge", "eop"),
    )
    b["av"].between("bop", "post_charge").charge(af["me_rate"], label="M&E Fee")
    b["av"].grow(af["fund_return"], label="Fund Return")

    compiled = compile_rollforward(b)
    af.post_charge = compiled.expr_for("av", point="post_charge")
    af.eop = compiled.expr_for("av", point="eop")
    out = af.collect()

    assert out["post_charge"][0][0] == pytest.approx(900.0)
    assert out["eop"][0][0] == pytest.approx(1350.0)


def test_window_persists_within_a_chain() -> None:
    """Ops chained from the between() handle all land on the window end."""
    af = _frame()
    b = af.projection.rollforward(
        states={"av": af["av_init"]},
        points=("bop", "post_charge", "eop"),
    )
    h = b["av"].between("bop", "post_charge")
    h.charge(af["me_rate"], label="Fee 1").charge(af["me_rate"], label="Fee 2")
    b["av"].between("post_charge", "eop").grow(af["fund_return"], label="Growth")

    compiled = compile_rollforward(b)
    af.post_charge = compiled.expr_for("av", point="post_charge")
    af.eop = compiled.expr_for("av", point="eop")
    out = af.collect()

    # Both charges inside the window: 1000 * 0.9 * 0.9 = 810; then grow: 1215.
    assert out["post_charge"][0][0] == pytest.approx(810.0)
    assert out["eop"][0][0] == pytest.approx(1215.0)


def test_second_builder_state_unaffected_by_first_states_window() -> None:
    """A window on one state never leaks onto another state's handle."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "av_init": [1000.0],
                "sv_init": [500.0],
                "me_rate": [[0.1, 0.1, 0.1]],
                "fund_return": [[0.5, 0.5, 0.5]],
            }
        )
    )
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=3, frequency="1Y"
    )
    b = af.projection.rollforward(
        states={"av": af["av_init"], "sv": af["sv_init"]},
        points=("bop", "post_charge", "eop"),
    )
    b["av"].between("bop", "post_charge").charge(af["me_rate"], label="Fee")
    b["sv"].grow(af["fund_return"], label="SV Growth")

    compiled = compile_rollforward(b)
    af.sv_eop = compiled.expr_for("sv", point="eop")
    out = af.collect()

    # sv grows the full period on a plain handle: 500 * 1.5 = 750.
    assert out["sv_eop"][0][0] == pytest.approx(750.0)
