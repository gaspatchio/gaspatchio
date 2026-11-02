#![allow(clippy::needless_pass_by_value)] // PyO3 functions often need owned types

// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

use polars::prelude::*;
use polars::prelude::{DataType, Field, PlSmallStr, PolarsResult, Series};
use pyo3::PyResult;
use pyo3_polars::derive::polars_expr;
use pyo3_polars::PyDataFrame;

use pyo3::prelude::*;
use serde::Deserialize;
use std::str::FromStr;

use gaspatchio_core_lib::assumptions::{
    append_to_assumption_table_global, append_to_assumption_table_global_with_identity,
    get_global_assumption_registry, missing_keys_refusal,
    register_assumption_table_global_with_mode,
    register_or_replace_assumption_table_global_with_identity,
    register_or_replace_assumption_table_global_with_mode, reset_global_assumption_registry,
    StorageMode, SAMPLE_KEY_CAP,
};

// Kwargs struct for the assumption lookup plugin.
//
// The four identity fields carry no `serde(default)` on purpose, and the
// reason is not that a lookup is never written down. One is: the published
// vector in `gaspatchio/schemas/vectors/lookup.json` is a lookup plan node on
// disk, read back and run again by the conformance test beside it. It crosses
// versions safely because it carries only the graph's own attributes -- the
// table's name, its content fingerprint, the miss policy -- and
// `_lower_lookup` mints `key_columns` and `value_column` fresh from the
// running process's table directory each time it lowers one.
//
// What this struct reads is the other half of that, and the property holding
// it up is narrower: a payload is written and read by the same installation.
// A plan names its plugin by the path of the `.so` sitting beside the
// lowering that wrote it. Pickling a frame mid-model and reading it back in
// the same process carries every field of the payload verbatim and runs,
// which is the round trip the tests pin. A payload from any other build is
// refused here, by the name of the field it is short of. That refusal is the
// intended outcome and not a gap.
//
// A default would blunt it. It would fire by inventing an empty content
// fingerprint or an empty key list, and that lookup would go on to fail the
// identity check against the directory several steps later, complaining about
// a table whose name the author never wrote.
#[derive(Deserialize, Debug, Clone)]
pub struct AssumptionLookupKwargs {
    /// Registered name the lookup resolves by at execution time.
    pub table_name: String,
    /// Processed content and registration schema captured when the plan was built.
    pub table_fingerprint: String,
    /// Key columns of the processed table, in the order the operands arrive.
    pub key_columns: Vec<String>,
    /// Value column the rate is read from.
    pub value_column: String,
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

