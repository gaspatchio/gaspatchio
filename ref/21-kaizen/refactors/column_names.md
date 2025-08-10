# Column Attribute Access Enhancement

## Overview

This refactor adds support for pandas-style attribute column access (`af.column_name`) to ActuarialFrame, while maintaining the existing bracket notation (`af["column_name"]`) as the primary recommended method.

## Background Context

### Current State
- ActuarialFrame currently only supports bracket notation for column access: `af["column_name"]`
- This returns a `ColumnProxy` object that enables method chaining and accessor usage
- The `__getattr__` method in `ActuarialFrame` (`gaspatchio_core/frame/base.py:1602`) currently only handles dynamic accessor instantiation (date, excel, finance)

### User Request
Users want the convenience of pandas-style attribute access: `af.column_name` in addition to the existing bracket notation, similar to how `df.column_name` works in pandas.

### Research Findings
Based on analysis of pandas and Polars implementations:

1. **Pandas Pattern**: Uses `__getattr__` with fallback chain: methods → internal attributes → column names
2. **Common Gotchas**:
   - Method name conflicts (columns named "count", "mean", etc.)
   - Invalid Python identifiers (spaces, special chars, starting with numbers)
   - Shadowing of internal attributes
   - Assignment asymmetry
   - IDE/static analysis limitations

3. **Best Practices**:
   - Validate Python identifiers
   - Give precedence to methods/attributes
   - Provide clear error messages
   - Document limitations
   - Keep bracket notation as primary method

## Implementation Plan

### Phase 1: Core Implementation

#### 1.1 Modify `__getattr__` Method
**File**: `gaspatchio_core/frame/base.py:1602`

**Current signature**:
```python
def __getattr__(self, name: str) -> Any:
    """Dynamically instantiate and return registered frame accessors."""
```

**New implementation order**:
1. Check for registered frame accessors (existing logic)
2. Validate Python identifier (`name.isidentifier()`)
3. Check for method/attribute conflicts (`hasattr(type(self), name)`)
4. Check if name exists in columns (`name in self.columns`)
5. Return `self[name]` if found (delegates to `__getitem__`)
6. Provide helpful error message if not found

#### 1.2 Error Handling Strategy
- **Invalid identifiers**: `"'{name}' is not a valid attribute name"`
- **Method conflicts**: `"'{name}' conflicts with existing method/attribute"`
- **Column not found**: `"'{type(self).__name__}' object has no attribute '{name}'. If '{name}' is a column name, use af['{name}'] instead."`

#### 1.3 Precedence Order
1. **Accessors** (date, excel, finance) - highest priority
2. **Class methods/attributes** (count, mean, sum, etc.)
3. **Valid column names** (Python identifiers only)
4. **Error for invalid/not found**

### Phase 2: Testing Strategy

#### 2.1 Unit Tests
**File**: `tests/test_column_attribute_access.py`

**Test cases**:
- Basic attribute access functionality
- Invalid Python identifiers (spaces, numbers, special chars)
- Method name conflicts (count, mean, sum)
- Accessor precedence (date, excel, finance)
- Nonexistent attributes
- Edge cases (empty column names, unicode, keywords)

#### 2.2 Integration Tests
- Test with real actuarial models
- Performance comparison (attribute vs bracket access)
- Memory usage analysis
- IDE autocompletion behavior

#### 2.3 Regression Tests
- Ensure existing accessor functionality unchanged
- Verify bracket notation still works identically
- Confirm no performance degradation

### Phase 3: Documentation Updates

#### 3.1 Docstring Updates
**Files to update**:
- `gaspatchio_core/frame/base.py` - ActuarialFrame class docstring
- Method docstrings throughout the codebase

**Content changes**:
- Add examples showing both `af.column_name` and `af["column_name"]`
- Document limitations and gotchas
- Recommend bracket notation for programmatic access
- Show error scenarios and solutions

#### 3.2 User Documentation
- Update README with new feature
- Add migration guide from bracket-only usage
- Document best practices and limitations

### Phase 4: Performance Considerations

#### 4.1 Performance Analysis
- Benchmark `__getattr__` overhead
- Compare attribute vs bracket access speed
- Profile column lookup performance
- Memory usage analysis

#### 4.2 Optimization Opportunities
- Cache column name validation results
- Optimize `name in self.columns` lookup
- Consider lazy evaluation strategies

