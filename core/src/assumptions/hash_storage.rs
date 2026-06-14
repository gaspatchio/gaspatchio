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
    pub fn encode(&self, av: AnyValue) -> u64 {
        match (self, av) {
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
                // SAFETY: idx is bounded by out.len() == key_cols[0].len() == key_cols[1].len()
                // (length parity verified above). Series::get_unchecked is measurably faster
                // (~15%) than Series::get on this hot lookup path.
                let av1 = unsafe { key_cols[0].get_unchecked(idx) };
                let av2 = unsafe { key_cols[1].get_unchecked(idx) };
                let hash1 = self.codecs[0].encode(av1);
                let hash2 = self.codecs[1].encode(av2);
                hash1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ hash2
            } else {
                let mut h = AHasher::default();
                for (codec, series) in self.codecs.iter().zip(key_cols) {
                    // SAFETY: idx is bounded by out.len() == series.len() (length parity above).
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

                    // SAFETY: global_idx < end_idx <= len == series1.len() == series2.len()
                    // (verified by the early-break above). Series::get_unchecked is measurably
                    // faster than Series::get on this 1024-row chunked hot path.
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
