# Gaspatchio Architecture: Key Decisions for Technical Actuaries

## Executive Summary

Gaspatchio is a high-performance actuarial modeling framework that combines Python's ease of use with Rust's computational efficiency. This document explains the major architectural decisions that shape how actuaries interact with the system, focusing on both the technical implementation and the actuarial motivations behind each choice.

## 1. Python-Native DSL with Dual Execution Modes

### Problem Solved
Traditional DSLs often sacrifice debuggability for performance. Actuaries need to step through calculations, inspect intermediate values, and use familiar Python debugging tools while developing models, but also require production-grade performance for running large portfolios.

### Solution: Dual Mode Execution
Gaspatchio provides two execution modes:
- **Debug Mode**: Execute operations step-by-step in Python, supporting breakpoints, print statements, and IDE debuggers
- **Optimize Mode**: Batch operations into optimized Polars/Rust execution plans with Numba JIT compilation

### Why This Matters for Actuaries
- During model development, you can use `pdb.set_trace()` or IDE breakpoints to inspect calculations
- You can add print statements to verify intermediate results (e.g., checking mortality rates)
- Production runs achieve near-native performance without code changes
- The same model code works in both modes, ensuring consistency

```python
# Same code, different performance characteristics
af = ActuarialFrame(data, mode="debug")  # For development
af = ActuarialFrame(data, mode="optimize")  # For production
```

## 2. ActuarialFrame: The Core Abstraction

### Problem Solved
Actuarial models involve complex vector calculations over time periods (e.g., projecting cash flows for 480 months). Traditional DataFrame operations don't naturally express these patterns, leading to verbose, error-prone code.

### Solution: ActuarialFrame with Operation Tracing
ActuarialFrame wraps Polars DataFrames while:
- Capturing operations in a computation graph for optimization
- Supporting vectorized operations naturally (e.g., `af["mortality_rate"]` can be a vector)
- Providing domain-specific extensions through accessor patterns

### Why This Matters for Actuaries
- Write natural expressions like `af["pv"] = af["cashflow"] * af["discount_factor"]`
- Automatic handling of vector projections without explicit loops
- Lazy evaluation allows the system to optimize entire calculation chains
- Integration with assumption tables through the registry system

## 3. Library Isolation: Core Logic vs Python Bindings

### Problem Solved
Mixing business logic with language bindings creates testing challenges, limits reusability, and complicates maintenance. Actuarial calculations should be testable independently of Python integration.

### Solution: Separated Crate Architecture
- **Core Library (Rust)**: Pure actuarial logic, algorithms, and data structures
- **Python Bindings**: Thin PyO3 wrapper exposing core functionality to Python

### Why This Matters for Actuaries
- Core calculations are rigorously tested in Rust with comprehensive benchmarks
- The same logic could be exposed to R, Excel, or other platforms in the future
- Performance-critical calculations run at native speed
- Clear separation between actuarial logic and interface code

## 4. High-Performance Assumption Lookups

### Problem Solved
Actuarial models frequently look up rates from tables (mortality, lapse, premium rates) based on multiple keys. Traditional join-based approaches explode DataFrames and create performance bottlenecks, especially with vector projections.

### Solution: HashMap-Based Registry with Plugin Functions
- Pre-indexed HashMap lookups with O(1) performance
- Support for both scalar and vector lookups without DataFrame explosion
- Wide-to-long transformations built into the registration process
- Global registry accessible throughout model calculations

### Why This Matters for Actuaries
- Looking up mortality rates for 480 monthly projections is as fast as a single lookup
- No need to manually reshape assumption tables
- Consistent interface whether looking up one value or thousands
- Assumption tables are validated and indexed once at startup

```python
# Register mortality table (wide format automatically transformed)
register_table("mortality_rates", df, 
              keys=["age_last", "gender_smoking"], 
              value_column="rate")

# Lookup returns vector of rates for all projection months
af["mortality_rate"] = assumption_lookup(
    af["age_last"],  # Vector: [31, 32, 33, ...]
    af["gender_smoking"],  # Scalar: "MNS"
    table_name="mortality_rates"
)
```

