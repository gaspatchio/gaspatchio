# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio calc-graph --portfolio`` folds the book as one batch, whatever the machine.

The fold ran the model a second time through ``run_aggregated`` with the
batch size left to the memory budget, whose seed is a tenth of the book. A
batch runner refuses a setup that collected and rebuilt its frame in a batch
of several, because the batch cannot see whether that setup read across rows
(section 13.2). So a 0.9-template model -- ``mp = af.collect()``, a join in
plain Polars, ``ActuarialFrame(mp)`` -- was refused under ``--portfolio`` on a
book of three policies, and whether a bigger book was refused depended on how
much memory the reviewer's machine had. The command's first run already holds
every policy's values at once: the frame is the book there, and it is the
book in the fold too, so the fold now runs the book whole and is that run's
own total on every machine.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

import gaspatchio.scenarios._aggregated as aggregated
from gaspatchio.cli import app

if TYPE_CHECKING:
    from pathlib import Path

_HEAD = """
import datetime

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import Sum

AGGREGATIONS = (Sum("pv_prem").alias("total"),)
LOADS = pl.DataFrame({"product": ["A", "B"], "load": [1.1, 1.0]})


def finish(af):
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=3,
        frequency="monthly",
    )
    af.prem = af.premium * af.load + af.month * 0.0
    af.pv_prem = af.prem.list.sum()
    return af
"""

# The 0.9 template: the setup joins a side file in plain Polars and rebuilds.
_JOINED = (
    _HEAD
    + """

def main(af):
    mp = af.collect().join(LOADS, on="product", how="left", maintain_order="left")
    return finish(ActuarialFrame(mp))
"""
)

# A setup that reads across rows: each premium's share of the largest.
_SHARE = (
    _HEAD
    + """

def main(af):
    mp = af.collect()
    mp = mp.with_columns((pl.col("premium") / pl.col("premium").max()).alias("load"))
    return finish(ActuarialFrame(mp))
"""
)

# By hand. Premiums 100 (A), 400 (B), 300 (A), four boundaries each.
# Joined: (100 * 1.1 + 400 * 1.0 + 300 * 1.1) * 4 = 840 * 4 = 3360.
# Share: load = premium / 400, so (25 + 400 + 225) * 4 = 650 * 4 = 2600.
_HAND = {"joined": 3360.0, "share": 2600.0}


def _calc_graph(tmp_path: Path, source: str) -> tuple[Any, dict[str, Any] | None]:
    model = tmp_path / "model.py"
    model.write_text(source)
    book = tmp_path / "book.parquet"
    pl.DataFrame(
        {
            "policy_id": [1, 2, 3],
            "premium": [100.0, 400.0, 300.0],
            "product": ["A", "B", "A"],
        }
    ).write_parquet(book)
    out = tmp_path / "graph.json"
    result = CliRunner().invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(book),
            "-o",
            str(out),
            "--portfolio",
            "--policies",
            "1",
        ],
    )
    return result, (json.loads(out.read_text()) if result.exit_code == 0 else None)


def _the_fold(document: dict[str, Any]) -> float:
    (at,) = [i for i, e in enumerate(document["policies"]) if e["aggregation"]]
    node = next(n for n in document["nodes"] if n.get("column") == "pv_prem")
    return float(node["value_sample"][at])


def _cut_into_batches_of_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the memory budget cut any book into batches of one policy."""
    monkeypatch.setattr(aggregated, "bounded_seed_size", lambda _n: 1)
    monkeypatch.setattr(aggregated, "size_to_budget", lambda *_a, **_k: 1)


@pytest.mark.parametrize(
    ("name", "source"),
    [("joined", _JOINED), ("share", _SHARE)],
    ids=["joined", "share"],
)
def test_a_setup_that_rebuilds_its_frame_is_folded_over_the_whole_book(
    name: str, source: str, tmp_path: Path
) -> None:
    result, document = _calc_graph(tmp_path, source)

    assert result.exit_code == 0, result.output
    assert document is not None
    assert _the_fold(document) == pytest.approx(_HAND[name], rel=1e-12)


@pytest.mark.parametrize(
    ("name", "source"),
    [("joined", _JOINED), ("share", _SHARE)],
    ids=["joined", "share"],
)
def test_the_fold_does_not_depend_on_the_machine_s_memory(
    name: str, source: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cut_into_batches_of_one(monkeypatch)

    result, document = _calc_graph(tmp_path, source)

    assert result.exit_code == 0, result.output
    assert document is not None
    assert _the_fold(document) == pytest.approx(_HAND[name], rel=1e-12)


def test_the_fold_asks_for_one_batch_the_size_of_the_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[object] = []
    real = aggregated.run_aggregated

    def spy(*args: object, **kwargs: object) -> object:
        asked.append(kwargs.get("batch_size", "auto"))
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("gaspatchio.scenarios.run_aggregated", spy)

    result, _ = _calc_graph(tmp_path, _JOINED)

    assert result.exit_code == 0, result.output
    assert asked == [3]
