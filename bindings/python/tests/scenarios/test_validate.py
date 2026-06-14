# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test the shared scenario validators."""

from __future__ import annotations

import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._validate import (
    check_no_duplicate_ids,
    check_no_scenario_column,
    check_non_empty,
)


def test_check_non_empty_raises_on_empty() -> None:
    """Empty scenario list must raise ValueError."""
    with pytest.raises(ValueError, match="at least one"):
        check_non_empty([])


def test_check_non_empty_passes() -> None:
    """Non-empty list passes without exception."""
    check_non_empty([1, 2, 3])


def test_check_no_duplicate_ids_raises() -> None:
    """Duplicate scenario IDs must raise ValueError naming the duplicates."""
    with pytest.raises(ValueError, match="duplicate"):
        check_no_duplicate_ids([1, 2, 1])


def test_check_no_duplicate_ids_passes() -> None:
    """Unique scenario IDs pass without exception."""
    check_no_duplicate_ids([1, 2, 3])


def test_check_no_scenario_column_raises() -> None:
    """Existing scenario_column on the frame must raise ValueError."""
    af = ActuarialFrame({"scenario_id": [1, 2], "x": [10, 20]})
    with pytest.raises(ValueError, match="scenario_id"):
        check_no_scenario_column(af, "scenario_id")


def test_check_no_scenario_column_passes() -> None:
    """Missing scenario_column on the frame passes without exception."""
    af = ActuarialFrame({"policy_id": [1, 2], "x": [10, 20]})
    check_no_scenario_column(af, "scenario_id")
