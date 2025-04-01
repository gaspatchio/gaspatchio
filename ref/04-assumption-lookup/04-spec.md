# Developer Specification: High-Performance Vector Lookup Registry

## Overview

This specification defines a new architecture for supporting fast, scalable lookups in actuarial models. It is designed for use cases like mortality, lapse, premium, and benefit rate lookups, particularly when vector projections (e.g., ages over time) are involved.

The system replaces our previous `KeySpec`- and explode-based pipeline with a new table registry and plugin function that performs direct, in-memory `HashMap` lookups using scalar or list inputs.

---

## Objectives

- Replace explode-based vector lookups with a high-performance, plugin-based approach
- Support arbitrary key combinations (e.g., `age_last + gender`, `duration + channel`, etc.)
- Allow lookup inputs to be scalars or lists (vectors) per row
- Eliminate need for dataframe explosion or re-grouping
- Use pre-indexed in-memory hash maps for fast runtime performance
- Integrate via Polars plugin expressions with full Python bindings

---

## Design Principles

- Vector in, vector out: no explode/collect cycles
- HashMap-based key indexing for fast lookup
- Flexible key schemas: tables define their own key columns
- Purely functional: registry is read-only at runtime, initialized up front
- All joins implemented as plugin expressions for lazy + optimized execution

---

## Project Architecture

This project follows a modular architecture with clear separation of concerns:

### 1. Core Rust Library (`gaspatchio-core/core`)
- Contains all core functionality, data structures, and algorithms
- No PyO3 dependencies or references
- Benchmarkable and testable in pure Rust
- Includes all lookup registry logic, HashMap building, and plugin expressions
- Integration and unit tests for all functionality

```
gaspatchio-core/core/
├── src/
│   ├── registry/           # TableRegistry implementation
│   ├── polars_functions/   # Polars plugin expressions
│   ├── transform/          # Data transformation utilities
│   └── index/              # Lookup index and HashMap builders
├── benches/                # Performance benchmarks
├── tests/                  # Integration tests
└── Cargo.toml              # Core dependencies only
```

### 2. PyO3 Bindings (`gaspatchio-core/bindings/python`)
- Thin layer that exposes core functionality to Python
- Handles conversion between Python and Rust types
- Only place where PyO3 dependencies should exist
- No business logic, only binding code

```
gaspatchio-core/bindings/python/
├── src/
│   ├── lib.rs              # PyO3 module definition
│   ├── registry.rs         # Python bindings for TableRegistry
│   └── vector.rs           # Export plugin functions to Python
└── Cargo.toml              # PyO3 and core dependencies
```

### 3. Python Interface (`gaspatchio-core/bindings/python/gaspatchio_core`)
- Pure Python code for user-friendly interface
- Polars plugin registration
- Type conversions and convenience functions
- Documentation and examples

```
gaspatchio-core/bindings/python/gaspatchio_core/
├── __init__.py             # Package exports
├── functions.py            # Plugin function wrappers
├── registry.py             # TableRegistry Python interface
└── typing.py               # Type definitions
```

### Motivation for This Architecture

This separation provides several benefits:
1. **Core Library Purity**: The core Rust implementation remains focused and PyO3-free, making it easier to test, benchmark, and maintain.
2. **Multiple Bindings**: Future bindings to other languages (R, JavaScript, etc.) can be added without modifying the core library.
3. **Testing Efficiency**: Core functionality can be tested in Rust without Python dependencies, allowing for faster test cycles.
4. **Performance Optimization**: Benchmarking can be done directly on the core library, ensuring optimal performance.
5. **Maintainability**: Changes to the Python interface don't require recompiling the Rust code, and vice versa.

---

## Components

### 1. `TableRegistry`
A global, read-only registry storing assumption tables and pre-built lookup indices.

