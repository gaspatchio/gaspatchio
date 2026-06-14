# RFC 29: Assumption Lookup Performance Optimization

**Status**: Draft
**Date**: 2025-12-09
**Authors:** Matt Wright, Claude

## Summary

Investigate and document strategies to improve assumption lookup performance in gaspatchio models. Profiling shows lookups consume ~63% of model execution time (~27 seconds in a 100k x 3 benchmark), presenting significant optimization opportunities.

**The core insight**: Hash table lookups are the bottleneck. By restructuring assumptions as **multi-dimensional arrays with dictionary-encoded keys**, we eliminate hash operations entirely:

| Path | Lookup Time | Speedup |
|------|-------------|---------|
| Current (hash tables) | ~27s | 1x |
| **Strategy 5: Arrays on CPU** | ~1s | **27x** |
| **Strategy 6a: Arrays on GPU** | ~0.6s | **45x** |

**The simplest path to GPU**: Implement array storage (Strategy 5), then switch backend to JAX/GPU (Strategy 6a). Two steps, ~45x speedup.

Pre-denormalization (Strategy 1) and other optimizations are **optional enhancements** for specific scenarios, not prerequisites.

## Motivation

### Current Performance Profile

Profiling a 100k model points x 3 scenarios benchmark revealed:

| Category | Time (s) | % of Total |
|----------|----------|------------|
| **LOOKUPS** | 27.65s | 63.3% |
| **CALCULATIONS** | 16.03s | 36.7% |
| OTHER | 0.01s | 0.0% |
| **TOTAL** | 43.69s | 100% |

Top lookup operations:

| Operation | Time | % Total |
|-----------|------|---------|
| `inv_return_mth` (fund returns) | 4.41s | 10.1% |
| `base_mort_rate` (mortality) | 4.16s | 9.5% |
| `surr_charge_rate` (surrender) | 4.07s | 9.3% |
| `disc_rate` (discount rates) | 3.97s | 9.1% |
| `mort_scalar, lapse_dur...` | 3.96s | 9.1% |
| `base_lapse_rate` (lapse) | 3.84s | 8.8% |

### Current Implementation

The existing Rust implementation is already well-optimized:

- **AHashMap** for O(1) hash table lookups
- **Parallel processing** via `par_chunks_mut`
- **Fast path** for 2-key lookups (avoids AHasher allocation)
- **Cache-friendly** 1024-element chunk batching
- **Polars plugin** integration for lazy evaluation

Current throughput: ~12M lookups/second

### The Opportunity

While individual lookups are fast, the sheer volume creates overhead:

```
300k rows x 180 timesteps = 54M row-timesteps
54M x 6 assumption tables = ~324M hash lookups
```

Reducing the NUMBER of lookups or changing the lookup ARCHITECTURE could yield significant gains.

---

## Proposed Optimization Strategies

### Strategy 1: Pre-Denormalization (Hoist Static Lookups)

**Status**: Researched - OPTIONAL (useful for CPU-only deployments)

**Idea**: Perform time-independent lookups ONCE per policy before time expansion, not per timestep.

> **Note**: This strategy is **not required** for the GPU path. If using Strategy 5 + 6a (arrays on GPU), the GPU handles 324M lookups trivially (~0.6s). Pre-denormalization is most valuable for CPU-only scenarios where you want to minimize total lookup count.

#### Analysis of Example Model Lookups

**TIME-INDEPENDENT (4 lookups - can pre-denormalize):**

| Lookup | Keys | Range | Current | Pre-Denorm |
|--------|------|-------|---------|------------|
| Mortality select | table_id, age, duration | 0-24 | 54M | 7.5M |
| Mortality scalar | scalar_id, duration | 0-14 | 54M | 4.5M |
| Base lapse rate | lapse_id, duration | 0-14 | 54M | 4.5M |
| Surrender charge | surr_charge_id, duration | 0-9 | 54M | 3M |

**TIME-DEPENDENT (2 lookups - cannot pre-denormalize directly):**

| Lookup | Keys | Optimization |
|--------|------|--------------|
| Investment returns | scenario_id, t, fund_index | Broadcast join (1080 rows) |
| Risk-free rates | scenario, currency, year | Broadcast join (7 rows) |

#### Potential Savings

**Current flow**:
```
model_points (100k rows)
    → expand with scenarios (300k rows)
    → expand with time (54M rows)
    → lookup mortality(age, duration) per row  ← 54M lookups!
```

**Proposed flow**:
```
model_points (100k rows)
    → lookup mortality[0:24], lapse[0:14], etc.  ← 19.5M lookups (pre-expansion)
    → store as list columns
    → expand with time (54M rows)
    → index into list by duration  ← 54M array indexing (fast)
```

