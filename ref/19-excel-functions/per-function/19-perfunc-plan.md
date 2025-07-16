You are a skilled software developer tasked with implementing an Excel function in Rust code, creating comprehensive tests, and documenting the process. 

# Goal    
Your goal is to create an accurate Rust implementation that matches the Excel function's behavior, including any quirks or limitations. You MUST match the Excel function's behavior EXACTLY.

**Note:** The templates below are general patterns. You'll need to adapt them based on:
- Number of required and optional parameters in the Excel function
- Data types (numeric, string, boolean, date)
- Return type (single value vs arrays)
- Whether the function can fail (needs error handling)

Here is the name of the Excel function you need to implement:

<function_name>
{{FUNCTION_NAME}}
</function_name>

# Steps

### Step 0: Study past learnings

Look at the file "ref/19-excel-functions/per-function/19-learnings.md" to see if there are any insights or tips for this function.


### Step 1: Break down the Excel documentation into key components:

Look at the Excel documentation for this function:
FUNCTION LIST: https://support.microsoft.com/en-us/office/excel-functions-alphabetical-b3944572-255d-4efb-bb96-c6d90033e188 

SPECIFIC FUNCTION: https://support.microsoft.com/en-us/office/yearfrac-function-3844141e-c76d-4143-82b6-208454ddc6a8


Break down the Excel documentation into key components:
   - Function purpose
   - Parameters
   - Return value
   - Special cases


### Step 2: Analyze the Excel function's behavior in different scenarios:
   - Normal use cases
   - Edge cases
   - Error conditions

**Research Sources (in order of priority):**
1. Microsoft Excel documentation (primary)
2. Excel help forums and StackOverflow for edge cases
3. Financial textbooks for formula verification
4. Other Excel-compatible software documentation
5. Financial calculator manuals for cross-verification

Search the web for any information you need to implement the function, especially regarding edge cases and special cases.

### Step 3: Make a plan for the implementation

- List potential Rust data types for each parameter and the return value.
- Brainstorm potential edge cases and error conditions that might need special handling.
- Outline a detailed step-by-step implementation plan for Rust.
- List potential challenges and quirks you might encounter during implementation.

Look through other implementations of functions in @src/excel/ to get a sense of how to implement this.

**Performance Considerations:**
- Define constants for frequently used magic numbers at the module level
- Create expensive objects (like epoch dates) once outside loops
- Consider using `#[inline]` for small helper functions
- Use iterator patterns with `collect::<Float64Chunked>()` for better Polars integration
- Add `#[allow(clippy::useless_conversion)]` if clippy complains about necessary `.into_iter()` calls on Polars types
- For functions used in actuarial projections, add basic benchmarks
- Test with large datasets (1M+ rows) if likely to be used at scale
- Profile memory usage for functions that process date ranges

**IMPORTANT: Two-Function Design Pattern for Polars Integration**

When implementing Excel functions for Polars, you MUST follow a two-function design pattern:

1. **Polars Interface Function**: This function MUST have the exact signature:
   ```rust
   pub fn function_name(inputs: &[Series], kwargs: &FunctionNameKwargs) -> PolarsResult<Series>
   ```
   This function should:
   - Extract Series from inputs array
   - Validate parameters
   - Handle type conversions (e.g., getting typed arrays like `.i64()?` or `.date()?`)
   - Loop through elements and call the calculation function
   - Wrap results back into a Series

2. **Pure Calculation Function**: This function takes Rust primitives and performs the actual calculation:
   ```rust
   fn calculate_function_name(param1: RustType1, param2: RustType2, ...) -> ReturnType
   ```
   This function should:
   - Take primitive Rust types (e.g., `NaiveDate`, `f64`, `i32`, `String`, `bool`)
   - Contain the pure implementation logic
   - Return primitive results (not wrapped in Result unless the function can fail)

