# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every artifact says which book it was built over, and a comparison reads it.

Two exports of one model over two different in-force files used to compare as
``drift: False`` with nothing under ``calculations`` and nothing under
``data``, unless the caller had remembered to hand each export a
``ModelIdentity`` naming the file. The model never reads a model point by
name, so nothing in the graph moves when the policies do, and the one field
that could have said so was the one a caller had to fill in.

Now every export records a content digest of the book it was built over --
the columns the model reads, in name order, under the specification's content
grammar -- and ``diff_artifacts`` reports a changed book with no argument.
The digest is the one a result manifest records as ``inputs_digest`` when the
engine was handed the book itself, so a document and such a result can be
matched by the data behind them.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines.protocol import digest_of_inputs
from gaspatchio.frame.graph import (
    DataChange,
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    build_artifact,
    diff_artifacts,
    document_digest_of,
    fold,
    inspect_execution,
    validate_artifact,
)
from gaspatchio.scenarios import with_scenarios

# --- the book, and the model run over it ------------------------------------

_BOOK = pl.DataFrame(
    {
        "policy_id": ["P1", "P2", "P3"],
        "sum_assured": [100_000.0, 250_000.0, 50_000.0],
        "mortality_rate": [0.0012, 0.0031, 0.0008],
        "adviser_note": ["new", "renewal", "new"],
    }
)


def _claims_model(book: pl.DataFrame) -> ActuarialFrame:
    """Return a model that reads two columns and hands back the policy id.

    The adviser's note arrives with the book, is read by no line and is
    dropped before the model finishes, which makes it the column a revised
    book can change without changing anything the model's numbers rest on.
    """
    af = ActuarialFrame(book)
    af.death_claims = af.sum_assured * af.mortality_rate
    return af.drop("adviser_note")


def _exported(
    af: ActuarialFrame, config: GraphExportConfig | None = None
) -> dict[str, Any]:
    """Return the artifact the model exports, parsed."""
    document: dict[str, Any] = json.loads(GraphExporter(af).export(config=config))
    return document


# --- what the member records ---------------------------------------------------


def test_every_export_records_the_book_it_was_built_over() -> None:
    """No argument asked for it: the digest is over the columns the model reads."""
    document = _exported(_claims_model(_BOOK))

    assert document["book"] == {
        "columns": ["mortality_rate", "policy_id", "sum_assured"],
        "digest": digest_of_inputs(
            _BOOK, ["mortality_rate", "policy_id", "sum_assured"]
        ),
    }


def test_the_book_s_digest_is_the_one_a_result_manifest_records() -> None:
    """The columns are the required inputs an engine is handed, digested alike.

    ``inputs_digest`` is taken over the input columns the executable document
    names as required, in name order; the artifact's book is taken over the
    same columns by the same function, so an engine handed the book itself
    records the book's digest.
    """
    rates = pl.DataFrame({"product": ["term", "whole"], "rate": [0.05, 0.03]})
    book = pl.DataFrame(
        {"product": ["term", "whole"], "premium": [1_200.0, 900.0], "age": [40, 50]}
    )
    af = ActuarialFrame(book).join(rates, on="product")
    af.commission = af.premium * af.rate
    document = json.loads(GraphExporter(af).export(profile="executable"))

    required = [
        requirement.column
        for requirement in inspect_execution(document).required_inputs
    ]

    assert document["book"]["columns"] == sorted(required)
    assert document["book"]["digest"] == digest_of_inputs(book, required)


def test_the_book_is_the_one_the_frame_was_handed_after_a_timeline_and_a_freeze() -> (
    None
):
    """A timeline explodes the frame and a freeze replaces its plan; the book stays.

    The digest is of the policy data the model was built over, not of the
    shape the model put it in, so the book a projected and frozen model
    records is the book it started from.
    """
    af = ActuarialFrame(_BOOK)
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    af.claims = af.sum_assured * af.mortality_rate
    af = af.materialize()
    af.reserve = af.claims * 0.5
    document = _exported(af)

    assert document["book"]["digest"] == digest_of_inputs(
        _BOOK, document["book"]["columns"]
    )