**Lookup count reduction:**

| Approach | Hash Lookups | Array Indexing |
|----------|--------------|----------------|
| Current | 324M | 0 |
| Pre-denorm only | 127.5M | 216M |
| Pre-denorm + broadcast | **19.5M** | 216M |

**~94% reduction in hash table operations!**

#### Implementation Approach

**Phase 1**: Pre-denormalize duration-based lookups
```python
# Before time expansion, for each policy:
af.mort_rate_by_duration = mortality_table.lookup_vector(
    table_id=af.mort_table_id,
    age=af.age_at_entry,
    duration=pl.int_range(0, 25)  # All durations 0-24
)
# Returns: list[f64] of length 25 per policy

# After time expansion, index by duration:
af.base_mort_rate = af.mort_rate_by_duration.list.get(af.duration_capped)
```

**Phase 2**: Broadcast join for time-dependent lookups
```python
# Instead of per-row lookup:
af.disc_rate = risk_free_rates.lookup(scenario=..., year=af.year)

# Use broadcast join:
rate_table = risk_free_rates.to_df()  # Small: 7 rows per scenario
af = af.join(rate_table, on=["scenario", "year"])  # Broadcast join
```

#### Memory Trade-off

- **Current**: 300k policies x ~50 bytes = ~15MB
- **Pre-denorm**: 300k policies x (25+15+15+10) x 8 bytes = ~156MB
- **10x memory increase at start, but massive performance gain**

---

### Strategy 2: Array Indexing for Integer-Keyed Tables

**Status**: Researched - MEDIUM IMPACT

**Idea**: For assumptions keyed by a single integer (duration, t, age), use direct array indexing instead of hash table lookup.

#### Tables Suitable for Array Indexing

| Table | Key | Range | Use Case |
|-------|-----|-------|----------|
| scenario_returns | t | 0-179 | **PERFECT** - pure 1D |
| lapse.csv | duration | 1-100 | Classic use case |
| lapse_rates | duration | 0-14 | When filtered by lapse_id |
| inflation_rates | duration | 1-30 | When filtered by currency |
| risk_free_rates | year | 0-89 | When filtered by scenario |

#### Performance Comparison

**Hash Table Overhead:**
1. Codec encoding: `AnyValue::Int64(5) → u64 = 5`
2. Hash computation: `AHasher::write_u64(5)` + `finish()`
3. HashMap probe: Hash → bucket → linear probe
4. **Total: ~10-20ns per lookup**

**Array Indexing:**
1. Bounds check: `if idx < array.len()`
2. Direct access: `array[idx]`
3. **Total: ~2-3ns per lookup (L1 cache hit)**

**Expected speedup: 3-10x for single-integer-key tables**

#### Proposed Rust Implementation

```rust
pub enum TableStorage {
    HashMap(AHashMap<u64, f64>),  // Current general-purpose
    Array1D(ArrayTable1D),         // Single integer key
}

pub struct ArrayTable1D {
    offset: i64,      // Min key value (e.g., 0 or 1)
    data: Vec<f64>,   // Values indexed by (key - offset)
}

impl AssumptionTable {
    fn can_use_array_1d(df: &DataFrame, keys: &[String]) -> bool {
        keys.len() == 1
            && is_integer_type(df.column(&keys[0]))
            && density > 0.7  // >70% filled
            && range < 10_000  // Memory threshold
    }

    fn lookup_array_1d(&self, key_cols: &[&Series], arr: &ArrayTable1D)
        -> PolarsResult<Series> {
        let key_series = key_cols[0].i64()?;
        let mut out = vec![f64::NAN; key_series.len()];

        out.par_iter_mut().enumerate().for_each(|(idx, slot)| {
            if let Some(key) = key_series.get(idx) {
                let array_idx = (key - arr.offset) as usize;
                if array_idx < arr.data.len() {
                    *slot = arr.data[array_idx];
                }
            }
        });

        Ok(Series::from_vec("lookup".into(), out))
    }
}
```

#### Backward Compatibility

- Zero API changes - optimization is transparent
- Existing hash-based tables continue to work
- Auto-detection based on table characteristics

#### Limitation: Mixed String+Integer Keys

**Important**: Array indexing only applies to tables with a **single integer key**. Analysis of the `applied_life` model reveals that most real-world actuarial tables have mixed key types:

