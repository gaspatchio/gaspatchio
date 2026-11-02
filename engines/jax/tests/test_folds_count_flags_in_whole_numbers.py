# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A run of flags folds as the whole numbers it counts; a whole suffix sum stays whole.

Two folds the producer and the reference reader answer were refused here by
name. A total, an average, the two running folds and a suffix sum over a run
of flags -- an in-force flag a period, a claim indicator -- count in whole
numbers (11.1.9, 11.1.14, 11.1.20): ``sum`` is how many periods were set, as
an ``i64``, ``cum_sum`` and ``remaining_sum`` how many have been and are
still to come, ``cum_prod`` whether every one so far has been, and ``mean``
the share, as an ``f64``. This engine refused the run's carrier before it
read a book. And ``remaining_sum`` over a run of whole numbers, which 11.1.20
answers as ``list[i64]`` exact in every period, was computed here in doubles
and refused as a type this engine had widened; it now takes the checked
whole-number running total ``cum_sum(reverse=True)`` takes, and refuses a
period past ``i64`` by name, as the producer does.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_FLAGS = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "f": [
            [True, False, True, True],
            [False, False, True, False],
            [True, True, True, True],
        ],
    },
    schema={"policy_id": pl.Int64, "f": pl.List(pl.Boolean)},
)

# Each fold of the flags above, by hand: True counts 1 and False 0.
_FOLDS: list[tuple[str, Callable[[Any], Any], str, list[object]]] = [
    ("sum", lambda af: af.f.list.sum(), "i64", [3, 1, 4]),
    ("mean", lambda af: af.f.list.mean(), "f64", [0.75, 0.25, 1.0]),
    (
        "cum_sum",
        lambda af: af.f.cum_sum(),
        "list[i64]",
        [[1, 1, 2, 3], [0, 0, 1, 1], [1, 2, 3, 4]],
    ),
    (
        "cum_sum reversed",
        lambda af: af.f.cum_sum(reverse=True),
        "list[i64]",
        [[3, 2, 2, 1], [1, 1, 1, 0], [4, 3, 2, 1]],
    ),
    (
        "cum_prod",
        lambda af: af.f.cum_prod(),
        "list[i64]",
        [[1, 0, 0, 0], [0, 0, 0, 0], [1, 1, 1, 1]],
    ),
    (
        "remaining_sum",
        lambda af: af.f.projection.remaining_sum(),
        "list[i64]",
        [[3, 2, 2, 1], [1, 1, 1, 0], [4, 3, 2, 1]],
    ),
]


def _document(book: pl.DataFrame, line: Callable[[Any], Any]) -> tuple[Any, dict]:
    af = ActuarialFrame(book)
    af.r = line(af)
    out = af.collect()
    doc = json.loads(
        GraphExporter(af).export(out, profile="executable", include_source=False)
    )
    return out, doc


def _on_jax(doc: dict, book: pl.DataFrame) -> pl.Series:
    columns = engine_named("jax").run(doc, book, FrameSink(), every_node=True).columns
    node = next(n for n in doc["nodes"] if n.get("column") == "r")
    return columns[node["id"]]


@pytest.mark.parametrize(
    ("name", "line", "dtype", "hand"), _FOLDS, ids=[x[0] for x in _FOLDS]
)
def test_a_fold_over_a_run_of_flags_answers_the_producer_s_count(
    name: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    dtype: str,
    hand: list[object],
) -> None:
    out, doc = _document(_FLAGS, line)
    node = next(n for n in doc["nodes"] if n.get("column") == "r")

    answered = _on_jax(doc, _FLAGS)  # refused by name on the base

    assert node["dtype"] == dtype
    assert out["r"].to_list() == hand
    assert answered.to_list() == hand
    assert answered.dtype == out["r"].dtype


_P53 = 2**53

# remaining_sum over whole numbers, by hand: each period is the sum of it and
# every later one, exact past 2**53 and at the edge of i64.
_WHOLE: list[tuple[str, list[list[int]], list[list[int]]]] = [
    (
        "past 2**53",
        [[_P53 + 1, 2], [_P53, 1, 1], [1, 2, 3]],
        [[_P53 + 3, 2], [_P53 + 2, 2, 1], [6, 5, 3]],
    ),
    (
        "at the edge of i64",
        [[2**63 - 2, 1], [-(2**63) + 1, -1], [5, -5]],
        [[2**63 - 1, 1], [-(2**63), -1], [0, -5]],
    ),
]


def _whole(runs: list[list[int]]) -> pl.DataFrame:
    return pl.DataFrame(
        {"policy_id": list(range(1, len(runs) + 1)), "v": runs},
        schema={"policy_id": pl.Int64, "v": pl.List(pl.Int64)},
    )


@pytest.mark.parametrize(("case", "runs", "hand"), _WHOLE, ids=[x[0] for x in _WHOLE])
def test_remaining_sum_over_whole_numbers_is_exact_in_every_period(
    case: str,  # noqa: ARG001 -- the id
    runs: list[list[int]],
    hand: list[list[int]],
) -> None:
    book = _whole(runs)
    out, doc = _document(book, lambda af: af.v.projection.remaining_sum())

    answered = _on_jax(doc, book)  # refused as a widened type on the base

    assert out["r"].to_list() == hand
    assert answered.dtype == pl.List(pl.Int64)
    assert answered.to_list() == hand


def test_remaining_sum_past_i64_is_refused_by_name_as_the_producer_refuses_it() -> None:
    _, doc = _document(_whole([[1, 2]]), lambda af: af.v.projection.remaining_sum())
    past = _whole([[1, 2**63 - 1]])

    frame = ActuarialFrame(past)
    frame.r = frame.v.projection.remaining_sum()

    with pytest.raises(pl.exceptions.InvalidOperationError, match="remaining sum"):
        frame.collect()
    with pytest.raises(EngineRefusal, match=r"i64\.range"):
        _on_jax(doc, past)
