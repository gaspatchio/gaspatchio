# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``run_aggregated`` reports the policies the model valued, not the book's rows.

A model that filters to its in-force business values three of these four
policies, and its total is a total over those three: 0.002 x (100,000 +
250,000 + 50,000) = 800. Polars used to report ``n_policies`` 4 -- the rows it
was handed -- beside that total, while the JAX engine reported 3, so one fold
said two different things about how many policies it had added up. The count
is now the rows the folds saw, at every batch size and in the audit record.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.scenarios import Sum, run_aggregated

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


@pytest.mark.parametrize("batch_size", ["auto", 1, 3, 10])
def test_the_count_is_the_policies_the_model_valued(batch_size: int | str) -> None:
    result = run_aggregated(
        _in_force,
        _BOOK,
        [Sum("premium").alias("premium")],
        batch_size=batch_size,  # type: ignore[arg-type]
    )
    assert result.n_policies == 3
    assert result.premium == pytest.approx(800.0, rel=1e-15)


def test_a_model_that_selects_nothing_counts_the_book() -> None:
    result = run_aggregated(_everything, _BOOK, [Sum("premium").alias("premium")])
    assert result.n_policies == 4
    assert result.premium == pytest.approx(960.0, rel=1e-15)


def test_the_audit_record_states_the_count_the_result_does(tmp_path: Path) -> None:
    path = tmp_path / "run.audit.json"
    result = run_aggregated(
        _in_force, _BOOK, [Sum("premium").alias("premium")], audit=path
    )
    record = json.loads(path.read_text())
    assert result.n_policies == 3
    assert record["run_metadata"]["n_policies"] == 3
