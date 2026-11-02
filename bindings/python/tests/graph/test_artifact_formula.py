# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The formula an exported node carries is the line the model's author wrote.

``formula`` is the audit surface: it is what a reviewer reads to see the
calculation, and what a comparison between two quarters is a comparison of.
So it carries the right-hand side as it was typed, and not the engine's own
rendering of the same calculation -- which says the same thing about the
model and says it differently every time the engine changes how it prints an
expression. A base artifact that churns on that is one nobody can compare
quarter to quarter, which is the whole purpose of the graph-level identity.

The engine's rendering is still reachable, because a reader chasing a number
wants to see what actually ran. It travels in the ``gaspatchio_lowered``
facet, which is off unless it is asked for, and the envelope announces it by
the same act that emits it.

Where no single written expression defines a column -- a batch call, whatever
the number of columns it defined, a rename, a join, the timeline's own
configuration, a date derivation -- the field is null, and the null is the
claim. The door is the test, not the number of siblings behind it.

What the field does carry is free-form author text rather than a normalised
expression: the segment the right-hand side occupies, newlines, continuation
indentation, interior comments and all. Most models below are written the way
a model is written, one statement per column, because the text of those
statements is the thing under test; the two that are not are written the
other ways an author writes, for the same reason.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import polars as pl

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter


def _artifact(af: ActuarialFrame) -> dict[str, Any]:
    """Return ``af``'s exported artifact, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export())
    return artifact


def _artifact_carrying_the_engine_rendering(af: ActuarialFrame) -> dict[str, Any]:
    """Return ``af``'s artifact with the engine's rendering asked for."""
    artifact: dict[str, Any] = json.loads(
        GraphExporter(af).export(include_lowered=True)
    )
    return artifact


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found: list[dict[str, Any]] = [
        node for node in artifact["nodes"] if node["id"] == node_id
    ]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def _a_two_column_model() -> ActuarialFrame:
    """Return a model of two arriving columns and one calculation over them."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    af.death_claims = af.sum_assured * af.mortality_rate
    return af


def _a_model_with_a_wrapped_conditional() -> ActuarialFrame:
    """Return a model whose second write of a column spans several lines.

    The maturity test is written the way an actuary writes one, over three
    lines, so what the export carries can be checked against the whole
    statement rather than against its first physical line.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "initial_policies": [1_000.0, 2_500.0],
                "mortality_rate": [0.001_23, 0.002_04],
                "policy_term": [10, 20],
                "elapsed_years": [10, 5],
            }
        )
    )
    af.policies_in_force = af.initial_policies * (1.0 - af.mortality_rate)
    af.policies_in_force = (
        when(af.elapsed_years >= af.policy_term)
        .then(0.0)
        .otherwise(af.policies_in_force)
    )
    return af


def _a_model_using_a_multi_column_call() -> ActuarialFrame:
    """Return a model that defines two columns in one call."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "annual_premium": [450.0, 1_200.0],
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    return af.with_columns(
        (pl.col("annual_premium") * 0.05).alias("expenses"),
        (pl.col("sum_assured") * pl.col("mortality_rate")).alias("death_claims"),
    )


def _a_model_using_a_single_column_call() -> ActuarialFrame:
    """Return a model whose one batch call defined exactly one column."""
    af = ActuarialFrame(pl.DataFrame({"annual_premium": [450.0, 1_200.0]}))
    return af.with_columns((pl.col("annual_premium") * 0.05).alias("expenses"))


def _a_model_written_by_a_tuple_assignment() -> ActuarialFrame:
    """Return a model whose one statement writes two columns from one tuple."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "annual_premium": [450.0, 1_200.0],
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    af.expenses, af.death_claims = (
        af.annual_premium * 0.05,
        af.sum_assured * af.mortality_rate,
    )
    return af


def _a_model_deriving_a_date() -> ActuarialFrame:
    """Return a model with a column the date door stamped from a duration."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "issue_date": [
                    datetime.date(2020, 1, 1),
                    datetime.date(2021, 6, 15),
                ]
            }
        )
    )
    af.date.add_duration("issue_date", "10y", "maturity_date")
    return af


def _a_model_with_a_commented_right_hand_side() -> ActuarialFrame:
    """Return a model whose author wrapped one statement and annotated it.

    The comment inside the right-hand side sits between its first token and
    its last; the comment on the second statement trails the whole thing.
    The two are on opposite sides of where the captured segment stops.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
                "annual_premium": [450.0, 1_200.0],
            }
        )
    )
    af.death_claims = (
        af.sum_assured  # the benefit at risk
        * af.mortality_rate
    )
    af.expenses = af.annual_premium * 0.05  # a tenth of a fifth of the premium
    return af


def _a_model_written_by_a_loop() -> ActuarialFrame:
    """Return a model whose two columns were written by one statement.

    The target is the loop variable rather than a literal name, and the two
    iterations read different rates -- which is what tells the columns
    apart once they carry the same text.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
                "lapse_rate": [0.05, 0.08],
            }
        )
    )
    for out_name, rate_name in (
        ("death_claims", "mortality_rate"),
        ("lapse_claims", "lapse_rate"),
    ):
        af[out_name] = af.sum_assured * af[rate_name]
    return af


