# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A NaN or an infinity a join brings is a value, as Polars brings it (GSP-217).

A non-finite answer from a lookup is a miss (11.1.24), because a rate table
holding NaN has no rate there. A value arriving through a join is the right
side's own data, so it arrives as it is. Only a cell holding nothing at all is
blank: this engine holds no absent number, and it refuses that by name.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines.report import EngineRefusal

_BOOK = pl.DataFrame({"pid": [1, 2], "rider": ["ADB", "WOP"], "sa": [100.0, 200.0]})


def _joined(cell: float | None) -> ActuarialFrame:
    right = pl.DataFrame(
        {"rider": ["ADB", "WOP"], "rate": [0.5, cell]},
        schema={"rider": pl.String, "rate": pl.Float64},
    )
    return ActuarialFrame(_BOOK).join(right, on="rider")


@pytest.mark.parametrize("cell", [math.nan, math.inf, -math.inf])
def test_an_unread_non_finite_value_arrives_as_polars_brings_it(cell: float) -> None:
    af = _joined(cell)

    assert repr(af.collect(engine="jax")["rate"].to_list()) == repr(
        af.collect()["rate"].to_list()
    )


@pytest.mark.parametrize("cell", [math.nan, math.inf, -math.inf])
def test_a_formula_reading_it_agrees_with_polars(cell: float) -> None:
    af = _joined(cell)
    af.charge = af.sa * af.rate

    assert repr(af.collect(engine="jax")["charge"].to_list()) == repr(
        af.collect()["charge"].to_list()
    )


def test_a_cell_holding_nothing_is_still_refused_when_read() -> None:
    af = _joined(None)
    af.charge = af.sa * af.rate

    with pytest.raises(EngineRefusal, match="carries no value"):
        af.collect(engine="jax")
