# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for the named conversions of 11.1.23 and 11.1.38-11.1.40.

Every expected answer below is derived by hand from the clause quoted beside
it and from nothing else. **No expected value here was read off the
producer**: the producer is the thing these cases test, and a vector taken
from it would only say that it agrees with itself. Stdlib only, for the same
reason -- nothing here imports gaspatchio, polars or numpy.

Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_conversion_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**The doors from outside.** Three of these clauses exist because a column
arrives in a storage type section 10 has no name for: an unsigned or 128-bit
integer whose value runs past an ``i64``, a dictionary-encoded string, a
fixed-width array. Those are the inputs the refusals at the export boundary
send an author here to convert, so the envelope names them on inputs -- and
only on inputs. A result is still named from section 10's closed vocabulary.

**The float text trap, and how it is avoided.** 11.1.39 states the shortest
decimal that reads back to the same double. Two conforming shortest-decimal
printers can still disagree about how they *spell* an exponent -- ``1e-7``
against ``1e-07`` -- which is a fact about the printer rather than about the
number. Every float in these cases is therefore one whose shortest form
carries no exponent or carries a positive one (``0.1``, ``2.5``, ``1e+21``),
where the spelling is not in dispute. A case turning on a small negative
exponent would be publishing a printer's habit as a contract, so there is
none, and the reader normalises nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)

CASES: list[dict] = []


# The empty-portfolio case of every bounded-value identifier is named
# ``empty-portfolio-<identifier>``, because that is the name the packaged
# checklist's guard looks for: a clause claiming a reviewed boundary with no
# case exhibiting it is a claim with nothing behind it, and a model with no
# policies in it is the boundary every identifier is asked about.


def column(dtype: str, values: list) -> dict:
    return {"dtype": dtype, "values": values}


def _call(name: str) -> dict:
    return {
        "op": "call",
        "name": name,
        "args": [{"op": "col", "name": "x"}],
        "attrs": {},
    }


def value(
    identifier: str, name: str, inputs: dict, expected: dict, *, atol: float = 0.0
) -> None:
    """Add one value case invoking ``name`` on a single column ``x``."""
    CASES.append(
        {
            "id": identifier,
            "covers": [name],
            "inputs": {"x": inputs},
            "expr": _call(name),
            "producer_check": True,
            "expected": expected,
            "comparison": {"atol": atol, "rtol": 0.0},
            "case_kind": "value",
        }
    )


def refuses(
    identifier: str, name: str, inputs: dict, refusal: str, producer_message: str
) -> None:
    """Add one refusal case invoking ``name`` on a single column ``x``."""
    CASES.append(
        {
            "id": identifier,
            "covers": [name],
            "inputs": {"x": inputs},
            "expr": _call(name),
            "producer_check": True,
            "case_kind": "portable-domain-refusal",
            "refusal": refusal,
            "producer_message": producer_message,
        }
    )


