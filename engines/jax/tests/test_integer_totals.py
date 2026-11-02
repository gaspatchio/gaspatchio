# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A total of whole numbers folded here is the producer's exact total.

This engine folds a per-policy ``Sum`` through the producer's own batch
fold, which summed an ``Int64`` batch in ``Int64``: 2**62, 2**62 and 5
answered 9.2e18 one policy a batch and -9.2e18 two a batch, here as on
Polars. The fold now totals whole numbers exactly and refuses a total past
the signed 64-bit range by name, so both engines answer, and refuse, alike.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.scenarios import Sum, run_aggregated

if TYPE_CHECKING:
    from gaspatchio import ActuarialFrame

_H = 2**62


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {"amt": [2.0, 3.0, 4.0], "big": [_H, _H, 5], "back": [_H, _H, -_H]}
    )


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af.r = af.amt * 2
    af.b = af.big * 1
    af.k = af.back * 1
    return af


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_a_total_past_i64_is_refused_on_both_engines(batch_size: int) -> None:
    for engine in (None, "jax"):
        with pytest.raises(ValueError, match="Column 'b' totals 9223372036854775813,"):
            run_aggregated(
                _model,
                _book(),
                aggregations=[Sum("b").alias("t")],
                batch_size=batch_size,
                engine=engine,
            )


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_a_total_that_fits_is_the_same_on_both_engines(batch_size: int) -> None:
    """Hand value: 2**62 + 2**62 - 2**62 = 2**62 (was -1.38e19 at two a batch)."""
    answers = [
        run_aggregated(
            _model,
            _book(),
            aggregations=[Sum("k").alias("t")],
            batch_size=batch_size,
            engine=engine,
        ).aggregations["t"]
        for engine in (None, "jax")
    ]

    assert answers == [float(_H), float(_H)]
