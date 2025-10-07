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

## Decisions and Constraints

The following policies are confirmed and in-scope for implementation:

- **Identifier policy**: Strict. Attribute access must satisfy `str.isidentifier()` and must not be a Python keyword (`keyword.iskeyword(name)`).
- **Underscore names**: Disallowed via attribute (including leading underscore or dunder). Use bracket notation only.
- **Conflict resolution**: Accessors win. If an attribute name matches a registered accessor, the accessor is returned. Class methods/properties continue to have precedence over columns. Columns are only returned if there is no conflict.
- **Non-identifier column names**: Strict. No sanitization or mapping. Use bracket notation only.
- **Column attribute caching**: Disabled. Do not cache `ColumnProxy` on instances to avoid staleness after rename/drop.
- **Autocomplete (`__dir__`)**: Include valid-identifier, non-underscore column names; exclude underscores and non-identifiers. Keep accessor names included. Refresh on schema/order changes.
- **Performance**: Maintain an internal set for O(1) membership tests of attribute-eligible column names (kept in sync with `_column_order`).
- **Error messages**: Use the messages specified in this doc (see Error Handling Strategy).
- **Assignment via attribute**: In scope. Implement attribute-style assignment for eligible identifiers (see Section “Attribute Assignment Semantics”).
- **Feature flag**: None. This behavior is the default.
- **Type stubs**: Update `.pyi` stubs to reflect dynamic `__getattr__` and `__setattr__` behavior, plus accessor overloads.
- **Edge cases**: Unicode identifiers allowed; dunder names disallowed via attribute; reserved names like `columns` and accessors remain properties/methods; bracket notation always works.
- **Autocomplete staleness**: `__dir__` should reflect current eligible columns based on tracked state.
- **Tests location**: Place tests under `bindings/python/tests`.

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
3. Reject Python keywords (`keyword.iskeyword(name)`)
4. Disallow underscore/dunder names (`name.startswith("_")`)
5. Check for method/attribute conflicts (`hasattr(type(self), name)` or reserved names)
6. Check if name exists in attribute-eligible set (`name in self._attr_columns_set`)
7. Return `self[name]` if found (delegates to `__getitem__`)
8. Provide helpful error message if not found

#### 1.2 Error Handling Strategy
- **Invalid identifiers**: `"'{name}' is not a valid attribute name"`
- **Method conflicts**: `"'{name}' conflicts with existing method/attribute"`
- **Column not found**: `"'{type(self).__name__}' object has no attribute '{name}'. If '{name}' is a column name, use af['{name}'] instead."`

Additional conditions:
- **Keyword names**: `"'{name}' is a Python keyword; use af['{name}'] instead"`
- **Underscore/dunder names**: `"'{name}' is not available via attribute access; use af['{name}']"`

#### 1.3 Precedence Order
1. **Accessors** (date, excel, finance) - highest priority
2. **Class methods/attributes** (count, mean, sum, etc.)
3. **Valid column names** (Python identifiers only)
4. **Error for invalid/not found**

#### 1.4 Implement `__setattr__` for Attribute-Style Column Assignment

Enable `af.new_col = expr` for eligible identifiers. This does not cache proxies or shadow internal state.

Rules:
1. If the name targets known internal/private attributes or existing class attributes/properties/accessors, defer to `object.__setattr__` (or raise, if property denies assignment). Reserved names cannot be overridden.
2. If the name fails identifier checks (`not isidentifier`, `iskeyword`, startswith underscore), raise `AttributeError` instructing to use bracket assignment: `af['name'] = value`.
3. If the name matches a registered accessor, raise `AttributeError` to avoid collisions: instruct to use bracket assignment instead.
4. Otherwise, treat as column assignment and delegate to `__setitem__`: `self[name] = value`.

Pseudo-code:
```python
def __setattr__(self, name: str, value: Any) -> None:
    # 1) Existing attributes/accessors/properties: normal behavior
    if name.startswith("_") or hasattr(type(self), name) or name in _ACCESSOR_REGISTRY:
        return object.__setattr__(self, name, value)

    # 2) Enforce identifier policy for column assignment
    if (not name.isidentifier()) or keyword.iskeyword(name) or name.startswith("_"):
        raise AttributeError(
            f"'{name}' is not a valid attribute name; use af['{name}'] = ..."
        )

    # 3) Column assignment via bracket semantics
    self[name] = value
```

Notes:
- Attempting to override reserved names like `columns`, `date`, `excel`, `finance` should not result in a column assignment.
- Attribute deletion (`del af.col`) is out of scope for now; use explicit column APIs.

### Phase 2: Testing Strategy

#### 2.1 Unit Tests
**Location**: `bindings/python/tests/`

**Test cases**:
- Basic attribute access functionality
- Basic attribute assignment (`af.col = expr`) and type coverage
- Invalid Python identifiers (spaces, numbers, special chars)
- Python keywords rejection
- Underscore/dunder names rejection
- Method name conflicts (count, mean, sum)
- Accessor precedence (date, excel, finance)
- Nonexistent attributes
- Edge cases (empty column names, unicode, keywords)
- `__dir__` autocomplete includes only eligible columns and accessors

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
- Add examples for attribute assignment: `af.new_col = af["a"] + 1`
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
- Maintain `self._attr_columns_set` (eligible names) for O(1) membership
- Optimize `name in self.columns` lookup when needed
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
elif name in self._attr_columns_set:
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
- **Fallback**: N/A (feature is default; rely on documentation and toggling usage)

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
- [ ] `af.new_col = expr` creates/updates columns for eligible identifiers
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
- Implement `__setattr__` for attribute-style assignment
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
2. **Short-term**: Temporarily disable attribute assignment by reverting `__setattr__`
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
  and implemented `__setattr__` for attribute assignment

### Testing
- `bindings/python/tests/test_column_attribute_access.py` - Comprehensive suite (access + assignment)
- `bindings/python/tests/performance/test_column_access_perf.py` - Performance benchmarks

### Documentation
- Update class docstrings throughout codebase
- Update README and user guides
- Add migration examples
 
### Type Stubs
- Update `ActuarialFrame` stubs to include accessor overloads, `__getattr__`, and `__setattr__`

This plan provides a senior engineer with complete context and implementation strategy for adding pandas-style column attribute access to ActuarialFrame while maintaining backward compatibility and following established best practices.