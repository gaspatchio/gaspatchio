# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The policy axis: what picks the model points, and what the document says.

An artifact carries one policy by default and may carry several, on an axis
the envelope declares. Two things have to hold or the axis is worse than not
having one.

**A single-policy document is what it always was.** Every enrichment field is
the value itself rather than an array of one, so a consumer written against
the edition before the axis reads it unchanged. That is checked here by
exporting one policy two ways -- the older ``--policy-id`` spelling and the
newer ``--policies`` one -- and holding the two documents to each other field
by field.

**A selection says what it selected, and refuses what it cannot select
honestly.** Each refusal below has a test that reads the sentence and not
only the exit code: a sentence nobody asserts is a sentence that rots into
"Error: None" without anything failing.

The book these run over is deliberately not one this framework ships. Its ids
are strings, out of order, with gaps, one of them shaped like a slice, one
shaped like the word for the whole book, and one carried by two rows -- which
is what a real policy identifier looks like and what the grammar has to be
safe against. The tutorial books, whose ``point_id`` is an ``Int64`` starting
at 1 with no gaps, would let a selector that confused position with identity
pass every test in this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph.policies import (
    PolicySelectionError,
    select_policies,
)
from gaspatchio.frame.graph.row_identity import ROW_STAMP

if TYPE_CHECKING:
    from collections.abc import Sequence

runner = CliRunner()

# The awkward book, and the ids it carries in the order it carries them.
_BOOK = Path(__file__).resolve().parents[1] / "fixtures" / "policy-axis-book.parquet"
_IDS = (
    "POL-000343",
    "GB-2019-88231",
    "3:40",
    "POL-000012",
    "all",
    "DUP-7",
    "DUP-7",
    "ZZ-000001",
)

# A model small enough to run in a test and real enough to have a projection:
# a per-period column is what makes an axis cost anything, and an artifact
# whose every column held one value per policy would not exercise the arrays.
_MODEL = """
import datetime

from gaspatchio import ActuarialFrame, when


def main(af, params=None):
    mp = af.collect()
    af = ActuarialFrame(mp)
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_years",
        until_value=4,
        frequency="annual",
    )
    af.duration = af.month // 12
    af.attained_age = af.issue_age + af.duration
    af.reserve = af.sum_assured * 0.01 * (af.duration + 1)
    af.in_force = when(af.duration < af.policy_term).then(1.0).otherwise(0.0)
    return af
"""


@pytest.fixture
def model(tmp_path: Path) -> Path:
    """Write the model this file exports, and return its path."""
    written = tmp_path / "model.py"
    written.write_text(_MODEL)
    return written


def _book() -> pl.DataFrame:
    """Return the awkward book as it arrives."""
    return pl.read_parquet(_BOOK)


def _selected(*specs: str) -> tuple[tuple[int, str | None], ...]:
    """Return the rows and ids one selection reaches, over the awkward book."""
    return tuple(
        (entry.row, entry.policy_id)
        for entry in select_policies(
            specs, book=_book(), id_column="Policy number", source="book.parquet"
        )
    )


def _refusal(
    *specs: str,
    book: pl.DataFrame | None = None,
    kept: Sequence[int] | None = None,
    cut: str | None = None,
) -> str:
    """Return the sentence a selection was refused with."""
    with pytest.raises(PolicySelectionError) as raised:
        select_policies(
            specs,
            book=_book() if book is None else book,
            id_column="Policy number",
            source="book.parquet",
            kept=kept,
            cut=cut,
        )
    return str(raised.value)


def _advised_filter(said: str) -> str:
    """Return the ``--filter`` expression a refusal printed, verbatim.

    Read out of the sentence rather than written beside it, so that what a
    test executes is what a reader is told to run and the two cannot drift.
    """
    _, _, rest = said.partition("--filter ")
    return rest.split('"')[1]


def _export(model: Path, out: Path, *extra: str) -> Any:  # noqa: ANN401 -- the runner's own result
    """Run ``calc-graph`` over the awkward book and return the runner result."""
    return runner.invoke(
        app,
        ["calc-graph", str(model), str(_BOOK), "-o", str(out), *extra],
    )


