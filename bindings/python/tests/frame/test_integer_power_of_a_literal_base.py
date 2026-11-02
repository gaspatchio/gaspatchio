# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A whole-number base raised to an integer column answers the ``i64`` the record names.

Section 11.1.25: two ``i64`` operands answer an ``i64`` for an exponent in
``[0, 2**32 - 1]`` whose exact result fits. A literal written as the base is a
whole number, which section 10 carries as an ``i64``, and the record said so
-- but Polars gives a bare integer literal no width and takes a power's type
from its base, so ``2 ** af.pid`` answered an ``Int32`` and 2 ** 40 wrapped to
0, where the JAX engine answered 1,099,511,627,776 from the same record. The
base is now stated as an ``i64`` before the power is taken.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame({"pid": [3, 40], "e": [2, 3]})

# Hand values: 2**3, 2**40; 3**2, 3**3; (-2)**2, (-2)**3; 2**2, 2**3.
_POWERS: list[tuple[str, Callable[[Any], Any], list[int]]] = [
    ("2 ** pid", lambda af: 2**af.pid, [8, 1_099_511_627_776]),
    ("3 ** e", lambda af: 3**af.e, [9, 27]),
    ("(-2) ** e", lambda af: (-2) ** af.e, [4, -8]),
    ("2 ** e", lambda af: 2**af.e, [4, 8]),
]


@pytest.mark.parametrize(
    ("written", "line", "expected"), _POWERS, ids=[p[0] for p in _POWERS]
)
@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
def test_a_literal_base_answers_the_i64_the_record_names(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    expected: list[int],
    door: str,
) -> None:
    af = ActuarialFrame(_BOOK if door == "DataFrame" else _BOOK.lazy())
    af.r = line(af)
    out = af.collect()

    assert out.schema["r"] == pl.Int64
    assert out["r"].to_list() == expected
    document = json.loads(GraphExporter(af).export(profile="executable"))
    (node,) = [n for n in document["nodes"] if n["column"] == "r"]
    assert node["dtype"] == "i64"


def test_a_negative_exponent_column_is_still_refused_in_the_author_s_names() -> None:
    """The base is an i64 now; the refusal still writes the line as it was written."""
    af = ActuarialFrame(pl.DataFrame({"e": [2, -1]}))
    af.r = 2**af.e

    with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
        af.collect()

    message = str(caught.value)
    assert message.startswith(
        "2 ** af.e raises an integer to an integer exponent that holds a value "
        "outside 0 to 2**32 - 1."
    )
    assert "2.0 ** af.e, or 2 ** af.e.to_float()" in message
