# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The total of a policy with no periods is +0.0, as 11.1.14 states.

Polars' list kernel starts a sum of doubles from -0.0, so an empty run's total
was -0.0 and ``4.0 / total`` was -inf, where the JAX engine, the reader and
Polars' own column sum answer +inf (audit D1-P15). A run with periods keeps
the sum Polars gives -- one period of -0.0 sums to -0.0.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
def test_an_empty_total_is_positive_and_a_negative_nought_stays(engine: str) -> None:
    af = ActuarialFrame(pl.DataFrame({"r": [[], [1.0, -1.0], [-0.0], [2.5]]}))
    af.s = af.r.list.sum()
    af.q = 4.0 / af.r.list.sum()
    out = af.collect(engine=engine)
    assert [math.copysign(1.0, v) for v in out["s"].to_list()] == [1.0, 1.0, -1.0, 1.0]
    assert out["q"].to_list() == [math.inf, math.inf, -math.inf, 1.6]
    assert out.schema["s"] == pl.Float64


def test_a_whole_number_total_is_untouched() -> None:
    af = ActuarialFrame(pl.DataFrame({"r": [[], [1, -1], [3]]}))
    af.s = af.r.list.sum()
    out = af.collect()
    assert out["s"].to_list() == [0, 0, 3]
    assert out.schema["s"] == pl.Int64
