# Gaspatchio Architecture

Gaspatchio is a high-performance actuarial modeling framework that combines Python's ease of use with Rust's computational efficiency. This document explains the major architectural decisions and the core components of the system.

## 1. Hybrid Architecture: Python Interface, Rust Engine

Gaspatchio follows a hybrid architecture to balance developer experience with execution speed:

-   **Python Layer (`gaspatchio_core` Python package)**: Provides the user-facing API, including `ActuarialFrame`, `Table`, and domain-specific accessors. It handles API ergonomics, type hinting, and integration with the Python ecosystem.
-   **Rust Layer (`gaspatchio_core` Rust crate)**: Implements performance-critical components, including the `TableRegistry`, assumption lookups, and specialized vector functions. It exposes these via PyO3 bindings.
-   **Polars Backbone**: The framework relies heavily on [Polars](https://pola.rs/) for efficient, multi-threaded DataFrame operations. `ActuarialFrame` wraps Polars structures to add actuarial intelligence without sacrificing performance.

## 2. ActuarialFrame: The Core Abstraction

`ActuarialFrame` is the primary data structure, wrapping a Polars `LazyFrame` (or `DataFrame`) to provide:

1.  **Context-Aware Execution**: Supports different execution modes (`run`, `optimize`, `debug`).
2.  **Tracing & Optimization**: Captures operations in a computation graph to optimize execution plans.
3.  **Domain Accessors**: Namespaced extensions for actuarial logic (e.g., `af.date`, `af.finance`).

### Execution Modes

-   **Run (Eager)**: Operations are executed immediately. Best for interactive exploration and simple scripts.
-   **Optimize (Lazy/Graph)**: Operations are recorded in a computation graph. The system optimizes the graph before execution. This is the primary mode for production models.
-   **Debug**: detailed logging and tracing to help diagnose issues in complex models.

### Tracing

The `trace` decorator allows functions to be captured as sub-graphs, enabling the optimizer to see through function calls and optimize the entire model end-to-end.

```python
@af.trace
def calculate_premium(af):
    af.premium = af.sum_assured * af.premium_rate
```

## 3. Assumption Tables (v2 API)

Gaspatchio implements a specialized assumption table system designed for high-performance actuarial lookups.

### Key Concepts

-   **Table**: Represents a loaded assumption table (e.g., Mortality, Lapse). It handles dimension processing and registration with the Rust backend.
-   **Dimensions**: Tables are structured by dimensions (e.g., `age`, `duration`, `calendar_year`).
-   **Storage**: Tables are stored in a global, thread-safe registry in Rust.
    -   **Array Storage**: Ultra-fast (nanosecond scale) lookups for dense, integer-keyed tables (e.g., standard mortality tables).
    -   **Hash Storage**: Fast lookups for sparse or string-keyed tables.
    -   **Auto-Selection**: The system automatically chooses the optimal storage backend.

### Usage Pattern

Instead of manual joins, Gaspatchio uses a `lookup` API that compiles to efficient Rust plugin calls.

```python
from gaspatchio_core.assumptions import Table

# 1. Define and Register Table
mortality = Table(
    name="mortality_2024",
    source=df,
    dimensions={"age": "age_nearest", "gender": "sex"},
    value="qx"
)

# 2. Perform Lookup
# Returns a Polars expression that executes efficiently in Rust
af.qx = mortality.lookup(
    age=af.age_at_entry + af.duration,
    gender=af.gender
)
```

### Advanced Features

-   **Scenarios**: Tables can be loaded from scenario files or templates (`Table.from_scenario_files`).
-   **Shocks**: Apply shocks (multiplicative, additive, overrides) to tables for sensitivity analysis (`Table.from_shocks`).
-   **Metadata**: Tables carry rich metadata for governance and documentation.

## 4. Domain Accessors

Functionality is organized into namespaces to keep the API clean and discoverable:

-   **`af.date`**: Date arithmetic (e.g., `add_months`, `create_timeline`, `add_duration`).
-   **`af.finance`**: Financial functions (e.g., `npv`, `irr`, `discount_factors`).
-   **`af.excel`**: Excel-compatible implementations of common functions.

These accessors are dynamically registered and can be extended by plugins.

## 5. Performance Strategy

1.  **Vectorization**: All operations are vectorized. There are no Python loops over rows.
2.  **Lazy Evaluation**: `ActuarialFrame` builds a query plan that Polars optimizes (projection pushdown, predicate pushdown).
3.  **Rust Extensions**: Custom Polars plugins (written in Rust) handle operations that are hard to express efficiently in standard expression languages (e.g., complex conditional logic on lists, specific actuarial lookups).
4.  **Zero-Copy**: Data is passed between Python and Rust with minimal copying using Arrow memory format.

## 6. Directory Structure

-   `core/`: Rust implementation of the engine, registry, and plugins.
-   `bindings/python/`: Python package (`gaspatchio_core`), PyO3 bindings, and CLI.
-   `ref/`: Architecture references and RFCs.
