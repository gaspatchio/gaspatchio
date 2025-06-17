use super::table::AssumptionTable;
use arc_swap::ArcSwap;
use log::debug;
use once_cell::sync::Lazy;
use polars::prelude::*;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

/// A registry that stores assumption tables for lookup operations.
#[derive(Debug, Default, Clone)]
pub struct AssumptionTableRegistry {
    /// Pre-built assumption tables
    assumption_tables: HashMap<String, Arc<AssumptionTable>>,
}

// --- Global Registry Definition ---

// Define the static REGISTRY using Lazy for one-time initialization
// and ArcSwap for atomic updates.
static GLOBAL_REGISTRY: Lazy<ArcSwap<AssumptionTableRegistry>> = Lazy::new(|| {
    // Initialize with an empty AssumptionTableRegistry wrapped in ArcSwap
    ArcSwap::from_pointee(AssumptionTableRegistry::default())
});

// Add a Mutex to serialize registration attempts
static REGISTRATION_LOCK: Lazy<Mutex<()>> = Lazy::new(|| Mutex::new(()));

// Helper function to acquire the registration lock with consistent error handling
fn acquire_registration_lock() -> PolarsResult<std::sync::MutexGuard<'static, ()>> {
    REGISTRATION_LOCK
        .lock()
        .map_err(|_| polars_err!(ComputeError: "Registration lock poisoned"))
}

// Helper function to update the global registry atomically
fn update_global_registry<F>(operation_name: &str, table_name: &str, update_fn: F) -> PolarsResult<()>
where
    F: FnOnce(&mut AssumptionTableRegistry) -> PolarsResult<()>,
{
    let current_arc = GLOBAL_REGISTRY.load_full();
    let mut new_registry = (*current_arc).clone();
    
    match update_fn(&mut new_registry) {
        Ok(()) => {
            GLOBAL_REGISTRY.store(Arc::new(new_registry));
            debug!("Successfully {} table '{}' in global registry", operation_name, table_name);
            Ok(())
        }
        Err(e) => {
            log::error!("Failed to {} table '{}': {}", operation_name, table_name, e);
            Err(e)
        }
    }
}

/// Gets a thread-safe snapshot (Arc) of the current global AssumptionTableRegistry.
/// Clients should hold onto this snapshot for the duration of their operation
/// rather than calling get_global_assumption_registry() repeatedly.
pub fn get_global_assumption_registry() -> Arc<AssumptionTableRegistry> {
    GLOBAL_REGISTRY.load_full()
}

/// Resets the global assumption registry to an empty state. For testing purposes only.
pub fn reset_global_assumption_registry() {
    debug!("Attempting to reset global assumption registry...");
    GLOBAL_REGISTRY.store(Arc::new(AssumptionTableRegistry::default()));
    let registry = get_global_assumption_registry(); // Get snapshot after reset
    debug!(
        "Global assumption registry reset. Current table count: {}",
        registry.assumption_tables.len()
    );
}

/// Registers a table in the global, thread-safe assumption registry using Read-Copy-Update,
/// guarded by a Mutex to ensure atomic check-then-update semantics.
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
/// `Ok(())` on success, or a `PolarsError` if table building fails.
pub fn register_assumption_table_global(
    name: String,
    df: DataFrame,
    keys: Vec<String>,
    value_column: String,
) -> PolarsResult<()> {
    let _guard = acquire_registration_lock()?;

    // Check for existing table inside the lock
    let current_registry = get_global_assumption_registry();
    if current_registry.get_table(&name).is_some() {
        return Err(polars_err!(ComputeError: "assumption table '{}' already exists", name));
    }
    drop(current_registry);

    // Atomically update registry
    update_global_registry("registered", &name, |registry| {
        registry.register_table(name.clone(), df, keys, value_column)
    })
}

