# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``verify`` over what a model rests on beside its own file: tables and helpers.

Seven of seven independent builds hand-built the same check: an assumption table
edited on disk, and a helper module the model imports edited beside it, both
passed ``gspio verify`` with exit 0, because the audit file's ``source_sha``
covers the model file alone and nothing read a table back from a file. The
audit file now names the local modules a model imports, each with the hash
of its bytes, and the file each table was read from; ``verify --model``
holds every module against the file beside the model, and ``verify
--assumptions`` reads each table's file as that table and compares the
fingerprint ``Table.fingerprint()`` gives it.

The model here is those builds' shape: a helper beside it, one table read with
``pl.read_parquet`` and handed over as a frame, one handed its file's path,
and one built from a frame written in the code.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio._beside import local_modules
from gaspatchio.assumptions import Table
from gaspatchio.cli import app
from gaspatchio.frame.graph import (
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    VerificationReport,
    verify_artifact,
)

if TYPE_CHECKING:
    from pathlib import Path

    from click.testing import Result

runner = CliRunner()

_MODEL = """\
from pathlib import Path

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

import helpers

HERE = Path(__file__).resolve().parent


def main(af: ActuarialFrame) -> ActuarialFrame:
    mortality = Table(
        name="verify_mortality",
        source=pl.read_parquet(HERE / "assumptions" / "verify_mortality.parquet"),
        dimensions={"age": "age"},
        value="qx",
    )
    lapse = Table(
        name="verify_lapse",
        source=HERE / "assumptions" / "lapse_rates.parquet",
        dimensions={"age": "age"},
        value="rate",
    )
    expense = Table(
        name="verify_expense",
        source=pl.DataFrame({"age": [30, 40], "cost": [10.0, 12.0]}),
        dimensions={"age": "age"},
        value="cost",
    )
    af.qx = mortality.lookup(age=af.age)
    af.lapse_rate = lapse.lookup(age=af.age)
    af.expense = expense.lookup(age=af.age)
    af.claims = af.sum_assured * af.qx * helpers.loading()
    return af
"""

_HELPER = "def loading() -> float:\n    return 1.10\n"


@dataclass(frozen=True)
class Room:
    """One model directory, exported, as a reviewer is handed it."""

    model: Path
    helper: Path
    tables: Path
    points: Path
    audit: Path

    @property
    def document(self) -> dict[str, Any]:
        """Return the audit file."""
        return json.loads(self.audit.read_text())

    def audit_document_module_path(self) -> str:
        """Return the path the audit file records for the helper module."""
        (module,) = self.document["model"]["modules"]
        return str(module["path"])


def _a_room_at(folder: Path) -> Room:
    """Write the model, its helper, its tables and its points, then export it."""
    tables = folder / "assumptions"
    tables.mkdir(parents=True)
    model = folder / "model.py"
    model.write_text(_MODEL)
    helper = folder / "helpers.py"
    helper.write_text(_HELPER)
    pl.DataFrame({"age": [30, 40], "qx": [0.001, 0.002]}).write_parquet(
        tables / "verify_mortality.parquet"
    )
    pl.DataFrame({"age": [30, 40], "rate": [0.05, 0.04]}).write_parquet(
        tables / "lapse_rates.parquet"
    )
    points = folder / "points.parquet"
    pl.DataFrame(
        {"policy_id": [1, 2], "age": [30, 40], "sum_assured": [1000.0, 2000.0]}
    ).write_parquet(points)
    audit = folder.parent / f"{folder.name}.audit.json"
    exported = runner.invoke(
        app, ["calc-graph", str(model), str(points), "-o", str(audit)]
    )
    assert exported.exit_code == 0, exported.output
    return Room(model, helper, tables, points, audit)


def _copied(room: Room, to: Path) -> Room:
    """Return a copy of the room's files beside the same audit file."""
    shutil.copytree(room.model.parent, to)
    return Room(
        to / "model.py",
        to / "helpers.py",
        to / "assumptions",
        to / "points.parquet",
        room.audit,
    )


def _by_against(report: VerificationReport) -> dict[str, str]:
    """Return each check's outcome, keyed by what it was held against."""
    return {check.against: check.outcome for check in report.checks}


