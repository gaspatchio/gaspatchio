use polars::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fmt;
use std::hash::{Hash, Hasher};
use std::sync::Arc;

use arc_swap::ArcSwap;
use log::debug;
use once_cell::sync::Lazy;
use polars::chunked_array::builder::{get_list_builder, ListBuilderTrait};
use polars::datatypes::PlSmallStr;
use polars::series::Series;

/// Represents a value that can be used as a key or value in the lookup table.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Value {
    Int(i64),
    Float(f64),
    String(String),
    Null,
}

impl PartialEq for Value {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (Value::Int(a), Value::Int(b)) => a == b,
            (Value::Float(a), Value::Float(b)) => {
                // Handle NaN equality
                if a.is_nan() && b.is_nan() {
                    true
                } else {
                    (a - b).abs() < f64::EPSILON
                }
            }
            (Value::String(a), Value::String(b)) => a == b,
            (Value::Null, Value::Null) => true,
            _ => false,
        }
    }
}

impl Eq for Value {}

impl Hash for Value {
    fn hash<H: Hasher>(&self, state: &mut H) {
        match self {
            Value::Int(i) => {
                0u8.hash(state); // Type tag
                i.hash(state);
            }
            Value::Float(f) => {
                1u8.hash(state); // Type tag
                if f.is_nan() {
                    // Hash NaN consistently
                    f64::NAN.to_bits().hash(state);
                } else {
                    f.to_bits().hash(state);
                }
            }
            Value::String(s) => {
                2u8.hash(state); // Type tag
                s.hash(state);
            }
            Value::Null => {
                3u8.hash(state); // Type tag
            }
        }
    }
}

impl fmt::Display for Value {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Value::Int(i) => write!(f, "{}", i),
            Value::Float(fl) => write!(f, "{}", fl),
            Value::String(s) => write!(f, "{}", s),
            Value::Null => write!(f, "null"),
        }
    }
}

impl From<i64> for Value {
    fn from(i: i64) -> Self {
        Value::Int(i)
    }
}

impl From<f64> for Value {
    fn from(f: f64) -> Self {
        Value::Float(f)
    }
}

impl From<String> for Value {
    fn from(s: String) -> Self {
        Value::String(s)
    }
}

impl From<&str> for Value {
    fn from(s: &str) -> Self {
        Value::String(s.to_string())
    }
}

/// A lookup index that maps from a set of key values to a single value.
#[derive(Debug, Clone)]
pub struct LookupIndex {
    /// Names of the key columns
    pub keys: Vec<String>,
    /// Name of the value column
    pub value_column: String,
    /// Data type of the value column
    pub value_dtype: DataType,
    /// The actual lookup table
    pub index: HashMap<Vec<Value>, Value>,
}

impl LookupIndex {
    /// Creates a new empty lookup index.
    pub fn new(keys: Vec<String>, value_column: String, value_dtype: DataType) -> Self {
        Self {
            keys,
            value_column,
            value_dtype,
            index: HashMap::new(),
        }
    }

    /// Looks up a value using the given key combination.
    pub fn lookup(&self, key: &[Value]) -> Option<&Value> {
        if key.len() != self.keys.len() {
            return None;
        }
        self.index.get(key)
    }

    /// Returns the number of entries in the index.
    pub fn len(&self) -> usize {
        self.index.len()
    }

    /// Returns true if the index is empty.
    pub fn is_empty(&self) -> bool {
        self.index.is_empty()
    }
}

/// Converts a Polars AnyValue to our internal Value enum.
/// Handles common types (Int32, Int64, Float64, Utf8/String) and Null.
/// Returns PolarsError for unsupported types.
fn any_value_to_value(av: AnyValue) -> PolarsResult<Value> {
    debug!("Received AnyValue: {:?}, dtype: {:?}", av, av.dtype());

    match av {
        AnyValue::Int32(i) => Ok(Value::Int(i.into())),
        AnyValue::Int64(i) => Ok(Value::Int(i)),
        AnyValue::Float64(f) => Ok(Value::Float(f)),
        AnyValue::String(s) => Ok(Value::String(s.to_string())), // s is &str
        AnyValue::StringOwned(s) => Ok(Value::String(s.to_string())),
        AnyValue::Null => Ok(Value::Null),
        other => Err(PolarsError::ComputeError(
            format!(
                "Unsupported AnyValue type for key/value: {:?}",
                other.dtype()
            )
            .into(),
        )),
    }
}

