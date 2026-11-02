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

**Two search budgets, chosen by hypothesis profile.** Nothing here is skipped
under either: every case runs, both tolerance rationales apply, only the number
of examples drawn and the length of the drawn lists move.

``default`` -- what an ordinary run gets: five examples a case, and the sketch
cases draw at most 40 values. About twenty seconds; three runs on one seed
landed between 18 s and 19 s. (It was about a minute before ``_sketch.py``
walked its store once per query -- see below.)

``thorough`` -- ``uv run pytest tests/scenarios/test_aggregator_property.py
--hypothesis-profile=thorough`` -- restores exactly the budgets this file
carried before the two were separated: 50 examples for the merge cases, 20 for
the sketch ones, lists up to 100 values. About a minute and a half (94-98 s on
the same seed; four to seven minutes before). **Run it before a release, and
after any change to ``_aggregators.py`` or ``_sketch.py``** -- those are the
two files whose merge algebra this pins.

The cost of an example is set by what hypothesis draws, not by how much it
draws -- see below -- so read a single timing as a sample, not as the number.

Almost all of what ``default`` still costs is the four sketch cases (``Median``
and ``CTE``), and no search budget reaches it: a sketch extract's cost is set by
how wide a span of magnitudes the drawn values happen to cover, because the
DDSketch store holds every bucket between the smallest and largest magnitude
seen (~11,500 per decade at the default accuracy; a draw near 1e-300 keys
millions of them) and resolving an order statistic is a Python walk of that
store. ``SignedSketch`` now collects every order statistic a ``quantile()`` or
``cte()`` needs and walks each store once for all of them, where it used to
walk once per fetch -- four times per quantile, up to forty per ``cte()``. That
took this file from about a minute to about twenty seconds under ``default``
and from six and a half minutes to a minute and a half under ``thorough``, on
the same seeded draws. Shortening the drawn lists still buys almost nothing:
what remains is that one walk per store on the widest draws.

The profile is registered in the root ``conftest.py`` (hypothesis resolves the
flag before a conftest deeper in the tree is imported); the numbers it selects
live in ``_BUDGET`` below, because they are this file's business rather than the
whole tree's.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gaspatchio.scenarios._aggregators import (
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


class _Budget(NamedTuple):
    """How hard one profile asks this file to search.

    Attributes:
        merge_examples: Examples drawn for each closed-form merge case.
        sketch_examples: Examples drawn for each DDSketch case. Lower than
            ``merge_examples`` because a sketch example walks a DDSketch store
            per extract (the module docstring says what that costs) where a
            merge example costs microseconds.
        sketch_values: Longest list of observations a sketch case draws.

    """

    merge_examples: int
    sketch_examples: int
    sketch_values: int


_BUDGETS = {
    "default": _Budget(merge_examples=5, sketch_examples=5, sketch_values=40),
    "thorough": _Budget(merge_examples=50, sketch_examples=20, sketch_values=100),
}

# Read at import, which pytest reaches after hypothesis has resolved
# ``--hypothesis-profile``. Any profile this file does not name -- hypothesis's
# own ``ci``, or one somebody registers locally -- searches on the small budget:
# the deep search is something you ask for, never something you inherit.
_BUDGET = _BUDGETS.get(settings.get_current_profile_name(), _BUDGETS["default"])

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
@settings(max_examples=_BUDGET.merge_examples, deadline=None)
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
@settings(max_examples=_BUDGET.merge_examples, deadline=None)
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
@settings(max_examples=_BUDGET.sketch_examples, deadline=None)
@given(st.data())
def test_sketch_merge_is_associative_within_tolerance(
    name: str,
    factory: Any,  # noqa: ANN401
    value_strategy: Any,  # noqa: ANN401
    data: st.DataObject,
) -> None:
    """fold(A ++ B) extract-equals merge(fold(A), fold(B)) within sketch tolerance."""
    values = data.draw(
        st.lists(value_strategy, min_size=10, max_size=_BUDGET.sketch_values)
    )
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
@settings(max_examples=_BUDGET.sketch_examples, deadline=None)
@given(st.data())
def test_sketch_merge_is_commutative_within_tolerance(
    name: str,
    factory: Any,  # noqa: ANN401
    value_strategy: Any,  # noqa: ANN401
    data: st.DataObject,
) -> None:
    """merge(a, b) extract-equals merge(b, a) within sketch tolerance."""
    values = data.draw(
        st.lists(value_strategy, min_size=10, max_size=_BUDGET.sketch_values)
    )
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
