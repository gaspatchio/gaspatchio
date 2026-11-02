# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A join bringing a list or a date column refuses as this engine's limit.

Section 15 carries a ``date`` or ``list[T]`` column in a join payload, and the
reference producer answers a join that brings one. This engine holds a column
a join brings only as a number, a whole number, a flag or text, so it refuses
-- but it said the column's type was one "a payload cell is not", cited the
lookup clause, and sent the reader to re-export, which changes nothing. It now
names the join clause and Polars. A ``list[f64]`` holding a NaN or an
infinity died before that, inside the export, until the payload wrote the
sentinel inside a list; it reaches the same refusal now.
"""

from __future__ import annotations

import datetime as dt
import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines.report import EngineRefusal

_DAYS = [dt.date(2025, 1, 1), dt.date(2026, 6, 30)]
_RIGHT_SIDES = {
    "list[f64] NaN": [[math.nan, 1.0], [2.0]],
    "list[f64] +inf": [[math.inf], [1.0]],
    "list[f64] -inf": [[-math.inf], [1.0]],
    "list[f64]": [[0.5, 1.0], [2.0]],
    "list[date]": [_DAYS, [_DAYS[0]]],
    "date": _DAYS,
}


@pytest.mark.parametrize("what", list(_RIGHT_SIDES))
def test_the_refusal_names_the_join_clause_and_polars(what: str) -> None:
    right = pl.DataFrame({"k": [1, 2], "c": _RIGHT_SIDES[what]})
    af = ActuarialFrame(pl.DataFrame({"pid": [1, 2], "k": [1, 2]})).join(right, on="k")
    af.out = af.k * 2
    assert af.collect()["out"].to_list() == [2, 4]

    with pytest.raises(EngineRefusal) as refused:
        af.collect(engine="jax")
    said = str(refused.value)
    assert "brings the column 'c' as " in said
    assert "run this model on Polars" in said
    assert "11.1.2" in said
    assert "payload cell is not" not in said
