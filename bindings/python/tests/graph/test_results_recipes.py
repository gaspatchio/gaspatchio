# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The three utilities the results-analysis skill ships, run over a real export.

The skill teaches four recipes and hands three scripts over to do the parts
that are easy to get subtly wrong: laying one policy's timeline out as a frame,
folding a whole book out of the results Parquet, and refusing a results file
that is not the one its artifact was written against. A recipe nobody runs is
prose; these are the checks that keep the three honest.

The fixture is this file's own. A model of six monthly periods over three
policies is written into a temporary directory, exported through the command
line exactly as a user would export it -- artifact and results file in one run
-- and every assertion below is made against that pair. Nothing here reads a
file the repository does not build, so the suite owns what it asserts on.

What is asserted, one per thing that could quietly stop being true:

* the timeline frame is one row per projection period and one column per list
  node, so a chart drawn from it has the periods it claims to have;
* the book total at each period equals the same sum taken a different way,
  straight off the list column, so the explode-and-group fold is not quietly
  dropping or double-counting a policy;
* a mean is that sum over the policy count, so the two folds agree;
* the digest check passes on the file the artifact names and refuses the same
  file one byte different, which is the whole reason it exists;
* each utility answers ``--help``, because a script an agent cannot interrogate
  is a script it will guess at.
"""

from __future__ import annotations

import copy
import csv
import importlib.util
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from loguru import logger
from typer.testing import CliRunner

from gaspatchio.cli import app

if TYPE_CHECKING:
    import types
    from collections.abc import Callable, Iterator

runner = CliRunner()

SCRIPTS = (
    Path(__file__).resolve().parents[4]
    / "skills"
    / "gaspatchio-results-analysis"
    / "scripts"
)

N_PERIODS = 6
"""The projection the fixture model runs, so a timeline is seven rows long."""

POLICIES = 3
"""How many policies the results file holds, and what a mean divides by."""

MODEL_SRC = '''
import datetime

from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Six monthly periods of decrement, survival, claims and net cashflow."""
    af = af.projection.set(
        start_date=datetime.date(2026, 1, 31),
        n_periods=6,
        frequency="monthly",
    )
    af.monthly_decrement = (af.annual_decrement / 12).projection.broadcast_to_periods(
        like=af.month
    )
    af.survival = af.monthly_decrement.projection.cumulative_survival()
    af.claims = af.sum_assured * af.monthly_decrement * af.survival
    af.net_cf = af.premium - af.claims
    return af
