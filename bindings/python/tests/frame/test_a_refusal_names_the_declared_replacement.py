# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A call 1.0 no longer takes names the declared operation before the escape.

A line through ``.polars_native()`` records as engine-native: it is less
auditable and only one engine runs it. Where the vocabulary declares the
calculation under another name, the refusal says that name first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

_FRAME = pl.DataFrame({"policy_id": [1], "run": [[1.0, 2.0]], "one": [1.5]})


@pytest.mark.parametrize(
    ("spelled", "named"),
    [
        (lambda af: af.run.shift(1), ".projection.previous_period()"),
        (lambda af: af.run.shift(1), ".projection.at_period("),
        (lambda af: af.one.cast(pl.Int64), ".to_integer()"),
        (lambda af: af.one.cast(pl.Int64), ".to_float()"),
        (lambda af: af.one.cast(pl.Utf8), ".to_text()"),
        (lambda af: af.run.list.first(), ".list.get(0)"),
        (lambda af: af.run.list.last(), ".list.get(-1)"),
    ],
    ids=[
        "shift back",
        "shift any",
        "cast int",
        "cast float",
        "cast text",
        "first",
        "last",
    ],
)
def test_the_refusal_names_the_declared_operation_before_the_escape(
    spelled: Callable[[ActuarialFrame], object], named: str
) -> None:
    with pytest.raises(AttributeError) as refused:
        spelled(ActuarialFrame(_FRAME))

    message = str(refused.value)
    assert named in message
    assert message.index(named) < message.index(".polars_native()")
