# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``0 ** run`` keeps a null period null, as 11.1.25 states for a null element.

The zero-base branch of a per-period power tested each period's sign and sent
a null period to its NaN branch, so ``0 ** [2.5, null, 0.0, 1.0]`` answered
``[0.0, NaN, 1.0, 0.0]`` -- a NaN no formula wrote, where the clause answers
null (audit D1-P14). A nonzero base already kept the null.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame


@pytest.mark.parametrize("base", [0, 0.0, -0.0, 2.0])
@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
def test_a_null_period_is_null_whatever_the_base(base: float, engine: str) -> None:
    af = ActuarialFrame(
        pl.DataFrame({"L": [[2.5, None, 0.0, 1.0]]}, schema={"L": pl.List(pl.Float64)})
    )
    af.r = base**af.L
    got = af.collect(engine=engine)["r"].to_list()[0]
    assert got[1] is None
    assert got[2] == 1.0