| Lookup | Keys | Array Indexing? |
|--------|------|-----------------|
| `mortality_select` | table_id (str), age (int), duration (int) | ❌ No - has string key |
| `mortality_scalars` | scalar_id (str), duration (int) | ❌ No - has string key |
| `lapse_rates` | lapse_id (str), duration (int) | ❌ No - has string key |
| `surrender_charges` | surr_charge_id (str), duration (int) | ❌ No - has string key |
| `inv_returns` | scenario_id (int), t (int), fund_index (str) | ❌ No - has string key |
| `risk_free_rates` | scenario (str), currency (str), year (int) | ❌ No - has string keys |

**For typical actuarial models with string+integer keys, array indexing alone provides ~0% improvement.**

Array indexing shines for:
- Simple benchmark tables with pure integer keys
- Synthetic test data
- Simplified models without dimension identifiers

**Conclusion**: Array indexing is a niche optimization. Pre-denormalization (Strategy 1) is the primary win for real-world models.

---

### Strategy 3: Lookup Result Caching

**Status**: Not yet researched

**Idea**: Cache lookup results for repeated key combinations within a model run.

**Observation**: Many policies share the same assumption lookup keys:
- All 30-year-olds with duration 5 get the same mortality rate
- All policies in scenario 1 at time t=10 get the same fund return

**Implementation options**:

**A. Query-level memoization**:
```rust
pub struct CachedLookupTable {
    base_table: AssumptionTable,
    cache: DashMap<u64, f64>,  // Thread-safe concurrent cache
}
```

**B. Batch deduplication**:
```python
# Before lookup, identify unique key combinations
unique_keys = df.select(key_cols).unique()
unique_values = table.lookup(unique_keys)
# Join back to full dataset
result = df.join(unique_values, on=key_cols)
```

**Challenges**:
- Cache invalidation complexity
- Memory overhead for cache storage
- Overhead of cache lookup vs direct lookup

---

### Strategy 4: Lookup Fusion (Batch Multiple Tables)

**Status**: Researched - MEDIUM IMPACT

**Idea**: When multiple lookups share the same keys, fuse them into a single operation.

#### Groups of Lookups with Shared Keys

**Group 1: Duration-Based (3 lookups)**
- `mort_scalar`: duration (clipped to 14), scalar_id
- `base_lapse_rate`: duration (clipped to 14), lapse_id
- `surr_charge_rate`: duration_year (clipped to 9), surr_charge_id

**Group 2: Scenario-Based (2 lookups)**
- `inv_return_mth`: scenario_id, t, fund_index
- `disc_rate`: scenario, currency, year

#### Current Overhead Per Lookup

| Layer | Overhead |
|-------|----------|
| Python (expression building) | ~10-20µs |
| Rust (registry access, setup) | ~5-10µs |
| Per-row (encoding + hash) | ~20-50ns |
| **Total per lookup** | **~30µs + (50ns x rows)** |

#### Proposed API (Option A - Explicit Batch)

```python
# Current: 3 separate lookups
af.mort_scalar = mortality_scalars.lookup(
    scalar_id=af.mort_scalar_id,
    duration=af.duration.clip(upper_bound=14)
)
af.base_lapse_rate = lapse_rates.lookup(
    lapse_id=af.lapse_id,
    duration=af.duration.clip(upper_bound=14)
)

# Proposed: Fused lookup
results = Table.lookup_batch([
    ("mort_scalar", mortality_scalars, {
        "scalar_id": af.mort_scalar_id,
        "duration": af.duration.clip(upper_bound=14)
    }),
    ("base_lapse_rate", lapse_rates, {
        "lapse_id": af.lapse_id,
        "duration": af.duration.clip(upper_bound=14)
    })
])
```

#### Estimated Benefit

For large-scale model (10k policies x 360 months):
- **Current**: 21.6M lookup operations
- **Fused (3 duration lookups)**: 14.4M hash operations
- **Reduction**: 33% fewer hash computations
- **Time saved**: ~360ms per model run at 50ns/hash

---

### Strategy 5: Multi-Dimensional Array Storage (THE FOUNDATION)

**Status**: Researched - **PRIMARY STRATEGY**

**Idea**: Replace hash tables with multi-dimensional arrays indexed by dictionary-encoded keys. This works for ALL tables (including mixed string+integer keys) and is the foundation for GPU acceleration.

> **This is the key architectural change.** Once implemented, you get:
> - **27x speedup on CPU** (hash → array indexing)
> - **Direct path to GPU** (same arrays, different backend)
> - **Zero API changes** for model authors

#### The Key Insight

Hash tables exist because we have string keys. But strings can be **dictionary-encoded** to integers:

```
table_id: {"A": 0, "B": 1, "C": 2}  → 3 values
age:      direct index (0-100)      → 101 values
duration: direct index (0-24)       → 25 values
```

