# Rollforward Spec-Diffing and Model Fingerprinting

## GSP-87: Declarative Model Validation, Diffing, and Change Control

### Status: Design Proposal
### Authors: Matt Wright, Claude
### Date: 2026-03-25
### Depends on: GSP-86 (Rollforward Builder)

---

## 1. Problem Statement

Because the rollforward builder compiles to declarative data (a JSON kwargs payload of `StepSpec` variants), rather than opaque Python code, we can treat a model as a **structured, inspectable artifact**. This creates three opportunities that code-based modeling frameworks cannot offer:

1. **Validation against a product specification** -- a validation actuary receives a model and needs to verify it implements the product spec correctly, step by step.
2. **Structural diffing between model versions** -- quarterly model changes need clear audit trails showing exactly what changed and what did not.
3. **Fingerprinting for change control** -- regulatory submissions need proof that the model used in production is identical to the model that was validated.

### The Validation Actuary's Workflow

The target user opens a product specification document (paper or PDF), then opens the model, and needs to answer: "Does this model implement this spec?" Today, this requires reading Python code line by line. With a declarative rollforward, the framework can answer this question programmatically.

---

## 2. Design Principles

1. **The spec is the source of truth** -- it represents what the product *should* do, authored by the product or validation team
2. **Comparison is structural, not textual** -- column names are aliases; the step *shape* is what matters
3. **Labels are documentation, not logic** -- they are excluded from structural comparisons by default
4. **Extra steps are warnings, not failures** -- a model may have defensive `.floor(0)` steps not in the spec; that is a finding, not a defect
5. **Specs are version-controlled data** -- YAML files that live alongside the model code in git

---

## 3. Canonical Form and Fingerprinting

### 3.1 What Goes Into the Canonical Form

The canonical form strips implementation details (column indices, labels) and retains only the **structural shape** that affects computation:

```python
@dataclass(slots=True)
class CanonicalStep:
    """A single step in canonical form, stripped of implementation details."""
    op: str                          # e.g., "Add", "Charge", "DeductNar", "Floor"
    target: str                      # state name, e.g., "av" or "__default__" for single-state
    params: dict[str, Any]           # structural params only (see below)
```

What is **included** in the canonical form:

| Field | Included | Rationale |
|-------|----------|-----------|
| Step type (op) | Yes | Defines the computation |
| Step ordering | Yes | Order changes semantics (charge-then-grow differs from grow-then-charge) |
| Target state name | Yes | Which state the step operates on |
| Constant parameters (`floor` value, `cap` value, breakpoints, rates) | Yes | These are part of the product definition |
| `death_benefit` parameter presence in DeductNar | Yes | Structural -- determines NAR formula |
| Input column names | **No** | See section 3.2 |
| Labels | **No** | Documentation only, do not affect computation |
| `input_index` values | **No** | Implementation detail of column ordering |
| `track_increments` flag | **No** | Observability setting, not computation |

The canonical form for the UL example from the design doc:

```json
{
  "version": 1,
  "states": [{"name": "__default__"}],
  "steps": [
    {"op": "Add",       "target": "__default__", "params": {}},
    {"op": "DeductNar", "target": "__default__", "params": {"has_death_benefit": true}},
    {"op": "Charge",    "target": "__default__", "params": {}},
    {"op": "Grow",      "target": "__default__", "params": {}},
    {"op": "Floor",     "target": "__default__", "params": {"value": 0.0}}
  ]
}
```

### 3.2 Why Column Names Are Excluded from the Fingerprint

Column names are **environment-dependent aliases**. The same model, using a different naming convention, performs identical computation:

```python
# Team A's convention
.deduct_nar(af.qx_monthly, death_benefit=af.sum_assured)

# Team B's convention
.deduct_nar(af.coi_rate, death_benefit=af.death_benefit_amount)
```

These are structurally identical: both are `DeductNar` with a rate input and a death_benefit input. Including column names in the fingerprint would cause false negatives (different fingerprint for identical logic).

**However**, column names *are* available in the full spec for human-readable diffing and `explain()` output. They are just not part of the canonical hash.

### 3.3 The Initial Value Column

The initial value column name is **excluded** from the fingerprint for the same reason as other column names. The *presence* of an initial value is implicit (every rollforward has one). Whether it is called `av_init` or `account_value_initial` does not change computation.

