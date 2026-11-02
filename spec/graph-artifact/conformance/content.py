# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Independently re-derive the published content-grammar vectors (section 12.3).

Only the Python standard library is used. Each case describes a frame in plain
JSON; this encoder writes section 12.3's bytes for it from the specification
alone and compares them, and their SHA-256, with what the case publishes.
Run: python -I content.py path/to/content-identity.json
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
from datetime import date
from pathlib import Path

_TAGS = {"bool": 0x11, "i64": 0x12, "f64": 0x13, "str": 0x14, "date": 0x16}
_LIST, _DATETIME = 0x15, 0x17
_NANOSECONDS_PER = {"ns": 1, "us": 1_000, "ms": 1_000_000}
_EPOCH = date(1970, 1, 1)
_PRESENT, _MISSING = b"\x02", b"\x01\x00"
_I64 = range(-(2**63), 2**63)


class Refusal(ValueError):
    """A frame section 12.3 does not write, named by the case's refusal code."""


def varint(value: int) -> bytes:
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def whole(value: int) -> bytes:
    return varint(value * 2 if value >= 0 else -value * 2 - 1)


def text(value: str) -> bytes:
    data = value.encode("utf-8")
    return varint(len(data)) + data


def zone_text(zone: str | None) -> bytes:
    # 12.3: a zone-naive column is read as UTC (section 10); both write empty.
    return text("" if zone in {None, "UTC"} else zone)


def tag(dtype: str, zone: str | None) -> bytes:
    if dtype.startswith("list["):
        return bytes([_LIST]) + tag(dtype[5:-1], zone)
    if dtype == "datetime":
        return bytes([_DATETIME]) + zone_text(zone)
    return bytes([_TAGS[dtype]])


def value(item: object, dtype: str, unit: str | None) -> bytes:
    if dtype == "bool":
        return b"\x01" if item else b"\x00"
    if dtype == "i64":
        return whole(item)
    if dtype == "f64":
        # Every NaN one quiet payload; a negative zero written as zero.
        if math.isnan(item):
            return bytes.fromhex("7ff8000000000000")
        return struct.pack(">d", 0.0 if item == 0 else item)
    if dtype == "str":
        return text(item)
    if dtype == "date":
        return whole((date.fromisoformat(item) - _EPOCH).days)
    # datetime: the count put on nanoseconds, then divided towards the
    # earlier microsecond (Python's floor division) with the 0-999 remainder.
    nanoseconds = item * _NANOSECONDS_PER[unit]
    microseconds = nanoseconds // 1000
    # 12.3: a count whose microseconds leave i64 is refused, never wrapped
    # onto another instant (only a millisecond count can reach that far).
    if microseconds not in _I64:
        raise Refusal("datetime-microseconds-past-i64")
    return whole(microseconds) + varint(nanoseconds % 1000)


def marked(item: object, dtype: str, unit: str | None) -> bytes:
    if item is None:
        return _MISSING
    if dtype.startswith("list["):
        inner = dtype[5:-1]
        return (
            _PRESENT
            + varint(len(item))
            + b"".join(marked(member, inner, unit) for member in item)
        )
    return _PRESENT + value(item, dtype, unit)


def encode(columns: list[dict]) -> bytes:
    out = bytearray(varint(len(columns)))
    for column in columns:
        dtype, unit = column["dtype"], column.get("unit")
        out += text(column["name"]) + tag(dtype, column.get("zone"))
        out += varint(len(column["values"]))
        for item in column["values"]:
            out += marked(item, dtype, unit)
    return bytes(out)


def verify(case: dict) -> list[str]:
    if "refusal" in case:
        try:
            data = encode(case["columns"])
        except Refusal as refused:
            said = str(refused)
            return [] if said == case["refusal"] else [f"refused as {said}"]
        return [f"not refused: wrote {data.hex()}"]
    data = encode(case["columns"])
    findings = []
    if data.hex() != case["bytes"]:
        findings.append(f"bytes: {data.hex()} != {case['bytes']}")
    if "sha256:" + hashlib.sha256(data).hexdigest() != case["digest"]:
        findings.append("digest")
    return findings


def main() -> None:
    document = json.loads(Path(sys.argv[1]).read_text())
    failures = {
        case["id"]: found for case in document["cases"] if (found := verify(case))
    }
    print(
        json.dumps(
            {
                "algorithm": document["fingerprint_algorithm"],
                "cases": len(document["cases"]),
                "failures": failures,
            },
            indent=2,
        )
    )
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
