# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A compare report cites the document it was handed by its seal too (§13.1).

``gspio compare`` reads a written executable document, so its report is a
record that points at an artifact it does not enclose: it carries the
document's ``document_digest`` beside the ``graph_fingerprint`` it already
carried. Two exports of one model -- one fingerprint, two seals -- gave
byte-equal reports, so the report could not say which written document it was
a comparison under. The seal is recorded and never compared: the verdict over
the same two results is the same under either export.
"""

from __future__ import annotations

import json

import polars as pl

from gaspatchio.engines.compare import REPORT_VERSION, compare_results
from tests.engines.test_compare import FIVE_NODES, ID, _artifact, _manifest, _named

SEAL = "sha256:" + "aa" * 32
OTHER_SEAL = "sha256:" + "bb" * 32


def _report(seal: str | None) -> dict[str, object]:
    columns, kept = _named(["net@1", "pv@1"], {"net@1": "f64", "pv@1": "f64"})
    frame = pl.DataFrame({"policy_id": [1, 2], "net@1": [1.0, 2.0], "pv@1": [3.0, 4.0]})
    document = _artifact(FIVE_NODES)
    if seal is not None:
        document["document_digest"] = seal
    report = compare_results(
        document,
        frame,
        frame,
        before_manifest=_manifest("final-schema", columns, kept, identity=ID),
        after_manifest=_manifest("final-schema", columns, kept, identity=ID),
    )
    return json.loads(json.dumps(report.to_dict()))


def test_the_report_names_the_seal_beside_the_fingerprint() -> None:
    read = _report(SEAL)
    assert read["document_digest"] == SEAL
    keys = list(read)
    assert keys.index("document_digest") == keys.index("artifact_fingerprint") + 1


def test_two_exports_of_one_model_give_two_reports_with_one_verdict() -> None:
    one, other = _report(SEAL), _report(OTHER_SEAL)
    assert one["document_digest"] != other["document_digest"]
    assert one["artifact_fingerprint"] == other["artifact_fingerprint"]
    assert one["verdict"] == other["verdict"] == "agree"
    one.pop("document_digest")
    other.pop("document_digest")
    assert one == other


def test_a_document_without_a_seal_is_cited_with_null() -> None:
    assert _report(None)["document_digest"] is None


def test_the_report_grammar_moved_to_preview_two() -> None:
    assert REPORT_VERSION == "gaspatchio-graph-compare/v0-preview.2"
    assert _report(SEAL)["report_version"] == REPORT_VERSION
