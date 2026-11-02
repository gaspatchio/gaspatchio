# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The agreement ratchet: a worsened ratio moves only with a reason beside it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gaspatchio_jax.vectors import run_vectors
from tests.conftest import PROJECT, vectors_directory

AGREEMENT = PROJECT / "agreement.json"
EXPECTATIONS = Path(__file__).with_name("expectations.json")

# The agreement band, 1e-12 of a line's scale (specification section 11.1.12),
# which no ratio this engine records may reach.
AGREEMENT_BAND = 1e-12


@pytest.fixture(scope="module")
def measured() -> dict[str, float]:
    expectations = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))["outcomes"]
    return run_vectors(vectors_directory(), expectations=expectations).ratios


def _recorded() -> dict[str, float]:
    return json.loads(AGREEMENT.read_text(encoding="utf-8"))["ratios"]


def test_no_identifier_agrees_worse_than_the_ratchet_records(measured) -> None:
    recorded = _recorded()
    worsened = {
        identifier: (recorded.get(identifier), ratio)
        for identifier, ratio in measured.items()
        if ratio > recorded.get(identifier, 0.0)
    }
    assert not worsened, worsened


def test_every_recorded_ratio_is_one_this_run_still_measures(measured) -> None:
    assert set(_recorded()) == set(measured)


def test_every_recorded_ratio_is_inside_the_agreement_band() -> None:
    assert all(ratio < AGREEMENT_BAND for ratio in _recorded().values())


def test_a_ratio_that_is_not_zero_carries_its_reason() -> None:
    document = json.loads(AGREEMENT.read_text(encoding="utf-8"))
    for identifier, ratio in document["ratios"].items():
        if ratio > 0.0:
            assert identifier in document["_reasons"], identifier


def test_an_exact_zero_root_is_measured_despite_a_generous_vector_budget() -> None:
    """An acceptance tolerance conveys no uncertainty about an exact root."""
    from gaspatchio_jax.vectors import _ratio, normalise

    cases = [
        case
        for path in vectors_directory().glob("*.json")
        for case in json.loads(path.read_text()).get("cases", [])
    ]
    case = next(one for one in cases if one["id"] == "irr-six-hundred-period-zero-root")
    invocation = normalise(case, "excel-irr.json")
    ratio = _ratio([5e-8], [0.0], invocation)
    assert ratio is not None
    assert ratio > AGREEMENT_BAND
    assert invocation.comparison["atol"] > 5e-8


@pytest.mark.parametrize(
    "case_id",
    [
        "rollforward-structural-floor-that-never-bites",
        "rollforward-ratchet-at-the-anniversary",
    ],
)
def test_rounded_reference_exclusion_is_bound_to_the_expected_data(
    case_id: str,
) -> None:
    """A changed dataset cannot inherit a precision annotation by its name."""
    import copy

    from gaspatchio_jax.vectors import _ratio, normalise

    cases = json.loads((vectors_directory() / "rollforward.json").read_text())["cases"]
    case = copy.deepcopy(next(one for one in cases if one["id"] == case_id))
    invocation = normalise(case, "rollforward.json")
    wanted = case["expected"]["values"]
    assert _ratio(wanted, wanted, invocation) is None
    case["expected"]["values"][0][0] += 1.0
    changed = normalise(case, "rollforward.json")
    assert (
        _ratio(case["expected"]["values"], case["expected"]["values"], changed) == 0.0
    )


def test_precision_exclusions_are_reported_and_keep_vector_budget_checks() -> None:
    import copy

    from gaspatchio_jax.engine import JaxEngine
    from gaspatchio_jax.vectors import _ROUNDED_REFERENCES, _one_case

    agreement = json.loads(AGREEMENT.read_text())["_reference_precision"]
    cases = json.loads((vectors_directory() / "rollforward.json").read_text())["cases"]
    for case_id, digest in _ROUNDED_REFERENCES.items():
        assert agreement[case_id]["expected_sha256"] == digest
        case = copy.deepcopy(next(one for one in cases if one["id"] == case_id))
        outcome = _one_case(case, "rollforward.json", JaxEngine())
        assert outcome.outcome == "value-pass"
        assert outcome.ratio is None
        assert case_id in outcome.detail
        assert digest in outcome.detail
        assert "the agreement rule is not measurable" in outcome.detail
        initial = "av_init" if "av_init" in case["inputs"] else "fund_init"
        case["inputs"][initial]["values"] = [1e6]
        assert _one_case(case, "rollforward.json", JaxEngine()).outcome == "value-fail"
