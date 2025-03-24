# Execution Plan: Separating Core Rust Logic from Python Bindings

## Overview

This document outlines the step-by-step process for refactoring the Gaspatchio project to separate core Rust logic from Python bindings. The plan is broken down into phases, with each phase containing specific tasks and corresponding LLM prompts for implementation.

## Phase 1: Project Structure Setup

### Step 1.1: Create Workspace Structure
- Create new workspace layout
- Set up initial Cargo.toml files
- Configure build settings

**LLM Prompt 1.1:**
```text
Create a new Rust workspace for Gaspatchio with the following structure:
- gaspatchio/
  |- Cargo.toml (workspace)
  |- gaspatchio-core/
     |- Cargo.toml
     |- src/lib.rs
  |- gaspatchio-py/
     |- Cargo.toml
     |- src/lib.rs
     |- pyproject.toml

Requirements:
1. Workspace Cargo.toml should define both crates as members
2. gaspatchio-core should be a pure Rust library (rlib)
3. gaspatchio-py should be a cdylib with PyO3 dependencies
4. Set up basic module structure in both lib.rs files
5. Configure pyproject.toml for maturin

Ensure all configuration files are properly set up for development and testing.
```

### Step 1.2: Migration Planning
- Analyze current codebase
- Identify core functionality
- Map dependencies

**LLM Prompt 1.2:**
```text
Analyze the current Gaspatchio codebase and create:
1. A list of core Rust functions and types that need to be migrated
2. A dependency graph showing relationships between components
3. A mapping of current Python bindings to their core Rust implementations
4. Identification of any shared types or interfaces

Output should be in a structured format that can be used for the migration process.
```

## Phase 2: Core Library Implementation

### Step 2.1: Core Data Structures
- Implement fundamental types
- Set up error handling
- Add basic traits

**LLM Prompt 2.1:**
```text
Implement the core data structures for gaspatchio-core:
1. Create basic types for mortality tables, rates, and calculations
2. Implement custom error types using thiserror
3. Add basic traits for data manipulation
4. Write unit tests for all implementations

Requirements:
- Use Rust 2021 edition
- Follow Rust naming conventions
- Implement Debug, Clone where appropriate
- Add comprehensive documentation
- Include test coverage for edge cases
```

### Step 2.2: Core Business Logic
- Implement calculation functions
- Add validation logic
- Set up testing framework

**LLM Prompt 2.2:**
```text
Implement the core business logic for mortality calculations:
1. Port existing calculation functions from the current codebase
2. Add input validation and error handling
3. Implement test helpers and fixtures
4. Create comprehensive test suite

Requirements:
- Use strong typing
- Handle all error cases
- Add benchmarks for critical paths
- Document all public APIs
- Include property-based tests where appropriate
```

## Phase 3: Python Bindings

### Step 3.1: Basic Type Conversions
- Implement PyO3 type conversions
- Set up error mapping
- Add basic Python tests

**LLM Prompt 3.1:**
```text
Create Python bindings for core data types:
1. Implement From/Into traits for Python conversions
2. Add error mapping between Rust and Python
3. Create Python-friendly constructors
4. Write Python-side unit tests

Requirements:
- Handle all Python exceptions properly
- Implement __repr__ and __str__
- Add type hints for Python
- Include docstrings
- Create pytest fixtures
```

### Step 3.2: Function Bindings
- Wrap core functions
- Add Python-specific features
- Implement convenience methods

**LLM Prompt 3.2:**
```text
Create Python bindings for core functions:
1. Wrap all calculation functions
2. Add Python-specific convenience methods
3. Implement any needed async support
4. Create comprehensive Python tests

Requirements:
- Handle GIL properly
- Add proper type annotations
- Include performance tests
- Document all Python APIs
- Add examples in docstrings
```

## Phase 4: Integration and Testing

### Step 4.1: Integration Tests
- Create end-to-end tests
- Add performance benchmarks
- Implement stress tests

**LLM Prompt 4.1:**
```text
Create integration tests for the complete system:
1. Write end-to-end tests covering main use cases
2. Add performance benchmarks comparing old vs new
3. Create stress tests for edge cases
4. Implement memory leak tests

Requirements:
- Test both Rust and Python interfaces
- Include concurrent testing
- Add load testing
- Document test coverage
- Create test documentation
```

### Step 4.2: Documentation and Examples
- Write comprehensive docs
- Create example code
- Add usage guides

**LLM Prompt 4.2:**
```text
Create comprehensive documentation:
1. Write API documentation for both Rust and Python
2. Create example programs showing common use cases
3. Add installation and setup guides
4. Include performance tips and best practices

Requirements:
- Include runnable examples
- Add API reference
- Create troubleshooting guide
- Document all configuration options
- Add migration guide from old version
```

## Phase 5: Deployment and Release

### Step 5.1: Build and Package
- Set up CI/CD
- Configure packaging
- Prepare release process

**LLM Prompt 5.1:**
```text
Set up build and deployment:
1. Configure GitHub Actions for CI/CD
2. Set up crates.io and PyPI packaging
3. Create release scripts
4. Add version management

Requirements:
- Automate all builds
- Include all necessary files
- Set up proper versioning
- Configure cross-platform builds
- Add release documentation
```

### Step 5.2: Migration Support
- Create migration tools
- Add compatibility layer
- Write migration docs

**LLM Prompt 5.2:**
```text
Create migration support:
1. Implement compatibility layer for old API
2. Create migration scripts
3. Add deprecation warnings
4. Write migration documentation

Requirements:
- Handle all edge cases
- Provide clear upgrade path
- Include rollback procedures
- Document breaking changes
- Add version compatibility matrix
```

## Review Checklist

Before each phase:
- [ ] Review previous phase's output
- [ ] Update test coverage metrics
- [ ] Check performance benchmarks
- [ ] Update documentation
- [ ] Review error handling
- [ ] Check API consistency

After each phase:
- [ ] Run full test suite
- [ ] Check documentation coverage
- [ ] Review code quality metrics
- [ ] Update changelog
- [ ] Tag release if applicable

## Notes

- Each phase should be completed and tested before moving to the next
- All code changes should be reviewed and approved
- Documentation should be updated in parallel with code changes
- Performance benchmarks should be run before and after each phase
- Regular backups of the codebase should be maintained
