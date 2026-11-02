# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test the signed-value DDSketch facade - bit-exact mergeability."""

from __future__ import annotations

import math
import pickle
import random
import sys
from typing import TYPE_CHECKING, Literal, cast

import pytest

from gaspatchio.scenarios._sketch import (
    DEFAULT_RELATIVE_ACCURACY,
    SignedSketch,
)

if TYPE_CHECKING:
    from ddsketch.ddsketch import BaseDDSketch


def test_pos_only_quantile() -> None:
    """Median of 1..10 is ~5.5."""
    s = SignedSketch()
    for v in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
        s.add(v)
    assert math.isclose(s.quantile(0.5), 5.5, rel_tol=5e-3, abs_tol=5e-3)


def test_negative_only_quantile() -> None:
    """Median of -10..-1 is ~-5.5."""
    s = SignedSketch()
    for v in [-10.0, -9.0, -8.0, -7.0, -6.0, -5.0, -4.0, -3.0, -2.0, -1.0]:
        s.add(v)
    assert math.isclose(s.quantile(0.5), -5.5, rel_tol=5e-3, abs_tol=5e-3)


def test_mixed_sign_quantile() -> None:
    """Median of -5..5 is approximately 0."""
    s = SignedSketch()
    for v in range(-5, 6):  # -5..5
        s.add(float(v))
    assert math.isclose(s.quantile(0.5), 0.0, abs_tol=5e-3)


def test_zero_count_tracked() -> None:
    """Zero values are counted separately and recoverable at the median."""
    s = SignedSketch()
    for _ in range(5):
        s.add(0.0)
    s.add(-1.0)
    s.add(1.0)
    # 7 values: -1, 0, 0, 0, 0, 0, 1 -> median = 0
    assert s.quantile(0.5) == 0.0


def test_quantile_interpolates_across_zero_boundary() -> None:
    """Quantiles straddling the zero plateau interpolate across regions (#3)."""
    s = SignedSketch()
    for v in [-100.0, -50.0, 0.0, 0.0, 50.0, 100.0, 200.0]:
        s.add(v)
    # rank 1.5 -> halfway between -50 (rank 1) and 0 (rank 2) -> -25 (was -50)
    assert s.quantile(0.25) == pytest.approx(-25.0, abs=1.0)
    # rank 3.5 -> halfway between 0 (rank 3) and 50 (rank 4) -> 25 (was 0)
    assert s.quantile(3.5 / 6) == pytest.approx(25.0, abs=1.0)


def test_merge_is_commutative() -> None:
    """SignedSketch.merge(a, b) and SignedSketch.merge(b, a) produce same quantiles."""
    a = SignedSketch()
    for v in [-3.0, -2.0, -1.0]:
        a.add(v)
    b = SignedSketch()
    for v in [1.0, 2.0, 3.0]:
        b.add(v)

    merged_ab = SignedSketch.merge(a, b)
    merged_ba = SignedSketch.merge(b, a)
    assert merged_ab.quantile(0.5) == merged_ba.quantile(0.5)


def test_serialise_round_trip() -> None:
    """to_bytes -> from_bytes preserves quantiles."""
    s = SignedSketch()
    for v in [-1.0, 0.0, 1.0, 2.0, 3.0]:
        s.add(v)
    blob = s.to_bytes()
    s2 = SignedSketch.from_bytes(blob)
    assert s.quantile(0.5) == s2.quantile(0.5)


def test_cte_upper_tail() -> None:
    """CTE upper-tail of 1..1000 at level=0.005 is approximately 998."""
    s = SignedSketch()
    for v in range(1, 1001):
        s.add(float(v))
    # Top 0.5% = values ranked 996..1000 -> mean ~ 998
    cte = s.cte(level=0.005, direction="upper")
    assert 990.0 < cte < 1005.0


def test_cte_lower_tail() -> None:
    """CTE lower-tail (left tail of positive distribution)."""
    s = SignedSketch()
    for v in range(1, 1001):
        s.add(float(v))
    # Bottom 0.5% ~ mean of 1..5 ~ 3
    cte = s.cte(level=0.005, direction="lower")
    assert 0.0 < cte < 10.0


