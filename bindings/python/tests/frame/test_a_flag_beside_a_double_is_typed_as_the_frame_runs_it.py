# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A conditional with a flag beside a double is a double before the frame runs, too.

``when(af.smoker == "Y").then(False).otherwise(3.25)`` ran and answered
``Float64`` ``[0.0, 3.25]``, but Polars types the pair as ``Unknown`` before it
runs, so the frame recorded no type for the column and the export refused a
model that had run, calling a ``Float64`` column "type Unknown" (section 10:
a producer must never write ``unknown`` for a type it met). The flag is read
as its 0.0/1.0 double where the other branch is a double, as it already was
beside a whole number and a fixed-point decimal (11.1.25, 11.1.28).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame(
    {"smoker": ["Y", "N"], "age": [50, 40], "load": [1.5, 2.5], "flag": [True, False]}
)
_LINES: dict[str, tuple[Callable[[ActuarialFrame], object], list[float]]] = {
    "a false flag then a double": (
        lambda af: when(af.smoker == "Y").then(False).otherwise(3.25),  # noqa: FBT003
        [0.0, 3.25],
    ),
    "a double then a false flag": (
        lambda af: when(af.age > 45).then(2.5).otherwise(False),  # noqa: FBT003
        [2.5, 0.0],
    ),
    "a stored flag then a double": (
        lambda af: when(af.age > 45).then(af.flag).otherwise(3.25),
        [1.0, 3.25],
    ),
    "a chain": (
        lambda af: (
            when(af.age > 45).then(False).when(af.age > 30).then(0.5).otherwise(2.0)  # noqa: FBT003
        ),
        [0.0, 0.5],
    ),
}


@pytest.mark.parametrize("line", list(_LINES))
def test_the_record_names_the_double_the_frame_runs(line: str) -> None:
    make, expected = _LINES[line]
    af = ActuarialFrame(_BOOK)
    af.r = make(af)
    assert af.schema["r"] == pl.Float64
    out = af.collect()
    assert out["r"].to_list() == expected
    document = json.loads(GraphExporter(af).export(out, profile="executable"))
    (node,) = [one for one in document["nodes"] if one["column"] == "r"]
    assert node["dtype"] == "f64"
