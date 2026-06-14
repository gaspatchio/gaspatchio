# Calculation Graph MVP Plan

## Overview

This MVP will enhance Gaspatchio's existing tracing infrastructure to build a dependency graph of calculations, enabling visualization, optimization, and debugging of actuarial models.

## Current State

Gaspatchio already has:
- **Operation Tracing**: Captures operations in `_computation_graph` during debug mode
- **Source Location**: Tracks file and line number for each operation
- **Type Inference**: Attempts to infer result types of expressions
- **Column Order Tracking**: Maintains order of column creation

What's missing:
- **Dependency Extraction**: No analysis of which columns an expression depends on
- **Graph Structure**: Operations stored as a list, not a proper directed graph
- **Variable Substitution**: No mapping between model point columns and variable names
- **Visualization**: No graph output or DAG representation

## MVP Goals

### Part 1: Variable Mapping & IDE Support (First Priority)
1. **Variable Mapping**: Support natural variable names (e.g., `issue_age = policyholder_issue_age + term_offset`)
2. **IDE Support**: Generate files for autocomplete and type hints
3. **Runtime Integration**: Seamless execution with mapped variables

### Part 2: Calculation Graph (Builds on Part 1)
1. **Extract Dependencies**: Analyze Polars expressions to identify column dependencies
2. **Build Dependency Graph**: Create a proper DAG structure from operations
3. **JSON Export**: Produce the JSON format specified in the plan for visualization

## Critical Design Issues Discovered During Implementation

### 1. Fundamental Assignment Semantics Problem

The most critical issue discovered is the fundamental difference in semantics between:
- `af["column"] = expr` - Creates or updates a column in the ActuarialFrame
- `variable = expr` - Creates a local Python variable

With natural syntax, we want `issue_age = policyholder_issue_age + term_offset` to behave like the first case (column creation), but Python's assignment operator cannot be overloaded, making this challenging.

#### The Problem
In the original design, the AST transformer only transforms assignments to variables that already exist in the mapping (from model points). This means:
```python
# This gets transformed correctly (policyholder_issue_age is a known column)
policyholder_issue_age = policyholder_issue_age + 10  # → af["Policyholder issue age"] = af["Policyholder issue age"] + 10

# This DOES NOT get transformed (term_offset is not in model points)
term_offset = (year - 26).clip(lower_bound=0)  # → remains as local variable!

# This fails because term_offset is just a local variable
issue_age = policyholder_issue_age + term_offset  # → ERROR: can't add ColumnProxy to int
```

This completely breaks the ability to create new computed columns using natural syntax, which defeats the purpose.

### 2. Two Implementation Approaches and Their Conflict

During implementation, we discovered two different approaches that conflict when used together:

#### Approach 1: AST Transformation
- Transform Python code at the AST level before execution
- Convert `variable = expr` to `af["variable"] = expr`
- Pros: True natural syntax without imports
- Cons: Complex logic needed to distinguish column assignments from local variables

#### Approach 2: VariableAccessor with Import
- Generate a module with VariableAccessor proxy objects
- Model imports these with `from model_vars import *`
- Pros: IDE support, simpler implementation
- Cons: Cannot handle assignment syntax naturally

**The Conflict**: When a model uses the import approach BUT the runner also applies AST transformation, it causes errors because the AST transformer tries to transform already-imported VariableAccessor objects.

### 3. Design Solutions for Assignment Problem

#### Option 1: Transform All Assignments (Recommended)
Transform ALL assignments to ActuarialFrame operations by default, with heuristics to identify local variables:
```python
# These would remain local variables (detected by heuristics)
valuation_date = datetime.date(2024, 12, 31)  # Literal assignment
mortality_factor = 1.0  # Numeric literal
table = load_mortality_table()  # Function call returning non-column

# These would become columns
term_offset = (year - 26).clip(lower_bound=0)  # Expression with column reference
issue_age = policyholder_issue_age + term_offset  # Column arithmetic
```

