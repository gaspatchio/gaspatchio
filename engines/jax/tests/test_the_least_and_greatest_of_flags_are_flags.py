# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The least and the greatest of a run of flags are flags, as the producer answers.

``min`` and ``max`` choose one of the run's own values (11.1.16, 11.1.17), so
over a run of flags -- an in-force flag a period, a claim indicator -- the
least is whether every period was set and the greatest whether any was. The
producer and the reference reader answer ``bool``; this engine refused the
run's carrier by name before it read a book. It now folds the flags as the 0
and 1 they indicate, as the totals do, and answers the flag the fold chose,
per policy over that policy's own periods.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

# The fourth policy's timeline is half the others', so the fold reads its own
# two periods and never the padding beside them.
_FLAGS = pl.DataFrame(
    {
        "policy_id": [1, 2, 3, 4],
        "f": [
            [True, False, True, True],
            [False, False, False, False],
            [True, True, True, True],
            [False, True],
        ],
    },
    schema={"policy_id": pl.Int64, "f": pl.List(pl.Boolean)},
)

# By hand: the least is True only where every period is set, the greatest
# True where any is.
_FOLDS: list[tuple[str, Callable[[Any], Any], str, list[object]]] = [
    ("min", lambda af: af.f.list.min(), "bool", [False, False, True, False]),
    ("max", lambda af: af.f.list.max(), "bool", [True, False, True, True]),
    (
        "min read as a number",
        lambda af: af.f.list.min() * 1,
        "f64",
        [0.0, 0.0, 1.0, 0.0],
    ),
]


def _document(line: Callable[[Any], Any]) -> tuple[pl.DataFrame, dict[str, Any]]:
    af = ActuarialFrame(_FLAGS)
    af.r = line(af)
    out = af.collect()
    doc = json.loads(
        GraphExporter(af).export(out, profile="executable", include_source=False)
    )
    return out, doc


@pytest.mark.parametrize(
    ("name", "line", "dtype", "hand"), _FOLDS, ids=[x[0] for x in _FOLDS]
)
def test_the_fold_answers_the_flag_the_producer_answers(
    name: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    dtype: str,
    hand: list[object],
) -> None:
    out, doc = _document(line)
    node = next(n for n in doc["nodes"] if n.get("column") == "r")

    columns = engine_named("jax").run(doc, _FLAGS, FrameSink(), every_node=True)
    answered = columns.columns[node["id"]]  # refused by name on the base

    assert node["dtype"] == dtype
    assert out["r"].to_list() == hand
    assert answered.to_list() == hand
    assert answered.dtype == out["r"].dtype
