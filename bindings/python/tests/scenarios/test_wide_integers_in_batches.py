# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A batched run reads a wide integer column in one width, judged over the book.

A ``UInt64``, ``Int128`` or ``UInt128`` column is read as ``Int64`` where every
value fits and keeps its width where one does not (section 10). A batch runner
that let the frame judge each batch alone would read the same column as
``Int64`` in a batch whose values happen to fit and as ``UInt64`` in the next,
so ``run_to_parquet`` wrote files of two schemas that no reader could take
together. The runners judge the column over the whole book, and every batch
reads it in that one width. Arithmetic on it answers the ``i64`` sum, or is
refused, at every batch size: ``run_aggregated`` summed the wrapped values to
36,893,488,147,419,103,000 at ``batch_size=1`` and half that at 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.scenarios import Sum, run_aggregated, run_to_parquet

if TYPE_CHECKING:
    from pathlib import Path

    from gaspatchio import ActuarialFrame

FITS = pl.DataFrame({"pid": pl.Series([7, 8], dtype=pl.UInt64), "amt": [2.0, 3.0]})
PAST = pl.DataFrame(
    {"pid": pl.Series([7, 2**64 - 1], dtype=pl.UInt64), "amt": [2.0, 3.0]}
)


def _text(af: ActuarialFrame) -> ActuarialFrame:
    af.pid_text = af.pid.to_text()
    return af


def _less_ten(af: ActuarialFrame) -> ActuarialFrame:
    af.d = af.pid - 10
    return af


@pytest.mark.parametrize("size", [1, 2])
@pytest.mark.parametrize(("book", "width"), [(FITS, pl.Int64), (PAST, pl.UInt64)])
def test_every_file_a_batched_run_writes_carries_one_width(
    tmp_path: Path, book: pl.DataFrame, width: type[pl.DataType], size: int
) -> None:
    out = tmp_path / "out"
    run_to_parquet(_text, book, out, batch_size=size)
    files = sorted(out.rglob("*.parquet"))

    assert files
    assert {pl.read_parquet_schema(one)["pid"] for one in files} == {width}
    written = pl.read_parquet(files).sort("amt")
    assert written["pid_text"].to_list() == [str(v) for v in book["pid"]]


@pytest.mark.parametrize("size", [1, 2])
def test_arithmetic_in_a_batched_run_answers_the_i64_sum_or_refuses(
    size: int,
) -> None:
    total = run_aggregated(_less_ten, FITS, [Sum("d").alias("d")], batch_size=size)
    # Hand value: (7 - 10) + (8 - 10).
    assert total.d == -5

    with pytest.raises(
        pl.exceptions.InvalidOperationError,
        match="Column 'pid' holds a whole number outside the signed 64-bit range",
    ):
        run_aggregated(_less_ten, PAST, [Sum("d").alias("d")], batch_size=size)
