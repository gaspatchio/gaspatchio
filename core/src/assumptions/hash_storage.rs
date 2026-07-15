// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

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
    pub fn encode(&self, av: AnyValue) -> Option<u64> {
        // Null and unhandled dtype/codec combinations are a miss (None), not
        // a silent 0u64 that aliases to key 0's hash and returns key 0's rate.
        if matches!(av, AnyValue::Null) {
            return None;
        }
        let hash = match (self, av) {
            // String encoding - handle special cases first (categorical indices)
            (ColumnCodec::String, AnyValue::Categorical(idx, _)) => u64::from(idx),
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
            // Narrow integers widen to the same hash as their i64 value
            (ColumnCodec::Integer | ColumnCodec::Float64, AnyValue::Int8(i)) => i as u64,
            (ColumnCodec::Integer | ColumnCodec::Float64, AnyValue::Int16(i)) => i as u64,
            (ColumnCodec::Integer | ColumnCodec::Float64, AnyValue::UInt8(u)) => u as u64,
            (ColumnCodec::Integer | ColumnCodec::Float64, AnyValue::UInt16(u)) => u as u64,
            (ColumnCodec::String, AnyValue::Int8(i)) => Self::hash_int_as_string(i as i64),
            (ColumnCodec::String, AnyValue::Int16(i)) => Self::hash_int_as_string(i as i64),
            (ColumnCodec::String, AnyValue::UInt8(u)) => Self::hash_int_as_string(u as i64),
            (ColumnCodec::String, AnyValue::UInt16(u)) => Self::hash_int_as_string(u as i64),
            _ => return None,
        };
        Some(hash)
    }

    #[inline]
    fn hash_int_as_string(i: i64) -> u64 {
        let s = i.to_string();
        let mut hasher = AHasher::default();
        hasher.write(s.as_bytes());
        hasher.finish()
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
    pub fn build(df: &DataFrame, keys: &[String], value: &str) -> PolarsResult<Self> {
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
        // Transient build-time index: first source row per hash, so a hash
        // conflict can be verified against the actual key values rather than
        // misreported (a 64-bit collision between distinct keys is
        // astronomically rare but must not be called a duplicate).
        let mut first_row_for_hash: AHashMap<u64, usize> =
            AHashMap::with_capacity(n_rows.next_power_of_two());
        let value_series = df.column(value)?.f64()?;

        for row_idx in 0..n_rows {
            let hash = Self::compute_hash_for_row(df, keys, &codecs, row_idx)?;
            let v = value_series.get(row_idx).unwrap_or(f64::NAN);
            if let Some(&prev_row) = first_row_for_hash.get(&hash) {
                let is_true_duplicate = keys.iter().all(|key_name| {
                    let col = df.column(key_name);
                    match col {
                        Ok(c) => match (c.get(prev_row), c.get(row_idx)) {
                            (Ok(a), Ok(b)) => a == b,
                            _ => false,
                        },
                        Err(_) => false,
                    }
                });
                if is_true_duplicate {
                    return Err(polars_err!(ComputeError:
                        "Duplicate key combination at source row {} while building table (same keys as row {}). Deduplicate the source or fix the dimension mapping.",
                        row_idx, prev_row));
                }
                return Err(polars_err!(ComputeError:
                    "64-bit key-hash collision between distinct source rows {} and {} while building table; use storage_mode=\"array\" for this table.",
                    prev_row, row_idx));
            }
            first_row_for_hash.insert(hash, row_idx);
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
            let hash1 = codecs[0].encode(av1).ok_or_else(|| polars_err!(ComputeError:
                "null or unencodable key value in column '{}' at source row {} while building table",
                keys[0], row_idx))?;
            let hash2 = codecs[1].encode(av2).ok_or_else(|| polars_err!(ComputeError:
                "null or unencodable key value in column '{}' at source row {} while building table",
                keys[1], row_idx))?;
            Ok(hash1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ hash2)
        } else {
            let mut h = AHasher::default();
            for (codec, key_name) in codecs.iter().zip(keys) {
                let av = df.column(key_name)?.get(row_idx)?;
                let part = codec.encode(av).ok_or_else(|| polars_err!(ComputeError:
                    "null or unencodable key value in column '{}' at source row {} while building table",
                    key_name, row_idx))?;
                h.write_u64(part);
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
                // SAFETY: idx is bounded by out.len() == key_cols[0].len() == key_cols[1].len()
                // (length parity verified above). Series::get_unchecked is measurably faster
                // (~15%) than Series::get on this hot lookup path.
                let av1 = unsafe { key_cols[0].get_unchecked(idx) };
                let av2 = unsafe { key_cols[1].get_unchecked(idx) };
                match (self.codecs[0].encode(av1), self.codecs[1].encode(av2)) {
                    (Some(h1), Some(h2)) => {
                        Some(h1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ h2)
                    }
                    _ => None,
                }
            } else {
                let mut h = AHasher::default();
                let mut valid = true;
                for (codec, series) in self.codecs.iter().zip(key_cols) {
                    // SAFETY: idx is bounded by out.len() == series.len() (length parity above).
                    let av = unsafe { series.get_unchecked(idx) };
                    match codec.encode(av) {
                        Some(part) => h.write_u64(part),
                        None => {
                            valid = false;
                            break;
                        }
                    }
                }
                valid.then(|| h.finish())
            };
            if let Some(v) = key.and_then(|k| self.map.get(&k)) {
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

                    // SAFETY: global_idx < end_idx <= len == series1.len() == series2.len()
                    // (verified by the early-break above). Series::get_unchecked is measurably
                    // faster than Series::get on this 1024-row chunked hot path.
                    let av1 = unsafe { series1.get_unchecked(global_idx) };
                    let av2 = unsafe { series2.get_unchecked(global_idx) };

                    if let (Some(hash1), Some(hash2)) =
                        (self.codecs[0].encode(av1), self.codecs[1].encode(av2))
                    {
                        let key = hash1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ hash2;
                        if let Some(v) = self.map.get(&key) {
                            *slot = *v;
                        }
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
