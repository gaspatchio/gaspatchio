# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Per-period (vector) aggregators sharing the Aggregator Protocol.
# ABOUTME: batch_reduce(frame, period) -> length-n_periods vector; merges pad-and-add.

"""Per-period vector aggregators.

These are first-class aggregators (same ``create/add/merge/extract`` Protocol as
``Sum``/``Mean``) with vector-valued state. The one new seam, ``batch_reduce``,
reduces a batch frame to a per-period vector via ``explode -> group_by(period)``;
it is axis-agnostic, so the same aggregator works over policy batches
(``run_aggregated``) and scenario batches (``for_each_scenario``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl

from gaspatchio_core.scenarios._aggregators import _BaseAggregator, scenario_aggregator

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray


def _pad_add(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Element-wise add two vectors of possibly-unequal length (zero-pad shorter)."""
    n = max(a.shape[0], b.shape[0])
    out = np.zeros(n, dtype=np.float64)
    out[: a.shape[0]] += a
    out[: b.shape[0]] += b
    return out


def _pad_combine(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    op: Callable[[NDArray[np.float64], NDArray[np.float64]], NDArray[np.float64]],
    fill: float,
) -> NDArray[np.float64]:
    """Element-wise combine via ``op`` (np.minimum/np.maximum); ``fill`` pads the gap.

    A period present in only one operand keeps that operand's value (the other side
    is the identity ``fill``: +inf for min, -inf for max).
    """
    n = max(a.shape[0], b.shape[0])
    ap = np.full(n, fill, dtype=np.float64)
    bp = np.full(n, fill, dtype=np.float64)
    ap[: a.shape[0]] = a
    bp[: b.shape[0]] = b
    return op(ap, bp)


def _reduce_by_period(
    frame: pl.DataFrame, period: str, column: str, *aggs: pl.Expr
) -> pl.DataFrame:
    """Explode the ``(period, column)`` lists and reduce per period, sorted by period.

    An empty ``[]`` projection explodes to a single ``(null, null)`` row, which would
    sort FIRST and insert a phantom leading bucket that shifts every period by one.
    Dropping null periods removes that phantom; the period index is built from
    ``int_ranges(list.len())`` so it is never null for real data.
    """
    return (
        frame.lazy()
        .select(pl.col(period), pl.col(column))
        .explode([period, column])
        .filter(pl.col(period).is_not_null())
        .group_by(period)
        .agg(*aggs)
        .sort(period)
        .collect()
    )


def _reduce_by_period_over(
    frame: pl.DataFrame,
    period: str,
    column: str,
    by: tuple[str, ...],
    *aggs: pl.Expr,
) -> dict[tuple[Any, ...], pl.DataFrame]:
    """Partitioned per-period reduce — returns ``{partition_tuple: per-period frame}``.

    Like :func:`_reduce_by_period` but the partition column(s) ``by`` join the group key
    (``group_by([*by, period])``). The ``by`` columns are scalar-per-policy, so they
    ride the existing explode. Returns the reduced rows partitioned by ``by`` (key
    columns dropped), each sub-frame sorted by ``period`` — ready to feed
    ``_Partitioned``.
    """
    reduced = (
        frame.lazy()
        .select(*[pl.col(b) for b in by], pl.col(period), pl.col(column))
        .explode([period, column])
        .filter(pl.col(period).is_not_null())
        .group_by([*by, period])
        .agg(*aggs)
        .sort([*by, period])
        .collect()
    )
    return reduced.partition_by(*by, as_dict=True, include_key=False)


def _tidy_partitioned_vector(
    df: pl.DataFrame, *, by: tuple[str, ...], alias: str
) -> pl.DataFrame:
    """Explode a ``{by..., alias:<vector>}`` frame to tidy ``{by..., period, alias}``.

    A vector `.over()` output has one row per partition where the ``alias`` column
    holds a per-period array (numpy ndarray / Python list). This helper casts that
    cell value to ``List(Float64)``, annotates each element with its period index,
    then explodes to one row per (partition, period). Shared by both drivers'
    finalise (run_aggregated and for_each_scenario).
    """
    return (
        df.with_columns(pl.col(alias).cast(pl.List(pl.Float64)))
        .with_columns(pl.int_ranges(pl.col(alias).list.len()).alias("period"))
        .explode([alias, "period"])
        .select([*by, "period", alias])
    )


