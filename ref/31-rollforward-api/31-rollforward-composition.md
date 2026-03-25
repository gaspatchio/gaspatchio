# Rollforward Composition API Design

## GSP-87: Template Composition and Decomposition for Rollforward Builder

### Status: Design Proposal
### Authors: Matt Wright, Claude
### Date: 2026-03-25
### Depends on: GSP-86 (Rollforward Builder)

---

## 1. Core Insight

The rollforward builder (GSP-86) compiles to `list[StepSpec]` — a flat, ordered, labeled sequence of declarative operations. This is an ideal structure for composition. Unlike expression trees or DAGs, a step list supports insert/remove/replace by position or label with zero ambiguity about execution order.

The key design question is: **when does column binding happen?**

- Too early (at step creation): templates cannot be reused across datasets
- Too late (at Rust execution): Python cannot validate column existence
- Right: at `bind()` time, when template meets frame

---

## 2. Two-Layer Architecture

### Layer 1: `RollforwardBuilder` (bound, Phase 1)

Already defined in GSP-86. Bound to an `ActuarialFrame`. Steps reference real column proxies (`af.premium`, `af.coi_rate`). Compiles directly to kwargs + `register_plugin_function`.

Labels are **required** on every step (auto-generated if omitted). Composition operations work directly on the builder.

### Layer 2: `RollforwardTemplate` (unbound, Phase 2)

Abstract step sequence using string column names. No frame reference. Immutable — every mutation returns a new template. Becomes a builder via `.bind(af)`.

### Why Two Layers

A product actuary prototyping 20 variations in a single notebook does not need templates. They have one frame, one set of columns, and they are iterating on step order and parameters. The builder with labels and composition methods is sufficient.

Templates matter when:
- Sharing rollforward definitions across teams or models
- Storing product definitions in version control
- Building a product library that multiple models import
- Running the same logic against different datasets with different column names

Phase 1 delivers the 80% case. Phase 2 adds the reuse layer.

---

## 3. Phase 1: Builder with Labels and Composition

### 3.1 Step Class (internal, for composition addressing)

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class StepDef:
    """Internal representation of a single rollforward step.

    Immutable. Used by both RollforwardBuilder and RollforwardTemplate
    for storage and composition operations. Not part of the public API —
    users interact through builder methods.
    """

    operation: str          # "add", "charge", "grow", "deduct_nar", etc.
    label: str              # Required. Used for addressing in composition.
    args: tuple[Any, ...]   # Positional arguments (column refs or values)
    kwargs: dict[str, Any] = field(default_factory=dict)  # Keyword arguments
