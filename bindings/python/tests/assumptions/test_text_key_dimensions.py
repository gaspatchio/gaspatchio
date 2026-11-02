# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A text dimension whose cells look like numbers, read both ways it can be.

A published table often keys a parameter by labels that happen to be digits:
maturity bands ``"1"`` and ``"5"``, plan codes ``"10"`` and ``"20"``. Left
undeclared, such a column is judged on the numbers it spells, so the same
values carry one processed type and one content hash whichever type the file
writer chose (§15 of ``spec/graph-artifact/v0-preview.md``). That judgement is
kept, and tested in ``test_numeric_key_conversion.py``.

Two things around it were wrong. A dimension the author *declared* text with
``DataDimension(dtype=pl.String)`` was judged on its numbers anyway, so the
declaration did nothing. And a text key looked up against a dimension judged
numeric missed with "missing keys (k="5")" -- while the printed table held a
row the reader could see was "5" -- because a text key never matches a number
(§11.1.24 puts the pair outside the lookup's domain). The declaration now
holds, and the cross-family read is refused when the lookup is written, with
both ways out named.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import DataDimension, Table
from gaspatchio.scenarios._stack import stack_shocked_table
from gaspatchio.scenarios.shocks import MultiplicativeShock


def _declared_text(name: str, *, storage_mode: str = "auto") -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"maturity": ["1", "5"], "m": [0.7, 0.55]}),
        dimensions={"maturity": DataDimension(column="maturity", dtype=pl.String)},
        value="m",
        storage_mode=storage_mode,
    )


def _undeclared(name: str, *, on_missing: str = "raise") -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"maturity": ["1", "5"], "m": [0.7, 0.55]}),
        dimensions={"maturity": "maturity"},
        value="m",
        on_missing=on_missing,
    )


def test_a_declared_text_dimension_stays_text() -> None:
    table = _declared_text("declared_text_stays_text")

    assert table.to_dataframe()["maturity"].dtype == pl.String
    assert sorted(table.dimension_values("maturity")) == ["1", "5"]


def test_a_declared_text_dimension_answers_text_keys() -> None:
    af = ActuarialFrame({"k": ["5", "1"]})
    af.value = _declared_text("declared_text_answers").lookup(maturity=af.k)

    assert af.collect()["value"].to_list() == [0.55, 0.7]


def test_a_declared_text_dimension_keeps_spellings_apart() -> None:
    """Judged on numbers, "05" and "5" are one key and the table duplicates it."""
    table = Table(
        name="declared_text_spellings",
        source=pl.DataFrame({"band": ["05", "5"], "m": [0.1, 0.2]}),
        dimensions={"band": DataDimension(column="band", dtype=pl.String)},
        value="m",
    )
    af = ActuarialFrame({"k": ["5", "05"]})
    af.value = table.lookup(band=af.k)

    assert af.collect()["value"].to_list() == [0.2, 0.1]


def test_a_shocked_declared_text_table_stays_text() -> None:
    """Rebuilding from the processed frame keeps the declaration it was built on."""
    shocked = _declared_text("declared_text_base").with_shock(
        MultiplicativeShock(factor=2.0)
    )
    af = ActuarialFrame({"k": ["5"]})
    af.value = shocked.lookup(maturity=af.k)

    assert shocked.to_dataframe()["maturity"].dtype == pl.String
    assert af.collect()["value"].to_list() == [1.1]


def test_an_extended_declared_text_table_stays_text() -> None:
    # Appending needs hash storage; array storage refuses an append outright.
    table = _declared_text("declared_text_extended", storage_mode="hash")
    table.extend(pl.DataFrame({"maturity": ["10"], "m": [0.4]}))
    af = ActuarialFrame({"k": ["10", "1"]})
    af.value = table.lookup(maturity=af.k)

    assert table.to_dataframe()["maturity"].dtype == pl.String
    assert af.collect()["value"].to_list() == [0.4, 0.7]


def test_a_scenario_stack_of_a_declared_text_table_stays_text() -> None:
    stacked = stack_shocked_table(
        _declared_text("declared_text_stacked"),
        {"BASE": [], "UP": [MultiplicativeShock(factor=2.0)]},
    )
    af = ActuarialFrame({"k": ["5", "5"], "scenario_id": ["BASE", "UP"]})
    af.value = stacked.lookup(maturity=af.k, scenario_id=af.scenario_id)

    assert stacked.to_dataframe()["maturity"].dtype == pl.String
    assert af.collect()["value"].to_list() == [0.55, 1.1]


def test_an_undeclared_digit_column_is_still_judged_on_its_numbers() -> None:
    table = _undeclared("undeclared_digits_numeric")
    af = ActuarialFrame({"k": [5, 1]})
    af.value = table.lookup(maturity=af.k)

    assert table.to_dataframe()["maturity"].dtype == pl.Float64
    assert af.collect()["value"].to_list() == [0.55, 0.7]


@pytest.mark.parametrize("on_missing", ["raise", "nan"])
def test_a_text_key_against_a_numeric_dimension_is_refused_naming_both_fixes(
    on_missing: str,
) -> None:
    """Refused when written, whatever the miss policy: it is not a miss."""
    table = _undeclared(f"text_key_refused_{on_missing}", on_missing=on_missing)
    af = ActuarialFrame({"k": ["5", "1"]})

    with pytest.raises(TypeError) as caught:
        table.lookup(maturity=af.k)

    message = str(caught.value)
    assert "'maturity'" in message
    assert "text" in message
    assert ".cast(pl.Float64)" in message
    assert "DataDimension(column='maturity', dtype=pl.String)" in message


def test_a_bare_text_value_against_a_numeric_dimension_is_refused() -> None:
    with pytest.raises(TypeError, match="'maturity'"):
        _undeclared("bare_text_value_refused").lookup(maturity="5")


def test_a_per_period_text_key_against_a_numeric_dimension_is_refused() -> None:
    af = ActuarialFrame({"k": ["5"]})
    af = af.projection.set(
        start_date=datetime.date(2026, 1, 31), n_periods=2, frequency="annual"
    )
    af.k_t = af.k.projection.broadcast_to_periods()

    with pytest.raises(TypeError, match="'maturity'"):
        _undeclared("per_period_text_key_refused").lookup(maturity=af.k_t)
