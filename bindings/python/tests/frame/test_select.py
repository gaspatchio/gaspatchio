# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The frame's ``select``: each call Polars accepts, read as Polars reads it."""

from __future__ import annotations

import inspect
import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.frame import base
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.execution import inspect_execution

if TYPE_CHECKING:
    from collections.abc import Callable

_HERE = Path(__file__).name

_BOOK = pl.DataFrame({"policy_id": [1, 2], "premium": [100.0, 200.0], "term": [10, 20]})


@pytest.mark.parametrize(
    "names",
    [
        pytest.param(["policy_id", "term"], id="a_list"),
        pytest.param(("policy_id", "term"), id="a_tuple"),
        pytest.param(iter(["policy_id", "term"]), id="an_iterator"),
    ],
)
def test_a_list_of_names_selects_those_columns(names: object) -> None:
    """One list of names is the names, as Polars reads it, not a list literal."""
    af = ActuarialFrame(_BOOK)

    selected = af.select(names)

    assert selected.collect().columns == ["policy_id", "term"]


def test_a_list_of_names_takes_named_expressions_beside_it() -> None:
    af = ActuarialFrame(_BOOK)

    selected = af.select(["policy_id"], doubled=af.premium * 2)

    assert selected.collect().to_dict(as_series=False) == {
        "policy_id": [1, 2],
        "doubled": [200.0, 400.0],
    }


def test_names_one_by_one_still_select_those_columns() -> None:
    af = ActuarialFrame(_BOOK)

    assert af.select("premium", af.term).collect().columns == ["premium", "term"]


# --- what a select records ------------------------------------------------------
#
# A select that hands a column back as it stands defines nothing. One that
# computes a column defines it: under a name the frame holds, a redefinition,
# and under a new name, a new definition, each recorded at the select's line
# the way with_columns records one.


def _line_after() -> int:
    """Return the number of the line after the caller's."""
    caller = inspect.currentframe()
    assert caller is not None
    assert caller.f_back is not None
    return caller.f_back.f_lineno + 1


def _document(af: ActuarialFrame) -> dict[str, Any]:
    """Return ``af``'s executable artifact."""
    exported: dict[str, Any] = json.loads(
        GraphExporter(af).export(profile="executable")
    )
    return exported


def _nodes(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in document["nodes"]}


def test_a_select_that_writes_over_an_input_records_the_definition() -> None:
    """The select replaces ``a``; the calculation log says so, at its line."""
    af = ActuarialFrame(pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]}))
    af.x = af.a * 2
    line = _line_after()
    af = af.select(pl.all().exclude("a"), (pl.col("a") * 10).alias("a"))

    document = _document(af)
    nodes = _nodes(document)

    assert af.collect().to_dict(as_series=False) == {
        "b": [3.0, 4.0],
        "x": [2.0, 4.0],
        "a": [10.0, 20.0],
    }
    assert nodes["a@1"]["in_final_schema"] is True
    assert nodes["a@1"]["reads"] == ["a"]
    assert str(nodes["a@1"]["source_location"]).endswith(f"{_HERE}:{line}")
    assert nodes["x@1"]["reads"] == ["a"]
    assert af.graph.holes() == []
    assert validate_artifact(document).ok
    # A second engine is handed Polars' own line for a@1, and says it cannot
    # run it, rather than answering from the book's a.
    assert any(
        finding.where.startswith("/nodes/a@1")
        for finding in inspect_execution(document).findings
    )