def test_the_book_is_the_one_the_frame_was_handed_under_a_scenario_axis() -> None:
    """A scenario axis crossed onto the book is the model's, not the book's.

    The axis widens every row into one per scenario and brings a column the
    book never held; the digest is of the policies the model was run over,
    once each, as the frame was handed them.
    """
    af = with_scenarios(ActuarialFrame(_BOOK), ["BASE", "UP", "DOWN"])
    af.claims = af.sum_assured * af.mortality_rate
    document = _exported(af)

    assert "scenario_id" not in document["book"]["columns"]
    assert document["book"]["digest"] == digest_of_inputs(
        _BOOK, document["book"]["columns"]
    )


def test_the_book_is_the_one_the_frame_was_handed_after_values_came_back() -> None:
    """Values that leave the frame and come back through ``continue_from=``.

    The frame they come back on is the same model one step further on, built
    over the same book, so the book it records is the one the model started
    from -- not the values handed back, which here have one column changed
    outside the frame.
    """
    af = ActuarialFrame(_BOOK)
    af.claims = af.sum_assured * af.mortality_rate
    changed = af.collect().with_columns(pl.col("sum_assured") * 2)
    back = ActuarialFrame(changed, continue_from=af)
    back.reserve = back.claims * 10
    document = _exported(back)

    assert document["book"]["digest"] == digest_of_inputs(
        _BOOK, document["book"]["columns"]
    )
    assert document["book"]["digest"] != digest_of_inputs(
        changed, document["book"]["columns"]
    )


def test_a_graph_with_no_book_beside_it_says_so_rather_than_naming_one() -> None:
    """Built from the calculations alone, the document cannot vouch for a book."""
    af = _claims_model(_BOOK)

    document = build_artifact(fold(af))

    assert document["book"]["columns"] == ["mortality_rate", "policy_id", "sum_assured"]
    assert document["book"]["digest"]["omitted"] == "unavailable"
    assert document["book"]["digest"]["detail"].startswith(
        "No book was handed to the export"
    )
    assert not [
        finding
        for finding in validate_artifact(document).findings
        if "book" in finding.where
    ]


def test_a_book_the_grammar_cannot_read_is_unavailable_not_a_failed_export() -> None:
    """A column type the content grammar cannot read stops the digest, not the export.

    The policy term arrives as a duration, is read by one line and is then
    dropped: the model rests on it, and the content grammar has no reading of
    a duration -- its unit lives in the engine -- so the document says it
    could not vouch for its book.
    """
    termed = _BOOK.with_columns(pl.Series("term", [datetime.timedelta(days=3_650)] * 3))
    af = ActuarialFrame(termed)
    af.term_days = af["term"].polars_native().dt.total_days()
    af = af.drop("term")

    document = _exported(af)

    assert "term" in document["book"]["columns"]
    assert document["book"]["digest"]["omitted"] == "unavailable"
    assert "'term'" in document["book"]["digest"]["detail"]
    assert validate_artifact(document).ok


# --- a column held as categories -----------------------------------------------


def _noting_model(book: pl.DataFrame) -> ActuarialFrame:
    """Return a model that reads the adviser's note and then drops it.

    A column held as categories is refused where the finished frame would
    hold it, because the node record has no name for its type. Read on the
    way and dropped, its values never travel -- only the book's digest reads
    it -- so the model rests on it and the export goes ahead.
    """
    af = ActuarialFrame(book)
    af.renewal = af.adviser_note == "renewal"
    return af.drop("adviser_note")


