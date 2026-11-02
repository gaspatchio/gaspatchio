# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A record laid out as a workbook holds the record's own doubles, digit for digit.

``render_xlsx`` writes its own OOXML because the Python spreadsheet writers
keep sixteen significant digits, and a sheet claiming to show the record's
numbers would quietly undo the full precision the record carries. So the
claim held here is exact: every numeric cell's text is ``repr`` of the double
the record holds and parses back to that double bit for bit, ``-0.0``
included; a NaN or an infinity, which a spreadsheet number cannot hold, is
the record's own word for it as text; a whole number past 2^53, which Excel
would round, is its digits as text. Read three ways -- the raw XML, openpyxl
and fastexcel, which is calamine -- and held against the record and against
the results file the run wrote.

Beside exactness: the bytes are a function of the record (a committed golden,
``goldens/one_policy_sheet.json`` laid out to ``goldens/one_policy_sheet.xlsx``),
the package is OOXML a reader opens (a schema-light check of every part), no
cell holds a formula, and the layout follows the record's policy axis.

To regenerate the golden after a deliberate change to the layout::

    from tests.graph.test_xlsx_export import _GOLDEN_RECORD, _GOLDEN_SHEET
    from gaspatchio.frame.graph import render_xlsx

    _GOLDEN_SHEET.write_bytes(render_xlsx(_GOLDEN_RECORD))

The record itself was written by :func:`_tricky_record` with ``created_at``
pinned and the document sealed again; it is committed so that the golden
holds the writer alone, whatever the exporter does next.
"""

from __future__ import annotations

import datetime
import io
import json
import math
import re
import struct
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import (
    GraphExportConfig,
    GraphExporter,
    document_digest_of,
    render_xlsx,
    xlsx_export,
)

_GOLDENS = Path(__file__).resolve().parent / "goldens"
_GOLDEN_RECORD = _GOLDENS / "one_policy_sheet.json"
_GOLDEN_SHEET = _GOLDENS / "one_policy_sheet.xlsx"
_PINNED_AT = "2026-10-20T00:00:00Z"

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_TYPES = "{http://schemas.openxmlformats.org/package/2006/content-types}"

# Doubles that a sixteen-digit writer gets wrong, or that sit at an edge of
# the type: 0.1 + 0.2, a third, the smallest subnormal, the largest double,
# a negative zero, and the non-finite three.
_RATES = [0.1, 0.2, 0.1 + 0.2, math.nan, math.inf, -0.0, 1 / 3]
_TEXT = '=SUM(A1) <&> "quoted" _x0041_ \r\n\x01 tab\there '


def _tricky_record() -> dict[str, Any]:
    """Return the record of a one-policy model holding every awkward value."""
    book = pl.DataFrame(
        {
            "policy_id": ["P-1"],
            "sum_assured": [100_000.0],
            "ratio": [0.1 + 0.2],
            "tiny": [5e-324],
            "huge": [1.7976931348623157e308],
            "neg_zero": [-0.0],
            "missing": [math.nan],
            "unbounded": [-math.inf],
            "count": [2**53 + 1],
            "small_count": [-42],
            "label": [_TEXT],
            "issued": [datetime.date(2025, 1, 1)],
            "active": [True],
            "rate": [_RATES],
        }
    )
    af = ActuarialFrame(book)
    af.claims = af.sum_assured * af.ratio
    af.third = af.sum_assured / 3.0
    af.scaled = af.rate * 1.0
    af.prior = af.rate.projection.previous_period()
    af.running = af.rate.cum_sum()
    config = GraphExportConfig(policy_id_column="policy_id")
    record = GraphExporter(af).export(af.collect(), config, versions="withheld")
    return json.loads(record)


def _pinned(document: dict[str, Any], created_at: str = _PINNED_AT) -> dict[str, Any]:
    """Return the record written at ``created_at``, sealed again over that date."""
    pinned = {key: value for key, value in document.items() if key != "document_digest"}
    pinned["created_at"] = created_at
    pinned["document_digest"] = document_digest_of(pinned)
    return pinned


# --- reading a workbook back, with nothing but the standard library ----------


def _parts(workbook: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _sheet_files(parts: dict[str, bytes]) -> dict[str, str]:
    """Return each sheet's name and the part holding it, in workbook order."""
    book = ET.fromstring(parts["xl/workbook.xml"])  # noqa: S314 -- our own bytes
    rels = ET.fromstring(parts["xl/_rels/workbook.xml.rels"])  # noqa: S314
    target = {rel.get("Id"): rel.get("Target") for rel in rels}
    return {
        sheet.get("name"): f"xl/{target[sheet.get(f'{_DOC_REL}id')]}"
        for sheet in book.iter(f"{_MAIN}sheet")
    }


