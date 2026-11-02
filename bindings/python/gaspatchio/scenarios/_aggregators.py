# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: The scenario aggregator primitives, implementing the Aggregator Protocol.
# ABOUTME: Each aggregator is partition-blind; partitioning is added via .over().

"""The scenario aggregator primitives: Sum, Count, Min, Max and the rest.

Each aggregator implements the Aggregator Protocol from _metric.py:
    within_expr, create_accumulator, add_input, merge_accumulators,
    extract_output, canonical_form.

Aggregators are partition-blind. To partition, call ``.over(by)`` which
returns a ``_Partitioned`` wrapper that holds the
``dict[partition_key, acc]`` state.

**A null is a missing value, and it never becomes a number.** Every
aggregator skips a null where it reads one -- in the within-scenario
reduction and in the fold across scenarios or policies alike, as Polars'
``mean``, ``min`` and ``max`` skip one -- and an aggregator that saw nothing
but nulls answers null (``None``). ``Count`` counts the values it saw, so it
answers ``0``. The within ``sum`` departs from Polars here on purpose: Polars
sums nothing to ``0.0``, and an IRR that does not exist (Excel's ``#NUM!``)
folded to ``0.0`` is a plausible rate nobody computed. A NaN is different: it
is a value the model computed and could not determine, and it propagates (see
:class:`Min`).
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

import polars as pl

from gaspatchio._dtypes import I64_MAX, I64_MIN
from gaspatchio.errors.formatting_errors import integer_total_refusal
from gaspatchio.scenarios._metric import Aggregator, _Partitioned
from gaspatchio.scenarios._sketch import SignedSketch

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


def _sum_or_null(column: str, *, whole: bool = False) -> pl.Expr:
    """Sum ``column``'s non-null values, or null where it holds none.

    Polars sums an all-null group to ``0.0``. A scenario whose every value is
    missing has no total, and a ``0.0`` there is read downstream as a real one.

    ``whole`` sums an integer column in ``Int128``, so a group's total is
    exact where its own width would wrap one past ``i64``.
    """
    values = pl.col(column).cast(pl.Int128) if whole else pl.col(column)
    return pl.when(pl.col(column).count() > 0).then(values.sum())


def _total_and_count(column: str) -> pl.Expr:
    """Return a group's exact total of an integer ``column`` beside its count.

    Polars' ``mean`` of an integer column turns each value into a double
    before adding them, so 2**63 - 1, -2**63 and 5 averaged to 5/3 where the
    exact mean is 4/3. The total is taken in ``Int128``, where no ``i64``
    values can wrap it, and :func:`exact_mean` divides it by the count once.
    """
    return pl.struct(
        _sum_or_null(column, whole=True).alias("total"),
        pl.col(column).count().alias("count"),
    )


def exact_mean(parts: dict[str, Any] | None) -> float | None:
    """Return the double nearest a group's exact total over its count.

    Python divides one ``int`` by another correctly rounded, so the answer is
    the double nearest the exact mean, rounded once. A group that counted
    nothing has no mean.
    """
    if parts is None or parts["total"] is None or not parts["count"]:
        return None
    return int(parts["total"]) / int(parts["count"])


_WITHIN_TABLE: dict[str, Callable[[str], pl.Expr]] = {
    "sum": _sum_or_null,
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
        inst = cls(column="__check__")
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


def scenario_aggregator[T](name: str) -> Callable[[type[T]], type[T]]:
    """Register a class as an aggregator under ``name``.

    Usage: ``@scenario_aggregator("Sum")`` above the class.

    Cross-join note: every scenario sees every policy via cross-join. The
    within-reduction (``within_expr()``) runs over the full per-scenario
    projection; ``add_input`` receives one value per scenario, not one per row.
    """

    # Typed as returning the class it was given, which is what it does: a
    # checker that reads the decorated class sees ``Sum``, not a bare ``type``.
    def decorator(cls: type[T]) -> type[T]:
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

    if TYPE_CHECKING:
        # The rest of the Aggregator protocol. Concrete subclasses supply these
        # five; declaring them here lets a value typed as the base (what
        # ``.alias()`` and ``.of()`` return) pass where an Aggregator is wanted,
        # as every constructed aggregator does at runtime.
        def create_accumulator(self) -> Any: ...  # noqa: ANN401
        def add_input(self, state: Any, value: Any) -> Any: ...  # noqa: ANN401
        def merge_accumulators(self, a: Any, b: Any) -> Any: ...  # noqa: ANN401
        def extract_output(self, state: Any) -> Any: ...  # noqa: ANN401
        def canonical_form(self) -> dict[str, Any]: ...

    def within_expr(self) -> pl.Expr:
        if self.within_expr_override is not None:
            return self.within_expr_override
        return _within_to_expr(self.column, self.within)

    def add_batch(self, state: Any, values: pl.Series) -> Any:  # noqa: ANN401
        """Fold an entire batch of per-policy values into ``state`` at once.

        Optional vectorisation hook used by the policy-axis driver
        (``run_aggregated``). The default folds each non-null value with
        ``add_input``; concrete aggregators that can reduce a whole Series in a
        single pass (Sum, Min, Max, Mean, Variance, Std) override this. Nulls
        are skipped, matching the null-dropping semantics of the ``within_expr``
        reductions this replaced; an accumulator that has folded only nulls
        is still empty, and extracts to null.
        """
        agg = cast("Aggregator", self)
        for value in values.drop_nulls():
            state = agg.add_input(state, value)
        return state

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
"""Base class for writing your own scenario aggregator.

