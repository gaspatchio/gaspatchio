# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A whole number past i64 is refused here wherever the producer refuses it.

The producer refuses arithmetic on a book column holding a value past the
signed 64-bit range, and now a sum, a running fold, an absolute value and a
rollforward reading one, and a literal past that range written into a line.
This engine carries every integer the record names as an i64, so it refuses
such a column at its door whatever reads it, and such a literal where the
document holds one; these tests pin that the two engines refuse the same
lines. A power of a whole-number literal over an integer column answers the
i64 the record names on both engines.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.rollforward import compile_rollforward
from tests.conftest import invocation

if TYPE_CHECKING:
    from collections.abc import Callable

_PAST = {pl.UInt64: 2**64 - 1, pl.Int128: -(2**70), pl.UInt128: 2**64 - 1}


def _exported(af: ActuarialFrame) -> dict[str, Any]:
    return json.loads(GraphExporter(af).export(profile="executable"))


@pytest.mark.parametrize("literal", [2**64, 2**63, -(2**63) - 1])
def test_a_literal_past_i64_in_a_document_is_refused_naming_both_moves(
    literal: int,
) -> None:
    """A document the producer would no longer write: one carrying such a literal."""
    one = invocation(
        {
            "op": "binop",
            "kind": "add",
            "left": {"op": "col", "name": "a"},
            "right": {"op": "lit", "value": literal},
        },
        {"a": {"dtype": "i64", "values": [1]}},
        "i64",
    )

    with pytest.raises(EngineRefusal) as caught:
        engine_named("jax").run(one.document, one.inputs, FrameSink())

    refused = caught.value.report.refusals[0]
    assert f"the integer literal {literal} is outside the signed 64-bit range" in (
        refused.what
    )
    assert "to_text()" in refused.move
    assert "decimal literal" in refused.move
    # Section 10 carries a whole number as an i64: the literal's range is its.
    assert refused.clause == "10"


def test_a_member_past_i64_is_refused_with_the_same_moves() -> None:
    one = invocation(
        {
            "op": "call",
            "name": "is_in",
            "args": [
                {"op": "col", "name": "a"},
                {"op": "lit", "values": [2**64, 1]},
            ],
            "attrs": {"nulls_equal": False},
        },
        {"a": {"dtype": "i64", "values": [1]}},
        "bool",
    )

    with pytest.raises(EngineRefusal) as caught:
        engine_named("jax").run(one.document, one.inputs, FrameSink())

    refused = caught.value.report.refusals[0]
    assert "the integer literal 18446744073709551616" in refused.what
    assert "to_text()" in refused.move


@pytest.mark.parametrize(
    ("written", "line", "expected"),
    [
        ("2 ** pid", lambda af: 2**af.pid, [8, 1_099_511_627_776]),
        ("(-2) ** e", lambda af: (-2) ** af.e, [4, -8]),
    ],
    ids=["2 ** pid", "(-2) ** e"],
)
def test_a_literal_base_answers_one_i64_on_both_engines(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    expected: list[int],
) -> None:
    """Hand values: 2**3 and 2**40; (-2)**2 and (-2)**3."""
    book = pl.DataFrame({"pid": [3, 40], "e": [2, 3]})
    af = ActuarialFrame(book)
    af.r = line(af)
    produced = af.collect()

    result = engine_named("jax").run(_exported(af), book, FrameSink())

    assert produced["r"].to_list() == expected
    assert result.columns["r"].to_list() == expected
    assert produced.schema["r"] == result.columns["r"].dtype == pl.Int64


# The reads the producer now refuses on a column still wider than i64, each
# exported over the i64 book it was written against.
_READS: list[tuple[str, Callable[[Any], Any]]] = [
    ("ids.list.sum()", lambda af: af.ids.list.sum()),
    ("ids.cum_sum()", lambda af: af.ids.cum_sum()),
    ("ids.cum_prod()", lambda af: af.ids.cum_prod()),
    ("pid.abs()", lambda af: af.pid.abs()),
]


