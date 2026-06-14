# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Shared scenario validators for with_scenarios + for_each_scenario.
# ABOUTME: Single source of truth for duplicate-ID / column-collision / empty checks.

"""Shared validators for scenario primitives."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from gaspatchio_core.frame import ActuarialFrame

T = TypeVar("T")


def check_non_empty(scenario_ids: list[T]) -> None:
    """Raise ValueError if the scenario list is empty."""
    if not scenario_ids:
        msg = (
            "scenarios must contain at least one scenario id. "
            "For single-scenario models, pass ['DETERMINISTIC']."
        )
        raise ValueError(msg)


def check_no_duplicate_ids(scenario_ids: list[T]) -> None:
    """Raise ValueError if any scenario_id appears more than once."""
    if len(scenario_ids) == len(set(scenario_ids)):
        return
    seen: set[T] = set()
    dups: list[T] = []
    for s in scenario_ids:
        if s in seen and s not in dups:
            dups.append(s)
        seen.add(s)
    msg = f"scenarios contains duplicate ids: {dups}. Each scenario_id must be unique."
    raise ValueError(msg)


def check_no_scenario_column(af: ActuarialFrame, column: str) -> None:
    """Raise ValueError if the ActuarialFrame already has a column called ``column``."""
    cols = af.get_column_order()
    if column in cols:
        msg = (
            f"Column {column!r} already exists in ActuarialFrame. "
            f"Rename the existing column or pass a different scenario_column name. "
            f"Existing columns: {cols}"
        )
        raise ValueError(msg)


__all__ = [
    "check_no_duplicate_ids",
    "check_no_scenario_column",
    "check_non_empty",
]