def test_empty_sketch_returns_nan() -> None:
    """quantile() on an empty sketch returns NaN (not 0, not crash)."""
    s = SignedSketch()
    assert math.isnan(s.quantile(0.5))


def test_n_property() -> None:
    """N returns total count across pos/neg/zero."""
    s = SignedSketch()
    for v in [-1.0, 0.0, 1.0]:
        s.add(v)
    assert s.n == 3


def test_cte_upper_tail_precision() -> None:
    """CTE precision on uniform 1..1000 stays within measured DDSketch tolerance.

    Empirical: ~10.5 bp relative error on uniform 1..1000 at
    ``level=0.005``, dominated by bucket-centre interpolation (refining
    ``n_probes`` does not help). See module docstring of ``_sketch.py``.
    """
    s = SignedSketch()
    for v in range(1, 1001):
        s.add(float(v))
    # True top 0.5% (values 996..1000) -> mean = 998
    cte = s.cte(level=0.005, direction="upper")
    relerr_bp = abs(cte - 998.0) / 998.0 * 1e4
    # 15 bp tolerance: comfortably above the measured 10.5 bp,
    # leaves headroom for ddsketch version drift.
    assert relerr_bp < 15.0, f"CTE relative error {relerr_bp:.2f} bp exceeds tolerance"


def test_sketch_memory_envelope() -> None:
    """Pickle size for realistic actuarial value range stays under documented bound.

    Empirically the paired sketch is ~2.5 MB at ``rel_acc=1e-4`` for
    100 k lognormal observations across 6 decades. This is a smoke
    check — exceeding 5 MB indicates a regression in the sketch
    library or the wrapper.
    """
    rng = random.Random(42)  # noqa: S311 - non-cryptographic; envelope smoke check
    s = SignedSketch()
    for _ in range(100_000):
        s.add(rng.uniform(1.0, 1e6))
    size_kb = len(pickle.dumps(s)) / 1024
    msg = f"Sketch pickle is {size_kb:.0f} KB, exceeded 5 MB envelope"
    assert size_kb < 5000.0, msg


def test_relative_accuracy_tunable() -> None:
    """Sketch accepts a tunable relative_accuracy parameter."""
    coarse = SignedSketch(relative_accuracy=1e-2)
    fine = SignedSketch(relative_accuracy=1e-4)
    for v in range(1, 1001):
        coarse.add(float(v))
        fine.add(float(v))
    # Coarser accuracy => fewer buckets => smaller pickle.
    assert len(pickle.dumps(coarse)) < len(pickle.dumps(fine))
    assert coarse.relative_accuracy == 1e-2
    assert fine.relative_accuracy == 1e-4


def test_canonical_form_contains_parameters() -> None:
    """canonical_form() reports the sketch kind + relative accuracy."""
    s = SignedSketch(relative_accuracy=5e-4)
    form = s.canonical_form()
    assert form["sketch_kind"] == "DDSketch"
    assert form["relative_accuracy"] == 5e-4


def test_default_relative_accuracy_constant() -> None:
    """Default constructor uses DEFAULT_RELATIVE_ACCURACY."""
    s = SignedSketch()
    assert s.relative_accuracy == DEFAULT_RELATIVE_ACCURACY


def test_merge_mismatched_accuracy_rejected() -> None:
    """Merging sketches with different relative_accuracy must raise."""
    a = SignedSketch(relative_accuracy=1e-4)
    b = SignedSketch(relative_accuracy=1e-3)
    a.add(1.0)
    b.add(2.0)
    with pytest.raises(ValueError, match="relative_accuracy"):
        SignedSketch.merge(a, b)


# ---------------------------------------------------------------------------
# One walk of the store per order statistic: the reference and the pins.
#
# ``SignedSketch.quantile`` and ``SignedSketch.cte`` resolve every order
# statistic they need in ONE ascending walk of each DDSketch store. The path
# they replaced walked the store once per ``get_quantile_value`` call: two order
# statistics per probe, and ``_subsketch_value_at_rank`` fetched a second
# bucket for every integer rank below the last and then multiplied it by a
# weight of exactly zero -- up to four walks per quantile and up to forty per
# ``cte()``, on a store sized by the span of magnitudes (~11,500 buckets per
# decade at 1e-4).
#
# The answer has to be bit-identical, because the value is what a regulator
# reconciles against and the tutorial oracles pin. So the replaced path is kept
# here, verbatim (``self`` became ``s``; each method became a module function
# with the same name and body), and the battery below pins the new
# ``quantile()`` and ``cte()`` to it on every case by ``repr`` and ``type``:
# ``==`` would let an int ``0`` pass for the reference's ``-0.0``.
# ---------------------------------------------------------------------------