For multi-state rollforward, the **state names** (e.g., `"av"`, `"guarantee"`) *are* included because they are structural -- they define cross-state references like `.ratchet_to("av")`.

### 3.4 Fingerprint API

```python
# SHA-256 of the canonical JSON, deterministically serialized
fingerprint: str = rf.fingerprint()
# e.g., "sha256:a1b2c3d4e5f6..."

# Access the canonical form directly for inspection
canonical: dict = rf.canonical()
```

**Implementation:** The canonical JSON is serialized with sorted keys, no whitespace, and UTF-8 encoding. The SHA-256 is computed over the bytes. This is deterministic across platforms and Python versions.

```python
import hashlib
import json

def fingerprint(self) -> str:
    """Return SHA-256 hash of the canonical model specification.

    The canonical form includes step types, ordering, target states,
    and constant parameters. It excludes column names, labels, and
    implementation details like column indices.

    Returns:
        A string of the form "sha256:<hex_digest>".

    """
    canonical = self.canonical()
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
```

### 3.5 Named Fingerprint for Audit Logs

For regulatory submissions, the fingerprint should be paired with metadata:

```python
rf.fingerprint_record()
# Returns:
# FingerprintRecord(
#     fingerprint="sha256:a1b2c3d4...",
#     step_count=5,
#     states=["__default__"],
#     timestamp="2026-03-25T14:30:00Z",
#     canonical={"version": 1, "states": [...], "steps": [...]}
# )
```

This record can be serialized to JSON and stored in audit systems.

---

## 4. Product Specification (ProductSpec)

### 4.1 What Is a ProductSpec

A `ProductSpec` is a **declarative description of expected rollforward structure**, authored by a product team or validation team. It defines what steps a model *should* contain, in what order, with what parameter constraints.

A ProductSpec is NOT a runnable model. It has no column references, no data. It is a template that says: "A correct implementation of Universal Life v3.2 must have these steps in this order."

```python
from gaspatchio_core.rollforward import ProductSpec, Step

spec = ProductSpec(
    name="Universal Life v3.2",
    version="3.2.0",
    description="Standard UL with COI on NAR, monthly admin charge, and credited interest.",
    steps=[
        Step.add(label="Premium deposit"),
        Step.deduct_nar(has_death_benefit=True, label="COI on net amount at risk"),
        Step.charge(label="Monthly admin charge"),
        Step.grow(label="Interest crediting"),
        Step.floor(0, label="Non-negative AV constraint"),
    ],
)
```

### 4.2 Step Constraint Levels

Each `Step` in a ProductSpec can constrain at three levels of granularity:

| Level | What It Checks | When to Use |
|-------|---------------|-------------|
| **Type only** | Step is the right operation type | "There must be a Charge step" |
| **Type + shape** | Step has the right parameter structure | "There must be a DeductNar with a death_benefit" |
| **Type + shape + value** | Constant parameters match exactly | "There must be a Floor at exactly 0" |

```python
# Level 1: Type only -- "must have a charge step"
Step.charge()

# Level 2: Type + shape -- "must deduct NAR with a death benefit reference"
Step.deduct_nar(has_death_benefit=True)

# Level 3: Type + value -- "must floor at exactly zero"
Step.floor(0)

# Level 3: Tiered with exact breakpoints
Step.charge_tiered(breakpoints=[0, 25_000, 100_000], rates=[0.0025, 0.0020, 0.0015])
```

### 4.3 Step Data Structure

