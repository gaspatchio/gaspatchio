mod assumptions;
mod table_registry;
mod vector;

use log::{debug, info};
use pyo3::prelude::*;

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

    // Register our submodules
    table_registry::register_registry_module(m.py(), m)?;
    // assumptions::register_assumptions_functions(m.py(), m)?; // Removed, registration via Python polars plugin API

    Ok(())
}
