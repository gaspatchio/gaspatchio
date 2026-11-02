# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Verify _schema and _schema_generation are kept in sync with _df after every mutation."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame


@pytest.fixture
def af() -> ActuarialFrame:
    return ActuarialFrame({"x": [1, 2, 3], "y": [10, 20, 30]})


class TestSchemaInvalidation:
    def test_setitem_refreshes_schema_and_bumps_generation(
        self, af: ActuarialFrame
    ) -> None:
        gen0 = af._schema_generation
        af["z"] = af["x"] + af["y"]
        assert af._schema_generation == gen0 + 1
        assert af._schema == af._df.collect_schema()
        assert "z" in af._schema

    def test_setattr_refreshes_schema_and_bumps_generation(
        self, af: ActuarialFrame
    ) -> None:
        gen0 = af._schema_generation
        af.z = af["x"] * 2
        assert af._schema_generation == gen0 + 1
        assert af._schema == af._df.collect_schema()
        assert "z" in af._schema

    @pytest.mark.parametrize("method", ["with_columns", "select", "drop", "rename"])
    def test_each_mutation_method(self, af: ActuarialFrame, method: str) -> None:
        """Every method that ends up reassigning self._df must trigger the setter."""
        gen0 = af._schema_generation

        if method == "with_columns":
            af._df = af._df.with_columns(pl.col("x").alias("z"))
        elif method == "select":
            af._df = af._df.select("x")
        elif method == "drop":
            af._df = af._df.drop("y")
        elif method == "rename":
            af._df = af._df.rename({"x": "x_renamed"})
        else:
            pytest.fail(f"unhandled method {method}")

        assert af._schema_generation == gen0 + 1
        assert af._schema == af._df.collect_schema()


def test_a_plan_that_does_not_resolve_keeps_the_last_schema_and_says_why(
    af: ActuarialFrame,
) -> None:
    """An unresolvable plan is an error at collect; until then, the log says so."""
    from loguru import logger

    resolved = af._schema
    said: list[str] = []
    sink = logger.add(lambda m: said.append(m.record["message"]), level="DEBUG")
    try:
        af._df = af._df.select(pl.col("not_a_column"))
        kept = af._schema
    finally:
        logger.remove(sink)

    assert kept == resolved
    (line,) = [m for m in said if "does not resolve yet" in m]
    assert "not_a_column" in line
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        af.collect()