## Technical Specifications

### 4.1 Method Signature
```python
def __getattr__(self, name: str) -> Any:
    """Dynamically instantiate and return registered frame accessors or provide column access."""
```

### 4.2 Return Types
- **Accessors**: Accessor instance (DateFrameAccessor, etc.)
- **Columns**: ColumnProxy (same as bracket notation)
- **Errors**: AttributeError with descriptive message

### 4.3 Validation Logic
```python
# Pseudo-code implementation
if name in _ACCESSOR_REGISTRY:
    return instantiate_accessor(name)
elif not name.isidentifier():
    raise AttributeError(f"'{name}' is not a valid attribute name")
elif hasattr(type(self), name):
    raise AttributeError(f"'{name}' conflicts with existing method/attribute")
elif name in self.columns:
    return self[name]
else:
    raise AttributeError(helpful_message)
```

## Risk Assessment

### 4.1 Breaking Changes
- **Risk**: Low - purely additive feature
- **Mitigation**: Extensive regression testing

### 4.2 Performance Impact
- **Risk**: Medium - `__getattr__` overhead on attribute access
- **Mitigation**: Benchmark and optimize hot paths
- **Fallback**: Feature flag for disable if needed

### 4.3 User Confusion
- **Risk**: Medium - method vs column conflicts
- **Mitigation**: Clear documentation and error messages
- **Strategy**: Promote bracket notation as primary method

### 4.4 IDE/Static Analysis
- **Risk**: Medium - dynamic attribute access limits tooling
- **Mitigation**: Document limitations, provide type stubs if needed

## Success Criteria

### 5.1 Functional Requirements
- [ ] `af.column_name` returns same ColumnProxy as `af["column_name"]`
- [ ] Invalid identifiers properly rejected with clear errors
- [ ] Method conflicts handled correctly (methods take precedence)
- [ ] Accessors continue to work unchanged
- [ ] Performance impact < 5% on typical operations

### 5.2 Quality Requirements
- [ ] 100% test coverage for new functionality
- [ ] All existing tests pass
- [ ] Documentation updated with examples
- [ ] Performance benchmarks within acceptable range

### 5.3 User Experience
- [ ] Clear error messages guide users to correct usage
- [ ] Feature works intuitively for pandas users
- [ ] No regression in existing functionality
- [ ] IDE autocompletion works reasonably well

## Implementation Timeline

### Week 1: Core Implementation
- Modify `__getattr__` method
- Basic functionality working
- Initial test suite

### Week 2: Testing & Polish  
- Comprehensive test coverage
- Performance analysis
- Error message refinement

### Week 3: Documentation & Integration
- Update docstrings and examples
- Integration testing
- User documentation

### Week 4: Review & Release
- Code review
- Final testing
- Release preparation

## Rollback Plan

If issues arise:
1. **Immediate**: Comment out column access logic in `__getattr__`
2. **Short-term**: Feature flag to disable new functionality  
3. **Long-term**: Full revert with lessons learned

## Questions for Stakeholders

1. **Error Handling**: Should we be more permissive with identifier validation, or stick to strict Python rules?

2. **Performance Trade-offs**: What's the acceptable performance overhead for this convenience feature?

3. **Documentation Strategy**: Should we promote attribute access as equal to bracket access, or keep bracket as primary?

4. **IDE Support**: Should we invest in type stub generation for better IDE support?

5. **Feature Scope**: Should this extend to assignment (`af.new_col = values`) or keep read-only?

## Future Enhancements

### Potential Extensions
- Attribute-style assignment: `af.new_column = expression`
- Better IDE support via dynamic type stubs
- Caching for performance optimization
- Configuration options for strictness levels

### Integration Opportunities
- Jupyter notebook tab completion
- Enhanced error reporting with suggestions
- Performance monitoring and optimization

---

## Files Modified/Created

### Core Implementation
- `gaspatchio_core/frame/base.py` - Modified `__getattr__` method

### Testing
- `tests/test_column_attribute_access.py` - New comprehensive test suite
- `tests/performance/test_column_access_perf.py` - Performance benchmarks

### Documentation
- Update class docstrings throughout codebase
- Update README and user guides
- Add migration examples

This plan provides a senior engineer with complete context and implementation strategy for adding pandas-style column attribute access to ActuarialFrame while maintaining backward compatibility and following established best practices.