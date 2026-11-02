# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A frame rebuilt over a ``with_scenarios`` crossing is judged against it.

``with_scenarios`` crosses the book with every scenario it is handed and gives
the frame back with no runner around the model. Collected there, the frame
holds every scenario's copy of the book, so a share of the total sum assured
taken in plain Polars is taken over every copy at once: two scenarios answered
111.1 for a policy whose figure is 222.2, with nothing refused. Section 13.2
says whole policies do not excuse a frame that crosses scenarios, so the
rebuild is judged against the crossed frame and refused by name, with the two
routes this door has -- the column computed on the book before it is crossed,
and a side table joined through the frame. One scenario crossed is that
scenario's whole book, and answers as before.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import with_scenarios

if TYPE_CHECKING:
    from collections.abc import Callable

    Model = Callable[[ActuarialFrame], ActuarialFrame]

BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "sa": [100.0, 200.0, 600.0],
        "product": ["A", "B", "A"],
    }
)
SIDE = pl.DataFrame({"product": ["A", "B"], "load": [1.0, 1.2]})
TWO = ["BASE", "B2"]


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
    return frame.with_columns((pl.col("sa") / pl.col("sa").sum()).alias("v"))


def _bare_share(af: ActuarialFrame) -> ActuarialFrame:
    return _priced(ActuarialFrame(_share(af.collect())))


def _continued_share(af: ActuarialFrame) -> ActuarialFrame:
    return _priced(ActuarialFrame(_share(af.collect()), continue_from=af))


def _bare_join(af: ActuarialFrame) -> ActuarialFrame:
    joined = af.collect().join(SIDE, on="product", how="left", maintain_order="left")
    return _priced(
        ActuarialFrame(
            joined.with_columns((pl.col("sa") * pl.col("load") / 900.0).alias("v"))
        )
    )


def _bare_filter(af: ActuarialFrame) -> ActuarialFrame:
    af = ActuarialFrame(af.collect().filter(pl.col("sa") > pl.col("sa").mean()))
    return _priced(af.with_columns((pl.col("sa") / 900.0).alias("v")))


def _lazy_share(af: ActuarialFrame) -> ActuarialFrame:
    return _priced(
        ActuarialFrame(
            af._df.with_columns((pl.col("sa") / pl.col("sa").sum()).alias("v"))  # noqa: SLF001
        )
    )


def _lazy_over_a_collect(af: ActuarialFrame) -> ActuarialFrame:
    return _priced(ActuarialFrame(_share(af.collect()).lazy()))


# Hand values, per scenario: the shares are 100/900, 200/900 and 600/900 of
# the book's total, 2000 a share: 2000 in all. The join prices sa * load / 900:
# (100 + 240 + 600) / 900 * 2000 = 18800/9. The filter keeps the policy above
# the book's mean of 300 -- policy 3 -- at 600 / 900 * 2000 = 4000/3.
REFUSED: dict[str, tuple[Model, float]] = {
    "a cross-row share on a DataFrame": (_bare_share, 2000.0),
    "the same share back through continue_from=": (_continued_share, 2000.0),
    "a per-row join on a DataFrame": (_bare_join, 18800.0 / 9.0),
    "a filter on a DataFrame": (_bare_filter, 4000.0 / 3.0),
    "a cross-row share in a plan": (_lazy_share, 2000.0),
    "a plan over a DataFrame that took the share": (_lazy_over_a_collect, 2000.0),
}


def _per_scenario(model: Model, scenarios: list[str]) -> dict[str, float]:
    out = model(with_scenarios(ActuarialFrame(BOOK), scenarios)).collect()
    totals = out.group_by("scenario_id").agg(pl.col("pv").sum())
    return dict(zip(totals["scenario_id"], totals["pv"], strict=True))


@pytest.mark.parametrize("case", REFUSED, ids=list(REFUSED))
def test_a_rebuild_over_two_scenarios_is_refused_by_name(case: str) -> None:
    model, _book = REFUSED[case]

    with pytest.raises(
        ValueError, match="values the crossed frame did not hold"
    ) as refused:
        _per_scenario(model, TWO)

    message = str(refused.value)
    assert "with_scenarios crossed the book with 2 scenarios on 'scenario_id'" in (
        message
    )
    assert "Whole policies do not excuse a frame that crosses scenarios" in message
    for route in ("before with_scenarios crosses it", "af.join(table"):
        assert route in message


