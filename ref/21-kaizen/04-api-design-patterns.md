# API Design Patterns: Rails-Inspired Patterns for Gaspatchio

## Overview

This document details specific API patterns inspired by Rails that can improve Gaspatchio's usability and developer experience. Each pattern includes rationale, implementation details, and concrete examples.

## 1. ActiveRecord Pattern for Actuarial Entities

### Pattern Description
Treat actuarial concepts (policies, assumptions, projections) as first-class objects with intelligent behavior, similar to Rails' ActiveRecord.

### Implementation

```python
# Rails-inspired base class for actuarial entities
class ActuarialRecord:
    """Base class providing Rails-like functionality"""
    
    # Class-level DSL for configuration
    @classmethod
    def validates(cls, field: str, **options):
        """Add validation rules"""
        cls._validations[field] = options
    
    @classmethod
    def has_many(cls, association: str, **options):
        """Define one-to-many relationships"""
        cls._associations[association] = HasManyAssociation(**options)
    
    @classmethod
    def belongs_to(cls, association: str, **options):
        """Define many-to-one relationships"""
        cls._associations[association] = BelongsToAssociation(**options)

# Example usage
class Policy(ActuarialRecord):
    validates :issue_age, presence=True, inclusion=(18, 80)
    validates :face_amount, presence=True, numericality={'greater_than': 0}
    
    has_many :claims
    has_many :premiums
    belongs_to :product
    
    # Rails-style scopes
    scope :active, lambda: where(status='active')
    scope :term, lambda: where(product_type='term')
    scope :recent, lambda: where(issue_date > date.today() - timedelta(days=90))
    
    # Callbacks
    before_save :calculate_modal_premium
    after_create :send_welcome_letter
```

### Benefits
- Familiar to Rails developers
- Encapsulates business logic
- Provides consistent interface

## 2. Query Interface Pattern

### Pattern Description
Provide a chainable query interface for filtering and transforming actuarial data, inspired by Rails' Arel.

### Implementation

```python
class ActuarialQuery:
    """Rails-style query builder for actuarial data"""
    
    def where(self, **conditions) -> 'ActuarialQuery':
        """Filter records"""
        return self._add_filter(conditions)
    
    def joins(self, *tables) -> 'ActuarialQuery':
        """Join with assumption tables"""
        return self._add_joins(tables)
    
    def select(self, *fields) -> 'ActuarialQuery':
        """Select specific fields"""
        return self._add_projection(fields)
    
    def group(self, *fields) -> 'ActuarialQuery':
        """Group by fields"""
        return self._add_grouping(fields)

# Example usage
results = (Policy
    .active()  # Named scope
    .where(issue_age__gte=25, issue_age__lte=65)
    .joins(:mortality_table, :lapse_table)
    .select(:policy_id, :premium, :death_benefit)
    .calculate_reserves()
)

# Complex queries with Rails-style syntax
high_risk = (Policy
    .where(smoking_status='smoker')
    .where(face_amount__gt=1_000_000)
    .joins(:underwriting)
    .merge(Underwriting.substandard())
)
```

### Benefits
- Intuitive query building
- Lazy evaluation
- Composable queries

## 3. Migration Pattern for Assumptions

### Pattern Description
Version and manage assumption table changes using Rails-style migrations.

### Implementation

```python
class AssumptionMigration:
    """Base class for assumption migrations"""
    
    def up(self):
        """Apply the migration"""
        raise NotImplementedError
    
    def down(self):
        """Rollback the migration"""
        raise NotImplementedError
    
    def change(self):
        """Reversible migration (preferred)"""
        pass

# Example migration
class AddCovid19MortalityAdjustment(AssumptionMigration):
    """Add COVID-19 mortality adjustments to base tables"""
    
    def change(self):
        # Add new column
        add_column :mortality_2015_vbt, :covid_adjustment, :float, default=1.0
        
        # Update specific ages/years
        update :mortality_2015_vbt do |t|
            t.where(age__gte=65, year__in=[2020, 2021])
             .set(covid_adjustment=1.15)
        end
        
        # Create new derived table
        create_assumption :mortality_covid_adjusted do |t|
            t.base_table = :mortality_2015_vbt
            t.calculation = "base_rate * covid_adjustment"
        end

# Migration runner
class MigrationRunner:
    def run_pending_migrations(self):
        """Run all pending migrations in order"""
        
    def rollback(self, steps=1):
        """Rollback migrations"""
        
    def status(self):
        """Show migration status"""
```

### Benefits
- Traceable assumption changes
- Team coordination
- Regulatory compliance

