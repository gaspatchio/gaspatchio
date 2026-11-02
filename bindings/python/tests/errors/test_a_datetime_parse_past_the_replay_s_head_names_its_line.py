# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Text that is not a date and time, past the replay's head, still names its line.

The replay reads the first 10,000 rows; a failure in a later row reproduces
nothing there, and the line is then the one calculation whose expression holds
the failing operation. For a strict parse that is ``col("<name>").str.strptime(``,
found from Polars' ``conversion from `str` to `...` failed in column '<name>'``.
That fallback was written for a date and reached a date and time only because
``datetime`` begins with ``date``; it now names both kinds, in any unit and
zone, and these pin it.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

_POLICIES = 10_001


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
@pytest.mark.parametrize(
    ("unit", "zone"), [("us", None), ("ns", None), ("us", "UTC")], ids=str
)
def test_a_datetime_parse_past_the_head_names_its_line(
    engine: str, unit: str, zone: str | None
) -> None:
    texts = ["2025-01-01 00:00:00"] * (_POLICIES - 1) + ["31/12/2025 10:00"]
    af = ActuarialFrame(pl.DataFrame({"issue_text": texts}))
    af.issued = af.issue_text.polars_native().str.to_datetime(
        "%Y-%m-%d %H:%M:%S", time_unit=unit, time_zone=zone
    )

    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        af.collect(engine=engine)

    message = str(refused.value)
    assert "Failing column: 'issued'" in message
    assert "does not read as a date and time" in message