Once ALL keys are integers, we can use a multi-dimensional array:

```rust
// Array[table_idx][age][duration] = rate
let data: Vec<f64> = vec![0.0; 3 * 101 * 25];  // 7,575 values
data[0 * 101 * 25 + 30 * 25 + 0] = 0.001;      // "A", age 30, duration 0
```

#### Performance Comparison

**Current (hash lookup):**
```
For each of 54M rows:
  1. Encode (table_id, age, duration) → composite hash
  2. Probe hash table
  3. Return value
Total: 54M hash operations × ~20ns = ~1.1 seconds
```

**Multi-dimensional array:**
```
One-time setup:
  - Dictionary-encode "table_id" column → 3 hash lookups

For each of 54M rows:
  1. Compute linear index: table_idx * 101 * 25 + age * 25 + duration
  2. Direct array access: data[linear_idx]
Total: 3 hash lookups + 54M index computations × ~3ns = ~0.16 seconds
```

**~7x faster on CPU alone!**

#### Leveraging Polars Categoricals

Polars already does dictionary encoding via `Categorical` dtype:

```python
# Model points with categorical columns
model_points = pl.read_parquet("mp.parquet").with_columns(
    pl.col("mort_table_id").cast(pl.Categorical),
    pl.col("lapse_id").cast(pl.Categorical),
)

# .to_physical() gives integer codes directly - no hash needed!
table_idx = af.mort_table_id.to_physical()  # [0, 0, 1, 2, 0, ...]
```

If columns are already categorical, **we skip dictionary encoding entirely**.

#### Rust Implementation

```rust
pub struct ArrayNDTable {
    /// For each key column, how to map values to indices
    key_encoders: Vec<KeyEncoder>,
    /// Strides for computing linear index: [101*25, 25, 1]
    strides: Vec<usize>,
    /// Flat array: data[t*101*25 + age*25 + dur]
    data: Vec<f64>,
    /// Default for missing combinations (NaN)
    default: f64,
}

pub enum KeyEncoder {
    /// For integer keys with small range (age, duration, t)
    IntRange { offset: i64, size: usize },
    /// For string keys - build dictionary on first use
    Dictionary(AHashMap<String, usize>),
    /// For pre-encoded categorical columns - use physical value directly
    Categorical { size: usize },
}

impl ArrayNDTable {
    fn lookup(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        // 1. Encode each key column to indices (hash only for unique values!)
        let indices: Vec<UInt32Chunked> = key_cols.iter()
            .zip(&self.key_encoders)
            .map(|(col, enc)| enc.encode(col))
            .collect::<Result<_, _>>()?;

        // 2. Compute linear index in parallel
        let n = indices[0].len();
        let mut linear = vec![0usize; n];

        linear.par_chunks_mut(1024).enumerate().for_each(|(chunk_idx, chunk)| {
            let base = chunk_idx * 1024;
            for (i, slot) in chunk.iter_mut().enumerate() {
                let row = base + i;
                *slot = indices.iter()
                    .zip(&self.strides)
                    .map(|(idx_col, stride)| idx_col.get(row).unwrap_or(0) as usize * stride)
                    .sum();
            }
        });

        // 3. Gather values (pure array indexing!)
        let result: Vec<f64> = linear.par_iter()
            .map(|&idx| self.data.get(idx).copied().unwrap_or(self.default))
            .collect();

        Ok(Series::from_vec("result".into(), result))
    }
}
```

#### Memory Considerations

For a mortality table with 3 table_ids × 101 ages × 25 durations:
- **Dense array**: 3 × 101 × 25 × 8 bytes = **60 KB** (tiny!)
- **Hash table**: Similar, but with hash overhead

For larger tables, check density before choosing storage:
- Density > 30%: Use array (memory-efficient enough)
- Density < 30%: Fall back to hash table (sparse data)

#### Why This Matters for GPU

**This is the bridge to GPU acceleration.** Once tables are stored as arrays:

- **CPU (Polars)**: `data[linear_idx]` - already fast
- **GPU (JAX)**: `jnp.take(data, linear_idx)` - massively parallel

The same data structure works on both. No code changes needed when switching backends.

---

### Strategy 6: GPU Execution Path

**Status**: Researched - Dependent on Strategy 5 ONLY

**Key Insight**: Once Strategy 5 (array storage) is implemented, GPU execution is straightforward - the same arrays work on both CPU and GPU.