def _decoded(text: str) -> str:
    """Return OOXML text with its ``_xHHHH_`` escapes undone."""
    return re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), text)


def _grid(workbook: bytes, sheet: str) -> dict[tuple[int, int], tuple[str, str]]:
    """Return each cell of one sheet as ``(row, column) -> (type, text)``.

    The type is ``n`` for a number, ``b`` for a Boolean and ``s`` for text;
    the text is the cell's own characters, as the file holds them.
    """
    parts = _parts(workbook)
    root = ET.fromstring(parts[_sheet_files(parts)[sheet]])  # noqa: S314
    grid: dict[tuple[int, int], tuple[str, str]] = {}
    for cell in root.iter(f"{_MAIN}c"):
        found = re.fullmatch(r"([A-Z]+)(\d+)", cell.get("r", ""))
        assert found is not None
        column = 0
        for letter in found.group(1):
            column = column * 26 + ord(letter) - 64
        kind = cell.get("t", "n")
        if kind == "inlineStr":
            text = "".join(cell.find(f"{_MAIN}is").itertext())  # type: ignore[union-attr]
            grid[int(found.group(2)) - 1, column - 1] = ("s", _decoded(text))
        else:
            grid[int(found.group(2)) - 1, column - 1] = (
                kind,
                cell.find(f"{_MAIN}v").text or "",  # type: ignore[union-attr]
            )
    return grid


def _bits(value: float) -> bytes:
    return struct.pack("<d", value)


def _assert_holds(cell: tuple[str, str] | None, recorded: object, where: str) -> None:
    """Assert one cell holds exactly what the record holds at that place."""
    if recorded is None:
        assert cell is None, f"{where}: a null is a blank cell, found {cell}"
        return
    assert cell is not None, f"{where}: the record holds {recorded!r}, the cell none"
    kind, text = cell
    if isinstance(recorded, bool):
        assert (kind, text) == ("b", str(int(recorded))), where
    elif isinstance(recorded, int) and abs(recorded) > 2**53:
        assert (kind, text) == ("s", str(recorded)), where
    elif isinstance(recorded, int | float):
        assert kind == "n", where
        written = repr(recorded) if isinstance(recorded, float) else str(recorded)
        assert text == written, f"{where}: {text} is not {written}"
        assert _bits(float(text)) == _bits(float(recorded)), f"{where}: {text}"
    else:
        assert kind == "s", where
        assert text == recorded, where


def _nodes(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in document["nodes"]}


# --- exactness -------------------------------------------------------------------


def test_every_timeline_cell_is_the_records_double_bit_for_bit() -> None:
    document = _tricky_record()
    grid = _grid(render_xlsx(document), "Timeline")
    nodes = _nodes(document)

    headers = {column: text for (row, column), (_, text) in grid.items() if row == 0}
    assert headers[0] == "period"
    per_period = [node for node in document["nodes"] if node["shape"] == "list"]
    assert [headers[at] for at in range(1, len(headers))] == [
        node["id"] for node in per_period
    ]
    checked = 0
    for column, node_id in headers.items():
        if column == 0:
            continue
        node = nodes[node_id]
        assert grid.get((1, column), ("s", ""))[1] == (node["formula"] or "")
        for period, recorded in enumerate(node["value_sample"]):
            _assert_holds(
                grid.get((3 + period, column)), recorded, f"{node_id}[{period}]"
            )
            checked += 1
    assert checked == 4 * len(_RATES)  # rate, scaled, prior, running


