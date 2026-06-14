# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Verify Table.name public property — needed by MortalityTable wrapper."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table


class TestTableNameProperty:
    """Public read-only Table.name property."""

    def test_name_returns_constructor_argument(self) -> None:
        """Table.name returns the value supplied at construction."""
        frame = pl.DataFrame({"age": [30, 35], "qx": [0.001, 0.002]})
        t = Table(
            name="test_mortality",
            source=frame,
            dimensions={"age": "age"},
            value="qx",
        )
        assert t.name == "test_mortality"

    def test_name_is_read_only(self) -> None:
        """Property has no setter — assignment raises AttributeError."""
        frame = pl.DataFrame({"age": [30, 35], "qx": [0.001, 0.002]})
        t = Table(
            name="test_mortality",
            source=frame,
            dimensions={"age": "age"},
            value="qx",
        )
        with pytest.raises(AttributeError):
            t.name = "renamed"  # type: ignore[misc]