```
Strategy 5 (Array Storage)
         │
         ├──────────────────────────────────────┐
         │                                      │
         ▼                                      ▼
┌─────────────────────┐            ┌─────────────────────┐
│  CPU Backend        │            │  GPU Backend (JAX)  │
│  data[linear_idx]   │            │  jnp.take(data,idx) │
│  ~1s for 324M       │            │  ~0.6s for 324M     │
└─────────────────────┘            └─────────────────────┘
```

**Pre-denormalization (Strategy 1) is NOT required for GPU.** The GPU handles 324M array lookups trivially.

#### 6a: Implicit GPU Lookups (Primary Path)

**Idea**: Once tables are dense arrays (Strategy 5), moving to GPU means lookups become trivial array indexing - automatically parallelized across thousands of GPU threads.

**No GPU hash tables needed. No CUDA kernels to write. Just arrays.**

##### How It Works

```python
# 1. At model init (CPU): Build dense arrays, upload to GPU once
mort_array = jnp.array(mortality_table.to_dense_array())  # Shape: [3, 101, 25]
lapse_array = jnp.array(lapse_table.to_dense_array())     # Shape: [5, 15]
inv_array = jnp.array(inv_returns.to_dense_array())       # Shape: [3, 180, 2]

# 2. In JAX kernel: Pure array indexing (massively parallel)
@jax.jit
def projection_step(state, t, mort_array, lapse_array):
    # These are NOT hash lookups - they're array gathers!
    mort_rate = mort_array[state.table_idx, state.age, state.duration]
    lapse_rate = lapse_array[state.lapse_idx, state.duration]
    inv_return = inv_array[state.scenario_idx, t, state.fund_idx]

    # ... rest of projection calculation
    return new_state
```

##### Performance Expectations

| Backend | Throughput | Latency per Lookup |
|---------|------------|-------------------|
| CPU (Polars hash) | ~12M/sec | ~80ns |
| CPU (array index) | ~80M/sec | ~12ns |
| GPU (JAX array) | ~500M+/sec | ~2ns effective |

**GPU provides 40-50x throughput over current CPU hash lookups.**

##### Memory Layout for GPU

GPU prefers contiguous memory access patterns:

```python
# Good: Access pattern aligned with memory layout
# mort_array[policy_batch, :, :] - all ages/durations for batch of policies
mort_rates = jax.lax.dynamic_slice(mort_array, [batch_start, 0, 0], [batch_size, 101, 25])

# Better: Pre-gather only needed values before kernel
# If we know duration range is 0-24, pre-slice that dimension
mort_subset = mort_array[:, :, :25]  # [3, 101, 25] - fits in GPU L2 cache
```

##### JAX Implementation Architecture

The JAX backend would work as follows:

**1. Table Preparation (One-time, at model load)**

```python
class JaxAssumptionTables:
    """GPU-resident assumption tables."""

    def __init__(self, tables: dict[str, Table]):
        # Convert each table to dense array and upload to GPU
        self.mort_array = jax.device_put(
            tables["mortality"].to_dense_array()  # Shape: [n_tables, n_ages, n_durations]
        )
        self.lapse_array = jax.device_put(
            tables["lapse"].to_dense_array()      # Shape: [n_lapse_ids, n_durations]
        )
        self.inv_array = jax.device_put(
            tables["inv_returns"].to_dense_array() # Shape: [n_scenarios, n_timesteps, n_funds]
        )

        # Store key encoders for mapping strings → indices
        self.mort_table_encoder = tables["mortality"].get_key_encoder("table_id")
        self.lapse_id_encoder = tables["lapse"].get_key_encoder("lapse_id")
```

**2. Model Point Encoding (Per batch)**

```python
def encode_model_points(mp: pl.DataFrame, encoders: dict) -> dict[str, jnp.ndarray]:
    """Convert model points to GPU-friendly integer indices."""
    return {
        # String columns → encoded indices
        "mort_table_idx": jnp.array(encoders["mort_table"].encode(mp["mort_table_id"])),
        "lapse_idx": jnp.array(encoders["lapse"].encode(mp["lapse_id"])),
        "fund_idx": jnp.array(encoders["fund"].encode(mp["fund_id"])),

        # Integer columns → direct copy
        "age": jnp.array(mp["age_at_entry"].to_numpy()),
        "scenario_idx": jnp.array(mp["scenario_id"].to_numpy()),

        # Other policy data
        "sum_assured": jnp.array(mp["sum_assured"].to_numpy()),
        "premium": jnp.array(mp["premium"].to_numpy()),
    }
```

**3. The Projection Kernel**

