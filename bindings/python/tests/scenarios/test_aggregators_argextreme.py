# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test ArgMin/ArgMax - best-pair mergeable with lex tiebreak."""

from __future__ import annotations

from gaspatchio_core.scenarios._aggregators import ArgMax, ArgMin


def test_argmax_returns_scenario_id() -> None:
    """ArgMax returns the scenario_id at the max value."""
    a = ArgMax("v")
    s = a.create_accumulator()
    s = a.add_input(s, ("S1", 10.0))
    s = a.add_input(s, ("S2", 30.0))
    s = a.add_input(s, ("S3", 20.0))
    assert a.extract_output(s) == "S2"


def test_argmin_returns_scenario_id() -> None:
    """ArgMin returns the scenario_id at the min value."""
    a = ArgMin("v")
    s = a.create_accumulator()
    s = a.add_input(s, ("S1", 10.0))
    s = a.add_input(s, ("S2", 30.0))
    s = a.add_input(s, ("S3", 20.0))
    assert a.extract_output(s) == "S1"


def test_argmax_lex_tiebreak() -> None:
    """On equal values the smallest scenario_id wins."""
    a = ArgMax("v")
    s = a.create_accumulator()
    s = a.add_input(s, ("S2", 10.0))
    s = a.add_input(s, ("S1", 10.0))
    assert a.extract_output(s) == "S1"


def test_argmin_lex_tiebreak() -> None:
    """On equal values the smallest scenario_id wins for ArgMin too."""
    a = ArgMin("v")
    s = a.create_accumulator()
    s = a.add_input(s, ("S2", 10.0))
    s = a.add_input(s, ("S1", 10.0))
    assert a.extract_output(s) == "S1"


def test_argmax_merge_commutative() -> None:
    """merge(a, b) == merge(b, a) for ArgMax."""
    a = ArgMax("v")
    left = a.add_input(a.create_accumulator(), ("S1", 5.0))
    right = a.add_input(a.create_accumulator(), ("S2", 7.0))
    assert a.extract_output(a.merge_accumulators(left, right)) == "S2"
    assert a.extract_output(a.merge_accumulators(right, left)) == "S2"


def test_argmax_empty_extract_returns_none() -> None:
    """Empty state extracts to None."""
    a = ArgMax("v")
    assert a.extract_output(a.create_accumulator()) is None


def test_argmax_int_scenario_ids() -> None:
    """Integer scenario_ids work; lex tiebreak on equal values."""
    a = ArgMax("v")
    s = a.create_accumulator()
    s = a.add_input(s, (5, 100.0))
    s = a.add_input(s, (3, 100.0))
    assert a.extract_output(s) == 3


def test_argmax_canonical_form() -> None:
    """canonical_form lists kind, column, within."""
    cf = ArgMax("loss").canonical_form()
    assert cf["kind"] == "ArgMax"
    assert cf["column"] == "loss"
