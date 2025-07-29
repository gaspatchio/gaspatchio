# Step 6: Write Comprehensive Tests

Create thorough test coverage for the implemented function including list operations.

## Input
- Rust implementation from Step 5
- Behavior analysis from Step 3
- Test values from research
- Function name: `{{FUNCTION_NAME}}`
- List handling patterns from yearfrac tests

## Process

1. **Create test structure**:
   - Test calculation function directly
   - Test output type detection
   - Test Polars interface (scalar and list)
   - Test error conditions
   - Test Excel compatibility
   - Test list operations and broadcasting

2. **Use test values from research**:
   - HyperFormula test cases
   - Excel verified outputs
   - Edge cases discovered
   - Actuarial projection patterns

3. **Follow testing patterns**:
   - Use approx for floating point
   - Test null propagation at all levels
   - Verify error messages
   - Use property-based tests for lists

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/06-tests.rs` to append to the implementation:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;
    
    // Test categories:
    // 1. Calculation function tests
    // 2. Output type detection tests
    // 3. Scalar operation tests
    // 4. List operation tests
    // 5. Broadcasting tests
    // 6. Null handling tests
    // 7. Error condition tests
    // 8. Excel compatibility tests
    // 9. Property-based tests
}
```

## Complete Test Template with List Support

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;
    use chrono::NaiveDate;  // If using dates
    use polars::prelude::*;

    // Helper functions for test data creation
    fn create_float_series(name: &str, values: Vec<f64>) -> Series {
        Series::new(name.into(), values)
    }

    fn create_date_series(name: &str, dates: Vec<NaiveDate>) -> Series {
        let days: Vec<i32> = dates
            .into_iter()
            .map(|d| (d - NaiveDate::from_ymd_opt(1970, 1, 1).unwrap()).num_days() as i32)
            .collect();
        Series::new(name.into(), days)
    }

    fn create_string_series(name: &str, values: Vec<&str>) -> Series {
        Series::new(name.into(), values)
    }

    // Create list series from vectors of values
    fn create_float_list_series(values: Vec<Vec<f64>>) -> Series {
        let lists: Vec<Option<Series>> = values
            .into_iter()
            .map(|v| Some(Series::new("".into(), v)))
            .collect();
        
        ListChunked::from_iter(lists).into_series()
    }

    // Create date list series
    fn create_date_list_series(date_vecs: Vec<Vec<NaiveDate>>) -> Series {
        let lists: Vec<Option<Series>> = date_vecs
            .into_iter()
            .map(|dates| {
                let days: Vec<i32> = dates
                    .into_iter()
                    .map(|d| (d - NaiveDate::from_ymd_opt(1970, 1, 1).unwrap()).num_days() as i32)
                    .collect();
                Some(Series::new("".into(), days))
            })
            .collect();
        
        ListChunked::from_iter(lists).into_series()
    }

    // ===== Calculation Function Tests =====
    
    #[test]
    fn test_calculate_{{function_name}}_normal_cases() {
        // Test case from Excel documentation
        let result = calculate_{{function_name}}(100.0, 0.05, 0);
        assert_relative_eq!(result, 5.0, epsilon = 1e-10);
        
        // Test case from HyperFormula
        let result = calculate_{{function_name}}(200.0, 0.10, 1);
        assert_relative_eq!(result, 20.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_{{function_name}}_edge_cases() {
        // Zero handling
        let result = calculate_{{function_name}}(0.0, 0.05, 0);
        assert_eq!(result, 0.0);
        
        // Negative values
        let result = calculate_{{function_name}}(-100.0, 0.05, 0);
        assert_relative_eq!(result, -5.0, epsilon = 1e-10);
        
        // Very large values
        let result = calculate_{{function_name}}(1e10, 0.01, 0);
        assert_relative_eq!(result, 1e8, epsilon = 1e-10);
    }

    // ===== Output Type Detection Tests =====
    
    #[test]
    fn test_output_type_scalar_inputs() {
        let fields = vec![
            Field::new("param1".into(), DataType::Float64),
            Field::new("param2".into(), DataType::Float64),
        ];
        
        let result = {{function_name}}_output_type(&fields).unwrap();
        assert_eq!(result.dtype(), &DataType::Float64);
    }

    #[test]
    fn test_output_type_list_inputs() {
        let fields = vec![
            Field::new("param1".into(), DataType::List(Box::new(DataType::Float64))),
            Field::new("param2".into(), DataType::List(Box::new(DataType::Float64))),
        ];
        
        let result = {{function_name}}_output_type(&fields).unwrap();
        assert_eq!(result.dtype(), &DataType::List(Box::new(DataType::Float64)));
    }

    #[test]
    fn test_output_type_mixed_inputs() {
        // Scalar first, list second
        let fields = vec![
            Field::new("param1".into(), DataType::Float64),
            Field::new("param2".into(), DataType::List(Box::new(DataType::Float64))),
        ];
        
        let result = {{function_name}}_output_type(&fields).unwrap();
        assert_eq!(result.dtype(), &DataType::List(Box::new(DataType::Float64)));
        
        // List first, scalar second
        let fields = vec![
            Field::new("param1".into(), DataType::List(Box::new(DataType::Float64))),
            Field::new("param2".into(), DataType::Float64),
        ];
        
        let result = {{function_name}}_output_type(&fields).unwrap();
        assert_eq!(result.dtype(), &DataType::List(Box::new(DataType::Float64)));
    }

    // ===== Scalar Operation Tests =====

    #[test]
    fn test_{{function_name}}_scalar_basic() {
        let param1 = create_float_series("param1", vec![100.0, 200.0, 300.0]);
        let param2 = create_float_series("param2", vec![0.05, 0.10, 0.15]);
        
        let kwargs = {{FunctionName}}Kwargs {
            optional_param: Some(0),
        };
        
        let result = {{function_name}}(&[param1, param2], &kwargs).unwrap();
        let values = result.f64().unwrap();
        
        assert_relative_eq!(values.get(0).unwrap(), 5.0, epsilon = 1e-10);
        assert_relative_eq!(values.get(1).unwrap(), 20.0, epsilon = 1e-10);
        assert_relative_eq!(values.get(2).unwrap(), 45.0, epsilon = 1e-10);
    }

    // ===== List Operation Tests =====

    #[test]
    fn test_{{function_name}}_with_list_columns() {
        // Create list columns
        let list1_values = vec![
            vec![100.0, 200.0, 300.0],
            vec![150.0, 250.0, 350.0],
        ];
        let list2_values = vec![
            vec![0.05, 0.10, 0.15],
            vec![0.06, 0.11, 0.16],
        ];
        
        let param1_lists = create_float_list_series(list1_values.clone());
        let param2_lists = create_float_list_series(list2_values.clone());
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: Some(0) };
        let result = {{function_name}}(&[param1_lists, param2_lists], &kwargs).unwrap();
        
        // Verify result is a list column
        assert!(matches!(result.dtype(), DataType::List(_)));
        
        // Verify values
        let list_ca = result.list().unwrap();
        assert_eq!(list_ca.len(), 2); // Two rows
        
        // Check first row results
        if let Some(arr) = list_ca.get_as_series(0) {
            let values = arr.f64().unwrap();
            assert_eq!(values.len(), 3);
            assert_relative_eq!(values.get(0).unwrap(), 5.0, epsilon = 1e-10);
            assert_relative_eq!(values.get(1).unwrap(), 20.0, epsilon = 1e-10);
            assert_relative_eq!(values.get(2).unwrap(), 45.0, epsilon = 1e-10);
        }
    }

    #[test]
    fn test_{{function_name}}_mismatched_list_lengths() {
        let list1_values = vec![
            vec![100.0, 200.0],        // 2 elements
            vec![150.0, 250.0, 350.0], // 3 elements - mismatch!
        ];
        let list2_values = vec![
            vec![0.05, 0.10, 0.15],     // 3 elements - mismatch!
            vec![0.06, 0.11, 0.16],     // 3 elements
        ];
        
        let param1_lists = create_float_list_series(list1_values);
        let param2_lists = create_float_list_series(list2_values);
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: None };
        let result = {{function_name}}(&[param1_lists, param2_lists], &kwargs);
        
        // Should handle mismatched lengths gracefully
        // The exact behavior depends on the function requirements
    }

    // ===== Broadcasting Tests =====

    #[test]
    fn test_{{function_name}}_broadcast_scalar_first() {
        // Scalar first parameter, list second parameter
        let param1 = create_float_series("param1", vec![100.0, 100.0]); // Broadcasted scalar
        let list2_values = vec![
            vec![0.05, 0.10, 0.15],
            vec![0.06, 0.11, 0.16],
        ];
        let param2_lists = create_float_list_series(list2_values);
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: Some(0) };
        let result = {{function_name}}(&[param1, param2_lists], &kwargs).unwrap();
        
        // Verify result is a list column
        assert!(matches!(result.dtype(), DataType::List(_)));
        
        let list_ca = result.list().unwrap();
        assert_eq!(list_ca.len(), 2); // Two rows of lists
        
        // Each list should have 3 values (broadcast scalar to each element)
        for i in 0..2 {
            if let Some(arr) = list_ca.get_as_series(i) {
                let values = arr.f64().unwrap();
                assert_eq!(values.len(), 3);
                
                // All calculated with same first parameter (100.0)
                assert_relative_eq!(values.get(0).unwrap(), 5.0, epsilon = 1e-10);
                assert_relative_eq!(values.get(1).unwrap(), 10.0, epsilon = 1e-10);
                assert_relative_eq!(values.get(2).unwrap(), 15.0, epsilon = 1e-10);
            }
        }
    }

    #[test]
    fn test_{{function_name}}_broadcast_scalar_second() {
        // List first parameter, scalar second parameter
        let list1_values = vec![
            vec![100.0, 200.0, 300.0],
            vec![150.0, 250.0, 350.0],
        ];
        let param1_lists = create_float_list_series(list1_values);
        let param2 = create_float_series("param2", vec![0.10, 0.10]); // Broadcasted scalar
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: Some(0) };
        let result = {{function_name}}(&[param1_lists, param2], &kwargs).unwrap();
        
        // Verify result structure
        assert!(matches!(result.dtype(), DataType::List(_)));
        
        let list_ca = result.list().unwrap();
        assert_eq!(list_ca.len(), 2);
        
        // Verify values - all use same second parameter (0.10)
        if let Some(arr) = list_ca.get_as_series(0) {
            let values = arr.f64().unwrap();
            assert_relative_eq!(values.get(0).unwrap(), 10.0, epsilon = 1e-10);
            assert_relative_eq!(values.get(1).unwrap(), 20.0, epsilon = 1e-10);
            assert_relative_eq!(values.get(2).unwrap(), 30.0, epsilon = 1e-10);
        }
    }

    #[test]
    fn test_{{function_name}}_dataframe_scalar_broadcasting() {
        // Test Polars DataFrame scalar broadcasting behavior
        // When a scalar is provided to DataFrame, it's repeated for all rows
        let param1 = create_float_series("param1", vec![100.0]); // True scalar
        let list2_values = vec![
            vec![0.05, 0.10, 0.15],
        ];
        let param2_lists = create_float_list_series(list2_values);
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: Some(0) };
        let result = {{function_name}}(&[param1, param2_lists], &kwargs).unwrap();
        
        // Should work with any length scalar (not just length 1)
        assert!(result.is_ok());
    }

    // ===== Null Handling Tests =====

    #[test]
    fn test_{{function_name}}_null_propagation_scalars() {
        let param1 = Series::new("param1".into(), vec![Some(100.0), None, Some(300.0)]);
        let param2 = Series::new("param2".into(), vec![Some(0.05), Some(0.10), None]);
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: None };
        let result = {{function_name}}(&[param1, param2], &kwargs).unwrap();
        let values = result.f64().unwrap();
        
        // First: both present, should calculate
        assert!(values.get(0).is_some());
        assert_relative_eq!(values.get(0).unwrap(), 5.0, epsilon = 1e-10);
        
        // Second: first null, should be null
        assert!(values.get(1).is_none());
        
        // Third: second null, should be null
        assert!(values.get(2).is_none());
    }

    #[test]
    fn test_{{function_name}}_null_handling_lists() {
        // Test with nulls at different levels
        let list1_values = vec![
            vec![100.0, 200.0, 300.0],
            vec![150.0, 250.0],         // Will have null in matching position
        ];
        let list2_values = vec![
            vec![0.05, 0.10, 0.15],
            vec![0.06, 0.11],           // Shorter list
        ];
        
        // Create lists with explicit nulls
        let lists1: Vec<Option<Series>> = vec![
            Some(Series::new("".into(), vec![Some(100.0), None, Some(300.0)])),
            Some(Series::new("".into(), vec![Some(150.0), Some(250.0)])),
            None, // Entire list is null
        ];
        let lists2: Vec<Option<Series>> = vec![
            Some(Series::new("".into(), vec![Some(0.05), Some(0.10), None])),
            Some(Series::new("".into(), vec![Some(0.06), Some(0.11)])),
            Some(Series::new("".into(), vec![Some(0.05), Some(0.10)])),
        ];
        
        let param1_lists = ListChunked::from_iter(lists1).into_series();
        let param2_lists = ListChunked::from_iter(lists2).into_series();
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: None };
        let result = {{function_name}}(&[param1_lists, param2_lists], &kwargs).unwrap();
        
        let list_ca = result.list().unwrap();
        
        // First row: has nulls within the list
        if let Some(arr) = list_ca.get_as_series(0) {
            let values = arr.f64().unwrap();
            assert!(values.get(0).is_some()); // 100.0 * 0.05
            assert!(values.get(1).is_none());  // null * 0.10
            assert!(values.get(2).is_none());  // 300.0 * null
        }
        
        // Third row: entire list should be null
        assert!(list_ca.get(2).is_none());
    }

    #[test]
    fn test_{{function_name}}_empty_lists() {
        let empty_lists: Vec<Option<Series>> = vec![
            Some(Series::new("".into(), Vec::<f64>::new())), // Empty list
            Some(Series::new("".into(), vec![100.0, 200.0])),
        ];
        
        let param1_lists = ListChunked::from_iter(empty_lists.clone()).into_series();
        let param2_lists = ListChunked::from_iter(empty_lists).into_series();
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: None };
        let result = {{function_name}}(&[param1_lists, param2_lists], &kwargs).unwrap();
        
        let list_ca = result.list().unwrap();
        
        // First row should be empty list
        if let Some(arr) = list_ca.get_as_series(0) {
            assert_eq!(arr.len(), 0);
        }
    }

    // ===== Error Condition Tests =====

    #[test]
    fn test_{{function_name}}_insufficient_parameters() {
        let param1 = create_float_series("param1", vec![100.0]);
        let kwargs = {{FunctionName}}Kwargs { optional_param: None };
        
        let result = {{function_name}}(&[param1], &kwargs);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("requires at least 2 parameters"));
    }

    #[test]
    fn test_{{function_name}}_invalid_optional_parameter() {
        let param1 = create_float_series("param1", vec![100.0]);
        let param2 = create_float_series("param2", vec![0.05]);
        
        let kwargs = {{FunctionName}}Kwargs {
            optional_param: Some(5),  // Out of range
        };
        
        let result = {{function_name}}(&[param1, param2], &kwargs);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("Must be 0-4"));
    }

    #[test]
    fn test_{{function_name}}_type_mismatch_in_lists() {
        let fields = vec![
            Field::new("param1".into(), DataType::List(Box::new(DataType::String))), // Wrong inner type
            Field::new("param2".into(), DataType::List(Box::new(DataType::Float64))),
        ];
        
        let result = {{function_name}}_output_type(&fields);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("must contain Float64 type"));
    }

    // ===== Excel Compatibility Tests =====
    
    #[cfg(test)]
    mod excel_verification {
        use super::*;
        
        #[test]
        fn test_excel_known_outputs() {
            // Test against actual Excel outputs
            // These values were verified in Excel 365
            
            struct ExcelTestCase {
                inputs: (f64, f64, i32),
                expected: f64,
                description: &'static str,
            }
            
            let test_cases = vec![
                ExcelTestCase {
                    inputs: (100.0, 0.05, 0),
                    expected: 5.0,
                    description: "Basic calculation",
                },
                ExcelTestCase {
                    inputs: (1000.0, 0.0825, 1),
                    expected: 82.5,
                    description: "Different basis",
                },
                // Add more verified Excel outputs
            ];
            
            for tc in test_cases {
                let result = calculate_{{function_name}}(tc.inputs.0, tc.inputs.1, tc.inputs.2);
                assert_relative_eq!(
                    result,
                    tc.expected,
                    epsilon = 1e-9,
                    "{}", tc.description
                );
            }
        }
        
        #[test]
        fn test_excel_dynamic_array_compatibility() {
            // Test Excel 365 dynamic array behavior
            // =FUNCTION($A$1, B1:B3) should broadcast A1 to each B value
            
            let scalar_param = create_float_series("param1", vec![100.0]); // A1
            let array_param = create_float_list_series(vec![
                vec![0.05, 0.10, 0.15], // B1:B3
            ]);
            
            let kwargs = {{FunctionName}}Kwargs { optional_param: Some(0) };
            let result = {{function_name}}(&[scalar_param, array_param], &kwargs).unwrap();
            
            // Result should be array matching Excel's spill behavior
            assert!(matches!(result.dtype(), DataType::List(_)));
        }
    }

    // ===== Property-Based Tests =====
    
    #[cfg(test)]
    mod property_tests {
        use super::*;
        use proptest::prelude::*;
        
        proptest! {
            #[test]
            fn property_{{function_name}}_list_preserves_length(
                values1 in prop::collection::vec(-1000.0..1000.0, 1..50),
                values2 in prop::collection::vec(-1000.0..1000.0, 1..50),
            ) {
                // If we have equal length lists, output should preserve length
                let len = values1.len().min(values2.len());
                let list1 = values1[..len].to_vec();
                let list2 = values2[..len].to_vec();
                
                let param1_lists = create_float_list_series(vec![list1.clone()]);
                let param2_lists = create_float_list_series(vec![list2.clone()]);
                
                let kwargs = {{FunctionName}}Kwargs { optional_param: Some(0) };
                let result = {{function_name}}(&[param1_lists, param2_lists], &kwargs);
                
                if let Ok(series) = result {
                    let list_ca = series.list().unwrap();
                    if let Some(arr) = list_ca.get_as_series(0) {
                        assert_eq!(arr.len(), len);
                    }
                }
            }
            
            #[test]
            fn property_{{function_name}}_broadcasting_consistency(
                scalar_val in -1000.0..1000.0,
                list_vals in prop::collection::vec(-1000.0..1000.0, 1..20),
            ) {
                // Broadcasting should produce same result regardless of how scalar is represented
                
                // Method 1: True scalar
                let scalar1 = create_float_series("scalar", vec![scalar_val]);
                let list1 = create_float_list_series(vec![list_vals.clone()]);
                
                // Method 2: Repeated scalar (DataFrame behavior)
                let scalar2 = create_float_series("scalar", vec![scalar_val, scalar_val]);
                let list2 = create_float_list_series(vec![list_vals.clone(), list_vals.clone()]);
                
                let kwargs = {{FunctionName}}Kwargs { optional_param: Some(0) };
                
                let result1 = {{function_name}}(&[scalar1, list1], &kwargs);
                let result2 = {{function_name}}(&[scalar2, list2], &kwargs);
                
                // Both should succeed and produce equivalent results
                assert_eq!(result1.is_ok(), result2.is_ok());
            }
        }
    }

    // ===== Performance Tests (Optional) =====
    
    #[test]
    #[ignore]  // Run with --ignored flag
    fn test_{{function_name}}_performance_scalars() {
        use std::time::Instant;
        
        // Create large dataset
        let size = 1_000_000;
        let param1 = create_float_series("param1", vec![100.0; size]);
        let param2 = create_float_series("param2", vec![0.05; size]);
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: None };
        
        let start = Instant::now();
        let result = {{function_name}}(&[param1, param2], &kwargs).unwrap();
        let duration = start.elapsed();
        
        println!("Processed {} scalar rows in {:?}", size, duration);
        assert_eq!(result.len(), size);
        
        // Ensure it completes in reasonable time
        assert!(duration.as_secs() < 5, "Function too slow for large datasets");
    }
    
    #[test]
    #[ignore]  // Run with --ignored flag
    fn test_{{function_name}}_performance_lists() {
        use std::time::Instant;
        
        // Create dataset with lists (actuarial projection pattern)
        let num_policies = 10_000;
        let projection_length = 120; // Monthly for 10 years
        
        let list_values: Vec<Vec<f64>> = (0..num_policies)
            .map(|_| vec![100.0; projection_length])
            .collect();
        
        let param1_lists = create_float_list_series(list_values.clone());
        let param2_lists = create_float_list_series(
            list_values.into_iter()
                .map(|_| vec![0.05; projection_length])
                .collect()
        );
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: None };
        
        let start = Instant::now();
        let result = {{function_name}}(&[param1_lists, param2_lists], &kwargs).unwrap();
        let duration = start.elapsed();
        
        println!(
            "Processed {} policies with {}-month projections in {:?}", 
            num_policies, projection_length, duration
        );
        
        assert_eq!(result.len(), num_policies);
    }
}

