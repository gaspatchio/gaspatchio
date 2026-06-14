# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test Mean/Variance/Std - Welford + Chan parallel merge."""

from __future__ import annotations

import math
import statistics

import pytest

from gaspatchio_core.scenarios._aggregators import Mean, Std, Variance


def test_mean_matches_statistics() -> None:
    """Mean matches statistics.mean for a small fixed sample."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    a = Mean("v")
    s = a.create_accumulator()
    for v in values:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(statistics.mean(values))


def test_variance_matches_statistics() -> None:
    """Sample variance (ddof=1) matches statistics.variance."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    a = Variance("v")
    s = a.create_accumulator()
    for v in values:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(statistics.variance(values))


def test_std_matches_statistics() -> None:
    """Sample stdev matches statistics.stdev."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    a = Std("v")
    s = a.create_accumulator()
    for v in values:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(statistics.stdev(values))


def test_mean_chan_merge_matches_single_pass() -> None:
    """Chan's parallel mean is exact for arbitrary splits."""
    values = [float(i) for i in range(1, 101)]
    a = Mean("v")
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

    assert a.extract_output(merged) == pytest.approx(a.extract_output(single))


def test_variance_chan_merge_matches_single_pass() -> None:
    """Chan's parallel variance is exact for arbitrary splits."""
    values = [float(i) for i in range(1, 101)]
    a = Variance("v")
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

    assert a.extract_output(merged) == pytest.approx(a.extract_output(single))


def test_std_merge_consistent() -> None:
    """Std = sqrt(Variance); merge consistency."""
    values = [float(i) for i in range(1, 51)]
    a = Std("v")
    single = a.create_accumulator()
    for v in values:
        single = a.add_input(single, v)

    left = a.create_accumulator()
    for v in values[:10]:
        left = a.add_input(left, v)
    right = a.create_accumulator()
    for v in values[10:]:
        right = a.add_input(right, v)
    merged = a.merge_accumulators(left, right)
    assert a.extract_output(merged) == pytest.approx(a.extract_output(single))


def test_single_value_variance_is_nan() -> None:
    """Sample variance of one value is undefined -> NaN."""
    a = Variance("v")
    s = a.create_accumulator()
    s = a.add_input(s, 42.0)
    assert math.isnan(a.extract_output(s))


def test_empty_extract_returns_nan() -> None:
    """Mean of an empty accumulator is NaN, not zero."""
    a = Mean("v")
    assert math.isnan(a.extract_output(a.create_accumulator()))


def test_canonical_forms() -> None:
    """canonical_form()['kind'] matches the registered name."""
    assert Mean("loss").canonical_form()["kind"] == "Mean"
    assert Variance("loss").canonical_form()["kind"] == "Variance"
    assert Std("loss").canonical_form()["kind"] == "Std"
