# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: DDSketch facade with paired pos/neg sub-sketches for signed values.
# ABOUTME: Provides bit-exact mergeable tail quantile + CTE primitives.

"""DDSketch wrapper for signed-value quantile/CTE aggregators.

DDSketch's relative-error semantics assume strictly positive values. We
hold paired sketches (one for positives, one for absolute negatives) plus
a zero-counter, and route queries / merges accordingly.

The underlying sketch is :class:`DDSketch` (non-collapsing ``DenseStore``).
Default ``relative_accuracy`` is ``1e-4``; this is exposed on the
constructor so aggregator callers (CTE/Quantile/Median/QuantileRank) can
trade memory against tail precision. Empirically (see
``tests/scratch/gsp101_t3_fix/measure.py``):

* ``rel_acc=1e-4`` on 100 k lognormal observations across 6 decades
  produces ~1.2 MB per (un-signed) sketch with ~47 bp relative error
  on the 99.5% quantile.
* ``rel_acc=1e-3`` produces ~125 KB with ~46 bp error — i.e. the
  bucket-discretisation error swamps the relative-accuracy parameter
  for this regime; ``1e-3`` is the better default for memory-bound
  use cases.
* On a uniform ``1..1000`` distribution, the upper-tail CTE at
  ``level=0.005`` carries a ~10.5 bp relative error from
  bucket-centre interpolation; this is independent of ``n_probes``
  (refining the integration grid does not help) and consistent
  across both ``rel_acc=1e-4`` and ``rel_acc=1e-3``.

The collapsing variants (``LogCollapsingHighest`` /
``LogCollapsingLowest``) drop accuracy on the highest- or
lowest-magnitude observed values once the bin count exceeds
``bin_limit``. For tail-loss data we tested empirically: ``Highest``
collapses *exactly the bins the CTE reads from*, so 99.5% quantiles
collapse toward zero. ``Lowest`` would collapse the small-domain bins
needed for median tests on integer sequences ``1..10``. The
non-collapsing ``DDSketch`` is therefore the only variant that gives
deterministic, bit-exact merging across our actuarial workload.

Merge is integer bucket addition - no compactor randomness.

Quantile queries linearly interpolate between adjacent order-statistic
buckets. This makes ``q=0.5`` of the values ``1..10`` return ~5.5 rather
than the bucket centre of the 5th or 6th order statistic.

Serialisation uses :mod:`pickle` to preserve internal mapping state
bit-exactly; the protobuf format shipped with ``ddsketch`` rebuilds
mappings from ``(gamma, offset)`` which drifts by ~1 ULP on retrieved
quantile values.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from ddsketch import DDSketch
from ddsketch.ddsketch import (
    BaseDDSketch,  # noqa: TC002 - used in dataclass fields at runtime
)

DEFAULT_RELATIVE_ACCURACY: float = 1e-4
"""Project-default relative accuracy for new sketches.

