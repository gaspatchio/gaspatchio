# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A flag times a negative zero is a negative zero, and its reciprocal points down.

11.1.25 reads a flag in arithmetic as its 0.0 or 1.0, and ``0.0 * -0.0`` is
``-0.0``. XLA rewrote a product by a converted truth value into a selection
between the other operand and a constant ``+0.0``, so a false flag times
``-0.0`` came back ``+0.0`` and ``-3 / that`` came back ``-inf`` where the
reference producer and the reader answer ``+inf``. 11.1.12
compares which way an infinity points.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

_BOOK = pl.DataFrame(
    {
        "flag": [True, False],
        "nz": [-0.0, -0.0],
        "i": [-3.0, -3.0],
        "flags": [[True, False, True, False]] * 2,
        "nzs": [[-0.0] * 4] * 2,
    }
)


def _signs(values: list) -> list:
    return [
        _signs(one) if isinstance(one, list) else math.copysign(1.0, one)
        for one in values
    ]


@pytest.mark.parametrize(
    "written",
    [
        lambda af: af.flag * af.nz,
        lambda af: af.nz * af.flag,
        lambda af: af.flags * af.nzs,
        lambda af: af.flags * af.nz,
    ],
    ids=["flag*z", "z*flag", "per-period", "per-period flag, per-policy zero"],
)
def test_the_product_keeps_its_sign_and_so_does_the_quotient(written: object) -> None:
    af = ActuarialFrame(_BOOK)
    af.d = written(af)  # type: ignore[operator]
    af.q = af.i / af.d
    producer = af.collect()
    engine = af.collect(engine="jax")
    assert _signs(engine["d"].to_list()) == _signs(producer["d"].to_list())
    assert engine["q"].to_list() == producer["q"].to_list()
    flat = [
        v
        for row in producer["q"].to_list()
        for v in (row if isinstance(row, list) else [row])
    ]
    assert all(v == math.inf for v in flat)