def test_every_scalar_cell_is_the_records_value_bit_for_bit() -> None:
    document = _tricky_record()
    grid = _grid(render_xlsx(document), "Scalars")
    rows = {text: row for (row, column), (_, text) in grid.items() if column == 0}
    for node in document["nodes"]:
        if node["shape"] == "list":
            assert node["id"] not in rows
            continue
        _assert_holds(grid.get((rows[node["id"]], 4)), node["value_sample"], node["id"])


@pytest.mark.parametrize(
    ("node_id", "expected"),
    [
        ("ratio", ("n", "0.30000000000000004")),
        ("tiny", ("n", "5e-324")),
        ("huge", ("n", "1.7976931348623157e+308")),
        ("neg_zero", ("n", "-0.0")),
        ("missing", ("s", "NaN")),
        ("unbounded", ("s", "-Infinity")),
        ("count", ("s", "9007199254740993")),
        ("small_count", ("n", "-42")),
        ("label", ("s", _TEXT)),
        ("issued", ("s", "2025-01-01")),
        ("active", ("b", "1")),
        ("third@1", ("n", "33333.333333333336")),
    ],
)
def test_awkward_values_are_written_as_the_record_writes_them(
    node_id: str, expected: tuple[str, str]
) -> None:
    grid = _grid(render_xlsx(_tricky_record()), "Scalars")
    rows = {text: row for (row, column), (_, text) in grid.items() if column == 0}
    assert grid[rows[node_id], 4] == expected


def test_a_negative_zero_keeps_its_sign() -> None:
    grid = _grid(render_xlsx(_tricky_record()), "Scalars")
    rows = {text: row for (row, column), (_, text) in grid.items() if column == 0}
    assert math.copysign(1.0, float(grid[rows["neg_zero"], 4][1])) == -1.0


def test_openpyxl_reads_back_the_records_doubles() -> None:
    openpyxl = pytest.importorskip("openpyxl")
    document = _tricky_record()
    sheet = openpyxl.load_workbook(io.BytesIO(render_xlsx(document)))["Timeline"]
    nodes = _nodes(document)
    header = [cell.value for cell in sheet[1]]
    for at, node_id in enumerate(header[1:], start=2):
        column = [row[at - 1] for row in sheet.iter_rows(min_row=4, values_only=True)]
        for read, recorded in zip(column, nodes[node_id]["value_sample"], strict=True):
            if isinstance(recorded, str):
                assert read == recorded
            else:
                assert _bits(read) == _bits(recorded), (node_id, read, recorded)


def test_fastexcel_reads_back_the_results_files_own_doubles(tmp_path: Path) -> None:
    """The design's own test: the workbook against the results Parquet, bit for bit."""
    fastexcel = pytest.importorskip("fastexcel")
    book = pl.DataFrame(
        {
            "policy_id": ["A", "B"],
            "sum_assured": [100_000.0, 250_000.0],
            "q": [[0.001, 0.0012, 0.0015, 0.0019], [0.002, 0.0023, 0.0027, 0.0031]],
        }
    )
    af = ActuarialFrame(book)
    af.survival = (1.0 - af.q).cum_prod()
    af.claims = af.sum_assured * af.q * af.survival / 3.0
    results = af.collect()
    results.write_parquet(tmp_path / "results.parquet")
    record = GraphExporter(af).export(
        results, GraphExportConfig(policy_id="B", policy_id_column="policy_id")
    )
    (tmp_path / "policy.xlsx").write_bytes(render_xlsx(record))

    read = (
        fastexcel.read_excel(tmp_path / "policy.xlsx")
        .load_sheet("Timeline", header_row=0, skip_rows=2)
        .to_polars()
    )
    row = pl.read_parquet(tmp_path / "results.parquet").row(1, named=True)
    for column in ("q", "survival", "claims"):
        (header,) = [name for name in read.columns if name.split("@")[0] == column]
        assert [_bits(value) for value in read[header].to_list()] == [
            _bits(value) for value in row[column]
        ], column


