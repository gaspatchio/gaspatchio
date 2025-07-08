# When-Then Conditional Expression Support Plan

## Overview

This document outlines the implementation plan for adding `when-then` conditional expression support to the ActuarialFrame, providing a wrapper around Polars' `when().then().otherwise()` functionality that integrates seamlessly with the expression proxy system.

## Goals

1. **Seamless Integration**: Provide intuitive conditional expression support that works naturally with the existing proxy system
2. **Vector Support**: Ensure conditional operations work correctly on both scalar and vector (list) columns
3. **Type Safety**: Maintain type consistency and proper error handling
4. **Performance**: Leverage Polars' efficient conditional execution without overhead

## Design Approach

### 1. Conditional Proxy Pattern

Create a specialized `ConditionalProxy` class that represents an in-progress conditional expression:

```python
class ConditionalProxy:
    """Represents a conditional expression chain (when-then-otherwise)."""
    
    def __init__(self, condition: pl.Expr, parent: ActuarialFrame):
        self._condition = condition
        self._parent = parent
        self._when_then_pairs: list[tuple[pl.Expr, pl.Expr]] = []
        self._otherwise_expr: pl.Expr | None = None
    
    def then(self, value) -> "ConditionalProxy":
        """Specify the value when condition is true."""
        # Implementation details below
    
    def when(self, condition) -> "ConditionalProxy":
        """Add another condition (elif)."""
        # Implementation details below
    
    def otherwise(self, value) -> ExpressionProxy:
        """Specify the default value and complete the expression."""
        # Implementation details below
```

### 2. Integration Points

#### 2.1 Module-Level Function
Add a `when()` function at the module level that initiates conditional expressions:

```python
def when(condition) -> ConditionalProxy:
    """
    Start a conditional expression.
    
    Examples
    --------
    >>> import gaspatchio as gp
    >>> # Simple condition
    >>> gp.when(af["age"] > 65).then(0.05).otherwise(0.02)
    >>> 
    >>> # Multiple conditions
    >>> (gp.when(af["age"] < 18).then("child")
    ...    .when(af["age"] < 65).then("adult")
    ...    .otherwise("senior"))
    """
```

#### 2.2 Column Proxy Method
Add a `when()` method to `ColumnProxy` for column-specific conditions:

```python
class ColumnProxy:
    def when(self, condition) -> ConditionalProxy:
        """
        Apply conditional logic to this column.
        
        Examples
        --------
        >>> # Apply different rates based on age
        >>> af["rate"] = af["base_rate"].when(af["age"] > 65).then(0.05).otherwise(0.02)
        """
```

### 3. Vector Column Support

Extend the conditional logic to work with vector columns:

```python
def _handle_vector_conditional(self, condition, then_value, otherwise_value):
    """Handle conditional operations on list columns."""
    if self._is_list_column():
        # Use list.eval for element-wise conditionals
        return self.list.eval(
            pl.when(condition).then(then_value).otherwise(otherwise_value)
        )
```

### 4. Implementation Details

#### 4.1 Core Methods

```python
class ConditionalProxy:
    def then(self, value):
        """Specify the value when condition is true."""
        value_expr = self._parent._convert_to_expr(value)
        
        if self._when_then_pairs:
            # This is part of a chain, add to pairs
            last_condition = self._when_then_pairs[-1][0]
            self._when_then_pairs[-1] = (last_condition, value_expr)
        else:
            # First then in the chain
            self._when_then_pairs.append((self._condition, value_expr))
        
        return self
    
    def when(self, condition):
        """Add another condition (elif)."""
        condition_expr = self._parent._convert_to_expr(condition)
        self._when_then_pairs.append((condition_expr, None))
        return self
    
    def otherwise(self, value):
        """Specify the default value and complete the expression."""
        self._otherwise_expr = self._parent._convert_to_expr(value)
        
        # Build the Polars expression
        expr = pl.when(self._when_then_pairs[0][0]).then(self._when_then_pairs[0][1])
        
        for condition, then_value in self._when_then_pairs[1:]:
            expr = expr.when(condition).then(then_value)
        
        expr = expr.otherwise(self._otherwise_expr)
        
        return ExpressionProxy(expr, self._parent)
```

#### 4.2 Error Handling

- Validate that `then()` is called after each `when()`
- Ensure `otherwise()` is called to complete the expression
- Provide clear error messages for invalid chains

#### 4.3 Type Conversion

Ensure proper type conversion for literal values:

