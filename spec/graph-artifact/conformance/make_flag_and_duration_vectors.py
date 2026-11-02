# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for a run of flags' least and greatest, and a duration's refusals.

Two bundles, each worked by hand from its clause and **none read off the
producer**, which is what they test. Stdlib only. Run from
``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_flag_and_duration_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

``flag-extremes.json`` -- sections 11.1.16 and 11.1.17: ``min`` and ``max``
answer one of the periods' own values, in their type, so a run of flags
answers ``bool`` (whether every period was set, whether any was), never the
0 or 1 the totals of 11.1.14 count it as.

``duration-refusals.json`` -- section 10 has no duration type, so a call that
reads a number out of one has no number of the vocabulary's own to read: the
thirteen maths calls other than ``abs``, plus ``cum_prod`` and
``projection.cumulative_survival``, are refused where the line is written,
per policy and per period. ``duration`` and ``list[duration]`` are input-only
names, as ``categorical`` is, and a value is a whole number of microseconds.
**Not here:** ``abs``, ``sum``, ``cum_sum``, ``projection.remaining_sum``,
``mean``, ``min`` and ``max`` of a duration answer a duration, which no
result can be named as, so they have no case a reader could check.
"""

from __future__ import annotations

import json
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)
SCHEMA = "gaspatchio-operation-vectors/v0-preview.1"
ARTIFACT = (
    "gaspatchio-graph/v0-preview.2"  # the envelope's own pin, as every bundle carries
)
TOKEN = "gspv0-preview-3"
DAY = 86_400_000_000  # microseconds


def col(name: str) -> dict:
    return {"op": "col", "name": name}


def call(name: str, attrs: dict | None = None) -> dict:
    return {"op": "call", "name": name, "args": [col("x")], "attrs": attrs or {}}


def bundle(family: str, cases: list[dict]) -> dict:
    return {
        "schema": SCHEMA,
        "artifact_schema": ARTIFACT,
        "fingerprint_algorithm": TOKEN,
        "family": family,
        "cases": cases,
    }


# No null period and no empty run here: those are §11.1.14's rule for the
# family, carried by ``nulls.json`` and ``boundaries.json``, and an engine that
# holds no null would refuse this case at the door for them alone.
FLAGS = [[True, False, True, True], [False, False], [True, True], [True]]
# By hand: min is "every period set", max is "any period set".
FLAG_ANSWERS = {
    "min": [False, False, True, True],
    "max": [True, False, True, True],
}


def flag_cases() -> list[dict]:
    return [
        {
            "id": f"flag-{name}-answers-a-flag",
            "covers": [name],
            "inputs": {"x": {"dtype": "list[bool]", "values": FLAGS}},
            "expr": call(name),
            "producer_check": True,
            "expected": {"dtype": "bool", "values": answer},
            "comparison": {"atol": 0.0, "rtol": 0.0},
            "case_kind": "value",
        }
        for name, answer in FLAG_ANSWERS.items()
    ]


# Five years and one year, in microseconds; per period [1827, 366, 31] days.
PER_POLICY = {"dtype": "duration", "values": [1827 * DAY, 366 * DAY]}
PER_PERIOD = {
    "dtype": "list[duration]",
    "values": [[1827 * DAY, 366 * DAY, 31 * DAY], [1310 * DAY, 366 * DAY, 31 * DAY]],
}
REFUSED = [
    ("sign", {}),
    ("round", {"decimals": 2, "mode": "half_to_even"}),
    ("floor", {}),
    ("ceil", {}),
    ("sqrt", {}),
    ("cbrt", {}),
    ("exp", {}),
    ("log", {}),
    ("log10", {}),
    ("log1p", {}),
    ("round_sig_figs", {"digits": 2}),
    ("norm_cdf", {}),
]
PER_PERIOD_ONLY = [
    ("cum_prod", {"reverse": False}),
    (
        "projection.cumulative_survival",
        {"start_at": None, "from_survival": False},
    ),
]


def duration_case(name: str, attrs: dict, shape: str, column: dict) -> dict:
    return {
        "id": f"duration-{name.replace('.', '-').replace('_', '-')}-{shape}-refused",
        "covers": [name],
        "inputs": {"x": column},
        "expr": call(name, attrs),
        "producer_check": True,
        "case_kind": "portable-domain-refusal",
        "refusal": "duration-read-as-a-number",
        "producer_message": "is a duration",
    }


def duration_cases() -> list[dict]:
    cases = []
    for name, attrs in REFUSED:
        cases.append(duration_case(name, attrs, "per-policy", PER_POLICY))
        cases.append(duration_case(name, attrs, "per-period", PER_PERIOD))
    cases.extend(
        duration_case(name, attrs, "per-period", PER_PERIOD)
        for name, attrs in PER_PERIOD_ONLY
    )
    return cases


def write(name: str, document: dict) -> None:
    (VECTORS / name).write_text(json.dumps(document, indent=2) + "\n")


def main() -> None:
    write(
        "flag-extremes.json",
        bundle("A run of flags' least and greatest (11.1.16-11.1.17)", flag_cases()),
    )
    write(
        "duration-refusals.json",
        bundle(
            "Calls that would read a number out of a duration (10)", duration_cases()
        ),
    )


if __name__ == "__main__":
    main()
