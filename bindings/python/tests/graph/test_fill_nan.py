# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``fill_nan`` is a declared operation: the fill where a value is NaN, nowhere else.

A NaN is a value an arithmetic produced and cannot name -- zero over zero, an
assumption cell a spreadsheet left blank and a lookup built with
``on_missing="nan"`` answered. It is a different absence from a null, and
section 11.1.13 keeps the two apart: ``fill_nan`` replaces the NaN and leaves
a null as it is, which is ``fill_null``'s to fill. Until this operation was
declared, ``af.q0.fill_nan(0.0)`` was refused as an undeclared name and
``lookup(...).fill_nan(0.0)`` was refused for hiding the table inside engine
text, so the commonest clean-up of a lookup took two lines and an escape.

Over a whole number there is no NaN to replace, so every value stands, in the
type the value and the fill share. A Boolean, text or date value cannot hold a
NaN either, and there the clause states no answer and this producer refuses.
"""

from __future__ import annotations

import json
import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Call, Col, Lit
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.frame.graph.trace_voice import sentence_for

NAN = math.nan


def _same(actual: list, expected: list) -> bool:
    """Compare two runs where a NaN equals a NaN and a null equals a null."""
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_same(a, b) for a, b in zip(actual, expected, strict=True))
        )
    if isinstance(expected, float) and math.isnan(expected):
        return isinstance(actual, float) and math.isnan(actual)
    return actual == expected


def _filled(column: list, fill: object = 0.0, **others: list) -> list:
    af = ActuarialFrame(pl.DataFrame({"x": column, **others}))
    af.answer = af.x.fill_nan(af[fill] if isinstance(fill, str) else fill)
    return af.collect()["answer"].to_list()


def test_a_nan_is_replaced_and_every_number_beside_it_kept() -> None:
    """An infinity is a number an arithmetic named; only the NaN is filled."""
    answer = _filled([1.5, NAN, math.inf, -math.inf])
    assert answer == [1.5, 0.0, math.inf, -math.inf]


def test_a_null_is_the_other_absence_and_stays_null() -> None:
    assert _filled([NAN, None, 2.0]) == [0.0, None, 2.0]


def test_per_period_each_period_is_filled_and_a_null_outer_list_stays_null() -> None:
    answer = _filled(
        [[0.25, NAN, None], None, [NAN], []],
    )
    assert answer == [[0.25, 0.0, None], None, [0.0], []]


def test_a_per_policy_fill_column_fills_a_per_policy_value() -> None:
    assert _filled([NAN, 2.0], "by", by=[9.0, 8.0]) == [9.0, 2.0]


def test_a_per_policy_fill_column_reaches_every_nan_period_of_its_policy() -> None:
    answer = _filled([[NAN, 0.5, NAN, None], [0.25, NAN]], "by", by=[9.0, 8.0])
    assert answer == [[9.0, 0.5, 9.0, None], [0.25, 8.0]]


def test_a_per_period_fill_column_reaches_the_same_period_only() -> None:
    answer = _filled(
        [[NAN, 0.5, NAN], [0.25, NAN]],
        "by",
        by=[[1.0, 2.0, 3.0], [4.0, 5.0]],
    )
    assert answer == [[1.0, 0.5, 3.0], [0.25, 5.0]]


def test_the_fill_may_be_a_calculation() -> None:
    af = ActuarialFrame(pl.DataFrame({"x": [[NAN, 0.5]], "fill": [4.5]}))
    af.answer = af.x.fill_nan(af.fill * 2.0)
    assert af.collect()["answer"].to_list() == [[9.0, 0.5]]


def test_a_whole_number_holds_no_nan_and_stands_in_the_shared_type() -> None:
    """A decimal fill makes the answer a decimal; a whole fill keeps the integer."""
    af = ActuarialFrame(pl.DataFrame({"x": [1, -2, None], "xs": [[1, 2], [3], []]}))
    af.decimal = af.x.fill_nan(0.0)
    af.whole = af.x.fill_nan(0)
    af.periods = af.xs.fill_nan(0.0)
    out = af.collect()
    assert out["decimal"].dtype == pl.Float64
    assert out["decimal"].to_list() == [1.0, -2.0, None]
    assert out["whole"].dtype == pl.Int64
    assert out["whole"].to_list() == [1, -2, None]
    assert out["periods"].to_list() == [[1.0, 2.0], [3.0], []]


@pytest.mark.parametrize("column", [[True, False], ["a", "b"]], ids=["boolean", "text"])
def test_a_value_that_cannot_hold_a_nan_is_refused(column: list) -> None:
    """11.1.13 states no answer past the numbers, and the reference refuses.

    It refuses where the line is written, naming the value's kind, rather
    than in Polars' words when the frame runs.
    """
    af = ActuarialFrame(pl.DataFrame({"x": column}))
    with pytest.raises(TypeError, match="never holds a NaN"):
        af.answer = af.x.fill_nan(0.0)


def test_a_null_fill_is_not_the_declared_form_and_names_the_escape() -> None:
    """Turning a NaN into a null is written where the engine's meaning is."""
    af = ActuarialFrame(pl.DataFrame({"x": [NAN, 1.0]}))
    with pytest.raises(TypeError, match=r"polars_native\(\)\.fill_nan"):
        af.x.fill_nan(None)
    af.answer = af.x.polars_native().fill_nan(None)
    assert af.collect()["answer"].to_list() == [None, 1.0]


