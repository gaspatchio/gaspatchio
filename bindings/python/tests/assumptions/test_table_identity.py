# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test Table.canonical_form / source_sha / _content_sha."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios.shocks import MultiplicativeShock


@pytest.fixture
def mortality_df() -> pl.DataFrame:
    """Sample mortality frame with two dimensions and one value column."""
    return pl.DataFrame(
        {
            "age": [30, 31, 32, 30, 31, 32],
            "sex": ["M", "M", "M", "F", "F", "F"],
            "rate": [0.001, 0.0012, 0.0015, 0.0008, 0.001, 0.0012],
        },
    )


@pytest.fixture
def mortality_table(mortality_df: pl.DataFrame) -> Table:
    """Table built from the mortality fixture."""
    return Table(
        name="mortality",
        source=mortality_df,
        dimensions={"age": "age", "sex": "sex"},
        value="rate",
    )


def test_canonical_form_shape(mortality_table: Table) -> None:
    """canonical_form returns the expected identity dict."""
    cf = mortality_table.canonical_form()
    assert cf["kind"] == "Table"
    assert cf["name"] == "mortality"
    assert cf["dimensions"] == ["age", "sex"]  # sorted
    assert cf["value_column"] == "rate"
    assert cf["content_sha"].startswith("sha256:")


def test_source_sha_format(mortality_table: Table) -> None:
    """source_sha is a sha256: prefix plus 64 hex chars."""
    sha = mortality_table.source_sha()
    assert sha.startswith("sha256:")
    assert len(sha) == len("sha256:") + 64


def test_two_tables_same_data_same_sha(mortality_df: pl.DataFrame) -> None:
    """Two Tables with identical data and name produce identical source_sha."""
    dims = {"age": "age", "sex": "sex"}
    t1 = Table(name="m", source=mortality_df, dimensions=dims, value="rate")
    t2 = Table(name="m", source=mortality_df, dimensions=dims, value="rate")
    assert t1.source_sha() == t2.source_sha()


def test_content_sha_row_order_independent(mortality_df: pl.DataFrame) -> None:
    """Shuffled rows still produce the same _content_sha."""
    dims = {"age": "age", "sex": "sex"}
    t1 = Table(name="m", source=mortality_df, dimensions=dims, value="rate")
    t2 = Table(
        name="m",
        source=mortality_df.sample(fraction=1.0, shuffle=True, seed=42),
        dimensions=dims,
        value="rate",
    )
    assert t1._content_sha() == t2._content_sha()  # noqa: SLF001


def test_shocked_table_has_different_sha(mortality_table: Table) -> None:
    """A shocked table has a different source_sha to its base."""
    shocked = mortality_table.with_shock(MultiplicativeShock(factor=1.2))
    assert mortality_table.source_sha() != shocked.source_sha()


def test_shocked_table_content_sha_changes_with_name_held_constant(
    mortality_table: Table,
) -> None:
    """Same name, different value column -> different content_sha."""
    shocked = mortality_table.with_shock(
        MultiplicativeShock(factor=1.2),
        name=mortality_table._name,  # noqa: SLF001
    )
    # Names match, but value column content differs
    assert shocked._name == mortality_table._name  # noqa: SLF001
    assert shocked._content_sha() != mortality_table._content_sha()  # noqa: SLF001
    # And therefore source_sha differs (the new fact, not piggy-backing on name)
    assert shocked.source_sha() != mortality_table.source_sha()


def test_renamed_table_has_different_canonical_form(
    mortality_df: pl.DataFrame,
) -> None:
    """Same content, different names -> different source_sha but same _content_sha."""
    dims = {"age": "age", "sex": "sex"}
    t1 = Table(name="m1", source=mortality_df, dimensions=dims, value="rate")
    t2 = Table(name="m2", source=mortality_df, dimensions=dims, value="rate")
    assert t1.source_sha() != t2.source_sha()
    # But content is identical
    assert t1._content_sha() == t2._content_sha()  # noqa: SLF001


def test_content_sha_empty_table() -> None:
    """Zero-row table produces a stable content_sha."""
    empty_df = pl.DataFrame(
        {"age": [], "rate": []},
        schema={"age": pl.Int64, "rate": pl.Float64},
    )
    dims = {"age": "age"}
    t = Table(name="m", source=empty_df, dimensions=dims, value="rate")
    sha = t._content_sha()  # noqa: SLF001
    assert sha.startswith("sha256:")

    # Reconstructed same-shape empty table produces same SHA
    t2 = Table(name="m", source=empty_df.clone(), dimensions=dims, value="rate")
    assert t._content_sha() == t2._content_sha()  # noqa: SLF001


def test_content_sha_single_row_table() -> None:
    """Single-row table produces a stable content_sha."""
    single_df = pl.DataFrame({"age": [30], "rate": [0.001]})
    t = Table(name="m", source=single_df, dimensions={"age": "age"}, value="rate")
    sha = t._content_sha()  # noqa: SLF001
    assert sha.startswith("sha256:")
    assert len(sha) == len("sha256:") + 64


def test_content_sha_with_nan_value() -> None:
    """NaN in value column does not break content_sha; same NaN-shape -> same SHA."""
    nan_df = pl.DataFrame(
        {"age": [30, 31, 32], "rate": [0.001, float("nan"), 0.002]},
    )
    dims = {"age": "age"}
    t1 = Table(name="m", source=nan_df, dimensions=dims, value="rate")
    t2 = Table(name="m", source=nan_df, dimensions=dims, value="rate")
    assert t1._content_sha() == t2._content_sha()  # noqa: SLF001