@pytest.mark.parametrize(
    "categories",
    [pl.Categorical(), pl.Enum(["new", "renewal"])],
    ids=["categorical", "enum"],
)
def test_a_book_held_as_categories_is_the_book_held_as_text(
    categories: pl.DataType,
) -> None:
    """The dictionary in front of the strings is storage; the strings are the book.

    The same policies extracted by a pipeline that keeps the note as a
    category and by one that keeps it as text are one book, as an ``Int32``
    and an ``Int64`` holding the same numbers are.
    """
    coded = _BOOK.with_columns(pl.col("adviser_note").cast(categories))

    as_text = _exported(_noting_model(_BOOK))
    as_categories = _exported(_noting_model(coded))

    assert "adviser_note" in as_text["book"]["columns"]
    assert isinstance(as_text["book"]["digest"], str)
    assert as_categories["book"] == as_text["book"]


def test_two_books_held_as_categories_are_two_books() -> None:
    """Read as text, a category-coded book is compared like any other."""
    coded = _BOOK.with_columns(pl.col("adviser_note").cast(pl.Categorical))
    before = _exported(_noting_model(coded))
    after = _exported(_noting_model(coded.with_columns(pl.col("sum_assured") * 2)))

    report = diff_artifacts(before, after)

    assert report.drift
    assert report.data == (
        DataChange(
            "model_points", None, before["book"]["digest"], after["book"]["digest"]
        ),
    )


def test_the_digest_reads_a_category_as_its_text_inside_a_list_too() -> None:
    """A list of categories is a list of the strings they stand for."""
    as_text = pl.DataFrame({"band": ["a", "b", None], "bands": [["a"], ["b", "a"], []]})
    coded = as_text.with_columns(
        pl.col("band").cast(pl.Categorical),
        pl.col("bands").cast(pl.List(pl.Categorical)),
    )

    assert digest_of_inputs(coded, ["band", "bands"]) == digest_of_inputs(
        as_text, ["band", "bands"]
    )


@pytest.mark.parametrize(
    "dropped", [(), ("mortality_rate",)], ids=["kept", "read-then-dropped"]
)
def test_the_polars_reference_records_the_book_s_own_digest(
    dropped: tuple[str, ...],
) -> None:
    """A Polars run is handed the frame's own book, so it records that book's digest.

    An input the model read and then dropped counts on both sides: the
    finished frame no longer holds it, and the book the numbers rest on does.
    """
    from gaspatchio.engines.reference import polars_reference

    af = ActuarialFrame(_BOOK)
    af.death_claims = af.sum_assured * af.mortality_rate
    af = af.drop("adviser_note", *dropped)
    _, manifest = polars_reference(af)
    document = _exported(af)

    assert "mortality_rate" in document["book"]["columns"]
    assert manifest.inputs_digest == document["book"]["digest"]


def test_the_engine_door_takes_no_digest_of_the_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A document handed to an engine leaves the digest to the engine.

    The engine digests the inputs it runs over into its own result manifest,
    so a digest taken in the door as well is a pass over every required
    column of the book, paid on every run and read by nothing. A document
    that is filed still takes it.
    """
    from gaspatchio.frame.graph import artifact

    taken: list[list[str]] = []
    real = artifact.digest_of_inputs

    def counted(frame: pl.DataFrame, columns: list[str]) -> str:
        taken.append(list(columns))
        return real(frame, columns)

    monkeypatch.setattr(artifact, "digest_of_inputs", counted)
    document, _ = _claims_model(_BOOK)._for_an_engine()  # noqa: SLF001 -- the door

    assert taken == []
    assert document["book"]["columns"] == ["mortality_rate", "policy_id", "sum_assured"]
    assert document["book"]["digest"]["omitted"] == "unavailable"
    assert "engine" in document["book"]["digest"]["detail"]
    assert isinstance(_exported(_claims_model(_BOOK))["book"]["digest"], str)
    assert len(taken) == 1


def test_one_exporter_takes_the_book_s_digest_once_for_two_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second document over the same book reuses the digest the first took.

    A results file's manifest names the book, and so does the audit file of
    the same run, written after it. The digest is a function of the book and
    the columns alone, so a second pass over every column the model reads
    would be paid for the same answer. A new exporter takes it afresh.
    """
    from gaspatchio.frame.graph import artifact

    taken: list[list[str]] = []
    real = artifact.digest_of_inputs

    def counted(frame: pl.DataFrame, columns: list[str]) -> str:
        taken.append(list(columns))
        return real(frame, columns)

    monkeypatch.setattr(artifact, "digest_of_inputs", counted)
    af = _claims_model(_BOOK)
    values = af.collect()
    exporter = GraphExporter(af)

    first = json.loads(exporter.export(include_tables=False, seal=False))
    second = json.loads(exporter.export(values))

    assert len(taken) == 1
    assert second["book"] == first["book"]
    assert second["book"]["digest"] == digest_of_inputs(
        _BOOK, ["mortality_rate", "policy_id", "sum_assured"]
    )
    assert json.loads(GraphExporter(af).export())["book"] == first["book"]
    assert len(taken) == 2


