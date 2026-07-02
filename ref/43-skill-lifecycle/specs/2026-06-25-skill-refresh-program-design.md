# Skill Refresh Program — design

> Bring all 7 agent skills from their pre-#104 state up to current `develop`:
> repair removed-API breakage and add coverage for the new API surface, with
> every change proven (introspection + the L4 effectiveness gate), not guessed.

## Why now

The skills were authored at #80 (2026-03-26) and last meaningfully touched at #105
(2026-05-28). The core API has moved substantially since — and the L3 eval caught
the consequence: models generated under the skills' guidance *fail* (they call the
removed `create_projection_timeline`). The `.skills-sync.yml` anchor
(`synced_sha: efcb54c`, pinned 2026-06-22) hides this — it claims the skills are
current. They are not.

DETECT against the true authored baseline (`c7f5aa8 → develop`) reports **227
added / 43 removed / 25 changed** importable symbols. De-noised (the raw count is
inflated by import aliases and internal modules), the real drift is a **months-deep
refresh across all 7 skills**.

## The drift, by area

Decompose by **API-area** (an area is one coherent introspection job that cuts
across several skills — far better than a per-skill split, where each skill is hit
by several unrelated areas). Five areas, by priority:

| # | Area | Removed (fix) | New (draft) | Skills touched |
|---|------|---------------|-------------|----------------|
| 1 | **Projection backbone** | `create_projection_timeline` → `af.projection.set()` / `af.projection.period_dates()` | per-policy / jagged timelines (`per_policy=True`, `until_value`) | model-building, quickstart, extending-gaspatchio |
| 2 | **Scenarios / aggregators** | `Step`, `StepDef`, `sensitivity_analysis`, `describe_scenarios`, `batch_scenarios` | **`ScenarioRun`** (verify/reconcile — already taught, surface drifted), `for_each_scenario`, `run_aggregated`, `AggregatedResult`, `Period*` (Sum/Mean/Min/Max/Median/Std/Variance/Count/Quantile/CTE), the base aggregators, `register_aggregator` | model-scenarios, model-review |
| 3 | **Streaming / scale** | — | `run_to_parquet`, `SpillResult`, model-point batching | model-building, model-scenarios |
| 4 | **Curves / scheduling** | — | `Curve`, `Schedule`, `Calendar`, `DayCount`, `BusinessDayConvention` | model-building, model-discovery |
| 5 | **Mortality / rollforward** | `RollforwardBuilder` | `MortalityTable`, `compile_rollforward`, `CompiledRollforward`, `RollforwardCollector` | model-building, model-review |

Within an area, a symbol is either **reconcile** (the skill already teaches it but
the surface has drifted — e.g. `ScenarioRun`, added in #105 and taught across
`model-scenarios`, but now carrying `from_yaml`/`with_extra_*`/`canonical_form`
the skill predates, *and* cited next to the removed `describe_scenarios`/
`sensitivity_analysis`) or **draft** (the skill is silent — e.g. `Curve`,
`Schedule`). The introspect step catches both: it verifies a taught surface as
readily as it grounds a new one. Do not assume a "new" symbol is undocumented —
the #105 scenario update means `model-scenarios` is partially current.

(`AGENTS.md` — the always-loaded framework knowledge — *also* teaches
`create_projection_timeline`. It is in core, edited via a core PR, and should be
fixed alongside Area 1, but it is not a `skills/` artifact and so sits outside the
L4 loop's worklist.)

## Per-area method

Each area runs through the L4 `skill-update` loop, executed by a dedicated
subagent with the `skill-update` SKILL.md as its method:

1. **DETECT-scoped** — the area's removed/changed/added symbols (from the corrected
   delta + the de-noised symbol→skill map).
