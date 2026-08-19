# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Scalar input columns broadcast across every period.

A level death benefit, a flat charge rate, or a per-policy flag is one value
per policy. Requiring the caller to materialise ``n_periods`` identical copies
would be ceremony with no meaning, so the kernel accepts the scalar and holds
it constant across the projection.

The equivalence asserted throughout is the one that matters: a scalar must
give bit-identical results to the list of repeated values it stands for.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.rollforward._collector import RollforwardCollector
from gaspatchio.rollforward._compile import compile_rollforward
from gaspatchio.schedule import Schedule

N = 3


def schedule() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=N,
        frequency="1M",
    )


def project(df: pl.DataFrame) -> list[float]:
    """Add a premium then grow — both read from input columns."""
    b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=schedule())
    b["av"].add(pl.col("premium")).grow(pl.col("rate"))
    collector = RollforwardCollector(compile_rollforward(b))
    out = df.with_columns(av=collector.expr_for("av"))
    return out.get_column("av").to_list()[0]


class TestScalarMatchesTheListItStandsFor:
    """A scalar and n copies of it are the same projection."""

    def test_float_scalar(self) -> None:
        scalar = project(
            pl.DataFrame(
                {
                    "init": [100.0],
                    "premium": [10.0],
                    "rate": [[0.05] * N],
                }
            ),
        )
        listed = project(
            pl.DataFrame(
                {
                    "init": [100.0],
                    "premium": [[10.0] * N],
                    "rate": [[0.05] * N],
                }
            ),
        )
        assert scalar == pytest.approx(listed)
        # And it is the arithmetic anyone would do by hand.
        av, want = 100.0, []
        for _ in range(N):
            av = (av + 10.0) * 1.05
            want.append(av)
        assert scalar == pytest.approx(want)

    def test_integer_scalar_is_cast(self) -> None:
        got = project(
            pl.DataFrame(
                {
                    "init": [100.0],
                    "premium": pl.Series([10], dtype=pl.Int64),
                    "rate": [[0.0] * N],
                }
            ),
        )
        assert got == pytest.approx([110.0, 120.0, 130.0])

    def test_every_input_scalar_still_finds_the_horizon(self) -> None:
        """Period count comes from the schedule, not from the first input.

        With no List column present there is nothing to read a length from,
        so a wrong implementation projects a single period and silently
        truncates the run.
        """
        got = project(
            pl.DataFrame({"init": [100.0], "premium": [10.0], "rate": [0.0]}),
        )
        assert len(got) == N


class TestBooleanScalar:
    """Boolean is admitted because the List path already accepts it."""

    def _ratchet(self, when: pl.Series | list) -> list[float]:
        b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=schedule())
        b["av"].ratchet(to=pl.col("floor_to"), when=pl.col("flag"))
        collector = RollforwardCollector(compile_rollforward(b))
        df = pl.DataFrame(
            {
                "init": [100.0],
                "floor_to": [[150.0] * N],
                "flag": when,
            }
        )
        out = df.with_columns(av=collector.expr_for("av"))
        return out.get_column("av").to_list()[0]

    def test_scalar_flag_matches_the_repeated_list(self) -> None:
        scalar = self._ratchet(pl.Series([True], dtype=pl.Boolean))
        listed = self._ratchet([[True] * N])
        assert scalar == pytest.approx(listed)
        assert scalar == pytest.approx([150.0] * N)

    def test_false_scalar_flag_leaves_the_state_alone(self) -> None:
        assert self._ratchet(pl.Series([False], dtype=pl.Boolean)) == pytest.approx(
            [100.0] * N,
        )


class TestRejectsWhatItCannotBroadcast:
    def test_string_names_the_column_and_the_dtype(self) -> None:
        """A String cast to Float64 yields nulls, so guard on the dtype.

        Letting the cast fail would report "null value not supported", which
        describes the symptom rather than the mistake.
        """
        df = pl.DataFrame(
            {
                "init": [100.0],
                "premium": ["ten"],
                "rate": [[0.0] * N],
            }
        )
        with pytest.raises(Exception, match="premium") as excinfo:
            project(df)
        # "str", not "String" — the kernel prints Rust's DataType Display,
        # which spells it differently from polars-Python's repr.
        assert "got str" in str(excinfo.value)
        assert "must be List, Boolean, or numeric" in str(excinfo.value)
