# Tutorial refresh — findings log

> Tutorial state, surfaced while running the *skill*-refresh program
> (`ref/43-skill-lifecycle/`). The tutorials ship inside the package at
> `bindings/python/gaspatchio_core/tutorials/` (repo-root `tutorial` is a symlink
> to it).

## Verdict (execution-verified, 2026-06-26): the tutorials are healthy

The provisional findings below (from a static grep on 2026-06-25) **overstated the
problem** — the same "worklist overstates" pattern the skill refresh kept hitting.
A full execution sweep against current `develop` settles it:

- **All 26 `model.py` execute clean** (6 base + 20 steps). The one apparent
  failure — `level-3-mini-va/06-reconcile` — is **by design**: it's the
  reconciliation tutorial whose default `--model gaps` has "4 deliberate gaps" and
  whose *expected* output is `RESULT: RECONCILIATION FAILED` (`--model fixed`
  passes).
- **The L5 v0.2 scenario path runs clean** — `level-5-scenarios/base/run_scenarios.py`
  (`ScenarioRun`) executes (exit 0); the step `run_scenarios.py` scripts are
  static-clean of removed APIs.
- **`Curve`/`MortalityTable`/`Schedule` are correctly demonstrated** in
  `level-3-mini-va-typed` (the typed variant) — and it passes `t_years` as a
  `list[float]`, i.e. the eager path, *avoiding* the `map_elements` footgun of
  GSP-116. Good reference for the correct pattern.
- **The CI "Tutorial Smoke Tests" job works** — it globs `../../tutorial/level-*/base/model.py`;
  repo-root `tutorial` is a symlink to the package tutorials, so it resolves at
  runtime (git pathspecs just don't traverse the symlink, which made it *look*
  dead on inspection).

## The only real fix (done)

### 1. `tutorials/README.md:66` — referenced the removed `sensitivity_analysis()`
- **Status:** FIXED 2026-06-26. The L5-steps table row for step 03 described
  sweeps "via `sensitivity_analysis()`" (removed). Reworded to the current
  approach — a list comprehension of `ScenarioRun` scenarios — matching what
  `steps/03-sensitivity/run_scenarios.py` actually does and the `model-scenarios`
  skill teaches.

## Corrected (earlier provisional findings that did NOT hold up)

- **~~Duplicate level-3 (`mini-va` vs `mini-va-typed`)~~ — intentional, not drift.**
  The typed variant deliberately mirrors the untyped one using the three typed
  inputs (`Schedule`/`Curve`/`MortalityTable`), with per-step `expected_output.txt`
  and a `06-reconcile` parity gate (typed == untyped to ~1e-9). Both ship on
  purpose.
- **~~No tutorial demonstrates `Curve`~~ — wrong.** `level-3-mini-va-typed`
  demonstrates `Curve` (and `Schedule`, `MortalityTable`) throughout.

## Residual (optional enhancements, not bugs)

- The CI smoke job runs only `base/model.py` + the L4 benchmark runner — **not the
  steps or the L5 `run_scenarios.py` scripts**. They're static-clean and I
  execution-verified them by hand, but they aren't CI-protected. Adding them to the
  smoke matrix would close the gap.
- Skills could cross-reference `level-3-mini-va-typed` for the typed-input
  composition story (it's currently only referenced as `level-3-mini-va`).

---

*Conclusion: "do the tutorials need updating?" — essentially no. One stale README
line (fixed). The models, the typed-input showcase, the v0.2 scenario scripts, and
the CI smoke test are all sound.*