# --- 11.1.38 to_float -------------------------------------------------------
#
# "An integer value x is converted where -2^53 <= x <= 2^53." Every whole
# number in that interval has a double of its own, so the double is the same
# number and the answer is the value with a decimal point on it.
value(
    "conversion-to_float-scalar",
    "to_float",
    column("i64", [12, -30, 0]),
    column("f64", [12.0, -30.0, 0.0]),
)
value(
    "conversion-to_float-list",
    "to_float",
    column("list[i64]", [[1, 2], [3]]),
    column("list[f64]", [[1.0, 2.0], [3.0]]),
)
# 2^53 = 9007199254740992. It is one times two to the fifty-third, so a
# double holds it with a mantissa of one: exact, and the last whole number
# before the doubles are more than one apart.
value(
    "conversion-to_float-at-the-boundary",
    "to_float",
    column("i64", [9007199254740992, -9007199254740992]),
    column("f64", [9007199254740992.0, -9007199254740992.0]),
)
# 2^53 + 1 = 9007199254740993. The doubles either side of it are 2^53 and
# 2^53 + 2, so no double is this number and the invocation refuses.
refuses(
    "conversion-to_float-past-the-boundary",
    "to_float",
    column("i64", [9007199254740993]),
    "checked-float-conversion",
    "no double names",
)
refuses(
    "conversion-to_float-below-the-boundary",
    "to_float",
    column("i64", [-9007199254740993]),
    "checked-float-conversion",
    "no double names",
)
# "A null is carried rather than refused ... nothing about an absent value is
# too large for a double."
value(
    "conversion-to_float-null-carried",
    "to_float",
    column("i64", [7, None]),
    column("f64", [7.0, None]),
)
value(
    "conversion-to_float-null-period",
    "to_float",
    column("list[i64]", [[1, None], None]),
    column("list[f64]", [[1.0, None], None]),
)
# "An empty list returns an empty list[f64]."
value(
    "conversion-to_float-empty-list",
    "to_float",
    column("list[i64]", [[], [2]]),
    column("list[f64]", [[], [2.0]]),
)
value(
    "empty-portfolio-to_float",
    "to_float",
    column("i64", []),
    column("f64", []),
)
# "A floating-point value is returned unchanged."
value(
    "conversion-to_float-double-unchanged",
    "to_float",
    column("f64", [0.1, 2.5]),
    column("f64", [0.1, 2.5]),
)
# The door from outside: an unsigned width is an integer for this call and is
# judged on its value like any other.
value(
    "conversion-to_float-unsigned-within-the-boundary",
    "to_float",
    column("u64", [9007199254740992]),
    column("f64", [9007199254740992.0]),
)
refuses(
    "conversion-to_float-unsigned-past-the-boundary",
    "to_float",
    column("u64", [9223372036854775808]),
    "checked-float-conversion",
    "no double names",
)
# "Every other input type is refused, including Boolean, text and date."
for suffix, arriving in (
    ("bool", column("bool", [True])),
    ("text", column("str", ["1"])),
    ("date", column("date", ["2026-01-01"])),
):
    refuses(
        f"conversion-to_float-refuses-{suffix}",
        "to_float",
        arriving,
        "float-conversion-type",
        "only integer or floating-point",
    )

# --- 11.1.39 to_text --------------------------------------------------------
#
# "An integer is written by its digits."
value(
    "conversion-to_text-integer",
    "to_text",
    column("i64", [10123, -7, 0]),
    column("str", ["10123", "-7", "0"]),
)
# "the shortest decimal that reads back to the same number at the width it is
# stored in". The double nearest 0.1 is 0.1000000000000000055511151231257827,
# and 0.1 is the shortest decimal that reads back to it; 2.5 is a sum of two
# powers of two and is its own shortest form; 1e21 is exactly representable
# and its shortest form carries the exponent, positive and so unambiguously
# spelled.
value(
    "conversion-to_text-float-shortest-form",
    "to_text",
    column("f64", [0.1, 2.5, 1e21]),
    column("str", ["0.1", "2.5", "1e+21"]),
)
# "A Boolean is true or false." The words, not the spellings a host language
# happens to print.
value(
    "conversion-to_text-bool",
    "to_text",
    column("bool", [True, False]),
    column("str", ["true", "false"]),
)
# "A date is its ISO calendar day, YYYY-MM-DD."
value(
    "conversion-to_text-date",
    "to_text",
    column("date", ["2025-01-31", "2025-02-28"]),
    column("str", ["2025-01-31", "2025-02-28"]),
)
# "Text and categories are carried through unchanged."
value(
    "conversion-to_text-text-unchanged",
    "to_text",
    column("str", ["term", ""]),
    column("str", ["term", ""]),
)
value(
    "conversion-to_text-list",
    "to_text",
    column("list[i64]", [[1, 2], [3]]),
    column("list[str]", [["1", "2"], ["3"]]),
)
# "A null is carried as null, on a scalar, on a list item and on a whole list."
value(
    "conversion-to_text-null-carried",
    "to_text",
    column("i64", [7, None]),
    column("str", ["7", None]),
)
value(
    "conversion-to_text-null-period",
    "to_text",
    column("list[i64]", [[1, None], None]),
    column("list[str]", [["1", None], None]),
)
# "An empty list returns an empty list[str]."
value(
    "conversion-to_text-empty-list",
    "to_text",
    column("list[f64]", [[], [2.5]]),
    column("list[str]", [[], ["2.5"]]),
)
value(
    "empty-portfolio-to_text",
    "to_text",
    column("i64", []),
    column("str", []),
)
# The door from outside, and the reason this clause exists: 18446744073709551557
# is 2^64 - 59, a prime past 2^63 that no i64 carries and no double names.
# Section 10 has no exact numeric name for it and text has one, digit for
# digit.
value(
    "conversion-to_text-unsigned-past-i64",
    "to_text",
    column("u64", [18446744073709551557]),
    column("str", ["18446744073709551557"]),
)
# -170141183460469231731687303715884105728 is -2^127, the smallest signed
# 128-bit value, written out the same way.
value(
    "conversion-to_text-signed-128",
    "to_text",
    column("i128", [-170141183460469231731687303715884105728]),
    column("str", ["-170141183460469231731687303715884105728"]),
)
# A category is a string with a dictionary in front of it, and the dictionary
# was never content, so the repeated category answers the same text twice.
value(
    "conversion-to_text-categorical",
    "to_text",
    column("categorical", ["term", "term", "whole life"]),
    column("str", ["term", "term", "whole life"]),
)
# "Every other input type is refused by name, including ... a fixed-width
# array", which goes through to_list first.
refuses(
    "conversion-to_text-refuses-an-array",
    "to_text",
    column("array[f64,2]", [[1.5, 2.5]]),
    "text-conversion-type",
    "to_text has no text form for",
)

