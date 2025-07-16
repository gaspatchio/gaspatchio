You are a skilled software developer tasked with implementing an Excel function in Rust code, creating comprehensive tests, and documenting the process. Your goal is to create an accurate Rust implementation that matches the Excel function's behavior, including any quirks or limitations.

Here is the Excel documentation for this function:

<excel_documentation>
{{EXCEL_DOCUMENTATION}}
</excel_documentation>

Here is the name of the Excel function you need to implement:

<function_name>
{{FUNCTION_NAME}}
</function_name>

**Note:** The templates below are general patterns. You'll need to adapt them based on:
- Number of required and optional parameters in the Excel function
- Data types (numeric, string, boolean, date)
- Return type (single value vs arrays)
- Whether the function can fail (needs error handling)

Before providing your final output, wrap your implementation planning inside <implementation_planning> tags in your thinking block. In this section:

### Step 1: Break down the Excel documentation into key components:
   - Function purpose
   - Parameters
   - Return value
   - Special cases


### Step 2: Analyze the Excel function's behavior in different scenarios:
   - Normal use cases
   - Edge cases
   - Error conditions

### Step 3: Make a plan for the implementation

- List potential Rust data types for each parameter and the return value.
- Brainstorm potential edge cases and error conditions that might need special handling.
- Outline a detailed step-by-step implementation plan for Rust.
- List potential challenges and quirks you might encounter during implementation.

Look through other implementations of functions in @src/excel/ to get a sense of how to implement this.

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
   fn calculate_function_name(param1: RustType1, param2: RustType2, ...) -> PolarsResult<ReturnType>
   ```
   This function should:
   - Take primitive Rust types (e.g., `NaiveDate`, `f64`, `i32`, `String`, `bool`)
   - Contain the pure implementation logic
   - Return primitive results (not wrapped in Result unless the function can fail)

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
       
       // Calculate results for each row
       let mut results = Vec::with_capacity(param1_array.len());
       
       for idx in 0..param1_array.len() {
           let param1_opt = param1_array.get(idx);
           let param2_opt = param2_array.get(idx);
           
           match (param1_opt, param2_opt) {
               (Some(param1), Some(param2)) => {
                   // Convert to appropriate types if needed (e.g., days to NaiveDate)
                   // Call calculation function - add ? if it returns Result
                   let result = calculate_function_name(param1, param2, optional_value);
                   results.push(Some(result));
               }
               _ => results.push(None), // Handle null inputs
           }
       }
       
       Ok(Series::new("function_name".into(), results))
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

4. Write Comprehensive Tests:
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

5. Update Learnings Document:
   Provide content to be added to the file "ref/19-excel-functions/per-function/19-learnings.md" using this format:

   ```markdown
   ## function_name

   - Insight 1
   - Insight 2
   - Tip for future implementations
   ```

   Include information on:
   - Challenges faced during implementation
   - Unexpected behavior of the Excel function
   - Useful resources or documentation
   - Tips for handling similar functions in the future

Please format each section of your output clearly, using appropriate code blocks and markdown formatting. Your final output should consist only of these four sections and should not duplicate or rehash any of the work you did in the implementation planning section.