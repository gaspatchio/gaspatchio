# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A read partitioned by the scenario answers each scenario's own book.

A scenario plan hands the model every scenario's copy of the whole book,
crossed on a scenario axis, and never cuts the policies into batches. So a
read across rows partitioned by ``scenario_id`` --
``pl.col("sa").sum().over("scenario_id")``, or with further keys,
``.over(["scenario_id", "product"])`` -- reads within one scenario's copy of
the book: an expense of 1,000,000 allocated by share of sum assured totals
1,000,000 in every scenario, at every number of scenarios per batch. Before
this, the partitioned read was refused there with the unpartitioned one; now
it stands. An unpartitioned read stays refused, even at one scenario per
batch, and its refusal names the partitioned form. Where the policies are cut
into batches -- a model crossing its own axis inside ``run_aggregated`` --
the partitioned read is the batch's too, and is still refused.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated
from gaspatchio.scenarios import MultiplicativeShock, ScenarioRun, Sum, with_scenarios

if TYPE_CHECKING:
    from collections.abc import Callable

FIXED_EXPENSE = 1_000_000.0

BOOK = pl.DataFrame(
    {
        "policy_id": [f"P{i}" for i in range(8)],
        "sa": [1e5 * (i + 1) for i in range(8)],
        "term_m": [12] * 8,
        "lapse_adj": [1.0] * 8,
    }
)

# Hand value: each scenario's allocation is 1,000,000 a year, paid as a
# twelfth at each of the 13 boundaries of a 12-month term and valued at the
# end of each period at 0.25% a month: (1e6 / 12) * sum_{t=1..13} 1.0025^-t.
PV0_BASE = 1_064_609.6294
# The lapse_adj shock scales every cashflow by 1.1; an sa shock moves every
# policy's sum assured alike, so the shares -- and the 1,000,000 -- hold.
PV0_UP = 1_171_070.5923

PLAN = ScenarioRun(
    shocks={
        "BASE": [],
        "UP": [MultiplicativeShock(factor=1.1, column="lapse_adj")],
        "SA_UP": [MultiplicativeShock(factor=1.5, column="sa")],
    },
    aggregations=(
        Sum("exp0").alias("exp0").over("scenario_id"),
        Sum("pv0").alias("pv0").over("scenario_id"),
    ),
)


def _model(share: Callable[[ActuarialFrame], object]) -> Callable[..., ActuarialFrame]:
    def model(af: ActuarialFrame) -> ActuarialFrame:
        af.sa_share = share(af)
        af.alloc_exp = af.sa_share * FIXED_EXPENSE
        af = af.projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="term_months",
            until_value="term_m",
            frequency="monthly",
        )
        af.cf = af.alloc_exp / 12 * af.lapse_adj + af.month * 0.0
        af.pv = af.cf.projection.prospective_value(discount_rate=0.0025)
        af.pv0 = af.pv.list.get(0)
        af.exp0 = af.alloc_exp * 1.0
        return af

    return model


PARTITIONED = {
    "raw": _model(lambda af: af.sa / pl.col("sa").sum().over("scenario_id")),
    "raw-col": _model(
        lambda af: af.sa / pl.col("sa").sum().over(pl.col("scenario_id"))
    ),
    "escape": _model(
        lambda af: (
            af.sa / af.sa.polars_native().sum().polars_native().over("scenario_id")
        )
    ),
    "count": _model(lambda af: af.sa * 0.0 + 1.0 / pl.len().over("scenario_id")),
}
UNPARTITIONED = _model(lambda af: af.sa / af.sa.polars_native().sum())


@pytest.mark.parametrize("model", list(PARTITIONED.values()), ids=list(PARTITIONED))
@pytest.mark.parametrize("size", [1, 2, 16])
def test_a_scenario_plan_admits_a_read_partitioned_by_the_scenario(
    model: Callable[..., ActuarialFrame], size: int
) -> None:
    result = PLAN.run(ActuarialFrame(BOOK), model, batch_size=size)
    expense = {
        row["scenario_id"]: row["exp0"]
        for row in result.aggregations["exp0"].to_dicts()
    }
    pv0 = {
        row["scenario_id"]: row["pv0"] for row in result.aggregations["pv0"].to_dicts()
    }

    assert expense == pytest.approx(
        {"BASE": FIXED_EXPENSE, "UP": FIXED_EXPENSE, "SA_UP": FIXED_EXPENSE}
    )
    assert pv0 == pytest.approx({"BASE": PV0_BASE, "UP": PV0_UP, "SA_UP": PV0_BASE})


def test_a_frame_crossed_with_its_axis_admits_the_partitioned_read() -> None:
    crossed = with_scenarios(ActuarialFrame(BOOK), ["BASE", "UP"])
    out = PARTITIONED["raw"](crossed).collect()
    totals = dict(out.group_by("scenario_id").agg(pl.col("exp0").sum()).rows())

    assert totals == pytest.approx({"BASE": FIXED_EXPENSE, "UP": FIXED_EXPENSE})


