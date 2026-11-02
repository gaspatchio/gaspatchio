# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A calculated column of a type the vocabulary cannot name, asked about.

``af.graph.holes()`` asks which columns the model cannot account for. A
calculated count -- ``pl.col("funds").list.len()``, ``pl.len()`` -- comes
back in Polars' unsigned index type, and ``pl.struct(...)`` comes back as a
struct; the artifact's vocabulary has a name for neither. That is a question
about the column's *type*, and the export answers it, by name, with the cast
that carries the value. It is not an answer to "is this column accounted
for?", and a calculation the frame recorded is accounted for whatever type
it produced.

The two doors a calculation comes through have to agree. ``select`` always
records the type it resolved; an assignment records it only once the frame
is wide enough for the cheap per-assignment type probe to run. So the
assignment on a narrow frame used to answer and the same assignment on a
wide one, like ``select``, used to refuse. All three are pinned here, beside
the export that still refuses each one.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio.frame.base import _INCREMENTAL_SCHEMA_MIN_COLS
from gaspatchio.frame.graph import GraphExporter, find_holes

# Each calculation, under the column name the model gives it.
CALCULATIONS: dict[str, tuple[str, pl.Expr]] = {
    "list-len": ("fund_count", pl.col("funds").list.len()),
    "pl-len": ("policy_count", pl.len()),
    "struct": ("terms", pl.struct("term", "premium")),
}

ROUTES = ("select", "narrow-assignment", "wide-assignment")


def _model_points(*, wide: bool) -> pl.DataFrame:
    """Return two policies, padded past the type probe's width when ``wide``."""
    data: dict[str, list[object]] = {
        "funds": [[1.0, 2.0], [3.0]],
        "term": [10, 20],
        "premium": [1200.0, 900.0],
    }
    if wide:
        for i in range(_INCREMENTAL_SCHEMA_MIN_COLS):
            data[f"padding_{i}"] = [0.0, 0.0]
    return pl.DataFrame(data)


def _calculated(route: str, case: str) -> tuple[ActuarialFrame, str]:
    """Return a frame that calculated ``case`` through ``route``, and its column."""
    column, expression = CALCULATIONS[case]
    af = ActuarialFrame(_model_points(wide=route == "wide-assignment"))
    if route == "select":
        return af.select(expression.alias(column)), column
    af[column] = expression
    return af, column


@pytest.mark.parametrize("case", list(CALCULATIONS))
@pytest.mark.parametrize("route", ROUTES)
def test_holes_answers_for_a_calculated_column_of_an_unnamed_type(
    route: str, case: str
) -> None:
    """The column is a recorded calculation, so it is no hole on any door."""
    af, _ = _calculated(route, case)

    assert af.graph.holes() == []
    assert find_holes(af) == []


@pytest.mark.parametrize("case", list(CALCULATIONS))
def test_select_and_assignment_give_holes_the_same_answer(case: str) -> None:
    """The two doors are one answer, whichever of them recorded the type."""
    answers = [_calculated(route, case)[0].graph.holes() for route in ROUTES]

    assert answers == [answers[0]] * len(ROUTES)


@pytest.mark.parametrize("case", list(CALCULATIONS))
@pytest.mark.parametrize("route", ROUTES)
def test_the_other_graph_questions_answer_too(route: str, case: str) -> None:
    """Every question that does not ask for the type answers without it."""
    af, column = _calculated(route, case)
    graph = af.graph
    node = f"{column}@1"

    assert graph.versions(column) == (node,)
    assert graph.latest(column) == node
    assert node in graph.trace(column)
    assert node in graph.affected(column)
    assert isinstance(graph.precedents(column), tuple)
    assert graph.dependents(column) == ()
    assert node in graph.tiers().engine_native
    assert graph.fingerprint().startswith("sha256:")


@pytest.mark.parametrize("case", list(CALCULATIONS))
@pytest.mark.parametrize("route", ROUTES)
def test_the_export_still_refuses_the_type_by_name(route: str, case: str) -> None:
    """The type question is the export's, and its refusal is unchanged.

    The export folded with nothing collected has no values to judge an
    unsigned count on, so it refuses the width as it always has, naming the
    column and ending with the cast that carries it.
    """
    af, column = _calculated(route, case)

    with pytest.raises(UnmappedDtypeError) as refused:
        GraphExporter(af).export()

    assert refused.value.column == column
    assert f"Column {column!r} has type" in str(refused.value)
    assert refused.value.move is not None
    assert refused.value.move in str(refused.value)


def test_a_struct_read_off_a_hole_is_not_mistaken_for_a_failed_batch() -> None:
    """A recorded struct with no type name is not a batch that never resolved.

    The fold tells a ``with_columns`` that failed by its untyped record. A
    struct the fold could not name is untyped in the inquiry's graph too,
    and the hole it reads must be given the hint a typed calculation's
    reading of it would get -- not one blaming a statement that never
    failed.
    """

    def reading_the_hole(expression: pl.Expr) -> str:
        af = ActuarialFrame(_model_points(wide=False))
        af._df = af._df.with_columns(pl.lit(0.5).alias("bonus_rate"))  # noqa: SLF001 -- the write past the doors is the subject
        af = af.select(expression.alias("derived"))
        (hole,) = af.graph.holes()
        assert hole.column == "bonus_rate"
        return hole.hint

    typed = reading_the_hole(pl.col("bonus_rate") * 2.0)
    unnamed = reading_the_hole(pl.struct("bonus_rate", "term"))

    assert unnamed == typed
