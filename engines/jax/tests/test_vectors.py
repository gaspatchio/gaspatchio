# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The kit's 909 cases through this engine, one outcome each.

``expectations.json`` beside this file records what *this engine* expects of
every case. A case moving from *not-yet-lowered* to *value-pass* is then an
edit somebody made to that file, reviewed in the diff, rather than a count
that quietly went up.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gaspatchio_jax.vectors import run_vectors
from tests.conftest import vectors_directory

EXPECTATIONS = Path(__file__).with_name("expectations.json")

# The kit's published case count at this edition. Stated rather than read off
# the bundles, so a bundle that lost a case fails here.
PUBLISHED_CASES = 909


@pytest.fixture(scope="module")
def run() -> object:
    expectations = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))["outcomes"]
    return run_vectors(vectors_directory(), expectations=expectations)


def test_the_run_reports_every_case_by_kind_and_no_value_case_fails(run) -> None:
    assert run.total == PUBLISHED_CASES
    assert run.by_outcome.get("value-fail", 0) == 0
    assert run.by_outcome.get("capability-refusal-unexpected", 0) == 0
    assert run.by_outcome.get("adapter-gap", 0) == 0


def test_every_case_lands_on_the_outcome_this_unit_recorded_for_it(run) -> None:
    expected = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))["outcomes"]
    moved = {
        case_id: (expected.get(case_id), outcome)
        for case_id, outcome in run.outcomes.items()
        if expected.get(case_id) != outcome
    }
    assert not moved, moved


def test_a_supported_positive_case_fails_when_its_lowering_is_replaced_by_a_refusal(
    monkeypatch,
) -> None:
    from gaspatchio_jax.lowerings import LOWERINGS, load
    from gaspatchio_jax.typed import DomainRefused

    load()

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise DomainRefused(what="swapped out", move="put it back", clause="11.1.25")

    swapped = dict(LOWERINGS)
    swapped["add"] = (refuse, LOWERINGS["add"][1])
    monkeypatch.setattr("gaspatchio_jax.lowerings.LOWERINGS", swapped)
    monkeypatch.setattr("gaspatchio_jax.plan.LOWERINGS", swapped)
    broken = run_vectors(vectors_directory())
    assert broken.outcomes["add-i64-policies"] == "capability-refusal-unexpected"


def test_door_projection_set_is_a_positive_recording_case(run) -> None:
    """The door the producer records, answered: the axis is a value now.

    ``projection_set`` mints a per-period column, so the entry read
    *not-yet-lowered* while the period axis was outside this engine. It is the
    axis itself, and the case is where the engine's reading of the boundary
    count meets the producer's.
    """
    expected = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))["outcomes"]
    assert run.outcomes["door-projection_set"] == expected["door-projection_set"]
    assert expected["door-projection_set"] == "value-pass"


def test_door_join_keeps_its_unmatched_key_as_the_null_the_record_says(run) -> None:
    """``on_missing="null"`` on the record: the second row's arriving cell is null.

    The case's right side carries products A and B and its book carries A and
    C. The record states that the model keeps a policy with no row (11.1.2),
    so this engine holds the miss beside the value and publishes the
    null the reference producer publishes.
    """
    assert run.outcomes["door-join"] == "value-pass"
    assert run.outcomes["door-join-every-key-matched"] == "value-pass"


def test_a_join_whose_record_keeps_no_miss_refuses_the_unmatched_key(run) -> None:
    """No ``on_missing`` on the record: a left join refuses a key with no row.

    What it names is the key, ``product=C``, at the row it is on; the reference
    producer refuses the same join where it is written.
    """
    expected = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))["outcomes"]
    case = "door-join-unmatched-refused"
    assert run.outcomes[case] == expected[case]
    assert "product=C" in run.details[case]


def test_a_join_over_no_policies_at_all_answers_no_rows(run) -> None:
    """The boundary the same door states: an empty book has no key to miss."""
    assert run.outcomes["empty-portfolio-join"] == "value-pass"


