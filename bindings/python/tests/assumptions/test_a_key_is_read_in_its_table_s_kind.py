# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A lookup key is read by its value in the table's kind, or refused by kind.

A flag, a fixed-point decimal or a date against a table of another kind
passed the text-or-number family check and was reported as "missing keys",
with advice -- ``on_missing="nan"`` -- that turned every policy to NaN; a
date-keyed table answered an integer day count silently. A flag now reads as
its 0 or 1 against a table keyed 0 and 1, with the conversion written into
the record, and is refused against any other keys; a decimal reads by value;
a date or a timestamp answers a key of its own kind and refuses
any other by kind, with the conversion to write, whatever the miss policy.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter

_COUNT = iter(range(10_000))


def _table(keys: pl.Series, values: list[float], **options: Any) -> Table:  # noqa: ANN401
    return Table(
        name=f"b3_kinds_{next(_COUNT)}",
        source=pl.DataFrame({"k": keys, "v": values}),
        dimensions={"k": "k"},
        value="v",
        **options,
    )


def _read(table: Table, query: pl.Series) -> list[Any]:
    af = ActuarialFrame(pl.DataFrame({"q": query}))
    af.r = table.lookup(k=af.q)
    return af.collect()["r"].to_list()


_FLAGS = pl.Series([True, False, True])


@pytest.mark.parametrize(
    "keys", [pl.Series([True, False]), pl.Series([1, 0]), pl.Series([1.0, 0.0])]
)
def test_a_flag_reads_as_its_number_against_a_table_keyed_0_and_1(
    keys: pl.Series,
) -> None:
    values = [1.5, 1.0] if keys[0] in (True, 1) else [1.0, 1.5]
    assert _read(_table(keys, values), _FLAGS) == [1.5, 1.0, 1.5]


def test_the_record_writes_the_flag_as_its_number() -> None:
    table = _table(pl.Series([0, 1]), [1.0, 1.5])
    af = ActuarialFrame(pl.DataFrame({"smoker": _FLAGS}))
    af.load = table.lookup(k=af.smoker)
    document = json.loads(GraphExporter(af).export(af.collect(), profile="executable"))
    (load,) = [node for node in document["nodes"] if node["id"] == "load@1"]

    assert load["expr"]["args"] == [
        {
            "op": "binop",
            "kind": "mul",
            "left": {"op": "col", "name": "smoker"},
            "right": {"op": "lit", "value": 1.0},
        }
    ]


@pytest.mark.parametrize("on_missing", ["raise", "nan", 0.0])
def test_a_flag_against_codes_that_are_not_0_and_1_is_refused(
    on_missing: str | float,
) -> None:
    table = _table(pl.Series([1, 2]), [1.0, 1.5], on_missing=on_missing)
    with pytest.raises(TypeError, match=r"with a flag.*this table's keys are 1, 2"):
        _read(table, _FLAGS)


def test_a_decimal_key_reads_by_its_value() -> None:
    query = pl.Series([Decimal("5.00"), Decimal("1.00")], dtype=pl.Decimal(38, 2))
    assert _read(_table(pl.Series([1, 5]), [0.1, 0.5]), query) == [0.5, 0.1]


_DATES = pl.Series([dt.date(2025, 1, 1), dt.date(2025, 6, 30)])


def test_a_date_table_answers_a_date_per_policy_and_per_period() -> None:
    table = _table(_DATES, [100.0, 103.0])
    assert _read(table, _DATES.reverse()) == [103.0, 100.0]

    af = ActuarialFrame(pl.DataFrame({"q": [list(_DATES)]}))
    af.r = table.lookup(k=af.q)
    assert af.collect()["r"].to_list() == [[100.0, 103.0]]


@pytest.mark.parametrize("on_missing", ["raise", "nan"])
@pytest.mark.parametrize(
    ("keys", "query", "said"),
    [
        (_DATES, pl.Series([20269]), "with numbers"),
        (pl.Series([20089, 20269]), _DATES, "with dates"),
        (pl.Series(["2025-01-01", "2025-06-30"]), _DATES, "with dates"),
        (pl.Series(["Y", "N"]), _FLAGS, "with flags"),
    ],
)
def test_a_key_of_another_kind_is_refused_by_kind_never_as_a_miss(
    keys: pl.Series, query: pl.Series, said: str, on_missing: str
) -> None:
    table = _table(keys, [100.0, 103.0], on_missing=on_missing)
    with pytest.raises(TypeError, match=said) as refused:
        _read(table, query)
    assert "on_missing" not in str(refused.value)
    assert "Convert the key" in str(refused.value)


def test_two_nanosecond_instants_are_two_keys() -> None:
    at = 1_577_880_000_000_000_000
    keys = pl.Series([at, at + 1], dtype=pl.Int64).cast(pl.Datetime("ns"))
    table = _table(keys, [1.0, 2.0])
    assert _read(table, keys.reverse()) == [2.0, 1.0]
    in_microseconds = pl.Series([at // 1000], dtype=pl.Int64).cast(pl.Datetime("us"))
    assert _read(table, in_microseconds) == [1.0]


def test_a_zone_naive_timestamp_against_a_zoned_table_is_refused() -> None:
    zoned = pl.Series([dt.datetime(2025, 1, 1)]).dt.replace_time_zone("UTC")  # noqa: DTZ001
    table = _table(zoned, [1.0])
    with pytest.raises(TypeError, match="zone-naive timestamp and a zoned one"):
        _read(table, pl.Series([dt.datetime(2025, 1, 1)]))  # noqa: DTZ001


def test_an_executable_record_of_a_date_keyed_lookup_is_refused() -> None:
    """The frame answers it; the executable form (section 11.1.24) does not hold it."""
    table = _table(_DATES, [100.0, 103.0])
    af = ActuarialFrame(pl.DataFrame({"q": _DATES}))
    af.r = table.lookup(k=af.q)
    result = af.collect()

    with pytest.raises(
        ValueError, match=r"outside the executable form \(section 11\.1\.24\)"
    ):
        GraphExporter(af).export(result, profile="executable")
    assert json.loads(GraphExporter(af).export(result))["profile"] == "audit"