def _said(report: VerificationReport, against: str) -> str:
    """Return what the check held against one member said."""
    return next(check.detail for check in report.checks if check.against == against)


def _verify(audit: Path, *options: str) -> Result:
    """Run ``gspio verify`` over one audit file."""
    return runner.invoke(app, ["verify", str(audit), *options])


_MORTALITY = "assumptions[name=verify_mortality].fingerprint"
_LAPSE = "assumptions[name=verify_lapse].fingerprint"
_EXPENSE = "assumptions[name=verify_expense].fingerprint"


# --- what the record carries ------------------------------------------------------


def test_the_record_names_each_local_module_the_model_imports(tmp_path: Path) -> None:
    room = _a_room_at(tmp_path / "room")

    modules = room.document["model"]["modules"]

    assert [module["path"] for module in modules] == ["helpers.py"]
    assert modules[0]["fingerprint"].startswith("sha256:")


def test_the_record_names_the_file_each_table_was_read_from(tmp_path: Path) -> None:
    """A path names its file; a frame names none, which is null; a join no member."""
    room = _a_room_at(tmp_path / "room")

    sources = {
        entry["name"]: (entry.get("source_file", "absent"), entry.get("shaped_by"))
        for entry in room.document["assumptions"]
    }

    assert sources == {
        "verify_expense": (None, []),
        "verify_lapse": ("assumptions/lapse_rates.parquet", []),
        "verify_mortality": (None, []),
    }


def test_a_frame_exported_with_no_model_file_carries_no_module_list() -> None:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100.0]}))
    af.claims = af.sum_assured * 0.001

    document = json.loads(GraphExporter(af).export())

    assert "modules" not in document["model"]


def test_an_extended_table_names_no_file(tmp_path: Path) -> None:
    """Its rows are no longer the file's, so the record does not vouch for one."""
    rates = tmp_path / "extended.parquet"
    pl.DataFrame({"age": [30], "qx": [0.001]}).write_parquet(rates)
    table = Table("verify_extended", rates, {"age": "age"}, "qx", storage_mode="hash")
    table.extend(pl.DataFrame({"age": [40], "qx": [0.002]}))
    af = ActuarialFrame(pl.DataFrame({"age": [30, 40]}))
    af.qx = table.lookup(age=af.age)

    (entry,) = json.loads(GraphExporter(af).export())["assumptions"]

    assert entry["source_file"] is None


def test_the_python_route_records_the_modules_the_command_line_does(
    tmp_path: Path,
) -> None:
    """The list is read off the source, so no process state can move it."""
    room = _a_room_at(tmp_path / "room")

    from_python = ModelIdentity.of(room.model)

    assert from_python.modules == room.document["model"]["modules"]


# --- which files are the model's own ---------------------------------------------


def test_local_modules_follow_helpers_and_packages_and_leave_installed_ones(
    tmp_path: Path,
) -> None:
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    (tmp_path / "model.py").write_text(
        "import json\nimport polars\nimport sys\n"
        "from gaspatchio import ActuarialFrame\n"
        "import helper\nimport pkg.sub.leaf\nfrom pkg import tool\n"
        "def main():\n    import late\n"
    )
    (tmp_path / "helper.py").write_text("import deep\n")
    (tmp_path / "deep.py").write_text("X = 1\n")
    (tmp_path / "late.py").write_text("Y = 2\n")
    (tmp_path / "unused.py").write_text("Z = 3\n")
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "tool.py").write_text("from . import sibling\n")
    (tmp_path / "pkg" / "sibling.py").write_text("")
    (tmp_path / "pkg" / "sub" / "leaf.py").write_text("from ..tool import *\n")

    found = local_modules(tmp_path / "model.py")

    assert [path.relative_to(tmp_path.resolve()).as_posix() for path in found] == [
        "deep.py",
        "helper.py",
        "late.py",
        "pkg/__init__.py",
        "pkg/sibling.py",
        "pkg/sub/leaf.py",
        "pkg/tool.py",
    ]