Heuristics for local variables:
- Assignments to literals (dates, numbers, strings)
- Assignments from imports or module attributes
- Function parameters and loop variables
- Variables that are never used in column expressions

#### Option 2: Explicit Column Declaration
Require explicit syntax to indicate column assignments:
```python
# Using type hints
term_offset: Column = (year - 26).clip(lower_bound=0)

# Using a decorator/marker
column.term_offset = (year - 26).clip(lower_bound=0)

# Using a special assignment operator (would need custom parser)
term_offset := (year - 26).clip(lower_bound=0)
```

#### Option 3: Hybrid Detection
Use multiple passes to determine variable types:
1. First pass: Identify all assignments
2. Second pass: Trace usage to determine if variables are used as columns
3. Transform only variables identified as columns

## Technical Approach

### Part 1: Variable Mapping (Implement First)

**Option B: Code Generation (Selected Approach)**

This approach generates Python code that creates wrapper properties for natural variable names, allowing static analysis and IDE support while maintaining compatibility with existing column names.

#### How it works:

1. **Analysis Phase**: Parse the model code to identify variable usage patterns
2. **Mapping Generation**: Create a mapping between natural names and actual column names
3. **Code Generation**: Generate a Python module with property definitions
4. **Runtime Integration**: Import generated code to enable natural variable access

#### Implementation Details:

**Step 1: Generate Mapping from Model Points**
```python
def generate_mapping_from_model_points(model_points_path: str) -> dict[str, str]:
    """Generate variable mapping from model points column names."""
    import polars as pl
    from python_varname.utils import nameof  # for validation
    import inflection  # or python-slugify
    
    # Read just the schema to get column names
    df = pl.scan_parquet(model_points_path)
    columns = df.collect_schema().names()
    
    # Create mapping from pythonic names to original names
    mapping = {}
    seen_names = set()
    
    for col in columns:
        # Option 1: Using inflection library
        var_name = inflection.underscore(col)  # Convert to snake_case
        var_name = inflection.parameterize(var_name, separator='_')  # Clean special chars
        
        # Option 2: Using python-slugify
        # from slugify import slugify
        # var_name = slugify(col, separator='_', lowercase=True)
        
        # Option 3: Using identifier-generator
        # from identifier import make_identifier
        # var_name = make_identifier(col)
        
        # Ensure it's a valid Python identifier
        if not var_name.isidentifier():
            # Handle edge cases like starting with digit
            if var_name[0].isdigit():
                var_name = f"col_{var_name}"
            # Remove any remaining invalid characters
            var_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in var_name)
        
        # Handle Python keywords
        import keyword
        if keyword.iskeyword(var_name):
            var_name = f"{var_name}_"
        
        # Handle duplicates
        original_name = var_name
        counter = 1
        while var_name in seen_names:
            var_name = f"{original_name}_{counter}"
            counter += 1
        
        seen_names.add(var_name)
        mapping[var_name] = col
    
    return mapping
```

**Step 2: Mapping Configuration**
```json
{
  "model_points_mapping": {
    "policyholder_issue_age": "Policyholder issue age",
    "policyholder_sex": "Policyholder sex",
    "policyholder_smoking_status": "Policyholder smoking status",
    "policy_cover_effective_date": "Policy Cover Effective date",
    "face_value": "Face Value",
    "annual_premium": "Annual Premium"
  },
  "computed_columns": [
    "term_offset",
    "issue_age",
    "age",
    "year",
    "premium_double"
  ]
}
```

**Step 3: AST Transformation Approach (Alternative to VariableAccessor)**

For models that don't use the import approach, we can transform the Python AST:

