# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A sampled date outside the years 1 to 9999 refuses the export by its column.

An administration extract carries ``9999-12-31`` as an open end, and
``excel.edate(1)`` on it is year 10000, which the run holds as a count of
days. The export reads the sampled row's value as a date to write it as
ISO-8601 text, and there the host language raised ``ValueError: year 10000
is out of range`` naming no column. The export now refuses by the column and
the cause; section 11.1.33 puts such a result outside the domain.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter


def test_the_sampled_row_s_date_past_9999_names_the_column() -> None:
    book = pl.DataFrame(
        {
            "pid": [1, 2],
            "end_date": [dt.date(9999, 12, 31), dt.date(2030, 6, 30)],
            "sa": [1000.0, 2000.0],
        }
    )
    af = ActuarialFrame(book)
    af.end_plus_1m = af.end_date.excel.edate(1)
    af.sa2 = af.sa * 2.0
    out = af.collect()

    with pytest.raises(
        ValueError, match="Column 'end_plus_1m' holds a date outside"
    ) as refused:
        GraphExporter(af).export(out, profile="executable", include_source=False)

    assert "9999-12-31" in str(refused.value)
