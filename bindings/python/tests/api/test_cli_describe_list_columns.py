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
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from gaspatchio_core.cli import app

runner = CliRunner()


def _write_projection_output(tmp_path: Path) -> Path:
    path = tmp_path / "results.parquet"
    pl.DataFrame(
        {
            "policy_id": [1, 2],
            "sum_assured": [100_000.0, 250_000.0],
            "net_cf": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        }
    ).write_parquet(path)
    return path


def test_describe_survives_list_columns(tmp_path: Path) -> None:
    """Describing a results file must not leak a storage-layer error."""
    path = _write_projection_output(tmp_path)
    result = runner.invoke(app, ["describe", str(path)])
    assert result.exit_code == 0, result.output
    assert "net_cf" in result.output
    assert "Unsupported key type" not in result.output


def test_describe_json_survives_list_columns(tmp_path: Path) -> None:
    """The --json path must survive per-period columns too."""
    path = _write_projection_output(tmp_path)
    result = runner.invoke(app, ["describe", str(path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)


def test_describe_json_never_reports_a_list_column_as_a_dimension(
    tmp_path: Path,
) -> None:
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


def test_describe_all_list_columns(tmp_path: Path) -> None:
    """A frame of nothing but list columns must not fall over either."""
    path = tmp_path / "lists_only.parquet"
    pl.DataFrame({"a": [[1.0, 2.0]], "b": [[3.0, 4.0]]}).write_parquet(path)
    result = runner.invoke(app, ["describe", str(path)])
    assert result.exit_code == 0, result.output


def test_multiple_list_columns_get_distinct_aliases(tmp_path: Path) -> None:
    """Two list columns must not share one alias.

    ``pl.col("a", "b").list.len().alias("n_periods")`` expands to two outputs
    with the same name and raises DuplicateError, so the printed example did
    not run on any file with more than one per-period column.
    """
    path = tmp_path / "two_lists.parquet"
    pl.DataFrame(
        {
            "policy_id": [1, 2],
            "net_cf": [[1.0, 2.0], [3.0, 4.0]],
            "claims": [[5.0, 6.0], [7.0, 8.0]],
        }
    ).write_parquet(path)

    result = runner.invoke(app, ["describe", str(path)])
    assert result.exit_code == 0, result.output
    assert "net_cf_n_periods" in result.output
    assert "claims_n_periods" in result.output
    # The multi-argument form is what produced the duplicate name.
    assert 'pl.col("net_cf", "claims")' not in result.output


def test_json_on_a_list_only_file_invents_no_columns(tmp_path: Path) -> None:
    """An all-list file has no assumption-table value column to report.

    ``analyze_table`` on an empty scalar frame falls back to a default value
    name ("rate") that appears nowhere in the file; reporting it sent agents
    after a column that does not exist.
    """
    path = tmp_path / "lists_only.parquet"
    pl.DataFrame({"a": [[1.0, 2.0]], "b": [[3.0, 4.0]]}).write_parquet(path)

    result = runner.invoke(app, ["describe", str(path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)

    assert payload["detected_value_column"] == ""
    assert payload["detected_dimensions"] == []
    assert "rate" not in payload["suggested_code"]
    assert [c["name"] for c in payload["list_columns"]] == ["a", "b"]


def test_value_column_naming_a_list_column_is_rejected(tmp_path: Path) -> None:
    """A per-period list is projection output, never an assumption value."""
    path = tmp_path / "two_lists.parquet"
    pl.DataFrame(
        {
            "policy_id": [1, 2],
            "net_cf": [[1.0, 2.0], [3.0, 4.0]],
            "claims": [[5.0, 6.0], [7.0, 8.0]],
        }
    ).write_parquet(path)

    result = runner.invoke(app, ["describe", str(path), "--value-column", "net_cf"])
    assert result.exit_code != 0
    assert "list column" in result.output
    assert "policy_id" in result.output  # names the scalar columns available


def test_value_column_naming_a_scalar_column_still_works(tmp_path: Path) -> None:
    """An explicit scalar value column still describes the scalar part.

    Asserting only ``exit_code == 0`` let this pass while the early return for
    per-period columns silently swallowed the ``Table(...)`` example the user
    had explicitly asked for.
    """
    path = tmp_path / "mixed.parquet"
    pl.DataFrame(
        {"age": [40, 41], "rate": [0.1, 0.2], "cf": [[1.0], [2.0]]}
    ).write_parquet(path)

    result = runner.invoke(app, ["describe", str(path), "--value-column", "rate"])
    assert result.exit_code == 0, result.output
    assert "Table(" in result.output
    assert 'value="rate"' in result.output
    # The per-period column is still reported, just not as table material.
    assert "cf" in result.output


def test_describe_still_works_on_an_assumption_table(tmp_path: Path) -> None:
    """The ordinary path must be untouched by the list-column handling."""
    path = tmp_path / "mortality.parquet"
    pl.DataFrame({"age": [40, 41, 42], "rate": [0.001, 0.002, 0.003]}).write_parquet(
        path
    )
    result = runner.invoke(app, ["describe", str(path)])
    assert result.exit_code == 0, result.output
    assert "age" in result.output
