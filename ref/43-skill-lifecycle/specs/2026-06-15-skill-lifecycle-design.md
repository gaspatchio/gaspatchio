# Skill Lifecycle — maintenance, freshness, and effectiveness

**Status:** Draft for review
**Date:** 2026-06-15 (rev. 2026-06-16: shared engine, then split by public/private)
**Topic:** `ref/43-skill-lifecycle/`
**Author:** Matt Wright

A system for keeping the gaspatchio agent skills correct, current, and *provably
effective* as the core API evolves. It is **split by sensitivity across two
repos**: cheap deterministic gates run **public, in `gaspatchio-core`** (they
never ship to actuaries and need no secrets); the heavier machinery — a **shared
"md-sync" engine, the effectiveness evals, and the LLM fix/draft authoring** —
lives **private, in `gaspatchio-docs`**, serving both docs and skills. The
freshness machinery exists once. Deterministic gates first, LLM automation last.

---

## 1. Problem

Gaspatchio ships seven agent skills (`skills/*/SKILL.md` + `references/`) as a
plugin to Claude Code, Cursor, and GitHub Copilot. The skills are prose guidance
**plus embedded Python examples that call an evolving API**. Failure modes today:

1. **Source-of-truth drift.** The skill set is hard-coded in *six* places — three
   distribution manifests, the `EXPECTED_SKILLS` list in
   `tests/skills/test_skill_structure.py`, the `evals/` factories, and prose
   counts in `bindings/python/AGENTS.md`. Only `.claude-plugin/plugin.json` (a
   directory glob) is self-maintaining. When `extending-gaspatchio` was added
   (PR #90), the test list and evals were updated but the two list-based
   manifests and the prose count silently fell behind — Cursor and Copilot
   shipped 6 of 7 skills for ~two months. No check ties the manifests to disk.
2. **Example rot.** Skill examples reference `ActuarialFrame` methods, accessor
   namespaces, and CLI flags that get renamed or retired. Nothing executes skill
   code blocks against the current core, so rot is invisible until a user hits it.
3. **No proof of effectiveness.** We cannot demonstrate that a skill actually
   makes an agent produce *correct* models — only that the files are well-formed
   (`test_skill_structure.py`) and that an eval harness exists (`evals/`, 4
   models) without a rigorous effectiveness metric or CI gate.
4. **Duplication risk.** `gaspatchio-docs` has *already built* the freshness
   machinery (API-delta, example execution, sync-anchor, quarantine) for
   documentation. A second copy in core would duplicate the expensive, subtle
   half of the system — a drift-prevention system that is itself duplicated can
   itself drift. **The freshness machinery must exist once.**

## 2. Public vs private — the placement constraint

`gaspatchio-core` is **open-source** and ships a wheel to actuaries via
`uv install`. `gaspatchio-docs` is **private** and publishes only the rendered
documentation site; its tooling never ships anywhere.

**What the core wheel actually contains (verified).** The wheel (`gaspatchio`,
built by maturin from `bindings/python/`) carries only the runtime
`dependencies` — no `griffe`, `mktestdocs`, `sybil`, or `pydantic-ai`. The
maintenance-flavoured deps already sit in dev-only `[dependency-groups]`
(`evals` = `pydantic-ai`/`pydantic-evals`) that `uv install gaspatchio` / pip
never pull. The tooling dirs (`scripts/`, `evals/`, `tests/`, `skills/`,
`hooks/`) live at repo root, **outside `bindings/python/`**, so they are not in
the sdist/wheel. Skills reach actuaries via the *plugin marketplace*, not the
wheel. So maintenance code in core never reaches an actuary's machine — the real
constraints are (a) keep the public lib clean and its CI self-contained, and
(b) keep heavy/LLM/secret tooling out of public view.

**Consequence — split by sensitivity:**
- **Public, in core:** the cheap, deterministic, secret-free gates that external
  contributors should be able to run and that must write files living in core.
- **Private, in docs:** the shared engine, the effectiveness evals (need API
  keys), and the LLM fix/draft authoring.

## 3. Goals / Non-goals

**Goals**
- Cheap deterministic **skill gates run public in `gaspatchio-core`** CI:
  source-of-truth/manifest generation + guard (L0) and structural rubric (L1).
- A **single shared md-sync engine in private `gaspatchio-docs`** (API-delta +
  example execution + sync-anchor + LLM fix/draft scaffold), consumed by both
  docs and skills — no duplicated freshness machinery.
- A defensible, gated measure of skill **effectiveness** (L3), run private in
  docs where the API keys already live.
- A clear staging order; each piece ships and proves value independently.

**Non-goals**
- Rewriting skill/doc *content* now — content updates are the first downstream
  *use* of the finished system (the L4 fix/draft path), not part of building it.
- Actuary-facing tone enforcement for skills (skills are agent-facing; see D10).
- Migrating tutorials this iteration (named as a future engine consumer, §5.5).

## 4. What exists today

| Asset | Repo | Role going forward |
|-------|------|--------------------|
| `tests/skills/test_skill_structure.py` | core | **Public L1** structural gate (extended). |
| `scripts/` (manifest fix seeded here) | core | **Public L0** generator + guard lives here. |
| `.cursor-plugin/`, `.github/`, `.claude-plugin/plugin.json`; `AGENTS.md` count | core | Generated from `skills/` (L0). |
| `evals/agents.py` + `.github/workflows/evals.yml` | core | **Migrates to private docs** as the L3 harness (needs API keys). |
| `.docs-sync.yml`, `scripts/docs_delta.py`, `tests/test_docs_examples.py` + `_docs_harness.py`, Vale, `docs_quarantine.txt` | docs | Generalised into the **shared md-sync engine** (L2/L4) serving docs + skills. |

`gaspatchio-docs` already built, for documentation, exactly the freshness
machinery skills need; the engine is its generalisation, not a rebuild.

## 5. Architecture — public gates in core + shared private engine in docs

```
gaspatchio-core (PUBLIC, shipped)
  skills/ , distribution manifests
  scripts/gen_skill_manifests.py + tests/skills/    ← L0 source-of-truth + L1 structural
                                                       deterministic, no secrets, public CI

gaspatchio-docs (PRIVATE, publish-only)
  md-sync engine                                    ← Griffe API-delta · example-execution
    (one impl, two consumers)                          harness · sync-anchor · quarantine ·
                                                       fix/draft scaffold   [L2 + L4]
  consumers/
    docs/   → engine + Vale tone/evergreen            (its existing pages)
    skills/ → engine + reads ../gaspatchio-core/skills, maps symbol→skill
  evals/  (skills + docs)                            ← L3 effectiveness, needs API keys
```

Mapping to the brainstorm layers: **core** owns L0 + L1; **docs** owns the engine
(generalised L2 + L4) and L3.

### 5.1 Core (public) — L0 + L1
- **L0 source of truth.** `skills/` is canonical; `scripts/gen_skill_manifests.py`
  generates every distribution manifest + the `AGENTS.md` count/list; CI
  regenerates and asserts a clean tree (ruff `test -z "$(git status --porcelain)"`
  pattern). A guard test asserts `EXPECTED_SKILLS` matches the directory. CI also
  runs `claude plugin validate --strict` and checks cross-tool traps (kebab-case
  names, no namespace prefixes, `SKILL.md name` == dir name). No secrets; runnable
  by any contributor; never shipped to actuaries.
- **L1 structural rubric.** Extend `test_skill_structure.py` with Anthropic's
  rubric: SKILL.md ≤500 lines; references exactly one level deep; refs >100 lines
  carry a TOC; `description` third-person ≤1024 chars with a trigger clause;
  `name` matches the directory.

### 5.2 Docs (private) — the shared md-sync engine [L2 + L4]
Its subject is the core API, but it is placed in private docs (D1) because it is
heavy/LLM/secret tooling and docs already hosts its predecessor. It runs in docs'
private CI and against the sibling `../gaspatchio-core` checkout (as
`.docs-sync.yml` already does today). Capabilities:
- **Sync anchor** — a `.sync.yml` per consumer pinning the core SHA its artifacts
  are "current as of" (`core_repo`/`core_ref`/`synced_sha`). Generalises
  `.docs-sync.yml`; a `skills.sync.yml` points at core's `skills/`.
- **API symbol-delta (advisory)** — `griffe check <core-on-stubs> --against
  <synced_sha>`; the consumer maps symbols → affected artifacts; surfaced as a
  report/warning, not a hard failure.
- **Example-execution harness (hard)** — extract runnable code blocks, execute
  against a freshly-built core. Bar = *run-without-error*. Fragment-aware: default
  *run-only*; **skip marker** (HTML comment before the fence) for pseudocode;
  **invisible setup blocks** to inject shared imports/fixtures; **namespace shared
  within a file** with explicit reset. Engine = **mktestdocs** (what docs uses);
  **Sybil** the documented upgrade.
- **Quarantine** — `<consumer>_quarantine.txt` of known-broken artifacts marked
  `xfail(strict=True)`.
- **Fix/draft authoring scaffold** — the narrow LLM skill pattern
  (DETECT→MAP→EDIT→VERIFY→REVIEW), parameterised by consumer, two modes invoked
  separately: **fix** (repair flagged examples) and **draft** (author new
  artifact/section for a feature surfaced by the delta). Automated ceiling = edits
  on a fresh branch + report, then STOP. Never gates CI. **Content updates are a
  first-class use of fix/draft.** A fix PR is opened *back into core* for skills,
  or stays in docs for docs.

### 5.3 Docs (private) — effectiveness evals [L3]
Today's core `evals/` migrates here (it needs LLM API keys, already a private-CI
concern). Adopt Anthropic's shape: `evals/<skill>.json`
(`prompt`/`expected_output`/`expectations`). Trigger-test → Executor →
**execution-dominant Grader** (`gspio run-model … --output-file` → parquet checked
against expected within tolerance, à la the L4-lifelib 0.0000% match; plus
"doesn't break"); LLM-judge a **minority** grader for subjective style,
reference-guided + position-swapped. **Comparator** runs with-skill vs
without-skill paired in the same turn; **headline metric = per-model paired lift**
(CI excluding 0), never pooled. **Analyzer** flags always-pass assertions and
high-variance evals. Multi-trial, clustered SEM, **pass^k** for reliability;
determinism in the oracle. Gate = lift *regression*, not a raw pass floor; keep a
held-out task set.