```python
class VariableTransformer(ast.NodeTransformer):
    \"\"\"Transform natural variable assignments into ActuarialFrame operations.\"\"\"
    
    def __init__(self, mapping: dict[str, str], af_name: str = \"af\"):
        self.mapping = mapping
        self.af_name = af_name
        self.variable_names = set(mapping.keys())
        self.assigned_vars = set()
        
    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        \"\"\"Transform variable assignments.\"\"\"
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var_name = node.targets[0].id
            
            # CRITICAL: Current implementation only transforms known variables
            # This is the fundamental flaw - new columns are not transformed!
            if var_name in self.variable_names:
                # Transform to af[\"column\"] = expr
                col_name = self.mapping.get(var_name, var_name)
                new_target = ast.Subscript(
                    value=ast.Name(id=self.af_name, ctx=ast.Load()),
                    slice=ast.Constant(value=col_name),
                    ctx=ast.Store()
                )
                # ... transform assignment
            
            # TODO: Need to handle ALL assignments, not just known columns
            # Options:
            # 1. Transform all assignments except those matching heuristics
            # 2. Track assigned variables and transform subsequent references
            # 3. Use type inference to determine column vs local variable
```

**Step 4: Code Generation for Natural Variables (VariableAccessor Approach)**
```python
def generate_variable_module(mapping: dict[str, str], af_name: str = "_af") -> str:
    """Generate Python module that exposes variables for import *."""
    code = f'''"""Auto-generated variable mappings for actuarial model."""
# This file is auto-generated. Do not edit manually.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from gaspatchio_core import ActuarialFrame
    from gaspatchio_core.column import ColumnProxy

# Global reference to ActuarialFrame instance
{af_name}: 'ActuarialFrame' = None

def _init_variables(af_instance: 'ActuarialFrame'):
    """Initialize the module with an ActuarialFrame instance."""
    global {af_name}
    {af_name} = af_instance

# Define __all__ for clean import *
__all__ = [
'''
    
    # Add all variable names to __all__
    all_vars = list(mapping.keys())
    for var in all_vars:
        code += f'    "{var}",\n'
    code += ']\n\n'
    
    # Generate variable access functions
    for var_name, col_name in mapping.items():
        code += f'''
def _get_{var_name}():
    """Get {var_name} (maps to '{col_name}')."""
    if {af_name} is None:
        raise RuntimeError("Variables not initialized. Call _init_variables first.")
    return {af_name}["{col_name}"]

def _set_{var_name}(value):
    """Set {var_name} (maps to '{col_name}')."""
    if {af_name} is None:
        raise RuntimeError("Variables not initialized. Call _init_variables first.")
    {af_name}["{col_name}"] = value

# Create module-level variable using property
class _ModuleProxy:
    @property
    def {var_name}(self):
        return _get_{var_name}()
    
    @{var_name}.setter
    def {var_name}(self, value):
        _set_{var_name}(value)

# Replace module with proxy to support variable access
import sys
_proxy = _ModuleProxy()
for attr in ["{var_name}"]:
    setattr(sys.modules[__name__], attr, getattr(_proxy, attr))
'''
    
    return code
```

**Alternative Simpler Approach - Direct Variable Injection**
```python
def inject_variables_into_namespace(af: ActuarialFrame, mapping: dict[str, str], namespace: dict):
    """Inject variable proxies directly into a namespace (e.g., globals())."""
    
    class VariableProxy:
        def __init__(self, af: ActuarialFrame, var_name: str, col_name: str):
            self._af = af
            self._var_name = var_name
            self._col_name = col_name
        
        def __repr__(self):
            return f"<Variable '{self._var_name}' -> '{self._col_name}'>"
        
        # Implement all operators to return column expressions
        def __add__(self, other):
            return self._af[self._col_name] + other
        
        def __radd__(self, other):
            return other + self._af[self._col_name]
        
        def __sub__(self, other):
            return self._af[self._col_name] - other
        
        # ... implement other operators ...
    
    # Inject each variable into the namespace
    for var_name, col_name in mapping.items():
        namespace[var_name] = VariableProxy(af, var_name, col_name)
```

**Step 4: Auto-generation Workflow**

Based on implementation experience, the auto-generation workflow should:

1. **File Naming Convention**: Use `<model_name>_vars.py` and `<model_name>_vars.pyi` to avoid conflicts
2. **Hash-based Change Detection**: Only regenerate when model points file changes
3. **Automatic Import Addition**: Add import statement to model file if not present
4. **Smart Import Detection**: Detect if model already has import to avoid conflicts

```python
def auto_generate_pyi_if_needed(model_path: Path, model_points_path: Path):
    """Auto-generate .pyi file with change detection."""
    # Check if regeneration needed using file hashes
    if not should_regenerate_pyi(model_path, model_points_path):
        return
    
    # Generate mapping and files
    mapping = generate_mapping_from_model_points(model_points_path)
    module_name = f"{model_path.stem}_vars"
    generate_ide_support_files(mapping, model_path.parent, module_name)
    
    # Add import to model if needed
    add_import_to_model(model_path, module_name)
    
    # Save hash cache for next time
    save_hash_cache(model_path, model_points_path)
```

**Step 5: Integration in Runner**
```python
# In gaspatchio_core/runner.py
def run_model_with_variables(config: ModelRunConfig) -> ModelRunResult:
    """Enhanced model runner that supports natural variable names."""
    
    # Auto-generate files if needed
    if config.enable_variables:
        auto_generate_pyi_if_needed(config.model_path, config.model_points_path)
    
    # Load model points to generate mapping
    model_points_path = config.directory / config.model_points_file
    mapping = generate_mapping_from_model_points(model_points_path)
    
    # Check if model already has import statement
    model_source = inspect.getsource(model_func)
    has_import = f"from {module_name} import" in model_source
    
    # Use different strategies based on import presence
    if has_import:
        # Model uses VariableAccessor approach - don't use AST transform
        wrapped_func = inject_variables(af, mapping, model_func, 
                                      use_ast_transform=False)
    else:
        # Model uses pure natural syntax - use AST transform
        wrapped_func = inject_variables(af, mapping, model_func, 
                                      use_ast_transform=True)
    
    # Continue with normal execution
    return dsl_run_model(wrapped_func, af)
```

**Step 6: Model Code Using Natural Variables**
```python
# models/example_model.py
from model_variables import *  # Import all generated variables

def main(af):
    # Direct variable access - no af["..."] needed!
    issue_age = policyholder_issue_age + term_offset
    age = issue_age + year - 1
    premium_double = age * 2
    
    # Variables automatically map to ActuarialFrame columns
    # This is equivalent to:
    # af["issue_age"] = af["Policyholder issue age"] + af["term_offset"]
```

**Step 7: IDE Support via Generated Files**

For static IDE support (autocomplete, type hints, go-to-definition), we MUST generate actual Python files:

```python
def generate_ide_support_files(mapping: dict[str, str], output_dir: Path):
    """Generate Python files for IDE support."""
    
    # Generate .py file with type annotations
    py_content = '''"""Auto-generated variable definitions for IDE support."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaspatchio_core.column import ColumnProxy

# Variable definitions with type hints
'''
    
    for var_name, col_name in mapping.items():
        py_content += f'{var_name}: "ColumnProxy"  # Maps to "{col_name}"\n'
    
    # Write the .py file
    (output_dir / "model_variables.py").write_text(py_content)
    
    # Generate .pyi stub file for even better IDE support
    pyi_content = '''"""Type stubs for model variables."""
from gaspatchio_core.column import ColumnProxy

'''
    
    for var_name, col_name in mapping.items():
        pyi_content += f'{var_name}: ColumnProxy\n'
    
    # Write the .pyi file
    (output_dir / "model_variables.pyi").write_text(pyi_content)
```

**Hybrid Approach: File Generation + Runtime Injection**

The MVP will use both approaches:

1. **Development time**: Generate `model_variables.py` and `.pyi` files
   - Full IDE support with autocomplete
   - Type checking works correctly
   - No squiggly lines for undefined variables

