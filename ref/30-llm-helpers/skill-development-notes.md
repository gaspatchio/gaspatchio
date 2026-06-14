# Skill Development Notes

Observations from building tutorial models — feeds into skill improvements.

## Format

Each entry records:
- **What I was doing** when the observation arose
- **What the building skill would have done** (helped / missed / wrong)
- **Skill fix needed** (if any)
- **Status**: applied or pending

---

## Observations

### During L3 (mini-va) development

1. **Broadcasting a constant to a list column.** To create a lapse rate list from a scalar constant, I used `af.month * 0 + LAPSE_RATE_ANNUAL`. This is a common pattern but non-obvious. The building skill should document this idiom or recommend scalar assignment. **Status: APPLIED** — added to common-mistakes.md #18 and gotcha table #11.

2. **Section numbering matches L4.** I deliberately structured L3 with numbered sections that map to appliedlife's sections. The building skill's "three-phase build pattern" (setup → projection → calculations) is too coarse — it should acknowledge that real models have 10+ logical sections. **Status: APPLIED** — replaced calculation order in model-phases.md with 11-section table matching tutorial/appliedlife structure.

3. **`--output-file` not referenced anywhere in building skill.** The building skill says to use `gspio run-single-policy` for validation but doesn't mention `--output-file`. An agent following the skill would parse stdout instead of writing parquet. **Status: APPLIED** — added to Environment section, Validate Incrementally section, and reconciliation skill's Running Comparisons section.

4. **Standalone `if __name__` block.** The model includes a standalone execution block so it can be run directly (`python model.py`) as well as via `gspio run-model`. The building skill doesn't mention this pattern. **Status: APPLIED** — added to model skeleton in gaspatchio-building.md.

5. **`exp/log` identity for scalar^list.** Used `(af.month / 12.0 * math.log(1.0 + INFLATION_RATE)).exp()` for inflation factor. This is the standard pattern for computing `scalar ** list_column` without breaking the lazy pipeline. The building skill should document this. **Status: APPLIED** — added to common-mistakes.md #19 and gotcha table #12.

6. **No `gspio docs` lookup needed during L3 build.** Because I already know the API from reading the codebase. But a fresh agent would need to look up: `cumulative_survival` vs `cum_prod`, `previous_period`, `next_period`, `create_projection_timeline`, `str.to_date`, `finance.compound`. The building skill's mandatory lookup gate is correct and important. **Status: No fix needed — validates the skill.**

7. **Missing: model-review skill.** After building the model, there's no skill that says "now check it." A model-review skill would verify: all sections have comments, formulas match documentation, no `map_elements`, no Python loops, `--output-file` used for validation, key outputs have expected signs/magnitudes. **Status: PENDING** — new skill to be created in Phase 3.

8. **`when()` with boolean multiplication pattern.** L4 uses `af.pols_if_bef_mat * (af.duration_mth_t <= af.maturity_month)` — boolean masking via multiplication instead of `when().then().otherwise()`. Initially used the same in L3 but reverted. **Status: APPLIED** — added to conditionals-and-lists.md and gotcha table #13.

9. **Prefer `when/then/otherwise` over boolean masking for tutorial/teaching code.** Boolean masking reads like a programmer's trick; `when().then().otherwise()` reads like English and mirrors Excel's IF(). For a tutorial aimed at actuaries, readability > brevity. **Status: APPLIED** — added "Default: Prefer when/then/otherwise" section to conditionals-and-lists.md.

### During Step 06 / L4 reconciliation work

10. **Tutorial references in skills.** The discovery, building, and reconciliation skills should point to the tutorial levels as starting points and examples. **Status: APPLIED** — added tutorial reference sections to all three skills.

11. **Reconciliation report format.** A structured `reconciliation_status.md` is the gold standard format. 0.0000% is the benchmark — not "approximately zero." **Status: APPLIED** — created `tutorial/level-4-lifelib/reconciliation_report.md` in this format; reconciliation skill now references it as a template.