```python
@functools.partial(jax.jit, static_argnums=(3,))  # n_timesteps is static
def run_projection(
    policy_data: dict[str, jnp.ndarray],   # Encoded model points
    assumption_tables: JaxAssumptionTables, # GPU-resident tables
    initial_state: dict[str, jnp.ndarray],  # Starting values
    n_timesteps: int,                        # Projection length
) -> dict[str, jnp.ndarray]:
    """Run projection for all policies in parallel on GPU."""

    n_policies = policy_data["age"].shape[0]

    def projection_step(carry, t):
        """Single timestep - vectorized across all policies."""
        state = carry

        # Compute duration (capped)
        duration = jnp.minimum(state["duration"], 24)

        # === LOOKUPS (all are array indexing, massively parallel) ===

        # Mortality: mort_array[table_idx, age + duration, duration]
        mort_rate = assumption_tables.mort_array[
            policy_data["mort_table_idx"],
            policy_data["age"] + duration,
            duration
        ]

        # Lapse: lapse_array[lapse_idx, duration]
        lapse_rate = assumption_tables.lapse_array[
            policy_data["lapse_idx"],
            jnp.minimum(duration, 14)
        ]

        # Investment returns: inv_array[scenario_idx, t, fund_idx]
        inv_return = assumption_tables.inv_array[
            policy_data["scenario_idx"],
            t,
            policy_data["fund_idx"]
        ]

        # === CALCULATIONS (standard actuarial logic) ===

        # Decrement probabilities
        q_x = mort_rate * state["lives"]
        w_x = lapse_rate * (state["lives"] - q_x)

        # Fund value projection
        new_fund_value = state["fund_value"] * (1 + inv_return) - state["charges"]

        # Update state
        new_state = {
            "lives": state["lives"] - q_x - w_x,
            "fund_value": new_fund_value,
            "duration": state["duration"] + 1,
            # ... other state variables
        }

        # Output for this timestep
        output = {
            "death_benefit": q_x * policy_data["sum_assured"],
            "surrender_value": w_x * new_fund_value,
            "fund_value": new_fund_value,
        }

        return new_state, output

    # Run projection using jax.lax.scan (efficient GPU loop)
    final_state, outputs = jax.lax.scan(
        projection_step,
        initial_state,
        jnp.arange(n_timesteps)
    )

    return outputs  # Shape: {metric: [n_timesteps, n_policies]}
```

**4. Batching for Large Models**

```python
def run_model_batched(
    model_points: pl.DataFrame,
    tables: JaxAssumptionTables,
    batch_size: int = 100_000,  # Tune based on GPU memory
) -> pl.DataFrame:
    """Run model in batches, aggregate results."""

    results = []
    for batch_start in range(0, len(model_points), batch_size):
        batch = model_points[batch_start:batch_start + batch_size]

        # Encode and run on GPU
        encoded = encode_model_points(batch, tables.encoders)
        initial = create_initial_state(encoded)

        outputs = run_projection(encoded, tables, initial, n_timesteps=180)

        # Transfer results back to CPU (only aggregates if needed)
        results.append(jax.device_get(outputs))

    return aggregate_results(results)
```

**5. Key JAX Features Used**

| Feature | Purpose |
|---------|---------|
| `jax.device_put()` | Upload arrays to GPU once |
| `@jax.jit` | Compile projection to optimized GPU kernel |
| `jax.lax.scan()` | Efficient time loop without Python overhead |
| `jax.vmap()` | (Alternative) Vectorize across policies explicitly |
| `jax.device_get()` | Transfer results back to CPU |

**6. Why This Is Fast**

```
Traditional (Polars + hash lookups):
  For each timestep:
    For each policy:
      Hash lookup mortality → ~20ns
      Hash lookup lapse → ~20ns
      Hash lookup returns → ~20ns
      Calculate → ~50ns
  Total: 180 × 300k × 110ns = ~6 seconds

JAX (arrays on GPU):
  Compile once: ~500ms (cached after first run)
  For each timestep (parallel across 300k policies):
    Array gather mortality → ~0.1ns effective
    Array gather lapse → ~0.1ns effective
    Array gather returns → ~0.1ns effective
    Calculate → ~1ns effective
  Total: 180 × ~1.5ns × 300k = ~0.08 seconds
  + overhead = ~0.5 seconds total
```

##### Optional: Pre-Denormalization on GPU

If memory is tight or you want maximum performance, pre-denormalization can be combined:

```python
# Pre-expand mortality rates per policy (on GPU)
# Shape: [n_policies, 25] instead of looking up each timestep
mort_by_duration = assumption_tables.mort_array[
    policy_data["mort_table_idx"][:, None],  # Broadcast
    policy_data["age"][:, None] + jnp.arange(25),
    jnp.arange(25)
]

# In projection loop, just index by duration
mort_rate = mort_by_duration[jnp.arange(n_policies), duration]
```

