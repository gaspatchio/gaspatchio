# Implementation Roadmap: Rails-Style Enhancements for Gaspatchio

## Overview

This roadmap outlines a phased approach to implementing Rails-inspired improvements in Gaspatchio. Each phase builds on the previous one, allowing for incremental delivery of value while maintaining backward compatibility.

## Phase 1: Foundation (Months 1-2)
*"Convention Over Configuration Infrastructure"*

### Goals
- Establish convention detection framework
- Improve error messages
- Create auto-configuration system

### Deliverables

#### 1.1 Convention Registry System
```python
# New module: gaspatchio_core/conventions/registry.py
class ConventionRegistry:
    """Central registry for actuarial conventions"""
    
    def register_column_aliases(self, concept: str, aliases: list[str]):
        """Register common column name variations"""
        # e.g., "age" -> ["age", "Age", "issue_age", "attained_age"]
    
    def detect_columns(self, af: ActuarialFrame) -> dict[str, str]:
        """Auto-detect actuarial columns in a frame"""
```

#### 1.2 Enhanced Error System
```python
# Enhance: gaspatchio_core/errors/formatter.py
class ActuarialErrorFormatter:
    def format_with_suggestions(self, error: Exception) -> str:
        """Add Rails-style helpful suggestions to errors"""
```

#### 1.3 Smart Table Detection
```python
# New module: gaspatchio_core/assumptions/auto_detect.py
class TableAutoDetector:
    def detect_table_type(self, df: pl.DataFrame) -> TableType:
        """Detect if table is mortality, lapse, expense, etc."""
    
    def detect_dimensions(self, df: pl.DataFrame) -> dict:
        """Auto-detect select/ultimate, age bands, etc."""
```

### Migration Impact
- Fully backward compatible
- Opt-in conveniences

## Phase 2: Developer Experience (Months 2-3)
*"Actuarial Happiness"*

### Goals
- Implement DSL shortcuts
- Add fluent interfaces
- Create model templates

### Deliverables

#### 2.1 Actuarial Shortcuts
```python
# New module: gaspatchio_core/shortcuts.py
class ActuarialShortcuts:
    """Rails-style shortcuts for common patterns"""
    
    def pv_benefits(self, benefit_col: str, **kwargs):
        """Simple PV calculation with smart defaults"""
    
    def apply_decrements(self, **decrements):
        """Generate standard decrement chain"""
    
    def add_policy_dates(self):
        """Add standard date calculations"""
```

#### 2.2 Fluent Interface Enhancements
```python
# Enhance: gaspatchio_core/frame/base.py
class ActuarialFrame:
    def with_mortality(self, table_name: str) -> 'ActuarialFrame':
        """Fluent mortality application"""
        
    def project_monthly(self, months: int, from_date=None) -> 'ActuarialFrame':
        """Simplified projection setup"""
```

#### 2.3 Model Templates
```python
# New module: gaspatchio_core/templates/
class TermLifeTemplate(ModelTemplate):
    """Pre-configured term life model"""
    
    product_type = "term_life"
    default_assumptions = {
        "mortality": "2015-VBT",
        "lapse": "SOA-2019-Term"
    }
```

### Migration Impact
- New APIs are additive
- Existing code continues to work

## Phase 3: Smart Defaults (Months 3-4)
*"It Just Works"*

### Goals
- Implement intelligent defaults
- Add assumption auto-loading
- Create project scaffolding

### Deliverables

#### 3.1 Intelligent Defaults System
```python
# New module: gaspatchio_core/defaults/
class DefaultsProvider:
    def get_defaults_for_product(self, product_type: str) -> dict:
        """Get sensible defaults by product type"""
    
    def infer_product_type(self, data: pl.DataFrame) -> str:
        """Guess product type from data"""
```

#### 3.2 Assumption Auto-Loading
```python
# New module: gaspatchio_core/assumptions/auto_loader.py
class AssumptionAutoLoader:
    def load_from_directory(self, path: Path) -> Registry:
        """Auto-load all assumptions from standard structure"""
    
    def download_standard_tables(self, tables: list[str]):
        """Download SOA/regulatory tables on demand"""
```