'''


@dataclass(frozen=True, slots=True)
class Exported:
    """One run's two files, and the artifact already parsed.

    Attributes:
        root: The directory the model sits in, which every path in the
            artifact is written relative to.
        artifact: Where the JSON document the export wrote sits on disk.
        results: The Parquet the same run wrote.
        document: The artifact, parsed.

    """

    root: Path
    artifact: Path
    results: Path
    document: dict[str, Any]


def _utility(name: str) -> types.ModuleType:
    """Load one of the skill's scripts as a module.

    The scripts sit in the skill payload rather than in an importable package
    -- an ``__init__.py`` there would claim a package nothing imports -- so
    they are loaded by path. The module is put in ``sys.modules`` before it is
    executed because a ``slots=True`` dataclass looks its own module up by
    name while the class body is being processed.
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None, f"no utility named {name} in {SCRIPTS}"
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def timeline_utility() -> types.ModuleType:
    return _utility("artifact_timeline")


@pytest.fixture(scope="module")
def totals_utility() -> types.ModuleType:
    return _utility("portfolio_totals")


@pytest.fixture(scope="module")
def digest_utility() -> types.ModuleType:
    return _utility("check_results_digest")


def _write_model(root: Path) -> tuple[Path, Path]:
    """Write the fixture model and the policy data it is run over."""
    model = root / "model.py"
    model.write_text(MODEL_SRC)
    points = root / "points.parquet"
    pl.DataFrame(
        {
            "policy_id": ["A", "B", "C"],
            "sum_assured": [100_000.0, 250_000.0, 50_000.0],
            "annual_decrement": [0.012, 0.008, 0.020],
            "premium": [1_200.0, 2_500.0, 600.0],
        }
    ).write_parquet(points)
    return model, points


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> Exported:
    """Export one run's artifact and results file, the way a user would."""
    root = tmp_path_factory.mktemp("results_recipes")
    model, points = _write_model(root)
    artifact = root / "graph.json"
    results = root / "results.parquet"
    outcome = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(points),
            "-o",
            str(artifact),
            "--output-file",
            str(results),
        ],
    )
    assert outcome.exit_code == 0, outcome.output
    return Exported(
        root=root,
        artifact=artifact,
        results=results,
        document=json.loads(artifact.read_text()),
    )


def _list_node_ids(document: dict[str, Any]) -> list[str]:
    """Return the identifier of every node carrying a per-period value."""
    return [node["id"] for node in document["nodes"] if node["shape"] == "list"]


# --- Recipe 1: one policy's timeline, read out of the artifact --------------


def test_the_timeline_is_one_row_per_period_and_one_column_per_list_node(
    exported: Exported, timeline_utility: types.ModuleType
) -> None:
    """The frame has the periods the projection ran and the nodes it wrote."""
    frame = timeline_utility.timeline(exported.document)

    assert frame.height == N_PERIODS + 1
    expected = {timeline_utility.PERIOD_COLUMN, *_list_node_ids(exported.document)}
    assert set(frame.columns) == expected


def test_the_timeline_carries_the_values_the_artifact_states(
    exported: Exported, timeline_utility: types.ModuleType
) -> None:
    """Every cell is the node's own sample, read across rather than invented."""
    frame = timeline_utility.timeline(exported.document)
    stated = {
        node["id"]: node["value_sample"]
        for node in exported.document["nodes"]
        if node["shape"] == "list"
    }

    for node_id, values in stated.items():
        assert frame[node_id].to_list() == values


def test_the_time_axis_leads_the_timeline(
    exported: Exported, timeline_utility: types.ModuleType
) -> None:
    """``month`` sits first after the period index, so the frame reads left."""
    frame = timeline_utility.timeline(exported.document)

    assert frame.columns[0] == timeline_utility.PERIOD_COLUMN
    assert frame.columns[1] == "month@1"


def test_the_timeline_holds_the_full_doubles_the_results_file_holds(
    exported: Exported, timeline_utility: types.ModuleType
) -> None:
    """The declared policy's cells are its results-file values, to the bit.

    The skill tells a reconciler the artifact's timeline is the run's own
    numbers; a sample written to fewer digits than the double would match
    some cells of a workbook and not others.
    """
    frame = timeline_utility.timeline(exported.document)
    policy = exported.document["enrichment"]["policy_id"]
    row = pl.read_parquet(exported.results).filter(pl.col("policy_id") == policy)

    for column in ("survival", "claims", "net_cf"):
        assert frame[f"{column}@1"].to_list() == row[column].item().to_list()


def _warnings_from(read: Callable[[], object]) -> list[str]:
    """Return what loguru warned while ``read`` ran."""
    heard: list[str] = []
    sink = logger.add(lambda message: heard.append(str(message)), level="WARNING")
    try:
        read()
    finally:
        logger.remove(sink)
    return heard


def test_a_node_one_value_short_of_the_axis_is_named_not_left_a_blank_period(
    exported: Exported, timeline_utility: types.ModuleType
) -> None:
    """A per-period node beside the boundary axis blanks the last row, and says so.

    A compiled rollforward's balances hold one value per period where
    ``month`` holds one per boundary, so the frame's last row is the axis's
    final boundary with the balance blank -- a row a reader of the CSV takes
    for one more period. The document is the fixture's own with one node cut
    to that length, the shape a rollforward export writes.
    """
    document = copy.deepcopy(exported.document)
    node = next(n for n in document["nodes"] if n["id"] == "net_cf@1")
    node["value_sample"] = node["value_sample"][:-1]

    frames: list[pl.DataFrame] = []
    heard = _warnings_from(lambda: frames.append(timeline_utility.timeline(document)))

    frame = frames[0]
    assert frame.height == N_PERIODS + 1
    assert frame["net_cf@1"][-1] is None
    assert frame["month@1"][-1] == N_PERIODS
    assert len(heard) == 1
    assert f"net_cf@1 ({N_PERIODS})" in heard[0]
    assert f"the {N_PERIODS + 1} of month@1" in heard[0]
    assert "final boundary, not another period" in heard[0]


def test_a_timeline_whose_nodes_all_fill_the_axis_warns_of_nothing(
    exported: Exported, timeline_utility: types.ModuleType
) -> None:
    """The warning is for a short node only, not for every export."""
    heard = _warnings_from(lambda: timeline_utility.timeline(exported.document))

    assert heard == []


def test_the_nodes_table_states_the_formula_as_the_model_wrote_it(
    exported: Exported, timeline_utility: types.ModuleType
) -> None:
    """Identifier, formula, shape and tier, one row per node, nothing derived."""
    table = timeline_utility.nodes_table(exported.document)

    assert table.height == len(exported.document["nodes"])
    assert table.columns == ["id", "formula", "shape", "tier"]
    net_cf = table.filter(pl.col("id") == "net_cf@1")
    assert net_cf["formula"].item() == "af.premium - af.claims"


def test_an_artifact_carrying_no_values_refuses_to_pretend_to_a_timeline(
    timeline_utility: types.ModuleType,
) -> None:
    """The refusal names the command that writes one that does carry values."""
    with pytest.raises(ValueError, match="carries no values"):
        timeline_utility.timeline({"nodes": [], "enrichment": None})


# --- Recipe 2: the book, folded out of the results Parquet ------------------


def test_the_book_total_at_each_period_is_the_sum_over_policies(
    exported: Exported, totals_utility: types.ModuleType
) -> None:
    """The fold agrees with the same sum taken straight off the list column."""
    frame = totals_utility.read_results(exported.results)
    folded = totals_utility.fold(frame)

    for period in range(N_PERIODS + 1):
        by_hand = frame.select(pl.col("net_cf").list.get(period).sum()).item()
        assert folded.per_period["net_cf"][period] == pytest.approx(by_hand)


def test_the_mean_is_the_sum_over_the_policy_count(
    exported: Exported, totals_utility: types.ModuleType
) -> None:
    """Two folds of one rectangular book, and they agree."""
    frame = totals_utility.read_results(exported.results)
    summed = totals_utility.fold(frame, aggregate="sum")
    averaged = totals_utility.fold(frame, aggregate="mean")

    assert summed.policy_count == POLICIES
    for period in range(N_PERIODS + 1):
        assert averaged.per_period["net_cf"][period] == pytest.approx(
            summed.per_period["net_cf"][period] / POLICIES
        )


def test_the_per_policy_columns_are_summed_across_the_book(
    exported: Exported, totals_utility: types.ModuleType
) -> None:
    """A per-policy result has no period to average over, so it is totalled."""
    frame = totals_utility.read_results(exported.results)
    folded = totals_utility.fold(frame)

    assert folded.scalars["sum_assured"].item() == pytest.approx(400_000.0)
    assert folded.scalars["premium"].item() == pytest.approx(4_300.0)


def test_the_columns_no_fold_is_defined_over_are_named_not_guessed_at(
    exported: Exported, totals_utility: types.ModuleType
) -> None:
    """Dates and identifiers are left out, and the fold says which."""
    frame = totals_utility.read_results(exported.results)
    folded = totals_utility.fold(frame)

    assert "policy_id" in folded.skipped
    assert "projection_start_date" in folded.skipped
    assert "net_cf" not in folded.skipped


def test_a_column_the_results_file_does_not_hold_is_refused_by_name(
    exported: Exported, totals_utility: types.ModuleType
) -> None:
    """The message names the column and the command that lists the real ones."""
    frame = totals_utility.read_results(exported.results)

    with pytest.raises(ValueError, match="no column named reserve"):
        totals_utility.fold(frame, columns=["reserve"])


def test_a_jagged_book_folds_over_the_periods_each_policy_reaches(
    totals_utility: types.ModuleType,
) -> None:
    """A shorter timeline contributes where it has values and nowhere else."""
    jagged = pl.DataFrame({"net_cf": [[1.0, 2.0, 3.0], [10.0, 20.0]]})

    folded = totals_utility.fold(jagged)

    assert folded.per_period["net_cf"].to_list() == [11.0, 22.0, 3.0]


# --- Recipe 4: the results file is the one the artifact was written against --


def test_the_digest_check_passes_on_the_file_the_artifact_names(
    exported: Exported, digest_utility: types.ModuleType
) -> None:
    """Zero, and the digest it reports is the one the artifact states."""
    status = digest_utility.main([str(exported.artifact), "--root", str(exported.root)])

    assert status == digest_utility.MATCHED
    outcome = digest_utility.check(exported.document, exported.root)
    assert outcome.found == exported.document["model"]["results"]["fingerprint"]


def test_the_digest_check_refuses_a_results_file_one_byte_different(
    exported: Exported, digest_utility: types.ModuleType, tmp_path: Path
) -> None:
    """One byte appended, and the pair is refused with both digests printed."""
    moved = tmp_path / "graph.json"
    moved.write_text(exported.artifact.read_text())
    changed = tmp_path / exported.document["model"]["results"]["path"]
    changed.write_bytes(exported.results.read_bytes() + b"\x00")

    status = digest_utility.main([str(moved), "--root", str(tmp_path)])

    assert status == digest_utility.DIFFERED
    assert status != 0
    outcome = digest_utility.check(exported.document, tmp_path)
    assert outcome.stated != outcome.found
    assert "Quote no number from it" in outcome.message


def test_an_artifact_naming_no_results_file_has_nothing_to_check(
    digest_utility: types.ModuleType, tmp_path: Path
) -> None:
    """Absent is not a mismatch, and the two do not share an exit status."""
    model, points = _write_model(tmp_path)
    artifact = tmp_path / "graph.json"
    outcome = runner.invoke(
        app, ["calc-graph", str(model), str(points), "-o", str(artifact)]
    )
    assert outcome.exit_code == 0, outcome.output

    status = digest_utility.main([str(artifact), "--root", str(tmp_path)])

    assert status == digest_utility.UNCHECKABLE
    assert status != digest_utility.DIFFERED


# --- Every utility answers for itself ---------------------------------------


@pytest.mark.parametrize(
    "name",
    ["artifact_timeline", "portfolio_totals", "check_results_digest"],
)
def test_each_utility_prints_its_own_help(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A script an agent cannot interrogate is a script it will guess at."""
    utility = _utility(name)

    with pytest.raises(SystemExit) as exit_status:
        utility.main(["--help"])

    assert exit_status.value.code == 0
    printed = capsys.readouterr().out
    assert f"usage: {name}.py" in printed
    assert "--help" in printed


@pytest.mark.parametrize(
    "name",
    ["artifact_timeline", "portfolio_totals", "check_results_digest"],
)
def test_each_utility_is_importable_and_does_nothing_on_import(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Importing one reads nothing, writes nothing and prints nothing."""
    _utility(name)

    assert capsys.readouterr().out == ""


def test_the_command_line_writes_a_timeline_a_caller_can_read_back(
    exported: Exported, timeline_utility: types.ModuleType, tmp_path: Path
) -> None:
    """The CSV door round-trips into the same frame the function returns."""
    written = tmp_path / "timeline.csv"

    status = timeline_utility.main(
        [str(exported.artifact), "--format", "csv", "--output", str(written)]
    )

    assert status == 0
    read_back = pl.read_csv(written)
    assert read_back.height == N_PERIODS + 1
    assert read_back.columns == timeline_utility.timeline(exported.document).columns


def test_the_command_line_writes_totals_as_json_a_caller_can_read_back(
    exported: Exported, totals_utility: types.ModuleType, tmp_path: Path
) -> None:
    """The JSON door states the fold taken, the policy count and the skips."""
    written = tmp_path / "totals.json"

    status = totals_utility.main(
        [str(exported.results), "--format", "json", "--output", str(written)]
    )

    assert status == 0
    document = json.loads(written.read_text())
    assert document["aggregate"] == "sum"
    assert document["policy_count"] == POLICIES
    assert len(document["per_period"]) == N_PERIODS + 1
    assert "policy_id" in document["skipped"]


@pytest.fixture(autouse=True)
def _forget_the_utilities() -> Iterator[None]:
    """Leave no utility behind in ``sys.modules`` for another test to inherit."""
    yield
    for name in ("artifact_timeline", "portfolio_totals", "check_results_digest"):
        sys.modules.pop(name, None)


_FORMULA_CELLS = [
    '=HYPERLINK("https://example.invalid","x")',
    "+1+1",
    "-2+3",
    "@SUM(1)",
    "\tx",
    "\rx",
]


def _csv_cells(text: str) -> list[list[str]]:
    """Return the cells of a CSV the way a spreadsheet's reader splits them."""
    return list(csv.reader(io.StringIO(text)))


def test_the_timeline_csv_neutralises_formula_cells_and_leaves_numbers(
    timeline_utility: types.ModuleType,
) -> None:
    """A text cell or header Excel would run as a formula gets a leading quote."""
    frame = pl.DataFrame(
        {
            "id": [*_FORMULA_CELLS, "plain", None],
            "=cost": [-1.5, 2.0, -0.25, 3.0, 4.0, 5.0, -6.0, 7.0],
        }
    )

    header, *rows = _csv_cells(timeline_utility.render(frame, "csv"))

    assert header == ["id", "'=cost"]
    assert [row[0] for row in rows] == [
        *(f"'{cell}" for cell in _FORMULA_CELLS),
        "plain",
        "",
    ]
    assert [row[1] for row in rows] == [
        "-1.5",
        "2.0",
        "-0.25",
        "3.0",
        "4.0",
        "5.0",
        "-6.0",
        "7.0",
    ]
    # The other two forms say what the frame holds, unchanged.
    assert (
        json.loads(timeline_utility.render(frame, "json"))[0]["id"] == _FORMULA_CELLS[0]
    )


def test_the_totals_csv_neutralises_a_formula_header_and_leaves_numbers(
    totals_utility: types.ModuleType,
) -> None:
    """A per-period column named like a formula reaches the CSV header inert."""
    per_period = pl.DataFrame({"period": [0, 1], "@net_cf": [-10.5, 3.0]})
    folded = totals_utility.Fold(
        per_period=per_period, scalars=pl.DataFrame(), policy_count=2, skipped=()
    )

    header, *rows = _csv_cells(totals_utility.render(folded, "csv", "sum"))

    assert header == ["period", "'@net_cf"]
    assert rows == [["0", "-10.5"], ["1", "3.0"]]