```python
@dataclass(slots=True, frozen=True)
class Step:
    """A single step constraint in a ProductSpec."""
    op: str
    params: dict[str, Any] = field(default_factory=dict)
    label: str | None = None

    # Factory methods for each operation type
    @classmethod
    def add(cls, *, label: str | None = None) -> Step:
        return cls(op="Add", label=label)

    @classmethod
    def subtract(cls, *, label: str | None = None) -> Step:
        return cls(op="Subtract", label=label)

    @classmethod
    def charge(cls, *, label: str | None = None) -> Step:
        return cls(op="Charge", label=label)

    @classmethod
    def grow(cls, *, label: str | None = None) -> Step:
        return cls(op="Grow", label=label)

    @classmethod
    def grow_capped(
        cls,
        *,
        floor: float | None = None,
        cap: float | None = None,
        label: str | None = None,
    ) -> Step:
        params: dict[str, Any] = {}
        if floor is not None:
            params["floor"] = floor
        if cap is not None:
            params["cap"] = cap
        return cls(op="GrowCapped", params=params, label=label)

    @classmethod
    def deduct_nar(
        cls,
        *,
        has_death_benefit: bool = True,
        label: str | None = None,
    ) -> Step:
        return cls(
            op="DeductNar",
            params={"has_death_benefit": has_death_benefit},
            label=label,
        )

    @classmethod
    def charge_tiered(
        cls,
        breakpoints: list[float] | None = None,
        rates: list[float] | None = None,
        *,
        label: str | None = None,
    ) -> Step:
        params: dict[str, Any] = {}
        if breakpoints is not None:
            params["breakpoints"] = breakpoints
        if rates is not None:
            params["rates"] = rates
        return cls(op="ChargeTiered", params=params, label=label)

    @classmethod
    def floor(cls, value: float | None = None, *, label: str | None = None) -> Step:
        params: dict[str, Any] = {}
        if value is not None:
            params["value"] = value
        return cls(op="Floor", params=params, label=label)

    @classmethod
    def cap(cls, value: float | None = None, *, label: str | None = None) -> Step:
        params: dict[str, Any] = {}
        if value is not None:
            params["value"] = value
        return cls(op="Cap", params=params, label=label)
```

### 4.4 ProductSpec Data Structure

```python
@dataclass(slots=True)
class ProductSpec:
    """Declarative product specification for model validation.

    A ProductSpec defines the expected structure of a rollforward model.
    It is authored by the product or validation team and stored as a
    version-controlled YAML file alongside the model code.
    """
    name: str
    steps: list[Step]
    version: str = "1.0.0"
    description: str = ""
    states: list[str] | None = None  # None means single-state

    # Validation strictness
    allow_extra_steps: bool = True     # Model may have steps not in spec
    allow_reordering: bool = False     # Steps must appear in spec order

    @classmethod
    def from_yaml(cls, path: str | Path) -> ProductSpec:
        """Load a ProductSpec from a YAML file."""
        ...

    def to_yaml(self, path: str | Path) -> None:
        """Serialize a ProductSpec to a YAML file."""
        ...

    def fingerprint(self) -> str:
        """Return SHA-256 of the spec's canonical form."""
        ...
```

### 4.5 YAML File Format

Product specs are stored as YAML files that can be version-controlled, reviewed, and shared between teams.

```yaml
# specs/universal_life_v3.2.yaml
name: "Universal Life v3.2"
version: "3.2.0"
description: >
  Standard UL with monthly COI deduction on net amount at risk,
  percentage-based admin charge, interest crediting at declared rate,
  and non-negative AV floor.

states: null  # single-state rollforward

allow_extra_steps: true
allow_reordering: false

steps:
  - op: Add
    label: "Premium deposit"

  - op: DeductNar
    label: "COI on net amount at risk"
    params:
      has_death_benefit: true

  - op: Charge
    label: "Monthly admin charge"

  - op: Grow
    label: "Interest crediting"

  - op: Floor
    label: "Non-negative AV constraint"
    params:
      value: 0.0
```

Multi-state example:

```yaml
# specs/va_gmdb_v2.1.yaml
name: "Variable Annuity with GMDB v2.1"
version: "2.1.0"
description: "VA with separate account and GMDB ratchet guarantee."

states: ["av", "guarantee"]

allow_extra_steps: true
allow_reordering: false

steps:
  - op: Add
    target: av
    label: "Premium deposit"

  - op: Charge
    target: av
    label: "M&E charge"

  - op: Grow
    target: av
    label: "Fund return"

  - op: Floor
    target: av
    params:
      value: 0.0

  - op: RatchetTo
    target: guarantee
    params:
      other_state: "av"
    label: "GMDB high-water mark"

  - op: Grow
    target: guarantee
    label: "Roll-up rate"
```

---

## 5. Validation API (`validate_against`)

### 5.1 Usage

```python
result = rf.validate_against(spec)

# Quick check
if result.passed:
    print("Model matches product spec.")
else:
    print(result)
```

### 5.2 Validation Result Data Structure

