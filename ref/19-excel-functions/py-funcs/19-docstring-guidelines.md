# Excel Function Docstring Guidelines for Actuaries

## Goal

1. When an actuary reads this documentation they'll understand how to use this function for their domain (life insurance)
2. They'll think "gosh this is absolutely the best documentation I've read"
3. An LLM using RAG, especially in the when_to_use admonition, will be able to use this documentation when an actuary types "I would like to $ACHIEVE_A_THING" where $ACHIEVE_A_THING is some operation on an actuarial model.

## Instructions

When you write a docstring you're aiming to educate an experienced life insurance actuary, so use dedicated domain specific examples.

As much as possible we want to use ActuarialFrame examples showing off our DSL, and not just polars examples.

You're also laying down the groundwork for an LLM to RAG this information, so we want to explain "When to use..."
again tying that back to when you're building an actuarial model you'd use this function to do what?

You can search the web for good domain examples if you want to.

The examples are going to get parsed into this object GaspatchioDocstring in @models.py so make sure that conform to that schema, pay special attention to `examples` and DocstringCodeExample which is where the lintable, executable examples are.

Your examples are going to be linted using ruff and executed so they must be self contained.

You need to provide a scalar and vector example if that makes sense in relation to the function.

## Guidelines and tips
- No need to mention " (List Shimming) " at all.
- Avoid using pl.col where we could reference by af[''] instead. BAD: pl.col("policy_id") GOOD: af["policy_id"]
- Don't bother explaining that it mirrors polars behavior
- Keep "When to use" highly practical and domain specific for actuaries.
- "When to use" can have 1-4 items, depending on how many actuarial use cases there are
- "When to use" - don't overly explain obvious cases like dates, strings.
- "When to use" - do go into detail when the function is financial in nature.
- "When to use" - doesn't need a preamble like "In actuarial data management..." or "Actuaries use `strip_suffix` when:...." or "In actuarial workflows, removing suffixes is useful for:..." just the heading then the list is fine.

## Excel Function Specific Considerations

### Financial Functions
For Excel financial functions (like YEARFRAC, PV, FV, PMT, etc.), focus on:
- **Premium Calculations**: How the function helps calculate policy premiums
- **Reserve Valuations**: Using for statutory and GAAP reserve calculations  
- **Cash Flow Projections**: Building actuarial models with projected cash flows
- **Interest Rate Sensitivity**: How the function handles different interest rate scenarios
- **Product Pricing**: Using the function for life insurance product development

### Date Functions  
For Excel date functions (like DATEDIF, EOMONTH, etc.), focus on:
- **Policy Duration**: Calculating exact policy duration for reserve calculations
- **Age Calculations**: Determining attained age for mortality rate lookups
- **Benefit Payment Timing**: When benefits become payable or mature
- **Valuation Date Calculations**: Moving between different valuation points

### Lookup Functions
For Excel lookup functions (like VLOOKUP, HLOOKUP, etc.), focus on:
- **Mortality Table Lookups**: Finding mortality rates by age and duration
- **Assumption Table Lookups**: Retrieving interest rates, lapse rates, expense rates
- **Product Feature Lookups**: Mapping policy features to calculation parameters
- **Commission Schedule Lookups**: Finding commission rates by product and duration

### Mathematical Functions
For Excel mathematical functions, focus on:
- **Statistical Analysis**: Portfolio risk metrics and experience analysis
- **Interpolation**: Smoothing between mortality table values or interest rate curves
- **Financial Calculations**: Net present value, internal rate of return on policies
- **Risk Calculations**: Standard deviation of claims, confidence intervals

## Example Template for Excel Functions

```python
def excel_function_name(
    self,
    param2: "IntoExprColumn", 
    optional_param: SomeType = default_value
) -> "ExpressionProxy":
    """Calculate [specific Excel function] using Excel's [FUNCTION_NAME] behavior.
    
    [Detailed explanation of what this Excel function does in actuarial context,
    including any important technical details about Excel compatibility or 
    specific calculation methods that actuaries should know about.]
    
    !!! note "When to use"
        *   **Premium Calculations**: [Specific use case for calculating premiums]
        *   **Reserve Valuations**: [How this helps with reserve calculations] 
        *   **Cash Flow Modeling**: [Application in actuarial projections]
        *   **[Other Use Case]**: [Additional actuarial application]
    
    Parameters
    ----------
    param2 : IntoExprColumn
        [Description in actuarial context - what this represents in insurance terms]
    optional_param : SomeType, optional
        [Description with actuarial meaning]. Defaults to [value].
        
    Returns
    -------
    ExpressionProxy
        [What this represents actuarially - be specific about the calculation result]
        
    Raises
    ------
    TypeError
        If the underlying proxy is not a ColumnProxy or ExpressionProxy.
    RuntimeError
        If the operation requires an ActuarialFrame context that is not available.
    ValueError
        If invalid parameters are provided to the Excel function.
        
    Examples
    --------
    **Scalar Example: [Single Policy Use Case]**::

        [Brief scenario description focused on a single policy calculation]

        ```python
        import datetime
        from gaspatchio_core import ActuarialFrame
        
        # [Realistic single policy data setup]
        af = ActuarialFrame({
            "policy_id": ["POL001"],
            "parameter1": [realistic_value],
            "parameter2": [realistic_value],
        })
        
        # [Clear example of the function usage]
        result = af.with_columns(
            af["parameter1"].excel.function_name(
                af["parameter2"], 
                optional_param=value
            ).alias("result_name")
        )
        print(result.collect())
        ```
        
        ```
        [Exact output from running the code above]
        ```

    **Vector Example: [Portfolio/Batch Use Case]**::

        [Brief scenario description focused on portfolio analysis]

        ```python
        import datetime
        from gaspatchio_core import ActuarialFrame
        
        # [Realistic portfolio data setup]
        af = ActuarialFrame({
            "policy_id": ["POL001", "POL002", "POL003"],
            "product_type": ["TERM", "WHOLE", "UL"],
            "parameter1": [value1, value2, value3],
            "parameter2": [value1, value2, value3],
        })
        
        # [Clear example showing batch processing]
        result = af.with_columns(
            af["parameter1"].excel.function_name(
                af["parameter2"]
            ).alias("calculated_result")
        )
        print(result.collect())
        ```
        
        ```
        [Exact output from running the code above]
        ```
    """
```

## Critical Requirements

1. **Excel Compatibility**: Always mention that the function follows Excel's behavior precisely
2. **Executable Examples**: All code examples MUST run without modification and produce the exact output shown
3. **Actuarial Context**: Every parameter and return value should be explained in insurance/actuarial terms
4. **Realistic Data**: Use realistic policy data, ages, premiums, and other actuarial values
5. **Domain-Specific Use Cases**: The "When to use" section should focus specifically on actuarial modeling scenarios

## Testing Your Docstrings

Before submitting, always:
1. Copy the exact code from your docstring examples into a Python file
2. Run the code to verify it produces the exact output shown
3. Run `ruff check` and `ruff format` on the code to ensure it passes linting
4. Verify that import statements are correct and minimal
5. Confirm that data values are realistic for life insurance context
6. Test that the function actually behaves as documented