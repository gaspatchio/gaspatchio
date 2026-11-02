# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Independent tables rules for the published synthetic vectors."""

from __future__ import annotations

import hashlib
import math
import struct

from identity import string as text_bytes
from identity import varint as unsigned_bytes

from .shared import Column, DomainRefusal, map_values


def table_cell(kind: str, value: int | float | str | None) -> bytes:
    # 12.3: every cell carries a marker in front of it saying whether it is
    # there -- 0x02 and the value's bytes when it is, 0x01 and one placeholder
    # byte when it is not. A blank answer cell is the ordinary shape of a
    # published basis, a select table padded at the age and duration pairs no
    # life occupies, so it encodes as absent rather than stopping the hash.
    # 11.1.24 says what a query that reaches one gets.
    if value is None:
        return b"\x01\x00"
    if kind == "f64":
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise DomainRefusal("lookup-nonfinite-table-cell")
        return b"\x02" + struct.pack(">d", 0.0 if value == 0 else value)
    if kind == "i64":
        return b"\x02" + unsigned_bytes(value * 2 if value >= 0 else -value * 2 - 1)
    return b"\x02" + text_bytes(value)


def table_identity(payload: dict) -> str:
    raw = unsigned_bytes(len(payload["columns"]))
    for position, column in enumerate(payload["columns"]):
        kind = column["dtype"]
        if kind not in {"i64", "f64", "str"}:
            raise DomainRefusal("lookup-table-type")
        raw += (
            text_bytes(column["name"])
            + bytes([{"i64": 0x12, "f64": 0x13, "str": 0x14}[kind]])
            + unsigned_bytes(len(payload["rows"]))
        )
        for row in payload["rows"]:
            raw += table_cell(kind, row[position])
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def table_payload(attrs: dict, assumptions: list[dict]) -> dict:
    matches = [
        item
        for item in assumptions
        if item["kind"] == "table"
        and item["name"] == attrs["table"]
        and item["fingerprint"] == attrs["table_fingerprint"]
    ]
    if len(matches) != 1:
        raise DomainRefusal("lookup-payload-missing-or-ambiguous")
    payload = matches[0]["payload"]
    if table_identity(payload) != attrs["table_fingerprint"]:
        raise DomainRefusal("lookup-payload-identity")
    return payload


def lookup_layout(payload: dict, operands: list[Column]) -> tuple[list[int], int]:
    names = [column["name"] for column in payload["columns"]]
    dimensions = [column for column in names if column in payload["dimensions"]]
    answers = [name for name in names if name not in dimensions]
    if not payload["rows"] or not dimensions:
        raise DomainRefusal("lookup-empty-table")
    if (
        len(names) != len(set(names))
        or len(answers) != 1
        or answers[0] != payload["value"]
        or len(dimensions) != len(operands)
    ):
        raise DomainRefusal("lookup-key-answer-layout")
    positions = [names.index(column) for column in dimensions]
    answer = names.index(payload["value"])
    if payload["columns"][answer]["dtype"] != "f64":
        raise DomainRefusal("lookup-answer-type")
    for position, operand in zip(positions, operands):
        kind = payload["columns"][position]["dtype"]
        if not (
            kind == operand.inner == "str"
            or kind == "f64"
            and operand.inner in {"i64", "f64"}
        ):
            raise DomainRefusal("lookup-key-type")
    return positions, answer


def lookup_key(value: float | int | str | None) -> bool:
    """Return whether this key is a miss. 11.1.24: a null key is one."""
    if value is None:
        return True
    if isinstance(value, str):
        return False
    if not math.isfinite(value) or abs(value) > 2**53:
        raise DomainRefusal("lookup-key-range")
    return False


def lookup_rows(payload: dict, positions: list[int], answer: int) -> dict:
    values = {}
    for row in payload["rows"]:
        key = tuple(row[position] for position in positions)
        # A key cell of the table is judged table-wide, as 11.1.24 states it:
        # a null there is outside the bounded domain rather than a miss, which
        # is a thing only a query can be.
        for value in key:
            if lookup_key(value):
                raise DomainRefusal("lookup-null-table-key")
        if key in values:
            raise DomainRefusal("lookup-duplicate-key")
        # 12.3: a data -0.0 is written as 0.0 where a table enters, before it
        # is hashed or read, so a sign-reading operation sees +0.0.
        cell = row[answer]
        values[key] = 0.0 if isinstance(cell, float) and cell == 0.0 else cell
    return values


def lookup_miss(attrs: dict) -> float:
    if attrs.get("on_missing") == "nan":
        return math.nan
    if attrs.get("on_missing") == "fill":
        return attrs["fill_value"]
    raise DomainRefusal("lookup-missing-key")


def lookup_missing_contract(attrs: dict) -> None:
    mode, fill = attrs.get("on_missing", "raise"), attrs.get("fill_value")
    if mode == "fill":
        if fill is None or not math.isfinite(fill):
            raise DomainRefusal("lookup-fill-configuration")
    elif mode not in {"nan", "raise"} or fill is not None:
        raise DomainRefusal("lookup-fill-configuration")


