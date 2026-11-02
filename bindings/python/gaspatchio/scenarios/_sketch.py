# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: DDSketch facade with paired pos/neg sub-sketches for signed values.
# ABOUTME: Provides bit-exact mergeable tail quantile + CTE primitives.

"""DDSketch wrapper for signed-value quantile/CTE aggregators.

DDSketch's relative-error semantics assume strictly positive values. We
hold paired sketches (one for positives, one for absolute negatives) plus
a zero-counter, and route queries / merges accordingly. A NaN answers False
to both sign tests, so it is counted separately rather than falling into the
zero bucket, and any NaN at all takes the answer away from a quantile.

The underlying sketch is :class:`DDSketch` (non-collapsing ``DenseStore``).
Default ``relative_accuracy`` is ``1e-4``; this is exposed on the
constructor so aggregator callers (CTE/Quantile/Median/QuantileRank) can
trade memory against tail precision. Measured empirically:

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

import math
import pickle
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

from ddsketch import DDSketch
from ddsketch.ddsketch import (
    BaseDDSketch,  # noqa: TC002 - used in dataclass fields at runtime
)

if TYPE_CHECKING:
    from ddsketch.store import DenseStore

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


def _keys_at_ranks(store: DenseStore, ranks: list[float]) -> list[int]:
    """Resolve every rank in ascending ``ranks`` to its bucket key in one walk.

    The arithmetic is ``DenseStore.key_at_rank(rank)``'s: the key of the first
    bucket whose running count exceeds the rank, ``max_key`` if none does. The
    library walks once per rank, and the store holds every bucket between the
    smallest and largest magnitude seen (~11,500 per decade at the default
    accuracy), so walking once for all the ranks is the whole saving.
    """
    keys = [store.max_key] * len(ranks)
    running = 0.0
    i_rank = 0
    for i, bin_count in enumerate(store.bins):
        running += bin_count
        while i_rank < len(ranks) and running > ranks[i_rank]:
            keys[i_rank] = i + store.offset
            i_rank += 1
        if i_rank == len(ranks):
            break
    return keys


def _subsketch_values_at_ranks(
    sketch: BaseDDSketch,
    ranks: set[int],
) -> dict[int, float]:
    """Return the bucket-centre value of each integer order statistic in ``ranks``.

    Each value is what ``sketch.get_quantile_value(rank / (m - 1))`` returns --
    the same rank arithmetic, the same inner zero-count region -- but the store
    is walked once for all the ranks instead of once per call. ddsketch keeps
    the store, mapping and counts behind private names and offers no batched
    query, so this reads the fields ``get_quantile_value`` reads.

    Inside the zero-count region the library answers the int ``0``. The path
    this replaced handed the last rank on as given (a lone entry is its own
    last rank) and interpolated every rank below it, weight ``rank - lo``,
    after clamping its int ranks with ``max(0.0, min(rank, m - 1))`` -- so
    rank 0 carried the float weight ``0.0`` and every rank above it the int
    weight ``0``. Below the last rank it therefore coerced at rank 0 and
    wherever a bracketing answer came from the store, and returned the int at
    a rank above 0 whose bracketing answers were both the library's ``0``.
    Here every rank below the last is a float and the last is handed on as
    given. The ranks the two treat differently reach ``quantile()`` only
    through a float-weighted interpolation, so the public answer is the same
    object either way. Where a zero's type does reach the caller unmixed the
    two agree as well: a lone entry at every ``q``, and otherwise
    ``quantile(1.0)`` -- with any positives the positive sub-sketch's last
    rank as the library gave it, and on an all-negative sketch of two or more
    the negative sub-sketch's rank 0, coerced and negated: ``-0.0``, not ``0``.
    """
    if not ranks:
        return {}
    m = _sketch_count(sketch)
    if m == 0:
        return dict.fromkeys(ranks, float("nan"))
    # ddsketch types get_quantile_value as float | None, but it only returns
    # None on an empty sketch -- the m == 0 guard above rules that out, so
    # the casts are sound for any non-empty sketch.
    if m == 1:
        return dict.fromkeys(ranks, cast("float", sketch.get_quantile_value(0.0)))
    below_store = sketch._zero_count + sketch._negative_store.count  # noqa: SLF001
    values: dict[int, float] = {}
    targets: dict[int, float] = {}
    for r in ranks:
        clamped = max(0, min(r, m - 1))
        q = clamped / (m - 1)
        rank = q * (sketch.count - 1)
        if rank < below_store:
            value = cast("float", sketch.get_quantile_value(q))
            values[r] = float(value) if clamped < m - 1 else value
        else:
            targets[r] = rank - sketch._zero_count - sketch._negative_store.count  # noqa: SLF001
    if targets:
        wanted = sorted(set(targets.values()))
        keys = _keys_at_ranks(sketch._store, wanted)  # noqa: SLF001
        key_of = dict(zip(wanted, keys, strict=True))
        for r, target in targets.items():
            values[r] = sketch._mapping.value(key_of[target])  # noqa: SLF001
    return values


@dataclass
class SignedSketch:
    """Paired DDSketch wrapper handling negatives, zeros and NaNs.

    Attributes:
        pos: DDSketch holding strictly positive values.
        neg: DDSketch holding the absolute value of strictly negative inputs.
        zero_n: Count of exact-zero observations.
        nan_n: Count of NaN observations. A NaN is neither greater nor less
            than zero, so it used to fall through :meth:`add`'s sign test
            into ``zero_n`` and be answered as an exact zero. It is counted
            here instead, and any count above nought takes the answer away
            from :meth:`quantile` and :meth:`cte`.
        relative_accuracy: Bucket-relative-error parameter shared by both
            sub-sketches. See :data:`DEFAULT_RELATIVE_ACCURACY` and the
            module docstring for precision/memory characterisation.

    """

    pos: BaseDDSketch = field(default=None)  # type: ignore[assignment]
    neg: BaseDDSketch = field(default=None)  # type: ignore[assignment]
    zero_n: int = 0
    nan_n: int = 0
    relative_accuracy: float = DEFAULT_RELATIVE_ACCURACY

    def __init__(
        self,
        *,
        relative_accuracy: float = DEFAULT_RELATIVE_ACCURACY,
        pos: BaseDDSketch | None = None,
        neg: BaseDDSketch | None = None,
        zero_n: int = 0,
        nan_n: int = 0,
    ) -> None:
        """Construct a paired sketch with the requested relative accuracy.

        ``pos``/``neg`` are accepted for internal use (deserialisation,
        :meth:`merge`); user code should leave them at their defaults.
        """
        self.relative_accuracy = relative_accuracy
        self.pos = pos if pos is not None else _new_sketch(relative_accuracy)
        self.neg = neg if neg is not None else _new_sketch(relative_accuracy)
        self.zero_n = zero_n
        self.nan_n = nan_n

    def add(self, v: float) -> None:
        """Add a single observation, routing by sign.

        A NaN answers False to both comparisons, so it is tested for by name
        before the zero bucket takes it. The zero bucket therefore holds real
        zeros and nothing else.
        """
        if v > 0:
            self.pos.add(v)
        elif v < 0:
            self.neg.add(-v)
        elif math.isnan(v):
            self.nan_n += 1
        else:
            self.zero_n += 1

    @property
    def n(self) -> int:
        """Total observation count across pos/neg/zero, NaNs included.

        A NaN is an observation: the sketch saw a value, and the value it saw
        was unknown. It is counted here for the same reason ``Count`` counts
        it, and it is why :meth:`quantile` refuses rather than ranking.
        """
        return (
            _sketch_count(self.pos) + _sketch_count(self.neg) + self.zero_n + self.nan_n
        )

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
        out.nan_n = a.nan_n + b.nan_n
        return out

    def quantile(self, q: float) -> float:
        """Return the linearly-interpolated ``q``-th quantile.

        Returns ``NaN`` if the sketch is empty, and ``NaN`` if it has seen a
        NaN: one unknown observation leaves every order statistic over the
        set unknown, because nothing places it in the ordering.
        """
        return self._probe_values([q])[0]

    def _single_value(self, *, n_neg: int, n_zero: int) -> float:
        """Return the lone observation when ``n == 1``."""
        if n_neg == 1:
            return -_subsketch_values_at_ranks(self.neg, {0})[0]
        if n_zero == 1:
            return 0.0
        return _subsketch_values_at_ranks(self.pos, {0})[0]

    def _order_stats(
        self,
        ranks: set[int],
        *,
        n_neg: int,
        n_zero: int,
    ) -> dict[int, float]:
        """Values of the ascending order statistics ``ranks`` over the full set.

        The ascending sequence is the negatives (most-negative first), then the zeros,
        then the positives; within each region the value is that sub-sketch's order
        statistic, so a quantile can interpolate ACROSS a region boundary (a rank
        between the last negative and the first zero) instead of clamping to an
        edge. Each sub-sketch is walked once for every rank that lands in it.
        """
        # r-th smallest true negative == the (n_neg-1-r)-th ascending |neg| value.
        neg_ranks = {n_neg - 1 - r for r in ranks if r < n_neg}
        pos_ranks = {r - n_neg - n_zero for r in ranks if r >= n_neg + n_zero}
        neg = _subsketch_values_at_ranks(self.neg, neg_ranks)
        pos = _subsketch_values_at_ranks(self.pos, pos_ranks)
        values: dict[int, float] = {}
        for r in ranks:
            if r < n_neg:
                values[r] = -neg[n_neg - 1 - r]
            elif r < n_neg + n_zero:
                values[r] = 0.0
            else:
                values[r] = pos[r - n_neg - n_zero]
        return values

    def _probe_values(self, qs: list[float]) -> list[float]:
        """Linearly-interpolated quantile at each ``q`` in ``qs``, one walk per store.

        Every probe is two order statistics; all of them are resolved together
        so each sub-sketch's store is walked once, then each probe interpolates
        between its own pair. NaN for every probe if the sketch is empty, and
        NaN for every probe if it has seen a NaN -- the single place both
        :meth:`quantile` and :meth:`cte` take that answer from, so the two
        cannot drift apart. Below this guard ``nan_n`` is nought, so ``self.n``
        is the count the ranks are computed against and every one of those
        observations is in a store or the zero bucket.
        """
        if self.nan_n:
            return [float("nan")] * len(qs)
        total = self.n
        if total == 0:
            return [float("nan")] * len(qs)
        n_neg = _sketch_count(self.neg)
        n_zero = self.zero_n
        if total == 1:
            return [self._single_value(n_neg=n_neg, n_zero=n_zero)] * len(qs)
        probes: list[tuple[int, int, float]] = []
        for q in qs:
            rank = q * (total - 1)
            lo = max(0, min(int(rank), total - 1))
            hi = min(lo + 1, total - 1)
            probes.append((lo, hi, rank - lo))
        ranks = {r for lo, hi, _ in probes for r in (lo, hi)}
        v = self._order_stats(ranks, n_neg=n_neg, n_zero=n_zero)
        return [
            v[lo] if hi == lo else v[lo] + (v[hi] - v[lo]) * weight
            for lo, hi, weight in probes
        ]

    def cte(
        self,
        level: float,
        direction: Literal["upper", "lower"] = "upper",
    ) -> float:
        """Approximate Conditional Tail Expectation: the mean of ten quantile probes.

        The probes sit at the midpoints of ten equal slices of a tail of width
        ``level``: ``q_i = 1 - level * (i + 0.5) / 10`` for the upper tail and
        ``q_i = level * (i + 0.5) / 10`` for the lower, ``i = 0..9``. Each probe
        is the value :meth:`quantile` returns there, and the result is their
        plain average -- a probe-quantile average, not the exact mean of the
        worst ``level`` fraction of observations. The outermost probe sits
        ``level * 0.05`` inside the tail, so the extreme 5% of the tail is never
        sampled directly.

        Args:
            level: Tail probability (e.g. ``0.005`` for the 99.5% tail).
            direction: ``"upper"`` for right-tail (large losses) or
                ``"lower"`` for left-tail.

        Returns:
            Mean of the ten probe quantiles, or NaN if the sketch is empty or
            has seen a NaN -- every probe is a quantile, and a quantile over a
            set holding an unknown value is unknown.

        """
        n_probes = 10
        if direction == "upper":
            qs = [1.0 - level * (i + 0.5) / n_probes for i in range(n_probes)]
        else:
            qs = [level * (i + 0.5) / n_probes for i in range(n_probes)]
        samples = self._probe_values(qs)
        return sum(samples) / len(samples)

    def canonical_form(self) -> dict[str, Any]:
        """Return a dict identifying this sketch's parameterisation.

        This is the audit-sidecar (T14) and YAML round-trip (T15/T16)
        representation. Two sketches with the same canonical form
        produce comparable buckets and are merge-compatible.

        **It names the parameterisation and never the observations.** No
        count is in here -- not ``zero_n``, and for the same reason not
        ``nan_n``: two sketches that have seen different data are still
        merge-compatible, which is the only question this answers. Keeping
        the NaN count out is also what leaves every digest taken over a
        canonical form where it was.
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

        **This is state, and it carries ``nan_n``.** The blob is the whole
        object, so the NaN count travels with the buckets and the zero count,
        and a sketch that comes back from :meth:`from_bytes` still knows to
        refuse. The alternative -- refusing to serialise a sketch that has
        seen a NaN -- would stop a batched run in the middle for a reason the
        run is meant to carry to the end and report. Nothing in the framework
        digests these bytes: they are read back by :meth:`from_bytes` and
        compared blob-to-blob in-process, never pinned to a published value.
        """
        return pickle.dumps(self, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def from_binned(
        cls,
        *,
        pos: list[tuple[float, int]],
        neg: list[tuple[float, int]],
        zero_n: int,
        nan_n: int = 0,
        relative_accuracy: float = DEFAULT_RELATIVE_ACCURACY,
    ) -> SignedSketch:
        """Build a sketch from histograms: ``(representative_value, count)`` per bin.

        Each ``representative_value`` must be a real observed value from its bin, so
        the underlying ddsketch ``add(value, weight=count)`` places the whole count in
        the correct bucket by the library's own mapping — no per-value loop.
        ``pos``/``neg`` carry **positive** representatives (``neg`` is the abs value).

        ``nan_n`` is the count of NaN observations the histogram was built from.
        It exists because a NaN has no bin -- it belongs in no store and is not a
        zero -- and :meth:`add` keeps the same count on the per-value path. A
        caller that drops NaNs instead of counting them here builds a sketch that
        ranks the values it did see and reports a quantile, when the honest answer
        is that the quantile is unknown; see :meth:`_probe_values`, which is the
        one place that decision is taken.
        """
        out = cls(relative_accuracy=relative_accuracy)
        for value, count in pos:
            out.pos.add(float(value), float(count))
        for value, count in neg:
            out.neg.add(float(value), float(count))
        out.zero_n = int(zero_n)
        out.nan_n = int(nan_n)
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
