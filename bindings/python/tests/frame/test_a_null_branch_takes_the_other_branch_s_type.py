# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A null branch carries no type, and a per-period conditional keeps its whole numbers.

``when(af.month > 0).then(None).otherwise(af.k)`` over a ``list[i64]`` run
answered ``list[f64]``: the per-period route selects through a kernel that
works in doubles, and a bare ``None`` gave the frame no second integer
branch to type the answer by, so a count of 2**53 + 1 came back as
9007199254740992.0, and the record said ``list[f64]``. A Boolean run beside a
``None`` came back as 0.0 and 1.0, a date run as day counts, and a text run
was refused by the kernel. The per-policy form of the same line always kept
the other branch's type.

Typing the answer was half of it. The kernel's doubles also lost the last
bits of every whole number past 2**53 under two integer branches -- the
answer said ``list[i64]`` and held 2**53 where the run held 2**53 + 1, where
the JAX engine answered the run's own value. A per-period conditional of
64-bit whole numbers now selects each value's high and low 32 bits apart,
which a double holds exactly, and joins them.

A bare ``None`` reaches the record as an engine-native fragment, so the JAX
engine refuses such a document by name before it reads a book; that is
unchanged here.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_BIG = 2**53 + 1
_DAY = datetime.date(2025, 1, 1)


def _frame() -> ActuarialFrame:
    """Two policies over three months; ``k`` is ``n`` plus the month."""
    book = pl.DataFrame(
        {
            "pid": [1, 2],
            "n": pl.Series([3, _BIG], dtype=pl.Int64),
            "x": [1.5, 3.5],
            "flag": [True, False],
        }
    )
    af = ActuarialFrame(book).projection.set(
        start_date=_DAY, n_periods=2, frequency="monthly"
    )
    af.k = af.n + af.month
    af.later = when(af.month > 0).then(True).otherwise(False)  # noqa: FBT003 -- a flag run
    af.on = af.month > 1
    af.text = when(af.month > 0).then("b").otherwise("a")
    af.day = when(af.month > 0).then(_DAY).otherwise(_DAY)
    return af


