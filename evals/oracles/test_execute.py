# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101
"""Tests for the execute oracle (runs emitted model code via gspio)."""

import shutil
from pathlib import Path

import pytest

from evals.oracles.execute import grade_execution

FIXTURE = Path(__file__).resolve().parent / "_fixtures" / "min_points.parquet"

GOOD = """Here is the model:

```python
from gaspatchio_core import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.expected_claims = af.sum_assured * af.mortality_rate
    return af
```
"""

BROKEN = """```python
from gaspatchio_core import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.x = af.nonexistent_column * 2
    return af
```
"""

NO_CODE = "I would compute expected claims as sum_assured times mortality_rate."


@pytest.fixture
def case(tmp_path: Path) -> dict:
    """Set up a minimal case dict with fixture data copied into a temp workdir."""
    shutil.copy(FIXTURE, tmp_path / "data.parquet")
    return {
        "fixture_data": "data.parquet",
        "expected_columns": ["expected_claims"],
        "_workdir": tmp_path,
    }


def test_good_model_scores_one(case: dict) -> None:
    """A model that runs and produces the expected column scores 1.0."""
    r = grade_execution(GOOD, case, case["_workdir"])
    assert r.score == 1.0, r.detail


def test_broken_model_scores_zero(case: dict) -> None:
    """A model that raises at run time scores 0.0."""
    r = grade_execution(BROKEN, case, case["_workdir"])
    assert r.score == 0.0, r.detail


def test_no_code_scores_zero(case: dict) -> None:
    """An artifact with no code block scores 0.0."""
    r = grade_execution(NO_CODE, case, case["_workdir"])
    assert r.score == 0.0
