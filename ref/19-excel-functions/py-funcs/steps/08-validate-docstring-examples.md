# Step 8: Validate Docstring Examples

## Input
- Excel accessor method with docstring from Step 7
- Function implementation from previous steps
- Docstring recipe at `ref/recipes/write-docstring.md`

## Task
Write comprehensive, domain-focused docstrings following the recipe, then validate executable examples.

### Actions

#### 1. Review Docstring Recipe
Read the docstring recipe at `ref/recipes/write-docstring.md` which covers:
- Goal: Documentation for actuaries and LLM RAG
- Actuarial domain-specific examples
- "When to use" sections with actuarial use cases
- Scalar and vector example templates
- Style rules (attribute access, assignment style, no context managers)
- **CRITICAL**: Never guess expected output - always run code and copy exact output

#### 2. Fetch Excel Documentation
Use Step 01's Excel doc analysis approach to get the official Excel documentation:

```bash
# Fetch from Microsoft's official docs
# Example URL pattern: https://support.microsoft.com/en-us/office/{{function-name}}-function-...
```

Create YAML analysis following Step 01 format with:
- Function purpose
- Parameters (name, type, required/optional, accepts scalar/vector/both)
- Return value
- Special cases
- Use cases

#### 3. Write Docstring
Write docstring in the implementation file (`gaspatchio_core/accessors/excel_functions/{{function_name}}.py`) following the recipe pattern:

**Key Requirements:**
- **Short description** (one line)
- **Long description** (2-3 sentences explaining the function)
- **"When to use" admonition** with 4-6 actuarial use cases (detailed for financial functions, brief for obvious ones like dates)
- **Parameters section** with full descriptions
- **Returns section**
- **Scalar example** using ActuarialFrame with realistic insurance data
- **Vector example** (if applicable) showing list column usage

**Style Rules:**
- Default to attribute access: `af.column_name` (NOT `pl.col()` or `af["column_name"]`)
- Default to assignment: `af.new_col = af.old_col.method(...)`
- End with `print(af.collect())`
- ❌ NEVER use context managers (`with pl.Config(...):`), no indented code blocks
- For list operations, prefer vectorized list APIs or use the function directly with `list.eval()`

#### 4. Generate Expected Output

**CRITICAL STEP - DO NOT SKIP:**

```bash
# Run each example to get EXACT output
uv run python -c "
import datetime
from gaspatchio_core import ActuarialFrame

# Paste your example code here
data = {...}
af = ActuarialFrame(data)
af.result = af.column.excel.function(...)
print(af.collect())
"

# Copy the EXACT output including:
# - Column widths (Polars auto-sizes to content)
# - Table borders and spacing
# - All data formatting
# - Shape information
```

❌ **NEVER** guess column widths or use shortened output with `…` unless that's what actually prints
✅ **ALWAYS** run code and copy actual output character-for-character

#### 5. Validate Docstring Examples

Run the custom pytest validator that lints and executes docstring examples:

```bash
# Test the specific function file with example validation
TMPDIR=/tmp uv run pytest gaspatchio_core/accessors/excel_functions/{{function_name}}.py --gp-run-examples -s

# If there are errors:
# - Linting errors: Fix the code in the docstring
# - Output mismatch: Re-run the example and copy the EXACT output
# - Runtime errors: Fix the example code
```

The `--gp-run-examples` flag:
- Lints all docstring code examples with ruff
- Executes all examples in isolation
- Compares actual output to expected output
- Validates docstring structure requirements

#### 6. Fix Any Issues

Common issues and fixes:
- **Missing imports in examples**: Add `import polars as pl` if using `pl.element()` or `pl.lit()`
- **Output mismatch**: Re-run and copy exact output (don't guess!)
- **Linting errors**: Fix code style issues
- **Missing columns in output**: Update expected output to match actual (all columns show by default)
- **For list operations**: Import function directly and use with `list.eval()` if `.excel` accessor doesn't work inside list context

## Output
Save validation report to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/08-validation-report.yaml`

```yaml
function_name: {{FUNCTION_NAME}}
docstring_written: true
excel_docs_analyzed: true
when_to_use_cases: 6  # Number of actuarial use cases
scalar_example: pass/fail
vector_example: pass/fail  # N/A if not applicable
pytest_validation: pass/fail
linting_passes: true/false
exact_outputs_captured: true/false
issues_found:
  - "Issue description if any"
final_status: ready/needs_fixes
```

## Example Workflow

For a function like `DAYS`:

1. Read `ref/recipes/write-docstring.md`
2. Fetch Excel docs for DAYS function
3. Write docstring in `gaspatchio_core/accessors/excel_functions/days.py`:
   - Short description: "Calculate the number of days between two dates, similar to Excel's DAYS."
   - Long description explaining the function
   - "When to use" with 6 actuarial use cases
   - Parameters and returns sections
   - Scalar example: Policy duration calculation
   - Vector example: Monthly projection days using `list.eval()`
4. Run examples to get exact output
5. Run: `TMPDIR=/tmp uv run pytest gaspatchio_core/accessors/excel_functions/days.py --gp-run-examples -s`
6. Fix any issues and re-run until all tests pass

## Next Step
This output feeds into Step 9: Create Python Tests
