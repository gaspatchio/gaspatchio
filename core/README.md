# Gaspatchio Core

Gaspatchio Core is the high-performance Rust engine that powers the Gaspatchio actuarial modeling framework. This library provides the computational backbone for efficient DataFrame operations, assumption table management, and vectorized calculations essential for actuarial projections.

## Overview

Gaspatchio Core is a high-performance Rust library underpinning an actuarial modeling system. It is designed to provide a flexible and efficient backend for complex actuarial calculations.

## Key Features

*   **Polars-Based DataFrame Operations**: Leverages the [Polars](https://pola.rs/) DataFrame library for fast, memory-efficient data manipulation and computation.
*   **In-Memory Table Registry**: Implements a concurrent, in-memory `TableRegistry` using `ArcSwap` for near lock-free reads. This registry stores assumption tables (e.g., mortality, lapse rates) as Polars DataFrames, allowing for high-speed lookups during model runs.
*   **Dynamic Table Transformations**: Supports transformations of tables before registration, such as converting wide-format tables (common in actuarial data) to long-format for easier joining.
*   **Vectorized Lookups**: Provides specialized functions to perform lookups on vector/list columns within DataFrames, essential for time-based projections in actuarial models. This allows for efficient lookup of rates for entire projection arrays in a single operation.
*   **Python-Native DSL Support**: While the core is in Rust, it's designed to support a Python-native DSL. This allows actuaries to write models in familiar Python, with operations captured and optimized by the Rust core. It aims for a dual execution model: a debug mode for interpretability and an optimized mode for performance.
*   **Plugin Architecture**: The system is designed to integrate with custom plugin functions, as seen in `vector.rs`, which can extend its capabilities.

The main logic, including data structures like `AssumptionTable`, `AssumptionTableRegistry`, and core functionalities for building assumption tables, performing scalar and vector lookups, and managing the global table registry, is implemented in `src/assumptions/`.

## Building and Testing

To build the library, ensure you have Rust installed and then run:

```bash
cargo build
```

### Running Tests

Unit and integration tests can be run using:

```bash
cargo test
```

This command will execute all tests defined within the `src` directory and any integration tests in the `tests` directory (if present).

### Running Benchmarks

Performance benchmarks are included to measure the speed of critical operations, particularly DataFrame lookups and joins.

To run the benchmarks:

```bash
cargo bench
```

The benchmarks primarily focus on:

*   **Index Lookups**: Defined in `benches/index_lookups_benchmark.rs`, these tests measure the performance of looking up values from the in-memory `TableRegistry` using various key combinations and data sizes.
*   **Vector Plugin Performance**: Defined in `benches/vector_plugin_benchmark.rs`, these tests likely assess the speed of lookup operations involving vector columns, which is a key feature for actuarial projections.

The benchmarks use the `criterion` crate to provide detailed performance statistics.
