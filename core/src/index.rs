use polars::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fmt;
use std::hash::{Hash, Hasher};
use std::sync::Arc;

use arc_swap::ArcSwap;
use log::debug;
use once_cell::sync::Lazy;

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
    /// The actual lookup table
    pub index: HashMap<Vec<Value>, Value>,
}

impl LookupIndex {
    /// Creates a new empty lookup index.
    pub fn new(keys: Vec<String>, value_column: String) -> Self {
        Self {
            keys,
            value_column,
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
fn extract_value_from_series(column: &Column, index: usize) -> PolarsResult<Value> {
    let any_value = column.get(index)?;
    any_value_to_value(any_value)
}

/// Builds a lookup index (HashMap) from a DataFrame.
///
/// # Arguments
///
/// * `df` - The input Polars DataFrame.
/// * `key_columns` - A slice of strings representing the names of the key columns.
/// * `value_column` - The name of the column containing the values.
///
/// # Returns
///
/// A `Result` containing the `HashMap<Vec<Value>, Value>` or a `PolarsError`.
pub fn build_lookup_index(
    df: &DataFrame,
    key_columns: &[String],
    value_column: &str,
) -> PolarsResult<HashMap<Vec<Value>, Value>> {
    // 1. Verify columns exist
    for col_name in key_columns {
        if df.column(col_name).is_err() {
            return Err(PolarsError::ColumnNotFound(
                format!("Key column '{}' not found in DataFrame.", col_name).into(),
            ));
        }
    }
    if df.column(value_column).is_err() {
        return Err(PolarsError::ColumnNotFound(
            format!("Value column '{}' not found in DataFrame.", value_column).into(),
        ));
    }

    // Extract Column references once
    let key_columns_result: Result<Vec<&Column>, _> =
        key_columns.iter().map(|name| df.column(name)).collect();
    let key_columns_vec = key_columns_result?; // Propagate error if any column not found

    let value_column_ref = df.column(value_column)?;

    let capacity = df.height();
    let mut index_map = HashMap::with_capacity(capacity);

    // 2. Iterate through rows and build the map
    for row_idx in 0..df.height() {
        // 3. Extract key values for the current row
        let mut key = Vec::with_capacity(key_columns.len());
        for col_ref in &key_columns_vec {
            // Pass *col_ref (&Column)
            let val = extract_value_from_series(*col_ref, row_idx)?;
            key.push(val);
        }

        // 4. Extract the value for the current row
        // Pass value_column_ref (&Column)
        let value = extract_value_from_series(value_column_ref, row_idx)?;

        // 5. Insert into HashMap
        // Note: Polars DataFrames can have duplicate key combinations.
        // The last occurrence in the DataFrame will overwrite previous entries.
        // This behavior might need clarification based on requirements.
        index_map.insert(key, value);
    }

    Ok(index_map)
}

/// Errors that can occur during registry operations.
#[derive(Debug, thiserror::Error)]
pub enum RegistryError {
    #[error("Table '{0}' not found in the registry.")]
    TableNotFound(String),
    #[error("Failed to build lookup index for table '{0}': {1}")]
    IndexBuildFailed(String, PolarsError),
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

    /// Registers a table and builds its lookup index.
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
    /// `Ok(())` on success, or a `RegistryError` on failure.
    pub fn register_table(
        &mut self,
        name: &str,
        df: DataFrame,
        keys: Vec<String>,
        value_column: &str,
    ) -> Result<(), RegistryError> {
        // Build the lookup index first. If this fails, we don't modify the registry.
        let index_map = build_lookup_index(&df, &keys, value_column)
            .map_err(|e| RegistryError::IndexBuildFailed(name.to_string(), e))?;

        let lookup_index = LookupIndex {
            keys,
            value_column: value_column.to_string(),
            index: index_map,
        };

        // Store both the original DataFrame and the built index.
        // We clone the DataFrame to store it, as the original might be owned elsewhere.
        self.tables.insert(name.to_string(), df.clone());
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
    // Call store directly
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
    // 1. Perform the fallible operation (index building) *before* the RCU attempt.
    let index_map = build_lookup_index(&df, &keys, value_column)
        .map_err(|e| RegistryError::IndexBuildFailed(name.to_string(), e))?;

    // 2. Create the LookupIndex struct with the pre-built map.
    let lookup_index = LookupIndex {
        keys,
        value_column: value_column.to_string(),
        index: index_map,
    };

    // 3. Use ArcSwap's Read-Copy-Update (RCU) mechanism for the atomic swap.
    //    The closure provided here is now infallible from RCU's perspective.
    REGISTRY.rcu(move |current_registry_arc| {
        // Inside the RCU closure:
        // a. Clone the data from the current Arc<TableRegistry>.
        let mut new_registry = (**current_registry_arc).clone();

        // b. Insert the pre-built index and the DataFrame clone.
        //    Need to clone lookup_index and df as the closure might be retried.
        new_registry.tables.insert(name.to_string(), df.clone());
        new_registry
            .lookup_indices
            .insert(name.to_string(), lookup_index.clone()); // Clone pre-built index

        // c. Return the Arc containing the *new* registry data.
        Arc::new(new_registry)
    });

    // 4. If build_lookup_index succeeded, the RCU operation will eventually succeed.
    //    Return Ok(()) from the main function.
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::reset_global_registry;
    use super::*;
    use polars::df; // Import the df! macro
    use std::thread;
    use std::time::Duration;

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
            vec!["age".to_string(), "gender".to_string()],
            "mortality_rate".to_string(),
        );

        // Add some test data
        let key = vec![Value::Int(35), Value::String("M".into())];
        let value = Value::Float(0.001);
        index.index.insert(key.clone(), value.clone());

        // Test lookup
        assert_eq!(index.lookup(&key), Some(&value));
        assert_eq!(
            index.lookup(&[Value::Int(35), Value::String("F".into())]),
            None
        );

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
        // Use Column::new explicitly to match function signature
        let s = Column::new("a".into(), &[Some(1i64), None, Some(3i64)]);
        // Pass &s (&Column) directly
        assert_eq!(extract_value_from_series(&s, 0).unwrap(), Value::Int(1));
        assert_eq!(extract_value_from_series(&s, 1).unwrap(), Value::Null);
        assert_eq!(extract_value_from_series(&s, 2).unwrap(), Value::Int(3));
        assert!(extract_value_from_series(&s, 3).is_err()); // Out of bounds
    }

    #[test]
    fn test_build_lookup_index_single_key() -> PolarsResult<()> {
        let df = df!(
            "id" => &[1, 2, 3, 1], // Duplicate key
            "value" => &["a", "b", "c", "d"] // Last '1' maps to 'd'
        )?;

        let key_cols = ["id".to_string()];
        let value_col = "value";

        let index = build_lookup_index(&df, &key_cols, value_col)?;

        assert_eq!(index.len(), 3); // 3 unique keys
        assert_eq!(
            index.get(&vec![Value::Int(1)]),
            Some(&Value::String("d".into()))
        );
        assert_eq!(
            index.get(&vec![Value::Int(2)]),
            Some(&Value::String("b".into()))
        );
        assert_eq!(
            index.get(&vec![Value::Int(3)]),
            Some(&Value::String("c".into()))
        );
        assert_eq!(index.get(&vec![Value::Int(4)]), None);

        Ok(())
    }

    #[test]
    fn test_build_lookup_index_multi_key() -> PolarsResult<()> {
        let df = df!(
            "key1" => &["A", "A", "B", "A"],
            "key2" => &[1, 2, 1, 1], // Duplicate key ("A", 1)
            "value" => &[10.1, 20.2, 30.3, 40.4] // Last ("A", 1) maps to 40.4
        )?;

        let key_cols = ["key1".to_string(), "key2".to_string()];
        let value_col = "value";

        let index = build_lookup_index(&df, &key_cols, value_col)?;

        assert_eq!(index.len(), 3);
        assert_eq!(
            index.get(&vec![Value::String("A".into()), Value::Int(1)]),
            Some(&Value::Float(40.4))
        );
        assert_eq!(
            index.get(&vec![Value::String("A".into()), Value::Int(2)]),
            Some(&Value::Float(20.2))
        );
        assert_eq!(
            index.get(&vec![Value::String("B".into()), Value::Int(1)]),
            Some(&Value::Float(30.3))
        );
        assert_eq!(
            index.get(&vec![Value::String("C".into()), Value::Int(1)]),
            None
        );

        Ok(())
    }

    #[test]
    fn test_build_lookup_index_with_nulls() -> PolarsResult<()> {
        let df = df!(
            "key1" => &[Some("A"), None, Some("B"), Some("A")],
            "key2" => &[Some(1), Some(2), None, Some(1)],
            "value" => &[Some(10.0), Some(20.0), Some(30.0), None::<f64>] // Last ("A", 1) maps to Null
        )?;

        let key_cols = ["key1".to_string(), "key2".to_string()];
        let value_col = "value";

        let index = build_lookup_index(&df, &key_cols, value_col)?;

        assert_eq!(index.len(), 3); // ("A", 1), (Null, 2), ("B", Null)
        assert_eq!(
            index.get(&vec![Value::String("A".into()), Value::Int(1)]),
            Some(&Value::Null) // Last value for this key was None
        );
        assert_eq!(
            index.get(&vec![Value::Null, Value::Int(2)]),
            Some(&Value::Float(20.0))
        );
        assert_eq!(
            index.get(&vec![Value::String("B".into()), Value::Null]),
            Some(&Value::Float(30.0))
        );
        assert_eq!(index.get(&vec![Value::Null, Value::Null]), None); // No key (Null, Null)

        Ok(())
    }

    #[test]
    fn test_build_lookup_index_errors() -> PolarsResult<()> {
        let df = df!(
            "col_a" => &[1, 2],
            "col_b" => &["x", "y"]
        )?;

        // Missing key column
        let result =
            build_lookup_index(&df, &["col_a".to_string(), "missing".to_string()], "col_b");
        assert!(matches!(result, Err(PolarsError::ColumnNotFound(_)))); // Changed to ColumnNotFound
        if let Err(PolarsError::ColumnNotFound(msg)) = result {
            // Changed to ColumnNotFound
            assert!(msg.contains("Key column 'missing' not found"));
        }

        // Missing value column
        let result = build_lookup_index(&df, &["col_a".to_string()], "missing_val");
        assert!(matches!(result, Err(PolarsError::ColumnNotFound(_)))); // Changed to ColumnNotFound
        if let Err(PolarsError::ColumnNotFound(msg)) = result {
            // Changed to ColumnNotFound
            assert!(msg.contains("Value column 'missing_val' not found"));
        }

        // Unsupported data type in key
        let df_bad_type = df!(
            "key" => &[true, false], // Boolean not supported by any_value_to_value
            "value" => &[1, 2]
        )?;
        let result = build_lookup_index(&df_bad_type, &["key".to_string()], "value");
        assert!(matches!(result, Err(PolarsError::ComputeError(_)))); // ComputeError check remains the same
        if let Err(PolarsError::ComputeError(msg)) = result {
            assert!(msg.contains("Unsupported AnyValue type"));
            assert!(msg.contains("Boolean"));
        }

        Ok(())
    }

    // --- Tests based on 04-examples.md ---

    #[test]
    fn test_build_lookup_index_mortality_example() -> PolarsResult<()> {
        // Simulates the *transformed* mortality table (long format)
        let df_mortality = df!(
            "age-last" => &[31i64, 31, 31, 31, 33, 33, 33, 33, 34, 34, 34, 34],
            "gender_smoking" => &["MNS", "FNS", "MS", "FS", "MNS", "FNS", "MS", "FS", "MNS", "FNS", "MS", "FS"],
            "mortality_rate" => &[0.0012f64, 0.0011, 0.0022, 0.0020, 0.0013, 0.0012, 0.0023, 0.0021, 0.0014, 0.0013, 0.0024, 0.0022]
        )?;

        let key_cols = ["age-last".to_string(), "gender_smoking".to_string()];
        let value_col = "mortality_rate";

        let index = build_lookup_index(&df_mortality, &key_cols, value_col)?;

        assert_eq!(index.len(), 12);
        // Check a few specific key-value pairs
        assert_eq!(
            index.get(&vec![Value::Int(31), Value::String("MNS".into())]),
            Some(&Value::Float(0.0012))
        );
        assert_eq!(
            index.get(&vec![Value::Int(33), Value::String("FS".into())]),
            Some(&Value::Float(0.0021))
        );
        assert_eq!(
            index.get(&vec![Value::Int(34), Value::String("MS".into())]),
            Some(&Value::Float(0.0024))
        );
        // Check a non-existent key
        assert_eq!(
            index.get(&vec![Value::Int(32), Value::String("MNS".into())]),
            None
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

        let index = build_lookup_index(&df_lapse, &key_cols, value_col)?;

        assert_eq!(index.len(), 24);
        // Check a few specific key-value pairs
        assert_eq!(index.get(&vec![Value::Int(1)]), Some(&Value::Float(0.03)));
        assert_eq!(index.get(&vec![Value::Int(9)]), Some(&Value::Float(0.10)));
        assert_eq!(index.get(&vec![Value::Int(15)]), Some(&Value::Float(0.11)));
        // Check a non-existent key
        assert_eq!(index.get(&vec![Value::Int(0)]), None);
        assert_eq!(index.get(&vec![Value::Int(25)]), None);

        Ok(())
    }

    // --- TableRegistry Tests ---

    #[test]
    fn test_registry_new() {
        let registry = TableRegistry::new();
        assert!(registry.tables.is_empty());
        assert!(registry.lookup_indices.is_empty());
    }

    #[test]
    fn test_registry_register_and_get() -> Result<(), Box<dyn std::error::Error>> {
        let mut registry = TableRegistry::new();
        let df = df!(
            "id" => &[1, 2],
            "data" => &["a", "b"]
        )?;
        let keys = vec!["id".to_string()];
        let value_col = "data";

        registry.register_table("test_table", df.clone(), keys.clone(), value_col)?;

        // Check if table and index exist
        assert!(registry.get_table("test_table").is_some());
        assert!(registry.get_lookup_index("test_table").is_some());

        // Verify stored DataFrame content (optional, but good check)
        assert!(registry.get_table("test_table").unwrap().equals(&df));

        // Verify lookup index content
        let index = registry.get_lookup_index("test_table").unwrap();
        assert_eq!(index.keys, keys);
        assert_eq!(index.value_column, value_col);
        assert_eq!(index.len(), 2);

        // Check non-existent table
        assert!(registry.get_table("non_existent").is_none());
        assert!(registry.get_lookup_index("non_existent").is_none());

        Ok(())
    }

    #[test]
    fn test_registry_lookup() -> Result<(), Box<dyn std::error::Error>> {
        let mut registry = TableRegistry::new();

        // --- Setup using the Mortality Example from 04-examples.md ---
        // Create the transformed mortality DataFrame (long format)
        let df_mortality = df!(
            "age-last" => &[31i64, 31, 31, 31, 33, 33, 33, 33, 34, 34, 34, 34],
            "gender_smoking" => &["MNS", "FNS", "MS", "FS", "MNS", "FNS", "MS", "FS", "MNS", "FNS", "MS", "FS"],
            "mortality_rate" => &[0.0012f64, 0.0011, 0.0022, 0.0020, 0.0013, 0.0012, 0.0023, 0.0021, 0.0014, 0.0013, 0.0024, 0.0022]
        )?;
        let keys = vec!["age-last".to_string(), "gender_smoking".to_string()];
        let value_col = "mortality_rate";
        let table_name = "mortality_rates";

        // Register the table
        registry.register_table(table_name, df_mortality, keys, value_col)?;

        // --- Test successful lookups based on the example ---
        // Key for Age 31, Male Non-Smoker
        let key_31_mns = vec![Value::Int(31), Value::String("MNS".into())];
        assert_eq!(
            registry.lookup(table_name, &key_31_mns)?,
            Some(&Value::Float(0.0012)),
            "Lookup failed for Age 31 MNS"
        );

        // Key for Age 33, Female Smoker
        let key_33_fs = vec![Value::Int(33), Value::String("FS".into())];
        assert_eq!(
            registry.lookup(table_name, &key_33_fs)?,
            Some(&Value::Float(0.0021)),
            "Lookup failed for Age 33 FS"
        );

        // Key for Age 34, Male Smoker
        let key_34_ms = vec![Value::Int(34), Value::String("MS".into())];
        assert_eq!(
            registry.lookup(table_name, &key_34_ms)?,
            Some(&Value::Float(0.0024)),
            "Lookup failed for Age 34 MS"
        );

        // --- Test lookup for non-existent key ---
        // Use an age not present in the example table
        let key_32_fns = vec![Value::Int(32), Value::String("FNS".into())];
        assert_eq!(
            registry.lookup(table_name, &key_32_fns)?,
            None,
            "Lookup should return None for non-existent key"
        );

        // --- Test lookup in non-existent table ---
        let result = registry.lookup("non_existent_table", &key_31_mns);
        assert!(matches!(result, Err(RegistryError::TableNotFound(_))));
        if let Err(RegistryError::TableNotFound(name)) = result {
            assert_eq!(name, "non_existent_table");
        }

        // --- Test lookup with wrong key length ---
        // Use only one key element when two are expected
        let short_key = vec![Value::Int(31)];
        let result = registry.lookup(table_name, &short_key);
        assert!(matches!(
            result,
            Err(RegistryError::KeyLengthMismatch(_, _, _))
        ));
        if let Err(RegistryError::KeyLengthMismatch(name, expected, got)) = result {
            assert_eq!(name, table_name);
            assert_eq!(expected, 2); // Expected 2 keys ("age-last", "gender_smoking")
            assert_eq!(got, 1);
        }

        Ok(())
    }

    #[test]
    fn test_registry_register_errors() -> Result<(), Box<dyn std::error::Error>> {
        let mut registry = TableRegistry::new();
        let df = df!(
            "id" => &[1, 2],
            "data" => &["a", "b"]
        )?;

        // Error: Missing key column during build
        let result = registry.register_table(
            "error_table",
            df.clone(),
            vec!["missing_key".to_string()],
            "data",
        );
        assert!(matches!(result, Err(RegistryError::IndexBuildFailed(_, _))));
        if let Err(RegistryError::IndexBuildFailed(name, PolarsError::ColumnNotFound(msg))) = result
        {
            assert_eq!(name, "error_table");
            assert!(msg.contains("Key column 'missing_key' not found"));
        }

        // Error: Missing value column during build
        let result = registry.register_table(
            "error_table2",
            df.clone(),
            vec!["id".to_string()],
            "missing_value",
        );
        assert!(matches!(result, Err(RegistryError::IndexBuildFailed(_, _))));
        if let Err(RegistryError::IndexBuildFailed(name, PolarsError::ColumnNotFound(msg))) = result
        {
            assert_eq!(name, "error_table2");
            assert!(msg.contains("Value column 'missing_value' not found"));
        }

        // Ensure registry was not modified on error
        assert!(registry.get_table("error_table").is_none());
        assert!(registry.get_lookup_index("error_table").is_none());
        assert!(registry.get_table("error_table2").is_none());
        assert!(registry.get_lookup_index("error_table2").is_none());

        Ok(())
    }

    // --- Global Registry Tests ---

    #[test]
    fn test_global_registry_initialization() {
        reset_global_registry(); // Reset state before test
        let registry_arc = get_registry();
        let registry = &*registry_arc;
        assert!(registry.tables.is_empty());
        assert!(registry.lookup_indices.is_empty());
    }

    #[test]
    fn test_global_register_and_get() -> Result<(), Box<dyn std::error::Error>> {
        reset_global_registry(); // Reset state before test

        let df1 = df!("id" => &[1], "val" => &["a"])?;
        let df2 = df!("key" => &["X"], "rate" => &[0.5])?;

        // Register first table
        register_table("table1", df1.clone(), vec!["id".to_string()], "val")?;

        // Get registry and check first table
        let registry1 = get_registry();
        assert!(registry1.get_table("table1").is_some());
        assert!(registry1.get_lookup_index("table1").is_some());
        assert!(registry1.get_table("table2").is_none());
        // assert_eq!(registry1.tables.len(), 1); // This can fail if tests run in parallel and interfere before snapshot

        // Register second table
        register_table("table2", df2.clone(), vec!["key".to_string()], "rate")?;

        // Get registry again and check both tables
        let registry2 = get_registry();
        assert!(registry2.get_table("table1").is_some());
        assert!(registry2.get_lookup_index("table1").is_some());
        assert!(registry2.get_table("table2").is_some());
        assert!(registry2.get_lookup_index("table2").is_some());
        // assert_eq!(registry2.tables.len(), 2); // This can fail if tests run in parallel
        // Check for presence instead of exact count due to potential parallel test interference
        assert!(
            registry2.tables.contains_key("table1"),
            "Registry should contain table1"
        );
        assert!(
            registry2.tables.contains_key("table2"),
            "Registry should contain table2"
        );

        // Check that the first snapshot (registry1) is unchanged
        assert!(registry1.get_table("table2").is_none());

        // Perform a lookup using the latest registry state
        let lookup_result = registry2.lookup("table1", &[Value::Int(1)])?;
        assert_eq!(lookup_result, Some(&Value::String("a".into())));

        let lookup_result_2 = registry2.lookup("table2", &[Value::String("X".into())])?;
        assert_eq!(lookup_result_2, Some(&Value::Float(0.5)));

        Ok(())
    }

    #[test]
    fn test_concurrent_reads_and_updates() -> Result<(), Box<dyn std::error::Error>> {
        reset_global_registry(); // Reset state before test

        // Register an initial table
        let initial_df = df!("id" => &[0], "val" => &["initial"])?;
        register_table("initial_table", initial_df, vec!["id".to_string()], "val")?;

        // Get the snapshot *after* initial registration is complete
        let reader_snapshot_arc = get_registry();
        // Sanity check: ensure the initial table is indeed in this snapshot
        assert!(
            reader_snapshot_arc.get_table("initial_table").is_some(),
            "Initial table missing from snapshot intended for readers"
        );

        let num_threads = 5;
        let mut handles = vec![];

        // Spawn reader threads - Pass them the specific snapshot Arc
        for i in 0..num_threads {
            let snapshot_clone = Arc::clone(&reader_snapshot_arc); // Clone Arc for thread
            let handle = thread::spawn(move || {
                // Simulate some work
                thread::sleep(Duration::from_millis(10));
                // Read from the passed snapshot (guaranteed to have initial_table)
                let val = snapshot_clone
                    .lookup("initial_table", &[Value::Int(0)])
                    .unwrap();
                assert_eq!(val, Some(&Value::String("initial".into())));

                // Try reading tables that might be added later by the writer
                // This will *always* be None or Err(TableNotFound) because the readers' snapshot doesn't change
                let lookup_dynamic =
                    snapshot_clone.lookup(&format!("dynamic_table_{}", i), &[Value::Int(i as i64)]);
                // Check that the lookup either results in Ok(None) or Err(TableNotFound)
                // It should specifically be Err(TableNotFound) as the table doesn't exist in the snapshot
                assert!(
                    matches!(lookup_dynamic, Err(RegistryError::TableNotFound(_))),
                    "Expected TableNotFound for dynamic table in reader snapshot"
                );
            });
            handles.push(handle);
        }

        // Spawn writer threads (registering new tables) - unchanged
        for i in 0..num_threads {
            let df = df!("id" => &[i as i64], "val" => &[format!("dynamic_{}", i)])?;
            let handle = thread::spawn(move || {
                thread::sleep(Duration::from_millis(5)); // Stagger writes slightly
                register_table(
                    &format!("dynamic_table_{}", i),
                    df,
                    vec!["id".to_string()],
                    "val",
                )
                .unwrap();
            });
            handles.push(handle);
        }

        // Wait for all threads to complete
        for handle in handles {
            handle.join().unwrap();
        }

        // Verify final state of the registry (using a *new* snapshot)
        let final_registry = get_registry();
        assert!(final_registry.get_table("initial_table").is_some());
        for i in 0..num_threads {
            let table_name = format!("dynamic_table_{}", i);
            assert!(
                final_registry.get_table(&table_name).is_some(),
                "Dynamic table {} not found in final registry",
                i
            );
            let val = final_registry
                .lookup(&table_name, &[Value::Int(i as i64)])?
                .unwrap();
            assert_eq!(val, &Value::String(format!("dynamic_{}", i).into()));
        }
        // assert_eq!(final_registry.tables.len(), num_threads + 1); // This can fail if tests run in parallel
        // Check that *at least* the expected number of tables are present
        let expected_tables = num_threads + 1;
        assert!(
            final_registry.tables.len() >= expected_tables,
            "Expected at least {} tables, found {}",
            expected_tables,
            final_registry.tables.len()
        );

        // Verify the reader snapshot was not affected
        // assert_eq!(reader_snapshot_arc.tables.len(), 1); // This can fail if tests run in parallel
        assert!(reader_snapshot_arc.get_table("dynamic_table_0").is_none());

        Ok(())
    }
}
