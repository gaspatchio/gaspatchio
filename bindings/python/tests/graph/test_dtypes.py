# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The artifact's own type names, and the refusal when a type has none.

An engine's display string for a type is that engine's, not the artifact's.
``Utf8`` and ``String`` are the same type under two names one release apart,
``Int8`` and ``Int64`` are one type as far as any reader of this document is
concerned, and none of those words mean anything to a consumer that never
heard of the engine that wrote them. So the artifact names types itself, from
a closed list, and a type it cannot name stops the export rather than being
lowercased into something that merely looks like a name.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio._dtypes import (
    EXECUTION_TYPES,
    NEUTRAL_SCALARS,
    UnmappedDtypeError,
    neutral_dtype,
)
from gaspatchio.frame.graph.calc_graph import GraphExporter


def _exported(af: ActuarialFrame) -> dict[str, dict[str, Any]]:
    """Export the frame's graph against its own collected values, by node id."""
    artifact = json.loads(GraphExporter(af).export(af.collect()))
    return {node["id"]: node for node in artifact["nodes"]}


# --- the vocabulary ---------------------------------------------------------


@pytest.mark.parametrize(
    ("polars_dtype", "expected"),
    [
        (pl.Boolean, "bool"),
        (pl.Int8, "i64"),
        (pl.Int32, "i64"),
        (pl.Int64, "i64"),
        (pl.UInt32, "i64"),
        (pl.Float32, "f64"),
        (pl.Float64, "f64"),
        (pl.String, "str"),
        (pl.Date, "date"),
        (pl.Datetime, "datetime"),
        (pl.List(pl.Float64), "list[f64]"),
        (pl.List(pl.List(pl.Int64)), "list[list[i64]]"),
    ],
)
def test_a_polars_type_gets_the_artifact_s_own_name(polars_dtype, expected) -> None:
    assert neutral_dtype(polars_dtype, column="reserve") == expected


def test_an_unmapped_type_is_refused_by_name() -> None:
    with pytest.raises(UnmappedDtypeError) as raised:
        neutral_dtype(pl.Categorical, column="product_group")
    message = str(raised.value)
    assert "product_group" in message
    assert "Categorical" in message
    assert "bool, i64, f64, str, date, datetime" in message


def test_a_type_that_could_not_be_probed_is_unknown_not_refused() -> None:
    assert neutral_dtype(None, column="reserve") == "unknown"


def test_integer_width_is_not_recoverable_from_the_artifact() -> None:
    """Stated so nobody builds on it: widths collapse, deliberately."""
    assert neutral_dtype(pl.Int32, column="policy_term") == neutral_dtype(
        pl.Int64, column="policy_term"
    )


def test_float_width_is_not_recoverable_from_the_artifact() -> None:
    """The same collapse on the float side, for the same reason."""
    assert neutral_dtype(pl.Float32, column="mortality_rate") == neutral_dtype(
        pl.Float64, column="mortality_rate"
    )


@pytest.mark.parametrize(
    "polars_dtype", [pl.UInt64(), pl.Int128(), pl.UInt128()], ids=str
)
def test_an_integer_wider_than_i64_is_refused_where_no_values_are_in_reach(
    polars_dtype: pl.DataType,
) -> None:
    """Widths collapse only while the name they collapse to can hold the value.

    Every ``i64`` in this vocabulary travels as a signed 64-bit value, and
    each of these three can hold a number that does not fit one --
    ``.hash()`` produces a ``UInt64`` column whose values run past 2^63 as a
    matter of course. Handed the width and nothing else, this cannot tell
    such a column from one of policy numbers, and naming it ``i64`` on the
    chance would put a number in the artifact that the artifact's own
    declared type cannot carry. So it refuses, and the refusal is the same
    one it has always been: the caller with the values is the one that gets
    to judge them.
    """
    with pytest.raises(UnmappedDtypeError) as raised:
        neutral_dtype(polars_dtype, column="policy_hash")
    message = str(raised.value)
    assert "policy_hash" in message
    assert polars_dtype.base_type().__name__ in message
    assert ".to_integer()" in message