def _ref_sketch_count(sketch: BaseDDSketch) -> int:
    """Return integer count from a sketch (count is stored as float internally)."""
    return int(sketch.count)


def _ref_subsketch_value_at_rank(sketch: BaseDDSketch, rank: float) -> float:
    """Return the reference bucket-centre value at ``rank``: one walk per fetch."""
    m = _ref_sketch_count(sketch)
    if m == 0:
        return float("nan")
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


def _ref_single_value(s: SignedSketch, *, n_neg: int, n_zero: int) -> float:
    """Return the reference lone observation when ``n == 1``."""
    if n_neg == 1:
        return -_ref_subsketch_value_at_rank(s.neg, 0)
    if n_zero == 1:
        return 0.0
    return _ref_subsketch_value_at_rank(s.pos, 0)


def _ref_order_stat(s: SignedSketch, r: int, *, n_neg: int, n_zero: int) -> float:
    """Return the reference ``r``-th ascending order statistic over the full set."""
    if r < n_neg:
        # r-th smallest true negative == the (n_neg-1-r)-th ascending |neg| value.
        return -_ref_subsketch_value_at_rank(s.neg, n_neg - 1 - r)
    if r < n_neg + n_zero:
        return 0.0
    return _ref_subsketch_value_at_rank(s.pos, r - n_neg - n_zero)


def _ref_interp_quantile(
    s: SignedSketch,
    *,
    q: float,
    n_neg: int,
    n_zero: int,
    n_pos: int,
) -> float:
    """Return the reference linearly-interpolated quantile for ``n >= 2``."""
    total = n_neg + n_zero + n_pos
    rank = q * (total - 1)
    lo = max(0, min(int(rank), total - 1))
    hi = min(lo + 1, total - 1)
    v_lo = _ref_order_stat(s, lo, n_neg=n_neg, n_zero=n_zero)
    if hi == lo:
        return v_lo
    v_hi = _ref_order_stat(s, hi, n_neg=n_neg, n_zero=n_zero)
    return v_lo + (v_hi - v_lo) * (rank - lo)


def _ref_quantile(s: SignedSketch, q: float) -> float:
    """Return the reference ``quantile``: up to four walks of the store."""
    total = s.n
    if total == 0:
        return float("nan")
    n_neg = _ref_sketch_count(s.neg)
    n_zero = s.zero_n
    n_pos = _ref_sketch_count(s.pos)
    if total == 1:
        return _ref_single_value(s, n_neg=n_neg, n_zero=n_zero)
    return _ref_interp_quantile(s, q=q, n_neg=n_neg, n_zero=n_zero, n_pos=n_pos)


def _ref_cte(
    s: SignedSketch,
    level: float,
    direction: Literal["upper", "lower"] = "upper",
) -> float:
    """Return the reference ``cte``: ten probes, up to forty walks of the store."""
    total = s.n
    if total == 0:
        return float("nan")
    n_probes = 10
    if direction == "upper":
        qs = [1.0 - level * (i + 0.5) / n_probes for i in range(n_probes)]
    else:
        qs = [level * (i + 0.5) / n_probes for i in range(n_probes)]
    samples = [_ref_quantile(s, q) for q in qs]
    return sum(samples) / len(samples)


