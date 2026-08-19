# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Typed Op vocabulary for the rollforward IR.

Each Op is a frozen dataclass with construction-time validation. The
ten Ops cover the actuarial primitive set:

    Arithmetic:  Add, Subtract, Charge
    Time-aware:  Grow, GrowCapped, DeductNAR
    Structural:  Ratchet, Floor, Round, Apply

Pattern adopted from MLIR Op + Verifier — typed Op + a verify() method
that catches impossible configurations at construction time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from gaspatchio.rollforward._refs import StateRef


class Op:
    """Marker base — every concrete Op is a frozen dataclass subclass.

    Not an ABC: ``verify()`` is a sensible no-op default that most Ops
    inherit unchanged; Charge overrides it. Subclassing alone signals
    "this dataclass is an Op", and the canonical-form walker discovers
    fields via ``dataclasses.fields(op)`` rather than via abstract methods.
    """

    def verify(self) -> None:
        """Construction-time validation. Default is a no-op; override per Op."""


_MAX_ROUND_DECIMALS = 15  # beyond f64's decimal precision, rounding is a no-op


def _verify_round_charge(round_charge: int | None, op_name: str) -> None:
    """Reject a charge-rounding precision the kernel cannot apply meaningfully."""
    if round_charge is None:
        return
    # bool is an int subclass and 2.0 passes the range check; both would only
    # fail later, deep in the kernel's Option<i32> deserialization, with an
    # error that never names round_charge.
    if isinstance(round_charge, bool) or not isinstance(round_charge, int):
        msg = (
            f"{op_name}: round_charge must be an int number of decimal places "
            f"or None, got {round_charge!r} ({type(round_charge).__name__}). "
            f"Use 2 for currency."
        )
        raise TypeError(msg)
    if not -_MAX_ROUND_DECIMALS <= round_charge <= _MAX_ROUND_DECIMALS:
        msg = (
            f"{op_name}: round_charge must be between {-_MAX_ROUND_DECIMALS} "
            f"and {_MAX_ROUND_DECIMALS}, got {round_charge}. Use 2 for "
            f"currency; negative values round to tens, hundreds, and so on."
        )
        raise ValueError(msg)


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
    """``s *= 1 - rate[t]`` at the target's point.

    ``round_charge`` rounds the computed charge (half away from zero, Excel's
    ROUND) to that many decimals before applying it — ``s -= ROUND(s*rate, d)``
    — leaving the running state to carry its sub-unit residue forward, which
    is the placement spreadsheets use. Contrast ``Round``, which rounds the
    state and discards the residue every period.
    """

    target: StateRef
    rate: pl.Expr
    label: str | None = None
    round_charge: int | None = None

    def verify(self) -> None:
        _verify_round_charge(self.round_charge, "charge")
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
    """``s *= 1 + rate[t]`` — the rate is applied as quoted per period.

    The schedule ``dt`` is not threaded through, so pre-scale an annual rate to
    the projection frequency yourself (e.g. a monthly rate for a monthly grid).

    ``round_charge`` rounds the computed credit before applying it —
    ``s += ROUND(s*rate, d)`` — the spreadsheet placement (see ``Charge``).
    """

    target: StateRef
    rate: pl.Expr
    label: str | None = None
    round_charge: int | None = None

    def verify(self) -> None:
        _verify_round_charge(self.round_charge, "grow")


@dataclass(frozen=True)
class GrowCapped(Op):
    """``s *= 1 + clamp(rate[t], floor, cap)`` — IUL crediting.

    The rate is applied as quoted per period (no schedule ``dt`` scaling —
    pre-scale to the period).
    """

    target: StateRef
    rate: pl.Expr
    floor: pl.Expr
    cap: pl.Expr
    label: str | None = None


