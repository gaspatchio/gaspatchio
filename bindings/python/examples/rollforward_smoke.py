# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

r"""End-to-end smoke for the rollforward public API surface.

Run::

    uv run python \\
        bindings/python/examples/rollforward_smoke.py

If this prints 12 monthly account values starting near 100 and ending near
``100 * 1.01**12 ≈ 112.68`` the accessor, builder, compiler, and collector
have all wired up correctly.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core import (
    ActuarialFrame,
    RollforwardCollector,
    Schedule,
    compile_rollforward,
)


def main() -> None:
    af = ActuarialFrame(
        pl.DataFrame({"av_init": [100.0], "rate": [[0.01] * 12]}),
    )
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )
    rf = af.projection.rollforward(
        states={"av": pl.col("av_init")},
        schedule=sched,
    )
    rf["av"].grow(pl.col("rate"))

    compiled = compile_rollforward(rf)
    collector = RollforwardCollector(compiled)
    af.av = collector.expr_for("av")

    result = af.collect()
    print(result.select("av"))

    av = result.get_column("av").to_list()[0]
    expected_terminal = 100.0 * (1.01**12)
    assert abs(av[-1] - expected_terminal) < 1e-9, (
        f"final AV {av[-1]} differs from {expected_terminal}"
    )
    print(f"\nFinal AV: {av[-1]:.4f} (expected: {expected_terminal:.4f}) ✓")


if __name__ == "__main__":
    main()
