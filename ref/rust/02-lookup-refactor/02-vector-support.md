# Vector Support Implementation Plan

## Problem Statement

The new `AssumptionTable::lookup_series()` implementation in `table.rs` only supports scalar lookups, returning `Series<f64>`. However, the old `perform_lookup()` implementation in `index.rs` was vector-aware and could return `Series<List<f64>>` when input keys contained lists.

This causes a breaking change where actuarial model code expects vector lookups to return lists for time-series projections, but now receives scalar values, leading to errors like:

```
invalid series dtype: expected `List`, got `f64` for series with name `monthly_persist_prob`
```

## Current State Analysis

### OLD Implementation (`perform_lookup` in `index.rs`)
- Calls `registry.lookup_vector()` which detects vector vs scalar inputs
- Returns `List<f64>` for vector lookups, scalar `f64` for scalar lookups  
- Handles mixed vector/scalar keys with broadcasting
- Uses `DashMap<Vec<Value>, Value>` with `Value` enum overhead

### NEW Implementation (`lookup_series` in `table.rs`)
- Always returns scalar `f64` Series
- No vector detection or List Series support
- Uses optimized `AHashMap<u64, f64>` with direct f64 storage
- Pre-compiled codecs for faster encoding

## Solution: Enhanced Vector-Aware `lookup_series`

### 1. Method Signature (Unchanged)

```rust
impl AssumptionTable {
    pub fn lookup_series(&self, key_cols: &[&Series]) -> PolarsResult<Series>
}
```

### 2. Main Logic Flow

```rust
pub fn lookup_series(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
    // Validate input lengths
    if key_cols.len() != self.codecs.len() {
        return Err(polars_err!(ShapeMismatch: "wrong # key columns"));
    }
    
    // Fast path: Quick check for scalar-only inputs (most common case)
    if key_cols.iter().all(|s| !matches!(s.dtype(), DataType::List(_))) {
        return self.lookup_scalar(key_cols);
    }
    
    // Vector path: Full analysis when lists are present
    let (any_vectors, vector_len, vector_indices) = self.analyze_inputs(key_cols)?;
    
    if any_vectors {
        self.lookup_vector(key_cols, vector_len.unwrap(), &vector_indices)
    } else {
        self.lookup_scalar(key_cols)
    }
}
```

### 3. Input Analysis Helper

```rust
fn analyze_inputs(&self, key_cols: &[&Series]) -> PolarsResult<(bool, Option<usize>, Vec<usize>)> {
    let mut any_vectors = false;
    let mut vector_len = None;
    let mut vector_indices = Vec::new();
    
    for (i, series) in key_cols.iter().enumerate() {
        if matches!(series.dtype(), DataType::List(_)) {
            any_vectors = true;
            vector_indices.push(i);
            let current_len = series.len();
            
            // Validate all vector columns have same length
            if let Some(expected_len) = vector_len {
                if current_len != expected_len {
                    return Err(polars_err!(ShapeMismatch: 
                        "Vector length mismatch: expected {}, got {} for column {}", 
                        expected_len, current_len, i
                    ));
                }
            } else {
                vector_len = Some(current_len);
            }
        } else if any_vectors {
            // Scalar column in presence of vectors - validate broadcasting compatibility
            let scalar_len = series.len();
            let vec_len = vector_len.unwrap();
            if !(scalar_len == 1 || scalar_len == vec_len) {
                return Err(polars_err!(ShapeMismatch:
                    "Scalar column {} has length {} but expected 1 or {} for broadcasting",
                    i, scalar_len, vec_len
                ));
            }
        }
    }
    
    Ok((any_vectors, vector_len, vector_indices))
}
```

### 4. Scalar Lookup (Current Implementation)

```rust
fn lookup_scalar(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
    let len = key_cols[0].len();
    
    // Validate all series have same length
    for s in key_cols.iter().skip(1) {
        if s.len() != len {
            return Err(polars_err!(ShapeMismatch: "key columns not equal length"));
        }
    }

    // Pre-allocate result vector
    let mut out = vec![f64::NAN; len];
    
    // Parallel processing for scalar lookups
    out.par_iter_mut().enumerate().for_each(|(idx, slot)| {
        let mut h = AHasher::default();
        for (codec, series) in self.codecs.iter().zip(key_cols) {
            let av = unsafe { series.get_unchecked(idx) };
            h.write_u64((codec.encode)(av));
        }
        let key = h.finish();
        if let Some(v) = self.map.get(&key) {
            *slot = *v;
        }
    });

    Ok(Series::from_vec("lookup".into(), out))
}
```