/// Extracts a single Value from a Column at a given row index.
/// Note: Takes &Column, which Derefs to &Series, so .get() works.
fn extract_value_from_series(column: &Series, index: usize) -> PolarsResult<Value> {
    // Ensure index is within bounds before getting
    if index >= column.len() {
        return Err(PolarsError::OutOfBounds(
            format!(
                "Index {} out of bounds for series '{}' with length {}",
                index,
                column.name(),
                column.len()
            )
            .into(),
        ));
    }
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

    // Check outer bounds first
    if list_idx >= list_ca.len() {
        return Ok(Value::Null);
    }

    // Try getting the AnyValue directly from the ListChunked
    // This avoids dealing with the Option<Series> intermediate type
    match list_ca.get_any_value(list_idx)? {
        AnyValue::List(inner_series) => {
            // Now we have a Series, check inner bounds and get the value
            if element_idx >= inner_series.len() {
                Ok(Value::Null)
            } else {
                let av = inner_series.get(element_idx)?;
                any_value_to_value(av)
            }
        }
        AnyValue::Null => Ok(Value::Null), // The list entry itself was null
        _ => Err(PolarsError::ComputeError(
            "Expected AnyValue::List from ListChunked".into(),
        )),
    }
}

/// Converts a Vec<Value> into a Polars Series with a specified DataType.
fn create_series_from_values(
    values: &[Value],
    name: PlSmallStr,
    dtype: &DataType,
) -> PolarsResult<Series> {
    // name is PlSmallStr
    match dtype {
        DataType::Int64 => {
            let ints: Vec<Option<i64>> = values
                .iter()
                .map(|v| match v {
                    Value::Int(i) => Some(*i),
                    Value::Null => None,
                    _ => None,
                })
                .collect();
            Ok(Int64Chunked::from_slice_options(name, &ints).into_series())
        }
        DataType::Float64 => {
            let floats: Vec<Option<f64>> = values
                .iter()
                .map(|v| match v {
                    Value::Float(f) => Some(*f),
                    Value::Null => None,
                    _ => None,
                })
                .collect();
            Ok(Float64Chunked::from_slice_options(name, &floats).into_series())
        }
        DataType::String => {
            let strings: Vec<Option<String>> = values
                .iter()
                .map(|v| match v {
                    Value::String(s) => Some(s.clone()),
                    Value::Null => None,
                    _ => None,
                })
                .collect();
            Ok(StringChunked::from_slice_options(name, &strings).into_series())
        }
        DataType::Null => Ok(Series::new_null(name, values.len())),
        _ => Err(PolarsError::ComputeError(
            format!(
                "Unsupported data type {:?} for create_series_from_values",
                dtype
            )
            .into(),
        )),
    }
}

/// Builds a lookup index from a DataFrame.
fn build_lookup_index(
    df: &DataFrame,
    key_columns: &[String],
    value_column: &str,
) -> PolarsResult<(HashMap<Vec<Value>, Value>, DataType)> {
    let mut index = HashMap::new();
    let value_series_col = df.column(value_column)?;
    let value_dtype = value_series_col.dtype().clone();
    let key_cols_vec: Vec<&Column> = key_columns
        .iter()
        .map(|name| df.column(name))
        .collect::<Result<Vec<_>, _>>()?;

    for row_idx in 0..df.height() {
        let mut key_vec = Vec::with_capacity(key_columns.len());
        for col in &key_cols_vec {
            key_vec.push(extract_value_from_series(
                col.as_series()
                    .expect("Key column could not be represented as Series"),
                row_idx,
            )?);
        }
        let value = extract_value_from_series(
            value_series_col
                .as_series()
                .expect("Value column could not be represented as Series"),
            row_idx,
        )?;
        index.insert(key_vec, value);
    }
    Ok((index, value_dtype))
}

/// Errors that can occur during registry operations.
#[derive(Debug, thiserror::Error)]
pub enum RegistryError {
    #[error("Table '{0}' already exists in the registry.")]
    TableAlreadyExists(String),
    #[error("Table '{0}' not found in the registry.")]
    TableNotFound(String),
    #[error("Failed to build lookup index for table '{0}': {1}")]
    IndexBuildFailed(String, PolarsError),
    #[error("Lookup failed for table '{0}': {1}")]
    LookupFailed(String, PolarsError),
    #[error("Lookup key length mismatch for table '{0}'. Expected {1}, got {2}.")]
    KeyLengthMismatch(String, usize, usize),
}

