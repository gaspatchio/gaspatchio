# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import polars as pl


def read_model_points(path: Path | str) -> pl.LazyFrame:
    """Read model points from parquet file and cast columns to appropriate types"""
    df = pl.scan_parquet(
        path,
        low_memory=True,  # Minimize memory usage
        cache=True,  # Cache the data for repeated access
        row_index_name=None,  # Disable row count column
        rechunk=False,  # Avoid rechunking during read
    )
    return df


def read_model_points_from_s3(s3_uri: str, region: str = "us-east-1") -> pl.LazyFrame:
    """Read model points from S3 parquet file and cast columns to appropriate types"""
    df = pl.scan_parquet(
        s3_uri,
        storage_options={"region": region},
        low_memory=True,
        cache=True,
        row_index_name=None,
        rechunk=False,
    )
    return df