### 5. Vector Lookup (New Implementation)

```rust
fn lookup_vector(&self, key_cols: &[&Series], vector_len: usize, vector_indices: &[usize]) -> PolarsResult<Series> {
    let vector_indices_set: std::collections::HashSet<usize> = 
        vector_indices.iter().copied().collect();
    
    // Determine parallelization threshold
    let use_parallel = vector_len > 100;
    
    // Process each row (policy/entity)
    let series_list_result: PolarsResult<Vec<Series>> = if use_parallel {
        (0..vector_len)
            .into_par_iter()
            .map(|row_idx| self.process_vector_row(key_cols, &vector_indices_set, row_idx))
            .collect()
    } else {
        (0..vector_len)
            .map(|row_idx| self.process_vector_row(key_cols, &vector_indices_set, row_idx))
            .collect()
    };
    
    let series_list = series_list_result?;
    
    // Convert to ListChunked
    let list_chunked = ListChunked::from_iter(series_list.into_iter().map(Some))
        .with_name("lookup".into());
    
    Ok(list_chunked.into_series())
}

fn process_vector_row(&self, key_cols: &[&Series], vector_indices_set: &std::collections::HashSet<usize>, row_idx: usize) -> PolarsResult<Series> {
    // Get inner list length from first vector column
    let first_vector_idx = *vector_indices_set.iter().next().unwrap();
    let inner_len = self.get_inner_list_len(key_cols[first_vector_idx], row_idx)?;
    
    if inner_len == 0 {
        return Ok(Series::new_empty("inner".into(), &DataType::Float64));
    }
    
    // Pre-allocate result vector
    let mut inner_results = Vec::with_capacity(inner_len);
    
    // Process each element in the inner lists
    for element_idx in 0..inner_len {
        let mut h = AHasher::default();
        let mut key_has_null = false;
        
        // Build hash key from all input columns
        for (key_idx, series) in key_cols.iter().enumerate() {
            let value_result = if vector_indices_set.contains(&key_idx) {
                // Vector key - extract from list at [row_idx][element_idx]
                self.extract_from_list(series, row_idx, element_idx)
            } else {
                // Scalar key - broadcast (len=1) or row-wise (len=vector_len)
                let scalar_idx = if series.len() == 1 { 0 } else { row_idx };
                self.extract_scalar(series, scalar_idx)
            };
            
            match value_result {
                Ok(av) => {
                    if matches!(av, AnyValue::Null) {
                        key_has_null = true;
                    }
                    h.write_u64((self.codecs[key_idx].encode)(av));
                }
                Err(_) => {
                    key_has_null = true;
                    h.write_u64(0u64); // Fallback for errors
                }
            }
        }
        
        // Perform lookup
        let result_value = if key_has_null {
            f64::NAN
        } else {
            let key = h.finish();
            self.map.get(&key).copied().unwrap_or(f64::NAN)
        };
        
        inner_results.push(result_value);
    }
    
    Ok(Series::from_vec("inner".into(), inner_results))
}
```

### 6. Value Extraction Helpers

```rust
fn get_inner_list_len(&self, list_series: &Series, row_idx: usize) -> PolarsResult<usize> {
    let list_ca = list_series.list()?;
    if row_idx >= list_ca.len() {
        return Ok(0);
    }
    
    match list_ca.get_any_value(row_idx)? {
        AnyValue::List(inner_series) => Ok(inner_series.len()),
        AnyValue::Null => Ok(0),
        _ => Err(polars_err!(ComputeError: "Expected List type in get_inner_list_len")),
    }
}

fn extract_from_list(&self, series: &Series, row_idx: usize, element_idx: usize) -> PolarsResult<AnyValue> {
    let list_ca = series.list()?;
    if row_idx >= list_ca.len() {
        return Ok(AnyValue::Null);
    }
    
    match list_ca.get_any_value(row_idx)? {
        AnyValue::List(inner_series) => {
            if element_idx < inner_series.len() {
                Ok(inner_series.get(element_idx)?)
            } else {
                Ok(AnyValue::Null)
            }
        }
        AnyValue::Null => Ok(AnyValue::Null),
        _ => Err(polars_err!(ComputeError: "Expected List type in extract_from_list")),
    }
}

fn extract_scalar(&self, series: &Series, idx: usize) -> PolarsResult<AnyValue> {
    if idx >= series.len() {
        Ok(AnyValue::Null)
    } else {
        Ok(series.get(idx)?)
    }
}
```

