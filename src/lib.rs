mod expressions;
mod table_registry;

use log::{debug, info};
use pyo3::prelude::*;
use pyo3_polars::PolarsAllocator;

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

    // Add TableRegistry module
    let table_reg = PyModule::new_bound(m.py(), "table_registry")?;
    table_registry::init_module(&table_reg)?;
    m.add_submodule(&table_reg)?;

    Ok(())
}

#[global_allocator]
static ALLOC: PolarsAllocator = PolarsAllocator::new();