# The battery. Every sketch below is pinned on all of these; the case count is
# the product and is asserted at the end so it cannot shrink unnoticed.
_SPANS: dict[str, tuple[float, float]] = {
    "two_decades": (1e2, 1e4),
    "six_decades": (1e-2, 1e4),
    "eleven_decades": (1e-2, 1e9),
}
_SIGN_KINDS = ("positive", "negative", "mixed", "mixed_with_zeros")
_SIZES = (1, 2, 7, 40)
_ACCURACIES = (1e-4, 1e-3)
# Rows: span, accuracy, sizes drawn, sign mixes. The reference walks the store
# up to forty times per cte() -- over the 680 cte() calls the rows below make,
# the count runs from 9 to 40, is 30 most often, and reaches 40 on 124 of them
# -- so the finest accuracy on the wide spans (~69,000 and ~126,000 buckets per
# sign) is drawn at the one size that fills them rather than at every size; the
# arithmetic under test does not depend on n. A row with two or more sizes also
# pins the merge of its two largest sketches.
_BATTERY: tuple[tuple[str, float, tuple[int, ...], tuple[str, ...]], ...] = (
    ("two_decades", 1e-4, _SIZES, _SIGN_KINDS),
    ("two_decades", 1e-3, _SIZES, _SIGN_KINDS),
    ("six_decades", 1e-4, (40,), _SIGN_KINDS),
    ("six_decades", 1e-3, _SIZES, _SIGN_KINDS),
    ("eleven_decades", 1e-4, (40,), ("mixed_with_zeros",)),
    ("eleven_decades", 1e-3, _SIZES, _SIGN_KINDS),
)
_LEVELS = (0.005, 0.01, 0.05, 0.5)
_DIRECTIONS: tuple[Literal["upper", "lower"], ...] = ("upper", "lower")
_QS = (0.0, 0.005, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 0.995, 1.0)
# The battery's width when its comparison was widened to repr and type; it may
# grow, never shrink.
_MIN_CASES = 2033


def _draw_values(
    rng: random.Random,
    span: tuple[float, float],
    kind: str,
    n: int,
) -> list[float]:
    """Draw log-uniform magnitudes across ``span`` (normal floats), signed by kind."""
    lo, hi = math.log10(span[0]), math.log10(span[1])
    values: list[float] = []
    for _ in range(n):
        v = 10.0 ** rng.uniform(lo, hi)
        if kind == "negative" or (kind.startswith("mixed") and rng.random() < 0.3):
            v = -v
        if kind == "mixed_with_zeros" and rng.random() < 0.15:
            v = 0.0
        values.append(v)
    return values


def _build(values: list[float], relative_accuracy: float) -> SignedSketch:
    s = SignedSketch(relative_accuracy=relative_accuracy)
    for v in values:
        s.add(v)
    return s


def _identical(a: float, b: float) -> bool:
    """Tell int ``0`` from ``-0.0``: same ``type``, same ``repr``, NaN equal to NaN.

    ``==`` passes int ``0`` for float ``-0.0`` -- the answer the reference gives
    at ``quantile(1.0)`` on an all-negative sketch whose smallest magnitude sits
    inside ddsketch's zero-count region -- and fails NaN against NaN, which is
    what an empty sketch answers. On a float, ``repr`` equality is ``==`` with
    the sign of a zero kept and NaN equal to NaN; ``type`` tells int from float.
    """
    return type(a) is type(b) and repr(a) == repr(b)


def _pin_against_reference(s: SignedSketch, label: str) -> int:
    """Pin ``cte()`` and ``quantile()`` to the reference by ``repr`` and ``type``.

    Returns the case count.
    """
    cases = 0
    for level in _LEVELS:
        for direction in _DIRECTIONS:
            got, ref = s.cte(level, direction), _ref_cte(s, level, direction)
            assert _identical(got, ref), (
                f"{label}: cte({level}, {direction}) {got!r} ({type(got).__name__})"
                f" is not {ref!r} ({type(ref).__name__})"
            )
            cases += 1
    for q in _QS:
        got, ref = s.quantile(q), _ref_quantile(s, q)
        assert _identical(got, ref), (
            f"{label}: quantile({q}) {got!r} ({type(got).__name__})"
            f" is not {ref!r} ({type(ref).__name__})"
        )
        cases += 1
    return cases


