# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A sampled number is the number the run wrote, not a display of it (R80b).

Every value an artifact carries used to be rounded to six decimal places on
its way in. A reader who rebuilt a policy's timeline from the file and held
it against the results parquet beside it -- the file ``model.results`` pins
by digest -- matched 1,554 of 2,109 cells in one model, and a check at
``1e-9`` in another reported 174 false mismatches out of 297. The ruling is
full precision: a float travels as its binary64 value, JSON writes the
shortest decimal that reads back to it, and a sample parsed out of the
document is the results cell bit for bit. These tests hold that for every
place a number reaches the wire -- the samples on every policy of the axis,
the branch a condition did not take, the numbers a walk-through carries, and
the book's own fold -- and hold that the non-finite spellings of section 10
did not move with it.
"""

from __future__ import annotations

import json
import math
import struct
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph.value_extractor import one_value_on_the_wire

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# Numbers chosen so that six decimals cannot hold them: a third, a rate with
# twelve significant figures, and a run of each per period. A model of round
# numbers would pass with the rounding still in place.
_MODEL = """
import datetime
from gaspatchio import ActuarialFrame, when


def main(af: ActuarialFrame, params=None) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    af.third = af.sum_assured / 3
    af.rate = af.sum_assured * 0.000123456789123 / 7
    af.claims = af.sum_assured * 0.0001 * (af.month + 1) / 3
    af.reserve = when(af.month > 2).then(af.claims).otherwise(af.claims / 7)
    return af
"""

_BOOK = pl.DataFrame(
    {"policy_id": [1, 2, 3], "sum_assured": [100_000.0, 123_456.789, 7.0]}
)


def _bits(value: float) -> bytes:
    """Return the eight bytes of one double, so equality is bit equality."""
    return struct.pack("<d", value)


def _export(tmp_path: Path, *extra: str) -> tuple[dict[str, Any], pl.DataFrame]:
    """Export the model over the three-policy book; return the document and results."""
    model = tmp_path / "model.py"
    model.write_text(_MODEL)
    book = tmp_path / "book.parquet"
    _BOOK.write_parquet(book)
    out = tmp_path / "graph.json"
    results = tmp_path / "results.parquet"
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(book),
            "-o",
            str(out),
            "--results",
            str(results),
            *extra,
        ],
    )
    assert result.exit_code == 0, result.output
    document: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    return document, pl.read_parquet(results)


def _node(document: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node carrying ``node_id``."""
    return next(node for node in document["nodes"] if node["id"] == node_id)


def _cells(sample: Any, held: Any) -> list[tuple[Any, Any]]:  # noqa: ANN401 -- a sampled value, of whatever shape the column holds
    """Pair a sample with the results cell it is of, period by period."""
    if isinstance(held, list):
        assert isinstance(sample, list)
        assert len(sample) == len(held)
        return list(zip(sample, held, strict=True))
    return [(sample, held)]


def test_every_sampled_number_is_the_results_cell_bit_for_bit(tmp_path: Path) -> None:
    """On every policy of the axis, every float sample is the parquet's own double."""
    document, results = _export(tmp_path, "--policies", "all")
    width = len(document["policies"])
    assert width == len(_BOOK)
    compared = rounding_would_have_moved = 0

    for node in document["nodes"]:
        if (
            node.get("in_final_schema") is not True
            or node["column"] not in results.columns
        ):
            continue
        for position, entry in enumerate(document["policies"]):
            row = results.filter(
                pl.col("policy_id").cast(pl.String) == entry["policy_id"]
            )
            held = row[node["column"]][0]
            held = held.to_list() if isinstance(held, pl.Series) else held
            for wrote, cell in _cells(node["value_sample"][position], held):
                if not isinstance(cell, float):
                    continue
                assert isinstance(wrote, float), (node["id"], wrote, cell)
                assert _bits(wrote) == _bits(cell), (node["id"], wrote, cell)
                compared += 1
                rounding_would_have_moved += round(cell, 6) != cell

    # The comparison has to have been one the rounding would have failed.
    assert compared > 0
    assert rounding_would_have_moved > 0


def test_a_branch_the_condition_did_not_take_carries_its_whole_value(
    tmp_path: Path,
) -> None:
    """``otherwise`` is the branch evaluated, every period, not that branch rounded."""
    document, results = _export(tmp_path, "--branches")
    claims = results["claims"][0].to_list()
    branches = _node(document, "reserve@1")["branches"]

    assert [_bits(one) for one in branches["then"]] == [_bits(one) for one in claims]
    assert [_bits(one) for one in branches["otherwise"]] == [
        _bits(one / 7) for one in claims
    ]


def test_a_walk_through_ends_at_the_whole_number_beside_it(tmp_path: Path) -> None:
    """A trace's numbers are the column's own, not a rounding of them."""
    document, results = _export(tmp_path)
    third = _node(document, "third@1")
    held = results["third"][0]

    assert third["trace"][-1]["result"] == held
    assert _bits(third["trace"][-1]["result"]) == _bits(held)
    assert _bits(third["value_sample"]) == _bits(held)
    assert held != round(held, 6)


def test_the_books_fold_carries_its_whole_value(tmp_path: Path) -> None:
    """The fold at the head of the axis is the book's sum, not that sum rounded."""
    document, results = _export(tmp_path, "--portfolio-by", "sum:third,claims")
    # One fold entry per accumulator kind: a sum over a column holding one
    # value per policy, a period-by-period sum over a per-period one.
    at = {entry["aggregation"]: k for k, entry in enumerate(document["policies"])}

    folded = _node(document, "third@1")["value_sample"][at["sum"]]
    expected = math.fsum(results["third"].to_list())
    # A few units in the last place of a sum of three: the fold adds in the
    # engine's order and fsum exactly. Six decimals is thousands of times
    # wider than this on a value of this size.
    assert math.isclose(folded, expected, rel_tol=1e-15, abs_tol=0.0)
    assert folded != round(folded, 6)

    per_period = _node(document, "claims@1")["value_sample"][at["period_sum"]]
    by_period = zip(*results["claims"].to_list(), strict=True)
    for wrote, cells in zip(per_period, by_period, strict=True):
        assert math.isclose(wrote, math.fsum(cells), rel_tol=1e-15, abs_tol=0.0)


@pytest.mark.parametrize(
    "value",
    [1 / 3, 0.1 + 0.2, 0.0008712345678, 5e-324, 1.7976931348623157e308, -0.0, 1e21],
    ids=["third", "tenths", "rate", "subnormal", "largest", "negative-zero", "big"],
)
def test_one_value_reads_back_bit_for_bit_through_json(value: float) -> None:
    """The wire's own writer and reader give back the same eight bytes."""
    read = json.loads(json.dumps(one_value_on_the_wire(value)))

    assert _bits(read) == _bits(value)


@pytest.mark.parametrize(
    ("value", "spelled"),
    [(math.nan, "NaN"), (math.inf, "Infinity"), (-math.inf, "-Infinity")],
)
def test_a_non_finite_value_keeps_its_section_10_spelling(
    value: float, spelled: str
) -> None:
    """Full precision moved the finite numbers and nothing else."""
    assert one_value_on_the_wire(value) == spelled
