# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``run_to_parquet`` reports the policies the model valued, which is the rows written.

A model that filters to its in-force business values three of these four
policies and writes three rows, whose premiums add to 0.002 x (100,000 +
250,000 + 50,000) = 800. The spill used to report ``n_policies`` 4 -- the rows
it was handed -- beside those three rows, so the aggregate-at-scale tutorial's
check that the rows read back equal ``spill.n_policies`` failed on any model
that chooses its policies. ``run_aggregated`` already counts the rows its folds
saw; the spill now counts the rows it wrote, at every batch size.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.scenarios import run_to_parquet

if TYPE_CHECKING:
    from pathlib import Path

    from gaspatchio import ActuarialFrame

_BOOK = pl.DataFrame(
    {
        "policy_id": ["P1", "P2", "P3", "P4"],
        "status": ["IF", "IF", "IF", "LAPSED"],
        "sum_assured": [100_000.0, 250_000.0, 50_000.0, 80_000.0],
    }
)


def _in_force(af: ActuarialFrame) -> ActuarialFrame:
    af = af.filter(af.status == "IF")
    af.premium = af.sum_assured * 0.002
    return af


def _everything(af: ActuarialFrame) -> ActuarialFrame:
    af.premium = af.sum_assured * 0.002
    return af


@pytest.mark.parametrize("batch_size", ["auto", 1, 2, 3, 10])
def test_the_count_is_the_rows_the_spill_wrote(
    tmp_path: Path, batch_size: int | str
) -> None:
    spill = run_to_parquet(
        _in_force,
        _BOOK,
        tmp_path,
        batch_size=batch_size,  # type: ignore[arg-type]
    )
    written = pl.read_parquet(tmp_path / "*.parquet")
    assert spill.n_policies == 3
    assert written.height == spill.n_policies
    assert sorted(written["policy_id"].to_list()) == ["P1", "P2", "P3"]
    assert written["premium"].sum() == pytest.approx(800.0, rel=1e-15)


def test_a_model_that_selects_nothing_counts_the_book(tmp_path: Path) -> None:
    spill = run_to_parquet(_everything, _BOOK, tmp_path, batch_size=3)
    written = pl.read_parquet(tmp_path / "*.parquet")
    assert spill.n_policies == 4
    assert written.height == 4
    assert written["premium"].sum() == pytest.approx(960.0, rel=1e-15)