/// Registers or replaces a table in the global registry. This function is idempotent and
/// allows re-registration of tables, making it suitable for interactive environments like
/// Jupyter notebooks or test scenarios where models may be run multiple times.
///
/// # Arguments
///
/// * `name` - The name to register the table under.
/// * `df` - The DataFrame containing the table data.
/// * `keys` - A vector of column names to use as lookup keys.
/// * `value_column` - The name of the column containing the values.
/// * `force_replace` - If true, forcefully replace existing tables. If false, silently skip.
///
/// # Returns
///
/// `Ok(())` on success, or a `PolarsError` if table building fails.
pub fn register_or_replace_assumption_table_global(
    name: String,
    df: DataFrame,
    keys: Vec<String>,
    value_column: String,
    force_replace: bool,
) -> PolarsResult<()> {
    let _guard = acquire_registration_lock()?;

    // Check for existing table inside the lock
    let current_registry = get_global_assumption_registry();
    let table_exists = current_registry.get_table(&name).is_some();
    drop(current_registry);

    if table_exists && !force_replace {
        debug!(
            "Table '{}' already exists and force_replace=false, skipping registration",
            name
        );
        return Ok(());
    }

    // Atomically update registry
    let operation = if table_exists { "replaced" } else { "registered" };
    update_global_registry(operation, &name, |registry| {
        // Remove existing table if force_replace is true
        if table_exists && force_replace {
            registry.assumption_tables.remove(&name);
            debug!("Removed existing table '{}' for replacement", name);
        }
        registry.register_table(name.clone(), df, keys, value_column)
    })
}

/// Appends data to an existing table in the global registry using immutable rebuild approach.
/// This preserves hot path (lookup) performance by maintaining the same efficient data structures.
///
/// # Arguments
///
/// * `name` - The name of the existing table to append to.
/// * `df` - The DataFrame containing the new data to append.
/// * `keys` - A vector of column names to use as lookup keys (must match existing table).
/// * `value_column` - The name of the column containing the values (must match existing table).
///
/// # Returns
///
/// `Ok(())` on success, or a `PolarsError` if append fails due to validation or other errors.
pub fn append_to_assumption_table_global(
    name: String,
    df: DataFrame,
    keys: Vec<String>,
    value_column: String,
) -> PolarsResult<()> {
    let _guard = acquire_registration_lock()?;

    // Atomically update registry
    update_global_registry("appended to", &name, |registry| {
        registry.append_to_table(name.clone(), df, keys, value_column)
    })
}

/// Performs a lookup using the global registry.
///
/// This is the core logic function that accesses the globally shared
/// `AssumptionTableRegistry` and performs the lookup.
///
/// # Arguments
///
/// * `table_name` - The name of the registered table to use.
/// * `key_cols` - A slice of `&Series` representing the key columns.
///
/// # Returns
///
/// `Ok(Series)` containing the lookup results,
/// or `Err(PolarsError)` if the lookup fails.
pub fn lookup_assumption_global(table_name: &str, key_cols: &[&Series]) -> PolarsResult<Series> {
    let registry = get_global_assumption_registry(); // Get a thread-safe snapshot
    debug!(
        "Performing lookup for table '{}' in global registry. Registry table count: {}. Available tables: {:?}",
        table_name,
        registry.assumption_tables.len(),
        registry.list_tables()
    );

    registry.lookup(table_name, key_cols)
}

impl AssumptionTableRegistry {
    /// Creates a new empty registry.
    pub fn new() -> Self {
        Self::default()
    }

    /// Registers an assumption table built from a DataFrame.
    pub fn register_table(
        &mut self,
        name: String,
        df: DataFrame,
        keys: Vec<String>,
        value: String,
    ) -> PolarsResult<()> {
        let table = AssumptionTable::build(df, keys, value)?;
        debug!("assumption table registered: {:?}", name);
        self.assumption_tables.insert(name, Arc::new(table));
        Ok(())
    }

