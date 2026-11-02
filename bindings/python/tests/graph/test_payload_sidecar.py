# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The identities-only export and the payload files that stand beside it.

An inline artifact is a filing that *contains* the basis: the mortality
table the reserve was struck on is in the file, and a reader re-hashes it
without leaving the page. That is the right shape for a document handed
over once. It is the wrong shape for a repository, where ten quarters of
one unchanged basis are ten copies of the same three hundred kilobytes and
"did the basis move?" is a diff of two payloads rather than a glance.

The sidecar is the other half. The document keeps every identity and
carries no values; each base's values sit in one file beside it, named
after the identity the document already states. Wherever the store keeps
one file per name, ten filings then share one payload file; and the
question a supervisor asks -- *is this the same mortality basis you used
last quarter?* -- is answered by comparing two file names either way.

What is tested here is that the two halves say the same thing. Each file
re-hashes to the fingerprint it is named after, under the grammar section
13 names for its kind and with nothing read off the base it came from;
re-inlining the files reproduces the inline artifact entry by entry; and a
deep reading of the pair reaches the same verdict a deep reading of the
inline document reaches.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio._identity import content_sha_of, source_sha_of
from gaspatchio.assumptions import Table
from gaspatchio.curves import Curve
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.artifact import (
    ARTIFACT_FILE_NAME,
    DOCUMENT_DIGEST_FIELD,
    PAYLOAD_DIRECTORY,
    SOURCE_DIRECTORY,
    document_digest_of,
    payload_bytes,
    payload_file_name,
)
from gaspatchio.frame.lowering import artefacts
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

# What a consumer holding a table payload and the published grammar builds
# each column back as. Neutral names in, storage types out.
_POLARS_BY_NEUTRAL: dict[str, pl.DataType] = {
    "bool": pl.Boolean(),
    "i64": pl.Int64(),
    "f64": pl.Float64(),
    "str": pl.String(),
    "date": pl.Date(),
    "datetime": pl.Datetime(),
}

# What a non-finite float travels as, and what a consumer reads it back to
# before hashing.
_SENTINELS: dict[str, float] = {
    "NaN": float("nan"),
    "Infinity": float("inf"),
    "-Infinity": float("-inf"),
}

# The one entry kind whose payload is a frame of values rather than a
# recipe, and therefore the one that re-hashes under the content grammar.
_TABLE = "table"


# --- the models ---------------------------------------------------------------


def _mortality_table(name: str = "mortality") -> Table:
    """Build a one-dimension mortality table under the name given."""
    ages = list(range(20, 121))
    return Table(
        name=name,
        source=pl.DataFrame(
            {
                "age": ages,
                "rate": [round(0.000_5 + 0.000_4 * (age - 20), 6) for age in ages],
            }
        ),
        dimensions={"age": "age"},
        value="rate",
    )


def _a_model_reading_all_three_kinds() -> ActuarialFrame:
    """Return a model reading a table, a projection schedule and a yield curve.

    All three, because the sidecar's promise is one rule for every entry
    and the three do not hash alike: a table's fingerprint is a content
    hash over a frame of values, a schedule's and a curve's is a recipe
    stamp over the canonical form each publishes.
    """
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    frame = frame.projection.set(
        schedule=Schedule.from_calendar_grid(
            start_date=datetime.date(2026, 1, 31), n_periods=6, frequency="1M"
        )
    )
    frame.years_elapsed = frame.projection.t_years()
    curve = Curve.from_zero_rates(tenors=[1.0, 2.0, 3.0], rates=[0.02, 0.025, 0.03])
    frame.spot_rate = curve.spot_rate(frame.years_elapsed)
    frame.mortality_rate = _mortality_table().lookup(age=frame.issue_age)
    return frame


def _a_model_with_one_lookup() -> ActuarialFrame:
    """Return a model whose one rate comes out of a named mortality table."""
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    frame.mortality_rate = _mortality_table().lookup(age=frame.issue_age)
    return frame


# --- what a consumer does with what it fetched --------------------------------