This trades memory (300k × 25 × 8 = 60MB) for fewer gather operations per timestep.

#### 6b: Explicit GPU Hash Tables (Fallback)

**Status**: Only needed for tables that resist densification

**When to consider**:
- Multi-key tables with huge sparse key spaces (>10M combinations, <1% density)
- Giant scenario-specific surfaces where densifying would blow GPU memory
- Tables keyed by combinations like (age, duration, smoker, product, region, rider1, rider2, ...)

##### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Polars Plugin                             │
├─────────────────────────────────────────────────────────────┤
│  if gpu_available && table.is_sparse:                       │
│      use GpuHashTable                                        │
│  else:                                                       │
│      use ArrayNDTable (or AHashMap fallback)                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    GPU Hash Table                            │
├─────────────────────────────────────────────────────────────┤
│  Build Phase (once per table):                               │
│    1. Encode keys to u64 on CPU                             │
│    2. Copy keys[] + vals[] to GPU                           │
│    3. Build hash table via CUDA kernel (cuCollections/RAFT) │
│                                                              │
│  Query Phase (per lookup):                                   │
│    1. Encode query keys to u64                              │
│    2. Copy to GPU (batched, async)                          │
│    3. Launch probe kernel - each thread probes one key      │
│    4. Copy results back to CPU                              │
└─────────────────────────────────────────────────────────────┘
```

##### When GPU Hash Tables Pay Off

GPU hash lookups are faster than CPU, but data transfer has overhead:

```
CPU hash lookup:     ~20ns per lookup
GPU hash lookup:     ~5ns per lookup (once data is on device)
PCIe transfer:       ~1µs per KB (round trip)
```

Break-even analysis:
- Transfer 1M keys (8 MB): ~8ms overhead
- Lookup 1M keys on GPU: ~5ms
- Lookup 1M keys on CPU: ~20ms

**GPU wins when batch size > ~500k lookups per table.**

##### Libraries

- **cuCollections**: NVIDIA's GPU hash table implementation
- **RAFT**: RAPIDS ML library with GPU data structures
- **Custom CUDA**: Open addressing with linear probing (simpler, often sufficient)

##### Recommendation

Treat 6b as "break glass in emergency":

1. Implement Strategies 1 + 5 first (pre-denorm + arrays)
2. Profile to find remaining bottlenecks
3. If a specific table still dominates AND can't be densified → consider GPU hash

For typical actuarial models, 6a (implicit GPU via arrays) should handle 95%+ of lookups.

---

### Strategy 7: Reduce Lookup Count via Derivation

**Status**: Not yet researched

**Idea**: Derive some assumptions from others instead of separate lookups.

**Example**: Single lookup returning multiple columns:

```python
# Current: 2 lookups
af.mort_scalar = scalar_table.lookup(duration=af.duration, scalar_id="mort")
af.lapse_scalar = scalar_table.lookup(duration=af.duration, scalar_id="lapse")