def test_a_local_file_shadowing_the_standard_library_is_the_model_s(
    tmp_path: Path,
) -> None:
    """Python puts the model's directory first, so the file beside it is the one run."""
    (tmp_path / "model.py").write_text("import statistics\nimport sys\n")
    (tmp_path / "statistics.py").write_text("")
    (tmp_path / "sys.py").write_text("")

    found = local_modules(tmp_path / "model.py")

    assert [path.name for path in found] == ["statistics.py"]


# --- verify --model over the helpers -----------------------------------------------


def test_an_untouched_helper_agrees(tmp_path: Path) -> None:
    room = _a_room_at(tmp_path / "room")

    report = verify_artifact(room.audit, model=room.model, model_points=room.points)

    assert _by_against(report)["model.modules"] == "agree"
    assert _by_against(report)["graph_fingerprint"] == "agree"
    assert report.verdict == "agree"


def test_an_edited_helper_disagrees_naming_it(tmp_path: Path) -> None:
    """gmdb-r3's extension_edited: the model file's bytes have not moved."""
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    room.helper.write_text(_HELPER.replace("1.10", "1.25"))

    report = verify_artifact(room.audit, model=room.model)

    assert _by_against(report)["model.source_sha"] == "agree"
    assert _by_against(report)["model.modules"] == "disagree"
    assert "helpers.py" in _said(report, "model.modules")
    assert report.verdict == "disagree"


def test_an_edited_helper_is_named_by_the_file_read_beside_the_path_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The digest is the file read, so the line names that file.

    It named the path the record holds beside the digest of the copy that was
    actually read -- ".../room/helpers.py is sha256:<the copy's>" -- which a
    reviewer holding two folders reads as the original having changed.
    """
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    room.helper.write_text(_HELPER.replace("1.10", "1.25"))
    monkeypatch.chdir(tmp_path)

    said = _said(verify_artifact(room.audit, model=room.model), "model.modules")

    recorded = room.audit_document_module_path()
    assert said.startswith(f"copy/helpers.py (recorded as {recorded}) is sha256:")


def test_a_helper_read_where_the_record_put_it_is_named_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    room = _a_room_at(tmp_path / "room")
    recorded = room.audit_document_module_path()
    monkeypatch.chdir(tmp_path)

    said = _said(verify_artifact(room.audit, model=room.model), "model.modules")

    assert said.startswith("room/helpers.py ")
    assert ("recorded as" in said) == (recorded != "room/helpers.py"), said


def test_a_helper_missing_beside_the_model_cannot_be_checked(tmp_path: Path) -> None:
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    room.helper.unlink()

    report = verify_artifact(room.audit, model=room.model)

    assert _by_against(report)["model.modules"] == "indeterminate"
    assert "helpers.py is not beside model.py" in _said(report, "model.modules")
    assert report.verdict == "indeterminate"


def test_a_record_without_a_module_list_cannot_vouch_for_helpers(
    tmp_path: Path,
) -> None:
    room = _a_room_at(tmp_path / "room")
    document = room.document
    del document["model"]["modules"]

    report = verify_artifact(document, model=room.model)

    assert _by_against(report)["model.modules"] == "indeterminate"


# --- verify --assumptions -----------------------------------------------------------


def test_every_untouched_table_agrees_and_the_coded_one_is_not_asked(
    tmp_path: Path,
) -> None:
    room = _a_room_at(tmp_path / "room")

    report = verify_artifact(room.audit, assumptions=[room.tables])

    assert {
        against: outcome
        for against, outcome in _by_against(report).items()
        if against.startswith("assumptions[")
    } == {_EXPENSE: "not_asked", _LAPSE: "agree", _MORTALITY: "agree"}
    assert "handed it a frame rather than a file's path" in _said(report, _EXPENSE)
    assert report.verdict == "agree"


def test_an_edited_table_read_from_its_path_disagrees_naming_both_fingerprints(
    tmp_path: Path,
) -> None:
    """One rate moves in a file the record names the table a plain read of."""
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    recorded = next(
        entry["fingerprint"]
        for entry in room.document["assumptions"]
        if entry["name"] == "verify_lapse"
    )
    pl.DataFrame({"age": [30, 40], "rate": [0.05, 0.045]}).write_parquet(
        room.tables / "lapse_rates.parquet"
    )

    report = verify_artifact(room.audit, assumptions=[room.tables])

    assert _by_against(report)[_LAPSE] == "disagree"
    assert _by_against(report)[_MORTALITY] == "agree"
    assert recorded in _said(report, _LAPSE)
    assert report.verdict == "disagree"


def test_an_edited_file_behind_a_frame_built_table_leaves_the_question_open(
    tmp_path: Path,
) -> None:
    """ul-r7's and gmdb-r3's tamper case: the model read the file into a frame.

    Nothing records what the frame was, so the edit fails verify -- the
    question is open -- and is not called a disagreement it cannot prove.
    """
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    pl.DataFrame({"age": [30, 40], "qx": [0.001, 0.0025]}).write_parquet(
        room.tables / "verify_mortality.parquet"
    )

    report = verify_artifact(room.audit, assumptions=[room.tables])

    assert _by_against(report)[_MORTALITY] == "indeterminate"
    assert "handed this table a frame" in _said(report, _MORTALITY)
    assert "Hand Table the file's path" in _said(report, _MORTALITY)
    assert report.verdict == "indeterminate"


def test_a_table_rewritten_in_another_layout_and_format_still_agrees(
    tmp_path: Path,
) -> None:
    """Table.fingerprint() semantics: the values, not the file's bytes or order."""
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    rates = pl.read_parquet(room.tables / "lapse_rates.parquet")
    (room.tables / "lapse_rates.parquet").unlink()
    rates.select("rate", "age").reverse().write_csv(room.tables / "lapse.csv")

    report = verify_artifact(
        room.audit, assumptions=[f"verify_lapse={room.tables / 'lapse.csv'}"]
    )

    assert _by_against(report)[_LAPSE] == "agree"


