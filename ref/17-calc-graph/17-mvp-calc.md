# Calculation Graph MVP - Part 2 Only

## Overview

Build a dependency graph of calculations by enhancing Gaspatchio's existing tracing infrastructure. This will enable visualization and debugging of actuarial models by producing a JSON representation of the calculation flow.

## Current State

Gaspatchio already has:
- **Operation Tracing**: Captures operations in `_computation_graph` during debug mode
- **Source Location**: Tracks file and line number for each operation
- **Type Inference**: Attempts to infer result types of expressions
- **Column Order Tracking**: Maintains order of column creation

What's missing:
- **Dependency Extraction**: No analysis of which columns an expression depends on
- **Graph Structure**: Operations stored as a list, not a proper directed graph
- **JSON Export**: No graph output format for visualization

## MVP Goals

1. **Extract Dependencies**: Analyze Polars expressions to identify column dependencies
2. **Build Dependency Graph**: Create a proper DAG structure from operations
3. **JSON Export**: Produce the JSON format for visualization tools

## Target Output Format

```json
{
  "nodes": [
    { "id": "policyholder_issue_age", "type": "input", "label": "policyholder_issue_age", 
      "data": { "dtype": "int", "source": "model_points.csv", "dependencies": [] } },
    { "id": "term_offset", "type": "input", "label": "term_offset", 
      "data": { "dtype": "int", "source": "model_points.csv", "dependencies": [] } },
    { "id": "issue_age", "type": "computed", "label": "issue_age = policyholder_issue_age + term_offset", 
      "data": { 
         "formula": "policyholder_issue_age + term_offset", 
         "dependencies": ["policyholder_issue_age","term_offset"],
         "source_location": "model_calculation.py:5",
         "value_sample": 42  } },
    { "id": "year", "type": "input", "label": "year", 
      "data": { "dtype": "int", "source": "model_points.csv", "dependencies": [] } },
    { "id": "age", "type": "computed", "label": "age = issue_age + year - 1", 
      "data": { 
         "formula": "issue_age + year - 1", 
         "dependencies": ["issue_age","year"],
         "source_location": "model_calculation.py:6",
         "value_sample": 41  } },
    { "id": "premium_double", "type": "computed", "label": "premium_double = age * 2", 
      "data": { 
         "formula": "age * 2", 
         "dependencies": ["age"],
         "source_location": "model_calculation.py:7",
         "value_sample": 82  } }
  ],
  "edges": [
    { "source": "policyholder_issue_age", "target": "issue_age" },
    { "source": "term_offset", "target": "issue_age" },
    { "source": "issue_age", "target": "age" },
    { "source": "year", "target": "age" },
    { "source": "age", "target": "premium_double" }
  ]
}
```

## Technical Approach

### 1. Enhance TracedOperation

Update the existing `TracedOperation` dataclass to include dependencies:

```python
# In gaspatchio_core/frame/traced_operation.py
@dataclass
class TracedOperation:
    alias: str
    expression: pl.Expr
    metadata: SourceContext
    expected_dtype: pl.DataType | None = None
    dependencies: list[str] = field(default_factory=list)  # NEW
```

### 2. Implement Dependency Extraction

Create a new module `gaspatchio_core/frame/expr_analyzer.py`:

```python
import polars as pl
from typing import Set

def extract_dependencies(expr: pl.Expr) -> list[str]:
    """Extract column names referenced in a Polars expression.
    
    This function walks the expression tree to find all column references.
    It handles:
    - Simple column references: pl.col("x")
    - Multiple columns: pl.col("x") + pl.col("y")
    - Nested expressions: pl.col("x").clip(0, 100)
    - Struct field access: pl.col("data").struct.field("value")
    - List operations: pl.col("list").list.get(0)
    """
    dependencies = set()
    
    # Use Polars' meta utilities to extract column names
    # This is a simplified version - actual implementation needs to
    # handle all expression types properly
    meta = expr.meta
    if hasattr(meta, '_column_names'):
        dependencies.update(meta._column_names)
    
    return sorted(list(dependencies))
```