### 7. Update Output Type Function

```rust
fn lookup_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    // Check if any input is a List type
    let has_list_input = input_fields.iter().any(|field| {
        matches!(field.data_type(), DataType::List(_))
    });
    
    let value_dtype = DataType::Float64;
    let output_dtype = if has_list_input {
        DataType::List(Box::new(value_dtype))  // Vector lookup
    } else {
        value_dtype  // Scalar lookup
    };
    
    Ok(Field::new(
        PlSmallStr::from_static("lookup_result"),
        output_dtype,
    ))
}
```

## Performance Analysis

### Expected Performance Characteristics

#### Scalar Lookups (Most Common Case)
- **Performance**: **25-50% faster** than old implementation
- **Overhead**: Minimal input analysis (O(k) where k = number of key columns)
- **Memory**: More efficient due to direct f64 storage vs Value enum boxing

#### Vector Lookups (Actuarial Projections)  
- **Performance**: **40-60% faster** than old implementation
- **Reasons**:
  - No `Value` enum boxing/unboxing overhead
  - Faster `AHasher` vs `DefaultHasher`
  - Direct f64 map vs generic `DashMap<Vec<Value>, Value>`
  - Pre-compiled codecs vs runtime type dispatch
  - Better memory locality with contiguous f64 storage

#### Performance Optimizations

1. **Fast Path Detection**: Quick dtype check avoids analysis for scalar-only inputs
2. **Parallel Processing**: Both scalar and vector paths use `rayon` for parallelization
3. **Memory Pre-allocation**: Vectors sized based on known capacities
4. **Efficient Data Structures**: `AHashMap<u64, f64>` vs `DashMap<Vec<Value>, Value>`

### Benchmark Expectations

```rust
// Scalar lookup: 1000 rows, 2 keys
// Old: ~50μs (Value conversions + DashMap overhead)
// New: ~25μs (direct f64 + AHashMap + fast path)

// Vector lookup: 100 policies × 600 months, 2 keys  
// Old: ~15ms (60k Value conversions + DashMap contention)
// New: ~8ms (direct f64 + optimized codecs + parallel processing)
```

## Migration Strategy

### Phase 1: Implement Vector Support
- Add vector detection and lookup logic to `AssumptionTable`
- Maintain backward compatibility for scalar inputs
- Update output type function to handle both cases

### Phase 2: Test Compatibility
- Ensure new implementation returns same types as old:
  - Vector inputs → `Series<List<f64>>` output
  - Scalar inputs → `Series<f64>` output
- Run existing test suite to verify behavior

### Phase 3: Integration
- `lookup_by_table_and_hash` automatically gets vector support
- Model code should work without changes
- Monitor performance improvements

## Expected Behavior After Implementation

```rust
// Scalar Input Example:
// age-last = [31, 32, 33], variable = ["MNS", "FNS", "MS"] (scalars)
// Output: Series<f64> = [0.0012, 0.0013, 0.0014]

// Vector Input Example:  
// age-last = [[31, 32], [33, 34]], variable = ["MNS", "FNS"] (vectors)
// Output: Series<List<f64>> = [[0.0012, 0.0013], [0.0014, 0.0015]]

// Mixed Input Example (Broadcasting):
// age-last = [[31, 32], [33, 34]], variable = ["MNS"] (scalar broadcast)
// Output: Series<List<f64>> = [[0.0012, 0.0013], [0.0014, 0.0015]]
```

## Testing Strategy

### Unit Tests
- Scalar-only inputs (existing behavior)
- Vector-only inputs (new behavior)
- Mixed scalar/vector inputs with broadcasting
- Error cases (mismatched lengths, invalid types)

### Integration Tests
- Run existing model code to ensure compatibility
- Performance benchmarks vs old implementation
- Memory usage validation

### Edge Cases
- Empty lists in vector inputs
- Null values in keys
- Single-element vectors vs scalars
- Large vector inputs (performance validation)

This implementation maintains full backward compatibility while adding the missing vector support that actuarial model code requires, with expected performance improvements across all use cases.