# --- the grammar --------------------------------------------------------------


@pytest.mark.parametrize(
    "spec",
    [":3", "3:", "1:5", "::2", "-5:", ":-2", "2:7:3", "-6:-1:2", ":", "::"],
)
def test_a_slice_selects_what_python_selects(spec: str) -> None:
    """The row positions a slice reaches are ``ids[slice]``, and nothing else.

    The claim ``--policies 3:40`` makes is that it means what ``ids[3:40]``
    means, so the test is the comparison rather than a restatement of the
    rule. It runs over a book whose ids are *not* row numbers, because on a
    book where they are, an implementation that quietly matched ids would
    pass.
    """
    bounds = [None if part == "" else int(part) for part in spec.split(":")]
    if len(bounds) == 2:
        bounds.append(None)
    expected = list(_IDS)[slice(*bounds)]

    assert [policy_id for _, policy_id in _selected(spec)] == expected


def test_a_slice_that_reaches_nothing_is_refused_rather_than_returned_empty() -> None:
    """An axis with nothing on it is a document that says nothing about anything."""
    said = _refusal("5:2")

    assert "'5:2'" in said
    assert "8 policies" in said
    assert "book.parquet" in said
    assert ":1" in said


def test_ids_are_matched_as_text_in_the_order_they_were_named() -> None:
    """Commas mean identity, and identity is the id the book carries."""
    assert _selected("ZZ-000001,POL-000012") == (
        (7, "ZZ-000001"),
        (3, "POL-000012"),
    )


def test_a_term_shaped_like_a_slice_is_a_slice_whatever_the_book_carries() -> None:
    """The grammar decides by the term's own shape, never by what is in the book.

    This book carries a policy called ``3:40``, sitting at row 2. The term is
    still read as a slice -- rows 3 onward -- because a rule that changed
    meaning with the data would make one command line mean two things on two
    books. ``id:`` is what makes the policy reachable anyway, and the two
    answers being different is the whole of the point.
    """
    assert [policy_id for _, policy_id in _selected("3:40")] == list(_IDS)[3:40]
    assert _selected("id:3:40") == ((2, "3:40"),)


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("id:3:40", (2, "3:40")),
        ("id:all", (4, "all")),
        ("id:ZZ-000001", (7, "ZZ-000001")),
    ],
)
def test_the_escape_reaches_an_id_shaped_like_another_form(
    spec: str, expected: tuple[int, str]
) -> None:
    """``id:`` takes the rest of the term verbatim, whatever it looks like.

    Without it, a book whose ids collide with the grammar has policies no
    selection can name at all -- which is the failure this escape exists to
    prevent, and this book has two of them.
    """
    assert _selected(spec) == (expected,)


def test_all_is_every_policy_in_the_book() -> None:
    """One entry per row, in the order the book holds them."""
    assert [policy_id for _, policy_id in _selected("all")] == list(_IDS)


def test_a_term_that_is_none_of_the_forms_names_the_forms() -> None:
    """A book with no such id gets the refusal that says how to name one."""
    said = _refusal("NOT-A-POLICY")

    assert "'NOT-A-POLICY'" in said
    assert "'Policy number'" in said
    assert "8 policies" in said


def test_repeated_options_are_unioned_keeping_the_first_occurrence() -> None:
    """A policy named twice is one entry, at the position it was first asked for."""
    assert _selected(":2", "id:3:40", "POL-000343") == (
        (0, "POL-000343"),
        (1, "GB-2019-88231"),
        (2, "3:40"),
    )


# --- the refusals -------------------------------------------------------------


def test_an_id_more_than_one_row_answers_to_is_refused() -> None:
    """Three rows carrying one id make the id a question with three answers."""
    said = _refusal("DUP-7")

    assert "'DUP-7'" in said
    assert "2 rows" in said
    assert "--filter" in said
    assert "5:6" in said


def test_the_duplicate_id_refusal_names_a_filter_that_resolves_it() -> None:
    """The way through it offers is one it has checked against the book.

    The sentence used to recommend ``--filter`` in the abstract while the
    command resolved the id before the filter reached it, so following the
    advice produced the same refusal. It now
    names a column whose values tell the offending rows apart and prints
    the expression that leaves one of them.
    """
    assert _advised_filter(_refusal("DUP-7")) == "col('sum_assured') == 125000.0"