```python
def _convert_conditional_value(self, value):
    """Convert Python values to appropriate Polars expressions."""
    if isinstance(value, (int, float, str, bool)):
        return pl.lit(value)
    elif isinstance(value, (ColumnProxy, ExpressionProxy)):
        return value._to_expr()
    elif isinstance(value, pl.Expr):
        return value
    else:
        raise ValueError(f"Unsupported type for conditional value: {type(value)}")
```

### 5. Testing Strategy

#### 5.1 Unit Tests
- Test basic when-then-otherwise chains
- Test multiple when conditions (elif chains)
- Test with different value types (literals, columns, expressions)
- Test error cases (incomplete chains, invalid types)

#### 5.2 Integration Tests
- Test with ActuarialFrame operations
- Test in computation graph mode
- Test with vector columns
- Test performance with large datasets

#### 5.3 Example Tests

```python
def test_simple_conditional():
    af = ActuarialFrame({"age": [25, 45, 70], "base_rate": [0.01, 0.02, 0.03]})
    af["adjusted_rate"] = when(af["age"] > 65).then(0.05).otherwise(af["base_rate"])
    result = af.collect()
    assert result["adjusted_rate"].to_list() == [0.01, 0.02, 0.05]

def test_chained_conditional():
    af = ActuarialFrame({"score": [0, 50, 80, 100]})
    af["grade"] = (when(af["score"] >= 90).then("A")
                   .when(af["score"] >= 80).then("B")
                   .when(af["score"] >= 70).then("C")
                   .otherwise("F"))
    result = af.collect()
    assert result["grade"].to_list() == ["F", "F", "B", "A"]

def test_vector_conditional():
    af = ActuarialFrame({
        "id": [1, 2],
        "values": [[10, 20, 30], [5, 15, 25]],
        "threshold": [15, 20]
    })
    af["above_threshold"] = af["values"].when(af["values"] > af["threshold"]).then(1).otherwise(0)
    # Should apply element-wise within each vector
```

### 6. Documentation Plan

#### 6.1 User Guide
- Introduction to conditional expressions
- Common patterns in actuarial modeling
- Performance considerations

#### 6.2 API Reference
- Detailed documentation for each method
- Parameter descriptions
- Return types
- Examples for each use case

#### 6.3 Cookbook Examples
- Risk classification based on multiple factors
- Premium adjustment calculations
- Benefit determination logic
- Vector-based conditional operations

### 7. Implementation Steps

1. **Phase 1: Core Implementation**
   - [ ] Create `ConditionalProxy` class
   - [ ] Implement basic when-then-otherwise chain
   - [ ] Add module-level `when()` function
   - [ ] Add `when()` method to `ColumnProxy`

2. **Phase 2: Advanced Features**
   - [ ] Support multiple when conditions (elif)
   - [ ] Add vector column support
   - [ ] Implement proper type conversion
   - [ ] Add error handling and validation

3. **Phase 3: Testing & Documentation**
   - [ ] Write comprehensive unit tests
   - [ ] Add integration tests
   - [ ] Create user documentation
   - [ ] Add cookbook examples

4. **Phase 4: Optimization**
   - [ ] Profile performance
   - [ ] Optimize for common patterns
   - [ ] Add caching if beneficial
   - [ ] Integration with computation graph

### 8. Future Enhancements

1. **Case/Switch Expressions**: Support for `case_when` style expressions
2. **Conditional Aggregations**: Special support for conditional aggregations
3. **Type-Safe Conditionals**: Enhanced type checking for conditional chains
4. **DSL Extensions**: Domain-specific conditional helpers (e.g., `when_age_band()`)

### 9. Success Criteria

- Intuitive API that feels natural to Python/Polars users
- Full compatibility with existing ActuarialFrame features
- No performance overhead compared to raw Polars
- Comprehensive documentation and examples
- Robust error handling with clear messages

## Calculation Graph Integration

### Overview

The when-then conditional expressions integrate seamlessly with the existing calculation graph infrastructure. The graph already captures complex Polars expressions, so conditional logic requires no special handling beyond ensuring proper dependency extraction and visualization.

### Integration Details

#### 1. Operation Capture

When a conditional expression is assigned to a column:

```python
af["risk_category"] = when(af["age"] > 65).then("high").otherwise("normal")
```

The calculation graph captures this as a `TracedOperation`:

```python
TracedOperation(
    alias="risk_category",
    expression=pl.when(col("age") > 65).then("high").otherwise("normal"),
    dependencies=["age"],  # Automatically extracted by expr_analyzer
    metadata=SourceLocation(file="model.py", line=42, function="calculate_risk")
)
```

