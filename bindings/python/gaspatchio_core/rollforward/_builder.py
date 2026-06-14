# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""User-facing builder API for the rollforward kernel.

The builder is mutable scaffolding that emits an immutable :class:`IR`
on ``._build()``. Users construct it via ``af.projection.rollforward(...)``
or directly, and chain method calls on state handles to declare
transitions.

Builder semantics:
  - Default points are ``("bop", "eop")`` if not supplied.
  - User-supplied ``points`` must include ``'bop'`` and ``'eop'``; the
    declared order is the partial order the kernel walks.
  - Default ``batch_axes`` is ``("policy",)``.
  - Schedule is required (even for products that don't care about
    calendar discipline — pass an integer-period default Schedule).
  - ``contract_boundary`` accepts a closed-subset boolean :class:`pl.Expr`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio_core.rollforward._ops import (
    Add,
    Apply,
    Charge,
    DeductNAR,
    Floor,
    Grow,
    GrowCapped,
    Ratchet,
    Subtract,
)
from gaspatchio_core.rollforward._refs import StateRef

if TYPE_CHECKING:
    from collections.abc import Iterable

    import polars as pl

    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.rollforward._ir import IR
    from gaspatchio_core.rollforward._ops import Op
    from gaspatchio_core.schedule import Schedule

    # An accepted expression-like input. Anything with ``_to_expr()`` is
    # unwrapped at the boundary; plain ``pl.Expr`` passes through unchanged.
    # TYPE_CHECKING-only — stubtest allowlists this alias by name.
    ExprLike = pl.Expr | ColumnProxy | ExpressionProxy


def _to_polars_expr(x: object) -> pl.Expr:
    """Coerce ``af['col']`` / ``af['a'] + af['b']`` to a polars expression.

    Pass-through for anything that's already a ``pl.Expr``. Detection is
    structural (looks for ``_to_expr``) to avoid importing the column-proxy
    module here.
    """
    to_expr = getattr(x, "_to_expr", None)
    if callable(to_expr):
        return to_expr()
    return x  # type: ignore[return-value]


class RollforwardBuilder:
    """Mutable builder that produces an immutable IR on ``._build()``."""

    def __init__(  # noqa: PLR0913 — every kwarg maps to an IR field; collapsing into a config dict would lose call-site readability
        self,
        *,
        states: dict[str, ExprLike],
        schedule: Schedule,
        points: Iterable[str] | None = None,
        track_increments: bool = False,
        lapse_when_all_non_positive: Iterable[str] = (),
        contract_boundary: ExprLike | None = None,
        batch_axes: tuple[str, ...] = ("policy",),
    ) -> None:
        # Validate points
        pts = tuple(points) if points is not None else ("bop", "eop")
        if "bop" not in pts or "eop" not in pts:
            msg = "points must include 'bop' and 'eop'"
            raise ValueError(msg)

        # Validate lapse states all exist
        lapse_tuple = tuple(lapse_when_all_non_positive)
        unknown = [s for s in lapse_tuple if s not in states]
        if unknown:
            msg = (
                f"lapse_when_all_non_positive references unknown state(s) {unknown}; "
                f"declared states are {list(states)}"
            )
            raise ValueError(msg)

        self._state_inits: dict[str, pl.Expr] = {
            k: _to_polars_expr(v) for k, v in states.items()
        }
        self._points: tuple[str, ...] = pts
        self._schedule = schedule
        self._track_increments = track_increments
        self._lapse_when_all_non_positive = lapse_tuple
        self._contract_boundary = (
            _to_polars_expr(contract_boundary) if contract_boundary is not None else None
        )
        self._batch_axes: tuple[str, ...] = tuple(batch_axes)

        # Op accumulator — mutated as the user chains transitions
        self._transitions: list[Op] = []
        # Current scope window (None if no .between(...) is active)
        self._current_state: str | None = None
        self._current_window: tuple[str, str] | None = None

    def __getitem__(self, state_name: str) -> _StateHandle:
        if state_name not in self._state_inits:
            msg = (
                f"unknown state {state_name!r}; "
                f"declared states are {list(self._state_inits)}"
            )
            raise KeyError(msg)
        return _StateHandle(self, state_name)

    def increment(self, label: str) -> IncrementRef:
        if not self._track_increments:
            msg = (
                "rf.increment(...) requires track_increments=True on the builder; "
                "construct rollforward with track_increments=True to use increments"
            )
            raise ValueError(msg)
        return IncrementRef(label=label)

    def _build(self) -> IR:
        from gaspatchio_core.rollforward._ir import IR as _IR
        from gaspatchio_core.rollforward._ir import State

        states = tuple(
            State(name=name, init=init) for name, init in self._state_inits.items()
        )
        return _IR(
            states=states,
            points=self._points,
            transitions=tuple(self._transitions),
            schedule=self._schedule,
            batch_axes=self._batch_axes,
            track_increments=self._track_increments,
            lapse_when_all_non_positive=self._lapse_when_all_non_positive,
            contract_boundary=self._contract_boundary,
        )


