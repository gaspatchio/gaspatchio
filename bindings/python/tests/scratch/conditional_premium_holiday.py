# ABOUTME: Scratch test showing premium holiday calculation with conditionals.
# ABOUTME: Demonstrates zeroing premiums at specific months using when/then/otherwise.
# ruff: noqa: T201, INP001, ANN201, PLR2004
"""Premium Holiday Example.

Shows how to implement premium holidays (e.g., no premium in month 5).
This replaces complex map_elements logic with clean when/then/otherwise.
Run with: uv run python tests/scratch/conditional_premium_holiday.py
"""

import polars as pl

from gaspatchio_core import ActuarialFrame, when

# Sample data: Three policies with monthly premiums
data = {
    "policy_id": [1, 2, 3],
    "base_premium": [100.0, 250.0, 500.0],
    "month": [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    ],
}

af = ActuarialFrame(data)

print("=" * 80)
print("PREMIUM HOLIDAY EXAMPLE")
print("=" * 80)
print("\nOriginal data:")
print(af.collect())

# ============================================================================
# OLD APPROACH: Using map_elements
# ============================================================================
print("\n" + "=" * 80)
print("OLD APPROACH: map_elements")
print("=" * 80)


def premium_with_holiday_old(row):
    """Old approach: Python function to zero out month 5."""
    months = row["month"]
    base = row["base_premium"]
    return [0.0 if m == 5 else base for m in months]


af.premium_old = pl.struct([pl.col("month"), pl.col("base_premium")]).map_elements(
    premium_with_holiday_old, return_dtype=pl.List(pl.Float64)
)

result_old = af.collect()
print("\nResult with map_elements:")
print(result_old.select(["policy_id", "base_premium", "premium_old"]))

print("\nPolicy 1 premium schedule (should be 0.0 at month 5):")
print(result_old["premium_old"][0])

# ============================================================================
# NEW APPROACH: Using when/then/otherwise (WIP)
# ============================================================================
print("\n" + "=" * 80)
print("NEW APPROACH: when/then/otherwise (WIP)")
print("=" * 80)

print("\nWhat we WANT to write:")
print("""
af.premium = (
    when(af.month == 5)
    .then(0.0)
    .otherwise(af.base_premium)
)
""")

print("\nCurrently raises NotImplementedError (list broadcasting not yet implemented):")

try:
    af.premium = when(af.month == 5).then(0.0).otherwise(af.base_premium)
    result_new = af.collect()
    print("\n✅ SUCCESS! List broadcasting is now implemented!")
    print(result_new.select(["policy_id", "base_premium", "premium"]))
except NotImplementedError as e:
    print(f"\n❌ {e}")

# ============================================================================
# MULTIPLE CONDITIONS: Holidays at months 5 and 11
# ============================================================================
print("\n" + "=" * 80)
print("MULTIPLE PREMIUM HOLIDAYS (months 5 and 11)")
print("=" * 80)

print("\nWhat we WANT to write for multiple holidays:")
print("""
af.premium_multi = (
    when(af.month == 5).then(0.0)
    .when(af.month == 11).then(0.0)
    .otherwise(af.base_premium)
)
""")

print("\nOr even cleaner with .is_in():")
print("""
af.premium_multi = (
    when(af.month.is_in([5, 11]))
    .then(0.0)
    .otherwise(af.base_premium)
)
""")

# ============================================================================
# WHAT WORKS NOW: Scalar example
# ============================================================================
print("\n" + "=" * 80)
print("WHAT WORKS NOW: Scalar conditionals")
print("=" * 80)

# Scalar example: Apply loading based on policy size
af3 = ActuarialFrame({"policy_id": [1, 2, 3], "base_premium": [100.0, 250.0, 500.0]})

# Add loading for large policies
af3.premium_with_loading = (
    when(af3.base_premium > 300)
    .then(af3.base_premium * 1.1)
    .otherwise(af3.base_premium)
)

result_scalar = af3.collect()
print("\nScalar conditional example (10% loading for premium > 300):")
print(result_scalar)

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("""
✅ Scalar conditionals work NOW
❌ List broadcasting coming in Task 4+
🎯 This pattern will replace ALL map_elements conditionals once implemented!
""")
