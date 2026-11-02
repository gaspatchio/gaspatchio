# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A hole the frame arrived holding carries the stamp of its values.

The 0.9 setup step collects the frame, joins a side file in plain Polars and
builds a fresh frame over the result. The joined column is a hole: nothing
in the record says what made it. It used to be a hole by name alone, so an
edit to the side file moved the numbers and no identity -- the
``graph_fingerprint`` of the model over the original file and over the
edited one were the same string. The frame cannot say what made the column,
and it can say what the column held when it arrived: that stamp now sits on
the hole (section 7.1's ``content``) and beside its name in the digest
(section 12.4's third section), so the edit moves the identity and an
unchanged file does not. The formulas digest leaves the stamp out.

The record is told which columns the book carried wherever a runner watched
the run begin -- ``gspio calc-graph``, and now every batch runner and
scenario plan -- so one model writes one record whichever of them wrote it.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import TYPE_CHECKING

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.scenarios import ScenarioRun, Sum, run_aggregated

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "premium": [100.0, 400.0, 300.0],
        "product": ["A", "B", "A"],
    }
)

# Section 12.3's bytes for the column 'load' as the frame arrived holding it,
# written out by hand: one column, its name, the f64 tag, three rows, and each
# value present (0x02) as eight IEEE-754 bytes, most significant first.
_LOAD_A_1_0 = "01046c6f61641303" + ("02" + "3ff0000000000000") * 3
_LOAD_A_1_1 = (
    "01"
    "046c6f6164"
    "13"
    "03"
    "02" + "3ff199999999999a" + "02" + "3ff0000000000000" + "02" + "3ff199999999999a"
)


def _stamp(hex_bytes: str) -> str:
    return "sha256:" + hashlib.sha256(bytes.fromhex(hex_bytes)).hexdigest()


def _setup_join(load_a: float) -> Callable[[ActuarialFrame], ActuarialFrame]:
    """Return the 0.9 template: collect, join a side file in Polars, rebuild."""
    loads = pl.DataFrame({"product": ["A", "B"], "load": [load_a, 1.0]})

    def main(af: ActuarialFrame) -> ActuarialFrame:
        mp = af.collect().join(loads, on="product", how="left", maintain_order="left")
        af = ActuarialFrame(mp)
        af = af.projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="term_months",
            until_value=3,
            frequency="monthly",
        )
        af.prem = af.premium * af.load + af.month * 0.0
        af.pv_prem = af.prem.list.sum()
        return af

    return main


def _exported(load_a: float) -> dict[str, object]:
    af = _setup_join(load_a)(ActuarialFrame(BOOK))
    exporter = GraphExporter(af, data_columns=BOOK.columns)
    return json.loads(exporter.export(af.collect()))


def test_the_joined_column_is_a_hole_stamped_with_what_it_held() -> None:
    document = _exported(1.0)

    assert document["holes"] == [
        {
            "column": "load",
            "reason": "unrecorded",
            "content": _stamp(_LOAD_A_1_0),
            "closes_with": "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3#holes",
        }
    ]
    assert _exported(1.1)["holes"][0]["content"] == _stamp(_LOAD_A_1_1)


def test_an_edit_to_the_side_file_moves_the_identity_and_nothing_else() -> None:
    base, copy, edited = _exported(1.0), _exported(1.0), _exported(1.1)

    assert copy["graph_fingerprint"] == base["graph_fingerprint"]
    assert edited["graph_fingerprint"] != base["graph_fingerprint"]
    # The edit is data, not a formula, and the book did not move.
    assert edited["formulas_fingerprint"] == base["formulas_fingerprint"]
    assert edited["book"]["digest"] == base["book"]["digest"]


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        low = value & 0x7F
        value >>= 7
        if value:
            out.append(low | 0x80)
        else:
            out.append(low)
            return bytes(out)


def _text(value: str) -> bytes:
    raw = value.encode()
    return _varint(len(raw)) + raw


