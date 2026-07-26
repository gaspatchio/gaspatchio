#![allow(clippy::needless_pass_by_value)] // PyO3 functions often need owned types

// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

                                          // Keep only necessary imports for the plugin function itself
use polars::prelude::*;
use polars::prelude::{DataType, Field, PlSmallStr, PolarsResult, Series};
use pyo3::PyResult;
use pyo3_polars::derive::polars_expr;
use pyo3_polars::PyDataFrame;

use pyo3::prelude::*;
use serde::Deserialize;
use std::str::FromStr;

// Import the core logic function and assume Kwargs struct is defined there
use gaspatchio_core_lib::assumptions::{
    append_to_assumption_table_global, get_global_assumption_registry,
    register_assumption_table_global, register_assumption_table_global_with_mode,
    register_or_replace_assumption_table_global,
    register_or_replace_assumption_table_global_with_mode, reset_global_assumption_registry,
    StorageMode,
};

// Kwargs struct for the assumption lookup plugin
#[derive(Deserialize, Debug, Clone)]
pub struct AssumptionLookupKwargs {
    pub table_name: String,
    /// Miss policy: "raise" (default), "nan", or "fill".
    #[serde(default)]
    pub on_missing: Option<String>,
    /// Fill constant used when `on_missing == "fill"`.
    #[serde(default)]
    pub fill_value: Option<f64>,
}

// --- Binding Plugin Implementation ---

fn lookup_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let value_dtype = DataType::Float64;
    // Scalar keys return a flat Float64 series; any List key returns one
    // list of rates per row. The declared dtype must match what
    // lookup_series actually returns, otherwise the schema cache holds a
    // dtype the collected column contradicts and shape-dependent
    // operations (when/otherwise lowering, list-vs-scalar arithmetic
    // routing) misfire on scalar-key lookups.
    let has_list_key = input_fields
        .iter()
        .any(|f| matches!(f.dtype(), DataType::List(_)));
    let dtype = if has_list_key {
        DataType::List(Box::new(value_dtype))
    } else {
        value_dtype
    };
    Ok(Field::new(PlSmallStr::from_static("lookup_result"), dtype))
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
    
    // Debug logging to diagnose the issue
    log::debug!(
        "lookup_by_table_and_hash: Looking for table '{}'. Available tables: {:?}",
        table_name,
        registry.list_tables()
    );
    
    let table = registry
        .get_table(table_name)
        .ok_or_else(|| {
            let available_tables = registry.list_tables();
            polars_err!(
                ComputeError: 
                "Table '{}' not found in AssumptionTableRegistry. Available tables: {:?}. Registry has {} tables.",
                table_name, available_tables, available_tables.len()
            )
        })?;
        
    // Determine if this is a vector lookup (any key is a List type)
    let has_list_keys = key_series_refs
        .iter()
        .any(|s| matches!(s.dtype(), polars::prelude::DataType::List(_)));
    let lookup_type = if has_list_keys { "vector" } else { "scalar" };
    let num_rows = key_series_refs.first().map(|s| s.len()).unwrap_or(0);

    log::debug!(
        "Lookup '{}': {} rows, {} keys, mode={}, storage={}",
        table_name,
        num_rows,
        lookup_type,
        key_series_refs.len(),
        match table.storage_mode() {
            StorageMode::Hash => "hash",
            StorageMode::Array => "array",
            StorageMode::Auto => "auto",
        }
    );

    let result = table.lookup_series(&key_series_refs)?;
    apply_on_missing_policy(
        result,
        &key_series_refs,
        table_name,
        kwargs.on_missing.as_deref(),
        kwargs.fill_value,
    )
}

