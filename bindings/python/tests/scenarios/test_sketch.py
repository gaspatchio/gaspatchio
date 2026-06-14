# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test the signed-value DDSketch facade - bit-exact mergeability."""

from __future__ import annotations

import math
import pickle
import random

import pytest

from gaspatchio_core.scenarios._sketch import (
    DEFAULT_RELATIVE_ACCURACY,
    SignedSketch,
)


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