2. **Runtime**: Still inject variables dynamically
   - Ensures variables are connected to the correct ActuarialFrame
   - Handles cases where generated files might be out of date

```python
# CLI command to generate IDE support files
gspio generate-variables model-points.parquet --output-dir ./

# This creates:
# - model_variables.py (for imports)
# - model_variables.pyi (for better type hints)
```

**Example Generated Files for the example model**

`model_variables.py`:
```python
"""Auto-generated variable definitions for the example model."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaspatchio_core.column import ColumnProxy

# Variable definitions with type hints
policy_number: "ColumnProxy"  # Maps to "Policy number"
policyholder_issue_age: "ColumnProxy"  # Maps to "Policyholder issue age"
policyholder_sex: "ColumnProxy"  # Maps to "Policyholder sex"
policyholder_smoking_status: "ColumnProxy"  # Maps to "Policyholder smoking status"
underwriting_loadings: "ColumnProxy"  # Maps to "Underwriting loadings"
policy_cover_effective_date: "ColumnProxy"  # Maps to "Policy Cover Effective date"
face_value: "ColumnProxy"  # Maps to "Face Value"
annual_premium: "ColumnProxy"  # Maps to "Annual Premium"

# Runtime connection handled by injection
```

#### Advantages of Code Generation:

1. **Static Analysis**: IDEs can provide autocomplete and type hints
2. **Performance**: No runtime lookup overhead after initial generation
3. **Validation**: Can validate variable names at generation time
4. **Documentation**: Generated code includes docstrings
5. **Debugging**: Clear stack traces with actual property access

### Practical Implementation Lessons

#### File Path Handling
- Models should use relative paths for assets (e.g., `"assumptions/table.csv"`)
- Runner should handle path resolution based on model location
- Avoid hardcoding absolute paths in models

#### Import Statement Management
- Use AST parsing to safely add imports to existing models
- Place imports after existing imports or module docstrings
- Handle edge cases like models with no imports

#### Error Handling
- Provide clear error messages when natural syntax fails
- Distinguish between column access errors and variable reference errors
- Include suggestions for fixing common issues

#### Performance Considerations
- Cache generated files to avoid regeneration
- Use lazy loading for variable modules
- Minimize AST transformation overhead

### Part 2: Calculation Graph (After Variable Mapping)

#### 1. Dependency Extraction

Enhance `TracedOperation` to include dependencies:
```python
@dataclass
class TracedOperation:
    alias: str
    expression: pl.Expr
    metadata: SourceContext
    expected_dtype: pl.DataType | None = None
    dependencies: list[str] = field(default_factory=list)  # NEW
```

Create a dependency extractor that walks Polars expression trees:
```python
def extract_dependencies(expr: pl.Expr) -> list[str]:
    """Extract column names referenced in a Polars expression."""
    # Walk the expression tree to find col() references
    # Handle nested expressions, struct access, etc.
    # NOW USING MAPPED VARIABLE NAMES!
```

#### 2. Graph Building

Create a new module `gaspatchio_core/frame/calc_graph.py`:
```python
@dataclass
class GraphNode:
    id: str
    type: Literal["input", "computed"]
    label: str
    data: dict

@dataclass
class GraphEdge:
    source: str
    target: str

class CalculationGraph:
    def __init__(self):
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
    
    def add_operation(self, operation: TracedOperation):
        # Create node and edges from operation
        
    def to_json(self) -> dict:
        # Export to visualization format
```

### 4. Integration Points

Modify existing code:
1. **`append_operation_to_graph()`**: Extract dependencies when capturing operations
2. **`ActuarialFrame.__setitem__()`**: Support variable mapping during assignment
3. **`ActuarialFrame.__getitem__()`**: Support variable mapping during access
4. **Add new CLI command**: `gspio calc-graph` to generate graph JSON

## MVP Deliverables

