# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Benchmark: a per-period Categorical condition costs what a numeric one does.

``af.plan == "A"`` over a per-period Categorical column handed the
conditional kernel the labels, and Polars re-entered every label into the
category map for each block of rows it passed across the plugin boundary.
Streaming, which is what ``ActuarialFrame.collect()`` runs, that took about
5 s over 100,000 policies x 360 months against 0.13 s for the same
comparison over numbers. Equality is now handed over as codes, and the gate
below holds a Categorical and an Enum condition to a small multiple of the
numeric one on the same frame. On the label path the ratio was about 40.
"""

from __future__ import annotations

import statistics
import time

import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame

pytestmark = pytest.mark.benchmark

POLICIES = 50_000
PERIODS = 360
REPEATS = 5
# The codes path measured about 1x the numeric condition streaming; the
# label path about 40x. Three leaves room for a loaded machine.
RATIO_GATE = 3.0


def _book() -> pl.DataFrame:
    rng = np.random.default_rng(0)
    labels = np.array(["A", "B", "C", "D"])[rng.integers(0, 4, POLICIES * PERIODS)]
    plan = (
        pl.Series("plan", labels).reshape((POLICIES, PERIODS)).cast(pl.List(pl.String))
    )
    rate = (
        pl.Series("rate", rng.uniform(0.0, 1.0, POLICIES * PERIODS))
        .reshape((POLICIES, PERIODS))
        .cast(pl.List(pl.Float64))
    )
    return pl.DataFrame(
        {
            "plan_cat": plan.cast(pl.List(pl.Categorical)),
            "plan_enum": plan.cast(pl.List(pl.Enum(["A", "B", "C", "D"]))),
            "rate": rate,
        }
    )


def _streaming_median(book: pl.DataFrame, column: str, value: object) -> float:
    af = ActuarialFrame(book.select(column))
    af.out = af[column] == value
    plan = af._df.select("out")  # noqa: SLF001 - the condition alone, as the engine runs it
    times = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        plan.collect(engine="streaming")
        times.append(time.perf_counter() - start)
    return statistics.median(times)


@pytest.fixture(scope="module")
def book() -> pl.DataFrame:
    """Build the frame once for the module."""
    return _book()


@pytest.mark.parametrize("column", ["plan_cat", "plan_enum"])
def test_a_categorical_condition_streams_at_the_numeric_rate(
    book: pl.DataFrame, column: str
) -> None:
    """``plan == "A"`` streams within a small multiple of ``rate == 0.5``."""
    numeric = _streaming_median(book, "rate", 0.5)
    categorical = _streaming_median(book, column, "A")

    assert categorical <= RATIO_GATE * numeric, (
        f"{column} == 'A' streamed in {categorical:.3f}s against "
        f"{numeric:.3f}s for the numeric condition"
    )
