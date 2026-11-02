# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What an engine reads an artifact through: the public edge of the format.

An engine runs a document, not a model. To do that in Python it needs three
things from the core: the formula nodes a document's ``expr`` fields are made
of, the vocabulary of operations a document may use, and the functions that
read a node from JSON and check the identity stamps the producer wrote. This
module names all three in one place, so a second engine -- the JAX engine in
this repository, or one written by somebody else -- reads the format here and
never reaches into the modules the core keeps private.

**It is a preview, and it moves with the schema.** Everything below is the
reading of :data:`SCHEMA_ID`. While the schema is a ``v0-preview``, a name here
may change, but only together with a schema bump and a changelog line saying
what moved; it does not change quietly between two releases that write the same
schema. The standard itself is still the JSON document and its specification: an
engine in another language reads those and needs nothing here.

**The fingerprints are checked with the function that stamped them.** A second
engine that re-implemented the byte grammar could disagree with the producer and
never say so. :func:`canonical_bytes`, :func:`local_fingerprint`,
:func:`fingerprint` and the two run encoders are the producer's own, so a check
made through this module is the same check the producer's validator makes.

Importing this module loads the graph modules it reads through. It is imported
by name when an engine needs it, never from :mod:`gaspatchio.engines` itself, so
discovering an engine stays as cheap as it was.

**A package, so that it is a door.** Everything here is written elsewhere in
the core, and a module that only re-publishes is refused by
``tests/test_no_shim_modules.py`` unless it is a package's ``__init__.py`` --
the one address a reader knows to look at. This is that address for the
format. It is also the unit that separates into a distribution of its own,
with no modelling runtime behind it, when the first engine is written outside
this repository. Until then it is part of the engine protocol, which 1.0
publishes as a preview outside its stability promise: a name here changes only
with the schema identifier, and the changelog records it.
"""

from __future__ import annotations

from gaspatchio._identity import SHA256_PREFIX
from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    LitScalar,
    LitSequenceMember,
    OpNode,
    State,
    WhenThen,
)
from gaspatchio._semantic.join_keys import join_key_sides
from gaspatchio._semantic.vocabulary import VOCABULARY
from gaspatchio.frame.graph.artifact import (
    SCHEMA_ID,
    book_columns,
    book_of,
    document_digest_of,
)
from gaspatchio.frame.graph.execution import ExecutionInspection, inspect_execution
from gaspatchio.frame.graph.fingerprint import (
    _sequence as encode_sequence,
)
from gaspatchio.frame.graph.fingerprint import (
    _text as encode_text,
)
from gaspatchio.frame.graph.fingerprint import (
    canonical_bytes,
    fingerprint,
    local_fingerprint,
    selection_local,
    selection_section,
)
from gaspatchio.frame.graph.op_json import op_node_from_json
from gaspatchio.frame.graph.selection import SelectionRefusedError
from gaspatchio.frame.graph.selection_replay import apply_selection

__all__ = [
    "SCHEMA_ID",
    "SHA256_PREFIX",
    "VOCABULARY",
    "BinOp",
    "Call",
    "Col",
    "EngineNative",
    "ExecutionInspection",
    "Lit",
    "LitScalar",
    "LitSequenceMember",
    "OpNode",
    "SelectionRefusedError",
    "State",
    "WhenThen",
    "apply_selection",
    "book_columns",
    "book_of",
    "canonical_bytes",
    "document_digest_of",
    "encode_sequence",
    "encode_text",
    "fingerprint",
    "inspect_execution",
    "join_key_sides",
    "local_fingerprint",
    "op_node_from_json",
    "selection_local",
    "selection_section",
]
