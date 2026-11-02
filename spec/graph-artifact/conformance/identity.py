# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Independently reproduce the published §12.5 corpus's current-token identities.

Only the Python standard library is used. The model below transcribes §12.5;
it is deliberately not a general artifact loader or an authenticity check.
Every identity the corpus publishes is recomputed here: each node's local and
upstream digests, ``graph_fingerprint``, the formulas-only
``formulas_fingerprint`` of §12.6, and the ``document_digest`` seal.
Run: python -I identity.py path/to/corpus.json
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
from datetime import date
from pathlib import Path
from typing import Any


def varint(value: int) -> bytes:
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def string(value: str) -> bytes:
    data = value.encode("utf-8")
    return varint(len(data)) + data


def decimal(value: float) -> bytes:
    # 12.1: every NaN collapses to one quiet payload; a negative zero keeps
    # its own sign bit and hashes apart from a positive one.
    if math.isnan(value):
        return bytes.fromhex("7ff8000000000000")
    return struct.pack(">d", value)


def content_decimal(value: float) -> bytes:
    # 12.3's content grammar, which is a different grammar: it still writes a
    # negative zero as zero, and says so in its own words rather than by
    # pointing at 12.1. Only the injected column below is hashed under it.
    if math.isnan(value):
        return bytes.fromhex("7ff8000000000000")
    return struct.pack(">d", 0.0 if value == 0 else value)


def scalar(value: Any) -> bytes:
    if value is None:
        return b"\x10"
    if isinstance(value, bool):
        return b"\x11" + bytes([int(value)])
    if isinstance(value, int):
        return b"\x12" + varint(value * 2 if value >= 0 else -value * 2 - 1)
    if isinstance(value, float):
        return b"\x13" + decimal(value)
    if isinstance(value, str):
        return b"\x14" + string(value)
    if isinstance(value, list):
        return b"\x15" + varint(len(value)) + b"".join(scalar(item) for item in value)
    if isinstance(value, date):
        days = (value - date(1970, 1, 1)).days
        return b"\x16" + varint(days * 2 if days >= 0 else -days * 2 - 1)
    raise TypeError(type(value).__name__)


def encode(tree: dict[str, Any]) -> bytes:
    kind = tree["op"]
    if kind == "col":
        return b"\x01" + string(tree["name"])
    if kind == "lit":
        return b"\x02" + scalar(tree["value"])
    if kind == "binop":
        return (
            b"\x03"
            + string(tree["kind"])
            + encode(tree["left"])
            + encode(tree["right"])
        )
    if kind == "when_then":
        return b"\x05" + b"".join(
            encode(tree[key]) for key in ("cond", "then", "otherwise")
        )
    if kind == "call":
        args = tree["args"]
        attrs = tree["attrs"]
        return (
            b"\x04"
            + string(tree["name"])
            + varint(len(args))
            + b"".join(encode(arg) for arg in args)
            + varint(len(attrs))
            + b"".join(string(key) + scalar(attrs[key]) for key in sorted(attrs))
        )
    raise ValueError(f"not a corpus tree: {kind}")


def col(name: str) -> dict[str, Any]:
    return {"op": "col", "name": name}


def lit(value: Any) -> dict[str, Any]:
    return {"op": "lit", "value": value}


