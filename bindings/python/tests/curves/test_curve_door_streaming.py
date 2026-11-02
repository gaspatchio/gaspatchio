# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The curve door lowers to an expression the streaming engine can chunk.

``Curve.spot_rate(t)`` and ``Curve.discount_factor(t)`` lower to nothing but
element-wise kernels, so every row's answer depends on that row's time and
on nothing else. That is what lets the streaming engine -- the engine
``ActuarialFrame.collect()`` uses by default -- carry the whole column
through in chunks, and it is where the door's speed comes from.

It reads like an obvious optimisation to evaluate the curve once per
*distinct* time and broadcast the answer back to the rows that share it: on
a projection grid, thousands of policies share one year-fraction vector, so
the deduplicated read does a fraction of the arithmetic. Measured, it is
slower, and it is slower at every cardinality that was tried, in both the
scalar and the list shape. Sharing rows means looking at other rows, so the
expression stops being element-wise, and the streaming engine's chunked
evaluation of the element-wise kernel is already faster than that same
engine's deduplicated computation. Sharing wins only against the in-memory
engine, which is not the engine a model runs on -- so compare within one
engine before quoting either number.

So the sharing-free shape is load-bearing rather than incidental, and these
tests are here to fail if a lowering starts sharing rows. They pin the two
spellings the obvious optimisation reaches for -- the window (``over(``) and
the ``unique`` + dense-``rank`` + ``gather`` shape, which produces no window
at all -- and a third spelling would still slip past them. If a future
Polars makes a window streamable, re-measure before believing this again --
but re-measure with ``engine="streaming"``, because measuring it any other
way is what makes deduplication look good.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import Curve

if TYPE_CHECKING:
    from collections.abc import Callable

_LIST = pl.List(pl.Float64)
_GRID = [k / 12.0 for k in range(83)]

_CURVE = Curve.from_zero_rates(
    tenors=[0.5, 1.0, 5.0, 10.0, 30.0],
    rates=[0.030, 0.032, 0.038, 0.040, 0.043],
)

_SHAPES: list[tuple[str, pl.DataFrame]] = [
    ("scalar-t", pl.DataFrame({"t": [1.0, 1.0, 2.5, 7.0]}, schema={"t": pl.Float64})),
    (
        "list-t shared",
        pl.DataFrame({"t": [_GRID] * 8}, schema={"t": _LIST}),
    ),
    (
        "list-t jagged",
        pl.DataFrame(
            {"t": [_GRID[: 1 + (i % 5) * 16] for i in range(20)]}, schema={"t": _LIST}
        ),
    ),
]
_SHAPE_IDS = [name for name, _ in _SHAPES]
_FRAMES = [frame for _, frame in _SHAPES]

_DOORS: list[Callable[[pl.Expr], pl.Expr]] = [_CURVE.spot_rate, _CURVE.discount_factor]

# The plan fragments a row-sharing lowering leaves behind. ``over(`` is the
# window spelling; the other three are the ``unique`` + dense-``rank`` +
# ``gather`` spelling, which produces no window and would otherwise pass.
#
# Each of the three carries its leading dot because the plan text a door
# lowers to embeds the absolute path of the kernel's shared object, and a
# bare ``rank`` is a substring of ordinary directory names -- a checkout
# under ``franks-checkout`` failed every test here on the shipped, correct
# lowering. The dot is what tells a method call apart from the path around
# it. ``.unique`` carries no bracket because the order-preserving spelling
# of the same optimisation prints as ``unique_stable()``, and that is the
# same thing being caught.
_SHARING_OPERATORS = ("over(", ".unique", ".rank(", ".gather(")


@pytest.mark.parametrize("door", _DOORS, ids=["spot_rate", "discount_factor"])
@pytest.mark.parametrize("frame", _FRAMES, ids=_SHAPE_IDS)
def test_the_door_lowers_without_sharing_rows(
    door: Callable[[pl.Expr], pl.Expr],
    frame: pl.DataFrame,
) -> None:
    """No row-sharing operator reaches the plan, so the read stays element-wise.

    "Evaluate once per distinct time and join the answer back" has two
    spellings: a window, and ``unique`` + dense ``rank`` + ``gather``, which
    produces no window at all. Both are the thing the module docstring says
    costs more than it saves, so both are named here. Catching either is
    cheaper than catching it as a model that got slower.
    """
    plan = frame.lazy().select(door(pl.col("t")).alias("r")).explain()
    found = [operator for operator in _SHARING_OPERATORS if operator in plan]
    assert not found, f"row-sharing operators {found} reached the plan:\n{plan}"


@pytest.mark.parametrize("door", _DOORS, ids=["spot_rate", "discount_factor"])
@pytest.mark.parametrize("frame", _FRAMES, ids=_SHAPE_IDS)
def test_the_door_answers_the_same_on_either_engine(
    door: Callable[[pl.Expr], pl.Expr],
    frame: pl.DataFrame,
) -> None:
    """Streaming and in-memory agree byte for byte.

    The default is streaming and a reader reproducing a number may well
    not use it, so the two have to be the same answer rather than two
    answers that round alike. Compared as Arrow IPC because a curve
    returns NaN outside its domain and ``NaN != NaN`` would let a lost one
    through.
    """
    expr = door(pl.col("t")).alias("r")
    rendered: list[bytes] = []
    for engine in ("streaming", "in-memory"):
        buffer = io.BytesIO()
        frame.lazy().select(expr).collect(engine=engine).write_ipc(
            buffer, compression=None
        )
        rendered.append(buffer.getvalue())
    assert rendered[0] == rendered[1]
