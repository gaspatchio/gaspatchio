# Calculation Graph MVP - Todo List

## Step 1: Dependency Extraction
- [ ] Create `gaspatchio_core/frame/expr_analyzer.py` module
- [ ] Implement `extract_dependencies` function for Polars expressions
- [ ] Handle simple column references (`pl.col("x")`)
- [ ] Handle binary operations (`pl.col("x") + pl.col("y")`)
- [ ] Handle method chains (`pl.col("x").clip(0, 100)`)
- [ ] Handle conditional expressions (`pl.when().then().otherwise()`)
- [ ] Handle struct field access (`pl.col("data").struct.field("value")`)
- [ ] Handle list operations (`pl.col("list").list.get(0)`)
- [ ] Add comprehensive unit tests for dependency extraction

## Step 2: Graph Building
- [ ] Create `gaspatchio_core/frame/calc_graph.py` module
- [ ] Implement `GraphNode` dataclass
- [ ] Implement `GraphEdge` dataclass
- [ ] Implement `CalculationGraph` class
- [ ] Add `add_input_column` method
- [ ] Add `add_computed_operation` method
- [ ] Add `to_json` export method
- [ ] Handle automatic input column inference
- [ ] Add unit tests for graph building

## Step 3: Integration with Existing Tracing
- [ ] Update `TracedOperation` dataclass to include dependencies field
- [ ] Modify `append_operation_to_graph` to extract dependencies
- [ ] Create `gaspatchio_core/frame/graph_export.py` module
- [ ] Implement `export_calculation_graph` function
- [ ] Handle model points schema for input columns
- [ ] Test integration with existing debug mode

## Step 4: CLI and Testing
- [ ] Add `calc-graph` command to `gaspatchio_mix/cli.py`
- [ ] Support single policy mode for debugging
- [ ] Add output file parameter
- [ ] Create integration tests with sample models
- [ ] Test with the example model
- [ ] Verify JSON output format matches specification
- [ ] Add error handling for non-debug mode
- [ ] Document usage in CLI help text

## Step 5: Documentation and Examples
- [ ] Add docstrings to all new functions
- [ ] Create example usage in documentation
- [ ] Add section to main documentation about calculation graphs
- [ ] Create visualization example using the JSON output

## Verification Checklist
- [ ] All Polars expression types are handled
- [ ] Dependencies are correctly identified
- [ ] Graph has no missing nodes or edges
- [ ] JSON format matches specification exactly
- [ ] Performance overhead in debug mode is acceptable
- [ ] Error messages are clear and helpful