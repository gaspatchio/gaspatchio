# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A plan whose schema cannot be resolved is refused at export, not written untyped.

A model whose plan Polars cannot type -- ``af.code * af.rate`` over text --
exported without results as a record whose every computed node said
``dtype: unknown`` and none of them ``in_final_schema``, with a logged
warning and nothing else. The JAX engine ran that record and handed back
the book's own columns: no answer, no refusal. Section 10 makes ``unknown``
history only, never a column the model holds, so an executable export --
the document an engine runs -- refuses the plan by name. An audit record,
which no engine runs, is still written for the reader, and a plan that
types is exported as before. The frame's own arithmetic between text or a
date and a number is refused where it is written, so each untyped plan here
is an engine fragment written by hand, which Polars alone types.
"""

from __future__ import annotations

import json
from datetime import date

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

_BOOK = pl.DataFrame(
    {
        "rate": [0.01, 0.02],
        "n": [1, 2],
        "code": ["A", "B"],
        "issue": [date(2025, 1, 1)] * 2,
    }
)


@pytest.mark.parametrize(
    "line",
    [
        lambda _af: pl.col("code") * pl.col("rate"),
        lambda _af: pl.col("issue") + pl.col("n"),
    ],
    ids=["text times a rate", "a date plus a number"],
)
def test_an_untyped_plan_is_refused_at_export_by_name(line: object) -> None:
    af = ActuarialFrame(_BOOK)
    af.bad = line(af)  # type: ignore[operator]
    af.fine = af.rate * 2.0

    with pytest.raises(ValueError, match="cannot state the type of its plan"):
        GraphExporter(af).export(profile="executable")


def test_an_audit_record_of_an_untyped_plan_is_still_written() -> None:
    af = ActuarialFrame(_BOOK)
    af.bad = pl.col("code") * pl.col("rate")
    document = json.loads(GraphExporter(af).export(profile="audit"))
    (node,) = [node for node in document["nodes"] if node["column"] == "bad"]
    assert node["dtype"] == "unknown"


def test_a_plan_that_types_is_exported_with_every_column_typed() -> None:
    af = ActuarialFrame(_BOOK)
    af.fine = af.rate * 2.0
    document = json.loads(GraphExporter(af).export(profile="executable"))
    computed = [node for node in document["nodes"] if node["kind"] == "computed"]
    assert [(node["dtype"], node["in_final_schema"]) for node in computed] == [
        ("f64", True)
    ]
