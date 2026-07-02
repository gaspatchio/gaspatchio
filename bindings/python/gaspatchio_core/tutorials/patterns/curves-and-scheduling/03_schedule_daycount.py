# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Day-count conventions: ``OneTwelfth`` vs ``ActualActualISDA`` over leap-Feb.

A monthly projection has to answer "how much of a year is one period?" — and the
answer is not free. The actuarial default, ``OneTwelfth``, says every month is
exactly ``1/12`` of a year, ignoring that February is shorter and a leap
February longer. That is correct for ~80% of life models (VM-20/VM-21, SII,
IFRS 17 practice). But for a precise EIOPA / SII discounting basis you want
``ActualActualISDA`` — actual days over the actual year length — and across a
leap year the two diverge measurably.

This script builds the **same** monthly grid two ways, spanning the 2024 leap
February, and makes the contrast vivid. The conventions are grounded from
``schedule/_day_count.py`` so the hand calc matches the *implemented* Act/Act
ISDA formula, not a textbook variant:

  - ``OneTwelfth.year_fraction`` is whole-months / 12 (``_day_count.py:60``) —
    so every monthly period is **exactly** ``1/12``, date-independent.
  - ``ActualActualISDA.year_fraction`` for a same-year period is
    ``(end - start).days / (366 if leap else 365)`` (``_day_count.py:166``). The
    2024 numerator-and-denominator are both leap-aware, so:
      * Jan 31 → Feb 29 2024 (29 days)  = ``29 / 366`` ≈ 0.07923  (**below** 1/12)
      * Feb 29 → Mar 31 2024 (31 days)  = ``31 / 366`` ≈ 0.08470  (**above** 1/12)
  - ``period_dates()`` returns ``n_periods + 1`` boundary dates (inclusive of
    both endpoints).

A clean ``uv run python 03_schedule_daycount.py`` (exit 0, asserts pass) is the
test.

Reference: ISDA day-count fraction definitions (Act/Act ISDA); EIOPA risk-free
term-structure technical documentation (day-count basis for sub-annual
discounting). Source of truth: ``gaspatchio_core/schedule/_day_count.py``.
"""

from __future__ import annotations

from datetime import date

from gaspatchio_core import ActualActualISDA, OneTwelfth, Schedule

START_DATE = date(2024, 1, 31)  # month-end anchor; 2024 is a leap year
N_PERIODS = 14  # Jan 2024 -> Mar 2025: spans the leap February

ONE_TWELFTH = 1.0 / 12.0


def main() -> None:
    # Same grid, two day-counts. anchor defaults to "month_end", so the
    # February boundary lands on the 29th (leap) — not the 28th.
    sched_otf = Schedule.from_calendar_grid(
        start_date=START_DATE,
        n_periods=N_PERIODS,
        frequency="1M",
        day_count=OneTwelfth(),
    )
    sched_aa = Schedule.from_calendar_grid(
        start_date=START_DATE,
        n_periods=N_PERIODS,
        frequency="1M",
        day_count=ActualActualISDA(),
    )

    boundaries = sched_aa.period_dates()  # day-count does not change the dates
    otf_yf = sched_otf.year_fractions()
    aa_yf = sched_aa.year_fractions()

    # --- period_dates() has n_periods + 1 boundaries --------------------
    assert len(boundaries) == N_PERIODS + 1, (
        f"expected {N_PERIODS + 1} boundary dates, got {len(boundaries)}"
    )
    # Month-end anchoring put the leap day on the grid: Feb 29 2024.
    assert boundaries[1] == date(2024, 2, 29), (
        f"month-end anchor should land on the leap day; got {boundaries[1]}"
    )

    # --- OneTwelfth: EVERY period is exactly 1/12 -----------------------
    for t, yf in enumerate(otf_yf):
        assert abs(yf - ONE_TWELFTH) < 1e-15, (
            f"OneTwelfth period {t} = {yf} != 1/12"
        )

    # --- ActualActualISDA: matches the source-grounded hand calc --------
    # Period 0 spans Jan 31 -> Feb 29 2024 (29 actual days). Same calendar
    # year, which is a leap year, so the denominator is 366.
    hand_leap_feb = (boundaries[1] - boundaries[0]).days / 366.0
    assert abs(aa_yf[0] - hand_leap_feb) < 1e-15, (
        f"Act/Act period 0 = {aa_yf[0]} != 29/366 = {hand_leap_feb}"
    )
    # Period 1 spans Feb 29 -> Mar 31 2024 (31 actual days) / 366.
    hand_feb_mar = (boundaries[2] - boundaries[1]).days / 366.0
    assert abs(aa_yf[1] - hand_feb_mar) < 1e-15, (
        f"Act/Act period 1 = {aa_yf[1]} != 31/366 = {hand_feb_mar}"
    )

    # --- the contrast is real: Act/Act differs from 1/12 at the leap ----
    # The short Jan->Feb period sits BELOW 1/12; the 31-day Feb->Mar period
    # sits ABOVE. A flat 1/12 erases this — the whole point of Act/Act.
    assert aa_yf[0] < ONE_TWELFTH, (
        f"leap Jan->Feb {aa_yf[0]} should be below 1/12 {ONE_TWELFTH}"
    )
    assert aa_yf[1] > ONE_TWELFTH, (
        f"Feb->Mar {aa_yf[1]} should be above 1/12 {ONE_TWELFTH}"
    )
    # Whole horizon: the two conventions disagree (otherwise the contrast is
    # vacuous). Act/Act sums to slightly more than 14/12 across this 2024-2025
    # window because most months exceed 1/12.
    assert abs(sum(aa_yf) - sum(otf_yf)) > 1e-6, (
        "Act/Act and OneTwelfth totals coincide — contrast would be vacuous"
    )

    print("Schedule day-counts — OneTwelfth (flat) vs Act/Act ISDA (leap-aware)")
    print(f"  Grid: {boundaries[0]} -> {boundaries[-1]}  ({N_PERIODS} periods)")
    print(f"  Boundary count       : {len(boundaries)}  (== n_periods + 1)")
    print(f"  OneTwelfth, period 0 : {otf_yf[0]:.8f}  (Jan->Feb, flat 1/12)")
    print(f"  Act/Act,    period 0 : {aa_yf[0]:.8f}  (29/366, BELOW 1/12)")
    print(f"  Act/Act,    period 1 : {aa_yf[1]:.8f}  (31/366, ABOVE 1/12)")
    print(f"  Sum OneTwelfth       : {sum(otf_yf):.8f}")
    print(f"  Sum Act/Act ISDA     : {sum(aa_yf):.8f}  (they disagree)")


if __name__ == "__main__":
    main()
