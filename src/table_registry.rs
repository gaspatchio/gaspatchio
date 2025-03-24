use arc_swap::ArcSwap;
use polars::prelude::SortMultipleOptions;

use polars::prelude::*;
use pyo3::prelude::*;
use pyo3_polars::PyDataFrame;
use std::collections::HashMap;
use std::sync::Arc;
use std::sync::OnceLock;

/// Holds a global reference to the shared table registry
static REGISTRY: OnceLock<ArcSwap<TableRegistry>> = OnceLock::new();

/// Initialize and get the registry if not already initialized
fn ensure_registry() -> &'static ArcSwap<TableRegistry> {
    REGISTRY.get_or_init(|| {
        ArcSwap::new(Arc::new(TableRegistry {
            tables_internal: HashMap::new(),
            keyspecs: HashMap::new(),
        }))
    })
}

/// Get a reference to the current global registry
pub fn get_registry() -> Arc<TableRegistry> {
    ensure_registry().load_full()
}

/// Update the global registry by applying a function to a clone of the current registry
pub fn set_registry<F>(update_fn: F)
where
    F: FnOnce(&mut TableRegistry),
{
    let current = ensure_registry().load_full();
    let mut new_registry = (*current).clone();
    update_fn(&mut new_registry);
    ensure_registry().store(Arc::new(new_registry));
}

/// Register a table in the global registry
pub fn register_table_global(table_name: &str, df: DataFrame, key_spec: KeySpec) {
    set_registry(|registry| {
        registry.register_table(table_name, df, key_spec);
    });
}

/// Register a table in the global registry with optional transformation
pub fn register_table_global_with_transform(
    table_name: &str,
    df: DataFrame,
    key_spec: KeySpec,
    transform_spec: Option<TransformSpec>,
) -> PolarsResult<()> {
    // If transform_spec is provided, transform the DataFrame before registering
    let final_df = match transform_spec {
        Some(spec) => transform_wide_to_long(&df, &spec)?,
        None => df,
    };

    // Register the (potentially transformed) table
    set_registry(|registry| {
        registry.register_table(table_name, final_df, key_spec);
    });

    Ok(())
}

/// Python wrapper to register a table in the global registry with optional transformation
#[pyfunction]
#[pyo3(signature = (table_name, py_df, key_spec, transform_spec=None))]
pub fn py_register_table_with_transform(
    table_name: String,
    py_df: PyDataFrame,
    key_spec: KeySpec,
    transform_spec: Option<TransformSpec>,
) -> PyResult<()> {
    // Convert PyDataFrame to DataFrame
    let df = py_df.0;
    match register_table_global_with_transform(&table_name, df, key_spec, transform_spec) {
        Ok(_) => Ok(()),
        Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            e.to_string(),
        )),
    }
}

/// Transform a wide DataFrame to long format using unpivot
pub fn transform_wide_to_long(
    df: &DataFrame,
    transform_spec: &TransformSpec,
) -> PolarsResult<DataFrame> {
    // Get the id columns that should be kept as is
    let id_vars = &transform_spec.id_vars;

    // Get the value columns that should be unpivoted
    let value_vars = &transform_spec.value_vars;

    // Column names for the new columns
    let var_name = &transform_spec.var_name;
    let value_name = &transform_spec.value_name;

    // First build a LazyFrame for all id vars
    let mut id_columns = Vec::new();
    for id_var in id_vars {
        id_columns.push(col(id_var));
    }

    // Create an empty result frame to stack results into
    let mut result_frames = Vec::new();

    // For each value column, create a subset with id columns and the single value column
    for value_var in value_vars {
        // Make a selection of just the ID columns and this value column
        let mut expr_vec = id_columns.clone();
        expr_vec.push(col(value_var).alias(value_name));

        // Add a literal column for the variable name
        expr_vec.push(lit(value_var.clone()).alias(var_name));

        // Build a LazyFrame with the needed columns and collect it
        let subset = df.clone().lazy().select(expr_vec).collect()?;
        result_frames.push(subset);
    }

    // Combine all the individual frames
    let mut result = result_frames.remove(0);
    for frame in result_frames {
        result = result.vstack(&frame)?;
    }

    Ok(result)
}

