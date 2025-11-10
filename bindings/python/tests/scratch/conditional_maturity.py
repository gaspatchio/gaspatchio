# ABOUTME: Scratch test comparing old map_elements approach vs new when/then/otherwise.
# ABOUTME: Demonstrates maturity calculation pattern for actuarial projections.
# ruff: noqa: T201, INP001, ANN201, PLR2004
"""Maturity Calculation Example.

Shows the before/after of replacing map_elements with when/then/otherwise.
Run with: uv run python tests/scratch/conditional_maturity.py
"""

import polars as pl

from gaspatchio_core import ActuarialFrame, when

# Sample data: Two policies with different terms
data = {
    "policy_id": [1, 2],
    "policy_term": [1, 2],  # years
    "month": [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],  # 13 months
        [
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
        ],  # 25 months
    ],
    "surviving_at_t": [
        [100.0, 99.5, 99.0, 98.5, 98.0, 97.5, 97.0, 96.5, 96.0, 95.5, 95.0, 94.5, 94.0],
        [
            100.0,
            99.5,
            99.0,
            98.5,
            98.0,
            97.5,
            97.0,
            96.5,
            96.0,
            95.5,
            95.0,
            94.5,
            94.0,
            93.5,
            93.0,
            92.5,
            92.0,
            91.5,
            91.0,
            90.5,
            90.0,
            89.5,
            89.0,
            88.5,
            88.0,
        ],
    ],
}

af = ActuarialFrame(data)

print("=" * 80)
print("MATURITY CALCULATION EXAMPLE")
print("=" * 80)
print("\nOriginal data:")
print(af.collect())

# ============================================================================
# OLD APPROACH: Using map_elements (slow, Python overhead)
# ============================================================================
print("\n" + "=" * 80)
print("OLD APPROACH: map_elements (slow)")
print("=" * 80)


def maturity_logic_old(row):
    """Old approach: Python function with element-wise logic."""
    months = row["month"]
    maturity_month = row["policy_term"] * 12
    surviving = row["surviving_at_t"]
    return [
        surv if m == maturity_month else 0.0
        for m, surv in zip(months, surviving, strict=False)
    ]


# Note: This currently works but is 6-8x slower than native Polars
af.pols_maturity_old = pl.struct(
    [pl.col("month"), pl.col("policy_term"), pl.col("surviving_at_t")]
).map_elements(maturity_logic_old, return_dtype=pl.List(pl.Float64))

result_old = af.collect()
print("\nResult with map_elements:")
print(result_old.select(["policy_id", "policy_term", "pols_maturity_old"]))

print("\nPolicy 1 maturity (should be 94.0 at month 12):")
print(result_old["pols_maturity_old"][0])

print("\nPolicy 2 maturity (should be 88.0 at month 24):")
print(result_old["pols_maturity_old"][1])

# ============================================================================
# NEW APPROACH: Using when/then/otherwise (will be fast when implemented)
# ============================================================================
print("\n" + "=" * 80)
print("NEW APPROACH: when/then/otherwise (WIP - list broadcasting not implemented)")
print("=" * 80)

print("\nWhat we WANT to write (clean, readable, Excel-like):")
print("""
af.pols_maturity = (
    when(af.month == af.policy_term * 12)
    .then(af.surviving_at_t)
    .otherwise(0.0)
)
""")

print("\nThis would:")
print("  1. Read like an Excel IF() formula")
print("  2. Run 6-8x faster (native Polars, no Python overhead)")
print("  3. Be auditable and transparent")

print("\nCurrently raises NotImplementedError because list broadcasting")
print("requires the explode/re-aggregate pattern (Task 4+):")

try:
    af.pols_maturity = (
        when(af.month == af.policy_term * 12).then(af.surviving_at_t).otherwise(0.0)
    )
    result_new = af.collect()
    print("\n✅ SUCCESS! List broadcasting is now implemented!")
    print(result_new.select(["policy_id", "policy_term", "pols_maturity"]))
except NotImplementedError as e:
    print(f"\n❌ {e}")
    print("\n   This is expected - list broadcasting implementation is in progress.")

# ============================================================================
# WHAT WORKS NOW: Scalar conditionals
# ============================================================================
print("\n" + "=" * 80)
print("WHAT WORKS NOW: Scalar conditionals")
print("=" * 80)

# Simple scalar conditional
af2 = ActuarialFrame({"age": [25, 45, 70], "policy_id": [1, 2, 3]})

af2.rate = when(af2.age > 65).then(0.05).otherwise(0.02)

result_scalar = af2.collect()
print("\nScalar conditional example:")
print("af2.rate = when(af2.age > 65).then(0.05).otherwise(0.02)")
print(result_scalar)

# Multiple conditions (elif)
af2.category = (
    when(af2.age < 18)
    .then("child")
    .when(af2.age < 65)
    .then("adult")
    .otherwise("senior")
)

result_multi = af2.collect()
print("\nMultiple conditions (elif) example:")
print("""
af2.category = (
    when(af2.age < 18).then("child")
    .when(af2.age < 65).then("adult")
    .otherwise("senior")
)
""")
print(result_multi)

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("""
✅ Scalar conditionals work NOW and are production-ready
❌ List broadcasting detection works but raises NotImplementedError
🔧 List broadcasting implementation coming in Task 4+ (explode/re-aggregate)

Expected performance improvement: 6-8x faster than map_elements once implemented!
""")