def test_the_refusal_s_own_advice_is_a_way_through() -> None:
    """The exact expression the refusal prints resolves the id it refused."""
    said = _refusal("DUP-7")
    cut = _advised_filter(said)
    kept = tuple(
        row for row, weight in enumerate(_book()["sum_assured"]) if weight == 125000.0
    )

    entries = select_policies(
        ["DUP-7"],
        book=_book(),
        id_column="Policy number",
        source="book.parquet",
        kept=kept,
        cut=cut,
    )

    assert [(entry.row, entry.policy_id) for entry in entries] == [(5, "DUP-7")]
    assert "among the 1 rows" in entries[0].why


def test_an_id_still_ambiguous_inside_the_cut_is_still_refused() -> None:
    """A cut that keeps both rows leaves the question with two answers."""
    said = _refusal("DUP-7", kept=(5, 6), cut="col('band') != 'nothing'")

    assert "2 rows" in said
    assert "'DUP-7'" in said


def test_a_cut_that_keeps_nothing_is_refused_before_the_selection() -> None:
    """An axis is made among the rows the cut keeps, and there are none."""
    said = _refusal(":1", kept=(), cut="col('issue_age') > 200")

    assert "keeps none of the 8 rows" in said
    assert "col('issue_age') > 200" in said


def test_an_id_asked_of_a_book_that_names_no_policy_column() -> None:
    """Identity needs a column that holds one, and this book has none."""
    with pytest.raises(PolicySelectionError) as raised:
        select_policies(
            ["POL-000343"],
            book=_book().drop("Policy number"),
            id_column=None,
            source="book.parquet",
        )

    assert "--policy-id-column" in str(raised.value)


def test_a_book_with_no_policy_column_can_still_be_walked_by_row() -> None:
    """A row position asks nothing of an id, so a book with none still answers."""
    entries = select_policies(
        [":2"],
        book=_book().drop("Policy number"),
        id_column=None,
        source="book.parquet",
    )

    assert [(entry.row, entry.policy_id) for entry in entries] == [(0, None), (1, None)]


def test_a_spread_over_a_column_the_book_does_not_hold() -> None:
    """A selection cannot order the book by a number the model has not computed."""
    said = _refusal("spread:3@pv_net_cf")

    assert "'pv_net_cf'" in said
    assert "as they arrive" in said
    assert "Policy number" in said


def test_a_spread_over_a_per_period_column() -> None:
    """A book cannot be ordered by a run of values, and the refusal says why."""
    book = _book().with_columns(
        pl.Series("monthly_fee", [[1.0, 2.0]] * 8, dtype=pl.List(pl.Float64))
    )
    said = _refusal("spread:3@monthly_fee", book=book)

    assert "'monthly_fee'" in said
    assert "one value per projection period" in said


def test_a_spread_finer_than_the_column_can_separate() -> None:
    """Past the column's own distinct values a spread returns the same policy twice."""
    said = _refusal("spread:5@band")

    assert "'band'" in said
    assert "2 distinct values" in said
    assert "at most 2" in said


def test_a_spread_walks_the_ordered_book_at_even_spacing() -> None:
    """Both ends included, and the middle evenly divided between them.

    Eight rows and three points put the walk at 0, 3.5 and 7, and the
    rounding is Python's own -- half to even, so 3.5 is row 4. The spacing
    is even to within a row, which is all an even spacing over a book whose
    length is not a multiple of the points asked for can be.
    """
    ordered = _book().sort("sum_assured")["Policy number"].to_list()
    chosen = [policy_id for _, policy_id in _selected("spread:3@sum_assured")]

    assert chosen == [ordered[0], ordered[4], ordered[-1]]


# --- the document -------------------------------------------------------------