def test_a_table_read_from_a_file_that_is_not_found_cannot_be_checked(
    tmp_path: Path,
) -> None:
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    (room.tables / "lapse_rates.parquet").unlink()

    report = verify_artifact(room.audit, assumptions=[room.tables])

    assert _by_against(report)[_LAPSE] == "indeterminate"
    assert "was not found" in _said(report, _LAPSE)
    assert report.verdict == "indeterminate"


def test_a_file_that_does_not_hold_the_table_s_columns_cannot_be_read_as_it(
    tmp_path: Path,
) -> None:
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    pl.DataFrame({"attained_age": [30, 40], "qx": [0.001, 0.002]}).write_parquet(
        room.tables / "verify_mortality.parquet"
    )

    report = verify_artifact(room.audit, assumptions=[room.tables])

    assert _by_against(report)[_MORTALITY] == "indeterminate"
    assert "does not hold age" in _said(report, _MORTALITY)


def test_a_table_whose_values_and_roles_the_record_left_out_cannot_be_read(
    tmp_path: Path,
) -> None:
    room = _a_room_at(tmp_path / "room")
    document = room.document
    for entry in document["assumptions"]:
        entry["payload"] = {"omitted": "size", "bytes": 10}

    report = verify_artifact(document, assumptions=[room.tables])

    assert _by_against(report)[_MORTALITY] == "indeterminate"
    assert "payload omitted for size" in _said(report, _MORTALITY)


def test_a_table_too_large_to_inline_is_still_checked_against_its_file(
    tmp_path: Path,
) -> None:
    """Over the 1 MiB inline budget the values stay out and the roles travel."""
    rates = tmp_path / "large_select.parquet"
    ages, durations = range(18, 121), range(1, 301)
    pl.DataFrame(
        {
            "age": [age for age in ages for _ in durations],
            "duration": [duration for _ in ages for duration in durations],
            "qx": [
                round(0.0001 * age + 0.00001 * duration, 8)
                for age in ages
                for duration in durations
            ],
        }
    ).write_parquet(rates)
    table = Table(
        "verify_large_select", rates, {"age": "age", "duration": "duration"}, "qx"
    )
    af = ActuarialFrame(pl.DataFrame({"age": [30], "duration": [5]}))
    af.qx = table.lookup(age=af.age, duration=af.duration)
    document = json.loads(GraphExporter(af).export())
    (entry,) = document["assumptions"]

    untouched = verify_artifact(document, assumptions=[rates])
    pl.read_parquet(rates).with_columns(qx=pl.col("qx") * 1.01).write_parquet(rates)
    edited = verify_artifact(document, assumptions=[rates])

    assert entry["payload"]["omitted"] == "size"
    assert entry["payload"]["bytes"] > 1_048_576
    assert entry["payload"]["roles"]["value"] == "qx"
    assert [column["name"] for column in entry["payload"]["roles"]["columns"]] == [
        "age",
        "duration",
        "qx",
    ]
    assert untouched.verdict == "agree"
    assert edited.verdict == "disagree"