@dataclass(frozen=True)
class VectorAggregator(_BaseAggregator):
    """Aggregator with per-period vector state.

    Shares the Protocol; the driver dispatches on the presence of ``batch_reduce``.
    ``within_expr`` is intentionally unsupported (the vector path never calls it).

    Subclasses implement two seams:
    - ``_period_aggs()``: the Polars aggregation expressions used in the group_by step.
    - ``_assemble_partial(reduced)``: converts the period-sorted reduced frame into the
      partial value (e.g., numpy array or tuple of arrays).

    Both ``batch_reduce`` and ``batch_reduce_over`` are composed from these two seams.
    """

    def _period_aggs(self) -> list[pl.Expr]:
        """Per-period aggregation expression(s) for this aggregator. Override."""
        raise NotImplementedError

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        """Turn a period-sorted reduced frame into this aggregator's partial.

        Override in subclasses.
        """
        raise NotImplementedError

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        return self._assemble_partial(
            _reduce_by_period(frame, period, self.column, *self._period_aggs())
        )

    def batch_reduce_over(
        self, frame: pl.DataFrame, period: str, by: tuple[str, ...]
    ) -> dict[tuple[Any, ...], Any]:
        """Partitioned reduce: ``{partition_tuple: partial}`` (one group_by pass)."""
        parts = _reduce_by_period_over(
            frame, period, self.column, by, *self._period_aggs()
        )
        return {key: self._assemble_partial(sub) for key, sub in parts.items()}

    def within_expr(self) -> pl.Expr:
        """Not supported — vector aggregators reduce via batch_reduce()."""
        msg = "VectorAggregator reduces via batch_reduce(), not within_expr()."
        raise NotImplementedError(msg)


@scenario_aggregator("PeriodSum")
@dataclass(frozen=True)
class PeriodSum(VectorAggregator):
    """Per-period portfolio total: sum across the batched axis at each period index."""

    def _period_aggs(self) -> list[pl.Expr]:
        return [pl.col(self.column).sum()]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return reduced[self.column].to_numpy().astype(np.float64)

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return np.zeros(0, dtype=np.float64)

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _pad_add(state, np.asarray(value, dtype=np.float64))

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _pad_add(a, b)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return state

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodSum", "column": self.column}


@scenario_aggregator("PeriodCount")
@dataclass(frozen=True)
class PeriodCount(VectorAggregator):
    """Per-period count of contributing (non-null) values across the batched axis."""

    def _period_aggs(self) -> list[pl.Expr]:
        return [pl.col(self.column).count()]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return reduced[self.column].to_numpy().astype(np.float64)

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return np.zeros(0, dtype=np.float64)

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _pad_add(state, np.asarray(value, dtype=np.float64))

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _pad_add(a, b)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return state

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodCount", "column": self.column}


