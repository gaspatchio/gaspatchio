# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The Excel lowerings read a column named by a string as that column.

Their operands are typed ``IntoExprColumn``, which includes a column name.
``to_polars_expression`` handed a name back unchanged where it promised an
expression, so DAYS, EDATE, EOMONTH and ROUND raised AttributeError on one,
and YEARFRAC read the name as a string literal and refused it.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio.frame.lowering._excel.days import days
from gaspatchio.frame.lowering._excel.edate import edate
from gaspatchio.frame.lowering._excel.eomonth import eomonth
from gaspatchio.frame.lowering._excel.round import round as excel_round
from gaspatchio.frame.lowering._excel.yearfrac import yearfrac
from gaspatchio.frame.lowering._polars.expressions import to_polars_expression

POLICY = pl.DataFrame(
    {
        "start": [datetime.date(2024, 1, 31)],
        "end": [datetime.date(2024, 7, 31)],
        "premium": [1234.5678],
    }
)


def test_a_column_name_reads_the_column() -> None:
    assert POLICY.select(days("end", "start")).item() == 182
    assert POLICY.select(edate("start", pl.lit(1))).item() == datetime.date(2024, 2, 29)
    assert POLICY.select(eomonth("start", pl.lit(1))).item() == datetime.date(
        2024, 2, 29
    )
    assert POLICY.select(excel_round("premium", 2)).item() == pytest.approx(1234.57)

    by_name = POLICY.select(yearfrac("start", "end", basis=1)).item()
    by_column = POLICY.select(yearfrac(pl.col("start"), pl.col("end"), basis=1)).item()
    assert by_name == by_column


def test_every_operand_becomes_an_expression() -> None:
    """A name is a column and any other value a literal, as Polars reads them."""
    assert to_polars_expression("start").meta.eq(pl.col("start"))
    for literal in (pl.Series([1, 2]), 3, 0.5, datetime.date(2024, 1, 31)):
        assert isinstance(to_polars_expression(literal), pl.Expr)

    as_of = datetime.date(2024, 1, 31)
    assert POLICY.select(days(pl.col("end"), as_of)).item() == 182
