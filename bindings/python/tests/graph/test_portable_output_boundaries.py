# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Portable output requires a declared meaning for every live column's type."""

from __future__ import annotations

import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio.frame.graph import GraphExporter, validate_artifact


@pytest.mark.parametrize(
    "passenger",
    [
        pl.Series("passenger", [None]),
        pl.Series("passenger", [[None]]),
        pl.Series("passenger", [[]]),
    ],
    ids=["null-scalar", "null-list-element", "untyped-empty-list"],
)
def test_untyped_passenger_refuses_graph_and_both_profiles(
    passenger: pl.Series,
) -> None:
    """An unused passenger needs a type even when calculations succeed."""
    frame = ActuarialFrame(pl.DataFrame({"base": [100.0], "passenger": passenger}))
    frame.answer = frame.base * 2.0
    assert frame.collect()["answer"].to_list() == [200.0]
    with pytest.raises(UnmappedDtypeError, match=r"passenger.*explicit dtype"):
        frame.graph.precedents("answer")
    for profile in ("audit", "executable"):
        with pytest.raises(
            UnmappedDtypeError, match=r"Null.*cannot be recorded as unknown"
        ):
            GraphExporter(frame).export(profile=profile)
    # Refusal must neither remove the passenger nor invent an f64 input.
    assert frame.collect()["passenger"].equals(passenger)


@pytest.mark.parametrize(
    "passenger",
    [
        pl.Series("passenger", [None], dtype=pl.Float64),
        pl.Series("passenger", [[None]], dtype=pl.List(pl.Float64)),
        pl.Series("passenger", [[]], dtype=pl.List(pl.Float64)),
        pl.Series("passenger", [None], dtype=pl.List(pl.Float64)),
    ],
    ids=[
        "typed-null-scalar",
        "typed-null-element",
        "typed-empty-list",
        "typed-null-list",
    ],
)
def test_explicit_type_keeps_nullable_passenger_and_lineage(
    passenger: pl.Series,
) -> None:
    """A missing value is portable when its intended type is supplied by the author."""
    frame = ActuarialFrame(pl.DataFrame({"base": [100.0], "passenger": passenger}))
    frame.answer = frame.base * 2.0
    assert list(frame.graph.precedents("answer")) == ["base"]
    for profile in ("audit", "executable"):
        artifact = GraphExporter(frame).export(profile=profile)
        assert validate_artifact(artifact, deep=True).ok
        node = next(
            n for n in json.loads(artifact)["nodes"] if n["column"] == "passenger"
        )
        assert node["dtype"] == (
            "list[f64]" if isinstance(passenger.dtype, pl.List) else "f64"
        )
        assert node["kind"] == "input"
    assert frame.collect()["passenger"].equals(passenger)