Subclass it as a frozen dataclass, register the subclass under a name with
``@scenario_aggregator("Name")``, and supply ``create_accumulator``,
``add_input``, ``merge_accumulators``, ``extract_output`` and
``canonical_form``. The subclass inherits ``.alias(name)``, ``.over(by)``,
``.of(expr)`` and the named ``within`` reduction, so it can be used anywhere
``Sum`` or ``CTE`` can.
"""

# ---- Sum ----


def _a_whole_number(value: object) -> bool:
    """Say whether a value folded into a ``Sum`` is a whole number, not a flag."""
    return isinstance(value, numbers.Integral) and not isinstance(value, bool)


def _exact(state: tuple[float, float] | None) -> bool:
    """Say whether a ``Sum`` state is empty or an exact whole-number total.

    The exact form is a pair of Python ints, the compensation always nought;
    a decimal anywhere in the fold makes it the compensated pair of doubles.
    """
    return state is None or all(type(part) is int for part in state)


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

    Nulls are skipped. A sum that saw nothing but nulls is null, not ``0.0``:
    the state is ``None`` until a value arrives, so "no value" and "a total
    of zero" stay apart. A null a NaN became upstream is skipped like any
    other -- a NaN ``cut`` placed in no band, a test a NaN left without a
    truth value stored as a flag (spec 11.1.4, 11.1.26) -- so the total does
    not show it; a NaN that reaches the fold as a NaN makes it NaN.

    **Whole numbers are totalled exactly.** An integer column's batch is
    summed in ``Int128`` and the state carries the exact total, so the answer
    is the same at every ``batch_size`` and on both axes. Summed in the
    column's own width, a total past ``i64`` wrapped -- 2**62, 2**62 and 5
    answered 9.2e18 one policy at a time and -9.2e18 two at a time -- so a
    total outside ``[-2**63, 2**63 - 1]`` is refused by name when it is read
    out, and one inside it answers the double nearest the exact total.
    """

    def create_accumulator(self) -> tuple[float, float] | None:
        return None

    def add_input(
        self,
        state: tuple[float, float] | None,
        value: float | None,
    ) -> tuple[float, float] | None:
        if value is None:
            return state
        if _a_whole_number(value) and _exact(state):
            whole = int(value)
            return (whole, 0) if state is None else (state[0] + whole, 0)
        if state is None:
            return (float(value), 0.0)
        s, c = state
        x = float(value)
        t = s + x
        # Neumaier: pick the |larger|-magnitude side as the "stable" addend.
        c = c + ((s - t) + x) if abs(s) >= abs(x) else c + ((x - t) + s)
        return (t, c)

    def merge_accumulators(
        self,
        a: tuple[float, float] | None,
        b: tuple[float, float] | None,
    ) -> tuple[float, float] | None:
        if a is None:
            return b
        if b is None:
            return a
        sa, ca = a
        sb, cb = b
        t = sa + sb
        merge_c = ((sa - t) + sb) if abs(sa) >= abs(sb) else ((sb - t) + sa)
        return (t, ca + cb + merge_c)

    def add_batch(
        self,
        state: tuple[float, float] | None,
        values: pl.Series,
    ) -> tuple[float, float] | None:
        non_null = values.drop_nulls()
        if non_null.len() == 0:
            return state
        if non_null.dtype.is_integer():
            # Int128 holds any batch's total of i64s exactly; the column's
            # own width wraps one past i64.
            whole = int(cast("int", non_null.cast(pl.Int128).sum()))
            return self.merge_accumulators(state, (whole, 0))
        return self.merge_accumulators(
            state, (float(cast("float", non_null.sum())), 0.0)
        )

    def extract_output(self, state: tuple[float, float] | None) -> float | None:
        if state is None:
            return None
        s, c = state
        if _exact(state) and not I64_MIN <= s + c <= I64_MAX:
            raise ValueError(integer_total_refusal(self.column, int(s + c)))
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
    """Count of scenarios that contributed a value.

    A null is not a value: a scenario whose within-reduction is null (every
    policy's value missing) is not counted, so a partition that saw only
    nulls counts ``0``. A NaN is a value the model computed, and is counted.
    """

    def create_accumulator(self) -> int:
        return 0

    def add_input(self, state: int, value: Any) -> int:  # noqa: ANN401
        if value is None:
            return state
        return state + 1

    def merge_accumulators(self, a: int, b: int) -> int:
        return a + b

    def extract_output(self, state: int) -> int:
        return int(state)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Count", "column": self.column}


