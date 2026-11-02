# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The published calculation-graph artifact schema, shipped inside the package.

An artifact's ``schema`` field carries a string identifier. A consumer resolves
that identifier to a schema document through :data:`SCHEMA_IDENTIFIERS`: the
string is a key, not a locator, and it is never parsed for a version and never
fetched as a URL.

Reading a schema never touches the network. The document is package data, read
through :mod:`importlib.resources`, so it resolves the same way from an
installed wheel, a zipped distribution, and any working directory.
"""

from __future__ import annotations

import importlib.resources
import json
from typing import Any, Final, cast

__all__ = ["SCHEMA_IDENTIFIERS", "load_schema"]

# The identifier table. A row stays here for as long as artifacts bearing that
# identifier exist: removing one is what breaks a stored artifact, and adding
# one never does.
#
# **The earlier row places a document; it does not validate one, and the
# difference is worth stating where the row is.** This package ships one
# schema document, and while the preview is open that document pins both the
# schema identifier and the byte-grammar token by ``const`` -- section 12.2
# says why, and says the pin relaxes to a pattern at ``/v0`` final. So a
# ``v0-preview.1`` document resolved through this table reaches a schema that
# refuses it, by that pin and by ``document_digest`` being required. What the
# row buys is the refusal a reader can act on: "this document is under an
# earlier edition of the format" rather than "this build cannot place this
# identifier at all", which is the difference between a reader who knows what
# they are holding and one who does not. A grammar was never translatable
# between the two either way (section 12.2), so nothing is lost by the row
# that a second document would have recovered.
SCHEMA_IDENTIFIERS: Final[dict[str, str]] = {
    "gaspatchio-graph/v0-preview.1": "gaspatchio-graph-v0.schema.json",
    "gaspatchio-graph/v0-preview.2": "gaspatchio-graph-v0.schema.json",
    "gaspatchio-graph/v0-preview.3": "gaspatchio-graph-v0.schema.json",
}


def load_schema(name: str = "gaspatchio-graph-v0.schema.json") -> dict[str, Any]:
    """Return the published schema document named ``name``.

    Args:
        name: The schema document's file name, as :data:`SCHEMA_IDENTIFIERS`
            gives it for an artifact's ``schema`` identifier. A name that table
            does not carry is refused rather than resolved: the name is a value
            read out of the table, never a path into the package.

    Returns:
        The parsed schema document.

    Raises:
        ValueError: If ``name`` is not one of the documents
            :data:`SCHEMA_IDENTIFIERS` names.

    Examples:
        >>> from gaspatchio.schemas import load_schema
        >>> load_schema()["$id"]
        'https://gaspatchio.dev/schemas/gaspatchio-graph-v0.schema.json'
    """
    published = sorted(set(SCHEMA_IDENTIFIERS.values()))
    if name not in published:
        msg = (
            f"No published schema document is named {name!r}. This package "
            f"ships {', '.join(published)}. A schema name is a value read out "
            "of SCHEMA_IDENTIFIERS rather than a path: resolve an artifact's "
            "schema string through that table and pass what it gives back."
        )
        raise ValueError(msg)
    source = importlib.resources.files(__name__).joinpath(name).read_text("utf-8")
    return cast("dict[str, Any]", json.loads(source))