# Proposed: 1 lookup returning struct
scalars = scalar_table.lookup_multi(
    duration=af.duration,
    columns=["mort_scalar", "lapse_scalar"]
)
```

---

## Impact Summary

| Strategy | Impact | Effort | Risk | Required? |
|----------|--------|--------|------|-----------|
| **5. Multi-dim arrays** | **27x on CPU** | Medium | Low | ✅ **FOUNDATION** |
| **6a. GPU (implicit)** | **45x total** | Low | Low | ✅ Primary goal |
| 1. Pre-denormalization | Additional 2-3x | Medium | Medium | ❌ Optional |
| 2. Array indexing (1D) | Subsumed by #5 | - | - | ❌ Superseded |
| 3. Caching | Unnecessary | - | - | ❌ Skip |
| 4. Lookup fusion | Minor gains | Medium | Low | ❌ Optional |
| 6b. GPU (explicit hash) | Sparse tables only | High | High | ❌ Rare cases |
| 7. Derivation | 10-20% | Low | Low | ❌ Optional |

**Recommended path** (simplest to GPU):
1. **Strategy 5: Multi-dim array storage** - transforms architecture
2. **Strategy 6a: JAX/GPU backend** - same arrays, massive parallelism

That's it. Two steps.

### The Simplified GPU Path

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Current State                                                          │
│  324M hash lookups @ 12M/sec = ~27 seconds                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  Strategy 5: Replace hash tables
                                    │  with multi-dimensional arrays
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  After Strategy 5 (Arrays on CPU)                                       │
│  ~100 dict lookups + 324M array index @ 300M/sec = ~1 second           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  Strategy 6a: Same arrays,
                                    │  JAX backend on GPU
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  After Strategy 6a (Arrays on GPU)                                      │
│  324M array index @ 500M+/sec = ~0.6 seconds                           │
│  + projection calculations also on GPU                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Total: 27s → 0.6s = ~45x improvement in TWO STEPS**

### Optional Enhancements

After the core path is working:

| Enhancement | When to Consider |
|-------------|------------------|
| Pre-denormalization | CPU-only deployment, want extra 2-3x |
| Lookup fusion | Many small tables with shared keys |
| GPU hash tables | One stubborn sparse table dominates |

---

## Implementation Plan

### Phase 1: Array Storage Architecture (THE FOUNDATION)
**Goal**: Eliminate hash tables, enable GPU path

- [ ] Implement `ArrayNDTable` with dictionary-encoded keys
- [ ] Add `KeyEncoder` variants (IntRange, Dictionary, Categorical)
- [ ] Add `Table.to_dense_array()` for numpy/JAX export
- [ ] Auto-detection: choose array vs hash based on density (>30% = array)
- [ ] Leverage Polars `Categorical` columns via `.to_physical()`
- [ ] Benchmark: Target ~1s (down from 27s)

**Deliverable**: All lookups are array-based, ready for any backend

### Phase 2: JAX/GPU Backend
**Goal**: 45x total speedup

- [ ] Implement `JaxAssumptionTables` class for GPU-resident arrays
- [ ] Create JAX projection kernel using `jax.lax.scan()`
- [ ] Add model point encoding (string → index mapping)
- [ ] GPU memory management: upload tables once, batch policies
- [ ] Benchmark: Target ~0.6s on GPU

**Deliverable**: Full GPU-accelerated model execution

### Phase 3: Polish and Optional Enhancements

- [ ] Pre-denormalization API (optional, for CPU-only scenarios)
- [ ] GPU hash tables (Strategy 6b) for rare sparse tables
- [ ] Multi-GPU support for very large models
- [ ] Documentation and migration guide

### Dependency Graph (Simplified)

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: Array Storage                                         │
│  ─────────────────────────                                      │
│  • Replace AHashMap with ArrayNDTable                           │
│  • Dictionary-encode string keys                                │
│  • Result: 27s → 1s on CPU (27x speedup)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│  Phase 2: JAX/GPU       │   │  (Optional)             │
│  ─────────────────      │   │  Pre-denormalization    │
│  • Same arrays on GPU   │   │  for CPU-only deploys   │
│  • 1s → 0.6s (45x total)│   │                         │
└─────────────────────────┘   └─────────────────────────┘
```

**Key insight**: Phase 1 is the only prerequisite for GPU. Everything else is optional.

---

## Open Questions

### CPU Optimization Questions

1. **Memory vs speed trade-off**: Is 10x memory increase acceptable for pre-denormalization?

2. **List column performance**: How fast is `list.get(idx)` vs hash lookup in Polars?

3. **Integration with ScenarioRun**: How do these optimizations interact with RFC 28 batching?

4. **Auto-detection**: Can we automatically choose optimal storage (hash vs array vs multi-dim)?

5. **Categorical column adoption**: Should we encourage/require categorical columns for string keys in model points?

### GPU Execution Questions

6. **JAX vs other backends**: Is JAX the right choice, or should we consider:
   - **CuPy**: More numpy-like, less compilation overhead
   - **Triton**: Custom kernels with Python syntax
   - **CUDA directly**: Maximum control, maximum effort

7. **GPU memory limits**: What's the maximum model size that fits in GPU memory?
   - A100 80GB vs consumer GPUs (8-24GB)
   - Can we stream batches if model exceeds GPU memory?

8. **Mixed CPU/GPU execution**: For models with one huge sparse table:
   - Run 95% on GPU (dense array lookups)
   - Fall back to CPU for the sparse table
   - Is the data transfer overhead worth it?

9. **Multi-GPU scaling**: For very large models:
   - Data parallelism: split policies across GPUs
   - Model parallelism: split assumption tables across GPUs
   - Which approach works better for actuarial workloads?

10. **Cloud GPU selection**: For Azure deployment:
    - A100 vs H100 vs AMD MI250
    - Cost/performance trade-offs
    - Spot instance viability for batch workloads

---

## References

- [Rust Assumptions Implementation](../../../core/src/assumptions/)
- [Python Assumptions API](../../gaspatchio_core/assumptions/_api.py)
- [RFC 28: ScenarioRun](../28-scenario-runs/28-scenario-runs-rfc.md)
- [Example Model](../../tests/scratch/scenarios/model_applied_life.py)
