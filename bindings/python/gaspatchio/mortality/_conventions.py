# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Mortality-specific Literal types + validation helpers."""

from __future__ import annotations

from typing import Literal

AgeBasis = Literal["age_last_birthday", "age_nearest_birthday"]
Structure = Literal["aggregate", "select_ultimate", "joint"]

_VALID_AGE_BASES: frozenset[str] = frozenset(
    {"age_last_birthday", "age_nearest_birthday"}
)
_VALID_STRUCTURES: frozenset[str] = frozenset({"aggregate", "select_ultimate", "joint"})


def validate_age_basis(value: str) -> None:
    """Raise ValueError if `value` is not a recognised age basis."""
    if value not in _VALID_AGE_BASES:
        msg = f"unknown age_basis {value!r}; expected one of {sorted(_VALID_AGE_BASES)}"
        raise ValueError(msg)


def validate_structure(value: str) -> None:
    """Raise ValueError if `value` is not a recognised structure."""
    if value not in _VALID_STRUCTURES:
        msg = (
            f"unknown structure {value!r}; expected one of {sorted(_VALID_STRUCTURES)}"
        )
        raise ValueError(msg)


def validate_select_period(structure: str, select_period: int | None) -> None:
    """Enforce the structure <-> select_period coupling.

    select_period is required for structure='select_ultimate' and
    forbidden for the other structures.
    """
    if structure == "select_ultimate":
        if select_period is None:
            msg = "select_period is required when structure='select_ultimate'"
            raise ValueError(msg)
        if select_period < 1:
            msg = f"select_period must be a positive integer; got {select_period}"
            raise ValueError(msg)
    elif select_period is not None:
        msg = (
            f"select_period only valid for structure='select_ultimate'; "
            f"got structure={structure!r}"
        )
        raise ValueError(msg)


__all__ = [
    "AgeBasis",
    "Structure",
    "validate_age_basis",
    "validate_select_period",
    "validate_structure",
]
