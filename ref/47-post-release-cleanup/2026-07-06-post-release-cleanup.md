# Post-Release Cleanup Backlog — v0.5.1

A single, prioritised backlog of improvements to work through after the v0.5.1 release.
It brings together what we learned from a first-time-user onboarding walkthrough (actuaries
new to the framework, installing from the public docs) and an internal code-review pass,
deduplicated into one ordered list.

The plan is to work these **top to bottom**: correctness and the first-run experience first,
then docs and onboarding polish, then deeper follow-ups. Each item notes roughly where the
change lives and a rough size (S / M / L). Items marked **(both)** were surfaced independently
by both the onboarding walkthrough and the review — good signal they're worth doing early.

Nothing here is architectural; most items are small, well-scoped changes.

---

## Priority 1 — Correctness & first-run experience

Start here. These most affect whether a new user's first model — and their numbers — come out right.

1. **Projection horizon for mixed-age books.** With `until='maximum_age'` and an integer age, the shared timeline is sized to the *oldest* issue age, so younger cohorts get cut short. Use `min(issue_age)` and add a multi-cohort regression test. `projection_frame.py:346`. **S. (both)**
2. **Excel `PV` broadcasting.** When any input is a list column, `PV` currently reads only row 0 of the scalar inputs, so every policy uses the first policy's `nper`/`pmt`. Add a shared broadcast helper for unit-length literals across pv/yearfrac and cover it with mixed-shape tests. `pv.rs:142`, `pv.rs:117`. **M.**
3. **Ship the tutorial datasets in the wheel.** The release wheel currently contains Git-LFS *pointer* files rather than the parquet data, so tutorials past the base level can't load. Add `git lfs pull` to the release build (this also un-skips the reconciliation gate). **S. (both)**
4. **Make assumption-lookup misses loud.** A key outside the table returns a bare `NaN` today, which slips past `is_null`/`fill_null` and can then be zeroed inside `prospective_value`. Add an `on_missing='raise'|'nan'|constant` option, drop the blanket `fill_nan(0.0)`, and note the exact-match + miss behaviour on the assumptions pages. `array_storage.rs:158`, `projection.py:1399`. **M. (both)**
5. **Align `prospective_value` timing labels.** The period-start / period-end labels are currently swapped relative to the docstring, so following the docstring discounts by an extra period. Swap the mapping behind clearly named values and unify the timing vocabulary — cheapest to do pre-1.0. `projection.py:1407`. **M. (both)**
6. **Firm up the assumptions boundary.** A few quiet edge cases: hash-encoded null / narrow-int keys can collide with real key 0; duplicate key rows last-write-win at build; ragged inner lists can misalign later policies' rates. Add a miss sentinel + Python-side key casts, error on duplicate keys, and validate ragged lists. `hash_storage.rs:93/128`, `array_storage.rs:267`. **M.**
7. **Make debug and optimize modes match.** Debug mode (the CLI default) replays the graph and applies each op twice, so self-referential assignments (`af.x = af.x + …`) can differ from production. Make tracing record-only (or apply-only) and add a debug == optimize equivalence test. `base.py:358/493`. **M.**
8. **Smooth a few frame-API footguns.** (a) Reassigning an existing column by attribute silently bypasses the frame and keeps the old values — route it through `__setitem__`; (b) add a `__bool__` guard so `when(a and b)` doesn't quietly drop a predicate; (c) add the missing length checks in `list_conditional` Cases 2/2b/3 so final-period cashflows aren't truncated. `base.py:2315`, `condition_expression.py:27`, `list_conditional.rs:465`. **S–M.**
9. **Tighten table binding & plugin dtype.** Same-name re-registration with `force_replace=True` can swap data under a live lazy expression — resolve tables per query and warn on same-name replacement. Separately, make the lookup plugin's output dtype shape-aware (it always declares `List(Float64)`, even for scalar lookups). `_api.py:645`, `assumptions.rs:35`. **M.**

## Priority 2 — Docs & onboarding polish

The first 25 minutes for a new user. Mostly small, high-leverage.