/// Lookup data from a registered table using the query DataFrame
/// The lookup joins the query DataFrame with the registered table based on the key specification
///
/// # Arguments
/// * `table_name` - The name of the registered table to lookup
/// * `query_df` - The DataFrame containing the lookup keys
///
/// # Returns
/// A DataFrame containing the joined data
pub fn lookup(table_name: &str, query_df: DataFrame) -> PolarsResult<DataFrame> {
    let registry = get_registry();

    // Get the table DataFrame and KeySpec
    let table_df = match registry.get_table(table_name) {
        Some(df) => df,
        None => {
            return Err(PolarsError::ComputeError(
                format!("Table '{}' not found in registry", table_name).into(),
            ))
        }
    };

    let key_spec = match registry.keyspecs.get(table_name) {
        Some(ks) => ks,
        None => {
            return Err(PolarsError::ComputeError(
                format!("KeySpec for table '{}' not found in registry", table_name).into(),
            ))
        }
    };

    // Prepare for join operation
    let query_lf = query_df.lazy();
    let table_lf = table_df.clone().lazy();

    // Create the left and right join columns expressions
    let left_on: Vec<Expr> = key_spec.source_cols.iter().map(|c| col(c)).collect();

    let right_on: Vec<Expr> = key_spec.table_cols.iter().map(|c| col(c)).collect();

    // Execute the join with default join arguments
    let join_result = query_lf
        .join(table_lf, left_on, right_on, JoinArgs::new(JoinType::Left))
        .collect()?;

    Ok(join_result)
}

/// Python wrapper to lookup data from a registered table
#[pyfunction]
pub fn py_lookup(table_name: String, query_df: PyDataFrame) -> PyResult<PyDataFrame> {
    let df = query_df.0;
    match lookup(&table_name, df) {
        Ok(result_df) => Ok(PyDataFrame(result_df)),
        Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            e.to_string(),
        )),
    }
}

#[pyfunction]
pub fn py_lookup_vector(table_name: String, query_df: PyDataFrame) -> PyResult<PyDataFrame> {
    // Convert PyDataFrame to Polars DataFrame
    let df = query_df.0;

    // Perform vector lookup
    match lookup_vector(&table_name, df) {
        Ok(result) => Ok(PyDataFrame(result)),
        Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            e.to_string(),
        )),
    }
}

/// Python wrapper to get the global registry
#[pyfunction]
pub fn py_get_registry() -> PyResult<TableRegistry> {
    let registry = get_registry();
    Ok((*registry).clone())
}

/// Python wrapper to update the global registry with a new KeySpec
#[pyfunction]
pub fn py_register_keyspec(table_name: String, key_spec: KeySpec) -> PyResult<()> {
    set_registry(|registry| {
        registry.keyspecs.insert(table_name, key_spec);
    });
    Ok(())
}

/// Python wrapper to register a table in the global registry
#[pyfunction]
pub fn py_register_table(
    table_name: String,
    py_df: PyDataFrame,
    key_spec: KeySpec,
) -> PyResult<()> {
    // Convert PyDataFrame to DataFrame
    let df = py_df.0;
    register_table_global(&table_name, df, key_spec);
    Ok(())
}

/// Specification for transforming wide format DataFrames to long format
#[pyclass]
#[derive(Debug, Clone)]
pub struct TransformSpec {
    /// Columns to keep as identifier variables
    #[pyo3(get, set)]
    pub id_vars: Vec<String>,

    /// Columns to unpivot (convert from wide to long)
    #[pyo3(get, set)]
    pub value_vars: Vec<String>,

    /// Name for the new column that will contain the unpivoted column names
    #[pyo3(get, set)]
    pub var_name: String,

    /// Name for the new column that will contain the values from the unpivoted columns
    #[pyo3(get, set)]
    pub value_name: String,
}

#[pymethods]
impl TransformSpec {
    #[new]
    pub fn new(
        id_vars: Vec<String>,
        value_vars: Vec<String>,
        var_name: String,
        value_name: String,
    ) -> Self {
        TransformSpec {
            id_vars,
            value_vars,
            var_name,
            value_name,
        }
    }
}

/// KeySpec defines the column mappings for joining tables
#[pyclass]
#[derive(Debug, Clone)]
pub struct KeySpec {
    /// Columns from the source (query) dataframe
    #[pyo3(get, set)]
    pub source_cols: Vec<String>,
    /// Corresponding columns from the table being joined
    #[pyo3(get, set)]
    pub table_cols: Vec<String>,
}

