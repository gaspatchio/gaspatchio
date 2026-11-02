# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""No period outside the window an aggregation's edge states reaches this engine.

Section 9 has every aggregation read state its window, quoted from the
identifier's own attributes, and a window is a bound: an operand moved
outside it moves no period of the answer. That is a claim about every
engine, not about the producer, so the kit's perturbation vectors
(``vectors/windows.json``) run here as well. Each moved case is the base case
beside it with one cell of one operand moved. The case's own expected answer
is checked to the bit by ``test_vectors.py``; what this file checks is the
relation between this engine's two answers -- every period the window
excludes stands where it stood, every other policy stands where it stood, and
something inside the window moved.

A padded bucket is where this would break first. A policy shorter than the
bucket it is run in has cells nobody projected, and a fold that read across
the padding would move a short policy's answer when a long policy's operand
moved -- which is the other-policy half of the check.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from gaspatchio.engines.protocol import FrameSink
from gaspatchio_jax.engine import JaxEngine
from gaspatchio_jax.lowerings import load
from gaspatchio_jax.vectors import normalise
from tests.conftest import vectors_directory

_BUNDLE = "windows.json"


def _cases() -> dict[str, dict[str, Any]]:
    bundle = json.loads((vectors_directory() / _BUNDLE).read_text(encoding="utf-8"))
    return {case["id"]: case for case in bundle["cases"]}


def _moved() -> list[dict[str, Any]]:
    return [case for case in _cases().values() if "perturbation" in case]


def _answer(case: dict[str, Any]) -> list[Any]:
    """Return this engine's answer to one case, as the run reports it."""
    load()
    invocation = normalise(case, _BUNDLE)
    result = JaxEngine().run(invocation.document, invocation.inputs, FrameSink())
    return result.columns[str(invocation.resources["output_column"])].to_list()


def _covered(window: dict[str, Any], period: int | None, length: int) -> set[int]:
    """Return the operand periods ``window`` covers for one period of the answer."""
    if "position" in window:
        at = window["position"]
        return {at if at >= 0 else length + at}
    here = period or 0
    ends = []
    for bound in (window["periods"]["from"], window["periods"]["to"]):
        if bound == "first":
            ends.append(0)
        elif bound == "last":
            ends.append(length - 1)
        else:
            ends.append(here + bound)
    return set(range(max(ends[0], 0), min(ends[1], length - 1) + 1))


def _assert_held(case: dict[str, Any], before: list[Any], after: list[Any]) -> None:
    moved = case["perturbation"]
    policy, period = moved["policy"], moved["period"]
    length = len(case["inputs"][moved["operand"]]["values"][policy])
    assert [row for i, row in enumerate(after) if i != policy] == [
        row for i, row in enumerate(before) if i != policy
    ], "another policy's answer moved"
    was, now = before[policy], after[policy]
    pairs = (
        list(enumerate(zip(was, now, strict=True)))
        if isinstance(was, list)
        else [(None, (was, now))]
    )
    inside = [
        (old, new)
        for at, (old, new) in pairs
        if period in _covered(moved["window"], at, length)
    ]
    outside = [
        (at, old, new)
        for at, (old, new) in pairs
        if period not in _covered(moved["window"], at, length)
    ]
    assert all(old == new for _, old, new in outside), outside
    assert not inside or any(old != new for old, new in inside)


@pytest.mark.parametrize("case", _moved(), ids=lambda case: case["id"])
def test_moving_an_operand_outside_its_window_moves_nothing_on_jax(
    case: dict[str, Any],
) -> None:
    base = _cases()[case["perturbation"]["of"]]
    _assert_held(case, _answer(base), _answer(case))


def test_a_padded_policy_is_still_held_to_its_own_run() -> None:
    """The last of a three-period run is its period 2, inside a bucket of four."""
    case = _cases()["window-list-get-last-moved"]
    assert case["perturbation"] == {
        "of": "window-list-get-last",
        "operand": "x",
        "policy": 1,
        "period": 2,
        "window": {"position": -1},
    }
    assert _answer(case) == [8.0, 65.0]


def test_the_check_would_catch_an_engine_that_read_outside_the_window() -> None:
    """Not vacuous: an answer that moved at a period the window excludes fails."""
    case = _cases()["window-cum_sum-moved"]
    before = _answer(_cases()["window-cum_sum"])
    leaked = [list(row) for row in _answer(case)]
    leaked[0][1] += 1.0
    with pytest.raises(AssertionError):
        _assert_held(case, before, leaked)
