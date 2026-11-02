# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The kit's citation cases: a comparison report cites the corpus by its seal.

Section 13.1 has every record that points at a document it does not enclose
carry that document's ``document_digest`` beside the identity it already
carries, and a comparison report is such a record. ``conformance/
citations.json`` publishes two reports the producer writes over the §12.5
corpus -- one handed the corpus, one handed another export of the same model,
one fingerprint and another seal -- and the kit's standard-library reader
recomputes the corpus's seal and tells the two apart.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[4]
_KIT = _ROOT / "bindings/python/gaspatchio/schemas/conformance"
_CITATIONS = _KIT / "citations.json"
_SOURCE = _ROOT / "spec/graph-artifact/conformance"
_READER = _SOURCE / "citation.py"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed local interpreter and repository fixtures
        [sys.executable, "-I", *arguments],
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )


def _generator() -> Any:  # noqa: ANN401 -- a module loaded from its path
    spec = importlib.util.spec_from_file_location(
        "make_citation_vectors", _SOURCE / "make_citation_vectors.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_published_reports_are_the_producer_s_own() -> None:
    generator = _generator()
    corpus = json.loads((_KIT / "corpus.json").read_text())
    published = json.loads(_CITATIONS.read_text())["cases"]

    assert published[0]["record"] == generator._report(corpus)  # noqa: SLF001
    assert published[1]["record"] == generator._report(  # noqa: SLF001
        generator._another_export(corpus)  # noqa: SLF001
    )


def test_one_model_s_two_exports_give_one_verdict_and_two_seals() -> None:
    first, second = (
        case["record"] for case in json.loads(_CITATIONS.read_text())["cases"]
    )

    assert first["artifact_fingerprint"] == second["artifact_fingerprint"]
    assert first["document_digest"] != second["document_digest"]
    assert first["verdict"] == second["verdict"] == "agree"


def test_the_reader_finds_every_published_citation_as_stated() -> None:
    result = _run(str(_READER), str(_CITATIONS))

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"cases": 2, "failures": {}}


def test_the_packaged_reader_runs_outside_the_repository(tmp_path: Path) -> None:
    directory = shutil.copytree(_KIT, tmp_path / "conformance")
    result = _run(
        str(directory / "reader.pyz"), "--citation", str(directory / "citations.json")
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["cases"] == 2


def test_the_reader_names_a_report_citing_by_fingerprint_alone(tmp_path: Path) -> None:
    bundle = json.loads(_CITATIONS.read_text())
    bundle["cases"][0]["record"]["document_digest"] = None
    directory = shutil.copytree(_KIT, tmp_path / "conformance")
    (directory / "citations.json").write_text(json.dumps(bundle))

    result = _run(str(_READER), str(directory / "citations.json"))

    assert result.returncode == 1
    assert json.loads(result.stdout)["failures"] == {
        "compare-report-cites-the-corpus-by-its-seal": {
            "expected": [],
            "found": ["document_digest"],
        }
    }


def test_the_reader_refuses_a_cited_corpus_that_was_edited(tmp_path: Path) -> None:
    directory = shutil.copytree(_KIT, tmp_path / "conformance")
    corpus = json.loads((directory / "corpus.json").read_text())
    corpus["created_at"] = "2026-11-02T00:00:00Z"
    (directory / "corpus.json").write_text(json.dumps(corpus))

    result = _run(str(_READER), str(directory / "citations.json"))

    assert result.returncode == 1
    assert json.loads(result.stdout)["failures"]["cited document"] == [
        "document_digest"
    ]
