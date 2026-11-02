# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the identifier-to-clause map the kit hands a second implementation.

``contracts.json`` says, for every operation identifier this format owns,
which section of the specification answers for it. It used to be typed by
hand beside the two tables that hold the same identifiers, and nothing
checked that the three agreed. It is now the clause column of the one row
per identifier the producer keeps, printed out.

**The row is read, not imported.** This file is stdlib only and never
imports ``gaspatchio``, for the reason the rest of the kit is: what the kit
publishes must be derivable from public source and data, by anyone, without
building the producer's extension. The table is a plain literal in a module
that imports nothing outside the standard library either, so it is loaded
from its path the way the proxy generator loads the operation declarations.

Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_contracts.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

``build_kit.py`` reads the file this writes, so it runs after. The bytes are
pinned by ``tests/graph/test_vocabulary.py``, which asks this module for
them and compares them with the file on disk: a row whose clause moves
without the checked-in map moving fails there rather than shipping a kit
that points a consumer at the wrong section.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

SOURCE = Path(__file__).resolve().parent
CONTRACTS = SOURCE / "contracts.json"
VOCABULARY = SOURCE.parents[2] / "bindings/python/gaspatchio/_semantic/vocabulary.py"


def _vocabulary() -> ModuleType:
    """Load the identifier table without importing ``gaspatchio``."""
    module_name = "_gaspatchio_operation_vocabulary"
    spec = importlib.util.spec_from_file_location(module_name, VOCABULARY)
    if spec is None or spec.loader is None:
        msg = f"Cannot load the identifier table from {VOCABULARY}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[module_name]
    return module


def contracts_document() -> dict[str, str]:
    """Return every identifier's specification clause, ordered by identifier.

    Alphabetical rather than the table's own order, because this file is
    looked things up in rather than read through: a consumer holding an
    identifier wants the clause beside it without scanning.
    """
    rows: tuple[Any, ...] = _vocabulary().VOCABULARY
    return {row.identifier: row.clause for row in sorted(rows, key=_identifier)}


def _identifier(row: Any) -> str:  # noqa: ANN401 - the row type is loaded by path
    """Return one row's identifier, for ordering the printed map."""
    identifier: str = row.identifier
    return identifier


def contracts_bytes() -> bytes:
    """Return the exact bytes of the checked-in map."""
    return (json.dumps(contracts_document(), indent=2, allow_nan=False) + "\n").encode()


def main() -> None:
    """Write the map, refusing a duplicate identifier before it ships."""
    document = contracts_document()
    rows: tuple[Any, ...] = _vocabulary().VOCABULARY
    if len(document) != len(rows):
        msg = "identifiers must be unique across the table"
        raise ValueError(msg)
    CONTRACTS.write_bytes(contracts_bytes())
    print("operation clauses", len(document))


if __name__ == "__main__":
    main()
