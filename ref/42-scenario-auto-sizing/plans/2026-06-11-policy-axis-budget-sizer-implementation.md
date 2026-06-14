# Policy-Axis Budget Sizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Size `run_aggregated` / `run_to_parquet` policy batches to the fastest batch that
fits the cgroup-aware memory budget, deleting the hardcoded 384 MB working-set cap and
unifying the two duplicated sizers onto one shared `size_to_budget`.

**Architecture:** The policy axis is monotonic in batch size (measured 1K/10K/100K — no
cross-join, no U-shape), so "largest B that fits the budget" is speed-optimal. A new pure
function `size_to_budget(per_cell, n)` computes that B from a measured per-policy cost and
the existing `memory_budget_bytes` helper, with `safety_margin` (1.3) guarding seed
mis-estimates. Both drivers keep their seed measurement and delegate the arithmetic.

**Tech Stack:** Python 3.12, Polars, pytest, mypy/pyright, uv. Spec:
`ref/42-scenario-auto-sizing/specs/2026-06-11-policy-axis-budget-sizer-design.md`.

**All commands run from `bindings/python` with `uv run`. Signed conventional commits, no
AI-assistant trailer.**

---

## File Structure

- `gaspatchio_core/scenarios/_auto_batch.py` — **add** `size_to_budget` (the one new unit).
- `gaspatchio_core/scenarios/_aggregated.py` — `_resolve_auto` delegates to `size_to_budget`;
  **delete** `_WORKING_SET_TARGET_BYTES`.
- `gaspatchio_core/scenarios/_spill.py` — `run_to_parquet` auto path delegates to `size_to_budget`.
- `gaspatchio_core/scenarios/_memory.py` — **delete** dead `SizingDefaults` fields.
- Tests: `tests/scenarios/test_auto_batch.py`, `test_run_aggregated.py`, `test_spill.py`,
  `test_memory.py`.

---

## Task 1: `size_to_budget` pure sizer + unit tests

**Files:**
- Modify: `gaspatchio_core/scenarios/_auto_batch.py`
- Test: `tests/scenarios/test_auto_batch.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/scenarios/test_auto_batch.py`:

```python
import pytest


def _patch_budget(monkeypatch, budget_bytes):
    from gaspatchio_core.scenarios import _auto_batch

    monkeypatch.setattr(_auto_batch, "memory_budget_bytes", lambda _f: budget_bytes)


def test_size_to_budget_clamps_to_n_items(monkeypatch):
    from gaspatchio_core.scenarios._auto_batch import size_to_budget

    _patch_budget(monkeypatch, 10_000_000_000)  # huge budget
    assert size_to_budget(1000, 50) == 50  # whole portfolio fits in one batch


def test_size_to_budget_is_budget_bound(monkeypatch):
    from gaspatchio_core.scenarios._auto_batch import size_to_budget

    # budget=1300, per_cell=100, margin=1.3 -> denom=130 -> B=10
    _patch_budget(monkeypatch, 1300)
    assert size_to_budget(100, 1000, safety_margin=1.3) == 10


def test_size_to_budget_margin_shrinks_b(monkeypatch):
    from gaspatchio_core.scenarios._auto_batch import size_to_budget

    _patch_budget(monkeypatch, 1000)
    assert size_to_budget(100, 1000, safety_margin=1.0) == 10
    assert size_to_budget(100, 1000, safety_margin=2.0) == 5


def test_size_to_budget_runs_single_item_that_fits_raw(monkeypatch):
    from gaspatchio_core.scenarios._auto_batch import size_to_budget

    # one 100-byte item fits the raw budget of 120, but 100*1.3=130 > 120 -> still B=1
    _patch_budget(monkeypatch, 120)
    assert size_to_budget(100, 10, safety_margin=1.3) == 1


def test_size_to_budget_raises_when_one_item_exceeds_raw(monkeypatch):
    from gaspatchio_core.scenarios import _memory
    from gaspatchio_core.scenarios._auto_batch import size_to_budget

    _patch_budget(monkeypatch, 50)  # one 100-byte item exceeds even the raw budget
    with pytest.raises(_memory.IrreducibleCellError):
        size_to_budget(100, 10)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/scenarios/test_auto_batch.py -q`
Expected: FAIL — `ImportError: cannot import name 'size_to_budget'`.