// Additional test modules for specific aspects

#[cfg(test)]
mod list_tests {
    use super::*;
    
    #[test]
    fn test_all_optional_values_with_lists() {
        // Test all valid optional parameter values with list inputs
        let list1_values = vec![vec![100.0, 200.0]];
        let list2_values = vec![vec![0.05, 0.10]];
        
        let param1_lists = create_float_list_series(list1_values);
        let param2_lists = create_float_list_series(list2_values);
        
        for opt_val in 0..=4 {
            let kwargs = {{FunctionName}}Kwargs { optional_param: Some(opt_val) };
            let result = {{function_name}}(&[param1_lists.clone(), param2_lists.clone()], &kwargs);
            
            assert!(result.is_ok(), "Failed with optional_param = {}", opt_val);
            
            // Verify results differ based on optional parameter
            let list_ca = result.unwrap().list().unwrap();
            if let Some(arr) = list_ca.get_as_series(0) {
                let values = arr.f64().unwrap();
                assert_eq!(values.len(), 2);
                
                // Verify calculation uses the optional parameter
                let expected0 = calculate_{{function_name}}(100.0, 0.05, opt_val);
                let expected1 = calculate_{{function_name}}(200.0, 0.10, opt_val);
                
                assert_relative_eq!(values.get(0).unwrap(), expected0, epsilon = 1e-10);
                assert_relative_eq!(values.get(1).unwrap(), expected1, epsilon = 1e-10);
            }
        }
    }
}

