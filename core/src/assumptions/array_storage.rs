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
            let column = df.column(key_name)?;
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
            dims, capacity, density * 100.0, memory_bytes / 1024
        );

        Ok(Some(Self {
            encoders,
            strides,
            data,
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
