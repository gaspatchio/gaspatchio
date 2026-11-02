# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every list plugin answers a slice exactly as it answers those rows of the whole.

The streaming engine -- ``ActuarialFrame.collect``'s default -- hands an
elementwise plugin one slice of the frame per morsel, and ``DataFrame.head`` /
``DataFrame.slice`` hand it the same thing in memory. A sliced list column
keeps the whole column's inner values and moves only its offsets, so the
offsets of rows two onwards do not start at zero. A kernel that walked the
flat values without its offsets would answer the wrong policy's periods, or
refuse a slice for a value in a row it was never given; each case below
compares a slice's answer with the slice of the whole frame's answer.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.frame.lowering._excel.irr import irr
from gaspatchio.frame.lowering._excel.pv import pv
from gaspatchio.frame.lowering._excel.yearfrac import yearfrac
from gaspatchio.frame.lowering._polars import plugins

if TYPE_CHECKING:
    from collections.abc import Callable

ROWS = 6
c = pl.col


def _frame() -> pl.DataFrame:
    """Six policies whose every list differs by row, with a hole in the last."""
    return pl.DataFrame(
        {
            "x": [[1.0 + r, 2.0 + r, 3.0 + r] for r in range(ROWS - 1)]
            + [[1.0, None, 3.0]],
            "y": [[0.5, 1.5, 2.5 + r] for r in range(ROWS)],
            "ix": [[r, r + 1, r + 2] for r in range(ROWS)],
            "plan": [
                ["A", "B", "A"] if r % 2 else ["B", "B", "A"] for r in range(ROWS)
            ],
            "s": [1.0 + r / 10 for r in range(ROWS)],
            "cf": [[-100.0, 30.0 + r, 40.0, 50.0] for r in range(ROWS)],
            "d0": [[date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1)]] * ROWS,
            "d1": [[date(2020, 7, 1), date(2021, 9, 1), date(2023, 1, 1)]] * ROWS,
        },
    ).with_columns(cat=c("plan").cast(pl.List(pl.Categorical)))


PLUGINS: dict[str, Callable[[], pl.Expr]] = {
    "ieee div list/list": lambda: plugins.ieee_quotient(c("x"), c("y"), "div"),
    "ieee div list/policy": lambda: plugins.ieee_quotient(c("x"), c("s"), "div"),
    "ieee floordiv int list": lambda: plugins.ieee_quotient(
        c("ix"), pl.lit(2), "floordiv"
    ),
    "ieee mod policy/list": lambda: plugins.ieee_quotient(c("s"), c("y"), "mod"),
    "list_pow list^list": lambda: plugins.list_pow(c("x"), c("y")),
    "list_pow list^policy": lambda: plugins.list_pow(c("y"), c("s")),
    "list_pow policy^int list": lambda: plugins.list_pow(c("s"), c("ix")),
    "list_clip int list": lambda: plugins.list_clip(c("ix"), pl.lit(1.0), pl.lit(4.0)),
    "list_clip list bounds": lambda: plugins.list_clip(c("x"), c("y"), c("y") + 2.0),
    "accumulate": lambda: plugins.accumulate(c("s"), c("x"), c("y")),
    "accumulate int addend": lambda: plugins.accumulate(c("s"), c("y"), c("ix")),
    "list_conditional": lambda: plugins.list_conditional(
        c("x"), c("y"), c("x"), pl.lit(0.0), "gt"
    ),
    "list_conditional text": lambda: plugins.list_conditional(
        c("plan"), pl.lit("A"), c("y"), pl.lit(0.0), "eq"
    ),
    "list_conditional categorical": lambda: plugins.list_conditional(
        c("cat"), pl.lit("A"), c("y"), pl.lit(0.0), "eq"
    ),
    "curve_eval": lambda: plugins.curve_eval(
        c("y"), method="linear", xs=[0.0, 1.0, 2.0], ys=[0.01, 0.02, 0.03]
    ),
    "pv": lambda: pv(c("s") / 100, c("ix"), c("s")),
    "irr": lambda: irr(c("cf")),
    "yearfrac": lambda: yearfrac(c("d0"), c("d1")),
}


@pytest.mark.parametrize("name", list(PLUGINS))
@pytest.mark.parametrize(("start", "length"), [(0, 2), (2, 3), (1, 5)])
def test_a_slice_answers_as_the_whole_frame_does(
    name: str, start: int, length: int
) -> None:
    frame = _frame()
    expr = PLUGINS[name]().alias("out")
    whole = frame.lazy().select(expr).collect(engine="in-memory").get_column("out")
    part = frame.slice(start, length).lazy().select(expr).collect(engine="in-memory")
    assert part.get_column("out").equals(whole.slice(start, length))