/// A registry to store original DataFrames and their corresponding lookup indices.
#[derive(Debug, Clone, Default)]
pub struct TableRegistry {
    /// Stores the original DataFrames registered.
    tables: HashMap<String, DataFrame>,
    /// Stores the pre-built lookup indices for registered tables.
    lookup_indices: HashMap<String, LookupIndex>,
}

impl TableRegistry {
    /// Creates a new, empty TableRegistry.
    pub fn new() -> Self {
        Self::default()
    }

    /// Registers a DataFrame under a given name, building a lookup index for it.
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

        debug!(
            "Registering table '{}' with keys {:?} and value column '{}'",
            name, keys, value_column
        );

        // build_lookup_index now returns a tuple
        let (index_map, value_dtype) = build_lookup_index(&df, &keys, value_column)
            .map_err(|e| RegistryError::IndexBuildFailed(name.to_string(), e))?;

        debug!(
            "Built index for table '{}' with {} entries. Value type: {}",
            name,
            index_map.len(),
            value_dtype
        );

        let lookup_index = LookupIndex {
            keys,
            value_column: value_column.to_string(),
            value_dtype, // Use the returned dtype
            index: index_map,
        };

        self.tables.insert(name.to_string(), df);
        self.lookup_indices.insert(name.to_string(), lookup_index);

        Ok(())
    }

    /// Retrieves a reference to the original DataFrame registered under the given name.
    pub fn get_table(&self, name: &str) -> Option<&DataFrame> {
        self.tables.get(name)
    }

    /// Retrieves a reference to the LookupIndex registered under the given name.
    pub fn get_lookup_index(&self, name: &str) -> Option<&LookupIndex> {
        self.lookup_indices.get(name)
    }

    /// Performs a lookup using a pre-built index.
    ///
    /// # Arguments
    ///
    /// * `name` - The name of the registered table/index to use.
    /// * `key` - A vector of `Value` enums representing the key combination to look up.
    ///
    /// # Returns
    ///
    /// `Ok(Some(Value))` if the key is found, `Ok(None)` if the key is not found,
    /// or `Err(RegistryError)` if the table doesn't exist or the key length is incorrect.
    pub fn lookup(&self, name: &str, key: &[Value]) -> Result<Option<&Value>, RegistryError> {
        let lookup_index = self
            .get_lookup_index(name)
            .ok_or_else(|| RegistryError::TableNotFound(name.to_string()))?;

        if key.len() != lookup_index.keys.len() {
            return Err(RegistryError::KeyLengthMismatch(
                name.to_string(),
                lookup_index.keys.len(),
                key.len(),
            ));
        }

        Ok(lookup_index.lookup(key))
    }

    /// Performs a scalar lookup using a pre-built index.
    ///
    /// This is a convenience wrapper around `get_lookup_index` and `lookup`.
    pub fn lookup_scalar(&self, name: &str, key: &[Value]) -> Result<Value, RegistryError> {
        let lookup_index = self
            .get_lookup_index(name)
            .ok_or_else(|| RegistryError::TableNotFound(name.to_string()))?;

        if key.len() != lookup_index.keys.len() {
            return Err(RegistryError::KeyLengthMismatch(
                name.to_string(),
                lookup_index.keys.len(),
                key.len(),
            ));
        }

        Ok(lookup_index.lookup(key).cloned().unwrap_or(Value::Null))
    }

    /// Performs a vector-aware lookup using a pre-built index.
    ///
    /// If any input `keys` series is of type List, the lookup is performed element-wise
    /// for all vectors, broadcasting scalar values. The result will be a List series.
    /// If all inputs are scalar, a single lookup is performed, and the result is a scalar Series.
    ///
    /// # Arguments
    ///
    /// * `name` - The name of the registered table/index to use.
    /// * `keys` - A slice of `&Series` representing the key columns.
    ///
    /// # Returns
    ///
    /// `Ok(Series)` containing the lookup results (scalar or List Series),
    /// or `Err(RegistryError)` if the table doesn't exist or a PolarsError occurs during lookup.
    pub fn lookup_vector(&self, name: &str, keys: &[&Series]) -> Result<Series, RegistryError> {
        let lookup_index = self
            .get_lookup_index(name)
            .ok_or_else(|| RegistryError::TableNotFound(name.to_string()))?;

        if keys.len() != lookup_index.keys.len() {
            return Err(RegistryError::KeyLengthMismatch(
                name.to_string(),
                lookup_index.keys.len(),
                keys.len(),
            ));
        }

        perform_vector_lookup(lookup_index, keys)
            .map_err(|e| RegistryError::LookupFailed(name.to_string(), e))
    }
}