class _StateHandle:
    """Mutable proxy returned by ``builder["state_name"]``.

    Holds a reference to the parent builder and the state name; method
    calls (``.add()``, ``.subtract()``, etc.) emit Ops into the builder.
    Returns ``self`` from each emit so calls chain.
    """

    def __init__(self, builder: RollforwardBuilder, state: str) -> None:
        self._b = builder
        self._state = state

    def _target_point(self) -> str:
        # If a .between(...) scope is active and applies to this state, use its
        # end-point. Otherwise default to 'eop'.
        if (
            self._b._current_state == self._state
            and self._b._current_window is not None
        ):
            return self._b._current_window[1]
        return "eop"

    def add(self, expr: ExprLike, *, label: str | None = None) -> _StateHandle:
        op = Add(
            target=StateRef(state=self._state, point=self._target_point()),
            expr=_to_polars_expr(expr),
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def subtract(self, expr: ExprLike, *, label: str | None = None) -> _StateHandle:
        op = Subtract(
            target=StateRef(state=self._state, point=self._target_point()),
            expr=_to_polars_expr(expr),
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def charge(self, rate: ExprLike, *, label: str | None = None) -> _StateHandle:
        op = Charge(
            target=StateRef(state=self._state, point=self._target_point()),
            rate=_to_polars_expr(rate),
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def grow(self, rate: ExprLike, *, label: str | None = None) -> _StateHandle:
        op = Grow(
            target=StateRef(state=self._state, point=self._target_point()),
            rate=_to_polars_expr(rate),
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def grow_capped(
        self,
        rate: ExprLike,
        *,
        floor: ExprLike,
        cap: ExprLike,
        label: str | None = None,
    ) -> _StateHandle:
        op = GrowCapped(
            target=StateRef(state=self._state, point=self._target_point()),
            rate=_to_polars_expr(rate),
            floor=_to_polars_expr(floor),
            cap=_to_polars_expr(cap),
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def deduct_nar(
        self,
        coi_rate: ExprLike,
        *,
        death_benefit: ExprLike,
        label: str | None = None,
    ) -> _StateHandle:
        op = DeductNAR(
            target=StateRef(state=self._state, point=self._target_point()),
            coi_rate=_to_polars_expr(coi_rate),
            death_benefit=_to_polars_expr(death_benefit),
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def ratchet(
        self,
        *,
        to: ExprLike,
        when: ExprLike | None = None,
        label: str | None = None,
    ) -> _StateHandle:
        op = Ratchet(
            target=StateRef(state=self._state, point=self._target_point()),
            to=_to_polars_expr(to),
            when=_to_polars_expr(when) if when is not None else None,
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def floor(self, value: float) -> _StateHandle:
        op = Floor(
            target=StateRef(state=self._state, point=self._target_point()),
            value=value,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def apply(self, body: ExprLike, *, label: str | None = None) -> _StateHandle:
        op = Apply(
            target=StateRef(state=self._state, point=self._target_point()),
            body=_to_polars_expr(body),
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def between(self, p1: str, p2: str) -> _StateHandle:
        # Validate points exist
        for p in (p1, p2):
            if p not in self._b._points:
                msg = (
                    f"unknown point {p!r}; declared points are {list(self._b._points)}"
                )
                raise ValueError(msg)
        # Validate p1 precedes p2 in declared order
        if self._b._points.index(p1) >= self._b._points.index(p2):
            msg = f"{p1!r} must precede {p2!r} in declared point order"
            raise ValueError(msg)
        # Stash the scope on the builder; subsequent ops on this handle pick it up.
        # New handle is returned (rather than mutating self) so each chain has its
        # own scope window without aliasing.
        new_handle = _StateHandle(self._b, self._state)
        self._b._current_state = self._state
        self._b._current_window = (p1, p2)
        return new_handle

    def at(self, point: str) -> StateRef:
        if point not in self._b._points:
            msg = (
                f"unknown point {point!r}; declared points are {list(self._b._points)}"
            )
            raise ValueError(msg)
        return StateRef(state=self._state, point=point)


from dataclasses import dataclass  # noqa: E402


@dataclass(frozen=True)
class IncrementRef:
    """Opaque reference to a labelled per-period delta.

    Resolved by the compiler into the corresponding Struct field name.
    """

    label: str


__all__ = ["IncrementRef", "RollforwardBuilder"]