    // The identity check and value read share one immutable registry snapshot.
    // Replacement between streamed chunks may make the next chunk refuse;
    // no chunk can silently serve replacement data under the old identity.
    let table = registry.require_table_identity(
        table_name,
        &kwargs.table_fingerprint,
        &kwargs.key_columns,
        &kwargs.value_column,
    )?;

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
        &kwargs.key_columns,
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
    key_columns: &[String],
    table_name: &str,
    on_missing: Option<&str>,
    fill_value: Option<f64>,
) -> PolarsResult<Series> {
    match on_missing.unwrap_or("raise") {
        "nan" => Ok(result),
        "fill" => fill_missing(result, fill_value.unwrap_or(f64::NAN)),
        _ => raise_if_missing(result, key_cols, key_columns, table_name),
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

/// Name a lookup operand the way the reader wrote it.
///
/// An operand carries its own column name (`attained_age`), which is what
/// the reader recognises and what every engine reports. A key passed as a
/// value -- `lookup(product="annuity", ...)` -- arrives as a Polars literal
/// whose name is the engine's placeholder `literal`, which names nothing the
/// reader wrote; that key is named by the table's own key column instead,
/// which `key_columns` holds in the order the operands arrive.
fn operand_name<'a>(key_col: &'a Series, at: usize, key_columns: &'a [String]) -> &'a str {
    let name = key_col.name().as_str();
    if name == "literal" {
        if let Some(column) = key_columns.get(at) {
            return column.as_str();
        }
    }
    name
}

fn raise_if_missing(
    result: Series,
    key_cols: &[&Series],
    key_columns: &[String],
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

    // The position a miss is found at is how its key value is fetched and goes
    // no further: the reader is given the key, which names the same rows in
    // the frame under either engine, and never a number that only holds
    // inside this batch.
    let key_at = |row: usize| -> String {
        key_cols
            .iter()
            .enumerate()
            .map(|(i, kc)| {
                // Unit-length literals broadcast; index them at 0.
                let at = if kc.len() == 1 { 0 } else { row };
                let name = operand_name(kc, i, key_columns);
                match kc.get(at) {
                    Ok(av) => format!("{name}={av}"),
                    Err(_) => format!("{name}=?"),
                }
            })
            .collect::<Vec<String>>()
            .join(", ")
    };

    // The sample is scoped to the batch of rows this call was handed. The
    // engine hands an elementwise plugin one batch per call and passes no row
    // offset with it (polars-plan 0.53.0, `call_plugin`, which builds a fresh
    // `CallerContext` whose only field is a PARALLEL bit), so neither a
    // position nor a total here can be spoken of as the frame's -- and no
    // count is reported at all: a batch's count read as the frame's
    // is a wrong number, and the keys already find every row. The sample
    // collects DISTINCT keys: a batch that misses the same attained age forty
    // times has one key to report.
    let mut sample_keys: Vec<String> = Vec::new();
    let note_miss = |row: usize, sample_keys: &mut Vec<String>| {
        if sample_keys.len() < SAMPLE_KEY_CAP {
            let key = key_at(row);
            if !sample_keys.contains(&key) {
                sample_keys.push(key);
            }
        }
    };
    match result.dtype() {
        DataType::List(_) => {
            let lc = result.list()?;
            for row in 0..lc.len() {
                let row_has_nan = lc
                    .get_as_series(row)
                    .and_then(|s| s.f64().ok().map(|ca| ca.is_nan().any()))
                    .unwrap_or(false);
                if row_has_nan {
                    note_miss(row, &mut sample_keys);
                }
            }
        }
        _ => {
            let ca = result.f64()?;
            for (row, v) in ca.into_iter().enumerate() {
                if v.map(|v| v.is_nan()).unwrap_or(true) {
                    note_miss(row, &mut sample_keys);
                }
            }
        }
    }

    // The key column names go on the refusal's first line with the table:
    // they are the same under every engine and in every batch, which is what
    // lets the collect-time replay match this failure to the calculation that
    // raised it. The samples above vary with the batch and go on the line
    // after.
    let named: Vec<&str> = key_cols
        .iter()
        .enumerate()
        .map(|(i, kc)| operand_name(kc, i, key_columns))
        .collect();

    Err(polars_err!(
        ComputeError: "{}",
        missing_keys_refusal(table_name, &named, &sample_keys)
    ))
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

    #[pyo3(signature = (name, df, keys, value_column, *, fingerprint=None, expected_fingerprint=None))]
    fn append_to_table(
        &self,
        name: String,
        df: PyDataFrame,
        keys: Vec<String>,
        value_column: String,
        fingerprint: Option<String>,
        expected_fingerprint: Option<String>,
    ) -> PyResult<()> {
        let rust_df: DataFrame = df.into();

        let result = match (expected_fingerprint, fingerprint) {
            (Some(expected), Some(next)) => append_to_assumption_table_global_with_identity(
                name,
                rust_df,
                keys,
                value_column,
                expected,
                next,
            ),
            (None, None) => append_to_assumption_table_global(name, rust_df, keys, value_column),
            _ => {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "append requires both fingerprint and expected_fingerprint, or neither",
                ))
            }
        };
        result.map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

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

    #[pyo3(signature = (name, df, keys, value_column, force_replace=true, storage_mode="auto", *, fingerprint=None))]
    fn register_or_replace_table(
        &self,
        name: String,
        df: PyDataFrame,
        keys: Vec<String>,
        value_column: String,
        force_replace: Option<bool>,
        storage_mode: Option<&str>,
        fingerprint: Option<String>,
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
        let result = match fingerprint {
            Some(fingerprint) => register_or_replace_assumption_table_global_with_identity(
                name.clone(),
                rust_df,
                keys,
                value_column,
                force,
                mode,
                fingerprint,
            ),
            None => register_or_replace_assumption_table_global_with_mode(
                name.clone(),
                rust_df,
                keys,
                value_column,
                force,
                mode,
            ),
        };
        result.map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{}", e)))?;

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
