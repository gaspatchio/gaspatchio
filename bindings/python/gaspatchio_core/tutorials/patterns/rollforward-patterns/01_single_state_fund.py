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

Reference: Hardy (2003), *Investment Guarantees: Modeling and Risk
Management for Equity-Linked Life Insurance*, §6.3.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward


def main() -> None:
    n_periods = 12
    fund_return_monthly = 0.01
    me_charge_monthly = 0.0010

    # One policy. Monthly fund return 1%, monthly M&E charge 0.10%.
    af = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "fund_return": [[fund_return_monthly] * n_periods],
            "me_charge": [[me_charge_monthly] * n_periods],
        },
    )
    af = af.projection.set(
        start_date=date(2025, 1, 31),
        n_periods=n_periods,
        frequency="monthly",
    )

    # No per-policy contract end here — synthetic demo with a single policy
    # over a fixed horizon. ``contract_boundary=`` is omitted; the kernel
    # runs every period.
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
    collector = RollforwardCollector(compiled)
    af.av = collector.expr_for("av")
    av = af.collect().get_column("av").to_list()[0]

    # Closed form: AV_T = AV_0 * ((1 + r) * (1 - m))^T
    period_factor = (1 + fund_return_monthly) * (1 - me_charge_monthly)
    expected_terminal = 100_000.0 * period_factor**n_periods
    assert abs(av[-1] - expected_terminal) < 1e-6, (
        f"terminal AV {av[-1]} differs from {expected_terminal}"
    )

    print("Single-state fund accumulation (Hardy 2003 §6)")
    print(f"  Initial AV:      {100_000.0:>12,.2f}")
    print(f"  Period factor:   {period_factor:>12.6f}")
    print(f"  After {n_periods}M:       {av[-1]:>12,.2f}")
    print(f"  Closed-form:     {expected_terminal:>12,.2f}")


if __name__ == "__main__":
    main()
