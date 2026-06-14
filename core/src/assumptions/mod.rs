// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Assumption table storage and lookup functionality.
// ABOUTME: Provides high-performance storage backends (Hash, Array) with auto-selection.

//! Assumption table storage and lookup functionality.
//!
//! This module provides high-performance assumption table storage with two backends:
//!
//! - **Hash Storage**: Uses AHashMap for O(1) average-case lookups. Best for sparse tables.
//! - **Array Storage**: Uses multi-dimensional arrays with dictionary-encoded keys.
//!   Provides faster lookups for dense tables through direct array indexing.
//!
//! # Storage Mode Selection
//!
//! By default (`StorageMode::Auto`), the system automatically chooses:
//! - Array storage for tables with >30% density
//! - Hash storage for sparse tables or large dimensions
//!
//! You can force a specific mode via `AssumptionTable::build_with_mode()`.
//!
//! # Example
//!
//! ```rust,ignore
//! use gaspatchio_core_lib::assumptions::{AssumptionTable, StorageMode};
//!
//! // Auto-select storage
//! let table = AssumptionTable::build(df, keys, value)?;
//!
//! // Force array storage
//! let table = AssumptionTable::build_with_mode(df, keys, value, StorageMode::Array)?;
//! ```

mod array_storage;
mod hash_storage;
mod key_encoder;
pub mod registry;
pub mod table;

pub use array_storage::ArrayStorage;
pub use hash_storage::{ColumnCodec, HashStorage};
pub use key_encoder::KeyEncoder;
pub use registry::{
    append_to_assumption_table_global, get_global_assumption_registry, lookup_assumption_global,
    register_assumption_table_global, register_assumption_table_global_with_mode,
    register_or_replace_assumption_table_global,
    register_or_replace_assumption_table_global_with_mode, reset_global_assumption_registry,
    AssumptionTableRegistry,
};
pub use table::{AssumptionTable, StorageMode, TableStorage};