This is the bucket-relative error guarantee on the underlying
``DDSketch``. See module docstring for empirical precision/memory
characterisation.
"""

_SKETCH_KIND = "DDSketch"  # non-collapsing DenseStore variant


def _new_sketch(relative_accuracy: float) -> BaseDDSketch:
    """Create a fresh DDSketch with the requested relative accuracy."""
    return DDSketch(relative_accuracy=relative_accuracy)


def _sketch_count(sketch: BaseDDSketch) -> int:
    """Return integer count from a sketch (count is stored as float internally)."""
    return int(sketch.count)


def _subsketch_value_at_rank(sketch: BaseDDSketch, rank: float) -> float:
    """Return the linearly-interpolated value at fractional ``rank`` (0-indexed).

    ``rank`` is clamped to ``[0, m - 1]`` where ``m`` is the sketch count.
    For integer ranks this returns the bucket-centre value of that order
    statistic; for fractional ranks it linearly interpolates between the
    bracketing order-statistic bucket centres.
    """
    m = _sketch_count(sketch)
    if m == 0:
        return float("nan")
    # ddsketch types get_quantile_value as float | None, but it only returns
    # None on an empty sketch -- the m == 0 guard above rules that out, so
    # the cast is sound for any non-empty sketch.
    if m == 1:
        return cast("float", sketch.get_quantile_value(0.0))
    rank = max(0.0, min(rank, m - 1))
    lo = int(rank)
    hi = min(lo + 1, m - 1)
    if hi == lo:
        return cast("float", sketch.get_quantile_value(lo / (m - 1)))
    v_lo = cast("float", sketch.get_quantile_value(lo / (m - 1)))
    v_hi = cast("float", sketch.get_quantile_value(hi / (m - 1)))
    weight = rank - lo
    return v_lo + (v_hi - v_lo) * weight


@dataclass
class SignedSketch:
    """Paired DDSketch wrapper handling negatives + zeros.

    Attributes:
        pos: DDSketch holding strictly positive values.
        neg: DDSketch holding the absolute value of strictly negative inputs.
        zero_n: Count of exact-zero observations.
        relative_accuracy: Bucket-relative-error parameter shared by both
            sub-sketches. See :data:`DEFAULT_RELATIVE_ACCURACY` and the
            module docstring for precision/memory characterisation.

    """

    pos: BaseDDSketch = field(default=None)  # type: ignore[assignment]
    neg: BaseDDSketch = field(default=None)  # type: ignore[assignment]
    zero_n: int = 0
    relative_accuracy: float = DEFAULT_RELATIVE_ACCURACY

    def __init__(
        self,
        *,
        relative_accuracy: float = DEFAULT_RELATIVE_ACCURACY,
        pos: BaseDDSketch | None = None,
        neg: BaseDDSketch | None = None,
        zero_n: int = 0,
    ) -> None:
        """Construct a paired sketch with the requested relative accuracy.

        ``pos``/``neg`` are accepted for internal use (deserialisation,
        :meth:`merge`); user code should leave them at their defaults.
        """
        self.relative_accuracy = relative_accuracy
        self.pos = pos if pos is not None else _new_sketch(relative_accuracy)
        self.neg = neg if neg is not None else _new_sketch(relative_accuracy)
        self.zero_n = zero_n

    def add(self, v: float) -> None:
        """Add a single observation, routing by sign."""
        if v > 0:
            self.pos.add(v)
        elif v < 0:
            self.neg.add(-v)
        else:
            self.zero_n += 1

    @property
    def n(self) -> int:
        """Total observation count across pos/neg/zero sub-sketches."""
        return _sketch_count(self.pos) + _sketch_count(self.neg) + self.zero_n

    @classmethod
    def merge(cls, a: SignedSketch, b: SignedSketch) -> SignedSketch:
        """Merge two sketches into a new sketch (bit-exact, commutative).

        Both operands must share the same ``relative_accuracy``; mixing is
        rejected because the underlying bucket boundaries differ.
        """
        if a.relative_accuracy != b.relative_accuracy:
            msg = (
                "Cannot merge SignedSketches with different relative_accuracy "
                f"({a.relative_accuracy} vs {b.relative_accuracy}); "
                "bucket boundaries differ."
            )
            raise ValueError(msg)
        out = cls(relative_accuracy=a.relative_accuracy)
        if _sketch_count(a.pos):
            out.pos.merge(a.pos)
        if _sketch_count(b.pos):
            out.pos.merge(b.pos)
        if _sketch_count(a.neg):
            out.neg.merge(a.neg)
        if _sketch_count(b.neg):
            out.neg.merge(b.neg)
        out.zero_n = a.zero_n + b.zero_n
        return out

    def quantile(self, q: float) -> float:
        """Return the linearly-interpolated ``q``-th quantile.

        Returns ``NaN`` if the sketch is empty.
        """
        total = self.n
        if total == 0:
            return float("nan")
        n_neg = _sketch_count(self.neg)
        n_zero = self.zero_n
        n_pos = _sketch_count(self.pos)
        if total == 1:
            return self._single_value(n_neg=n_neg, n_zero=n_zero)
        return self._interp_quantile(q=q, n_neg=n_neg, n_zero=n_zero, n_pos=n_pos)

    def _single_value(self, *, n_neg: int, n_zero: int) -> float:
        """Return the lone observation when ``n == 1``."""
        if n_neg == 1:
            return -_subsketch_value_at_rank(self.neg, 0)
        if n_zero == 1:
            return 0.0
        return _subsketch_value_at_rank(self.pos, 0)

    def _order_stat(self, r: int, *, n_neg: int, n_zero: int) -> float:
        """Value of the ``r``-th ascending order statistic over the full set.

        The ascending sequence is the negatives (most-negative first), then the zeros,
        then the positives; within each region the value is that sub-sketch's order
        statistic. Exposing integer order statistics this way lets the quantile
        interpolate ACROSS region boundaries (e.g. a rank between the last negative
        and the first zero) instead of clamping to a region edge.
        """
        if r < n_neg:
            # r-th smallest true negative == the (n_neg-1-r)-th ascending |neg| value.
            return -_subsketch_value_at_rank(self.neg, n_neg - 1 - r)
        if r < n_neg + n_zero:
            return 0.0
        return _subsketch_value_at_rank(self.pos, r - n_neg - n_zero)

    def _interp_quantile(
        self,
        *,
        q: float,
        n_neg: int,
        n_zero: int,
        n_pos: int,
    ) -> float:
        """Linearly-interpolated quantile for ``n >= 2`` (interpolates regions)."""
        total = n_neg + n_zero + n_pos
        rank = q * (total - 1)
        lo = max(0, min(int(rank), total - 1))
        hi = min(lo + 1, total - 1)
        v_lo = self._order_stat(lo, n_neg=n_neg, n_zero=n_zero)
        if hi == lo:
            return v_lo
        v_hi = self._order_stat(hi, n_neg=n_neg, n_zero=n_zero)
        return v_lo + (v_hi - v_lo) * (rank - lo)

    def cte(
        self,
        level: float,
        direction: Literal["upper", "lower"] = "upper",
    ) -> float:
        """Approximate Conditional Tail Expectation at ``level``.

        Args:
            level: Tail probability (e.g. ``0.005`` for the 99.5% tail).
            direction: ``"upper"`` for right-tail (large losses) or
                ``"lower"`` for left-tail.

        Returns:
            Mean of values in the tail, or NaN if the sketch is empty.

        """
        total = self.n
        if total == 0:
            return float("nan")
        n_probes = 10
        if direction == "upper":
            qs = [1.0 - level * (i + 0.5) / n_probes for i in range(n_probes)]
        else:
            qs = [level * (i + 0.5) / n_probes for i in range(n_probes)]
        samples = [self.quantile(q) for q in qs]
        return sum(samples) / len(samples)

    def canonical_form(self) -> dict[str, Any]:
        """Return a dict identifying this sketch's parameterisation.

        This is the audit-sidecar (T14) and YAML round-trip (T15/T16)
        representation. Two sketches with the same canonical form
        produce comparable buckets and are merge-compatible.
        """
        return {
            "sketch_kind": _SKETCH_KIND,
            "relative_accuracy": self.relative_accuracy,
        }

    def to_bytes(self) -> bytes:
        """Serialise to a bit-exact byte blob (pickle-based).

        Pickle is used in preference to the protobuf round-trip shipped
        with ``ddsketch`` because the protobuf path rebuilds the
        :class:`LogarithmicMapping` from ``(gamma, offset)`` and drifts
        by ~1 ULP on retrieved quantile values - which would break the
        bit-exact regulator-audit story.
        """
        return pickle.dumps(self, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def from_binned(
        cls,
        *,
        pos: list[tuple[float, int]],
        neg: list[tuple[float, int]],
        zero_n: int,
        relative_accuracy: float = DEFAULT_RELATIVE_ACCURACY,
    ) -> SignedSketch:
        """Build a sketch from histograms: ``(representative_value, count)`` per bin.

        Each ``representative_value`` must be a real observed value from its bin, so
        the underlying ddsketch ``add(value, weight=count)`` places the whole count in
        the correct bucket by the library's own mapping — no per-value loop.
        ``pos``/``neg`` carry **positive** representatives (``neg`` is the abs value).
        """
        out = cls(relative_accuracy=relative_accuracy)
        for value, count in pos:
            out.pos.add(float(value), float(count))
        for value, count in neg:
            out.neg.add(float(value), float(count))
        out.zero_n = int(zero_n)
        return out

    @classmethod
    def from_bytes(cls, blob: bytes) -> SignedSketch:
        """Inverse of :meth:`to_bytes`."""
        obj = pickle.loads(blob)  # noqa: S301 - pickle of our own type
        if not isinstance(obj, cls):
            msg = f"Deserialised object is not a {cls.__name__}: {type(obj).__name__}"
            raise TypeError(msg)
        return obj


__all__ = ["DEFAULT_RELATIVE_ACCURACY", "SignedSketch"]