def test_a_value_sixteen_digits_cannot_hold_is_written_with_seventeen() -> None:
    """The finding the writer exists for: ``.16g`` reads back as another double."""
    grid = _grid(render_xlsx(_tricky_record()), "Scalars")
    rows = {text: row for (row, column), (_, text) in grid.items() if column == 0}
    text = grid[rows["ratio"], 4][1]
    assert float(f"{float(text):.16g}") != float(text)
    assert float(text) == 0.1 + 0.2


# --- determinism -----------------------------------------------------------------


def test_one_record_lays_out_to_one_file() -> None:
    document = _pinned(_tricky_record())
    assert render_xlsx(document) == render_xlsx(json.dumps(document))


def test_the_created_date_is_the_records_and_moves_only_its_own_part() -> None:
    document = _tricky_record()
    earlier = _parts(render_xlsx(_pinned(document, "2026-01-01T00:00:00Z")))
    later = _parts(render_xlsx(_pinned(document, "2027-01-01T00:00:00Z")))
    assert b"2027-01-01T00:00:00Z" in later["docProps/core.xml"]
    moved = {name for name in earlier if earlier[name] != later[name]}
    # The README quotes created_at and the digest; the properties carry the date.
    assert moved == {"docProps/core.xml", "xl/worksheets/sheet1.xml"}


def test_the_golden_record_lays_out_to_the_golden_bytes() -> None:
    assert render_xlsx(_GOLDEN_RECORD) == _GOLDEN_SHEET.read_bytes(), (
        "The workbook layout moved. If that was meant, regenerate the golden as "
        "this module's docstring says, and open it in Excel before committing."
    )


def test_the_archive_states_no_machine() -> None:
    with zipfile.ZipFile(io.BytesIO(render_xlsx(_GOLDEN_RECORD))) as archive:
        for member in archive.infolist():
            assert member.date_time == (1980, 1, 1, 0, 0, 0)
            assert member.create_system == 0
            assert member.compress_type == zipfile.ZIP_STORED


# --- the package is OOXML ------------------------------------------------------


def test_the_package_is_ooxml_a_reader_opens() -> None:
    workbook = render_xlsx(_pinned(_tricky_record()))
    parts = _parts(workbook)
    for name, data in parts.items():
        ET.fromstring(data)  # noqa: S314 -- every part is well-formed XML
        assert data.startswith(b'<?xml version="1.0" encoding="UTF-8"'), name

    types = ET.fromstring(parts["[Content_Types].xml"])  # noqa: S314
    overridden = {item.get("PartName") for item in types.iter(f"{_TYPES}Override")}
    defaults = {item.get("Extension") for item in types.iter(f"{_TYPES}Default")}
    for name in parts:
        assert f"/{name}" in overridden or name.rsplit(".", 1)[-1] in defaults, name
    assert {part[1:] for part in overridden} <= set(parts)

    package = ET.fromstring(parts["_rels/.rels"])  # noqa: S314
    assert {rel.get("Target") for rel in package.iter(f"{_PKG_REL}Relationship")} == {
        "xl/workbook.xml",
        "docProps/core.xml",
    }
    sheets = _sheet_files(parts)
    assert list(sheets) == [
        "README",
        "Timeline",
        "Scalars",
        "Nodes",
        "Edges",
        "Assumptions",
    ]
    assert set(sheets.values()) <= set(parts)
    assert "xl/styles.xml" in parts

    for name in sheets.values():
        root = ET.fromstring(parts[name])  # noqa: S314
        assert root.find(f".//{_MAIN}f") is None, f"{name} holds a formula"
        rows = [int(row.get("r", "0")) for row in root.iter(f"{_MAIN}row")]
        assert rows == sorted(set(rows))
        for cell in root.iter(f"{_MAIN}c"):
            assert cell.get("t") in {None, "b", "inlineStr"}, cell.get("t")
            if cell.get("t") == "inlineStr":
                assert cell.find(f"{_MAIN}is/{_MAIN}t") is not None


