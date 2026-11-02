# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A hole whose stamp moved is reported as data that changed.

The 0.9 setup step collects the frame, joins a side file in plain Polars and
builds a fresh frame over the result. The joined column is a hole, and since
holes carry a stamp of what they held an edit to that file moves the
document's ``graph_fingerprint``. It moves no node digest -- the hole's node
carries no stamp -- so ``gspio diff`` read the two documents node by node,
found nothing, and printed "nothing moved" over two different fingerprints.
The change report now reads the holes section too: a hole both documents list
whose stamp moved is a ``data`` entry of kind ``hole``, and it is drift.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
from typing import TYPE_CHECKING

import polars as pl
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph import DataChange, GraphExporter, diff_artifacts

if TYPE_CHECKING:
    from pathlib import Path

BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "premium": [100.0, 400.0, 300.0],
        "product": ["A", "B", "A"],
    }
)

# Section 12.3's bytes for the column 'load' as the frame arrived holding it,
# by hand: one column, its name, the f64 tag, three rows, each value present
# (0x02) as eight IEEE-754 bytes. Product A's load is 1.0, then 1.1.
_LOAD_1_0 = "01046c6f61641303" + ("02" + "3ff0000000000000") * 3
_LOAD_1_1 = "01046c6f61641303" + "".join(
    "02" + value
    for value in ("3ff199999999999a", "3ff0000000000000", "3ff199999999999a")
)


def _stamp(hex_bytes: str) -> str:
    return "sha256:" + hashlib.sha256(bytes.fromhex(hex_bytes)).hexdigest()


def _finish(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=3,
        frequency="monthly",
    )
    af.prem = af.premium * af.load + af.month * 0.0
    af.pv_prem = af.prem.list.sum()
    return af


def _unrecorded(load_a: float) -> ActuarialFrame:
    """Return the 0.9 template: collect, join the side file in Polars, rebuild."""
    loads = pl.DataFrame({"product": ["A", "B"], "load": [load_a, 1.0]})
    mp = ActuarialFrame(BOOK).collect()
    return _finish(
        ActuarialFrame(mp.join(loads, on="product", how="left", maintain_order="left"))
    )


def _rebuilt(load_a: float) -> ActuarialFrame:
    """Return a column another frame calculated, still held, in a new frame."""
    loads = pl.DataFrame({"product": ["A", "B"], "load": [load_a, 1.0]})
    af = ActuarialFrame(BOOK).join(loads, on="product", how="left")
    af.load2 = af.load * 1.0
    held = af.collect()
    return _finish(ActuarialFrame(held.drop("load").rename({"load2": "load"})))


def _exported(af: ActuarialFrame) -> dict[str, object]:
    exporter = GraphExporter(af, data_columns=BOOK.columns)
    return json.loads(exporter.export(af.collect()))


def test_an_edited_side_file_is_a_hole_whose_stamp_moved() -> None:
    before, after = _exported(_unrecorded(1.0)), _exported(_unrecorded(1.1))
    assert before["graph_fingerprint"] != after["graph_fingerprint"]

    report = diff_artifacts(before, after)

    assert report.data == (
        DataChange("hole", "load", _stamp(_LOAD_1_0), _stamp(_LOAD_1_1)),
    )
    assert report.calculations == ()
    assert report.drift is True


def test_a_rebuilt_column_whose_values_moved_is_reported_the_same_way() -> None:
    report = diff_artifacts(_exported(_rebuilt(1.0)), _exported(_rebuilt(1.1)))

    assert report.data == (
        DataChange("hole", "load", _stamp(_LOAD_1_0), _stamp(_LOAD_1_1)),
    )
    assert report.drift is True


def test_an_unchanged_side_file_moves_nothing() -> None:
    report = diff_artifacts(_exported(_unrecorded(1.0)), _exported(_unrecorded(1.0)))

    assert report.data == ()
    assert report.drift is False


def test_a_hole_stamped_on_one_side_only_could_not_be_compared() -> None:
    after = _exported(_unrecorded(1.0))
    before = copy.deepcopy(after)
    for hole in before["holes"]:  # type: ignore[union-attr]
        del hole["content"]

    (entry,) = diff_artifacts(before, after).data

    assert (entry.kind, entry.name, entry.before) == ("hole", "load", None)
    assert entry.after == _stamp(_LOAD_1_0)
    assert entry.reason is not None
    assert entry.reason.startswith("The hole load could not be compared")
    assert "the earlier document records no stamp" in entry.reason
    assert diff_artifacts(before, after).drift is True


def test_an_overwritten_hole_says_why_it_carries_no_stamp() -> None:
    before = _exported(_unrecorded(1.0))
    after = copy.deepcopy(before)
    after["holes"] = [  # type: ignore[index]
        {"column": "load", "reason": "overwritten", "closes_with": "x"}
    ]

    (entry,) = diff_artifacts(before, after).data

    assert entry.after is None
    assert entry.reason is not None
    assert "the later document records no stamp" in entry.reason
    assert "an overwritten definition" in entry.reason


def test_a_hole_only_one_document_lists_is_left_to_the_calculations() -> None:
    before = _exported(_unrecorded(1.0))
    after = copy.deepcopy(before)
    after["holes"] = []  # type: ignore[index]

    assert diff_artifacts(before, after).data == ()


def test_the_command_says_something_moved_and_names_the_hole(tmp_path: Path) -> None:
    earlier, later = tmp_path / "q1.json", tmp_path / "q2.json"
    earlier.write_text(json.dumps(_exported(_unrecorded(1.0))))
    later.write_text(json.dumps(_exported(_unrecorded(1.1))))

    result = CliRunner().invoke(app, ["diff", str(earlier), str(later)])

    assert result.exit_code == 1, result.output
    text = " ".join(result.output.split())
    assert "something moved between q1.json and q2.json" in text
    assert (
        "formulas unchanged (formulas_fingerprint equal); data changed: hole load"
        in text
    )
    assert f"hole load {_stamp(_LOAD_1_0)} → {_stamp(_LOAD_1_1)}" in text
