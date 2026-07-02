# Area 5 — Mortality & rollforward: refresh plan

> **For agentic workers:** execute via the `skill-update` loop. Two halves:
> **`MortalityTable` = DRAFT** (used but never taught), **rollforward = RECONCILE /
> verify-only** (already taught correctly — confirm, fix only genuine drift).
> Grounded against develop; cross-check every signature against source.

**Goal:** Teach the typed `MortalityTable` primitive in `model-building`, and verify
the existing rollforward content across skills is current.

---

## Part A — `MortalityTable` (DRAFT — the real work)

The skills teach generic `Table.lookup` for assumptions and only *use*
`MortalityTable` in passing (`model-scenarios` model_fn re-wrap). `MortalityTable`
is the typed mortality primitive — it encodes age basis and table structure and,
for select-ultimate tables, **auto-clamps duration at the select period** (the
ultimate-rate behaviour you otherwise hand-roll).

### Grounded API (verified: `mortality/_mortality_table.py`, `tests/mortality/test_at_*.py`)

Top-level: `from gaspatchio_core import MortalityTable` (verify the export path).

```python
from gaspatchio_core import MortalityTable

m = MortalityTable(
    table=mortality_table,            # a gaspatchio_core.assumptions.Table
    age_basis="age_last_birthday",    # AgeBasis (e.g. age_last_birthday, age_nearest_birthday)
    structure="select_ultimate",      # "aggregate" | "select_ultimate" | "joint"
    select_period=4,                  # int | None — select window for select_ultimate
)

# Vectorised lookup (accepts pl.Expr / af columns):
af.qx = m.at(age=af["age"], duration=af["duration"])
```

- **`structure="select_ultimate"`** — `.at(age=, duration=)` looks up the select
  rate while `duration <= select_period`, and **clamps duration to `select_period`**
  beyond it (ultimate rates). Verified: durations 10/25 with `select_period=4` both
  resolve to the duration-4 rate. This is the headline value over generic
  `Table.lookup`, which has no select/ultimate clamping.
- **`structure="aggregate"`** — age-only lookup (no duration). Ground the exact
  call against `tests/mortality/test_at_aggregate.py` before writing.
- **`structure="joint"`** — multiple-life. Ground against
  `tests/mortality/test_at_joint.py`; teach lightly (advanced).

### What to write
1. **Create `skills/model-building/references/mortality-tables.md`**: construction;
   the three structures (aggregate / select_ultimate / joint) with the
   select-ultimate auto-clamp as the headline; the `.at()` lookup; and a
   **when-to-use** contrast — `MortalityTable` for select/ultimate or age-basis
   semantics, generic `Table.lookup` for flat dimensional tables. Realistic
   actuarial data; ≤600 lines. Cross-link the `model-scenarios` re-wrap usage
   (typed wrappers under `assumptions_override`).
2. **`skills/model-building/SKILL.md`**: a short pointer near the assumptions /
   mortality material (the classification table or reference list) — "for
   select/ultimate or age-basis mortality, use `MortalityTable` (see ref)". A few
   lines.

---

## Part B — Rollforward (RECONCILE / verify-only — expect NO edits)

Rollforward is already taught across `model-building/SKILL.md` (classification
table), `references/recursive-patterns.md`, `references/aggregate-patterns.md`,
`quickstart`, `extending-gaspatchio`, and `model-review/references/gaspatchio-antipatterns.md`.
The de-noise worklist flagged `RollforwardBuilder`/`compile_rollforward` as
removed/changed, but **they exist and are current** (the flag was signature drift
the skills don't expose).

### Verified-current pattern (`tutorials/rollforward-patterns/01_single_state_fund.py`)
```python
b = af.projection.rollforward(states={"av": af["av_init"]})
(b["av"].grow(af["fund_return"], label="fund_return")
        .charge(af["me_charge"], label="me_charge")
        .floor(value=0.0))
compiled = compile_rollforward(b)
collector = RollforwardCollector(compiled)
af.av = collector.expr_for("av")
```
Step methods all exist on `RollforwardBuilder`: `add`, `subtract`, `charge`,
`grow`, `grow_capped`, `deduct_nar`, `ratchet`, `floor`, `apply`, `at`, `between`,
`increment`.

### What to do
- **Verify** every rollforward reference in the skills against this pattern +
  source: `af.projection.rollforward(states={…})`, the step methods, `compile_rollforward`,
  `RollforwardCollector`. The `model-review/references/gaspatchio-antipatterns.md`
  example (`rollforward(states={"av": af["av_init"]})` → `compile_rollforward(b)`)
  is the one detailed call site — confirm it matches.
- **Fix only genuine drift.** If a skill shows a step-method call with a wrong
  signature (e.g. missing the `label=`/`value=` kwargs, or a removed method), fix
  it. If everything matches (expected), make **no rollforward edits** and say so.
- Do NOT rewrite correct content.

---

## Verification

1. **Source cross-check:** `MortalityTable` examples use only real params
   (`table`, `age_basis`, `structure`, `select_period`, `.at(age=, duration=)`);
   import path verified. Rollforward references match the grounded pattern.
2. **Grep gate:** `grep -rn "MortalityTable" skills/model-building/` shows the new
   content.
3. **Structural gate** (worktree env — lancedb): `uv run --no-project --with pytest
   --with pyyaml python -m pytest tests/skills/ -q` → all pass; new reference ≤600 lines.
4. **Deferred:** L3 lift spot-check once #138 lands.

## REVIEW

Report the diff + grep/structural results + the rollforward verification outcome
(edited vs confirmed-current). Commit on `feat/skill-refresh` (conventional, no AI
trailer). Do not push. `AGENTS.md` out of scope. Append any tutorial issues to
`ref/45-tutorial-refresh/2026-06-25-tutorial-refresh-findings.md`.