```rust
use std::sync::Arc;
use arc_swap::ArcSwap;
use once_cell::sync::Lazy;

pub struct TableRegistry {
    pub tables: HashMap<String, DataFrame>,
    pub lookup_indices: HashMap<String, LookupIndex>,
}

pub struct LookupIndex {
    pub keys: Vec<String>,             // e.g., ["age_last", "gender_smoking"]
    pub value_column: String,          // e.g., "mortality_rate"
    pub index: HashMap<Vec<Value>, Value>, // Fast lookup map
}

pub enum Value {
    Int(i64),
    Float(f64),
    Str(String),
}

// Global registry with ArcSwap for near lock-free reads
static REGISTRY: Lazy<ArcSwap<TableRegistry>> = Lazy::new(|| {
    ArcSwap::from_pointee(TableRegistry::default())
});

impl TableRegistry {
    pub fn get_registry() -> Arc<TableRegistry> {
        REGISTRY.load().clone()
    }

    pub fn set_registry(new_reg: TableRegistry) {
        REGISTRY.store(Arc::new(new_reg));
    }

    pub fn register_table(&mut self, name: &str, df: DataFrame, keys: Vec<String>, value_column: String) -> Result<()> {
        // Build HashMap<Vec<Value>, Value> from rows
        let index = build_lookup_index(&df, &keys, &value_column)?;
        
        let lookup_index = LookupIndex {
            keys,
            value_column: value_column.to_string(),
            index,
        };

        // Update registry
        self.tables.insert(name.to_string(), df);
        self.lookup_indices.insert(name.to_string(), lookup_index);
        Ok(())
    }
}
```

The `TableRegistry` provides:
- Near lock-free reads using `ArcSwap`
- Thread-safe global state management
- Fast HashMap-based lookups
- Support for both DataFrame and pre-indexed lookups

#### Performance Characteristics:
- Read operations: O(1) - just an atomic pointer read
- Registration: O(n) where n is size of existing registry (due to clone)
- Lookup: O(1) average case using HashMap
- Memory: 2x overhead during registration due to clone

#### Usage Example:
```rust
// Reading from registry
let registry = TableRegistry::get_registry();
let table = registry.tables.get("mortality_rates")?;

// Registering new table
let old_registry = TableRegistry::get_registry();
let mut new_registry = (*old_registry).clone();
new_registry.register_table("mortality_rates", df, keys, "rate")?;
TableRegistry::set_registry(new_registry);
```

### 2. `register_table`
Registers a table into the global registry and pre-builds the lookup index.

```rust
pub fn register_table(
    name: &str,
    df: DataFrame,
    keys: Vec<&str>,
    value_column: &str,
    transform_spec: Option<&TransformSpec> = None
) -> Result<()> {
    // Apply transformation if specified
    let transformed_df = if let Some(spec) = transform_spec {
        match spec.type_value() {
            TransformType::WIDE_TO_LONG => {
                // Extract fields from the WideToLongTransform
                let id_vars = spec.id_vars();
                let value_vars = spec.value_vars();
                let var_name = spec.var_name();
                let value_name = spec.value_name();
                
                // Transform wide format to long format using melt
                df.lazy()
                    .melt(
                        id_vars.iter().map(|s| s.to_string()).collect(),
                        value_vars.iter().map(|s| s.to_string()).collect(),
                        Some(var_name.to_string()),
                        Some(value_name.to_string()),
                    )
                    .collect()?
            }
            // Add handling for future transform types here
        }
    } else {
        df
    };
    
    // Build HashMap<Vec<Value>, Value> from rows
    let index = build_lookup_index(&transformed_df, &keys, value_column)?;
    
    // Get current registry
    let old_registry = TableRegistry::get_registry();
    let mut new_registry = (*old_registry).clone();
    
    // Add lookup index to registry
    let lookup_index = LookupIndex {
        keys: keys.iter().map(|&s| s.to_string()).collect(),
        value_column: value_column.to_string(),
        index,
    };
    
    // Store both the transformed DataFrame and lookup index
    new_registry.tables.insert(name.to_string(), transformed_df);
    new_registry.lookup_indices.insert(name.to_string(), lookup_index);
    
    // Update global registry
    TableRegistry::set_registry(new_registry);
    
    Ok(())
}
```

### 3. `assumption_lookup` Plugin
A plugin expression callable from Polars that performs direct lookups against a table.

