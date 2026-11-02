# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period extreme over a book the model's selection emptied answers nothing.

``PeriodMin`` and ``PeriodMax`` through ``run_aggregated`` on this engine
raised numpy's "zero-size array to reduction operation min which has no
identity" when every policy was filtered out -- a run-off cohort, a closed
block -- where the reference producer, and this engine's own ``PeriodSum``
and ``PeriodMean``, answered ``[]`` (audit D2-F2). 11.1.1 lays zero periods
over zero rows and does not fail; each extremum now starts from its identity.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated
from gaspatchio.scenarios import Max, Min, PeriodMax, PeriodMean, PeriodMin, PeriodSum

_BOOK = pl.DataFrame(
    {
        "pid": [1, 2, 3, 4],
        "inforce": ["N", "N", "Y", "Y"],
        "term_m": [6, 6, 6, 6],
        "sa": [2000.0, 3000.0, 4000.0, 5000.0],
    }
)


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af = af.filter(af.inforce == "Y")
    af = af.projection.set(
        valuation_date=dt.date(2025, 1, 1),
        until="term_months",
        until_value="term_m",
        frequency="monthly",
    )
    af.cf = af.sa * 0.01 + af.month * 0.0
    af.pv = af.cf.list.sum()
    return af


def _both(book: pl.DataFrame, fold: object) -> tuple[object, object]:
    return tuple(
        run_aggregated(_model, book, [fold], batch_size=2, engine=engine).v
        for engine in (None, "jax")
    )


@pytest.mark.parametrize(
    "fold", [PeriodMin, PeriodMax, PeriodSum, PeriodMean], ids=lambda f: f.__name__
)
def test_a_per_period_fold_over_an_emptied_book_is_empty_on_both_engines(
    fold: type,
) -> None:
    emptied = _BOOK.with_columns(pl.lit("N").alias("inforce"))
    producer, engine = _both(emptied, fold("cf").alias("v"))
    assert list(producer) == list(engine) == []


@pytest.mark.parametrize("fold", [Min, Max], ids=lambda f: f.__name__)
def test_an_extreme_per_policy_over_an_emptied_book_is_none_on_both(fold: type) -> None:
    emptied = _BOOK.with_columns(pl.lit("N").alias("inforce"))
    assert _both(emptied, fold("pv").alias("v")) == (None, None)


@pytest.mark.parametrize(
    ("fold", "want"), [(PeriodMin, 40.0), (PeriodMax, 50.0)], ids=["min", "max"]
)
def test_a_batch_emptied_beside_one_that_is_not_changes_nothing(
    fold: type, want: float
) -> None:
    producer, engine = _both(_BOOK, fold("cf").alias("v"))
    assert [float(v) for v in engine] == [float(v) for v in producer] == [want] * 7