### 3. Create Graph Building Module

Create `gaspatchio_core/frame/calc_graph.py`:

```python
from dataclasses import dataclass, field
from typing import Literal, Dict, List, Any
import json

@dataclass
class GraphNode:
    id: str
    type: Literal["input", "computed"]
    label: str
    data: dict[str, Any]

@dataclass
class GraphEdge:
    source: str
    target: str

class CalculationGraph:
    def __init__(self):
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self.input_columns: set[str] = set()
    
    def add_input_column(self, column_name: str, dtype: pl.DataType, source: str = "model_points"):
        """Add an input column node to the graph."""
        if column_name not in self.nodes:
            self.nodes[column_name] = GraphNode(
                id=column_name,
                type="input",
                label=column_name,
                data={
                    "dtype": str(dtype),
                    "source": source,
                    "dependencies": []
                }
            )
            self.input_columns.add(column_name)
    
    def add_computed_operation(self, operation: TracedOperation):
        """Add a computed node and its edges to the graph."""
        # Create the computed node
        node = GraphNode(
            id=operation.alias,
            type="computed",
            label=f"{operation.alias} = {operation.expression}",
            data={
                "formula": str(operation.expression),
                "dependencies": operation.dependencies,
                "source_location": f"{operation.metadata.filename}:{operation.metadata.line}",
                "value_sample": None  # Could be populated with actual values
            }
        )
        self.nodes[operation.alias] = node
        
        # Create edges from dependencies to this node
        for dep in operation.dependencies:
            # If dependency is not yet in graph, it must be an input
            if dep not in self.nodes and dep not in self.input_columns:
                # Infer it's an input column
                self.add_input_column(dep, pl.Utf8, "inferred")
            
            self.edges.append(GraphEdge(source=dep, target=operation.alias))
    
    def to_json(self) -> str:
        """Export the graph to JSON format."""
        return json.dumps({
            "nodes": [
                {
                    "id": node.id,
                    "type": node.type,
                    "label": node.label,
                    "data": node.data
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target
                }
                for edge in self.edges
            ]
        }, indent=2)
```

### 4. Integrate with Existing Tracing

Modify `append_operation_to_graph` in `gaspatchio_core/frame/operations.py`:

```python
def append_operation_to_graph(
    expression: pl.Expr,
    alias: str,
    actual_dtype: pl.DataType | None = None,
    expected_dtype: pl.DataType | None = None,
) -> None:
    """Append an operation to the computation graph with dependency tracking."""
    frame = inspect.currentframe()
    # ... existing source context extraction ...
    
    # NEW: Extract dependencies
    from .expr_analyzer import extract_dependencies
    dependencies = extract_dependencies(expression)
    
    operation = TracedOperation(
        alias=alias,
        expression=expression,
        metadata=SourceContext(
            line=lineno,
            filename=filename,
            code=source_code,
        ),
        expected_dtype=expected_dtype,
        dependencies=dependencies  # NEW
    )
    
    _computation_graph.append(operation)
```

### 5. Add Graph Export Functionality

Create a new function in `gaspatchio_core/frame/graph_export.py`:

```python
def export_calculation_graph(af: ActuarialFrame) -> str:
    """Export the calculation graph from an ActuarialFrame to JSON.
    
    Args:
        af: ActuarialFrame with computation graph populated (must have run in debug mode)
    
    Returns:
        JSON string representing the calculation graph
    """
    if not hasattr(af, '_computation_graph') or not af._computation_graph:
        raise ValueError("No computation graph found. Run model in debug mode.")
    
    # Build the graph
    graph = CalculationGraph()
    
    # First pass: identify all input columns from model points
    if hasattr(af, '_model_points_schema'):
        for col_name, dtype in af._model_points_schema.items():
            graph.add_input_column(col_name, dtype, "model_points")
    
    # Second pass: add all computed operations
    for operation in af._computation_graph:
        graph.add_computed_operation(operation)
    
    return graph.to_json()
```

### 6. CLI Integration

Add command to `gaspatchio_mix/cli.py`:

```python
@app.command()
def calc_graph(
    model_file: Path,
    model_points_file: Path,
    output_file: Path = Path("calc_graph.json"),
    policy_id: str | None = None,
):
    """Generate a calculation graph from a model run.
    
    Args:
        model_file: Path to the model Python file
        model_points_file: Path to the model points Parquet file
        output_file: Path to save the JSON graph (default: calc_graph.json)
        policy_id: Optional policy ID to run single policy (for debugging)
    """
    # Run model in debug mode to capture graph
    config = ModelRunConfig(
        model_file=model_file,
        model_points_file=model_points_file,
        mode="debug",  # Must be debug to capture graph
        policy_id=policy_id
    )
    
    result = run_model(config)
    
    # Export the graph
    json_graph = export_calculation_graph(result.actuarial_frame)
    
    # Save to file
    output_file.write_text(json_graph)
    
    print(f"Calculation graph saved to {output_file}")
```

## Implementation Steps

### Step 1: Dependency Extraction (Week 1)
- [ ] Implement `extract_dependencies` function
- [ ] Handle all Polars expression types (binary ops, functions, methods)
- [ ] Test with complex expressions from My Model model
- [ ] Add unit tests for edge cases

### Step 2: Graph Building (Week 1-2)
- [ ] Create `CalculationGraph` class
- [ ] Implement node and edge creation
- [ ] Handle input column detection
- [ ] Add JSON export functionality

### Step 3: Integration (Week 2)
- [ ] Update `TracedOperation` dataclass
- [ ] Modify `append_operation_to_graph` to extract dependencies
- [ ] Add `export_calculation_graph` function
- [ ] Test with existing models

### Step 4: CLI and Testing (Week 2-3)
- [ ] Add `calc-graph` command to CLI
- [ ] Create integration tests with sample models
- [ ] Test with My Model model
- [ ] Document usage and examples

## Testing Strategy

### Unit Tests
```python
def test_extract_dependencies():
    # Simple column reference
    expr = pl.col("age")
    assert extract_dependencies(expr) == ["age"]
    
    # Binary operation
    expr = pl.col("age") + pl.col("term")
    assert extract_dependencies(expr) == ["age", "term"]
    
    # Nested expression
    expr = (pl.col("age") + pl.col("term")).clip(0, 100)
    assert extract_dependencies(expr) == ["age", "term"]
    
    # Complex expression
    expr = pl.when(pl.col("age") > 65).then(pl.col("rate_senior")).otherwise(pl.col("rate_normal"))
    assert extract_dependencies(expr) == ["age", "rate_normal", "rate_senior"]
```

### Integration Test
```python
def test_calc_graph_generation():
    # Create simple model
    def model(af):
        af["issue_age"] = af["policyholder_issue_age"] + af["term_offset"]
        af["age"] = af["issue_age"] + af["year"] - 1
        af["premium"] = af["age"] * 2
    
    # Run in debug mode
    af = ActuarialFrame(debug=True)
    # ... load model points ...
    model(af)
    
    # Export graph
    json_graph = export_calculation_graph(af)
    graph_data = json.loads(json_graph)
    
    # Verify structure
    assert len(graph_data["nodes"]) >= 6  # 3 inputs + 3 computed
    assert len(graph_data["edges"]) >= 5
    
    # Verify dependencies
    age_node = next(n for n in graph_data["nodes"] if n["id"] == "age")
    assert set(age_node["data"]["dependencies"]) == {"issue_age", "year"}
```

## Success Criteria

1. **Dependency Extraction**: Correctly identifies all column references in expressions
2. **Graph Structure**: Produces valid DAG with no missing dependencies
3. **JSON Format**: Output matches specified format and can be visualized
4. **Performance**: Minimal overhead when running in debug mode
5. **Coverage**: Handles all expression types used in My Model model

## Future Enhancements (Post-MVP)

- Value sampling: Include actual computed values in nodes
- Circular dependency detection
- Topological sort for execution order
- Graph optimization suggestions
- Interactive visualization component
- Expression simplification analysis