# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A book's narrow floats are read as f64 at this door, as the producer reads them.

The reference producer reads a ``Float32`` or ``Float16`` book column -- and a
list of one -- as ``Float64`` where it enters the frame, so the run computes
in the double its record names. This door refused that same book file --
"the artifact reads 'qx' as list[f64] ... this book carries it as
list[Float32]" -- so the two engines did not take one book. It now reads the
book as the producer does, and the result is the producer's double.
"""

from __future__ import annotations

import json

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.frame.graph import GraphExporter

# The stored single-precision rates, read exactly as doubles, summed in a
# double by hand: 0.0010000000474974513 + 0.001500000013038516 +
# 0.0020000000949949026 = 0.00450000015553087.
_BOOK = pl.DataFrame(
    [
        pl.Series("qx", [[0.001, 0.0015, 0.002]], dtype=pl.List(pl.Float32)),
        pl.Series("sa", [123456.789], dtype=pl.Float32),
    ]
)


def test_a_float32_book_runs_and_answers_the_producer_s_doubles() -> None:
    af = ActuarialFrame(_BOOK)
    af.total = af.qx.list.sum()
    af.third = af.sa / 3.0
    document = json.loads(GraphExporter(af).export(profile="executable"))

    result = engine_named("jax").run(document, _BOOK, FrameSink())

    assert result.columns["total"].to_list() == [0.00450000015553087]
    # 123456.789f is 123456.7890625; a third of it in a double.
    assert result.columns["third"].to_list() == [41152.263020833336]
    assert result.columns["third"].dtype == pl.Float64
    frame = af.collect()
    assert result.columns["total"].to_list() == frame["total"].to_list()
    assert result.manifest.inputs_digest == document["book"]["digest"]
