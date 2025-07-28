# Step 9: Create Excel Accessor Method

## Input
- All analysis from Steps 1-8
- Function signature and behavior understanding
- Docstring requirements from guidelines

## Task
Create the Excel accessor method with comprehensive docstring.

### Pre-requisites
⚠️ **CRITICAL**: Read these files first:
- `ref/12-docstring-and-examples/12-docstring-README.md`
- `ref/19-excel-functions/py-funcs/19-docstring-guidelines.md`

### Actions
1. Add method to `ExcelColumnAccessor` class in `gaspatchio_core/accessors/excel.py`
2. Create comprehensive docstring with actuarial context
3. Include executable examples with exact output

## Output
The complete accessor method:

```python
def {{function_name}}(
    self, 
    param2: "IntoExprColumn", 
    optional_param: OptionalType = default_value
) -> "ExpressionProxy":
    """{{One-line description}} using Excel's {{FUNCTION_NAME}} behavior.
    
    {{Detailed explanation paragraph with actuarial context}}
    
    !!! note "When to use"
        *   **{{Use Case 1}}**: {{Specific actuarial scenario}}
        *   **{{Use Case 2}}**: {{How this helps with specific calculation}}
        *   **{{Use Case 3}}**: {{Application in projections/valuations}}
        *   **{{Use Case 4}}**: {{Additional actuarial application}}
    
    Parameters
    ----------
    param2 : IntoExprColumn
        {{Description in actuarial terms}}
    optional_param : OptionalType, optional
        {{Description with actuarial meaning}}. Defaults to {{default}}.
        
    Returns
    -------
    ExpressionProxy
        {{What this represents actuarially}}
        
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
    **Scalar Example: {{Single Policy Use Case}}**::

        {{Brief scenario description}}

        ```python
        {{Complete, executable example with imports}}
        ```
        
        ```
        {{EXACT output from execution}}
        ```

    **Vector Example: {{Portfolio Use Case}}**::

        {{Brief portfolio scenario}}

        ```python
        {{Complete, executable example with imports}}
        ```
        
        ```
        {{EXACT output from execution}}
        ```
    """
    # Implementation here
```

### Key Requirements
- Examples must be executable and produce shown output
- Use realistic actuarial data (policies, premiums, dates)
- Include 2-4 specific "When to use" cases
- All code must pass ruff linting

## Next Step
This output feeds into Step 10: Validate Docstring Examples