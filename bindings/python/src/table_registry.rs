use gaspatchio_core_lib::index::{self as core_index, RegistryError, TransformSpec, TransformType}; // Use alias
use polars::prelude::DataFrame; // Removed unused Polars types
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3_polars::PyDataFrame;
// Removed PyExpr import
// Removed unused import: Mutex
// Removed HashMap import as core_index::TableRegistry is used
use pyo3::{types::PyDict, FromPyObject, PyAny, PyObject, PyResult, Python};

// Removed unused global static registry instance
// static REGISTRY: Lazy<Mutex<core_index::TableRegistry>> =
//     Lazy::new(|| Mutex::new(core_index::TableRegistry::new()));

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
#[derive(Debug, Clone)]
struct PyTransformSpec {
    transform_type: PyTransformType,
    id_vars: Vec<String>,
    value_vars: Vec<String>,
    var_name: String,
    value_name: String,
}

// Manual implementation of FromPyObject for PyTransformSpec
impl<'source> FromPyObject<'source> for PyTransformSpec {
    fn extract_bound(ob: &Bound<'source, PyAny>) -> PyResult<Self> {
        // Try to cast the PyAny to a PyDict
        let dict: &Bound<'source, PyDict> = ob.downcast()?;

        // Extract fields, providing clear errors if keys are missing or types are wrong
        let transform_type: PyTransformType = dict
            .get_item("transform_type")?
            .ok_or_else(|| PyValueError::new_err("'transform_type' key missing in transform_spec"))?
            .extract()?;

        let id_vars: Vec<String> = dict
            .get_item("id_vars")?
            .ok_or_else(|| PyValueError::new_err("'id_vars' key missing in transform_spec"))?
            .extract()?;

        let value_vars: Vec<String> = dict
            .get_item("value_vars")?
            .ok_or_else(|| PyValueError::new_err("'value_vars' key missing in transform_spec"))?
            .extract()?;

        let var_name: String = dict
            .get_item("var_name")?
            .ok_or_else(|| PyValueError::new_err("'var_name' key missing in transform_spec"))?
            .extract()?;

        let value_name: String = dict
            .get_item("value_name")?
            .ok_or_else(|| PyValueError::new_err("'value_name' key missing in transform_spec"))?
            .extract()?;

        Ok(PyTransformSpec {
            transform_type,
            id_vars,
            value_vars,
            var_name,
            value_name,
        })
    }
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
    #[pyo3(signature = (name, df, keys, value_column, transform_spec_py=None))]
    fn register_table(
        &self,
        py: Python, // Add Python GIL token
        name: String,
        df: PyDataFrame,
        keys: Vec<String>,
        value_column: String,
        transform_spec_py: Option<PyObject>, // Accept PyObject (representing the dict or None)
    ) -> PyResult<()> {
        // Convert PyDataFrame to Rust DataFrame
        let rust_df: DataFrame = df.into();

        // Attempt to extract PyTransformSpec if the PyObject is provided
        let core_transform_spec: Option<TransformSpec> = match transform_spec_py {
            Some(py_obj) => {
                // Bind the PyObject to the GIL
                let bound_obj = py_obj.bind_borrowed(py);
                // Attempt to extract the PyTransformSpec struct from the Python object
                match bound_obj.extract::<PyTransformSpec>() {
                    Ok(py_spec) => Some(py_spec.into()), // Convert to core TransformSpec
                    Err(e) => {
                        return Err(PyValueError::new_err(format!(
                            "Invalid transform_spec structure: {}",
                            e
                        )))
                    }
                }
            }
            None => None, // No transform spec provided
        };

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
