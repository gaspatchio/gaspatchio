# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Independently check the published citations of the §12.5 corpus (section 13.1).

Only the Python standard library is used. Section 13.1 has every record that
points at a document it does not enclose carry that document's
``document_digest`` beside the identity it already carries. Each case is such
a record -- a comparison report (``gaspatchio-graph-compare/v0-preview.2``)
over the corpus -- with the findings a reader owes it: none where the record
cites the corpus by its own fingerprint and its own seal, and
``document_digest`` where it cites another written document of one model,
whose fingerprint is the same and whose seal is not. The seal is recomputed
here from the corpus's bytes, never read from it.
Run: python -I citation.py path/to/citations.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Script mode under -I omits its directory from sys.path. Add only this
# reader's own directory; no producer package is imported or discovered.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from identity import stamp, verify  # noqa: E402 -- after the path above

REPORT_VERSION = "gaspatchio-graph-compare/v0-preview.2"


def seal_of(document: dict[str, Any]) -> str:
    """Return the seal section 13.1 states: SHA-256 of the unsealed document."""
    unsealed = {
        key: value for key, value in document.items() if key != "document_digest"
    }
    return stamp(
        json.dumps(
            unsealed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    )


def findings_of(record: dict[str, Any], document: dict[str, Any]) -> list[str]:
    """Return what one citing record gets wrong about the document it cites."""
    findings: list[str] = []
    if record.get("report_version") != REPORT_VERSION:
        findings.append("report_version")
    if record.get("artifact_fingerprint") != document["graph_fingerprint"]:
        findings.append("artifact_fingerprint")
    if record.get("document_digest") != seal_of(document):
        findings.append("document_digest")
    return findings


def main() -> None:
    path = Path(sys.argv[1])
    bundle = json.loads(path.read_text())
    document = json.loads((path.parent / bundle["cites"]).read_text())
    failures: dict[str, Any] = {}
    # The cited document must itself be the corpus whose identities the
    # identity reader recomputes; a citation of a tampered corpus proves nothing.
    corpus = verify(document)
    if corpus:
        failures["cited document"] = corpus
    for case in bundle["cases"]:
        found = findings_of(case["record"], document)
        if found != case["findings"]:
            failures[case["id"]] = {"expected": case["findings"], "found": found}
    print(
        json.dumps(
            {"cases": len(bundle["cases"]), "failures": failures},
            indent=2,
            sort_keys=True,
        )
    )
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
