## Project Architecture

This project follows a modular architecture with clear separation of concerns:

### 1. Core Rust Library (`gaspatchio-core/core`)
- Contains all core functionality, data structures, and algorithms
- No PyO3 dependencies or references
- Benchmarkable and testable in pure Rust
- Includes all lookup registry logic, HashMap building, and plugin expressions
- Integration and unit tests for all functionality
- Built using cargo (`cargo build`)
- Test using cargo (`cargo test`)

```
gaspatchio-core/core/
├── src/
│   ├── registry/           # TableRegistry implementation
│   ├── plugin/             # Polars plugin expressions
│   ├── transform/          # Data transformation utilities
│   └── index/              # Lookup index and HashMap builders
├── benches/                # Performance benchmarks
├── tests/                  # Integration tests
└── Cargo.toml              # Core dependencies only
```

### 2. PyO3 Bindings in Rust (`gaspatchio-core/bindings/python`)
- Thin layer that exposes core functionality to Python
- Handles conversion between Python and Rust types
- Only place where PyO3 dependencies should exist
- No business logic, only binding code
- Built using Matruin (`matruin build -uv`)

```
gaspatchio-core/bindings/python/
├── src/
│   ├── lib.rs              # PyO3 module definition
│   ├── registry.rs         # Python bindings for TableRegistry
│   └── plugin.rs           # Export plugin functions to Python
└── Cargo.toml              # PyO3 and core dependencies
```

### 3. Python Interface (`gaspatchio-core/bindings/python/gaspatchio_core`)
- Pure Python code for user-friendly interface
- Polars plugin registration
- Type conversions and convenience functions
- Documentation and examples
- Test using pytest (`uv run pytest -v`)

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