10. **Refresh the install page.** `uv add gaspatchio` needs a project (mention `uv init`); state the import name (`gaspatchio_core`) and the Python 3.12+ floor; add a two-line verify snippet and a "Next: Tutorials" link; refresh the wheel-version example. **S.**
11. **Keep first-touch examples runnable.** Make the README quickstart run end-to-end, update the shipped `AGENTS.md` / skills references to the current `af.projection.set(...)` API, and add CI guards that execute README snippets and grep the knowledge files for removed symbols. `README.md:39`, `AGENTS.md:153`. **S. (both)**
12. **Finish the tutorial ladder.** Make the advertised Steps reachable (`init --step`, or copy the steps/README on init), give levels 1 & 2 distinct default destinations, and have `verify` check the user's own directory. **M.**
13. **Fill in the stub API reference pages.** Curve / Mortality / Schedule / rollforward / scenarios / errors render nearly empty even though the docstrings exist in the wheel — looks like a doc-build issue for the Rust-backed classes. **M.**
14. **Tidy a handful of doc examples.** Fix a few mis-nested code fences (scenarios, assumptions), the `with_columns(kwarg=…)` examples on api/excel (the signature is positional), the all-NaN `TableBuilder` melt example, and note `extend()`'s `storage_mode="hash"` requirement. **S–M.**
15. **Complete `llms.txt` / `llms-full.txt`.** Add the getting-started pages (home, install, tutorials, cli, why, ai/*) with working `index.md` variants so an agent can discover install steps and the CLI. **S.**
16. **Quiet default logging.** Set the default library log level to WARNING, document `LOGURU_LEVEL`, and soften the red ERROR that `gspio describe` prints on float-keyed model points. **S.**
17. **Declare `pyyaml`.** `ScenarioRun.to_yaml` needs it — add it as a dependency (or a `[yaml]` extra). **S.**
18. **Add `gaspatchio_core.__version__`.** Small, and people reach for it. **S.**

## Priority 3 — Correctness & governance follow-ups

19. **Scenario-axis aggregation.** For `for_each_scenario`, add the within-scenario reduction for `Period*` aggregators so stats are taken across scenarios (not policy × scenario cells); whitelist batch-invariant aggregators in `run_aggregated`; and either implement or remove the placeholder `RelativeFloorShock`. `_for_each.py:406`, `_aggregated.py:187`, `shocks.py:781`. **L.**
20. **Excel-parity polish.** Reconcile (or document) the Act/Act leap-day and basis-default behaviour, firm up IRR convergence/bracketing, fix `log_linear` flat extrapolation at the long end, and add an Excel-generated fixture suite. `yearfrac.rs:418`, `irr.rs:212`, `curve_eval.rs:185`. **M.**
21. **Per-group assumption fills.** Melt-dimension `fill=` strategies currently fall back to a global fill across groups; make them per-group (or raise), and document the Dimension / Strategy classes (FillForward / FillConstant / etc. aren't on the docs pages yet). `_strategies.py`. **M/L.**
22. **Document projection-timeline contracts.** Clarify rollforward length vs the Schedule, `num_proj_months` boundary semantics, and the `maximum_age` behaviour; add a t-counter recipe and flesh out the `fill_series` helper; guard scalar-shape time-shifts inside a frame. **M. (both)**
23. **Scalar-then-lookup ordering.** `(af[col] * lookup_result) * 0.97` currently raises a schema error naming an unrelated column (scalar-first works); fix the ordering or give a clearer message. **M.**
24. **Make the lifelib reconciliation reproducible & gated.** Ship (or hash-pin) the full reference dataset, derive the pass summary from the actual point counts, and wire `reconcile_full.py` into CI so coverage can't silently shrink. **M.**
25. **Round out CI.** Run the existing gates (clippy / fmt / ruff / mypy / pyright), SHA-pin the release build actions + maturin image, smoke-test built wheels per platform, and fail (not skip) when LFS data is missing on gated paths. `CI.yml:78/93/110`. **S–M.**
26. **Provenance & determinism niceties.** Fingerprint model points + model code into the run sidecar, emit a small manifest from `run-model`, sort the scenario fold, and publish a one-page numeric / determinism note. `_run.py:299`, `_for_each.py:459`. **S.**
27. **Polish `calc-graph`.** Carry tracing through the documented mid-model frame rebuild, fix the env-var name in its hint (`GASPATCHIO_MODE`), and swap the formatter's `eval()` for a restricted parser. `calc_graph.py:45`. **M.**
28. **Improve the "did you mean" errors.** Wire the existing similar-column matcher into the attribute-access path (the most common first mistake), drop the two suggestions that recommend `.map_elements()`, and prune the over-eager typo entries (`premiums`, `data`). `suggestions.py:304/330`, `base.py:2308`. **S.**
29. **Add an Excel → gaspatchio cheatsheet and a short lifelib migration page.** Both audiences search for terms (VLOOKUP, NPV, PMT, lifelib) the site doesn't yet use. **M.**

A few papercuts to batch alongside: `gspio knowledge --jurisdiction EU` returns nothing (corpus is tagged `international` / `us`); concepts/mortality lists an unsupported `age_next_birthday` basis; a raw polars `ShapeError` bypasses the friendly formatter; and the PyPI summary / description could use a polish (broken relative link, no Python classifiers). **S each.**

## Later — deeper review areas

Worth a dedicated pass once the above settle; not blocking:

- The `curves/` Python layer (Solvency II / EIOPA discounting, calibration, shocked shifts) — check for divergence from the Rust kernel at and beyond knots.
- `schedule/` day-count vs the Excel `yearfrac` conventions on month-end / leap dates.
- The rollforward Python compiler (`_passes.py` / `_ir.py`) and the index / order preconditions it feeds the Rust kernel.
- The `evals/` subsystem behind the "LLM-ready" story.
- A golden-number regression net for the eventual coupled polars / pyo3 / pyo3-polars upgrade.
- A provenance / licensing note for the bundled mortality / curve / model-point fixtures.
- A quick look at published wheel contents and size.
- Convention roadmap questions — fractional age / age basis / dependent decrements, run-diff tooling, and a deprecation policy.

---

### Summary

| Priority | Focus | Items |
|----------|-------|-------|
| 1 | Correctness & first-run experience | 9 |
| 2 | Docs & onboarding polish | 9 |
| 3 | Correctness & governance follow-ups | 11 |
| Later | Deeper review areas | 8 |

Working Priority 1 top-to-bottom lands the biggest wins first — the fixes that most affect
whether a new user's first model comes out right — and the rest is steady, well-scoped polish.