def test_the_third_section_is_the_name_and_then_the_stamp_in_one_entry() -> None:
    """Section 12.4 recomputed by hand from the document alone."""
    document = _exported(1.0)
    nodes = {node["id"]: node["fingerprint"] for node in document["nodes"]}
    pairs = [
        _text(node_id) + bytes.fromhex(nodes[node_id].removeprefix("sha256:"))
        for node_id in sorted(nodes)
    ]
    stamp = document["holes"][0]["content"]
    by_hand = hashlib.sha256(
        _varint(len(pairs))
        + b"".join(pairs)
        + _varint(0)  # no assumption tables
        + _varint(1)  # one hole: one entry, two strings
        + _text("load")
        + _text(stamp)
    ).hexdigest()

    assert document["graph_fingerprint"] == f"sha256:{by_hand}"
    assert validate_artifact(json.dumps(document), deep=True).ok


def test_a_document_whose_stamp_was_edited_no_longer_validates() -> None:
    document = _exported(1.0)
    document["holes"][0]["content"] = _stamp(_LOAD_A_1_1)

    report = validate_artifact(json.dumps(document), deep=True)

    assert not report.ok
    assert any(
        finding.severity == "error" and "graph_fingerprint" in finding.message
        for finding in report.findings
    )


def test_a_rebuilt_column_carries_the_stamp_of_the_values_it_arrived_with() -> None:
    af = ActuarialFrame(pl.DataFrame({"premium": [100.0, 200.0]}))
    af.q = af.premium * 0.5
    held = af.collect()
    rebuilt = ActuarialFrame(held)

    (hole,) = rebuilt.graph.holes()

    # 'q' as it arrived: 50.0 and 100.0, as doubles.
    assert (hole.column, hole.reason) == ("q", "rebuilt")
    assert hole.content == _stamp("0101711302024049000000000000024059000000000000")


def test_an_overwritten_column_carries_no_stamp_and_keeps_its_digest() -> None:
    """A write past the doors holds no arriving values: name alone, as before."""
    af = ActuarialFrame(BOOK)
    af._df = af._df.with_columns(pl.col("premium") * 2.0)  # noqa: SLF001
    af.net = af.premium * 0.9
    document = json.loads(GraphExporter(af).export(af.collect()))

    assert [(h["column"], h["reason"]) for h in document["holes"]] == [
        ("premium", "overwritten")
    ]
    assert "content" not in document["holes"][0]
    assert validate_artifact(json.dumps(document), deep=True).ok


def test_every_door_that_watched_the_run_begin_writes_one_record(
    tmp_path: Path,
) -> None:
    """calc-graph, run_aggregated and a scenario plan agree on the model's figure."""
    exported = _exported(1.0)["graph_fingerprint"]
    model = _setup_join(1.0)

    run_aggregated(
        model,
        BOOK,
        aggregations=(Sum("pv_prem").alias("total"),),
        batch_size=3,
        audit=tmp_path / "agg.json",
    )
    ScenarioRun(shocks={"BASE": []}, aggregations=(Sum("pv_prem").alias("total"),)).run(
        ActuarialFrame(BOOK), model, audit=tmp_path / "plan.json"
    )

    aggregated = json.loads((tmp_path / "agg.json").read_text())
    plan = json.loads((tmp_path / "plan.json").read_text())
    assert aggregated["graph_fingerprint"] == exported
    assert plan["graph_fingerprint_by_scenario"]["BASE"] == exported


def test_a_run_record_moves_with_the_side_file(tmp_path: Path) -> None:
    for name, load_a in (("base", 1.0), ("copy", 1.0), ("edited", 1.1)):
        run_aggregated(
            _setup_join(load_a),
            BOOK,
            aggregations=(Sum("pv_prem").alias("total"),),
            batch_size=3,
            audit=tmp_path / f"{name}.json",
        )
    figure = {
        name: json.loads((tmp_path / f"{name}.json").read_text())["graph_fingerprint"]
        for name in ("base", "copy", "edited")
    }

    assert figure["copy"] == figure["base"]
    assert figure["edited"] != figure["base"]