@dataclass(frozen=True)
class DeductNAR(Op):
    """Net-amount-at-risk COI, on one of two timing conventions.

    ``nar_timing="beginning_of_period"`` (default) measures the amount at
    risk where the charge is taken and applies no discount::

        s -= coi_rate[t] * (death_benefit[t] - s)

    ``nar_timing="end_of_period"`` measures it against the accumulated
    balance — the benefit is paid at period end — and discounts the charge
    back. Deducting the COI lowers the balance, which raises the amount at
    risk, so the two are mutually dependent; this is the closed form::

        NAR = (death_benefit - s * accum) / (1 - coi_rate * accum * v)
        s -= coi_rate * NAR * v

    where ``v = 1/(1+coi_discount_rate)`` and ``accum = 1+credited_rate``.

    ``corridor_factor`` adds the regulatory corridor test (IRC §7702 and its
    equivalents): the death benefit is at least ``y`` times the account
    value, so the amount at risk becomes ``MAX(NARf, NARc)`` where the
    corridor branch solves its own, differently-signed, circularity::

        NARc = ((y - 1) * s * accum) / (1 + (y - 1) * coi_rate * accum * v)

    That ``MAX`` is exactly ``death_benefit = MAX(face, y * account_value)``.
    The sign flip matters: under a fixed benefit, charging the COI widens the
    gap to the target, so the branch is self-reinforcing; under a
    proportional benefit it shrinks the benefit too, so the branch is
    self-limiting. As ``y`` approaches 1.0 at advanced ages ``NARc`` goes to
    zero, which is what stops a well-funded policy running away.

    Omitted, only the fixed-benefit branch is computed — and a **negative**
    amount at risk is then refused rather than returned, because it would
    credit the account value and compound.
    """

    target: StateRef
    coi_rate: pl.Expr
    death_benefit: pl.Expr
    nar_timing: str = "beginning_of_period"
    coi_discount_rate: pl.Expr | None = None
    credited_rate: pl.Expr | None = None
    corridor_factor: pl.Expr | None = None
    round_charge: int | None = None
    label: str | None = None

    def verify(self) -> None:
        """Reject a timing convention without the rates it needs."""
        _verify_round_charge(self.round_charge, "deduct_nar")
        valid = ("beginning_of_period", "end_of_period")
        if self.nar_timing not in valid:
            msg = (
                f"deduct_nar: nar_timing must be one of {valid}, got "
                f"{self.nar_timing!r}. This names when the net amount at risk "
                f"is measured — at the point the COI is charged, or at period "
                f"end when the death benefit is actually paid."
            )
            raise ValueError(msg)
        if self.nar_timing == "beginning_of_period" and (
            self.coi_discount_rate is not None or self.credited_rate is not None
        ):
            msg = (
                "deduct_nar: coi_discount_rate and credited_rate only apply "
                'when nar_timing="end_of_period". Under the '
                "beginning-of-period convention the charge is taken on the "
                "balance as it stands, with no discounting, so neither rate "
                "has anything to act on."
            )
            raise ValueError(msg)
        if self.nar_timing == "end_of_period":
            # Both factors default to 1.0 in the kernel. Left to default they
            # would silently produce the simultaneous-solve convention — a
            # third, real convention this API deliberately does not expose —
            # rather than the end-of-period one that was asked for. Refuse.
            missing = [
                name
                for name, rate in (
                    ("coi_discount_rate", self.coi_discount_rate),
                    ("credited_rate", self.credited_rate),
                )
                if rate is None
            ]
            if missing:
                msg = (
                    f"deduct_nar: {' and '.join(missing)} "
                    f"{'is' if len(missing) == 1 else 'are'} required when "
                    'nar_timing="end_of_period". The amount at risk is measured '
                    "against the balance accumulated to period end, and the "
                    "charge is discounted back from the benefit payment, so "
                    "both rates carry the timing. Defaulting them to 1.0 would "
                    "give the simultaneous-solve convention instead — a "
                    "different answer, not a rounding difference."
                )
                raise ValueError(msg)


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
class Round(Op):
    """``s = round(s, decimals)`` — half away from zero, as Excel's ROUND.

    Reproduces a source model that rounds *inside* the recursion. Rounding only
    the final answer is not the same thing: the rounding feeds the next period's
    opening balance, so the difference compounds. Where the running balance is
    already an exact multiple of the rounding unit, rounding the state is
    equivalent to rounding the charge that was just applied to it.

    Half-away-from-zero rather than banker's rounding is deliberate. The op
    exists to match spreadsheets, and over a long projection the tie-breaking
    rule stops being a rounding detail and becomes a visible drift.
    """

    target: StateRef
    decimals: int = 2

    def verify(self) -> None:
        """Reject a rounding precision the kernel cannot apply meaningfully."""
        max_decimals = 15  # beyond f64's decimal precision, rounding is a no-op
        if not -max_decimals <= self.decimals <= max_decimals:
            msg = (
                f"Round: decimals must be between {-max_decimals} and "
                f"{max_decimals}, got {self.decimals}. Use 2 for currency; "
                f"negative values round to tens, hundreds, and so on."
            )
            raise ValueError(msg)


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
    "Round",
    "Subtract",
]