    /// Appends data to an existing assumption table using immutable rebuild approach.
    /// This method maintains optimal lookup performance by rebuilding the entire table
    /// with combined data rather than using interior mutability.
    pub fn append_to_table(
        &mut self,
        name: String,
        df: DataFrame,
        keys: Vec<String>,
        value: String,
    ) -> PolarsResult<()> {
        // Get existing table
        let existing_table = self.assumption_tables.get(&name).ok_or_else(|| {
            let available_tables = self.list_tables();
            polars_err!(
                ComputeError:
                "Table '{}' not found for append. Available tables: {:?}",
                name, available_tables
            )
        })?;

        // Build combined table using immutable rebuild approach
        let combined_table =
            AssumptionTable::build_combined(existing_table.as_ref(), df, keys, value)?;

        // Replace the Arc atomically (this is the core of the immutable approach)
        self.assumption_tables
            .insert(name.clone(), Arc::new(combined_table));

        debug!("Successfully appended data to table '{}'", name);
        Ok(())
    }

    /// Gets a reference to a registered assumption table.
    pub fn get_table(&self, name: &str) -> Option<&AssumptionTable> {
        debug!("assumption tables available: {:?}", self.list_tables());
        self.assumption_tables.get(name).map(|arc| arc.as_ref())
    }

    /// Performs a lookup on a registered table.
    pub fn lookup(&self, table_name: &str, key_cols: &[&Series]) -> PolarsResult<Series> {
        match self.get_table(table_name) {
            Some(table) => table.lookup_series(key_cols),
            None => Err(polars_err!(ComputeError: "assumption table '{}' not found", table_name)),
        }
    }

    /// Lists all registered table names.
    pub fn list_tables(&self) -> Vec<String> {
        self.assumption_tables.keys().cloned().collect()
    }

    /// Check if a table exists in the registry.
    pub fn table_exists(&self, name: &str) -> bool {
        self.assumption_tables.contains_key(name)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    // Test mutex to serialize global registry tests
    static TEST_MUTEX: Lazy<Mutex<()>> = Lazy::new(|| Mutex::new(()));

    #[test]
    fn test_assumption_table_registry_basics() {
        let registry = AssumptionTableRegistry::new();
        assert!(registry.get_table("test").is_none());
        assert!(registry.list_tables().is_empty());
    }

    #[test]
    fn test_register_and_lookup() -> PolarsResult<()> {
        let mut registry = AssumptionTableRegistry::new();

        // Create test data
        let df = df! {
            "age" => [25, 30, 35],
            "gender" => ["M", "F", "M"],
            "rate" => [0.1, 0.2, 0.15]
        }?;

        // Register the table
        registry.register_table(
            "mortality".to_string(),
            df,
            vec!["age".to_string(), "gender".to_string()],
            "rate".to_string(),
        )?;

        // Verify it's registered
        assert!(registry.get_table("mortality").is_some());
        assert_eq!(registry.list_tables().len(), 1);

        Ok(())
    }

    #[test]
    fn test_global_registry_basics() -> PolarsResult<()> {
        // Serialize access to global registry
        let _guard = TEST_MUTEX.lock().unwrap();

        // Reset global registry for clean test
        reset_global_assumption_registry();

        // Create test data
        let df = df! {
            "age" => [25, 30, 35],
            "rate" => [0.1, 0.2, 0.15]
        }?;

        // Register the table globally
        register_assumption_table_global(
            "test_global".to_string(),
            df,
            vec!["age".to_string()],
            "rate".to_string(),
        )?;

        // Verify it's registered in global registry
        let registry = get_global_assumption_registry();
        assert!(registry.get_table("test_global").is_some());
        assert_eq!(registry.list_tables().len(), 1);

        Ok(())
    }

    #[test]
    fn test_global_registry_duplicate_registration() -> PolarsResult<()> {
        // Serialize access to global registry
        let _guard = TEST_MUTEX.lock().unwrap();

        // Reset global registry for clean test
        reset_global_assumption_registry();

        // Create test data
        let df = df! {
            "age" => [25, 30],
            "rate" => [0.1, 0.2]
        }?;

        // Register the table globally
        register_assumption_table_global(
            "duplicate_test".to_string(),
            df.clone(),
            vec!["age".to_string()],
            "rate".to_string(),
        )?;

        // Try to register again - should fail
        let result = register_assumption_table_global(
            "duplicate_test".to_string(),
            df,
            vec!["age".to_string()],
            "rate".to_string(),
        );

        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("already exists"));

        Ok(())
    }

