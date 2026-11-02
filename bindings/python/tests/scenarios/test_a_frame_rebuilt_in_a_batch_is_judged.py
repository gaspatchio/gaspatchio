# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A frame the model rebuilds inside a batch is judged against the batch.

The 0.9 setup step collects the frame, works in plain Polars and builds a
fresh frame over the result. Work done there is outside the frame's record,
so the refusal of a read across rows never saw it: a share of the book
taken there (``sa / sa.max()``) was the batch's share, and ``run_aggregated``
returned 6000 at a batch size of 1 and 5000 at 2 where the book's figure is
3000, with nothing refused.

A batch runner that cuts the book into more than one batch holds the batch,
so it judges the frame the model builds against it. A DataFrame is values,
so it passes only where it is the batch's own; a LazyFrame keeps its
expressions, so it is judged on its plan. The refusal names the four ways to
write the model so that it runs in batches. Over the whole book -- one batch,
``collect()`` -- the setup is the book's work and stands.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import ScenarioRun, Sum, run_aggregated, run_to_parquet

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    Model = Callable[[ActuarialFrame], ActuarialFrame]

BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "sa": [100.0, 200.0, 600.0],
        "product": ["A", "B", "A"],
    }
)
SIDE = pl.DataFrame({"product": ["A", "B"], "load": [1.0, 1.2]})


def _priced(af: ActuarialFrame) -> ActuarialFrame:
    """1000 a period by the share ``v`` over two boundaries: pv = 2000 * v."""
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=1,
        frequency="monthly",
    )
    af.pv = (af.v * 1000.0 + af.month * 0.0).list.sum()
    return af


