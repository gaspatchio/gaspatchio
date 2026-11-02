# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The rollforward kernel answers for the rows it is handed.

``DataFrame.head`` and ``DataFrame.slice`` are zero-copy: a sliced list column
keeps the whole column's inner values and moves only its offsets, and the
streaming engine hands every plugin its morsel the same way. A kernel that
read the flat values as they stand paid for the whole portfolio once per
morsel, and the rollforward refused a slice for a missing premium in a policy
the slice did not contain.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.rollforward._compile import compile_rollforward
from gaspatchio.schedule import Schedule
from tests.rollforward.conftest import _standalone_state_expr


def _av_expr() -> pl.Expr:
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=3,
        frequency="1M",
    )
    b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
    b["av"].add(pl.col("premium"), label="P").grow(pl.col("rate"), label="G")
    return _standalone_state_expr(compile_rollforward(b), "av")


def _four_policies(*, hole: bool) -> pl.DataFrame:
    """Four three-period policies; the last lacks its second premium if ``hole``."""
    return pl.DataFrame(
        {
            "init": [100.0, 200.0, 300.0, 400.0],
            "premium": [
                [10.0, 11.0, 12.0],
                [20.0, 21.0, 22.0],
                [30.0, 31.0, 32.0],
                [40.0, None, 42.0] if hole else [40.0, 41.0, 42.0],
            ],
            "rate": [[0.01, 0.01, 0.01]] * 4,
        },
    )


def test_a_slice_with_offsets_past_zero_answers_as_the_whole_frame_does() -> None:
    frame = _four_policies(hole=False)
    whole = frame.with_columns(av=_av_expr()).get_column("av").to_list()
    part = frame.slice(1, 2).with_columns(av=_av_expr()).get_column("av").to_list()
    assert part == whole[1:3]


def test_a_slice_is_not_refused_for_a_hole_in_a_policy_it_left_out() -> None:
    clean = _four_policies(hole=False).head(2).with_columns(av=_av_expr())
    holed = _four_policies(hole=True).head(2).with_columns(av=_av_expr())
    assert holed.get_column("av").to_list() == clean.get_column("av").to_list()
    assert holed.get_column("av").to_list()[0] == pytest.approx(
        [111.1, 123.321, 136.67421],
    )


def test_the_hole_is_still_refused_when_its_policy_is_in_the_slice() -> None:
    holed = _four_policies(hole=True).slice(2, 2)
    with pytest.raises(pl.exceptions.ComputeError, match="null inner values"):
        holed.with_columns(av=_av_expr())