# --- what a comparison reads off it -------------------------------------------


def test_two_books_are_data_drift_with_no_argument_given() -> None:
    """The quarter's new in-force, compared with last quarter's: the book moved."""
    revised = _BOOK.with_columns(pl.col("sum_assured") * 1.1)
    before = _exported(_claims_model(_BOOK))
    after = _exported(_claims_model(revised))

    report = diff_artifacts(before, after)

    assert report.drift
    assert report.calculations == ()
    assert report.data == (
        DataChange(
            "model_points",
            None,
            before["book"]["digest"],
            after["book"]["digest"],
        ),
    )


def test_one_book_exported_twice_is_no_drift() -> None:
    """The same model over the same data, written at two moments, moved nothing."""
    report = diff_artifacts(
        _exported(_claims_model(_BOOK)), _exported(_claims_model(_BOOK))
    )

    assert not report.drift


def test_a_change_where_the_model_does_not_read_is_no_drift() -> None:
    """The adviser's note moved and no number could have: the book is the same."""
    renoted = _BOOK.with_columns(pl.Series("adviser_note", ["x", "y", "z"]))
    before = _exported(_claims_model(_BOOK))
    after = _exported(_claims_model(renoted))

    report = diff_artifacts(before, after)

    assert "adviser_note" not in after["book"]["columns"]
    assert not report.drift


def test_the_same_book_in_another_column_order_is_one_book() -> None:
    """The digest is taken in name order, so the file's own layout is not content."""
    shuffled = _BOOK.select(sorted(_BOOK.columns, reverse=True))

    report = diff_artifacts(
        _exported(_claims_model(_BOOK)), _exported(_claims_model(shuffled))
    )

    assert not report.drift


def test_a_model_identity_still_records_the_file_it_names() -> None:
    """The caller's account of the run's file stays; the book is judged by content.

    Two runs over one book whose callers named different files -- the same
    data written out twice -- are one book. Two runs over different books are
    drift, and the entry is named by the file the run said it read.
    """

    def stamped(book: pl.DataFrame, path: str, stamp: str) -> dict[str, Any]:
        identity = ModelIdentity(
            label="claims", model_points={"path": path, "fingerprint": stamp}
        )
        return _exported(_claims_model(book), GraphExportConfig(model=identity))

    q1 = stamped(_BOOK, "inforce_q1.parquet", "sha256:" + "a" * 64)
    rewritten = stamped(_BOOK, "inforce_q1_copy.parquet", "sha256:" + "b" * 64)
    q2 = stamped(
        _BOOK.with_columns(pl.col("mortality_rate") * 2),
        "inforce_q2.parquet",
        "sha256:" + "c" * 64,
    )

    assert q1["model"]["model_points"] == {
        "path": "inforce_q1.parquet",
        "fingerprint": "sha256:" + "a" * 64,
    }
    assert q1["model"]["label"] == "claims"
    assert not diff_artifacts(q1, rewritten).drift
    assert diff_artifacts(q1, q2).data == (
        DataChange(
            "model_points",
            "inforce_q2.parquet",
            q1["book"]["digest"],
            q2["book"]["digest"],
        ),
    )


