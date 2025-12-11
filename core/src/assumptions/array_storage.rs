// ABOUTME: Multi-dimensional array storage for assumption tables.
// ABOUTME: Uses dictionary-encoded keys for O(1) array indexing instead of hash lookups.

use crate::assumptions::key_encoder::KeyEncoder;
use ahash::AHashMap;
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
}

impl ArrayStorage {
    /// Build array storage from DataFrame.
    /// Returns None if table is too sparse (< 30% density).
    /// If string_mappings is provided, creates CategoricalWithStringFallback encoders
    /// for columns that have mappings, enabling transparent string lookup.
    pub fn build(
        df: &DataFrame,
        keys: &[String],
        value: &str,
    ) -> PolarsResult<Option<Self>> {
        Self::build_with_mappings(df, keys, value, None)
    }

    /// Build array storage with optional string mappings for transparent string lookup.
    pub fn build_with_mappings(
        df: &DataFrame,
        keys: &[String],
        value: &str,
        string_mappings: Option<&AHashMap<String, AHashMap<String, u32>>>,
    ) -> PolarsResult<Option<Self>> {
        let n_rows = df.height();

        // Build encoders for each key column
        let mut encoders = Vec::with_capacity(keys.len());
        for key_name in keys {
            let column = df.column(key_name)?;

            // If we have a string mapping for this column, create a hybrid encoder
            // that can handle both categorical and string input
            if let Some(mappings) = string_mappings {
                if let Some(mapping) = mappings.get(key_name) {
                    let encoder = KeyEncoder::categorical_with_string_fallback(mapping.clone());
                    encoders.push(encoder);
                    continue;
                }
            }

            // Default: create encoder from column type
            let encoder = KeyEncoder::from_column(column)?;
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
            dims,
            capacity,
            density * 100.0,
            memory_bytes / 1024
        );

        Ok(Some(Self {
            encoders,
            strides,
            data,
        }))
    }

