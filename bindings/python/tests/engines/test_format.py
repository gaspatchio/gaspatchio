# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The format an engine reads through is the producer's own, not a copy.

The module is a set of names, so what can go wrong with it is that a name
stops being the producer's object -- somebody wraps it, re-implements it, or
points it at a look-alike -- and an engine then checks fingerprints with
something the producer never stamped with. Each test below holds one of those
identities, and one holds the promise that discovering an engine does not
load the format.
"""

from __future__ import annotations

import subprocess
import sys
from importlib import import_module

import gaspatchio.engines.format as fmt
from gaspatchio._semantic import ir, vocabulary

# By module path: ``gaspatchio.frame.graph`` re-exports a function called
# ``fingerprint``, which a ``from`` import would pick up instead of the module.
artifact = import_module("gaspatchio.frame.graph.artifact")
execution = import_module("gaspatchio.frame.graph.execution")
fingerprint = import_module("gaspatchio.frame.graph.fingerprint")
op_json = import_module("gaspatchio.frame.graph.op_json")
validate = import_module("gaspatchio.frame.graph.validate")

NODES = (
    "BinOp",
    "Call",
    "Col",
    "EngineNative",
    "Lit",
    "LitScalar",
    "LitSequenceMember",
    "OpNode",
    "State",
    "WhenThen",
)


def test_every_published_name_resolves() -> None:
    missing = [name for name in fmt.__all__ if not hasattr(fmt, name)]
    assert missing == []


def test_the_nodes_and_vocabulary_are_the_producer_s_own() -> None:
    for name in NODES:
        assert getattr(fmt, name) is getattr(ir, name), name
    assert fmt.VOCABULARY is vocabulary.VOCABULARY
    assert fmt.op_node_from_json is op_json.op_node_from_json


def test_identity_is_checked_with_the_functions_that_stamped_it() -> None:
    # The validator imports the two run encoders under their private names;
    # the published names must be those very functions, or an engine's check
    # and the validator's check are two readings of one grammar.
    assert fmt.encode_text is validate._text  # noqa: SLF001 -- the identity is the point
    assert fmt.encode_sequence is validate._sequence  # noqa: SLF001
    assert fmt.canonical_bytes is fingerprint.canonical_bytes
    assert fmt.local_fingerprint is fingerprint.local_fingerprint
    assert fmt.fingerprint is fingerprint.fingerprint
    assert fmt.document_digest_of is artifact.document_digest_of
    assert fmt.inspect_execution is execution.inspect_execution


def test_a_node_read_through_the_format_fingerprints_as_the_producer_s() -> None:
    node = fmt.op_node_from_json(
        {
            "op": "binop",
            "kind": "sub",
            "left": {"op": "col", "name": "pv_premiums"},
            "right": {"op": "col", "name": "pv_claims"},
        }
    )
    expected = fingerprint.local_fingerprint(
        ir.BinOp("sub", ir.Col("pv_premiums"), ir.Col("pv_claims"))
    )
    assert fmt.local_fingerprint(node) == expected


def test_the_format_names_the_schema_it_reads() -> None:
    assert fmt.SCHEMA_ID == artifact.SCHEMA_ID
    assert fmt.SCHEMA_ID.startswith("gaspatchio-graph/")


def test_discovering_an_engine_does_not_load_the_format() -> None:
    code = (
        "import gaspatchio, gaspatchio.engines, gaspatchio.cli, sys; "
        "print('gaspatchio.engines.format' in sys.modules)"
    )

    out = subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert out.strip() == "False"