def test_no_cell_anywhere_holds_a_formula() -> None:
    for name, data in _parts(render_xlsx(_GOLDEN_RECORD)).items():
        assert b"<f>" not in data, name
        assert b"<f " not in data, name


def test_text_a_spreadsheet_would_read_as_a_formula_stays_text() -> None:
    grid = _grid(render_xlsx(_tricky_record()), "Scalars")
    rows = {text: row for (row, column), (_, text) in grid.items() if column == 0}
    assert grid[rows["label"], 4] == ("s", _TEXT)


# --- the layout follows the record -------------------------------------------


def test_the_readme_names_the_record_it_was_laid_out_from() -> None:
    document = _pinned(_tricky_record())
    grid = _grid(render_xlsx(document), "README")
    readme = {
        grid[row, 0][1]: grid.get((row, 1), ("", ""))[1]
        for row in range(1, 1 + max(r for r, _ in grid))
        if (row, 0) in grid
    }
    assert readme["document_digest"] == document["document_digest"]
    assert readme["graph_fingerprint"] == document["graph_fingerprint"]
    assert readme["formulas_fingerprint"] == document["formulas_fingerprint"]
    assert readme["book digest"] == document["book"]["digest"]
    assert readme["policy"] == "P-1"
    assert readme["  why"] == document["policies"][0]["why"]
    assert readme["check: seal"].startswith("agree")


def test_a_record_carrying_several_policies_gives_each_a_timeline() -> None:
    record = _GOLDENS / "policy_axis_example.json"
    parts = _parts(render_xlsx(record))
    assert list(_sheet_files(parts)) == [
        "README",
        "Timeline POL-000343",
        "Timeline GB-2019-88231",
        "Timeline 3_40",
        "Scalars",
        "Nodes",
        "Edges",
        "Assumptions",
    ]
    document = json.loads(record.read_text())
    grid = _grid(render_xlsx(record), "Timeline GB-2019-88231")
    header = {column: text for (row, column), (_, text) in grid.items() if row == 0}
    for column, node_id in header.items():
        if column == 0:
            continue
        sample = _nodes(document)[node_id]["value_sample"][1]
        for period, recorded in enumerate(sample):
            _assert_holds(grid.get((3 + period, column)), recorded, node_id)


def test_one_policy_of_several_is_laid_out_alone() -> None:
    record = _GOLDENS / "policy_axis_example.json"
    sheets = list(_sheet_files(_parts(render_xlsx(record, policy="3:40"))))
    assert sheets == ["README", "Timeline", "Scalars", "Nodes", "Edges", "Assumptions"]


def test_a_fold_of_the_book_is_laid_out_under_its_aggregation() -> None:
    record = _GOLDENS / "portfolio_fold_example.json"
    sheets = list(_sheet_files(_parts(render_xlsx(record))))
    assert sheets[1:3] == ["Timeline sum", "Timeline period_sum"]
    grid = _grid(render_xlsx(record), "Scalars")
    assert [grid[0, column][1] for column in range(4, 8)] == [
        "sum",
        "period_sum",
        "POL-000343",
        "GB-2019-88231",
    ]


def test_a_policy_the_record_does_not_carry_is_refused_naming_the_axis() -> None:
    record = _GOLDENS / "policy_axis_example.json"
    with pytest.raises(ValueError, match=r"'POL-9' is not on the record's axis") as no:
        render_xlsx(record, policy="POL-9")
    assert "'GB-2019-88231'" in str(no.value)
    assert "--policies id:POL-9" in str(no.value)


def test_a_record_whose_seal_does_not_hold_is_refused() -> None:
    document = _pinned(_tricky_record())
    document["nodes"][1]["value_sample"] = 1.0
    with pytest.raises(ValueError, match="seal does not hold"):
        render_xlsx(document)


