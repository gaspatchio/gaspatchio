# Step 6: Write Comprehensive Tests

Create thorough test coverage for the implemented function.

## Input
- Rust implementation from Step 5
- Behavior analysis from Step 3
- Test values from research
- Function name: `{{FUNCTION_NAME}}`

## Process

1. **Create test structure**:
   - Test calculation function directly
   - Test Polars interface
   - Test error conditions
   - Test Excel compatibility

2. **Use test values from research**:
   - HyperFormula test cases
   - Excel verified outputs
   - Edge cases discovered

3. **Follow testing patterns**:
   - Use approx for floating point
   - Test null propagation
   - Verify error messages

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/06-tests.rs` to append to the implementation:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;
    
    // Test categories:
    // 1. Calculation function tests
    // 2. Polars interface tests  
    // 3. Null handling tests
    // 4. Error condition tests
    // 5. Excel compatibility tests
}
```

## Complete Test Template

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
            .map(|d| (d - NaiveDate::from_ymd_opt(1899, 12, 30).unwrap()).num_days() as i32)
            .collect();
        Series::new(name.into(), days)
    }

    fn create_string_series(name: &str, values: Vec<&str>) -> Series {
        Series::new(name.into(), values)
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

    #[test]
    fn test_calculate_{{function_name}}_special_cases() {
        // Document any Excel-specific quirks
        // Example: Excel treats empty cells as 0
        let result = calculate_{{function_name}}(0.0, 0.0, 0);
        assert_eq!(result, 0.0, "Excel treats empty cells as 0");
    }

    // ===== Polars Interface Tests =====

    #[test]
    fn test_{{function_name}}_polars_basic() {
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

    #[test]
    fn test_{{function_name}}_with_dates() {
        // If function uses dates
        let start_dates = create_date_series(
            "start",
            vec![
                NaiveDate::from_ymd_opt(2012, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2013, 6, 15).unwrap(),
            ],
        );
        let end_dates = create_date_series(
            "end",
            vec![
                NaiveDate::from_ymd_opt(2012, 12, 31).unwrap(),
                NaiveDate::from_ymd_opt(2014, 6, 15).unwrap(),
            ],
        );
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: None };
        let result = {{function_name}}(&[start_dates, end_dates], &kwargs).unwrap();
        
        // Verify results
    }

    // ===== Null Handling Tests =====

    #[test]
    fn test_{{function_name}}_null_propagation() {
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
        fn test_excel_edge_case_compatibility() {
            // Test Excel-specific quirks
            // Example: How Excel handles the 1900 leap year bug
            // Example: Sign conventions for financial functions
            // Example: Rounding behavior
        }
    }

    // ===== Performance Tests (Optional) =====
    
    #[test]
    #[ignore]  // Run with --ignored flag
    fn test_{{function_name}}_performance() {
        use std::time::Instant;
        
        // Create large dataset
        let size = 1_000_000;
        let param1 = create_float_series("param1", vec![100.0; size]);
        let param2 = create_float_series("param2", vec![0.05; size]);
        
        let kwargs = {{FunctionName}}Kwargs { optional_param: None };
        
        let start = Instant::now();
        let result = {{function_name}}(&[param1, param2], &kwargs).unwrap();
        let duration = start.elapsed();
        
        println!("Processed {} rows in {:?}", size, duration);
        assert_eq!(result.len(), size);
        
        // Ensure it completes in reasonable time
        assert!(duration.as_secs() < 5, "Function too slow for large datasets");
    }
}
```

## Test Categories Checklist

### 1. Calculation Function Tests
- [ ] Normal cases with typical values
- [ ] Edge cases (zero, negative, very large)
- [ ] All optional parameter values
- [ ] Known Excel outputs

### 2. Polars Interface Tests
- [ ] Basic functionality
- [ ] Multiple rows
- [ ] Different input types
- [ ] Optional parameters

### 3. Null Handling
- [ ] Null in first parameter
- [ ] Null in second parameter
- [ ] Mixed null/non-null

### 4. Error Conditions
- [ ] Insufficient parameters
- [ ] Invalid parameter types
- [ ] Out of range values
- [ ] Division by zero (if applicable)

### 5. Excel Compatibility
- [ ] Verified Excel outputs
- [ ] Known quirks/bugs
- [ ] Edge case behavior
- [ ] Sign conventions

## Testing Tips

1. **Use HyperFormula tests**: Best source for comprehensive test values
2. **Verify in Excel**: Test edge cases in actual Excel
3. **Document quirks**: Add comments explaining non-obvious behavior
4. **Test both functions**: Both calculation and Polars interface
5. **Consider performance**: Add benchmarks for functions used at scale

## Next Step

Verify the build and run quality checks in Step 7.