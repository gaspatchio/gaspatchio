# Calculation Graph MVP Todo List

## Part 1: Variable Mapping & IDE Support (Implement First)

### Phase 1.1: Automatic Mapping Generation
- [ ] Create `gaspatchio_core/codegen/__init__.py` module
- [ ] Create `gaspatchio_core/codegen/mapping.py` module
- [ ] Add dependency for identifier generation:
  - [ ] Option 1: `inflection` - Convert between naming conventions
  - [ ] Option 2: `python-slugify` - Convert strings to valid identifiers
  - [ ] Option 3: `identifier-generator` - Purpose-built for Python identifiers
- [ ] Implement `generate_mapping_from_model_points()` function
  - [ ] Read parquet schema to get column names
  - [ ] Use library to convert to valid Python identifiers
  - [ ] Handle Python keywords with suffix
  - [ ] Handle duplicate names with counter
  - [ ] Ensure all names are valid with `.isidentifier()`
- [ ] Create mapping cache to avoid regenerating
- [ ] Write unit tests for edge cases (keywords, special chars, duplicates)

### Phase 1.2: Code Generation for IDE Support
- [ ] Create `gaspatchio_core/codegen/generator.py` module
- [ ] Implement `generate_ide_support_files()` function:
  - [ ] Generate `model_variables.py` with type annotations
  - [ ] Generate `model_variables.pyi` stub file
  - [ ] Include docstrings with column mappings
  - [ ] Use `TYPE_CHECKING` for import optimization
- [ ] Create CLI command `generate-variables`:
  - [ ] Add to `gaspatchio_core.cli`
  - [ ] Read model points file
  - [ ] Generate mapping
  - [ ] Write .py and .pyi files to specified directory
  - [ ] Option to watch for changes and regenerate

### Phase 1.3: Runtime Variable Injection
- [ ] Create `gaspatchio_core/codegen/runtime.py` module
- [ ] Implement `generate_variable_module()` for runtime use:
  - [ ] Generate module with `__all__` for import *
  - [ ] Create getter/setter functions for each variable
  - [ ] Handle module-level variable access
  - [ ] Connect to ActuarialFrame instance
- [ ] Implement `inject_variables()` function:
  - [ ] Create temporary module in sys.modules
  - [ ] Initialize with ActuarialFrame instance
  - [ ] Handle cleanup after execution

### Phase 1.4: Runner Integration
- [ ] Modify `runner.py` to support variable generation:
  - [ ] Add `--enable-variables` flag to run-model command
  - [ ] Add `--enable-variables` flag to run-single-policy command
  - [ ] Generate mapping from model points on first load
  - [ ] Create wrapper function for model execution
  - [ ] Inject variables into model's namespace
- [ ] Update `ModelRunConfig` to include variable mapping settings
- [ ] Ensure backward compatibility when flag is not used

### Phase 1.5: Testing Part 1
- [ ] Test mapping generation with My Model model points
- [ ] Test IDE support file generation
- [ ] Create integration test with My Model model:
  - [ ] Copy `model_calculation_vars.py` to `model_calculation_natural.py`
  - [ ] Replace key variable assignments with natural syntax:
    ```python
    # Old: af["issue_age"] = af["Policyholder issue age"] + af["term_offset"]
    # New: issue_age = policyholder_issue_age + term_offset
    
    # Old: af["age"] = af["issue_age"] + af["year"] - 1
    # New: age = issue_age + year - 1
    
    # Old: af["mortality_rates"] = 1 - (1 - af["monthly_CSO_table"]) ** (1 / 12)
    # New: mortality_rates = 1 - (1 - monthly_cso_table) ** (1 / 12)
    ```
  - [ ] Run the test command:
    ```bash
    cd gaspatchio-models/models
    LOGURU_LEVEL=TRACE uv run gspio run-single-policy \
      my-model/model_calculation_natural.py \
      my-model/model-points.parquet 1 \
      --policy-id-column "Policy number" -f 8 -l 1 \
      --enable-variables
    ```
  - [ ] Verify output matches original model
  - [ ] Check that tracing shows natural variable names
- [ ] Verify IDE autocomplete works in the natural model
- [ ] Test performance impact vs original

## Part 2: Calculation Graph (After Part 1 is Complete)

