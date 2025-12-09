# Array Storage Implementation Plan (RFC 29 Strategy 5)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace hash table lookups with multi-dimensional array indexing using dictionary-encoded keys, achieving ~3-5x lookup speedup while maintaining full backward compatibility.

**Architecture:** Add `ArrayNDTable` as an alternative storage backend alongside existing `AHashMap`. Both backends live behind a `TableStorage` enum with unified `lookup_series()` interface. Python controls which backend via a flag. Benchmarks run identical inputs through both backends for direct comparison.

**Tech Stack:** Rust (polars 0.49, rayon 1.10, ahash 0.8), PyO3 bindings, Criterion benchmarks

---

## File Structure After Implementation

```
core/src/assumptions/
├── mod.rs                      # Module exports
├── registry.rs                 # UNCHANGED - storage agnostic
├── table.rs                    # Slim coordinator, TableStorage enum
├── hash_storage.rs             # NEW - extracted hash table impl
├── array_storage.rs            # NEW - ArrayNDTable implementation
└── key_encoder.rs              # NEW - KeyEncoder types

bindings/python/src/
├── assumptions.rs              # Add storage_mode kwarg
└── ...

benches/
├── assumption_table_lookup_benchmark.rs  # Add array vs hash comparison
└── ...
```

---

## Task 1: Extract Hash Storage to Separate Module

**Files:**
- Create: `core/src/assumptions/hash_storage.rs`
- Modify: `core/src/assumptions/table.rs`
- Modify: `core/src/assumptions/mod.rs`

**Step 1: Create hash_storage.rs with extracted types**

Create `core/src/assumptions/hash_storage.rs`:

```rust
// ABOUTME: Hash-based assumption table storage using AHashMap.
// ABOUTME: Original implementation extracted for modularity alongside array storage.

use ahash::{AHashMap, AHasher};
use polars::prelude::*;
use rayon::prelude::*;
use std::hash::Hasher;

/// Codec for encoding column values to u64 keys for hash table lookup.
#[derive(Debug, Clone)]
pub enum ColumnCodec {
    String,
    Float64,
    Integer,
}

impl ColumnCodec {
    #[inline]
    pub fn encode(&self, av: AnyValue) -> u64 {
        match (self, av) {
            // String encoding - handle special cases first (categorical indices)
            (ColumnCodec::String, AnyValue::Categorical(idx, _, _)) => u64::from(idx),
            (ColumnCodec::String, AnyValue::String(s)) => {
                let mut hasher = AHasher::default();
                hasher.write(s.as_bytes());
                hasher.finish()
            }
            (ColumnCodec::String, AnyValue::StringOwned(s)) => {
                let mut hasher = AHasher::default();
                hasher.write(s.as_bytes());
                hasher.finish()
            }
            (ColumnCodec::String, AnyValue::Int64(i)) => {
                let s = i.to_string();
                let mut hasher = AHasher::default();
                hasher.write(s.as_bytes());
                hasher.finish()
            }
            (ColumnCodec::String, AnyValue::Int32(i)) => {
                let s = i.to_string();
                let mut hasher = AHasher::default();
                hasher.write(s.as_bytes());
                hasher.finish()
            }
            (ColumnCodec::String, AnyValue::UInt64(u)) => {
                let s = u.to_string();
                let mut hasher = AHasher::default();
                hasher.write(s.as_bytes());
                hasher.finish()
            }
            (ColumnCodec::String, AnyValue::UInt32(u)) => {
                let s = u.to_string();
                let mut hasher = AHasher::default();
                hasher.write(s.as_bytes());
                hasher.finish()
            }
            (ColumnCodec::String, AnyValue::Float64(f)) => {
                let s = if f.fract() == 0.0 && f.is_finite() {
                    format!("{}", f as i64)
                } else {
                    f.to_string()
                };
                let mut hasher = AHasher::default();
                hasher.write(s.as_bytes());
                hasher.finish()
            }
            (ColumnCodec::Float64, AnyValue::Float64(f)) => {
                if f.fract() == 0.0 && f.is_finite() {
                    f as i64 as u64
                } else {
                    f.to_bits()
                }
            }
            (ColumnCodec::Float64, AnyValue::Int64(i)) => i as u64,
            (ColumnCodec::Float64, AnyValue::Int32(i)) => i as u64,
            (ColumnCodec::Float64, AnyValue::UInt64(u)) => u,
            (ColumnCodec::Float64, AnyValue::UInt32(u)) => u as u64,
            (ColumnCodec::Integer, AnyValue::Int64(i)) => i as u64,
            (ColumnCodec::Integer, AnyValue::Int32(i)) => i as u64,
            (ColumnCodec::Integer, AnyValue::UInt64(u)) => u,
            (ColumnCodec::Integer, AnyValue::UInt32(u)) => u as u64,
            (ColumnCodec::Integer, AnyValue::Float64(f)) => {
                if f.fract() == 0.0 && f.is_finite() {
                    f as i64 as u64
                } else {
                    f.to_bits()
                }
            }
            _ => 0u64,
        }
    }
}

/// Hash-based storage backend for assumption tables.
#[derive(Debug)]
pub struct HashStorage {
    pub(crate) codecs: Vec<ColumnCodec>,
    pub(crate) map: AHashMap<u64, f64>,
}

impl HashStorage {
    /// Build hash storage from DataFrame.
    pub fn build(
        df: &DataFrame,
        keys: &[String],
        value: &str,
    ) -> PolarsResult<Self> {
        let n_rows = df.height();

        // Prepare codecs
        let mut codecs = Vec::with_capacity(keys.len());
        for col_name in keys {
            let s = df.column(col_name)?;
            codecs.push(match s.dtype() {
                DataType::String => ColumnCodec::String,
                DataType::Float64 => ColumnCodec::Float64,
                _ => ColumnCodec::Integer,
            });
        }

        // Build the hash map
        let mut map: AHashMap<u64, f64> = AHashMap::with_capacity(n_rows.next_power_of_two());
        let value_series = df.column(value)?.f64()?;

        for row_idx in 0..n_rows {
            let hash = Self::compute_hash_for_row(df, keys, &codecs, row_idx)?;
            let v = value_series.get(row_idx).unwrap_or(f64::NAN);
            map.insert(hash, v);
        }

        Ok(Self { codecs, map })
    }

    /// Compute hash for a single row during build.
    fn compute_hash_for_row(
        df: &DataFrame,
        keys: &[String],
        codecs: &[ColumnCodec],
        row_idx: usize,
    ) -> PolarsResult<u64> {
        if codecs.len() == 2 {
            // Fast path for 2-key case
            let av1 = df.column(&keys[0])?.get(row_idx)?;
            let av2 = df.column(&keys[1])?.get(row_idx)?;
            let hash1 = codecs[0].encode(av1);
            let hash2 = codecs[1].encode(av2);
            Ok(hash1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ hash2)
        } else {
            let mut h = AHasher::default();
            for (codec, key_name) in codecs.iter().zip(keys) {
                let av = df.column(key_name)?.get(row_idx)?;
                h.write_u64(codec.encode(av));
            }
            Ok(h.finish())
        }
    }

    /// Lookup values for scalar key columns.
    pub fn lookup_scalar(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        let len = key_cols[0].len();

        // Validate all series have same length
        for s in key_cols.iter().skip(1) {
            if s.len() != len {
                return Err(polars_err!(ShapeMismatch: "key columns not equal length"));
            }
        }

        // Fast path for common case: 2 keys with >1000 rows
        if self.codecs.len() == 2 && len > 1000 {
            return self.lookup_scalar_fast_path_2keys(key_cols);
        }

        let mut out = vec![f64::NAN; len];

        out.par_iter_mut().enumerate().for_each(|(idx, slot)| {
            let key = if self.codecs.len() == 2 {
                let av1 = unsafe { key_cols[0].get_unchecked(idx) };
                let av2 = unsafe { key_cols[1].get_unchecked(idx) };
                let hash1 = self.codecs[0].encode(av1);
                let hash2 = self.codecs[1].encode(av2);
                hash1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ hash2
            } else {
                let mut h = AHasher::default();
                for (codec, series) in self.codecs.iter().zip(key_cols) {
                    let av = unsafe { series.get_unchecked(idx) };
                    h.write_u64(codec.encode(av));
                }
                h.finish()
            };
            if let Some(v) = self.map.get(&key) {
                *slot = *v;
            }
        });

        Ok(Series::from_vec("lookup".into(), out))
    }

    /// Fast path for 2-key lookups.
    fn lookup_scalar_fast_path_2keys(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        let len = key_cols[0].len();
        let mut out = vec![f64::NAN; len];

        let series1 = key_cols[0];
        let series2 = key_cols[1];

        const CHUNK_SIZE: usize = 1024;

        out.par_chunks_mut(CHUNK_SIZE)
            .enumerate()
            .for_each(|(chunk_idx, chunk)| {
                let start_idx = chunk_idx * CHUNK_SIZE;
                let end_idx = (start_idx + chunk.len()).min(len);

                for (local_idx, slot) in chunk.iter_mut().enumerate() {
                    let global_idx = start_idx + local_idx;
                    if global_idx >= end_idx {
                        break;
                    }

                    let av1 = unsafe { series1.get_unchecked(global_idx) };
                    let av2 = unsafe { series2.get_unchecked(global_idx) };

                    let hash1 = self.codecs[0].encode(av1);
                    let hash2 = self.codecs[1].encode(av2);

                    let key = hash1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ hash2;

                    if let Some(v) = self.map.get(&key) {
                        *slot = *v;
                    }
                }
            });

        Ok(Series::from_vec("lookup".into(), out))
    }

    /// Get the number of entries in the storage.
    pub fn entry_count(&self) -> usize {
        self.map.len()
    }

    /// Get reference to codecs for append validation.
    pub fn codecs(&self) -> &[ColumnCodec] {
        &self.codecs
    }
}
```