def test_the_escape_spelling_of_the_declared_form_is_pointed_at_it() -> None:
    """Two spellings of one calculation would record two different things."""
    af = ActuarialFrame(pl.DataFrame({"x": [NAN, 1.0]}))
    with pytest.raises(ValueError, match=r"Drop \.polars_native\(\) from this line"):
        af.x.polars_native().fill_nan(0.0)


def test_the_operation_is_recorded_with_the_fill_as_its_operand() -> None:
    af = ActuarialFrame(pl.DataFrame({"x": [NAN], "fill": [9.0]}))
    af.by_value = af.x.fill_nan(0.0)
    af.by_column = af.x.fill_nan(af.fill)
    trees = fold(af).op_trees
    assert trees["by_value@1"] == Call("fill_nan", (Col("x"), Lit(0.0)))
    assert trees["by_column@1"] == Call("fill_nan", (Col("x"), Col("fill")))


def test_a_value_fill_and_a_column_fill_are_two_digests() -> None:
    af = ActuarialFrame(pl.DataFrame({"x": [NAN], "fill": [0.0]}))
    af.by_value = af.x.fill_nan(0.0)
    af.by_column = af.x.fill_nan(af.fill)
    nodes = {
        node["column"]: node for node in json.loads(GraphExporter(af).export())["nodes"]
    }
    assert nodes["by_value"]["fingerprint"] != nodes["by_column"]["fingerprint"]


def test_fill_nan_and_fill_null_are_two_identifiers() -> None:
    """A null and a NaN are two absences, and the record keeps them apart."""
    af = ActuarialFrame(pl.DataFrame({"x": [NAN, None]}))
    af.nan_filled = af.x.fill_nan(0.0)
    af.null_filled = af.x.fill_null(0.0)
    out = af.collect()
    assert _same(out["nan_filled"].to_list(), [0.0, None])
    assert _same(out["null_filled"].to_list(), [NAN, 0.0])
    trees = fold(af).op_trees
    assert trees["nan_filled@1"].name == "fill_nan"  # type: ignore[union-attr]
    assert trees["null_filled@1"].name == "fill_null"  # type: ignore[union-attr]


def test_the_walk_through_says_what_it_fills() -> None:
    assert sentence_for(Call("fill_nan", (Col("q"), Lit(0.0))), None) == (
        "q, with 0.0 wherever a value is NaN"
    )


def test_a_lookup_cleaned_on_one_line_is_core_and_portable_to_jax() -> None:
    """The once-refused line, now one line: a core fill over a lookup, read by jax."""
    table = Table(
        name="lapse",
        source=pl.DataFrame({"duration": [1, 2, 3], "rate": [0.08, NAN, 0.04]}),
        dimensions={"duration": "duration"},
        value="rate",
        on_missing="nan",
    )
    af = ActuarialFrame(pl.DataFrame({"duration": [1, 2, 3]}))
    af.lapse_rate = table.lookup(duration=af.duration).fill_nan(0.0)
    assert af.collect()["lapse_rate"].to_list() == [0.08, 0.0, 0.04]

    artifact = json.loads(GraphExporter(af).export(profile="executable"))
    computed = [node for node in artifact["nodes"] if node["kind"] == "computed"]
    assert {node["tier"] for node in computed} == {"core"}
    assert all(node["engines"] == [] for node in computed)
    report = validate_artifact(artifact, engine="jax", deep=True)
    assert report.ok, report.findings
