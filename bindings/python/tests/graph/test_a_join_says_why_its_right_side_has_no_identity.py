# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A join whose right side the content grammar refuses says why, where it is seen.

Section 11.1.2 has a join's ``right_fingerprint`` null for "a frame the sort
or the encoding refuses", and so it is. But the refusal -- a millisecond
instant whose microseconds leave an ``i64``, refused by name under section 12.3 --
was dropped at TRACE, so nothing a user sees said why the join's identity was
null, while the hole door says the same refusal at WARNING. It is said at
WARNING now, in the refusal's own words. No identity moves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
from loguru import logger

from gaspatchio import ActuarialFrame
from gaspatchio.frame.base import _right_side_fingerprint

if TYPE_CHECKING:
    from collections.abc import Iterator

import pytest

_PAST_I64_MICROSECONDS = 9_223_372_036_854_776  # ms


@pytest.fixture
def warnings_said() -> Iterator[list[str]]:
    said: list[str] = []
    sink = logger.add(lambda message: said.append(str(message)), level="WARNING")
    yield said
    logger.remove(sink)


def _right(ms: int) -> pl.DataFrame:
    stamps = pl.Series("ts", [0, ms], dtype=pl.Int64).cast(pl.Datetime("ms"))
    return pl.DataFrame({"k": [1, 2], "ts": stamps})


def test_a_refused_right_side_is_null_and_says_why(warnings_said: list[str]) -> None:
    assert _right_side_fingerprint(_right(_PAST_I64_MICROSECONDS)) is None

    (said,) = [line for line in warnings_said if "right side" in line]
    assert "no content identity" in said
    assert "leaves the 64-bit whole number" in said
    assert "right_fingerprint" in said


def test_the_join_runs_and_its_graph_says_it_once(warnings_said: list[str]) -> None:
    book = pl.DataFrame({"pid": [1, 2], "k": [1, 2], "x": [1.0, 2.0]})
    af = ActuarialFrame(book).join(_right(_PAST_I64_MICROSECONDS), on="k")
    af.y = af.x * 2.0

    assert af.collect()["y"].to_list() == [2.0, 4.0]
    assert sum("right side" in line for line in warnings_said) == 1


def test_a_right_side_it_can_hash_says_nothing(warnings_said: list[str]) -> None:
    assert _right_side_fingerprint(_right(5)) is not None
    assert not [line for line in warnings_said if "right side" in line]


def test_a_lazy_right_side_is_null_without_a_warning(warnings_said: list[str]) -> None:
    """Lazy is the caller's choice, stated in the record; it is not a refusal."""
    assert _right_side_fingerprint(_right(5).lazy()) is None
    assert not [line for line in warnings_said if "right side" in line]
