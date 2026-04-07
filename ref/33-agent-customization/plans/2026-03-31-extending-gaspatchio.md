# Extending Gaspatchio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a tested `extending-gaspatchio` skill, three registry improvements, and cross-references so agents can safely extend Gaspatchio.

**Architecture:** The skill files (SKILL.md + 3 references) already exist as drafts from brainstorming. This plan finishes the registry code changes, adds tests, adds cross-references, and commits everything.

**Tech Stack:** Python 3.12+, Polars, pytest, gaspatchio_core accessor registry

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `bindings/python/gaspatchio_core/frame/registry.py` | Modify | Idempotent registration, validation, `list_registered_accessors()` |
| `bindings/python/tests/test_registry.py` | Create | Tests for registry improvements |
| `skills/extending-gaspatchio/SKILL.md` | Exists (draft) | Review and finalize |
| `skills/extending-gaspatchio/references/accessor-template.md` | Exists (draft) | Review and finalize |
| `skills/extending-gaspatchio/references/performance-ladder.md` | Exists (draft) | Review and finalize |
| `skills/extending-gaspatchio/references/anti-patterns.md` | Exists (draft) | Review and finalize |
| `AGENTS.md` | Modify | Add extending section |
| `skills/model-building/SKILL.md` | Modify | Add routing note |

---

### Task 1: Registry — Idempotent Same-Class Registration

**Files:**
- Modify: `bindings/python/gaspatchio_core/frame/registry.py:37-51`
- Create: `bindings/python/tests/test_registry.py`

- [ ] **Step 1: Write failing tests for idempotent registration**

Create `bindings/python/tests/test_registry.py`:

```python
"""Tests for accessor registry improvements."""

from gaspatchio_core.accessors.base import BaseColumnAccessor, BaseFrameAccessor
from gaspatchio_core.frame.registry import (
    _ACCESSOR_REGISTRY,
    register_accessor,
)
import pytest


class _TestColumnAccessor(BaseColumnAccessor):
    def __init__(self, proxy):
        super().__init__(proxy)


class _TestColumnAccessor2(BaseColumnAccessor):
    def __init__(self, proxy):
        super().__init__(proxy)


class _TestFrameAccessor(BaseFrameAccessor):
    def __init__(self, frame):
        super().__init__(frame)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Remove test accessors from registry after each test."""
    yield
    for name in list(_ACCESSOR_REGISTRY.keys()):
        if name.startswith("_test"):
            del _ACCESSOR_REGISTRY[name]


class TestIdempotentRegistration:
    def test_same_class_reregistration_succeeds(self):
        """Re-registering the same class with same name+kind should succeed silently."""
        register_accessor("_test_idem", kind="column")(_TestColumnAccessor)
        # Should not raise
        register_accessor("_test_idem", kind="column")(_TestColumnAccessor)

    def test_different_class_same_name_raises(self):
        """Registering a different class with same name+kind should raise ValueError."""
        register_accessor("_test_conflict", kind="column")(_TestColumnAccessor)
        with pytest.raises(ValueError, match="already registered"):
            register_accessor("_test_conflict", kind="column")(_TestColumnAccessor2)

    def test_same_name_different_kind_succeeds(self):
        """Same name but different kind should succeed."""
        register_accessor("_test_kinds", kind="column")(_TestColumnAccessor)
        register_accessor("_test_kinds", kind="frame")(_TestFrameAccessor)
        assert "column" in _ACCESSOR_REGISTRY["_test_kinds"]
        assert "frame" in _ACCESSOR_REGISTRY["_test_kinds"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd bindings/python && uv run pytest tests/test_registry.py::TestIdempotentRegistration -v`
Expected: `test_same_class_reregistration_succeeds` FAILS (raises ValueError)

- [ ] **Step 3: Implement idempotent registration**

In `bindings/python/gaspatchio_core/frame/registry.py`, replace the decorator inner function:

```python
    def decorator(cls: Type[T]) -> Type[T]:
        if name not in _ACCESSOR_REGISTRY:
            _ACCESSOR_REGISTRY[name] = {}

        if kind in _ACCESSOR_REGISTRY[name]:
            existing = _ACCESSOR_REGISTRY[name][kind]
            if existing is cls:
                return cls  # Same class re-registered — idempotent
            raise ValueError(
                f"Accessor '{name}' (kind='{kind}') already registered by "
                f"{existing.__qualname__}. Cannot re-register with "
                f"{cls.__qualname__}."
            )

        _ACCESSOR_REGISTRY[name][kind] = cls
        return cls
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd bindings/python && uv run pytest tests/test_registry.py::TestIdempotentRegistration -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/frame/registry.py bindings/python/tests/test_registry.py
git commit -m "feat: make register_accessor idempotent for same-class re-registration"
```

---

### Task 2: Registry — Registration Validation

**Files:**
- Modify: `bindings/python/gaspatchio_core/frame/registry.py:37-51`
- Modify: `bindings/python/tests/test_registry.py`

- [ ] **Step 1: Write failing tests for validation**

Add to `bindings/python/tests/test_registry.py`:

```python
class _NotAnAccessor:
    def __init__(self, proxy):
        pass


class TestRegistrationValidation:
    def test_column_accessor_must_inherit_base(self):
        """Column accessor must inherit from BaseColumnAccessor."""
        with pytest.raises(TypeError, match="must inherit from BaseColumnAccessor"):
            register_accessor("_test_bad_col", kind="column")(_NotAnAccessor)

    def test_frame_accessor_must_inherit_base(self):
        """Frame accessor must inherit from BaseFrameAccessor."""
        with pytest.raises(TypeError, match="must inherit from BaseFrameAccessor"):
            register_accessor("_test_bad_frame", kind="frame")(_NotAnAccessor)

    def test_valid_column_accessor_passes(self):
        """Valid column accessor should register without error."""
        register_accessor("_test_valid_col", kind="column")(_TestColumnAccessor)
        assert "_test_valid_col" in _ACCESSOR_REGISTRY

    def test_valid_frame_accessor_passes(self):
        """Valid frame accessor should register without error."""
        register_accessor("_test_valid_frame", kind="frame")(_TestFrameAccessor)
        assert "_test_valid_frame" in _ACCESSOR_REGISTRY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd bindings/python && uv run pytest tests/test_registry.py::TestRegistrationValidation -v`
Expected: `test_column_accessor_must_inherit_base` and `test_frame_accessor_must_inherit_base` FAIL (no TypeError raised)

- [ ] **Step 3: Add validation to register_accessor**

In `bindings/python/gaspatchio_core/frame/registry.py`, add validation at the top of the `decorator` function, before the idempotent check. Add the import at the top of the file:

```python
def register_accessor(
    name: str, *, kind: str = "column"
) -> Callable[[Type[T]], Type[T]]:
    """Decorator factory to register an accessor class.

    Parameters
    ----------
    name : str
        The name under which the accessor should be registered (e.g., 'date').
    kind : str
        The type of accessor, either "frame" or "column". Defaults to 'column'.

    Returns
    -------
    Callable
        A decorator that registers the class.

    Raises
    ------
    ValueError
        If the kind is not 'frame' or 'column', or if a different accessor
        with the same name and kind is already registered.
    TypeError
        If the class does not inherit from the correct base class.

    """
    if kind not in ("frame", "column"):
        msg = "Accessor kind must be 'frame' or 'column'"
        raise ValueError(msg)

    def decorator(cls: Type[T]) -> Type[T]:
        from gaspatchio_core.accessors.base import BaseColumnAccessor, BaseFrameAccessor

        expected_base = BaseFrameAccessor if kind == "frame" else BaseColumnAccessor
        if not issubclass(cls, expected_base):
            msg = (
                f"Accessor '{name}' (kind='{kind}') must inherit from "
                f"{expected_base.__name__}. Got {cls.__qualname__} which "
                f"inherits from {', '.join(b.__name__ for b in cls.__bases__)}."
            )
            raise TypeError(msg)

        if name not in _ACCESSOR_REGISTRY:
            _ACCESSOR_REGISTRY[name] = {}

        if kind in _ACCESSOR_REGISTRY[name]:
            existing = _ACCESSOR_REGISTRY[name][kind]
            if existing is cls:
                return cls
            raise ValueError(
                f"Accessor '{name}' (kind='{kind}') already registered by "
                f"{existing.__qualname__}. Cannot re-register with "
                f"{cls.__qualname__}."
            )

        _ACCESSOR_REGISTRY[name][kind] = cls
        return cls

    return decorator
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd bindings/python && uv run pytest tests/test_registry.py -v`
Expected: All tests PASS (both TestIdempotentRegistration and TestRegistrationValidation)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/frame/registry.py bindings/python/tests/test_registry.py
git commit -m "feat: validate accessor base class inheritance at registration time"
```

---

### Task 3: Registry — `list_registered_accessors()` Helper

**Files:**
- Modify: `bindings/python/gaspatchio_core/frame/registry.py`
- Modify: `bindings/python/tests/test_registry.py`

- [ ] **Step 1: Write failing test**

Add to `bindings/python/tests/test_registry.py`:

```python
from gaspatchio_core.frame.registry import list_registered_accessors


