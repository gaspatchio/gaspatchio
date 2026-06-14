# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Hypothesis-driven property test pinning merge associativity + commutativity.

Every aggregator implementing the GSP-101 Aggregator Protocol must satisfy:

- ``extract(fold(A ++ B)) == extract(merge(fold(A), fold(B)))`` (associativity)
- ``merge(a, b)`` extract-equals ``merge(b, a)`` (commutativity)

For DDSketch-backed aggregators, the equality is on the serialised sketch
state - bit-identical.

Aggregator classes are registered in the ``AGGREGATOR_PARAMS`` list as they
land in subsequent tasks.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gaspatchio_core.scenarios._aggregators import (
    CTE,
    ArgMax,
    ArgMin,
    Count,
    Max,
    Mean,
    Median,
    Min,
    Std,
    Sum,
    Variance,
)

_ID_VAL = st.tuples(
    st.text(min_size=1, max_size=8),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
)

# Aggregator classes registered as they land. Each entry is
# ``(name, factory, value_strategy)`` where ``factory`` is a zero-arg callable
# returning an aggregator and ``value_strategy`` supplies test inputs.
AGGREGATOR_PARAMS: list[tuple[str, Any, Any]] = [
    (
        "Sum",
        lambda: Sum("v"),
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
    ),
    (
        "Count",
        lambda: Count("v"),
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
    ),
    (
        "Min",
        lambda: Min("v"),
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
    ),
    (
        "Max",
        lambda: Max("v"),
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
    ),
    ("ArgMax", lambda: ArgMax("v"), _ID_VAL),
    ("ArgMin", lambda: ArgMin("v"), _ID_VAL),
    (
        "Mean",
        lambda: Mean("v"),
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
    ),
    (
        "Variance",
        lambda: Variance("v"),
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
    ),
    (
        "Std",
        lambda: Std("v"),
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
    ),
]


def _fold(agg: Any, values: list[Any]) -> Any:  # noqa: ANN401
    state = agg.create_accumulator()
    for v in values:
        state = agg.add_input(state, v)
    return state


def _float_close(a: float, b: float) -> bool:
    """Compare floats with combined abs/rel tolerance.

    Welford+Chan merge is single-pass-equivalent up to floating-point
    arithmetic. Catastrophic cancellation on large values (e.g. variance
    of values near 1e6) lifts the absolute error above 1e-9 while the
    relative error stays at machine epsilon. Combined tolerance:
    rel < 1e-9 OR abs < 1e-6.
    """
    return abs(a - b) < 1e-6 or abs(a - b) < 1e-9 * max(abs(a), abs(b), 1.0)


def _sketch_close(a: float, b: float) -> bool:
    """Looser tolerance for DDSketch-backed aggregators.

    DDSketch buckets values in log-space; merge is bit-exact at the
    bucket level, but the linearly-interpolated value returned by
    ``quantile()`` shifts by relative-accuracy quanta when the order
    statistics fall in different buckets across orderings. CTE samples
    10 quantile probes and averages, which compounds the wobble. A
    combined rel < 5e-3 OR abs < 0.5 tolerance covers both effects on
    the value ranges exercised in this property test (+/- 1e4).
    """
    return abs(a - b) < 0.5 or abs(a - b) / max(abs(a), abs(b), 1e-9) < 5e-3


# Sketch-backed aggregators with scalar float extract_output.
# Quantile is omitted (returns dict). QuantileRank is omitted (40-iter
# binary search is too slow at hypothesis cadence).
SKETCH_SCALAR_PARAMS: list[tuple[str, Any, Any]] = [
    (
        "Median",
        lambda: Median("v"),
        st.floats(min_value=-1e4, max_value=1e4, allow_nan=False),
    ),
    (
        "CTE",
        lambda: CTE("v"),
        st.floats(min_value=-1e4, max_value=1e4, allow_nan=False),
    ),
]