**Return Type Guidelines for Calculation Functions:**
- Return `T` directly if the function cannot fail mathematically
- Return `PolarsResult<T>` only if Excel would return an error (#NUM!, #VALUE!, etc.)
- Use `Option<T>` for null propagation, not for error conditions

See `yearfrac.rs` for a good example of this pattern where `year_frac` handles the Polars interface and `calculate_year_frac` does the actual calculation.

### Step 4: Write the implementation

1. Define Kwargs Structure:
   First, define the kwargs structure for optional parameters:

   ```rust
   #[derive(Deserialize, Clone)]
   pub struct FunctionNameKwargs {
       pub optional_param: Option<Type>,
   }
   ```

   Note: If the function has no optional parameters, you can use an empty struct:
   ```rust
   #[derive(Deserialize, Clone)]
   pub struct FunctionNameKwargs {}
   ```

   For functions with multiple optional parameters, consider using Option<T> for each:
   ```rust
   #[derive(Deserialize, Clone)]
   pub struct FunctionNameKwargs {
       pub basis: Option<i32>,
       pub method: Option<String>,
   }
   ```

2. Polars Interface Function:
   Create the main function with the required Polars signature:

   ```rust
   /// Excel FUNCTION_NAME implementation for Polars
   /// 
   /// [Add Excel function description here]
   pub fn function_name(inputs: &[Series], kwargs: &FunctionNameKwargs) -> PolarsResult<Series> {
       // Validate input count if needed
       if inputs.len() < 2 {  // Adjust based on minimum required parameters
           return Err(PolarsError::ComputeError(
               "function_name requires at least 2 parameters".into()
           ));
       }
       
       // Extract input series based on function requirements
       let param1_series = &inputs[0];
       let param2_series = &inputs[1]; // Add more as needed
       
       // Extract typed arrays (use appropriate method for your data type)
       let param1_array = param1_series.type()?; // Examples: .i64()?, .f64()?, .date()?, .str()?, .bool()?
       let param2_array = param2_series.type()?; // Choose based on expected Excel parameter type
       
       // Process optional parameters
       let optional_value = kwargs.optional_param.unwrap_or(default_value);
       
       // Use iterator pattern for better performance and Polars integration
       #[allow(clippy::useless_conversion)]
       let result_ca = param1_array
           .into_iter()
           .zip(param2_array.into_iter())
           .map(|(p1_opt, p2_opt)| {
               match (p1_opt, p2_opt) {
                   (Some(p1), Some(p2)) => {
                       // Convert to appropriate types if needed (e.g., days to NaiveDate)
                       // Call calculation function
                       Some(calculate_function_name(p1, p2, optional_value))
                   }
                   _ => None, // Handle null inputs
               }
           })
           .collect::<Float64Chunked>(); // Adjust type based on return type
       
       Ok(result_ca.with_name("function_name".into()).into_series())
   }
   ```

3. Pure Calculation Function:
   Implement the core logic using Rust primitives:

   ```rust
   /// Calculate the actual function result
   fn calculate_function_name(
       param1: RustType1,
       param2: RustType2,
       optional_param: RustType3,
   ) -> ReturnType {
       // Pure implementation matching Excel behavior
       // Include comments for any Excel quirks or special cases
   }
   ```

   Include comments in your code to explain any special handling for Excel-specific behavior, known quirks, bugs, limitations, or edge cases.

**Error Handling Standards:**
- Use descriptive error messages that include parameter names
- Match Excel's error types where possible (#NUM!, #VALUE!, #DIV/0!)
- Include the invalid value in the error message when helpful
   
   For functions that can return negative values (like YEARFRAC when start > end), handle this explicitly:
   ```rust
   fn calculate_function_name(start: Type, end: Type) -> ReturnType {
       // Check if we need to return a negative value
       let is_negative = start > end;
       
       // Always calculate with normalized order
       let (normalized_start, normalized_end) = if start <= end {
           (start, end)
       } else {
           (end, start)
       };
       
       // Perform calculation
       let result = // ... calculation logic
       
       // Return negative if order was reversed
       if is_negative { -result } else { result }
   }
   ```

### Step 5: Write Comprehensive Tests:

**Excel Verification Strategy:**
- Copy-paste actual Excel formulas and results for test cases
- Test with Excel Online when possible for verification
- Use financial calculators as secondary verification sources
- Include edge cases Excel users commonly encounter
- Test with both positive and negative parameters where applicable
- Search the web at https://github.com/handsontable/hyperformula/blob/master/test/interpreter/function-{{FUNCTION_NAME}}.spec.ts for test cases and values to use in our tests. eg for YEARFRAC, search for
https://github.com/handsontable/hyperformula/blob/master/test/interpreter/function-yearfrac.spec.ts. Don't copy the tests, but use the inputs and expected outputs to create our tests.

**Required Test Categories:**
- Mathematical edge cases (zero, negative, infinity)
- Real-world financial scenarios (typical use cases)
- Excel compatibility verification (known Excel outputs)
- Performance stress tests (large datasets)
- Cross-function integration tests (when functions work together)

   Create test code with the following structure:

   ```rust
   #[cfg(test)]
   mod tests {
       use super::*;
       // Add imports based on what you need:
       // use approx::assert_relative_eq; // For floating point comparisons
       // use chrono::NaiveDate; // For date functions

       // Add helper functions if needed for your specific data types
       // Example for dates:
       // fn create_date_series(dates: Vec<NaiveDate>) -> Series { ... }
       // Example for strings:
       // fn create_string_series(values: Vec<&str>) -> Series { 
       //     Series::new("strings".into(), values)
       // }

       // Test the calculation function directly
       #[test]
       fn test_calculate_function_normal_case() {
           let result = calculate_function_name(param1, param2, optional);
           // Use appropriate assertion based on return type:
           // assert_eq!(result, expected_result); // For exact matches
           // assert_relative_eq!(result, expected_result, epsilon = 1e-10); // For floats
       }

       // Test the Polars interface
       #[test]
       fn test_function_polars_interface() {
           // Create input series appropriate for your function
           let param1_series = Series::new("param1".into(), vec![val1, val2]);
           let param2_series = Series::new("param2".into(), vec![val3, val4]);
           
           let kwargs = FunctionNameKwargs { optional_param: Some(value) };
           let result = function_name(&[param1_series, param2_series], &kwargs).unwrap();
           
           // Extract values based on return type:
           // let values = result.f64().unwrap(); // For float results
           // let values = result.i64().unwrap(); // For integer results  
           // let values = result.str().unwrap(); // For string results
           // let values = result.bool().unwrap(); // For boolean results
           
           // Assert based on type:
           // assert_eq!(values.get(0).unwrap(), expected1);
           // assert_relative_eq!(values.get(0).unwrap(), expected1, epsilon = 1e-10);
       }

       // Test null handling
       #[test]
       fn test_null_handling() {
           // Create series with null values - adjust types as needed
           // For numeric types:
           // let param1_series = Series::new("param1".into(), vec![Some(1.0), None, Some(3.0)]);
           // let param2_series = Series::new("param2".into(), vec![Some(2.0), Some(4.0), None]);
           
           // For string types:
           // let param1_series = Series::new("param1".into(), vec![Some("a"), None, Some("c")]);
           // let param2_series = Series::new("param2".into(), vec![Some("x"), Some("y"), None]);
           
           let kwargs = FunctionNameKwargs { optional_param: None };
           let result = function_name(&[param1_series, param2_series], &kwargs).unwrap();
           
           // Extract values based on return type
           // let values = result.type().unwrap(); // Replace 'type' with actual method
           
           // Verify null handling - when any input is null, output should be null
           // assert!(values.get(0).is_some()); // Both inputs present
           // assert!(values.get(1).is_none()); // First input null
           // assert!(values.get(2).is_none()); // Second input null
       }

       // Add more test functions as needed
       
       // For Excel compatibility, consider adding a separate test module:
       #[cfg(test)]
       mod excel_verification_tests {
           use super::*;
           
           // Test against known Excel outputs
           #[test]
           fn test_excel_known_values() {
               // Use actual values from Excel to verify compatibility
               // Document any quirks or non-standard behavior
           }
       }
   }
   ```

   Ensure your tests cover:
   - Both the calculation function and Polars interface
   - Normal use cases
   - Edge cases  
   - Known quirks or bugs
   - Null/None handling
   - Different input types (if applicable)
   - Error conditions

### Step 5.5: Verify Build and Basic Quality

1. Run `cargo fmt` to ensure consistent formatting
2. Run `cargo clippy --pedantic` to catch warnings and errors
3. Run `cargo test` but only for the function you are implementing.

### Step 6: Integration and Documentation

1. Update `src/excel/mod.rs` to export your new function
2. Add comprehensive doc comments following existing patterns
3. Mark function as complete in the tracking list

### Step 7: Update Learnings Document:
  Provide universal learnings to be added to the file "ref/19-excel-functions/per-function/19-learnings.md". 
   
   These should be generic insights that apply to ALL Excel function implementations, not function-specific notes. Format each learning as a single bullet point that captures one critical insight:

    - **Learning title**: Detailed explanation of a universal principle that applies to implementing any Excel function
    
   Focus on:
   - Universal patterns discovered during implementation
   - Generic Excel behaviors that affect all functions
   - Implementation techniques that apply broadly
   - Testing strategies that work across functions
   - Common pitfalls to avoid in any Excel function implementation

   Each bullet point should be a standalone learning that future implementers can apply to hundreds of different Excel functions.

   - If you don't have any learnings to add, it's ok to not add anything. 
   - You can modify / update existing learnings