def _book(
    width: type[pl.DataType], pid: list[int], ids: list[list[int]]
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "pid": pl.Series(pid, dtype=width),
            "ids": pl.Series(ids, dtype=pl.List(width)),
        }
    )


@pytest.mark.parametrize(("written", "line"), _READS, ids=[r[0] for r in _READS])
@pytest.mark.parametrize("width", list(_PAST), ids=str)
def test_a_fold_over_a_column_past_i64_is_refused_at_the_door(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    width: type[pl.DataType],
) -> None:
    af = ActuarialFrame(_book(pl.Int64, [-7, 8], [[1, 2], [3, 4]]))
    af.r = line(af)
    document = _exported(af)
    past = _PAST[width]

    with pytest.raises(EngineRefusal) as caught:
        engine_named("jax").run(
            document, _book(width, [7, past], [[1, 2], [past, 4]]), FrameSink()
        )

    refused = caught.value.report.refusals[0]
    assert refused.group == "inputs"
    assert f"holds {past}, which is outside the signed 64-bit range" in refused.what


@pytest.mark.parametrize("width", list(_PAST), ids=str)
def test_a_fold_over_a_wide_column_that_fits_answers_the_producer_s_numbers(
    width: type[pl.DataType],
) -> None:
    """Hand values: [1 + 2, 3 + 4], [[1, 3], [3, 7]], [7, 8]."""
    signed = _book(pl.Int64, [7, 8], [[1, 2], [3, 4]])
    af = ActuarialFrame(signed)
    af.s = af.ids.list.sum()
    af.c = af.ids.cum_sum()
    af.a = af.pid.abs()

    result = engine_named("jax").run(
        _exported(af), _book(width, [7, 8], [[1, 2], [3, 4]]), FrameSink()
    )

    assert result.columns["s"].to_list() == [3, 7]
    assert result.columns["c"].to_list() == [[1, 3], [3, 7]]
    assert result.columns["a"].to_list() == [7, 8]


def _rollforward_model(book: pl.DataFrame) -> ActuarialFrame:
    af = ActuarialFrame(book).projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    b = af.projection.rollforward(states={"av": af["av_init"]})
    b["av"].add(af["premium"]).grow(af["rate"])
    af.av = compile_rollforward(b).expr_for("av")
    return af


def _rollforward_book(premium: pl.Series) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "av_init": [100.0, 5.0],
            "premium": premium,
            "rate": [[0.0] * 3, [0.0] * 3],
        }
    )


@pytest.mark.parametrize("width", list(_PAST), ids=str)
def test_a_rollforward_over_a_premium_past_i64_is_refused_at_the_door(
    width: type[pl.DataType],
) -> None:
    """The producer refuses this run by name; this engine refuses the book."""
    document = _exported(
        _rollforward_model(
            _rollforward_book(pl.Series([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]))
        )
    )
    past = _PAST[width]
    book = _rollforward_book(pl.Series([[1, 2, 3], [past, 5, 6]], dtype=pl.List(width)))

    with pytest.raises(EngineRefusal) as caught:
        engine_named("jax").run(document, book, FrameSink())

    refused = caught.value.report.refusals[0]
    assert refused.group == "inputs"
    assert f"holds {past}, which is outside the signed 64-bit range" in refused.what


def test_a_rollforward_reading_an_integer_column_is_refused_by_the_tree() -> None:
    """Section 16.1's subset reads f64 operands, so an integer one never runs here."""
    book = _rollforward_book(pl.Series([[1, 2, 3], [4, 5, 6]], dtype=pl.List(pl.Int64)))
    document = _exported(_rollforward_model(book))

    with pytest.raises(EngineRefusal) as caught:
        engine_named("jax").run(document, book, FrameSink())

    assert any(
        "Add reads 'premium', carried as list[i64]" in refusal.what
        for refusal in caught.value.report.refusals
    )