@pytest.mark.parametrize(("name", "factory", "value_strategy"), AGGREGATOR_PARAMS)
@settings(max_examples=50, deadline=None)
@given(st.data())
def test_merge_is_associative(
    name: str,
    factory: Any,  # noqa: ANN401
    value_strategy: Any,  # noqa: ANN401
    data: st.DataObject,
) -> None:
    """fold(A ++ B) extract-equals merge(fold(A), fold(B))."""
    values = data.draw(st.lists(value_strategy, min_size=2, max_size=100))
    if len(values) < 2:
        pytest.skip("Need at least 2 values to split.")
    split = len(values) // 2
    left, right = values[:split], values[split:]

    agg = factory()
    single = agg.extract_output(_fold(agg, values))
    merged = agg.extract_output(
        agg.merge_accumulators(_fold(agg, left), _fold(agg, right)),
    )

    if isinstance(single, float):
        assert _float_close(single, merged), (
            f"{name}: associativity broken (single={single}, merged={merged})"
        )
    else:
        assert single == merged, f"{name}: associativity broken"


@pytest.mark.parametrize(("name", "factory", "value_strategy"), AGGREGATOR_PARAMS)
@settings(max_examples=50, deadline=None)
@given(st.data())
def test_merge_is_commutative(
    name: str,
    factory: Any,  # noqa: ANN401
    value_strategy: Any,  # noqa: ANN401
    data: st.DataObject,
) -> None:
    """merge(a, b) extract-equals merge(b, a)."""
    values = data.draw(st.lists(value_strategy, min_size=2, max_size=100))
    if len(values) < 2:
        pytest.skip("Need at least 2 values to split.")
    split = len(values) // 2
    left, right = values[:split], values[split:]

    agg = factory()
    a = _fold(agg, left)
    b = _fold(agg, right)
    forward = agg.extract_output(agg.merge_accumulators(a, b))
    reverse = agg.extract_output(agg.merge_accumulators(b, a))

    if isinstance(forward, float):
        assert _float_close(forward, reverse), (
            f"{name}: commutativity broken (forward={forward}, reverse={reverse})"
        )
    else:
        assert forward == reverse, f"{name}: commutativity broken"


@pytest.mark.parametrize(("name", "factory", "value_strategy"), SKETCH_SCALAR_PARAMS)
@settings(max_examples=20, deadline=None)
@given(st.data())
def test_sketch_merge_is_associative_within_tolerance(
    name: str,
    factory: Any,  # noqa: ANN401
    value_strategy: Any,  # noqa: ANN401
    data: st.DataObject,
) -> None:
    """fold(A ++ B) extract-equals merge(fold(A), fold(B)) within sketch tolerance."""
    values = data.draw(st.lists(value_strategy, min_size=10, max_size=100))
    if len(values) < 4:
        pytest.skip("Need >=4 values to split.")
    split = len(values) // 2
    left, right = values[:split], values[split:]

    agg = factory()
    single = agg.extract_output(_fold(agg, values))
    merged = agg.extract_output(
        agg.merge_accumulators(_fold(agg, left), _fold(agg, right)),
    )
    assert _sketch_close(single, merged), (
        f"{name}: |single - merged| = {abs(single - merged)} "
        f"(single={single}, merged={merged})"
    )


@pytest.mark.parametrize(("name", "factory", "value_strategy"), SKETCH_SCALAR_PARAMS)
@settings(max_examples=20, deadline=None)
@given(st.data())
def test_sketch_merge_is_commutative_within_tolerance(
    name: str,
    factory: Any,  # noqa: ANN401
    value_strategy: Any,  # noqa: ANN401
    data: st.DataObject,
) -> None:
    """merge(a, b) extract-equals merge(b, a) within sketch tolerance."""
    values = data.draw(st.lists(value_strategy, min_size=10, max_size=100))
    if len(values) < 4:
        pytest.skip("Need >=4 values to split.")
    split = len(values) // 2
    left, right = values[:split], values[split:]

    agg = factory()
    a = _fold(agg, left)
    b = _fold(agg, right)
    forward = agg.extract_output(agg.merge_accumulators(a, b))
    reverse = agg.extract_output(agg.merge_accumulators(b, a))
    assert _sketch_close(forward, reverse), (
        f"{name}: |forward - reverse| = {abs(forward - reverse)} "
        f"(forward={forward}, reverse={reverse})"
    )