/// Validates inputs for vector lookup, checking key counts, detecting vectors,
/// and validating lengths.
///
/// Returns a tuple: `(any_vectors, first_vector_len, vector_indices)`.
fn validate_lookup_inputs<'a>(
    lookup_index: &LookupIndex,
    keys: &[&'a Series],
) -> PolarsResult<(bool, Option<usize>, Vec<usize>)> {
    if keys.len() != lookup_index.keys.len() {
        // Early exit if key counts don't match the index definition
        return Err(PolarsError::ComputeError(
            format!(
                "Lookup key length mismatch for index '{}'. Expected {}, got {}.",
                lookup_index.value_column, // Using value_column as identifier for now
                lookup_index.keys.len(),
                keys.len()
            )
            .into(),
        ));
    }

    let mut first_vector_len: Option<usize> = None;
    let mut vector_indices = Vec::new();
    let mut any_vectors = false;

    for (i, series) in keys.iter().enumerate() {
        if matches!(series.dtype(), DataType::List(_)) {
            any_vectors = true;
            vector_indices.push(i);
            let list_ca = series.list()?; // Already checked dtype
            let current_len = list_ca.len();

            if let Some(expected_len) = first_vector_len {
                if current_len != expected_len {
                    return Err(PolarsError::ShapeMismatch(format!(
                        "Input vector lengths mismatch. Expected length {}, but key '{}' (index {}) has length {}.",
                        expected_len, series.name(), i, current_len
                    ).into()));
                }
            } else {
                first_vector_len = Some(current_len);
            }
        } else {
            // Check scalar length only if vectors are present
            if first_vector_len.is_some() && series.len() != 1 && !series.is_empty() {
                // Allow empty scalar only if no vectors
                return Err(PolarsError::ShapeMismatch(
                    format!(
                        "Scalar key '{}' (index {}) has length {} but expected 1 when vector keys are present.",
                        series.name(), i, series.len()
                    ).into()
                 ));
            } else if first_vector_len.is_none() && series.len() != 1 && keys.len() > 0 {
                // If only scalars, they must all have length 1
                return Err(PolarsError::ShapeMismatch(
                    format!(
                        "Scalar key '{}' (index {}) has length {} but expected 1 for scalar lookup.",
                        series.name(), i, series.len()
                    ).into()
                 ));
            }
            // Empty dataframe check is handled later or by specific lookup cases
        }
    }

    Ok((any_vectors, first_vector_len, vector_indices))
}

/// Performs the lookup when all input keys are scalar Series.
fn execute_scalar_lookup(lookup_index: &LookupIndex, keys: &[&Series]) -> PolarsResult<Series> {
    let mut key_values = Vec::with_capacity(keys.len());
    for series in keys {
        // Validation ensures series.len() == 1 here
        if series.is_empty() {
            // Handle case where input DF might be empty
            return create_series_from_values(
                &[Value::Null], // Return null if any key is from an empty series
                lookup_index.value_column.as_str().into(),
                &lookup_index.value_dtype,
            );
        }
        key_values.push(extract_value_from_series(*series, 0)?);
    }
    let result_value = lookup_index
        .lookup(&key_values)
        .cloned()
        .unwrap_or(Value::Null);
    create_series_from_values(
        &[result_value],
        lookup_index.value_column.as_str().into(),
        &lookup_index.value_dtype,
    )
}

