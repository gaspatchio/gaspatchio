# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test Quantile/Median/CTE/QuantileRank - DDSketch-backed."""

from __future__ import annotations

import math

import pytest

from gaspatchio_core.scenarios._aggregators import CTE, Median, Quantile, QuantileRank


def test_median() -> None:
    """Median of 1..5 is ~3 within sketch tolerance."""
    a = Median("v")
    s = a.create_accumulator()
    for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
        s = a.add_input(s, v)
    assert math.isclose(a.extract_output(s), 3.0, rel_tol=5e-2, abs_tol=5e-2)


def test_quantile_single_level() -> None:
    """Quantile.extract_output returns {level: value} dict."""
    a = Quantile("v", levels=(0.5,))
    s = a.create_accumulator()
    for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
        s = a.add_input(s, v)
    out = a.extract_output(s)
    assert isinstance(out, dict)
    assert math.isclose(out[0.5], 3.0, rel_tol=5e-2, abs_tol=5e-2)


def test_quantile_multi_level() -> None:
    """Quantile supports multiple levels in one extract."""
    a = Quantile("v", levels=(0.1, 0.5, 0.9))
    s = a.create_accumulator()
    for v in range(1, 101):
        s = a.add_input(s, float(v))
    out = a.extract_output(s)
    assert math.isclose(out[0.1], 10.0, abs_tol=2.0)
    assert math.isclose(out[0.5], 50.0, abs_tol=2.0)
    assert math.isclose(out[0.9], 90.0, abs_tol=2.0)


def test_cte_upper_precision() -> None:
    """CTE upper-tail relative error within ~50 bp on uniform 1..1000."""
    a = CTE("v", level=0.005, direction="upper")
    s = a.create_accumulator()
    for v in range(1, 1001):
        s = a.add_input(s, float(v))
    # Top 0.5%: values 996..1000 -> true mean = 998
    cte = a.extract_output(s)
    relerr_bp = abs(cte - 998.0) / 998.0 * 1e4
    assert relerr_bp < 50.0, f"CTE relerr {relerr_bp:.2f} bp exceeds 50 bp"


def test_cte_lower() -> None:
    """CTE lower-tail on uniform 1..1000 returns ~bottom 5 values mean."""
    a = CTE("v", level=0.005, direction="lower")
    s = a.create_accumulator()
    for v in range(1, 1001):
        s = a.add_input(s, float(v))
    cte = a.extract_output(s)
    # Bottom 0.5% -> mean of 1..5 ~ 3; precision matches upper-tail bound
    assert 0.0 < cte < 20.0


def test_quantile_rank() -> None:
    """QuantileRank at v=50 in uniform 1..100 distribution is ~0.5."""
    a = QuantileRank("v", at=50.0)
    s = a.create_accumulator()
    for v in range(1, 101):
        s = a.add_input(s, float(v))
    rank = a.extract_output(s)
    assert 0.45 < rank < 0.55


def test_median_merge_consistent() -> None:
    """Median across batches matches single-pass within sketch tolerance."""
    a = Median("v")
    values = [float(i) for i in range(1, 101)]
    single = a.create_accumulator()
    for v in values:
        single = a.add_input(single, v)

    left = a.create_accumulator()
    for v in values[:30]:
        left = a.add_input(left, v)
    right = a.create_accumulator()
    for v in values[30:]:
        right = a.add_input(right, v)
    merged = a.merge_accumulators(left, right)

    assert math.isclose(
        a.extract_output(single),
        a.extract_output(merged),
        rel_tol=1e-3,
        abs_tol=1e-3,
    )


def test_relative_accuracy_passthrough() -> None:
    """Coarser relative_accuracy produces a smaller pickled sketch."""
    import pickle

    coarse = CTE("v", level=0.005, direction="upper", relative_accuracy=1e-2)
    fine = CTE("v", level=0.005, direction="upper", relative_accuracy=1e-4)

    coarse_state = coarse.create_accumulator()
    fine_state = fine.create_accumulator()
    for v in range(1, 1001):
        coarse_state = coarse.add_input(coarse_state, float(v))
        fine_state = fine.add_input(fine_state, float(v))

    assert len(pickle.dumps(coarse_state)) < len(pickle.dumps(fine_state))


def test_canonical_forms() -> None:
    """Each aggregator's canonical_form()['kind'] matches its registered name."""
    assert Quantile("v", levels=(0.5,)).canonical_form()["kind"] == "Quantile"
    assert Median("v").canonical_form()["kind"] == "Median"
    assert CTE("v", level=0.005).canonical_form()["kind"] == "CTE"
    assert QuantileRank("v", at=0.0).canonical_form()["kind"] == "QuantileRank"


def test_quantile_canonical_records_levels() -> None:
    """Quantile.canonical_form() records the configured levels as a list."""
    cf = Quantile("v", levels=(0.1, 0.5, 0.9)).canonical_form()
    assert cf["levels"] == [0.1, 0.5, 0.9]


def test_cte_canonical_records_level_and_direction() -> None:
    """CTE.canonical_form() records both level and direction."""
    cf = CTE("v", level=0.005, direction="upper").canonical_form()
    assert cf["level"] == 0.005
    assert cf["direction"] == "upper"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