```

### 3.2 Builder API

```python
class RollforwardBuilder:
    """Bound rollforward builder with composition support.

    Created via af.projection.rollforward(initial=...).
    Steps reference real ColumnProxy/ExpressionProxy objects from the
    parent ActuarialFrame. Labels are required for composition;
    auto-generated from operation + argument name if omitted.

    Immutable with respect to composition: insert_before(), remove(), etc.
    return new builders. The chaining methods (add, charge, grow...) also
    return new builders — the whole thing is a persistent data structure.
    """

    def __init__(
        self,
        frame: ActuarialFrame,
        initial: ColumnProxy | ExpressionProxy,
        *,
        track_increments: bool = False,
    ) -> None: ...

    # ── Step methods (return new RollforwardBuilder) ──────────────

    def add(
        self,
        amount: ColumnProxy | ExpressionProxy,
        label: str | None = None,
    ) -> RollforwardBuilder: ...

    def subtract(
        self,
        amount: ColumnProxy | ExpressionProxy,
        label: str | None = None,
    ) -> RollforwardBuilder: ...

    def charge(
        self,
        rate: ColumnProxy | ExpressionProxy,
        label: str | None = None,
    ) -> RollforwardBuilder: ...

    def grow(
        self,
        rate: ColumnProxy | ExpressionProxy,
        label: str | None = None,
    ) -> RollforwardBuilder: ...

    def grow_capped(
        self,
        rate: ColumnProxy | ExpressionProxy,
        *,
        floor: float,
        cap: float,
        label: str | None = None,
    ) -> RollforwardBuilder: ...

    def deduct_nar(
        self,
        rate: ColumnProxy | ExpressionProxy,
        *,
        death_benefit: ColumnProxy | ExpressionProxy,
        label: str | None = None,
    ) -> RollforwardBuilder: ...

    def floor(
        self,
        value: float,
        label: str | None = None,
    ) -> RollforwardBuilder: ...

    def cap(
        self,
        value: float,
        label: str | None = None,
    ) -> RollforwardBuilder: ...

    def lapse_if_zero(self) -> RollforwardBuilder: ...

    def add_if(
        self,
        condition: ColumnProxy | ExpressionProxy,
        amount: ColumnProxy | ExpressionProxy,
        label: str | None = None,
    ) -> RollforwardBuilder: ...

    def charge_if(
        self,
        condition: ColumnProxy | ExpressionProxy,
        rate: ColumnProxy | ExpressionProxy,
        label: str | None = None,
    ) -> RollforwardBuilder: ...

    def capture(self, name: str) -> RollforwardBuilder: ...

    # ── Composition methods (return new RollforwardBuilder) ──────

    def insert_before(
        self, label: str, step: StepDef,
    ) -> RollforwardBuilder: ...

    def insert_after(
        self, label: str, step: StepDef,
    ) -> RollforwardBuilder: ...

    def remove(self, label: str) -> RollforwardBuilder: ...

    def replace(self, label: str, step: StepDef) -> RollforwardBuilder: ...

    def prepend(self, step: StepDef) -> RollforwardBuilder: ...

    def append(self, step: StepDef) -> RollforwardBuilder: ...

    # ── Inspection ───────────────────────────────────────────────

    @property
    def steps(self) -> tuple[StepDef, ...]:
        """Return the current step sequence (read-only)."""
        ...

    @property
    def labels(self) -> tuple[str, ...]:
        """Return all step labels in order."""
        ...

    def explain(self) -> str:
        """Return the formula table from GSP-86 section 7."""
        ...

    # ── Compilation (internal) ───────────────────────────────────

    def _compile(self) -> tuple[list[pl.Expr], dict[str, Any]]:
        """Compile to (args, kwargs) for register_plugin_function."""
        ...
```

### 3.3 Label Requirements and Auto-Generation

Labels serve two purposes: composition addressing and audit display. The rule:

1. **If the user provides a label, use it exactly.** This is the composition handle.
2. **If no label is provided, auto-generate one** from the operation and the column name: `"Add(premium)"`, `"Charge(admin_rate)"`, `"DeductNAR(coi_rate)"`, `"Floor(0)"`.
3. **Labels must be unique within a builder.** Duplicate labels are an error at step-addition time, not at compilation time. The error message suggests a fix:

```
ValueError: Duplicate label 'COI' in rollforward.
Already used at step 2. Use a distinct label:
  .deduct_nar(af.rider_coi_rate, death_benefit=af.sa, label="Rider COI")
```

4. **Auto-generated labels are deterministic** so they can be used in composition — but users who plan to compose should use explicit labels for clarity.

This means there is no separate "step ID" concept. Labels ARE the addressing mechanism. They also appear in `.explain()` and `track_increments` output. One concept, three uses.

### 3.4 Composition Error Handling

All composition methods raise `KeyError` if the target label does not exist. Not a warning — a silent miss in a composition chain produces a silently wrong model, which is the worst failure mode in actuarial software.

```python
# KeyError: "No step with label 'Admin' in rollforward.
#  Available labels: ['Premium', 'COI', 'Charge(admin_rate)', 'Interest', 'Floor(0)']"
builder.remove("Admin")

# Works — user used explicit labels
builder.remove("Charge(admin_rate)")
```

This is why explicit labels matter for composition. Auto-generated labels work but are fragile — rename the column and the label changes.

### 3.5 Immutability

Every method returns a new `RollforwardBuilder`. The internal step list is a `tuple[StepDef, ...]`, not a `list`. This means:

```python
base = (
    af.projection.rollforward(initial=af.av_init)
    .add(af.premium, "Premium")
    .charge(af.admin_rate, "Admin")
    .grow(af.interest_rate, "Interest")
    .floor(0)
)

