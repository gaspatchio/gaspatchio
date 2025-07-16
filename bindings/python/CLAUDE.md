# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Python Bindings Development Commands

- How to build and install the Python bindings
  ```bash
  # Build Rust extensions with maturin (required after Rust changes)
  maturin build -uv

  # Install all workspace dependencies
  uv sync
  ```

### Testing
```bash
# Run all Python tests
uv run pytest

# Run tests with docstring validation (important for API docs)
uv run pytest --doctest-modules --doctest-glob="*.pyi"

# Run specific test categories
uv run pytest -m "not benchmark"  # Skip slow benchmarks
uv run pytest -m performance      # Only performance tests

# Type checking (both tools should pass)
uv run mypy gaspatchio_core
uv run pyright gaspatchio_core

# Validate type stubs match implementation
uv run python -m mypy.stubtest gaspatchio_core

# Update docstring test expectations
uv run pytest gaspatchio_core/accessors/excel.py --doctest-modules --accept
```

### Model Execution
```bash
# Run actuarial model
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true gspio run-model model.py data.parquet

# Debug single policy
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true gspio run-single-policy model.py data.parquet "PolicyID" --policy-id-column "Policy number"

# Run single policy
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true uv run gspio run-single-policy ../../../gaspatchio-models/models/my-model/model_calculation.py ../../../gaspatchio-models/models/my-model/model-points.parquet 1 --policy-id-column "Policy number"

# Run model
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true uv run gspio run-model ../../../gaspatchio-models/models/my-model/model_calculation.py ../../../gaspatchio-models/models/my-model/model-points.parquet

# Run with debug mode (more output rows)
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true gspio run-model model.py data.parquet --mode debug -r 50

# Output to file
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true gspio run-model model.py data.parquet --output-file results.parquet
```

## High-Level Architecture

### Python Package Structure
The Python bindings wrap the Rust core library via PyO3:

- **gaspatchio_core._internal**: PyO3 module built from Rust (see _internal.pyi for API)
- **ActuarialFrame**: Main DataFrame-like structure for actuarial calculations
  - Wraps Polars DataFrames with actuarial-specific operations
  - Supports method chaining via proxy pattern
  - Lazy evaluation for performance
  
- **Proxy Pattern**: ColumnProxy/ExpressionProxy enable fluent API
  - `af["column"].excel.pv(...)` - Excel functions via accessor
  - `af["column"].dt.year_frac(...)` - Date functions via accessor
  - Chain operations before execution for optimization

- **Assumption Tables**: Table/TableBuilder for rate lookups
  - Multiple join strategies (age/duration, select/ultimate)
  - Efficient batch lookups via Polars joins

### Critical Implementation Details

1. **Docstring Examples Are Tests**: Examples in docstrings are validated by pytest. When modifying examples, run with `--accept` to update expected outputs.

2. **Type Stubs Required**: The `_internal.pyi` file must match Rust exports exactly. Use `mypy.stubtest` to verify.

3. **Performance Warnings**: The codebase emits warnings for suboptimal patterns (e.g., iterating over policies). Always use vectorized operations.

4. **Error Formatting**: Custom error formatter (`errors/formatter.py`) provides clear error messages with context. Preserve error handling patterns.

5. **Telemetry Integration**: Logfire telemetry is configured but optional. Set `LOGFIRE_TOKEN` to enable.

### Testing Philosophy

- **Docstring-Driven**: Public API examples in docstrings serve as tests
- **Type Safety**: Both mypy and pyright must pass in strict mode
- **Performance**: Benchmarks track regression (see `tests/test_performance.py`)
- **Integration**: Example models in `tests/examples/` validate end-to-end functionality

### Development Workflow

1. For new Excel functions: Add to `accessors/excel.py` with docstring examples
2. For new vector operations: Add to `functions/vector.py` 
3. Always run type checkers and tests before committing
4. Use `gspio` CLI to validate changes with real models
5. Check parent `CLAUDE.md` for broader project guidelines



@.claude/docs/python-general.md
@.claude/docs/typing.md
@.claude/docs/style.md
@.claude/docs/uv.md