### Phase 2.1: Dependency Extraction
- [ ] Create `gaspatchio_core/frame/dependencies.py` module
- [ ] Implement `extract_dependencies(expr: pl.Expr) -> list[str]` function
  - [ ] Handle basic column references (`col("name")`)
  - [ ] Handle nested expressions (arithmetic, comparisons)
  - [ ] Handle struct field access (`col("name").struct.field("field")`)
  - [ ] Handle list operations (`col("name").list.get(0)`)
  - [ ] Handle Excel functions (e.g., `col("name").excel.from_excel_serial()`)
  - [ ] Handle assumption lookups (`lookup_by_table_and_hash`)
  - [ ] **Use mapped variable names in dependencies**
- [ ] Write unit tests for dependency extraction

### Phase 2.2: Enhanced Tracing
- [ ] Modify `TracedOperation` dataclass to include `dependencies: list[str]`
- [ ] Update `append_operation_to_graph()` to:
  - [ ] Call dependency extractor
  - [ ] Store mapped variable names
  - [ ] Track both original and mapped names
- [ ] Ensure backward compatibility with existing code
- [ ] Update tracing output to show natural variable names

### Phase 2.3: Graph Data Structures
- [ ] Create `gaspatchio_core/frame/calc_graph.py` module
- [ ] Implement `GraphNode` dataclass:
  ```python
  @dataclass
  class GraphNode:
      id: str  # Mapped variable name
      type: Literal["input", "computed"]
      label: str
      data: dict  # dtype, source, dependencies, formula, etc.
  ```
- [ ] Implement `GraphEdge` dataclass
- [ ] Implement `CalculationGraph` class with methods:
  - [ ] `add_input_column(name, dtype, source)`
  - [ ] `add_computed_column(operation: TracedOperation)`
  - [ ] `to_json() -> dict`

### Phase 2.4: Graph Construction
- [ ] Hook into `ActuarialFrame` to build graph during execution
- [ ] Identify input columns vs computed columns
- [ ] Create edges based on dependencies
- [ ] Handle columns that appear in both input and computed (overrides)
- [ ] Use mapped variable names throughout

### Phase 2.5: JSON Export
- [ ] Implement JSON serialization matching specified format
- [ ] Include sample values (from first row or single policy run)
- [ ] Add source location information
- [ ] Handle special types (dates, lists) in serialization
- [ ] Ensure all names in JSON use mapped variables

### Phase 2.6: CLI Integration
- [ ] Add `calc-graph` command to `gaspatchio_core.cli`
- [ ] Command arguments:
  - [ ] `model_path`: Path to model Python file
  - [ ] `model_points`: Path to model points data
  - [ ] `--output`: Output JSON file path
  - [ ] `--enable-variables`: Use variable mapping (default: True)
  - [ ] `--policy-id`: Optional single policy for sample values
  - [ ] `--pretty`: Pretty print JSON output
- [ ] Integration with existing commands:
  - [ ] Add `--export-graph` flag to `run-model` command
  - [ ] Add `--export-graph` flag to `run-single-policy` command

### Phase 2.7: Testing Part 2
- [ ] Test dependency extraction with mapped variables
- [ ] Test graph construction with My Model model
- [ ] Test JSON output format matches specification
- [ ] Test that graph shows natural variable names:
  ```json
  {
    "nodes": [
      { "id": "policyholder_issue_age", "type": "input", ... },
      { "id": "issue_age", "type": "computed", 
        "data": { 
          "formula": "policyholder_issue_age + term_offset",
          "dependencies": ["policyholder_issue_age", "term_offset"]
        }
      }
    ]
  }
  ```
- [ ] Test edge cases and complex expressions

## Phase 3: Documentation & Polish

### 3.1: Documentation
- [ ] Document variable mapping feature
- [ ] Document calculation graph feature
- [ ] Create example showing full workflow
- [ ] Document JSON output format
- [ ] Add to main Gaspatchio docs

### 3.2: Examples
- [ ] Create example model using natural variables
- [ ] Create example of graph visualization
- [ ] Show how to integrate with existing models

### 3.3: Performance & Edge Cases
- [ ] Benchmark performance impact
- [ ] Handle models with 1000+ variables
- [ ] Test with complex expressions
- [ ] Handle circular dependencies gracefully

## Success Checklist

- [ ] My Model model runs with natural variable syntax
- [ ] IDE provides autocomplete for all variables
- [ ] Generated graph JSON uses natural variable names
- [ ] No performance regression in normal mode
- [ ] All existing tests still pass
- [ ] Documentation is complete

## Future Enhancements (Post-MVP)

- [ ] VS Code extension for Gaspatchio
- [ ] Interactive graph visualization web app
- [ ] Automatic variable name inference from expressions
- [ ] Execution order optimization based on graph
- [ ] Incremental computation based on changed inputs
- [ ] Integration with debugging tools