# base is not modified — each returns a new builder
with_rider = base.insert_before("Interest", StepDef("charge", "Rider", (af.rider_rate,)))
without_admin = base.remove("Admin")
```

The `frame` reference is shared across variants (shallow copy of pointer). Only the step tuple differs.

### 3.6 Convenience: Step Factory Methods

Building `StepDef` objects by hand is verbose. The builder provides static factory methods so composition reads naturally:

```python
class RollforwardBuilder:
    # ... (step methods and composition methods as above)

    @staticmethod
    def step_add(
        amount: ColumnProxy | ExpressionProxy,
        label: str | None = None,
    ) -> StepDef:
        """Create an Add step for use with insert_before/after/replace."""
        ...

    @staticmethod
    def step_charge(
        rate: ColumnProxy | ExpressionProxy,
        label: str | None = None,
    ) -> StepDef:
        """Create a Charge step for use with insert_before/after/replace."""
        ...

    @staticmethod
    def step_grow(
        rate: ColumnProxy | ExpressionProxy,
        label: str | None = None,
    ) -> StepDef:
        """Create a Grow step for use with insert_before/after/replace."""
        ...

    # ... one per operation type
```

Usage:

```python
with_rider = base.insert_before(
    "Interest",
    RollforwardBuilder.step_charge(af.rider_rate, "Rider Fee"),
)
```

Or, with a module-level alias for terseness:

```python
from gaspatchio_core.rollforward import Step

with_rider = base.insert_before("Interest", Step.charge(af.rider_rate, "Rider Fee"))
```

`Step` is a namespace class (no instances) with static factory methods. This is the recommended public API for composition.

### 3.7 Full Phase 1 Example

```python
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward import Step

af = ActuarialFrame(data)

# Build a base UL rollforward
base_ul = (
    af.projection.rollforward(initial=af.av_init, track_increments=True)
    .add(af.premium, "Premium")
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
    .charge(af.admin_rate, "Admin")
    .grow(af.interest_rate, "Interest")
    .floor(0)
)

# Variation 1: Insert rider charge before interest
ul_with_rider = base_ul.insert_before(
    "Interest", Step.charge(af.rider_rate, "Rider Fee")
)

# Variation 2: Replace flat admin with percentage-of-premium
ul_prem_admin = base_ul.replace(
    "Admin", Step.subtract(af.admin_dollar, "Admin ($)")
)

# Variation 3: Remove admin entirely
ul_no_admin = base_ul.remove("Admin")

# Variation 4: Add surrender charge after floor
ul_with_surrender = base_ul.append(Step.charge(af.surrender_rate, "Surrender"))

# Inspect any variant
print(ul_with_rider.explain())
# Rollforward: initial=av_init, 6 steps
#   Step  Operation              Label        Formula
#   1     Add(premium)           Premium      av[t] += premium[t]
#   2     DeductNAR(coi_rate)    COI          av[t] -= coi_rate[t] * max(0, sa[t] - av[t])
#   3     Charge(admin_rate)     Admin        av[t] *= (1 - admin_rate[t])
#   4     Charge(rider_rate)     Rider Fee    av[t] *= (1 - rider_rate[t])
#   5     Grow(interest_rate)    Interest     av[t] *= (1 + interest_rate[t])
#   6     Floor(0)               Floor(0)     av[t] = max(av[t], 0)

# Assign to trigger compilation and execution
af.av = ul_with_rider
af.av_no_rider = base_ul

