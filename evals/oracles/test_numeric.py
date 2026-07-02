# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101
"""Tests for the numeric oracle (reconcile output to a reference)."""

import shutil
from pathlib import Path

import polars as pl
import pytest

from evals.oracles.numeric import grade_numeric

FIXTURE = Path(__file__).resolve().parent / "_fixtures" / "min_points.parquet"

MATCHES = """```python
from gaspatchio_core import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.expected_claims = af.sum_assured * af.mortality_rate
    return af
```
"""

WRONG = """```python
from gaspatchio_core import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.expected_claims = af.sum_assured * af.mortality_rate * 2.0
    return af
```
"""


@pytest.fixture
def case(tmp_path: Path) -> dict:
    """Set up a case dict with fixture data and a matching reference parquet."""
    shutil.copy(FIXTURE, tmp_path / "data.parquet")
    pts = pl.read_parquet(FIXTURE)
    ref = pts.select(
        (pl.col("sum_assured") * pl.col("mortality_rate")).alias("expected_claims")
    )
    ref.write_parquet(tmp_path / "reference.parquet")
    return {
        "fixture_data": "data.parquet",
        "reference": "reference.parquet",
        "reconcile_columns": ["expected_claims"],
        "tolerance": 1e-6,
        "_workdir": tmp_path,
    }


def test_matching_model_scores_one(case: dict) -> None:
    """A model whose numbers match the reference within tolerance scores 1.0."""
    r = grade_numeric(MATCHES, case, case["_workdir"])
    assert r.score == 1.0, r.detail


def test_wrong_model_scores_below_one(case: dict) -> None:
    """A model off by 2x scores below 1.0."""
    r = grade_numeric(WRONG, case, case["_workdir"])
    assert r.score < 1.0, r.detail