/// Internal function to perform the actual vector or scalar lookup.
fn perform_vector_lookup(lookup_index: &LookupIndex, keys: &[&Series]) -> PolarsResult<Series> {
    // 1. Validate inputs
    let (any_vectors, first_vector_len, vector_indices) =
        validate_lookup_inputs(lookup_index, keys)?;

    // --- Case 1: All inputs are scalar ---
    if !any_vectors {
        return execute_scalar_lookup(lookup_index, keys);
    }

    // --- Case 2: At least one vector input ---
    let output_len =
        first_vector_len.expect("first_vector_len should be Some if any_vectors is true");
    if output_len == 0 {
        // Handle empty vector input case
        let list_dtype = DataType::List(Box::new(lookup_index.value_dtype.clone()));
        return Ok(Series::new_empty(
            lookup_index.value_column.as_str().into(),
            &list_dtype,
        ));
    }

    // Extract scalar values once
    let scalar_values: Vec<Option<Value>> = keys
        .iter()
        .enumerate()
        .map(|(i, series)| -> PolarsResult<Option<Value>> {
            if vector_indices.contains(&i) {
                Ok(None) // Placeholder for vector keys
            } else {
                // Validation ensures scalar series have len 1 or are empty (handled by output_len == 0 check)
                extract_value_from_series(*series, 0).map(Some)
            }
        })
        .collect::<PolarsResult<Vec<_>>>()?;

    // Use .into() for name
    let mut list_builder = get_list_builder(
        &lookup_index.value_dtype,
        output_len,
        output_len, // capacity estimate
        lookup_index.value_column.as_str().into(),
    ); // Removed ? for potential error from get_list_builder

    for i in 0..output_len {
        let mut current_key = Vec::with_capacity(keys.len());
        let mut key_contains_null = false; // Track if any part of the key was null/error

        for (key_idx, series) in keys.iter().enumerate() {
            let value_result = if vector_indices.contains(&key_idx) {
                // Extract from the list series for this row
                // Assuming element_idx 0 for now, needs clarification if lists can have multiple elements per row relevant to the key
                extract_value_from_list_series(series, i, 0)
            } else {
                // Use the pre-extracted scalar value
                Ok(scalar_values[key_idx]
                    .clone()
                    .expect("Scalar value should exist here")) // Should be Some based on logic above
            };

            match value_result {
                Ok(Value::Null) => {
                    current_key.push(Value::Null);
                    key_contains_null = true; // Mark key as invalid if any part is Null
                }
                Ok(val) => {
                    current_key.push(val);
                }
                Err(e) => {
                    debug!(
                         "Error extracting key element at row {} for key '{}': {}. Treating as Null.",
                         i, series.name(), e
                     );
                    current_key.push(Value::Null);
                    key_contains_null = true; // Mark key as invalid on error
                }
            }
        }

        let result_value = if key_contains_null {
            // If any part of the key was null or failed extraction, the lookup result is Null
            Value::Null
        } else {
            lookup_index
                .lookup(&current_key)
                .cloned()
                .unwrap_or(Value::Null) // Default to Null if lookup fails
        };

        // Append the single result value (or Null) to the list builder for this row
        let append_result = match result_value {
            Value::Int(v) => list_builder.append_series(&Series::new("".into(), &[Some(v)])),
            Value::Float(v) => list_builder.append_series(&Series::new("".into(), &[Some(v)])),
            Value::String(v) => {
                list_builder.append_series(&Series::new("".into(), &[Some(v.as_str())]))
            } // Use &str
            Value::Null => {
                list_builder.append_null();
                Ok(())
            }
        };
        append_result?; // Propagate error from append
    }

    Ok(list_builder.finish().into_series())
}

// --- Global Registry Definition ---

// Define the static REGISTRY using Lazy for one-time initialization
// and ArcSwap for atomic updates.
static REGISTRY: Lazy<ArcSwap<TableRegistry>> = Lazy::new(|| {
    // Initialize with an empty TableRegistry wrapped in ArcSwap
    ArcSwap::from_pointee(TableRegistry::default())
});

/// Gets a thread-safe snapshot (Arc) of the current global TableRegistry.
/// Clients should hold onto this snapshot for the duration of their operation
/// rather than calling get_registry() repeatedly.
pub fn get_registry() -> Arc<TableRegistry> {
    REGISTRY.load_full()
}

/// Resets the global registry to an empty state. For testing purposes only.
#[cfg(test)]
pub(crate) fn reset_global_registry() {
    REGISTRY.store(Arc::new(TableRegistry::default()));
}