def test_a_renamed_table_is_never_read_back_from_its_file(tmp_path: Path) -> None:
    """The recipe renamed a column, so the file is not the table -- named or found."""
    rates = tmp_path / "verify_renamed.parquet"
    pl.DataFrame({"Age": [30, 40], "qx": [0.001, 0.002]}).write_parquet(rates)
    table = Table("verify_renamed", rates, {"age": "Age"}, "qx")
    af = ActuarialFrame(pl.DataFrame({"age": [30, 40]}))
    af.qx = table.lookup(age=af.age)
    document = json.loads(GraphExporter(af).export())
    pl.DataFrame({"Age": [30, 40], "qx": [0.001, 0.0025]}).write_parquet(rates)
    against = "assumptions[name=verify_renamed].fingerprint"

    found = verify_artifact(document, assumptions=[tmp_path])
    named = verify_artifact(document, assumptions=[f"verify_renamed={rates}"])

    assert document["assumptions"][0]["shaped_by"] == [
        {"step": "renamed", "column": "age", "from": "Age"}
    ]
    for report in (found, named):
        assert _by_against(report)[against] == "indeterminate"
        assert "age renamed from Age" in _said(report, against)
        assert "would not help" in _said(report, against)


def test_a_filtered_table_never_reads_as_an_edit_of_its_file(tmp_path: Path) -> None:
    """Rows dropped in code before Table: not the file, and not an edit of it."""
    rates = tmp_path / "verify_filtered.parquet"
    pl.DataFrame({"age": [30, 40, 50], "qx": [0.001, 0.002, 0.004]}).write_parquet(
        rates
    )
    table = Table(
        "verify_filtered",
        pl.read_parquet(rates).filter(pl.col("age") < 50),
        {"age": "age"},
        "qx",
    )
    af = ActuarialFrame(pl.DataFrame({"age": [30, 40]}))
    af.qx = table.lookup(age=af.age)
    document = json.loads(GraphExporter(af).export())
    against = "assumptions[name=verify_filtered].fingerprint"

    for given in ([tmp_path], [f"verify_filtered={rates}"]):
        report = verify_artifact(document, assumptions=given)
        assert _by_against(report)[against] == "indeterminate"
        assert "rows filtered" in _said(report, against)


def test_a_file_given_that_names_no_recorded_table_is_said(tmp_path: Path) -> None:
    room = _a_room_at(tmp_path / "room")
    stray = tmp_path / "stray.parquet"
    pl.DataFrame({"age": [30], "qx": [0.5]}).write_parquet(stray)

    report = verify_artifact(room.audit, assumptions=[stray])

    assert ("assumptions", "indeterminate") in {
        (check.against, check.outcome) for check in report.checks
    }


def test_name_equals_file_for_a_table_not_recorded_is_refused(tmp_path: Path) -> None:
    room = _a_room_at(tmp_path / "room")

    with pytest.raises(ValueError, match="names no table the audit file records"):
        verify_artifact(
            room.audit,
            assumptions=[f"no_such_table={room.tables / 'lapse_rates.parquet'}"],
        )


def test_a_path_that_names_nothing_is_refused(tmp_path: Path) -> None:
    room = _a_room_at(tmp_path / "room")

    with pytest.raises(OSError, match="names no file or directory"):
        verify_artifact(room.audit, assumptions=[tmp_path / "nowhere"])