    /// Lookup values for scalar key columns.
    /// Uses pre-encoded indices for maximum performance.
    pub fn lookup_scalar(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        let len = key_cols[0].len();

        // Validate all series have same length
        for s in key_cols.iter().skip(1) {
            if s.len() != len {
                return Err(polars_err!(ShapeMismatch: "key columns not equal length"));
            }
        }

        // PRE-ENCODE all columns to indices BEFORE the parallel loop.
        // This is the key optimization - hash lookups happen here ONCE,
        // then the inner loop is pure integer arithmetic.
        let encoded_cols: Vec<Vec<u32>> = self
            .encoders
            .iter()
            .zip(key_cols.iter())
            .map(|(encoder, series)| encoder.encode_column(series))
            .collect::<PolarsResult<Vec<_>>>()?;

        let invalid = u32::MAX;
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

                    // Compute linear index from pre-encoded indices
                    // This is now PURE INTEGER ARITHMETIC - no hash lookups!
                    let mut linear_idx = 0usize;
                    let mut valid = true;

                    for (i, encoded) in encoded_cols.iter().enumerate() {
                        let idx = encoded[global_idx];
                        if idx == invalid {
                            valid = false;
                            break;
                        }
                        linear_idx += idx as usize * self.strides[i];
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

    /// Lookup values for vector key columns using batch encoding (optimized).
    /// Each outer row produces a List of lookup results.
    /// This method uses vectorized operations for dramatically faster performance.
    ///
    /// Key optimization: Encode scalars once, then expand the encoded indices (cheap u32 repeat)
    /// rather than expanding values then encoding (expensive AnyValue operations).
    pub fn lookup_vector_batch(
        &self,
        key_cols: &[&Series],
        vector_len: usize,
        vector_indices: &[usize],
    ) -> PolarsResult<Series> {
        // Step 1: Compute offsets and total flattened length from first vector column
        let (offsets, total_len) = self.compute_offsets_and_total_len(key_cols, vector_indices)?;

        // Step 2: Encode all columns, then expand to total_len
        // - Vector columns: explode first, then encode
        // - Scalar columns: encode once, then expand indices (cheap!)
        let encoded = self.encode_and_expand_columns(key_cols, &offsets, total_len, vector_indices)?;

        // Step 3: Compute linear indices vectorially
        let linear_indices = self.compute_linear_indices_batch(&encoded, total_len);

        // Step 4: Gather values from data array (parallel)
        let flat_values: Vec<f64> = linear_indices
            .par_iter()
            .map(|&idx| {
                if idx < self.data.len() {
                    self.data[idx]
                } else {
                    f64::NAN
                }
            })
            .collect();

        // Step 5: Reshape to Lists using offsets
        self.reshape_to_lists(&flat_values, &offsets, vector_len)
    }

    /// Compute offsets and total length from vector columns.
    /// Returns (offsets, total_len) where offsets[i] is the start index in the flattened array.
    fn compute_offsets_and_total_len(
        &self,
        key_cols: &[&Series],
        vector_indices: &[usize],
    ) -> PolarsResult<(Vec<i64>, usize)> {
        let first_vec_idx = vector_indices[0];
        let list_series = key_cols[first_vec_idx];
        let list_chunked = list_series.list()?;

        let offsets_buffer = list_chunked.offsets()?;
        let offsets = offsets_buffer.as_slice();
        let total_len = offsets[offsets.len() - 1] as usize;

        Ok((offsets.to_vec(), total_len))
    }

    /// Encode columns and expand to total_len.
    /// - Vector columns: explode, then encode (both at total_len)
    /// - Scalar columns: encode at outer_len, then expand indices to total_len
    fn encode_and_expand_columns(
        &self,
        key_cols: &[&Series],
        offsets: &[i64],
        total_len: usize,
        vector_indices: &[usize],
    ) -> PolarsResult<Vec<Vec<u32>>> {
        let outer_len = offsets.len() - 1;
        let mut encoded_expanded = Vec::with_capacity(key_cols.len());

        for (key_idx, series) in key_cols.iter().enumerate() {
            let encoder = &self.encoders[key_idx];

            if vector_indices.contains(&key_idx) {
                // Vector column: explode the List, then encode
                let list_chunked = series.list()?;
                let exploded = list_chunked.explode(false)?;
                let encoded = encoder.encode_column(&exploded)?;
                encoded_expanded.push(encoded);
            } else {
                // Scalar column: encode once at outer_len, then expand indices
                let scalar_len = series.len();

                // Handle broadcast case where scalar_len == 1
                let series_to_encode = if scalar_len == 1 && outer_len > 1 {
                    // Broadcast single value to outer_len using Polars new_from_index
                    series.new_from_index(0, outer_len)
                } else {
                    (*series).clone()
                };

                // Encode at outer_len (cheap - only outer_len encode operations)
                let encoded_outer = encoder.encode_column(&series_to_encode)?;

                // Expand encoded indices to total_len (cheap - just repeating u32 values)
                let mut expanded = Vec::with_capacity(total_len);
                for outer_idx in 0..outer_len {
                    let idx = encoded_outer[outer_idx];
                    let inner_len = (offsets[outer_idx + 1] - offsets[outer_idx]) as usize;
                    expanded.extend(std::iter::repeat(idx).take(inner_len));
                }
                encoded_expanded.push(expanded);
            }
        }

        Ok(encoded_expanded)
    }

    /// Compute linear indices from encoded columns using vectorized operations.
    /// linear_idx[i] = sum(encoded[k][i] * strides[k] for k in 0..n_keys)
    fn compute_linear_indices_batch(&self, encoded: &[Vec<u32>], total_len: usize) -> Vec<usize> {
        let invalid = u32::MAX;

        (0..total_len)
            .into_par_iter()
            .map(|i| {
                let mut linear_idx = 0usize;
                let mut valid = true;

                for (key_idx, encoded_col) in encoded.iter().enumerate() {
                    let idx = encoded_col[i];
                    if idx == invalid {
                        valid = false;
                        break;
                    }
                    linear_idx += idx as usize * self.strides[key_idx];
                }

                if valid {
                    linear_idx
                } else {
                    usize::MAX
                }
            })
            .collect()
    }

    /// Reshape flat values back to Lists using offsets.
    fn reshape_to_lists(
        &self,
        flat_values: &[f64],
        offsets: &[i64],
        vector_len: usize,
    ) -> PolarsResult<Series> {
        let mut out_lists = Vec::with_capacity(vector_len);

        for outer_idx in 0..vector_len {
            let start = offsets[outer_idx] as usize;
            let end = offsets[outer_idx + 1] as usize;
            let inner_vals = flat_values[start..end].to_vec();

            let inner_series = Series::from_vec("inner".into(), inner_vals);
            out_lists.push(inner_series);
        }

        let list_chunked: ListChunked = out_lists.into_iter().collect();
        Ok(list_chunked.into_series())
    }

    /// Lookup values for vector key columns (List types).
    /// Each outer row produces a List of lookup results.
    pub fn lookup_vector(
        &self,
        key_cols: &[&Series],
        vector_len: usize,
        vector_indices: &[usize],
    ) -> PolarsResult<Series> {
        // Pre-allocate result vector of Lists
        let mut out_lists = Vec::with_capacity(vector_len);

        // For each outer row, look up all inner vector elements
        for outer_idx in 0..vector_len {
            // Determine inner vector length from first vector column
            let inner_len = self.compute_inner_len(key_cols, outer_idx, vector_indices)?;

            let mut inner_vals = vec![f64::NAN; inner_len];

            // For each inner element, compute linear index and look up
            for inner_idx in 0..inner_len {
                // Compute linear index from all keys
                let mut linear_idx = 0usize;
                let mut valid = true;

                for (key_idx, encoder) in self.encoders.iter().enumerate() {
                    let av =
                        self.get_value_at(key_cols, key_idx, outer_idx, inner_idx, vector_indices)?;

                    if let Some(idx) = encoder.encode(av) {
                        linear_idx += idx as usize * self.strides[key_idx];
                    } else {
                        valid = false;
                        break;
                    }
                }

                if valid && linear_idx < self.data.len() {
                    inner_vals[inner_idx] = self.data[linear_idx];
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
    ) -> PolarsResult<AnyValue<'static>> {
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

        let storage = ArrayStorage::build(&df, &["age".to_string(), "gender".to_string()], "rate")?;

        assert!(
            storage.is_some(),
            "Should build array storage for dense table"
        );
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

        let storage = ArrayStorage::build(&df, &["age".to_string(), "gender".to_string()], "rate")?
            .expect("Should build array storage");

        // Test lookup
        let age_series = Series::new("age".into(), &[30i64, 31, 32, 99]);
        let gender_series = Series::new("gender".into(), &["F", "F", "F", "M"]);

        let result = storage.lookup_scalar(&[&age_series, &gender_series])?;

        let values: Vec<f64> = result.f64()?.into_no_null_iter().collect();
        assert!((values[0] - 0.0008).abs() < 1e-10); // age=30, gender=F
        assert!((values[1] - 0.001).abs() < 1e-10); // age=31, gender=F
        assert!((values[2] - 0.0012).abs() < 1e-10); // age=32, gender=F
        assert!(values[3].is_nan()); // age=99 - not in table

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

        let storage = ArrayStorage::build(&df, &["key1".to_string(), "key2".to_string()], "value")?;

        assert!(storage.is_none(), "Should return None for sparse table");

        Ok(())
    }

    #[test]
    fn test_lookup_timing_sanity_check() -> PolarsResult<()> {
        use std::time::Instant;

        // Build a mortality-like table: 83 ages x 4 categories = 332 entries
        let ages: Vec<i64> = (18..=100).collect();
        let mut df_rows_age = vec![];
        let mut df_rows_cat = vec![];
        let mut df_rows_rate = vec![];

        for age in &ages {
            for cat in &["MNS", "FNS", "MS", "FS"] {
                df_rows_age.push(*age);
                df_rows_cat.push(*cat);
                df_rows_rate.push(0.001 * (1.0 + *age as f64 / 100.0));
            }
        }

        let df = df! {
            "age" => df_rows_age,
            "cat" => df_rows_cat,
            "rate" => df_rows_rate
        }?;

        let storage = ArrayStorage::build(&df, &["age".to_string(), "cat".to_string()], "rate")?
            .expect("Should build array storage");

        // Create test data with 10k lookups
        let test_ages: Vec<i64> = (0..10_000).map(|i| 18 + (i % 83) as i64).collect();
        let test_cats: Vec<&str> = (0..10_000)
            .map(|i| match i % 4 {
                0 => "MNS",
                1 => "FNS",
                2 => "MS",
                _ => "FS",
            })
            .collect();

        let age_series = Series::new("age".into(), test_ages);
        let cat_series = Series::new("cat".into(), test_cats);
        let keys = vec![&age_series, &cat_series];

        // Warm up
        let _ = storage.lookup_scalar(&keys)?;

        // Timed run
        let start = Instant::now();
        let iterations = 100;
        for _ in 0..iterations {
            let result = storage.lookup_scalar(&keys)?;
            let _ = std::hint::black_box(result);
        }
        let elapsed = start.elapsed();

        let per_lookup_ns = elapsed.as_nanos() as f64 / (iterations as f64 * 10_000.0);
        eprintln!("ArrayStorage lookup timing:");
        eprintln!(
            "  10k lookups x {} iterations = {} total lookups",
            iterations,
            iterations * 10_000
        );
        eprintln!("  Total time: {:?}", elapsed);
        eprintln!("  Per lookup: {:.2}ns", per_lookup_ns);

        // Sanity check: should be at least 1ns per lookup (anything less is suspicious)
        assert!(
            per_lookup_ns > 0.1,
            "Lookup time suspiciously fast: {:.2}ns",
            per_lookup_ns
        );

        Ok(())
    }

    #[test]
    fn test_array_vs_hash_timing_comparison() -> PolarsResult<()> {
        use crate::assumptions::hash_storage::HashStorage;
        use std::time::Instant;

        // Build a mortality-like table: 83 ages x 4 categories = 332 entries
        let ages: Vec<i64> = (18..=100).collect();
        let mut df_rows_age = vec![];
        let mut df_rows_cat = vec![];
        let mut df_rows_rate = vec![];

        for age in &ages {
            for cat in &["MNS", "FNS", "MS", "FS"] {
                df_rows_age.push(*age);
                df_rows_cat.push(*cat);
                df_rows_rate.push(0.001 * (1.0 + *age as f64 / 100.0));
            }
        }

        let df = df! {
            "age" => df_rows_age,
            "cat" => df_rows_cat,
            "rate" => df_rows_rate
        }?;

        let array_storage =
            ArrayStorage::build(&df, &["age".to_string(), "cat".to_string()], "rate")?
                .expect("Should build array storage");

        let hash_storage =
            HashStorage::build(&df, &["age".to_string(), "cat".to_string()], "rate")?;

        // Create test data with 10k lookups
        let test_ages: Vec<i64> = (0..10_000).map(|i| 18 + (i % 83) as i64).collect();
        let test_cats: Vec<&str> = (0..10_000)
            .map(|i| match i % 4 {
                0 => "MNS",
                1 => "FNS",
                2 => "MS",
                _ => "FS",
            })
            .collect();

        let age_series = Series::new("age".into(), test_ages);
        let cat_series = Series::new("cat".into(), test_cats);
        let keys = vec![&age_series, &cat_series];

        // Warm up both
        let _ = array_storage.lookup_scalar(&keys)?;
        let _ = hash_storage.lookup_scalar(&keys)?;

        let iterations = 20;

        // Time array storage
        let start = Instant::now();
        for _ in 0..iterations {
            let result = array_storage.lookup_scalar(&keys)?;
            let _ = std::hint::black_box(result);
        }
        let array_elapsed = start.elapsed();

        // Time hash storage
        let start = Instant::now();
        for _ in 0..iterations {
            let result = hash_storage.lookup_scalar(&keys)?;
            let _ = std::hint::black_box(result);
        }
        let hash_elapsed = start.elapsed();

        let array_per_lookup_ns = array_elapsed.as_nanos() as f64 / (iterations as f64 * 10_000.0);
        let hash_per_lookup_ns = hash_elapsed.as_nanos() as f64 / (iterations as f64 * 10_000.0);
        let speedup = hash_elapsed.as_nanos() as f64 / array_elapsed.as_nanos() as f64;

        eprintln!(
            "\nArray vs Hash timing comparison (10k lookups x {} iterations):",
            iterations
        );
        eprintln!(
            "  Array: {:?} total, {:.2}ns per lookup",
            array_elapsed, array_per_lookup_ns
        );
        eprintln!(
            "  Hash:  {:?} total, {:.2}ns per lookup",
            hash_elapsed, hash_per_lookup_ns
        );
        eprintln!("  Speedup: {:.1}x", speedup);

        // Both should be reasonably fast (< 500ns per lookup)
        // Note: Debug mode is ~10x slower than release mode
        assert!(
            array_per_lookup_ns < 500.0,
            "Array lookup too slow: {:.2}ns",
            array_per_lookup_ns
        );
        assert!(
            hash_per_lookup_ns < 500.0,
            "Hash lookup too slow: {:.2}ns",
            hash_per_lookup_ns
        );

        Ok(())
    }

    #[test]
    fn test_vector_lookup() -> PolarsResult<()> {
        // Create a dense table: 3 ages x 2 genders = 6 entries
        let df = df! {
            "age" => [30i64, 30, 31, 31, 32, 32],
            "gender" => ["M", "F", "M", "F", "M", "F"],
            "rate" => [0.001, 0.0008, 0.0012, 0.001, 0.0014, 0.0012]
        }?;

        let storage = ArrayStorage::build(&df, &["age".to_string(), "gender".to_string()], "rate")?
            .expect("Should build array storage");

        // Create vector input: age is a List column (vector), gender is scalar
        // Two outer rows, each with a vector of ages to look up
        let age_lists = ListChunked::from_iter([
            Some(Series::new("".into(), vec![30i64, 31, 32])), // First row: look up ages 30, 31, 32
            Some(Series::new("".into(), vec![30i64, 31])),     // Second row: look up ages 30, 31
        ]);
        let age_series = age_lists.into_series();

        // Gender is scalar, broadcasts to each inner element
        let gender_series = Series::new("gender".into(), &["M", "F"]);

        // vector_indices indicates which columns are vectors (just column 0 = age)
        let vector_indices = vec![0usize];
        let vector_len = 2; // Two outer rows

        let result =
            storage.lookup_vector(&[&age_series, &gender_series], vector_len, &vector_indices)?;

        // Result should be a List of Lists
        let result_list = result.list()?;
        assert_eq!(result_list.len(), 2);

        // First row: ages [30, 31, 32] with gender "M"
        let first_inner = result_list.get_any_value(0)?;
        if let AnyValue::List(inner_series) = first_inner {
            let values: Vec<f64> = inner_series.f64()?.into_no_null_iter().collect();
            assert_eq!(values.len(), 3);
            assert!((values[0] - 0.001).abs() < 1e-10); // age=30, gender=M
            assert!((values[1] - 0.0012).abs() < 1e-10); // age=31, gender=M
            assert!((values[2] - 0.0014).abs() < 1e-10); // age=32, gender=M
        } else {
            panic!("Expected List, got {:?}", first_inner);
        }

        // Second row: ages [30, 31] with gender "F"
        let second_inner = result_list.get_any_value(1)?;
        if let AnyValue::List(inner_series) = second_inner {
            let values: Vec<f64> = inner_series.f64()?.into_no_null_iter().collect();
            assert_eq!(values.len(), 2);
            assert!((values[0] - 0.0008).abs() < 1e-10); // age=30, gender=F
            assert!((values[1] - 0.001).abs() < 1e-10); // age=31, gender=F
        } else {
            panic!("Expected List, got {:?}", second_inner);
        }

        Ok(())
    }

    #[test]
    fn test_vector_lookup_batch_matches_current() -> PolarsResult<()> {
        // Create a table with array storage
        let df = df! {
            "age" => [30i64, 30, 31, 31, 32, 32],
            "gender" => ["M", "F", "M", "F", "M", "F"],
            "rate" => [0.001, 0.0008, 0.0012, 0.001, 0.0014, 0.0012]
        }?;

        let storage = ArrayStorage::build(&df, &["age".to_string(), "gender".to_string()], "rate")?
            .expect("Should build array storage");

        // Create vector lookup keys: age is List, gender is scalar
        let age_lists = ListChunked::from_iter([
            Some(Series::new("".into(), vec![30i64, 31, 32])),
            Some(Series::new("".into(), vec![30i64, 31])),
            Some(Series::new("".into(), vec![32i64])),
        ]);
        let age_series = age_lists.into_series();
        let gender_series = Series::new("gender".into(), &["M", "F", "M"]);

        let vector_indices = vec![0usize];
        let vector_len = 3;

        // Call both methods
        let current_result = storage.lookup_vector(
            &[&age_series, &gender_series],
            vector_len,
            &vector_indices,
        )?;

        let batch_result = storage.lookup_vector_batch(
            &[&age_series, &gender_series],
            vector_len,
            &vector_indices,
        )?;

        // Results should be identical
        let current_list = current_result.list()?;
        let batch_list = batch_result.list()?;

        assert_eq!(current_list.len(), batch_list.len());

        for i in 0..current_list.len() {
            let current_inner = current_list.get_any_value(i)?;
            let batch_inner = batch_list.get_any_value(i)?;

            if let (AnyValue::List(c_series), AnyValue::List(b_series)) =
                (current_inner, batch_inner)
            {
                let c_vals: Vec<f64> = c_series.f64()?.into_no_null_iter().collect();
                let b_vals: Vec<f64> = b_series.f64()?.into_no_null_iter().collect();

                assert_eq!(c_vals.len(), b_vals.len(), "Row {} length mismatch", i);
                for (j, (c, b)) in c_vals.iter().zip(b_vals.iter()).enumerate() {
                    if c.is_nan() {
                        assert!(b.is_nan(), "Row {} elem {} NaN mismatch", i, j);
                    } else {
                        assert!(
                            (c - b).abs() < 1e-15,
                            "Row {} elem {} value mismatch: {} vs {}",
                            i,
                            j,
                            c,
                            b
                        );
                    }
                }
            } else {
                panic!("Expected Lists at row {}", i);
            }
        }

        Ok(())
    }
}
