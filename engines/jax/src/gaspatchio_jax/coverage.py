# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The coverage manifest: what this engine claims, generated from what it does.

One row per identifier in the format's vocabulary, and every row comes from
the same capability predicate the runtime applies -- so the manifest cannot
say *lowered* of a form the runtime refuses, which is the failure a
hand-kept table always eventually has.

**Stable claims only.** No observed ratios and no platform stamp: a ratio is
a measurement of one run on one machine, and it lives in
``agreement.json`` where a change to it needs a reason beside the value. A
manifest that carried both would change every time anything was measured, and
a file that changes for two reasons is a file nobody can read a diff of.

The kit's index generator reads this file as a declared input, so the
conformance index carries the engine's claims without the kit ever importing
jax -- it reads a JSON file.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

from gaspatchio.engines.format import VOCABULARY

from .capability import Capability, NodeRecord
from .lowerings import LOWERINGS, load, refused_by_name

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MANIFEST_VERSION", "manifest", "write"]

MANIFEST_VERSION: Final = "gaspatchio-engine-coverage/v0-preview.1"

# The column an admitted form reads. One arriving column, so that the operand
# condition -- every operand an input or a literal -- is satisfied by the
# form a manifest asks about, and an identifier that is off the trace says so
# rather than reading as refused.
_ARRIVING: Final = "x"


def _admitted_form(capability: Capability) -> tuple[dict[str, Any], NodeRecord]:
    """Return the plainest invocation this registration admits.

    Built *from* the capability rather than guessed: the smallest operand
    count it takes, a sequence literal where it requires one, a value inside
    every attribute interval and the first of every admitted attribute value.
    Its operands are columns whose type the record does not state, so the
    declared operand domain goes unchecked here and travels in the row's
    condition instead -- which is what a manifest row is for. A form that
    tripped one of the registration's own restrictions would make every
    restricted identifier read *refused*, which is as wrong as reading them
    all *lowered*.
    """
    count = min(capability.arity) if capability.arity else 1
    args: list[dict[str, Any]] = []
    for position in range(count):
        if position in capability.literal_operands:
            args.append({"op": "lit", "values": []})
        else:
            args.append({"op": "col", "name": f"{_ARRIVING}{position}"})
    node = {
        "op": "call",
        "name": capability.identifier,
        "args": args,
        "attrs": _admitted_attrs(capability),
    }
    reads = tuple(
        f"{_ARRIVING}{position}"
        for position in range(count)
        if position not in capability.literal_operands
    )
    record = NodeRecord(
        node_id=capability.identifier,
        column="answer",
        version=1,
        kind="computed",
        dtype="f64",
        shape="scalar",
        reads=reads,
        expr=node,
        in_final_schema=True,
        arriving_columns=frozenset(reads),
        read_dtypes={},
        # The plainest invocation reads columns that arrived, which is what
        # lets an off-trace registration read *lowered-off-trace* here rather
        # than refused: the operand condition is about the node an operand resolves
        # to, and these resolve to arrivals.
        read_kinds=dict.fromkeys(reads, "input"),
    )
    return node, record


def _admitted_attrs(capability: Capability) -> dict[str, Any]:
    """Return one admitted setting for every attribute this registration names."""
    written: dict[str, Any] = {}
    for name, admitted in (capability.attrs or {}).items():
        written[name] = _read_back(admitted[0])
    conditional = capability.attrs_required_when or {}
    for name, (low, high) in (capability.attr_bounds or {}).items():
        if _not_required_here(name, conditional, written):
            # An attribute the form's own settings do not call for is left
            # out of the form. ``mortality.at``'s select period is the case:
            # the plainest form is an aggregate basis, and 11.1.10 says an
            # aggregate basis has no select period at all rather than one
            # set to nought.
            continue
        inside = low if low is not None else high
        written[name] = inside if inside is not None else 0
    for name in capability.attrs_numeric:
        written.setdefault(name, 1.0)
    for name in capability.attrs_required:
        written.setdefault(name, _STATED_ATTR)
    for name, (deciding, values) in (capability.attrs_required_when or {}).items():
        # The admitted form takes the first admitted setting of the deciding
        # attribute, so where that is the setting the requirement turns on,
        # the required attribute has to be there too -- otherwise the plainest
        # invocation this registration admits would trip its own rule and the
        # row would read *refused*.
        if str(written.get(deciding)) in values:
            written.setdefault(name, _STATED_ATTR)
    return written


