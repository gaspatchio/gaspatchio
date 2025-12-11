# RFC 29 Learnings: Lookup Performance Optimization

This document captures experiments tried, what worked, and what didn't.

---

## What Worked: Array Storage (Implemented)

**Problem:** Hash table lookups are slow due to hashing overhead and cache misses.

**Solution:** For dense tables with contiguous integer keys (age 18-100, duration 0-30), store values in a flat n-dimensional array. Convert keys to array indices via simple arithmetic.

**Result:** 8x lookup speedup, 2.7x overall model speedup (100k × 3 scenarios).

**Key insight:** Most actuarial tables ARE dense. Age ranges, durations, policy years - these are naturally contiguous integers. String keys (gender, smoker status) can be dictionary-encoded to small integers.

**Status:** ✅ Committed and in use.

---

## What Didn't Work: CompiledLookup (Abandoned)

**Problem:** In a projection loop, the same model points are looked up repeatedly (e.g., 720 times for 60-year monthly projection). Key encoding is redundant.

**Proposed Solution:** Pre-compile key encodings once, cache the linear array indices, reuse on subsequent lookups.

**Implementation:** Built `CompiledLookup` struct that:
1. Encodes all key columns to integers (once)
2. Computes linear indices using dimensional strides (once)
3. Stores indices for fast repeated lookups

**Benchmark Results:** 26-135x speedup for loop-based patterns.

### Why We Abandoned It

The actual model uses **vectorized Polars projections**, not Python loops:

```python
# What we assumed:
for t in range(720):
    rates = table.lookup(age=df.age, gender=df.gender)  # Same keys each time

# What actually happens:
af = ActuarialFrame(model_points).expand(projection_months=720)
af.rate = table.lookup(age=af.age, gender=af.gender)  # ONE call, all months
```

In the vectorized pattern:
- Lookup is called **once** (not 720 times)
- Each row has **different keys** (because month varies per row)
- CompiledLookup provides **zero benefit**

The array storage optimization already helps the vectorized pattern because it makes the single large lookup faster.

### Lesson Learned

**Understand the actual usage pattern before optimizing.** We built a sophisticated caching system for a problem that doesn't exist in the primary use case.

The vectorized Polars approach is actually *better* than loop-based projections because:
- Single lookup amortizes Python/Rust boundary overhead
- Polars can parallelize internally
- No Python loop overhead

If we ever have a loop-based model pattern, CompiledLookup could be revisited. The implementation was:
- ~300 lines Rust (`compiled.rs`)
- ~50 lines Python bindings
- 7 passing tests
- Full documentation

---

## Performance Summary

| Optimization | Speedup | Status | Notes |
|-------------|---------|--------|-------|
| Array storage | 8x lookups, 2.7x overall | ✅ Shipped | Works with vectorized pattern |
| CompiledLookup | 26-135x (loop pattern only) | ❌ Abandoned | Doesn't help vectorized pattern |

---

## Future Optimization Ideas (Not Yet Explored)

1. **SIMD value gathering** - Use AVX2/NEON to parallelize array indexing
2. **Pre-allocated output buffers** - Reuse Series allocation across lookups
3. **Batch table registration** - Register multiple tables in single Rust call
4. **Column-major storage** - May improve cache locality for certain access patterns

These would be incremental improvements on the array storage foundation.
