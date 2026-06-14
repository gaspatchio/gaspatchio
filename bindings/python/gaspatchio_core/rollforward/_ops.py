# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Typed Op vocabulary for the rollforward IR.

Each Op is a frozen dataclass with construction-time validation. The
nine Ops cover the actuarial primitive set:

    Arithmetic:  Add, Subtract, Charge
    Time-aware:  Grow, GrowCapped, DeductNAR
    Structural:  Ratchet, Floor, Apply

Pattern adopted from MLIR Op + Verifier — typed Op + a verify() method
that catches impossible configurations at construction time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._refs import StateRef


class Op:
    """Marker base — every concrete Op is a frozen dataclass subclass.

    Not an ABC: ``verify()`` is a sensible no-op default that most Ops
    inherit unchanged; Charge overrides it. Subclassing alone signals
    "this dataclass is an Op", and the canonical-form walker discovers
    fields via ``dataclasses.fields(op)`` rather than via abstract methods.
    """

    def verify(self) -> None:
        """Construction-time validation. Default is a no-op; override per Op."""


@dataclass(frozen=True)
class Add(Op):
    """``s += amount[t]`` at the target's point."""

    target: StateRef
    expr: pl.Expr
    label: str | None = None


@dataclass(frozen=True)
class Subtract(Op):
    """``s -= amount[t]`` at the target's point."""

    target: StateRef
    expr: pl.Expr
    label: str | None = None


@dataclass(frozen=True)
class Charge(Op):
    """``s *= 1 - rate[t]`` at the target's point."""

    target: StateRef
    rate: pl.Expr
    label: str | None = None

    def verify(self) -> None:
        # Heuristic: a literal negative rate is almost certainly a bug
        # (rate=0.05 means "5% expense charge"; rate=-0.05 would mean
        # "negative expense" i.e. a credit). Real negative rates should
        # be modelled as Add, not Charge.
        try:
            value = pl.select(self.rate.cast(pl.Float64)).item()
        except Exception:  # noqa: BLE001
            return  # Non-literal expression — defer to runtime
        if value is not None and value < 0:
            msg = (
                f"Charge {self.label!r} has negative literal rate ({value}); "
                "use Add for credits"
            )
            raise ValueError(msg)


@dataclass(frozen=True)
class Grow(Op):
    """``s *= 1 + rate[t]`` — the rate is applied as quoted per period; the
    schedule ``dt`` is not threaded through, so pre-scale an annual rate to the
    projection frequency yourself (e.g. a monthly rate for a monthly grid)."""

    target: StateRef
    rate: pl.Expr
    label: str | None = None


@dataclass(frozen=True)
class GrowCapped(Op):
    """``s *= 1 + clamp(rate[t], floor, cap)`` — IUL crediting; rate applied as
    quoted per period (no schedule ``dt`` scaling — pre-scale to the period)."""

    target: StateRef
    rate: pl.Expr
    floor: pl.Expr
    cap: pl.Expr
    label: str | None = None


@dataclass(frozen=True)
class DeductNAR(Op):
    """Net-amount-at-risk COI: ``s -= coi_rate[t] * (death_benefit[t] - s)``."""

    target: StateRef
    coi_rate: pl.Expr
    death_benefit: pl.Expr
    label: str | None = None


@dataclass(frozen=True)
class Ratchet(Op):
    """``s = max(s, to[t]) if when[t] else s`` — GMxB anniversary step-up.

    ``when=None`` means unconditional (every period) — used for lookback /
    HWM trackers where the ratchet fires every period.
    """

    target: StateRef
    to: pl.Expr
    when: pl.Expr | None
    label: str | None = None


@dataclass(frozen=True)
class Floor(Op):
    """``s = max(s, value)`` — non-negativity (or other lower-bound) constraint."""

    target: StateRef
    value: float


@dataclass(frozen=True)
class Apply(Op):
    """Escape hatch — assign ``body`` directly to the target's point.

    Use sparingly: ``Apply.body`` is an unbounded ``pl.Expr`` that the
    static engine-binding walk inspects. Any non-closed-subset operator
    (``pl.max_horizontal``, raw ``pl.Expr`` calls, autopatched methods)
    flips the IR's ``engine_binding`` from ``'portable'`` to ``'polars'``.
    """

    target: StateRef
    body: pl.Expr
    label: str | None = None


__all__ = [
    "Add",
    "Apply",
    "Charge",
    "DeductNAR",
    "Floor",
    "Grow",
    "GrowCapped",
    "Op",
    "Ratchet",
    "Subtract",
]
