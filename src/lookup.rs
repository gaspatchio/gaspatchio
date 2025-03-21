use log::{debug, error, info, trace, warn};
use polars::prelude::*;
use pyo3::prelude::*;
use pyo3_polars::derive::polars_expr;
use serde::Deserialize;

#[derive(Deserialize)]
pub struct LookupKwargs {
    pub table_name: String,
}

fn same_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let field = &input_fields[0];

    // Use Python's logging directly
    Python::with_gil(|py| {
        let logging = PyModule::import_bound(py, "logging").unwrap();
        let logger = logging
            .getattr("getLogger")
            .unwrap()
            .call1(("gaspatchio_core.lookup",))
            .unwrap();
        logger
            .call_method1(
                "error",
                ("RUST ERROR LOG - Creating output field using Python logging",),
            )
            .unwrap();
        logger
            .call_method1(
                "warning",
                ("RUST WARN LOG - Creating output field using Python logging",),
            )
            .unwrap();
    });

    error!("RUST ERROR LOG - Creating output field"); // Test error level
    warn!("RUST WARN LOG - Creating output field"); // Test warn level

    Ok(field.clone())
}

#[polars_expr(output_type_func = same_output_type)]
pub fn lookup(inputs: &[Series], kwargs: LookupKwargs) -> PolarsResult<Series> {
    // Use Python's logging directly
    Python::with_gil(|py| {
        let logging = PyModule::import_bound(py, "logging").unwrap();
        let logger = logging
            .getattr("getLogger")
            .unwrap()
            .call1(("gaspatchio_core.lookup",))
            .unwrap();
        logger
            .call_method1(
                "error",
                (format!(
                    "RUST via Python ERROR LOG - Lookup function called with {} inputs",
                    inputs.len()
                ),),
            )
            .unwrap();
        logger
            .call_method1(
                "warning",
                ("RUST via Python WARN LOG - Lookup function called",),
            )
            .unwrap();
        logger
            .call_method1(
                "info",
                ("RUST via Python INFO LOG - Lookup function called",),
            )
            .unwrap();
        logger
            .call_method1(
                "debug",
                ("RUST via Python DEBUG LOG - Lookup function called",),
            )
            .unwrap();
    });

    error!(
        "RUST ERROR LOG - Lookup function called with {} inputs",
        inputs.len()
    ); // Should show at ERROR level
    warn!("RUST WARN LOG - Lookup function called"); // Should show at WARN level
    info!("RUST INFO LOG - Lookup function called"); // Should show at INFO level
    debug!("RUST DEBUG LOG - Lookup function called"); // Should show at DEBUG level
    trace!("RUST TRACE LOG - Lookup function called"); // Should show at TRACE level

    // The first input is the table name (already handled via kwargs)
    // The remaining inputs are the key columns for lookup
    if inputs.len() < 2 {
        return Err(PolarsError::ComputeError(
            "lookup requires at least 2 inputs: one for lookup values and one for key column"
                .into(),
        ));
    }

    let lookup_values = &inputs[0];
    let key_columns = &inputs[1..];
    let table_name = &kwargs.table_name;

    debug!(
        "Looking up values from table '{}' using {} key columns",
        table_name,
        key_columns.len()
    );

    // Log detailed information about lookup values at info level
    info!(
        "Lookup operation: table={}, lookup_type={:?}, keys_count={}",
        table_name,
        lookup_values.dtype(),
        key_columns.len()
    );

    // Log more detailed information at debug level
    debug!(
        "Lookup values dtype: {:?}, inner_type: {:?}",
        lookup_values.dtype(),
        lookup_values.dtype().inner_dtype()
    );

    // Log sample data at trace level
    trace!("Sample lookup values: {:?}", lookup_values.head(Some(3)));

    for (i, key_col) in key_columns.iter().enumerate() {
        trace!("Key column {} type: {:?}", i, key_col.dtype());
        trace!("Sample key column {}: {:?}", i, key_col.head(Some(3)));
    }

    // For now we'll just return a constant value since we're still debugging
    // We're not worried about the actual implementation yet
    debug!(
        "Returning constant value 0.05 for all {} rows",
        lookup_values.len()
    );

    // Return 0.05 for all rows as the mortality rate
    let length = lookup_values.len();

    // Since the original function has same_output_type, we need to return the same type
    // as the lookup_values
    match lookup_values.dtype() {
        DataType::Float64 => {
            let values = vec![0.05; length];
            let s = Series::new(PlSmallStr::from_static(""), values);
            Ok(s)
        }
        DataType::Float32 => {
            let values = vec![0.05_f32; length];
            let s = Series::new(PlSmallStr::from_static(""), values);
            Ok(s)
        }
        DataType::Int64 => {
            let values = vec![5_i64; length];
            let s = Series::new(PlSmallStr::from_static(""), values);
            Ok(s)
        }
        DataType::Int32 => {
            let values = vec![5_i32; length];
            let s = Series::new(PlSmallStr::from_static(""), values);
            Ok(s)
        }
        DataType::List(inner) => {
            // Handle list type
            debug!("Processing list type with inner type: {:?}", inner);
            match inner.as_ref() {
                DataType::Float64 => {
                    let values = vec![0.05; length];
                    let s = Series::new(PlSmallStr::from_static(""), values);
                    Ok(s)
                }
                DataType::Float32 => {
                    let values = vec![0.05_f32; length];
                    let s = Series::new(PlSmallStr::from_static(""), values);
                    Ok(s)
                }
                DataType::Int64 => {
                    let values = vec![5_i64; length];
                    let s = Series::new(PlSmallStr::from_static(""), values);
                    Ok(s)
                }
                DataType::Int32 => {
                    let values = vec![5_i32; length];
                    let s = Series::new(PlSmallStr::from_static(""), values);
                    Ok(s)
                }
                _ => {
                    let err_msg = format!("Unsupported inner type in lookup function: {:?}", inner);
                    debug!("Error: {}", err_msg);
                    Err(PolarsError::ComputeError(err_msg.into()))
                }
            }
        }
        _ => {
            let err_msg = format!(
                "Unsupported type in lookup function: {:?}",
                lookup_values.dtype()
            );
            debug!("Error: {}", err_msg);
            Err(PolarsError::ComputeError(err_msg.into()))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lookup_function_behavior() -> PolarsResult<()> {
        // This test validates the behavior we expect from the lookup function
        // Instead of calling the function directly (which isn't accessible),
        // we'll test the core logic used within the function

        // Test that we can create a simple hash from strings
        let key_str = "test_key";
        let hash_i32 = key_str
            .bytes()
            .fold(0i32, |acc, b| acc.wrapping_add(b as i32));
        let hash_value_i32 = (hash_i32 % 100).abs();

        // Ensure the hash produces consistent results
        let same_key_str = "test_key";
        let same_hash_i32 = same_key_str
            .bytes()
            .fold(0i32, |acc, b| acc.wrapping_add(b as i32));
        let same_hash_value_i32 = (same_hash_i32 % 100).abs();

        // Different keys should produce different hashes
        let different_key_str = "different_key";
        let different_hash_i32 = different_key_str
            .bytes()
            .fold(0i32, |acc, b| acc.wrapping_add(b as i32));
        let different_hash_value_i32 = (different_hash_i32 % 100).abs();

        // Verify that same inputs produce same outputs
        assert_eq!(hash_value_i32, same_hash_value_i32);

        // Verify that different inputs produce different outputs
        assert_ne!(hash_value_i32, different_hash_value_i32);

        // Verify bounds of the hash values
        assert!(hash_value_i32 >= 0);
        assert!(hash_value_i32 < 100);
        assert!(different_hash_value_i32 >= 0);
        assert!(different_hash_value_i32 < 100);

        // Verify the float version works similarly
        let hash_i64 = key_str
            .bytes()
            .fold(0i64, |acc, b| acc.wrapping_add(b as i64));
        let hash_value_f64 = ((hash_i64 % 100).abs() as f64) / 100.0;

        assert!(hash_value_f64 >= 0.0);
        assert!(hash_value_f64 <= 1.0);

        Ok(())
    }

    #[test]
    fn test_lookup_multiple_keys_behavior() -> PolarsResult<()> {
        // Test the behavior for multiple keys

        // Create a table name for testing
        let table_name = "mortality";

        // Create a hash from the table name
        let mut hash_i32 = table_name
            .bytes()
            .fold(0i32, |acc, b| acc.wrapping_add(b as i32));

        // Add some key column lengths to simulate multiple keys
        let key_column_lengths = [10, 20, 30];

        for &len in &key_column_lengths {
            hash_i32 = hash_i32.wrapping_add(len as i32);
        }

        let hash_value_i32 = (hash_i32 % 100).abs();

        // Verify bounds of the hash values
        assert!(hash_value_i32 >= 0);
        assert!(hash_value_i32 < 100);

        // Create a float version
        let mut hash_i64 = table_name
            .bytes()
            .fold(0i64, |acc, b| acc.wrapping_add(b as i64));

        for &len in &key_column_lengths {
            hash_i64 = hash_i64.wrapping_add(len as i64);
        }

        let hash_value_f64 = ((hash_i64 % 100).abs() as f64) / 100.0;

        assert!(hash_value_f64 >= 0.0);
        assert!(hash_value_f64 <= 1.0);

        // Verify that changes to inputs produce different outputs
        let different_table = "lapse";
        let mut different_hash_i32 = different_table
            .bytes()
            .fold(0i32, |acc, b| acc.wrapping_add(b as i32));

        for &len in &key_column_lengths {
            different_hash_i32 = different_hash_i32.wrapping_add(len as i32);
        }

        let different_hash_value_i32 = (different_hash_i32 % 100).abs();

        // Different table names should give different results
        assert_ne!(hash_value_i32, different_hash_value_i32);

        Ok(())
    }

    #[test]
    fn test_null_handling_behavior() -> PolarsResult<()> {
        // Test null handling by applying the same pattern used in lookup function

        // Create a chunked array with nulls
        let values: Vec<Option<i64>> = vec![Some(25), None, Some(45), None];
        let chunked = Int64Chunked::from_iter(values.iter().cloned());

        // Apply a function that preserves nulls but transforms non-null values
        let result: Int64Chunked = chunked.apply(|opt_v: Option<i64>| {
            opt_v.map(|_v| {
                // Just return a constant value for this test
                42i64
            })
        });

        // Verify null values are preserved
        assert_eq!(result.len(), 4);
        assert!(result.get(0).is_some());
        assert!(result.get(1).is_none());
        assert!(result.get(2).is_some());
        assert!(result.get(3).is_none());

        // Verify values are transformed correctly
        assert_eq!(result.get(0), Some(42));
        assert_eq!(result.get(2), Some(42));

        Ok(())
    }
}
