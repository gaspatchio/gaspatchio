# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``excel.eomonth`` reads its months as ``excel.edate`` does (11.1.33).

This engine refused a double count of months for ``eomonth`` outright, where
the producer moved a whole one and truncated a fraction. A whole double is
now that number of months on both engines; one that is not is refused by
value, under the whole-number conversion's check.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines.report import EngineRefusal

START = dt.date(2025, 1, 31)


def _frame(months: list[float]) -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"start": [START] * 3, "months": months}))
    af.moved = af.start.excel.eomonth(af.months)
    return af


def test_a_whole_double_is_that_number_of_months_on_both_engines() -> None:
    af = _frame([1.0, -2.0, 12.0])
    want = [dt.date(2025, 2, 28), dt.date(2024, 11, 30), dt.date(2026, 1, 31)]
    assert af.collect(engine="jax")["moved"].to_list() == want
    assert af.collect()["moved"].to_list() == want


def test_a_count_that_is_not_whole_is_refused_by_value() -> None:
    with pytest.raises(EngineRefusal, match=r"to_integer\.integral"):
        _frame([1.0, 1.5, 1.0]).collect(engine="jax")