### 5.4 Why this resolves both concerns
The public shipped lib stays lean and its CI self-contained (only L0/L1, no
secrets); the heavy/LLM/secret machinery and the one freshness engine sit private
in docs, serving docs and skills from a single implementation. No duplication; no
maintenance tooling in public view beyond the cheap deterministic gates.

### 5.5 Tutorials (future engine consumer)
Tutorial models (`tutorial/`, Levels 1–5) are a third executable-markdown
consumer (execute examples; reconcile numbers). Named so the engine contract
anticipates it; not built this iteration.

## 6. Design decisions

- **D1 — Split by sensitivity: cheap deterministic gates public in core; the
  shared engine, evals, and authoring private in docs.** *Why:* core is
  open-source/shipped — keep it lean and its CI self-contained and secret-free;
  docs is private/publish-only and already hosts the freshness machinery, so it is
  the right home for heavy/LLM/secret tooling. Maintenance code in core would not
  reach actuaries (verified, §2), but visibility + clean CI still argue for the
  split. *(Supersedes earlier "engine in core" framing.)*
- **D2 — `skills/` is the one canonical source; all else generated or checked**
  (ruff pattern). *Why:* the PR #90 drift came from six hand-maintained lists.
- **D3 — Deterministic gates run first and block; LLM automation never gates.**
  *Why:* field merge-rate data (96–100% vs 43%); merged PRs pass CI.