def test_a_document_that_states_no_book_is_compared_on_the_file_it_names() -> None:
    """Where either side has no digest, the run's own account of its file decides."""

    def without_a_book(stamp: str) -> dict[str, Any]:
        return build_artifact(
            fold(_claims_model(_BOOK)),
            config=GraphExportConfig(
                model=ModelIdentity(
                    model_points={"path": "inforce.parquet", "fingerprint": stamp}
                )
            ),
        )

    report = diff_artifacts(
        without_a_book("sha256:" + "a" * 64), without_a_book("sha256:" + "b" * 64)
    )

    assert report.data == (
        DataChange(
            "model_points",
            "inforce.parquet",
            "sha256:" + "a" * 64,
            "sha256:" + "b" * 64,
        ),
    )


def _termed(book: pl.DataFrame) -> ActuarialFrame:
    """Return a model resting on a column the content grammar cannot read.

    The policy term arrives as a duration, is read by one line and is then
    dropped, so the book's digest cannot be taken and the document says so.
    """
    af = ActuarialFrame(
        book.with_columns(pl.Series("term", [datetime.timedelta(days=3_650)] * 3))
    )
    af.term_days = af["term"].polars_native().dt.total_days()
    return af.drop("term")


def test_two_books_neither_could_digest_are_drift_naming_why() -> None:
    """A book the export could not vouch for is never read as the same book.

    Neither document states a digest of its book and neither names a file for
    its policy data, so nothing is left to compare the two books on. That is
    not "nothing moved": the entry says the books could not be compared, and
    why, and the comparison reports drift.
    """
    before = _exported(_termed(_BOOK))
    after = _exported(_termed(_BOOK.with_columns(pl.col("sum_assured") * 2)))

    report = diff_artifacts(before, after)

    assert report.drift
    (entry,) = report.data
    assert (entry.kind, entry.name, entry.before, entry.after) == (
        "model_points",
        None,
        None,
        None,
    )
    assert entry.reason is not None
    assert "could not be compared" in entry.reason
    assert "'term'" in entry.reason
    assert report.to_dict()["data"][0]["reason"] == entry.reason


def test_a_document_with_no_book_beside_it_is_drift_naming_why() -> None:
    """A graph written from its calculations alone leaves nothing to compare."""
    written = build_artifact(fold(_claims_model(_BOOK)))

    report = diff_artifacts(written, written)

    assert report.drift
    (entry,) = report.data
    assert entry.kind == "model_points"
    assert entry.reason is not None
    assert "no book was handed to the export" in entry.reason.lower()


def test_the_reason_is_the_sentence_the_audit_view_writes() -> None:
    """The comparison page reads the two books by the same rule, in the same words.

    ``viewer/test/compare.test.ts`` holds the page to this exact sentence, so
    a reviewer reading the page and one reading ``gspio diff`` read one text.
    """
    written = build_artifact(fold(_claims_model(_BOOK)))

    (entry,) = diff_artifacts(written, written).data

    assert entry.reason == (
        "The two books could not be compared: neither document states a digest "
        "of its book (No book was handed to the export: the graph was written "
        "from its calculations alone, with no policy data beside it), and "
        "neither run named a file for its policy data to compare instead. To "
        "compare them, export each model from the frame built over its book, "
        "with every column the model reads in a type the format names, or name "
        "each run's file with "
        'ModelIdentity.of("model.py", model_points="points.parquet"), passed '
        "to the export as GraphExportConfig(model=...)."
    )


def test_a_document_written_before_the_book_is_drift_naming_why() -> None:
    """One side predates the member and names no file: the books cannot be compared."""
    later = _exported(_claims_model(_BOOK))
    earlier = dict(later)
    del earlier["book"]

    report = diff_artifacts(earlier, later)

    assert report.drift
    (entry,) = report.data
    assert entry.before is None
    assert entry.after == later["book"]["digest"]
    assert entry.reason is not None
    assert "records no book" in entry.reason


