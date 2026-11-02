# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period conditional of whole numbers answers one set of values on both engines.

The record types ``when(af.month > 0).then(0).otherwise(af.k)`` over a
``list[i64]`` run as ``list[i64]``, and this engine selects in it. The
producer selected through a kernel that works in doubles and typed the
answer back, so a run holding 2**53 + 1 came back as 2**53 there and as
2**53 + 1 here, from one document, and 2**63 - 1 failed to come back at
all. These pin that the two engines now agree, at the hand values, on each
route the producer takes: a comparison, a per-period flag, and one flag per
policy.

A ``None`` branch reaches the record as an engine-native fragment, which
this engine refuses by name before it reads the book; the last case pins
that the refusal is loud rather than a guess at the null's type.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_BIG = 2**53 + 1
_TOP = 2**63 - 1


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "pid": pl.Series([1, 2], dtype=pl.Int64),
            "n": pl.Series([3, _BIG], dtype=pl.Int64),
            "x": [1.5, 3.5],
        }
    )


def _projected() -> Any:  # noqa: ANN401 -- a frame being written
    af = ActuarialFrame(_book()).projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.k = af.n + af.month
    return af


_FORMS: list[tuple[str, Callable[[Any], Any], list[list[int]]]] = [
    (
        "a comparison: then(0).otherwise(k)",
        lambda af: when(af.month > 0).then(0).otherwise(af.k),
        [[3, 0, 0], [_BIG, 0, 0]],
    ),
    (
        "a comparison: then(k).otherwise(n)",
        lambda af: when(af.month > 1).then(af.k).otherwise(af.n),
        [[3, 3, 5], [_BIG, _BIG, _BIG + 2]],
    ),
    (
        "one flag per policy: then(0).otherwise(k)",
        lambda af: when(af.x < 2).then(0).otherwise(af.k),
        [[0, 0, 0], [_BIG, _BIG + 1, _BIG + 2]],
    ),
    (
        "a comparison: then(the greatest i64).otherwise(k)",
        lambda af: when(af.month > 1).then(_TOP).otherwise(af.k),
        [[3, 4, _TOP], [_BIG, _BIG + 1, _TOP]],
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "expected"), _FORMS, ids=[form[0] for form in _FORMS]
)
def test_a_per_period_conditional_of_whole_numbers_agrees_on_both_engines(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    expected: list[list[int]],
) -> None:
    af = _projected()
    af.r = line(af)
    produced = af.collect()

    document = json.loads(GraphExporter(af).export(profile="executable"))
    result = engine_named("jax").run(document, _book(), FrameSink())

    assert produced["r"].to_list() == expected
    assert result.columns["r"].to_list() == expected
    assert produced.schema["r"] == result.columns["r"].dtype == pl.List(pl.Int64)


def test_a_null_branch_is_refused_by_name_on_this_engine() -> None:
    """The producer answers list[i64]; this engine names the fragment it cannot run."""
    af = _projected()
    af.r = when(af.month > 0).then(None).otherwise(af.k)
    produced = af.collect()
    document = json.loads(GraphExporter(af).export(profile="executable"))

    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(document, _book(), FrameSink())

    assert produced.schema["r"] == pl.List(pl.Int64)
    assert "engine_native" in refused.value.report.render()