#[pymethods]
impl KeySpec {
    #[new]
    pub fn new(source_cols: Vec<String>, table_cols: Vec<String>) -> Self {
        KeySpec {
            source_cols,
            table_cols,
        }
    }
}

/// TableRegistry stores DataFrames and their associated KeySpecs
#[pyclass]
#[derive(Debug, Clone)]
pub struct TableRegistry {
    /// Maps table names to their DataFrames
    tables_internal: HashMap<String, DataFrame>,
    /// Maps table names to their KeySpecs
    #[pyo3(get)]
    pub keyspecs: HashMap<String, KeySpec>,
}

#[pymethods]
impl TableRegistry {
    /// Creates a new empty TableRegistry
    #[new]
    pub fn new() -> Self {
        TableRegistry {
            tables_internal: HashMap::new(),
            keyspecs: HashMap::new(),
        }
    }

    /// Get a list of available table names
    #[getter]
    fn tables(&self) -> Vec<String> {
        self.tables_internal.keys().cloned().collect()
    }
}

/// For Rust access to tables
impl TableRegistry {
    pub fn get_tables(&self) -> &HashMap<String, DataFrame> {
        &self.tables_internal
    }

    /// Register a table with the registry
    pub fn register_table(&mut self, table_name: &str, df: DataFrame, key_spec: KeySpec) {
        self.tables_internal.insert(table_name.to_string(), df);
        self.keyspecs.insert(table_name.to_string(), key_spec);
    }

    /// Get a table by name
    pub fn get_table(&self, table_name: &str) -> Option<&DataFrame> {
        self.tables_internal.get(table_name)
    }
}

/// Detects list/vector columns in a DataFrame
///
/// # Arguments
/// * `df` - The DataFrame to examine
/// * `column_names` - Column names to check
///
/// # Returns
/// A vector of column names that contain list data
pub fn detect_vector_columns(df: &DataFrame, column_names: &[String]) -> PolarsResult<Vec<String>> {
    // Pre-allocate with estimated capacity
    let mut vector_cols = Vec::with_capacity(column_names.len());

    // Get schema once instead of accessing columns repeatedly
    let schema = df.schema();

    for col_name in column_names {
        // Use schema lookup instead of getting column
        if let Some(dtype) = schema.get(col_name) {
            if matches!(dtype, DataType::List(_)) {
                // Use to_string() only when needed
                vector_cols.push(col_name.to_string());
            }
        }
    }

    Ok(vector_cols)
}

pub fn explode_vector_columns(
    df: &DataFrame,
    vector_columns: &[String],
) -> PolarsResult<DataFrame> {
    // Create row tracking column before explosion
    let with_index = df.clone().with_row_index("__row_idx".into(), None)?;

    // Use Polars' native explode - handles nulls and different length vectors automatically
    let exploded = with_index.explode(vector_columns)?;

    // Add projection index using window functions
    let result = exploded
        .lazy()
        .with_column(
            col("__row_idx")
                .sort_by([col("__row_idx")], SortMultipleOptions::default())
                .alias("__proj_idx"),
        )
        .collect()?;

    Ok(result)
}

/// Collects lookup results back into vector format using Polars' list operations
///
/// # Arguments
/// * `df` - Exploded DataFrame with lookup results
/// * `group_column` - Column to group by (usually __row_idx)
/// * `value_columns` - Columns to collect into vectors
///
/// # Returns
/// A DataFrame with vector results
pub fn collect_vector_results(
    df: &DataFrame,
    group_column: &str,
    value_columns: &[String],
) -> PolarsResult<DataFrame> {
    // Create expressions for grouping value columns into lists
    let mut agg_exprs = vec![
        // Keep first value of non-grouped columns
        col("*").exclude(value_columns).first(),
    ];

    // Add list aggregation for each value column
    for col_name in value_columns {
        agg_exprs.push(col(col_name).list().0.alias(col_name));
    }

    // Group by the specified column and aggregate
    let result = df
        .clone()
        .lazy()
        .group_by([col(group_column)])
        .agg(agg_exprs)
        .sort(vec![group_column], SortMultipleOptions::default())
        .collect()?;

    Ok(result)
}

