# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A whole number no ``i64`` holds, assigned as a constant column, is refused by name.

A literal past the signed 64-bit range written into a formula is refused
where it is written, naming it and the two moves (``to_text()`` for an
identifier, a decimal literal for a quantity). The same number assigned on
its own -- ``af.c = 2**64`` -- reached Polars instead, which refused it in its
own words: ``conversion from `i128` to `i64` failed in column 'literal'``. The
assignment door now gives it the formula's sentence. A constant at either end
of the range is stored as before.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.lowering.ingress import IntegerLiteralPastI64Error


def _frame() -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame({"pid": [7, 8], "x": [1.5, 2.5]}))


@pytest.mark.parametrize("value", [2**64, 2**63, -(2**63) - 1])
def test_a_constant_past_i64_is_refused_in_the_formula_s_sentence(value: int) -> None:
    af = _frame()
    with pytest.raises(IntegerLiteralPastI64Error) as caught:
        af.c = value
    text = str(caught.value)
    assert "Error setting column 'c'" in text
    assert f"The integer literal {value} is outside the signed 64-bit range" in text
    assert f'af.policy_id.to_text() == "{value}"' in text
    assert "c" not in af.columns


def test_the_bracket_door_refuses_it_the_same_way() -> None:
    af = _frame()
    with pytest.raises(IntegerLiteralPastI64Error, match="18446744073709551616"):
        af["c"] = 2**64


def test_a_numpy_whole_number_past_i64_is_refused_too() -> None:
    af = _frame()
    with pytest.raises(IntegerLiteralPastI64Error, match="18446744073709551615"):
        af.c = np.uint64(2**64 - 1)


@pytest.mark.parametrize("value", [2**63 - 1, -(2**63)])
def test_a_constant_at_either_end_of_i64_is_stored_as_before(value: int) -> None:
    af = _frame()
    af.c = value
    out = af.collect()
    assert out.schema["c"] == pl.Int64
    assert out["c"].to_list() == [value, value]
