# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-policy lookup raised to a flag's power, or a flag to its, answers here too.

The producer failed on ``lookup ** True`` and ``True ** lookup`` in Polars'
words, so no record of either reached this engine; a per-policy lookup's
operators are now the column's, and the record answers here as the
producer's does. A comparison on the lookup, stored, is the 0.0 or 1.0
indicator a column's is, here as on the producer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest
from polars.testing import assert_series_equal

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame({"k": [1, 5]})
_TABLE = Table(
    name="jax_a_lookup_s_operators",
    source=pl.DataFrame({"k": [1, 5], "rate": [135.021, 0.25]}),
    dimensions={"k": "k"},
    value="rate",
)


@pytest.mark.parametrize(
    ("make", "hand"),
    [
        (lambda v: v**True, [135.021, 0.25]),
        (lambda v: True**v, [1.0, 1.0]),
        (lambda v: v / 1000, [135.021 / 1000, 0.25 / 1000]),
    ],
)
def test_the_lookup_s_operator_answers_as_the_producer_does(
    make: Callable[[object], object], hand: list[float]
) -> None:
    af = ActuarialFrame(_BOOK)
    af.r = make(_TABLE.lookup(k=af.k))

    reference, engine = af.collect(), af.collect(engine="jax")

    assert engine["r"].to_list() == hand
    assert_series_equal(engine["r"], reference["r"], check_exact=True)


@pytest.mark.parametrize(
    ("make", "hand"),
    [
        (lambda v: v > 1, [1.0, 0.0]),
        (lambda v: v <= 1, [0.0, 1.0]),
        (lambda v: v == 0.25, [0.0, 1.0]),
    ],
)
def test_a_lookup_s_stored_comparison_is_the_indicator_here_too(
    make: Callable[[object], object], hand: list[float]
) -> None:
    af = ActuarialFrame(_BOOK)
    af.r = make(_TABLE.lookup(k=af.k))

    reference, engine = af.collect(), af.collect(engine="jax")

    assert engine.schema["r"] == pl.Float64
    assert engine["r"].to_list() == hand
    assert_series_equal(engine["r"], reference["r"], check_exact=True)