def test_a_record_carrying_no_values_lays_out_its_calculations() -> None:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
    af.claims = af.sum_assured * 0.00123
    workbook = render_xlsx(GraphExporter(af).export())
    assert list(_sheet_files(_parts(workbook))) == [
        "README",
        "Nodes",
        "Edges",
        "Assumptions",
    ]
    readme = _grid(workbook, "README")
    assert any("carries no values" in text for _, text in readme.values())


def test_the_edges_carry_each_reads_offset_and_window() -> None:
    grid = _grid(render_xlsx(_tricky_record()), "Edges")
    header = [grid[0, column][1] for column in range(8)]
    rows = {
        (grid[row, 1][1], grid[row, 0][1]): {
            header[column]: grid[row, column][1]
            for column in range(8)
            if (row, column) in grid
        }
        for row in range(1, 1 + max(r for r, _ in grid))
    }
    assert rows["prior@1", "rate"]["offset"] == "-1"
    assert rows["running@1", "rate"]["narrowing"] == "AGGREGATION"
    assert rows["running@1", "rate"]["periods from"] == "first"
    assert rows["running@1", "rate"]["periods to"] == "0"
    assert "offset" not in rows["scaled@1", "rate"]


def test_the_nodes_sheet_names_every_node_in_the_records_order() -> None:
    document = _tricky_record()
    grid = _grid(render_xlsx(document), "Nodes")
    ids = [grid[row, 0][1] for row in range(1, len(document["nodes"]) + 1)]
    assert ids == [node["id"] for node in document["nodes"]]
    header = [grid[0, column][1] for column in range(14)]
    assert {"formula", "kind", "tier", "reads", "local_fingerprint"} <= set(header)
    assert "source_location" in header


def test_a_text_past_excels_cell_limit_is_cut_and_says_so() -> None:
    cell = xlsx_export._cell_xml("A1", xlsx_export._Cell("x" * 40_000))  # noqa: SLF001
    text = ET.fromstring(cell).find("is/t").text or ""  # type: ignore[union-attr]  # noqa: S314
    assert len(text) == 32_767
    assert text.endswith("the record holds the whole text]")


def test_a_sheet_past_excels_columns_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(xlsx_export, "_MAX_COLUMNS", 3)
    with pytest.raises(ValueError, match=r"5 columns, past Excel.s 3:"):
        render_xlsx(_tricky_record())


def test_sheet_names_are_made_legal_and_unique() -> None:
    names = xlsx_export._unique_sheet_names(  # noqa: SLF001
        ["Timeline a/b", "Timeline a?b", "Timeline " + "x" * 40, "Nodes"]
    )
    assert names == [
        "Timeline a_b",
        "Timeline a_b (2)",
        "Timeline " + "x" * 22,
        "Nodes (2)",
    ]
    assert all(len(name) <= 31 for name in names)


def test_af_graph_to_excel_writes_the_frames_record(tmp_path: Path) -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": ["Z"], "premium": [0.1]}))
    af.loaded = af.premium + 0.2
    written = af.graph.to_excel(
        tmp_path / "policy.xlsx",
        af.collect(),
        GraphExportConfig(policy_id_column="policy_id"),
    )
    grid = _grid(written.read_bytes(), "Scalars")
    rows = {text: row for (row, column), (_, text) in grid.items() if column == 0}
    assert grid[rows["loaded@1"], 4] == ("n", "0.30000000000000004")


def test_a_carriage_return_survives_any_xml_reader() -> None:
    """A bare CR would be read back as a line feed; a character reference is not."""
    openpyxl = pytest.importorskip("openpyxl")
    cell = xlsx_export._cell_xml("A1", xlsx_export._Cell("one\r\ntwo"))  # noqa: SLF001
    assert "&#13;" in cell
    text = ET.fromstring(cell).find("is/t").text  # type: ignore[union-attr]  # noqa: S314
    assert text == "one\r\ntwo"
    document = _tricky_record()
    sheet = openpyxl.load_workbook(io.BytesIO(render_xlsx(document)))["Scalars"]
    (label,) = [
        row[4] for row in sheet.iter_rows(values_only=True) if row[0] == "label"
    ]
    assert "\r\n" in label
