# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tier 2: Execute the factual claims of the workbook-conversion skill.

The skill is a document of claims: the fastexcel/calamine reader mangles
float precision behind a String-dtype inference, the API surface the prose
names exists, the sibling skills and files it routes to are where it says.
These tests execute those claims so the skill cannot silently drift from
reality. When one goes red the fix is to update the skill — that is the
point, not a nuisance: a future fastexcel release that repairs the
truncation makes the HARD GATE section fiction, and this suite is the only
thing that would tell us.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import fastexcel
import pytest
import xlsxwriter

REPO_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SKILL_MD = SKILLS_DIR / "gaspatchio-workbook-conversion" / "SKILL.md"

# Probe values from the skill's own HARD GATE table. The table's third probe
# (2238.2200000000003) needs 17 significant digits and dies in xlsxwriter's
# %.16g serialisation before the reader ever sees it — using it here would
# attribute the loss to the wrong tool. These two round-trip the write
# exactly, so any loss measured below belongs to the reader alone.
PROBES = [0.970873786407767, 497761.77773510211]


@pytest.fixture(scope="module")
def probe_workbook(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a workbook with a text title row above a float data block."""
    path = tmp_path_factory.mktemp("claims") / "probe.xlsx"
    workbook = xlsxwriter.Workbook(str(path))
    sheet = workbook.add_worksheet("Sheet1")
    sheet.write_row(0, 0, ["Projection of Account Values"])
    sheet.write_row(1, 0, ["t", "v", "av"])
    sheet.write_row(2, 0, [1, *PROBES])
    sheet.write_row(3, 0, [2, *[p * 1.01 for p in PROBES]])
    workbook.close()
    return path


def test_probe_values_survive_the_write() -> None:
    """Fixture self-check: every probe round-trips xlsxwriter's %.16g.

    Guards future probe edits from reintroducing the 17-digit trap, which
    would make the truncation tests blame the reader for the writer's loss.
    """
    for probe in PROBES:
        assert float(f"{probe:.16g}") == probe


def test_string_inferred_read_truncates_floats(probe_workbook: Path) -> None:
    """The skill's HARD GATE premise holds.

    A text header row above the data block makes the columns infer String,
    and the stringified values lose precision.
    """
    frame = fastexcel.read_excel(str(probe_workbook)).load_sheet(0).to_polars()

    value_dtypes = frame.dtypes[1:]
    assert all(str(dtype) == "String" for dtype in value_dtypes), (
        "The text-header read no longer infers String — the skill's HARD "
        f"GATE premise has changed (got {value_dtypes})"
    )
    # Row 0 is the column-header row swallowed as data; row 1 is the first
    # data row. Parsing the strings back must NOT recover the true doubles.
    read_back = [float(value) for value in frame.row(1)[1:]]
    for got, want in zip(read_back, PROBES, strict=True):
        assert got != want, (
            f"String-path read preserved {want!r} exactly — fastexcel may "
            "have fixed the truncation; re-verify and update the skill's "
            "HARD GATE section"
        )


def test_header_skipped_read_is_lossless(probe_workbook: Path) -> None:
    """The skill's remedy holds.

    Skip the text row and the block reads Float64 bit-exact — this is what
    makes the reader provable against the XML.
    """
    frame = (
        fastexcel.read_excel(str(probe_workbook))
        .load_sheet(0, header_row=1)
        .to_polars()
    )

    value_dtypes = frame.dtypes[1:]
    assert all(str(dtype) == "Float64" for dtype in value_dtypes), (
        f"Header-skipped read no longer infers Float64 (got {value_dtypes})"
    )
    read_back = list(frame.row(0)[1:])
    for got, want in zip(read_back, PROBES, strict=True):
        assert got == want, f"Float64 path lost precision: {got!r} != {want!r}"


def test_named_sibling_skills_exist() -> None:
    """Every gaspatchio-* skill the prose routes to is a real skill dir."""
    content = SKILL_MD.read_text()
    named = {
        match.rstrip("-") for match in re.findall(r"gaspatchio-[a-z][a-z-]*", content)
    }
    assert named, "The skill no longer names any sibling skills"
    for skill_name in sorted(named):
        assert (SKILLS_DIR / skill_name / "SKILL.md").exists(), (
            f"SKILL.md routes to '{skill_name}' but skills/{skill_name}/ does not exist"
        )


def test_discovery_reference_file_exists() -> None:
    """The discovery reference the skill routes to exists.

    The skill sends readers to discovery's spreadsheet-conversion reference
    first; that file must exist where the prose points.
    """
    assert "references/spreadsheet-conversion.md" in SKILL_MD.read_text()
    reference = (
        SKILLS_DIR
        / "gaspatchio-model-discovery"
        / "references"
        / "spreadsheet-conversion.md"
    )
    assert reference.exists(), f"Referenced file missing: {reference}"


def test_named_api_surface_exists() -> None:
    """Every API surface the prose names exists on the shipped package.

    The prose names round_charge=, .clip(), and .round(); pin each so the
    skill cannot outlive a rename.
    """
    from gaspatchio.column.column_proxy import ColumnProxy
    from gaspatchio.rollforward._builder import _StateHandle

    for op_name in ("charge", "grow", "deduct_nar"):
        signature = inspect.signature(getattr(_StateHandle, op_name))
        assert "round_charge" in signature.parameters, (
            f"Skill prose promises round_charge= on ops, but "
            f"_StateHandle.{op_name} does not accept it"
        )
    assert hasattr(ColumnProxy, "clip"), (
        "Skill prose promises .clip() on the lookup key"
    )
    assert callable(getattr(_StateHandle, "round", None)), (
        "Skill prose promises .round() on the rollforward state"
    )
