# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``is_in`` of a NaN answers false on this engine, as on the producer (11.1.26).

Under IEEE 754 equality a NaN equals no member, so it is a member of no set,
per policy and per period: false, not the unknown a comparison with a NaN
stores, and the null of a null value is untouched.
"""

from __future__ import annotations

import polars as pl

from gaspatchio import ActuarialFrame


def test_a_nan_is_a_member_of_no_set_on_both_engines() -> None:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "a0": [0.0, 1.0, 3.0],
                "b0": [0.0, 1.0, 1.0],
                "a": [[0.0, 1.0, 3.0]] * 3,
                "b": [[0.0, 1.0, 1.0]] * 3,
            }
        )
    )
    af.r0 = af.a0 / af.b0
    af.r = af.a / af.b
    af.m0 = af.r0.is_in([1.0, 2.0])
    af.m = af.r.is_in([1.0, 2.0])
    want = {"m0": [False, True, False], "m": [[False, True, False]] * 3}
    for engine in ("in-memory", "jax"):
        got = af.collect(engine=engine).select("m0", "m").to_dict(as_series=False)
        assert got == want, engine