def test_one_policy_is_written_exactly_as_it_was_before_the_axis(
    model: Path, tmp_path: Path
) -> None:
    """The older spelling and the newer one produce the same document.

    ``--policy-id 7`` is ``--policies 7``, and the enrichment on every node
    is the value itself rather than an array of one. Everything but the
    three fields that cannot be equal -- when it was written, and the two
    digests over that -- is held byte for byte.
    """
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    assert _export(model, old, "--policy-id", "POL-000343").exit_code == 0
    assert _export(model, new, "--policies", "POL-000343").exit_code == 0

    before = json.loads(old.read_text())
    after = json.loads(new.read_text())
    for document in (before, after):
        document.pop("created_at")
        document.pop("document_digest")

    assert before == after
    assert (
        not isinstance(before["nodes"][0]["value_sample"], list)
        or before["shape_is_the_columns_own"]
    )


def test_the_axis_records_the_row_and_the_id_on_every_entry(
    model: Path, tmp_path: Path
) -> None:
    """``why`` says how each policy came to be in the file, row and id both."""
    out = tmp_path / "graph.json"
    assert _export(model, out, "--policies", ":2").exit_code == 0
    document = json.loads(out.read_text())

    assert [entry["policy_id"] for entry in document["policies"]] == [
        "POL-000343",
        "GB-2019-88231",
    ]
    assert "row 0 of 8" in document["policies"][0]["why"]
    assert "row 1 of 8" in document["policies"][1]["why"]


def test_enrichment_is_the_head_of_the_axis_with_why_left_off(
    model: Path, tmp_path: Path
) -> None:
    """A consumer written against the earlier edition reads the first policy."""
    out = tmp_path / "graph.json"
    assert _export(model, out, "--policies", ":3").exit_code == 0
    document = json.loads(out.read_text())

    head = document["policies"][0]
    assert document["enrichment"] == {
        name: value for name, value in head.items() if name != "why"
    }
    assert "why" not in document["enrichment"]


def test_no_fingerprint_moves_with_the_axis(model: Path, tmp_path: Path) -> None:
    """A policy is no part of any identity, which is what makes the axis cheap."""
    one = tmp_path / "one.json"
    three = tmp_path / "three.json"
    assert _export(model, one, "--policies", ":1").exit_code == 0
    assert _export(model, three, "--policies", ":3").exit_code == 0

    before = json.loads(one.read_text())
    after = json.loads(three.read_text())

    assert before["graph_fingerprint"] == after["graph_fingerprint"]
    assert [node["fingerprint"] for node in before["nodes"]] == [
        node["fingerprint"] for node in after["nodes"]
    ]
    assert [node["local_fingerprint"] for node in before["nodes"]] == [
        node["local_fingerprint"] for node in after["nodes"]
    ]


def test_every_carried_policy_carries_its_own_values_and_its_own_trace(
    model: Path, tmp_path: Path
) -> None:
    """The walk-through travels for every policy, not only the first.

    A policy whose worked example is missing is a policy the document
    answers differently about, so the arrays are as long as the axis on
    every node that carries one.
    """
    out = tmp_path / "graph.json"
    assert _export(model, out, "--policies", ":3").exit_code == 0
    document = json.loads(out.read_text())
    reserve = next(node for node in document["nodes"] if node["id"] == "reserve@1")

    assert len(reserve["value_sample"]) == 3
    assert len(reserve["trace"]) == 3
    assert reserve["value_sample"][0] != reserve["value_sample"][1]
    assert all(step is not None for step in reserve["trace"])


def test_a_document_over_the_ceiling_names_its_weight_and_the_flag(
    model: Path, tmp_path: Path
) -> None:
    """The guard is in bytes over the assembled document, and says both numbers."""
    out = tmp_path / "graph.json"
    result = _export(model, out, "--policies", "all", "--max-size", "1024")

    assert result.exit_code == 3
    assert "--max-size" in result.output
    assert "1,024 bytes" in result.output
    assert not out.exists()


