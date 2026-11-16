# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``to_integer`` over a run answers exactly, and refuses what it always refused.

The cast is not guarded element by element, because the validity check beside
it refuses every row an unguarded cast could get wrong.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

_RUN = pl.List(pl.Float64)


def _converted(run: list[float | None] | None) -> list[object]:
    frame = pl.DataFrame(
        {"policy_id": [1], "x": [run]}, schema={"policy_id": pl.Int64, "x": _RUN}
    )
    af = ActuarialFrame(frame)
    af.y = af.x.to_integer()
    return af.collect()["y"].to_list()


@pytest.mark.parametrize(
    ("run", "want"),
    [
        ([1.0, -2.0, -0.0], [1, -2, 0]),
        ([2.0**53, -(2.0**62)], [2**53, -(2**62)]),
        ([], []),
    ],
    ids=["whole numbers", "large whole numbers", "no periods"],
)
def test_whole_numbers_convert_exactly(run: list[float], want: list[int]) -> None:
    assert _converted(run) == [want]


@pytest.mark.parametrize(
    "run",
    [
        [1.5],
        [1.0, None],
        [float("nan")],
        [float("inf")],
        [2.0**63],
        None,
    ],
    ids=["a fraction", "a null", "a NaN", "an infinity", "past i64", "no run"],
)
def test_a_run_holding_anything_else_is_refused(run: list[float | None] | None) -> None:
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _converted(run)
