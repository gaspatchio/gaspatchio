# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One policy's run shows the run's number, even where the model reads across rows.

``gspio run-single-policy`` cut the book to one row and ran the model on it,
outside the guard a batch runner opens. A model allocating an overhead of
12,000 by share of sum assured gave each policy 12,000 there, where the run
gives policy 1 its 1,500; a grid sized from the youngest life gave policy 4
a horizon of its own; a filter on the book's mean valued a policy the run
drops (audit C3a-F1). Now (spec section 13.2) the policy runs alone inside the
guard, and where the guard refuses a read across rows the whole book runs,
the policy is selected from it, and one line says so. A policy the model's
own selection drops is refused by name. The Python runner does the same.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.engines.protocol import digest_of_inputs, read_manifest
from gaspatchio.runner import ModelRunConfig, run_model, run_single_policy

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3, 4],
        "issue_age": [35, 50, 65, 70],
        "sa": [100_000.0, 250_000.0, 400_000.0, 50_000.0],
        "term": [3, 3, 3, 3],
    }
)

_HEAD = """import datetime
import polars as pl
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
"""
_TIMELINE = (
    "    af = af.projection.set(valuation_date=datetime.date(2025, 1, 1), "
    'until="term_years", until_value="term", frequency="annual")\n'
)

MODELS = {
    # An overhead of 12,000 allocated by share of sum assured.
    "share": _HEAD
    + _TIMELINE
    + "    af.share = af.sa / af.sa.polars_native().sum()\n"
    + "    af.overhead = af.share * 12000.0\n"
    + "    return af\n",
    # One grid sized from the youngest life in the frame.
    "max_age_grid": _HEAD
    + "    af = af.projection.set(valuation_date=datetime.date(2025, 1, 1), "
    'until="maximum_age", until_value=100, frequency="annual", per_policy=False)\n'
    + "    af.pay = (af.sa * 0.01).projection.broadcast_to_periods()\n"
    + "    af.pv = af.pay.projection.prospective_value(discount_rate=0.03)\n"
    + "    return af\n",
    # The 0.9 template's setup: collect, a share in Polars, rebuild.
    "phase_one_share": _HEAD
    + "    mp = af.collect()\n"
    + "    mp = mp.with_columns((pl.col('sa') / pl.col('sa').sum()).alias('share'))\n"
    + "    af = ActuarialFrame(mp)\n"
    + _TIMELINE
    + "    af.expense = af.share * 900.0\n"
    + "    return af\n",
    # Value only the policies at or above the book's mean sum assured.
    "filter_by_mean": _HEAD
    + "    af = af.filter(pl.col('sa') >= pl.col('sa').mean())\n"
    + _TIMELINE
    + "    af.claim = af.sa * 0.01\n"
    + "    return af\n",
    # A share through a Python function.
    "map_batches": _HEAD
    + _TIMELINE
    + "    af.share = af.sa.polars_native().map_batches("
    + "lambda s: s / s.sum(), return_dtype=pl.Float64)\n"
    + "    af.overhead = af.share * 12000.0\n"
    + "    return af\n",
    # One simulated return per policy, in book order.
    "injected": _HEAD
    + _TIMELINE
    + "    af.ret = pl.Series([0.05, -0.02, 0.10, 0.01])\n"
    + "    af.gain = af.sa * af.ret\n"
    + "    return af\n",
    # Per row: one grid of a fixed length, not sized from the rows.
    "fixed_grid": _HEAD
    + "    af = af.projection.set(start_date=datetime.date(2025, 1, 1), "
    'n_periods=5, frequency="annual", per_policy=False)\n'
    + "    af.pay = (af.sa * 0.01).projection.broadcast_to_periods()\n"
    + "    af.pv = af.pay.projection.prospective_value(discount_rate=0.03)\n"
    + "    return af\n",
}
ACROSS_ROWS = [
    "share",
    "max_age_grid",
    "phase_one_share",
    "map_batches",
    "injected",
]


def _files(tmp_path: Path, name: str) -> tuple[Path, Path]:
    model = tmp_path / f"{name}.py"
    model.write_text(MODELS[name])
    book = tmp_path / "book.parquet"
    BOOK.write_parquet(book)
    return model, book