    #[test]
    fn test_registry_metadata_methods() -> PolarsResult<()> {
        let mut registry = AssumptionTableRegistry::new();

        // Initially empty
        assert_eq!(registry.list_tables().len(), 0);
        assert!(!registry.table_exists("nonexistent"));

        // Create test data
        let df1 = df! {
            "age" => [25, 30, 35],
            "rate" => [0.1, 0.2, 0.15]
        }?;

        let df2 = df! {
            "duration" => [1, 2, 3],
            "lapse_rate" => [0.05, 0.04, 0.03]
        }?;

        // Register two tables
        registry.register_table(
            "mortality".to_string(),
            df1,
            vec!["age".to_string()],
            "rate".to_string(),
        )?;

        registry.register_table(
            "lapse".to_string(),
            df2,
            vec!["duration".to_string()],
            "lapse_rate".to_string(),
        )?;

        // Test list_tables returns owned strings
        let table_names = registry.list_tables();
        assert_eq!(table_names.len(), 2);
        assert!(table_names.contains(&"mortality".to_string()));
        assert!(table_names.contains(&"lapse".to_string()));

        // Test table_exists
        assert!(registry.table_exists("mortality"));
        assert!(registry.table_exists("lapse"));
        assert!(!registry.table_exists("nonexistent"));

        Ok(())
    }

    #[test]
    fn test_global_registry_metadata() -> PolarsResult<()> {
        // Serialize access to global registry
        let _guard = TEST_MUTEX.lock().unwrap();

        // Reset global registry for clean test
        reset_global_assumption_registry();

        // Create test data
        let df = df! {
            "age" => [25, 30, 35],
            "gender" => ["M", "F", "M"],
            "rate" => [0.1, 0.2, 0.15]
        }?;

        // Register the table globally
        register_assumption_table_global(
            "metadata_test".to_string(),
            df,
            vec!["age".to_string(), "gender".to_string()],
            "rate".to_string(),
        )?;

        // Get registry snapshot and test metadata
        let registry = get_global_assumption_registry();

        // Test list_tables
        let tables = registry.list_tables();
        assert_eq!(tables.len(), 1);
        assert_eq!(tables[0], "metadata_test");

        // Test table_exists
        assert!(registry.table_exists("metadata_test"));
        assert!(!registry.table_exists("nonexistent"));

        // Test table metadata through get_table
        let table = registry.get_table("metadata_test").unwrap();
        assert_eq!(table.get_key_count(), 2);
        assert_eq!(table.get_key_name(0)?, "age");
        assert_eq!(table.get_key_name(1)?, "gender");

        let key_columns = table.get_key_columns();
        assert_eq!(key_columns.len(), 2);
        assert_eq!(key_columns[0], "age");
        assert_eq!(key_columns[1], "gender");

        Ok(())
    }

    #[test]
    fn test_registry_append_to_table() -> PolarsResult<()> {
        let mut registry = AssumptionTableRegistry::new();

        // Register base table
        let base_df = df! {
            "age" => [30, 31],
            "gender" => ["M", "F"],
            "rate" => [0.001, 0.0008]
        }?;

        registry.register_table(
            "mortality".to_string(),
            base_df,
            vec!["age".to_string(), "gender".to_string()],
            "rate".to_string(),
        )?;

        // Append new data
        let new_df = df! {
            "age" => [32, 33],
            "gender" => ["M", "F"],
            "rate" => [0.0012, 0.001]
        }?;

        registry.append_to_table(
            "mortality".to_string(),
            new_df,
            vec!["age".to_string(), "gender".to_string()],
            "rate".to_string(),
        )?;

        // Verify the table was updated
        let table = registry.get_table("mortality").unwrap();
        assert_eq!(table.entry_count(), 4); // 2 original + 2 appended

        // Test lookups work on appended data
        let age_series = Series::new("age".into(), &[30, 32, 33]);
        let gender_series = Series::new("gender".into(), &["M", "M", "F"]);
        let result = table.lookup_series(&[&age_series, &gender_series])?;

        let result_f64 = result.f64()?;
        assert!((result_f64.get(0).unwrap() - 0.001).abs() < 1e-10); // Original data
        assert!((result_f64.get(1).unwrap() - 0.0012).abs() < 1e-10); // Appended data
        assert!((result_f64.get(2).unwrap() - 0.001).abs() < 1e-10); // Appended data

        Ok(())
    }

