# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario plan's shock moves exactly the target it names, or the plan refuses.

Each of these used to produce a number without a word: a shock with no
target moved every base table, a shock naming a table the run does not hold
(or the model never reads) left its scenario equal to BASE, and an inner
shock's own table was ignored. The model is the reconciled ``main(af)``,
reading its own tables; the plan answers those reads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import (
    AdditiveShock,
    MultiplicativeShock,
    PipelineShock,
    ScenarioRun,
    Sum,
    for_each_scenario,
)

if TYPE_CHECKING:
    from gaspatchio.scenarios import ScenarioResult


def _table(name: str, value: float) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": [30, 31], "q": [value, value]}),
        dimensions={"age": "age"},
        value="q",
    )


def _mort() -> Table:
    return _table("w2i_mort", 0.01)


def _lapse() -> Table:
    return _table("w2i_lapse", 0.05)


@pytest.fixture
def bases() -> dict[str, Table]:
    return {"w2i_mort": _mort(), "w2i_lapse": _lapse()}


@pytest.fixture
def book() -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [30]}))


_AGGS = (
    Sum("q").alias("q").over("scenario_id"),
    Sum("w").alias("w").over("scenario_id"),
)


def _reads_both(af: ActuarialFrame) -> ActuarialFrame:
    af.q = _mort().lookup(age=af.age)
    af.w = _lapse().lookup(age=af.age)
    return af


def _by_scenario(result: ScenarioResult, alias: str) -> dict[str, float]:
    return dict(result.aggregations[alias].iter_rows())


# --- 1. a shock with no target no longer moves every table -------------------


def test_an_untargeted_shock_is_refused_naming_the_tables(
    bases: dict[str, Table],
) -> None:
    with pytest.raises(ValueError, match="names no target") as info:
        ScenarioRun(
            shocks={"BASE": [], "UP": [MultiplicativeShock(factor=2.0)]},
            base_tables=bases,
            aggregations=_AGGS,
        )
    assert "'w2i_lapse', 'w2i_mort'" in str(info.value)
    assert "column=" in str(info.value)


def test_an_untargeted_shock_is_refused_by_for_each_scenario(
    book: ActuarialFrame,
) -> None:
    with pytest.raises(ValueError, match="names no target"):
        for_each_scenario(
            book,
            {"BASE": [], "UP": [MultiplicativeShock(factor=2.0)]},
            _reads_both,
            aggregations=_AGGS,
            batch_size=2,
        )


def test_a_targeted_shock_moves_only_its_table(book: ActuarialFrame) -> None:
    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "UP": [MultiplicativeShock(factor=2.0, table="w2i_mort")],
        },
        aggregations=_AGGS,
    )
    result = plan.run(book, _reads_both, batch_size=2)
    assert _by_scenario(result, "q") == pytest.approx({"BASE": 0.01, "UP": 0.02})
    assert _by_scenario(result, "w") == pytest.approx({"BASE": 0.05, "UP": 0.05})


# --- 2. a shock on a table the plan does not state, or no read reaches -------


def test_a_misspelled_table_is_refused_with_a_suggestion(
    bases: dict[str, Table],
) -> None:
    with pytest.raises(ValueError, match="Did you mean 'w2i_mort'") as info:
        ScenarioRun(
            shocks={"TYPO": [MultiplicativeShock(factor=2.0, table="w2i_mortt")]},
            base_tables=bases,
            aggregations=_AGGS,
        )
    assert "'w2i_lapse', 'w2i_mort'" in str(info.value)


def test_a_plan_without_tables_checks_its_targets_against_the_reads(
    book: ActuarialFrame,
) -> None:
    recipe = ScenarioRun(
        shocks={"TYPO": [MultiplicativeShock(factor=2.0, table="w2i_mortt")]},
        aggregations=_AGGS,
    )
    assert recipe.describe()  # a recipe can still be described and written down
    with pytest.raises(ValueError, match="no read in the model") as info:
        recipe.run(book, _reads_both, batch_size=1)
    assert "Did you mean 'w2i_mort'" in str(info.value)


def test_a_shocked_table_the_model_never_reads_is_refused(
    book: ActuarialFrame,
) -> None:
    def reads_mort_only(af: ActuarialFrame) -> ActuarialFrame:
        af.q = _mort().lookup(age=af.age)
        af.w = af.q * 0.0
        return af

    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "UP": [MultiplicativeShock(factor=2.0, table="w2i_lapse")],
        },
        aggregations=_AGGS,
    )
    for batch_size in (1, 2):
        with pytest.raises(ValueError, match="no read in the model reached") as info:
            plan.run(book, reads_mort_only, batch_size=batch_size)
        assert "The model read: 'w2i_mort'" in str(info.value)


