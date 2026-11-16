# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A null-run guard holds a computed run once (11.1.28, GSP-244).

The guard asks whether a run is null and the selection reads the same run, so
a run another calculation produced was written into the plan twice. A chain of
``when`` calls guards the level below it, so its plan doubled with each level.
"""

from __future__ import annotations

import polars as pl

from gaspatchio import ActuarialFrame, when


def _plan_size(depth: int) -> int:
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1], "x": [[1.0, 2.0]], "y": [[3.0, 4.0]]})
    )
    chain = af.x + af.y
    for level in range(depth):
        chain = when(af.x > float(level)).then(af.y + float(level)).otherwise(chain)
    return len(str(af._convert_to_expr(chain)))  # noqa: SLF001 -- the lowered plan


def _book() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "x": [[1.0, 2.0], [5.0, 6.0]],
                "y": [[3.0, 4.0], None],
            },
            schema={
                "policy_id": pl.Int64,
                "x": pl.List(pl.Float64),
                "y": pl.List(pl.Float64),
            },
        )
    )


def test_a_when_chain_s_plan_grows_with_its_levels_not_by_doubling() -> None:
    assert _plan_size(8) < 3 * _plan_size(4)


def test_a_computed_branch_holding_no_run_still_answers_null() -> None:
    af = _book()
    af.answer = when(af.x > 1.5).then(af.y * 2.0).otherwise(af.x + 1.0)

    assert af.collect()["answer"].to_list() == [[2.0, 8.0], None]


def test_a_computed_right_hand_run_holding_nothing_still_answers_null() -> None:
    af = _book()
    af.answer = when(af.x > af.y * 2.0).then(1.0).otherwise(0.0)

    assert af.collect()["answer"].to_list() == [[0.0, 0.0], None]
