#![allow(clippy::needless_pass_by_value)] // PyO3 functions often need owned types
                                          // Keep only necessary imports for the plugin function itself
use polars::prelude::{AnyValue, DataType, Field, PlSmallStr, PolarsError, PolarsResult, Series};
use pyo3_polars::derive::polars_expr;

// Import the core logic function
use gaspatchio_core_lib::index::perform_lookup;

// --- Binding Plugin Implementation ---

fn lookup_output_type(_input_fields: &[Field]) -> PolarsResult<Field> {
    let value_dtype = DataType::Float64;
    Ok(Field::new(
        PlSmallStr::from_static("lookup_result"),
        DataType::List(Box::new(value_dtype)),
    ))
}

// This is the function Polars executes. It wraps the core logic.
// NOTE: This function is not called directly via PyO3.
// Polars finds it by symbol name when the corresponding expression is evaluated.
#[polars_expr(output_type_func=lookup_output_type)]
fn lookup_plugin_binding(inputs: &[Series]) -> PolarsResult<Series> {
    if inputs.len() < 2 {
        return Err(PolarsError::ComputeError(
            "Lookup requires at least one key column and a table name literal.".into(),
        ));
    }

    let table_name_series = inputs.last().unwrap();
    let key_series_slice = &inputs[0..inputs.len() - 1];

    if table_name_series.len() != 1 {
        return Err(PolarsError::ComputeError(
            "Table name argument must be a scalar string literal.".into(),
        ));
    }
    let table_name_av = table_name_series.get(0).map_err(|_| {
        PolarsError::ComputeError("Could not extract table name from series.".into())
    })?;

    // Ensure both arms produce String
    let table_name_owned: String = match table_name_av {
        AnyValue::String(s) => s.to_owned(),
        AnyValue::StringOwned(s) => s.to_string(), // Use to_string() for PlSmallStr
        _ => {
            return Err(PolarsError::ComputeError(
                "Table name argument must be a string literal.".into(),
            ))
        }
    };

    let key_series_refs: Vec<&Series> = key_series_slice.iter().collect();

    perform_lookup(&table_name_owned, &key_series_refs)
}

// --- PyO3 Binding Function Removed ---

// --- Module Registration Removed ---
