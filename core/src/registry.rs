use crate::index::LookupIndex;
use polars::prelude::*;
use std::collections::HashMap;

/// A registry that stores lookup tables and their indices.
#[derive(Debug, Clone, Default)]
pub struct TableRegistry {
    /// Original tables
    tables: HashMap<String, DataFrame>,
    /// Pre-built lookup indices
    lookup_indices: HashMap<String, LookupIndex>,
}

impl TableRegistry {
    /// Creates a new empty registry.
    pub fn new() -> Self {
        Self::default()
    }

    /// Gets a reference to a registered table.
    pub fn get_table(&self, name: &str) -> Option<&DataFrame> {
        self.tables.get(name)
    }

    /// Gets a reference to a lookup index.
    pub fn get_lookup_index(&self, name: &str) -> Option<&LookupIndex> {
        self.lookup_indices.get(name)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_registry_basics() {
        let registry = TableRegistry::new();
        assert!(registry.get_table("test").is_none());
        assert!(registry.get_lookup_index("test").is_none());
    }
}
