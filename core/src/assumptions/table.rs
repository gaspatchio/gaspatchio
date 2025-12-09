// ABOUTME: AssumptionTable with pluggable storage backends (hash or array).
// ABOUTME: Provides unified lookup interface with Python-controlled storage mode.

use crate::assumptions::array_storage::ArrayStorage;
use crate::assumptions::hash_storage::{ColumnCodec, HashStorage};
use ahash::{AHashMap, AHasher};
use log::debug;
use polars::prelude::*;
use std::hash::Hasher;
use std::str::FromStr;

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

impl FromStr for StorageMode {
    type Err = PolarsError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_lowercase().as_str() {
            "hash" => Ok(StorageMode::Hash),
            "array" => Ok(StorageMode::Array),
            "auto" => Ok(StorageMode::Auto),
            _ => Err(
                polars_err!(ComputeError: "Invalid storage mode: '{}'. Use 'hash', 'array', or 'auto'", s),
            ),
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

#[derive(Debug)]
pub struct AssumptionTable {
    keys: Vec<String>,
    storage: TableStorage,
    storage_mode_used: StorageMode,
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

    /// Build a new table by combining an existing table with new DataFrame data.
    /// Uses immutable rebuild approach for optimal lookup performance.
    /// Note: This always uses hash storage since it requires append support.
    pub fn build_combined(
        existing: &AssumptionTable,
        new_df: DataFrame,
        keys: Vec<String>,
        value: String,
    ) -> PolarsResult<Self> {
        // Validate compatibility with existing table
        if existing.keys.len() != keys.len() {
            return Err(polars_err!(
                ComputeError:
                "Key count mismatch: existing table has {} keys, new data has {} keys",
                existing.keys.len(), keys.len()
            ));
        }

        for (i, (existing_key, new_key)) in existing.keys.iter().zip(&keys).enumerate() {
            if existing_key != new_key {
                return Err(polars_err!(
                    ComputeError:
                    "Key name mismatch at position {}: existing table has '{}', new data has '{}'",
                    i, existing_key, new_key
                ));
            }
        }

        // If existing table is using array storage, error out with helpful message
        // This is a temporary limitation until we support array storage append
        let existing_hash = match &existing.storage {
            TableStorage::Hash(h) => h,
            TableStorage::Array(_) => {
                return Err(polars_err!(ComputeError:
                    "Cannot append to table using array storage. This is a temporary limitation. \
                     Please use StorageMode::Hash when building tables that will need append operations."));
            }
        };

        let existing_codecs = existing_hash.codecs();

        // Validate codecs compatibility by checking column types
        for (i, key_name) in keys.iter().enumerate() {
            let new_series = new_df.column(key_name)?;
            let new_codec = match new_series.dtype() {
                DataType::String => ColumnCodec::String,
                DataType::Float64 => ColumnCodec::Float64,
                _ => ColumnCodec::Integer,
            };

            // Compare with existing codec
            if !Self::codecs_compatible(&existing_codecs[i], &new_codec) {
                return Err(polars_err!(
                    ComputeError:
                    "Codec mismatch for key '{}': existing type {:?}, new type {:?}",
                    key_name, existing_codecs[i], new_codec
                ));
            }
        }

        // Clone existing map as base (AHashMap clone is efficient)
        let mut combined_map = existing_hash.map.clone();

        // Build new entries from DataFrame
        let new_entries = Self::build_entries_map(&new_df, &keys, &value, existing_codecs)?;

        // Validate no duplicate keys before extending
        for key in new_entries.keys() {
            if combined_map.contains_key(key) {
                return Err(polars_err!(
                    ComputeError:
                    "Duplicate key found during append. Cannot append data with existing key combinations."
                ));
            }
        }

        // Extend with new entries
        combined_map.extend(new_entries);

        // Create new hash storage with combined map
        let combined_storage = HashStorage {
            codecs: existing_codecs.to_vec(),
            map: combined_map,
        };

        Ok(Self {
            keys: existing.keys.clone(),
            storage: TableStorage::Hash(combined_storage),
            storage_mode_used: StorageMode::Hash,
        })
    }

    /// Build hashmap entries from DataFrame using existing codec logic
    fn build_entries_map(
        df: &DataFrame,
        keys: &[String],
        value: &str,
        codecs: &[ColumnCodec],
    ) -> PolarsResult<AHashMap<u64, f64>> {
        let n_rows = df.height();
        let mut map: AHashMap<u64, f64> = AHashMap::with_capacity(n_rows.next_power_of_two());

        let value_series = df.column(value)?.f64()?;

        for row_idx in 0..n_rows {
            let hash = if codecs.len() == 2 {
                // Fast path for 2-key case (same as build method)
                let av1 = df.column(&keys[0])?.get(row_idx)?;
                let av2 = df.column(&keys[1])?.get(row_idx)?;
                let hash1 = codecs[0].encode(av1);
                let hash2 = codecs[1].encode(av2);
                hash1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ hash2
            } else {
                // General case (same as build method)
                let mut h = AHasher::default();
                for (codec, key_name) in codecs.iter().zip(keys) {
                    let av = df.column(key_name)?.get(row_idx)?;
                    h.write_u64(codec.encode(av));
                }
                h.finish()
            };
            let v = value_series.get(row_idx).unwrap_or(f64::NAN);
            map.insert(hash, v);
        }

        Ok(map)
    }

    /// Check if two codecs are compatible for append operations
    fn codecs_compatible(existing: &ColumnCodec, new: &ColumnCodec) -> bool {
        match (existing, new) {
            (ColumnCodec::String, ColumnCodec::String) => true,
            (ColumnCodec::Float64, ColumnCodec::Float64) => true,
            (ColumnCodec::Integer, ColumnCodec::Integer) => true,
            // Allow integer to float promotion for flexibility
            (ColumnCodec::Float64, ColumnCodec::Integer) => true,
            (ColumnCodec::Integer, ColumnCodec::Float64) => true,
            _ => false,
        }
    }

    pub fn lookup_series(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        // Validate input lengths
        if key_cols.len() != self.keys.len() {
            return Err(polars_err!(ShapeMismatch: "wrong # key columns"));
        }

        // Fast path: Quick check for scalar-only inputs (most common case)
        if key_cols
            .iter()
            .all(|s| !matches!(s.dtype(), DataType::List(_)))
        {
            return self.storage.lookup_scalar(key_cols);
        }

        // Vector path: Full analysis when lists are present
        // For now, vector lookups always use hash storage fallback
        self.lookup_vector_fallback(key_cols)
    }

    /// Fallback for vector lookups - uses hash-based logic internally
    fn lookup_vector_fallback(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        let (any_vectors, vector_len, vector_indices) = self.analyze_inputs(key_cols)?;

        if any_vectors {
            self.lookup_vector(key_cols, vector_len.unwrap(), &vector_indices)
        } else {
            self.storage.lookup_scalar(key_cols)
        }
    }

    fn analyze_inputs(
        &self,
        key_cols: &[&Series],
    ) -> PolarsResult<(bool, Option<usize>, Vec<usize>)> {
        let mut any_vectors = false;
        let mut vector_len = None;
        let mut vector_indices = Vec::new();

        for (i, series) in key_cols.iter().enumerate() {
            if matches!(series.dtype(), DataType::List(_)) {
                any_vectors = true;
                vector_indices.push(i);
                let current_len = series.len();

                // Validate all vector columns have same length
                if let Some(expected_len) = vector_len {
                    if current_len != expected_len {
                        return Err(polars_err!(ShapeMismatch:
                            "Vector length mismatch: expected {}, got {} for column {}",
                            expected_len, current_len, i
                        ));
                    }
                } else {
                    vector_len = Some(current_len);
                }
            } else if any_vectors {
                // Scalar column in presence of vectors - validate broadcasting compatibility
                let scalar_len = series.len();
                let vec_len = vector_len.unwrap();
                if !(scalar_len == 1 || scalar_len == vec_len) {
                    return Err(polars_err!(ShapeMismatch:
                        "Scalar column {} has length {} but expected 1 or {} for broadcasting",
                        i, scalar_len, vec_len
                    ));
                }
            }
        }

        Ok((any_vectors, vector_len, vector_indices))
    }

    fn lookup_vector(
        &self,
        key_cols: &[&Series],
        vector_len: usize,
        vector_indices: &[usize],
    ) -> PolarsResult<Series> {
        // For vector lookups, we need hash storage's codec logic
        // This is a temporary limitation - we could optimize this in the future
        let codecs = match &self.storage {
            TableStorage::Hash(h) => h.codecs(),
            TableStorage::Array(_) => {
                // If we're using array storage, we need to fall back to hash-style lookup for vectors
                // This is acceptable as vector lookups are less common
                return Err(
                    polars_err!(ComputeError: "Vector lookups with array storage not yet implemented"),
                );
            }
        };

        debug!(
            "lookup_vector: vector_len={}, vector_indices={:?}",
            vector_len, vector_indices
        );

        // Pre-allocate result vector of Lists
        let mut out_lists = Vec::with_capacity(vector_len);

        // For each outer row, look up all inner vector elements
        for outer_idx in 0..vector_len {
            // First, determine the inner vector length by examining all vector columns
            let inner_len = self.compute_inner_len(key_cols, outer_idx, vector_indices)?;

            let mut inner_vals = vec![f64::NAN; inner_len];

            // For each inner element, look up the value
            #[allow(clippy::needless_range_loop)]
            for inner_idx in 0..inner_len {
                // Build the hash key for this specific inner element
                let key = if codecs.len() == 2 {
                    // Fast path for 2 keys
                    let av1 =
                        self.get_value_at(key_cols, 0, outer_idx, inner_idx, vector_indices)?;
                    let av2 =
                        self.get_value_at(key_cols, 1, outer_idx, inner_idx, vector_indices)?;
                    let hash1 = codecs[0].encode(av1);
                    let hash2 = codecs[1].encode(av2);
                    hash1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ hash2
                } else {
                    // General case
                    let mut h = AHasher::default();
                    for (key_idx, codec) in codecs.iter().enumerate() {
                        let av = self.get_value_at(
                            key_cols,
                            key_idx,
                            outer_idx,
                            inner_idx,
                            vector_indices,
                        )?;
                        h.write_u64(codec.encode(av));
                    }
                    h.finish()
                };

                // Look up in hash map
                if let TableStorage::Hash(h) = &self.storage {
                    if let Some(v) = h.map.get(&key) {
                        inner_vals[inner_idx] = *v;
                    }
                }
            }

            // Convert inner values to Series
            let inner_series = Series::from_vec("inner".into(), inner_vals);
            out_lists.push(inner_series);
        }

        // Convert list of Series to ListChunked
        let list_chunked: ListChunked = out_lists.into_iter().collect();

        Ok(list_chunked.into_series())
    }

    /// Compute the length of the inner vector at a given outer index.
    fn compute_inner_len(
        &self,
        key_cols: &[&Series],
        outer_idx: usize,
        vector_indices: &[usize],
    ) -> PolarsResult<usize> {
        // Check the first vector column for the inner length
        let first_vec_idx = vector_indices[0];
        let list_series = key_cols[first_vec_idx];

        let list_chunked = list_series.list()?;
        match list_chunked.get_any_value(outer_idx)? {
            AnyValue::List(inner_series) => Ok(inner_series.len()),
            AnyValue::Null => Ok(0),
            _ => Err(polars_err!(ComputeError: "Expected List type in compute_inner_len")),
        }
    }

    /// Get the value at the specified position, handling both scalar and vector columns.
    fn get_value_at(
        &self,
        key_cols: &[&Series],
        key_idx: usize,
        outer_idx: usize,
        inner_idx: usize,
        vector_indices: &[usize],
    ) -> PolarsResult<AnyValue<'_>> {
        let series = key_cols[key_idx];

        // Check if this column is a vector
        if vector_indices.contains(&key_idx) {
            // Vector column - access inner element
            let list_chunked = series.list()?;
            match list_chunked.get_any_value(outer_idx)? {
                AnyValue::List(inner_series) => {
                    if inner_idx < inner_series.len() {
                        Ok(inner_series.get(inner_idx)?.into_static())
                    } else {
                        Ok(AnyValue::Null)
                    }
                }
                AnyValue::Null => Ok(AnyValue::Null),
                _ => Err(polars_err!(ComputeError: "Expected List type in get_value_at")),
            }
        } else {
            // Scalar column - handle broadcasting
            let scalar_len = series.len();
            let actual_idx = if scalar_len == 1 { 0 } else { outer_idx };
            Ok(series.get(actual_idx)?.into_static())
        }
    }

    // Metadata methods
    pub fn get_key_count(&self) -> usize {
        self.keys.len()
    }

    pub fn get_key_name(&self, index: usize) -> PolarsResult<&str> {
        self.keys
            .get(index)
            .map(|s| s.as_str())
            .ok_or_else(|| polars_err!(ComputeError: "Key index {} out of bounds", index))
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

#[cfg(test)]
mod tests {
    use super::*;
    use polars::df;

    #[test]
    fn test_build_with_auto_mode() -> PolarsResult<()> {
        let df = df! {
            "age" => [30i64, 30, 31, 31, 32, 32],
            "gender" => ["M", "F", "M", "F", "M", "F"],
            "rate" => [0.001, 0.0008, 0.0012, 0.001, 0.0014, 0.0012]
        }?;

        let table = AssumptionTable::build(
            df,
            vec!["age".to_string(), "gender".to_string()],
            "rate".to_string(),
        )?;

        // With high density, should choose array storage
        assert!(table.is_array_storage());
        assert_eq!(table.storage_mode(), StorageMode::Array);

        Ok(())
    }

    #[test]
    fn test_force_hash_mode() -> PolarsResult<()> {
        let df = df! {
            "age" => [30i64, 30, 31, 31, 32, 32],
            "gender" => ["M", "F", "M", "F", "M", "F"],
            "rate" => [0.001, 0.0008, 0.0012, 0.001, 0.0014, 0.0012]
        }?;

        let table = AssumptionTable::build_with_mode(
            df,
            vec!["age".to_string(), "gender".to_string()],
            "rate".to_string(),
            StorageMode::Hash,
        )?;

        assert!(!table.is_array_storage());
        assert_eq!(table.storage_mode(), StorageMode::Hash);

        Ok(())
    }

    #[test]
    fn test_lookup_works_with_both_storage_modes() -> PolarsResult<()> {
        let df = df! {
            "age" => [30i64, 30, 31, 31],
            "gender" => ["M", "F", "M", "F"],
            "rate" => [0.001, 0.0008, 0.0012, 0.001]
        }?;

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

        // Test lookup
        let ages = Series::new("age".into(), &[30i64, 31, 99]);
        let genders = Series::new("gender".into(), &["M", "F", "X"]);

        let hash_result = hash_table.lookup_series(&[&ages, &genders])?;
        let array_result = array_table.lookup_series(&[&ages, &genders])?;

        // Results should be identical
        let hash_vals: Vec<f64> = hash_result
            .f64()?
            .into_iter()
            .map(|v| v.unwrap_or(f64::NAN))
            .collect();
        let array_vals: Vec<f64> = array_result
            .f64()?
            .into_iter()
            .map(|v| v.unwrap_or(f64::NAN))
            .collect();

        for (h, a) in hash_vals.iter().zip(array_vals.iter()) {
            if h.is_nan() {
                assert!(a.is_nan());
            } else {
                assert!((h - a).abs() < 1e-15);
            }
        }

        Ok(())
    }

    #[test]
    fn test_storage_mode_from_str() -> PolarsResult<()> {
        assert_eq!(StorageMode::from_str("hash")?, StorageMode::Hash);
        assert_eq!(StorageMode::from_str("array")?, StorageMode::Array);
        assert_eq!(StorageMode::from_str("auto")?, StorageMode::Auto);
        assert_eq!(StorageMode::from_str("HASH")?, StorageMode::Hash); // case insensitive

        assert!(StorageMode::from_str("invalid").is_err());

        Ok(())
    }
}