#[cfg(test)]
mod excel_list_compatibility_tests {
    use super::*;
    
    #[test]
    fn test_excel_actuarial_projection_pattern() {
        // Common actuarial pattern: fixed assumptions with varying projection dates
        let valuation_date = create_float_series("val_date", vec![0.0]); // Fixed
        
        // Monthly projection values for 10 years
        let projection_values: Vec<f64> = (1..=120).map(|month| month as f64).collect();
        let projections = create_float_list_series(vec![projection_values]);
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: Some(0) };
        let result = {{function_name}}(&[valuation_date, projections], &kwargs).unwrap();
        
        // Result should be list of 120 calculated values
        let list_ca = result.list().unwrap();
        if let Some(arr) = list_ca.get_as_series(0) {
            assert_eq!(arr.len(), 120);
        }
    }
}
```

## Test Categories Checklist

### 1. Calculation Function Tests
- [ ] Normal cases with typical values
- [ ] Edge cases (zero, negative, very large)
- [ ] All optional parameter values
- [ ] Known Excel outputs

### 2. Output Type Detection Tests  
- [ ] Scalar inputs → scalar output
- [ ] List inputs → list output
- [ ] Mixed inputs → list output (broadcasting)
- [ ] Invalid type combinations

### 3. Scalar Operation Tests
- [ ] Basic functionality
- [ ] Multiple rows
- [ ] Different input types
- [ ] Optional parameters

### 4. List Operation Tests
- [ ] List×List with same lengths
- [ ] List×List with different lengths
- [ ] Empty lists
- [ ] Single-element lists
- [ ] Large lists (120+ elements)

### 5. Broadcasting Tests
- [ ] Scalar×List broadcasting
- [ ] List×Scalar broadcasting
- [ ] DataFrame scalar behavior
- [ ] Consistency across representations

### 6. Null Handling
- [ ] Null in scalar parameters
- [ ] Null entire lists
- [ ] Nulls within lists
- [ ] Mixed null/non-null

### 7. Error Conditions
- [ ] Insufficient parameters
- [ ] Invalid parameter types
- [ ] Out of range values
- [ ] List length mismatches

### 8. Excel Compatibility
- [ ] Verified Excel outputs
- [ ] Dynamic array behavior
- [ ] Broadcasting matches Excel
- [ ] Edge case compatibility

### 9. Property-Based Tests
- [ ] List length preservation
- [ ] Broadcasting consistency
- [ ] Mathematical properties
- [ ] Null propagation rules

## Testing Tips

1. **Use yearfrac tests as reference**: Best patterns for list handling
2. **Test actuarial patterns**: 120-month projections, policy cohorts
3. **Verify Excel 365 behavior**: Dynamic arrays and spilling
4. **Document quirks**: Add comments explaining non-obvious behavior
5. **Performance matters**: Test with realistic data volumes

## Next Step

Verify the build and run quality checks in Step 7.