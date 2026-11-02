# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A walk-through names the operation the model wrote, not a kernel's symbol.

A ``when`` over a per-period column lowers to the ``list_conditional``
kernel, a power with a per-period side to ``list_pow``, and a per-period
``clip`` to ``list_clip``. The walk-through's first line is the engine's
rendering, cleaned, and the cleaning stripped every ``.list`` it met -- the
namespace it meant, and the first five letters of each kernel's name with
it. So a line written ``when(af.duration > 1).then(af.sum_assured)
.otherwise(0.0)`` opened ``duration_conditional(1, sum_assured, 0)``: a
function that exists nowhere, with the comparison gone and the operand fused
into the name so that its values were never put in. Each kernel is now
written as the operation it computes -- the ``when`` with its comparison,
``.pow``, ``.clip`` -- in the record's rendering and so in the walk-through
read off it.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph.calc_graph import GraphExporter
from gaspatchio.frame.graph.validate import validate_artifact
from gaspatchio.frame.lowering._polars.plugins import list_conditional
from gaspatchio.frame.lowering._polars.rendering import (
    conditional_comparisons,
    kernels_as_operations,
)


def _exported() -> dict[str, Any]:
    """Export a one-policy projection with each list kernel on one line."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "sum_assured": [100_000.0],
                "term": [3],
                "lo": [2.0],
                "hi": [4.0],
            }
        )
    )
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    af.duration = af.month + 1
    af.flag = when(af.duration > 1).then(af.sum_assured).otherwise(0.0)
    af.banded = (
        when(af.duration <= af.term)
        .then(1.0)
        .otherwise(when(af.duration >= 5).then(3.0).otherwise(2.0))
    )
    af.t = af.duration * 1.0
    af.squared = af.t**2
    af.factor = 1.01**af.t
    af.capped = af.t.clip(af.lo, af.hi)
    frame = af.collect()
    document: dict[str, Any] = json.loads(
        GraphExporter(af).export(frame, include_lowered=True)
    )
    return document


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """Return the export, once for the module."""
    return _exported()


def _steps(document: dict[str, Any], node_id: str) -> list[dict[str, Any]]:
    node = next(one for one in document["nodes"] if one["id"] == node_id)
    steps: list[dict[str, Any]] = node["trace"]
    return steps


def test_a_per_period_when_opens_on_the_when_with_its_comparison(
    document: dict[str, Any],
) -> None:
    """The comparison is back, and the operand is substituted again."""
    steps = _steps(document, "flag@1")

    assert steps[0]["expr"] == ".when((duration) > (1)).then(sum_assured).otherwise(0)"
    assert steps[1]["expr"].startswith(".when((([1, 2, 3, ‥, 7])) > (1))")
    assert "duration" in steps[1]["values"]


def test_a_nested_when_writes_each_comparison_against_its_own_call(
    document: dict[str, Any],
) -> None:
    """Two calls, two comparisons, each where the model wrote it."""
    opening = _steps(document, "banded@1")[0]["expr"]

    assert opening == (
        ".when((duration) <= (term)).then(1)"
        ".otherwise(.when((duration) >= (5)).then(3).otherwise(2))"
    )


@pytest.mark.parametrize(
    ("node_id", "opening"),
    [("squared@1", "t.pow(2)"), ("capped@1", "t [clipped]")],
)
def test_a_power_and_a_clip_name_the_method_and_not_the_kernel(
    document: dict[str, Any], node_id: str, opening: str
) -> None:
    """``list_pow`` reads as ``.pow``, ``list_clip`` as the clip it is."""
    assert _steps(document, node_id)[0]["expr"] == opening


def test_no_walk_through_names_a_kernel_or_fuses_a_name_into_one(
    document: dict[str, Any],
) -> None:
    """No ``list_`` symbol, and no ``…_conditional`` that exists nowhere."""
    for node in document["nodes"]:
        for step in node.get("trace") or []:
            assert "list_" not in step["expr"], (node["id"], step["expr"])
            assert "_conditional" not in step["expr"], (node["id"], step["expr"])
            assert "_pow" not in step["expr"], (node["id"], step["expr"])


def test_the_walk_through_and_the_rendering_beside_it_still_tell_one_story(
    document: dict[str, Any],
) -> None:
    """The opening is the rendering cleaned, which the validator reads."""
    verdict = validate_artifact(document)

    assert verdict.ok
    assert not [one for one in verdict.findings if "opens on" in one.message]


def test_comparisons_are_read_in_the_order_the_rendering_writes_the_calls() -> None:
    """Receiver first, then the call, then its other arguments."""
    inner = list_conditional(pl.col("a"), pl.lit(1), pl.lit(1.0), pl.lit(0.0), "lt")
    outer = list_conditional(inner, pl.lit(0.5), pl.lit(9.0), pl.col("b"), "gte")
    nested = list_conditional(
        pl.col("c"),
        pl.lit(2),
        pl.lit(1.0),
        list_conditional(pl.col("c"), pl.lit(3), pl.lit(2.0), pl.lit(3.0), "eq"),
        "ne",
    )

    assert conditional_comparisons(outer) == ("lt", "gte")
    assert conditional_comparisons(nested) == ("ne", "eq")


@pytest.mark.parametrize(
    "comparisons",
    [None, (), ("gt", "lt"), ("approximately",)],
    ids=["unread", "none-for-the-call", "one-too-many", "unknown"],
)
def test_a_conditional_without_its_comparison_keeps_the_kernel_s_name(
    comparisons: tuple[str, ...] | None,
) -> None:
    """A ``when`` with a guessed comparison is worse than the kernel's name."""
    text = 'col("d").list_conditional([dyn int: 1, col("sa"), dyn float: 0])'

    assert kernels_as_operations(text, comparisons) == text


def test_a_kernel_name_inside_a_string_is_text() -> None:
    """A column literally named after a kernel call is the author's, untouched."""
    text = 'col("x.list_pow(").alias("y.list_conditional(")'

    assert kernels_as_operations(text, ()) == text


def test_a_decimal_before_a_kernel_keeps_its_digits(document: dict[str, Any]) -> None:
    """``1.01 ** t`` reads ``1.01``: the path scrub no longer eats the ``01.``."""
    assert ".then(1.01.pow(t))" in _steps(document, "factor@1")[0]["expr"]
