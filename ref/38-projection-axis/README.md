# Projection Axis API Unification

**Topic:** Replace two parallel time-axis primitives — `af.date.create_projection_timeline(...)` and user-facing `Schedule.from_*(...)` constructors — with a single unified verb on the existing `af.projection` accessor.

**Branch:** `gsp-92-rollforward-redesign` (continuation of typed-input + state-machine work)

**Why this exists**

Today an actuary has two ways to set up a per-policy time axis:

1. `af.date.create_projection_timeline(valuation_date=..., projection_end_type=..., projection_end_value=..., projection_frequency=...)` — eagerly stamps four columns; mutates the frame in place.
2. `Schedule.from_inception(inception_column=..., n_periods=..., frequency=...)` (or `from_calendar_grid(...)`) — typed input passed to the rollforward kernel via `schedule=`.

These are not equivalent. They live at different layers (frame accessor vs typed input), have different end-time vocabularies, use different frequency strings (`"monthly"` vs `"1M"`), and produce different lengths (`N+1` timeline steps vs `n_periods` widths). The off-by-one alignment trap between them is documented in the typed-input tutorial README as a known footgun.

This refactor unifies them into one surface — `af.projection.set(...)` — that both the actuary and the rollforward kernel read from.

**Status:** Spec drafted, brainstorm complete. Awaiting implementation plan.

**Documents**

- `specs/2026-05-05-projection-axis-design.md` — design spec (settled positions, API surface, migration scope)
- `migration.md` — companion guide with before/after examples drawn from the actual tutorial models

**Out of scope (separate Linear tickets)**

- GSP-97 — Native per-policy `n_periods` in the kernel (memory optimisation; 2-3 weeks; high regression risk)
- GSP-98 — Mid-period termination semantics (partial-period `dt` at lapse; 1-2 weeks plus regime-convention research)

Both reference back to this spec so the deferral chain is traceable.