```rust
#[polars_expr(output_type_func = dynamic)]
fn assumption_lookup(inputs: &[Series], kwargs: AssumptionLookupKwargs) -> PolarsResult<Series>

#[derive(Deserialize)]
pub struct AssumptionLookupKwargs {
    table_name: String,
}
```

#### Behavior
- Inputs correspond to the lookup key columns for the table
- Each row's keys are zipped into a composite key: `Vec<Value>`
- If any input is a `List`, each element is zipped with the broadcasted scalars
- Returns a `Series` or `ListSeries` of values
- Looks up from the pre-built `HashMap` in constant time

### 4. Python Interface
Expose registration and lookup functions via PyO3 bindings:

```python
assumption_lookup(
    *key_columns,
    table_name="mortality_rates"
) -> Series | List[Series]

register_table(
    name="mortality_rates",
    df: DataFrame,
    keys=["age_last", "gender_smoking"],
    value_column="mortality_rate",
    transform_spec: Optional[TransformSpec] = None
)
```

#### Transform Specification
For table format transformation (e.g., wide to long format), we use Pydantic models:

```python
from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Optional

class TransformType(str, Enum):
    WIDE_TO_LONG = "wide_to_long"
    # Future transform types can be added here
    # RANGE_BUCKETING = "range_bucketing"
    # INTERPOLATION = "interpolation"

class WideToLongTransform(BaseModel):
    type: TransformType = TransformType.WIDE_TO_LONG
    id_vars: List[str] = Field(..., description="Columns to use as identifier variables")
    value_vars: List[str] = Field(..., description="Columns to unpivot")
    var_name: str = Field(..., description="Name to use for the variable column")
    value_name: str = Field(..., description="Name to use for the value column")

# Union type for all transformation types
TransformSpec = WideToLongTransform  # Will become Union[] when more types are added
```

This typed specification ensures validation when registering tables with transformations.

### 5. Example Use Cases

#### Mortality (Vector + Scalar Input) with Table Transformation
```python
import polars as pl
from gaspatchio.assumptions import register_table, assumption_lookup, WideToLongTransform

# Load wide-format mortality table
mortality_df = pl.read_csv("mortality.csv")

# Define transformation specification
transform = WideToLongTransform(
    id_vars=["age-last"],
    value_vars=["MNS", "FNS", "MS", "FS"],
    var_name="gender_smoking",
    value_name="mortality_rate"
)

# Register with transformation
register_table(
    name="mortality_rates",
    df=mortality_df,
    keys=["age-last", "gender_smoking"],
    value_column="mortality_rate",
    transform_spec=transform
)

# Use in model calculation
df["age_last"] = [[31, 33, 34]]            # vector
df["gender_smoking"] = "MNS"              # scalar

# Lookup returns: [mortality_rate for (31, "MNS"), (33, "MNS"), (34, "MNS")]
# df["mortality_rate"] = [0.0012, 0.0014, 0.0015]

df["mortality_rate"] = assumption_lookup(
    df["age_last"],
    df["gender_smoking"],
    table_name="mortality_rates"
)
```

#### Lapse (Multiple Key Columns: Vector + Scalars)
```python
df["duration"] = [[1, 2, 3, 4]]
df["channel"] = "Direct"
df["product_code"] = "TERM10"

# Lookup returns: [lapse_rate for (1, "Direct", "TERM10"), lapse_rate for (2, ...), ...]
df["lapse_rate"] = assumption_lookup(
    df["duration"],
    df["channel"],
    df["product_code"],
    table_name="lapse_table"
)
```

---

## Performance Expectations

| Use Case              | Explode Join | Plugin Lookup |
|-----------------------|--------------|----------------|
| 100k policies, 480 months | ~20 seconds | ~1–2 seconds |
| 1M policies, scalar    | ~5 seconds   | ~0.5 seconds   |
| Memory usage          | High         | Low            |

- Benchmarks assume 1–4 key columns, float64 values
- Hash lookup time: O(1) per key
- Supports vector or scalar lookups equally

---