# ---- Min / Max NaN handling ----


def _is_nan(value: Any) -> bool:  # noqa: ANN401
    """Return True where ``value`` is a NaN -- the one value unequal to itself.

    Written as the inequality rather than ``math.isnan`` because an extremum
    fold is not promised a float: a ``within="first"`` reduction over a text
    or date column hands this something ``math.isnan`` would raise on, where
    the comparison simply answers False.
    """
    return bool(value != value)  # noqa: PLR0124


def _series_holds_a_nan(values: pl.Series) -> bool:
    """Return True where a null-free series holds a NaN.

    Whether a value is NaN is a float question; a column of any other type
    holds none by construction, and asking it that way is what keeps an
    extremum over a text or date column working.
    """
    if not values.dtype.is_float():
        return False
    return bool(values.is_nan().any())


def _min_or_nan(a: float, b: float) -> float:
    """Return the smaller of ``a`` and ``b``, or NaN where either is one.

    Python's ``min`` answers whichever side it was handed first when the
    comparison comes back False, so a NaN survives or is dropped depending on
    the order the two arrived in. A fold whose answer depends on how the run
    was batched is not an answer, so a NaN is tested for by name.
    """
    if _is_nan(a) or _is_nan(b):
        return float("nan")
    return min(a, b)


def _max_or_nan(a: float, b: float) -> float:
    """Return the larger of ``a`` and ``b``, or NaN where either is one."""
    if _is_nan(a) or _is_nan(b):
        return float("nan")
    return max(a, b)


# ---- Min ----


@scenario_aggregator("Min")
@dataclass(frozen=True)
class Min(_BaseAggregator):
    """Min across scenarios.

    A NaN anywhere in the column makes the answer NaN. Polars' own ``min``
    passes over one and so does Python's, which would report the smallest
    *known* value as though it were the smallest value -- and the scenario
    carrying the NaN is, in capital work, usually the stressed one.

    A null is different: it is a missing value, and it is skipped. A min that
    saw nothing but nulls is null.
    """

    def create_accumulator(self) -> float | None:
        return None

    def add_input(self, state: float | None, value: float | None) -> float | None:
        if value is None:
            return state
        if state is None:
            return value
        return _min_or_nan(state, value)

    def merge_accumulators(self, a: float | None, b: float | None) -> float | None:
        if a is None:
            return b
        if b is None:
            return a
        return _min_or_nan(a, b)

    def add_batch(self, state: float | None, values: pl.Series) -> float | None:
        non_null = values.drop_nulls()
        if non_null.len() == 0:
            return state
        if _series_holds_a_nan(non_null):
            return float("nan")
        return self.merge_accumulators(state, float(cast("float", non_null.min())))

    def extract_output(self, state: float | None) -> float | None:
        return None if state is None else float(state)

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
    """Max across scenarios.

    A NaN anywhere in the column makes the answer NaN, for the reasons given
    on :class:`Min`. A null is skipped, and a max that saw nothing but nulls
    is null.
    """

    def create_accumulator(self) -> float | None:
        return None

    def add_input(self, state: float | None, value: float | None) -> float | None:
        if value is None:
            return state
        if state is None:
            return value
        return _max_or_nan(state, value)

    def merge_accumulators(self, a: float | None, b: float | None) -> float | None:
        if a is None:
            return b
        if b is None:
            return a
        return _max_or_nan(a, b)

    def add_batch(self, state: float | None, values: pl.Series) -> float | None:
        non_null = values.drop_nulls()
        if non_null.len() == 0:
            return state
        if _series_holds_a_nan(non_null):
            return float("nan")
        return self.merge_accumulators(state, float(cast("float", non_null.max())))

    def extract_output(self, state: float | None) -> float | None:
        return None if state is None else float(state)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Max",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- ArgMin / ArgMax ----


