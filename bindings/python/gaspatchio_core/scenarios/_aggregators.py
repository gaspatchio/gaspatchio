# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: GSP-101 aggregator primitives implementing the Aggregator Protocol.
# ABOUTME: Each aggregator is partition-blind; partitioning is added via .over().

"""GSP-101 aggregator primitives.

Each aggregator implements the Aggregator Protocol from _metric.py:
    within_expr, create_accumulator, add_input, merge_accumulators,
    extract_output, canonical_form.

Aggregators are partition-blind. To partition, call ``.over(by)`` which
returns a ``_Partitioned`` wrapper that holds the
``dict[partition_key, acc]`` state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

import polars as pl

from gaspatchio_core.scenarios._metric import Aggregator, _Partitioned
from gaspatchio_core.scenarios._sketch import SignedSketch

if TYPE_CHECKING:
    from collections.abc import Callable

_VALID_WITHIN: tuple[str, ...] = (
    "sum",
    "mean",
    "max",
    "min",
    "count",
    "first",
    "last",
)


_WITHIN_TABLE: dict[str, Callable[[str], pl.Expr]] = {
    "sum": lambda c: pl.col(c).sum(),
    "mean": lambda c: pl.col(c).mean(),
    "max": lambda c: pl.col(c).max(),
    "min": lambda c: pl.col(c).min(),
    "count": lambda c: pl.col(c).count(),
    "first": lambda c: pl.col(c).first(),
    "last": lambda c: pl.col(c).last(),
}


def _within_to_expr(column: str, within: str) -> pl.Expr:
    """Translate a named within reduction into a polars expression."""
    builder = _WITHIN_TABLE.get(within)
    if builder is None:
        msg = f"within must be one of {_VALID_WITHIN}, got {within!r}"
        raise ValueError(msg)
    return builder(column)


def _validate_within(within: str) -> None:
    if within not in _VALID_WITHIN:
        msg = f"within must be one of {_VALID_WITHIN}, got {within!r}"
        raise ValueError(msg)


# ---- Plugin registry ----

_AGGREGATOR_REGISTRY: dict[str, type] = {}


def register_aggregator(name: str, cls: type) -> None:
    """Register an Aggregator class under a string name.

    Raises ValueError if the class's canonical_form()["kind"] does not
    match the registered name (when the class is zero-arg constructible).
    """
    if name in _AGGREGATOR_REGISTRY:
        msg = f"Aggregator {name!r} already registered."
        raise ValueError(msg)
    try:
        inst = cls(column="__check__")  # type: ignore[call-arg]
        actual_kind = inst.canonical_form().get("kind")
        if actual_kind != name:
            msg = (
                f"Aggregator class {cls.__name__} registered as {name!r} but "
                f"canonical_form()['kind'] returns {actual_kind!r}. "
                "These must match for YAML round-trip."
            )
            raise ValueError(msg)
    except (TypeError, KeyError):
        # Class signature mismatch, or canonical_form doesn't expose 'kind'.
        # Skip the check; YAML reload will surface real problems.
        pass
    _AGGREGATOR_REGISTRY[name] = cls


def scenario_aggregator(name: str) -> Callable[[type], type]:
    """Register a class as an aggregator under ``name``.

    Usage: ``@scenario_aggregator("Sum")`` above the class.

    Cross-join note: every scenario sees every policy via cross-join. The
    within-reduction (``within_expr()``) runs over the full per-scenario
    projection; ``add_input`` receives one value per scenario, not one per row.
    """

    def decorator(cls: type) -> type:
        register_aggregator(name, cls)
        return cls

    return decorator


# ---- Base modifier mixin (alias/over/of) ----


@dataclass(frozen=True)
class _BaseAggregator:
    """Shared modifier base: alias, over, of.

    Concrete subclasses supply create_accumulator/add_input/merge_accumulators/
    extract_output/canonical_form. They inherit within_expr, alias, over, of.

    Subclasses set ``requires_scenario_id = True`` (ClassVar) to opt into
    receiving ``(scenario_id, value)`` tuples in ``add_input`` rather than
    bare values. Default is False.
    """

    requires_scenario_id: ClassVar[bool] = False

    column: str
    within: str = "sum"
    alias_: str | None = None
    within_expr_override: pl.Expr | None = None

    def __post_init__(self) -> None:
        if self.within_expr_override is None:
            _validate_within(self.within)

    def within_expr(self) -> pl.Expr:
        if self.within_expr_override is not None:
            return self.within_expr_override
        return _within_to_expr(self.column, self.within)

    def alias(self, name: str) -> _BaseAggregator:
        return replace(self, alias_=name)

    def over(self, by: str | tuple[str, ...]) -> _Partitioned:
        if self.alias_ is None:
            msg = "Call .alias(name) before .over(...) so the output column is named."
            raise ValueError(msg)
        by_tuple = (by,) if isinstance(by, str) else tuple(by)
        # _BaseAggregator's abstract methods are filled in by concrete subclasses
        # (Sum, Mean, etc.). The runtime guard in _Partitioned.__post_init__
        # enforces the Aggregator Protocol; mypy cannot prove this through the
        # inheritance hierarchy.
        return _Partitioned(
            by=by_tuple,
            inner=cast("Aggregator", self),
            alias=self.alias_,
        )

    @classmethod
    def of(cls, within_expr: pl.Expr) -> _BaseAggregator:
        # column is unused when within_expr_override is set; pass sentinel
        return cls(column="__expr__", within_expr_override=within_expr)


# Public alias for the modifier base. The leading underscore is retained on
# the internal name because the dataclass field set is a private layout
# detail; users should inherit `BaseAggregator` rather than reach for it.
BaseAggregator = _BaseAggregator

# ---- Sum ----


@scenario_aggregator("Sum")
@dataclass(frozen=True)
class Sum(_BaseAggregator):
    """Sum across scenarios.

    Uses Neumaier-compensated summation. State is a ``(running_sum, comp)``
    tuple; each add and merge carries a compensation term that captures
    bits lost to round-off and feeds them back at ``extract_output``. Error
    is O(eps) regardless of input count, and the result is order-stable
    across ``batch_size`` for well-conditioned inputs (the only branch is
    a value-magnitude comparison, which is commutative).
    """

    def create_accumulator(self) -> tuple[float, float]:
        return (0.0, 0.0)

    def add_input(
        self,
        state: tuple[float, float],
        value: float,
    ) -> tuple[float, float]:
        if value is None:
            return state
        s, c = state
        x = float(value)
        t = s + x
        # Neumaier: pick the |larger|-magnitude side as the "stable" addend.
        c = c + ((s - t) + x) if abs(s) >= abs(x) else c + ((x - t) + s)
        return (t, c)

    def merge_accumulators(
        self,
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> tuple[float, float]:
        sa, ca = a
        sb, cb = b
        t = sa + sb
        merge_c = ((sa - t) + sb) if abs(sa) >= abs(sb) else ((sb - t) + sa)
        return (t, ca + cb + merge_c)

    def extract_output(self, state: tuple[float, float]) -> float:
        s, c = state
        return float(s + c)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Sum",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- Count ----


@scenario_aggregator("Count")
@dataclass(frozen=True)
class Count(_BaseAggregator):
    """Count of scenarios that contributed any value."""

    def create_accumulator(self) -> int:
        return 0

    def add_input(self, state: int, value: Any) -> int:  # noqa: ANN401, ARG002
        return state + 1

    def merge_accumulators(self, a: int, b: int) -> int:
        return a + b

    def extract_output(self, state: int) -> int:
        return int(state)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Count", "column": self.column}


# ---- Min ----


@scenario_aggregator("Min")
@dataclass(frozen=True)
class Min(_BaseAggregator):
    """Min across scenarios."""

    def create_accumulator(self) -> float | None:
        return None

    def add_input(self, state: float | None, value: float) -> float:
        return value if state is None else min(state, value)

    def merge_accumulators(self, a: float | None, b: float | None) -> float | None:
        if a is None:
            return b
        if b is None:
            return a
        return min(a, b)

    def extract_output(self, state: float | None) -> float:
        return float("nan") if state is None else float(state)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Min",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- Max ----


@scenario_aggregator("Max")
@dataclass(frozen=True)
class Max(_BaseAggregator):
    """Max across scenarios."""

    def create_accumulator(self) -> float | None:
        return None

    def add_input(self, state: float | None, value: float) -> float:
        return value if state is None else max(state, value)

    def merge_accumulators(self, a: float | None, b: float | None) -> float | None:
        if a is None:
            return b
        if b is None:
            return a
        return max(a, b)

    def extract_output(self, state: float | None) -> float:
        return float("nan") if state is None else float(state)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Max",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- ArgMin / ArgMax ----


@scenario_aggregator("ArgMax")
@dataclass(frozen=True)
class ArgMax(_BaseAggregator):
    """Scenario_id of the scenario with the maximum value.

    add_input receives a (scenario_id, value) tuple. Lexicographic
    tiebreak: on equal values, the smaller scenario_id wins.
    """

    requires_scenario_id: ClassVar[bool] = True

    def create_accumulator(self) -> tuple[Any, float] | None:
        return None

    def add_input(
        self,
        state: tuple[Any, float] | None,
        value: tuple[Any, float],
    ) -> tuple[Any, float]:
        sid, v = value
        if state is None:
            return (sid, v)
        best_sid, best_v = state
        if v > best_v:
            return (sid, v)
        if v == best_v and sid < best_sid:
            return (sid, v)
        return state

    def merge_accumulators(
        self,
        a: tuple[Any, float] | None,
        b: tuple[Any, float] | None,
    ) -> tuple[Any, float] | None:
        if a is None:
            return b
        if b is None:
            return a
        return self.add_input(a, b)

    def extract_output(self, state: tuple[Any, float] | None) -> Any:  # noqa: ANN401
        return None if state is None else state[0]

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "ArgMax",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


@scenario_aggregator("ArgMin")
@dataclass(frozen=True)
class ArgMin(_BaseAggregator):
    """Scenario_id of the scenario with the minimum value. Lex tiebreak."""

    requires_scenario_id: ClassVar[bool] = True

    def create_accumulator(self) -> tuple[Any, float] | None:
        return None

    def add_input(
        self,
        state: tuple[Any, float] | None,
        value: tuple[Any, float],
    ) -> tuple[Any, float]:
        sid, v = value
        if state is None:
            return (sid, v)
        best_sid, best_v = state
        if v < best_v:
            return (sid, v)
        if v == best_v and sid < best_sid:
            return (sid, v)
        return state

    def merge_accumulators(
        self,
        a: tuple[Any, float] | None,
        b: tuple[Any, float] | None,
    ) -> tuple[Any, float] | None:
        if a is None:
            return b
        if b is None:
            return a
        return self.add_input(a, b)

    def extract_output(self, state: tuple[Any, float] | None) -> Any:  # noqa: ANN401
        return None if state is None else state[0]

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "ArgMin",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- Welford / Chan helpers ----

# Sample variance (ddof=1) requires at least this many observations.
_MIN_N_FOR_SAMPLE_VARIANCE = 2


def _welford_create() -> dict[str, float]:
    return {"n": 0, "mean": 0.0, "m2": 0.0}


def _welford_add(state: dict[str, float], value: float) -> dict[str, float]:
    n = state["n"] + 1
    delta = value - state["mean"]
    mean = state["mean"] + delta / n
    delta2 = value - mean
    m2 = state["m2"] + delta * delta2
    return {"n": n, "mean": mean, "m2": m2}


def _welford_merge(
    a: dict[str, float],
    b: dict[str, float],
) -> dict[str, float]:
    if a["n"] == 0:
        return dict(b)
    if b["n"] == 0:
        return dict(a)
    n = a["n"] + b["n"]
    delta = b["mean"] - a["mean"]
    mean = a["mean"] + delta * b["n"] / n
    m2 = a["m2"] + b["m2"] + delta * delta * a["n"] * b["n"] / n
    return {"n": n, "mean": mean, "m2": m2}


# ---- Mean ----


@scenario_aggregator("Mean")
@dataclass(frozen=True)
class Mean(_BaseAggregator):
    """Mean across scenarios."""

    def create_accumulator(self) -> dict[str, float]:
        return _welford_create()

    def add_input(
        self,
        state: dict[str, float],
        value: float,
    ) -> dict[str, float]:
        return _welford_add(state, value)

    def merge_accumulators(
        self,
        a: dict[str, float],
        b: dict[str, float],
    ) -> dict[str, float]:
        return _welford_merge(a, b)

    def extract_output(self, state: dict[str, float]) -> float:
        return float("nan") if state["n"] == 0 else float(state["mean"])

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Mean",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- Variance ----


@scenario_aggregator("Variance")
@dataclass(frozen=True)
class Variance(_BaseAggregator):
    """Sample variance across scenarios (ddof=1)."""

    def create_accumulator(self) -> dict[str, float]:
        return _welford_create()

    def add_input(
        self,
        state: dict[str, float],
        value: float,
    ) -> dict[str, float]:
        return _welford_add(state, value)

    def merge_accumulators(
        self,
        a: dict[str, float],
        b: dict[str, float],
    ) -> dict[str, float]:
        return _welford_merge(a, b)

    def extract_output(self, state: dict[str, float]) -> float:
        if state["n"] < _MIN_N_FOR_SAMPLE_VARIANCE:
            return float("nan")
        return float(state["m2"] / (state["n"] - 1))

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Variance",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- Std ----


@scenario_aggregator("Std")
@dataclass(frozen=True)
class Std(_BaseAggregator):
    """Sample standard deviation across scenarios."""

    def create_accumulator(self) -> dict[str, float]:
        return _welford_create()

    def add_input(
        self,
        state: dict[str, float],
        value: float,
    ) -> dict[str, float]:
        return _welford_add(state, value)

    def merge_accumulators(
        self,
        a: dict[str, float],
        b: dict[str, float],
    ) -> dict[str, float]:
        return _welford_merge(a, b)

    def extract_output(self, state: dict[str, float]) -> float:
        if state["n"] < _MIN_N_FOR_SAMPLE_VARIANCE:
            return float("nan")
        return math.sqrt(state["m2"] / (state["n"] - 1))

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Std",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- Sketch-backed aggregators (Quantile / Median / CTE / QuantileRank) ----

# Binary-search iterations for QuantileRank: 40 halvings ~ 1e-12 precision in q-space.
_QUANTILE_RANK_BISECT_ITERS = 40


# ---- Quantile ----


@scenario_aggregator("Quantile")
@dataclass(frozen=True)
class Quantile(_BaseAggregator):
    """Quantile(s) across scenarios - DDSketch-backed mergeable."""

    levels: tuple[float, ...] = (0.5,)
    relative_accuracy: float = 1e-4

    def create_accumulator(self) -> SignedSketch:
        return SignedSketch(relative_accuracy=self.relative_accuracy)

    def add_input(self, state: SignedSketch, value: float) -> SignedSketch:
        state.add(float(value))
        return state

    def merge_accumulators(
        self,
        a: SignedSketch,
        b: SignedSketch,
    ) -> SignedSketch:
        return SignedSketch.merge(a, b)

    def extract_output(self, state: SignedSketch) -> dict[float, float]:
        return {level: state.quantile(level) for level in self.levels}

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Quantile",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
            "levels": list(self.levels),
            "relative_accuracy": self.relative_accuracy,
        }


# ---- Median ----


@scenario_aggregator("Median")
@dataclass(frozen=True)
class Median(_BaseAggregator):
    """Median across scenarios - DDSketch-backed. Equivalent to Quantile(0.5)."""

    relative_accuracy: float = 1e-4

    def create_accumulator(self) -> SignedSketch:
        return SignedSketch(relative_accuracy=self.relative_accuracy)

    def add_input(self, state: SignedSketch, value: float) -> SignedSketch:
        state.add(float(value))
        return state

    def merge_accumulators(
        self,
        a: SignedSketch,
        b: SignedSketch,
    ) -> SignedSketch:
        return SignedSketch.merge(a, b)

    def extract_output(self, state: SignedSketch) -> float:
        return state.quantile(0.5)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Median",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
            "relative_accuracy": self.relative_accuracy,
        }


# ---- CTE ----


@scenario_aggregator("CTE")
@dataclass(frozen=True)
class CTE(_BaseAggregator):
    """Conditional Tail Expectation - DDSketch-backed mergeable.

    For Solvency II SCR (99.5% loss):
      - positive-is-loss convention:
        ``CTE(column, level=0.005, direction="upper")``
      - P&L convention (positive is profit):
        ``CTE(column, level=0.005, direction="lower")``

    ``direction="upper"`` averages values **above** the ``(1 - level)`` quantile.
    ``direction="lower"`` averages values **below** the ``level`` quantile.
    """

    level: float = 0.005
    direction: Literal["upper", "lower"] = "upper"
    relative_accuracy: float = 1e-4

    def create_accumulator(self) -> SignedSketch:
        return SignedSketch(relative_accuracy=self.relative_accuracy)

    def add_input(self, state: SignedSketch, value: float) -> SignedSketch:
        state.add(float(value))
        return state

    def merge_accumulators(
        self,
        a: SignedSketch,
        b: SignedSketch,
    ) -> SignedSketch:
        return SignedSketch.merge(a, b)

    def extract_output(self, state: SignedSketch) -> float:
        return state.cte(level=self.level, direction=self.direction)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "CTE",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
            "level": self.level,
            "direction": self.direction,
            "relative_accuracy": self.relative_accuracy,
        }


# ---- QuantileRank ----


@scenario_aggregator("QuantileRank")
@dataclass(frozen=True)
class QuantileRank(_BaseAggregator):
    """Empirical rank of a target value in the across-scenario distribution.

    Returns a value in ``[0, 1]`` approximating the fraction of scenarios
    with value ``<= self.at``.
    """

    at: float = 0.0
    relative_accuracy: float = 1e-4

    def create_accumulator(self) -> SignedSketch:
        return SignedSketch(relative_accuracy=self.relative_accuracy)

    def add_input(self, state: SignedSketch, value: float) -> SignedSketch:
        state.add(float(value))
        return state

    def merge_accumulators(
        self,
        a: SignedSketch,
        b: SignedSketch,
    ) -> SignedSketch:
        return SignedSketch.merge(a, b)

    def extract_output(self, state: SignedSketch) -> float:
        if state.n == 0:
            return float("nan")
        # Binary-search through quantiles to find rank of self.at.
        # ~40 iters -> 1e-12 q-precision; bounded.
        lo, hi = 0.0, 1.0
        for _ in range(_QUANTILE_RANK_BISECT_ITERS):
            mid = (lo + hi) / 2.0
            q = state.quantile(mid)
            if q < self.at:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "QuantileRank",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
            "at": self.at,
            "relative_accuracy": self.relative_accuracy,
        }


__all__ = [
    "CTE",
    "_AGGREGATOR_REGISTRY",
    "ArgMax",
    "ArgMin",
    "BaseAggregator",
    "Count",
    "Max",
    "Mean",
    "Median",
    "Min",
    "Quantile",
    "QuantileRank",
    "Std",
    "Sum",
    "Variance",
    "register_aggregator",
    "scenario_aggregator",
]
