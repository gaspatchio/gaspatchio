# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The supervisory documentation, assembled from one artifact and nothing else.

Annex A of ``spec/graph-artifact/v0-preview.md`` claims that the documentation
a supervisor asks for about a model can be assembled from a conforming
artifact by a named path through its fields. This module is that claim's
proof, and the annex cites it by name.

Each test is named for the question it answers, and asserts the *path* rather
than the value: which field a reader follows to reach the answer, not what
this particular model happens to say. A test that pinned a number would pass
for a fixture and prove nothing about the format.

The example artifact in ``goldens/annex_example_artifact.json`` is a
hand-built eight-node account of a short term-assurance model: four columns
arriving, one column computed from two of them and then redefined -- so that
the superseded definition is carried as history -- one column discounted off a
yield curve, one column nothing accounts for, and one point at which the model
froze its plan. Every ``sha256:`` digest in it is a well-formed placeholder
rather than a digest taken under the byte grammar of
section 12.1, and nothing here asserts a digest's value. Carrying real
canonical bytes would pin this file to a grammar the specification is
explicitly free to move while the preview is open, and would buy the annex
nothing: what the annex claims is where a reader looks.

The redefinition is what carries the join to an assumption base: the first
definition multiplied by an arriving ``mortality_rate`` column, and the second
looks the mortality basis up in its own formula. That is the shape a producer
emits and the shape A.2 reasons about -- a name on the node whose formula did
the reading, never on the arriving column, which is a leaf with no formula to
have read anything and which A.2 names as an open case for exactly that
reason.

The discount factor carries the same join on the other sort of name. A table
states the name the model gave it; a curve states none and is named after its
own contents, and the entry's name here is the kind and the first eight digits
of the identity beside it -- the shape the producer synthesises. A fixture
carrying tables alone would leave the join proved for the kind that always had
a name and untested for the kinds that did not.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ANNEX_ARTIFACT = Path(__file__).parent / "goldens" / "annex_example_artifact.json"


def _load_annex_artifact() -> dict[str, Any]:
    """Return the example artifact, validated against the published schema first.

    Validating before asserting is what keeps the annex honest: it can never
    be proved against an artifact the schema would reject.
    """
    import jsonschema

    from gaspatchio.schemas import load_schema

    artifact: dict[str, Any] = json.loads(_ANNEX_ARTIFACT.read_text("utf-8"))
    jsonschema.Draft202012Validator(load_schema()).validate(artifact)
    return artifact


def test_the_calculation_of_every_output_column_is_assembled_from_the_artifact() -> (
    None
):
    """Minimum documentation: what each figure is, and what it was computed from."""
    artifact = _load_annex_artifact()
    answers = {
        node["column"]: (node["formula"], node["reads"])
        for node in artifact["nodes"]
        if node["in_final_schema"] and node["kind"] == "computed"
    }
    assert answers["death_claims"][0] == (
        "af.sum_assured * mortality.lookup(attained_age=af.attained_age)"
    )
    assert set(answers["death_claims"][1]) == {"sum_assured", "attained_age"}


def test_the_data_and_assumptions_used_are_assembled_from_the_artifact() -> None:
    """Minimum documentation: which data and assumption bases the figures rest on."""
    artifact = _load_annex_artifact()
    assert artifact["model"]["model_points"]["fingerprint"].startswith("sha256:")
    assert [(a["kind"], a["name"], a["fingerprint"]) for a in artifact["assumptions"]]


def test_which_figure_rests_on_which_assumption_base_is_a_join_that_resolves() -> None:
    """Article 244(g)'s usage: the path from one node to the base it read.

    The path is asserted rather than the pairing -- that every name a node
    gives resolves to an entry of the section, and that at least one node
    gives one, so the join is followed here rather than merely declared.

    And that the name sits where the reading happened. A leaf naming an
    entry would be the record answering the question A.2 says it cannot:
    which base an arriving assumption column came from. The join is only
    worth following because the node giving the name has a formula that
    did the reading.

    **The join is followed on both sorts of name.** A table states the name
    the model gave it; a schedule and a curve state none, and are named
    after their own contents. A fixture carrying tables alone would prove
    the join for the kind that always had a name and say nothing about the
    kinds that did not, so the bases reached here have to include one of
    each.
    """
    artifact = _load_annex_artifact()
    named = {entry["name"] for entry in artifact["assumptions"]}

    assert any(node["reads_assumptions"] for node in artifact["nodes"])
    for node in artifact["nodes"]:
        assert set(node["reads_assumptions"]) <= named, node["id"]
        if node["formula"] is None:
            assert node["reads_assumptions"] == [], node["id"]

    read = {name for node in artifact["nodes"] for name in node["reads_assumptions"]}
    reached = {
        entry["kind"] for entry in artifact["assumptions"] if entry["name"] in read
    }
    assert "table" in reached
    assert reached - {"table"}, "the join is unproved for a base with no stated name"


def test_the_circumstances_the_model_is_ineffective_in_are_assembled() -> None:
    """The honest account: what the model cannot explain, and what is engine-locked."""
    artifact = _load_annex_artifact()
    unexplained = [hole["column"] for hole in artifact["holes"]]
    engine_locked = [node["id"] for node in artifact["nodes"] if node.get("engines")]
    assert unexplained == ["reserve_override"]
    assert engine_locked == []


def test_an_absent_engines_and_an_empty_one_are_read_as_different_claims() -> None:
    """No claim at all, and a positive claim of engine-freedom, are not the same."""
    artifact = _load_annex_artifact()
    no_claim = [node["id"] for node in artifact["nodes"] if "engines" not in node]
    engine_free = [
        node["id"] for node in artifact["nodes"] if node.get("engines") == []
    ]
    assert no_claim == [
        "sum_assured",
        "attained_age",
        "mortality_rate",
        "years_elapsed",
        "reserve_override",
    ]
    assert engine_free == ["death_claims@1", "death_claims@2", "discount_factor@1"]
    assert not set(no_claim) & set(engine_free)


def test_the_record_of_changes_to_the_model_is_assembled_from_the_artifact() -> None:
    """The change record: what was edited, what inherited, and what it replaced."""
    artifact = _load_annex_artifact()
    for node in artifact["nodes"]:
        local, folded = node["local_fingerprint"], node["fingerprint"]
        assert isinstance(local, str)
        assert isinstance(folded, str)
        assert local != folded, node["id"]
    assert artifact["graph_fingerprint"].startswith("sha256:")

    definitions: dict[str, list[dict[str, Any]]] = {}
    for node in artifact["nodes"]:
        if node["version"] is not None:
            definitions.setdefault(node["column"], []).append(node)
    with_history = {
        column: nodes for column, nodes in definitions.items() if len(nodes) > 1
    }
    assert with_history
    for column, nodes in with_history.items():
        held = [node for node in nodes if node["in_final_schema"]]
        assert len(held) == 1, column