def _content_sha_of(payload: dict[str, Any]) -> str:
    """Return the digest a consumer re-derives from a fetched table payload.

    The columns the payload declares, in the order it declares them, with
    the rows in the order it declares them and no re-sort. A string in a
    column declared ``f64`` is the sentinel for a non-finite float and is
    read back to the float first. Nothing here reads the table it came
    from -- which is the whole claim the file is making.
    """
    schema = {
        column["name"]: _POLARS_BY_NEUTRAL[column["dtype"]]
        for column in payload["columns"]
    }
    floating = [
        column["name"] for column in payload["columns"] if column["dtype"] == "f64"
    ]
    rows = [
        [
            _SENTINELS[value] if name in floating and isinstance(value, str) else value
            for name, value in zip(schema, row, strict=True)
        ]
        for row in payload["rows"]
    ]
    return content_sha_of(pl.DataFrame(rows, schema=schema, orient="row"))


def _digest_of(kind: str, payload: dict[str, Any]) -> str:
    """Return the digest section 13 has a consumer take over ``payload``."""
    if kind == _TABLE:
        return _content_sha_of(payload)
    return source_sha_of(payload)


def _fetched(directory: Path, fingerprint: str, folder: str = PAYLOAD_DIRECTORY) -> (
    dict[str, Any]
):
    """Return the payload a consumer fetches for one entry, parsed.

    The folder is the name of the section the entry belongs to, which is the
    filing's whole rule for where a payload sits: a base under
    ``assumptions/``, the model's own text under ``sources/``.
    """
    path = directory / folder / payload_file_name(fingerprint)
    parsed: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return parsed


def _re_inlined(document: dict[str, Any], directory: Path) -> dict[str, Any]:
    """Return ``document`` with every fetched payload put back where it came from.

    What a holder of the pair does to reach the form the inline export
    would have written: for each entry the document weighed, fetch the file
    named after its fingerprint and substitute it for the stand-in.

    **And re-seal, because this is a transforming holder.** The seal covers
    every byte of the document it was taken over, and putting the values back
    changes those bytes -- so carrying the sidecar document's seal forward
    would be publishing a digest over a file nobody holds, which is the one
    move section 13.1's fourth limit refuses. Of the three that section
    leaves, re-sealing is the one that reaches a conforming document, and it
    says what is true: this record is the one this holder assembled.
    """
    rebuilt = json.loads(json.dumps(document))
    for entry in rebuilt["assumptions"]:
        if "bytes" not in entry["payload"]:
            continue
        entry["payload"] = _fetched(directory, entry["fingerprint"])
    # The model's own text comes back the same way, out of its own folder.
    # A holder rebuilding the inline form fetches every payload the document
    # weighed, and the sources section is weighed on the same terms.
    for entry in rebuilt["sources"]:
        if "bytes" not in entry["payload"]:
            continue
        entry["payload"] = _fetched(
            directory, entry["fingerprint"], SOURCE_DIRECTORY
        )
    rebuilt.pop(DOCUMENT_DIGEST_FIELD, None)
    rebuilt[DOCUMENT_DIGEST_FIELD] = document_digest_of(rebuilt)
    return rebuilt


def _without_the_write_stamps(document: dict[str, Any]) -> dict[str, Any]:
    """Return ``document`` with ``created_at`` and the seal dropped.

    Two exports of one model are the same account written at two moments.
    The moment is meant to differ, and the seal is taken with the moment
    inside it, so the seal is meant to differ too -- one member that moved
    and one that moved because it did.
    """
    return {
        name: value
        for name, value in document.items()
        if name not in {"created_at", DOCUMENT_DIGEST_FIELD}
    }


# --- the pair, as one export writes it ----------------------------------------