## 4. Convention-Based Routing Pattern

### Pattern Description
Automatically route calculations based on naming conventions, similar to Rails' routing.

### Implementation

```python
class CalculationRouter:
    """Routes calculations based on conventions"""
    
    # Convention: calculate_[output]_from_[inputs]
    def route_calculation(self, method_name: str):
        match = re.match(r'calculate_(\w+)_from_(\w+)', method_name)
        if match:
            output, inputs = match.groups()
            return self.auto_calculate(output, inputs.split('_and_'))

# Example usage
class ReserveCalculator:
    # These methods are auto-discovered and routed
    def calculate_reserve_from_cashflows(self, cashflows):
        """Convention: automatically called for reserve calculations"""
        return cashflows.pv(interest=self.valuation_rate)
    
    def calculate_premium_from_benefits_and_expenses(self, benefits, expenses):
        """Convention: multiple inputs supported"""
        return (benefits + expenses) / self.annuity_factor()

# Auto-routing in action
calc = ReserveCalculator()
reserve = calc.calculate('reserve')  # Automatically finds and calls the right method
```

### Benefits
- Reduces configuration
- Self-documenting code
- Enables metaprogramming

## 5. Concern Pattern for Shared Behavior

### Pattern Description
Use Rails-style concerns to share behavior across actuarial models.

### Implementation

```python
class Concern:
    """Base class for actuarial concerns"""
    
    @classmethod
    def included(cls, base):
        """Called when concern is included"""
        base.extend(cls.ClassMethods)
        if hasattr(cls, 'InstanceMethods'):
            base.include(cls.InstanceMethods)

# Example concerns
class Mortalizable(Concern):
    """Concern for models that use mortality"""
    
    class ClassMethods:
        def mortality_table(self, table_name):
            self._mortality_table = table_name
    
    def apply_mortality(self):
        self.af = self.af.with_mortality(self._mortality_table)
    
    def survival_probability(self, from_time, to_time):
        return self.af.survival_prob(from_time, to_time)

class Projectable(Concern):
    """Concern for projectable models"""
    
    def project_monthly(self, months):
        self.af = self.af.create_monthly_timeline(months)
        return self
    
    def project_annually(self, years):
        self.af = self.af.create_annual_timeline(years)
        return self

# Usage
class TermLifeModel(ActuarialModel):
    include Mortalizable
    include Projectable
    
    mortality_table "2015-VBT"
```

### Benefits
- DRY principle
- Modular functionality
- Easy testing

## 6. Helper Pattern for Complex Calculations

### Pattern Description
Provide Rails-style helpers for complex actuarial calculations.

### Implementation

```python
# Actuarial helpers module
class ActuarialHelpers:
    """Rails-style view helpers for calculations"""
    
    @helper
    def format_rate(rate: float, decimals: int = 4) -> str:
        """Format rate as percentage"""
        return f"{rate * 100:.{decimals}f}%"
    
    @helper
    def age_last_birthday(birth_date: date, as_of: date) -> int:
        """Calculate age last birthday"""
        return (as_of - birth_date).days // 365
    
    @helper 
    def mortality_improvement(base_rate: float, years: int, 
                            improvement_rate: float = 0.01) -> float:
        """Apply mortality improvement"""
        return base_rate * (1 - improvement_rate) ** years
    
    @helper
    def annuity_certain(rate: float, periods: int) -> float:
        """Calculate annuity certain factor"""
        if rate == 0:
            return periods
        return (1 - (1 + rate) ** -periods) / rate

# Auto-included in models
class ActuarialModel:
    include ActuarialHelpers
    
    def calculate_premium(self):
        # Helpers available as methods
        age = self.age_last_birthday(self.birth_date, self.valuation_date)
        improved_mortality = self.mortality_improvement(
            self.base_mortality_rate, 
            years_since_table=5
        )
```

### Benefits
- Reusable calculations
- Consistent formatting
- Tested helpers

## 7. Configuration Pattern

### Pattern Description
Rails-style configuration for actuarial settings.

### Implementation

```python
class GaspatchioConfig:
    """Rails-style configuration"""
    
    class Config:
        # Default settings
        default_interest_rate = 0.04
        default_mortality_table = "2015-VBT"
        projection_frequency = "monthly"
        
        # Environments
        class Development:
            debug_mode = True
            max_projection_months = 120
            cache_assumptions = False
        
        class Test:
            debug_mode = True
            max_projection_months = 12
            use_mock_tables = True
        
        class Production:
            debug_mode = False
            max_projection_months = 1200
            cache_assumptions = True
    
    @classmethod
    def configure(cls):
        """Rails-style configuration block"""
        yield cls.Config

# Usage
Gaspatchio.configure do |config|
    config.default_interest_rate = 0.045
    config.default_mortality_table = "2017-CSO"
    
    config.production.cache_assumptions = True
    config.production.parallel_execution = True
end
```