@pytest.mark.parametrize(
    "polars_dtype", [pl.UInt64(), pl.Int128(), pl.UInt128()], ids=str
)
def test_a_wide_integer_whose_every_value_fits_is_named_i64(
    polars_dtype: pl.DataType,
) -> None:
    """A policy number is an ``i64`` of policy numbers whatever it was stored in.

    The values are what the record carries, and these all fit the signed
    64-bit form every integer in the artifact travels in -- so the name is
    the one the author's own ``.cast(pl.Int64)`` would earn, and with it
    the same canonical bytes.
    """
    values = pl.Series("policy_id", [7, 8, 9], dtype=polars_dtype)
    assert neutral_dtype(polars_dtype, column="policy_id", values=values) == "i64"


def test_a_wide_integer_column_with_no_values_at_all_fits() -> None:
    """Nulls are not numbers out of range, and an empty column holds none.

    ``.cast(pl.Int64)`` on either would succeed and produce a column of
    nulls, so refusing here would refuse what the cast this is measured
    against does not.
    """
    nulls = pl.Series("policy_id", [None, None], dtype=pl.UInt64)
    empty = pl.Series("policy_id", [], dtype=pl.UInt64)
    assert neutral_dtype(pl.UInt64, column="policy_id", values=nulls) == "i64"
    assert neutral_dtype(pl.UInt64, column="policy_id", values=empty) == "i64"


def test_a_value_no_i64_carries_is_refused_by_its_own_number() -> None:
    """Past 2^63 the refusal is about the number, not about the width.

    Which is what makes it an alarm worth having: a warehouse switching
    integer widths on unchanged identifiers is not a fact about the model,
    and a value that stops fitting next quarter is.
    """
    hashes = pl.Series("policy_hash", [12, 9_817_422_164_619_289_418], dtype=pl.UInt64)
    with pytest.raises(UnmappedDtypeError) as raised:
        neutral_dtype(pl.UInt64, column="policy_hash", values=hashes)
    message = str(raised.value)
    assert "policy_hash" in message
    assert "9817422164619289418" in message
    assert ".to_text()" in message


def test_a_signed_value_below_the_i64_floor_is_refused_by_its_own_number() -> None:
    """``Int128`` runs off the bottom as well as the top, and both are misses."""
    depths = pl.Series("drawdown", [-(2**70), 0], dtype=pl.Int128)
    with pytest.raises(UnmappedDtypeError) as raised:
        neutral_dtype(pl.Int128, column="drawdown", values=depths)
    message = str(raised.value)
    assert "-1180591620717411303424" in message
    assert "smaller" in message


def test_a_list_of_wide_integers_is_judged_on_the_numbers_inside_it() -> None:
    """The values are the values wherever the column keeps them.

    A per-period column holds its numbers one list deep, and the question
    is the same question: the name is ``list[i64]`` when every number fits
    and a refusal naming the number when one does not.
    """
    fitting = pl.Series("ids", [[7, 8], [9]], dtype=pl.List(pl.UInt64))
    assert (
        neutral_dtype(pl.List(pl.UInt64), column="ids", values=fitting) == "list[i64]"
    )

    wide = pl.Series("hashes", [[12], [2**64 - 1]], dtype=pl.List(pl.UInt64))
    with pytest.raises(UnmappedDtypeError) as raised:
        neutral_dtype(pl.List(pl.UInt64), column="hashes", values=wide)
    assert "18446744073709551615" in str(raised.value)


def test_a_fixed_width_array_is_told_the_conversion_that_carries_it() -> None:
    """An array is the ``list[...]`` the vocabulary already has, length fixed.

    Which makes it among the likeliest refusals a real model meets, and the
    one where the generic advice is least use: "cast it to one of these"
    does not say that the answer is one word and the shape is already right.
    Driven through, because advice that does not run costs more than advice
    that says nothing.
    """
    with pytest.raises(UnmappedDtypeError) as raised:
        neutral_dtype(pl.Array(pl.Float64, 3), column="quarterly_charges")
    message = str(raised.value)
    assert "quarterly_charges" in message
    assert ".to_list()" in message
    assert ".polars_native().cast(" not in message

    charges = pl.Series(
        "quarterly_charges", [[1.5, 2.5, 3.5]], dtype=pl.Array(pl.Float64, 3)
    )
    frame = ActuarialFrame(pl.DataFrame({"quarterly_charges": charges}))
    frame.charge_run = frame.quarterly_charges.to_list()
    assert _exported(frame.drop("quarterly_charges"))["charge_run@1"]["dtype"] == (
        "list[f64]"
    )


