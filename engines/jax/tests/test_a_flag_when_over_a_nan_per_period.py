# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period ``when`` choosing a flag over a NaN condition is a null, however read.

Section 11.1.28: where the condition has no truth value the answer is null
where its type holds no NaN, and a flag holds none; a consumer that carries
no null refuses those cells by name. This engine refused the flag stored as
it is, ``== 1`` and ``is_in``, but answered NaN where it was read by
arithmetic, ``&``, ``~`` or another ``when``, and a wrong flag under
``is_null`` and ``is_not_null``. Every one of those reads now refuses, and
the refusal names the node the model wrote rather than the check.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.engines.report import EngineRefusal

if TYPE_CHECKING:
    from collections.abc import Callable

NAN = math.nan


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "L": [[0.5, NAN, 2.0], [0.5, 0.5, 0.5]],
                "flag": [True, True],
                "g": [False, False],
                "q": [0.1, 0.1],
            }
        )
    )


_READS: dict[str, Callable[[object, ActuarialFrame], object]] = {
    "stored": lambda w, _af: w,
    "* 1.0": lambda w, _af: w * 1.0,  # type: ignore[operator]
    "- q": lambda w, af: w - af.q,  # type: ignore[operator]
    "+ 0": lambda w, _af: w + 0,  # type: ignore[operator]
    "== 1": lambda w, _af: w == 1,
    "& flag": lambda w, af: w & af.flag,  # type: ignore[operator]
    "~": lambda w, _af: ~w,  # type: ignore[operator]
    "is_null": lambda w, _af: w.is_null(),  # type: ignore[attr-defined]
    "is_not_null": lambda w, _af: w.is_not_null(),  # type: ignore[attr-defined]
    "is_in": lambda w, _af: w.is_in([True]),  # type: ignore[attr-defined]
    "when condition": lambda w, _af: when(w).then(1.0).otherwise(0.0),
}

_PAIRS: dict[str, Callable[[ActuarialFrame], object]] = {
    "flag | flag": lambda af: when(af.L < 1.0).then(af.flag).otherwise(af.g),
    "True | False": lambda af: when(af.L < 1.0).then(True).otherwise(False),  # noqa: FBT003
    "flag | False": lambda af: when(af.L < 1.0).then(af.flag).otherwise(False),  # noqa: FBT003
}


@pytest.mark.parametrize("pair", list(_PAIRS))
@pytest.mark.parametrize("read", list(_READS))
def test_every_read_of_the_null_refuses_by_the_node(read: str, pair: str) -> None:
    af = _frame()
    af.answer = _READS[read](_PAIRS[pair](af), af)
    producer = af.collect().get_column("answer").to_list()
    # The producer's answer at the unknown period: a null, or the null tested.
    expected = {"is_null": True, "is_not_null": False}.get(read)
    assert producer[0][1] is expected
    with pytest.raises(EngineRefusal, match=r"answer@\d+ · 1 · a comparison"):
        af.collect(engine="jax")


def test_a_condition_with_a_truth_value_everywhere_still_answers() -> None:
    af = ActuarialFrame(
        pl.DataFrame({"L": [[0.5, 3.0, 2.0]], "flag": [True], "g": [False], "q": [0.1]})
    )
    af.answer = when(af.L < 1.0).then(af.flag).otherwise(af.g) * 1.0
    assert af.collect(engine="jax").get_column("answer").to_list() == [[1.0, 0.0, 0.0]]
