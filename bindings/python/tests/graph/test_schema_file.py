# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests guarding the published artifact schema and how it is read."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_EXAMPLE_ARTIFACT = Path(__file__).parent / "goldens" / "annex_example_artifact.json"


def _example_artifact() -> dict[str, Any]:
    """Return a conforming artifact, for a test that makes one field wrong."""
    artifact: dict[str, Any] = json.loads(_EXAMPLE_ARTIFACT.read_text("utf-8"))
    return artifact


def _fields_the_schema_rejects(artifact: dict[str, Any]) -> list[list[str | int]]:
    """Return the path of every validation error, so a test can name the field."""
    import jsonschema

    from gaspatchio.schemas import load_schema

    validator = jsonschema.Draft202012Validator(load_schema())
    return [list(error.absolute_path) for error in validator.iter_errors(artifact)]


def test_schema_file_ships_inside_the_package() -> None:
    """The published schema is readable from the installed package, offline."""
    from gaspatchio.schemas import load_schema

    schema = load_schema()
    assert schema["$id"] == (
        "https://gaspatchio.dev/schemas/gaspatchio-graph-v0.schema.json"
    )


def test_schema_file_is_a_valid_2020_12_schema() -> None:
    """The document is itself a well-formed JSON Schema, not merely valid JSON."""
    import jsonschema

    from gaspatchio.schemas import load_schema

    jsonschema.Draft202012Validator.check_schema(load_schema())


def test_schema_is_read_through_the_package_not_the_working_directory() -> None:
    """load_schema() resolves through importlib.resources, so it works from anywhere."""
    import importlib.resources

    files = importlib.resources.files("gaspatchio.schemas")
    assert (files / "gaspatchio-graph-v0.schema.json").is_file()


def test_every_identifier_the_specification_lists_resolves() -> None:
    """The identifier table is the only way a schema string becomes a document."""
    from gaspatchio.schemas import SCHEMA_IDENTIFIERS, load_schema

    for identifier, filename in SCHEMA_IDENTIFIERS.items():
        assert load_schema(filename)["$id"].endswith(filename), identifier


def test_load_schema_refuses_a_name_it_does_not_publish() -> None:
    """A schema name is a key in the identifier table, not a path into the package."""
    from gaspatchio.schemas import load_schema

    with pytest.raises(ValueError, match=re.escape("gaspatchio-graph-v0.schema.json")):
        load_schema("../x")


def test_the_example_artifact_is_the_baseline_the_other_tests_break() -> None:
    """The artifact those tests start from validates, so the break is the field."""
    assert _fields_the_schema_rejects(_example_artifact()) == []


def test_a_foreign_fingerprint_algorithm_token_is_refused() -> None:
    """Equality is the token's whole contract, so the schema pins the token."""
    artifact = _example_artifact()
    artifact["fingerprint_algorithm"] = "some-other-grammar"

    assert _fields_the_schema_rejects(artifact) == [["fingerprint_algorithm"]]


def test_a_created_at_carrying_a_numeric_offset_is_refused() -> None:
    """RFC 3339 with the Z designator: two artifacts' timestamps compare as written."""
    artifact = _example_artifact()
    artifact["created_at"] = "2026-08-30T09:00:00+02:00"

    assert _fields_the_schema_rejects(artifact) == [["created_at"]]


def _with_one_assumption_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a conforming artifact carrying one assumption entry with ``payload``."""
    artifact = _example_artifact()
    artifact["assumptions"] = [
        {
            "kind": "table",
            "name": "mortality",
            "fingerprint": f"sha256:{'0' * 64}",
            "payload": payload,
        }
    ]
    return artifact


@pytest.mark.parametrize("weight", [0, 1, 32_799, 1_048_576])
def test_every_size_omission_a_producer_could_ever_have_written_still_validates(
    weight: int,
) -> None:
    """The reason grew from one word to two, and nothing already written broke.

    Growing a closed vocabulary is additive; making a field conditional on
    that vocabulary is not, unless every document already written falls on
    the side that keeps the field. Every omission this format could
    previously express was a size carrying a non-negative count of bytes,
    and each of those still says exactly what it said.
    """
    assert (
        _fields_the_schema_rejects(
            _with_one_assumption_payload({"omitted": "size", "bytes": weight})
        )
        == []
    )


def test_a_value_the_producer_cannot_vouch_for_claims_no_weight() -> None:
    """Nothing was in front of the producer to weigh, so no weight is claimed."""
    assert (
        _fields_the_schema_rejects(
            _with_one_assumption_payload({"omitted": "unavailable"})
        )
        == []
    )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"omitted": "size"}, id="size_without_the_weight_it_promises"),
        pytest.param({"omitted": "size", "bytes": None}, id="size_declining_to_weigh"),
        pytest.param(
            {"omitted": "unavailable", "bytes": 0}, id="unavailable_claiming_nought"
        ),
        pytest.param({"omitted": "lost"}, id="a_reason_the_format_does_not_define"),
    ],
)
def test_the_two_reasons_are_held_to_what_each_of_them_promises(
    payload: dict[str, Any],
) -> None:
    """A weighed reason states a weight; an unweighed one must not invent nought.

    "Left out for its size, nought bytes" is the sentence this conditional
    exists to make unwritable: a reason that did not happen standing beside a
    measurement nobody took, in the one field a reader budgets against.
    """
    assert _fields_the_schema_rejects(_with_one_assumption_payload(payload)) == [
        ["assumptions", 0, "payload"]
    ]


def _with_one_hole(reason: object) -> dict[str, Any]:
    """Return a conforming artifact whose one hole states ``reason``."""
    artifact = _example_artifact()
    (hole,) = artifact["holes"]
    artifact["holes"] = [{**hole, "reason": reason}]
    return artifact


@pytest.mark.parametrize("reason", ["unrecorded", "overwritten", "rebuilt"])
def test_each_reason_a_hole_can_state_validates(reason: str) -> None:
    """The reason grew from one word to three, and the one already written still holds.

    ``unrecorded`` is every hole a producer has written so far, so a document
    carrying one validates as it always did; the two new words name evidence
    a producer meets as it happens -- a write it saw replace a column it
    accounted for, and memory another frame's calculation produced.
    """
    assert _fields_the_schema_rejects(_with_one_hole(reason)) == []


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param("guessed", id="a_reason_the_format_does_not_define"),
        pytest.param("Overwritten", id="a_reason_spelled_another_way"),
        pytest.param(None, id="no_reason"),
    ],
)
def test_a_hole_reason_outside_the_vocabulary_is_refused(reason: object) -> None:
    """A reader matches the reason by equality, so the schema holds it to the three."""
    assert _fields_the_schema_rejects(_with_one_hole(reason)) == [
        ["holes", 0, "reason"]
    ]