def _exported_both_ways(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the inline artifact and the identities-only one, from one graph.

    One exporter, so the two documents are the same fold read twice and
    anything that differs between them is the payload carriage rather than
    the model.
    """
    exporter = GraphExporter(_a_model_reading_all_three_kinds())
    inline: dict[str, Any] = json.loads(exporter.export(include_tables="all"))
    beside: dict[str, Any] = json.loads(exporter.export_with_sidecar(directory))
    return inline, beside


# --- the document beside the payloads -----------------------------------------


def test_the_document_written_is_the_document_returned(tmp_path: Path) -> None:
    """The file on disk is the text the call handed back, byte for byte."""
    returned = GraphExporter(_a_model_with_one_lookup()).export_with_sidecar(tmp_path)

    written = (tmp_path / ARTIFACT_FILE_NAME).read_text("utf-8")

    assert written == returned


def test_the_document_beside_the_payloads_is_the_identities_only_document(
    tmp_path: Path,
) -> None:
    """No third carriage mode: the document is what ``include_tables=False`` writes."""
    exporter = GraphExporter(_a_model_with_one_lookup())

    slim = json.loads(exporter.export(include_tables=False))
    beside = json.loads(exporter.export_with_sidecar(tmp_path))

    assert _without_the_write_stamps(beside) == _without_the_write_stamps(slim)


def test_every_entry_the_producer_weighed_has_a_file_beside_it(
    tmp_path: Path,
) -> None:
    """The document is the index: an entry carrying a weight has values to fetch."""
    _, beside = _exported_both_ways(tmp_path)

    weighed = [entry for entry in beside["assumptions"] if "bytes" in entry["payload"]]
    assert len(weighed) == 3, "a table, a schedule and a curve were read"
    for entry in weighed:
        path = tmp_path / PAYLOAD_DIRECTORY / payload_file_name(entry["fingerprint"])
        assert path.is_file(), entry["name"]


def test_the_bytes_a_file_holds_are_the_bytes_the_entry_weighed(
    tmp_path: Path,
) -> None:
    """The stated fetch cost is the file's own size, not an estimate beside it."""
    _, beside = _exported_both_ways(tmp_path)

    for entry in beside["assumptions"]:
        path = tmp_path / PAYLOAD_DIRECTORY / payload_file_name(entry["fingerprint"])
        assert path.stat().st_size == entry["payload"]["bytes"], entry["name"]


# --- what a consumer holding one file can check -------------------------------


def test_a_fetched_payload_re_hashes_to_the_identity_it_is_named_after(
    tmp_path: Path,
) -> None:
    """The one check the sidecar exists to pass, for each of the three kinds.

    A consumer parses the file, hashes it under the grammar section 13
    names for its kind, and reaches the fingerprint the document declared
    and the file is named after. Nothing is read off the base itself: the
    re-hash goes through the hash helpers this module imports -- or, for a
    consumer outside this package, a stdlib reimplementation of section
    12.3's two grammars -- and through no part of the exporter that wrote
    the file.
    """
    _, beside = _exported_both_ways(tmp_path)

    for entry in beside["assumptions"]:
        fetched = _fetched(tmp_path, entry["fingerprint"])

        assert _digest_of(entry["kind"], fetched) == entry["fingerprint"], entry["name"]


def test_the_file_name_carries_the_identity_a_consumer_checks_it_against(
    tmp_path: Path,
) -> None:
    """A file that travelled alone still says which identity it claims to be."""
    _, beside = _exported_both_ways(tmp_path)

    for entry in beside["assumptions"]:
        name = payload_file_name(entry["fingerprint"])
        fetched = _fetched(tmp_path, entry["fingerprint"])

        assert name == f"{entry['fingerprint'].replace(':', '-')}.json"
        assert _digest_of(entry["kind"], fetched) in name.replace("-", ":")


# --- the round trip -----------------------------------------------------------


def test_re_inlining_the_sidecar_reproduces_the_inline_artifact(
    tmp_path: Path,
) -> None:
    """The pair carries what the one file carries, entry by entry and whole."""
    inline, beside = _exported_both_ways(tmp_path)

    rebuilt = _re_inlined(beside, tmp_path)

    for rebuilt_entry, inline_entry in zip(
        rebuilt["assumptions"], inline["assumptions"], strict=True
    ):
        assert rebuilt_entry == inline_entry, inline_entry["name"]
    assert _without_the_write_stamps(rebuilt) == _without_the_write_stamps(inline)


def test_the_re_inlined_document_reads_as_the_inline_one_reads(
    tmp_path: Path,
) -> None:
    """A deep reading of the pair reaches the inline document's verdict.

    Not merely "it still validates": the findings are the same findings,
    so nothing about fetching the values leaves a reader with a different
    account of the file than the reader who never had to fetch them.
    """
    inline, beside = _exported_both_ways(tmp_path)

    rebuilt = validate_artifact(_re_inlined(beside, tmp_path), deep=True)
    whole = validate_artifact(inline, deep=True)

    assert rebuilt.ok
    assert [finding.to_dict() for finding in rebuilt.findings] == [
        finding.to_dict() for finding in whole.findings
    ]


def test_the_document_alone_is_conforming_and_says_which_digests_it_did_not_check(
    tmp_path: Path,
) -> None:
    """A reader holding only the document is told exactly what they are missing."""
    _, beside = _exported_both_ways(tmp_path)

    report = validate_artifact(beside, deep=True)

    assert report.ok
    remarks = [
        finding
        for finding in report.findings
        if finding.where.startswith("/assumptions/")
    ]
    assert len(remarks) == 3
    assert all(finding.severity == "warning" for finding in remarks)
    assert all("read rather than checked" in finding.message for finding in remarks)


# --- what the filing shape buys -----------------------------------------------


def test_a_basis_that_did_not_move_is_one_file_name_in_two_filings(
    tmp_path: Path,
) -> None:
    """Quarter over quarter, "did the basis change?" is a name comparison.

    Two models reading the same mortality table name one payload file
    between them, and the bytes under that name are the same bytes. The
    name is what the saving rests on: in a store keeping one file per
    name, ten filings of an unchanged basis stop being ten copies of it.
    Filed into two directories, as here, they are two identical files --
    which is why what follows compares the bytes across the pair.
    """
    store = tmp_path / "repository"
    first = json.loads(
        GraphExporter(_a_model_with_one_lookup()).export_with_sidecar(store / "q1")
    )
    second = json.loads(
        GraphExporter(_a_model_with_one_lookup()).export_with_sidecar(store / "q2")
    )

    first_names = [
        payload_file_name(entry["fingerprint"]) for entry in first["assumptions"]
    ]
    second_names = [
        payload_file_name(entry["fingerprint"]) for entry in second["assumptions"]
    ]

    assert first_names == second_names
    assert (store / "q1" / PAYLOAD_DIRECTORY / first_names[0]).read_bytes() == (
        store / "q2" / PAYLOAD_DIRECTORY / second_names[0]
    ).read_bytes()


def test_a_base_this_process_cannot_reach_gets_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An entry with nothing to weigh has nothing to write, and says so itself.

    The document already discriminates the two: an entry left out for its
    size states the weight of what is beside it, and one whose values this
    process cannot reach states no weight at all. So the reader is never
    left guessing which entries have a file -- and no new field was needed
    to tell them.
    """
    exporter = GraphExporter(_a_model_with_one_lookup())
    monkeypatch.setattr(artefacts, "_TABLES", {})

    beside = json.loads(exporter.export_with_sidecar(tmp_path))

    assert beside["assumptions"][0]["payload"] == {"omitted": "unavailable"}
    assert not list((tmp_path / PAYLOAD_DIRECTORY).glob("*.json"))


def test_the_directory_is_made_where_it_does_not_exist(tmp_path: Path) -> None:
    """A caller names where the filing goes; they do not have to build it first."""
    where = tmp_path / "filings" / "2026-Q1"

    GraphExporter(_a_model_with_one_lookup()).export_with_sidecar(where)

    assert (where / ARTIFACT_FILE_NAME).is_file()
    assert (where / PAYLOAD_DIRECTORY).is_dir()


def test_the_payload_serialisation_is_the_one_the_entry_is_weighed_in(
    tmp_path: Path,
) -> None:
    """One function writes the file and measures the entry, so the two cannot part."""
    _, beside = _exported_both_ways(tmp_path)

    for entry in beside["assumptions"]:
        path = tmp_path / PAYLOAD_DIRECTORY / payload_file_name(entry["fingerprint"])

        assert path.read_bytes() == payload_bytes(json.loads(path.read_text("utf-8")))
