# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A column shock whose condition selects no policy of the book is refused by name.

``FilteredShock(..., where={"sex": "f"}, column="sa")`` over a book whose
policies hold ``"F"`` and ``"M"`` moved nothing and folded as BASE to the
bit, with no word. A table shock whose condition selects no row of its table
is already refused for the same reason; the column face now is too, naming
the condition and what the book holds, and saying the cost: a plan run on a
sample book that lacks the segment is refused, naming the condition.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import ScenarioRun, Sum, for_each_scenario
from gaspatchio.scenarios.shocks import FilteredShock, MultiplicativeShock

_BOOK = pl.DataFrame(
    {"pid": [1, 2, 3], "sex": ["M", "M", "F"], "sa": [100.0, 200.0, 300.0]}
)


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af.claim = af.sa * 0.01
    return af


def _shock(where: dict[str, object]) -> FilteredShock:
    return FilteredShock(
        shock=MultiplicativeShock(factor=2.0), where=where, column="sa"
    )


def _each(where: dict[str, object]) -> float:
    result = for_each_scenario(
        ActuarialFrame(_BOOK),
        {"BASE": [], "UP": [_shock(where)]},
        _model,
        aggregations=[Sum("claim").alias("c")],
        batch_size=1,
    )
    return result.aggregations["c"]


def test_a_condition_no_policy_meets_is_refused_naming_it_and_the_book() -> None:
    with pytest.raises(ValueError, match="no policy of the book") as refused:
        _each({"sex": "f"})

    said = str(refused.value)
    assert "where={'sex': 'f'}" in said
    assert "'sex' holds 'F', 'M'" in said
    assert "sample book that lacks the segment" in said


def test_the_same_refusal_on_a_scenario_plan() -> None:
    plan = ScenarioRun(
        shocks={"BASE": [], "UP": [_shock({"sex": "f"})]},
        aggregations=(Sum("claim").alias("c").over("scenario_id"),),
    )
    with pytest.raises(ValueError, match="no policy of the book"):
        plan.run(ActuarialFrame(_BOOK), _model, batch_size=3)


def test_a_condition_on_a_column_the_book_lacks_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match=r"holds no column 'sexx'.*Did you mean 'sex'"):
        _each({"sexx": "F"})


def test_a_condition_that_selects_policies_still_moves_them() -> None:
    # BASE 6.0 plus UP 3.0 + 6.0 on the one female policy (300 x 2 x 0.01).
    assert _each({"sex": "F"}) == pytest.approx(6.0 + 9.0)