### During L3 Step 06 reconciliation exercise and L1/L2 builds

12. **Deliberate-gap reconciliation is a powerful teaching pattern.** Building a model with 4 deliberate gaps and having the student discover them via reconciliation produces dramatic, measurable mismatches (2.5%–51.7%). This is far more engaging than explaining theory — the student sees FAIL, investigates, fixes, sees PASS. The reconciliation skill should recommend this pattern for onboarding. **Status: APPLIED** — skills/model-reconciliation/SKILL.md "Learning reconciliation" section.

13. **DL002 formula produces the largest mismatch (up to 51%).** When a model applies the wrong dynamic lapse formula (DL001 for all products), GMAB points fail dramatically because DL001 gives factor=1.0 while DL002 gives clip(ITM, Floor, Cap). This is a great example of product-specific formula selection — the building skill should emphasise that `formula_id` or `product_id` driven `when/then` branching is standard. **Status: APPLIED** — skills/model-building/SKILL.md "Product-specific formulas" section.

14. **`accumulate()` vs `cum_prod()` gives identical results for IF.** For in-force business (no premium injection), `accumulate(initial=V, multiply=G, add=0)` produces the same result as `V * cum_prod(G)`. The difference only matters for NB (where `add=prem_to_av`). A reconciliation against IF data won't catch this gap numerically — you need intermediate variable comparison or NB data. The reconciliation skill should note that "passing PVs is necessary but not sufficient." **Status: APPLIED** — skills/model-reconciliation/SKILL.md "Matching intermediates, not just aggregates" section.

15. **Closed-form discount factors differ from cum_prod when rates change.** Lifelib uses `(1+r)^(-t)` (current period's rate as if it always applied), while cum_prod chains each period's actual rate. With USD BASE rates varying from 3.357% to 3.366%, this produces a small but measurable PV difference across all points. Key lesson: reconciliation means matching the reference's formula convention, not being "more actuarially correct." **Status: APPLIED** — skills/model-building/references/timing-and-dates.md "Discount factor conventions" section.

16. **Data pipeline is the biggest L3→L4 change, not formulas.** L3 Step 05 puts product parameters directly on model points. L4 joins them from 3 assumption tables (product_params_gmxb, dynamic_lapse_params, space_params) and unpivots scenario_returns. The projection formulas are nearly identical. The building skill's focus on formula correctness is right, but should also cover data pipeline patterns (joins, unpivots, cross-joins for shared params). **Status: APPLIED** — skills/model-building/SKILL.md "Data enrichment patterns" section.

17. **Table.lookup() is exact-match, not interpolating.** When building L2's mortality table, the initial design used breakpoint ages (25, 30, 35...) but Table.lookup() requires exact key matches. The subagent had to generate a full integer-age table using Gompertz formula. The building skill should explicitly state this and recommend generating full-range tables. **Status: APPLIED** — skills/model-building/references/common-mistakes.md entry #20.

18. **`pols_if_bef_decr` ordering matters for NB but not IF.** The BEF_MAT/BEF_DECR pattern (maturities → remove → add NB → deaths → lapses from survivors) gives identical results to simple ordering for IF business because pols_new_biz=0. The difference only shows in NB or at the maturity month boundary. Like observation 14, this gap requires either NB data or intermediate comparison to detect. **Status: APPLIED** — skills/model-building/references/model-phases.md "Decrement ordering: BEF_DECR pattern" section.

19. **Tutorial progression validates the skill design.** L1 (scalars) → L2 (Tables) → L3 (full VA with steps) → L4 (production reconciliation) maps cleanly to the discovery → building → reconciliation skill chain. Each level introduces exactly the concepts that the corresponding skill teaches. The complete tutorial (25 runnable models, all tested) is now the primary reference for skills. **Status: APPLIED** — all 6 skills reference tutorial levels as worked examples.