def binary(name: str, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {"op": "binop", "kind": name, "left": left, "right": right}


def call(
    name: str, args: list[dict[str, Any]], attrs: dict[str, Any]
) -> dict[str, Any]:
    return {"op": "call", "name": name, "args": args, "attrs": attrs}


def conditional(
    condition: dict[str, Any], yes: dict[str, Any], no: dict[str, Any]
) -> dict[str, Any]:
    return {"op": "when_then", "cond": condition, "then": yes, "otherwise": no}


def stamp(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# 12.6's content attributes: the ones whose value names a value object's
# content, by the identifier carrying them. Each is replaced by the text
# "masked", whatever it held, a null included; nothing else in a tree moves.
_MASKED_BY_NAME: dict[str, tuple[str, ...]] = {
    "lookup": ("table_fingerprint",),
    "join": ("right_fingerprint",),
    "mortality.at": ("mortality", "table_fingerprint"),
    "injected": ("content", "origin"),
}


def masked_attributes(name: str, attrs: dict[str, Any]) -> set[str]:
    """Return the keys of a call's attributes that 12.6 masks."""
    if name in _MASKED_BY_NAME:
        return set(_MASKED_BY_NAME[name])
    if name == "projection_set":
        # The start and the frequency are the schedule's own content written
        # out again, so they go with its digest -- only on a call carrying it.
        restated = {"start", "frequency"} if "schedule_source_sha" in attrs else set()
        return {"schedule_source_sha", *restated}
    families = (
        (("curve.",), "curve"),
        (("schedule.", "projection_frame.", "rollforward."), "schedule"),
    )
    hidden = {key for prefixes, key in families if name.startswith(prefixes)}
    return hidden | ({"schedule"} if name == "rollforward" else set())


def masked(tree: dict[str, Any]) -> dict[str, Any]:
    """Return the tree with every content attribute's value replaced by "masked"."""
    kind = tree["op"]
    if kind == "binop":
        return {**tree, "left": masked(tree["left"]), "right": masked(tree["right"])}
    if kind == "when_then":
        return {
            **tree,
            **{key: masked(tree[key]) for key in ("cond", "then", "otherwise")},
        }
    if kind == "call":
        hidden = masked_attributes(tree["name"], tree["attrs"])
        return {
            **tree,
            "args": [masked(arg) for arg in tree["args"]],
            # A key the call does not carry stays absent: whether a
            # conditional key is present at all is part of the tree.
            "attrs": {
                key: "masked" if key in hidden else value
                for key, value in tree["attrs"].items()
            },
        }
    return tree


def corpus_trees() -> dict[str, dict[str, Any]]:
    # The content grammar: one f64 column, its fixed injection name, and 3
    # present values. No producer hash or published digest is used as an oracle.
    injection = varint(1) + string("injected") + b"\x13" + varint(3)
    injection += b"".join(
        b"\x02" + content_decimal(value) for value in (0.01, -0.02, 0.03)
    )
    return {
        "death_claims@1": binary("mul", col("sum_assured"), lit(0.00123)),
        "ceded_claims@1": conditional(
            binary("gt", col("sum_assured"), lit(200000.0)),
            col("death_claims"),
            lit(0.0),
        ),
        "select_loaded_claims@1": binary(
            "mul", col("death_claims"), lit([1.5, 1.25, 1.0])
        ),
        "prior_period_claims@1": call(
            "projection.at_period",
            [col("select_loaded_claims"), lit(0.0)],
            {"relative_period": -1},
        ),
        "simulated_shock@1": call(
            "injected", [], {"content": stamp(injection), "origin": "series"}
        ),
        "net_cashflow@1": binary(
            "add",
            binary(
                "sub", binary("mul", col("sum_assured"), lit(0.02)), col("death_claims")
            ),
            col("ceded_claims"),
        ),
        "net_cashflow@2": binary(
            "mul", col("net_cashflow"), binary("add", lit(1.0), col("simulated_shock"))
        ),
        "post_reform@1": conditional(
            binary("gt", col("entry_date"), lit(date(2022, 1, 1))), lit(1.0), lit(0.0)
        ),
        "total_claims@1": call("sum", [col("select_loaded_claims")], {}),
        # The column gspv0-preview-3 added: a decimal literal whose sign the
        # grammar keeps. Under gspv0-preview-2 its otherwise branch hashed as
        # 0.0 and this node's digests were the positive zero's.
        "unceded_claims@1": conditional(
            binary("eq", col("ceded_claims"), lit(0.0)),
            col("death_claims"),
            lit(-0.0),
        ),
    }


def verify(document: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if document["fingerprint_algorithm"] != "gspv0-preview-3":
        return ["fingerprint_algorithm: unsupported"]
    trees = corpus_trees()
    expected_ids = set(trees) | {"sum_assured", "entry_date"}
    if {node["id"] for node in document["nodes"]} != expected_ids:
        return ["corpus node set differs"]
    digests: dict[str, bytes] = {}
    masked_digests: dict[str, bytes] = {}
    for node in document["nodes"]:
        identifier = node["id"]
        leaf = b"\x20" + string(node["column"]) + string(node["dtype"])
        raw = encode(trees[identifier]) if identifier in trees else leaf
        local = hashlib.sha256(raw).digest()
        if "sha256:" + local.hex() != node["local_fingerprint"]:
            findings.append(identifier + ": local_fingerprint")
        full = hashlib.sha256(
            local + b"".join(digests[parent] for parent in node["reads"])
        ).digest()
        if "sha256:" + full.hex() != node["fingerprint"]:
            findings.append(identifier + ": fingerprint")
        digests[identifier] = full
        # 12.6: the same fold over masked trees. A leaf's masked local digest
        # is its own local digest -- a name and a type carry no content -- and
        # it is this reader's recomputation, never the published value.
        masked_local = (
            hashlib.sha256(encode(masked(trees[identifier]))).digest()
            if identifier in trees
            else local
        )
        masked_digests[identifier] = hashlib.sha256(
            masked_local + b"".join(masked_digests[parent] for parent in node["reads"])
        ).digest()
    # This corpus deliberately has no assumptions or holes. These two empty
    # counted sections remain part of its graph bytes.
    if document["assumptions"] or document["holes"]:
        findings.append("corpus assumption/hole set differs")
    graph = (
        varint(len(digests))
        + b"".join(string(key) + digests[key] for key in sorted(digests))
        + b"\x00\x00"
    )
    if stamp(graph) != document["graph_fingerprint"]:
        findings.append("graph_fingerprint")
    # 12.6: the pairs section and the unaccounted names, with the tables
    # section left out rather than masked. The corpus publishes the figure
    # (12.5), so its absence is a finding too.
    formulas = (
        varint(len(masked_digests))
        + b"".join(string(key) + masked_digests[key] for key in sorted(masked_digests))
        + b"\x00"
    )
    if stamp(formulas) != document.get("formulas_fingerprint"):
        findings.append("formulas_fingerprint")
    unsealed = {
        key: value for key, value in document.items() if key != "document_digest"
    }
    raw_document = json.dumps(
        unsealed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    if stamp(raw_document) != document.get("document_digest"):
        findings.append("document_digest")
    return findings


def main() -> None:
    artifact = json.loads(Path(sys.argv[1]).read_text())
    failures = verify(artifact)
    print(
        json.dumps(
            {
                "algorithm": "gspv0-preview-3",
                "nodes": len(artifact["nodes"]),
                "failures": failures,
            },
            indent=2,
        )
    )
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
