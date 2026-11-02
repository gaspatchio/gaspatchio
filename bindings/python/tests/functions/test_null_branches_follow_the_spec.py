# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period conditional's null branches answer as section 11.1.28 says.

"A null selected branch stays null; a null unselected branch does not
replace the selected value. Empty lists remain empty and null outer lists
remain null." The per-period kernel did otherwise, wherever its branches
were numbers:

- a per-policy ``then`` or ``otherwise`` null for one policy refused the
  whole run (``then_val at row 1 is null``), and ``.otherwise(None)``
  refused too;
- a ``then`` or ``otherwise`` list null for one policy answered that policy
  with an empty run, as if it had no periods;
- a null policy -- its per-period column null -- answered an empty run,
  and a comparison assigned as a value (``af.x > 1``) the same;
- a period whose UNselected list branch was null answered null.

Text branches already answered the spec's way, and so does Polars' own
``when``: the same frame with text branches is the oracle here.

A null *list* branch is a policy with no run, not a null value in each
period: section 11.1.28 makes the policy null whenever any run in the line
is null, selected or not, so P2's ``full`` nulls P2 wherever it stands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable

_ENGINES = ("streaming", "in-memory")


def _book() -> pl.DataFrame:
    """Three policies: P2 carries the nulls, P3's per-period column is null."""
    return pl.DataFrame(
        {
            "x": [[1.0, 2.0], [1.0, 2.0, 3.0], None],
            "v": [10.0, None, 30.0],
            "full": [[10.0, 20.0], None, [1.0]],
            "low": [[-1.0, -2.0], [-1.0, -2.0, -3.0], [-1.0]],
            "label": ["a", None, "c"],
            "labels": [["a", "b"], None, ["c"]],
        },
        schema={
            "x": pl.List(pl.Float64),
            "v": pl.Float64,
            "full": pl.List(pl.Float64),
            "low": pl.List(pl.Float64),
            "label": pl.String,
            "labels": pl.List(pl.String),
        },
    )


def _out(formula: Callable[[ActuarialFrame], object], engine: str) -> list[object]:
    af = ActuarialFrame(_book())
    af.out = formula(af)
    return af.collect(engine=engine)["out"].to_list()


# Each numeric case beside the same conditional with text branches, and the
# answer the spec gives: `x > 1` is false in period 0 and true after it.
_CASES: dict[str, tuple[Callable[[ActuarialFrame], object], list[object]]] = {
    "a null per-policy then": (
        lambda af: when(af.x > 1).then(af.v).otherwise(0.0),
        [[0.0, 10.0], [0.0, None, None], None],
    ),
    "a null per-policy otherwise": (
        lambda af: when(af.x > 1).then(0.0).otherwise(af.v),
        [[10.0, 0.0], [None, 0.0, 0.0], None],
    ),
    "a null literal otherwise": (
        lambda af: when(af.x > 1).then(af.low).otherwise(None),
        [[None, -2.0], [None, -2.0, -3.0], None],
    ),
    "a null then list": (
        lambda af: when(af.x > 1).then(af.full).otherwise(0.0),
        [[0.0, 20.0], None, None],
    ),
    "a null otherwise list": (
        lambda af: when(af.x > 1).then(af.low).otherwise(af.full),
        [[10.0, -2.0], None, None],
    ),
    "a null then list against a list": (
        lambda af: when(af.x > af.low).then(af.full).otherwise(af.low),
        [[10.0, 20.0], None, None],
    ),
    "a comparison assigned as a value": (
        lambda af: af.x > 1,
        [[0.0, 1.0], [0.0, 1.0, 1.0], None],
    ),
}


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize("case", list(_CASES), ids=list(_CASES))
def test_a_null_branch_answers_as_the_specification_says(
    case: str, engine: str
) -> None:
    """Null where a null branch is selected, the other branch where it is not."""
    formula, expected = _CASES[case]

    assert _out(formula, engine) == expected


@pytest.mark.parametrize("engine", _ENGINES)
def test_numbers_answer_where_text_answers(engine: str) -> None:
    """The text-branch path, which already followed the spec, is the oracle.

    Null where the null label is selected, the other label where it is not,
    and a null policy null: the same places as the numbers.
    """
    numbers = _out(lambda af: when(af.x > 1).then(af.v).otherwise(0.0), engine)
    text = _out(lambda af: when(af.x > 1).then(af.label).otherwise("z"), engine)
    assert text == [["z", "a"], ["z", None, None], None]
    assert [None if row is None else [v is None for v in row] for row in numbers] == [
        None if row is None else [v is None for v in row] for row in text
    ]

    numbers = _out(lambda af: when(af.x > 1).then(af.full).otherwise(0.0), engine)
    text = _out(lambda af: when(af.x > 1).then(af.labels).otherwise("z"), engine)
    assert [None if row is None else [v is None for v in row] for row in numbers] == [
        None if row is None else [v is None for v in row] for row in text
    ]


@pytest.mark.parametrize("engine", _ENGINES)
def test_an_empty_policy_still_answers_an_empty_run(engine: str) -> None:
    """A policy with no periods has nothing to select, null branch or not."""
    book = pl.DataFrame(
        {"x": [[], [1.0, 2.0]], "v": [None, 5.0]},
        schema={"x": pl.List(pl.Float64), "v": pl.Float64},
    )
    af = ActuarialFrame(book)
    af.out = when(af.x > 1).then(af.v).otherwise(0.0)

    assert af.collect(engine=engine)["out"].to_list() == [[], [0.0, 5.0]]


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_null_per_policy_condition_over_list_branches_is_null_per_period(
    engine: str,
) -> None:
    """A null scalar condition selects neither branch in each period."""
    book = pl.DataFrame(
        {"c": [True, None], "full": [[1.0, 2.0], [3.0, 4.0]]},
        schema={"c": pl.Boolean, "full": pl.List(pl.Float64)},
    )
    af = ActuarialFrame(book)
    af.out = when(af.c).then(af.full).otherwise(0.0)

    assert af.collect(engine=engine)["out"].to_list() == [[1.0, 2.0], [None, None]]


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_batch_of_null_policies_with_text_branches_is_still_text(engine: str) -> None:
    """Every policy null under text branches is a run of null policies of text.

    The kernel answered ``List(Null)`` where it declares ``List(String)``,
    because a batch of nulls gave its collector no inner type to infer.
    """
    book = pl.DataFrame(
        {"x": [None, None], "label": ["a", "b"]},
        schema={"x": pl.List(pl.Float64), "label": pl.String},
    )
    af = ActuarialFrame(book)
    af.out = when(af.x > 1).then(af.label).otherwise("z")

    out = af.collect(engine=engine)
    assert out.schema["out"] == pl.List(pl.String)
    assert out["out"].to_list() == [None, None]
