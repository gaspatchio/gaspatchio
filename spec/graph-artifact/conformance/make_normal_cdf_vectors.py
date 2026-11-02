# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for the standard normal distribution function, ``norm_cdf``.

Section 11.1.12 states ``norm_cdf`` with the transcendental family: Φ(x), the
probability that a standard normal variable is at most ``x``, held to **1e-12
relative** to the mathematical Φ wherever Φ is a normal double (``x >= -37.5``),
exact at the special values -- a null stays null, a NaN stays NaN, ``+inf``
answers 1.0 and ``-inf`` answers 0.0 -- and, below the normal range, held by
the line rule of the same section rather than by a relative tolerance.

Every expected answer is the double nearest Φ at the exact input double,
evaluated here to 60 significant digits in ``decimal``, and **none was read
off the producer or any floating-point library**: those are what these cases
test. Φ is taken from its Maclaurin series, ``1/2 + φ(x) Σ x^(2n+1) /
(2n+1)!!``, for ``|x| <= 4``, and from Laplace's continued fraction for the
upper tail, ``φ(t) / (t + 1/(t + 2/(t + 3/(t + …))))``, beyond; the two agree
to better than 1e-96 where both converge, and ``main`` checks that before it
writes anything. Stdlib only, for the same reason. Run from
``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_normal_cdf_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**Not here.** Excel's own bits: its algorithm is unpublished, so no case
claims them. The density and the inverse are not operations of this
vocabulary, so neither has an answer to publish.
"""

from __future__ import annotations

import json
from decimal import Decimal, getcontext
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)

getcontext().prec = 110
_PI = Decimal(
    "3.14159265358979323846264338327950288419716939937510582097494459230781640628620899862803482534211706798"
)
_TINY = Decimal(10) ** -105
# Where the series hands over to the continued fraction, in |x|.
_SERIES_REACH = 4


def _density(x: Decimal) -> Decimal:
    return (-(x * x) / 2).exp() / (2 * _PI).sqrt()


def _series(x: Decimal) -> Decimal:
    """Φ(x) by its Maclaurin series: converges everywhere, used for |x| <= 4."""
    term = total = x
    n = 0
    while True:
        n += 1
        term = term * x * x / (2 * n + 1)
        total += term
        if abs(term) < _TINY * max(abs(total), Decimal(1)):
            return Decimal("0.5") + _density(x) * total


def _upper_tail(t: Decimal, terms: int = 4000) -> Decimal:
    """1 - Φ(t) by Laplace's continued fraction, for t > 0, evaluated bottom up."""
    fraction = t
    for k in range(terms, 0, -1):
        fraction = t + k / fraction
    return _density(t) / fraction


def phi(value: float) -> Decimal:
    """Φ at the exact double ``value``, to well past 60 significant digits."""
    x = Decimal(value)
    if x == 0:
        return Decimal("0.5")
    if abs(x) <= _SERIES_REACH:
        return _series(x)
    if x < 0:
        return _upper_tail(-x)
    return 1 - _upper_tail(x)


def nearest(value: float) -> float:
    """Return the double nearest Φ(value): ``float`` of a Decimal rounds correctly."""
    return float(phi(value))


CASES: list[dict] = []
NORM_CDF = ("norm_cdf",)
CONTRACT = {"atol": 0.0, "rtol": 1e-12}
EXACT = {"atol": 0.0, "rtol": 0.0}


def norm_cdf(operand: dict) -> dict:
    """Return the call tree of ``norm_cdf`` over one operand."""
    return {"op": "call", "name": "norm_cdf", "args": [operand], "attrs": {}}


X = norm_cdf({"op": "col", "name": "x"})


def add(
    identifier: str,
    inputs: tuple[str, list],
    expected: tuple[str, list],
    comparison: dict,
) -> None:
    """Add one value case over the column ``x``."""
    kind, column = inputs
    dtype, values = expected
    CASES.append(
        {
            "id": identifier,
            "covers": list(NORM_CDF),
            "inputs": {"x": {"dtype": kind, "values": column}},
            "expr": X,
            "producer_check": True,
            "expected": {"dtype": dtype, "values": values},
            "comparison": comparison,
            "case_kind": "value",
        }
    )


def answered(values: list) -> list:
    """Φ of each value, a null staying null."""
    return [None if value is None else nearest(value) for value in values]


# --- the body, where a workbook evaluates Φ ---------------------------------