```python
@dataclass(slots=True)
class StepMatch:
    """Result of matching a single spec step against the model."""
    spec_index: int
    spec_step: Step
    model_index: int | None       # None if not found
    model_step: CanonicalStep | None
    status: Literal["match", "param_mismatch", "missing"]
    details: str = ""

@dataclass(slots=True)
class ExtraStep:
    """A model step that does not appear in the spec."""
    model_index: int
    model_step: CanonicalStep
    severity: Literal["info", "warning"]
    note: str = ""

@dataclass(slots=True)
class ValidationResult:
    """Complete result of validating a model against a product spec."""
    passed: bool
    spec_name: str
    spec_version: str
    spec_fingerprint: str
    model_fingerprint: str
    step_matches: list[StepMatch]
    extra_steps: list[ExtraStep]
    order_preserved: bool

    def summary(self) -> str:
        """Human-readable summary for audit reports."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serializable form for audit trail storage."""
        ...

    def __str__(self) -> str:
        return self.summary()
```

### 5.3 Validation Logic

The algorithm performs an **ordered subsequence match** when `allow_reordering=False` (the default):

1. Walk through spec steps in order.
2. For each spec step, find the next model step (from current position forward) whose `op` matches.
3. If found, compare parameters at the appropriate constraint level.
4. If not found, mark as `missing`.
5. Any model steps not matched to a spec step are reported as `extra_steps`.

When `allow_reordering=True`, the algorithm uses a greedy best-match (still by op type, then by params), ignoring position.

**Parameter matching rules:**

- If the spec step has `params: {}` (type-only constraint), any model step of the same `op` matches.
- If the spec step has `params: {"has_death_benefit": true}`, the model step must have that structural property.
- If the spec step has `params: {"value": 0.0}`, the model step must have that exact constant value.
- Float comparison uses a configurable tolerance (default: `1e-12`) for values like breakpoints and rates.

### 5.4 Example Output

```python
spec = ProductSpec("Universal Life v3.2", steps=[
    Step.add(label="Premium deposit"),
    Step.deduct_nar(has_death_benefit=True, label="COI"),
    Step.charge(label="Admin charge"),
    Step.grow(label="Interest crediting"),
    Step.floor(0, label="Non-negative AV"),
])

result = rf.validate_against(spec)
print(result)
```

When the model matches:

```
Validation: PASSED
Spec:  Universal Life v3.2 (v3.2.0)  fingerprint: sha256:e4f7...
Model: fingerprint: sha256:a1b2...

  Spec Step                      Model Step         Status
  ---------------------------    ----------------   ------
  1. Add (Premium deposit)       1. Add             Match
  2. DeductNar (COI)             2. DeductNar       Match
  3. Charge (Admin charge)       3. Charge          Match
  4. Grow (Interest crediting)   4. Grow            Match
  5. Floor=0 (Non-negative AV)   5. Floor=0         Match

Step order: preserved
Extra model steps: none
```

When the model has issues:

```
Validation: FAILED
Spec:  Universal Life v3.2 (v3.2.0)  fingerprint: sha256:e4f7...
Model: fingerprint: sha256:c9d8...

  Spec Step                      Model Step         Status
  ---------------------------    ----------------   ----------
  1. Add (Premium deposit)       1. Add             Match
  2. DeductNar (COI)             --                 MISSING
  3. Charge (Admin charge)       2. Charge          Match
  4. Grow (Interest crediting)   3. Grow            Match
  5. Floor=0 (Non-negative AV)   4. Floor=0         Match

Step order: preserved
Extra model steps:
  [warning] Model step 5: Subtract -- not in spec

Findings:
  - FAIL: Spec step 2 (DeductNar) not found in model. Expected COI deduction
    on net amount at risk. The model may be using a flat deduction instead.
  - WARNING: Model contains a Subtract step not present in the spec.
    Review whether this is an intentional addition.
```

### 5.5 Handling Labels

Labels are **excluded from matching** but **included in the output** for human readability. This means:

- A model step labeled "Monthly admin fee" matches a spec step labeled "Admin charge" as long as both are `Charge`.
- The validation output shows both labels side by side so the reviewer can spot naming discrepancies.

If label matching is desired (e.g., for strict organizational standards), it can be enabled:

```python
result = rf.validate_against(spec, match_labels=True)
```

When enabled, label mismatches are reported as `info`-level findings, never failures. Labels affect documentation, not correctness.

### 5.6 Handling Extra Steps

When `allow_extra_steps=True` (default), extra model steps are reported with severity levels:

| Extra Step Type | Severity | Rationale |
|----------------|----------|-----------|
| `.floor(0)` | info | Defensive constraint, commonly added |
| `.cap(...)` | info | Protective limit, not harmful |
| `.lapse_if_zero()` | info | Standard control flow |
| `.capture(...)` | info | Observability only, does not change computation |
| Any other step | warning | Could indicate spec drift or unauthorized change |

When `allow_extra_steps=False`, any extra step causes a failure.

---

## 6. Model-vs-Model Diffing

### 6.1 Usage

```python
diff = rf_q4.diff(rf_q3)
print(diff)
```

Or as a standalone function for comparing serialized specs:

```python
from gaspatchio_core.rollforward import diff_models

diff = diff_models(rf_q4, rf_q3)
# or from canonical dicts:
diff = diff_models(canonical_q4, canonical_q3)
```

### 6.2 Diff Result Data Structure

```python
@dataclass(slots=True)
class StepDiff:
    """A single difference between two model versions."""
    kind: Literal["added", "removed", "modified", "moved"]
    position_left: int | None    # index in left (old) model, None if added
    position_right: int | None   # index in right (new) model, None if removed
    step_left: CanonicalStep | None
    step_right: CanonicalStep | None
    param_changes: list[ParamChange] = field(default_factory=list)

@dataclass(slots=True)
class ParamChange:
    """A single parameter that changed between versions."""
    param_name: str
    old_value: Any
    new_value: Any

@dataclass(slots=True)
class ModelDiff:
    """Complete structural diff between two rollforward models."""
    left_fingerprint: str
    right_fingerprint: str
    identical: bool
    step_diffs: list[StepDiff]
    state_diffs: list[str]  # states added/removed

    def summary(self) -> str:
        """Human-readable diff summary."""
        ...

    def __str__(self) -> str:
        return self.summary()
```

### 6.3 Diff Algorithm

The diff uses a **longest common subsequence (LCS)** algorithm on step `op` types to align steps between versions, then compares parameters for aligned steps:

1. Compute LCS of step `op` sequences from both models.
2. Steps in LCS that have identical params: **unchanged** (not reported).
3. Steps in LCS that have different params: **modified**.
4. Steps in the left model not in LCS: **removed**.
5. Steps in the right model not in LCS: **added**.
6. If a step's `op` appears in both removed and added lists at different positions, check if it is a **move** (same op and params, different position).

### 6.4 Example Output

```python
diff = rf_q4.diff(rf_q3)
print(diff)
```

```
Model Diff
  Left:  sha256:a1b2...  (5 steps)
  Right: sha256:c9d8...  (6 steps)

  Step  Change     Details
  ----  ---------  ----------------------------------------
  1     unchanged  Add
  2     unchanged  DeductNar (has_death_benefit=true)
  3     modified   Charge
                     breakpoints: [0, 25000, 100000] -> [0, 25000, 75000, 150000]
                     rates: [0.0025, 0.0020, 0.0015] -> [0.0025, 0.0022, 0.0018, 0.0012]
  4     unchanged  Grow
  5     unchanged  Floor (value=0.0)
  --    added      Cap (value=500000.0)   [new step 6]
```

### 6.5 Handling Step Reordering

Step reordering is semantically significant -- charging before growing produces different results than growing before charging. The diff explicitly calls this out:

```
  Step  Change     Details
  ----  ---------  ----------------------------------------
  3     moved      Charge: position 3 -> 4
  4     moved      Grow: position 4 -> 3
                   WARNING: Grow now executes BEFORE Charge.
                   This changes the computation order.
```

The warning is generated whenever two adjacent steps swap positions, because this is the most common reordering mistake and has direct computational impact.

---

## 7. Integration with `.explain()`

The `explain()` output from Section 7 of the rollforward design doc is the **human-readable view** of the canonical form. The relationship is:

| Feature | Data Source | Audience |
|---------|------------|----------|
| `.explain()` | Full builder state (column names, labels, formulas) | Actuary reviewing their own model |
| `.canonical()` | Stripped structural form (ops, params, targets) | Machine comparison |
| `.fingerprint()` | SHA-256 of canonical form | Audit trail, change control |
| `.validate_against(spec)` | Canonical vs ProductSpec | Validation actuary |
| `.diff(other)` | Canonical vs canonical | Quarterly model change review |

The `explain()` output can optionally annotate which steps match the spec:

```python
print(rf.explain(spec=spec))
```