def test_every_published_lookup_case_is_answered_or_refused_on_its_own_ground(
    run,
) -> None:
    """The eleven published lookup reads, each with its outcome.

    Nine key on a ``list[f64]`` duration or age, which is why they all read
    *not-yet-lowered* while the period axis was outside this engine; two key
    on an ``f64`` age over a basis holding a ``-0.0`` answer, which this
    engine reads as ``0.0`` as data enters (section 12.3). The nine the kit
    states an answer for are answered; the two it states a refusal for -- a
    miss under ``raise``, once on a key the basis has no row for and once on
    a row whose answer cell is blank -- are refused on 11.1.24's own ground,
    which is the most a refusal case can reach.
    """
    from gaspatchio_jax.vectors import normalise

    cases = json.loads(
        (vectors_directory() / "lookup.json").read_text(encoding="utf-8")
    )["cases"]
    case = next(one for one in cases if one.get("assumptions"))
    built = normalise(case, "lookup.json")
    assert built.document["assumptions"]
    assert built.document["nodes"][-1]["reads_assumptions"]
    answered = {
        one["id"]: run.outcomes[one["id"]]
        for one in cases
        if one["case_kind"] == "value"
    }
    assert set(answered.values()) == {"value-pass"}, answered
    refused = {
        one["id"]: run.outcomes[one["id"]]
        for one in cases
        if one["case_kind"] != "value"
    }
    assert set(refused.values()) == {"domain-refusal-matched"}, refused
    assert len(answered) + len(refused) == 11


def test_integrity_mutations_are_applied_at_the_document_layer(run) -> None:
    cases = [
        case_id
        for case_id, outcome in run.outcomes.items()
        if outcome == "integrity-refusal-matched"
    ]
    assert len(cases) == 10


def test_the_run_records_a_ratio_per_identifier_it_answered_for(run) -> None:
    assert run.ratios
    assert all(0.0 <= ratio < 1e-12 for ratio in run.ratios.values())


@pytest.mark.parametrize(
    ("case_id", "dtype"),
    [
        ("conversion-to_float-unsigned-within-the-boundary", "u64"),
        ("conversion-to_float-unsigned-past-the-boundary", "u64"),
        ("conversion-to_text-unsigned-past-i64", "u64"),
        ("conversion-to_text-signed-128", "i128"),
        ("conversion-to_text-categorical", "categorical"),
        ("conversion-to_text-refuses-an-array", "array[f64,2]"),
        ("conversion-to_integer-unsigned-within-range", "u64"),
        ("conversion-to_integer-unsigned-past-i64", "u64"),
        ("conversion-to_integer-signed-128-below-i64", "i128"),
    ],
)
def test_conversion_types_outside_the_artifact_stop_before_the_engine(
    case_id: str, dtype: str, monkeypatch
) -> None:
    """An adapter boundary cannot earn an engine's domain-refusal result."""
    from gaspatchio_jax.engine import JaxEngine
    from gaspatchio_jax.vectors import AdapterGap, _one_case, normalise

    cases = json.loads(
        (vectors_directory() / "conversions.json").read_text(encoding="utf-8")
    )["cases"]
    case = next(one for one in cases if one["id"] == case_id)
    assert case["inputs"]["x"]["dtype"] == dtype
    with pytest.raises(AdapterGap, match="carries x as"):
        normalise(case, "conversions.json")

    def unexpected(*_args: object, **_kwargs: object) -> None:
        pytest.fail("An input with no artifact type reached the engine")

    monkeypatch.setattr(JaxEngine, "run", unexpected)
    result = _one_case(case, "conversions.json", JaxEngine())
    assert result.outcome == "not-yet-lowered"
    assert result.detail.endswith(f"carries x as {dtype}")


@pytest.mark.parametrize(
    ("case_id", "recorded"),
    [
        ("duration-sign-per-policy-refused", "i64"),
        ("duration-cum-prod-per-period-refused", "list[i64]"),
    ],
)
def test_a_duration_reaches_the_engine_and_its_door_refuses_it_by_name(
    run, case_id: str, recorded: str
) -> None:
    """The input-only duration is handed over as it is and refused by the engine.

    Section 10 names no time delta, so the document records the column as
    the whole number its values are stated in and the book carries the
    duration itself: the engine's door, not the adapter, refuses it, naming
    the duration and the cast, as the producer and the reader refuse it.
    """
    from gaspatchio.engines.protocol import FrameSink
    from gaspatchio.engines.report import EngineRefusal
    from gaspatchio_jax.engine import JaxEngine
    from gaspatchio_jax.vectors import normalise

    cases = json.loads(
        (vectors_directory() / "duration-refusals.json").read_text(encoding="utf-8")
    )["cases"]
    case = next(one for one in cases if one["id"] == case_id)
    built = normalise(case, "duration-refusals.json")
    (node,) = [one for one in built.document["nodes"] if one["id"] == "x"]
    assert node["dtype"] == recorded
    assert "Duration" in str(built.inputs.schema["x"])
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(built.document, built.inputs, FrameSink())
    assert any(
        "Duration(time_unit='us')" in one.what and "cast 'x'" in one.move
        for one in refused.value.report.refusals
    )
    assert run.outcomes[case_id] == "domain-refusal-matched"