# Zero answers exactly one half, and so does a value too small to move it.
# ±1.96 is the two-sided 95% point; -2.96 the split point a hand-built series
# and continued fraction met at in the converted GMDB workbook.
BODY = [
    -6.0,
    -3.0,
    -2.96,
    -1.96,
    -1.0,
    -0.5,
    -1e-300,
    0.0,
    1e-300,
    0.5,
    1.0,
    1.96,
    3.0,
    6.0,
]
add("norm-cdf-body", ("f64", BODY), ("f64", answered(BODY)), CONTRACT)
# Each policy's own periods, one value at a time; an empty policy stays empty.
JAGGED = [[-1.96, 0.0, 1.96], [], [3.0]]
add(
    "norm-cdf-per-period",
    ("list[f64]", JAGGED),
    ("list[f64]", [answered(row) for row in JAGGED]),
    CONTRACT,
)
# A whole number is evaluated as the double it is and answers a double.
add(
    "norm-cdf-whole-numbers",
    ("i64", [0, 1, -2]),
    ("f64", answered([0.0, 1.0, -2.0])),
    CONTRACT,
)

# --- the lower tail, to the end of the normal range -------------------------

# -8.36 is where the textbook 0.5 * (1 + erf(x / sqrt 2)) answers 0.0 for a Φ
# of 3.1e-17: the subtraction it makes loses every digit. -37.5 is the last
# half-step at which Φ (4.6e-308) is a normal double, and the relative
# contract still binds there.
TAIL = [-8.36, -10.0, -20.0, -30.0, -37.0, -37.5]
add("norm-cdf-lower-tail", ("f64", TAIL), ("f64", answered(TAIL)), CONTRACT)
# The upper tail saturates: Φ(8.3) is 1 - 5.2e-17, nearer 1.0 than the double
# below it, and so is everything past it.
UPPER = [8.3, 9.0, 40.0]
if answered(UPPER) != [1.0, 1.0, 1.0]:
    _MESSAGE = "the upper tail must saturate at 1.0 from 8.3"
    raise ValueError(_MESSAGE)
add("norm-cdf-upper-saturation", ("f64", UPPER), ("f64", answered(UPPER)), CONTRACT)

# --- below the normal range: the line rule, not a relative tolerance --------

# Φ(-38) is 2.9e-316, a subnormal, and Φ(-40) is 3.7e-350, below the smallest
# one: its double is 0.0. A relative tolerance means nothing where a double
# holds a few significant bits, so 11.1.12's line rule decides: agreement to
# 1e-12 of the line's scale, here the operand's own magnitude, 40.
DEEP = [-38.0, -40.0]
if answered(DEEP)[1] != 0.0:
    _MESSAGE = "Phi(-40) must be below the smallest subnormal"
    raise ValueError(_MESSAGE)
add(
    "norm-cdf-below-the-normal-range",
    ("f64", DEEP),
    ("f64", answered(DEEP)),
    {"atol": 1e-12 * 40.0, "rtol": 0.0},
)

# --- the exact values ---------------------------------------------------------

# A NaN stays a NaN, and the infinities answer the limits, exactly.
add(
    "norm-cdf-special-values",
    ("f64", [{"nonfinite": "nan"}, {"nonfinite": "+inf"}, {"nonfinite": "-inf"}]),
    ("f64", [{"nonfinite": "nan"}, 1.0, 0.0]),
    EXACT,
)
# 11.1.12: "A null value stays null under all" of the family, on both shapes;
# a null outer list is a policy with no column and answers null.
add(
    "null-norm_cdf-scalar",
    ("f64", [0.0, None, -1.0]),
    ("f64", answered([0.0, None, -1.0])),
    CONTRACT,
)
add(
    "null-norm_cdf-per-period",
    ("list[f64]", [[0.0, None], None, []]),
    ("list[f64]", [[0.5, None], None, []]),
    CONTRACT,
)
add("empty-portfolio-norm_cdf", ("f64", []), ("f64", []), CONTRACT)


def _check_the_reference() -> None:
    """Refuse to write if the two expansions part company where both converge."""
    for value in (-4.0, -3.5, 3.9):
        x = Decimal(value)
        tail = _upper_tail(-x) if value < 0 else 1 - _upper_tail(x)
        if abs(_series(x) - tail) > Decimal(10) ** -90 * tail:
            msg = f"the series and the continued fraction disagree at {value}"
            raise ValueError(msg)


def main() -> None:
    """Write the bundle, refusing a duplicate identifier before it ships."""
    _check_the_reference()
    ids = [entry["id"] for entry in CASES]
    if len(ids) != len(set(ids)):
        msg = "case identifiers must be unique within the bundle"
        raise ValueError(msg)
    bundle = {
        "schema": "gaspatchio-operation-vectors/v0-preview.1",
        "artifact_schema": "gaspatchio-graph/v0-preview.2",
        "fingerprint_algorithm": "gspv0-preview-3",
        "family": "The standard normal distribution function",
        "cases": CASES,
    }
    (VECTORS / "normal-cdf.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("normal distribution cases", len(CASES))


if __name__ == "__main__":
    main()
