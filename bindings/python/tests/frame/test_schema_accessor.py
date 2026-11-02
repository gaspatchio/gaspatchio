# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Asking a frame what it holds, without making it hold anything.

"Is ``scenario_id`` a label or an index?" is a question about the shape of
the data and not about any number in it. A frame that could be joined and
enriched but could not be asked for its own schema forced a collect for that
question -- or, worse, forced the modeller to infer the dtype from some other
flag that happened to correlate with it.

What is asserted here is that the answer comes off the plan: the names, the
dtypes, and the order they are in, with nothing executed to produce them.
The plan the tests below ask is poisoned -- it raises the moment anything
evaluates it -- so a schema that comes back at all is a schema that was read
rather than computed.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.calculation_log import (
    _RETAINED_PREFIX,
    _kernel_scratch_prefix,
)
from gaspatchio.rollforward import compile_rollforward


def _poisoned_plan() -> pl.LazyFrame:
    """Return a plan whose schema is declared and whose evaluation explodes.

    ``map_batches`` with an explicit ``schema=`` is the one construction that
    separates the two questions cleanly: Polars can state the output shape
    from the declaration, and it can only state the output *values* by calling
    the function -- which this one refuses to survive.
    """

    def detonate(_frame: pl.DataFrame) -> pl.DataFrame:
        msg = "the plan was executed to answer a question about its schema"
        raise AssertionError(msg)

    return pl.LazyFrame(
        {"sum_assured": [100_000.0], "issue_age": [45], "product": ["term"]}
    ).map_batches(
        detonate,
        schema={"sum_assured": pl.Float64, "issue_age": pl.Int64, "product": pl.String},
    )


def test_the_frame_says_what_it_holds_without_running_anything() -> None:
    af = ActuarialFrame(_poisoned_plan())

    assert af.schema == pl.Schema(
        {"sum_assured": pl.Float64, "issue_age": pl.Int64, "product": pl.String}
    )


def test_the_dtypes_come_off_the_plan_too() -> None:
    af = ActuarialFrame(_poisoned_plan())

    assert af.dtypes == [pl.Float64, pl.Int64, pl.String]


def test_the_dtypes_are_in_the_order_the_columns_are() -> None:
    """The pairing a caller writes -- ``zip(af.columns, af.dtypes)`` -- holds."""
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0], "issue_age": [45]}))
    af.death_claims = af.sum_assured * 0.00123

    assert dict(zip(af.columns, af.dtypes, strict=True)) == dict(af.schema)


def test_the_schema_follows_the_frame_as_it_is_written() -> None:
    af = ActuarialFrame(
        pl.DataFrame({"sum_assured": [100_000.0], "premium_pp": [250.0]})
    )
    af.death_claims = af.sum_assured * 0.00123

    assert af.schema["death_claims"] == pl.Float64

    af = af.drop("premium_pp")

    assert "premium_pp" not in af.schema
    assert af.columns == list(af.schema.names())


def test_a_superseded_definition_is_not_a_column_the_frame_reports() -> None:
    """A column written twice is carried in the plan, and is not the model's.

    The carried copy is how an export says what a column held before it was
    written over. Left in the schema it would be a column of nobody's model,
    and worse than a stray name: ``columns`` does not list it, so the two
    lists would be different lengths and every column written after the
    reassignment would be paired with the type of the one before it.
    """
    af = ActuarialFrame(pl.DataFrame({"base": [0.1, 0.2]}))
    af.rate = af.base * 2.0
    af.rate = af.rate * 3.0
    af.label = pl.lit("term")

    assert len(af.columns) == len(af.dtypes)
    assert dict(zip(af.columns, af.dtypes, strict=True)) == dict(af.schema)
    assert af.schema["label"] == pl.String
    assert not [name for name in af.schema if name.startswith(_RETAINED_PREFIX)]


def test_a_compiled_rollforward_s_scratch_is_not_one_either() -> None:
    """The other hidden column, and the same three answers have to agree.

    A compiled rollforward materialises one struct column so the kernel runs
    once however many states are read out of it. It is not a column anybody
    wrote or can ask about, and it reaches the schema the same way a carried
    definition does.
    """
    periods = 12
    af = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "fund_return": [[0.01] * periods],
            "me_charge": [[0.001] * periods],
        }
    )
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31),
        n_periods=periods,
        frequency="monthly",
    )
    builder = af.projection.rollforward(states={"fund_value": af["av_init"]})
    builder["fund_value"].grow(af["fund_return"], label="fund_return").charge(
        af["me_charge"], label="me_charge"
    )
    af.account_value = compile_rollforward(builder).expr_for("fund_value")

    assert len(af.columns) == len(af.dtypes)
    assert dict(zip(af.columns, af.dtypes, strict=True)) == dict(af.schema)
    assert af.schema["account_value"] == pl.List(pl.Float64)
    assert not [name for name in af.schema if name.startswith(_kernel_scratch_prefix())]


def test_a_frame_holding_no_data_holds_an_empty_schema() -> None:
    """``columns`` answers ``[]`` for such a frame, and these two agree with it."""
    af = ActuarialFrame()

    assert af.columns == []
    assert af.schema == pl.Schema()
    assert af.dtypes == []


def test_the_schema_is_read_only() -> None:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))

    with pytest.raises(AttributeError):
        af.schema = pl.Schema()  # type: ignore[misc]


def test_a_column_actually_called_schema_is_reached_through_brackets() -> None:
    """The reserved-name trade, and it is the one ``columns`` already makes.

    A model whose data really does carry a column called ``schema`` still has
    it. What it does not have is ``af.schema`` meaning that column, and the
    frame says so rather than handing back whichever of the two it guessed.
    """
    af = ActuarialFrame(pl.DataFrame({"schema": ["a"], "sum_assured": [100_000.0]}))

    # The refusal says the next move, as its two siblings in the same ladder
    # do. A frame that names the conflict and stops there leaves the reader
    # to find out for themselves what does work.
    with pytest.raises(
        AttributeError,
        match=r"conflicts with existing method/attribute; use af\['schema'\] instead",
    ):
        _ = af.schema

    assert "schema" in af.columns
    assert af.collect()["schema"].to_list() == ["a"]
