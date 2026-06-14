# Dispatch / Broadcasting Refactor

**Linear:** GSP-95
**Branch:** `gsp-95-dispatch-refactor` (work tracked in three sequential PRs)
**Status:** Phases 1, 2, and 3 complete. PR #101 open against `develop`.

## Goal

Keep the Python DSL surface as it is. Move the dispatch / broadcasting / conditional-execution machinery underneath onto a semantic IR with an explicit Polars backend boundary, so that:

1. Shape semantics (scalar vs vector, list vs flat) become first-class in the runtime instead of inferred per-callsite.
2. Semantic planning is separated from backend lowering — the DSL plans, the backend executes.
3. Polars-specific details (raw `pl.Expr`, list heuristics, plugin special cases) live behind the backend layer, not inside the DSL surface.
4. Chained `when().then()...otherwise()` lowers as a complete reverse-folded conditional chain with first-match-wins semantics.
5. The portable subset of the DSL is explicit. Arbitrary autopatched Polars `Expr` methods are not treated as future-engine portable.

## Phases shipped

- **Phase 1 — PR #99** ([merged](https://github.com/opioinc/gaspatchio-core/pull/99)). Reverse-fold lowering of chained `when().then()...otherwise()` with first-match-wins semantics on list columns. Fixed GSP-87.
- **Phase 2 — PR #100** ([merged](https://github.com/opioinc/gaspatchio-core/pull/100)). Shape source-of-truth (`column/shape.py`), `_schema_generation`-keyed proxy cache, deletion of `ColumnTypeDetector` and the regex/graph heuristics. Mode parity by construction.
- **Phase 3 — PR #101** (open against `develop`). Polars-backend boundary extraction: new `polars_backend/` subpackage, split of `column/dispatch.py` into four concern-specific files, operand-swap normalization on `ConditionExpression`, scalar OR/NOT routing fix, thinning of `condition_expression.py` to a frontend that delegates to the backend.

## Inputs

The starting point for this work was a draft proposal already written by Cursor on a separate branch. Treated as **input**, not as the design we shipped — the goal was to absorb its arguments, decide what to keep, and produce our own design and plan.

- **Cursor draft branch:** [`cursor/dispatch-refactor-design-76e5`](https://github.com/opioinc/gaspatchio-core/tree/cursor/dispatch-refactor-design-76e5)
- **Cursor draft PR:** [#98 (draft)](https://github.com/opioinc/gaspatchio-core/pull/98)

Note on numbering: Cursor's draft uses `ref/35-…`. This folder is `37-…` to avoid a same-name collision if PR #98 ever lands. The two are intentionally distinct directories.

## Layout

- `ARCHITECTURE.md` — developer guide to the dispatch / broadcasting / conditional surface as it stands after PR #101. Read this first.
- `specs/2026-04-30-dispatch-engine-refactor-design.md` — the original design doc (historical; preserved as written).
- `plans/2026-04-30-dispatch-engine-refactor.md` — phased implementation plan, updated through execution.

## Reading order

1. `ARCHITECTURE.md` — the post-implementation state.
2. `specs/` — what we set out to build and why.
3. `plans/` — how the work was broken into phases and what each PR did.