def lookup_value(
    name: str, operands: list[Column], attrs: dict, assumptions: list[dict]
) -> Column:
    payload = table_payload(attrs, assumptions)
    positions, answer = lookup_layout(payload, operands)
    values = lookup_rows(payload, positions, answer)
    lookup_missing_contract(attrs)
    # A null outer list is a policy with no axis at all rather than a key, and
    # 11.1.24 keeps it outside the bounded contract.
    if any(
        column.listed and any(row is None for row in column.values)
        for column in operands
    ):
        raise DomainRefusal("lookup-null-key-list")

    def cell(*key: float | int | str | None) -> float:
        # 11.1.24: a null query key is a miss, and so is a null or absent
        # answer cell at a key some query reaches. Both take the one path
        # `on_missing` decides. Every key is judged, so a key outside the
        # closed interval still refuses beside a null one.
        misses = [lookup_key(value) for value in key]
        if any(misses):
            return lookup_miss(attrs)
        if name == "mortality.at" and attrs["structure"] == "select_ultimate":
            key = (key[0], min(key[1], attrs["select_period"]), *key[2:])
        answer = values.get(key)
        return lookup_miss(attrs) if answer is None else answer

    return map_values(cell, operands, "f64")


def join_payload(attrs: dict, assumptions: list[dict]) -> dict | None:
    matches = [
        item
        for item in assumptions
        if item["kind"] == "join" and item["fingerprint"] == attrs["right_fingerprint"]
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise DomainRefusal("join-payload-ambiguous")
    payload = matches[0]["payload"]
    if "omitted" in payload:
        return None
    if table_identity(payload) != attrs["right_fingerprint"]:
        raise DomainRefusal("join-payload-identity")
    return payload


def setup_payload(setup: dict, attrs: dict) -> dict:
    right = setup["right"]
    payload = {
        "columns": [
            {"name": name, "dtype": "str" if isinstance(right[name][0], str) else "f64"}
            for name in right
        ],
        "rows": sorted(map(list, zip(*right.values()))),
    }
    if table_identity(payload) != attrs["right_fingerprint"]:
        raise DomainRefusal("join-right-identity")
    return payload


def fixed_step_index(case: dict, attrs: dict) -> list[int]:
    # 11.1.1's fourth form: step is 0..T, and month is k * 12 / n only where
    # steps_per_year = n makes a step whole months. It mints no dates.
    count = attrs["n_periods"]
    per_year = attrs.get("steps_per_year")
    if attrs.get("frequency") is not None or (attrs.get("step_years") is None) == (
        per_year is None
    ):
        raise DomainRefusal("projection-set-fixed-step-form")
    if case["output_column"] == "step":
        return list(range(count + 1))
    if case["output_column"] == "month" and per_year in {1, 2, 3, 4, 6, 12}:
        return [k * (12 // per_year) for k in range(count + 1)]
    raise DomainRefusal("projection-set-fixed-step-column")


def recording_value(case: dict, inputs: dict[str, Column]) -> Column:
    attrs = case["expr"]["attrs"]
    if case["expr"]["name"] == "projection_set":
        rows = len(next(iter(inputs.values())).values)
        if (
            attrs.get("step_years") is not None
            or attrs.get("steps_per_year") is not None
        ):
            return Column(
                "list[i64]", [fixed_step_index(case, attrs) for _ in range(rows)]
            )
        if case["output_column"] != "month" or attrs["frequency"] != "monthly":
            raise DomainRefusal("projection-set-capability")
        return Column(
            "list[i64]",
            [
                list(range(attrs["n_periods"] + 1))
                for _ in next(iter(inputs.values())).values
            ],
        )
    # The right side travels in the artifact as an assumptions entry of kind
    # join, resolved by the full digest the node carries and verified the way
    # a lookup's table is. A case that declares no such entry falls back to
    # the producer setup the published vectors carry -- the same frame reached
    # another way, and checked against the same digest before it is used.
    payload = join_payload(attrs, case.get("assumptions", [])) or setup_payload(
        case["producer_setup"], attrs
    )
    if attrs["how"] != "left" or "," in attrs["on"] or "=" in attrs["on"]:
        raise DomainRefusal("join-capability")
    names = [column["name"] for column in payload["columns"]]
    rows = payload["rows"]
    key, answer = names.index(attrs["on"]), names.index(case["output_column"])
    # 11.1.2: a left join refuses a key that matches no row unless the record
    # says the model keeps it, as null, with on_missing; a null key is a miss.
    keeps_a_miss = attrs.get("on_missing") == "null"
    if attrs.get("on_missing") not in {None, "null"}:
        raise DomainRefusal("join-miss-policy")
    result = []
    for value in inputs[attrs["on"]].values:
        matches = [
            row[answer] for row in rows if value is not None and row[key] == value
        ]
        if not matches and not keeps_a_miss:
            raise DomainRefusal("join-unmatched")
        result.extend(matches or [None])
    return Column(payload["columns"][answer]["dtype"], result)