#### 2. Dependency Extraction

The existing `expr_analyzer.py` module correctly handles conditional expressions:

- Uses `expr.meta.root_names()` which traverses the entire expression tree
- Extracts all column references from conditions and values
- Handles nested conditionals with multiple dependencies

Example with multiple dependencies:
```python
af["premium_adj"] = when(af["age"] > 60).then(
    af["base_premium"] * af["senior_factor"]
).otherwise(
    af["base_premium"]
)
# Dependencies: ["age", "base_premium", "senior_factor"]
```

#### 3. Graph Visualization

Conditional nodes in the calculation graph:

```json
{
  "nodes": [
    {
      "id": "risk_category",
      "type": "computed",
      "label": "risk_category",
      "data": {
        "formula": "when(age > 65).then('high').otherwise('normal')",
        "dependencies": ["age"],
        "is_conditional": true,  // New flag for visualization
        "conditions": [
          {"test": "age > 65", "result": "'high'"},
          {"test": "else", "result": "'normal'"}
        ]
      }
    }
  ]
}
```

#### 4. Trace Generation

The trace generator produces detailed step-by-step evaluation:

```json
{
  "column": "risk_category",
  "trace": [
    {
      "step": 1,
      "description": "Evaluate condition",
      "expr": "age > 65",
      "values": {"age": 38},
      "result": false
    },
    {
      "step": 2,
      "description": "Select branch",
      "expr": "otherwise('normal')",
      "result": "normal"
    }
  ]
}
```

#### 5. Execution Modes

**Debug Mode**:
- Conditional expressions execute immediately
- Full trace is captured with actual values
- Branch selection is recorded

**Optimize Mode**:
- Conditional expressions are deferred
- Included in the batched Polars query at `collect()`
- Dependencies ensure correct execution order

#### 6. Performance Considerations

1. **Batched Execution**: In optimize mode, all conditional expressions are part of a single Polars query plan, maintaining performance

2. **Lazy Evaluation**: The `ConditionalProxy` builds expressions without executing them until needed

3. **Expression Reuse**: Common conditional patterns can be stored and reused:
   ```python
   age_band = when(af["age"] < 18).then("child").when(af["age"] < 65).then("adult").otherwise("senior")
   af["age_category"] = age_band
   af["rate_category"] = age_band  # Reuses the same expression
   ```

#### 7. Special Considerations

1. **Complex Conditionals**: Nested conditions create deeper dependency trees but are handled correctly:
   ```python
   af["complex_risk"] = when(af["age"] > 60).then(
       when(af["health_score"] < 50).then("very_high")
       .when(af["health_score"] < 70).then("high")
       .otherwise("medium")
   ).otherwise("low")
   # Dependencies: ["age", "health_score"]
   ```

2. **Vector Conditionals**: When applied to list columns, the graph shows the list.eval wrapper:
   ```json
   {
     "formula": "list.eval(when(element() > threshold).then(1).otherwise(0))",
     "is_vector_operation": true
   }
   ```

3. **Conditional Assignment Patterns**: The graph can detect and optimize common patterns:
   - Binary classification (when-then-otherwise)
   - Multi-class categorization (multiple when-then chains)
   - Conditional calculations (different formulas based on conditions)

### Testing Graph Integration

Additional tests for calculation graph integration:

```python
def test_conditional_graph_capture():
    af = ActuarialFrame({"age": [25, 45, 70]}, mode="debug")
    af["category"] = when(af["age"] > 65).then("senior").otherwise("regular")
    
    # Check graph capture
    assert len(af._computation_graph) == 1
    op = af._computation_graph[0]
    assert op.alias == "category"
    assert op.dependencies == ["age"]
    assert "when" in str(op.expression)

def test_conditional_dependency_extraction():
    af = ActuarialFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
    af["result"] = when(af["a"] > 1).then(af["b"] * 2).otherwise(af["c"] - 1)
    
    # Should extract all three dependencies
    op = af._computation_graph[-1]
    assert sorted(op.dependencies) == ["a", "b", "c"]

def test_conditional_execution_order():
    af = ActuarialFrame({"x": [1, 2, 3]}, mode="optimize")
    af["y"] = af["x"] * 2
    af["z"] = when(af["y"] > 3).then("high").otherwise("low")
    
    # Should respect dependency order when collecting
    result = af.collect()
    assert result["z"].to_list() == ["low", "high", "high"]
```