@pytest.mark.parametrize(
    "polars_dtype", [pl.Categorical, pl.Enum(["preferred", "standard"])], ids=str
)
def test_a_category_is_told_the_cast_that_carries_it(
    polars_dtype: pl.DataType,
) -> None:
    """A category is a string with a dictionary in front of it, and the string carries.

    Which makes it the refusal a real model meets most: a product group, a
    smoker status, a rating class read out of a parquet file arrives
    categorical as often as not, and the generic advice ("cast it to one of
    these") does not say that the answer is one word and loses nothing.
    """
    with pytest.raises(UnmappedDtypeError) as raised:
        neutral_dtype(polars_dtype, column="product_group")
    message = str(raised.value)
    assert "product_group" in message
    assert ".to_text()" in message


def test_a_time_delta_names_the_cast_that_carries_it() -> None:
    """The vocabulary has no time-delta type, so the refusal says what to do."""
    with pytest.raises(UnmappedDtypeError) as raised:
        neutral_dtype(pl.Duration, column="time_since_issue")
    message = str(raised.value)
    assert "time_since_issue" in message
    assert ".dt.total_days()" in message


def test_an_unmapped_type_inside_a_list_is_refused_by_its_own_name() -> None:
    """The inner type has no name, and the sentence says where it was found.

    Naming ``Categorical`` on its own would send the author looking for a
    categorical column and finding a list of them. The type the column has
    and the type that stopped the export are two different types here, so
    the refusal states both.
    """
    with pytest.raises(UnmappedDtypeError) as raised:
        neutral_dtype(pl.List(pl.Categorical), column="rating_history")
    message = str(raised.value)
    assert "rating_history" in message
    assert (
        "has type List(Categorical), whose element type Categorical the "
        "calculation graph has no name for" in message
    )


def test_list_nesting_is_admitted_to_three_levels() -> None:
    """Three is what the published schema's own pattern can express."""
    assert (
        neutral_dtype(pl.List(pl.List(pl.List(pl.Float64))), column="scenario_paths")
        == "list[list[list[f64]]]"
    )


def test_a_fourth_level_of_list_nesting_is_refused() -> None:
    """A producer must not mint a type name its own schema would reject."""
    with pytest.raises(UnmappedDtypeError) as raised:
        neutral_dtype(
            pl.List(pl.List(pl.List(pl.List(pl.Float64)))), column="scenario_paths"
        )
    message = str(raised.value)
    assert "scenario_paths" in message
    assert "three" in message


# --- the execution typing table ---------------------------------------------


def test_every_name_in_the_vocabulary_says_how_an_engine_carries_it() -> None:
    """A consumer with no date type of its own still has to store the value."""
    assert set(EXECUTION_TYPES) == NEUTRAL_SCALARS


def test_a_date_is_carried_as_a_day_count_and_a_datetime_as_microseconds() -> None:
    """The epoch and the unit are stated, because a reader cannot infer them."""
    assert EXECUTION_TYPES["date"] == "int32 (days since 1970-01-01)"
    assert EXECUTION_TYPES["datetime"] == (
        "int64 (microseconds since 1970-01-01T00:00:00Z)"
    )


# --- the wire form of a date ------------------------------------------------


def test_a_date_column_s_sample_is_an_iso_calendar_date_on_the_wire() -> None:
    """The reader gets ``2025-01-01``, not a day count -- JSON Schema ``date``."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1"],
                "issue_date": [datetime.date(2025, 1, 1)],
                "sum_assured": [100_000.0],
            }
        )
    )
    frame.valuation_date = frame.issue_date

    node = _exported(frame)["valuation_date@1"]

    assert node["dtype"] == "date"
    assert node["value_sample"] == "2025-01-01"


def test_a_datetime_column_s_sample_is_an_iso_timestamp_on_the_wire() -> None:
    """Same rule one type along: the value is written, not encoded."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1"],
                "recorded_at": [datetime.datetime(2025, 1, 1, 12, 30, 0)],  # noqa: DTZ001
                "sum_assured": [100_000.0],
            }
        )
    )
    frame.booked_at = frame.recorded_at

    node = _exported(frame)["booked_at@1"]

    assert node["dtype"] == "datetime"
    assert node["value_sample"] == "2025-01-01T12:30:00"


# --- what the exporter now writes -------------------------------------------