@pytest.mark.parametrize("size", [1, 2, 16])
def test_an_unpartitioned_read_is_refused_naming_the_partitioned_form(
    size: int,
) -> None:
    with pytest.raises(ValueError, match="reads across the rows") as refused:
        PLAN.run(ActuarialFrame(BOOK), UNPARTITIONED, batch_size=size)
    message = str(refused.value)

    assert "every scenario's copy of every policy" in message
    assert ".over('scenario_id')" in message


@pytest.mark.parametrize(
    "share",
    [
        lambda af: af.sa / pl.col("sa").sum().over("scenario_id").max(),
        lambda af: (
            af.sa / pl.col("sa").sum().over("scenario_id", mapping_strategy="explode")
        ),
        lambda af: (
            af.sa / pl.col("sa").sum().over(["scenario_id", pl.col("sa").rank()])
        ),
        lambda af: af.sa / pl.col("sa").sum().over("term_m"),
    ],
    ids=[
        "a-read-outside-the-window",
        "explode",
        "a-key-that-reads-across-rows",
        "a-partition-without-the-scenario",
    ],
)
def test_a_window_that_leaves_the_scenario_s_book_is_refused(
    share: Callable[[ActuarialFrame], object],
) -> None:
    with pytest.raises(ValueError, match="reads across the rows"):
        PLAN.run(ActuarialFrame(BOOK), _model(share), batch_size=1)


# Two products, four policies each: a window partitioned by the scenario and
# the product allocates the expense within each product of each scenario.
BOOK_BY_PRODUCT = BOOK.with_columns(pl.Series("product", ["A"] * 4 + ["B"] * 4))

BY_PRODUCT = {
    "column": _model(
        lambda af: af.sa / pl.col("sa").sum().over(["scenario_id", "product"])
    ),
    "column-first": _model(
        lambda af: af.sa / pl.col("sa").sum().over(["product", "scenario_id"])
    ),
    "expression": _model(
        lambda af: (
            af.sa / pl.col("sa").sum().over(["scenario_id", pl.col("sa") > 4.5e5])
        )
    ),
}


@pytest.mark.parametrize("model", list(BY_PRODUCT.values()), ids=list(BY_PRODUCT))
@pytest.mark.parametrize("size", [1, 2, 16])
def test_a_partition_that_includes_the_scenario_is_admitted(
    model: Callable[..., ActuarialFrame], size: int
) -> None:
    """``.over(["scenario_id", x])`` stays inside one scenario's book (section 13.2).

    Hand value: each product (or each side of the 450,000 line, which splits
    the eight policies four and four) of each scenario allocates the whole
    1,000,000 among its own policies, so each scenario totals 2,000,000 --
    and its present value twice the one-product figure.
    """
    result = PLAN.run(ActuarialFrame(BOOK_BY_PRODUCT), model, batch_size=size)
    expense = {
        row["scenario_id"]: row["exp0"]
        for row in result.aggregations["exp0"].to_dicts()
    }
    pv0 = {
        row["scenario_id"]: row["pv0"] for row in result.aggregations["pv0"].to_dicts()
    }

    twice = 2 * FIXED_EXPENSE
    assert expense == pytest.approx({"BASE": twice, "UP": twice, "SA_UP": twice})
    assert pv0 == pytest.approx(
        {"BASE": 2 * PV0_BASE, "UP": 2 * PV0_UP, "SA_UP": 2 * PV0_BASE}
    )


def test_with_policy_batches_a_partition_including_the_scenario_is_refused() -> None:
    def crossing(af: ActuarialFrame) -> ActuarialFrame:
        return BY_PRODUCT["column"](with_scenarios(af, ["BASE", "UP"]))

    with pytest.raises(ValueError, match="run_aggregated cuts the 8 policies"):
        run_aggregated(
            crossing, BOOK_BY_PRODUCT, [Sum("exp0").alias("exp0")], batch_size=3
        )

    whole = run_aggregated(
        crossing, BOOK_BY_PRODUCT, [Sum("exp0").alias("exp0")], batch_size=8
    )
    assert whole.exp0 == pytest.approx(4 * FIXED_EXPENSE)


def test_the_refusal_writes_the_window_as_the_author_did() -> None:
    model = _model(lambda af: af.sa / pl.col("sa").sum().over("scenario_id").max())
    with pytest.raises(ValueError, match=r'max on col\("sa"\)\.sum\(\)\.over'):
        PLAN.run(ActuarialFrame(BOOK), model, batch_size=1)


def test_with_policy_batches_the_partitioned_read_is_still_refused() -> None:
    def crossing(af: ActuarialFrame) -> ActuarialFrame:
        return PARTITIONED["raw"](with_scenarios(af, ["BASE", "UP"]))

    with pytest.raises(
        ValueError, match="run_aggregated cuts the 8 policies"
    ) as refused:
        run_aggregated(crossing, BOOK, [Sum("exp0").alias("exp0")], batch_size=3)
    assert ".over('scenario_id')" not in str(refused.value)

    whole = run_aggregated(crossing, BOOK, [Sum("exp0").alias("exp0")], batch_size=8)
    assert whole.exp0 == pytest.approx(2 * FIXED_EXPENSE)
