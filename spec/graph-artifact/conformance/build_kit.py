# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Package the independent reader and index using only public source/data.

Run from bindings/python with .venv/bin/python; never installs or rebuilds
the producer extension. ZIP timestamps and ordering are deterministic.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
SCHEMAS = ROOT / "bindings/python/gaspatchio/schemas"

# Each engine's coverage manifest, as a declared input. A manifest is JSON an
# engine generated from the capability predicates its own runtime applies, so
# the index carries what a second engine claims without this kit ever importing
# that engine -- and the claims cannot drift from the runtime, because the
# engine's own suite fails when the file on disk stops equalling a fresh
# generation.
ENGINE_MANIFESTS = [ROOT / "engines/jax/coverage.json"]
MAIN = b'''"""Independent conformance reader entry point."""
import sys
if len(sys.argv) > 1 and sys.argv[1] == "--identity":
    sys.argv.pop(1)
    from identity import main
elif len(sys.argv) > 1 and sys.argv[1] == "--content":
    sys.argv.pop(1)
    from content import main
elif len(sys.argv) > 1 and sys.argv[1] == "--citation":
    sys.argv.pop(1)
    from citation import main
else:
    from reference import main
main()
'''


def archive_bytes() -> bytes:
    entries = {"__main__.py": MAIN}
    for name in ("reference.py", "identity.py", "content.py", "citation.py"):
        entries[name] = (SOURCE / name).read_bytes()
    for source in sorted((SOURCE / "reader").glob("*.py")):
        entries[f"reader/{source.name}"] = source.read_bytes()
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def operation_status(name: str, examples: list[dict]) -> str:
    if name == "rollforward":
        return "structural-identity"
    if name == "rollforward.struct":
        if not any(example["kind"] == "artifact-type-refusal" for example in examples):
            raise ValueError("raw Struct needs artifact refusal evidence")
        return "excluded-output"
    if not any(
        example["kind"] in {"value", "recording-door-value"} for example in examples
    ):
        raise ValueError(f"no positive value example for {name}")
    return "bounded-value"


def engine_manifests() -> dict:
    """Return each engine's coverage manifest, keyed by the engine's own name."""
    return {
        manifest["engine"]: manifest
        for manifest in (json.loads(source.read_text()) for source in ENGINE_MANIFESTS)
    }


def index_document() -> dict:
    contracts = json.loads((SOURCE / "contracts.json").read_text())
    cases = []
    bundles = []
    for source in sorted((SCHEMAS / "vectors").glob("*.json")):
        data = json.loads(source.read_text())
        bundles.append(
            {
                "path": f"../vectors/{source.name}",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "cases": len(data["cases"]),
            }
        )
        cases.extend((source.name, case) for case in data["cases"])
    ids = [case["id"] for _, case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case identifiers must be unique across bundles")
    operations = []
    for name, clause in contracts.items():
        examples = [
            {"bundle": bundle, "id": case["id"], "kind": case["case_kind"]}
            for bundle, case in cases
            if name in case["covers"]
        ]
        structural = [
            case["id"] for _, case in cases if name in case.get("structural_covers", [])
        ]
        status = operation_status(name, examples)
        operations.append(
            {
                "identifier": name,
                "clause": clause,
                "status": status,
                "examples": examples,
                "structural_examples": structural,
            }
        )
    return {
        "schema": "gaspatchio-operation-vector-index/v0-preview.1",
        "artifact_schema": "gaspatchio-graph/v0-preview.3",
        "fingerprint_algorithm": "gspv0-preview-3",
        "coverage_claim": "Examples of bounded domains, not exhaustive boundary or backend conformance.",
        "case_counts": dict(sorted(Counter(c["case_kind"] for _, c in cases).items())),
        "producer_checks": sum(c["producer_check"] for _, c in cases),
        "boundary_review": {
            "path": "boundary-review.json",
            "sha256": hashlib.sha256(
                (SCHEMAS / "conformance/boundary-review.json").read_bytes()
            ).hexdigest(),
        },
        "bundles": bundles,
        # 12.3's content grammar, read by ``reader.pyz --content``: frames
        # described in plain JSON and the bytes and digest they encode to.
        "content_identity": {
            "path": "content-identity.json",
            "sha256": hashlib.sha256(
                (SCHEMAS / "conformance/content-identity.json").read_bytes()
            ).hexdigest(),
            "cases": len(
                json.loads((SCHEMAS / "conformance/content-identity.json").read_text())[
                    "cases"
                ]
            ),
        },
        # 13.1's citation rule, read by ``reader.pyz --citation``: records
        # that point at the corpus, with the findings a reader owes each.
        "citations": {
            "path": "citations.json",
            "sha256": hashlib.sha256(
                (SCHEMAS / "conformance/citations.json").read_bytes()
            ).hexdigest(),
            "cases": len(
                json.loads((SCHEMAS / "conformance/citations.json").read_text())[
                    "cases"
                ]
            ),
        },
        "engines": engine_manifests(),
        "operations": operations,
        "composition": {"when_then": "11.1.28"},
    }


def main() -> None:
    destination = SCHEMAS / "conformance"
    destination.mkdir(exist_ok=True)
    (destination / "reader.pyz").write_bytes(archive_bytes())
    (destination / "index.json").write_text(
        json.dumps(index_document(), indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
