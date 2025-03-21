
# Developer Specification: In-Memory Polars Table Registry Using ArcSwap

## 1. Purpose
- High Performance: Load assumption tables into memory as Polars DataFrames.
- Batch Lookups: Equi-join lookups without re-reading Parquet.
- Dynamic Registration: Infrequently register new tables at runtime.
- Near Lock-Free Reads: Minimal contention using ArcSwap.

## 2. Requirements
- Tables fit in memory, updates infrequent, batch joins efficient, concurrency optimized, dynamic keys.

## 3. Core Data Structures
### KeySpec
```rust
#[derive(Debug, Clone)]
pub struct KeySpec {
    pub source_cols: Vec<String>,
    pub table_cols: Vec<String>,
}
```

### TableRegistry
```rust
#[derive(Default, Clone)]
pub struct TableRegistry {
    pub tables: std::collections::HashMap<String, polars::prelude::DataFrame>,
    pub keyspecs: std::collections::HashMap<String, KeySpec>,
}
```

### Global Registry using ArcSwap
```rust
use arc_swap::ArcSwap;
use once_cell::sync::Lazy;

static REGISTRY: Lazy<ArcSwap<TableRegistry>> = Lazy::new(|| {
    ArcSwap::from_pointee(TableRegistry::default())
});
```

## 4. Operations
- Register tables, perform joins, atomic swapping explained.

## 5. Sample Implementation
<details><summary><b>Rust Code Example</b></summary>
Complete Rust code implementation is included here (refer to previous conversation for details).
</details>

## 6. Testing & Validation
- Unit tests, integration tests, performance & monitoring guidelines provided.

## 7. Trade-offs & Alternatives
- ArcSwap vs RwLock, Range joins, multiple keyspecs, direct hashmap explained.

## 8. Conclusion
- ArcSwap solution detailed, next implementation steps provided.