def _not_required_here(
    name: str,
    conditional: dict[str, tuple[str, tuple[str, ...]]],
    written: dict[str, Any],
) -> bool:
    """Return whether this attribute's own condition is one the form does not meet."""
    stated = conditional.get(name)
    return stated is not None and str(written.get(stated[0])) not in stated[1]


def _read_back(admitted: str) -> Any:  # noqa: ANN401 -- an attribute is a flat typed value
    """Return an admitted attribute value as the tree writes it, not as text.

    An attribute is a flat typed value (12.1) and a registration states the
    values it admits as text, so the two meet here: a truth value and a whole
    number are written back as themselves rather than as their spelling. A
    basis of 0 written as ``"0"`` is a basis no clause names.
    """
    if admitted in ("True", "False"):
        return admitted == "True"
    if admitted.lstrip("-").isdigit():
        return int(admitted)
    return admitted


# What stands in an admitted form for an attribute whose value is free but
# whose presence is not. Any non-null value says the same thing here.
_STATED_ATTR = "stated"


def manifest() -> dict[str, Any]:
    """Return this engine's claims about every identifier the format names."""
    load()
    from . import __version__  # noqa: PLC0415 -- the package's own version, once

    operations: list[dict[str, Any]] = []
    for operation in VOCABULARY:
        registered = LOWERINGS.get(operation.identifier)
        if registered is None:
            # Two ways a row reads *refused*, and they are not one thing. An
            # identifier in ``REFUSED`` is one this engine will not answer and
            # says why; one in neither table is one nobody has reached yet.
            # A reader deciding whether to wait needs to be able to tell them
            # apart from the row alone.
            stated = refused_by_name(operation.identifier)
            operations.append(
                {
                    "identifier": operation.identifier,
                    "status": "refused",
                    "condition": (
                        stated[0]
                        if stated is not None
                        else "this engine has no lowering for it yet"
                    ),
                    "clause": stated[1] if stated is not None else operation.clause,
                }
            )
            continue
        capability = registered[1]
        node, record = _admitted_form(capability)
        status = capability.status_of(node, record)
        operations.append(
            {
                "identifier": operation.identifier,
                "status": status.status,
                # Everything the registration restricts, always -- not only
                # what the admitted form happened to trip. A row that read
                # "lowered" with nothing beside it would be claiming the
                # identifier where what is claimed is a shape of invocation.
                "condition": _condition(status.condition, capability),
                "clause": status.clause or operation.clause,
            }
        )
    counts: dict[str, int] = {}
    for row in operations:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
    return {
        "schema": MANIFEST_VERSION,
        "engine": "jax",
        "engine_version": __version__,
        "operations": operations,
        "counts": counts,
    }


def _condition(stated: str | None, capability: Capability) -> str | None:
    """Return the row's condition, in three parts joined into one sentence.

    What the status said, what the registration restricts, and whatever else
    the registration has to say. Joined rather than chosen between, because
    the three answer different
    questions: why this form was refused, what shape of invocation is claimed,
    and what a reader should know beside both.
    """
    written = capability.stated_condition()
    parts = [stated]
    if written and (stated is None or written not in stated):
        parts.append(written)
    parts.append(capability.note)
    return "; ".join(part for part in parts if part) or None


def write(destination: Path) -> dict[str, Any]:
    """Write the manifest to ``destination`` and return what was written."""
    document = manifest()
    destination.write_text(
        json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return document