- [ ] **Step 3: Implement `size_to_budget`**

In `gaspatchio_core/scenarios/_auto_batch.py`, add the function (after `memory_budget_bytes`)
and extend `__all__`:

```python
def size_to_budget(
    per_cell_bytes: int,
    n_items: int,
    *,
    target_memory_fraction: float = _memory.DEFAULTS.target_memory_fraction,
    safety_margin: float = _memory.DEFAULTS.safety_margin,
) -> int:
    """Largest batch size in ``[1, n_items]`` whose predicted peak fits the budget.

    The policy axis is linear (no cross-join): a batch of ``B`` items peaks at
    ~``per_cell_bytes * B``. We require ``predicted * safety_margin <= budget``, so
    ``B = budget // (per_cell_bytes * safety_margin)``, clamped to ``[1, n_items]``.

    The margin governs sizing above one item; a single item that fits the RAW budget
    always runs (nothing smaller exists). Raises :class:`IrreducibleCellError` only
    when one item exceeds even the raw budget.
    """
    budget = memory_budget_bytes(target_memory_fraction)
    per_cell = max(1, int(per_cell_bytes))
    denom = max(1, int(per_cell * safety_margin))
    b = budget // denom
    if b >= 1:
        return int(min(b, n_items))
    if budget // per_cell >= 1:
        return 1  # one item fits the raw budget; run it (margin can't be honoured)
    msg = (
        "one item's projection exceeds the memory budget: even batch_size=1 does not "
        "fit. Reduce the horizon/columns, raise target_memory_fraction, or run on a "
        "box/cgroup with more memory."
    )
    raise _memory.IrreducibleCellError(msg)
```

Change the export line to:

```python
__all__ = ["memory_budget_bytes", "process_rss_bytes", "size_to_budget"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/scenarios/test_auto_batch.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_auto_batch.py tests/scenarios/test_auto_batch.py
git commit -m "feat(scenarios): add size_to_budget — fastest policy batch that fits the budget"
```

---

## Task 2: `run_aggregated` delegates to `size_to_budget`; delete the 384 MB cap

**Files:**
- Modify: `gaspatchio_core/scenarios/_aggregated.py`
- Test: `tests/scenarios/test_run_aggregated.py`

- [ ] **Step 1: Replace the old cap test with budget-based tests**

In `tests/scenarios/test_run_aggregated.py`, **delete** the existing
`test_auto_sizes_from_working_set_target_and_is_equivalent` function (it patches the
soon-deleted `_WORKING_SET_TARGET_BYTES`). Replace it with:

