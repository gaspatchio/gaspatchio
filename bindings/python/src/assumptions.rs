#![allow(clippy::needless_pass_by_value)] // PyO3 functions often need owned types
                                          // Keep only necessary imports for the plugin function itself
use polars::prelude::*;
use polars::prelude::{DataType, Field, PlSmallStr, PolarsResult, Series};
use pyo3_polars::derive::polars_expr;

// Import the core logic function and assume Kwargs struct is defined there
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

// --- User-facing PyO3 Binding Function removed ---

// --- Module Registration removed ---
// Registration is handled on the Python side using polars plugin API