    #[test]
    fn test_registry_append_table_not_found() -> PolarsResult<()> {
        let mut registry = AssumptionTableRegistry::new();

        let df = df! {
            "age" => [30],
            "rate" => [0.001]
        }?;

        let result = registry.append_to_table(
            "nonexistent".to_string(),
            df,
            vec!["age".to_string()],
            "rate".to_string(),
        );

        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("not found for append"));

        Ok(())
    }

    #[test]
    fn test_registry_append_incompatible_keys() -> PolarsResult<()> {
        let mut registry = AssumptionTableRegistry::new();

        // Register base table with 2 keys
        let base_df = df! {
            "age" => [30, 31],
            "gender" => ["M", "F"],
            "rate" => [0.001, 0.0008]
        }?;

        registry.register_table(
            "test".to_string(),
            base_df,
            vec!["age".to_string(), "gender".to_string()],
            "rate".to_string(),
        )?;

        // Try to append with different key count
        let new_df = df! {
            "age" => [32],
            "rate" => [0.0012]
        }?;

        let result = registry.append_to_table(
            "test".to_string(),
            new_df,
            vec!["age".to_string()], // Only 1 key instead of 2
            "rate".to_string(),
        );

        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("Key count mismatch"));

        Ok(())
    }

    #[test]
    fn test_global_append_functionality() -> PolarsResult<()> {
        // Serialize access to global registry
        let _guard = TEST_MUTEX.lock().unwrap();

        // Reset global registry for clean test
        reset_global_assumption_registry();

        // Register base table globally
        let base_df = df! {
            "duration" => [1, 2, 3],
            "lapse_rate" => [0.05, 0.04, 0.03]
        }?;

        register_assumption_table_global(
            "lapse".to_string(),
            base_df,
            vec!["duration".to_string()],
            "lapse_rate".to_string(),
        )?;

        // Append new data globally
        let new_df = df! {
            "duration" => [4, 5, 6],
            "lapse_rate" => [0.02, 0.01, 0.005]
        }?;

        append_to_assumption_table_global(
            "lapse".to_string(),
            new_df,
            vec!["duration".to_string()],
            "lapse_rate".to_string(),
        )?;

        // Verify the global table was updated
        let registry = get_global_assumption_registry();
        let table = registry.get_table("lapse").unwrap();
        assert_eq!(table.entry_count(), 6); // 3 original + 3 appended

        // Test lookups work through global registry
        let duration_series = Series::new("duration".into(), &[1, 4, 6]);
        let result = lookup_assumption_global("lapse", &[&duration_series])?;

        let result_f64 = result.f64()?;
        assert!((result_f64.get(0).unwrap() - 0.05).abs() < 1e-10); // Original
        assert!((result_f64.get(1).unwrap() - 0.02).abs() < 1e-10); // Appended
        assert!((result_f64.get(2).unwrap() - 0.005).abs() < 1e-10); // Appended

        Ok(())
    }

    #[test]
    fn test_global_append_table_not_found() -> PolarsResult<()> {
        // Serialize access to global registry
        let _guard = TEST_MUTEX.lock().unwrap();

        // Reset global registry for clean test
        reset_global_assumption_registry();

        let df = df! {
            "age" => [30],
            "rate" => [0.001]
        }?;

        let result = append_to_assumption_table_global(
            "nonexistent".to_string(),
            df,
            vec!["age".to_string()],
            "rate".to_string(),
        );

        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("not found for append"));

        Ok(())
    }

    #[test]
    fn test_global_append_duplicate_keys() -> PolarsResult<()> {
        // Serialize access to global registry
        let _guard = TEST_MUTEX.lock().unwrap();

        // Reset global registry for clean test
        reset_global_assumption_registry();

        // Register base table
        let base_df = df! {
            "age" => [30, 31],
            "rate" => [0.001, 0.0008]
        }?;

        register_assumption_table_global(
            "test".to_string(),
            base_df,
            vec!["age".to_string()],
            "rate".to_string(),
        )?;

        // Try to append duplicate key
        let duplicate_df = df! {
            "age" => [30], // Same as existing
            "rate" => [0.0012] // Different value
        }?;

        let result = append_to_assumption_table_global(
            "test".to_string(),
            duplicate_df,
            vec!["age".to_string()],
            "rate".to_string(),
        );

        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("Duplicate key found"));

        Ok(())
    }

    #[test]
    fn test_multiple_appends_preserves_all_data() -> PolarsResult<()> {
        // Test multiple consecutive appends to ensure all data is preserved
        let mut registry = AssumptionTableRegistry::new();

        // Register base table
        let base_df = df! {
            "category" => ["A"],
            "value" => [1.0]
        }?;

        registry.register_table(
            "multi_append".to_string(),
            base_df,
            vec!["category".to_string()],
            "value".to_string(),
        )?;

        // First append
        let append1_df = df! {
            "category" => ["B"],
            "value" => [2.0]
        }?;

        registry.append_to_table(
            "multi_append".to_string(),
            append1_df,
            vec!["category".to_string()],
            "value".to_string(),
        )?;

        // Second append
        let append2_df = df! {
            "category" => ["C"],
            "value" => [3.0]
        }?;

        registry.append_to_table(
            "multi_append".to_string(),
            append2_df,
            vec!["category".to_string()],
            "value".to_string(),
        )?;

        // Third append
        let append3_df = df! {
            "category" => ["D"],
            "value" => [4.0]
        }?;

        registry.append_to_table(
            "multi_append".to_string(),
            append3_df,
            vec!["category".to_string()],
            "value".to_string(),
        )?;

        // Verify all data is present
        let table = registry.get_table("multi_append").unwrap();
        assert_eq!(table.entry_count(), 4); // 1 original + 3 appends

        // Test all lookups work
        let category_series = Series::new("category".into(), &["A", "B", "C", "D"]);
        let result = table.lookup_series(&[&category_series])?;

        let result_f64 = result.f64()?;
        assert!((result_f64.get(0).unwrap() - 1.0).abs() < 1e-10); // Original
        assert!((result_f64.get(1).unwrap() - 2.0).abs() < 1e-10); // First append
        assert!((result_f64.get(2).unwrap() - 3.0).abs() < 1e-10); // Second append
        assert!((result_f64.get(3).unwrap() - 4.0).abs() < 1e-10); // Third append

        Ok(())
    }

    #[test]
    fn test_append_performance_characteristics() -> PolarsResult<()> {
        // Test append with larger dataset to verify performance is reasonable
        let mut registry = AssumptionTableRegistry::new();

        // Create base table with 100 entries
        let base_ages: Vec<i32> = (1..=100).collect();
        let base_rates: Vec<f64> = base_ages.iter().map(|&age| age as f64 * 0.001).collect();

        let base_df = df! {
            "age" => base_ages,
            "rate" => base_rates
        }?;

        registry.register_table(
            "large_table".to_string(),
            base_df,
            vec!["age".to_string()],
            "rate".to_string(),
        )?;

        // Append 50 more entries
        let new_ages: Vec<i32> = (101..=150).collect();
        let new_rates: Vec<f64> = new_ages.iter().map(|&age| age as f64 * 0.001).collect();

        let new_df = df! {
            "age" => new_ages,
            "rate" => new_rates
        }?;

        registry.append_to_table(
            "large_table".to_string(),
            new_df,
            vec!["age".to_string()],
            "rate".to_string(),
        )?;

        // Verify all data is present
        let table = registry.get_table("large_table").unwrap();
        assert_eq!(table.entry_count(), 150); // 100 original + 50 appended

        // Test spot check lookups from both original and appended data
        let test_ages = Series::new("age".into(), &[1, 50, 100, 101, 150]);
        let result = table.lookup_series(&[&test_ages])?;
        let result_f64 = result.f64()?;

        assert!((result_f64.get(0).unwrap() - 0.001).abs() < 1e-10); // Original
        assert!((result_f64.get(1).unwrap() - 0.050).abs() < 1e-10); // Original
        assert!((result_f64.get(2).unwrap() - 0.100).abs() < 1e-10); // Original
        assert!((result_f64.get(3).unwrap() - 0.101).abs() < 1e-10); // Appended
        assert!((result_f64.get(4).unwrap() - 0.150).abs() < 1e-10); // Appended

        Ok(())
    }

    #[test]
    fn test_register_or_replace_idempotent() -> PolarsResult<()> {
        // Serialize access to global registry
        let _guard = TEST_MUTEX.lock().unwrap();

        // Reset global registry for clean test
        reset_global_assumption_registry();

        // Create test data
        let df = df! {
            "age" => [25, 30, 35],
            "rate" => [0.1, 0.2, 0.15]
        }?;

        // First registration
        register_or_replace_assumption_table_global(
            "idempotent_test".to_string(),
            df.clone(),
            vec!["age".to_string()],
            "rate".to_string(),
            false,
        )?;

        // Verify it's registered
        let registry = get_global_assumption_registry();
        assert!(registry.get_table("idempotent_test").is_some());

        // Second registration with force_replace=false (should skip)
        let result = register_or_replace_assumption_table_global(
            "idempotent_test".to_string(),
            df.clone(),
            vec!["age".to_string()],
            "rate".to_string(),
            false,
        );
        assert!(result.is_ok());

        // Third registration with force_replace=true (should replace)
        let new_df = df! {
            "age" => [25, 30, 35],
            "rate" => [0.11, 0.21, 0.16]  // Different values
        }?;

        register_or_replace_assumption_table_global(
            "idempotent_test".to_string(),
            new_df,
            vec!["age".to_string()],
            "rate".to_string(),
            true,
        )?;

        // Verify the table was replaced with new values
        let age_series = Series::new("age".into(), &[25, 30, 35]);
        let result = lookup_assumption_global("idempotent_test", &[&age_series])?;
        let result_f64 = result.f64()?;
        assert!((result_f64.get(0).unwrap() - 0.11).abs() < 1e-10);
        assert!((result_f64.get(1).unwrap() - 0.21).abs() < 1e-10);
        assert!((result_f64.get(2).unwrap() - 0.16).abs() < 1e-10);

        Ok(())
    }

    #[test]
    fn test_reentrancy_scenario() -> PolarsResult<()> {
        // Serialize access to global registry
        let _guard = TEST_MUTEX.lock().unwrap();

        // Reset global registry for clean test
        reset_global_assumption_registry();

        // Simulate multiple model runs in same process
        for i in 1..=3 {
            // Create test data (could be same or different)
            let df = df! {
                "duration" => [1, 2, 3],
                "lapse_rate" => [0.05 * i as f64, 0.04 * i as f64, 0.03 * i as f64]
            }?;

            // This should work without errors
            register_or_replace_assumption_table_global(
                "lapse_reentrancy".to_string(),
                df,
                vec!["duration".to_string()],
                "lapse_rate".to_string(),
                true,  // Always replace for reentrancy
            )?;

            // Verify table works
            let duration_series = Series::new("duration".into(), &[1, 2, 3]);
            let result = lookup_assumption_global("lapse_reentrancy", &[&duration_series])?;
            let result_f64 = result.f64()?;
            
            // Check values match current iteration
            assert!((result_f64.get(0).unwrap() - 0.05 * i as f64).abs() < 1e-10);
            assert!((result_f64.get(1).unwrap() - 0.04 * i as f64).abs() < 1e-10);
            assert!((result_f64.get(2).unwrap() - 0.03 * i as f64).abs() < 1e-10);
        }

        Ok(())
    }
}