def test_a_list_key_lookup_on_a_slice_answers_as_the_whole_frame_does() -> None:
    table = Table(
        name="slice_rates",
        source=pl.DataFrame(
            {"age": np.arange(20, dtype=np.int64), "rate": np.linspace(0.001, 0.1, 20)},
        ),
        dimensions={"age": "age"},
        value="rate",
    )

    def rates(frame: pl.DataFrame) -> pl.Series:
        af = ActuarialFrame(frame.select("ix"))
        af.rate = table.lookup(age=af.ix)
        return af.collect(engine="in-memory").get_column("rate")

    frame = _frame()
    assert rates(frame.slice(2, 3)).equals(rates(frame).slice(2, 3))


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
def test_a_text_condition_against_a_list_literal_reads_it_for_every_policy(
    engine: str,
) -> None:
    # The in-memory engine hands the plugin a list literal as one row; the
    # streaming engine broadcasts it first. Both answer the literal's periods
    # for every policy -- in memory this used to panic past its one row.
    frame = pl.DataFrame(
        {
            "plan": [["A", "B", "A"], ["B", "A", "B"], ["A", "A", "A"]],
            "x": [[1.0, 2.0, 3.0]] * 3,
        },
    )
    literal = pl.lit(pl.Series([["A", "A", "B"]]))
    expr = plugins.list_conditional(c("plan"), literal, c("x"), pl.lit(0.0), "eq")
    out = frame.lazy().select(expr.alias("out")).collect(engine=engine)
    assert out.get_column("out").to_list() == [
        [1.0, 0.0, 0.0],
        [0.0, 2.0, 3.0],
        [1.0, 2.0, 0.0],
    ]


_ONE_ROW = [2.0, 5.0, 8.0]

# Each case takes the right-hand operand ``r``: a one-row literal, or the same
# row repeated as a column, which is what the streaming engine hands over.
ONE_ROW_CASES: dict[str, Callable[[pl.Expr], pl.Expr]] = {
    "condition: right list": lambda r: plugins.list_conditional(
        c("x"), r, c("x"), pl.lit(0.0), "gt"
    ),
    "condition: then list": lambda r: plugins.list_conditional(
        c("x"), pl.lit(4.0), r, pl.lit(0.0), "gt"
    ),
    "condition: otherwise list": lambda r: plugins.list_conditional(
        c("x"), pl.lit(4.0), pl.lit(0.0), r, "gt"
    ),
    "condition: left list": lambda r: plugins.list_conditional(
        r, c("x"), pl.lit(1.0), pl.lit(0.0), "gt"
    ),
    "list_pow: exponent list": lambda r: plugins.list_pow(c("x"), r),
    "list_pow: base list": lambda r: plugins.list_pow(r, c("x")),
    "list_clip: values list": lambda r: plugins.list_clip(r, c("x"), c("x") + 10.0),
    "accumulate: multiplier list": lambda r: plugins.accumulate(c("s"), r, c("x")),
    "accumulate: addend list": lambda r: plugins.accumulate(c("s"), c("x"), r),
    "pv: rate list": lambda r: pv(r / 100, c("x"), c("s")),
    "ieee div: divisor list": lambda r: plugins.ieee_quotient(c("x"), r, "div"),
    "list_clip: lower bound list": lambda r: plugins.list_clip(
        c("x"), r, pl.lit(100.0)
    ),
}


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
@pytest.mark.parametrize("name", list(ONE_ROW_CASES))
def test_a_one_row_list_literal_is_read_for_every_policy(
    name: str, engine: str
) -> None:
    frame = pl.DataFrame(
        {
            "x": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]],
            "s": [1.0, 2.0, 3.0],
            "r": [_ONE_ROW] * 3,
        },
    )
    case = ONE_ROW_CASES[name]
    literal = pl.lit(pl.Series([_ONE_ROW]))
    out = frame.lazy().select(case(literal).alias("out")).collect(engine=engine)
    repeated = frame.lazy().select(case(c("r")).alias("out")).collect(engine=engine)
    assert out.get_column("out").to_list() == repeated.get_column("out").to_list()


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
def test_a_one_value_literal_is_read_for_every_policy_by_yearfrac_and_irr(
    engine: str,
) -> None:
    frame = pl.DataFrame(
        {
            "d1": [date(2020, 7, 1), date(2021, 1, 1), date(2022, 1, 1)],
            "cf": [[-100.0, 60.0, 60.0], [-100.0, 50.0, 70.0], [-100.0, 10.0, 120.0]],
        },
    )
    out = (
        frame.lazy()
        .select(
            years=yearfrac(c("d1"), pl.lit(date(2025, 1, 1))),
            back=yearfrac(pl.lit(date(2019, 1, 1)), c("d1")),
            rate=irr(c("cf"), pl.lit(0.1)),
        )
        .collect(engine=engine)
    )
    assert out.height == 3
    expected = frame.lazy().select(
        years=yearfrac(c("d1"), pl.lit(pl.Series([date(2025, 1, 1)] * 3))),
        back=yearfrac(pl.lit(pl.Series([date(2019, 1, 1)] * 3)), c("d1")),
        rate=irr(c("cf"), pl.lit(pl.Series([0.1] * 3))),
    )
    assert out.equals(expected.collect(engine=engine))


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
def test_a_year_fraction_to_a_valuation_date_answers_every_policy(engine: str) -> None:
    # af.date.excel.yearfrac(valuation_date) refused in memory -- the plugin
    # walked one row -- and answered in streaming.
    af = ActuarialFrame(
        pl.DataFrame({"d1": [date(2020, 7, 1), date(2021, 1, 1), date(2022, 1, 1)]}),
    )
    af.years = af.d1.excel.yearfrac(date(2025, 1, 1))
    years = af.collect(engine=engine).get_column("years").to_list()
    assert years == pytest.approx([4.5027, 4.0005, 3.0007], abs=1e-4)