### Part 1 Deliverables (Variable Mapping)
1. **IDE Support Files**: Generated .py and .pyi files for variable definitions
2. **Natural Variable Syntax**: Models can use `issue_age = policyholder_issue_age + term_offset`
3. **CLI Command**: `gspio generate-variables` to create IDE support files
4. **Runtime Integration**: Seamless execution with mapped variables

### Part 2 Deliverables (Calculation Graph)
1. **Enhanced Tracing**: Operations captured with dependency information using mapped names
2. **Graph Export**: JSON output matching the specified format with natural variable names
3. **CLI Command**: `gspio calc-graph` to generate visualization data
4. **Dependency Analysis**: Accurate tracking of variable relationships

## Example Usage

### Development Workflow

1. **Generate IDE support files** (one-time or when model points change):
```bash
# Generate model_variables.py and model_variables.pyi
gspio generate-variables model-points.parquet --output-dir ./
```

2. **Write model with natural variables**:
```python
# model.py
from model_variables import *  # IDE sees all variables!

def main(af: ActuarialFrame):
    # Full IDE support - autocomplete works!
    issue_age = policyholder_issue_age + term_offset
    age = issue_age + year - 1
    premium_double = age * 2
```

3. **Run model** (runtime injection ensures correct behavior):
```bash
# Run model with automatic variable mapping
gspio run-model model.py model-points.parquet --enable-variables

# Generate calculation graph
gspio calc-graph model.py model-points.parquet --output graph.json --enable-variables
```

### Integration Test Example: the example model

**Original Code** (`model_calculation_vars.py`):
```python
# Calculate ages
af["issue_age"] = af["Policyholder issue age"] + af["term_offset"]
af["age"] = af["issue_age"] + af["year"] - 1
af["age_mort_lookup"] = af["issue_age"] + (af["year"] - 26).clip(lower_bound=0)

# Calculate mortality rates
af["mortality_rates"] = 1 - (1 - af["monthly_CSO_table"]) ** (1 / 12)
```

**Natural Variable Syntax** (`model_calculation_natural.py`):
```python
from model_variables import *  # Import all variable mappings

# Calculate ages - natural syntax!
issue_age = policyholder_issue_age + term_offset
age = issue_age + year - 1
age_mort_lookup = issue_age + (year - 26).clip(lower_bound=0)

# Calculate mortality rates
mortality_rates = 1 - (1 - monthly_cso_table) ** (1 / 12)
```

## Implementation Phases

### Phase 1: Variable Mapping & IDE Support (First)
- Generate mapping from model points
- Create code generation framework
- Generate .py and .pyi files for IDE support
- Integrate with runner for runtime injection
- Test with the example model using natural variable names

### Phase 2: Dependency Extraction (Second)
- Implement expression tree walker
- Enhance TracedOperation with dependencies
- Update tracing to use mapped variable names
- Test with complex expressions

### Phase 3: Graph Building (Third)
- Implement CalculationGraph class
- Create JSON export functionality
- Add CLI command
- Ensure graph uses mapped variable names

### Phase 4: Testing & Refinement
- End-to-end test with the example model
- Handle edge cases (list operations, lookups)
- Performance optimization
- Documentation and examples

## Success Criteria

1. Can extract dependencies from all expression types in the example model
2. Variable mapping allows natural names like `issue_age = policyholder_issue_age + term_offset`
3. **Full IDE support**: Autocomplete, type hints, and go-to-definition work for all variables
4. Generated JSON matches specified format and can be visualized
5. No performance regression in normal execution mode
6. Generated files stay in sync with model points schema
7. **Critical**: Natural syntax must support creating NEW columns, not just referencing existing ones
8. **Critical**: Clear separation between local variables and column assignments

## Future Enhancements (Post-MVP)

- Topological sort for execution order optimization
- Circular dependency detection
- Interactive visualization tool
- Integration with debugging workflows
- Automatic variable name inference from expressions
- Domain-specific language (DSL) for actuarial models with custom operators
- Integration with Python type checkers (mypy, pyright) for better static analysis
- Custom assignment operator (e.g., `:=`) for explicit column creation