def test_an_inner_shock_naming_another_table_is_refused(
    bases: dict[str, Table],
) -> None:
    pipeline = PipelineShock(
        shocks=(MultiplicativeShock(factor=2.0, table="w2i_lapse"),),
        table="w2i_mort",
    )
    with pytest.raises(ValueError, match="inner MultiplicativeShock names table"):
        ScenarioRun(shocks={"X": [pipeline]}, base_tables=bases, aggregations=_AGGS)


def test_an_inner_shock_repeating_its_outer_target_is_accepted(
    book: ActuarialFrame,
) -> None:
    pipeline = PipelineShock(
        shocks=(MultiplicativeShock(factor=2.0, table="w2i_mort"),),
        table="w2i_mort",
    )
    plan = ScenarioRun(shocks={"BASE": [], "X": [pipeline]}, aggregations=_AGGS)
    result = plan.run(book, _reads_both, batch_size=2)
    assert _by_scenario(result, "q") == pytest.approx({"BASE": 0.01, "X": 0.02})


def test_a_non_shock_in_a_plan_is_refused_with_the_column_move(
    bases: dict[str, Table],
) -> None:
    with pytest.raises(TypeError, match="column='valuation_rate'"):
        ScenarioRun(
            shocks={"P": [("rate", "add", 0.01)]},  # type: ignore[list-item]
            base_tables=bases,
            aggregations=_AGGS,
        )


# --- a column shock on a column no line reads (W5 A-F4) -----------------------


def _rate_book() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "sa": [100.0, 200.0],
                "valuation_rate": [0.03, 0.03],
                "unused_col": [1.0, 2.0],
            }
        )
    )


_PV = (Sum("pv").alias("pv").over("scenario_id"),)


def _discounts_at_a_literal(af: ActuarialFrame) -> ActuarialFrame:
    """Discount at the basis rate written as a number, as a conversion may leave it."""
    af.pv = af.sa / (1.0 + 0.03)
    return af


def _discounts_at_the_column(af: ActuarialFrame) -> ActuarialFrame:
    af.pv = af.sa / (1.0 + af.valuation_rate)
    return af


@pytest.mark.parametrize("batch_size", [1, 2])
def test_a_shocked_column_no_line_reads_is_refused_naming_what_is_read(
    batch_size: int,
) -> None:
    """The skill's own RATE_UP example over a model that discounts at a literal."""
    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "RATE_UP_100BP": [AdditiveShock(delta=0.01, column="valuation_rate")],
        },
        aggregations=_PV,
    )
    with pytest.raises(ValueError, match="would equal BASE") as info:
        plan.run(_rate_book(), _discounts_at_a_literal, batch_size=batch_size)
    said = str(info.value)
    assert "model-point column 'valuation_rate'" in said
    assert "'sa' (at test_shock_targets_refused.py:" in said


def test_a_shocked_column_the_model_reads_still_moves_its_scenario() -> None:
    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "RATE_UP_100BP": [AdditiveShock(delta=0.01, column="valuation_rate")],
        },
        aggregations=_PV,
    )
    result = plan.run(_rate_book(), _discounts_at_the_column, batch_size=2)
    assert _by_scenario(result, "pv") == pytest.approx(
        {"BASE": 300.0 / 1.03, "RATE_UP_100BP": 300.0 / 1.04}
    )


def test_a_shocked_column_an_aggregation_folds_is_not_refused() -> None:
    """Summing the shocked column itself is a scenario that differs from BASE."""
    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "UP": [MultiplicativeShock(factor=2.0, column="unused_col")],
        },
        aggregations=(*_PV, Sum("unused_col").alias("u").over("scenario_id")),
    )
    result = plan.run(_rate_book(), _discounts_at_a_literal, batch_size=2)
    assert _by_scenario(result, "u") == pytest.approx({"BASE": 3.0, "UP": 6.0})


def test_a_model_that_rebuilds_its_frame_is_not_second_guessed() -> None:
    """A collect and a new frame start a new record; reads before it are not on it.

    Run one scenario a batch: a batch crossing two scenarios judges the
    rebuild against its crossed frame (section 13.2), and the renamed column is one
    that frame did not hold, so it is refused there by name.
    """

    def renames_then_reads(af: ActuarialFrame) -> ActuarialFrame:
        points = af.collect().with_columns(pl.col("valuation_rate").alias("rate"))
        af = ActuarialFrame(points)
        af.pv = af.sa / (1.0 + af.rate)
        return af

    plan = ScenarioRun(
        shocks={"BASE": [], "UP": [AdditiveShock(delta=0.01, column="valuation_rate")]},
        aggregations=_PV,
    )
    result = plan.run(_rate_book(), renames_then_reads, batch_size=1)
    assert _by_scenario(result, "pv") == pytest.approx(
        {"BASE": 300.0 / 1.03, "UP": 300.0 / 1.04}
    )
    with pytest.raises(ValueError, match="holds 'rate', which the batch did not hold"):
        plan.run(_rate_book(), renames_then_reads, batch_size=2)
