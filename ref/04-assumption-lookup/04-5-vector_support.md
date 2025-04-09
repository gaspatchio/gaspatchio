```rust
use polars::chunked_array::builder::get_list_builder;
use polars::datatypes::{DataType, Field}; // Added Field

/// A pre-built lookup index for fast value retrieval
pub struct LookupIndex {
    pub keys: Vec<String>,
    pub value_column: String,
    pub value_dtype: DataType, // Added field to store the value column's data type
    pub index: HashMap<Vec<Value>, Value>,
}

// ... existing Value enum, LookupIndex, any_value_to_value ...

/// Extracts a single Value from a Series at a given row index.
fn extract_value_from_series(column: &Series, index: usize) -> PolarsResult<Value> { // Changed Column to Series
    let any_value = column.get(index)?;
    any_value_to_value(any_value)
}


/// Extracts a single Value from a List Series at a given outer index `list_idx`
/// and inner index `element_idx`.
fn extract_value_from_list_series(
    list_series: &Series,
    list_idx: usize,
    element_idx: usize,
) -> PolarsResult<Value> {
    let list_ca = list_series.list()?;
    let inner_series = list_ca.get(list_idx)
        .ok_or_else(|| PolarsError::ComputeError(format!(
            "List index {} out of bounds for series '{}'", list_idx, list_series.name()
        ).into()))?;

    // Handle potentially empty or null inner series
    if inner_series.is_null() || element_idx >= inner_series.len() {
         // If the inner list is null or the index is out of bounds for the *inner* list,
         // we might consider this a lookup failure or handle it based on requirements.
         // Returning Null seems reasonable for now if the element doesn't exist.
         // Alternatively, could return an error:
         // return Err(PolarsError::ComputeError(format!(
         //    "Element index {} out of bounds for inner list at index {} in series '{}'",
         //    element_idx, list_idx, list_series.name()
         // ).into()));
         Ok(Value::Null) // Or return an error depending on desired behavior for missing inner elements
    } else {
        let av = inner_series.get(element_idx)?;
        any_value_to_value(av)
    }
}


/// Converts a Vec<Value> into a Polars Series with an appropriate DataType.
/// Attempts to infer the DataType from the first non-Null value.
fn create_series_from_values(values: &[Value], name: &str) -> PolarsResult<Series> {
    if values.is_empty() {
        // Create an empty series of a default type (e.g., Null or Float64)
        // Or determine the type from the LookupIndex if available
        // For now, let's default to Null, but this might need refinement.
        Ok(Series::new_null(name, 0))
        // Alternative: Require target_dtype
        // return Err(PolarsError::ComputeError("Cannot create series from empty values without target dtype".into()));
    }

    // Determine data type from first non-null value
    let mut iter = values.iter().filter(|v| !matches!(v, Value::Null));
    let first_val = iter.next();

    match first_val {
        Some(Value::Int(_)) => {
            let ints: Vec<Option<i64>> = values
                .iter()
                .map(|v| match v {
                    Value::Int(i) => Some(*i),
                    Value::Null => None,
                    _ => None, // Or return error for mixed types
                })
                .collect();
            Ok(Series::new(name, ints))
        }
        Some(Value::Float(_)) => {
            let floats: Vec<Option<f64>> = values
                .iter()
                .map(|v| match v {
                    Value::Float(f) => Some(*f),
                    Value::Null => None,
                    _ => None, // Or return error for mixed types
                })
                .collect();
            Ok(Series::new(name, floats))
        }
        Some(Value::String(_)) => {
            let strings: Vec<Option<String>> = values
                .iter()
                .map(|v| match v {
                    Value::String(s) => Some(s.clone()),
                    Value::Null => None,
                    _ => None, // Or return error for mixed types
                })
                .collect();
            Ok(Series::new(name, strings))
        }
        None => {
            // All values are Null
            Ok(Series::new_null(name, values.len()))
        }
         Some(Value::Null) => {
             // Should not happen due to filter, but handle defensively
             Ok(Series::new_null(name, values.len()))
         }
    }
}

/// Builds a lookup index from a DataFrame.
fn build_lookup_index(
    df: &DataFrame,
    key_columns: &[String],
    value_column: &str,
) -> PolarsResult<(HashMap<Vec<Value>, Value>, DataType)> { // Changed return type to include DataType
    let mut index = HashMap::new();
    
    // Extract the value data type BEFORE iterating
    let value_series = df.column(value_column)?;
    let value_dtype = value_series.dtype().clone();

    // Pre-compute iterators or collect columns to avoid repeated lookups
    let key_series: Vec<&Series> = key_columns
        .iter()
        .map(|name| df.column(name))
        .collect::<Result<Vec<_>, _>>()?;

    for row_idx in 0..df.height() {
        let mut key_vec = Vec::with_capacity(key_columns.len());
        
        // Extract key values
        for series in &key_series {
            key_vec.push(extract_value_from_series(series, row_idx)?);
        }
        
        // Extract value
        let value = extract_value_from_series(value_series, row_idx)?;
        
        // Insert into HashMap
        index.insert(key_vec, value);
    }

    Ok((index, value_dtype)) // Return both the index and the data type
}

// ... existing detect_vector_columns ...

/// Performs a lookup in a registered table using potentially vector inputs.
///
/// If any input `keys` series is of type List, the lookup is performed element-wise
/// for all vectors, broadcasting scalar values. The result will be a List series.
/// If all inputs are scalar, a single lookup is performed, and the result is a scalar Series.
///
/// # Arguments
///
/// * `lookup_index` - The pre-built index to use for lookups.
/// * `keys` - A slice of Series representing the key columns. Must match the order
///            and number of keys expected by the `lookup_index`.
///
/// # Returns
///
/// A `Result` containing the resulting `Series` or a `PolarsError`.
fn lookup_vector_internal(
    lookup_index: &LookupIndex,
    keys: &[&Series],
) -> PolarsResult<Series> {
    // 1. Validate key length
    if keys.len() != lookup_index.keys.len() {
        return Err(PolarsError::ShapeMismatch(
            format!(
                "Lookup key length mismatch. Index expects {} keys, but got {}.",
                lookup_index.keys.len(),
                keys.len()
            )
            .into(),
        ));
    }

    // 2. Identify vector inputs and determine output length
    let mut first_vector_len: Option<usize> = None;
    let mut vector_indices = Vec::new();
    let mut any_vectors = false;

    for (i, series) in keys.iter().enumerate() {
        if matches!(series.dtype(), DataType::List(_)) {
            any_vectors = true;
            vector_indices.push(i);
            let list_ca = series.list()?;
            let current_len = list_ca.len(); // Length of the outer list series

            if let Some(expected_len) = first_vector_len {
                if current_len != expected_len {
                    return Err(PolarsError::ShapeMismatch(
                        format!(
                            "Input vector lengths mismatch. Expected length {}, but key '{}' has length {}.",
                            expected_len, series.name(), current_len
                        ).into()
                    ));
                }
            } else {
                first_vector_len = Some(current_len);
            }
        } else {
             // Ensure scalar series have at least one element if vectors are present
             if first_vector_len.is_some() && series.len() == 0 {
                 return Err(PolarsError::ShapeMismatch(
                    format!(
                        "Scalar key '{}' is empty but vector keys are present.",
                        series.name()
                    ).into()
                ));
             }
             if first_vector_len.is_none() && series.len() != 1 {
                 // If all inputs *should* be scalar, they must have length 1
                 // (We handle the all-scalar case separately below, but this adds safety)
                  if keys.iter().all(|s| !matches!(s.dtype(), DataType::List(_))) && series.len() != 1 {
                     return Err(PolarsError::ShapeMismatch(
                        format!(
                            "Scalar key '{}' has length {}, expected 1 for scalar lookup.",
                            series.name(), series.len()
                        ).into()
                    ));
                 }
             }
        }
    }

    // --- Case 1: All inputs are scalar ---
    if !any_vectors {
        let mut key_values = Vec::with_capacity(keys.len());
        for series in keys {
             if series.len() != 1 {
                 return Err(PolarsError::ShapeMismatch(format!(
                    "Scalar input series '{}' has length {}, expected 1.", series.name(), series.len()
                 ).into()));
             }
            key_values.push(extract_value_from_series(series, 0)?);
        }
        let result_value = lookup_index.lookup(&key_values).cloned().unwrap_or(Value::Null);
        // Create a single-element series using the stored dtype
        return create_series_from_values(&[result_value], &lookup_index.value_column);
    }

    // --- Case 2: At least one vector input ---
    let output_len = first_vector_len.unwrap_or(0);
    if output_len == 0 {
         // Input vectors are empty, return an empty List series using stored dtype
         let list_dtype = DataType::List(Box::new(lookup_index.value_dtype.clone()));
         return Ok(Series::new_empty(&lookup_index.value_column, &list_dtype));
    }


    let mut results: Vec<Value> = Vec::with_capacity(output_len);

    // Pre-extract scalar values (avoids repeated extraction in loop)
    let scalar_values: Vec<Option<Value>> = keys.iter().enumerate().map(|(i, series)| {
        if vector_indices.contains(&i) {
            None // Placeholder for vectors
        } else {
            Some(extract_value_from_series(series, 0).unwrap_or(Value::Null)) // Handle potential error?
        }
    }).collect();


    for i in 0..output_len {
        let mut current_key = Vec::with_capacity(keys.len());
        let mut key_valid = true; // Flag to track if key extraction succeeded

        for (key_idx, series) in keys.iter().enumerate() {
             match scalar_values[key_idx] {
                Some(ref scalar_val) => {
                    // Use pre-extracted scalar value
                    current_key.push(scalar_val.clone());
                }
                None => {
                     // Extract from vector series at index i
                     match extract_value_from_list_series(series, i, 0) { // Assuming inner list has only one relevant value? Or should this handle nested lists? Let's assume the key vector is flat List<Type>. Adjust if needed.
                         Ok(val) => current_key.push(val),
                         Err(_) => {
                             // Error extracting from list, treat lookup as failed for this row
                             current_key.push(Value::Null); // Push a placeholder
                             key_valid = false;
                             // Optionally break the inner loop if one key part fails: break;
                         }
                     }
                 }
             }
        }

        // Perform lookup only if the key was fully extracted
        let result = if key_valid {
            lookup_index.lookup(&current_key).cloned().unwrap_or(Value::Null)
        } else {
            Value::Null // Key extraction failed, result is Null
        };
        results.push(result);
    }

    // Convert the Vec<Value> results into a List Series
    // Use a List builder with the stored dtype
    let mut list_builder = get_list_builder(
        &lookup_index.value_dtype,
        output_len,
        output_len * 1,
        &lookup_index.value_column
    )?;

    for val in results {
         match val {
            Value::Int(i) => list_builder.append_series(&Series::new("", &[Some(i)])),
            Value::Float(f) => list_builder.append_series(&Series::new("", &[Some(f)])),
            Value::String(s) => list_builder.append_series(&Series::new("", &[Some(s)])),
            Value::Null => list_builder.append_null(), // Append a null list entry
         }
         // This assumes the *result* is a list of single values.
         // If the lookup itself could return lists, this needs adjustment.
         // Based on the examples, the lookup returns a single rate/value per key combo.
    }


    Ok(list_builder.finish().into_series())

}


// ... existing TableRegistry struct and methods ...

impl TableRegistry {
    // ... existing new, register_table, get_table, get_lookup_index, lookup ...

    /// Performs a vector-aware lookup using a pre-built index.
    /// Delegates to the internal lookup_vector function.
    ///
    /// # Arguments
    ///
    /// * `name` - The name of the registered table/index to use.
    /// * `keys` - A slice of `&Series` representing the key columns.
    ///
    /// # Returns
    ///
    /// `Ok(Series)` containing the lookup results (scalar or List Series),
    /// or `Err(RegistryError)` if the table doesn't exist or a PolarsError occurs.
    pub fn lookup_vector(&self, name: &str, keys: &[&Series]) -> Result<Series, RegistryError> {
        let lookup_index = self
            .get_lookup_index(name)
            .ok_or_else(|| RegistryError::TableNotFound(name.to_string()))?;

        // Call the internal function that handles PolarsErrors
        lookup_vector_internal(lookup_index, keys)
            .map_err(|e| RegistryError::IndexBuildFailed(name.to_string(), e)) // Wrap PolarsError
    }

    pub fn register_table(
        &mut self,
        name: &str,
        df: DataFrame,
        keys: Vec<String>,
        value_column: &str,
    ) -> Result<(), RegistryError> {
        if self.tables.contains_key(name) {
            return Err(RegistryError::TableAlreadyExists(name.to_string()));
        }

        // Build the index and get the value dtype
        let (index_map, value_dtype) = build_lookup_index(&df, &keys, value_column)
            .map_err(|e| RegistryError::IndexBuildFailed(name.to_string(), e))?;

        let lookup_index = LookupIndex {
            keys,
            value_column: value_column.to_string(),
            value_dtype, // Store the data type
            index: index_map,
        };

        // Store both the original DataFrame and the index
        self.tables.insert(name.to_string(), df);
        self.lookup_indices.insert(name.to_string(), lookup_index);

        Ok(())
    }
}


// ... existing global registry definitions and functions ...

#[cfg(test)]
mod tests {
    use super::reset_global_registry;
    use super::*;
    use polars::df; // Import the df! macro
    use polars::prelude::NamedFrom; // For Series::new
    use polars::series::ChunkCompare; // For series comparison
    use std::thread;
    use std::time::Duration;

    // ... existing tests ...

    // Helper function for vector tests
    fn setup_mortality_registry() -> Result<(), RegistryError> {
        reset_global_registry();
        // Transformed mortality table
        let df_mortality = df!(
            "age-last" => &[31i64, 31, 31, 31, 33, 33, 33, 33, 34, 34, 34, 34],
            "gender_smoking" => &["MNS", "FNS", "MS", "FS", "MNS", "FNS", "MS", "FS", "MNS", "FNS", "MS", "FS"],
            "mortality_rate" => &[0.0012f64, 0.0011, 0.0022, 0.0020, 0.0013, 0.0012, 0.0023, 0.0021, 0.0014, 0.0013, 0.0024, 0.0022]
        ).unwrap();
        register_table(
            "mortality_rates",
            df_mortality,
            vec!["age-last".to_string(), "gender_smoking".to_string()],
            "mortality_rate",
        )
    }

    #[test]
    fn test_lookup_vector_scalar_inputs() -> Result<(), Box<dyn std::error::Error>> {
        setup_mortality_registry()?;
        let registry = get_registry();

        let age_key = Series::new("age-last", &[33i64]);
        let gs_key = Series::new("gender_smoking", &["MS"]);

        let result_series = registry.lookup_vector("mortality_rates", &[&age_key, &gs_key])?;

        // Expecting a scalar Float64 series
        let expected = Series::new("mortality_rate", &[0.0023f64]);
        assert!(result_series.equals(&expected));
        assert_eq!(result_series.dtype(), &DataType::Float64);

        Ok(())
    }


    #[test]
    fn test_lookup_vector_pure_vector_inputs() -> Result<(), Box<dyn std::error::Error>> {
        setup_mortality_registry()?;
        let registry = get_registry();

        // Inputs matching policyholder 2 from 04-examples.md (simplified)
        // age-last: [39.0, 39.0, ..., 100.0] -> Let's use [31, 33, 34, 99] for testing known/unknown rates
        // gender_smoking: MS (scalar, but needs broadcasting)
        let age_list = Series::new("age-last", vec![
            Series::new("", &[31i64]), // Corresponds to MNS -> 0.0012
            Series::new("", &[33i64]), // Corresponds to MNS -> 0.0013
            Series::new("", &[99i64]), // Not in table -> Null
            Series::new("", &[34i64]), // Corresponds to MNS -> 0.0014
        ]);
        let gs_list = Series::new("gender_smoking", vec![
             Series::new("", &["MNS"]),
             Series::new("", &["MNS"]),
             Series::new("", &["MNS"]),
             Series::new("", &["MNS"]),
        ]);


        // We need List type inputs for vector lookup
        let age_key_list = age_list.list().unwrap().clone().into_series(); // Convert ChunkedArray<ListType> to Series
        let gs_key_list = gs_list.list().unwrap().clone().into_series();

        let result_series = registry.lookup_vector("mortality_rates", &[&age_key_list, &gs_key_list])?;


        // Expecting a List<Float64> series
        let expected_values: Vec<Option<f64>> = vec![Some(0.0012), Some(0.0013), None, Some(0.0014)];
        // Construct expected List Series manually
         let mut expected_builder = get_list_builder(&DataType::Float64, expected_values.len(), expected_values.len(), "mortality_rate")?;
         for val_opt in expected_values {
             expected_builder.append_series(&Series::new("", &[val_opt]));
         }
         let expected = expected_builder.finish().into_series();


        println!("Result Series:\n{:?}", result_series);
        println!("Expected Series:\n{:?}", expected);

        // Polars equality check handles nested types
        assert!(result_series.equals(&expected));
        assert!(matches!(result_series.dtype(), DataType::List(_)));
        if let DataType::List(inner) = result_series.dtype() {
            assert_eq!(inner.as_ref(), &DataType::Float64);
        }


        Ok(())
    }


     #[test]
    fn test_lookup_vector_mixed_inputs() -> Result<(), Box<dyn std::error::Error>> {
        setup_mortality_registry()?;
        let registry = get_registry();

        // Vector for age, Scalar for gender_smoking
        // Example: Get rates for ages [31, 34, 31, 99] but all for 'FS'
        let age_list = Series::new("age-last", vec![
            Series::new("", &[31i64]), // FS -> 0.0020
            Series::new("", &[34i64]), // FS -> 0.0022
            Series::new("", &[31i64]), // FS -> 0.0020
            Series::new("", &[99i64]), // Not in table -> Null
        ]);
         let age_key_list = age_list.list().unwrap().clone().into_series();

        // Scalar gender_smoking key
        let gs_key_scalar = Series::new("gender_smoking", &["FS"]);


        let result_series = registry.lookup_vector("mortality_rates", &[&age_key_list, &gs_key_scalar])?;

        // Expecting a List<Float64> series
        let expected_values: Vec<Option<f64>> = vec![Some(0.0020), Some(0.0022), Some(0.0020), None];
        // Construct expected List Series manually
        let mut expected_builder = get_list_builder(&DataType::Float64, expected_values.len(), expected_values.len(), "mortality_rate")?;
         for val_opt in expected_values {
             expected_builder.append_series(&Series::new("", &[val_opt]));
         }
        let expected = expected_builder.finish().into_series();

        println!("Result Series (Mixed):\n{:?}", result_series);
        println!("Expected Series (Mixed):\n{:?}", expected);

        assert!(result_series.equals(&expected));
         assert!(matches!(result_series.dtype(), DataType::List(_)));
         if let DataType::List(inner) = result_series.dtype() {
             assert_eq!(inner.as_ref(), &DataType::Float64);
         }

        Ok(())
    }

    #[test]
    fn test_lookup_vector_mismatched_lengths() -> Result<(), Box<dyn std::error::Error>> {
         setup_mortality_registry()?;
         let registry = get_registry();

         let age_list = Series::new("age-last", vec![
             Series::new("", &[31i64]),
             Series::new("", &[34i64]),
         ]);
         let gs_list = Series::new("gender_smoking", vec![ // Different length
              Series::new("", &["MNS"]),
         ]);

         let age_key_list = age_list.list().unwrap().clone().into_series();
         let gs_key_list = gs_list.list().unwrap().clone().into_series();


         let result = registry.lookup_vector("mortality_rates", &[&age_key_list, &gs_key_list]);

         assert!(result.is_err());
         if let Err(RegistryError::IndexBuildFailed(_, polars_err)) = result {
              assert!(matches!(polars_err, PolarsError::ShapeMismatch(_)));
              assert!(polars_err.to_string().contains("Input vector lengths mismatch"));
         } else {
             panic!("Expected IndexBuildFailed with ShapeMismatch, got {:?}", result);
         }

         Ok(())
    }

     #[test]
     fn test_lookup_vector_empty_input() -> Result<(), Box<dyn std::error::Error>> {
         setup_mortality_registry()?;
         let registry = get_registry();

         // Empty list inputs
         let age_list_empty = Series::new_empty("age-last", &DataType::List(Box::new(DataType::Int64)));
         let gs_list_empty = Series::new_empty("gender_smoking", &DataType::List(Box::new(DataType::String)));


         let result_series = registry.lookup_vector("mortality_rates", &[&age_list_empty, &gs_list_empty])?;

         // Expecting an empty List<Float64> series
         let expected = Series::new_empty("mortality_rate", &DataType::List(Box::new(DataType::Float64)));

         println!("Result Series (Empty):\n{:?}", result_series);
         println!("Expected Series (Empty):\n{:?}", expected);

         assert!(result_series.equals(&expected));
         assert_eq!(result_series.len(), 0);
          assert!(matches!(result_series.dtype(), DataType::List(_)));
          if let DataType::List(inner) = result_series.dtype() {
              assert_eq!(inner.as_ref(), &DataType::Float64);
          }


         Ok(())
     }


     #[test]
     fn test_lookup_vector_with_nulls_in_vector() -> Result<(), Box<dyn std::error::Error>> {
         setup_mortality_registry()?;
         let registry = get_registry();

         // Vector for age with a null, Scalar for gender_smoking
         let age_list = Series::new("age-last", vec![
             Some(Series::new("", &[31i64])), // MNS -> 0.0012
             None,                          // Null key -> Null result
             Some(Series::new("", &[34i64])), // MNS -> 0.0014
         ]);
          let age_key_list = age_list.list().unwrap().clone().into_series();

         let gs_key_scalar = Series::new("gender_smoking", &["MNS"]);

         let result_series = registry.lookup_vector("mortality_rates", &[&age_key_list, &gs_key_scalar])?;

         // Expecting a List<Float64> series with a Null entry
         let expected_values: Vec<Option<f64>> = vec![Some(0.0012), None, Some(0.0014)];
         let mut expected_builder = get_list_builder(&DataType::Float64, expected_values.len(), expected_values.len(), "mortality_rate")?;
          for val_opt in expected_values {
              expected_builder.append_series(&Series::new("", &[val_opt]));
          }
         let expected = expected_builder.finish().into_series();


         println!("Result Series (Nulls):\n{:?}", result_series);
         println!("Expected Series (Nulls):\n{:?}", expected);

         assert!(result_series.equals(&expected));
          assert!(matches!(result_series.dtype(), DataType::List(_)));
          if let DataType::List(inner) = result_series.dtype() {
              assert_eq!(inner.as_ref(), &DataType::Float64);
          }

         Ok(())
     }

} // End of tests module