# (what the author wrote, the line, the answer's type, the hand values).
_LINES: list[tuple[str, Callable[[Any], Any], pl.DataType, list[Any]]] = [
    (
        "then(None).otherwise(k), a comparison",
        lambda af: when(af.month > 0).then(None).otherwise(af.k),
        pl.List(pl.Int64),
        [[3, None, None], [_BIG, None, None]],
    ),
    (
        "then(k).otherwise(None), a comparison",
        lambda af: when(af.month > 0).then(af.k).otherwise(None),
        pl.List(pl.Int64),
        [[None, 4, 5], [None, _BIG + 1, _BIG + 2]],
    ),
    (
        "then(None).otherwise(n), one value per policy",
        lambda af: when(af.month > 0).then(None).otherwise(af.n),
        pl.List(pl.Int64),
        [[3, None, None], [_BIG, None, None]],
    ),
    (
        "then(7).otherwise(None)",
        lambda af: when(af.month > 0).then(7).otherwise(None),
        pl.List(pl.Int64),
        [[None, 7, 7], [None, 7, 7]],
    ),
    (
        "then(None).otherwise(k), a per-period flag",
        lambda af: when(af.on).then(None).otherwise(af.k),
        pl.List(pl.Int64),
        [[3, 4, None], [_BIG, _BIG + 1, None]],
    ),
    (
        "then(None).otherwise(k), one flag per policy",
        lambda af: when(af.flag).then(None).otherwise(af.k),
        pl.List(pl.Int64),
        [[None, None, None], [_BIG, _BIG + 1, _BIG + 2]],
    ),
    (
        "a chain: then(None), then(k), otherwise(None)",
        lambda af: (
            when(af.month > 1).then(None).when(af.month > 0).then(af.k).otherwise(None)
        ),
        pl.List(pl.Int64),
        [[None, 4, None], [None, _BIG + 1, None]],
    ),
    (
        "then(None).otherwise(a flag run)",
        lambda af: when(af.month > 1).then(None).otherwise(af.later),
        pl.List(pl.Boolean),
        [[False, True, None], [False, True, None]],
    ),
    (
        "then(None).otherwise(a text run)",
        lambda af: when(af.month > 1).then(None).otherwise(af.text),
        pl.List(pl.String),
        [["a", "b", None], ["a", "b", None]],
    ),
    (
        "then(None).otherwise(a date run)",
        lambda af: when(af.month > 1).then(None).otherwise(af.day),
        pl.List(pl.Date),
        [[_DAY, _DAY, None], [_DAY, _DAY, None]],
    ),
    (
        "then(a date).otherwise(a date run)",
        lambda af: when(af.month > 1).then(_DAY).otherwise(af.day),
        pl.List(pl.Date),
        [[_DAY] * 3, [_DAY] * 3],
    ),
    (
        "then(0).otherwise(k), past 2**53",
        lambda af: when(af.month > 0).then(0).otherwise(af.k),
        pl.List(pl.Int64),
        [[3, 0, 0], [_BIG, 0, 0]],
    ),
    (
        "then(k).otherwise(n), past 2**53",
        lambda af: when(af.month > 1).then(af.k).otherwise(af.n),
        pl.List(pl.Int64),
        [[3, 3, 5], [_BIG, _BIG, _BIG + 2]],
    ),
    (
        "then(a typed null).otherwise(k), past 2**53",
        lambda af: (
            when(af.month > 0).then(pl.lit(None, dtype=pl.Int64)).otherwise(af.k)
        ),
        pl.List(pl.Int64),
        [[3, None, None], [_BIG, None, None]],
    ),
    (
        "then(0).otherwise(k), a per-period flag, past 2**53",
        lambda af: when(af.on).then(0).otherwise(af.k),
        pl.List(pl.Int64),
        [[3, 4, 0], [_BIG, _BIG + 1, 0]],
    ),
    (
        "then(0).otherwise(k), one flag per policy, past 2**53",
        lambda af: when(af.flag).then(0).otherwise(af.k),
        pl.List(pl.Int64),
        [[0, 0, 0], [_BIG, _BIG + 1, _BIG + 2]],
    ),
    (
        "then(k).otherwise(-k), both ends of i64",
        lambda af: (
            when(af.month > 0)
            .then(af.k * 0 + (2**63 - 1))
            .otherwise(af.k * 0 - (2**63 - 1) - 1)
        ),
        pl.List(pl.Int64),
        [[-(2**63), 2**63 - 1, 2**63 - 1], [-(2**63), 2**63 - 1, 2**63 - 1]],
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "dtype", "expected"), _LINES, ids=[line[0] for line in _LINES]
)
def test_a_per_period_conditional_answers_its_branches_type_and_values(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    dtype: pl.DataType,
    expected: list[Any],
) -> None:
    af = _frame()
    af.r = line(af)

    answer = af.collect()

    assert answer.schema["r"] == dtype
    assert answer["r"].to_list() == expected


def test_the_record_names_the_other_branch_s_type() -> None:
    """Was ``list[f64]`` for the run and the frame alike."""
    af = _frame()
    af.r = when(af.month > 0).then(None).otherwise(af.k)

    document = json.loads(GraphExporter(af).export(profile="executable"))
    node = next(n for n in document["nodes"] if n.get("column") == "r")

    assert node["dtype"] == "list[i64]"


def test_a_per_policy_null_branch_keeps_the_other_branch_s_type() -> None:
    """The per-policy route always answered so; a guard."""
    af = _frame()
    af.r = when(af.x > 2).then(None).otherwise(af.n)

    answer = af.collect()

    assert answer.schema["r"] == pl.Int64
    assert answer["r"].to_list() == [3, None]


def test_a_decimal_beside_a_null_branch_is_unchanged() -> None:
    af = _frame()
    af.r = when(af.month > 0).then(None).otherwise(af.x)

    answer = af.collect()

    assert answer.schema["r"] == pl.List(pl.Float64)
    assert answer["r"].to_list() == [[1.5, None, None], [3.5, None, None]]
