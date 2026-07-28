# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio describe`` must handle a model's own output.

Regression test for #40: describing a parquet containing a ``list<f64>``
column failed with "Unsupported key type for array storage: List(Float64)"
because describe treated every file as a candidate assumption table. Reading
back a run's own output is the documented agent workflow ("always use
``--output-file``, then read the parquet"), so the failing path was the one
the CLI's own guidance sends people down.
"""

import json

import polars as pl
from typer.testing import CliRunner

from gaspatchio_core.cli import app

runner = CliRunner()


def _write_projection_output(tmp_path):
    path = tmp_path / "results.parquet"
    pl.DataFrame(
        {
            "policy_id": [1, 2],
            "sum_assured": [100_000.0, 250_000.0],
            "net_cf": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        }
    ).write_parquet(path)
    return path


def test_describe_survives_list_columns(tmp_path) -> None:
    path = _write_projection_output(tmp_path)
    result = runner.invoke(app, ["describe", str(path)])
    assert result.exit_code == 0, result.output
    assert "net_cf" in result.output
    assert "Unsupported key type" not in result.output


def test_describe_json_survives_list_columns(tmp_path) -> None:
    path = _write_projection_output(tmp_path)
    result = runner.invoke(app, ["describe", str(path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)


def test_describe_json_never_reports_a_list_column_as_a_dimension(tmp_path) -> None:
    """The agent workflow reads --json; a per-period column is not a lookup key."""
    path = _write_projection_output(tmp_path)
    result = runner.invoke(app, ["describe", str(path), "--json"])
    payload = json.loads(result.stdout)

    assert "net_cf" not in [d["name"] for d in payload["detected_dimensions"]]
    assert payload["list_columns"] == [
        {
            "name": "net_cf",
            "inner_dtype": "Float64",
            "min_length": 3,
            "max_length": 3,
        }
    ]


def test_describe_all_list_columns(tmp_path) -> None:
    """A frame of nothing but list columns must not fall over either."""
    path = tmp_path / "lists_only.parquet"
    pl.DataFrame({"a": [[1.0, 2.0]], "b": [[3.0, 4.0]]}).write_parquet(path)
    result = runner.invoke(app, ["describe", str(path)])
    assert result.exit_code == 0, result.output


def test_describe_still_works_on_an_assumption_table(tmp_path) -> None:
    """The ordinary path must be untouched by the list-column handling."""
    path = tmp_path / "mortality.parquet"
    pl.DataFrame(
        {"age": [40, 41, 42], "rate": [0.001, 0.002, 0.003]}
    ).write_parquet(path)
    result = runner.invoke(app, ["describe", str(path)])
    assert result.exit_code == 0, result.output
    assert "age" in result.output
