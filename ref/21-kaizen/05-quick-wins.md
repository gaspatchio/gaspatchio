# Quick Wins: Immediate Rails-Style Improvements

This document identifies specific, implementable improvements that can be made to Gaspatchio immediately, requiring minimal architectural changes while providing maximum developer benefit.

## 1. Enhanced Error Messages

### Current Problem
```python
# Current error:
KeyError: 'mortality_rate'
```

### Quick Fix Implementation
```python
# In gaspatchio_core/errors/formatter.py, enhance format_error:

COMMON_ACTUARIAL_ERRORS = {
    'mortality_rate': {
        'aliases': ['qx', 'death_rate', 'mortality', 'mort_rate'],
        'suggestion': 'Add mortality rates using: af.apply_mortality("table_name") or af["mortality_rate"] = ...',
        'example': 'af = af.with_columns([mortality_table.lookup(age="age", sex="sex").alias("mortality_rate")])'
    },
    'lapse_rate': {
        'aliases': ['surrender_rate', 'withdrawal_rate', 'lapse'],
        'suggestion': 'Add lapse rates using: af.apply_lapses("table_name") or af["lapse_rate"] = ...',
        'example': 'af["lapse_rate"] = 0.05  # Fixed 5% lapse'
    }
}

def enhance_key_error(error: KeyError, af: ActuarialFrame) -> str:
    missing_key = str(error)
    
    # Check if it's a common actuarial column
    if missing_key in COMMON_ACTUARIAL_ERRORS:
        info = COMMON_ACTUARIAL_ERRORS[missing_key]
        available = [col for col in info['aliases'] if col in af.columns]
        
        message = f"\nMissing column: '{missing_key}'\n\n"
        
        if available:
            message += f"Did you mean one of these? {available}\n\n"
        
        message += f"Suggestion: {info['suggestion']}\n"
        message += f"Example:\n  {info['example']}\n"
        
        return message
    
    # Check for typos
    from difflib import get_close_matches
    similar = get_close_matches(missing_key, af.columns, n=3, cutoff=0.6)
    if similar:
        return f"\nColumn '{missing_key}' not found. Did you mean: {similar[0]}?"
    
    return f"\nColumn '{missing_key}' not found. Available columns: {list(af.columns)[:10]}..."
```

### Benefit
- Immediate help for users
- Reduces debugging time
- Teaches best practices

## 2. Column Name Auto-Detection

### Current Problem
```python
# Users must exactly match column names
mortality_table.lookup(age="Age", sex="Sex")  # Fails if columns are "age", "sex"
```

### Quick Fix Implementation
```python
# New file: gaspatchio_core/conventions/columns.py

STANDARD_COLUMNS = {
    'age': ['age', 'Age', 'AGE', 'issue_age', 'attained_age', 'current_age'],
    'sex': ['sex', 'Sex', 'SEX', 'gender', 'Gender', 'GENDER', 'M/F'],
    'smoking': ['smoking', 'Smoking', 'smoker', 'Smoker', 'smoking_status', 'NS/S'],
    'duration': ['duration', 'Duration', 'policy_year', 'policy_duration', 't'],
}

def detect_column(df: pl.DataFrame, concept: str) -> str | None:
    """Auto-detect standard actuarial columns"""
    if concept in df.columns:
        return concept
    
    for variant in STANDARD_COLUMNS.get(concept, []):
        if variant in df.columns:
            return variant
    
    return None

# Update Table class to use auto-detection
class Table:
    def lookup(self, **dimensions):
        # Auto-detect columns
        detected_dims = {}
        for key, value in dimensions.items():
            if isinstance(value, str):
                # Try to detect the column
                detected = detect_column(self.source, key)
                if detected:
                    detected_dims[detected] = value
                else:
                    detected_dims[key] = value
            else:
                detected_dims[key] = value
        
        return self._original_lookup(**detected_dims)
```

### Benefit
- Works with existing data
- No manual column mapping
- Reduces errors

## 3. Fluent Shortcuts

### Current Problem
```python
# Verbose present value calculation
af["pv_factor"] = (1 / (1 + 0.04)) ** af["t"]
af["pv_benefits"] = (af["benefit"] * af["pv_factor"]).sum()
```