class _ArgExtremumFold:
    """The fold ArgMax and ArgMin share: a ``(scenario_id, value)`` best-so-far.

    A plain mixin, not a dataclass: it adds behaviour and no fields. A scenario
    whose value is null is skipped -- it has no value to rank -- so a fold that
    saw only nulls holds ``None`` and extracts to null. On equal values the
    smaller scenario_id wins. Each kind says which value beats the best so far.
    """

    def _beats(self, value: float, best: float) -> bool:
        raise NotImplementedError

    def create_accumulator(self) -> tuple[Any, float] | None:
        return None

    def add_input(
        self,
        state: tuple[Any, float] | None,
        value: tuple[Any, float | None],
    ) -> tuple[Any, float] | None:
        sid, v = value
        if v is None:
            return state
        if state is None:
            return (sid, v)
        best_sid, best_v = state
        if self._beats(v, best_v) or (v == best_v and sid < best_sid):
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


@scenario_aggregator("ArgMax")
@dataclass(frozen=True)
class ArgMax(_ArgExtremumFold, _BaseAggregator):
    """Scenario_id of the scenario with the maximum value.

    add_input receives a (scenario_id, value) tuple. Lexicographic
    tiebreak: on equal values, the smaller scenario_id wins. A scenario whose
    value is null is skipped -- it has no value to be the largest -- and an
    ArgMax that saw only nulls is null.
    """

    requires_scenario_id: ClassVar[bool] = True

    def _beats(self, value: float, best: float) -> bool:
        return value > best

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "ArgMax",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


@scenario_aggregator("ArgMin")
@dataclass(frozen=True)
class ArgMin(_ArgExtremumFold, _BaseAggregator):
    """Scenario_id of the scenario with the minimum value. Lex tiebreak.

    A scenario whose value is null is skipped, and an ArgMin that saw only
    nulls is null.
    """

    requires_scenario_id: ClassVar[bool] = True

    def _beats(self, value: float, best: float) -> bool:
        return value < best

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "ArgMin",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- Welford / Chan helpers ----

# Sample variance (ddof=1) requires at least this many observations.
_MIN_N_FOR_SAMPLE_VARIANCE = 2

# A whole number is cut into its high and low 32 bits to total its square.
_LOW_BITS = 32


def _welford_create() -> dict[str, float]:
    return {"n": 0, "mean": 0.0, "m2": 0.0}


def _welford_add(state: dict[str, float], value: float | None) -> dict[str, float]:
    if value is None:
        return state
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


def _welford_from_series(values: pl.Series) -> dict[str, float]:
    """Build a Welford accumulator from a whole Series in two vectorised passes.

    The two-pass (mean, then summed squared deviations) form is at least as
    accurate as streaming ``_welford_add`` and combines with ``_welford_merge``
    to give a result independent of how the observations were split into
    batches. Nulls are dropped to match ``pl.col(c).mean()`` semantics.
    """
    non_null = values.drop_nulls()
    n = non_null.len()
    if n == 0:
        return _welford_create()
    mean = float(cast("float", non_null.mean()))
    m2 = float(cast("float", (non_null - mean).pow(2).sum()))
    return {"n": n, "mean": mean, "m2": m2}