### Benefits
- Environment-specific settings
- Clean configuration
- Easy overrides

## 8. Generator Pattern

### Pattern Description
Rails-style generators for common actuarial artifacts.

### Implementation

```python
class ActuarialGenerator:
    """Base class for generators"""
    
    def generate(self, name: str, **options):
        """Generate the artifact"""
        self.create_directories()
        self.generate_files(name, options)
        self.update_registry()

# Example generators
class ModelGenerator(ActuarialGenerator):
    """Generate a new actuarial model"""
    
    template = """
class {name}Model(ActuarialModel):
    product_type = "{product_type}"
    
    validates :issue_age, presence=True
    has_assumption :mortality, table="{mortality_table}"
    
    def calculate(self):
        # TODO: Implement calculations
        pass
"""

class AssumptionGenerator(ActuarialGenerator):
    """Generate assumption table structure"""
    
    def generate(self, name: str, dimensions: list):
        # Generate CSV template with specified dimensions
        pass

# CLI usage
$ gspio generate model TermLife --mortality=2015-VBT
$ gspio generate assumption lapse --dimensions=age,duration,product
$ gspio generate report valuation --format=pdf
```

### Benefits
- Consistent structure
- Quick scaffolding
- Best practices built-in

## 9. Callback Pattern

### Pattern Description
Rails-style callbacks for actuarial calculations.

### Implementation

```python
class CallbackChain:
    """Manages callback execution"""
    
    def __init__(self):
        self.callbacks = defaultdict(list)
    
    def register(self, event: str, callback: Callable, options=None):
        """Register a callback"""
        self.callbacks[event].append((callback, options))
    
    def run(self, event: str, context):
        """Run callbacks for an event"""
        for callback, options in self.callbacks[event]:
            if self._should_run(callback, options, context):
                callback(context)

# Example usage in models
class PolicyProjection(ActuarialModel):
    # Define callbacks
    before_projection :validate_data
    after_mortality :apply_mortality_improvement
    around_reserves :log_reserve_calculation
    
    def validate_data(self):
        """Called before projection starts"""
        assert self.af['issue_age'].min() >= 0
        assert self.af['face_amount'].min() > 0
    
    def apply_mortality_improvement(self):
        """Called after mortality rates applied"""
        years_improvement = date.today().year - 2015
        self.af['mortality_rate'] *= (0.99 ** years_improvement)
    
    def log_reserve_calculation(self):
        """Wraps reserve calculation"""
        start = time.time()
        yield  # Run the calculation
        duration = time.time() - start
        logger.info(f"Reserve calculation took {duration:.2f}s")
```

### Benefits
- Separation of concerns
- Extensibility
- Clean logging/monitoring

## 10. Instrumentation Pattern

### Pattern Description
Rails-style instrumentation for performance monitoring.

### Implementation

```python
class ActuarialInstrumentation:
    """Rails-style instrumentation"""
    
    def instrument(self, name: str, **payload):
        """Instrument a block of code"""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            self.notify(name, duration=duration, **payload)
    
    def subscribe(self, pattern: str, callback: Callable):
        """Subscribe to instrumentation events"""
        self.subscribers[pattern].append(callback)

# Usage in framework
class ActuarialFrame:
    def calculate(self):
        with instrument("actuarial.calculation", model=self.name):
            # Calculation code
            pass

# Monitoring subscriber
def log_slow_calculations(event):
    if event.duration > 1.0:
        logger.warning(f"Slow calculation: {event.model} took {event.duration}s")

ActuarialInstrumentation.subscribe("actuarial.calculation", log_slow_calculations)
```

### Benefits
- Performance visibility
- Easy debugging
- Production monitoring

## Summary

These Rails-inspired patterns provide:

1. **Familiar APIs**: Developers with Rails experience will feel at home
2. **Reduced Boilerplate**: Conventions eliminate repetitive code
3. **Better Organization**: Clear patterns for structuring code
4. **Enhanced Testability**: Patterns designed with testing in mind
5. **Progressive Complexity**: Simple things are simple, complex things are possible

The key is adapting Rails patterns to actuarial domain needs while maintaining Gaspatchio's performance advantages. These patterns create a framework that is both powerful for experts and approachable for beginners.