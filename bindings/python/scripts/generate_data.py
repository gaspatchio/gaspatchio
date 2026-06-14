# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import numpy as np
import polars as pl
import typer
from loguru import logger
from typing_extensions import Annotated


def expand_dataset(
    input_path: Annotated[
        Path,
        typer.Argument(help="Path to input Parquet file"),
    ],
    output_path: Annotated[
        Path,
        typer.Argument(help="Path to save expanded dataset"),
    ],
    number_of_data_points: Annotated[
        int,
        typer.Argument(help="Target number of rows in expanded dataset"),
    ],
    id_column: Annotated[
        str,
        typer.Option(help="Name of ID column to increment"),
    ] = None,
):
    logger.info("Reading source dataset from {}", input_path)
    df = pl.scan_parquet(input_path)

    # Get schema and actual data
    schema = df.schema
    data = df.collect()
    current_rows = len(data)
    rows_to_generate = number_of_data_points - current_rows

    if rows_to_generate <= 0:
        logger.warning(
            "Target size is less than or equal to current size. No expansion needed."
        )
        return

    # If id_column not specified, use first column
    if id_column is None:
        id_column = data.columns[0]
        logger.info("Using {} as ID column", id_column)

    # Generate synthetic data for each column
    synthetic_data = {}

    # Handle ID column first
    max_id = data[id_column].max()
    new_ids = pl.Series(
        name=id_column, values=range(max_id + 1, max_id + rows_to_generate + 1)
    )
    synthetic_data[id_column] = new_ids

    # Generate synthetic data for other columns
    for col in data.columns:
        if col == id_column:
            continue

        col_data = data[col]
        dtype = schema[col]

        if dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64]:
            min_val = col_data.min()
            max_val = col_data.max()

            if dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64]:
                synthetic_values = np.random.randint(
                    min_val, max_val + 1, size=rows_to_generate
                )
            else:
                synthetic_values = np.random.uniform(
                    min_val, max_val, size=rows_to_generate
                )

            synthetic_data[col] = pl.Series(
                name=col, values=synthetic_values, dtype=dtype
            )

        elif dtype == pl.Boolean:
            # Calculate probability of True in original data
            prob_true = (col_data == True).mean()
            synthetic_values = np.random.choice(
                [True, False], size=rows_to_generate, p=[prob_true, 1 - prob_true]
            )
            synthetic_data[col] = pl.Series(
                name=col, values=synthetic_values, dtype=dtype
            )

        elif dtype == pl.Utf8:
            # For string columns, randomly sample from existing values
            unique_values = col_data.unique()
            synthetic_values = np.random.choice(unique_values, size=rows_to_generate)
            synthetic_data[col] = pl.Series(
                name=col, values=synthetic_values, dtype=dtype
            )

        else:
            logger.warning(
                "Unsupported dtype {} for column {}, using random sampling", dtype, col
            )
            synthetic_values = np.random.choice(col_data, size=rows_to_generate)
            synthetic_data[col] = pl.Series(
                name=col, values=synthetic_values, dtype=dtype
            )

    # Create new dataframe and concatenate
    synthetic_df = pl.DataFrame(synthetic_data)
    final_df = pl.concat([data, synthetic_df])

    logger.info(
        "Generated {} new rows. Total rows: {}", rows_to_generate, len(final_df)
    )

    # Save expanded dataset
    final_df.write_parquet(output_path)
    logger.info("Saved expanded dataset to {}", output_path)


if __name__ == "__main__":
    typer.run(expand_dataset)