/// Performs lookups with vector column support using Polars' optimized operations
///
/// # Arguments
/// * `table_name` - Name of the registered table to lookup
/// * `query_df` - DataFrame that may contain vector columns
///
/// # Returns
/// A DataFrame with lookup results as vectors
pub fn lookup_vector(table_name: &str, query_df: DataFrame) -> PolarsResult<DataFrame> {
    // Get the registered table
    let registry = get_registry();
    let _table_df = registry.get_table(table_name).ok_or_else(|| {
        PolarsError::ComputeError(format!("Table '{}' not found", table_name).into())
    })?;

    let key_spec = registry.keyspecs.get(table_name).ok_or_else(|| {
        PolarsError::ComputeError(format!("KeySpec for table '{}' not found", table_name).into())
    })?;

    // Detect vector columns in query DataFrame
    let vector_cols = detect_vector_columns(&query_df, &key_spec.source_cols)?;

    if vector_cols.is_empty() {
        // No vector columns - use standard lookup
        return lookup(table_name, query_df);
    }

    // Explode vector columns
    let exploded = explode_vector_columns(&query_df, &vector_cols)?;

    // Perform lookup using standard mechanism
    let lookup_result = lookup(table_name, exploded)?;

    // Determine which columns to collect as vectors
    let value_columns: Vec<String> = lookup_result
        .get_column_names()
        .iter()
        .filter(|&name| !name.starts_with("__"))
        .map(|s| s.to_string())
        .collect();

    // Collect results back into vectors
    collect_vector_results(&lookup_result, "__row_idx", &value_columns)
}