## 5. Polars Integration with Vector-Aware Operations

### Problem Solved
Actuarial calculations often involve operations on vectors (e.g., arrays of values over time). Standard DataFrame operations may not handle these naturally, and manually writing vector operations is error-prone.

### Solution: Automatic Delegation with Vector Shimming
- Proxy objects that delegate to Polars expressions
- Automatic detection and handling of list/vector columns
- Seamless integration with Polars' native operations
- Special handling for unary numeric operations on vectors

### Why This Matters for Actuaries
- Operations like `floor()`, `abs()`, `exp()` work on both scalars and vectors
- Natural syntax: `af["ages"].floor()` works whether ages is a single value or array
- Access to full Polars ecosystem while maintaining actuarial conveniences
- No need to manually handle list operations

## 6. Namespaced Accessors for Domain Logic

### Problem Solved
Actuarial models need domain-specific operations (date calculations, financial functions, mortality adjustments) that aren't part of standard DataFrame libraries. These should be discoverable and well-organized.

### Solution: Accessor Pattern with Static Types
- Organized namespaces: `af.date`, `af.finance`, `af.mortality`
- Column-level and frame-level operations
- Full IDE support through property definitions and type stubs
- Extensible through decorators and entry points

### Why This Matters for Actuaries
- Domain operations are logically organized and discoverable
- IDE autocompletion helps find relevant functions
- Clear distinction between column operations and full-frame operations
- Third-party packages can add specialized accessors

```python
# Date operations
af["valuation_date"] = af["issue_date"].date.add_months(af["duration"])

# Financial operations
af["pv"] = af["cashflow"].finance.discount(rate=0.05, periods=af["t"])
```

## 7. Concrete Proxies for Better Developer Experience

### Problem Solved
Dynamic proxies break IDE intellisense and type checking, making it difficult to discover available operations and catch errors early. This is especially problematic for complex actuarial calculations.

### Solution: Static Proxy Classes with Type Stubs
- Concrete implementations for each namespace (DtProxy, StrProxy, etc.)
- Comprehensive .pyi stub files with embedded documentation
- Doctest examples directly in type stubs

### Why This Matters for Actuaries
- Full IDE support when writing model code
- Type errors caught before runtime
- Embedded examples show actuarial-specific usage patterns
- Documentation stays synchronized with implementation

## 8. Contextual Error Handling

### Problem Solved
Polars' error messages can be cryptic and lack context about which model calculation failed. Debugging complex actuarial models requires understanding exactly where and why calculations fail.

### Solution: Smart Error Context with Binary Search
- Capture source location for each operation
- Binary search to find exact failing operation efficiently
- Contextual error messages with suggestions
- LLM-friendly structured output for automated fixes

### Why This Matters for Actuaries
- Errors show the exact line in your model that failed
- Suggestions help fix common issues (typos, type mismatches)
- See the last successful state before failure
- AI assistants can automatically fix many errors

```
❌ Calculation error in model.py:27
af["premium_total"] = af["premiun"] * 12

Polars raised → ColumnNotFoundError: column 'premiun' does not exist

💡 Suggestions:
  • Did you mean 'premium'? (similar column found)
```

## Performance Impact

These architectural decisions work together to deliver:
- **Development Speed**: Natural Python syntax with full debugging support
- **Execution Speed**: Near-native performance through Rust and vectorization
- **Scalability**: Handle millions of policies with consistent performance
- **Reliability**: Type safety and comprehensive error handling

## Conclusion

Gaspatchio's architecture reflects a deep understanding of actuarial workflows. Each decision balances developer experience with computational efficiency, creating a system that's both powerful and pleasant to use. The framework doesn't just speed up calculations—it fundamentally improves how actuaries build, test, and maintain their models.