def test_an_exported_node_carries_the_neutral_name_not_the_engine_s() -> None:
    """The whole point, checked end to end rather than on the mapper alone."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1"],
                "policy_term": [20],
                "mortality_rate": [0.01],
                "in_force": [True],
            }
        )
    )
    frame.death_claims = frame.mortality_rate * frame.policy_term

    nodes = _exported(frame)

    assert nodes["policy_term"]["dtype"] == "i64"
    assert nodes["mortality_rate"]["dtype"] == "f64"
    assert nodes["in_force"]["dtype"] == "bool"
    assert nodes["policy_id"]["dtype"] == "str"
    assert nodes["death_claims@1"]["dtype"] == "f64"


def test_every_exported_dtype_satisfies_the_published_schema() -> None:
    """``unknown`` or a name from the closed list -- nothing else may appear."""
    import re

    from gaspatchio.schemas import load_schema

    pattern = load_schema()["$defs"]["dtype"]["pattern"]
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1"],
                "issue_date": [datetime.date(2025, 1, 1)],
                "policy_term": [20],
                "mortality_rate": [0.01],
            }
        )
    )
    # The projection is what puts a ``list[...]`` name in front of the
    # pattern. Its nesting alternation is the part of it a hand-written list
    # of names could not have covered -- which is this test's whole reason
    # for reading the pattern out of the published document -- so a frame of
    # scalars would leave exactly that part unexercised.
    frame = frame.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=3, frequency="annual"
    )
    frame.death_claims = frame.mortality_rate * frame.policy_term
    frame.mortality_by_period = frame.mortality_rate * frame.month

    nodes = _exported(frame)

    assert any(node["dtype"] == "list[f64]" for node in nodes.values())
    for node in nodes.values():
        dtype = node["dtype"]
        assert dtype == "unknown" or re.match(pattern, dtype), dtype


# --- a model's own unsigned column, judged at export ------------------------


def _a_book(policy_ids: pl.Series) -> ActuarialFrame:
    """Return the same one-line model over whichever spelling of the ids."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": policy_ids, "sum_assured": [100.0, 200.0, 300.0]})
    )
    frame.death_claims = frame.sum_assured * 0.01
    return frame


def test_an_unsigned_column_that_fits_exports_as_its_own_cast() -> None:
    """The exporter's measurement and the author's cast are one document.

    A warehouse writes policy numbers as ``UInt64``; the same numbers
    written as ``Int64`` are the same numbers. Section 12.1 takes a leaf's
    canonical bytes over its tag, its name and its type, so if the two
    exports agree on the type they agree on every digest in the file --
    which is the claim this pins, node record and model identity both.
    """
    book = _a_book(pl.Series("policy_id", [1, 2, 3], dtype=pl.UInt64))
    cast = _a_book(pl.Series("policy_id", [1, 2, 3], dtype=pl.Int64))

    unsigned = json.loads(GraphExporter(book).export(book.collect()))
    signed = json.loads(GraphExporter(cast).export(cast.collect()))

    unsigned_leaf = {node["id"]: node for node in unsigned["nodes"]}["policy_id"]
    signed_leaf = {node["id"]: node for node in signed["nodes"]}["policy_id"]

    assert unsigned_leaf["dtype"] == "i64"
    assert unsigned_leaf == signed_leaf
    assert unsigned["graph_fingerprint"] == signed["graph_fingerprint"]


def test_a_hash_column_is_refused_at_export_by_the_value_it_holds() -> None:
    """The case the measurement does not rescue, and must not.

    ``.hash()`` is past 2^63 by construction, so this column has no exact
    numeric name however hard anybody looks at it. The refusal says which
    number stopped it and offers the cast that keeps the digits.
    """
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))
    frame.policy_hash = frame.policy_id.polars_native().hash()
    collected = frame.collect()
    largest = collected["policy_hash"].max()

    with pytest.raises(UnmappedDtypeError) as raised:
        GraphExporter(frame).export(collected)

    message = str(raised.value)
    assert "policy_hash" in message
    assert str(largest) in message
    assert ".to_text()" in message


