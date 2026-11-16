# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A present value is null from a cashflow's hole backwards (11.1.21, GSP-243).

The rule is applied by a kernel rather than element by element, so a run with
no null pays nothing. These tests hold the kernel to the rule written out as
the Polars expression it replaced, and to the last bit.
"""

from __future__ import annotations

import random
import struct

import polars as pl
import pytest

from gaspatchio.frame.lowering._polars.plugins import list_null_from_hole_back

_RUN = pl.List(pl.Float64)


def _rule_written_out(total: pl.Expr, cashflows: pl.Expr) -> pl.Expr:
    lost = pl.element().is_null().cum_sum(reverse=True) > 0
    return total * cashflows.list.eval(pl.when(lost).then(None).otherwise(1.0))


def _bits(rows: list[list[float | None] | None]) -> list[object]:
    return [
        None
        if row is None
        else [None if v is None else struct.pack("<d", v) for v in row]
        for row in rows
    ]


def _both(frame: pl.DataFrame) -> tuple[list[object], list[object]]:
    answered = frame.select(
        kernel=list_null_from_hole_back(pl.col("total"), pl.col("cf")),
        rule=_rule_written_out(pl.col("total"), pl.col("cf")),
    )
    return _bits(answered["kernel"].to_list()), _bits(answered["rule"].to_list())


@pytest.mark.parametrize(
    ("total", "cashflows", "want"),
    [
        pytest.param([3.0, 2.0, 1.0], [1.0, 1.0, 1.0], [3.0, 2.0, 1.0], id="no hole"),
        pytest.param([3.0, 2.0, 1.0], [1.0, None, 1.0], [None, None, 1.0], id="middle"),
        pytest.param([3.0, 2.0, 1.0], [None, 1.0, 1.0], [None, 2.0, 1.0], id="first"),
        pytest.param([3.0, 2.0, 1.0], [1.0, 1.0, None], [None, None, None], id="last"),
        pytest.param([3.0, 2.0], [None, None], [None, None], id="all"),
        pytest.param([], [], [], id="no periods"),
    ],
)
def test_a_policy_is_null_from_its_last_hole_back(
    total: list[float],
    cashflows: list[float | None],
    want: list[float | None],
) -> None:
    frame = pl.DataFrame(
        {"total": [total], "cf": [cashflows]}, schema={"total": _RUN, "cf": _RUN}
    )

    kernel, rule = _both(frame)

    assert kernel == rule == _bits([want])


def test_a_policy_with_no_run_answers_null() -> None:
    frame = pl.DataFrame(
        {"total": [None, [1.0]], "cf": [None, [None]]},
        schema={"total": _RUN, "cf": _RUN},
    )

    kernel, rule = _both(frame)

    assert kernel == rule == _bits([None, [None]])


def test_nan_negative_zero_and_infinity_keep_their_bits() -> None:
    specials = [float("nan"), -0.0, float("inf"), -float("inf"), 5e-324]
    frame = pl.DataFrame(
        {"total": [specials, specials], "cf": [[1.0] * 5, [None, *[1.0] * 4]]},
        schema={"total": _RUN, "cf": _RUN},
    )

    kernel, rule = _both(frame)

    assert kernel == rule


def test_a_nan_cashflow_is_not_a_hole() -> None:
    frame = pl.DataFrame(
        {"total": [[1.0, 2.0]], "cf": [[float("nan"), 1.0]]},
        schema={"total": _RUN, "cf": _RUN},
    )

    kernel, rule = _both(frame)

    assert kernel == rule == _bits([[1.0, 2.0]])


@pytest.mark.parametrize("seed", range(5))
def test_random_books_answer_as_the_rule_does(seed: int) -> None:
    rng = random.Random(seed)  # noqa: S311 -- a reproducible test book
    lengths = [rng.randrange(0, 13) for _ in range(300)]
    total = [[rng.uniform(-1e6, 1e6) for _ in range(n)] for n in lengths]
    cashflows = [
        [None if rng.random() < 0.05 else 1.0 for _ in range(n)] for n in lengths
    ]
    frame = pl.DataFrame(
        {"total": total, "cf": cashflows}, schema={"total": _RUN, "cf": _RUN}
    )

    kernel, rule = _both(frame)

    assert kernel == rule


def test_an_integer_total_answers_in_doubles_as_the_rule_does() -> None:
    frame = pl.DataFrame(
        {"total": [[3, 2]], "cf": [[1.0, None]]},
        schema={"total": pl.List(pl.Int64), "cf": _RUN},
    )

    answered = frame.select(
        list_null_from_hole_back(pl.col("total"), pl.col("cf")).alias("a")
    )

    assert answered.schema["a"] == _RUN
    assert answered["a"].to_list() == [[None, None]]
