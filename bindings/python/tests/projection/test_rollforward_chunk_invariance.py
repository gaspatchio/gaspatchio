# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""GSP-112: rollforward bit-exactness across polars chunk widths.

The state-machine kernel claims bit-identical results regardless of how
polars chunks the input frame. The `array_storage.rs:247` panic (fixed in
2eb556d) survived as long as it did because no test crossed streaming chunk
boundaries — this audit closes that gap for the rollforward kernel.

One realistic UL account-value recurrence (add premium, deduct NAR-based
COI, subtract expense, grow at credited interest, floor at zero) runs over
the same 300-policy portfolio presented to the kernel at chunk widths
{1, 4, 16, 64, 256, single-chunk}. Every width must produce bit-identical
state columns — equality is asserted with ``==`` on the raw values (which
also rejects NaN, since NaN != NaN), not with a tolerance.

If this test ever fails, that is a real correctness bug: root-cause the
kernel rather than loosen the comparison.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule

N_POLICIES = 300
N_PERIODS = 24
CHUNK_WIDTHS = [1, 4, 16, 64, 256]


def _compiled_ul_rollforward(*, jagged: bool = False):
    """The §4.6 UL shape: add, deduct_nar, subtract, grow, floor."""
    if jagged:
        sched = Schedule.from_per_policy_grid(
            start_date=date(2025, 1, 31),
            n_periods=N_PERIODS,
            frequency="1M",
            until_kind="term_months",
            until_value_column="term",
        )
    else:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=N_PERIODS, frequency="1M"
        )
    b = RollforwardBuilder(
        states={"av": pl.col("av_init")},
        points=["bop", "post_coi", "eop"],
        schedule=sched,
    )
    b["av"].between("bop", "post_coi").add(
        pl.col("premium"), label="Premium"
    ).deduct_nar(
        pl.col("coi_rate"), death_benefit=pl.col("sum_assured"), label="COI"
    )
    b["av"].between("post_coi", "eop").subtract(
        pl.col("expense"), label="Expense"
    ).grow(pl.col("interest_rate"), label="Interest").floor(0.0)
    return compile_rollforward(b)


def _portfolio() -> pl.DataFrame:
    """300 deterministic policies with per-policy varying inputs.

    Values vary by policy index so any cross-chunk state bleed produces a
    visible difference, and a subset of policies is engineered to hit the
    zero floor (high expense, low premium) so the floor path is exercised
    across chunk boundaries too.
    """
    rows = []
    for i in range(N_POLICIES):
        floored = i % 7 == 0
        rows.append(
            {
                "policy_id": i,
                "av_init": 50.0 + (i % 13) * 25.0,
                # The kernel takes every non-init input as a per-period list.
                "sum_assured": [10_000.0 + (i % 5) * 5_000.0 for _ in range(N_PERIODS)],
                "premium": [0.0 if floored else 40.0 + (i % 11) for _ in range(N_PERIODS)],
                "coi_rate": [0.0004 + 0.00001 * (i % 9) for _ in range(N_PERIODS)],
                "expense": [
                    (90.0 if floored else 3.0) + 0.1 * (i % 3)
                    for _ in range(N_PERIODS)
                ],
                "interest_rate": [0.003 + 0.0001 * (i % 4) for _ in range(N_PERIODS)],
            }
        )
    return pl.DataFrame(rows)


def _in_chunks(df: pl.DataFrame, width: int) -> pl.DataFrame:
    """The same rows presented to the engine as chunks of ``width`` rows."""
    slices = [df.slice(o, width) for o in range(0, df.height, width)]
    chunked = pl.concat(slices, rechunk=False)
    assert chunked.n_chunks() > 1, "chunking harness failed to produce chunks"
    return chunked


def _run_av(compiled, df: pl.DataFrame) -> list[list[float]]:
    return (
        df.with_columns(av=RollforwardCollector(compiled).expr_for("av"))
        .get_column("av")
        .to_list()
    )


class TestChunkWidthInvariance:
    """Identical inputs at different chunk widths give bit-identical states."""

    @pytest.fixture(scope="class")
    def baseline(self):
        compiled = _compiled_ul_rollforward()
        df = _portfolio().rechunk()
        av = _run_av(compiled, df)
        return compiled, df, av

    def test_baseline_is_sane(self, baseline):
        """The recurrence itself behaves: right shape, floor binds somewhere."""
        _, _, av = baseline
        assert len(av) == N_POLICIES
        assert all(len(row) == N_PERIODS for row in av)
        floored_rows = [row for i, row in enumerate(av) if i % 7 == 0]
        assert any(x == 0.0 for row in floored_rows for x in row), (
            "floor never binds — the fixture no longer exercises Floor"
        )
        unfloored = [row for i, row in enumerate(av) if i % 7 != 0]
        assert all(x > 0.0 for row in unfloored for x in row)

    @pytest.mark.parametrize("width", CHUNK_WIDTHS)
    def test_bit_identical_across_chunk_widths(self, baseline, width):
        compiled, df, av_baseline = baseline
        av_chunked = _run_av(compiled, _in_chunks(df, width))

        for i, (a, b) in enumerate(zip(av_baseline, av_chunked)):
            assert a == b, f"chunk width {width} diverges at policy {i}"

    @pytest.mark.parametrize("width", [1, 16, 256])
    def test_jagged_bit_identical_across_chunk_widths(self, width):
        """Jagged per-policy horizons + chunking — the riskiest combination.

        Jaggedness is DECLARED via a per-policy grid (a ``term`` column carries
        each policy's horizon). The first version of this test fed jagged
        inputs to a uniform calendar-grid schedule and failed at chunk width 1:
        the kernel's old batch-variance heuristic classified single-row chunks
        as "uniform book, wrong length" and errored — chunk-width-dependent
        behaviour, the exact defect this audit exists to catch. The heuristic
        is gone; book shape now comes from the schedule.
        """
        compiled = _compiled_ul_rollforward(jagged=True)
        df = _portfolio().with_columns(
            # Each policy keeps only its own horizon: 1..N_PERIODS periods,
            # declared in `term` and applied to every input list.
            (pl.col("policy_id") % N_PERIODS + 1).alias("term"),
            pl.col("premium").list.head(pl.col("policy_id") % N_PERIODS + 1),
            pl.col("coi_rate").list.head(pl.col("policy_id") % N_PERIODS + 1),
            pl.col("sum_assured").list.head(pl.col("policy_id") % N_PERIODS + 1),
            pl.col("expense").list.head(pl.col("policy_id") % N_PERIODS + 1),
            pl.col("interest_rate").list.head(pl.col("policy_id") % N_PERIODS + 1),
        ).rechunk()

        av_baseline = _run_av(compiled, df)
        assert [len(r) for r in av_baseline] == [
            i % N_PERIODS + 1 for i in range(N_POLICIES)
        ]

        av_chunked = _run_av(compiled, _in_chunks(df, width))
        for i, (a, b) in enumerate(zip(av_baseline, av_chunked)):
            assert a == b, f"jagged: chunk width {width} diverges at policy {i}"