2. **Introspect every new/changed symbol** — `help(g.<X>)` + read its usage test
   under `bindings/python/tests/`. Non-negotiable: the skills' entire value is
   *correct* calls; a wrong signature is worse than silence. (The
   `create_timeline` ≠ `create_projection_timeline` trap — same leaf, totally
   different signature — is why a blind rename is forbidden.)
3. **Fix** — repair every reference to a removed/changed symbol (prose and
   examples).
4. **Draft** — add coverage for the area's new user-facing symbols (smallest
   targeted additions; skill voice; realistic actuarial data).
5. **VERIFY** — `skill_verify.py --skill <X>` per touched skill: structural gate
   (hard) + L3 lift spot-check (advisory).
6. **REVIEW** — report; **stop before commit**; the change is PR'd into core.

## Stage 0 — prerequisites (land before editing skills)

1. **Merge #138 (L3) and #136 (L0/L1)** into `develop`. The VERIFY step needs the
   L3 `run_evals.py` interface *and* the structural skill-tests / `gen_skill_manifests.py`
   in the core checkout; until then the lift arm reports "output not recognized".
2. **Reset `.skills-sync.yml synced_sha`** to the true baseline (≈#104's parent),
   so the debt is *visible* and DETECT is honest. Bump it forward only as areas
   land.
3. **De-noise the detector's symbol→skill map** — the leaf-name matcher is
   unusable at this scale (`add`, `floor`, `on`, `month`, `pl`, `Any` drown the
   signal). Add a stopword list of generic leaf names + prefer qualified-reference
   matching (`af.<symbol>(` / `g.<symbol>`). Lives in `mdsync/mapping.py` (docs).

**Exception:** Area 1 (projection) is fully grounded and *broken now*; it may go
first, structural-gate-only, with the lift check deferred until Stage 0 #1 lands.

## Verification & "done" per area

- **Structural gate** passes for every touched skill (always available).
- **Fix areas** (1, 2, 5): the L3 lift spot-check shows the skill now *helps* —
  these are currently *failing*, so the improvement is directly measurable
  (broken → working).
- **Draft areas** (3, 4, and the new-API half of 2/5): measuring added coverage
  may need **new L3 eval tasks** (a dataset case that exercises the new API).
  Authoring those tasks is part of the area's work, not a separate project.
- An area is done when: every removed/changed reference is gone, the new APIs have
  correct grounded examples, structural is green, and (where measurable) lift is
  non-negative.

## Execution model

- **One subagent per area** (fresh context, `skill-update` SKILL.md as method),
  reviewed before the next — the same implementer + spec-review + code-review
  discipline used to build L4 itself.
- **One PR per area** into core (`feat/skill-refresh-area-<n>`), so each lands and
  is measurable independently and the `synced_sha` advances incrementally.
- Stop-before-commit holds throughout: the human reviews each area's diff and PRs.

## Sequencing

1. **Stage 0** (prerequisites) — merges + anchor reset + map de-noise.
2. **Area 1** (projection) — highest impact, fixes the live breakage. *(May start
   before Stage 0's merges, structural-only.)*
3. **Area 2** (scenarios/aggregators) — large removed set + the aggregator layer.
4. **Areas 3–5** (streaming, curves, mortality/rollforward) — additive coverage;
   order by demand.

Each area is its own spec-light plan (this program spec + a per-area task plan).
Area 1's plan is written next.

## Decisions log

- **R1 — decompose by API-area, not by skill.** An area shares one introspection;
  a skill is touched by several areas.
- **R2 — Stage 0 is a hard prerequisite** (anchor honesty + de-noised worklist +
  merged tooling), with Area 1 the one safe early start.
- **R3 — each area is its own PR into core**, advancing `synced_sha` incrementally.
- **R4 — fix before draft within an area**; anti-rot first, coverage second.
- **R5 — introspect every symbol before writing** — no call from memory; grounded
  on `help()` + the usage test.
- **R6 — draft areas may add new L3 eval tasks** to make their coverage
  measurable; that authoring is in-scope for the area.
