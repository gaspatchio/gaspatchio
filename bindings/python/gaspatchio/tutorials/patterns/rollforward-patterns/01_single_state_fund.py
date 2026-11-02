# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Single-state separate-account VA accumulation (Hardy 2003 §6).

The simplest variable annuity (VA) building block: a separate account
where the policyholder bears full investment risk. Each period the
account value (AV) grows with the fund return, then a Mortality &
Expense (M&E) charge is deducted, and the balance is floored at zero:

    AV_eop = max( AV_bop * (1 + fund_return) * (1 - me_charge), 0 )

Three Ops, one state. Demonstrates the grow → charge → floor chain.

**The floor never bites here, and that is worth seeing rather than
hiding.** For any return above −100% and any charge below 100%, the
product ``AV_bop × (1 + r) × (1 − m)`` is already non-negative, so the
floor puts nothing back in any period and its movement reads 0.00 all
the way down. It stays in the chain because it is what a modeller
writes: the guard is a statement about what this account may never do,
and a guard that never fires is a guard that held. Export this model
and the audit page draws that row at zero in every period — which is
the truth about this model, and is the row you need to be able to read
on the account value that *would* have gone negative.

``main(af)`` takes the frame ``gspio`` builds from
``01_model_points.parquet``, so the same three Ops run under the CLI ——
``gspio calc-graph 01_single_state_fund.py 01_model_points.parquet`` ——
and the artifact carries what each step moved. Running the file directly
does the same thing over the same points and checks the closed form.

Reference: Hardy (2003), *Investment Guarantees: Modeling and Risk
Management for Equity-Linked Life Insurance*, §6.3.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from gaspatchio import ActuarialFrame, compile_rollforward

N_PERIODS = 12

MODEL_POINTS = Path(__file__).with_name("01_model_points.parquet")


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Grow the account, take the M&E charge, floor the balance at zero."""
    af = af.projection.set(
        start_date=date(2025, 1, 31),
        n_periods=N_PERIODS,
        frequency="monthly",
    )

    # No per-policy contract end here — synthetic demo over a fixed
    # horizon. ``contract_boundary=`` is omitted; the kernel runs every
    # period.
    b = af.projection.rollforward(
        states={"av": af["av_init"]},
    )
    (
        b["av"]
        .grow(af["fund_return"], label="fund_return")
        .charge(af["me_charge"], label="me_charge")
        .floor(value=0.0)
    )

    compiled = compile_rollforward(b)
    af.av = compiled.expr_for("av")
    return af


def demo() -> None:
    """Run the model over the shipped points and check it against the closed form."""
    out = main(ActuarialFrame(pl.read_parquet(MODEL_POINTS))).collect()
    av = out.get_column("av").to_list()[0]
    initial = out.get_column("av_init").to_list()[0]
    fund_return_monthly = out.get_column("fund_return").to_list()[0][0]
    me_charge_monthly = out.get_column("me_charge").to_list()[0][0]

    # Closed form: AV_T = AV_0 * ((1 + r) * (1 - m))^T
    period_factor = (1 + fund_return_monthly) * (1 - me_charge_monthly)
    expected_terminal = initial * period_factor**N_PERIODS
    assert abs(av[-1] - expected_terminal) < 1e-6, (
        f"terminal AV {av[-1]} differs from {expected_terminal}"
    )

    print("Single-state fund accumulation (Hardy 2003 §6)")
    print(f"  Initial AV:      {initial:>12,.2f}")
    print(f"  Period factor:   {period_factor:>12.6f}")
    print(f"  After {N_PERIODS}M:       {av[-1]:>12,.2f}")
    print(f"  Closed-form:     {expected_terminal:>12,.2f}")


if __name__ == "__main__":
    demo()