```
Rollforward: initial=av_init, 5 steps, 360 periods
Spec: Universal Life v3.2 (v3.2.0)

  Step  Operation                    Label                Formula                                       Spec
  ----  -------------------------    -------------------  ----------------------------------------      -----
  1     Add(premium)                 Premium income       av[t] = av[t] + premium[t]                    1/5
  2     DeductNAR(coi_rate, sa)      COI                  av[t] = av[t] - coi_rate[t] x max(0, sa-av)   2/5
  3     Charge(admin_rate)           Admin charge         av[t] = av[t] x (1 - admin_rate[t])           3/5
  4     Grow(interest_rate)          Interest credit      av[t] = av[t] x (1 + interest_rate[t])        4/5
  5     Floor(0)                     Non-negative         av[t] = max(av[t], 0)                         5/5

Spec match: 5/5 steps matched, 0 extra.  PASSED
```

---

## 8. Practical Concerns

### 8.1 Where Do Product Specs Live?

Product specs live as **YAML files in a `specs/` directory** alongside the model code, version-controlled in git:

```
my-model-repo/
  models/
    ul_model.py
    va_model.py
  specs/
    universal_life_v3.2.yaml
    variable_annuity_gmdb_v2.1.yaml
  tests/
    test_ul_spec_validation.py
```

This means:
- Specs are code-reviewed alongside model changes.
- Git blame shows who changed the spec and when.
- CI can run `rf.validate_against(spec)` as a test.

### 8.2 Who Creates the Specs?

| Team | Creates | Reviews |
|------|---------|---------|
| **Product team** | Initial spec from product filing | Model team reviews for implementability |
| **Validation team** | "Golden" reference spec for sign-off | Product team reviews for accuracy |
| **Model team** | Neither (they consume specs) | Both product and validation specs |

In practice, the **validation team** authors the golden spec from the product specification document. The model developer builds the model, then runs `validate_against()` as a self-check before submitting for validation review.

The validation actuary runs `validate_against()` independently, comparing the submitted model against their own spec. This is a two-party check: the model team and validation team each maintain their spec independently.

### 8.3 Specs as Python Objects vs. YAML Files

Both are supported. The Python API is convenient for inline tests and notebooks:

```python
# In a test file
def test_ul_model_matches_spec():
    spec = ProductSpec.from_yaml("specs/universal_life_v3.2.yaml")
    rf = build_ul_model(af)
    result = rf.validate_against(spec)
    assert result.passed, result.summary()
```

```python
# In a notebook for ad-hoc checking
spec = ProductSpec("Quick check", steps=[
    Step.add(),
    Step.deduct_nar(has_death_benefit=True),
    Step.charge(),
    Step.grow(),
    Step.floor(0),
])
rf.validate_against(spec)
```

YAML is the canonical storage format for specs that are shared, version-controlled, and used in CI.

### 8.4 CI Integration

A typical CI pipeline step:

```yaml
# .github/workflows/model-validation.yml
- name: Validate models against product specs
  run: |
    uv run pytest tests/test_spec_validation.py -v
```

```python
# tests/test_spec_validation.py
import pytest
from pathlib import Path
from gaspatchio_core.rollforward import ProductSpec

SPEC_DIR = Path("specs")

@pytest.mark.parametrize("spec_file", SPEC_DIR.glob("*.yaml"))
def test_model_matches_spec(spec_file, build_model):
    """Every spec file has a corresponding model that must match."""
    spec = ProductSpec.from_yaml(spec_file)
    model_name = spec_file.stem  # e.g., "universal_life_v3.2"
    rf = build_model(model_name)
    result = rf.validate_against(spec)
    assert result.passed, f"Model {model_name} failed spec validation:\n{result.summary()}"
```

### 8.5 Fingerprint in Audit Reports

For regulatory submissions:

```python
record = rf.fingerprint_record()
audit_entry = {
    "submission_id": "2026-Q1-UL-001",
    "model_fingerprint": record.fingerprint,
    "spec_fingerprint": spec.fingerprint(),
    "validation_result": result.to_dict(),
    "validated_at": record.timestamp,
    "validated_by": "jane.smith@company.com",
}
# Store in audit database or append to audit log
```

---

## 9. Implementation Phases

### Phase 1 (GSP-86 scope -- ship with the rollforward builder)

