# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period conditional of two dates and times, and this engine's door.

The producer selected two date-and-time runs through a kernel that works in
doubles and answered ``list[f64]`` counts of microseconds, so the record
named a type the per-policy form of the same line never held. It now answers
a date and time and records ``list[datetime]``.

This engine carries no date and time. It refused such a book column by
telling the author to cast it to the type it already was; it now refuses it
by its type, as a limit of the engine, before anything is compiled.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter

# 2025-01-01T00:00:00Z in microseconds.
_US = 1_735_689_600_000_000
_STAMPS = pl.List(pl.Datetime("us"))


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "pid": pl.Series([1, 2], dtype=pl.Int64),
            "m": pl.Series([[0, 1, 2], [0, 1, 2]], dtype=pl.List(pl.Int64)),
            "t": pl.Series([[_US + 1, _US + 2, _US + 3]] * 2).cast(_STAMPS),
            "o": pl.Series([[_US + 9] * 3] * 2).cast(_STAMPS),
        }
    )


def test_a_date_and_time_pair_is_recorded_as_one_and_refused_here_by_its_type() -> None:
    af = ActuarialFrame(_book())
    af.r = when(af.m > 0).then(af.t).otherwise(af.o)
    produced = af.collect()
    document = json.loads(GraphExporter(af).export(profile="executable"))
    recorded = next(n["dtype"] for n in document["nodes"] if n["column"] == "r")

    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(document, _book(), FrameSink())

    report = refused.value.report.render()
    assert produced.schema["r"] == _STAMPS
    assert produced["r"].to_physical().to_list() == [[_US + 9, _US + 2, _US + 3]] * 2
    assert recorded == "list[datetime]"
    assert "this engine carries no date and time" in report
    assert "cast 't'" not in report