def test_a_superseded_definition_is_judged_on_its_own_values() -> None:
    """One definition's width is never read off another definition's column.

    A column written twice is two worksheet columns wearing one name, and
    the frame ends up holding the second. Measuring the first against those
    numbers would certify a width from values it never produced -- the
    inference the refusal exists to stop -- so it is measured against the
    output the frame carried aside for it, where the hash still is.
    """
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))
    frame.marker = frame.policy_id.polars_native().hash()
    hashes = frame.collect()["marker"]
    frame.marker = frame.policy_id * 1.0
    collected = frame.collect()

    # The surviving column is an f64 of small numbers: judged on it, the
    # replaced definition would pass for i64.
    assert collected.schema["marker"] == pl.Float64

    with pytest.raises(UnmappedDtypeError) as raised:
        GraphExporter(frame).export(collected)
    assert str(hashes.max()) in str(raised.value)


def _a_lazy_book(policy_ids: pl.Series) -> ActuarialFrame:
    """Return the one-line model over a LazyFrame, whose values the door never held.

    A DataFrame's ``UInt64`` column that fits is read as ``Int64`` where it
    arrives (section 10), so the width survives to the export only where
    the values were not in hand: a LazyFrame book.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {"policy_id": policy_ids, "sum_assured": [100.0, 200.0, 300.0]}
        ).lazy()
    )
    frame.death_claims = frame.sum_assured * 0.01
    return frame


def test_an_export_with_no_frame_in_hand_measures_the_book_and_never_guesses() -> None:
    """No collected frame: a book column is measured off the book, nothing guessed.

    An export asked for without the collected frame -- and the structural
    fingerprint, which folds the same graph -- reads a wide column the book
    arrived with off the book itself, as the book's digest does, and names
    it on its numbers, as the DataFrame door does. A calculation has no book
    to be read from: with no values in hand it has its width and nothing
    else, and the answer is the refusal it always was, naming the type and
    the cast the author would write.
    """
    book = _a_lazy_book(pl.Series("policy_id", [1, 2, 3], dtype=pl.UInt64))

    nodes = {
        node["id"]: node for node in json.loads(GraphExporter(book).export())["nodes"]
    }
    assert nodes["policy_id"]["dtype"] == "i64"
    assert book.graph.fingerprint()

    book.hashed = book.policy_id.polars_native().hash()
    with pytest.raises(UnmappedDtypeError) as raised:
        GraphExporter(book).export()
    assert "has type UInt64" in str(raised.value)
    assert ".to_integer()" in str(raised.value)


def test_every_move_the_refusals_name_is_one_a_column_can_be_handed() -> None:
    """Advice that does not run costs more than advice that says nothing.

    Two of these three now name an operation of the vocabulary's own, so
    the sentence is written on the column exactly as it reads. The third is
    still an escape, because the date namespace belongs to Polars and a
    duration's unit is a decision this vocabulary declines to make for
    anyone. A bare ``.cast(pl.Int64)`` remains an ``AttributeError`` on
    every column, which is why no refusal names one.
    """
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))
    with pytest.raises(AttributeError, match=r"polars_native\(\)\.cast"):
        frame.policy_id.cast(pl.Int64)

    with pytest.raises(UnmappedDtypeError) as wide:
        neutral_dtype(pl.UInt64, column="policy_hash")
    with pytest.raises(UnmappedDtypeError) as category:
        neutral_dtype(pl.Categorical, column="product_group")
    with pytest.raises(UnmappedDtypeError) as delta:
        neutral_dtype(pl.Duration, column="time_in_force")

    assert ".to_integer()" in str(wide.value)
    assert ".to_text()" in str(category.value)
    assert ".polars_native().dt.total_days()" in str(delta.value)
    for raised in (wide, category):
        assert ".polars_native().cast(" not in str(raised.value)


def test_the_conversion_the_refusal_names_carries_the_column_it_refused() -> None:
    """Driven end to end: refuse, write the sentence out, export.

    The operation is not merely reachable -- it produces the column the
    refusal wanted, and the export that stopped now finishes. Both doors
    are exercised on the same column: the width fits an ``i64``, so
    ``to_integer`` names it, and the hash of it never will, so ``to_text``
    keeps the digits.
    """
    book = _a_lazy_book(pl.Series("policy_id", [1, 2, 3], dtype=pl.UInt64))
    book.hashed = book.policy_id.polars_native().hash()
    with pytest.raises(UnmappedDtypeError) as raised:
        GraphExporter(book).export()
    assert ".to_integer()" in str(raised.value)

    converted = ActuarialFrame(
        pl.DataFrame({"policy_id": pl.Series([1, 2, 3], dtype=pl.UInt64)}).lazy()
    )
    converted.policy_id_i64 = converted.policy_id.to_integer()
    converted.hashed = converted.policy_id.polars_native().hash().to_text()

    assert _exported(converted)["policy_id_i64@1"]["dtype"] == "i64"
    assert _exported(converted)["hashed@1"]["dtype"] == "str"


# --- the type a conditional and a recurrence state is the type they hold -----


def _a_projected_book() -> ActuarialFrame:
    """Return a one-policy, four-period book holding integer durations."""
    book = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["A"],
                "opening": pl.Series([100], dtype=pl.Int64),
                "start_year": pl.Series([3], dtype=pl.Int64),
                "rate": [0.25],
            }
        )
    )
    return book.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=3, frequency="monthly"
    )


def test_two_integer_branches_stay_integers_on_every_per_period_route() -> None:
    """A per-period conditional over two integers holds integers, as its tree says.

    Section 11.1.28 types a conditional as its branches' shared type, and
    the record's tree is two integers. The per-period routes selected in
    Float64 whatever they were handed, so the column -- and with it the
    node's declared type -- was ``list[f64]`` beneath a tree a reader typed
    ``list[i64]``: a comparison on a per-period column, a stored per-period
    indicator, and a per-policy test over a per-period branch alike. An
    integer opposite a double is still a double.
    """
    af = _a_projected_book()
    af.duration = af.month // 12 + af.start_year
    af.capped = when(af.duration > 4).then(4).otherwise(af.duration)
    af.past_four = af.duration > 4
    af.capped_on_a_mask = when(af.past_four).then(4).otherwise(af.duration)
    af.capped_on_a_policy = when(af.start_year > 2).then(af.duration).otherwise(0)
    af.mixed = when(af.duration > 4).then(af.rate).otherwise(af.duration)

    collected = af.collect()
    nodes = _exported(af)

    for column in ("capped", "capped_on_a_mask", "capped_on_a_policy"):
        assert collected.schema[column] == pl.List(pl.Int64), column
        assert nodes[f"{column}@1"]["dtype"] == "list[i64]", column
    assert collected["capped"].to_list() == [[3, 3, 3, 3]]
    assert collected.schema["mixed"] == pl.List(pl.Float64)
    assert nodes["mixed@1"]["dtype"] == "list[f64]"


def test_an_integer_operand_of_a_recurrence_is_recorded_widened() -> None:
    """``accumulate`` over an integer states the widening it runs under.

    Section 11.1.20 states the recurrence over Float64, and the kernel
    widens an integer operand on the way in. The record carried the integer
    column bare, so a reader holding the vocabulary refused the line and
    every calculation downstream of it. The tree now says ``to_float`` over
    an integer column and the double a literal opening balance opens at,
    and the numbers do not move.
    """
    af = _a_projected_book()
    af.growth = af.month * 0.0 + 1.0
    af.from_a_column = af.growth.projection.accumulate(
        initial=af.opening, multiplier=af.growth, addend=af.month
    )
    af.from_a_literal = af.growth.projection.accumulate(
        initial=0, multiplier=af.growth, addend=af.growth
    )
    af.from_a_double = af.growth.projection.accumulate(
        initial=af.rate, multiplier=af.growth, addend=1
    )

    collected = af.collect()
    artifact = json.loads(GraphExporter(af).export(collected, profile="executable"))
    trees = {node["id"]: node.get("expr") for node in artifact["nodes"]}

    assert trees["from_a_column@1"]["args"][0] == {
        "op": "call",
        "name": "to_float",
        "args": [{"op": "col", "name": "opening"}],
        "attrs": {},
    }
    assert trees["from_a_column@1"]["args"][2]["name"] == "to_float"
    assert trees["from_a_literal@1"]["args"][0] == {"op": "lit", "value": 0.0}
    assert trees["from_a_double@1"]["args"][0] == {"op": "col", "name": "rate"}
    assert trees["from_a_double@1"]["args"][2] == {"op": "lit", "value": 1}
    assert collected["from_a_column"].to_list() == [[100.0, 101.0, 103.0, 106.0]]
    assert collected["from_a_literal"].to_list() == [[1.0, 2.0, 3.0, 4.0]]
