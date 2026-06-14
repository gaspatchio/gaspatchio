# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import polars as pl

# ADDED: Define base path relative to this test file
TEST_DIR = Path(__file__).parent


def test_fixture_load():
    # Load fixture CSV and ensure it loads correctly
    # UPDATED: Use correct relative path and resolve
    fixture = (TEST_DIR.parent / "fixtures" / "age-dates-test.csv").resolve()
    df = pl.read_csv(fixture.as_posix(), infer_schema_length=10000)
    # Assert expected columns and row count
    assert "age" in df.columns
    assert df.height > 0
    assert len(df.columns) == 5
