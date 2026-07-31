# v0.6.0 outstanding-issue batch — design

**Date:** 2026-07-27
**Status:** approved, ready for planning
**Target release:** v0.6.0 — a single release carrying every fix, cut when the work is done
rather than to a date
**Supersedes nothing.** Continues the cycle of `ref/47-post-release-cleanup/` one release on.

---

## 1. Context

Two independent streams produced the same class of finding.

**A field report.** An actuary at a large insurer replicated a messy production spreadsheet
in under a day, then had a coding agent post-mortem the framework. The result was a
self-contained, LLM-readable document: 13 findings, each with a reproducer and a `file:line`
citation, explicitly review-only. Every one was reproduced against a fresh checkout and
confirmed real. Findings are tracked publicly as anonymised issues with rewritten examples.

**An internal correctness audit**, which independently surfaced 5–6 of the same defects plus
a batch of adjacent ones.

Ten issues (#21–#30) are already fixed and merged, awaiting release. They are tagged
`pending-release` and are **not** in scope here except for the release mechanics in §7.

This document triages what remains.

### The through-line

Almost every merged fix and most of what follows share one shape: **the framework accepted
input, did something other than what the caller meant, and said nothing.** Lookup misses
became `NaN`. Categorical keys all collided into one bucket. A documented rename mapping was
never applied. A declared `extrapolation` mode is read by nothing.

In a framework whose stated position is *audit by default*, silence is the defect. That
observation is the spine of every verdict below.

---

## 2. The triage lens

Verdicts are justified against [`PRINCIPLES.md`](../../../PRINCIPLES.md) by name. Where two
principles pull in opposite directions, the resolution recorded there applies:

> **Be liberal about the shapes you accept, be strict about the meanings you infer.**

This settles the two contested items (#37, #36) in opposite directions, which is the point —
it is a rule, not a preference.

---

## 3. Verdicts

| # | Issue | Verdict | Principle | Size |
|---|---|---|---|---|
| 33 | CI resolves dev deps fresh | **done** — see §8 | *Audit by default* | — |
| 38 | Unary `-col` fails on `list<f64>` | fix | plain bug | XS |
| 35 | Quickstart calls a removed projection API | fix | *LLM-shaped* | S |
| 40 | `gspio describe` fails on list columns | fix | *LLM-shaped* | S |
| 42 | Timing conventions unsignposted | fix | *Audit by default* | S |
| 37 | Bare-string lookup key misleads | **reshape** → error, not auto-wrap | *strict about meanings* | S |
| 31 | `log_linear` extrapolation collapses long end | fix via live `extrapolation` param | *Sharp knives* | M |
| 36 | No period-index column after `projection.set()` | fix — materialise | *Meet you where you are* | M |
| 39 | Collect-time errors don't name the column | fix | *Audit by default* | L |
| 41 | No guided path for porting an Excel workbook | **defer** | scope, not vision | XL |

### Why #41 is deferred

Excel-origin ports are a large share of real workloads and the gap is genuine. But it is an
entire skill — workbook discovery, dependency analysis, anchor selection, extraction, and a
cell-level diff harness — not a fix. It cannot land in this window without being bad, and a
bad port skill is worse than none. It stays open, scoped to the next release.

This is the only item where "not fixing" is the answer, and the reason is capacity, not
disagreement with the request.

---

## 4. Per-issue design

### #38 — unary negation on list columns

`-af.some_list` raises `InvalidOperationError: neg operation not supported for dtype
list[f64]`, while `0.0 - col` and `col * -1.0` both work. A missing `__neg__` on the
expression proxy, not a list limitation.

**Design.** Add `__neg__` to the expression/column proxy, implemented as multiplication by
`-1.0` (the path already proven to work on list dtypes). Do **not** add `__pos__`/`__abs__`
speculatively — `.abs()` already exists as a method and no one has asked for the others.

**Tests.** `-col == 0.0 - col` elementwise on a list column and on a scalar column; nested
inside `when/then/otherwise`.

---

### #35 — stale quickstart API

`af.date.create_projection_timeline(...)` no longer exists. Confirmed: zero hits in
`gaspatchio_core/`. The current API is `af.projection.set(...)` and **the parameter names
differ too**, so there are two stale places, not one:

| Location | Stale | Current |
|---|---|---|
| AGENTS.md, "Model Structure: Three Phases" | `af.date.create_projection_timeline(valuation_date=, projection_end_type=, projection_end_value=100, projection_frequency=)` | `af.projection.set(valuation_date=, until="maximum_age", until_value=100, frequency="monthly")` |
| AGENTS.md, Gotcha #2 | `projection_end_value=99` | `until_value=99` |

**Design.** Correct both, sweep `skills/` for the same call, and regenerate
`.github/copilot-instructions.md` (generated from AGENTS.md by
`scripts/gen_skill_manifests.py`, guarded by `tests/skills/test_skill_manifests.py`).

**The durable part.** Correcting the text fixes today and drifts again next release. The
quickstart example must become **executable** — extracted into a smoke test that runs the
documented snippet end to end. AGENTS.md is auto-loaded by every agent session; an example
that has silently rotted is the single highest-leverage defect in the repository, because it
makes every downstream session start from a false premise. *LLM-shaped from the inside out*
is not satisfied by prose that happens to be correct on the day it was written.

---

### #40 — `gspio describe` on parquet with list columns

`gspio describe` on a file containing `list<f64>` fails with
`Unsupported key type for array storage: List(Float64)` — it attempts to register the file as
an assumption table. Describing a model's own run output is the reflex the CLI's own agent
workflow instructs ("always use `--output-file`, then read the parquet"), so the documented
happy path is what breaks.

**Design.** `describe` summarises; it must not route through assumption-table registration.
Detect list columns and report dtype, inner dtype, length statistics (min/max/modal) and a
first-row preview. If a file genuinely cannot be interpreted as an assumption table, say that
in the CLI's own vocabulary rather than leaking a storage-layer message.

**Tests.** `describe` on a parquet with a `list<f64>` column exits 0 and names the column;
the `--json` form stays machine-readable.

---

### #42 — timing conventions unsignposted

`prospective_value`'s beginning/end-of-period semantics are documented in its docstring, but
AGENTS.md never mentions timing conventions at all, so the read-AGENTS-first path can miss
that it is a choice. #28 additionally fixed the discount-factor input contract (factors are
timing-anchored).

**Design.** A short signposting section in AGENTS.md: name the choice, state the default,
cross-reference the docstrings. A signpost, not a treatise — the detail belongs where it
already lives.

---

### #37 — bare-string lookup key (reshaped)

`tbl.lookup(product="annuity", age=af.age)` routes the string to `pl.col(...)`, so it is read
as a column name and fails with `ColumnNotFoundError: Column 'annuity' not found. Did you
mean...` — pointing away from the actual mistake.

**The issue proposes two options; we take the second, deliberately.** Auto-wrapping bare
scalars as literals infers a *meaning* from a *shape*, which is what *Sharp knives, no magic*
forbids, and it would silently change behaviour for anyone legitimately passing a column name
as a string. This is *Meet you where you are* losing to *strict about the meanings you infer* —
the one place in this batch where the two genuinely collide.

**Design.** Keep `str` → column. When a dimension key given as a bare string does not resolve
to a column, raise a targeted error naming **both** remedies and the table/dimension involved:

```
Table 'rates', dimension 'product': "annuity" was read as a column name and no such
column exists.
  • for a literal value:  product=pl.lit("annuity")
  • for a column:         product=af["annuity"]
```

`errors/formatter.py` already enriches `ColumnNotFoundError`; this extends that path rather
than adding a new one.

**Tests.** Assert the raised message contains both remedies and the dimension name.

---

### #31 — curve extrapolation

**Current behaviour.** `log_linear` interpolates linearly in log-discount-factor space via
`eval_linear`, which flat-clamps `ys` outside the knot range. For `log_linear`, `ys` are
log-DFs, so clamping holds the **discount factor** constant — it stops decaying entirely. A
flat 5% curve with a last knot at 10y evaluated at 30y returns a spot of ≈1.64%
(`0.50/30`), and `DF(30) = 0.607` against a correct `0.223` — the cashflow is carried at
roughly **2.7× its true value**. (A flat curve gives the same answer under either convention
below, which is what makes it the clean illustration.)

**Root cause is narrower than "wrong convention".** Look at what flat-clamping means per
method:

| method | `ys` are… | flat-clamping `ys` gives… |
|---|---|---|
| `linear`, `pchip` | rates | constant spot — correct |
| `log_linear` | log-DFs | constant DF — the collapse |

"Flat" is being applied **in the wrong space, for one method only.** Every other knot method
is already fine.

**The `extrapolation` parameter already exists and is dead.** It is declared in the Rust
kwargs struct (`curve_eval.rs:27`), defaulted to `"flat"` in `plugins.py:300`, serialised into
the kwargs dict at line 360, threaded across the plugin boundary — and **never read**
(`grep` for any read of `.extrapolation` in `core/src/` returns nothing). Its own doc comment
concedes it: *"Currently always flat (the only supported value); reserved for future
methods."* A user setting it gets it silently ignored: the same defect class as #24.

**Design.** Make the parameter live. In the `log_linear` arm only:

| value | behaviour |
|---|---|
| `"flat"` *(default)* | clamp the **spot rate**, not the log-DF — fixes the collapse and makes `"flat"` mean the same thing across all four methods |
| `"forward"` | extend the last segment's log-DF slope: `lnDF(t) = lnDF(Tₙ) + s·(t − Tₙ)`, `s = (yₙ − yₙ₋₁)/(xₙ − xₙ₋₁)` — constant forward, the market-consistent choice |
| anything else | `ComputeError` naming the valid options |

Both ends of the range need fixing: below the first knot, `log_linear` has the same
wrong-space clamp today.

`linear`/`pchip` accept only `"flat"` and error on `"forward"` rather than accepting and
ignoring it — no new silent parameters.

**Default rationale.** `"flat"` keeps the existing default value, changes no call signature,
and gives one coherent cross-method meaning. `"forward"` is documented as the market-consistent
choice for long-tail discounting. We ship both rather than picking one, because reconciliation
against a reference model may require either — but we do *not* add further modes speculatively.
Smith-Wilson (`fit_smith_wilson`, EIOPA/Solvency II) and `svensson` already exist as separate
methods and are unaffected.

**Worked expectations** (knots 4%@5y, 5%@10y; last-segment forward 6.0%; continuous
compounding for exposition):

| at t=30y | spot | DF |
|---|---|---|
| current (broken) | 1.67% | 0.607 |
| `"flat"` | 5.00% | 0.223 |
| `"forward"` | 5.67% | 0.183 |

**Breaking.** Long-end numbers move for anyone using `log_linear` beyond the last knot. This
is the third breaking change in v0.6.0 alongside #24 and #28; see §7.

**Tests.** Flat 5% curve returns 5% at 30y under **both** modes (self-consistency); the sloped
example returns the table above; an unknown value raises; a regression pin ensures 1.64% can
never reappear.

---

### #36 — period index after `projection.set()`

`projection.set()` materialises no period-index column, yet shipped examples use `af.month`
as though one existed. Users derive it themselves.

**Confirmed worse than reported.** There is a family of expression-returning helpers —
`t_years()`, `year_fractions()`, `period_dates()`, `anniversary_mask()`, `is_in_force()` — and
`t_years()` returns length `n_periods + 1` while `year_fractions()` returns `n_periods`.
Anyone hand-rolling a period index has an off-by-one waiting, which is Gotcha #2
(`projection_end_value=99`) in a different costume.

**Is materialising columns "magic"?** No. A period index is not an inferred *meaning*; it is a
definitional consequence of declaring a time axis. Refusing to provide it is not sharpness,
it is making everyone write the same error-prone snippet. This is the closest call in the
batch and it is recorded as a judgement, not a derivation.

**Design.** `projection.set()` materialises two columns:

| column | definition |
|---|---|
| `month` | elapsed whole months from projection start: `0, 1, 2, …` monthly; `0, 3, 6, …` quarterly; `0, 12, 24, …` annual |
| `proj_year` | `month // 12` |

**Naming.** `month` matches every shipped example (AGENTS.md, `ref/ARCHITECTURE.md`, the
dispatch-engine specs). A column named `year` was **rejected**: `ref/05-dsl-polars-wrapper`
uses `af["year"]` for *calendar* year, AGENTS.md Gotcha #7 names `proj_year` vs `year` as
causing silently-wrong stress scenarios, and the scenario design doc calls it "the catastrophic
`proj_year` vs `year` class of error". Materialising a framework-owned `year` would collide
with model-point data that routinely carries a calendar year and make a documented trap fire
*more* often. `proj_year` is the name the gotcha itself uses.

**Defining `month` as elapsed months rather than a period counter** keeps the name honest at
every frequency — a column called `month` that counts years would be its own trap.

**Length.** `n_periods + 1`, aligned with `t_years()`, so that a maturity test
`when(af.month == af.policy_term * 12)` can actually fire on the final boundary.

**Collision.** If the frame already carries `month` or `proj_year`, **raise**, naming the
collision and the remedy. Silently overwriting a user's calendar column is precisely the
failure this whole batch exists to eliminate.

**Jagged timelines.** Per-policy (`per_policy=True`/auto) projections produce variable-length
lists; `month` and `proj_year` must be jagged to match, not padded to the longest policy.

**Tests.** Monthly/quarterly/annual frequencies; uniform and jagged; length `n_periods + 1`;
the maturity example from AGENTS.md evaluates correctly; collision raises.

---

### #39 — collect-time error attribution

A lazy chain failing at `collect()` with e.g. `ShapeError: list lengths differed at index 0:
6 != 3` never says which assigned column produced it. In a 50-column model that is a long
hunt. Assign-time errors are already attributed; collect-time errors are not.

This is a **principle violation**, not an ergonomic wish: *Audit by default* promises that
"every output column carries expression lineage that traces back through every intermediate
step." The lineage exists — #18 made the computation graph record-only metadata, and
error-boundary diagnosis already replays against a pristine frame. The error path simply does
not use it.

**Design.** At the `collect()` boundary, catch raw Polars errors (`ShapeError`,
`InvalidOperationError`, `SchemaError`), use the recorded graph to attribute the failure to
the assigned column that introduced it, and re-raise enriched with the column name and its
source expression.

**Non-negotiable fallback.** If attribution fails or is ambiguous, surface the original error
**unchanged**. An error path must never make the error worse — a wrong column name is more
expensive than no column name.

**Tests.** Ragged-list assignment names the offending column; a multi-column chain attributes
to the correct one; an unattributable error passes through byte-identical.

---

## 5. Sequencing

Five pull requests. **The release is cut when the work is done, not to a date** — every fix
below ships in v0.6.0, and nothing is pre-designated to drop.

| PR | Contents | Risk |
|---|---|---|
| 1 — papercuts | #38, #35, #40, #42 | none |
| 2 — lookup boundary | #37 | low |
| 3 — period index | #36 | medium |
| 4 — curve extrapolation | #31 | medium |
| 5 — error attribution | #39 | high |

The ordering is still cheapest-and-most-certain first, but for a different reason now that
there is no deadline: PRs 1 and 2 touch surfaces that PRs 3–5 also touch (AGENTS.md examples,
the lookup error path), so landing them first means the harder work rebases onto corrected
foundations rather than the other way round.

**#39 is no longer at risk.** An earlier draft designated it the item to drop if a two-day
window proved optimistic. That constraint was lifted: the decision is to include every fix and
take the time. #39 is the one item whose cost cannot be estimated before starting — it must
work backwards from an error surfacing at the end of a lazy chain to the assignment that
caused it — so it is scheduled last to keep that uncertainty off the critical path, not
because it is expendable.

Seven of the eight fixes are from the field report (#35, #36, #37, #38, #39, #40, #42); #31
and #33 came from the internal audit. All thirteen of the reporter's findings are therefore
resolved or deferred-with-a-tracking-issue by the time v0.6.0 ships.

---

## 6. Testing strategy

Every fix ships a regression test pinning the **exact reported symptom**, not a paraphrase —
`1.64%` for #31, `neg operation not supported` for #38, the ragged-list message for #39. The
merged batch (#21–#30) established this pattern; it is what turns a fixed bug into a bug that
stays fixed.

The full suite must stay green: **2,644 passed, 8 skipped, 5 xfailed, 1 xpassed** at the time
of writing, run with the tracked lockfile (§8).

---

## 7. Release and communication

v0.6.0 carries **three breaking changes**, so release notes lead with migration, not features:

1. **#24** — lookup misses now raise (`on_missing="raise"` default). Opt out per table or per
   lookup with `on_missing="nan"` / a constant.
2. **#28** — `prospective_value` varying-rate `end_of_period` values change; NaN cashflows no
   longer silently zeroed.
3. **#31** — `log_linear` long-end numbers change past the last knot.

On release, the ten `pending-release` issues (#21–#30) plus this batch need version-stamping
so each shows the version carrying its fix.

The field reporter needs a direct heads-up on #24 in particular: a `when()` guard wrapped
around a lookup that deliberately relies on misses will now raise unless `on_missing="nan"` is
declared. That is the one change most likely to break the model already built against v0.5.x.

---

## 8. Already done (this branch)

**#33 — CI dependency reproducibility.** CI resolved dev dependencies fresh on every run, so a
PR's result depended on what PyPI released that morning: ruff floated to 0.16.0 and failed ~70
docstring-example tests on a PR that touched none of them. The lockfile existed locally but was
gitignored — laptops reproducible, CI not, which is the arrangement that hides the problem.

Fixed by tracking `bindings/python/uv.lock` and installing with `uv sync --locked` at all
twelve sync sites (eleven were still floating, including `evals.yml`, which runs on every push
to main).

A repository-root `pyproject.toml` was added declaring the workspace boundary: without it `uv`
walks up out of the repository and, in a multi-repo checkout, resolves against sibling
repositories, so `uv run` from the root failed with a dependency conflict belonging to another
project. `bindings/python` is **excluded** rather than made a member — as a member, uv
relocates the environment and lockfile to the root, orphaning the lockfile CI expects and
forcing every contributor into a full Rust rebuild.

Separately, `PRINCIPLES.md` now lives in the repository and is imported by `CLAUDE.md`, so
every agent session loads the north star. That gap is why this triage is the first to be
argued against the principles by name.

---

## 9. Open risks

| Risk | Mitigation |
|---|---|
| #39 attribution is harder than the graph suggests | Fallback to the unmodified error; scheduled last so the unknown sits off the critical path |
| #36 `month` semantics at non-monthly frequencies | Defined as *elapsed months*, so the name stays honest; covered by tests at three frequencies |
| #36 collides with existing user columns | Raise rather than overwrite |
| #31 long-end change surprises a reconciliation | Both modes shipped; migration note leads the release |
| Release date slips while two breaking changes sit unreleased | Accepted deliberately: the decision is one complete release over an early partial one. Mitigated by telling the field reporter directly that #24 and #28 are coming and what they change (§7) |

---

## 10. Amendments (2026-07-30)

Two §4 decisions changed during implementation review. Recorded here so the spec and the
code do not silently disagree.

### #37 — flipped from "targeted error" to "bare string is the value"

The targeted-error implementation drew three real review findings (a cross-frame false
positive that rejected *valid* lookups, wrong diagnosis ordering on a misspelled dimension,
broken quoting in the suggested remedy). The deeper problem was the premise: keeping
string-as-column forces `pl.lit("annuity")` — Polars in the middle of the most ordinary
actuarial operation there is — against *Meet you where you are*.

**Decision (Matt):** a bare string is the dimension **value** (VLOOKUP semantics). Columns
are referenced as `af.product` / `af["product"]` / `pl.col(...)`. This is the fourth
breaking change in v0.6.0, made safe by #24: a caller who relied on string-as-column gets a
loud lookup miss naming the key, not silently wrong numbers. The framework's own older
design docs already wrote lookups this way (`sex="M"`, `scalar_id="mort"`). Shipped in PR
#46.

### #36 — `proj_year` dropped; `month` only, stamped only where honest

Review found the materialised `proj_year` (0-based `month // 12`) contradicted the shipped
model-building skill, which defines it as BSCR-ordinal "year 1" via a ceiling. Research
showed the conflict is irreducible: the framework already carries **both** year conventions
under different names (lifelib-style 0-based `duration` in every reconciled model;
1-based ordinal in the skill and Excel's `ROUNDUP(t/12, 0)`), the two disagree at every
anniversary boundary, and *which* is correct for a stress shock depends on the model's
beginning/end-of-period timing convention — the user choice §4/#42 documents. A
framework-materialised `proj_year` therefore silently picks the user's timing convention:
*Sharp knives, no magic* says that column must not exist.

**Decision (Matt):** no `proj_year`. `set()` stamps **`month`** only (Int32), and only
where the name is honest — month-aligned frequencies, projection-anchored axes (not
`from_inception`, whose elapsed months are policy *duration*; not 1W/1D, where a
calendar-month difference over-counts). AGENTS.md documents both one-line year formulas
and why the framework stamps neither. Also halves the feature's memory cost (~577 MB per
Int64 column at 100K policies × 60y monthly). Reworked in PR #47.