def test_a_record_reading_no_table_has_nothing_to_hold_files_against(
    tmp_path: Path,
) -> None:
    """Nothing recorded is nothing to check, so the documented command passes.

    ``--assumptions <dir>`` over a model that reads no table was ``indeterminate``,
    exit 4, so the one-line command could never pass on such a model.
    """
    model = tmp_path / "model.py"
    model.write_text("RATE = 0.001\n")
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100.0]}))
    af.claims = af.sum_assured * 0.001
    config = GraphExportConfig(model=ModelIdentity.of(model))
    document = json.loads(GraphExporter(af).export(config=config))

    report = verify_artifact(document, assumptions=[tmp_path])

    assert _by_against(report)["assumptions"] == "agree"
    assert report.verdict == "agree"


def test_a_file_named_beside_a_record_reading_no_table_is_not_checked(
    tmp_path: Path,
) -> None:
    """A file named outright still has its own line: it was asked to be checked."""
    model = tmp_path / "model.py"
    model.write_text("RATE = 0.001\n")
    rates = tmp_path / "rates.parquet"
    pl.DataFrame({"age": [30], "qx": [0.001]}).write_parquet(rates)
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100.0]}))
    af.claims = af.sum_assured * 0.001
    config = GraphExportConfig(model=ModelIdentity.of(model))
    document = json.loads(GraphExporter(af).export(config=config))

    report = verify_artifact(document, assumptions=[rates])

    lines = [check for check in report.checks if check.name == "assumptions"]
    assert [line.outcome for line in lines] == ["agree", "indeterminate"]
    assert "rates.parquet was given" in lines[1].detail
    assert report.verdict == "indeterminate"


# --- the command line, end to end ---------------------------------------------------


def test_the_untouched_room_exits_zero(tmp_path: Path) -> None:
    room = _a_room_at(tmp_path / "room")

    result = _verify(
        room.audit,
        "--model",
        str(room.model),
        "--model-points",
        str(room.points),
        "--assumptions",
        str(room.tables),
    )

    assert result.exit_code == 0, result.output


def test_an_edited_table_read_from_its_path_exits_one(tmp_path: Path) -> None:
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    pl.DataFrame({"age": [30, 40], "rate": [0.05, 0.045]}).write_parquet(
        room.tables / "lapse_rates.parquet"
    )

    result = _verify(
        room.audit, "--model", str(room.model), "--assumptions", str(room.tables)
    )

    assert result.exit_code == 1, result.output


def test_an_edited_file_behind_a_frame_built_table_exits_four(tmp_path: Path) -> None:
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    pl.DataFrame({"age": [30, 40], "qx": [0.001, 0.0025]}).write_parquet(
        room.tables / "verify_mortality.parquet"
    )

    result = _verify(
        room.audit, "--model", str(room.model), "--assumptions", str(room.tables)
    )

    assert result.exit_code == 4, result.output


def test_an_edited_helper_exits_one(tmp_path: Path) -> None:
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    room.helper.write_text(_HELPER.replace("1.10", "1.25"))

    result = _verify(room.audit, "--model", str(room.model), "--json")

    assert result.exit_code == 1, result.output
    stored = json.loads(result.stdout)
    modules = next(c for c in stored["checks"] if c["name"] == "modules")
    assert modules["outcome"] == "disagree"
    assert "helpers.py" in modules["detail"]


def test_a_missing_table_file_exits_four(tmp_path: Path) -> None:
    room = _copied(_a_room_at(tmp_path / "room"), tmp_path / "copy")
    (room.tables / "lapse_rates.parquet").unlink()

    result = _verify(room.audit, "--assumptions", str(room.tables))

    assert result.exit_code == 4, result.output


def test_files_and_named_files_can_be_given_together(tmp_path: Path) -> None:
    room = _a_room_at(tmp_path / "room")

    result = _verify(
        room.audit,
        "--assumptions",
        str(room.tables / "verify_mortality.parquet"),
        "--assumptions",
        f"verify_lapse={room.tables / 'lapse_rates.parquet'}",
        "--json",
    )

    assert result.exit_code == 0, result.output
    stored = json.loads(result.stdout)
    assert {
        c["against"]: c["outcome"]
        for c in stored["checks"]
        if c["name"] == "assumptions"
    } == {_EXPENSE: "not_asked", _LAPSE: "agree", _MORTALITY: "agree"}