def test_raw_struct_refusal_names_its_own_cause_and_stage(run) -> None:
    """Tracking alone cannot satisfy the raw Struct output contract."""
    from gaspatchio.engines.protocol import FrameSink
    from gaspatchio.engines.report import EngineRefusal, RunReport
    from gaspatchio_jax.engine import JaxEngine
    from gaspatchio_jax.vectors import _refused, normalise

    case_id = "raw-struct-export-refuses"
    cases = json.loads(
        (vectors_directory() / "boundaries.json").read_text(encoding="utf-8")
    )["cases"]
    case = next(one for one in cases if one["id"] == case_id)
    built = normalise(case, "boundaries.json")
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(built.document, built.inputs, FrameSink())
    findings = refused.value.report.refusals
    assert any(
        one.group == "tree" and one.clause == "16.3" and "Struct" in one.what
        for one in findings
    )
    assert run.outcomes[case_id] == "domain-refusal-matched"
    assert "16.3" in run.details[case_id]
    assert "Struct" in run.details[case_id]
    tracking_only = tuple(one for one in findings if one.clause == "16.1")
    assert tracking_only
    broken = _refused(
        case,
        built,
        EngineRefusal(RunReport(refusals=tracking_only, notes=())),
        tuple(case["covers"]),
        reached=False,
    )
    assert broken.outcome == "not-yet-lowered"


@pytest.mark.parametrize(
    "witness",
    [
        "misleading-note",
        "split-findings",
        "wrong-clause",
        "inputs-stage",
        "completion-stage",
        "move-only",
        "incidental-mention",
    ],
)
def test_raw_struct_requires_one_matching_structured_refusal(witness: str) -> None:
    """Words elsewhere in a report cannot establish this output refusal."""
    from dataclasses import replace

    from gaspatchio.engines.protocol import FrameSink
    from gaspatchio.engines.report import EngineRefusal, RunReport
    from gaspatchio_jax.engine import JaxEngine
    from gaspatchio_jax.vectors import _refused, normalise

    cases = json.loads(
        (vectors_directory() / "boundaries.json").read_text(encoding="utf-8")
    )["cases"]
    case = next(one for one in cases if one["id"] == "raw-struct-export-refuses")
    built = normalise(case, "boundaries.json")
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(built.document, built.inputs, FrameSink())
    findings = refused.value.report.refusals
    struct = next(one for one in findings if one.clause == "16.3")
    tracking = next(one for one in findings if one.clause == "16.1")
    reports = {
        "misleading-note": RunReport(
            (tracking,), notes=("Struct output contract is specified in 16.3.",)
        ),
        "split-findings": RunReport(
            (replace(struct, clause="16.1"), replace(tracking, clause="16.3"))
        ),
        "wrong-clause": RunReport((replace(struct, clause="116.3"),)),
        "inputs-stage": RunReport((replace(struct, group="inputs"),)),
        "completion-stage": RunReport((replace(struct, group="completion"),)),
        "move-only": RunReport(
            (replace(struct, what=tracking.what, move=struct.what),)
        ),
        "incidental-mention": RunReport(
            (replace(struct, what="A Struct input carries missing values."),)
        ),
    }
    result = _refused(
        case,
        built,
        EngineRefusal(reports[witness]),
        tuple(case["covers"]),
        reached=False,
    )
    assert result.outcome == "not-yet-lowered", (witness, result)

    # Report ordering and distracting notes must not change the evidence
    # selected from a real tree/16.3 finding.
    positive = RunReport((tracking, struct), notes=reports["misleading-note"].notes)
    matched = _refused(
        case,
        built,
        EngineRefusal(positive),
        tuple(case["covers"]),
        reached=False,
    )
    assert matched.outcome == "domain-refusal-matched"
    assert matched.detail == struct.line()
