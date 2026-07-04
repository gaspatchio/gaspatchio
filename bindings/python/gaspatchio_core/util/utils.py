# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import Any

import polars as pl


def _scan_model_points(
    source: Path | str,
    *,
    storage_options: dict[str, str] | None = None,
) -> pl.LazyFrame:
    """Lazily scan model points from a Parquet or CSV file.

    The format is chosen from the file extension, so a run can point at whichever
    format the upstream data pipeline produced. Reader settings are tuned for the
    large, wide frames typical of a seriatim model point file.
    """
    suffix = Path(source).suffix.lower()
    scan_kwargs: dict[str, Any] = {
        "low_memory": True,  # Minimize memory usage
        "cache": True,  # Cache the data for repeated access
        "row_index_name": None,  # Disable row count column
        "rechunk": False,  # Avoid rechunking during read
    }
    if storage_options is not None:
        scan_kwargs["storage_options"] = storage_options

    if suffix == ".parquet":
        return pl.scan_parquet(source, **scan_kwargs)
    if suffix == ".csv":
        return pl.scan_csv(source, infer_schema_length=10000, **scan_kwargs)

    raise ValueError(
        f"Unsupported model points format: {suffix or '(no file extension)'}. "
        f"Model points must be a .parquet or .csv file (got: {source}).",
    )


def read_model_points(path: Path | str) -> pl.LazyFrame:
    """Read model points from a Parquet or CSV file, chosen by extension."""
    return _scan_model_points(path)


def read_model_points_from_s3(s3_uri: str, region: str = "us-east-1") -> pl.LazyFrame:
    """Read model points from an S3 Parquet or CSV file, chosen by extension."""
    return _scan_model_points(s3_uri, storage_options={"region": region})
