mod assumptions;
mod table_registry;
mod vector;
use gaspatchio_core_lib::index::reset_global_registry as rust_reset_global_registry;

use log::{debug, info};
use pyo3::prelude::*;

#[pyfunction]
fn reset_global_registry() -> PyResult<()> {
    rust_reset_global_registry();
    Ok(())
}

#[pymodule]
fn _internal(m: &Bound<PyModule>) -> PyResult<()> {
    // Initialize pyo3-log to redirect Rust logs to Python logging
    pyo3_log::init();

    // Initialize env_logger to make sure Rust logs are emitted
    // This is in addition to pyo3-log, as a fallback
    match env_logger::try_init() {
        Ok(_) => debug!("Initialized env_logger"),
        Err(e) => debug!("env_logger already initialized or error: {}", e),
    }

    info!("Initializing gaspatchio_core");
    debug!("Debug logging enabled");
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;

    // Add the PyTableRegistry class directly to the internal module
    m.add_class::<table_registry::PyTableRegistry>()?;

    m.add_class::<assumptions::PyAssumptionTableRegistry>()?;

    // Add the reset function
    m.add_function(wrap_pyfunction!(reset_global_registry, m)?)?;

    // Register our submodules (which might now be less necessary if classes are added directly)
    // table_registry::register_registry_module(m.py(), m)?;
    // assumptions::register_assumptions_functions(m.py(), m)?; // Removed, registration via Python polars plugin API

    Ok(())
}