class TestListRegisteredAccessors:
    def test_returns_dict(self):
        """list_registered_accessors should return a dict."""
        result = list_registered_accessors()
        assert isinstance(result, dict)

    def test_contains_builtin_accessors(self):
        """Should include built-in accessors like finance and projection."""
        result = list_registered_accessors()
        assert "finance" in result
        assert "projection" in result
        assert "column" in result["finance"]
        assert "frame" in result["finance"]

    def test_returns_copy(self):
        """Should return a copy, not the internal registry."""
        result = list_registered_accessors()
        result["injected"] = {"column": object}
        assert "injected" not in list_registered_accessors()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd bindings/python && uv run pytest tests/test_registry.py::TestListRegisteredAccessors -v`
Expected: FAIL with `ImportError: cannot import name 'list_registered_accessors'`

- [ ] **Step 3: Implement list_registered_accessors**

Add to the end of `bindings/python/gaspatchio_core/frame/registry.py`:

```python
def list_registered_accessors() -> dict[str, dict[str, type]]:
    """Return the current accessor registry.

    Returns a shallow copy of the registry mapping accessor names to their
    registered kinds and classes.

    Returns
    -------
    dict[str, dict[str, type]]
        Registry contents. Example::

            {"finance": {"frame": FinanceFrameAccessor, "column": FinanceColumnAccessor}}

    """
    return {name: dict(kinds) for name, kinds in _ACCESSOR_REGISTRY.items()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd bindings/python && uv run pytest tests/test_registry.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `cd bindings/python && uv run pytest -x -q`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add bindings/python/gaspatchio_core/frame/registry.py bindings/python/tests/test_registry.py
git commit -m "feat: add list_registered_accessors() for registry introspection"
```

---

### Task 4: Cross-Reference — AGENTS.md

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Read the current end of AGENTS.md to find the right insertion point**

```bash
uv run python3 -c "print('ready')"
```

Read the last section of `AGENTS.md` to find where to append the new section.

- [ ] **Step 2: Add extending section to AGENTS.md**

Append this section to the end of `AGENTS.md`:

```markdown
## Extending Gaspatchio

To add custom calculations or accessor methods, use the `extending-gaspatchio` skill.
Do not write raw Python loops or `map_elements` — compose Polars expressions.
The accessor pattern (`@register_accessor` + base classes) is the primary extension mechanism.

**Performance ladder:** Before writing anything, determine if the calculation is a setup utility (Python function), a reusable column operation (column accessor), a frame-level operation (frame accessor), or a Rust kernel contribution. The skill walks through the decision tree.

**Anti-patterns:** `map_elements`, Python for-loops over policies, dict lookups per row — all cause 50-1000x slowdowns. The skill documents 7 concrete anti-patterns with correct alternatives.
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: add extending-gaspatchio section to AGENTS.md"
```

---

### Task 5: Cross-Reference — model-building Routing Note

**Files:**
- Modify: `skills/model-building/SKILL.md:34`

- [ ] **Step 1: Add routing note after the MANDATORY lookup section**

After the "MANDATORY: Look Up Before You Write" section (around line 58, after the lookup table), add:

```markdown
**Missing a method?** If the calculation you need does not exist as a built-in method, do not implement it inline with raw Python. Invoke the `extending-gaspatchio` skill to create a proper accessor. This ensures the calculation is reusable, vectorized, and follows the framework's performance patterns.
```

- [ ] **Step 2: Commit**

```bash
git add skills/model-building/SKILL.md
git commit -m "docs: add extending-gaspatchio routing note to model-building skill"
```

---

### Task 6: Finalize and Commit Skill Files

**Files:**
- Review: `skills/extending-gaspatchio/SKILL.md`
- Review: `skills/extending-gaspatchio/references/accessor-template.md`
- Review: `skills/extending-gaspatchio/references/performance-ladder.md`
- Review: `skills/extending-gaspatchio/references/anti-patterns.md`

- [ ] **Step 1: Review SKILL.md for consistency**

Read `skills/extending-gaspatchio/SKILL.md` end to end. Verify:
- Frontmatter has `name: gaspatchio-extending`
- Section order matches convention: When → Hard gate → Core content → References → Completion gate
- No TODO/TBD placeholders
- All reference file links are correct relative paths

- [ ] **Step 2: Review accessor-template.md for accuracy**

Read `skills/extending-gaspatchio/references/accessor-template.md`. Verify:
- `ColumnTypeDetector` import uses `gaspatchio_core.column.dispatch` (NOT `type_detector`)
- Template includes `_get_polars_expr()` helper
- Template includes `_parent is None` guard
- Template uses `self._proxy.name` (not `._name`)
- Docstring examples use NumPy style
- `# noqa: SLF001` and `# noqa: N806` comments present
- list.eval patterns table includes all 6 patterns
- Local accessor section has complete worked example

- [ ] **Step 3: Review performance-ladder.md for completeness**

Read `skills/extending-gaspatchio/references/performance-ladder.md`. Verify:
- Sequential dependency table exists with `accumulate`, `prospective_value`, `cumulative_survival`, `rollforward`
- Decision examples include reserve recursion and forward rate
- Level 1 table lists all existing accessor namespaces

- [ ] **Step 4: Review anti-patterns.md for correctness**

Read `skills/extending-gaspatchio/references/anti-patterns.md`. Verify:
- All 7 anti-patterns have naive code AND correct approach
- Speedup numbers are present for each

- [ ] **Step 5: Commit skill files**

```bash
git add skills/extending-gaspatchio/
git commit -m "feat: add extending-gaspatchio skill with templates, performance ladder, and anti-patterns"
```

---

### Task 7: Integration Verification

**Files:**
- All modified files from Tasks 1-6

- [ ] **Step 1: Run full Python test suite**

Run: `cd bindings/python && uv run pytest -x -q`
Expected: All tests pass, no regressions

- [ ] **Step 2: Verify registry changes work with built-in accessors**

Run:
```bash
cd bindings/python && uv run python3 -c "
from gaspatchio_core.frame.registry import list_registered_accessors
accessors = list_registered_accessors()
print(f'Registered accessors: {list(accessors.keys())}')
for name, kinds in sorted(accessors.items()):
    print(f'  {name}: {list(kinds.keys())}')
assert 'finance' in accessors
assert 'projection' in accessors
assert 'date' in accessors
assert 'excel' in accessors
print('All assertions passed.')
"
```
Expected: Lists all 5 accessor namespaces with their kinds

- [ ] **Step 3: Verify idempotent registration with built-in accessor**

Run:
```bash
cd bindings/python && uv run python3 -c "
from gaspatchio_core.frame.registry import register_accessor
from gaspatchio_core.accessors.finance import FinanceColumnAccessor
# Re-registering the same class should succeed silently
register_accessor('finance', kind='column')(FinanceColumnAccessor)
print('Idempotent re-registration: OK')
"
```
Expected: Prints "OK" without error

- [ ] **Step 4: Verify validation catches bad accessor**

Run:
```bash
cd bindings/python && uv run python3 -c "
from gaspatchio_core.frame.registry import register_accessor

class BadAccessor:
    pass

try:
    register_accessor('_test_bad', kind='column')(BadAccessor)
    print('ERROR: Should have raised TypeError')
except TypeError as e:
    print(f'Validation caught: {e}')
    print('Validation: OK')
"
```
Expected: Prints "Validation caught: ..." and "OK"

- [ ] **Step 5: Verify skill files are in expected locations**

Run:
```bash
ls -la skills/extending-gaspatchio/SKILL.md skills/extending-gaspatchio/references/
```
Expected: SKILL.md and 3 reference files exist

- [ ] **Step 6: Commit any final fixes from verification**

If any issues were found and fixed:
```bash
git add -A
git commit -m "fix: address issues found during integration verification"
```