# --- 11.1.40 to_list --------------------------------------------------------
#
# "the same elements, in the same order, with the element type unchanged".
value(
    "conversion-to_list-two-element-array",
    "to_list",
    column("array[f64,2]", [[1.5, 2.5], [3.5, 4.5]]),
    column("list[f64]", [[1.5, 2.5], [3.5, 4.5]]),
)
value(
    "conversion-to_list-integer-array",
    "to_list",
    column("array[i64,3]", [[7, 8, 9]]),
    column("list[i64]", [[7, 8, 9]]),
)
# "A null element stays null and a null array answers null."
value(
    "conversion-to_list-null-element-and-null-array",
    "to_list",
    column("array[i64,2]", [[None, 5], None]),
    column("list[i64]", [[None, 5], None]),
)
# "An array of width zero answers an empty list."
value(
    "conversion-to_list-zero-width-array",
    "to_list",
    column("array[f64,0]", [[]]),
    column("list[f64]", [[]]),
)
value(
    "empty-portfolio-to_list",
    "to_list",
    column("array[f64,2]", []),
    column("list[f64]", []),
)
# "A column that is already a list refuses rather than passing through", and a
# scalar refuses for the same reason in the other direction.
refuses(
    "conversion-to_list-refuses-a-list",
    "to_list",
    column("list[f64]", [[1.5, 2.5]]),
    "list-conversion-shape",
    "to_list converts a fixed-width array",
)
refuses(
    "conversion-to_list-refuses-a-scalar",
    "to_list",
    column("f64", [1.5]),
    "list-conversion-shape",
    "to_list converts a fixed-width array",
)

# --- 11.1.23 to_integer, at the width boundary it now reads ------------------
#
# The nine cases already published for this clause live in boundaries.json and
# existing-contracts.json and are untouched. These are the two the widening
# adds: an unsigned width is an integer for this call, judged on its value.
# 9223372036854775807 is 2^63 - 1, the largest i64 there is.
value(
    "conversion-to_integer-unsigned-within-range",
    "to_integer",
    column("u64", [7, 9223372036854775807]),
    column("i64", [7, 9223372036854775807]),
)
# 9223372036854775808 is 2^63, one past it, so there is no i64 to convert to.
refuses(
    "conversion-to_integer-unsigned-past-i64",
    "to_integer",
    column("u64", [9223372036854775808]),
    "integer-range-conversion",
    "outside the signed 64-bit range",
)
# -9223372036854775809 is -2^63 - 1, one below the smallest i64.
refuses(
    "conversion-to_integer-signed-128-below-i64",
    "to_integer",
    column("i128", [-9223372036854775809]),
    "integer-range-conversion",
    "outside the signed 64-bit range",
)


def main() -> None:
    """Write the bundle, refusing a duplicate identifier before it ships."""
    ids = [entry["id"] for entry in CASES]
    if len(ids) != len(set(ids)):
        msg = "case identifiers must be unique within the bundle"
        raise ValueError(msg)
    bundle = {
        "schema": "gaspatchio-operation-vectors/v0-preview.1",
        "artifact_schema": "gaspatchio-graph/v0-preview.2",
        "fingerprint_algorithm": "gspv0-preview-3",
        "family": "Named conversions and the doors into them",
        "cases": CASES,
    }
    (VECTORS / "conversions.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("conversion cases", len(CASES))


if __name__ == "__main__":
    main()
