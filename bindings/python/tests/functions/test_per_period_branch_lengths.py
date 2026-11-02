# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period branch with another number of periods than its policy is refused.

``when(af.x > 1).then(af.short).otherwise(0.0)``, with ``short`` one period
shorter than ``x`` for a policy, answered that policy with the shorter run:
the conditional kernel zipped the two lists, so the last period was dropped
and nothing was said. A ``then`` one period longer lost its last period the
same way. On the base this frame answered, for a three-period policy:

- a value on the right, ``then`` short: ``[0.0, 20.0]``;
- a value on the right, ``then`` long: ``[0.0, 20.0, 30.0]`` (the fourth
  ``then`` period ignored);
- a list on the right, ``then`` short: ``[10.0, 20.0]``;
- all lists, ``then`` or ``otherwise`` short: ``[10.0, 20.0]``;
- a per-period flag, ``then`` short: ``[0.0, 20.0]``;
- a text condition, ``then`` short: ``[0.0, 20.0]``.

The specification says list branches of different lengths are not padded or
truncated (sections 11.1.18 and 11.1.28), so each is now refused by the
branch and both lengths, in one policy. The shapes that already refused say
it the same way, in place of the three different sentences they used
(``left=3, then=3, otherwise=2``; ``condition=3, then=2``).
"""

from __future__ import annotations

import re
from collections.abc import Callable

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

_ENGINES = ("streaming", "in-memory")


def _book() -> pl.DataFrame:
    """Two policies of two and three periods; the second carries the misfit."""
    return pl.DataFrame(
        {
            "x": [[1.0, 2.0], [1.0, 2.0, 3.0]],
            "y": [[0.0, 0.0], [0.0, 0.0, 9.0]],
            "full": [[10.0, 20.0], [10.0, 20.0, 30.0]],
            "short": [[10.0, 20.0], [10.0, 20.0]],
            "long": [[10.0, 20.0], [10.0, 20.0, 30.0, 40.0]],
            "flag": [[False, True], [False, True, True]],
            "plan": [["A", "B"], ["A", "B", "C"]],
        }
    )


_Branch = Callable[[ActuarialFrame], object]

_CASES: dict[str, tuple[_Branch, str]] = {
    "a value on the right, then short": (
        lambda af: when(af.x > 1).then(af.short).otherwise(0.0),
        "then=2",
    ),
    "a value on the right, then long": (
        lambda af: when(af.x > 1).then(af.long).otherwise(0.0),
        "then=4",
    ),
    "a list on the right, then short": (
        lambda af: when(af.x > af.y).then(af.short).otherwise(0.0),
        "then=2",
    ),
    "all lists, then short": (
        lambda af: when(af.x > af.y).then(af.short).otherwise(af.full),
        "then=2",
    ),
    "all lists, otherwise short": (
        lambda af: when(af.x > af.y).then(af.full).otherwise(af.short),
        "otherwise=2",
    ),
    "a per-period flag, then short": (
        lambda af: when(af.flag).then(af.short).otherwise(0.0),
        "then=2",
    ),
    "a text condition, then short": (
        lambda af: when(af.plan == "B").then(af.short).otherwise(0.0),
        "then=2",
    ),
    "a value on the right, both lists, otherwise short": (
        lambda af: when(af.x > 1).then(af.full).otherwise(af.short),
        "otherwise=2",
    ),
    "a value on the right, a value then, otherwise short": (
        lambda af: when(af.x > 1).then(1.0).otherwise(af.short),
        "otherwise=2",
    ),
    "a list on the right, a value then, otherwise short": (
        lambda af: when(af.x > af.y).then(1.0).otherwise(af.short),
        "otherwise=2",
    ),
    "text branches, then short": (
        lambda af: (
            when(af.x > 1)
            .then(af.short.polars_native().cast(pl.List(pl.String)))
            .otherwise("none")
        ),
        "then=2",
    ),
}


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize("case", list(_CASES), ids=list(_CASES))
def test_a_branch_of_another_length_is_refused_by_branch_and_lengths(
    case: str, engine: str
) -> None:
    """The branch and both lengths, in one policy -- never a shorter run.

    No row: the kernel is handed a block of rows at a time and could only
    count within it, which streaming makes a different number from the
    frame's. The sentence is therefore the same in both engines.
    """
    branch, misfit = _CASES[case]
    af = ActuarialFrame(_book())
    af.out = branch(af)
    operand = misfit.split("=")[0]
    sentence = re.escape(
        f"mismatched inner list lengths in one policy: {operand} against left\n"
        f"left=3, {misfit} in that policy."
    )

    with pytest.raises(pl.exceptions.ComputeError, match=sentence) as refused:
        af.collect(engine=engine)
    assert re.search(r"\brow \d", str(refused.value).split("Failing column")[0]) is None


@pytest.mark.parametrize("engine", _ENGINES)
def test_branches_that_fit_still_answer(engine: str) -> None:
    """Lists of the policy's own length select as before."""
    af = ActuarialFrame(_book())
    af.out = when(af.x > af.y).then(af.full).otherwise(0.0)

    assert af.collect(engine=engine)["out"].to_list() == [
        [10.0, 20.0],
        [10.0, 20.0, 0.0],
    ]
