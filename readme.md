## Project Architecture

This project follows a modular architecture with clear separation of concerns:

### 1. Core Rust Library (`gaspatchio-core/core`)
- Contains all core functionality, data structures, and algorithms
- No PyO3 dependencies or references
- Benchmarkable and testable in pure Rust
- Includes all lookup registry logic, HashMap building, and plugin expressions
- Integration and unit tests for all functionality
- Move to the `core` directory to run the core library (`cd core`)
- For more details, see the [Core README](core/README.md).

```
gaspatchio-core/core/
├── benches/
│   └── fixtures/           # Benchmark data fixtures
└── src/
    └── polars_functions/   # Core Polars function implementations
├── tests/                  # Integration tests (Note: Need to confirm if this still exists or moved)
└── Cargo.toml              # Core dependencies only
```

### 2. PyO3 Bindings in Rust (`gaspatchio-core/bindings/python`)
- Thin layer that exposes core functionality to Python
- Handles conversion between Python and Rust types
- Only place where PyO3 dependencies should exist
- No business logic, only binding code
- Built using Matruin (`matruin build -uv`)
- For more details, see the [Python Bindings README](bindings/python/README.md).

```
gaspatchio-core/bindings/python/
├── src/                    # PyO3 module definition and binding code
├── jobs/                   # Example job scripts (if applicable)
├── scripts/                # Utility scripts
├── tests/                  # Python binding tests
└── Cargo.toml              # PyO3 and core dependencies
```

### 3. Python Interface (`gaspatchio-core/bindings/python/gaspatchio_core`)
- Pure Python code for user-friendly interface
- Polars plugin registration
- Type conversions and convenience functions
- Documentation and examples
- Test using pytest (`uv run pytest -v`)
- For more details, see the [Python Bindings README](bindings/python/README.md) (as `gaspatchio_core` is part of the `bindings/python` module).

```
gaspatchio-core/bindings/python/gaspatchio_core/
├── __init__.py             # Package exports
├── functions.py            # Plugin function wrappers (if still used)
├── registry.py             # TableRegistry Python interface (if still used)
└── typing.py               # Type definitions (if still used)
```

### Motivation for This Architecture

This separation provides several benefits:
1. **Core Library Purity**: The core Rust implementation remains focused and PyO3-free, making it easier to test, benchmark, and maintain.
2. **Multiple Bindings**: Future bindings to other languages (R, JavaScript, etc.) can be added without modifying the core library.
3. **Testing Efficiency**: Core functionality can be tested in Rust without Python dependencies, allowing for faster test cycles.
4. **Performance Optimization**: Benchmarking can be done directly on the core library, ensuring optimal performance.
5. **Maintainability**: Changes to the Python interface don't require recompiling the Rust code, and vice versa.

### Project Documentation

For comprehensive documentation, including guides, concepts, and API references, please visit the official Gaspatchio documentation site:
- [Gaspatchio Documentation](https://opioinc.github.io/gaspatchio-docs/)

### For AI, LLMs, and Automated Tooling

Gaspatchio is designed with AI-assisted development in mind. We provide specific resources to help language models and automated tools understand and interact with the project:

- **`llms.txt`**: [https://opioinc.github.io/gaspatchio-docs/llms.txt](https://opioinc.github.io/gaspatchio-docs/llms.txt)
  - Provides concise, LLM-friendly context, guidance, and links to key documentation sections. This follows the emerging `llms.txt` convention (llmstxt.org), designed to give LLMs essential, structured information about a project or website efficiently.
- **`llms-full.txt`**: [https://opioinc.github.io/gaspatchio-docs/llms-full.txt](https://opioinc.github.io/gaspatchio-docs/llms-full.txt)
  - An expanded version, potentially including content from linked resources mentioned in `llms.txt`. This offers a more comprehensive context suitable for deeper analysis or more complex query answering.

This approach, inspired by the AI-first design of Gaspatchio (see [Building Actuarial Models with AI](https://opioinc.github.io/gaspatchio-docs/ai/intro/)), helps ensure that AI tools can effectively assist in the development, analysis, and understanding of models built with this framework.
