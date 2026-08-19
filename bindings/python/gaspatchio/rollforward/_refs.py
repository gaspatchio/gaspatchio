# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Typed references — StateRef and PointRef.

A StateRef names a (state, point) pair — used by users when reading state
mid-period (e.g. ``rf["fund"].at("after_growth")``) and by the compiler
when wiring captures into the kernel's Struct output.

A PointRef names a structural location within a single period (``bop``,
``post_coi``, ``after_growth``, ``eop``, etc.). The IR's ``points`` list
declares the partial order; transitions reference points to express
between-which-two-points the body fires.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateRef:
    state: str
    point: str

    def __post_init__(self) -> None:
        if not self.state:
            msg = "state name must be non-empty"
            raise ValueError(msg)
        if not self.point:
            msg = "point name must be non-empty"
            raise ValueError(msg)

    def canonical_name(self) -> str:
        return f"{self.state}@{self.point}"


@dataclass(frozen=True)
class PointRef:
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            msg = "point name must be non-empty"
            raise ValueError(msg)

    def canonical_name(self) -> str:
        return self.name


__all__ = ["PointRef", "StateRef"]