/// Apply the lookup miss policy to a lookup result.
///
/// Misses surface as NaN in the raw result (the storage kernels pre-fill NaN
/// and only overwrite on a hit). "raise" turns any NaN into a ComputeError
/// naming the table and sample keys; "fill" replaces NaN with a constant;
/// "nan" passes the raw result through. NaN-valued table entries are
/// indistinguishable from misses by construction, so under "raise" a table
/// whose rates legitimately contain NaN must opt out via "nan" or "fill".
fn apply_on_missing_policy(
    result: Series,
    key_cols: &[&Series],
    table_name: &str,
    on_missing: Option<&str>,
    fill_value: Option<f64>,
) -> PolarsResult<Series> {
    match on_missing.unwrap_or("raise") {
        "nan" => Ok(result),
        "fill" => fill_missing(result, fill_value.unwrap_or(f64::NAN)),
        _ => raise_if_missing(result, key_cols, table_name),
    }
}

fn fill_missing(result: Series, constant: f64) -> PolarsResult<Series> {
    let name = result.name().clone();
    match result.dtype() {
        DataType::List(_) => {
            let filled: ListChunked = result.list()?.try_apply_amortized(|inner| {
                let s = inner.as_ref();
                Ok(match s.f64() {
                    Ok(ca) => ca
                        .apply_values(|v| if v.is_nan() { constant } else { v })
                        .into_series(),
                    Err(_) => s.clone(),
                })
            })?;
            Ok(filled.into_series().with_name(name))
        }
        _ => {
            let ca = result.f64()?;
            Ok(ca
                .apply_values(|v| if v.is_nan() { constant } else { v })
                .into_series()
                .with_name(name))
        }
    }
}

