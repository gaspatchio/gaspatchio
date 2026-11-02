# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The error block's ``Graph:`` line names the failure's own column, or nothing.

The graph folds the whole frame, so a type it cannot name anywhere on it -- a
``UInt64`` holding a value past ``i64``, a fixed-width ``Array`` -- silences
its ``Blocks:`` and ``Reading:`` answers, and the block printed that refusal
in their place. Where the refused column was one the failing line never read,
a list read that failed for its own reason went out under ``Graph: Column
'big' holds 18446744073709551615 ...``, sending the reader to fix a column
the failure never touched. The line is printed only where the refused column
is the failing one or one its formula reads.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

_UNRELATED = {
    "u64": pl.Series([1, 2**64 - 1], dtype=pl.UInt64),
    "array": pl.Series([[1.0, 2.0]] * 2, dtype=pl.Array(pl.Float64, 2)),
}


@pytest.mark.parametrize("traced", [False, True], ids=["block", "panel"])
@pytest.mark.parametrize("kind", sorted(_UNRELATED))
def test_an_unrelated_unnamed_column_is_not_the_failure_s_graph_line(
    kind: str, *, traced: bool
) -> None:
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "other": _UNRELATED[kind]}).with_columns(
            av=pl.Series([[1.0] * 40, [2.0] * 24])
        )
    )
    af._traced_run = traced  # noqa: SLF001 -- standing in for the trace decorator
    af.last_av = af.av.list.get(36)

    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af.collect()

    message = str(refused.value)
    assert "last_av" in message
    assert "Graph:" not in message
    assert "'other'" not in message


def test_the_failure_s_own_unnamed_column_keeps_its_graph_line() -> None:
    af = ActuarialFrame(
        pl.DataFrame(
            {"policy_id": [1, 2], "term": [1, 7]},
        ).with_columns(
            cashflow=pl.Series([[10.0, 11.0, 12.0]] * 2).cast(pl.Array(pl.Float64, 3))
        )
    )
    af.final_cf = af.cashflow.polars_native().arr.get(af.term)

    with pytest.raises(Exception) as refused:  # noqa: PT011 -- the class is Polars'
        af.collect()

    message = str(refused.value)
    assert "Graph:" in message
    assert "Column 'cashflow' has type Array" in message