#### 3.3 Project Generator
```bash
# New CLI command
$ gspio new term_life my_model
Creating new term life model in my_model/
  ✓ Generated model.py
  ✓ Created assumptions/
  ✓ Added example data
  ✓ Created tests/
```

### Migration Impact
- Opt-in via new project structure
- Gradual adoption possible

## Phase 4: Advanced Patterns (Months 4-5)
*"Power When You Need It"*

### Goals
- Add declarative model syntax
- Implement lifecycle callbacks
- Create validation framework

### Deliverables

#### 4.1 Declarative Models
```python
# New module: gaspatchio_core/models/declarative.py
class DeclarativeModel:
    """Rails-style declarative model definition"""
    
    @classmethod
    def validates(cls, field: str, **validations):
        """Add field validations"""
    
    @classmethod
    def calculate(cls, name: str, func: Callable):
        """Define named calculations"""
```

#### 4.2 Lifecycle Callbacks
```python
# New module: gaspatchio_core/models/callbacks.py
class CallbackMixin:
    """Rails-style callbacks for models"""
    
    before_projection = []
    after_mortality = []
    before_save = []
```

#### 4.3 Business Rule Validations
```python
# New module: gaspatchio_core/validations/
class ValidationRunner:
    """Run business rule validations"""
    
    def validate_regulations(self, model, jurisdiction: str):
        """Check regulatory compliance"""
```

### Migration Impact
- New optional base classes
- Mixins for gradual adoption

## Phase 5: Ecosystem Integration (Months 5-6)
*"Big Tent Actuarial"*

### Goals
- Standard model sharing format
- Plugin architecture
- Community conventions

### Deliverables

#### 5.1 Model Package Format
```yaml
# gaspatchio.yaml - model package manifest
name: term_life_model
version: 1.0.0
author: Actuary Name
dependencies:
  - gaspatchio>=2.0
  - mortality_tables>=2023.1
assumptions:
  - SOA-2015-VBT
  - NAIC-2019-Lapse
```

#### 5.2 Plugin System
```python
# New module: gaspatchio_core/plugins/
class PluginRegistry:
    """Rails-style plugin system"""
    
    def load_plugin(self, name: str):
        """Load third-party extensions"""
```

#### 5.3 Convention Documentation
- Published convention guide
- Community best practices
- Standard calculation library

### Migration Impact
- Enables ecosystem growth
- Optional participation

## Phase 6: Performance & Polish (Month 6)
*"Fast by Default"*

### Goals
- Optimize common patterns
- Add caching layer
- Performance profiling

### Deliverables

#### 6.1 Pattern Optimization
- Pre-compile common calculation patterns
- Optimize convention detection
- Cache assumption lookups

#### 6.2 Development Mode
```python
# Enhanced debug mode
ActuarialFrame.development_mode = True
# Provides:
# - Better stack traces
# - Calculation explanations  
# - Performance warnings
```

#### 6.3 Production Optimizations
- Auto-batch small operations
- Parallel assumption loading
- GPU auto-detection

## Implementation Priorities

### Quick Wins (Can start immediately)
1. Better error messages
2. Simple shortcuts (pv_benefits, apply_decrements)
3. Convention detection for common columns

### High Impact (Focus after quick wins)
1. Fluent interface improvements
2. Model templates
3. Auto-loading assumptions

### Long Term (Build ecosystem)
1. Declarative model syntax
2. Plugin architecture
3. Community standards

## Success Metrics

### Developer Experience
- 50% reduction in boilerplate code
- 80% of models use conventions
- 90% satisfaction in developer survey

### Performance
- No regression in calculation speed
- <100ms overhead for conveniences
- Auto-optimization matches manual

### Adoption
- 100+ models using new patterns
- 20+ community plugins
- Standard conventions adopted industry-wide

## Risk Mitigation

### Backward Compatibility
- All changes are additive
- Deprecation warnings before removals
- Migration tools provided

### Performance Impact
- Benchmark every change
- Conventions compile to same operations
- Opt-out always available

### Learning Curve
- Comprehensive documentation
- Video tutorials
- Example model library

## Conclusion

This roadmap provides a path to transform Gaspatchio into a Rails-inspired framework while maintaining its performance advantages. By focusing on developer happiness, conventions, and progressive disclosure of complexity, we can create an actuarial modeling framework that is both powerful and delightful to use.