/// Registers a table in the global, thread-safe registry using Read-Copy-Update.
///
/// This function first builds the lookup index. If successful, it then
/// atomically updates the global registry using `ArcSwap::rcu`.
/// If the registry was modified concurrently during the update attempt,
/// `rcu` will automatically retry the update based on the newest state.
///
/// # Arguments
///
/// * `name` - The name to register the table under.
/// * `df` - The DataFrame containing the table data.
/// * `keys` - A vector of column names to use as lookup keys.
/// * `value_column` - The name of the column containing the values.
///
/// # Returns
///
/// `Ok(())` on success, or a `RegistryError` if index building fails.
pub fn register_table(
    name: &str,
    df: DataFrame,
    keys: Vec<String>,
    value_column: &str,
) -> Result<(), RegistryError> {
    let (index_map, value_dtype) = build_lookup_index(&df, &keys, value_column)
        .map_err(|e| RegistryError::IndexBuildFailed(name.to_string(), e))?;

    let lookup_index = LookupIndex {
        keys,
        value_column: value_column.to_string(),
        value_dtype,
        index: index_map,
    };

    REGISTRY.rcu(move |current_registry_arc| {
        let mut new_registry = (**current_registry_arc).clone();
        new_registry.tables.insert(name.to_string(), df.clone());
        new_registry
            .lookup_indices
            .insert(name.to_string(), lookup_index.clone());
        Arc::new(new_registry)
    });

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::reset_global_registry;
    use super::*;
    use polars::df; // Import the df! macro

    #[test]
    fn test_value_equality() {
        assert_eq!(Value::Int(42), Value::Int(42));
        assert_eq!(Value::Float(3.14), Value::Float(3.14));
        assert_eq!(Value::String("hello".into()), Value::String("hello".into()));
        assert_eq!(Value::Null, Value::Null);

        assert_ne!(Value::Int(42), Value::Float(42.0));
        assert_ne!(Value::String("42".into()), Value::Int(42));
        assert_ne!(Value::Null, Value::Int(0));
    }

    #[test]
    fn test_value_hash_consistency() {
        use std::collections::hash_map::DefaultHasher;

        fn get_hash<T: Hash>(t: &T) -> u64 {
            let mut s = DefaultHasher::new();
            t.hash(&mut s);
            s.finish()
        }

        // Same values should have same hashes
        assert_eq!(get_hash(&Value::Int(42)), get_hash(&Value::Int(42)));
        assert_eq!(get_hash(&Value::Float(3.14)), get_hash(&Value::Float(3.14)));
        assert_eq!(
            get_hash(&Value::String("hello".into())),
            get_hash(&Value::String("hello".into()))
        );
        assert_eq!(get_hash(&Value::Null), get_hash(&Value::Null));

        // Different values should have different hashes
        assert_ne!(get_hash(&Value::Int(42)), get_hash(&Value::Int(43)));
        assert_ne!(get_hash(&Value::Float(3.14)), get_hash(&Value::Float(3.15)));
        assert_ne!(
            get_hash(&Value::String("hello".into())),
            get_hash(&Value::String("world".into()))
        );
    }

    #[test]
    fn test_lookup_index_basic() {
        let mut index = LookupIndex::new(
            vec!["age".to_string()],
            "rate".to_string(),
            DataType::Float64, // Provide DataType
        );

        // Add some test data
        let key = vec![Value::Int(35)];
        let value = Value::Float(0.001);
        index.index.insert(key.clone(), value.clone());

        // Test lookup
        assert_eq!(index.lookup(&key), Some(&value));
        assert_eq!(index.lookup(&[Value::Int(35), Value::Float(0.001)]), None);

        // Test size methods
        assert_eq!(index.len(), 1);
        assert!(!index.is_empty());
    }

    #[test]
    fn test_value_display() {
        assert_eq!(Value::Int(42).to_string(), "42");
        assert_eq!(Value::Float(3.14).to_string(), "3.14");
        assert_eq!(Value::String("hello".into()).to_string(), "hello");
        assert_eq!(Value::Null.to_string(), "null");
    }

    #[test]
    fn test_any_value_to_value_conversion() {
        assert_eq!(
            any_value_to_value(AnyValue::Int64(123)).unwrap(),
            Value::Int(123)
        );
        assert_eq!(
            any_value_to_value(AnyValue::Float64(1.23)).unwrap(),
            Value::Float(1.23)
        );
        assert_eq!(
            any_value_to_value(AnyValue::String("test")).unwrap(),
            Value::String("test".into())
        );
        assert_eq!(any_value_to_value(AnyValue::Null).unwrap(), Value::Null);

        // Test unsupported type
        assert!(any_value_to_value(AnyValue::Boolean(true)).is_err());
    }

    #[test]
    fn test_extract_value_from_series() {
        // Test with Series now
        let s = Series::new("a".into(), &[Some(1i64), None, Some(3i64)]);
        assert_eq!(extract_value_from_series(&s, 0).unwrap(), Value::Int(1));
        assert_eq!(extract_value_from_series(&s, 1).unwrap(), Value::Null);
        assert_eq!(extract_value_from_series(&s, 2).unwrap(), Value::Int(3));
        assert!(extract_value_from_series(&s, 3).is_err());
    }

    #[test]
    fn test_build_lookup_index_single_key() -> PolarsResult<()> {
        let df = df!(
            "id" => &[1, 2, 3, 1],
            "value" => &["a", "b", "c", "d"]
        )?;
        let (index_map, _dtype) = build_lookup_index(&df, &["id".to_string()], "value")?;
        assert_eq!(index_map.len(), 3);
        assert_eq!(
            index_map.get(&vec![Value::Int(1)]),
            Some(&Value::String("d".into()))
        );
        Ok(())
    }

    #[test]
    fn test_build_lookup_index_multi_key() -> PolarsResult<()> {
        let df = df!(
            "key1" => &["A", "A", "B", "A"],
            "key2" => &[1, 2, 1, 1],
            "value" => &[10.1, 20.2, 30.3, 40.4]
        )?;
        let key_cols = ["key1".to_string(), "key2".to_string()];
        let value_col = "value";
        let (index_map, _dtype) = build_lookup_index(&df, &key_cols, value_col)?;
        assert_eq!(index_map.len(), 3);
        assert_eq!(
            index_map.get(&vec![Value::String("A".into()), Value::Int(1)]),
            Some(&Value::Float(40.4))
        );
        Ok(())
    }

    #[test]
    fn test_build_lookup_index_with_nulls() -> PolarsResult<()> {
        let df = df!(
            "key1" => &[Some("A"), None, Some("B"), Some("A")],
            "key2" => &[Some(1), Some(2), None, Some(1)],
            "value" => &[Some(10.0), Some(20.0), Some(30.0), None::<f64>]
        )?;
        let key_cols = ["key1".to_string(), "key2".to_string()];
        let value_col = "value";
        let (index_map, _dtype) = build_lookup_index(&df, &key_cols, value_col)?;
        assert_eq!(index_map.len(), 3);
        assert_eq!(
            index_map.get(&vec![Value::String("A".into()), Value::Int(1)]),
            Some(&Value::Null)
        );
        Ok(())
    }

    #[test]
    fn test_build_lookup_index_mortality_example() -> PolarsResult<()> {
        let df_mortality = df!(
            "age-last" => &[31i64, 31, 31, 31, 33, 33, 33, 33, 34, 34, 34, 34],
            "gender_smoking" => &["MNS", "FNS", "MS", "FS", "MNS", "FNS", "MS", "FS", "MNS", "FNS", "MS", "FS"],
            "mortality_rate" => &[0.0012f64, 0.0011, 0.0022, 0.0020, 0.0013, 0.0012, 0.0023, 0.0021, 0.0014, 0.0013, 0.0024, 0.0022]
        )?;
        let key_cols = ["age-last".to_string(), "gender_smoking".to_string()];
        let value_col = "mortality_rate";
        let (index_map, _dtype) = build_lookup_index(&df_mortality, &key_cols, value_col)?;
        assert_eq!(index_map.len(), 12);
        assert_eq!(
            index_map.get(&vec![Value::Int(31), Value::String("MNS".into())]),
            Some(&Value::Float(0.0012))
        );
        Ok(())
    }

    #[test]
    fn test_build_lookup_index_lapse_example() -> PolarsResult<()> {
        let df_lapse = df!(
            "policy_duration" => &[1i64, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24],
            "lapse_rate" => &[0.03f64, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11]
        )?;
        let key_cols = ["policy_duration".to_string()];
        let value_col = "lapse_rate";
        let (index_map, _dtype) = build_lookup_index(&df_lapse, &key_cols, value_col)?;
        assert_eq!(index_map.len(), 24);
        assert_eq!(
            index_map.get(&vec![Value::Int(1)]),
            Some(&Value::Float(0.03))
        );
        Ok(())
    }

    // ... Vector Lookup Tests ...

    fn setup_mortality_registry() -> Result<(), RegistryError> {
        reset_global_registry();
        let df_mortality = df!(
            "age-last" => &[31i64, 31, 31, 31, 33, 33, 33, 33, 34, 34, 34, 34],
            "gender_smoking" => &["MNS", "FNS", "MS", "FS", "MNS", "FNS", "MS", "FS", "MNS", "FNS", "MS", "FS"],
            "mortality_rate" => &[0.0012f64, 0.0011, 0.0022, 0.0020, 0.0013, 0.0012, 0.0023, 0.0021, 0.0014, 0.0013, 0.0024, 0.0022]
        ).expect("Failed to create mortality DataFrame");
        register_table(
            "mortality_rates",
            df_mortality,
            vec!["age-last".to_string(), "gender_smoking".to_string()],
            "mortality_rate",
        )
    }

    #[test]
    fn test_lookup_vector_with_nulls_in_key_vector() -> Result<(), Box<dyn std::error::Error>> {
        setup_mortality_registry()?;
        let registry = get_registry();
        let age_list_values = vec![
            Some(Series::new("".into(), &[31i64])),
            None,
            Some(Series::new("".into(), &[34i64])),
        ];
        let age_key_list_with_null = ListChunked::from_iter(age_list_values.into_iter())
            .into_series()
            .with_name("age-last".into());
        let gs_key_scalar = Series::new("gender_smoking".into(), &["MNS"]);
        let result_series = registry.lookup_vector(
            "mortality_rates",
            &[&age_key_list_with_null, &gs_key_scalar],
        )?;

        // Construct expected value correctly using append_null for None case
        let expected_values: Vec<Option<f64>> = vec![Some(0.0012), None, Some(0.0014)];
        let mut expected_builder = get_list_builder(
            &DataType::Float64,
            expected_values.len(),
            expected_values.len(),
            "mortality_rate".into(),
        );
        for val_opt in &expected_values {
            // Iterate over reference
            match val_opt {
                Some(val) => {
                    expected_builder.append_series(&Series::new("".into(), &[Some(*val)]))?
                }
                None => expected_builder.append_null(),
            }
        }
        let expected_series = expected_builder.finish().into_series();

        // Detailed comparison instead of just .equals()
        assert_eq!(
            result_series.len(),
            expected_series.len(),
            "Series length mismatch"
        );
        assert_eq!(
            result_series.dtype(),
            expected_series.dtype(),
            "Series dtype mismatch"
        );

        let result_ca = result_series.list()?;
        let expected_ca = expected_series.list()?;

        for i in 0..result_ca.len() {
            // get returns Option<Box<dyn Array>>
            let res_opt_arr: Option<Box<dyn polars_arrow::array::Array>> = result_ca.get(i);
            let exp_opt_arr: Option<Box<dyn polars_arrow::array::Array>> = expected_ca.get(i);

            // Match on references to avoid moving the values
            match (&res_opt_arr, &exp_opt_arr) {
                (Some(res_arr), Some(exp_arr)) => {
                    // Convert Array to Series, providing explicit type for .into()
                    // Pass the owned Box directly to try_from
                    let res_inner_series =
                        Series::try_from((<&str as Into<PlSmallStr>>::into(""), res_arr.clone()))?;
                    let exp_inner_series =
                        Series::try_from((<&str as Into<PlSmallStr>>::into(""), exp_arr.clone()))?;

                    // Now get Float64Chunked from the Series
                    let res_f64 = res_inner_series.f64()?;
                    let exp_f64 = exp_inner_series.f64()?;

                    // Compare the single float value inside
                    let res_val = res_f64.get(0); // Option<f64>
                    let exp_val = exp_f64.get(0); // Option<f64>
                    assert_eq!(
                        res_val, exp_val,
                        "Mismatch at index {} - Inner values: {:?} vs {:?}",
                        i, res_val, exp_val
                    );
                }
                (None, None) => { /* Both are null, which is expected */ }
                _ => {
                    // Now borrowing works fine here
                    panic!(
                        "Mismatch at index {} - Null/Some mismatch: {:?} vs {:?}",
                        i, res_opt_arr, exp_opt_arr
                    );
                }
            }
        }

        Ok(())
    }

    // ... test_lookup_vector_with_nulls_in_key_value ...
}