def _tracked_fund() -> tuple[ActuarialFrame, Any]:
    """Return a frame holding a rollforward's state, and its compilation."""
    af = ActuarialFrame(
        pl.DataFrame(
            {"av_init": [1000.0], "fund_return": [[0.01] * 3], "fee": [[5.0] * 3]}
        )
    )
    af = af.projection.set(
        start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    b = af.projection.rollforward(states={"av": af["av_init"]})
    b["av"].grow(af["fund_return"])
    b["av"].subtract(af["fee"])
    compiled = compile_rollforward(b)
    af.av = compiled.expr_for("av")
    return af, compiled


def test_a_select_that_writes_over_a_rollforward_input_moves_its_run() -> None:
    """A later read of the run is refused, as after an assignment over the input."""
    af, compiled = _tracked_fund()
    af = af.select(
        pl.all().exclude("fund_return"),
        (pl.col("fund_return") * 10).alias("fund_return"),
    )

    assert af.collect()["av"].to_list()[0] == pytest.approx(
        [1005.0, 1010.05, 1015.1505]
    )
    with pytest.raises(ValueError, match="'fund_return' was written again"):
        af.av_again = compiled.expr_for("av")


@pytest.mark.parametrize(
    "select",
    [
        pytest.param(lambda af: af.select(pl.all()), id="every_column"),
        pytest.param(
            lambda af: af.select("policy_id", "premium", "term", "loading"),
            id="names_one_by_one",
        ),
        pytest.param(
            lambda af: af.select(af.policy_id, af.premium, af.term, af.loading),
            id="columns_of_the_frame",
        ),
        pytest.param(
            lambda af: af.select(pl.col("premium").alias("premium"), "loading"),
            id="a_column_under_its_own_name",
        ),
        pytest.param(
            lambda af: af.select("loading", "term", "premium", "policy_id"),
            id="a_reorder",
        ),
        pytest.param(lambda af: af.select(pl.all().exclude("term")), id="a_drop"),
        pytest.param(lambda af: af.select(["premium", "loading"]), id="a_list"),
        pytest.param(lambda af: af.select(pl.col(pl.Float64)), id="a_type"),
        pytest.param(lambda af: af.select(premium="premium"), id="a_name_to_itself"),
        pytest.param(
            lambda af: af.select(
                pl.all().exclude("policy_id"), pl.col("policy_id").set_sorted()
            ),
            id="a_column_marked_sorted",
        ),
        pytest.param(
            lambda af: af.select(
                pl.all().exclude("premium"), pl.col("premium").cast(pl.Float64)
            ),
            id="a_column_cast_to_its_own_type",
        ),
        pytest.param(
            lambda af: af.select(
                pl.all().exclude("premium"),
                pl.col("premium").cast(pl.Float64, strict=False),
            ),
            id="a_column_cast_to_its_own_type_leniently",
        ),
        pytest.param(
            lambda af: af.select(
                pl.all().exclude("term"), pl.col("term").gather_every(1)
            ),
            id="every_row_of_a_column_kept",
        ),
        pytest.param(
            lambda af: af.select(pl.all().set_sorted()),
            id="every_column_marked_sorted",
        ),
        pytest.param(
            lambda af: af.select(
                policy_id=pl.col("policy_id").set_sorted(), loading="loading"
            ),
            id="a_named_column_marked_sorted",
        ),
    ],
)
def test_a_select_that_hands_columns_back_records_nothing(
    select: Callable[[ActuarialFrame], ActuarialFrame],
) -> None:
    af = ActuarialFrame(_BOOK)
    af.loading = af.premium * 0.1
    before = list(af._calculations)  # noqa: SLF001 -- the frame's own log

    selected = select(af)

    assert selected._calculations == before  # noqa: SLF001
    assert selected.graph.holes() == []


def test_a_select_that_names_a_new_column_records_its_definition() -> None:
    """A new name is a new definition, read through the frame's own formula."""
    af = ActuarialFrame(_BOOK)
    af = af.select(pl.all(), doubled=af.premium * 2)

    node = _nodes(_document(af))["doubled@1"]

    assert (node["reads"], node["tier"]) == (["premium"], "core")
    assert af.graph.holes() == []
    assert af.collect()["doubled"].to_list() == [200.0, 400.0]


def test_a_select_that_calculates_several_columns_at_once_is_refused() -> None:
    """The refusal names each column and writes the expression for each one."""
    af = ActuarialFrame(_BOOK)

    with pytest.raises(ValueError, match="one expression per column") as refusal:
        af.select(pl.col("premium", "term") * 2)

    message = str(refusal.value)
    assert "calculates 2 columns: premium, term" in message
    assert '(pl.col("premium") * 2.0).alias("premium")' in message
    assert '(pl.col("term") * 2).alias("term")' in message
    assert "af.rename" not in message
    assert "cs." not in message
    assert "dyn int" not in message
    assert af.collect().columns == ["policy_id", "premium", "term"]


def test_a_select_that_only_renames_several_columns_points_to_rename() -> None:
    """A rename or a copy calculates nothing: say so, and name the door for it."""
    af = ActuarialFrame(_BOOK)

    with pytest.raises(ValueError, match="only renames or copies") as refusal:
        af.select(pl.all().name.suffix("_out"))

    message = str(refusal.value)
    assert "writes policy_id_out, premium_out, term_out." in message
    assert (
        'af.rename({"policy_id": "policy_id_out", "premium": "premium_out", '
        '"term": "term_out"})' in message
    )
    assert 'pl.col("premium").alias("premium_out")' in message
    assert "* 2" not in message
    assert "cs." not in message
    assert af.collect().columns == ["policy_id", "premium", "term"]


def test_a_selector_that_yields_one_column_is_refused_naming_it() -> None:
    """A selector names no column, so the refusal writes it for the one it found."""
    af = ActuarialFrame(_BOOK)

    with pytest.raises(ValueError, match="one expression per column") as refusal:
        af.select(pl.col(pl.Float64).round(1))

    message = str(refusal.value)
    assert "calculates a column: premium" in message
    assert 'pl.col("premium").round(1).alias("premium")' in message


def test_a_refusal_over_many_columns_names_the_first_few_and_counts_the_rest() -> None:
    af = ActuarialFrame({f"rate_{n}": [0.1, 0.2] for n in range(6)})

    with pytest.raises(ValueError, match="one expression per column") as refusal:
        af.select(pl.all() * 2)

    message = str(refusal.value)
    assert "rate_0, rate_1, rate_2 and 3 more" in message
    assert '(pl.col("rate_2") * 2.0).alias("rate_2"), and 3 more' in message
    assert "rate_3" not in message


def test_a_calculation_the_reader_cannot_spell_is_written_as_a_template() -> None:
    af = ActuarialFrame(_BOOK)

    with pytest.raises(ValueError, match="one expression per column") as refusal:
        af.select(pl.col("premium", "term").cum_sum())

    message = str(refusal.value)
    assert '<the calculation on pl.col("premium")>.alias("premium")' in message


def test_an_expression_the_frame_cannot_read_is_refused_in_words() -> None:
    """Where the columns cannot be named, the message says what to do in words."""
    message = base._several_columns_refusal(None)  # noqa: SLF001

    assert "writes several columns at once" in message
    assert ".alias(...)" in message
    assert "cs." not in message


def test_a_select_that_casts_a_column_to_another_type_records_it() -> None:
    """A cast that changes the type changes the values the column holds.

    Written over ``term`` with an alias that says so: unnamed, Polars would
    name the cast after the column it reads, and the frame refuses a
    calculation that overwrites a column under an inherited name
    (``test_overwrite_by_an_unnamed_expression.py``).
    """
    af = ActuarialFrame(_BOOK)
    af = af.select(
        pl.all().exclude("term"), pl.col("term").cast(pl.Float64).alias("term")
    )

    assert [
        (entry.column, entry.ordinal)
        for entry in af._calculations  # noqa: SLF001
        if entry.column == "term"
    ] == [("term", 1)]