fn raise_if_missing(
    result: Series,
    key_cols: &[&Series],
    table_name: &str,
) -> PolarsResult<Series> {
    // Fast vectorised check first; the row-attribution pass below only runs
    // on the error path.
    let flat = match result.dtype() {
        DataType::List(_) => result.list()?.explode(ExplodeOptions {
            empty_as_null: false,
            keep_nulls: false,
        })?,
        _ => result.clone(),
    };
    let has_missing = flat.f64().map(|ca| ca.is_nan().any()).unwrap_or(false);
    if !has_missing {
        return Ok(result);
    }

    let mut missing_rows: Vec<usize> = Vec::new();
    let mut n_missing_rows = 0usize;
    match result.dtype() {
        DataType::List(_) => {
            let lc = result.list()?;
            for row in 0..lc.len() {
                let row_has_nan = lc
                    .get_as_series(row)
                    .and_then(|s| s.f64().ok().map(|ca| ca.is_nan().any()))
                    .unwrap_or(false);
                if row_has_nan {
                    n_missing_rows += 1;
                    if missing_rows.len() < 3 {
                        missing_rows.push(row);
                    }
                }
            }
        }
        _ => {
            let ca = result.f64()?;
            for (row, v) in ca.into_iter().enumerate() {
                if v.map(|v| v.is_nan()).unwrap_or(true) {
                    n_missing_rows += 1;
                    if missing_rows.len() < 3 {
                        missing_rows.push(row);
                    }
                }
            }
        }
    }

    let mut samples = String::new();
    for &row in &missing_rows {
        let key_desc: Vec<String> = key_cols
            .iter()
            .map(|kc| {
                // Unit-length literals broadcast; index them at 0.
                let at = if kc.len() == 1 { 0 } else { row };
                match kc.get(at) {
                    Ok(av) => format!("{}={}", kc.name(), av),
                    Err(_) => format!("{}=?", kc.name()),
                }
            })
            .collect();
        samples.push_str(&format!(" (row {}: {})", row, key_desc.join(", ")));
    }

    Err(polars_err!(ComputeError:
        "Lookup on table '{}' has {} row(s) with missing keys (or NaN-valued entries); first misses:{}. \
         Keys must exist in the table (exact match). Pass on_missing=\"nan\" or a numeric fill value \
         to Table(...) or lookup(...) to restore silent-NaN behaviour.",
        table_name, n_missing_rows, samples))
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

    #[pyo3(signature = (name, df, keys, value_column, storage_mode="auto"))]
    fn register_table(
        &self,
        name: String,
        df: PyDataFrame,
        keys: Vec<String>,
        value_column: String,
        storage_mode: Option<&str>,
    ) -> PyResult<()> {
        let rust_df: DataFrame = df.into();
        let mode = StorageMode::from_str(storage_mode.unwrap_or("auto"))
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{}", e)))?;

        log::debug!(
            "PyAssumptionTableRegistry::register_table: Registering table '{}' with {} rows, keys: {:?}, value_column: '{}', mode: {:?}",
            name, rust_df.height(), keys, value_column, mode
        );

        // Use the global registry function with mode
        register_assumption_table_global_with_mode(name.clone(), rust_df, keys, value_column, mode)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{}", e)))?;

        // Verify registration
        let registry = get_global_assumption_registry();
        let available_tables = registry.list_tables();
        log::debug!(
            "PyAssumptionTableRegistry::register_table: Successfully registered '{}'. Registry now has {} tables: {:?}",
            name, available_tables.len(), available_tables
        );

        Ok(())
    }

    #[pyo3(signature = (name, df, keys, value_column))]
    fn append_to_table(
        &self,
        name: String,
        df: PyDataFrame,
        keys: Vec<String>,
        value_column: String,
    ) -> PyResult<()> {
        let rust_df: DataFrame = df.into();

        // Use the global append function
        append_to_assumption_table_global(name, rust_df, keys, value_column)
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
        Ok(registry.list_tables())
    }

    fn reset(&self) -> PyResult<()> {
        // Reset the global registry
        reset_global_assumption_registry();
        Ok(())
    }

    fn get_table_metadata(&self, name: String) -> PyResult<Option<(usize, Vec<String>)>> {
        // Get table metadata: (key_count, key_names)
        let registry = get_global_assumption_registry();
        if let Some(table) = registry.get_table(&name) {
            let key_count = table.get_key_count();
            let key_names = table.get_key_columns_owned();
            Ok(Some((key_count, key_names)))
        } else {
            Ok(None)
        }
    }

    fn table_exists(&self, name: String) -> PyResult<bool> {
        // Check if table exists in global registry
        let registry = get_global_assumption_registry();
        Ok(registry.table_exists(&name))
    }

    fn get_table_storage_mode(&self, name: String) -> PyResult<Option<String>> {
        let registry = get_global_assumption_registry();
        if let Some(table) = registry.get_table(&name) {
            let mode = match table.storage_mode() {
                StorageMode::Hash => "hash",
                StorageMode::Array => "array",
                StorageMode::Auto => "auto",
            };
            Ok(Some(mode.to_string()))
        } else {
            Ok(None)
        }
    }

    #[pyo3(signature = (name, df, keys, value_column, force_replace=true, storage_mode="auto"))]
    fn register_or_replace_table(
        &self,
        name: String,
        df: PyDataFrame,
        keys: Vec<String>,
        value_column: String,
        force_replace: Option<bool>,
        storage_mode: Option<&str>,
    ) -> PyResult<()> {
        let rust_df: DataFrame = df.into();
        let force = force_replace.unwrap_or(true);
        let mode = StorageMode::from_str(storage_mode.unwrap_or("auto"))
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{}", e)))?;

        log::debug!(
            "PyAssumptionTableRegistry::register_or_replace_table: Registering/replacing table '{}' with {} rows, keys: {:?}, value_column: '{}', force_replace: {}, mode: {:?}",
            name, rust_df.height(), keys, value_column, force, mode
        );

        // Use the new idempotent registry function with mode
        register_or_replace_assumption_table_global_with_mode(
            name.clone(),
            rust_df,
            keys,
            value_column,
            force,
            mode,
        )
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{}", e)))?;

        // Verify registration
        let registry = get_global_assumption_registry();
        let available_tables = registry.list_tables();
        log::debug!(
            "PyAssumptionTableRegistry::register_or_replace_table: Successfully registered/replaced '{}'. Registry now has {} tables: {:?}",
            name, available_tables.len(), available_tables
        );

        Ok(())
    }
}
