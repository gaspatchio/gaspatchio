# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The reference reader refuses an i64 past 2**53 beside an f64 in a conditional.

Section 11.1.28 admits an ``i64`` branch beside an ``f64`` one "only within the
exact integer-conversion range", as section 11.1.25 admits the pair in
arithmetic. The reader refused ``k + x`` with ``k`` at ``2**53 + 1``, and
refused a flag beside such a whole number in a conditional, but answered
``when(c).then(k).otherwise(x)`` as the double ``2**53`` -- a value the
document's own entry does not state, and one the JAX engine refuses by name.
It now refuses the pair as it refuses the arithmetic, over every value of
both branches (a branch's domain is not suppressed by a false condition), and
answers the pair as before within the range.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

_TOO_FAR = 2**53 + 1


def _reference_reader() -> Any:  # noqa: ANN401 -- the reader is untyped
    conformance = (
        Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"
    )
    sys.path.insert(0, str(conformance))
    try:
        return importlib.import_module("reference")
    finally:
        sys.path.remove(str(conformance))


def _col(name: str) -> dict[str, Any]:
    return {"op": "col", "name": name}


def _lit(value: object, dtype: str) -> dict[str, Any]:
    return {"op": "lit", "value": value, "dtype": dtype}


def _when(then: dict[str, Any], otherwise: dict[str, Any]) -> dict[str, Any]:
    return {"op": "when_then", "cond": _col("c"), "then": then, "otherwise": otherwise}


def _evaluate(tree: dict[str, Any], k: list[Any], kind: str = "i64") -> Any:  # noqa: ANN401
    reference = _reference_reader()
    column = reference.Column
    inputs = {
        "c": column("bool", [True, False]),
        "k": column(kind, k),
        "x": column("f64", [0.5, 0.25]),
    }
    return reference.Reader(inputs, [], {}).evaluate(tree)


@pytest.mark.parametrize(
    ("tree", "k", "kind"),
    [
        (_when(_col("k"), _col("x")), [_TOO_FAR, 3], "i64"),
        (_when(_col("x"), _col("k")), [_TOO_FAR, 3], "i64"),
        (_when(_col("x"), _col("k")), [3, -_TOO_FAR], "i64"),
        (_when(_col("k"), _lit(0.5, "f64")), [_TOO_FAR, 3], "i64"),
        (_when(_lit(_TOO_FAR, "i64"), _col("x")), [3, 4], "i64"),
        (_when(_col("k"), _col("x")), [[_TOO_FAR, 3], [1, 2]], "list[i64]"),
    ],
    ids=[
        "then column",
        "otherwise column",
        "unselected negative",
        "beside a literal",
        "literal",
        "per period",
    ],
)
def test_a_whole_number_past_2_53_beside_a_double_is_refused(
    tree: dict[str, Any], k: list[Any], kind: str
) -> None:
    reference = _reference_reader()
    with pytest.raises(reference.DomainRefusal, match="exact-numeric-range"):
        _evaluate(tree, k, kind)


@pytest.mark.parametrize(
    ("k", "hand"),
    [
        ([2**53, 3], [9007199254740992.0, 0.25]),
        ([-(2**53), 3], [-9007199254740992.0, 0.25]),
        ([7, 3], [7.0, 0.25]),
    ],
    ids=["two to the 53", "its negative", "small"],
)
def test_the_pair_within_the_range_answers_a_double(
    k: list[int], hand: list[float]
) -> None:
    answer = _evaluate(_when(_col("k"), _col("x")), k)

    assert answer.dtype == "f64"
    assert answer.values == hand