@dataclass(frozen=True)
class _PeriodExtremum(VectorAggregator):
    """Shared min/max logic.

    Subclasses override ``_reduce_expr``, ``_fill``, and ``_combine``.
    """

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return np.zeros(0, dtype=np.float64)

    def _reduce_expr(self, col: str) -> pl.Expr:
        """Return the Polars aggregation expression for this extremum type."""
        raise NotImplementedError

    @property
    def _fill(self) -> float:
        """Identity fill value for padding: +inf for min, -inf for max."""
        raise NotImplementedError

    def _combine(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        """Pad-combine two accumulators using the appropriate extremum operation."""
        raise NotImplementedError

    def _period_aggs(self) -> list[pl.Expr]:
        return [self._reduce_expr(self.column)]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return reduced[self.column].to_numpy().astype(np.float64)

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return self._combine(state, np.asarray(value, dtype=np.float64))

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return self._combine(a, b)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return state


@scenario_aggregator("PeriodMin")
@dataclass(frozen=True)
class PeriodMin(_PeriodExtremum):
    """Per-period minimum across the batched axis."""

    def _reduce_expr(self, col: str) -> pl.Expr:
        return pl.col(col).min()

    @property
    def _fill(self) -> float:
        return np.inf

    def _combine(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _pad_combine(a, b, np.minimum, np.inf)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodMin", "column": self.column}


@scenario_aggregator("PeriodMax")
@dataclass(frozen=True)
class PeriodMax(_PeriodExtremum):
    """Per-period maximum across the batched axis."""

    def _reduce_expr(self, col: str) -> pl.Expr:
        return pl.col(col).max()

    @property
    def _fill(self) -> float:
        return -np.inf

    def _combine(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _pad_combine(a, b, np.maximum, -np.inf)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodMax", "column": self.column}


@scenario_aggregator("PeriodMean")
@dataclass(frozen=True)
class PeriodMean(VectorAggregator):
    """Per-period mean across the batched axis.

    State is ``(sum_vec, count_vec)`` — both exactly additive — so the result is
    batch-size-invariant (no Welford needed; mean is extracted as sum/count).
    """

    def _period_aggs(self) -> list[pl.Expr]:
        return [
            pl.col(self.column).sum().alias("s"),
            pl.col(self.column).count().alias("c"),
        ]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return (
            reduced["s"].to_numpy().astype(np.float64),
            reduced["c"].to_numpy().astype(np.float64),
        )

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return (np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64))

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        s, c = state
        vs, vc = value
        return (_pad_add(s, vs), _pad_add(c, vc))

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return (_pad_add(a[0], b[0]), _pad_add(a[1], b[1]))

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        s, c = state
        out = np.full(s.shape[0], np.nan, dtype=np.float64)
        nonzero = c > 0
        out[nonzero] = s[nonzero] / c[nonzero]
        return out

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodMean", "column": self.column}


_MIN_SAMPLE_VAR: int = 2  # ddof=1 requires at least 2 observations per period


def _welford_merge_vec(a: Any, b: Any) -> Any:  # noqa: ANN401
    """Elementwise Welford-Chan merge of two ``(n, mean, m2)`` vector states.

    Padding with zeros is the identity: a period present in only one operand keeps
    that operand's moments (the other side has n=0).
    """
    (na, ma, m2a), (nb, mb, m2b) = a, b
    length = max(na.shape[0], nb.shape[0])

    def _fit(x: Any) -> Any:  # noqa: ANN401
        out = np.zeros(length, dtype=np.float64)
        out[: x.shape[0]] = x
        return out

    na, ma, m2a = _fit(na), _fit(ma), _fit(m2a)
    nb, mb, m2b = _fit(nb), _fit(mb), _fit(m2b)
    # A period with n==0 in one operand carries mean=NaN (Polars mean() of an empty
    # group). It contributes nothing, but NaN*0 = NaN would still poison `delta`, so
    # replace those means with the identity 0.0 before combining.
    ma = np.where(na > 0, ma, 0.0)
    mb = np.where(nb > 0, mb, 0.0)
    n = na + nb
    safe = n > 0
    delta = mb - ma
    ratio_b = np.divide(nb, n, out=np.zeros(length), where=safe)
    ratio_ab = np.divide(na * nb, n, out=np.zeros(length), where=safe)
    mean = ma + delta * ratio_b
    m2 = m2a + m2b + delta * delta * ratio_ab
    return (n, mean, m2)


@dataclass(frozen=True)
class _PeriodMoment(VectorAggregator):
    """Shared per-period ``(n, mean, m2)`` Welford state for Variance/Std."""

    def _period_aggs(self) -> list[pl.Expr]:
        return [
            pl.col(self.column).count().alias("n"),
            pl.col(self.column).mean().alias("mean"),
            (pl.col(self.column).var(ddof=0) * pl.col(self.column).count()).alias("m2"),
        ]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        # var(ddof=0) is null at count==1; nan_to_num -> 0.0 (correct: m2=0 for n=1).
        return (
            reduced["n"].to_numpy().astype(np.float64),
            reduced["mean"].to_numpy().astype(np.float64),
            np.nan_to_num(reduced["m2"].to_numpy().astype(np.float64)),
        )

    def create_accumulator(self) -> Any:  # noqa: ANN401
        z = np.zeros(0, dtype=np.float64)
        return (z, z.copy(), z.copy())

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _welford_merge_vec(state, value)

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _welford_merge_vec(a, b)


@scenario_aggregator("PeriodVariance")
@dataclass(frozen=True)
class PeriodVariance(_PeriodMoment):
    """Per-period sample variance (ddof=1) across the batched axis."""

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        n, _mean, m2 = state
        out = np.full(n.shape[0], np.nan, dtype=np.float64)
        ok = n >= _MIN_SAMPLE_VAR
        out[ok] = m2[ok] / (n[ok] - 1)
        return out

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodVariance", "column": self.column}


@scenario_aggregator("PeriodStd")
@dataclass(frozen=True)
class PeriodStd(_PeriodMoment):
    """Per-period sample standard deviation across the batched axis."""

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        n, _mean, m2 = state
        out = np.full(n.shape[0], np.nan, dtype=np.float64)
        ok = n >= _MIN_SAMPLE_VAR
        out[ok] = np.sqrt(m2[ok] / (n[ok] - 1))
        return out

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodStd", "column": self.column}


__all__ = [
    "PeriodCount",
    "PeriodMax",
    "PeriodMean",
    "PeriodMin",
    "PeriodStd",
    "PeriodSum",
    "PeriodVariance",
    "VectorAggregator",
    "_pad_add",
    "_pad_combine",
]
