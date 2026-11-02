# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Section 7.6's recorded selection, applied to the book before the answer."""

from __future__ import annotations

from collections.abc import Callable

from reader.shared import Column, DomainRefusal
from reader.tables import setup_payload


def kept_rows(
    case: dict, inputs: dict[str, Column], evaluate: Callable[[dict, dict], Column]
) -> dict[str, Column]:
    """Return the inputs at the rows every recorded step keeps, in book order.

    A filter keeps a row where its predicate is true and drops it where the
    predicate is false or null. A semi join keeps a row whose key the right
    side holds and an anti join one whose key it does not; a null key matches
    nothing. The steps compose in the order they are listed.
    """
    rows = list(range(len(next(iter(inputs.values())).values)))
    for step in case["selection"]:
        current = {
            name: Column(column.dtype, [column.values[row] for row in rows])
            for name, column in inputs.items()
        }
        if step["kind"] == "filter":
            answer = evaluate(step["expr"], current)
            if answer.dtype != "bool":
                raise DomainRefusal("selection-predicate-type")
            rows = [row for row, keep in zip(rows, answer.values) if keep is True]
            continue
        attrs = step["expr"]["attrs"]
        if attrs["how"] != step["kind"] or "," in attrs["on"] or "=" in attrs["on"]:
            raise DomainRefusal("selection-join-capability")
        payload = setup_payload({"right": step["right"]}, attrs)
        names = [column["name"] for column in payload["columns"]]
        held = {row[names.index(attrs["on"])] for row in payload["rows"]}
        matched = [
            value is not None and value in held
            for value in current[attrs["on"]].values
        ]
        wanted = step["kind"] == "semi"
        rows = [row for row, hit in zip(rows, matched) if hit is wanted]
    return {
        name: Column(column.dtype, [column.values[row] for row in rows])
        for name, column in inputs.items()
    }
