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
}

// --- Binding Plugin Implementation ---

fn lookup_output_type(_input_fields: &[Field]) -> PolarsResult<Field> {
    let value_dtype = DataType::Float64; // Assuming float64 for now, might need dynamic type later
    Ok(Field::new(
        PlSmallStr::from_static("lookup_result"),
        // Vector lookup returns a list
        DataType::List(Box::new(value_dtype)),
    ))
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
