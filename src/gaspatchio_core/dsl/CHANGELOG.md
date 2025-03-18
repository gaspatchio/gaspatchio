# Core DSL Changelog

## [0.2.0] - 2025-03-18

### Changed
- Renamed module from "debuggable" to "core" to better reflect its role as the primary DSL
- Removed the old DSL implementation
- Updated all imports and references to use the new module name

## [0.1.0] - 2025-03-13

### Added
- Initial implementation of the core DSL with dual-mode operation (debug and optimize)
- Support for basic arithmetic operations
- Support for column access and assignment
- Support for function application
- Support for NumPy functions
- Support for plugin functions
- Tracing functionality for debugging
- Comprehensive test suite
- Performance benchmarks

### Features
- ActuarialFrame class that wraps Polars DataFrame with core functionality
- ColumnProxy and ExpressionProxy classes for column and expression manipulation
- run_model function for executing models
- set_default_mode function for setting the default execution mode
- trace method for debugging complex models

### Performance
- Simple model: 34.72x speedup in optimize mode
- Complex model: 1.73x speedup in optimize mode

### Known Issues
- Function applications in optimize mode may fall back to Python execution
- Numba optimization is not fully implemented
- Some operations may behave slightly differently between debug and optimize modes
- Deprecation warning from Polars regarding the old streaming engine 