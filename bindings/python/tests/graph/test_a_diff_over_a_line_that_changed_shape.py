# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A line edited from one value per policy to one per period is a move, not a crash.

The edit a model's author makes most often -- a scalar column becomes a
projected one -- crashed ``gspio diff`` whenever it read the two results files:
the comparison tried to read a list of values as text, failed, and fell back
to a conversion that can never succeed. The traceback exited 1, the status
that says something moved, so a script reading the status could not tell a
fault from a finding.

A value against a list of values is a change of shape: every policy's cell
moved, whatever the numbers. Each case here is read both ways round, as text
and as JSON, and a fault inside the comparison now exits 2 -- the two could
not be compared -- never 1.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph import diff_results
from gaspatchio.frame.graph.diff_results import _comparable

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_BOOK = pl.DataFrame(
    {
        "policy_id": ["P1", "P2", "P3"],
        "sum_assured": [100_000.0, 250_000.0, 80_000.0],
        "rate": [0.001, 0.002, 0.003],
        "term_months": [3, 3, 3],
    }
)

_MODEL = """
import datetime

from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=datetime.date(2026, 1, 1),
        until="term_months",
        until_value=3,
        frequency="monthly",
    )
    af.base = af.sum_assured * af.rate
    af.x = {x}
    return af
"""

# The one line the four versions differ in, and the type each gives it.
_SHAPES: dict[str, str] = {
    "f64": "af.base + 1.0",
    "list[f64]": "af.base + af.month",
    "list[i64]": "af.month * 2",
    "list[date]": "af.projection.period_dates()",
}

_LISTS = ("list[f64]", "list[i64]", "list[date]")


@pytest.fixture(scope="module")
def versions(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Run each version with ``calc-graph``, its results file named."""
    audits: dict[str, Path] = {}
    for at, (shape, x) in enumerate(_SHAPES.items()):
        folder = tmp_path_factory.mktemp(f"v{at}")
        model = folder / "model.py"
        model.write_text(_MODEL.format(x=x))
        points = folder / "book.parquet"
        _BOOK.write_parquet(points)
        audit = folder / "model.audit.json"
        ran = runner.invoke(
            app,
            [
                "calc-graph",
                str(model),
                str(points),
                "-o",
                str(audit),
                "--results",
                str(folder / "results.parquet"),
            ],
        )
        assert ran.exit_code == 0, ran.output
        audits[shape] = audit
    return audits


def _pairs() -> list[tuple[str, str]]:
    return [("f64", shape) for shape in _LISTS] + [(shape, "f64") for shape in _LISTS]


@pytest.mark.parametrize(("before", "after"), _pairs())
def test_a_line_that_changed_shape_moved_in_every_policy(
    versions: dict[str, Path], before: str, after: str
) -> None:
    """The JSON report names the line as moved in all three policies."""
    ran = runner.invoke(
        app, ["diff", str(versions[before]), str(versions[after]), "--json"]
    )

    assert ran.exit_code == 1, ran.output
    report = json.loads(ran.stdout)
    lines = {line["node"]: line for line in report["values"]["lines"]}
    x = lines["x@1"]
    assert x["compared"] is True
    assert x["moved"] is True
    assert (x["cells_compared"], x["cells_moved"]) == (3, 3)
    assert (x["policies_moved"], x["policies_compared"]) == (3, 3)
    assert x["within_band"] is False
    assert x["worst"]["policy"] == "P1"
    scalar, listed = (
        (x["worst"]["before"], x["worst"]["after"])
        if before == "f64"
        else (x["worst"]["after"], x["worst"]["before"])
    )
    assert scalar == pytest.approx(101.0)
    assert isinstance(listed, list)
    assert len(listed) == 4
    # The line the edit did not touch held.
    assert lines["base@1"]["moved"] is False


@pytest.mark.parametrize(("before", "after"), _pairs())
def test_the_printed_report_names_the_line_that_changed_shape(
    versions: dict[str, Path], before: str, after: str
) -> None:
    """Read as text, the comparison prints and names the line, exiting 1."""
    ran = runner.invoke(app, ["diff", str(versions[before]), str(versions[after])])

    assert ran.exit_code == 1, ran.output
    assert "Traceback" not in ran.output
    assert "x@1" in ran.output


def test_two_values_of_types_text_cannot_hold_compare_as_their_text() -> None:
    """Where neither side casts to text, each value's own text is compared."""
    before = pl.Series([{"a": 1}, None, {"a": 2}])
    after = pl.Series([1.5, None, 2.5], dtype=pl.Object)

    held, other, is_float = _comparable(before, after)

    assert held.dtype == other.dtype == pl.String
    assert held.to_list() == ["{'a': 1}", None, "{'a': 2}"]
    assert other.to_list() == ["1.5", None, "2.5"]
    assert is_float is False


def test_a_fault_inside_the_comparison_exits_2_never_the_status_of_a_move(
    versions: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fault is no finding about either model, so it is not reported as one."""

    def broken(*_: object, **__: object) -> None:
        message = "an internal fault"
        raise RuntimeError(message)

    monkeypatch.setattr(diff_results, "_measure", broken)
    for flags in ([], ["--json"]):
        ran = runner.invoke(
            app,
            ["diff", str(versions["f64"]), str(versions["list[f64]"]), *flags],
        )

        assert ran.exit_code == 2, ran.output
        assert "an internal fault" in ran.stderr
        assert "--no-results" in ran.stderr
        assert ran.stdout == ""


def test_a_difference_exits_1_and_no_difference_exits_0(
    versions: dict[str, Path],
) -> None:
    """The statuses a fault no longer borrows still mean what they meant."""
    same = runner.invoke(app, ["diff", str(versions["f64"]), str(versions["f64"])])
    moved = runner.invoke(
        app, ["diff", str(versions["list[f64]"]), str(versions["list[i64]"])]
    )

    assert same.exit_code == 0, same.output
    assert moved.exit_code == 1, moved.output