def _a_model_written_by_a_setattr_loop() -> ActuarialFrame:
    """Return a model whose columns were written through the ``setattr`` builtin.

    Attribute syntax has no dynamic form, so an actuary building one column
    per basis -- the ordinary shape behind a capital run's forty-odd
    columns -- reaches for the builtin instead. The statement that parses
    to is a call, and the right-hand side sits in the argument it was
    written in.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
                "lapse_rate": [0.05, 0.08],
            }
        )
    )
    for out_name, rate_name in (
        ("death_claims", "mortality_rate"),
        ("lapse_claims", "lapse_rate"),
    ):
        setattr(af, out_name, af.sum_assured * af[rate_name])
    return af


# --- what the field carries -------------------------------------------------


def test_the_formula_is_the_line_the_actuary_typed() -> None:
    """The right-hand side as written, character for character."""
    artifact = _artifact(_a_two_column_model())

    assert _node(artifact, "death_claims@1")["formula"] == (
        "af.sum_assured * af.mortality_rate"
    )


def test_a_multi_line_conditional_is_captured_whole() -> None:
    """A statement written over three lines is carried as the statement it is."""
    artifact = _artifact(_a_model_with_a_wrapped_conditional())

    formula = _node(artifact, "policies_in_force@2")["formula"]

    assert formula.startswith("when(")
    assert "otherwise" in formula
    assert "\n" in formula


def test_a_column_no_single_written_expression_defines_says_so() -> None:
    """A column minted through the batch door has no right-hand side of its own.

    The statement's right-hand side is the whole call, not the expression
    for the column beside it, so there is nothing to report that computes
    this number.
    """
    artifact = _artifact(_a_model_using_a_multi_column_call())

    assert _node(artifact, "expenses@1")["formula"] is None


def test_the_door_is_the_test_and_not_the_number_of_siblings() -> None:
    """A batch call that defined exactly one column is null just the same.

    The one-column call has no sibling to point at, so if the rule were
    "the statement defines its siblings too" this column would carry text.
    It does not: the right-hand side of that statement is the whole call
    either way, and the door it came through is what earns the null.
    """
    artifact = _artifact(_a_model_using_a_single_column_call())

    node = _node(artifact, "expenses@1")

    assert node["provenance"] == "batch"
    assert node["formula"] is None


def test_a_tuple_assignment_defines_no_column_from_its_own_text() -> None:
    """Two columns, one right-hand side, and it is neither column's formula.

    The door is ``assignment`` here rather than ``batch``, so the provenance
    alone does not earn the null -- the statement's shape does. Its value
    is a tuple, and reporting the whole tuple against either column would
    show a reviewer text that does not compute the number beside it, which
    is the same thing the batch door's null says.
    """
    artifact = _artifact(_a_model_written_by_a_tuple_assignment())

    expenses = _node(artifact, "expenses@1")
    death = _node(artifact, "death_claims@1")

    assert expenses["provenance"] == "assignment"
    assert expenses["formula"] is None
    assert death["formula"] is None


def test_a_date_derivation_is_a_configuration_and_not_a_formula() -> None:
    """The date door stamps a column from a duration, not from an expression."""
    artifact = _artifact(_a_model_deriving_a_date())

    node = _node(artifact, "maturity_date@1")

    assert node["provenance"] == "date"
    assert node["formula"] is None


# --- what a consumer must expect of the text --------------------------------


def test_the_text_is_free_form_and_carries_what_the_author_left_in_it() -> None:
    """Newlines, continuation indentation and an interior comment all survive.

    A consumer that treats ``formula`` as a bare expression meets all
    three, so the artifact says so and this pins that it does.
    """
    artifact = _artifact(_a_model_with_a_commented_right_hand_side())

    formula = _node(artifact, "death_claims@1")["formula"]

    assert "\n" in formula
    assert "\n    " in formula
    assert "# the benefit at risk" in formula


def test_a_comment_after_the_statement_is_not_part_of_the_text() -> None:
    """The segment stops at the expression; what trails the statement is outside it."""
    artifact = _artifact(_a_model_with_a_commented_right_hand_side())

    formula = _node(artifact, "expenses@1")["formula"]

    assert formula == "af.annual_premium * 0.05"
    assert "#" not in formula


def test_a_computed_target_carries_one_text_and_reads_tells_them_apart() -> None:
    """One loop body is one statement, and every column it defined gets it.

    The text is the statement that defined each of them, so nulling it
    would discard true audit text. What separates the two columns is what
    the calculation actually was, which ``reads`` carries.
    """
    artifact = _artifact(_a_model_written_by_a_loop())

    death = _node(artifact, "death_claims@1")
    lapse = _node(artifact, "lapse_claims@1")

    assert death["formula"] == lapse["formula"]
    assert death["formula"] == "af.sum_assured * af[rate_name]"
    assert death["reads"] == ["sum_assured", "mortality_rate"]
    assert lapse["reads"] == ["sum_assured", "lapse_rate"]


def test_a_column_the_setattr_builtin_wrote_carries_the_line_it_was_written_in() -> (
    None
):
    """The builtin's value argument is the right-hand side, and the node carries it.

    A dynamically named column is a column like any other: its tier is read
    off the operation tree, which says ``core`` whichever syntax wrote it.
    A null formula beside that tier would claim a fully portable
    calculation with nothing a reviewer can read -- the graph would be
    saying the column is auditable and holding nothing to audit.

    Both columns carry the one statement that defined them, as the
    subscript form above does, and ``reads`` is again what tells them
    apart.
    """
    artifact = _artifact(_a_model_written_by_a_setattr_loop())

    death = _node(artifact, "death_claims@1")
    lapse = _node(artifact, "lapse_claims@1")

    assert death["tier"] == "core"
    assert death["formula"] == "af.sum_assured * af[rate_name]"
    assert death["formula"] == lapse["formula"]
    assert death["reads"] == ["sum_assured", "mortality_rate"]
    assert lapse["reads"] == ["sum_assured", "lapse_rate"]


# --- what the base artifact does not carry ----------------------------------


def test_the_base_artifact_carries_no_engine_rendering() -> None:
    """No rendering facet, and the engine's own spelling of a column nowhere in it.

    The needle stops at the bracket rather than running on into the quote
    the engine writes after it: JSON escapes that quote, so a needle
    carrying one matches nothing whatever the document says and would be a
    guard that never bites.

    A node that reads something carries the narrowing of its reads either
    way, which is why the assertion names the rendering rather than asking
    for an empty facets object.

    The sources section is lifted out before the search, and the reason is
    the distinction this test is about. What it guards against is the
    *engine* spelling a column back at the reader; the model's own text is
    what the author wrote, and an author who reached for ``pl.col`` wrote
    that themselves. A needle found there would be the model, not a
    rendering of it -- as it is here, where the model under test is written
    in this file beside several that use Polars directly.
    """
    artifact = _artifact(_a_two_column_model())

    assert all("gaspatchio_lowered" not in node["facets"] for node in artifact["nodes"])
    assert "gaspatchio_lowered" not in artifact["facets_used"]
    assert "col(" not in json.dumps(
        {name: value for name, value in artifact.items() if name != "sources"}
    )


def test_the_engine_rendering_is_available_when_it_is_asked_for() -> None:
    """Asked for, it arrives as a facet the envelope announces in the same breath."""
    artifact = _artifact_carrying_the_engine_rendering(_a_two_column_model())

    facet = _node(artifact, "death_claims@1")["facets"]["gaspatchio_lowered"]

    assert facet["engine"] == "polars"
    assert 'col("sum_assured")' in facet["text"]
    assert artifact["facets_used"] == [
        "gaspatchio_column_transformation",
        "gaspatchio_lowered",
    ]
    assert artifact["facets_required"] == []


def test_the_facet_carries_the_two_members_every_facet_carries() -> None:
    """Who produced it, and which schema reads it -- read off the wire.

    Both values are spelled out here rather than taken from the constants
    the producer builds them from: a test that asks the producer what it
    said agrees with it however it changes, and the whole point of these
    two members is that a consumer meeting the artifact cold can tell whose
    facet it is holding and which schema reads it. They arrive because the
    emitting site goes through the wrapper that stamps them, and an inline
    dict written in its place would drop both with every other assertion in
    this file still green.
    """
    artifact = _artifact_carrying_the_engine_rendering(_a_two_column_model())

    facet = _node(artifact, "death_claims@1")["facets"]["gaspatchio_lowered"]

    assert "_producer" in facet
    assert "_schemaURL" in facet
    assert facet["_producer"] == (
        "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3"
    )
    assert facet["_schemaURL"] == (
        "https://gaspatchio.dev/schemas/facets/gaspatchio_lowered-v0-preview.1.json"
    )
