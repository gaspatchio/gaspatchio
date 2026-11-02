# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The five payloads the storage decision is measured on.

One per answer the decision can give: a dense grid, and the four ways a key
space earns the exact sorted-rows path instead. Each is built here rather
than stored, because one of them is a key space of eighteen quintillion cells
and another is a hundred and twelve megabytes of grid -- neither is a file,
and both are four numbers.

Run this module to write all five as JSON into a directory:

```
.venv/bin/python -m tests.fixtures.make_tables /tmp/payloads
```

The payloads are section 15's inline table form -- ``dimensions``, ``value``,
``columns``, ``rows`` -- and nothing about them is synthetic except their
size: the shapes are a select basis (two numeric keys and a rate), which is
what every table in the converted models this decision was measured on turns
out to be.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Final

__all__ = ["PAYLOADS", "write"]

# The answer column every fixture carries, and the rate it is filled with.
_VALUE: Final = "rate"
_RATE: Final = 0.01


def _payload(
    keys: list[tuple[str, str]], rows: list[list[Any]], value: str = _VALUE
) -> dict[str, Any]:
    """Return one section 15 table payload over these key columns and rows."""
    columns = [{"name": name, "dtype": dtype} for name, dtype in keys]
    columns.append({"name": value, "dtype": "f64"})
    return {
        # A set of names, as section 15 says, and deliberately in another
        # order than ``columns``: a reader binding operands to this rather
        # than to the column order mis-keys the table silently (11.1.24).
        "dimensions": sorted(name for name, _ in keys),
        "value": value,
        "columns": columns,
        "rows": rows,
    }


def dense() -> dict[str, Any]:
    """Return a fully crossed basis: three ages by two durations, six rows."""
    return _payload(
        [("age", "f64"), ("duration", "f64")],
        [
            [float(age), float(duration), _RATE * (1 + age - 45) * duration]
            for age in (45, 46, 47)
            for duration in (1, 2)
        ],
    )


def one_key(keys: list[float]) -> dict[str, Any]:
    """Return a basis on one numeric key, one rate a key."""
    return _payload([("key", "f64")], [[key, _RATE * (key + 1)] for key in keys])


def sparse_1pct() -> dict[str, Any]:
    """Return a hundred rows over ten thousand cells: one per cent dense."""
    return _payload(
        [("age", "f64"), ("duration", "f64")],
        [[float(age * 10), float(age % 10), _RATE * age] for age in range(100)],
    )


def sparse_002pct() -> dict[str, Any]:
    """Return ten rows over fifty thousand cells: two hundredths of a per cent."""
    return _payload(
        [("age", "f64"), ("duration", "f64")],
        [[float(age * 500), float(age), _RATE * age] for age in range(10)],
    )


def overflow() -> dict[str, Any]:
    """Return the two keys whose key space is wider than a flat index.

    Each axis spans ``2**32 + 1`` keys, so the flat grid would be
    ``(2**32 + 1)**2`` cells -- eighteen quintillion, past the top of the
    signed integer a flat index is held in. The two tuples are the pair a
    mixed-radix packing of the rank tuple collides on where the radix is
    taken as the span rather than the span plus one: ``(0, 2**32)`` packs
    onto the same integer as ``(1, 0)``, and ``(2**32, 0)`` packs to
    ``2**64``, which wraps onto ``(0, 0)``. A basis carrying the first of
    each pair would answer it for the second.
    """
    return _payload(
        [("age", "i64"), ("duration", "i64")],
        [[0, 2**32, 0.01], [2**32, 0, 0.02]],
    )


def oversize() -> dict[str, Any]:
    """Return a key space whose dense grid would be over a hundred mebibytes.

    An age span of 19,001 by a duration span of 761 is 14,459,761 cells, and
    a cell is eight bytes: 115,678,088 of them, above the 104,857,600 this
    engine builds a grid up to.
    """
    return _payload(
        [("age", "i64"), ("duration", "i64")],
        [[age * 1000, age * 40, _RATE * age] for age in range(20)],
    )


def fractional_key() -> dict[str, Any]:
    """Return a basis whose key column carries a cell that is not whole."""
    return _payload(
        [("age", "f64")],
        [[0.5, 0.01], [1.5, 0.02]],
    )


def duplicate_tuple() -> dict[str, Any]:
    """Return a basis carrying one key tuple twice, with answers that agree."""
    return _payload(
        [("age", "f64"), ("duration", "f64")],
        [[45.0, 1.0, 0.01], [45.0, 1.0, 0.01], [45.0, 2.0, 0.02]],
    )


def text_keyed() -> dict[str, Any]:
    """Return a basis keyed by a plan identifier and a whole-number duration."""
    return _payload(
        [("plan", "str"), ("duration", "i64")],
        [
            ["A", 1, 0.01],
            ["A", 2, 0.02],
            ["B", 1, 0.03],
            ["B", 2, 0.04],
        ],
    )


def blank_answer() -> dict[str, Any]:
    """Return a dense basis one of whose answer cells is not there."""
    return _payload(
        [("age", "f64"), ("duration", "f64")],
        [
            [45.0, 1.0, 0.01],
            [45.0, 2.0, None],
            [55.0, 1.0, 0.03],
            [55.0, 2.0, 0.04],
        ],
    )


# What each name builds. The five the plan names first, then the four the
# refusals and the reaches are measured on.
PAYLOADS: Final[dict[str, Any]] = {
    "dense": dense,
    "sparse_1pct": sparse_1pct,
    "sparse_002pct": sparse_002pct,
    "overflow": overflow,
    "oversize": oversize,
    "fractional_key": fractional_key,
    "duplicate_tuple": duplicate_tuple,
    "text_keyed": text_keyed,
    "blank_answer": blank_answer,
}


def write(destination: Path) -> list[Path]:
    """Write every payload into ``destination`` as JSON, and return the files."""
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, build in PAYLOADS.items():
        path = destination / f"{name}.json"
        path.write_text(json.dumps(build(), indent=1) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for path in write(Path(sys.argv[1] if len(sys.argv) > 1 else "payloads")):
        print(path)  # noqa: T201 -- this module is run as a script to write them
