# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A shared projection grid sized from the rows is refused where they are not the book.

``projection.set(..., per_policy=False)`` over a horizon the rows decide --
a maximum age measured against the youngest issue age, a term column, a
term expression, or a number of years named by a column -- lays one grid
whose length is read from the rows in the frame. In a batch runner that is
the batch, and on a scenario axis every scenario's copy of the book, so the
policy's value moved with which other policies shared its batch: a 70-year-
old's annuity-due to age 100 was 17,778.09 beside a 50-year-old (run on to
age 120) and 17,028.46 alone, so ``run_aggregated`` totalled 41,877.42 at
``batch_size=2`` and 41,127.79 at ``batch_size=1``. The grid is a read across
rows, and it is now refused exactly where one is, naming the grid and the
routes; where the frame is the book -- ``collect()``, one batch -- it stands.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated, run_to_parquet
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import MultiplicativeShock, ScenarioRun, Sum, with_scenarios

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

VALUATION = datetime.date(2025, 1, 1)
BOOK = pl.DataFrame(
    {
        "policy_id": ["P50", "P70"],
        "issue_age": [50, 70],
        "term_y": [5, 10],
        "lapse_adj": [1.0, 1.0],
    }
)

_Q = [min(1.0, 0.00004 * 1.1 ** (age - 18)) for age in range(18, 121)]
_MORTALITY = Table(
    name="w5r_shared_grid_annuity",
    source=pl.DataFrame({"age": list(range(18, 121)), "qx": _Q}),
    dimensions={"age": "age"},
    value="qx",
)


def _annuity_due(issue_age: int, to_age: int) -> float:
    """Return 1,000 a year in advance from ``issue_age`` to ``to_age``, at 3%."""
    survival, value = 1.0, 0.0
    for k, age in enumerate(range(issue_age, to_age + 1)):
        value += 1000 * survival / 1.03**k
        survival *= 1 - _Q[age - 18]
    return value


def maximum_age_on_one_grid(af: ActuarialFrame) -> ActuarialFrame:
    """Value a life annuity-due to age 100 on one grid sized from the youngest life."""
    af = af.projection.set(
        valuation_date=VALUATION,
        until="maximum_age",
        until_value=100,
        frequency="annual",
        per_policy=False,
    )
    af.att = af.issue_age + af.month // 12
    af.qx = _MORTALITY.lookup(age=af.att)
    af.surv = af.qx.projection.cumulative_survival()
    af.pv = (af.surv * 1000.0 * af.lapse_adj).projection.prospective_value(
        discount_rate=0.03, timing="beginning_of_period"
    )
    af.pv0 = af.pv.list.get(0)
    return af


def _level(
    until: str, until_value: object, **extra: object
) -> Callable[..., ActuarialFrame]:
    """1,000 at every boundary of the grid, undiscounted."""

    def model(af: ActuarialFrame) -> ActuarialFrame:
        af = af.projection.set(
            valuation_date=VALUATION,
            until=until,  # type: ignore[arg-type]
            until_value=until_value,  # type: ignore[arg-type]
            frequency="annual",
            **extra,  # type: ignore[arg-type]
        )
        af.cf = af.month * 0.0 + 1000.0 * af.lapse_adj
        af.pv = af.cf.projection.prospective_value(
            discount_rate=0.0, timing="beginning_of_period"
        )
        af.pv0 = af.pv.list.get(0)
        return af

    return model


# Hand values: on one grid sized from the longest term (10 years, 11
# boundaries) each policy is 11 x 1,000; alone, the 5-year policy is 6,000.
FORMS: dict[str, tuple[Callable[..., ActuarialFrame], list[float]]] = {
    "maximum_age": (
        maximum_age_on_one_grid,
        [_annuity_due(50, 100), _annuity_due(70, 120)],
    ),
    "term-column": (
        _level("term_years", "term_y", per_policy=False),
        [11000.0, 11000.0],
    ),
    "term-expression": (_level("term_years", pl.col("term_y")), [11000.0, 11000.0]),
}


def test_the_hand_values() -> None:
    assert _annuity_due(70, 100) == pytest.approx(17028.4564, abs=1e-4)
    assert _annuity_due(70, 120) == pytest.approx(17778.0869, abs=1e-4)
    assert _annuity_due(50, 100) == pytest.approx(24099.3288, abs=1e-4)


