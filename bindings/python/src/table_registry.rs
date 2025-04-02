use gaspatchio_core_lib::index::{self as core_index, RegistryError, TransformSpec, TransformType}; // Use alias
use once_cell::sync::Lazy;
use polars::prelude::{DataFrame, PolarsError}; // Removed unused Polars types
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3_polars::PyDataFrame; // Removed PyExpr import
use std::sync::Mutex;
// Removed HashMap import as core_index::TableRegistry is used

// Global static registry instance, protected by a Mutex
// Use the actual core TableRegistry now.
static REGISTRY: Lazy<Mutex<core_index::TableRegistry>> =
    Lazy::new(|| Mutex::new(core_index::TableRegistry::new()));

// Enum to represent transform type from Python
#[derive(Debug, Clone)]
enum PyTransformType {
    WideToLong,
    // Add future transform types here
}

impl From<PyTransformType> for TransformType {
    fn from(py_type: PyTransformType) -> Self {
        match py_type {
            PyTransformType::WideToLong => TransformType::WideToLong,
        }
    }
}

// Manual implementation of FromPyObject for PyTransformType
impl<'py> FromPyObject<'py> for PyTransformType {
    fn extract_bound(ob: &Bound<'py, PyAny>) -> PyResult<Self> {
        let s: String = ob.extract()?;
        match s.to_lowercase().as_str() {
            "widetolong" | "wide_to_long" => Ok(PyTransformType::WideToLong),
            _ => Err(PyValueError::new_err(format!(
                "Unknown transform type: '{}'. Expected 'WideToLong'.",
                s
            ))),
        }
    }
}

// Struct to receive transform specification from Python
#[derive(FromPyObject, Debug, Clone)]
struct PyTransformSpec {
    transform_type: PyTransformType,
    id_vars: Vec<String>,
    value_vars: Vec<String>,
    var_name: String,
    value_name: String,
}

// Conversion from PyO3 struct to core Rust struct
impl From<PyTransformSpec> for TransformSpec {
    fn from(py_spec: PyTransformSpec) -> Self {
        TransformSpec {
            transform_type: py_spec.transform_type.into(),
            id_vars: py_spec.id_vars,
            value_vars: py_spec.value_vars,
            var_name: py_spec.var_name,
            value_name: py_spec.value_name,
        }
    }
}

#[pyclass]
pub struct PyTableRegistry;

#[pymethods]
impl PyTableRegistry {
    #[new]
    fn new() -> Self {
        PyTableRegistry
    }

    /// Registers a table (DataFrame) with the global registry.
    ///
    /// Args:
    ///     name (str): The unique name for this table in the registry.
    ///     df (polars.DataFrame): The DataFrame containing the assumption data.
    ///     keys (list[str]): List of column names to use as lookup keys *after* transformation.
    ///     value_column (str): The name of the column containing the values *after* transformation.
    ///     transform_spec (dict | None): Optional dictionary specifying how to transform the input `df`
    ///         before creating the lookup index. Required keys depend on `transform_type`.
    ///         For `WideToLong`: `transform_type`, `id_vars`, `value_vars`, `var_name`, `value_name`.
    #[pyo3(signature = (name, df, keys, value_column, transform_spec=None))]
    fn register_table(
        &self,
        name: String,
        df: PyDataFrame,
        keys: Vec<String>,
        value_column: String,
        transform_spec: Option<PyTransformSpec>, // Use the PyO3 struct
    ) -> PyResult<()> {
        // Convert PyDataFrame to Rust DataFrame
        let rust_df: DataFrame = df.into();

        // Convert the Python transform spec to the core Rust transform spec
        let core_transform_spec: Option<TransformSpec> =
            transform_spec.map(|py_spec| py_spec.into());

        // Call the core registration function
        core_index::register_table(
            &name, // Pass name as &str
            rust_df,
            keys,
            &value_column, // Pass value_column as &str
            core_transform_spec,
        )
        .map_err(registry_error_to_py_err) // Map RegistryError to PyErr
    }

    // lookup_assumption will be added here later
}

// Helper function to convert RegistryError to PyErr
fn registry_error_to_py_err(e: RegistryError) -> PyErr {
    PyValueError::new_err(e.to_string())
}

// Helper function to convert PyO3 error to PolarsError
fn py_err_to_polars(e: PyErr) -> PolarsError {
    PolarsError::ComputeError(e.to_string().into())
}

// Make sure this module is added to lib.rs
pub fn register_registry_module(
    py: Python<'_>,
    parent_module: &Bound<'_, PyModule>,
) -> PyResult<()> {
    let registry_module = PyModule::new(py, "registry")?;
    registry_module.add_class::<PyTableRegistry>()?;
    parent_module.add_submodule(&registry_module)?;
    Ok(())
}