def test_undigested_books_still_compare_on_the_files_both_runs_named() -> None:
    """Where both runs named the same file, the file decides, as it always has."""
    identity = ModelIdentity(
        model_points={"path": "inforce.parquet", "fingerprint": "sha256:" + "a" * 64}
    )
    config = GraphExportConfig(model=identity)

    report = diff_artifacts(
        _exported(_termed(_BOOK), config), _exported(_termed(_BOOK), config)
    )

    assert not report.drift


# --- what the validator holds the member to -------------------------------------


def _resealed(document: dict[str, Any]) -> dict[str, Any]:
    """Return ``document`` with its seal taken again over what it now says."""
    document["document_digest"] = document_digest_of(document)
    return document


def test_the_book_the_model_was_built_over_passes_the_deep_reading() -> None:
    """Holding the in-force file, a reviewer checks the filing is an account of it."""
    document = _exported(_claims_model(_BOOK))

    verdict = validate_artifact(document, deep=True, book=_BOOK)

    assert verdict.ok, [finding.message for finding in verdict.findings]


def test_another_book_is_refused_by_the_deep_reading_naming_both_digests() -> None:
    """A filing matched to the wrong in-force file is the mistake this catches."""
    document = _exported(_claims_model(_BOOK))
    other = _BOOK.with_columns(pl.col("sum_assured") + 1.0)

    verdict = validate_artifact(document, deep=True, book=other)

    assert not verdict.ok
    (refused,) = [one for one in verdict.findings if one.where == "/book"]
    assert refused.severity == "error"
    assert document["book"]["digest"] in refused.message
    assert digest_of_inputs(other, document["book"]["columns"]) in refused.message


def test_a_book_handed_to_the_validator_is_checked_without_the_deep_reading() -> None:
    """Handing over the in-force file is the request; ``deep`` is not a second one.

    A reviewer checking a filing against the in-force file passes the file
    and nothing else. A check that ran only under ``deep=True`` answered them
    ``ok`` over the wrong book, which is worse than not offering the check.
    """
    document = _exported(_claims_model(_BOOK))
    other = _BOOK.with_columns(pl.col("sum_assured") * 9)

    verdict = validate_artifact(document, book=other)

    assert not verdict.ok
    (refused,) = [one for one in verdict.findings if one.where == "/book"]
    assert refused.severity == "error"
    assert document["book"]["digest"] in refused.message
    assert validate_artifact(document, book=_BOOK).ok


@pytest.mark.parametrize(
    ("columns", "said"),
    [
        (["sum_assured", "policy_id", "mortality_rate"], "not in name order"),
        (["adviser_note", "mortality_rate", "policy_id", "sum_assured"], "no line"),
    ],
    ids=["out-of-order", "a-column-nothing-reads"],
)
def test_the_book_s_columns_are_held_to_what_the_model_reads(
    columns: list[str], said: str
) -> None:
    """A list a reader cannot take the digest over again is refused by name."""
    document = _exported(_claims_model(_BOOK))
    document["book"]["columns"] = columns

    verdict = validate_artifact(_resealed(document))

    assert not verdict.ok
    assert any(one.where == "/book" and said in one.message for one in verdict.findings)


def test_a_digest_that_leaves_out_a_column_the_model_reads_is_a_warning() -> None:
    """Coverage short of what the model reads weakens "same book", and is said."""
    document = _exported(_claims_model(_BOOK))
    document["book"]["columns"] = ["policy_id", "sum_assured"]

    verdict = validate_artifact(_resealed(document))

    (warned,) = [one for one in verdict.findings if one.where == "/book"]
    assert warned.severity == "warning"
    assert "'mortality_rate'" in warned.message


def test_a_document_written_without_its_book_is_refused_by_the_schema() -> None:
    """Required from this edition's book line: every conforming document states one."""
    document = _exported(_claims_model(_BOOK))
    del document["book"]

    verdict = validate_artifact(_resealed(document))

    assert not verdict.ok
    assert any(one.section == "schema" for one in verdict.findings)