def test_quantile_and_cte_are_bit_identical_to_the_single_probe_path() -> None:
    """One-walk ``quantile()``/``cte()`` answer as the replaced path on every case.

    Sketches: the ``_BATTERY`` rows -- log-uniform draws across two, six and
    eleven decades, in four sign mixes and sizes 1, 2, 7 and 40 (the
    single-value path included), at both relative accuracies, plus the merge
    of the two largest sketches of each row -- and the edge cases: empty, a
    lone positive / negative / zero, all zeros, a pair straddling zero, one
    sub-normal observation (which ddsketch keeps in its inner zero count
    rather than in a bucket), and the zero-count region from both sides: the
    all-negative sketches whose smallest magnitude is a sub-normal or the
    smallest normal float (``LogarithmicMapping.min_possible`` sits above
    both), where the reference answers ``-0.0`` at ``quantile(1.0)``, and the
    sub-normal-only sketches where it answers int ``0``. Each sketch is pinned
    at four levels in both directions and at eleven quantiles. Equality is
    ``repr`` and ``type`` -- the sign of a zero and int against float both
    count -- never ``isclose``.
    """
    rng = random.Random(20260906)  # noqa: S311 - deterministic battery, not crypto
    cases = 0
    for span_name, accuracy, sizes, kinds in _BATTERY:
        for kind in kinds:
            drawn = {n: _draw_values(rng, _SPANS[span_name], kind, n) for n in sizes}
            for n, values in drawn.items():
                label = f"{span_name}/{kind}/n={n}/acc={accuracy}"
                cases += _pin_against_reference(_build(values, accuracy), label)
            if len(sizes) >= 2:
                a = _build(drawn[sizes[-2]], accuracy)
                b = _build(drawn[sizes[-1]], accuracy)
                label = f"{span_name}/{kind}/merge/acc={accuracy}"
                cases += _pin_against_reference(SignedSketch.merge(a, b), label)
    edge_cases: dict[str, list[float]] = {
        "empty": [],
        "lone_positive": [3.25],
        "lone_negative": [-3.25],
        "lone_zero": [0.0],
        "all_zeros": [0.0] * 5,
        "straddles_zero": [-2.0, 2.0],
        "sub_normal": [5e-324, 1.0, 100.0, 1e4, -3.0, 0.0],
        "negative_topped_by_sub_normal": [-5e-324, -5e-324, -1.0],
        "negative_topped_by_min_normal": [-sys.float_info.min, -1.0, -5.0],
        "two_sub_normals": [5e-324, 5e-324],
        "sub_normals_both_signs_with_zero": [-5e-324, 0.0, 5e-324],
    }
    for name, values in edge_cases.items():
        for accuracy in _ACCURACIES:
            cases += _pin_against_reference(
                _build(values, accuracy), f"{name}/acc={accuracy}"
            )
    assert cases >= _MIN_CASES, f"battery shrank to {cases} cases"


def test_queries_leave_the_audit_sidecar_bytes_untouched() -> None:
    """``to_bytes()`` and ``canonical_form()`` are the same before and after queries.

    The serialised sketch is the audit sidecar; a query that mutated or
    re-shaped the store would move it. Pinned around ``cte()`` and
    ``quantile()`` on a mixed-sign sketch at both accuracies.
    """
    rng = random.Random(7)  # noqa: S311 - deterministic, not crypto
    values = [rng.uniform(-1e6, 1e6) for _ in range(2_000)] + [0.0, 1e-2, 1e9]
    for accuracy in _ACCURACIES:
        s = _build(values, accuracy)
        blob, form = s.to_bytes(), s.canonical_form()
        for level in _LEVELS:
            s.cte(level, "upper")
            s.cte(level, "lower")
        for q in _QS:
            s.quantile(q)
        assert s.to_bytes() == blob
        assert s.canonical_form() == form


class _CountingBins(list[float]):
    """``DenseStore.bins`` that counts every walk (each ``iter()``) over it.

    ``DenseStore.key_at_rank`` and the one-pass resolver both walk the store
    with ``enumerate(store.bins)``, so one walk is one ``__iter__``. Indexing
    (``add``, ``merge``) is not a walk and is not counted.
    """

    def __init__(self, bins: list[float]) -> None:
        super().__init__(bins)
        self.walks = 0

    def __iter__(self):  # type: ignore[no-untyped-def]  # noqa: ANN204 - list's own signature
        self.walks += 1
        return super().__iter__()


