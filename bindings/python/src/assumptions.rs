#![allow(clippy::needless_pass_by_value)] // PyO3 functions often need owned types
                                          // Keep only necessary imports for the plugin function itself
use polars::prelude::*;
use polars::prelude::{DataType, Field, PlSmallStr, PolarsResult, Series};
use pyo3::PyResult;
use pyo3_polars::derive::polars_expr;
use pyo3_polars::PyDataFrame;

use pyo3::prelude::*;

// Import the core logic function and assume Kwargs struct is defined there
use gaspatchio_core_lib::assumptions::{
    get_global_assumption_registry, register_assumption_table_global,
    reset_global_assumption_registry,
};
use gaspatchio_core_lib::index::{perform_lookup, AssumptionLookupKwargs}; // Assuming moved Kwargs struct

// --- Binding Plugin Implementation ---

fn lookup_output_type(_input_fields: &[Field]) -> PolarsResult<Field> {
    let value_dtype = DataType::Float64; // Assuming float64 for now, might need dynamic type later
    Ok(Field::new(
        PlSmallStr::from_static("lookup_result"),
        // Vector lookup returns a list
        DataType::List(Box::new(value_dtype)),
    ))
}

// This is the function Polars executes. It wraps the core logic.
// Polars finds it by symbol name when the corresponding expression is evaluated.
#[polars_expr(output_type_func=lookup_output_type)]
fn lookup_plugin_binding(
    inputs: &[Series],              // These are the key columns
    kwargs: AssumptionLookupKwargs, // Use the imported Kwargs struct directly
) -> PolarsResult<Series> {
    if inputs.is_empty() {
        // Use polars_err! macro for better error creation
        return Err(polars_err!(ComputeError: "Lookup requires at least one key column."));
    }

    let table_name = &kwargs.table_name; // Get table name from kwargs, pass as &str
    let key_series_refs: Vec<&Series> = inputs.iter().collect(); // All inputs are keys now

    perform_lookup(table_name, &key_series_refs) // Pass table name as &str
}

#[polars_expr(output_type_func=lookup_output_type)]
fn lookup_by_table_and_hash(
    inputs: &[Series],              // These are the key columns
    kwargs: AssumptionLookupKwargs, // Use the imported Kwargs struct directly
) -> PolarsResult<Series> {
    if inputs.is_empty() {
        // Use polars_err! macro for better error creation
        return Err(polars_err!(ComputeError: "Lookup requires at least one key column."));
    }

    let table_name = &kwargs.table_name; // Get table name from kwargs, pass as &str
    let key_series_refs: Vec<&Series> = inputs.iter().collect(); // All inputs are keys now

    let registry = get_global_assumption_registry();
    let table = registry
        .get_table(table_name)
        .ok_or_else(|| polars_err!(ComputeError: "Table '{}' not found", table_name))?;
    table.lookup_series(&key_series_refs)
}

#[pyclass]
pub struct PyAssumptionTableRegistry;

#[pymethods]
impl PyAssumptionTableRegistry {
    #[new]
    fn new() -> Self {
        // No need to actually create anything - we use the global registry
        PyAssumptionTableRegistry
    }

    #[pyo3(signature = (name, df, keys, value_column))]
    fn register_table(
        &self,
        name: String,
        df: PyDataFrame,
        keys: Vec<String>,
        value_column: String,
    ) -> PyResult<()> {
        let rust_df: DataFrame = df.into();

        // Use the global registry function
        register_assumption_table_global(name, rust_df, keys, value_column)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{}", e)))?;

        Ok(())
    }

    fn get_table(&self, name: String) -> PyResult<bool> {
        // Check if table exists in global registry
        let registry = get_global_assumption_registry();
        Ok(registry.get_table(&name).is_some())
    }

    fn list_tables(&self) -> PyResult<Vec<String>> {
        // Get list of tables from global registry
        let registry = get_global_assumption_registry();
        Ok(registry.list_tables().into_iter().cloned().collect())
    }

    fn reset(&self) -> PyResult<()> {
        // Reset the global registry
        reset_global_assumption_registry();
        Ok(())
    }
}