**Step 2: Update mod.rs to export new module**

Add to `core/src/assumptions/mod.rs`:

```rust
mod hash_storage;
pub use hash_storage::{ColumnCodec, HashStorage};
```

**Step 3: Run existing tests to ensure extraction doesn't break anything**

Run: `cd ~/Projects/gaspatchio/gaspatchio-core/core && cargo test assumptions`

Expected: All existing tests pass (we haven't changed table.rs yet)

**Step 4: Commit extraction**

```bash
git add core/src/assumptions/hash_storage.rs core/src/assumptions/mod.rs
git commit -m "refactor(assumptions): extract HashStorage to separate module

Prepares for adding ArrayStorage as alternative backend.
No functional changes - pure extraction."
```

---

## Task 2: Create KeyEncoder Types

**Files:**
- Create: `core/src/assumptions/key_encoder.rs`
- Modify: `core/src/assumptions/mod.rs`

**Step 1: Write test for KeyEncoder**

Add to end of `core/src/assumptions/key_encoder.rs`:

```rust
// ABOUTME: Key encoders for converting column values to array indices.
// ABOUTME: Supports integer ranges, string dictionaries, and Polars categoricals.

use ahash::AHashMap;
use polars::prelude::*;

/// Encodes column values to array indices for multi-dimensional array storage.
#[derive(Debug, Clone)]
pub enum KeyEncoder {
    /// Integer keys with known range (age 0-100, duration 0-24).
    IntRange {
        offset: i64,
        size: usize,
    },
    /// String keys mapped to indices via dictionary.
    Dictionary {
        value_to_idx: AHashMap<String, u32>,
        size: usize,
    },
    /// Pre-encoded categorical columns - use physical value directly.
    Categorical {
        size: usize,
    },
}

impl KeyEncoder {
    /// Build encoder for an integer column with known min/max.
    pub fn int_range(min_val: i64, max_val: i64) -> Self {
        KeyEncoder::IntRange {
            offset: min_val,
            size: (max_val - min_val + 1) as usize,
        }
    }

    /// Build encoder for a string column by extracting unique values.
    pub fn dictionary(unique_values: &[String]) -> Self {
        let value_to_idx: AHashMap<String, u32> = unique_values
            .iter()
            .enumerate()
            .map(|(i, v)| (v.clone(), i as u32))
            .collect();
        KeyEncoder::Dictionary {
            size: unique_values.len(),
            value_to_idx,
        }
    }

    /// Build encoder for categorical column.
    pub fn categorical(n_categories: usize) -> Self {
        KeyEncoder::Categorical { size: n_categories }
    }

    /// Build encoder automatically from a Series.
    pub fn from_series(series: &Series) -> PolarsResult<Self> {
        match series.dtype() {
            DataType::Categorical(_, _) => {
                let n_unique = series.n_unique()?;
                Ok(KeyEncoder::categorical(n_unique))
            }
            DataType::Int64 | DataType::Int32 | DataType::UInt64 | DataType::UInt32 => {
                let min = series.min::<i64>()?.unwrap_or(0);
                let max = series.max::<i64>()?.unwrap_or(0);
                Ok(KeyEncoder::int_range(min, max))
            }
            DataType::Float64 => {
                // Treat as integer if all whole numbers
                let f64_ca = series.f64()?;
                let all_whole = f64_ca.into_iter().all(|opt| {
                    opt.map(|f| f.fract() == 0.0 && f.is_finite()).unwrap_or(true)
                });
                if all_whole {
                    let min = series.min::<i64>()?.unwrap_or(0);
                    let max = series.max::<i64>()?.unwrap_or(0);
                    Ok(KeyEncoder::int_range(min, max))
                } else {
                    Err(polars_err!(ComputeError: "Float64 keys with decimals not supported for array storage"))
                }
            }
            DataType::String => {
                let unique: Vec<String> = series
                    .unique()?
                    .str()?
                    .into_iter()
                    .filter_map(|opt| opt.map(|s| s.to_string()))
                    .collect();
                Ok(KeyEncoder::dictionary(&unique))
            }
            dt => Err(polars_err!(ComputeError: "Unsupported key type for array storage: {:?}", dt)),
        }
    }

    /// Get the size (cardinality) of this encoder.
    pub fn size(&self) -> usize {
        match self {
            KeyEncoder::IntRange { size, .. } => *size,
            KeyEncoder::Dictionary { size, .. } => *size,
            KeyEncoder::Categorical { size } => *size,
        }
    }

    /// Encode a single AnyValue to an index. Returns None for out-of-bounds or unknown values.
    #[inline]
    pub fn encode(&self, av: AnyValue) -> Option<u32> {
        match (self, av) {
            // Integer range encoding
            (KeyEncoder::IntRange { offset, size }, AnyValue::Int64(i)) => {
                let idx = i - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::Int32(i)) => {
                let idx = i as i64 - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::UInt64(u)) => {
                let idx = u as i64 - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::UInt32(u)) => {
                let idx = u as i64 - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::Float64(f)) => {
                if f.fract() == 0.0 && f.is_finite() {
                    let idx = f as i64 - offset;
                    if idx >= 0 && (idx as usize) < *size {
                        Some(idx as u32)
                    } else {
                        None
                    }
                } else {
                    None
                }
            }

            // Dictionary encoding
            (KeyEncoder::Dictionary { value_to_idx, .. }, AnyValue::String(s)) => {
                value_to_idx.get(s).copied()
            }
            (KeyEncoder::Dictionary { value_to_idx, .. }, AnyValue::StringOwned(s)) => {
                value_to_idx.get(s.as_str()).copied()
            }

            // Categorical - use physical index directly
            (KeyEncoder::Categorical { size }, AnyValue::Categorical(idx, _, _)) => {
                if (idx as usize) < *size {
                    Some(idx)
                } else {
                    None
                }
            }

            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_int_range_encoder() {
        let encoder = KeyEncoder::int_range(18, 100);
        assert_eq!(encoder.size(), 83);

        // Valid values
        assert_eq!(encoder.encode(AnyValue::Int64(18)), Some(0));
        assert_eq!(encoder.encode(AnyValue::Int64(50)), Some(32));
        assert_eq!(encoder.encode(AnyValue::Int64(100)), Some(82));

        // Out of bounds
        assert_eq!(encoder.encode(AnyValue::Int64(17)), None);
        assert_eq!(encoder.encode(AnyValue::Int64(101)), None);

        // Float that's a whole number
        assert_eq!(encoder.encode(AnyValue::Float64(50.0)), Some(32));
    }

    #[test]
    fn test_dictionary_encoder() {
        let values = vec!["M".to_string(), "F".to_string()];
        let encoder = KeyEncoder::dictionary(&values);
        assert_eq!(encoder.size(), 2);

        assert_eq!(encoder.encode(AnyValue::String("M")), Some(0));
        assert_eq!(encoder.encode(AnyValue::String("F")), Some(1));
        assert_eq!(encoder.encode(AnyValue::String("X")), None);
    }

    #[test]
    fn test_from_series_integer() -> PolarsResult<()> {
        let series = Series::new("age".into(), &[18i64, 25, 30, 100]);
        let encoder = KeyEncoder::from_series(&series)?;

        match encoder {
            KeyEncoder::IntRange { offset, size } => {
                assert_eq!(offset, 18);
                assert_eq!(size, 83); // 100 - 18 + 1
            }
            _ => panic!("Expected IntRange encoder"),
        }
        Ok(())
    }

    #[test]
    fn test_from_series_string() -> PolarsResult<()> {
        let series = Series::new("gender".into(), &["M", "F", "M", "F"]);
        let encoder = KeyEncoder::from_series(&series)?;

        match encoder {
            KeyEncoder::Dictionary { size, .. } => {
                assert_eq!(size, 2);
            }
            _ => panic!("Expected Dictionary encoder"),
        }
        Ok(())
    }
}
```

**Step 2: Update mod.rs**

Add to `core/src/assumptions/mod.rs`:

```rust
mod key_encoder;
pub use key_encoder::KeyEncoder;
```

**Step 3: Run tests**

Run: `cd ~/Projects/gaspatchio/gaspatchio-core/core && cargo test key_encoder`

Expected: 4 tests pass

**Step 4: Commit**

```bash
git add core/src/assumptions/key_encoder.rs core/src/assumptions/mod.rs
git commit -m "feat(assumptions): add KeyEncoder types for array indexing

Supports IntRange, Dictionary, and Categorical encoders.
Foundation for multi-dimensional array storage."
```

---

## Task 3: Create ArrayStorage Implementation

**Files:**
- Create: `core/src/assumptions/array_storage.rs`
- Modify: `core/src/assumptions/mod.rs`

**Step 1: Write ArrayStorage with tests**

Create `core/src/assumptions/array_storage.rs`:

```rust
// ABOUTME: Multi-dimensional array storage for assumption tables.
// ABOUTME: Uses dictionary-encoded keys for O(1) array indexing instead of hash lookups.

use crate::assumptions::key_encoder::KeyEncoder;
use polars::prelude::*;
use rayon::prelude::*;

/// Multi-dimensional array storage backend for assumption tables.
/// Stores values in a flat contiguous array with computed strides.
#[derive(Debug)]
pub struct ArrayStorage {
    /// Encoder for each key column
    pub(crate) encoders: Vec<KeyEncoder>,
    /// Strides for computing linear index: [dim1*dim2*..., dim2*dim3*..., ..., 1]
    pub(crate) strides: Vec<usize>,
    /// Flat contiguous array of values
    pub(crate) data: Vec<f64>,
    /// Total capacity (product of all dimensions)
    pub(crate) capacity: usize,
}

impl ArrayStorage {
    /// Build array storage from DataFrame.
    /// Returns None if table is too sparse (< 30% density).
    pub fn build(
        df: &DataFrame,
        keys: &[String],
        value: &str,
    ) -> PolarsResult<Option<Self>> {
        let n_rows = df.height();

        // Build encoders for each key column
        let mut encoders = Vec::with_capacity(keys.len());
        for key_name in keys {
            let series = df.column(key_name)?;
            let encoder = KeyEncoder::from_series(series)?;
            encoders.push(encoder);
        }

        // Compute dimensions and total capacity
        let dims: Vec<usize> = encoders.iter().map(|e| e.size()).collect();
        let capacity: usize = dims.iter().product();

        // Check density - only use array if > 30% filled
        let density = n_rows as f64 / capacity as f64;
        if density < 0.3 {
            log::debug!(
                "Table density {:.1}% < 30%, falling back to hash storage",
                density * 100.0
            );
            return Ok(None);
        }

        // Check memory limit - don't create arrays > 100MB
        let memory_bytes = capacity * std::mem::size_of::<f64>();
        if memory_bytes > 100 * 1024 * 1024 {
            log::debug!(
                "Array would be {}MB > 100MB limit, falling back to hash storage",
                memory_bytes / (1024 * 1024)
            );
            return Ok(None);
        }

        // Compute strides (row-major order)
        let mut strides = vec![1usize; dims.len()];
        for i in (0..dims.len() - 1).rev() {
            strides[i] = strides[i + 1] * dims[i + 1];
        }

        // Allocate array with NaN default
        let mut data = vec![f64::NAN; capacity];

        // Fill from DataFrame
        let value_series = df.column(value)?.f64()?;

        for row_idx in 0..n_rows {
            // Encode each key to index
            let mut linear_idx = 0usize;
            let mut valid = true;

            for (i, key_name) in keys.iter().enumerate() {
                let av = df.column(key_name)?.get(row_idx)?;
                if let Some(idx) = encoders[i].encode(av) {
                    linear_idx += idx as usize * strides[i];
                } else {
                    valid = false;
                    break;
                }
            }

            if valid {
                let v = value_series.get(row_idx).unwrap_or(f64::NAN);
                data[linear_idx] = v;
            }
        }

        log::debug!(
            "Built ArrayStorage: dims={:?}, capacity={}, density={:.1}%, memory={}KB",
            dims, capacity, density * 100.0, memory_bytes / 1024
        );

        Ok(Some(Self {
            encoders,
            strides,
            data,
            capacity,
        }))
    }

    /// Lookup values for scalar key columns.
    pub fn lookup_scalar(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        let len = key_cols[0].len();

        // Validate all series have same length
        for s in key_cols.iter().skip(1) {
            if s.len() != len {
                return Err(polars_err!(ShapeMismatch: "key columns not equal length"));
            }
        }

        let mut out = vec![f64::NAN; len];

        // Parallel processing with chunking for cache locality
        const CHUNK_SIZE: usize = 1024;

        out.par_chunks_mut(CHUNK_SIZE)
            .enumerate()
            .for_each(|(chunk_idx, chunk)| {
                let start_idx = chunk_idx * CHUNK_SIZE;
                let end_idx = (start_idx + chunk.len()).min(len);

                for (local_idx, slot) in chunk.iter_mut().enumerate() {
                    let global_idx = start_idx + local_idx;
                    if global_idx >= end_idx {
                        break;
                    }

                    // Compute linear index from all keys
                    let mut linear_idx = 0usize;
                    let mut valid = true;

                    for (i, series) in key_cols.iter().enumerate() {
                        let av = unsafe { series.get_unchecked(global_idx) };
                        if let Some(idx) = self.encoders[i].encode(av) {
                            linear_idx += idx as usize * self.strides[i];
                        } else {
                            valid = false;
                            break;
                        }
                    }

                    if valid && linear_idx < self.data.len() {
                        *slot = self.data[linear_idx];
                    }
                }
            });

        Ok(Series::from_vec("lookup".into(), out))
    }

    /// Get the number of non-NaN entries in the storage.
    pub fn entry_count(&self) -> usize {
        self.data.iter().filter(|v| !v.is_nan()).count()
    }

    /// Get encoders for external use (e.g., validation).
    pub fn encoders(&self) -> &[KeyEncoder] {
        &self.encoders
    }

    /// Export as dense array for GPU/JAX backend.
    pub fn to_dense_array(&self) -> &[f64] {
        &self.data
    }

    /// Get array dimensions.
    pub fn dimensions(&self) -> Vec<usize> {
        self.encoders.iter().map(|e| e.size()).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use polars::df;

    #[test]
    fn test_array_storage_build() -> PolarsResult<()> {
        // Create a dense table: 3 ages x 2 genders = 6 entries, 6 rows = 100% density
        let df = df! {
            "age" => [30i64, 30, 31, 31, 32, 32],
            "gender" => ["M", "F", "M", "F", "M", "F"],
            "rate" => [0.001, 0.0008, 0.0012, 0.001, 0.0014, 0.0012]
        }?;

        let storage = ArrayStorage::build(
            &df,
            &["age".to_string(), "gender".to_string()],
            "rate",
        )?;

        assert!(storage.is_some(), "Should build array storage for dense table");
        let storage = storage.unwrap();

        assert_eq!(storage.dimensions(), vec![3, 2]); // 3 ages x 2 genders
        assert_eq!(storage.entry_count(), 6);

        Ok(())
    }

    #[test]
    fn test_array_storage_lookup() -> PolarsResult<()> {
        let df = df! {
            "age" => [30i64, 30, 31, 31, 32, 32],
            "gender" => ["M", "F", "M", "F", "M", "F"],
            "rate" => [0.001, 0.0008, 0.0012, 0.001, 0.0014, 0.0012]
        }?;

        let storage = ArrayStorage::build(
            &df,
            &["age".to_string(), "gender".to_string()],
            "rate",
        )?.expect("Should build array storage");

        // Test lookup
        let age_series = Series::new("age".into(), &[30i64, 31, 32, 99]);
        let gender_series = Series::new("gender".into(), &["F", "F", "F", "M"]);

        let result = storage.lookup_scalar(&[&age_series, &gender_series])?;

        let values: Vec<f64> = result.f64()?.into_no_null_iter().collect();
        assert!((values[0] - 0.0008).abs() < 1e-10); // age=30, gender=F
        assert!((values[1] - 0.001).abs() < 1e-10);  // age=31, gender=F
        assert!((values[2] - 0.0012).abs() < 1e-10); // age=32, gender=F
        assert!(values[3].is_nan());                  // age=99 - not in table

        Ok(())
    }

    #[test]
    fn test_sparse_table_falls_back() -> PolarsResult<()> {
        // Create a very sparse table: 2 entries for 100*100 = 10000 capacity = 0.02% density
        let df = df! {
            "key1" => [0i64, 99],
            "key2" => [0i64, 99],
            "value" => [1.0, 2.0]
        }?;

        let storage = ArrayStorage::build(
            &df,
            &["key1".to_string(), "key2".to_string()],
            "value",
        )?;

        assert!(storage.is_none(), "Should return None for sparse table");

        Ok(())
    }
}
```

**Step 2: Update mod.rs**

Add to `core/src/assumptions/mod.rs`:

```rust
mod array_storage;
pub use array_storage::ArrayStorage;
```

**Step 3: Run tests**

Run: `cd ~/Projects/gaspatchio/gaspatchio-core/core && cargo test array_storage`

Expected: 3 tests pass

**Step 4: Commit**

```bash
git add core/src/assumptions/array_storage.rs core/src/assumptions/mod.rs
git commit -m "feat(assumptions): add ArrayStorage for multi-dimensional array lookups

- Dictionary-encoded keys for O(1) indexing
- Auto-falls back to hash for sparse tables (<30% density)
- Memory limit of 100MB per table
- Parallel chunk processing for cache locality"
```

---

## Task 4: Add TableStorage Enum and StorageMode

**Files:**
- Modify: `core/src/assumptions/table.rs`
- Modify: `core/src/assumptions/mod.rs`

**Step 1: Create storage mode enum and TableStorage**

Add to `core/src/assumptions/mod.rs` or create new file `core/src/assumptions/storage.rs`:

For simplicity, add to top of `table.rs` (after the existing code is refactored):

```rust
// ABOUTME: AssumptionTable with pluggable storage backends (hash or array).
// ABOUTME: Provides unified lookup interface with Python-controlled storage mode.

use crate::assumptions::array_storage::ArrayStorage;
use crate::assumptions::hash_storage::{ColumnCodec, HashStorage};
use polars::prelude::*;

/// Storage mode for assumption tables.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum StorageMode {
    /// Use hash table storage (original implementation).
    Hash,
    /// Use multi-dimensional array storage (faster for dense tables).
    Array,
    /// Automatically choose based on table density.
    #[default]
    Auto,
}

impl StorageMode {
    /// Parse from string (for Python interop).
    pub fn from_str(s: &str) -> PolarsResult<Self> {
        match s.to_lowercase().as_str() {
            "hash" => Ok(StorageMode::Hash),
            "array" => Ok(StorageMode::Array),
            "auto" => Ok(StorageMode::Auto),
            _ => Err(polars_err!(ComputeError: "Invalid storage mode: '{}'. Use 'hash', 'array', or 'auto'", s)),
        }
    }
}

/// Storage backend for assumption tables.
#[derive(Debug)]
pub enum TableStorage {
    Hash(HashStorage),
    Array(ArrayStorage),
}

impl TableStorage {
    /// Perform scalar lookup on the underlying storage.
    pub fn lookup_scalar(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        match self {
            TableStorage::Hash(h) => h.lookup_scalar(key_cols),
            TableStorage::Array(a) => a.lookup_scalar(key_cols),
        }
    }

    /// Get entry count from underlying storage.
    pub fn entry_count(&self) -> usize {
        match self {
            TableStorage::Hash(h) => h.entry_count(),
            TableStorage::Array(a) => a.entry_count(),
        }
    }

    /// Check if this is array storage.
    pub fn is_array(&self) -> bool {
        matches!(self, TableStorage::Array(_))
    }

    /// Check if this is hash storage.
    pub fn is_hash(&self) -> bool {
        matches!(self, TableStorage::Hash(_))
    }
}
```

**Step 2: Refactor AssumptionTable to use TableStorage**

Update `AssumptionTable` struct in `table.rs`:

```rust
#[derive(Debug)]
pub struct AssumptionTable {
    keys: Vec<String>,
    storage: TableStorage,
    storage_mode_used: StorageMode, // Track which mode was actually used
}

impl AssumptionTable {
    /// Build with specified storage mode.
    pub fn build_with_mode(
        df: DataFrame,
        keys: Vec<String>,
        value: String,
        mode: StorageMode,
    ) -> PolarsResult<Self> {
        let storage = match mode {
            StorageMode::Hash => {
                let hash = HashStorage::build(&df, &keys, &value)?;
                TableStorage::Hash(hash)
            }
            StorageMode::Array => {
                // Force array storage, but fall back to hash if it fails
                match ArrayStorage::build(&df, &keys, &value)? {
                    Some(arr) => TableStorage::Array(arr),
                    None => {
                        log::warn!("Array storage not suitable, falling back to hash");
                        let hash = HashStorage::build(&df, &keys, &value)?;
                        TableStorage::Hash(hash)
                    }
                }
            }
            StorageMode::Auto => {
                // Try array first, fall back to hash
                match ArrayStorage::build(&df, &keys, &value)? {
                    Some(arr) => TableStorage::Array(arr),
                    None => {
                        let hash = HashStorage::build(&df, &keys, &value)?;
                        TableStorage::Hash(hash)
                    }
                }
            }
        };

        let storage_mode_used = if storage.is_array() {
            StorageMode::Array
        } else {
            StorageMode::Hash
        };

        Ok(Self {
            keys,
            storage,
            storage_mode_used,
        })
    }

    /// Build with default (Auto) storage mode - backward compatible.
    pub fn build(df: DataFrame, keys: Vec<String>, value: String) -> PolarsResult<Self> {
        Self::build_with_mode(df, keys, value, StorageMode::Auto)
    }

    /// Get which storage mode is actually being used.
    pub fn storage_mode(&self) -> StorageMode {
        self.storage_mode_used
    }

    /// Check if using array storage.
    pub fn is_array_storage(&self) -> bool {
        self.storage.is_array()
    }

    pub fn lookup_series(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        // Validate input
        if key_cols.len() != self.keys.len() {
            return Err(polars_err!(ShapeMismatch: "wrong # key columns"));
        }

        // Check for vector inputs
        if key_cols.iter().all(|s| !matches!(s.dtype(), DataType::List(_))) {
            return self.storage.lookup_scalar(key_cols);
        }

        // Vector path - delegate to existing implementation
        // (For now, vector lookups use hash storage internally)
        self.lookup_vector_fallback(key_cols)
    }

    // ... keep existing helper methods for vector lookups ...

    // Metadata methods
    pub fn get_key_count(&self) -> usize {
        self.keys.len()
    }

    pub fn get_key_name(&self, index: usize) -> PolarsResult<&str> {
        self.keys.get(index).map(|s| s.as_str()).ok_or_else(|| {
            polars_err!(ComputeError: "Key index {} out of bounds", index)
        })
    }

    pub fn get_key_columns(&self) -> &[String] {
        &self.keys
    }

    pub fn get_key_columns_owned(&self) -> Vec<String> {
        self.keys.clone()
    }

    pub fn entry_count(&self) -> usize {
        self.storage.entry_count()
    }
}
```

**Step 3: Run all assumption tests**

Run: `cd ~/Projects/gaspatchio/gaspatchio-core/core && cargo test assumptions`

Expected: All tests pass

**Step 4: Commit**

```bash
git add core/src/assumptions/
git commit -m "feat(assumptions): add StorageMode and TableStorage enum

- StorageMode: Hash, Array, Auto (default)
- TableStorage enum for unified interface
- build_with_mode() for explicit control
- build() defaults to Auto for backward compat"
```

---

## Task 5: Add Python StorageMode Control

**Files:**
- Modify: `bindings/python/src/assumptions.rs`
- Modify: `bindings/python/gaspatchio_core/assumptions/_api.py`

**Step 1: Update Rust bindings to accept storage_mode**

Modify `bindings/python/src/assumptions.rs`:

```rust
// Add to imports
use gaspatchio_core_lib::assumptions::StorageMode;

// Update register_table method
#[pyo3(signature = (name, df, keys, value_column, storage_mode="auto"))]
fn register_table(
    &self,
    name: String,
    df: PyDataFrame,
    keys: Vec<String>,
    value_column: String,
    storage_mode: Option<&str>,
) -> PyResult<()> {
    let rust_df: DataFrame = df.into();
    let mode = StorageMode::from_str(storage_mode.unwrap_or("auto"))
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{}", e)))?;

    log::debug!(
        "PyAssumptionTableRegistry::register_table: Registering '{}' with mode {:?}",
        name, mode
    );

    // Use the new mode-aware registration
    register_assumption_table_global_with_mode(name.clone(), rust_df, keys, value_column, mode)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{}", e)))?;

    Ok(())
}

// Similarly update register_or_replace_table
#[pyo3(signature = (name, df, keys, value_column, force_replace=true, storage_mode="auto"))]
fn register_or_replace_table(
    &self,
    name: String,
    df: PyDataFrame,
    keys: Vec<String>,
    value_column: String,
    force_replace: Option<bool>,
    storage_mode: Option<&str>,
) -> PyResult<()> {
    let rust_df: DataFrame = df.into();
    let force = force_replace.unwrap_or(true);
    let mode = StorageMode::from_str(storage_mode.unwrap_or("auto"))
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{}", e)))?;

    register_or_replace_assumption_table_global_with_mode(
        name.clone(), rust_df, keys, value_column, force, mode
    )
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{}", e)))?;

    Ok(())
}

// Add method to query storage mode
fn get_table_storage_mode(&self, name: String) -> PyResult<Option<String>> {
    let registry = get_global_assumption_registry();
    if let Some(table) = registry.get_table(&name) {
        let mode = match table.storage_mode() {
            StorageMode::Hash => "hash",
            StorageMode::Array => "array",
            StorageMode::Auto => "auto",
        };
        Ok(Some(mode.to_string()))
    } else {
        Ok(None)
    }
}
```

**Step 2: Update Python Table class**

Modify `bindings/python/gaspatchio_core/assumptions/_api.py`:

Add `storage_mode` parameter to `Table.__init__`:

```python
from typing import Literal

StorageModeType = Literal["auto", "hash", "array"]

class Table:
    def __init__(
        self,
        *,
        name: str,
        source: pl.DataFrame | str | Path,
        dimensions: dict[str, str],
        value: str,
        storage_mode: StorageModeType = "auto",  # NEW
        # ... existing params ...
    ):
        # ... existing code ...
        self._storage_mode = storage_mode

    def _register_with_rust(self, processed_df: pl.DataFrame, key_columns: list[str]) -> None:
        """Register table with Rust backend."""
        try:
            _registry.register_or_replace_table(
                name=self._name,
                df=processed_df,
                keys=key_columns,
                value_column=self._value,
                force_replace=True,
                storage_mode=self._storage_mode,  # NEW
            )
            # ...
```

**Step 3: Add storage_mode to type stubs**

Update `bindings/python/gaspatchio_core/assumptions/__init__.pyi`:

```python
from typing import Literal

StorageModeType = Literal["auto", "hash", "array"]

class Table:
    def __init__(
        self,
        *,
        name: str,
        source: pl.DataFrame | str | Path,
        dimensions: dict[str, str],
        value: str,
        storage_mode: StorageModeType = "auto",
        # ... existing params ...
    ) -> None: ...
```

**Step 4: Run Python tests**

Run: `cd ~/Projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/assumptions/ -v`

Expected: All tests pass

**Step 5: Commit**

```bash
git add bindings/python/src/assumptions.rs bindings/python/gaspatchio_core/assumptions/
git commit -m "feat(python): add storage_mode parameter to Table

- 'auto' (default): choose based on density
- 'hash': force hash table storage
- 'array': force array storage (falls back if unsuitable)
- Enables A/B benchmarking of storage backends"
```

---

## Task 6: Add Comparison Benchmarks

**Files:**
- Modify: `core/benches/assumption_table_lookup_benchmark.rs`

**Step 1: Add benchmark comparing hash vs array**

Update `core/benches/assumption_table_lookup_benchmark.rs`:

```rust
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use gaspatchio_core_lib::assumptions::table::{AssumptionTable, StorageMode};
use polars::prelude::*;
// ... existing imports ...

// Create table with specific storage mode
fn create_mortality_table_with_mode(mode: StorageMode) -> PolarsResult<AssumptionTable> {
    let ages: Vec<i64> = (18..=100).collect();
    let df_mortality_wide = df!(
        "age-last" => ages.clone(),
        "MNS" => ages.iter().map(|&age| 0.001 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "FNS" => ages.iter().map(|&age| 0.0008 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "MS" => ages.iter().map(|&age| 0.0015 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "FS" => ages.iter().map(|&age| 0.0012 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
    )?;

    let df_mortality_long = custom_melt(
        &df_mortality_wide,
        &["age-last"],
        &["MNS", "FNS", "MS", "FS"],
        "gender_smoking",
        "mortality_rate",
    )?;

    AssumptionTable::build_with_mode(
        df_mortality_long,
        vec!["age-last".to_string(), "gender_smoking".to_string()],
        "mortality_rate".to_string(),
        mode,
    )
}

// Benchmark comparing hash vs array storage
fn benchmark_hash_vs_array_1k(c: &mut Criterion) {
    let df_model_points = match load_model_points_1k() {
        Ok(df) => df,
        Err(e) => {
            eprintln!("Failed to load model points: {}", e);
            return;
        }
    };

    let age_col = df_model_points.column("age-last").unwrap().as_series().unwrap();
    let gender_col = df_model_points.column("gender_smoking").unwrap().as_series().unwrap();
    let keys: Vec<&Series> = vec![age_col, gender_col];

    let mut group = c.benchmark_group("hash_vs_array_1k");

    // Hash storage
    let hash_table = create_mortality_table_with_mode(StorageMode::Hash).unwrap();
    group.bench_function("hash_lookup_1k", |b| {
        b.iter(|| {
            let result = hash_table.lookup_series(black_box(&keys));
            black_box(result)
        })
    });

    // Array storage
    let array_table = create_mortality_table_with_mode(StorageMode::Array).unwrap();
    assert!(array_table.is_array_storage(), "Should use array storage for dense table");
    group.bench_function("array_lookup_1k", |b| {
        b.iter(|| {
            let result = array_table.lookup_series(black_box(&keys));
            black_box(result)
        })
    });

    group.finish();
}

fn benchmark_hash_vs_array_100k(c: &mut Criterion) {
    let df_model_points = match load_model_points_100k() {
        Ok(df) => df,
        Err(e) => {
            eprintln!("Failed to load model points: {}", e);
            return;
        }
    };

    let age_col = df_model_points.column("age-last").unwrap().as_series().unwrap();
    let gender_col = df_model_points.column("gender_smoking").unwrap().as_series().unwrap();
    let keys: Vec<&Series> = vec![age_col, gender_col];

    let mut group = c.benchmark_group("hash_vs_array_100k");
    group.sample_size(20); // Reduce sample size for long benchmarks

    // Hash storage
    let hash_table = create_mortality_table_with_mode(StorageMode::Hash).unwrap();
    group.bench_function("hash_lookup_100k", |b| {
        b.iter(|| {
            let result = hash_table.lookup_series(black_box(&keys));
            black_box(result)
        })
    });

    // Array storage
    let array_table = create_mortality_table_with_mode(StorageMode::Array).unwrap();
    group.bench_function("array_lookup_100k", |b| {
        b.iter(|| {
            let result = array_table.lookup_series(black_box(&keys));
            black_box(result)
        })
    });

    group.finish();
}

// Parameterized benchmark with scaling
fn benchmark_scaling(c: &mut Criterion) {
    let mut group = c.benchmark_group("lookup_scaling");

    for size in [1_000, 10_000, 100_000].iter() {
        // Load or create appropriately sized model points
        let df = if *size <= 1_000 {
            load_model_points_1k().unwrap()
        } else {
            load_model_points_100k().unwrap().head(Some(*size))
        };

        let age_col = df.column("age-last").unwrap().as_series().unwrap();
        let gender_col = df.column("gender_smoking").unwrap().as_series().unwrap();
        let keys: Vec<&Series> = vec![age_col, gender_col];

        let hash_table = create_mortality_table_with_mode(StorageMode::Hash).unwrap();
        let array_table = create_mortality_table_with_mode(StorageMode::Array).unwrap();

        group.bench_with_input(
            BenchmarkId::new("hash", size),
            size,
            |b, _| {
                b.iter(|| hash_table.lookup_series(black_box(&keys)))
            },
        );

        group.bench_with_input(
            BenchmarkId::new("array", size),
            size,
            |b, _| {
                b.iter(|| array_table.lookup_series(black_box(&keys)))
            },
        );
    }

    group.finish();
}

criterion_group!(
    benches,
    benchmark_assumption_table_lookup_1k,
    benchmark_assumption_table_vector_lookup_1k,
    benchmark_hash_vs_array_1k,
    benchmark_hash_vs_array_100k,
    benchmark_scaling,
);
criterion_main!(benches);
```

**Step 2: Run benchmarks**

Run: `cd ~/Projects/gaspatchio/gaspatchio-core/core && cargo bench`

Expected: Benchmark output showing hash vs array comparison

**Step 3: Commit**

```bash
git add core/benches/assumption_table_lookup_benchmark.rs
git commit -m "bench(assumptions): add hash vs array comparison benchmarks

- benchmark_hash_vs_array_1k: Direct comparison with 1k rows
- benchmark_hash_vs_array_100k: Direct comparison with 100k rows
- benchmark_scaling: Parameterized scaling test
- Same inputs for both backends for fair comparison"
```

---

## Task 7: Update Registry for StorageMode Support

**Files:**
- Modify: `core/src/assumptions/registry.rs`
- Modify: `core/src/assumptions/mod.rs`

**Step 1: Add mode-aware registration functions**

Add to `core/src/assumptions/registry.rs`:

```rust
use crate::assumptions::table::StorageMode;

/// Register a table with explicit storage mode.
pub fn register_assumption_table_global_with_mode(
    name: String,
    df: DataFrame,
    keys: Vec<String>,
    value: String,
    mode: StorageMode,
) -> PolarsResult<()> {
    let table = AssumptionTable::build_with_mode(df, keys, value, mode)?;

    let _lock = REGISTRY_MUTEX.lock().unwrap();
    let current = GLOBAL_REGISTRY.load();

    if current.assumption_tables.contains_key(&name) {
        return Err(polars_err!(
            ComputeError: "Table '{}' already exists. Use register_or_replace for idempotent registration.",
            name
        ));
    }

    let mut new_tables = current.assumption_tables.clone();
    new_tables.insert(name, Arc::new(table));

    GLOBAL_REGISTRY.store(Arc::new(AssumptionTableRegistry {
        assumption_tables: new_tables,
    }));

    Ok(())
}

/// Register or replace a table with explicit storage mode.
pub fn register_or_replace_assumption_table_global_with_mode(
    name: String,
    df: DataFrame,
    keys: Vec<String>,
    value: String,
    force_replace: bool,
    mode: StorageMode,
) -> PolarsResult<()> {
    let table = AssumptionTable::build_with_mode(df, keys, value, mode)?;

    let _lock = REGISTRY_MUTEX.lock().unwrap();
    let current = GLOBAL_REGISTRY.load();

    if current.assumption_tables.contains_key(&name) && !force_replace {
        return Err(polars_err!(
            ComputeError: "Table '{}' already exists and force_replace=false",
            name
        ));
    }

    let mut new_tables = current.assumption_tables.clone();
    new_tables.insert(name, Arc::new(table));

    GLOBAL_REGISTRY.store(Arc::new(AssumptionTableRegistry {
        assumption_tables: new_tables,
    }));

    Ok(())
}
```

**Step 2: Export new functions in mod.rs**

Update `core/src/assumptions/mod.rs`:

```rust
pub use registry::{
    register_assumption_table_global,
    register_assumption_table_global_with_mode,  // NEW
    register_or_replace_assumption_table_global,
    register_or_replace_assumption_table_global_with_mode,  // NEW
    // ... existing exports ...
};
```

**Step 3: Run tests**

Run: `cd ~/Projects/gaspatchio/gaspatchio-core/core && cargo test`

Expected: All tests pass

**Step 4: Commit**

```bash
git add core/src/assumptions/registry.rs core/src/assumptions/mod.rs
git commit -m "feat(assumptions): add mode-aware registry functions

- register_assumption_table_global_with_mode()
- register_or_replace_assumption_table_global_with_mode()
- Enables Python control of storage backend"
```

---

## Task 8: Integration Tests

**Files:**
- Add: `core/tests/assumption_storage_integration.rs`

**Step 1: Create integration test file**

Create `core/tests/assumption_storage_integration.rs`:

```rust
// ABOUTME: Integration tests for assumption table storage backends.
// ABOUTME: Verifies hash and array storage produce identical results.

use gaspatchio_core_lib::assumptions::table::{AssumptionTable, StorageMode};
use polars::prelude::*;

fn create_test_df() -> PolarsResult<DataFrame> {
    df! {
        "age" => [30i64, 30, 31, 31, 32, 32, 33, 33],
        "gender" => ["M", "F", "M", "F", "M", "F", "M", "F"],
        "rate" => [0.001, 0.0008, 0.0012, 0.001, 0.0014, 0.0012, 0.0016, 0.0014]
    }
}

#[test]
fn test_hash_and_array_produce_same_results() -> PolarsResult<()> {
    let df = create_test_df()?;

    let hash_table = AssumptionTable::build_with_mode(
        df.clone(),
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Hash,
    )?;

    let array_table = AssumptionTable::build_with_mode(
        df,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Array,
    )?;

    // Verify storage modes
    assert!(!hash_table.is_array_storage());
    assert!(array_table.is_array_storage());

    // Test with various inputs
    let ages = Series::new("age".into(), &[30i64, 31, 32, 33, 99]);
    let genders = Series::new("gender".into(), &["M", "F", "M", "F", "X"]);

    let hash_result = hash_table.lookup_series(&[&ages, &genders])?;
    let array_result = array_table.lookup_series(&[&ages, &genders])?;

    // Results should be identical (including NaN positions)
    let hash_vals: Vec<f64> = hash_result.f64()?.into_iter().map(|v| v.unwrap_or(f64::NAN)).collect();
    let array_vals: Vec<f64> = array_result.f64()?.into_iter().map(|v| v.unwrap_or(f64::NAN)).collect();

    for (h, a) in hash_vals.iter().zip(array_vals.iter()) {
        if h.is_nan() {
            assert!(a.is_nan(), "Both should be NaN");
        } else {
            assert!((h - a).abs() < 1e-15, "Values should match: {} vs {}", h, a);
        }
    }

    Ok(())
}

#[test]
fn test_auto_mode_chooses_array_for_dense_tables() -> PolarsResult<()> {
    // Dense table: 8 rows for 4*2=8 combinations = 100% density
    let df = create_test_df()?;

    let table = AssumptionTable::build_with_mode(
        df,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Auto,
    )?;

    assert!(table.is_array_storage(), "Auto should choose array for dense table");

    Ok(())
}

#[test]
fn test_auto_mode_chooses_hash_for_sparse_tables() -> PolarsResult<()> {
    // Sparse table: 2 rows for 100*100=10000 combinations = 0.02% density
    let df = df! {
        "key1" => [0i64, 99],
        "key2" => [0i64, 99],
        "value" => [1.0, 2.0]
    }?;

    let table = AssumptionTable::build_with_mode(
        df,
        vec!["key1".to_string(), "key2".to_string()],
        "value".to_string(),
        StorageMode::Auto,
    )?;

    assert!(!table.is_array_storage(), "Auto should choose hash for sparse table");

    Ok(())
}

#[test]
fn test_force_hash_mode() -> PolarsResult<()> {
    let df = create_test_df()?;

    let table = AssumptionTable::build_with_mode(
        df,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Hash,
    )?;

    assert!(!table.is_array_storage(), "Hash mode should force hash storage");

    Ok(())
}
```

**Step 2: Run integration tests**

Run: `cd ~/Projects/gaspatchio/gaspatchio-core/core && cargo test --test assumption_storage_integration`

Expected: All 4 tests pass

**Step 3: Commit**

```bash
git add core/tests/assumption_storage_integration.rs
git commit -m "test(assumptions): add storage backend integration tests

- Verify hash and array produce identical results
- Test auto-detection for dense vs sparse tables
- Test force hash mode override"
```

---

## Task 9: Documentation and Cleanup

**Files:**
- Update: `core/src/assumptions/mod.rs` (doc comments)
- Update: `ref/29-lookup-performance/29-lookup-performance-rfc.md` (status update)

**Step 1: Add module documentation**

Update `core/src/assumptions/mod.rs`:

```rust
//! Assumption table storage and lookup functionality.
//!
//! This module provides high-performance assumption table storage with two backends:
//!
//! - **Hash Storage**: Uses AHashMap for O(1) average-case lookups. Best for sparse tables.
//! - **Array Storage**: Uses multi-dimensional arrays with dictionary-encoded keys.
//!   Provides ~3-5x faster lookups for dense tables.
//!
//! # Storage Mode Selection
//!
//! By default (`StorageMode::Auto`), the system automatically chooses:
//! - Array storage for tables with >30% density
//! - Hash storage for sparse tables or large dimensions
//!
//! You can force a specific mode via `AssumptionTable::build_with_mode()`.
//!
//! # Example
//!
//! ```rust,ignore
//! use gaspatchio_core_lib::assumptions::{AssumptionTable, StorageMode};
//!
//! // Auto-select storage
//! let table = AssumptionTable::build(df, keys, value)?;
//!
//! // Force array storage
//! let table = AssumptionTable::build_with_mode(df, keys, value, StorageMode::Array)?;
//! ```

mod array_storage;
mod hash_storage;
mod key_encoder;
mod registry;
mod table;

pub use array_storage::ArrayStorage;
pub use hash_storage::{ColumnCodec, HashStorage};
pub use key_encoder::KeyEncoder;
pub use registry::{
    // ... exports ...
};
pub use table::{AssumptionTable, StorageMode, TableStorage};
```

**Step 2: Update RFC status**

Update `ref/29-lookup-performance/29-lookup-performance-rfc.md`:

Change status from "Draft" to "Implementing" and add implementation notes.

**Step 3: Run full test suite**

Run: `cd ~/Projects/gaspatchio/gaspatchio-core/core && cargo test && cargo clippy && cargo fmt --check`

Expected: All pass

**Step 4: Final commit**

```bash
git add .
git commit -m "docs(assumptions): add module documentation and update RFC status

Strategy 5 (Multi-Dimensional Array Storage) implemented:
- ArrayStorage with dictionary-encoded keys
- KeyEncoder for IntRange, Dictionary, Categorical
- StorageMode enum (Auto/Hash/Array)
- Python control via storage_mode parameter
- Comprehensive benchmarks for comparison"
```

---

## Summary

**Total Tasks:** 9
**Estimated Time:** 4-6 hours
**Key Files Changed:**
- `core/src/assumptions/hash_storage.rs` (NEW)
- `core/src/assumptions/array_storage.rs` (NEW)
- `core/src/assumptions/key_encoder.rs` (NEW)
- `core/src/assumptions/table.rs` (REFACTORED)
- `core/src/assumptions/mod.rs` (UPDATED)
- `core/src/assumptions/registry.rs` (UPDATED)
- `bindings/python/src/assumptions.rs` (UPDATED)
- `bindings/python/gaspatchio_core/assumptions/_api.py` (UPDATED)
- `core/benches/assumption_table_lookup_benchmark.rs` (UPDATED)
- `core/tests/assumption_storage_integration.rs` (NEW)

**Expected Outcomes:**
- 3-5x faster lookups for dense tables
- Zero breaking changes - existing code works unchanged
- Python control via `storage_mode="hash"|"array"|"auto"`
- Side-by-side benchmark comparison
- Foundation for GPU acceleration (Strategy 6)
