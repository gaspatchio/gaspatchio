# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the content-grammar identity vectors (section 12.3), the datetime carrier first.

Each case is a frame described in plain JSON -- columns in order, each with a
name, a type and its values -- and the bytes section 12.3 writes for it,
spelled out **by hand** below from the grammar's table, with the SHA-256 over
them. None was read off the producer: the producer's native encoder and its
Python reference are what ``tests/graph/test_content_identity_vectors.py``
holds to these bytes, and the kit's ``content.py`` re-derives them with the
standard library alone.

A ``datetime`` column states its ``unit`` (``ms``, ``us`` or ``ns``) and its
``zone`` (null for zone-naive); each value is a whole count of that unit since
1970-01-01T00:00:00Z, so the instant is the same whatever zone shows it. A
``date`` value is ISO text. A refusal case publishes no bytes: it names the
refusal every encoder must meet instead (12.3: a millisecond count whose
microseconds leave ``i64`` is refused, never wrapped onto another instant).
Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_content_identity_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

DESTINATION = (
    Path(__file__).resolve().parents[3]
    / "bindings/python/gaspatchio/schemas/conformance/content-identity.json"
)
AUCKLAND = "Pacific/Auckland"
# "Pacific/Auckland" behind its byte length, sixteen.
AUCKLAND_TEXT = "10" + AUCKLAND.encode().hex()
# One column named "v": the count of columns, then the name behind its length.
V = "01 0176"
# The instant one millisecond past the epoch: microsecond 1000, zigzag 2000.
ONE_MS = "02 d00f 00"
# 2020-01-01T12:00:00Z in ns, the R116 cut-off, and a claim 500 ns after it.
CUT_OFF_NS = 1_577_880_000_000_000_000


def zigzag_varint(value: int) -> str:
    """Section 12.1's whole number: zigzag, then base-128 low group first."""
    return varint(value * 2 if value >= 0 else -value * 2 - 1)


def varint(value: int) -> str:
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return out.hex()


def datetime_column(values: list, *, unit: str = "us", zone: str | None = None) -> dict:
    return {
        "name": "v",
        "dtype": "datetime",
        "unit": unit,
        "zone": zone,
        "values": values,
    }


# The cut-off's microsecond, written once by hand from the count above.
CUT_OFF_US = zigzag_varint(CUT_OFF_NS // 1000)

CASES: list[tuple[str, str, list[dict], str]] = [
    (
        "worked-example-mortality-basis",
        "Section 12.3's worked example: two columns, i64 then f64.",
        [
            {"name": "age", "dtype": "i64", "values": [45, 46, 47]},
            {"name": "rate", "dtype": "f64", "values": [0.001, 0.0012, 0.0015]},
        ],
        (
            "02036167651203025a025c025e04726174651303023f50624dd2f1a9fc"
            "023f53a92a30553261023f589374bc6a7efa"
        ),
    ),
    (
        "datetime-naive-microseconds",
        "One ms past the epoch, zone-naive: an empty zone, microsecond 1000, 0 ns.",
        [datetime_column([1_000])],
        f"{V} 17 00 01 {ONE_MS}",
    ),
    (
        "datetime-same-instant-in-milliseconds",
        "The same instant kept in ms has the same encoding.",
        [datetime_column([1], unit="ms")],
        f"{V} 17 00 01 {ONE_MS}",
    ),
    (
        "datetime-same-instant-in-nanoseconds",
        "The same instant kept in ns has the same encoding.",
        [datetime_column([1_000_000], unit="ns")],
        f"{V} 17 00 01 {ONE_MS}",
    ),
    (
        "datetime-utc-digests-as-naive",
        "A UTC column writes the empty zone: naive is read as UTC (section 10).",
        [datetime_column([1_000], zone="UTC")],
        f"{V} 17 00 01 {ONE_MS}",
    ),
    (
        "datetime-zone-in-the-header",
        "The same instant shown in Pacific/Auckland is another column.",
        [datetime_column([1_000], zone=AUCKLAND)],
        f"{V} 17 {AUCKLAND_TEXT} 01 {ONE_MS}",
    ),
    (
        "datetime-nanosecond-before-the-epoch",
        "-1 ns is microsecond -1 (zigzag 01) and 999 ns past it (e7 07).",
        [datetime_column([-1], unit="ns")],
        f"{V} 17 00 01 02 01 e707",
    ),
    (
        "datetime-sub-microsecond-instants-apart",
        "A cut-off and a claim 500 ns after it: one microsecond, 0 then 500 ns.",
        [datetime_column([CUT_OFF_NS, CUT_OFF_NS + 500], unit="ns")],
        f"{V} 17 00 02 02 {CUT_OFF_US} 00 02 {CUT_OFF_US} f403",
    ),
    (
        "datetime-least-nanosecond",
        "i64's least ns: microsecond -9223372036854776 and 192 ns past it.",
        [datetime_column([-(2**63)], unit="ns")],
        f"{V} 17 00 01 02 {zigzag_varint(-9_223_372_036_854_776)} c001",
    ),
    (
        "datetime-missing-value",
        "A missing instant is the absent marker and its placeholder byte.",
        [datetime_column([None, 1_000])],
        f"{V} 17 00 02 01 00 {ONE_MS}",
    ),
    (
        "datetime-sequence-carries-the-zone",
        "list[datetime]: the zone behind the element's tag, each member marked.",
        [
            {
                "name": "v",
                "dtype": "list[datetime]",
                "unit": "ns",
                "zone": AUCKLAND,
                "values": [[1_000_000, None], [], None],
            }
        ],
        f"{V} 15 17 {AUCKLAND_TEXT} 03 02 02 {ONE_MS} 01 00 02 00 01 00",
    ),
    (
        "datetime-milliseconds-at-the-edge-of-i64",
        "The ms counts whose microseconds an i64 just holds scale up exactly.",
        [datetime_column([9_223_372_036_854_775, -9_223_372_036_854_775], unit="ms")],
        (
            f"{V} 17 00 02 02 {zigzag_varint(9_223_372_036_854_775_000)} 00"
            f" 02 {zigzag_varint(-9_223_372_036_854_775_000)} 00"
        ),
    ),
]

# Frames no encoder may write: (id, note, columns, the refusal each must meet).
REFUSALS: list[tuple[str, str, list[dict], str]] = [
    (
        "datetime-milliseconds-past-i64-refused",
        "One ms past the edge: its microseconds leave i64, and wrapping would "
        "write the instant -9223372036854775616 us. Refused by name, not wrapped.",
        [datetime_column([0, None, 9_223_372_036_854_776], unit="ms")],
        "datetime-microseconds-past-i64",
    ),
    (
        "datetime-milliseconds-before-i64-refused",
        "One ms below the edge, the other side: refused by name.",
        [datetime_column([-9_223_372_036_854_776], unit="ms")],
        "datetime-microseconds-past-i64",
    ),
]


def main() -> None:
    cases = []
    for identifier, note, columns, spelled in CASES:
        data = bytes.fromhex(spelled.replace(" ", ""))
        cases.append(
            {
                "id": identifier,
                "note": note,
                "columns": columns,
                "bytes": data.hex(),
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
        )
    for identifier, note, columns, refusal in REFUSALS:
        cases.append(
            {"id": identifier, "note": note, "columns": columns, "refusal": refusal}
        )
    document = {
        "schema": "gaspatchio-content-identity-vectors/v0-preview.1",
        "fingerprint_algorithm": "gspv0-preview-3",
        "grammar": "12.3",
        "cases": cases,
    }
    DESTINATION.write_text(json.dumps(document, indent=2) + "\n")


if __name__ == "__main__":
    main()
