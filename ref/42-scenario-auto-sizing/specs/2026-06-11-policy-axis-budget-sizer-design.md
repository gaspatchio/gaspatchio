# Policy-axis budget sizer — design spec

**Date:** 2026-06-11
**Status:** DRAFT — awaiting review
**Topic:** `ref/42-scenario-auto-sizing` (sibling of the shape-aware scenario driver)
**Evidence:** `reports/2026-06-11-policy-axis-evidence/findings.md` (1K/10K local +
1K/10K/100K runner sweep)

---

## 1. Objective (unchanged, restated)

> **Pick the fastest execution that still fits the memory budget.** Measure, don't
> assume. Simple and robust beats complex with minor gains. One model is one of
> hundreds — don't overfit. No backwards compatibility owed.

This spec applies that single objective to the **policy-axis** drivers
(`run_aggregated`, `run_to_parquet`), the no-scenario siblings of `for_each_scenario`.

## 2. What the evidence settled

A fresh-subprocess batch-size sweep on the real L4 model, at 1K / 10K / 100K:

- **Wall time is MONOTONIC in batch size B at every scale** (no cross-join → no
  U-shape). The smallest batches are 2–40× slower purely from per-batch fixed overhead
  × batch count. **=> "largest B that fits the budget" is speed-optimal. No search is
  needed** — porting the scenario-axis ladder would solve a problem this axis doesn't
  have.
- The current `auto` sizing caps B at a **hardcoded 384 MB working-set ceiling**
  (`_aggregated._WORKING_SET_TARGET_BYTES`), which **ignores the budget**: at 100K it
  forced 9 batches (516 MB, 5.98s) when the budget had room for the single 4 GB batch
  that ran fastest (5.47s). It is the exact model-blind magic constant removed from the
  scenario axis.
- The speed penalty of the cap shrinks at scale (~10% at 100K) because the wall curve
  flattens at the top — but the cap is still wrong against the objective, and removing
  it is a *simplification*, not added complexity.

## 3. The decision

Adopt the **pure budget sizer**: size each policy batch to the largest B whose predicted
peak fits the cgroup-aware memory budget, with a safety margin for measurement error.
Delete the working-set cap. Unify the two policy-axis drivers (which already duplicate
the seed→per_cell→budget block) onto one shared sizing function.

This is strictly less code, honours the objective exactly, and is consistent with the
scenario axis (same `memory_budget_bytes`, same `safety_margin`).

## 4. Architecture

### 4.1 Shared sizing function (the one new unit)

Lives in `scenarios/_auto_batch.py` (already the "memory budget seams for sizing"
module). Pure arithmetic over a *measured* per-item cost — no I/O, fully unit-testable:

```python
def size_to_budget(
    per_cell_bytes: int,
    n_items: int,
    *,
    target_memory_fraction: float = DEFAULTS.target_memory_fraction,
    safety_margin: float = DEFAULTS.safety_margin,
) -> int:
    """Largest B in [1, n_items] whose predicted peak fits the memory budget.

    Predicted peak for a batch of B items is ``per_cell_bytes * B`` (the policy axis
    is linear — no cross-join). We require ``predicted * safety_margin <= budget``,
    so ``B = budget // (per_cell_bytes * safety_margin)``, clamped to [1, n_items].

    The safety margin governs sizing ABOVE one item; it never refuses a single item
    that fits the RAW budget (there is nothing smaller to fall back to). So:
      * margin-adjusted B >= 1  -> return min(B, n_items)   (margin honoured)
      * else one item fits raw  -> return 1                 (best effort, tight)
      * else                    -> raise IrreducibleCellError (one item exceeds budget)
    """
    budget = memory_budget_bytes(target_memory_fraction)
    denom = max(1, int(per_cell_bytes * safety_margin))
    b = budget // denom
    if b >= 1:
        return int(min(b, n_items))
    if budget // max(1, per_cell_bytes) >= 1:
        return 1   # one item fits the raw budget; run it (margin can't be honoured)
    raise IrreducibleCellError(...)   # one item exceeds even the raw budget
```

