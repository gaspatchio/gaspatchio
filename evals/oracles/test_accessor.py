# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101
"""Tests for the accessor oracle (extending skill): static anti-pattern scan."""

from evals.oracles.accessor import grade_accessor

CLEAN = """```python
from gaspatchio_core import ActuarialFrame

def hazard(af):
    return -(1 - af.qx).log()
```
"""

ANTIPATTERN = """```python
def hazard(af):
    return af.qx.map_elements(lambda q: -1)
```
"""


def test_clean_accessor_scores_one() -> None:
    """Emitted code free of vectorisation anti-patterns scores 1.0."""
    assert grade_accessor(CLEAN, {}).score == 1.0


def test_antipattern_scores_zero() -> None:
    """map_elements / apply / iter_rows / row-loops score 0.0."""
    assert grade_accessor(ANTIPATTERN, {}).score == 0.0


def test_no_code_scores_zero() -> None:
    """No code block scores 0.0."""
    assert grade_accessor("I'd write an accessor.", {}).score == 0.0
