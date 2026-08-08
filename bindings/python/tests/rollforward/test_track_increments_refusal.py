# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""track_increments=True refuses loudly at build time (gh#69).

The kernel does not yet emit increment fields, so a builder that accepts
the flag promises a feature that fails only at collect time, phrased as a
wrong field name. Until emission lands, the builder refuses the flag at
the call that asks for it.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.schedule import Schedule


def _sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


class TestBuilderRefusal:
    def test_flag_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="gh#69"):
            RollforwardBuilder(
                states={"av": pl.col("init")},
                schedule=_sched(),
                track_increments=True,
            )

    def test_message_names_the_gap_and_the_next_move(self) -> None:
        with pytest.raises(NotImplementedError) as excinfo:
            RollforwardBuilder(
                states={"av": pl.col("init")},
                schedule=_sched(),
                track_increments=True,
            )
        message = str(excinfo.value)
        assert "does not yet emit increment fields" in message
        assert "captured points" in message

    def test_flag_false_still_builds(self) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=_sched(),
            track_increments=False,
        )
        assert b._track_increments is False

    def test_default_still_builds(self) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=_sched(),
        )
        assert b._track_increments is False


class TestAccessorRefusal:
    def test_projection_rollforward_also_refuses(self) -> None:
        from gaspatchio_core import ActuarialFrame

        af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "init": [100.0]}))
        af = af.projection.set(schedule=_sched())
        with pytest.raises(NotImplementedError, match="gh#69"):
            af.projection.rollforward(
                states={"av": pl.col("init")},
                track_increments=True,
            )


class TestIncrementGateTellsTheTruth:
    def test_increment_without_flag_names_the_unimplemented_feature(self) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=_sched(),
        )
        with pytest.raises(ValueError, match="not yet implemented"):
            b.increment("Premium")
