# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period exact comparison or whole-number clip grows with the lines written.

A per-period comparison of whole numbers reads each side four or five times
(its exact difference, the length guard, the kernel), and a per-period clip
of whole numbers by a bound read from a column reads the value and each
bound three times or more. Written into the plan at each read, a line nested
three deep was 58 kB and 15 kB of plan, growing geometrically. Each now holds
its operands once (``once.read_once``), and the record writes them back where
they are read, so the walk-through reads as the line written.
"""

from __future__ import annotations

from itertools import pairwise

import polars as pl

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph.graph_utils import clean_expression_string
from gaspatchio.frame.lowering._polars.rendering import conditional_comparisons


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "li": [[871, 5, 2**53 + 1], [3, 4, 5]],
            "lj": [[870, 6, 2**53], [3, 4, 6]],
            "j": [3, 4],
        }
    )


def _plan(af: ActuarialFrame, line: object) -> int:
    return len(str(af._convert_to_expr(line)))  # noqa: SLF001 - the plan is the case under test


def test_a_nested_exact_comparison_s_plan_grows_linearly() -> None:
    af = ActuarialFrame(_book())
    sizes = []
    line: object = af.li
    for _ in range(3):
        line = when(line > af.lj).then(7).otherwise(3)
        sizes.append(_plan(af, line))
    steps = [later - earlier for earlier, later in pairwise(sizes)]
    # Each level adds its own steps once: equal increments, not a ratio.
    assert max(steps) - min(steps) < sizes[0] / 4, sizes


def test_a_nested_whole_number_clip_s_plan_grows_linearly() -> None:
    af = ActuarialFrame(_book())
    sizes = []
    line: object = af.li
    for _ in range(3):
        line = line.clip(af.j - 1, af.j * 1000)  # type: ignore[attr-defined]
        sizes.append(_plan(af, line))
    steps = [later - earlier for earlier, later in pairwise(sizes)]
    assert max(steps) - min(steps) < sizes[0] / 4, sizes


def test_the_answers_are_the_exact_ones() -> None:
    af = ActuarialFrame(_book())
    af.above = when(af.li > af.lj).then(1).otherwise(0)
    out = af.collect()
    assert out["above"].to_list() == [[1, 0, 1], [0, 0, 0]]
    small = ActuarialFrame(pl.DataFrame({"li": [[871, 1, 9000]], "j": [3]}))
    small.held = small.li.clip(small.j - 1, small.j * 1000)
    assert small.collect()["held"].to_list() == [[871, 2, 3000]]


def test_the_record_writes_the_operands_back_where_they_are_read() -> None:
    af = ActuarialFrame(_book())
    line = when(when(af.li > af.lj).then(af.li).otherwise(af.lj) > af.lj).then(2)
    expr = af._convert_to_expr(line.otherwise(5))  # noqa: SLF001 - the record of the plan
    written = clean_expression_string(
        str(expr), comparisons=conditional_comparisons(expr)
    )
    assert "as_struct" not in written
    assert "operand_0" not in written
    assert "answer_as_written" not in written
    # Each operand is written back at each place it is read.
    assert written.count('col("lj")') >= 4
