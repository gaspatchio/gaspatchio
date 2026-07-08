# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""IR — the engine-portable canonical representation of a rollforward.

Frozen dataclass — once constructed, the IR is immutable. Compilation
passes operate by producing new IRs, not by mutating.

Fields:
  - states: (name, init) declarations
  - points: structural point names (must include 'bop' and 'eop')
  - transitions: typed Op tuple, in declared order
  - schedule: the bound Schedule
  - batch_axes: tuple of axis names; defaults to ('policy',). Forward-compat
    for stochastic projection (vmap over scenario axis).
  - track_increments: bool — when True, every Op's per-period delta is
    surfaced via ``CompiledRollforward.increment_for(label)``.
  - lapse_when_all_non_positive: tuple of state names — kernel stops
    advancing when all named states are <= 0 at end-of-period.
  - contract_boundary: optional closed-subset bool Expr — kernel stops at
    first True. Folded into spec_fingerprint; engine_binding-aware.
  - engine_binding: 'portable' | 'polars' — derived (not user-supplied).
    Computed by static walk over transitions + Apply.body + contract_boundary.

The IR is JSON-serialisable via ``_canonical.canonical_form()``. Two IRs
producing the same canonical bytes have identical spec_fingerprint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio_core.rollforward._ops import Op
    from gaspatchio_core.schedule import Schedule

EngineBinding = Literal["portable", "polars"]


@dataclass(frozen=True)
class State:
    """A named state with an initial-value expression."""

    name: str
    init: pl.Expr

    def __post_init__(self) -> None:
        if not self.name:
            msg = "state name must be non-empty"
            raise ValueError(msg)


@dataclass(frozen=True)
class IR:
    """Engine-portable rollforward intermediate representation."""

    states: tuple[State, ...]
    points: tuple[str, ...]
    transitions: tuple[Op, ...]
    schedule: Schedule
    batch_axes: tuple[str, ...]
    track_increments: bool
    lapse_when_all_non_positive: tuple[str, ...]
    contract_boundary: pl.Expr | None
    # engine_binding is intentionally NOT in the constructor — it's derived
    # by `_engine_binding.derive_engine_binding(ir)` when canonical form is
    # built. Storing it on the IR would create a "set after construction"
    # mutability hole.

    def __post_init__(self) -> None:
        if "bop" not in self.points or "eop" not in self.points:
            msg = "points must include 'bop' and 'eop'"
            raise ValueError(msg)
        names = [s.name for s in self.states]
        if len(names) != len(set(names)):
            msg = f"duplicate state name in {names}"
            raise ValueError(msg)


__all__ = ["IR", "EngineBinding", "State"]