def test_a_selection_never_narrows_the_model_run(model: Path, tmp_path: Path) -> None:
    """The book runs whatever is selected, so a sampled value is a quotation.

    Narrowing the run would make a policy's own value depend on which other
    policies were asked for, wherever the model has a cross-row step -- a
    scenario axis is a cross-join on the model points, and a fold over one
    reads across rows. Every value this document carries is a quotation of a
    run that was performed, and a value that is only what it is because the
    export was narrow is a quotation of nothing.

    Measured on the frame the run wrote, which is the one thing that cannot
    be argued about how many rows it held.
    """
    selected = tmp_path / "selected.parquet"
    whole = tmp_path / "whole.parquet"
    assert (
        _export(
            model,
            tmp_path / "a.json",
            "--policies",
            ":2",
            "--output-file",
            str(selected),
        ).exit_code
        == 0
    )
    assert (
        _export(model, tmp_path / "b.json", "--output-file", str(whole)).exit_code == 0
    )

    assert pl.read_parquet(selected).height == len(_IDS)
    assert pl.read_parquet(whole).height == len(_IDS)


def test_a_policys_values_do_not_depend_on_who_else_was_selected(
    model: Path, tmp_path: Path
) -> None:
    """One policy exported alone and in company carries the same numbers.

    This is what "never narrows the run" buys, stated as the property a
    reader relies on rather than as the row count that delivers it.
    """
    alone = tmp_path / "alone.json"
    company = tmp_path / "company.json"
    assert _export(model, alone, "--policies", "id:3:40").exit_code == 0
    assert _export(model, company, "--policies", ":3").exit_code == 0

    one = json.loads(alone.read_text())
    several = json.loads(company.read_text())
    assert several["policies"][2]["policy_id"] == "3:40"
    assert [node["value_sample"][2] for node in several["nodes"]] == [
        node["value_sample"] for node in one["nodes"]
    ]
    assert [node["trace"][2] for node in several["nodes"]] == [
        node["trace"] for node in one["nodes"]
    ]


def test_a_multi_policy_document_validates(model: Path, tmp_path: Path) -> None:
    """The reading walks the axis, so the arrays are read rather than skipped."""
    from gaspatchio.frame.graph import validate_artifact

    out = tmp_path / "graph.json"
    assert _export(model, out, "--policies", ":3").exit_code == 0

    report = validate_artifact(out, deep=True)

    assert report.schema == "gaspatchio-graph/v0-preview.3"
    assert "enrichment" in report.sections
    assert [finding for finding in report.findings if finding.severity == "error"] == []


def test_a_node_disagreeing_with_the_axis_about_its_length_is_refused(
    model: Path, tmp_path: Path
) -> None:
    """The envelope declares the axis and a node is read along it by position."""
    from gaspatchio.frame.graph import validate_artifact

    out = tmp_path / "graph.json"
    assert _export(model, out, "--policies", ":3").exit_code == 0
    document = json.loads(out.read_text())
    document["nodes"][0]["value_sample"] = document["nodes"][0]["value_sample"][:2]

    said = [
        finding.message
        for finding in validate_artifact(document).findings
        if finding.severity == "error"
    ]

    # Two refusals, and the document earns both: the node is not as long as
    # the axis, and -- because the node this edit shortened is the id column
    # -- the entries can no longer show the policies they name.
    assert any("``policies`` axis of 3" in message for message in said)
    assert any("names policy" in message for message in said)


def _ids_of(entries: Sequence[tuple[int, str | None]]) -> list[str | None]:
    """Return just the ids, for a comparison that is about order rather than rows."""
    return [policy_id for _, policy_id in entries]


def test_a_refusal_never_offers_the_export_s_own_row_stamp_as_the_way_through() -> None:
    """Rows identical in every column the model wrote are told apart by a slice.

    The export stamps each row (``ROW_STAMP``) before the selection is made,
    and the stamp separates every row by construction: the duplicate-id
    refusal named ``--filter "col('__gaspatchio_export_row__') == 1"``, a
    filter on scaffolding the model never sees, and taking it put the stamp
    on the wire. With no column of the book that separates the rows, the
    ways through are the id column and a ``:N`` slice.
    """
    book = pl.DataFrame(
        {"pol": ["P1", "P2", "P2"], "sum_assured": [1.0, 2.0, 2.0]}
    ).with_row_index(ROW_STAMP)
    with pytest.raises(PolicySelectionError) as raised:
        select_policies(["P2"], book=book, id_column="pol", source="dup.parquet")

    said = str(raised.value)
    assert ROW_STAMP not in said
    assert "--policy-id-column" in said
    assert "'1:2'" in said