### Quick Fix Implementation
```python
# Add to gaspatchio_core/frame/base.py

class ActuarialFrame:
    def pv(self, column: str, rate: float = 0.04) -> float:
        """Quick present value calculation"""
        if "t" not in self.columns:
            raise ValueError("Need 't' column for PV. Create with: af.add_time_column()")
        
        pv_factor = (1 / (1 + rate)) ** self["t"]
        return (self[column] * pv_factor).sum()
    
    def sum_product(self, *columns) -> float:
        """Sum of product of columns (common in actuarial calcs)"""
        result = self[columns[0]]
        for col in columns[1:]:
            result = result * self[col]
        return result.sum()
    
    def apply_decrements(self, **decrements) -> 'ActuarialFrame':
        """Apply multiple decrements and create standard columns"""
        af = self
        
        # Create individual probabilities
        for name, rate_col in decrements.items():
            af = af.with_columns([
                pl.col(rate_col).alias(f"prob_{name}")
            ])
        
        # Create survival probability
        survival = pl.lit(1.0)
        for name, rate_col in decrements.items():
            survival = survival * (1 - pl.col(rate_col))
        
        af = af.with_columns([
            survival.alias("prob_survival")
        ])
        
        return af
```

### Benefit
- Common calculations become one-liners
- Readable code
- Maintains performance

## 4. Smart Timeline Creation

### Current Problem
```python
# Too many parameters for simple monthly projection
af.date.create_projection_timeline(
    valuation_date=date(2024, 1, 1),
    projection_end_type="term_months", 
    projection_end_value=240,
    projection_frequency="monthly",
    output_column="projection_months",
    filter_after_term=True,
    create_t_column=True,
    t_column_name="t"
)
```

### Quick Fix Implementation
```python
# Add to gaspatchio_core/accessors/date.py

class DateAccessor:
    def project_monthly(self, months: int, from_date=None) -> ActuarialFrame:
        """Simplified monthly projection with smart defaults"""
        val_date = from_date or date.today()
        
        return self.create_projection_timeline(
            valuation_date=val_date,
            projection_end_type="term_months",
            projection_end_value=months,
            projection_frequency="monthly",
            output_column="date",  # Simple name
            filter_after_term=True,
            create_t_column=True,
            t_column_name="t"
        )
    
    def project_annual(self, years: int, from_date=None) -> ActuarialFrame:
        """Simplified annual projection"""
        val_date = from_date or date.today()
        
        return self.create_projection_timeline(
            valuation_date=val_date,
            projection_end_type="term_years",
            projection_end_value=years,
            projection_frequency="annual",
            output_column="date",
            filter_after_term=True,
            create_t_column=True,
            t_column_name="t"
        )
```

### Benefit
- 80% less code for common case
- Sensible defaults
- Still flexible when needed

## 5. Common Calculation Helpers

### Current Problem
```python
# Converting annual to monthly rates (very common)
af["monthly_rate"] = 1 - (1 - af["annual_rate"]) ** (1/12)
```

### Quick Fix Implementation
```python
# New file: gaspatchio_core/functions/actuarial.py

def annual_to_monthly(annual_rate):
    """Convert annual rate to monthly equivalent"""
    return 1 - (1 - annual_rate) ** (1/12)

def monthly_to_annual(monthly_rate):
    """Convert monthly rate to annual equivalent"""
    return 1 - (1 - monthly_rate) ** 12

def force_of_mortality(mortality_rate):
    """Convert mortality rate to force of mortality"""
    return -pl.log(1 - mortality_rate)

def survival_curve(mortality_rates):
    """Generate survival curve from mortality rates"""
    return (1 - mortality_rates).cumprod()

# Register as vector functions
from gaspatchio_core.functions import vector

vector.annual_to_monthly = annual_to_monthly
vector.monthly_to_annual = monthly_to_annual
vector.force_of_mortality = force_of_mortality
vector.survival_curve = survival_curve
```

### Benefit
- Common patterns become functions
- Self-documenting code
- Reduces errors

## 6. Model Template Generator

