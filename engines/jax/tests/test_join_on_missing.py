# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A left join's ``on_missing="null"``: held beside the value, filled or refused.

This engine holds no null, so a policy a left join keeps without a row
is held as an absence beside the arriving column (11.1.2). Published as
it stands, the column carries the null the reference producer publishes; read
by ``fill_null`` the absence is filled; read by any other formula, or folded,
it refuses for the policies it stands in, as a null read as a value does.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.scenarios import Sum

_RIDERS = pl.DataFrame(
    {"rider": ["ADB", "WOP"], "rider_rate": [0.0002, 0.0001], "label": ["a", "w"]}
)
_BOOK = pl.DataFrame(
    {"pid": [1, 2, 3], "rider": ["ADB", "NONE", "WOP"], "sa": [1e5, 2e5, 3e5]}
)


def _frame() -> ActuarialFrame:
    return ActuarialFrame(_BOOK).join(_RIDERS, on="rider", on_missing="null")


def test_an_unread_arriving_column_publishes_the_producer_s_null() -> None:
    af = _frame()
    want = af.collect().select("rider_rate", "label").to_dicts()
    got = af.collect(engine="jax").select("rider_rate", "label").to_dicts()
    assert got == want
    assert got[1] == {"rider_rate": None, "label": None}


def test_a_fill_on_the_next_line_answers_on_both_engines() -> None:
    af = _frame()
    af.rider_rate = af.rider_rate.fill_null(0.0)
    af.charge = af.sa * af.rider_rate
    assert (
        af.collect(engine="jax")["charge"].to_list() == af.collect()["charge"].to_list()
    )
    assert af.collect(engine="jax")["charge"].to_list() == [20.0, 0.0, 30.0]


def test_a_formula_reading_the_null_unfilled_is_refused_for_that_policy() -> None:
    af = _frame()
    af.charge = af.sa * af.rider_rate
    with pytest.raises(EngineRefusal, match=r"join\.unmatched, first at row 1"):
        af.collect(engine="jax")


def test_a_fold_of_the_null_unfilled_is_refused() -> None:
    def model(af: ActuarialFrame) -> ActuarialFrame:
        af = af.join(_RIDERS, on="rider", on_missing="null")
        return af.projection.set(
            valuation_date=dt.date(2025, 1, 1),
            until="term_years",
            until_value=1,
            frequency="annual",
        )

    with pytest.raises(EngineRefusal, match=r"join\.unmatched"):
        run_aggregated(model, _BOOK, [Sum("rider_rate").alias("t")], engine="jax")


_NULL_KEY_BOOK = pl.DataFrame(
    {"pid": [1, 2, 3], "rider": ["ADB", None, "WOP"], "sa": [1e5, 2e5, 3e5]}
)


def test_a_null_key_is_a_miss_kept_as_null_as_the_producer_keeps_it() -> None:
    """A null key matches no row (11.1.2): under ``"null"`` the policy stays.

    The key is read only to select a row, so the door does not refuse the
    book for it; the arriving columns are null for that policy, published as
    the producer publishes them, and a fill on the next line answers.
    """
    af = ActuarialFrame(_NULL_KEY_BOOK).join(_RIDERS, on="rider", on_missing="null")
    want = af.collect().select("rider_rate", "label").to_dicts()
    assert af.collect(engine="jax").select("rider_rate", "label").to_dicts() == want
    assert want[1] == {"rider_rate": None, "label": None}
    af.rider_rate = af.rider_rate.fill_null(0.0)
    af.charge = af.sa * af.rider_rate
    assert af.collect(engine="jax")["charge"].to_list() == [20.0, 0.0, 30.0]
