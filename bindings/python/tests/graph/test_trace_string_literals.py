# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A string literal in a walk-through, written as the model wrote it.

``af.is_profitable = when(af.profit > 0).then("Yes").otherwise("No")`` is the
first conditional a reader of this framework meets, and until this file
existed its walk-through opened on ``.when((profit) > (0)).then("Yes.otherwise("No``
-- every string literal in the line short of its closing quote and bracket.
An actuary opens the walk-through of a conditional to read which branch
fired and what the other one would have said; a literal cut off mid-word is
that reading taken away.

The cause was one pair of blind replacements in the cleaning that turns the
engine's rendering into a readable first line: the opening ``col("`` was
stripped, and then *every* ``")`` after it, which is the wrapper's own
closing pair on ``col("profit")`` and the literal's closing pair on
``.then("Yes")``. Three operations rendered a literal that way -- a
conditional with string branches, an equality against a string, a
concatenation with a string -- and the tests below are one per operation,
each holding every step the walk-through writes.

The last two tests hold the operations that were already right. A literal
inside the engine's bracketed argument list -- ``fill_null(["missing"])`` --
never met the ``")`` that did the damage, and a string accessor call carries
no literal at all. Both are here so that a later change to the cleaning
cannot fix one spelling of a literal by breaking the other.
"""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph.calc_graph import GraphExporter

_MODEL_POINTS: dict[str, list[Any]] = {
    "policy_id": ["POL001", "POL002", "POL003"],
    "sex": ["M", "F", "M"],
    "profit": [-95.0, 80.0, 1020.0],
    "band": ["a", None, "c"],
}


def _exported(af: ActuarialFrame) -> dict[str, dict[str, Any]]:
    """Export the frame's graph against its own collected values, by node id."""
    frame = af.collect()
    artifact = json.loads(GraphExporter(af).export(frame, None))
    return {node["id"]: node for node in artifact["nodes"]}


def _expressions(node: dict[str, Any]) -> list[str]:
    """Return the expression every step of one node's walk-through shows."""
    trace = node.get("trace")
    assert isinstance(trace, list), f"{node['id']} carries no walk-through"
    return [step["expr"] for step in trace]


def _a_book() -> ActuarialFrame:
    """Return three policies, the shape the broken literal was found on."""
    return ActuarialFrame(pl.DataFrame(_MODEL_POINTS))


def test_a_conditional_keeps_both_of_its_string_branches() -> None:
    """Both literals of a string-branched conditional survive every step."""
    af = _a_book()
    af.is_profitable = when(af.profit > 0).then("Yes").otherwise("No")

    node = _exported(af)["is_profitable@1"]

    assert _expressions(node) == [
        '.when((profit) > (0)).then("Yes").otherwise("No")',
        '.when(((-95)) > (0)).then("Yes").otherwise("No")',
        "No",
    ]


def test_an_equality_against_a_string_keeps_the_string_it_tests() -> None:
    """The literal an equality tests against is written out in full."""
    af = _a_book()
    af.is_male = af.sex == "M"

    node = _exported(af)["is_male@1"]

    assert _expressions(node) == [
        '(sex) == ("M").strict_cast(Float64)',
        '((M)) == ("M").strict_cast(Float64)',
        "1",
    ]


def test_a_concatenation_with_a_string_keeps_what_it_appends() -> None:
    """The literal a concatenation appends is written out in full."""
    af = _a_book()
    af.sex_marked = af.sex + "!"

    node = _exported(af)["sex_marked@1"]

    assert _expressions(node) == [
        '(sex) + ("!")',
        '((M)) + ("!")',
        "M!",
    ]


def test_a_string_filled_in_for_a_missing_value_reads_as_it_always_did() -> None:
    """A literal inside a bracketed argument list was right and stays right."""
    af = _a_book()
    af.band_filled = af.band.fill_null("missing")

    node = _exported(af)["band_filled@1"]

    assert _expressions(node) == [
        'band.fill_null("missing")',
        '(a).fill_null("missing")',
        "a",
    ]


def test_a_string_accessor_call_reads_as_it_always_did() -> None:
    """A call carrying no literal is untouched by the cleaning."""
    af = _a_book()
    af.sex_upper = af.sex.polars_native().str.to_uppercase()

    node = _exported(af)["sex_upper@1"]

    assert _expressions(node) == [
        "sex.str.to_uppercase()",
        "(M).str.to_uppercase()",
        "M",
    ]
