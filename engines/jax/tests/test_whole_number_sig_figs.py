# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A whole number kept to its significant figures is the producer's exact answer.

This engine rounded significant figures through a double, as the producer
did: 781,098 to one figure was 799,999 on both, and a whole number past
2**53 was refused here as a double that would lose it. Both now keep the
figures in whole-number arithmetic, a tie away from zero (section 11.1.12),
and flag an answer that rounds up past i64.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter

_I64_MAX = 2**63 - 1


@pytest.mark.parametrize(
    ("values", "figures", "expected"),
    [
        ([781098, 427160, -125000], 1, [800000, 400000, -100000]),
        ([125000, -125000, 124999], 2, [130000, -130000, 120000]),
        ([2**53 + 1, _I64_MAX, -(2**63)], 2, [9 * 10**15, 92 * 10**17, -92 * 10**17]),
    ],
    ids=["one figure", "ties", "past 2**53"],
)
def test_whole_number_figures_agree_with_the_producer(
    values: list[int], figures: int, expected: list[int]
) -> None:
    book = pl.DataFrame({"n": values})
    af = ActuarialFrame(book)
    af.r = af.n.round_sig_figs(figures)
    produced = af.collect()

    document = json.loads(GraphExporter(af).export(profile="executable"))
    result = engine_named("jax").run(document, book, FrameSink())

    assert produced["r"].to_list() == expected
    assert result.columns["r"].to_list() == expected
    assert result.columns["r"].dtype == pl.Int64


def test_a_whole_number_that_rounds_past_i64_is_refused() -> None:
    """2**63 - 1 to ten figures is 9,223,372,037 x 10**9."""
    book = pl.DataFrame({"n": [_I64_MAX]})
    af = ActuarialFrame(book)
    af.r = af.n.round_sig_figs(10)
    document = json.loads(GraphExporter(af).export(profile="executable"))

    with pytest.raises(EngineRefusal) as caught:
        engine_named("jax").run(document, book, FrameSink())

    assert "i64.range" in caught.value.report.render()