### Current Problem
- Starting from scratch every time
- No standard structure

### Quick Fix Implementation
```python
# Add to gaspatchio_core/cli.py

TERM_LIFE_TEMPLATE = '''"""
ABOUTME: Term life insurance model with monthly projections
ABOUTME: Calculates premiums, reserves, and death benefits
"""

from gaspatchio_core import ActuarialFrame
from datetime import date

class TermLifeModel:
    """Basic term life model"""
    
    def __init__(self, policies_df):
        self.af = ActuarialFrame(policies_df)
        self.valuation_date = date.today()
        
    def project(self, months=240):
        """Run projection"""
        # Create timeline
        self.af = self.af.date.project_monthly(months, self.valuation_date)
        
        # Add age progression
        self.af["current_age"] = self.af["issue_age"] + self.af["t"] / 12
        
        # Apply mortality (customize table name)
        self.af = self.af.with_mortality("2015-VBT")
        
        # Calculate death benefit
        self.af["death_benefit"] = self.af["face_amount"] * self.af["inforce"]
        
        # Add more calculations here
        
        return self.af

# Example usage
if __name__ == "__main__":
    import pandas as pd
    
    # Sample data
    policies = pd.DataFrame({
        "policy_id": [1, 2, 3],
        "issue_age": [35, 45, 55],
        "face_amount": [250000, 500000, 100000],
        "sex": ["M", "F", "M"],
        "smoking": ["NS", "NS", "SM"]
    })
    
    model = TermLifeModel(policies)
    results = model.project(months=240)
    print(results.head())
'''

@app.command()
def new_model(
    name: str = typer.Argument(..., help="Model name"),
    type: str = typer.Option("term_life", help="Model type")
):
    """Create a new model from template"""
    
    templates = {
        "term_life": TERM_LIFE_TEMPLATE,
        # Add more templates
    }
    
    if type not in templates:
        typer.echo(f"Unknown model type: {type}")
        raise typer.Exit(1)
    
    filename = f"{name}.py"
    with open(filename, "w") as f:
        f.write(templates[type])
    
    typer.echo(f"✨ Created {filename}")
    typer.echo(f"📝 Edit the model and customize for your needs")
    typer.echo(f"🚀 Run with: uv run {filename}")
```

### Benefit
- Quick start for new models
- Best practices built in
- Consistent structure

## 7. Assumption Table Registry

### Current Problem
```python
# Manual table registration
registry = Registry()
registry.register("mort", mortality_table)
registry.register("lapse", lapse_table)
# Easy to forget, typos in names
```

### Quick Fix Implementation
```python
# Update gaspatchio_core/assumptions/_api.py

class Registry:
    def auto_register(self, directory: str | Path):
        """Auto-register all CSV files in directory"""
        path = Path(directory)
        
        for csv_file in path.glob("*.csv"):
            table_name = csv_file.stem
            df = pl.read_csv(csv_file)
            
            # Auto-detect table type
            if any(col in df.columns for col in ['qx', 'mortality', 'death_rate']):
                table = MortalityTable.from_dataframe(df)
            elif any(col in df.columns for col in ['lapse', 'surrender', 'withdrawal']):
                table = LapseTable.from_dataframe(df)
            else:
                table = Table.from_dataframe(df)
            
            self.register(table_name, table)
            print(f"✓ Registered {table_name} from {csv_file.name}")
        
        return self

# Usage becomes:
registry = Registry().auto_register("./assumptions/")
```

### Benefit
- Zero configuration
- Automatic discovery
- Consistent naming

## Implementation Priority

1. **Enhanced Error Messages** (1 day)
   - Biggest impact on developer experience
   - Easy to implement

2. **Column Auto-Detection** (1 day)
   - Solves common frustration
   - Backward compatible

3. **Fluent Shortcuts** (2 days)
   - Makes common operations elegant
   - High visibility improvement

4. **Model Templates** (1 day)
   - Helps new users start quickly
   - Promotes best practices

5. **Common Calculations** (1 day)
   - Reduces repetitive code
   - Self-documenting

These quick wins can be implemented immediately without architectural changes, providing instant value while laying groundwork for larger Rails-inspired improvements.