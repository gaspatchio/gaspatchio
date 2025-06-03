pub mod registry;
pub mod table;

pub use registry::{
    append_to_assumption_table_global, get_global_assumption_registry, lookup_assumption_global,
    register_assumption_table_global, reset_global_assumption_registry, AssumptionTableRegistry,
};
pub use table::AssumptionTable;