```python
def test_auto_single_batch_when_budget_is_generous(monkeypatch) -> None:
    """Cap removed: a generous budget resolves 'auto' to a single batch (B == n)."""
    from gaspatchio_core.scenarios import _auto_batch

    mp = pl.DataFrame({"value": [float(i) for i in range(1, 21)]})  # 20 policies
    monkeypatch.setattr(_auto_batch, "memory_budget_bytes", lambda _f: 10_000_000_000)
    res = run_aggregated(
        _toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size="auto"
    )
    assert res.batch_size == 20  # whole portfolio fits -> one batch


def test_auto_batches_when_sizer_returns_small_b(monkeypatch) -> None:
    """When the sizer returns a small B, 'auto' batches and stays equivalent to full."""
    import gaspatchio_core.scenarios._aggregated as agg

    mp = pl.DataFrame({"value": [float(i) for i in range(1, 21)]})  # 20 policies
    full = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size=20)
    monkeypatch.setattr(agg, "size_to_budget", lambda *a, **k: 5)
    auto = run_aggregated(
        _toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size="auto"
    )
    assert auto.batch_size == 5  # uses the sizer's result
    assert np.allclose(auto.cf, full.cf, atol=1e-6)  # 4 batches == full
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `uv run pytest tests/scenarios/test_run_aggregated.py -q`
Expected: FAIL — `test_auto_batches_when_sizer_returns_small_b` errors on
`monkeypatch.setattr(agg, "size_to_budget", ...)` (`agg` has no `size_to_budget` yet).

- [ ] **Step 3: Rewrite `_resolve_auto`, delete the cap, swap the import**

In `gaspatchio_core/scenarios/_aggregated.py`:

(a) **Swap the import** — replace `from gaspatchio_core.scenarios import _memory` with:

```python
from gaspatchio_core.scenarios._auto_batch import size_to_budget
```

(b) **Delete** the constant block (lines defining `_WORKING_SET_TARGET_BYTES` and its
two comment lines).

(c) **Replace** the whole `_resolve_auto` function body with:

```python
def _resolve_auto(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,
) -> tuple[int, ActuarialFrame, pl.DataFrame, int]:
    """Run one seed batch (~10% of policies, >=1), measure per-policy peak, return B.

    The seed batch is REAL work — its ActuarialFrame and collected DataFrame are
    returned to the caller to be folded exactly once (not re-run). ``B`` is the
    largest batch that fits the memory budget (:func:`size_to_budget`); there is no
    working-set cap — the policy axis is monotonic, so the budget alone governs.

    Returns:
        ``(B, seed_af, seed_proj, seed_size)``.

    """
    n_policies = model_points.height
    seed_size = min(n_policies, max(1, n_policies // 10))
    seed_af = model_fn(ActuarialFrame(model_points.slice(0, seed_size)))
    seed_lazy = seed_af._df  # noqa: SLF001
    if seed_lazy is None:
        msg = "model_fn returned an ActuarialFrame with no underlying frame."
        raise ValueError(msg)
    seed_proj, seed_peak = _collect_with_peak(seed_lazy, engine="streaming")
    per_cell = max(1, seed_peak // max(1, seed_size))  # bytes per policy
    return int(size_to_budget(per_cell, n_policies)), seed_af, seed_proj, seed_size
```

The auto branch in `run_aggregated` already calls `_resolve_auto(model_fn, model_points)`
with no `fraction` argument, so no caller change is needed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/scenarios/test_run_aggregated.py -q`
Expected: PASS (all, including the two new tests and the existing equivalence/edge tests).

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_aggregated.py tests/scenarios/test_run_aggregated.py
git commit -m "refactor(scenarios): size run_aggregated to the budget; delete 384MB working-set cap"
```

---

## Task 3: `run_to_parquet` delegates to `size_to_budget`

**Files:**
- Modify: `gaspatchio_core/scenarios/_spill.py`
- Test: `tests/scenarios/test_spill.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/scenarios/test_spill.py`:

```python
def test_run_to_parquet_auto_batches_to_budget(tmp_path, monkeypatch):
    """auto path: the shared sizer's B drives the number of batch files."""
    import gaspatchio_core.scenarios._spill as spill

    mp = pl.DataFrame({"value": [float(i) for i in range(1, 11)]})  # 10 policies
    monkeypatch.setattr(spill, "size_to_budget", lambda *a, **k: 4)
    out = run_to_parquet(
        _toy_full_model,
        mp,
        tmp_path / "out",
        batch_size="auto",
        mounts_text="/dev/disk1 / ext4 rw 0 0\n",  # mark target as real disk
    )
    files = sorted((tmp_path / "out").glob("batch_*.parquet"))
    assert len(files) == 3  # 10 / 4 -> [4, 4, 2]
    assert out.n_batches == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/scenarios/test_spill.py -q`
Expected: FAIL — `monkeypatch.setattr(spill, "size_to_budget", ...)` errors (`_spill` has
no `size_to_budget` yet).

- [ ] **Step 3: Wire the auto path to `size_to_budget`, swap the import**

In `gaspatchio_core/scenarios/_spill.py`:

(a) **Swap the import** — replace `from gaspatchio_core.scenarios import _memory` with:

```python
from gaspatchio_core.scenarios._auto_batch import size_to_budget
```

(b) **Replace** the `if batch_size == "auto":` block body with:

```python
    if batch_size == "auto":
        # Size to the memory budget (no working-set cap): seed -> per_cell -> B.
        seed_size = min(n_policies, max(1, n_policies // 10))
        seed_af = model_fn(ActuarialFrame(model_points.slice(0, seed_size)))
        seed_lazy = seed_af._df  # noqa: SLF001
        if seed_lazy is None:
            msg = "model_fn returned an ActuarialFrame with no underlying frame."
            raise ValueError(msg)
        _seed_df, seed_peak = _collect_with_peak(seed_lazy, engine="streaming")
        per_cell = max(1, seed_peak // max(1, seed_size))
        preflight_disk(output_dir, estimated_bytes=per_cell * n_policies)
        resolved = size_to_budget(per_cell, n_policies)
        del _seed_df
    else:
        resolved = int(batch_size)
```

(The `IrreducibleCellError` raise is now inside `size_to_budget`; the `_memory` import is
no longer used here.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/scenarios/test_spill.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_spill.py tests/scenarios/test_spill.py
git commit -m "refactor(scenarios): size run_to_parquet via the shared size_to_budget"
```

---

## Task 4: Delete dead `SizingDefaults` constants

**Files:**
- Modify: `gaspatchio_core/scenarios/_memory.py`
- Test: `tests/scenarios/test_memory.py`

- [ ] **Step 1: Confirm no remaining references**

Run:
```bash
grep -rn "abs_first_batch_bytes\|min_floor_bytes\|\.safety\b" gaspatchio_core/ tests/ | grep -v "safety_margin"
```
Expected: only the three `DEFAULTS.*` assertions in `tests/scenarios/test_memory.py`
(removed in Step 2) and the three field definitions in `_memory.py` (removed in Step 3).

- [ ] **Step 2: Remove the assertions from `test_memory.py`**

In `tests/scenarios/test_memory.py`, delete these three lines from the defaults test
(~lines 30-32):

```python
    assert 0.0 < DEFAULTS.safety <= 1.0
    assert DEFAULTS.min_floor_bytes > 0
    assert DEFAULTS.abs_first_batch_bytes > 0
```

- [ ] **Step 3: Delete the dead fields from `SizingDefaults`**

In `gaspatchio_core/scenarios/_memory.py`, remove these three lines from `SizingDefaults`:

```python
    safety: float = 0.8
    min_floor_bytes: int = 1_000_000  # 1 MB noise floor for a measured per-cell cost
    abs_first_batch_bytes: int = 384 * 1024**2  # first-batch list-data ceiling (Plan 2)
```

`SizingDefaults` then holds exactly: `target_memory_fraction`, `ladder`, `safety_margin`.

- [ ] **Step 4: Run the affected tests**

Run: `uv run pytest tests/scenarios/test_memory.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_memory.py tests/scenarios/test_memory.py
git commit -m "refactor(scenarios): drop dead SizingDefaults constants (safety, min_floor_bytes, abs_first_batch_bytes)"
```

---

## Task 5: Final gate — full suite + type-check + stubtest

**Files:** none (verification only; fix-forward if anything is red).

- [ ] **Step 1: Full scenarios suite**

Run: `uv run pytest tests/scenarios -q`
Expected: PASS (no regressions; the equivalence and edge tests for both drivers green).

- [ ] **Step 2: Type-check**

Run: `uv run mypy gaspatchio_core/scenarios/_auto_batch.py gaspatchio_core/scenarios/_aggregated.py gaspatchio_core/scenarios/_spill.py gaspatchio_core/scenarios/_memory.py`
Then: `uv run pyright gaspatchio_core/scenarios`
Expected: clean (0 errors).

- [ ] **Step 3: Stub validation**

Run: `uv run python -m mypy.stubtest gaspatchio_core`
Expected: clean (no new divergences — no public signatures changed; `size_to_budget` is
private to `scenarios._auto_batch`).

- [ ] **Step 4: Commit any fixes**

If Steps 1-3 required edits:
```bash
git add -A
git commit -m "test(scenarios): final gate for the policy-axis budget sizer"
```
If nothing needed fixing, this task closes with no commit.

---

## Self-review checklist (controller, before dispatching)

- **Spec coverage:** size_to_budget (§4.1) → Task 1; run_aggregated wiring + cap delete
  (§4.2, §11) → Task 2; run_to_parquet wiring (§4.3) → Task 3; dead-constant cleanup
  (§4.4) → Task 4; testing strategy (§8) → distributed across Tasks 1-5; behavioural
  change (§5) carried by the cap deletion in Task 2. No `sizing_reason` (dropped). ✓
- **Type consistency:** `size_to_budget(per_cell_bytes, n_items, *, target_memory_fraction,
  safety_margin)` is identical in the spec, Task 1 impl, and the Task 2/3 call sites
  (callers pass only `per_cell, n`). ✓
- **No placeholders:** every step has concrete code, an exact command, and expected output. ✓