/// Initializes the module
pub fn init_module(m: &Bound<PyModule>) -> PyResult<()> {
    m.add_class::<KeySpec>()?;
    m.add_class::<TransformSpec>()?;
    m.add_class::<TableRegistry>()?;
    m.add_function(wrap_pyfunction!(py_get_registry, m)?)?;
    m.add_function(wrap_pyfunction!(py_register_keyspec, m)?)?;
    m.add_function(wrap_pyfunction!(py_register_table, m)?)?;
    m.add_function(wrap_pyfunction!(py_register_table_with_transform, m)?)?;
    m.add_function(wrap_pyfunction!(py_lookup, m)?)?;
    m.add_function(wrap_pyfunction!(py_lookup_vector, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_create_registry() {
        // Create a KeySpec
        let key_spec = KeySpec {
            source_cols: vec!["id".to_string()],
            table_cols: vec!["table_id".to_string()],
        };

        // Create a TableRegistry
        let registry = TableRegistry::new();

        // Verify the registry is empty
        assert_eq!(registry.tables_internal.len(), 0);
        assert_eq!(registry.keyspecs.len(), 0);

        // Verify KeySpec fields
        assert_eq!(key_spec.source_cols.len(), 1);
        assert_eq!(key_spec.table_cols.len(), 1);
        assert_eq!(key_spec.source_cols[0], "id");
        assert_eq!(key_spec.table_cols[0], "table_id");
    }

    #[test]
    fn test_global_registry() {
        // Get the initial registry
        let initial_registry = get_registry();
        assert_eq!(initial_registry.keyspecs.len(), 0);

        // Update the registry
        set_registry(|registry| {
            registry.keyspecs.insert(
                "test_table".to_string(),
                KeySpec {
                    source_cols: vec!["source_id".to_string()],
                    table_cols: vec!["table_id".to_string()],
                },
            );
        });

        // Get the updated registry
        let updated_registry = get_registry();
        assert_eq!(updated_registry.keyspecs.len(), 1);

        // Verify the keyspec was added
        assert!(updated_registry.keyspecs.contains_key("test_table"));
        let key_spec = updated_registry.keyspecs.get("test_table").unwrap();
        assert_eq!(key_spec.source_cols[0], "source_id");
        assert_eq!(key_spec.table_cols[0], "table_id");
    }

    #[test]
    fn test_register_table() {
        // Create a KeySpec
        let key_spec = KeySpec {
            source_cols: vec!["id".to_string()],
            table_cols: vec!["table_id".to_string()],
        };

        // Create a simple DataFrame
        let df = df! {
            "table_id" => [1, 2, 3],
            "value" => ["a", "b", "c"]
        }
        .unwrap();

        // Create a TableRegistry and register the table
        let mut registry = TableRegistry::new();
        registry.register_table("test_table", df.clone(), key_spec.clone());

        // Verify the table was registered
        assert_eq!(registry.tables_internal.len(), 1);
        assert_eq!(registry.keyspecs.len(), 1);
        assert!(registry.tables_internal.contains_key("test_table"));
        assert!(registry.keyspecs.contains_key("test_table"));

        // Verify the DataFrame was stored correctly
        let stored_df = registry.get_table("test_table").unwrap();
        assert_eq!(stored_df.shape(), (3, 2));
    }

    #[test]
    fn test_register_table_global() {
        // Reset registry to clean state for this test
        set_registry(|registry| {
            registry.tables_internal.clear();
            registry.keyspecs.clear();
        });

        // Create a KeySpec
        let key_spec = KeySpec {
            source_cols: vec!["id".to_string()],
            table_cols: vec!["table_id".to_string()],
        };

        // Create a simple DataFrame
        let df = df! {
            "table_id" => [1, 2, 3],
            "value" => ["a", "b", "c"]
        }
        .unwrap();

        // Register the table in the global registry
        register_table_global("test_global_table", df.clone(), key_spec);

        // Get the updated registry
        let registry = get_registry();

        // Verify the table was registered
        assert!(registry.get_tables().contains_key("test_global_table"));
        assert!(registry.keyspecs.contains_key("test_global_table"));

        // Verify the DataFrame was stored correctly
        let stored_df = registry.get_tables().get("test_global_table").unwrap();
        assert_eq!(stored_df.shape(), (3, 2));
    }

    #[test]
    fn test_transform_wide_to_long() {
        // Create a wide DataFrame for testing
        let df = df! {
            "id" => [1, 2, 3, 4],
            "name" => ["a", "b", "c", "d"],
            "val_2020" => [10, 20, 30, 40],
            "val_2021" => [11, 21, 31, 41],
            "val_2022" => [12, 22, 32, 42]
        }
        .unwrap();

        // Create a TransformSpec for wide-to-long transformation
        let transform_spec = TransformSpec {
            id_vars: vec!["id".to_string(), "name".to_string()],
            value_vars: vec![
                "val_2020".to_string(),
                "val_2021".to_string(),
                "val_2022".to_string(),
            ],
            var_name: "year".to_string(),
            value_name: "value".to_string(),
        };

        // Apply the transformation
        let result = transform_wide_to_long(&df, &transform_spec).unwrap();

        // Verify the result shape
        // Input: 4 rows x 5 columns
        // Output: 4 rows x 3 value_vars = 12 rows x 4 columns (id, name, year, value)
        assert_eq!(result.shape(), (12, 4));

        // Check column names
        let column_names: Vec<String> = result
            .get_column_names()
            .iter()
            .map(|name| name.to_string())
            .collect();

        assert!(column_names.contains(&"id".to_string()));
        assert!(column_names.contains(&"name".to_string()));
        assert!(column_names.contains(&"year".to_string()));
        assert!(column_names.contains(&"value".to_string()));

        // Check specific values
        // For id=1, year=val_2020, value should be 10
        let row1_2020 = result
            .clone()
            .lazy()
            .filter(col("id").eq(lit(1)).and(col("year").eq(lit("val_2020"))))
            .select([col("value")])
            .collect()
            .unwrap();

        assert_eq!(row1_2020.shape(), (1, 1));
        let value = row1_2020.column("value").unwrap().get(0).unwrap();
        assert_eq!(value.to_string(), "10"); // Compare the string representation

        // For id=3, year=val_2022, value should be 32
        let row3_2022 = result
            .clone()
            .lazy()
            .filter(col("id").eq(lit(3)).and(col("year").eq(lit("val_2022"))))
            .select([col("value")])
            .collect()
            .unwrap();

        assert_eq!(row3_2022.shape(), (1, 1));
        let value = row3_2022.column("value").unwrap().get(0).unwrap();
        assert_eq!(value.to_string(), "32"); // Compare the string representation
    }

    #[test]
    fn test_register_with_transform() {
        // Reset registry to clean state for this test
        set_registry(|registry| {
            registry.tables_internal.clear();
            registry.keyspecs.clear();
        });

        // Create a KeySpec
        let key_spec = KeySpec {
            source_cols: vec!["id".to_string()],
            table_cols: vec!["id".to_string()],
        };

        // Create a wide DataFrame
        let df = df! {
            "id" => [1, 2],  // 2 rows
            "value_x" => [10, 20],
            "value_y" => [100, 200],
            "value_z" => [1000, 2000]
        }
        .unwrap();

        // Create a TransformSpec
        let transform_spec = TransformSpec {
            id_vars: vec!["id".to_string()],
            value_vars: vec![
                "value_x".to_string(),
                "value_y".to_string(),
                "value_z".to_string(), // 3 value columns
            ],
            var_name: "variable".to_string(),
            value_name: "value".to_string(),
        };

        // Register with transformation
        register_table_global_with_transform(
            "test_transform_table",
            df,
            key_spec,
            Some(transform_spec),
        )
        .unwrap();

        // Get the updated registry
        let registry = get_registry();

        // Verify the table was registered
        assert!(registry.get_tables().contains_key("test_transform_table"));

        // Get the transformed DataFrame
        let stored_df = registry.get_tables().get("test_transform_table").unwrap();

        // Verify it was transformed
        // Original: 2 rows x 4 columns
        // Transformed: 2 rows x 3 value columns = 6 rows x 3 columns (id, variable, value)
        assert_eq!(stored_df.shape(), (6, 3)); // 2 rows × 3 value columns = 6 total rows

        // Check that the expected columns exist
        let column_names: Vec<String> = stored_df
            .get_column_names()
            .iter()
            .map(|name| name.to_string())
            .collect();

        assert!(column_names.contains(&"id".to_string()));
        assert!(column_names.contains(&"variable".to_string()));
        assert!(column_names.contains(&"value".to_string()));

        // Verify the transformed values
        let value_col = stored_df.column("value").unwrap();
        let values: Vec<i32> = value_col.i32().unwrap().into_iter().flatten().collect();
        assert_eq!(values, vec![10, 100, 1000, 20, 200, 2000]);

        // Verify the variable names
        let var_col = stored_df.column("variable").unwrap().str().unwrap();
        let vars: Vec<&str> = var_col.into_iter().flatten().collect();
        assert_eq!(
            vars,
            vec!["value_x", "value_y", "value_z", "value_x", "value_y", "value_z"]
        );

        // Verify the id values are properly repeated
        let id_col = stored_df.column("id").unwrap().i32().unwrap();
        let ids: Vec<i32> = id_col.into_iter().flatten().collect();
        assert_eq!(ids, vec![1, 1, 1, 2, 2, 2]);
    }

    #[test]
    fn test_lookup() {
        // Reset registry to clean state for this test
        set_registry(|registry| {
            registry.tables_internal.clear();
            registry.keyspecs.clear();
        });

        // Create a KeySpec for the lookup
        let key_spec = KeySpec {
            source_cols: vec!["id".to_string()],
            table_cols: vec!["table_id".to_string()],
        };

        // Create a table DataFrame
        let table_df = df! {
            "table_id" => [1, 2, 3],
            "value" => ["a", "b", "c"]
        }
        .unwrap();

        // Register the table in the global registry
        register_table_global("test_lookup_table", table_df, key_spec);

        // Create a query DataFrame with keys to lookup
        let query_df = df! {
            "id" => [1, 3, 5],
            "query_value" => ["x", "y", "z"]
        }
        .unwrap();

        // Perform the lookup
        let result_df = lookup("test_lookup_table", query_df).unwrap();

        // Verify the lookup result
        assert_eq!(result_df.shape().0, 3); // Should have same number of rows as query

        // Get the column names as strings for easier assertions
        let column_names: Vec<String> = result_df
            .get_column_names()
            .iter()
            .map(|name| name.to_string())
            .collect();

        // Check if the columns exist in the result
        assert!(column_names.contains(&"value".to_string()));
        assert!(column_names.contains(&"query_value".to_string()));

        // Get the data from the value column
        let value_col = result_df.column("value").unwrap();

        // For string columns, we need to get data as a string series
        let value_str = value_col.str().unwrap();

        // Check the actual values
        assert_eq!(value_str.get(0), Some("a"));
        assert_eq!(value_str.get(1), Some("c"));
        assert_eq!(value_str.get(2), None); // id=5 not in table
    }

    #[test]
    fn test_join_syntax() {
        // Create two simple DataFrames
        let df1 = df! {
            "id" => [1, 2, 3],
            "value" => ["a", "b", "c"]
        }
        .unwrap();

        let df2 = df! {
            "id" => [1, 3, 4],
            "other_value" => ["x", "y", "z"]
        }
        .unwrap();

        // Test the join syntax directly
        let result = df1
            .lazy()
            .join(
                df2.lazy(),
                [col("id")],
                [col("id")],
                JoinArgs::new(JoinType::Left),
            )
            .collect()
            .unwrap();

        // Verify result shape
        assert_eq!(result.shape().0, 3); // Should have same number of rows as left df

        // Get the column names as strings for easier assertions
        let column_names: Vec<String> = result
            .get_column_names()
            .iter()
            .map(|name| name.to_string())
            .collect();

        // Check if the columns exist in the result
        assert!(column_names.contains(&"value".to_string()));
        assert!(column_names.contains(&"other_value".to_string()));
    }

    #[test]
    fn test_detect_vector_columns() {
        let df = df! {
            "scalar_int" => [1, 2, 3],
            "scalar_str" => ["a", "b", "c"],
            "vector_int" => ListChunked::from_iter([
                Some(Series::new("".into(), vec![1, 2])),
                Some(Series::new("".into(), vec![3, 4])),
                Some(Series::new("".into(), vec![5, 6]))
            ]).into_series(),
            "vector_float" => ListChunked::from_iter([
                Some(Series::new("".into(), vec![1.1, 2.2])),
                Some(Series::new("".into(), vec![3.3, 4.4])),
                Some(Series::new("".into(), vec![5.5, 6.6]))
            ]).into_series()
        }
        .unwrap();

        // Test detection with all columns
        let all_cols = vec![
            "scalar_int".to_string(),
            "scalar_str".to_string(),
            "vector_int".to_string(),
            "vector_float".to_string(),
        ];
        let vector_cols = detect_vector_columns(&df, &all_cols).unwrap();

        // Should only detect the vector columns
        assert_eq!(vector_cols.len(), 2);
        assert!(vector_cols.contains(&"vector_int".to_string()));
        assert!(vector_cols.contains(&"vector_float".to_string()));

        // Test with subset of columns
        let subset_cols = vec!["scalar_int".to_string(), "vector_int".to_string()];
        let vector_cols = detect_vector_columns(&df, &subset_cols).unwrap();

        // Should only detect vector_int
        assert_eq!(vector_cols.len(), 1);
        assert!(vector_cols.contains(&"vector_int".to_string()));
    }

    #[test]
    fn test_detect_vector_columns_empty() {
        // Test with empty DataFrame
        let empty_df = df! {
            "scalar_int" => [1, 2, 3]
        }
        .unwrap();

        let cols = vec!["scalar_int".to_string()];
        let vector_cols = detect_vector_columns(&empty_df, &cols).unwrap();

        // Should return empty vector since no list columns
        assert!(vector_cols.is_empty());

        // Test with non-existent columns
        let bad_cols = vec!["non_existent".to_string()];
        let vector_cols = detect_vector_columns(&empty_df, &bad_cols).unwrap();

        // Should return empty vector for non-existent columns
        assert!(vector_cols.is_empty());
    }

    #[test]
    fn test_explode_vector_columns_basic() {
        let df = df! {
            "id" => [1, 2],
            "scalar" => ["a", "b"],
            "vector" => ListChunked::from_iter([
                Some(Series::new("".into(), vec![10, 20])),
                Some(Series::new("".into(), vec![30, 40, 50]))
            ]).into_series()
        }
        .unwrap();

        let vector_cols = vec!["vector".to_string()];
        let result = explode_vector_columns(&df, &vector_cols).unwrap();

        // Check shape - should be 5 rows (2 + 3 from vectors)
        assert_eq!(result.shape(), (5, 5)); // 5 columns including __row_idx, __proj_idx, and original columns

        // Check column names
        let cols: Vec<String> = result
            .get_column_names()
            .iter()
            .map(|s| s.to_string())
            .collect();
        assert!(cols.contains(&"id".to_string()));
        assert!(cols.contains(&"scalar".to_string()));
        assert!(cols.contains(&"vector".to_string()));
        assert!(cols.contains(&"__row_idx".to_string()));
        assert!(cols.contains(&"__proj_idx".to_string()));

        // Check values
        let vector_col = result.column("vector").unwrap().i32().unwrap();
        assert_eq!(vector_col.get(0), Some(10));
        assert_eq!(vector_col.get(1), Some(20));
        assert_eq!(vector_col.get(2), Some(30));
        assert_eq!(vector_col.get(3), Some(40));
        assert_eq!(vector_col.get(4), Some(50));

        // Check id values are properly repeated
        let id_col = result.column("id").unwrap().i32().unwrap();
        assert_eq!(id_col.get(0), Some(1));
        assert_eq!(id_col.get(1), Some(1));
        assert_eq!(id_col.get(2), Some(2));
        assert_eq!(id_col.get(3), Some(2));
        assert_eq!(id_col.get(4), Some(2));
    }

    #[test]
    fn test_explode_vector_columns_multiple() {
        let df = df! {
            "id" => [1, 2],
            "vector1" => ListChunked::from_iter([
                Some(Series::new("".into(), vec![10, 20])),
                Some(Series::new("".into(), vec![30, 40]))
            ]).into_series(),
            "vector2" => ListChunked::from_iter([
                Some(Series::new("".into(), vec!["a", "b"])),
                Some(Series::new("".into(), vec!["c", "d"]))
            ]).into_series()
        }
        .unwrap();

        let vector_cols = vec!["vector1".to_string(), "vector2".to_string()];
        let result = explode_vector_columns(&df, &vector_cols).unwrap();

        // Check shape - should be 4 rows (2 elements per vector)
        assert_eq!(result.shape(), (4, 5)); // 5 columns including __row_idx, __proj_idx, and original columns

        // Check values from both vector columns
        let vector1_col = result.column("vector1").unwrap().i32().unwrap();
        let vector2_col = result.column("vector2").unwrap().str().unwrap();

        assert_eq!(vector1_col.get(0), Some(10));
        assert_eq!(vector2_col.get(0), Some("a"));
        assert_eq!(vector1_col.get(1), Some(20));
        assert_eq!(vector2_col.get(1), Some("b"));
        assert_eq!(vector1_col.get(2), Some(30));
        assert_eq!(vector2_col.get(2), Some("c"));
        assert_eq!(vector1_col.get(3), Some(40));
        assert_eq!(vector2_col.get(3), Some("d"));
    }

    #[test]
    fn test_explode_vector_columns_with_nulls() {
        let df = df! {
            "id" => [1, 2, 3],
            "vector" => ListChunked::from_iter([
                Some(Series::new("".into(), vec![10, 20])),
                None,
                Some(Series::new("".into(), vec![30]))
            ]).into_series()
        }
        .unwrap();

        let vector_cols = vec!["vector".to_string()];
        let result = explode_vector_columns(&df, &vector_cols).unwrap();

        // Check shape - should be 4 rows (2 + 1 + 1 from vectors)
        assert_eq!(result.shape(), (4, 4)); // 4 columns including __row_idx and __proj_idx

        // Check values - note that None values are included in output
        let vector_col = result.column("vector").unwrap().i32().unwrap();
        assert_eq!(vector_col.get(0), Some(10));
        assert_eq!(vector_col.get(1), Some(20));
        assert_eq!(vector_col.get(2), None); // The None value is preserved
        assert_eq!(vector_col.get(3), Some(30));

        // Check id values
        let id_col = result.column("id").unwrap().i32().unwrap();
        assert_eq!(id_col.get(0), Some(1));
        assert_eq!(id_col.get(1), Some(1));
        assert_eq!(id_col.get(2), Some(2)); // ID for the None value
        assert_eq!(id_col.get(3), Some(3));
    }

    #[test]
    fn test_explode_vector_columns_empty() {
        let df = df! {
            "id" => [1, 2],
            "vector" => ListChunked::from_iter([
                Some(Series::new("".into(), Vec::<i32>::new())),
                Some(Series::new("".into(), Vec::<i32>::new()))
            ]).into_series()
        }
        .unwrap();

        let vector_cols = vec!["vector".to_string()];
        let result = explode_vector_columns(&df, &vector_cols).unwrap();

        // Check shape - should be 2 rows since empty vectors are preserved
        assert_eq!(result.shape().0, 2);
    }
}