def _whole_moment_sums(column: str) -> list[pl.Expr]:
    """Return the exact totals a whole-number column's moments are read from.

    ``n`` counts the values and ``s1`` totals them in ``Int128``. A value
    ``x = h * 2**32 + l`` squares to ``h*h * 2**64 + h*l * 2**33 + l*l``, so
    ``hh``, ``hl`` and ``ll`` total those three products, each of which an
    ``Int128`` sums over any batch without wrapping; the square of one
    ``i64`` fits ``Int128``, but the total of two need not.
    """
    value = pl.col(column).cast(pl.Int128)
    high = value // (1 << _LOW_BITS)
    low = value - high * (1 << _LOW_BITS)
    return [
        value.count().alias("n"),
        value.sum().alias("s1"),
        (high * high).sum().alias("hh"),
        (high * low).sum().alias("hl"),
        (low * low).sum().alias("ll"),
    ]


def total_of_squares(hh: object, hl: object, ll: object) -> int:
    """Join the product totals of :func:`_whole_moment_sums` into one exact total."""
    return (
        (int(cast("int", hh)) << (2 * _LOW_BITS))
        + (int(cast("int", hl)) << (_LOW_BITS + 1))
        + int(cast("int", ll))
    )


def nearest_root(numerator: int, denominator: int) -> float:
    """Return the double nearest the square root of ``numerator / denominator``.

    Rounded once, from the exact ratio: the ratio is scaled by an even power
    of two until its integer root holds at least 55 bits, and a last bit
    records whether anything lay below that root, so converting it to a
    double rounds as the exact root would.
    """
    if numerator == 0:
        return 0.0
    shift = max(0, 110 - numerator.bit_length() + denominator.bit_length())
    shift += shift % 2
    scaled = (numerator << shift) // denominator
    root = math.isqrt(scaled)
    below = root * root != scaled or scaled * denominator != numerator << shift
    return math.ldexp(float(2 * root + below), -(shift // 2) - 1)


def _exact_moments(state: dict[str, Any]) -> bool:
    """Say whether a moment state carries exact whole-number totals."""
    return "s1" in state


def _moments_of_whole_numbers(values: pl.Series) -> dict[str, Any]:
    """Return the exact ``(n, s1, s2)`` of a null-free integer Series."""
    row = values.to_frame("v").select(_whole_moment_sums("v")).row(0, named=True)
    return {
        "n": int(row["n"]),
        "s1": int(row["s1"]),
        "s2": total_of_squares(row["hh"], row["hl"], row["ll"]),
    }


def _as_welford(state: dict[str, Any]) -> dict[str, Any]:
    """Return a moment state as Welford's doubles, read once from exact totals."""
    if not _exact_moments(state) or state["n"] == 0:
        return state
    n, s1, s2 = state["n"], state["s1"], state["s2"]
    return {"n": n, "mean": s1 / n, "m2": (n * s2 - s1 * s1) / n}


class _MomentFold:
    """The moment fold Mean, Variance and Std share.

    A plain mixin, not a dataclass: it adds behaviour and no fields. A null is
    skipped on the way in, so ``n`` counts values; each kind reads its answer
    off the state, and every one of them answers null at ``n == 0``.

    **Whole numbers are folded exactly.** While every value folded is a whole
    number the state is ``(n, s1, s2)``: the count, the total and the total
    of squares as Python ints, so the answer is the same at every
    ``batch_size`` and is read once from the exact figures. Folded as doubles,
    2**53 + 1, 2**53 + 2, 2**53 + 3 and 2**53 + 5 -- variance 2.9166... --
    answered 5.22 one policy a batch, 6.67 two and 3.67 three. A decimal
    anywhere in the fold turns the state into Welford's ``(n, mean, m2)``
    doubles, as before.
    """

    def create_accumulator(self) -> dict[str, Any]:
        return _welford_create()

    def add_input(
        self,
        state: dict[str, Any],
        value: float | None,
    ) -> dict[str, Any]:
        if value is None:
            return state
        if _a_whole_number(value) and (state["n"] == 0 or _exact_moments(state)):
            whole = int(value)
            if not _exact_moments(state):
                return {"n": 1, "s1": whole, "s2": whole * whole}
            return {
                "n": state["n"] + 1,
                "s1": state["s1"] + whole,
                "s2": state["s2"] + whole * whole,
            }
        return _welford_add(_as_welford(state), value)

    def merge_accumulators(
        self,
        a: dict[str, Any],
        b: dict[str, Any],
    ) -> dict[str, Any]:
        if a["n"] == 0:
            return dict(b)
        if b["n"] == 0:
            return dict(a)
        if _exact_moments(a) and _exact_moments(b):
            return {key: a[key] + b[key] for key in ("n", "s1", "s2")}
        return _welford_merge(_as_welford(a), _as_welford(b))

    def add_batch(
        self,
        state: dict[str, Any],
        values: pl.Series,
    ) -> dict[str, Any]:
        non_null = values.drop_nulls()
        if non_null.len() and non_null.dtype.is_integer():
            return self.merge_accumulators(state, _moments_of_whole_numbers(non_null))
        return self.merge_accumulators(state, _welford_from_series(values))


def _sample_spread(state: dict[str, Any], *, root: bool) -> float | None:
    """Return the sample variance, or its root; null with no value, NaN with one.

    From exact totals the variance is ``(n * s2 - s1**2) / (n * (n - 1))``,
    read as the double nearest it, and its root is rounded once from that
    exact ratio (:func:`nearest_root`).
    """
    n = state["n"]
    if n == 0:
        return None
    if n < _MIN_N_FOR_SAMPLE_VARIANCE:
        return float("nan")
    if _exact_moments(state):
        total = int(state["s1"])
        spread = int(n) * int(state["s2"]) - total * total
        ways = int(n) * (int(n) - 1)
        return nearest_root(spread, ways) if root else spread / ways
    variance = state["m2"] / (n - 1)
    return math.sqrt(variance) if root else float(variance)


# ---- Mean ----


@scenario_aggregator("Mean")
@dataclass(frozen=True)
class Mean(_MomentFold, _BaseAggregator):
    """Mean across scenarios.

    Nulls are skipped; a mean that saw nothing but nulls is null. A null a
    NaN became upstream (a NaN ``cut`` placed in no band, spec 11.1.4) is
    skipped like any other.
    """

    def extract_output(self, state: dict[str, Any]) -> float | None:
        if state["n"] == 0:
            return None
        if _exact_moments(state):
            return int(state["s1"]) / int(state["n"])
        return float(state["mean"])

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Mean",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- Variance ----


@scenario_aggregator("Variance")
@dataclass(frozen=True)
class Variance(_MomentFold, _BaseAggregator):
    """Sample variance across scenarios (ddof=1).

    Nulls are skipped. With no values the answer is null; with one value it
    is NaN, because a sample variance of one observation is undefined.
    """

    def extract_output(self, state: dict[str, Any]) -> float | None:
        return _sample_spread(state, root=False)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Variance",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- Std ----


@scenario_aggregator("Std")
@dataclass(frozen=True)
class Std(_MomentFold, _BaseAggregator):
    """Sample standard deviation across scenarios.

    Nulls are skipped. With no values the answer is null; with one value it
    is NaN, as for :class:`Variance`.
    """

    def extract_output(self, state: dict[str, Any]) -> float | None:
        return _sample_spread(state, root=True)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Std",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# ---- Sketch-backed aggregators (Quantile / Median / CTE / QuantileRank) ----

# Binary-search iterations for QuantileRank: 40 halvings ~ 1e-12 precision in q-space.
_QUANTILE_RANK_BISECT_ITERS = 40


class _SketchFold:
    """The DDSketch fold Quantile, Median, CTE and QuantileRank share.

    A plain mixin, not a dataclass: it adds behaviour and no fields, so each
    kind keeps its own ``relative_accuracy`` field where its constructor has
    always had it. A null is skipped on the way in and never sketched, so a
    sketch that saw only nulls is empty -- ``n == 0`` -- and each kind
    answers null there.
    """

    relative_accuracy: float

    def create_accumulator(self) -> SignedSketch:
        return SignedSketch(relative_accuracy=self.relative_accuracy)

    def add_input(self, state: SignedSketch, value: float | None) -> SignedSketch:
        if value is not None:
            state.add(float(value))
        return state

    def merge_accumulators(
        self,
        a: SignedSketch,
        b: SignedSketch,
    ) -> SignedSketch:
        return SignedSketch.merge(a, b)


def _refuse_a_tail_option(
    kind: str,
    *,
    levels: tuple[float, ...] = (),
    level: float | None = None,
    direction: str | None = None,
) -> None:
    """Refuse a quantile level, a tail level or a tail direction that reads as another.

    ``direction`` was compared with ``"upper"`` and anything else -- ``"Upper"``
    from a notebook, ``up`` from YAML -- averaged the lower tail, an SCR read
    off the wrong end of the distribution. A quantile level outside [0, 1]
    extrapolated past the observed values (``Quantile(-0.2)``) or clipped to
    the largest (``Quantile(99.5)``, a percent for a probability), and a CTE
    level outside (0, 1] still answered. Each is refused here, naming it.

    Raises:
        ValueError: ``direction`` is not ``"upper"`` or ``"lower"``, a quantile
            level is outside [0, 1], or a tail level is outside (0, 1].

    """
    if direction is not None and direction not in ("upper", "lower"):
        msg = (
            f'{kind}(direction={direction!r}): direction is "upper", the mean '
            'of the largest values (losses positive), or "lower", the mean of '
            "the smallest (profit positive), spelled exactly so; any other "
            "value would be read as one of them."
        )
        raise ValueError(msg)
    for one in levels:
        if (
            isinstance(one, bool)
            or not isinstance(one, (int, float))
            or not (0.0 <= one <= 1.0)
        ):
            msg = (
                f"{kind}(levels=...) holds {one!r}: a quantile level is a "
                "probability in [0, 1], so the 99.5th percentile is 0.995."
            )
            raise ValueError(msg)
    if level is not None and (
        isinstance(level, bool)
        or not isinstance(level, (int, float))
        or not (0.0 < level <= 1.0)
    ):
        msg = (
            f"{kind}(level={level!r}): a tail level is the probability in the "
            "tail, in (0, 1], so the 99.5% tail is level=0.005."
        )
        raise ValueError(msg)


# ---- Quantile ----


@scenario_aggregator("Quantile")
@dataclass(frozen=True)
class Quantile(_SketchFold, _BaseAggregator):
    """Quantile(s) across scenarios - DDSketch-backed mergeable.

    Nulls are skipped; a quantile that saw nothing but nulls is null at
    every level.
    """

    levels: tuple[float, ...] = (0.5,)
    relative_accuracy: float = 1e-4

    def __post_init__(self) -> None:
        super().__post_init__()
        _refuse_a_tail_option("Quantile", levels=tuple(self.levels))

    def extract_output(self, state: SignedSketch) -> dict[float, float | None]:
        if state.n == 0:
            return dict.fromkeys(self.levels)
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
class Median(_SketchFold, _BaseAggregator):
    """Median across scenarios - DDSketch-backed. Equivalent to Quantile(0.5).

    Nulls are skipped; a median that saw nothing but nulls is null.
    """

    relative_accuracy: float = 1e-4

    def extract_output(self, state: SignedSketch) -> float | None:
        return None if state.n == 0 else state.quantile(0.5)

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
class CTE(_SketchFold, _BaseAggregator):
    """Conditional Tail Expectation - DDSketch-backed mergeable.

    For Solvency II SCR (99.5% loss):
      - positive-is-loss convention:
        ``CTE(column, level=0.005, direction="upper")``
      - P&L convention (positive is profit):
        ``CTE(column, level=0.005, direction="lower")``

    ``direction="upper"`` averages values **above** the ``(1 - level)`` quantile.
    ``direction="lower"`` averages values **below** the ``level`` quantile.

    Nulls are skipped; a CTE that saw nothing but nulls is null.
    """

    level: float = 0.005
    direction: Literal["upper", "lower"] = "upper"
    relative_accuracy: float = 1e-4

    def __post_init__(self) -> None:
        super().__post_init__()
        _refuse_a_tail_option("CTE", level=self.level, direction=self.direction)

    def extract_output(self, state: SignedSketch) -> float | None:
        if state.n == 0:
            return None
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
class QuantileRank(_SketchFold, _BaseAggregator):
    """Empirical rank of a target value in the across-scenario distribution.

    Returns a value in ``[0, 1]`` approximating the fraction of scenarios
    with value ``<= self.at``, and NaN where the column held a NaN: nothing
    places an unknown value on either side of the target, so the fraction is
    unknown too. Nulls are skipped; a rank over nothing but nulls is null.
    """

    at: float = 0.0
    relative_accuracy: float = 1e-4

    def extract_output(self, state: SignedSketch) -> float | None:
        # A sketch that has seen a NaN answers NaN at every quantile, and the
        # bisection below reads that as "the probe is not below the target"
        # every time -- walking to a confident 0.0. Said outright instead.
        if state.n == 0:
            return None
        if state.nan_n:
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
