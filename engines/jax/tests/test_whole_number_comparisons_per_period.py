# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period comparison of whole numbers answers exactly on both engines.

Section 11.1.26 stated a per-period comparison only inside ``[-2**53, 2**53]``,
because the producer's kernel compared in doubles and equated ``2**53 + 1``
with ``2**53``. This engine therefore refused such a run by name. The producer
now compares a whole number by its exact value per period as per policy, and
the clause's exclusion is withdrawn, so this engine compares in ``int64`` as
it always could, and the two answer one set of hand values from one document.
A whole number met by a decimal stays bounded, and still refuses.
"""

from __future__ import annotations

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

_BIG = 2**53
_TOP = 2**63 - 1


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "pid": pl.Series([1, 2], dtype=pl.Int64),
            "k": pl.Series(
                [[_BIG + 1, _TOP, -(2**63) + 1], [_BIG, _TOP - 1, -(2**63)]],
                dtype=pl.List(pl.Int64),
            ),
            "m": pl.Series([_BIG, _TOP - 1], dtype=pl.Int64),
        }
    )


_LINES: list[tuple[str, Callable[[Any], Any], list[list[Any]]]] = [
    (
        "a run against a literal",
        lambda af: af.k > _BIG,
        [[1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
    ),
    (
        "a run against a per-policy column",
        lambda af: af.k >= af.m,
        [[1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
    ),
    (
        "a literal on the left",
        lambda af: (_TOP - 1) == af.k,  # noqa: SIM300 -- the literal is written on the left
        [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    ),
    (
        "a conditional over the comparison",
        lambda af: when(af.k != _BIG).then(1).otherwise(0),
        [[1, 1, 1], [0, 1, 1]],
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "expected"), _LINES, ids=[line[0] for line in _LINES]
)
def test_a_per_period_comparison_of_whole_numbers_agrees_on_both_engines(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    expected: list[list[Any]],
) -> None:
    af = ActuarialFrame(_book())
    af.r = line(af)
    produced = af.collect()
    document = json.loads(GraphExporter(af).export(profile="executable"))

    result = engine_named("jax").run(document, _book(), FrameSink())

    assert produced["r"].to_list() == expected
    assert result.columns["r"].to_list() == expected


def test_a_whole_number_met_by_a_decimal_stays_bounded() -> None:
    af = ActuarialFrame(_book())
    af.r = af.k > 0.5
    document = json.loads(GraphExporter(af).export(profile="executable"))

    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(document, _book(), FrameSink())

    assert "mixed.2p53" in refused.value.report.render()
