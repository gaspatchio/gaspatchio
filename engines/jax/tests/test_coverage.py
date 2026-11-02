# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The coverage manifest on disk is the one this engine generates today."""

from __future__ import annotations

import json

from gaspatchio.engines.format import VOCABULARY
from gaspatchio_jax import coverage
from tests.conftest import PROJECT

MANIFEST = PROJECT / "coverage.json"

# The repository's index, not the installed core's. The core arrives here as a
# built wheel, and a wheel carries the index as it stood when it was built --
# which is before any landing that changes what this engine claims. The index
# the kit's generator writes is the one in the tree, and the tree is what a
# reader of the diff sees.
INDEX = PROJECT.parents[1] / "bindings/python/gaspatchio/schemas/conformance/index.json"


def test_the_manifest_on_disk_equals_a_fresh_generation() -> None:
    assert json.loads(MANIFEST.read_text(encoding="utf-8")) == coverage.manifest()


def test_the_manifest_carries_one_row_per_identifier_the_format_names() -> None:
    document = coverage.manifest()
    assert [row["identifier"] for row in document["operations"]] == [
        operation.identifier for operation in VOCABULARY
    ]
    assert sum(document["counts"].values()) == len(VOCABULARY)


def test_the_counts_are_what_this_engine_claims_of_the_whole_vocabulary() -> None:
    """Every identifier with a status, and the three statuses counted.

    Stated rather than derived, so that an identifier moving between statuses
    -- which is what a landing here *is* -- shows up as an edit to this line
    beside the edit to the manifest, rather than as a number nobody read.
    """
    assert coverage.manifest()["counts"] == {
        "lowered": 96,
        "lowered-off-trace": 2,
        "refused": 3,
    }


def test_the_three_refused_rows_say_why_rather_than_saying_not_yet() -> None:
    """Refused *by name*, which a reader can act on, and with the clause.

    An identifier nobody has reached yet is a thing to wait for; one this
    engine will not answer is a thing to stop waiting for, and the two must
    not read the same.
    """
    from gaspatchio_jax.lowerings import REFUSED

    rows = {
        row["identifier"]: row
        for row in coverage.manifest()["operations"]
        if row["status"] == "refused"
    }
    assert set(rows) == set(REFUSED)
    for identifier, row in rows.items():
        assert row["condition"] == REFUSED[identifier][0]
        assert row["clause"] == REFUSED[identifier][1]
        assert "no lowering for it yet" not in row["condition"]


def test_no_row_claims_more_than_the_runtime_does() -> None:
    from gaspatchio_jax.lowerings import LOWERINGS, load

    load()
    for row in coverage.manifest()["operations"]:
        if row["status"] == "refused":
            continue
        assert row["identifier"] in LOWERINGS, row


def test_no_row_reads_lowered_with_nothing_beside_it_while_it_restricts() -> None:
    """A status is about an invocation, so a claim has to say which invocations."""
    from gaspatchio_jax.lowerings import LOWERINGS, load

    load()
    for row in coverage.manifest()["operations"]:
        if row["status"] == "refused":
            continue
        capability = LOWERINGS[row["identifier"]][1]
        if capability.restricts():
            assert row["condition"], row
            assert capability.stated_condition() in row["condition"], row


def test_the_attribute_restrictions_a_lowering_enforces_are_declared() -> None:
    """The two the domain rule turns on, named in their own rows."""
    rows = {row["identifier"]: row for row in coverage.manifest()["operations"]}
    assert "digits >= 1" in rows["round_sig_figs"]["condition"]
    assert "decimals a whole number" in rows["round"]["condition"]
    assert "strict=True" in rows["str.to_date"]["condition"]
    assert "exact=True" in rows["str.to_date"]["condition"]
    assert "format stated" in rows["str.to_date"]["condition"]
    assert "3 operands" in rows["cut"]["condition"]
    assert "2 or 3 operands" in rows["clip"]["condition"]


def test_a_refused_row_says_what_it_is_refused_for() -> None:
    for row in coverage.manifest()["operations"]:
        if row["status"] != "lowered":
            assert row["condition"], row


def test_the_conformance_index_carries_what_this_manifest_says() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    assert index["engines"]["jax"] == json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_the_off_trace_rows_carry_their_condition_rather_than_the_bare_word() -> None:
    off_trace = [
        row
        for row in coverage.manifest()["operations"]
        if row["status"] == "lowered-off-trace"
    ]
    assert {row["identifier"] for row in off_trace} == {"to_text", "str.to_date"}
    # The operand condition first, then whatever else the registration restricts.
    assert all(
        (row["condition"] or "").startswith("operands are inputs or literals")
        for row in off_trace
    )