def _instrumented_sketch() -> tuple[SignedSketch, _CountingBins, _CountingBins]:
    """Build a mixed-sign sketch of 10,000 values whose two stores count their walks."""
    rng = random.Random(3)  # noqa: S311 - deterministic, not crypto
    s = SignedSketch()
    for _ in range(10_000):
        s.add(rng.uniform(-1e4, 1e6))
    pos_store, neg_store = s.pos._store, s.neg._store  # noqa: SLF001 - ddsketch keeps the store private
    pos_bins, neg_bins = _CountingBins(pos_store.bins), _CountingBins(neg_store.bins)
    pos_store.bins, neg_store.bins = pos_bins, neg_bins
    return s, pos_bins, neg_bins


def test_cte_walks_each_store_at_most_once() -> None:
    """One ``cte()`` is at most two walks -- each touched sub-sketch's store once.

    A count, not a clock, so a loaded machine cannot flake it. The replaced
    path walked forty times here (ten probes, two order statistics each, two
    fetches per order statistic). The one-pass path collects every order
    statistic first and walks each touched sub-sketch's store once, so two
    walks is the bound for a sketch holding both signs; this upper-tail
    query touches only the positive store and walks once. A bound of ten
    would let a regression to one walk per probe pass.
    """
    s, pos_bins, neg_bins = _instrumented_sketch()
    s.cte(level=0.005, direction="upper")
    walks = pos_bins.walks + neg_bins.walks
    assert walks <= 2, f"cte() walked the store {walks} times"


def test_quantile_walks_the_store_at_most_once_per_order_statistic() -> None:
    """One ``quantile()`` is at most two walks (its two order statistics), not four."""
    s, pos_bins, neg_bins = _instrumented_sketch()
    s.quantile(0.5)
    walks = pos_bins.walks + neg_bins.walks
    assert walks <= 2, f"quantile() walked the store {walks} times"


def test_one_walk_answers_at_the_float_ceiling_where_the_reference_raised() -> None:
    """With the largest float in the sketch, the reference raised; one walk answers.

    The bucket holding ``sys.float_info.max`` overflows ``math.pow`` in
    ``LogarithmicMapping.value``, so a query that needs the maximum order
    statistic raises ``OverflowError`` on both paths (``quantile(1.0)`` here).
    The reference fetched a second bucket for every integer rank below the
    last and multiplied it by a weight of exactly zero, so on
    ``[1.0, 2.0, sys.float_info.max]`` it reached the maximum, and raised, on
    ``quantile(0.0)`` and on every lower-tail ``cte()`` as well; the one-walk
    path resolves only the order statistics a query needs, and answers. This
    is the one place the two paths differ in behaviour rather than in the type
    of a zero -- not reachable by real data, pinned so that it is written
    down. The answers are held to the exact arithmetic on the raw values
    within the sketch's own relative accuracy: ``quantile(0.0)`` is
    ``0.9998999999999999`` against ``1.0`` (``1.0`` sits on a bucket boundary,
    so the error is the accuracy itself, ``1e-4``, to within one float
    rounding), and the lower-tail probe mean at ``level=0.005`` is
    ``1.0049000281786349`` against ``1.005`` (``9.9e-5``).
    """
    raw = [1.0, 2.0, sys.float_info.max]
    s = _build(raw, DEFAULT_RELATIVE_ACCURACY)
    with pytest.raises(OverflowError):
        _ref_quantile(s, 0.0)
    with pytest.raises(OverflowError):
        _ref_cte(s, 0.005, "lower")
    with pytest.raises(OverflowError):
        s.quantile(1.0)
    tolerance = DEFAULT_RELATIVE_ACCURACY + sys.float_info.epsilon
    exact_q0 = raw[0]
    assert abs(s.quantile(0.0) - exact_q0) <= tolerance * abs(exact_q0)
    # The same ten-probe arithmetic as cte(), on the exact order statistics:
    # every probe rank q * (n - 1) lands between the two smallest values.
    ranks = [0.005 * (i + 0.5) / 10 * (len(raw) - 1) for i in range(10)]
    exact_cte = sum(raw[0] + (raw[1] - raw[0]) * rank for rank in ranks) / 10
    assert abs(s.cte(0.005, "lower") - exact_cte) <= tolerance * abs(exact_cte)