Key properties:
- **Cgroup-honest budget**: routes through the existing `memory_budget_bytes`
  (`min(host_available, cgroup_headroom)` − base RSS, fail-open). The policy axis stops
  hardcoding `0.5` and stops calling `_memory.memory_budget` directly.
- **`safety_margin` (1.3, shared with the scenario axis) replaces the working-set cap's
  safety role** — it inflates the predicted peak before the budget comparison, so a
  10%-seed under-estimate of `per_cell` does not OOM. This is the *principled* guard,
  tied to the real budget, in place of the magic 384 MB.
- **No magic constants.** Only `target_memory_fraction` and `safety_margin`, both already
  defined in `SizingDefaults` and both used by the scenario axis.

### 4.2 `run_aggregated` (`_aggregated.py`)

`_resolve_auto` keeps its seed measurement (the "measure, don't assume" step) but
delegates the arithmetic:

1. Run the 10% seed batch (`n // 10`, ≥1), collect streaming, measure `seed_peak`.
2. `per_cell = max(1, seed_peak // seed_size)`.
3. `B = size_to_budget(per_cell, n_policies)`  ← replaces `min(memory_cap, working_cap, n)`.
4. Fold the seed exactly once; loop the remainder at B. (unchanged)

**Delete** `_WORKING_SET_TARGET_BYTES` and the `working_cap` term.

### 4.3 `run_to_parquet` (`_spill.py`)

Already sizes to the budget with no working-set cap — it just open-codes the same block.
Replace its inline `seed_peak // seed_size` → `memory_budget(0.5)` → `budget // per_cell`
with the same two steps (seed measure, then `size_to_budget`). The disk preflight
(`preflight_disk`) is unchanged. Net effect: both drivers share one sizer; the duplicated
arithmetic disappears.

### 4.4 Dead-constant cleanup (verify-then-delete)

`grep` shows no non-test references to `SizingDefaults.abs_first_batch_bytes` (a second,
separate 384 MB constant), `SizingDefaults.safety` (0.8), or `SizingDefaults.min_floor_bytes`
(1 MB). The first plan task confirms there are no test references either, then deletes
them. `SizingDefaults` should end with the live knobs:
`target_memory_fraction`, `ladder`, `safety_margin`, `seed_sample_cap` (see §4.5).

### 4.5 Bounded measurement seed (robustness — added post-1M evidence)

The auto path measures per-policy cost from a *seed* batch. The original seed was
`n // 10` policies **collected as one frame** — unbounded in `n`. At large scale the
seed itself OOMs *before* the budget sizer runs (10M → a 1M-policy / ~40 GB single
collect). Per-policy cost is **linear**, so a bounded sample estimates it just as well:

```python
def bounded_seed_size(n_items: int) -> int:
    return min(n_items, max(1, n_items // 10), DEFAULTS.seed_sample_cap)  # cap = 4096
```

Both drivers (which duplicated the `n // 10` seed line) call this shared helper. The
cap is a *measurement* constant — how big a sample reliably estimates a linear
quantity — not a model-shape or memory-threshold constant; a few-thousand-policy
sample is representative for any realistic model, and the budget sizer's
`IrreducibleCellError` still backstops a pathological single item. This makes `auto`
safe at any `n` on any box (e.g. 10M on a 16 GB laptop → bounded seed → hundreds of
budget-sized batches, no OOM).

## 5. Behavioural change (explicit, accepted)

Today `run_aggregated` peaks at a bounded ~500 MB regardless of scale (the cap). Under the
budget sizer, peak scales to the budget — a single ~4 GB batch at 100K on a roomy box,
because that is the fastest execution that fits. **This is the intended consequence of the
objective** ("fastest that fits the budget"), recorded here so it is a decision, not a
surprise. The `safety_margin` bounds the blast radius of a seed mis-estimate; the
`IrreducibleCellError` still fires loudly when even one item exceeds the budget.

## 6. Auditability

