# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An injected column is paired with the rows it was written for, or refused.

A column of values handed over wholesale -- a ``pl.Series``, a NumPy array,
``pl.lit(Series)``, a fixed ``pl.int_range`` -- lands on the rows by
position (spec 12.3): the second value belongs to the second policy. Where
the frame is one batch of a book cut into several, its rows are not the
book's, and Polars' streaming engine repeats a one-row frame to the
injection's length: one policy became four, and ``run_aggregated`` answered
10000 over 16 "policies" at ``batch_size=1`` where the book's answer is 3000
(audit C3a-F3). A one-row book through ``collect()`` became three rows. Now
an injection is refused where the runner cut the book, naming the routes,
and refused anywhere its length is not the frame's row count.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated, run_to_parquet
from gaspatchio.scenarios import Sum

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3, 4],
        "sa": [1000.0, 2000.0, 3000.0, 4000.0],
        "term": [3, 3, 3, 3],
    }
)
LOADS = [0.1, 0.2, 0.3, 0.4]
# Sum of sa * load over the book, by hand.
HAND = 3000.0

FORMS: dict[str, Callable[[ActuarialFrame], object]] = {
    "series": lambda _af: pl.Series("load", LOADS),
    "numpy": lambda _af: np.array(LOADS),
    "lit_series": lambda _af: pl.lit(pl.Series(LOADS)),
    "int_range": lambda _af: pl.int_range(1, 5) * 0.1,
    "operand_series": lambda af: af.sa * pl.Series(LOADS) / af.sa,
    "raw_operand_series": lambda _af: pl.col("sa") * pl.Series(LOADS) / pl.col("sa"),
}


def _model(form: str) -> Callable[[ActuarialFrame], ActuarialFrame]:
    def model(af: ActuarialFrame) -> ActuarialFrame:
        af = af.projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="term_years",
            until_value="term",
            frequency="annual",
        )
        af.load = FORMS[form](af)
        af.charge = af.sa * af.load
        return af

    return model


@pytest.mark.parametrize("form", list(FORMS))
def test_the_whole_book_takes_the_injection(form: str) -> None:
    model = _model(form)
    charge = model(ActuarialFrame(BOOK)).collect()["charge"]
    assert charge.sum() == pytest.approx(HAND)
    result = run_aggregated(model, BOOK, [Sum("charge").alias("c")], batch_size=4)
    assert result.c == pytest.approx(HAND)
    assert result.n_policies == len(BOOK)


@pytest.mark.parametrize("form", list(FORMS))
@pytest.mark.parametrize("size", [1, 2, 3])
def test_a_batch_runner_cutting_the_book_refuses_the_injection(
    form: str, size: int
) -> None:
    with pytest.raises(ValueError, match="lands on the rows by position") as refused:
        run_aggregated(_model(form), BOOK, [Sum("charge").alias("c")], batch_size=size)
    message = str(refused.value)
    assert "run_aggregated cuts the 4 policies into batches" in message, message
    assert "4 values" in message, message
    assert "model-point column" in message, message
    assert "one batch" in message, message


def test_run_to_parquet_refuses_the_injection_when_it_cuts_the_book(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="run_to_parquet cuts the 4 policies"):
        run_to_parquet(_model("series"), BOOK, output_dir=tmp_path / "c", batch_size=1)
    run_to_parquet(_model("series"), BOOK, output_dir=tmp_path / "w", batch_size=4)
    assert pl.read_parquet(tmp_path / "w" / "*.parquet").height == len(BOOK)


@pytest.mark.parametrize("form", list(FORMS))
def test_a_one_row_book_refuses_an_injection_of_another_length(form: str) -> None:
    # Refused at the line, before any engine is chosen: the streaming engine
    # copied the one row once for each value, and the in-memory engine
    # refused in Polars' words.
    with pytest.raises(ValueError, match="this frame holds 1 row") as refused:
        _model(form)(ActuarialFrame(BOOK.head(1)))
    assert "4 values" in str(refused.value)


def test_an_injection_of_one_value_stands_on_any_frame() -> None:
    def model(af: ActuarialFrame) -> ActuarialFrame:
        af.load = pl.Series("load", [0.5])
        af.charge = af.sa * af.load
        return af

    assert model(ActuarialFrame(BOOK)).collect()["charge"].to_list() == [
        500.0,
        1000.0,
        1500.0,
        2000.0,
    ]
    result = run_aggregated(model, BOOK, [Sum("charge").alias("c")], batch_size=1)
    assert result.c == pytest.approx(5000.0)