@pytest.mark.parametrize("case", REFUSED, ids=list(REFUSED))
def test_one_scenario_crossed_answers_as_before(case: str) -> None:
    model, book_total = REFUSED[case]

    assert _per_scenario(model, ["BASE"]) == pytest.approx(
        {"BASE": book_total}, rel=1e-12
    )


def test_the_e1_share_answered_111_for_222_and_is_refused() -> None:
    """E1's probe: policy 1's share is 100/900, 2000 a share -- 222.2, not 111.1."""
    one = _bare_share(with_scenarios(ActuarialFrame(BOOK), ["BASE"])).collect()
    assert one["pv"][0] == pytest.approx(2000.0 / 9.0, rel=1e-12)
    with pytest.raises(ValueError, match="holds 'v', which the crossed frame"):
        _bare_share(with_scenarios(ActuarialFrame(BOOK), TWO))


def _rebuilt_unchanged(af: ActuarialFrame) -> ActuarialFrame:
    af = ActuarialFrame(af.collect())
    return _priced(af.with_columns((pl.col("sa") / 900.0).alias("v")))


def _lazy_per_row(af: ActuarialFrame) -> ActuarialFrame:
    return _priced(
        ActuarialFrame(af._df.with_columns((pl.col("sa") / 900.0).alias("v")))  # noqa: SLF001
    )


def _frame_join(af: ActuarialFrame) -> ActuarialFrame:
    af = af.join(SIDE, on="product")
    af.v = af.sa * af.load / 900.0
    return _priced(af)


def _on_the_frame(af: ActuarialFrame) -> ActuarialFrame:
    af.v = af.sa / 900.0
    return _priced(af.materialize())


PASS: dict[str, tuple[Model, float]] = {
    "the crossed frame's own values, rebuilt": (_rebuilt_unchanged, 2000.0),
    "a per-row plan": (_lazy_per_row, 2000.0),
    "a join through the frame": (_frame_join, 18800.0 / 9.0),
    "the frame's own line, materialized": (_on_the_frame, 2000.0),
}


@pytest.mark.parametrize("case", PASS, ids=list(PASS))
def test_the_crossed_frame_s_own_values_and_the_routes_pass(case: str) -> None:
    model, book_total = PASS[case]

    assert _per_scenario(model, TWO) == pytest.approx(
        {"BASE": book_total, "B2": book_total}, rel=1e-12
    )


def test_the_column_computed_on_the_book_before_the_crossing_answers() -> None:
    book = _share(BOOK)

    out = _priced(with_scenarios(ActuarialFrame(book), TWO)).collect()

    totals = out.group_by("scenario_id").agg(pl.col("pv").sum())
    assert totals["pv"].to_list() == pytest.approx([2000.0, 2000.0], rel=1e-12)


def test_a_frame_over_the_book_alone_is_not_judged_by_a_crossing() -> None:
    """A crossing judges only frames carrying its axis: the book itself is the book."""
    with_scenarios(ActuarialFrame(BOOK), TWO)

    over_a_table = ActuarialFrame(_share(BOOK))
    over_a_plan = ActuarialFrame(_share(BOOK).lazy())

    assert over_a_table.collect()["v"].sum() == pytest.approx(1.0)
    assert over_a_plan.collect()["v"].sum() == pytest.approx(1.0)


def test_a_summary_by_scenario_is_not_a_rebuild() -> None:
    """A table that kept the axis and dropped the book's columns carries no crossing."""
    out = _rebuilt_unchanged(with_scenarios(ActuarialFrame(BOOK), TWO)).collect()
    summary = out.group_by("scenario_id", maintain_order=True).agg(pl.col("pv").sum())

    assert ActuarialFrame(summary).collect()["pv"].to_list() == pytest.approx(
        [2000.0, 2000.0]
    )


def test_a_second_crossing_of_a_book_is_not_judged_against_the_first() -> None:
    """A read taken on the book before it is crossed again is the book's."""
    with_scenarios(ActuarialFrame(BOOK), TWO)
    af = ActuarialFrame(BOOK)
    af.v = af.sa / af.sa.polars_native().sum()

    out = _priced(with_scenarios(af, TWO)).collect()

    assert out["pv"].sum() == pytest.approx(4000.0, rel=1e-12)