def test_an_assumption_path_that_names_nothing_exits_two(tmp_path: Path) -> None:
    room = _a_room_at(tmp_path / "room")

    result = _verify(room.audit, "--assumptions", str(tmp_path / "nowhere"))

    assert result.exit_code == 2, result.output


# --- a joined file and a helper loaded by its path (W5 A-F3) -----------------------

_JOINING_MODEL = """\
import importlib.util
from pathlib import Path

import polars as pl

from gaspatchio import ActuarialFrame

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("by_path", HERE / "by_path.py")
by_path = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(by_path)


def main(af: ActuarialFrame) -> ActuarialFrame:
    products = pl.read_parquet(HERE / "assumptions" / "products.parquet")
    af = af.join(products, on="product", how="left")
    af.premium = by_path.loaded(af.sum_assured * af.prem_rate)
    return af
"""

_BY_PATH = "def loaded(x):\n    return x * 1.00\n"


def _a_joining_room_at(folder: Path) -> tuple[Path, Path, Path]:
    """Write a model that joins a file and loads a helper by path; export it."""
    tables = folder / "assumptions"
    tables.mkdir(parents=True)
    model = folder / "model.py"
    model.write_text(_JOINING_MODEL)
    (folder / "by_path.py").write_text(_BY_PATH)
    pl.DataFrame({"product": ["T5", "T10"], "prem_rate": [0.003, 0.002]}).write_parquet(
        tables / "products.parquet"
    )
    points = folder / "points.parquet"
    pl.DataFrame(
        {"policy_id": [1, 2], "product": ["T5", "T10"], "sum_assured": [1e3, 2e3]}
    ).write_parquet(points)
    audit = folder.parent / f"{folder.name}.audit.json"
    exported = runner.invoke(
        app, ["calc-graph", str(model), str(points), "-o", str(audit)]
    )
    assert exported.exit_code == 0, exported.output
    return model, tables, audit


def _join_line(report: VerificationReport) -> tuple[str, str]:
    (check,) = [
        c for c in report.checks if c.against.startswith("assumptions[name=join:")
    ]
    return check.outcome, check.detail


def test_an_untouched_joined_file_agrees_by_its_content(tmp_path: Path) -> None:
    _, tables, audit = _a_joining_room_at(tmp_path / "room")

    report = verify_artifact(audit, assumptions=[tables])

    outcome, said = _join_line(report)
    assert outcome == "agree"
    assert "products.parquet, found by its content" in said


def test_an_edited_joined_file_is_never_reported_as_agreeing(tmp_path: Path) -> None:
    """The review's case: every rate doubled, and verify said ✓ assumptions agrees."""
    _, tables, audit = _a_joining_room_at(tmp_path / "room")
    pl.DataFrame({"product": ["T5", "T10"], "prem_rate": [0.006, 0.004]}).write_parquet(
        tables / "products.parquet"
    )

    report = verify_artifact(audit, assumptions=[tables])
    outcome, said = _join_line(report)
    result = _verify(audit, "--assumptions", str(tables))

    assert outcome == "indeterminate"
    assert "could not be checked" in said
    assert result.exit_code == 4, result.output


def test_name_equals_file_names_a_join_by_its_recorded_name(tmp_path: Path) -> None:
    _, tables, audit = _a_joining_room_at(tmp_path / "room")
    (entry,) = [
        a for a in json.loads(audit.read_text())["assumptions"] if a["kind"] == "join"
    ]

    report = verify_artifact(
        audit, assumptions=[f"{entry['name']}={tables / 'products.parquet'}"]
    )

    outcome, said = _join_line(report)
    assert outcome == "agree"
    assert f"named for it as {entry['name']}=FILE" in said


def test_a_helper_loaded_by_its_path_leaves_the_modules_line_open(
    tmp_path: Path,
) -> None:
    """The record lists what import statements reach, so it cannot hold this helper."""
    model, _, audit = _a_joining_room_at(tmp_path / "room")
    (model.parent / "by_path.py").write_text(_BY_PATH.replace("1.00", "1.25"))

    report = verify_artifact(audit, model=model)

    assert _by_against(report)["model.modules"] == "indeterminate"
    said = _said(report, "model.modules")
    assert "model.py:9 spec_from_file_location" in said
    assert "nothing beside" not in said