No new audit field. `AggregatedResult` / `SpillResult` already carry the resolved
`batch_size`, which (with the model's policy count) is sufficient to see what the sizer
did. The policy axis has nothing to "search" — there is no probe list worth recording —
so a `SelectionDecision` analog would be ceremony. Keep it simple.

## 7. Edge cases

| Case | Behaviour |
|------|-----------|
| `n_policies == 0` | `ValueError` (unchanged). |
| `n_policies == 1` | seed = 1; `size_to_budget` returns 1 if it fits, else raises. |
| seed peak ~0 (toy model) | `per_cell = max(1, …)`; `size_to_budget` returns `n` (whole portfolio fits). |
| even B=1 exceeds budget | `IrreducibleCellError` with actionable guidance. |
| explicit `batch_size=<int>` | unchanged — no sizing, loop as given. |
| `safety_margin` makes B=0 but B=1 would fit raw | clamp to ≥1 only when raw (no-margin) B≥1; otherwise raise. *(decision: the margin is advisory for sizing, but we never refuse a batch that genuinely fits without the margin — a one-item batch that fits the raw budget runs.)* |

## 8. Testing strategy

1. **Sizing math unit tests** (`size_to_budget`) with an injected budget (via the
   `_auto_batch._cgroup_root` / `_proc_cgroup_text` seams, as the scenario axis does):
   monotonic B in budget; clamps to `n`; raises when B<1; safety_margin shrinks B.
2. **Equivalence**: `run_aggregated(batch_size="auto")` aggregates == full-materialise
   aggregates == `batch_size=<small int>` aggregates (bit-identical), reusing
   `aggregated_runner.outputs_match`. This is the correctness gate.
3. **Cap-removal regression**: with a generous injected budget, `auto` resolves to a
   single batch (B == n) on a model that the old 384 MB cap would have split.
4. **No-OOM guard**: with a tiny injected budget, `auto` resolves to many small batches
   and never exceeds the budget; with an impossible budget it raises `IrreducibleCellError`.
5. **Runner confirmation** (already wired): the `Policy-Axis Batch Sweep` evals.yml job
   keeps charting the 1K/10K/100K curve; post-change, `auto` should track the budget, not
   the deleted cap.
6. Type-check (mypy + pyright) and stubtest stay green.

## 9. Out of scope / non-goals

- **No ladder search** on the policy axis (monotonic — unnecessary).
- **No change to `for_each_scenario`** or its streaming-batch search.
- **No gh-pages tracking change** — the sweep stays an artifact-producing confirmation
  job for now; a focused tracked metric can follow once the sizer lands.
- **No new user-facing parameters** — `batch_size="auto"` and explicit-int are the whole
  surface; `target_memory_fraction` stays an internal default.

## 10. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| 10% seed mis-estimates `per_cell` → under/over-size | `safety_margin` (1.3) inflates the estimate; equivalence tests catch correctness; the seed is REAL work (not a throwaway), so it never wastes a pass. |
| Larger peak surprises a memory-constrained caller | Documented behavioural change (§5); the budget is cgroup-aware so it is bounded by the *real* limit, not host RAM; `IrreducibleCellError` fails loud, never silent OOM. |
| Dead-constant deletion breaks a hidden reference | Plan task 1 greps tests before deleting; type-check + full suite gate. |

## 11. Summary of changes

- **Add**: `_auto_batch.size_to_budget(per_cell, n, *, target_memory_fraction, safety_margin)`
  and `_auto_batch.bounded_seed_size(n)` (§4.5) + `SizingDefaults.seed_sample_cap`.
- **Change**: `_aggregated._resolve_auto` and `_spill.run_to_parquet` call `size_to_budget`
  and `bounded_seed_size`.
- **Delete**: `_aggregated._WORKING_SET_TARGET_BYTES`; dead `SizingDefaults` fields
  (`abs_first_batch_bytes`, `safety`, `min_floor_bytes`) after verification.
- **No** new result fields or user parameters.
- **Net**: less code, one shared cgroup-honest sizer, zero magic constants, objective-exact.
