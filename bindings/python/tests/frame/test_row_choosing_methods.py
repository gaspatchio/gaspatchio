# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars' other ways of choosing rows say why they are not model steps.

``af.head(2)``, ``af.unique()``, ``af.slice(0, 2)`` and ``af.drop_nulls()`` used
to fail as "'ActuarialFrame' object has no attribute 'head'. If 'head' is a
column name, use af['head'] instead", reading a frame method as a column the
frame does not hold. Which policies a model values is part of its record, and
the record states a choice made on what a policy holds: ``af.filter``'s
condition, or a semi or anti join's key list. A choice by position, by
duplicates or by a missing value is not one of those, so each says so and
names what to write instead -- ``af.filter``, or the cut made on the model
points before the frame is built. Each route a refusal names is run here too.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

_BOOK = pl.DataFrame(
    {
        "policy_id": ["P1", "P2", "P3"],
        "sum_assured": [100_000.0, None, float("nan")],
    }
)

_CALLS = {
    "head": lambda af: af.head(2),
    "tail": lambda af: af.tail(2),
    "limit": lambda af: af.limit(2),
    "slice": lambda af: af.slice(0, 2),
    "unique": lambda af: af.unique(),
    "drop_nulls": lambda af: af.drop_nulls(),
    "drop_nans": lambda af: af.drop_nans(),
    "gather_every": lambda af: af.gather_every(2),
    "sample": lambda af: af.sample(2),
    "top_k": lambda af: af.top_k(2, by="sum_assured"),
    "bottom_k": lambda af: af.bottom_k(2, by="sum_assured"),
}


@pytest.mark.parametrize("name", list(_CALLS))
def test_a_row_choosing_method_says_why_and_names_the_filter(name: str) -> None:
    with pytest.raises(AttributeError) as refused:
        _CALLS[name](ActuarialFrame(_BOOK))
    message = str(refused.value)
    assert message.startswith(f"af.{name}() is not a step a model takes")
    assert "use af[" not in message
    assert "ActuarialFrame(model_points." in message
    if name != "unique":
        assert "af.filter(af." in message


def test_a_column_named_like_one_is_still_a_column() -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": ["P1"], "head": [3.0]}))
    af.twice = af.head * 2.0
    assert af.collect()["twice"].to_list() == [6.0]


@pytest.mark.parametrize(
    ("condition", "kept"),
    [
        (lambda af: af.policy_id.is_in(["P1", "P2"]), ["P1", "P2"]),
        (lambda af: af.sum_assured.is_not_null(), ["P1", "P3"]),
        (lambda af: af.sum_assured.is_not_nan(), ["P1"]),
    ],
    ids=["by identity", "not null", "not nan"],
)
def test_the_filter_a_refusal_names_is_recorded_and_replayable(
    condition: object, kept: list[str]
) -> None:
    book = ActuarialFrame(_BOOK)
    af = book.filter(condition(book))  # type: ignore[operator]
    af.premium = af.sum_assured * 0.002
    document = json.loads(GraphExporter(af).export(profile="executable"))
    assert af.collect()["policy_id"].to_list() == kept
    assert document["selection"][0]["tier"] == "core"


def test_remove_names_the_filter_of_the_policies_kept_and_its_null_test() -> None:
    """Polars' remove keeps a row whose condition is null; af.filter(~c) does not.

    So the sentence names both: the condition for the policies kept, and that
    condition with its null test, which is what remove did. With status IF,
    LAPSED and null, remove keeps P1 and P3, ~(status == LAPSED) keeps P1.
    """
    with pytest.raises(AttributeError) as refused:
        _ = ActuarialFrame(_BOOK).remove
    message = str(refused.value)
    assert message.startswith("af.remove() is not a frame method")
    assert "use af[" not in message
    plain = 'af.filter(~(af.status == "LAPSED"))'
    with_nulls = 'af.filter(~(af.status == "LAPSED") | af.status.is_null())'
    assert plain in message
    assert with_nulls in message
    book = pl.DataFrame(
        {"policy_id": ["P1", "P2", "P3"], "status": ["IF", "LAPSED", None]}
    )
    assert book.remove(pl.col("status") == "LAPSED")["policy_id"].to_list() == [
        "P1",
        "P3",
    ]
    routes = (
        (lambda af: af.filter(~(af.status == "LAPSED")), ["P1"]),
        (
            lambda af: af.filter(~(af.status == "LAPSED") | af.status.is_null()),
            ["P1", "P3"],
        ),
    )
    for route, kept in routes:
        af = route(ActuarialFrame(book))
        af.flag = af.status == "IF"
        assert af.collect()["policy_id"].to_list() == kept
        (step,) = json.loads(GraphExporter(af).export(profile="executable"))[
            "selection"
        ]
        assert step["tier"] == "core"


@pytest.mark.parametrize(
    ("cut", "kept"),
    [
        (lambda mp: mp.gather_every(2), ["P1", "P3"]),
        (lambda mp: mp.sample(2, seed=1), None),
        (lambda mp: mp.top_k(1, by="sum_assured"), ["P1"]),
        (lambda mp: mp.bottom_k(1, by="sum_assured"), ["P3"]),
    ],
    ids=["gather_every", "sample", "top_k", "bottom_k"],
)
def test_the_cut_on_the_model_points_a_refusal_names_runs(
    cut: object, kept: list[str] | None
) -> None:
    book = _BOOK.with_columns(pl.Series("sum_assured", [100_000.0, 50_000.0, 1.0]))
    af = ActuarialFrame(cut(book))  # type: ignore[operator]
    af.premium = af.sum_assured * 0.002
    held = af.collect()["policy_id"].to_list()
    assert len(held) == (len(kept) if kept is not None else 2)
    if kept is not None:
        assert held == kept
    assert "selection" not in json.loads(GraphExporter(af).export(profile="audit"))
