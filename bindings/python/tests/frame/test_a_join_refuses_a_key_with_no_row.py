# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A left join refuses a policy whose key matches no row, unless the model keeps it.

``af.join(products, on="prod")`` with a book key ``"Term20"`` against a table
holding ``"TERM20"`` gave that policy null parameters and a null value, and
every portfolio total skipped it: 1,460 where the hand total is 2,220, with no
word (audit C4-F4). ``Table.lookup`` refused the same data and the JAX engine
refused the same model. ``on_missing`` now says what a miss means: ``"raise"``,
the default for a left join, refuses where the join is written, naming the
count, the first policy and its key, the line and both moves; ``"null"``
keeps today's meaning and says so on the record.
"""

from __future__ import annotations

import datetime as dt
import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.scenarios import Sum

_PRODUCTS = pl.DataFrame({"prod": ["TERM10", "TERM20"], "exp_load": [25.0, 40.0]})
_BOOK = pl.DataFrame(
    {
        "pid": [1, 2, 3],
        "prod": ["TERM10", "TERM20", "Term20"],
        "sa": [100000.0, 200000.0, 150000.0],
    }
)


def _model(on_missing: str | None, *, fill: bool = False):  # noqa: ANN202 -- a model function
    def model(af: ActuarialFrame) -> ActuarialFrame:
        if on_missing is None:
            af = af.join(_PRODUCTS, on="prod")
        else:
            af = af.join(_PRODUCTS, on="prod", on_missing=on_missing)
        if fill:
            af.exp_load = af.exp_load.fill_null(0.0)
        af = af.projection.set(
            valuation_date=dt.date(2025, 1, 31),
            until="term_years",
            until_value=3,
            frequency="annual",
        )
        af.cf = af.sa * 0.001 + af.exp_load + af.month * 0
        af.pv = af.cf.list.sum()
        return af

    return model


def test_the_default_refuses_naming_the_count_the_policy_the_key_and_the_line() -> None:
    with pytest.raises(ValueError, match="1 of 3 policies") as refused:
        _model(None)(ActuarialFrame(_BOOK))
    message = str(refused.value)
    assert "row 2 (from 0), prod='Term20'" in message
    assert "test_a_join_refuses_a_key_with_no_row.py:" in message
    assert 'on_missing="null"' in message
    assert "fill_null" in message


@pytest.mark.parametrize("batch_size", [1, 3])
def test_every_door_refuses_it(batch_size: int) -> None:
    with pytest.raises(ValueError, match="found no row in the other table"):
        run_aggregated(
            _model(None), _BOOK, [Sum("pv").alias("t")], batch_size=batch_size
        )


def test_a_null_key_is_a_miss() -> None:
    book = _BOOK.with_columns(pl.Series("prod", ["TERM10", None, "TERM20"]))
    with pytest.raises(ValueError, match="row 1 \\(from 0\\), prod=None"):
        ActuarialFrame(book).join(_PRODUCTS, on="prod")


def test_null_keeps_the_policy_as_null_and_says_so_on_the_record() -> None:
    af = _model("null")(ActuarialFrame(_BOOK))
    out = af.collect()
    assert out["pv"].to_list() == [500.0, 960.0, None]
    node = next(
        one
        for one in json.loads(GraphExporter(af).export(profile="executable"))["nodes"]
        if one["column"] == "exp_load" and one["provenance"] == "join"
    )
    assert node["expr"]["attrs"]["on_missing"] == "null"


def test_null_filled_on_the_next_line_counts_the_policy() -> None:
    result = run_aggregated(
        _model("null", fill=True), _BOOK, [Sum("pv").alias("t")], batch_size=1
    )
    assert result.t == 2060.0


def test_a_join_that_matches_every_key_records_no_miss_policy() -> None:
    book = _BOOK.with_columns(pl.Series("prod", ["TERM10", "TERM20", "TERM20"]))
    af = _model(None)(ActuarialFrame(book))
    assert af.collect()["pv"].sum() == 2220.0
    node = next(
        one
        for one in json.loads(GraphExporter(af).export(profile="executable"))["nodes"]
        if one["column"] == "exp_load" and one["provenance"] == "join"
    )
    assert "on_missing" not in node["expr"]["attrs"]


@pytest.mark.parametrize("how", ["inner", "semi", "anti", "full"])
def test_other_join_types_keep_their_own_meaning_and_refuse_null(how: str) -> None:
    ActuarialFrame(_BOOK).join(_PRODUCTS, on="prod", how=how)
    with pytest.raises(ValueError, match="is a left join's"):
        ActuarialFrame(_BOOK).join(_PRODUCTS, on="prod", how=how, on_missing="null")


def test_a_miss_policy_that_is_not_one_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="not a miss policy a join takes"):
        ActuarialFrame(_BOOK).join(_PRODUCTS, on="prod", on_missing="nan")
