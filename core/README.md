# Gaspatchio Core (Rust engine)

The high-performance Rust engine behind [Gaspatchio](../README.md). It is the computational
backbone of the Python package: a concurrent assumption-table registry, vectorized lookups, and
Polars-based DataFrame operations for actuarial projections.

> Most users want the **[Python package](../bindings/python/README.md)**, not this crate directly.

## What it does

- **Polars-based operations** — fast, memory-efficient DataFrame computation via [Polars](https://pola.rs/).
- **In-memory table registry** — a concurrent `TableRegistry` (`ArcSwap`, near lock-free reads)
  holding assumption tables (mortality, lapse, …) as Polars DataFrames for high-speed lookups.
- **Vectorized lookups** — look up rates for an entire projection array in a single operation, the
  key primitive for time-based projections (`src/polars_functions/vector.rs`).
- **Dynamic table transforms** — wide-to-long reshaping and overflow strategies applied before
  registration.
- **Plugin architecture** — custom Polars expression plugins extend the engine (see
  `polars_functions/`).

The core data structures (`AssumptionTable`, the registry, table builders, scalar + vector
lookups) live in `src/assumptions/`.

## Build, test, benchmark

```bash
cargo build        # build the library
cargo test         # unit + integration tests
cargo clippy       # lint
cargo fmt          # format
cargo bench        # Criterion benchmarks
```

### Benchmarks

Criterion benchmarks track performance across releases:

- **`realistic_vector_lookup`** — mirrors the real model code path (list-column keys, 10K policies
  × 120 months). **This is the authoritative lookup-performance benchmark.**
- **`assumption_table_lookup_benchmark`** — scalar-path lookups (hash vs array storage).
- **`vector_plugin_benchmark`** — vector/list operations (e.g. `fill_series`).

```bash
cargo bench --bench realistic_vector_lookup
```

## Contributing

Rust coding standards, the Polars-plugin guidelines, and the streaming-engine rules are in
[`AGENTS.md`](AGENTS.md). See the [project overview](../README.md) for the full picture.