- **D4 — Example execution is the hard freshness gate; Griffe delta is advisory.**
  *Why:* execution catches actual rot; not every API change touches an artifact.
- **D5 — A consumer pins a core SHA in a `.sync.yml`; Griffe runs on `.pyi`
  stubs.** *Why:* buildless, rebase-proof; stubs are `mypy.stubtest`-validated.
- **D6 — Effectiveness = per-model paired lift, execution-oracle-dominant;
  LLM-judge minority, reference-guided + position-swapped.** *Why:* Anthropic's
  method + SWE-bench execution grading; documented judge biases.
- **D7 — Skills structural gates encode Anthropic's rubric; add `claude plugin
  validate --strict` and cross-tool trap checks.** *Why:* cheap, deterministic,
  catches silent load failures.
- **D8 — Currency via regenerate-from-gated-source on a deliberate human cadence,
  not auto-pull-latest.** *Why:* keeps gates strict; the synced SHA is bumped by a
  human on a clean run.
- **D9 — Authoring (fix/draft) is narrow, separately invoked, human-finishes-the-
  loop, ceiling = branch + report + STOP; content updates are a first-class use.**
  *Why:* mirrors the docs design and the 43% broad-agent ceiling.
- **D10 — No actuary-facing tone gate for skills; an optional light anti-pattern
  lint only.** *Why:* skills are agent-facing; a small Vale-style anti-pattern
  check is an optional skills-consumer extension, not core.
- **D11 — The engine generalises docs' existing machinery and is consumed by
  skills from docs' private CI via the sibling core checkout; skill fix PRs are
  opened back into core.** *Why:* docs already checks out core and pins it in
  `.docs-sync.yml`; reuse that wiring rather than invert the public→private
  dependency into core's CI.

## 7. Cross-repo wiring
- **Core (public):** L0 generator + guard and L1 rubric run in core's own CI
  (`CI.yml`), no secrets. These are the only skill-lifecycle pieces in the public
  repo. The manifest fix on this branch is the seed of L0.
- **Docs (private):** hosts the engine + L3 evals; its CI checks out core
  (already does), builds it (maturin), runs the engine over docs pages *and*
  core's `skills/`, and runs evals with API-key secrets. Skill freshness/eval
  findings open fix PRs back into core (where skills live).
- **Currency:** the engine is versioned; the `skills.sync.yml` in core (or docs)
  pins the core SHA skills are validated against; bumped by a human on a clean run.

## 8. Sequencing
Build deterministic-first; each stage is shippable:
1. **Core L0 + L1** (public, this repo/branch). Highest confidence; closes the
   PR #90 class of bug; seeded by the committed manifest fix. **← the first plan.**
2. **Docs: generalise the existing machinery into the shared engine; add the
   skills consumer** (skill example extraction + symbol→skill map + freshness run
   over `../gaspatchio-core/skills`). The field-leading differentiator.
3. **Docs: L3 effectiveness evals** (migrate core `evals/`, extend with paired
   lift + execution oracle).
4. **Docs: fix/draft authoring scaffold (L4)** — then run the pending **content
   updates** through it as the first real use.
5. **Docs: point its own pages at the shared engine; retire bespoke scripts.**
   Tutorials later.

## 9. Testing the system itself
- Core L0/L1: pytest + a generator-diff CI step; self-tested with fixture skills
  (a known-bad skill must fail each rule), mirroring docs' `test_vale_rules.py`.
- Engine harness (docs): self-tested with a deliberately-rotted example (must
  fail) and a fragment with a skip marker (must be skipped); a shared suite both
  consumers run.
- L3 harness (docs): self-tested with a stub skill whose lift is known.

## 10. Risks & mitigations
- **Skill rot caught in docs CI, not core PRs.** Because freshness runs private in
  docs, a core PR that breaks a skill example is caught in docs CI / a scheduled
  run, not at core PR time. *Mitigation:* the cheap L0/L1 gates run in core PRs;
  freshness runs on core's main + on a schedule, opening fix PRs back. Acceptable
  given the same model already governs docs example-rot today.
- **Examples that run but are subtly wrong** — run-only bar catches raises, not
  stale-but-valid numbers. *Mitigation:* `assert`-based examples; L3 numeric oracle.
- **Heavy projections slow CI** — small fixtures; scope to changed artifacts,
  full sweep on a schedule.
- **Griffe blind to Rust surface** — only sees `.pyi` stubs. *Mitigation:* stubs
  are `stubtest`-validated.
- **Eval gaming / overfitting** — held-out task set; Analyzer flags
  non-discriminating assertions; gate on lift regression, not absolute pass rate.

## 11. Open questions
- Engine packaging shape inside docs (module vs CLI) and how the skills consumer
  is configured.
- Execution scope per run: changed-artifacts-only vs full sweep (+ schedule).
- Whether L3 reuses an existing harness (promptfoo / Inspect AI / DeepEval) or
  extends the migrated `evals/`.
- Exact skip-marker / invisible-setup syntax (mktestdocs comment vs info-string).
- Migration ownership/timing of core `evals/` → docs, coordinated with the docs
  repo roadmap.

## 12. Sources
Anthropic Agent Skills spec & best-practices; Claude Code plugins reference;
anthropics/skills evals + skill-creator; "Demystifying evals for AI agents";
"A statistical approach to model evals"; Zheng et al. MT-Bench (arXiv 2306.05685);
SWE-bench; Cursor Rules; VS Code agent-plugins; MCP tools spec; obra/superpowers
v2.0; gh-aw continuous-docs field data; MSR 2026 failed-PR study (arXiv
2601.15195); Sybil, pytest-examples, mktestdocs, Polars run_doctest, ruff CI,
Griffe, Vale; and the `gaspatchio-docs` implementation. Full briefs in
`ref/43-skill-lifecycle/research/`.
