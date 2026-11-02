# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A table shock reaches its scenario's fingerprint through the table's content.

Section 13.2: a shocked scenario's figure moves through the table's content,
not through anything else. A scenario composed alone read its shocked table
through a copy registered as ``<name>_shocked``, and a lookup's bytes carry
the table's name, so an identity shock (x 1.0, + 0.0), whose rates are BASE's,
still moved the figure, and a real one could only be reproduced by a model
whose table was named ``<name>_shocked``. The record now reads each copy as
the table the model named: an identity shock gives BASE's figure, and a x 1.1
shock gives the figure the model gives over the x 1.1 rates under the table's
own name.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, ScenarioRun
from gaspatchio.assumptions import Table
from gaspatchio.mortality import MortalityTable
from gaspatchio.scenarios import AdditiveShock, MultiplicativeShock, Sum

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_RATES = pl.DataFrame({"age": [40, 41, 42, 43], "qx": [0.001, 0.002, 0.003, 0.004]})
_BOOK = pl.DataFrame({"policy_id": [1, 2], "age": [40, 41], "sa": [1000.0, 2000.0]})


def _model(
    rates: pl.DataFrame, read: str
) -> Callable[[ActuarialFrame], ActuarialFrame]:
    def main(af: ActuarialFrame) -> ActuarialFrame:
        table = Table(
            name="w5_bug24_mortality",
            source=rates,
            dimensions={"age": "age"},
            value="qx",
        )
        af = af.projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="term_months",
            until_value=2,
            frequency="monthly",
        )
        q = (
            MortalityTable(
                table, structure="aggregate", age_basis="age_last_birthday"
            ).at(age=af.age)
            if read == "mortality"
            else table.lookup(age=af.age)
        )
        af.claims = af.sa * q + af.month * 0.0
        af.pv = af.claims.list.sum()
        return af

    return main


def _run(
    tmp_path: Path, read: str, shocks: dict[str, list[object]], rates: pl.DataFrame
) -> tuple[dict[str, str | None], dict[str, float]]:
    plan = ScenarioRun(
        shocks=shocks,  # type: ignore[arg-type]
        aggregations=(Sum("pv").alias("t").over("scenario_id"),),
    )
    result = plan.run(
        ActuarialFrame(_BOOK), _model(rates, read), audit=tmp_path / "run.audit.json"
    )
    folded = result.aggregations["t"]
    assert isinstance(folded, pl.DataFrame)
    stamps = result.graph_fingerprint_by_scenario
    assert stamps is not None
    return dict(stamps), dict(zip(folded["scenario_id"], folded["t"], strict=True))


@pytest.mark.parametrize("read", ["lookup", "mortality"])
def test_an_identity_shock_leaves_base_s_figure(tmp_path: Path, read: str) -> None:
    table = "w5_bug24_mortality"
    stamps, totals = _run(
        tmp_path,
        read,
        {
            "BASE": [],
            "MUL1": [MultiplicativeShock(factor=1.0, table=table)],
            "ADD0": [AdditiveShock(delta=0.0, table=table)],
            "MUL11": [MultiplicativeShock(factor=1.1, table=table)],
        },
        _RATES,
    )

    # By hand over three boundaries: 1000 x 0.001 x 3 + 2000 x 0.002 x 3.
    assert totals["BASE"] == 15.0
    assert totals["MUL1"] == totals["ADD0"] == 15.0
    assert stamps["MUL1"] == stamps["ADD0"] == stamps["BASE"]
    assert stamps["MUL11"] != stamps["BASE"]

    by_hand, _ = _run(
        tmp_path / "by_hand",
        read,
        {"BASE": []},
        _RATES.with_columns(pl.col("qx") * 1.1),
    )
    assert stamps["MUL11"] == by_hand["BASE"]