@pytest.mark.parametrize("form", list(FORMS))
def test_the_book_in_one_frame_keeps_its_shared_grid(form: str) -> None:
    model, hand = FORMS[form]

    assert model(ActuarialFrame(BOOK)).collect()["pv0"].to_list() == pytest.approx(hand)
    whole = run_aggregated(model, BOOK, [Sum("pv0").alias("pv0")], batch_size=2)
    assert whole.pv0 == pytest.approx(sum(hand))


@pytest.mark.parametrize("form", list(FORMS))
@pytest.mark.parametrize("size", [1, "auto"])
def test_a_batch_runner_cutting_the_book_refuses_the_grid(
    form: str, size: int | str
) -> None:
    model, _ = FORMS[form]
    with pytest.raises(ValueError, match="lays one shared grid") as refused:
        run_aggregated(model, BOOK, [Sum("pv0").alias("pv0")], batch_size=size)  # type: ignore[arg-type]
    message = str(refused.value)

    assert "run_aggregated cuts the 2 policies into batches" in message
    assert "here those are the batch" in message
    assert "before the run" in message
    assert "one batch" in message


def test_run_to_parquet_refuses_the_grid_when_it_cuts_the_book(tmp_path: Path) -> None:
    model, hand = FORMS["term-column"]
    with pytest.raises(ValueError, match="run_to_parquet cuts the 2 policies"):
        run_to_parquet(model, BOOK, output_dir=tmp_path / "cut", batch_size=1)
    run_to_parquet(model, BOOK, output_dir=tmp_path / "whole", batch_size=2)
    assert pl.read_parquet(tmp_path / "whole" / "*.parquet")["pv0"].to_list() == hand


@pytest.mark.parametrize("form", list(FORMS))
def test_a_scenario_axis_refuses_the_grid(form: str) -> None:
    model, _ = FORMS[form]
    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "UP": [MultiplicativeShock(factor=1.1, column="lapse_adj")],
        },
        aggregations=(Sum("pv0").alias("pv0").over("scenario_id"),),
    )
    with pytest.raises(ValueError, match="lays one shared grid") as refused:
        plan.run(ActuarialFrame(BOOK), model, batch_size=1)
    assert "every scenario's copy of every policy" in str(refused.value)

    with pytest.raises(ValueError, match="this frame carries a scenario axis"):
        model(with_scenarios(ActuarialFrame(BOOK), ["BASE", "UP"]))


def test_the_refusal_names_the_grid_and_what_sizes_it() -> None:
    expected = {
        "maximum_age": (
            "projection.set(until='maximum_age', until_value=100, per_policy=False)",
            "the smallest 'issue_age'",
            "leave per_policy at its default",
        ),
        "term-column": (
            (
                "projection.set(until='term_years', until_value='term_y', "
                "per_policy=False)"
            ),
            "the largest 'term_y'",
            "until_value=int(model_points['term_y'].max())",
        ),
    }
    for form, fragments in expected.items():
        with pytest.raises(ValueError, match="lays one shared grid") as refused:
            run_aggregated(
                FORMS[form][0], BOOK, [Sum("pv0").alias("pv0")], batch_size=1
            )
        for fragment in fragments:
            assert fragment in str(refused.value), (form, fragment)


def test_a_grid_laid_before_the_cross_join_stands() -> None:
    af = ActuarialFrame(BOOK).projection.set(
        valuation_date=VALUATION,
        until="term_years",
        until_value="term_y",
        frequency="annual",
        per_policy=False,
    )
    crossed = with_scenarios(af, ["BASE", "UP"]).collect()
    assert crossed["num_proj_months"].to_list() == [11, 11, 11, 11]


@pytest.mark.parametrize(
    ("until", "until_value", "extra"),
    [
        ("maximum_age", 100, {}),
        ("term_years", "term_y", {}),
        ("term_years", 5, {"per_policy": False}),
    ],
    ids=["maximum-age-per-policy", "term-column-per-policy", "term-number"],
)
def test_an_axis_whose_length_the_rows_do_not_set_runs_in_batches(
    until: str, until_value: object, extra: dict[str, object]
) -> None:
    one = run_aggregated(
        _level(until, until_value, **extra),
        BOOK,
        [Sum("pv0").alias("pv0")],
        batch_size=1,
    )
    two = run_aggregated(
        _level(until, until_value, **extra),
        BOOK,
        [Sum("pv0").alias("pv0")],
        batch_size=2,
    )
    assert one.pv0 == pytest.approx(two.pv0)
