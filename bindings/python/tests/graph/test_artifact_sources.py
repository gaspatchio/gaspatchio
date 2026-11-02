# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The model's own text travels with the account of it.

An artifact has always named the model -- ``model.source_path``,
``model.source_sha`` -- and every node has always carried the line its
calculation was written on. It carried no line of the file. So a reader
could be told which line computed a figure and not be shown it, and a second
reader holding the artifact had the formulas without the code around them.

The sources section closes that. One entry per distinct path any node's
``source_location`` names, each carrying the file's text under the same
inline budget a lookup's table travels under, re-hashable against the digest
the envelope already publishes beside it. Leaving the text out is an
explicit act the file records -- withheld, for a decision; size, for a file
weighed and too large; unavailable, for one the producer could not read from
here -- and never a silence.
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import TYPE_CHECKING, Any, cast

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph import (
    DOCUMENT_DIGEST_FIELD,
    SOURCE_DIRECTORY,
    GraphExporter,
    document_digest_of,
    payload_file_name,
    validate_artifact,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

runner = CliRunner()

# A model written in two files, because the section's rule is one entry per
# file a node was written in and a single-file model cannot tell that rule
# from "one entry for the model".
MODEL_SRC = """
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gaspatchio import ActuarialFrame
from expenses import add_expenses


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.death_claims = af.sum_assured * 0.00123
    return add_expenses(af)
"""

EXPENSES_SRC = """
from gaspatchio import ActuarialFrame


def add_expenses(af: ActuarialFrame) -> ActuarialFrame:
    af.expenses = af.annual_premium * 0.05
    return af
"""


@pytest.fixture(autouse=True)
def _one_model_at_a_time() -> Iterator[None]:
    """Keep each test's two files out of the next test's import.

    Every test here writes ``model.py`` and ``expenses.py`` into its own
    temporary directory, and both are imported by name. Without this the
    second test to run would be handed the first test's ``expenses`` out of
    the module cache, and its nodes would carry locations pointing into a
    directory that test had finished with -- which is a fixture defect that
    reads exactly like a producer bug.
    """
    path, modules = list(sys.path), set(sys.modules)
    try:
        yield
    finally:
        sys.path[:] = path
        for name in set(sys.modules) - modules:
            if name in {"model", "expenses"}:
                del sys.modules[name]


def _a_model_at(directory: Path) -> Path:
    """Write the two-file model and the policy data it is run over."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "model.py").write_text(MODEL_SRC)
    (directory / "expenses.py").write_text(EXPENSES_SRC)
    pl.DataFrame(
        {"policy_id": ["A"], "sum_assured": [100_000.0], "annual_premium": [450.0]}
    ).write_parquet(directory / "points.parquet")
    return directory / "model.py"


def _exported(model: Path, *options: str) -> dict[str, Any]:
    """Export from the command line, where the root is decided, and read it back."""
    out = model.parent / "graph.json"
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(model.parent / "points.parquet"),
            "-o",
            str(out),
            *options,
        ],
    )
    assert result.exit_code == 0, result.output
    return cast("dict[str, Any]", json.loads(out.read_text()))


def _bytes_digest(path: Path) -> str:
    """Return the stamp over a file's own bytes, the way the envelope takes it."""
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _by_path(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the sources section keyed by the path each entry names."""
    return {entry["path"]: entry for entry in document["sources"]}


def _located(document: dict[str, Any]) -> set[str]:
    """Return the file part of every node location, with the line dropped."""
    return {
        node["source_location"].rpartition(":")[0]
        for node in document["nodes"]
        if node.get("source_location") is not None
    }


def _a_frame_from(model: Path) -> ActuarialFrame:
    """Run a written model the way the API does, without the command line."""
    import importlib.util

    specification = importlib.util.spec_from_file_location(model.stem, model)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    frame = ActuarialFrame(
        pl.DataFrame(
            {"policy_id": ["A"], "sum_assured": [100_000.0], "annual_premium": [450.0]}
        )
    )
    return cast("ActuarialFrame", module.main(frame))


# --- the text travels ---------------------------------------------------------


def test_the_model_the_artifact_is_an_account_of_travels_in_it(tmp_path: Path) -> None:
    """The file's own text, in the document, under the path a node names.

    The whole point of the section: a reader who has followed a node to
    ``model.py:12`` can read line 12 out of the same file rather than being
    sent to find a copy and asked to trust that it is the right one.
    """
    model = _a_model_at(tmp_path)

    document = _exported(model)

    assert _by_path(document)["model.py"]["payload"]["text"] == model.read_text()


def test_one_entry_per_file_a_node_was_written_in_ordered_by_path(
    tmp_path: Path,
) -> None:
    """Both files, once each, in the order the document will always write them.

    Ordered by path so that two artifacts of one model compare as written:
    a section whose order followed the walk would differ between two exports
    that found the same two files in a different order.
    """
    model = _a_model_at(tmp_path)

    document = _exported(model)

    assert [entry["path"] for entry in document["sources"]] == [
        "expenses.py",
        "model.py",
    ]


def test_a_source_entry_is_reached_by_the_same_path_a_node_names(
    tmp_path: Path,
) -> None:
    """The two strings are one string, so following a location arrives.

    A reader meets a path on a node and looks it up here. If the section
    spelled a path its own way -- absolute where the node was relative, or
    resolved through a link the node was not -- the lookup would miss and
    nothing in the document would say why.
    """
    model = _a_model_at(tmp_path)

    document = _exported(model)

    assert set(_by_path(document)) == _located(document)


def test_the_entry_for_the_model_file_re_hashes_to_the_digest_beside_it(
    tmp_path: Path,
) -> None:
    """The envelope's stamp and this entry's are one digest read twice.

    What lets a page say the source it is showing is the source that ran.
    Two digests taken two ways would leave a viewer able to show a file and
    unable to say whether the run used it.
    """
    model = _a_model_at(tmp_path)

    document = _exported(model)

    entry = _by_path(document)[document["model"]["source_path"]]
    assert entry["fingerprint"] == document["model"]["source_sha"]
    assert entry["fingerprint"] == _bytes_digest(model)


def test_every_carried_text_re_hashes_to_its_own_entry(tmp_path: Path) -> None:
    """The rule is every entry's, not the model file's alone.

    The digest is over the file's bytes, and the text is those bytes decoded
    as UTF-8 -- so re-encoding what the document carries reaches the digest
    beside it, which is a check a consumer runs with the standard library
    and nothing else.
    """
    model = _a_model_at(tmp_path)

    document = _exported(model)

    for entry in document["sources"]:
        carried = entry["payload"]["text"].encode()
        assert f"sha256:{hashlib.sha256(carried).hexdigest()}" == entry["fingerprint"]


# --- and where it does not -----------------------------------------------------


def test_the_text_withheld_still_carries_the_path_and_the_digest(
    tmp_path: Path,
) -> None:
    """A producer that declines to disclose says so, and says it about what.

    ``size`` would be a reason that is false -- the file was not weighed and
    found too large, it was not offered -- and a silence would leave a reader
    unable to tell a decision from an oversight. The path and the digest stay,
    so a reader knows what was withheld and can check a copy they hold.
    """
    model = _a_model_at(tmp_path)

    document = _exported(model, "--no-source")

    entry = _by_path(document)["model.py"]
    assert entry["payload"] == {"omitted": "withheld"}
    assert entry["fingerprint"] == _bytes_digest(model)
    assert [found["path"] for found in document["sources"]] == [
        "expenses.py",
        "model.py",
    ]


def test_a_source_over_the_inline_budget_states_what_fetching_it_would_cost(
    tmp_path: Path,
) -> None:
    """The table's guard, on the model's text, with the table's stand-in.

    The weight is the file written as its own document, which is what the
    sidecar would write, so the number is the size of the file a reader would
    fetch rather than an estimate standing near it.
    """
    model = _a_model_at(tmp_path)
    exporter = GraphExporter(_a_frame_from(model))

    document = json.loads(
        exporter.export(source_root=tmp_path, table_payload_limit=10)
    )

    entry = _by_path(document)["model.py"]
    assert entry["payload"]["omitted"] == "size"
    assert entry["payload"]["bytes"] > len(model.read_bytes())
    assert entry["fingerprint"] == _bytes_digest(model)


def test_a_model_file_that_moved_is_named_rather_than_invented(
    tmp_path: Path,
) -> None:
    """A file the producer can no longer read gets a path and no claim.

    Not a silence, which would say the model had one file fewer, and not an
    invented entry: the producer took no digest, so it publishes none. What
    survives is the one honest thing -- where the calculation was written.
    """
    model = _a_model_at(tmp_path)
    frame = _a_frame_from(model)
    model.unlink()

    document = json.loads(GraphExporter(frame).export(source_root=tmp_path))

    entry = _by_path(document)["model.py"]
    assert entry["payload"] == {"omitted": "unavailable"}
    assert entry["fingerprint"] is None


def test_a_file_outside_the_model_root_is_named_and_not_read(tmp_path: Path) -> None:
    """The root is the width of what an artifact speaks for.

    A model reaching outside the tree it is published from is a fact the
    document keeps, and ``..`` is how it keeps it. Reading past the root
    would publish a file from a tree the document does not account for and
    that no reader could resolve the path against.
    """
    model = _a_model_at(tmp_path / "models")
    inside = tmp_path / "models"

    document = json.loads(
        GraphExporter(_a_frame_from(model)).export(source_root=inside / "deeper")
    )

    entry = _by_path(document)["../model.py"]
    assert entry["payload"] == {"omitted": "unavailable"}
    assert entry["fingerprint"] is None


# --- the sidecar ---------------------------------------------------------------


def test_the_sidecar_files_the_text_in_a_folder_of_its_own(tmp_path: Path) -> None:
    """The bases' filing rule, applied to the model's text, in its own folder.

    The file is named after the fingerprint the entry publishes, so nothing
    in the document points at it and nothing needs to: a consumer fetches the
    name, re-hashes what comes back and either reaches the digest or has been
    handed the wrong file. The folder is the section's own name, because a
    model's code filed among the rate tables is the confusion the section
    exists to avoid.
    """
    model = _a_model_at(tmp_path / "tree")
    filing = tmp_path / "filed"

    document = json.loads(
        GraphExporter(_a_frame_from(model)).export_with_sidecar(
            filing, source_root=tmp_path / "tree"
        )
    )

    entry = _by_path(document)["model.py"]
    assert entry["payload"]["omitted"] == "size"
    beside = filing / SOURCE_DIRECTORY / payload_file_name(entry["fingerprint"])
    assert json.loads(beside.read_text("utf-8"))["text"] == model.read_text()
    assert len(beside.read_bytes()) == entry["payload"]["bytes"]


def test_a_filing_that_withholds_the_source_writes_no_file_for_it(
    tmp_path: Path,
) -> None:
    """Withheld is a decision about disclosure, not about where the text sits."""
    model = _a_model_at(tmp_path / "tree")
    filing = tmp_path / "filed"

    GraphExporter(_a_frame_from(model)).export_with_sidecar(
        filing, source_root=tmp_path / "tree", include_source=False
    )

    assert not (filing / SOURCE_DIRECTORY).exists()


# --- what a reader makes of it -------------------------------------------------


def test_the_reading_refuses_a_text_that_does_not_hash_to_its_digest(
    tmp_path: Path,
) -> None:
    """One character, and the document stops vouching for its own code.

    The failure this check exists for is a file whose text was edited after
    export: every fingerprint still checks, the document still parses, and a
    reader tracing a figure back to a line would be tracing it to a line
    somebody else wrote.
    """
    model = _a_model_at(tmp_path)
    document = _exported(model)
    entry = _by_path(document)["model.py"]
    entry["payload"]["text"] = entry["payload"]["text"].replace("0.00123", "0.00124")
    document.pop(DOCUMENT_DIGEST_FIELD, None)
    document[DOCUMENT_DIGEST_FIELD] = document_digest_of(document)

    report = validate_artifact(document, deep=True)

    assert not report.ok
    assert any(
        "not the code the model was run from" in finding.message
        for finding in report.findings
    )


@pytest.mark.parametrize("reason", ["withheld", "unavailable"])
def test_a_source_left_out_is_remarked_on_the_way_a_base_is(
    tmp_path: Path, reason: str
) -> None:
    """A remark, not a refusal: the producer said what happened and why.

    The same grade an assumption entry earns for the same shape. What the
    reader is told is that this entry's digest is one the file did not check
    for them, and which of the reasons put it there.
    """
    model = _a_model_at(tmp_path)
    document = _exported(model)
    for entry in document["sources"]:
        entry["payload"] = {"omitted": reason}
    document.pop(DOCUMENT_DIGEST_FIELD, None)
    document[DOCUMENT_DIGEST_FIELD] = document_digest_of(document)

    report = validate_artifact(document, deep=True)

    assert report.ok
    assert [finding.severity for finding in report.findings].count("warning") >= len(
        document["sources"]
    )


def test_the_schema_refuses_a_source_entry_with_neither_text_nor_a_reason(
    tmp_path: Path,
) -> None:
    """An empty payload is the one thing the form cannot mean.

    The member named ``omitted`` is what tells a carried text from a stood-in
    one. A payload carrying neither says nothing at all, and a reader could
    not tell it from a producer that meant to carry the file and lost it.
    """
    import jsonschema

    from gaspatchio.schemas import load_schema

    model = _a_model_at(tmp_path)
    document = _exported(model)
    document["sources"][0]["payload"] = {}

    refused = list(jsonschema.Draft202012Validator(load_schema()).iter_errors(document))

    assert [list(error.absolute_path) for error in refused] == [
        ["sources", 0, "payload"],
    ]


def test_the_schema_refuses_text_under_a_digest_nobody_took(tmp_path: Path) -> None:
    """A null fingerprint and carried text are two halves of one impossibility.

    A producer that took no digest did not read the file, and an entry
    claiming text under a null fingerprint would be publishing bytes nothing
    in the document identifies.
    """
    import jsonschema

    from gaspatchio.schemas import load_schema

    model = _a_model_at(tmp_path)
    document = _exported(model)
    document["sources"][1]["fingerprint"] = None

    refused = list(jsonschema.Draft202012Validator(load_schema()).iter_errors(document))

    assert [list(error.absolute_path) for error in refused] == [
        ["sources", 1, "payload"],
    ]