# Access increments (both track independently)
af.coi_amount = af.av.increments["COI"]
af.rider_fee_amount = af.av.increments["Rider Fee"]
```

---

## 4. Phase 2: RollforwardTemplate (Unbound)

### 4.1 Template Class

```python
class RollforwardTemplate:
    """Unbound rollforward definition using string column names.

    Immutable. All mutation methods return new templates. Becomes a
    RollforwardBuilder via .bind(af) or af.projection.rollforward(template=...).
    """

    def __init__(self) -> None: ...

    # ── Step methods (mirror builder, but accept str column names) ─────

    def add(self, column: str, label: str | None = None) -> RollforwardTemplate: ...
    def subtract(self, column: str, label: str | None = None) -> RollforwardTemplate: ...
    def charge(self, column: str, label: str | None = None) -> RollforwardTemplate: ...
    def grow(self, column: str, label: str | None = None) -> RollforwardTemplate: ...
    def grow_capped(
        self, column: str, *, floor: float, cap: float, label: str | None = None,
    ) -> RollforwardTemplate: ...
    def deduct_nar(
        self, rate_column: str, *, death_benefit: str, label: str | None = None,
    ) -> RollforwardTemplate: ...
    def floor(self, value: float, label: str | None = None) -> RollforwardTemplate: ...
    def cap(self, value: float, label: str | None = None) -> RollforwardTemplate: ...
    def lapse_if_zero(self) -> RollforwardTemplate: ...
    def capture(self, name: str) -> RollforwardTemplate: ...

    # ── Composition methods (identical semantics to builder) ───────────

    def insert_before(self, label: str, step: StepDef) -> RollforwardTemplate: ...
    def insert_after(self, label: str, step: StepDef) -> RollforwardTemplate: ...
    def remove(self, label: str) -> RollforwardTemplate: ...
    def replace(self, label: str, step: StepDef) -> RollforwardTemplate: ...
    def prepend(self, step: StepDef) -> RollforwardTemplate: ...
    def append(self, step: StepDef) -> RollforwardTemplate: ...

    # ── Binding ────────────────────────────────────────────────────────

    def bind(
        self,
        frame: ActuarialFrame,
        initial: ColumnProxy | ExpressionProxy | str,
        *,
        track_increments: bool = False,
        column_map: dict[str, str] | None = None,
    ) -> RollforwardBuilder:
        """Resolve string column names against a real frame.

        Parameters
        ----------
        frame
            The ActuarialFrame to bind to.
        initial
            The initial value column.
        track_increments
            Whether to track per-step dollar increments.
        column_map
            Optional mapping from template column names to frame column
            names. Allows reusing a template with different datasets:
            {"coi_rate": "monthly_coi", "admin_rate": "expense_charge"}.

        Raises
        ------
        KeyError
            If a template column name is not found in the frame and not
            in column_map.
        """
        ...

    # ── Inspection ─────────────────────────────────────────────────────

    @property
    def steps(self) -> tuple[StepDef, ...]: ...

    @property
    def labels(self) -> tuple[str, ...]: ...

    @property
    def required_columns(self) -> frozenset[str]:
        """Return all column names referenced by this template."""
        ...

    def explain(self) -> str:
        """Return formula table (with string column names, not resolved)."""
        ...

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary suitable for JSON/YAML."""
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RollforwardTemplate:
        """Deserialize from a dictionary."""
        ...

    def to_yaml(self, path: Path) -> None:
        """Write template to a YAML file."""
        ...

    @classmethod
    def from_yaml(cls, path: Path) -> RollforwardTemplate:
        """Load template from a YAML file."""
        ...
```

### 4.2 Binding via Frame Method

Both binding paths are supported:

```python
# Path 1: template.bind(af, initial=...)
builder = base_ul_template.bind(af, initial="av_init", track_increments=True)
af.av = builder

# Path 2: af.projection.rollforward(template=..., initial=...)
af.av = af.projection.rollforward(
    template=base_ul_template,
    initial=af.av_init,
    track_increments=True,
)
```

Path 2 is preferred — it reads as "this frame's projection uses this template," which matches the mental model. Path 1 exists for cases where you want the intermediate builder (e.g., to compose further after binding).

### 4.3 Column Mapping

Templates reference column names as strings. When the target dataset uses different names, `column_map` bridges the gap without modifying the template:

```python
# Template was written for one naming convention
base_ul = (
    RollforwardTemplate()
    .add("premium", "Premium")
    .deduct_nar("coi_rate", death_benefit="sum_assured", label="COI")
    .charge("admin_rate", "Admin")
    .grow("interest_rate", "Interest")
    .floor(0)
)

# Dataset uses different names
af.av = af.projection.rollforward(
    template=base_ul,
    initial=af.av_init,
    column_map={
        "premium": "gross_premium",
        "coi_rate": "monthly_coi",
        "sum_assured": "death_benefit_amount",
        "admin_rate": "monthly_expense_charge",
        "interest_rate": "credited_rate",
    },
)
```

The `required_columns` property makes it easy to discover what a template needs:

```python
>>> base_ul.required_columns
frozenset({'premium', 'coi_rate', 'sum_assured', 'admin_rate', 'interest_rate'})
```

### 4.4 Serialization Format

YAML is the primary serialization format because actuaries read it. The format mirrors the method chain:

```yaml
# ul_base.yaml
name: Universal Life Base
version: "1.0"
description: Standard UL account value rollforward

steps:
  - operation: add
    column: premium
    label: Premium

  - operation: deduct_nar
    rate_column: coi_rate
    death_benefit: sum_assured
    label: COI

  - operation: charge
    column: admin_rate
    label: Admin

  - operation: grow
    column: interest_rate
    label: Interest

  - operation: floor
    value: 0
```

JSON is also supported (same structure, just format difference). The schema is intentionally flat — no nesting beyond step-level kwargs.

### 4.5 Product Library Pattern

```python
# gaspatchio_models/templates/__init__.py
from gaspatchio_models.templates._definitions import (
    base_ul,
    base_vul,
    base_iul,
    base_wl,
)

# gaspatchio_models/templates/_definitions.py
from gaspatchio_core.rollforward import RollforwardTemplate

base_ul = (
    RollforwardTemplate()
    .add("premium", "Premium")
    .deduct_nar("coi_rate", death_benefit="sum_assured", label="COI")
    .charge("admin_rate", "Admin")
    .grow("interest_rate", "Interest")
    .floor(0)
)

base_vul = (
    base_ul
    .insert_before("Interest", RollforwardTemplate.step_charge("me_rate", "M&E Fee"))
    .replace("Interest", RollforwardTemplate.step_grow("fund_return", "Fund Return"))
)

base_iul = (
    base_ul
    .replace(
        "Interest",
        RollforwardTemplate.step_grow_capped(
            "index_return", floor=0.0, cap=0.12, label="Index Credit"
        ),
    )
)
```

Templates are Python objects (not file paths), so they compose with normal Python imports and IDE tooling. YAML files are for cross-language exchange and version control diffing.

---

## 5. Template Step Factories

Both `RollforwardBuilder` and `RollforwardTemplate` expose identical step factory namespaces. The difference is what the column argument type is:

```python
class Step:
    """Namespace for creating step definitions for composition.

    Used with insert_before, insert_after, replace, prepend, append.
    Column arguments accept either ColumnProxy (bound) or str (unbound).
    """

    @staticmethod
    def add(
        amount: ColumnProxy | ExpressionProxy | str,
        label: str | None = None,
    ) -> StepDef: ...

    @staticmethod
    def charge(
        rate: ColumnProxy | ExpressionProxy | str,
        label: str | None = None,
    ) -> StepDef: ...

    @staticmethod
    def grow(
        rate: ColumnProxy | ExpressionProxy | str,
        label: str | None = None,
    ) -> StepDef: ...

    @staticmethod
    def subtract(
        amount: ColumnProxy | ExpressionProxy | str,
        label: str | None = None,
    ) -> StepDef: ...

    @staticmethod
    def grow_capped(
        rate: ColumnProxy | ExpressionProxy | str,
        *,
        floor: float,
        cap: float,
        label: str | None = None,
    ) -> StepDef: ...

    @staticmethod
    def deduct_nar(
        rate: ColumnProxy | ExpressionProxy | str,
        *,
        death_benefit: ColumnProxy | ExpressionProxy | str,
        label: str | None = None,
    ) -> StepDef: ...

    @staticmethod
    def floor(value: float, label: str | None = None) -> StepDef: ...

    @staticmethod
    def cap(value: float, label: str | None = None) -> StepDef: ...

    @staticmethod
    def charge_tiered(
        breakpoints: list[float],
        rates: list[float],
        label: str | None = None,
    ) -> StepDef: ...

    @staticmethod
    def grow_tiered(
        breakpoints: list[float],
        rates: list[float],
        label: str | None = None,
    ) -> StepDef: ...
```

One `Step` class works for both builder and template composition. When a `StepDef` with string column references is inserted into a `RollforwardBuilder`, the builder resolves strings against the frame at insertion time. When a `StepDef` with `ColumnProxy` references is inserted into a `RollforwardTemplate`, a `TypeError` is raised — templates only accept strings.

---

## 6. Multi-Product Rollforwards (Out of Scope, with Guidance)

Running UL and VUL policies in the same frame with different rollforward logic is a common need. However, this is architecturally a **groupby-dispatch** problem, not a template-composition problem. The right solution:

```python
# Option A: Separate frames (recommended for Phase 1)
ul_policies = af.filter(af.product_type == "UL")
vul_policies = af.filter(af.product_type == "VUL")

ul_policies.av = ul_builder  # uses base_ul steps
vul_policies.av = vul_builder  # uses vul steps (with M&E fee)

# Option B: Future — conditional rollforward (Phase 3+)
af.av = af.projection.rollforward(
    initial=af.av_init,
    dispatch={
        "UL": base_ul_template,
        "VUL": base_vul_template,
    },
    dispatch_column="product_type",
)
```

Option A works today with Polars filtering and is explicit. Option B requires the Rust kernel to branch on a dispatch column — feasible but adds significant complexity for a niche case. Deferred.

Conditional step application (`.charge_if()`) already handles the simpler case where a single step differs:

```python
af.av = (
    af.projection.rollforward(initial=af.av_init)
    .add(af.premium, "Premium")
    .charge(af.admin_rate, "Admin")
    .charge_if(af.is_vul, af.me_rate, "M&E Fee")  # only for VUL policies
    .grow(af.interest_rate, "Interest")
    .floor(0)
)
```

---

## 7. Phase Plan

### Phase 1 (GSP-86 + composition)

What ships:
- `RollforwardBuilder` with all step methods from GSP-86 section 4
- **Labels: required-unique, auto-generated if omitted**
- **Composition: `insert_before`, `insert_after`, `remove`, `replace`, `prepend`, `append`**
- **`Step` factory namespace** for creating `StepDef` objects for composition
- **Immutability**: every method returns a new builder
- `.explain()` with formula table
- `track_increments` for audit
- Rust kernel (single-state)

What does NOT ship:
- `RollforwardTemplate` (unbound)
- Serialization (YAML/JSON)
- Column mapping
- Multi-product dispatch

Why: a product actuary prototyping 20 variations needs labels + composition on a live builder. They do not need serialization or cross-dataset reuse yet. The builder is self-contained and covers the day-to-day workflow.

### Phase 2 (GSP-87)

What ships:
- `RollforwardTemplate` (unbound, string column names)
- `.bind(af, initial=..., column_map=...)` binding
- `af.projection.rollforward(template=...)` entry point
- `required_columns` introspection
- `.to_dict()` / `.from_dict()` serialization
- `.to_yaml()` / `.from_yaml()` serialization
- Multi-state rollforward (`.on()`, `ratchet_to`, `pro_rata_with`, `lapse_when`)

### Phase 3 (future)

- Product library package pattern with curated templates
- Multi-product dispatch (dispatch column + template map)
- Template inheritance / mixin patterns
- Tiered operations (`charge_tiered`, `grow_tiered`)
- `charge_lookup` (mid-loop assumption table access)

---

## 8. Implementation Notes

### 8.1 Shared Step Storage

Both `RollforwardBuilder` and `RollforwardTemplate` store `tuple[StepDef, ...]`. The `StepDef` dataclass is the same object. The difference is what goes in `args`:

| Context | `StepDef.args` contains |
|---------|------------------------|
| Builder | `ColumnProxy`, `ExpressionProxy`, `float` |
| Template | `str` (column name), `float` |

At compilation time (builder only), `ColumnProxy` references are resolved to `pl.Expr` and then to positional indices in the `args` list passed to `register_plugin_function`.

### 8.2 Compilation Pipeline

```
StepDef tuple (Python)
    │
    ▼ _compile()
list[pl.Expr] args + RollforwardKwargs JSON
    │
    ▼ register_plugin_function()
Polars LazyFrame expression
    │
    ▼ af.__setitem__ / collect()
Rust kernel execution
```

The composition layer never touches Rust. It manipulates `StepDef` tuples in Python. Compilation happens once, at assignment time.

### 8.3 Immutability Implementation

```python
class RollforwardBuilder:
    __slots__ = ("_frame", "_initial", "_steps", "_track_increments")

    def __init__(self, frame, initial, *, steps=(), track_increments=False):
        self._frame = frame
        self._initial = initial
        self._steps = steps  # tuple[StepDef, ...]
        self._track_increments = track_increments

    def _with_steps(self, new_steps: tuple[StepDef, ...]) -> RollforwardBuilder:
        """Return a new builder with the given steps."""
        return RollforwardBuilder(
            self._frame,
            self._initial,
            steps=new_steps,
            track_increments=self._track_increments,
        )

    def add(self, amount, label=None):
        label = label or f"Add({_col_name(amount)})"
        self._check_unique_label(label)
        step = StepDef("add", label, (amount,))
        return self._with_steps((*self._steps, step))

    def insert_before(self, label, step):
        idx = self._find_label(label)  # raises KeyError if missing
        self._check_unique_label(step.label)
        new_steps = (*self._steps[:idx], step, *self._steps[idx:])
        return self._with_steps(new_steps)

    def remove(self, label):
        idx = self._find_label(label)
        new_steps = (*self._steps[:idx], *self._steps[idx + 1:])
        return self._with_steps(new_steps)

    def _find_label(self, label: str) -> int:
        for i, s in enumerate(self._steps):
            if s.label == label:
                return i
        available = [s.label for s in self._steps]
        msg = (
            f"No step with label {label!r} in rollforward. "
            f"Available labels: {available}"
        )
        raise KeyError(msg)

    def _check_unique_label(self, label: str) -> None:
        for i, s in enumerate(self._steps):
            if s.label == label:
                msg = (
                    f"Duplicate label {label!r} in rollforward. "
                    f"Already used at step {i + 1}."
                )
                raise ValueError(msg)
```

### 8.4 Label Interaction with track_increments and explain()

Labels are the single source of truth for step identity:

- **`.explain()`**: The "Label" column shows the step's label.
- **`track_increments`**: The Struct column fields are named by label. `af.av.increments["COI"]` works because "COI" is the label.
- **Composition**: `insert_before("COI", ...)` finds the step by label.

If a user changes a label via `.replace()`, the increment field name changes too. This is correct — the step has been replaced, so its identity should change.

Auto-generated labels produce increment field names like `"Add(premium)"` and `"Charge(admin_rate)"`. These are valid Polars field names and work with `struct.field()` access.

---

## 9. What This Intentionally Does NOT Do

### 9.1 No DAG / Dependency Tracking

Steps are a flat ordered list, not a graph. There is no automatic reordering. The actuary controls execution order by declaration order. If they put interest before COI, that is what executes. `.explain()` makes the order visible; the actuary validates it against the product spec.

### 9.2 No Template Inheritance

No `class VULTemplate(ULTemplate)` pattern. Templates compose via methods (`insert_before`, `replace`, `remove`), not via class hierarchies. Class inheritance would imply that VUL "is-a" UL, which misrepresents the relationship. VUL "is derived from" UL by adding M&E and replacing interest with fund return. The composition API expresses this directly.

### 9.3 No Conditional Steps Beyond charge_if / add_if

Conditional logic within the rollforward is limited to per-step predicates. Full dispatch (different step sequences for different policies) is a groupby-filter problem handled outside the rollforward. This keeps the Rust kernel simple: one step sequence per rollforward invocation, no branching in the inner loop.

### 9.4 No Python Callbacks

Templates cannot contain lambdas, functions, or any callable. Every step must be serializable to JSON kwargs. This is a fundamental constraint of the Polars plugin architecture and is the reason `.apply(fn)` is impossible.

---

## 10. Summary: What Makes 20 Product Variations Fast

The product development actuary's workflow:

1. **Build a base** using the builder chain (5 minutes)
2. **Create variations** using `insert_before`, `replace`, `remove` (30 seconds each)
3. **Inspect each** with `.explain()` to verify step order against product spec (10 seconds)
4. **Assign all variants** to the frame — they compile and execute in parallel (automatic)
5. **Compare results** using standard Polars operations on the output columns

The key accelerator is step 2: composition methods return new builders instantly because they manipulate a Python tuple, not Rust compilation. The actuary can create 20 variants from one base in under 10 minutes, then run them all in one `.collect()` call.

Without composition, each variant requires re-typing the full chain. With 5-8 steps per rollforward and 20 variants, that is 100-160 lines of repetitive code where a single typo produces a silent error. Composition reduces this to 20 one-liners where the diff from the base is explicit and auditable.