def _config(model: Path, book: Path, mode: str) -> ModelRunConfig:
    return ModelRunConfig(
        directory=model.parent,
        model_file=model.name,
        model_points_file=str(book),
        mode=mode,  # type: ignore[arg-type]
    )


def _the_run_s_row(model: Path, book: Path, policy: int) -> pl.DataFrame:
    whole = run_model(_config(model, book, "optimize"))
    assert whole.result is not None
    return whole.result.filter(pl.col("policy_id") == policy)


@pytest.mark.parametrize("name", [*ACROSS_ROWS, "fixed_grid"])
@pytest.mark.parametrize("mode", ["debug", "optimize"])
@pytest.mark.parametrize("policy", [1, 4])
def test_the_python_runner_answers_the_run_s_row(
    tmp_path: Path, name: str, mode: str, policy: int
) -> None:
    model, book = _files(tmp_path, name)

    one = run_single_policy(_config(model, book, mode), str(policy))

    assert one.status == "success", one.error_message
    assert one.result is not None
    assert one.result.equals(_the_run_s_row(model, book, policy))
    if name == "fixed_grid":
        assert one.route is None
    else:
        assert one.route is not None
        assert f"{name}.py:" in one.route
        assert f"ran the 4-policy book and selected policy {policy}" in one.route


def test_the_share_is_the_book_s_share(tmp_path: Path) -> None:
    model, book = _files(tmp_path, "share")
    one = run_single_policy(_config(model, book, "debug"), "1")
    assert one.result is not None
    # 12,000 x 100,000 / 800,000, by hand.
    assert one.result["overhead"].to_list() == [1500.0]
    assert one.route is not None
    assert 'sum on col("sa")' in one.route


def test_a_per_row_model_runs_its_one_row(tmp_path: Path) -> None:
    model, book = _files(tmp_path, "fixed_grid")
    one = run_single_policy(_config(model, book, "debug"), "2")
    assert one.route is None
    assert one.frame is not None
    assert one.frame.collect().height == 1


@pytest.mark.parametrize("mode", ["debug", "optimize"])
def test_a_policy_the_model_drops_is_refused_by_name(tmp_path: Path, mode: str) -> None:
    model, book = _files(tmp_path, "filter_by_mean")

    one = run_single_policy(_config(model, book, mode), "1")

    assert one.status == "error"
    said = str(one.error_message)
    assert "Policy 1 is not valued by this model" in said
    assert "filter_by_mean.py:7" in said
    assert "the 4-policy book ran" in said
    # A policy the model keeps is the run's.
    kept = run_single_policy(_config(model, book, mode), "3")
    assert kept.result is not None
    assert kept.result.equals(_the_run_s_row(model, book, 3))


def test_the_command_says_which_book_ran(tmp_path: Path) -> None:
    model, book = _files(tmp_path, "share")
    out = tmp_path / "one.parquet"

    result = runner.invoke(
        app, ["run-single-policy", str(model), str(book), "1", "-o", str(out)]
    )

    assert result.exit_code == 0, result.output
    said = " ".join(result.output.split())
    assert "share.py:8 reads across rows" in said
    assert "ran the 4-policy book and selected policy 1" in said
    assert pl.read_parquet(out)["overhead"].to_list() == [1500.0]
    # The manifest names the book that ran: the whole book, beside the one
    # row it holds, whose id the row identity names.
    manifest = read_manifest(out)
    assert manifest.inputs_digest == digest_of_inputs(BOOK, BOOK.columns)
    assert manifest.row_identity == ("policy_id",)


def test_the_command_runs_a_per_row_model_on_its_one_row(tmp_path: Path) -> None:
    model, book = _files(tmp_path, "fixed_grid")
    out = tmp_path / "one.parquet"

    result = runner.invoke(
        app, ["run-single-policy", str(model), str(book), "2", "-o", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert "reads across rows" not in result.output
    manifest = read_manifest(out)
    one_row = BOOK.filter(pl.col("policy_id") == 2)
    assert manifest.inputs_digest == digest_of_inputs(one_row, one_row.columns)


def test_the_command_refuses_a_policy_the_model_drops(tmp_path: Path) -> None:
    model, book = _files(tmp_path, "filter_by_mean")

    result = runner.invoke(app, ["run-single-policy", str(model), str(book), "1"])

    assert result.exit_code == 1
    said = " ".join(result.output.split())
    assert "Policy 1 is not valued by this model" in said
