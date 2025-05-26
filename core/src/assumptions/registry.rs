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
    // Acquire the lock to serialize registration attempts
    let _guard = REGISTRATION_LOCK.lock().map_err(|_| {
        // Handle potential Mutex poisoning
        polars_err!(ComputeError: "Registration lock poisoned")
    })?;

    // --- Check for existing table *inside the lock* ---
    let current_registry = get_global_assumption_registry(); // Get snapshot *after* acquiring lock
    if current_registry.get_table(&name).is_some() {
        return Err(polars_err!(ComputeError: "assumption table '{}' already exists", name));
    }
    drop(current_registry); // Drop Arc before RCU

    // --- Atomically Update Registry ---
    // We use store for synchronous update under the lock
    let current_arc = GLOBAL_REGISTRY.load_full(); // Get current state again
    let mut new_registry = (*current_arc).clone();

    // Register the table internally within the cloned state
    match new_registry.register_table(name.clone(), df, keys, value_column) {
        Ok(()) => {
            // If internal registration succeeded, store the new state
            GLOBAL_REGISTRY.store(Arc::new(new_registry));
            debug!(
                "Successfully registered and stored table '{}' in global registry",
                name
            );
            Ok(())
        }
        Err(e) => {
            // This should not happen due to the upfront check under lock
            log::error!("Internal registration failed unexpectedly under lock for '{}': {}. Aborting update.", name, e);
            // Do not store, return the error
            Err(e)
        }
    }
    // Lock guard is dropped here
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
    pub fn list_tables(&self) -> Vec<&String> {
        self.assumption_tables.keys().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