def _share(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns((pl.col("sa") / pl.col("sa").max()).alias("v"))


def _bare_share(af: ActuarialFrame) -> ActuarialFrame:
    return _priced(ActuarialFrame(_share(af.collect())))


def _continued_share(af: ActuarialFrame) -> ActuarialFrame:
    return _priced(ActuarialFrame(_share(af.collect()), continue_from=af))


def _bare_join(af: ActuarialFrame) -> ActuarialFrame:
    joined = af.collect().join(SIDE, on="product", how="left", maintain_order="left")
    return _priced(
        ActuarialFrame(
            joined.with_columns((pl.col("sa") * pl.col("load") / 600.0).alias("v"))
        )
    )


def _bare_filter(af: ActuarialFrame) -> ActuarialFrame:
    af = ActuarialFrame(af.collect().filter(pl.col("sa") > 150.0))
    return _priced(af.with_columns((pl.col("sa") / 600.0).alias("v")))


def _lazy_share(af: ActuarialFrame) -> ActuarialFrame:
    return _priced(
        ActuarialFrame(
            af._df.with_columns((pl.col("sa") / pl.col("sa").max()).alias("v"))  # noqa: SLF001
        )
    )


def _lazy_over_a_collect(af: ActuarialFrame) -> ActuarialFrame:
    return _priced(ActuarialFrame(_share(af.collect()).lazy()))


# Hand values: the shares are 100/600, 200/600 and 600/600 of the book's
# largest sum assured, 2000 a share: 1000/3 + 2000/3 + 2000 = 3000. The join
# prices sa * load / 600: 100 * 1.0, 200 * 1.2 and 600 * 1.0 over 600, times
# 2000: 1000/3 + 800 + 2000 = 9400/3. The filter keeps policies 2 and 3:
# (200 + 600) / 600 * 2000 = 8000/3.
REFUSED_IN_BATCHES: dict[str, tuple[Model, float]] = {
    "a cross-row share on a DataFrame": (_bare_share, 3000.0),
    "the same share back through continue_from=": (_continued_share, 3000.0),
    "a per-row join on a DataFrame": (_bare_join, 9400.0 / 3.0),
    "a filter on a DataFrame": (_bare_filter, 8000.0 / 3.0),
    "a cross-row share in a plan": (_lazy_share, 3000.0),
    "a plan over a DataFrame that took the share": (_lazy_over_a_collect, 3000.0),
}


def _total(model: Model, batch_size: int | str) -> float:
    result = run_aggregated(
        model, BOOK, aggregations=(Sum("pv").alias("total"),), batch_size=batch_size
    )
    return float(result.aggregations["total"])


@pytest.mark.parametrize("case", REFUSED_IN_BATCHES, ids=list(REFUSED_IN_BATCHES))
@pytest.mark.parametrize("batch_size", [1, 2])
def test_values_from_outside_are_refused_in_batches_of_several(
    case: str, batch_size: int
) -> None:
    model, _book = REFUSED_IN_BATCHES[case]

    with pytest.raises(ValueError, match="values the batch did not hold") as refused:
        _total(model, batch_size)

    message = str(refused.value)
    assert f"run_aggregated cuts the 3 policies into batches of {batch_size}" in message
    for route in (
        "af.join(table",
        "before the run",
        "run the book in one batch",
        'engine="jax"',
    ):
        assert route in message


@pytest.mark.parametrize("case", REFUSED_IN_BATCHES, ids=list(REFUSED_IN_BATCHES))
def test_over_the_whole_book_the_setup_stands(case: str) -> None:
    model, book_total = REFUSED_IN_BATCHES[case]

    assert _total(model, 3) == pytest.approx(book_total, rel=1e-12)
    collected = model(ActuarialFrame(BOOK)).collect()["pv"].sum()
    assert collected == pytest.approx(book_total, rel=1e-12)


def test_the_d2g_share_reads_the_figures_it_named() -> None:
    """6000 at batch size 1 and 5000 at 2 on 0.9.0's tree: now refused, 3000 whole."""
    for batch_size in (1, 2):
        with pytest.raises(ValueError, match="holds 'v', which the batch did not hold"):
            _total(_bare_share, batch_size)
    assert _total(_bare_share, 3) == 3000.0


def test_run_to_parquet_judges_the_same_way(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="values the batch did not hold"):
        run_to_parquet(_bare_share, BOOK, tmp_path / "two", batch_size=2)

    run_to_parquet(_bare_share, BOOK, tmp_path / "whole", batch_size=3)
    written = pl.read_parquet(tmp_path / "whole" / "*.parquet")
    assert written["pv"].sum() == 3000.0


def _rebuilt_over_the_batch(af: ActuarialFrame) -> ActuarialFrame:
    """Collect to look, and rebuild over the batch unchanged."""
    af = ActuarialFrame(af.collect())
    return _priced(af.with_columns((pl.col("sa") / 600.0).alias("v")))


def _lazy_per_row(af: ActuarialFrame) -> ActuarialFrame:
    return _priced(
        ActuarialFrame(af._df.with_columns((pl.col("sa") / 600.0).alias("v")))  # noqa: SLF001
    )


def _lazy_join(af: ActuarialFrame) -> ActuarialFrame:
    plan = af._df.join(SIDE.lazy(), on="product", how="left", maintain_order="left")  # noqa: SLF001
    return _priced(
        ActuarialFrame(
            plan.with_columns((pl.col("sa") * pl.col("load") / 600.0).alias("v"))
        )
    )


PASS_IN_BATCHES: dict[str, tuple[Model, float]] = {
    "the batch's own values, rebuilt": (_rebuilt_over_the_batch, 3000.0),
    "a per-row plan": (_lazy_per_row, 3000.0),
    "a per-row join in a plan": (_lazy_join, 9400.0 / 3.0),
}


@pytest.mark.parametrize("case", PASS_IN_BATCHES, ids=list(PASS_IN_BATCHES))
@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_the_batch_s_own_values_and_a_per_row_plan_pass(
    case: str, batch_size: int
) -> None:
    model, book_total = PASS_IN_BATCHES[case]

    assert _total(model, batch_size) == pytest.approx(book_total, rel=1e-12)


@pytest.mark.parametrize(
    ("step", "said"),
    [
        (lambda plan: plan.group_by("product").agg(pl.col("sa").sum()), "group_by"),
        (lambda plan: plan.head(5), "keeps a slice of the rows"),
        (lambda plan: plan.with_row_index("n"), "with_row_index"),
        (lambda plan: pl.concat([plan, plan]), "concat"),
        (lambda plan: plan.unique(subset=["product"]), "unique"),
        (
            lambda plan: plan.with_columns(pl.col("sa").rank().alias("r")),
            "rank on",
        ),
    ],
    ids=["group_by", "head", "row_index", "concat", "unique", "rank"],
)
def test_a_plan_step_that_reads_across_rows_is_refused(
    step: Callable[[pl.LazyFrame], pl.LazyFrame], said: str
) -> None:
    def model(af: ActuarialFrame) -> ActuarialFrame:
        rebuilt = ActuarialFrame(step(af._df))  # noqa: SLF001
        return _priced(rebuilt.with_columns((pl.col("sa") / 600.0).alias("v")))

    with pytest.raises(ValueError, match="values the batch did not hold") as refused:
        _total(model, 2)
    assert said in str(refused.value)


def test_a_scenario_plan_with_whole_policies_judges_nothing() -> None:
    plan = ScenarioRun(shocks={"BASE": []}, aggregations=(Sum("pv").alias("total"),))

    result = plan.run(ActuarialFrame(BOOK), _bare_share)

    assert result.aggregations["total"] == 3000.0


def _two_scenarios() -> ScenarioRun:
    return ScenarioRun(
        shocks={"BASE": [], "B2": []},
        aggregations=(Sum("pv").alias("total").over("scenario_id"),),
    )


def _per_scenario(model: Model, batch_size: int) -> list[float]:
    result = _two_scenarios().run(ActuarialFrame(BOOK), model, batch_size=batch_size)
    return [float(v) for v in result.aggregations["total"]["total"]]


@pytest.mark.parametrize("case", REFUSED_IN_BATCHES, ids=list(REFUSED_IN_BATCHES))
def test_a_scenario_batch_crossing_scenarios_is_judged_as_a_policy_cut(
    case: str,
) -> None:
    """Section 13.2: a batch holding two scenarios' copies of the book is not one book.

    Collected there, the frame holds every scenario's copy, so the share of
    the largest sum assured -- or of the total, A1's 450 for 900 -- is taken
    over both copies at once. Whole policies do not excuse it: it is refused
    by name, with the routes a scenario plan has.
    """
    model, _book = REFUSED_IN_BATCHES[case]

    with pytest.raises(ValueError, match="values the batch did not hold") as refused:
        _per_scenario(model, 2)

    message = str(refused.value)
    assert "this batch holds more than one scenario" in message
    assert "Whole policies do not excuse a batch that crosses scenarios" in message
    for route in ("before the run", "af.join(table", "batch_size=1"):
        assert route in message


def _share_of_the_total(af: ActuarialFrame) -> ActuarialFrame:
    """A1's repro: 900 allocated by each policy's share of the total sum assured."""
    mp = af.collect().with_columns((pl.col("sa") / pl.col("sa").sum()).alias("v"))
    af = _priced(ActuarialFrame(mp))
    af.pv = af.pv * 0.45
    return af


def test_the_a1_share_answered_450_for_900_and_is_refused() -> None:
    # One scenario a batch: each scenario's frame is its whole book, 900.
    assert _per_scenario(_share_of_the_total, 1) == pytest.approx([900.0, 900.0])
    with pytest.raises(ValueError, match="holds 'v', which the batch did not hold"):
        _per_scenario(_share_of_the_total, 2)


@pytest.mark.parametrize("case", REFUSED_IN_BATCHES, ids=list(REFUSED_IN_BATCHES))
def test_one_scenario_a_batch_answers_as_before(case: str) -> None:
    model, book_total = REFUSED_IN_BATCHES[case]

    assert _per_scenario(model, 1) == pytest.approx([book_total] * 2, rel=1e-12)


@pytest.mark.parametrize("case", PASS_IN_BATCHES, ids=list(PASS_IN_BATCHES))
@pytest.mark.parametrize("batch_size", [1, 2])
def test_the_crossed_batch_s_own_values_and_a_per_row_plan_pass(
    case: str, batch_size: int
) -> None:
    model, book_total = PASS_IN_BATCHES[case]

    assert _per_scenario(model, batch_size) == pytest.approx(
        [book_total] * 2, rel=1e-12
    )
