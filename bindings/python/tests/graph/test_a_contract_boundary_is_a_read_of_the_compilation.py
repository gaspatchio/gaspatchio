# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A rollforward's contract-boundary mask is something the compilation reads.

The kernel stops a policy's balance at the first period whose mask is True,
so the mask decides every later period of every state the machine carries.
A graph whose compilation node did not read the mask would tell a reviewer
that the balance does not depend on the stop flag -- and that a restated
stop flag moves nothing downstream -- which is false.

The mask is read ``INDIRECT``/``CONDITIONAL``: its value is never in the
balance, it is the test that decides whether a period runs or holds zero,
which is the shape of a conditional's test and not of a positional index.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.validate import validate_artifact
from gaspatchio.rollforward import compile_rollforward

_PERIODS = 3


def _frame() -> ActuarialFrame:
    """Return one policy over three monthly periods with a mid-run stop."""
    frame = ActuarialFrame(
        {
            "initial": [100.0],
            "amount": [[10.0] * _PERIODS],
            "stop_l": [[False, True, False]],
        }
    )
    return frame.projection.set(
        start_date=datetime.date(2025, 1, 31),
        n_periods=_PERIODS,
        frequency="monthly",
    )


def _model(*, computed_mask: bool) -> ActuarialFrame:
    """Return the model: a deposit each period, stopped by the mask.

    With ``computed_mask`` the model writes the mask into a column of its
    own first, which is the usual shape -- a universal-life model builds its
    stop flag from its own lapse test. Without it the mask is the column the
    data arrived with.
    """
    frame = _frame()
    if computed_mask:
        frame["stop_flag"] = frame["stop_l"]
        mask = frame["stop_flag"]
    else:
        mask = frame["stop_l"]
    builder = frame.projection.rollforward(
        states={"bal": frame["initial"]}, contract_boundary=mask
    )
    builder["bal"].add(frame["amount"], label="deposit")
    frame["bal"] = compile_rollforward(builder).expr_for("bal")
    return frame


def _artifact(frame: ActuarialFrame) -> dict[str, Any]:
    exported: dict[str, Any] = json.loads(
        GraphExporter(frame).export(result_df=frame.collect())
    )
    return exported


def _compilation(artifact: dict[str, Any]) -> dict[str, Any]:
    (node,) = [node for node in artifact["nodes"] if node["kind"] == "rollforward"]
    return node


@pytest.mark.parametrize(
    ("computed_mask", "mask_id"),
    [(False, "stop_l"), (True, "stop_flag@1")],
    ids=["arriving-mask", "model-written-mask"],
)
def test_the_compilation_reads_its_contract_boundary(
    *, computed_mask: bool, mask_id: str
) -> None:
    """The mask is in the compilation's reads, as an edge, narrowed CONDITIONAL."""
    artifact = _artifact(_model(computed_mask=computed_mask))
    compilation = _compilation(artifact)

    assert mask_id in compilation["reads"]
    edges = [
        edge
        for edge in artifact["edges"]
        if edge["source"] == mask_id and edge["target"] == compilation["id"]
    ]
    assert len(edges) == 1
    assert edges[0]["relationship"] == "INDIRECT"
    (read,) = [
        read
        for read in compilation["facets"]["gaspatchio_column_transformation"]["reads"]
        if read["source"] == mask_id
    ]
    assert [(way["type"], way["subtype"]) for way in read["transformations"]] == [
        ("INDIRECT", "CONDITIONAL")
    ]
    report = validate_artifact(artifact, deep=True)
    assert report.ok, report


@pytest.mark.parametrize("computed_mask", [False, True], ids=["arriving", "written"])
def test_a_stopped_compilation_still_reports_its_movements(
    *, computed_mask: bool
) -> None:
    """With the mask accounted for, the movement schedule is bound and attached.

    The schedule shows the deposit in the first period and nothing once the
    contract has terminated, which is what the balance came to.
    """
    frame = _model(computed_mask=computed_mask)
    assert frame.collect()["bal"].to_list() == [[110.0, 0.0, 0.0]]
    compilation = _compilation(_artifact(frame))

    assert "movements" in compilation