- `rf.canonical()` -- returns the canonical dict
- `rf.fingerprint()` -- returns the SHA-256
- `rf.explain()` -- already in scope per the design doc

These are trivial to implement because the builder already holds the step list internally. Canonical form is just a filtered projection of the builder's state.

### Phase 2 (GSP-87 scope -- validation and diffing)

- `ProductSpec` dataclass with factory methods
- `ProductSpec.from_yaml()` / `.to_yaml()`
- `rf.validate_against(spec)` with `ValidationResult`
- `rf.diff(other)` with `ModelDiff`
- Integration with `explain(spec=...)` annotated output
- `rf.fingerprint_record()` for audit trail

### Phase 3 (future -- advanced features)

- Spec inheritance: `ProductSpec.extend(base_spec, additional_steps=[...])`
- Spec composition for riders: `combined = base_spec.with_rider(gmdb_spec)`
- Historical fingerprint registry (which fingerprints were in production when)
- Diff visualization for notebooks (side-by-side with color highlighting)
- Spec generation from a model: `spec = ProductSpec.from_model(rf)` as a bootstrapping tool

---

## 10. Edge Cases and Design Decisions

### 10.1 Conditional Steps

Steps like `.add_if(condition, amount)` are a different op type (`AddIf`) from `.add(amount)`. A spec that requires `Step.add()` does NOT match a model that uses `.add_if()`. This is intentional -- conditional logic is a structural difference that the validation actuary needs to know about.

If the spec wants to allow either, it should include both:

```yaml
steps:
  - op: Add
    label: "Premium (unconditional)"
  # OR
  - op: AddIf
    label: "Premium (conditional on status)"
```

A future enhancement could add `Step.any_of([Step.add(), Step.add_if()])` for flexible matching.

### 10.2 Multi-State Step Ordering

For multi-state rollforwards, the step order in the spec must match the declared order in the model (which includes `.on()` target switches). The target state is part of the canonical form, so:

```yaml
steps:
  - op: Add
    target: av
  - op: Charge
    target: av
  - op: Grow
    target: av
  - op: RatchetTo
    target: guarantee
    params:
      other_state: av
```

This correctly enforces that the ratchet happens after AV growth.

### 10.3 Floating-Point Comparison

When specs include exact float values (e.g., `Floor(value=0.0)`), comparison uses `math.isclose(a, b, rel_tol=1e-12)`. This avoids false negatives from floating-point representation differences while still catching meaningful value changes.

For breakpoints and rates in tiered operations, element-wise comparison is used with the same tolerance.

### 10.4 Empty Params vs. Missing Params

- Spec step with `params: {}` means "any params are acceptable" (type-only match).
- Spec step with `params: {"value": 0.0}` means "this specific value is required."
- Model step with no constant params (e.g., `Charge` which only has a rate input) always has `params: {}` in canonical form.

This means `Step.charge()` (no params in spec) always matches any `Charge` step in the model, which is the correct behavior -- the validation actuary cannot constrain the *value* of a rate column, only its structural role.

---

## 11. Summary

| Capability | API | Returns | Phase |
|-----------|-----|---------|-------|
| Canonical form | `rf.canonical()` | `dict` | 1 |
| Fingerprint | `rf.fingerprint()` | `"sha256:..."` | 1 |
| Explain | `rf.explain()` | Formatted string | 1 |
| Product spec (Python) | `ProductSpec(name, steps)` | `ProductSpec` | 2 |
| Product spec (YAML) | `ProductSpec.from_yaml(path)` | `ProductSpec` | 2 |
| Validate against spec | `rf.validate_against(spec)` | `ValidationResult` | 2 |
| Model diff | `rf.diff(other)` | `ModelDiff` | 2 |
| Annotated explain | `rf.explain(spec=spec)` | Formatted string | 2 |
| Audit record | `rf.fingerprint_record()` | `FingerprintRecord` | 2 |
| Spec inheritance | `spec.with_rider(rider_spec)` | `ProductSpec` | 3 |
| Spec from model | `ProductSpec.from_model(rf)` | `ProductSpec` | 3 |

The key insight: because the rollforward is **declarative data** compiled from a method-chain builder, all of these capabilities come essentially for free. The builder already holds the complete step list. The canonical form is a filtered projection. The fingerprint is a hash. The diff is LCS on two lists. The validation is subsequence matching. None of this is possible with imperative Python loops.
