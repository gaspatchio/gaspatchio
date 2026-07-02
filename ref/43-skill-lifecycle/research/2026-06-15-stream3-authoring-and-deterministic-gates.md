# Research Stream 3 — Skill authoring structure + deterministic validation gates

**Date:** 2026-06-15 · primary-source brief · `VERIFIED` = official docs/repos; `[INFERENCE]` = labelled.

---

## 1. Authoring structure (what correlates with quality)
**Anthropic "Skill authoring best practices" + Skills overview [VERIFIED]:**
- **Progressive disclosure** is the core mechanism: only `name`+`description` pre-loaded; SKILL.md read on trigger; references on demand.
- **SKILL.md under 500 lines.**
- **References one level deep** — "Claude may partially read files when referenced from other referenced files" (uses `head -100` previews → incomplete info). Directly checkable.
- **Reference files >100 lines need a TOC** so partial reads see full scope.
- **Description is THE discovery lever:** third person, includes *what it does AND when to use it* with trigger keywords. `name` ≤64 chars (lowercase/hyphens, no "anthropic"/"claude"); `description` ≤1024 chars. "Inconsistent point-of-view can cause discovery problems."
- **Naming:** gerund form (`processing-pdfs`).
- **Completion gates / feedback loops:** "Run validator → fix errors → repeat … greatly improves output quality"; embed copyable checklists.
- **Examples** (input/output pairs) clarify desired style "more clearly than descriptions alone."
- **Lint-able anti-patterns:** Windows backslash paths, deeply-nested references, too many options without a default, time-sensitive info ("before August 2025…"), inconsistent terminology, magic numbers in bundled scripts.
- **Evaluation-driven development:** "Create evaluations BEFORE writing extensive documentation"; ≥3 eval scenarios; test across Haiku/Sonnet/Opus. Official "Checklist for effective Skills" = ready-made rubric.

(obra/superpowers writing-skills reproduces the same criteria — corroborating.)

## 2. Doc-as-tests / executable-examples tooling
| Tool | Collection | Skip fragments | Namespace | Output bar |
|---|---|---|---|---|
| **Sybil** | python fences + doctest; `<!-- invisible-code-block: python -->` setup | `<!-- skip: next -->`, `start/end`, conditional, labeled-with-reason | **shared by default**; `<!-- clear-namespace -->` | run-or-doctest, configurable |
| **pytest-examples** (pydantic) | `find_examples('README.md','pkg')` | pytest marks | per-block [INFERENCE] | `run()` exec-only; `run_print_check()` matches `#>`; `lint()` ruff+black; `--update-examples` rewrites |
| **mktestdocs** (koaning) | extracts ```python/```bash; `check_md_file` | only matching `lang` runs [INFERENCE]; no explicit skip directive | `memory=False` independent; `memory=True` shared | **run-without-error only**; `assert` = free unit tests |
| **Polars run_doctest.py** | docstring Examples | `# doctest: +IGNORE_RESULT` | doctest | runs + verifies; "config options too limited" → rolled own |
| **doctest** | `>>>` | `# doctest: +SKIP` | per-docstring | exact match |
| **Rust `cargo test --doc`** | ` ```rust ` | `ignore`/`no_run`/`compile_fail`/`text`; `#`-hidden setup lines | per-block | compile (+run) |

**Cross-tool insight:** two distinct skip needs — (1) *don't run* (pseudocode) vs (2) *run but don't check output*. Every mature tool separates them. **Invisible-setup blocks** (Sybil; Rust `#`-hidden) inject shared imports/fixtures without polluting reader-facing prose — directly applicable to multi-block tutorials.

## 3. Code-derived-artifact drift detection
**Ruff [VERIFIED]:** one command `cargo dev generate-all`; CI runs generators then `test -z "$(git status --porcelain)"` (fail on any diff). Canonical "single source → regenerate → fail on diff" pattern (equiv. `git diff --exit-code`).

**Griffe [VERIFIED]:** "compare two snapshots … to detect API breakages … a specific point in your Git history." `griffe check pkg --against 1.0` (any ref); `find_breaking_changes()` returns typed Breakages; static (no build) → CI-safe. **Pin a SHA in a config file** (docs repo uses `.docs-sync.yml`), run `griffe check pkg --against <sha>`, surface symbol-delta. **[INFERENCE]** Griffe is Python-static; our PyO3/Rust surface is visible only via `.pyi` stubs — which we maintain (`_internal.pyi`, `mypy.stubtest`-validated), so Griffe-on-stubs is viable.

## 4. Prose/style linting
**Vale [VERIFIED]:** editorial rules as deterministic YAML. `existence` (ban regex/tokens), `occurrence` (require N times), plus substitution/consistency/etc. `level: error` gates CI; `scope`/`tokens` localize. Real rule sets suppress false positives on camelCase/acronyms/CLI flags/file extensions — relevant for code-dense text. Maps 1:1 onto Anthropic's lint-able anti-patterns.

## 5. Single-source-of-truth for multi-target manifests
Strongest concrete pattern is **ruff's** (§3): one generator, N artifacts, CI re-runs + fails on diff. [INFERENCE] generalized: keep one canonical source (the `skills/` directory) and *generate* every manifest + the "N skills" count, then CI regenerate → `test -z "$(git status --porcelain)"`. (GitOps "reconcile-and-alert-on-drift" is the conceptual analog but infra-oriented; cite ruff for an implementable gate.)

## Implications (highest-leverage gates for SKILLS, given many blocks are fragments)
1. **Two-tier, fragment-aware example execution.** Default = **run-only** for ```python (mktestdocs/Polars `+IGNORE_RESULT` philosophy — prove it executes, don't pin actuarial numbers). **Skip marker** = HTML comment before the fence (Sybil form — invisible in render, most expressive) for fragments like `af.x = af.y * af.z`. **Invisible setup blocks** inject standard imports + a built `ActuarialFrame` once per file.
2. **Namespace shared-within-file, explicit reset** (`clear-namespace`) for Levels 1–5 tutorials. **Standardize on Sybil** (only tool with skip + conditional skip + clear-namespace + invisible setup + shared namespace); **mktestdocs** the lighter fallback (parity with docs repo).
3. **Structural lint of SKILL.md** encoding Anthropic's checklist: name regex / reserved words; description non-empty ≤1024 third-person with trigger; ≤500 lines; references exactly one level deep; refs >100 lines need TOC; Vale rules for anti-patterns at `level: error`.
4. **API-delta via Griffe against pinned SHA (`.skills-sync.yml`)** on `.pyi` stubs — gate to **warn** (list affected skills), not hard-fail; let run-only execution be the hard failure.
5. **Manifest single-source guard (ruff pattern)** — generate from `skills/`, CI regenerate → clean-tree assert. Pure determinism, no false positives.

**Sequencing (before any LLM repair):** hard-block on (a) structural lint, (b) run-only execution with skip-markers, (c) manifest staleness. Griffe delta runs as a warning-level advisory scoping what the downstream LLM repair must inspect.

### Sources
platform.claude.com agent-skills best-practices & overview · obra/superpowers writing-skills · sybil.readthedocs.io/en/latest/markdown.html · github.com/pydantic/pytest-examples · github.com/koaning/mktestdocs · docs.pola.rs/development/contributing/test · rustdoc documentation-tests · docs.astral.sh/ruff/contributing + ruff CI workflow · mkdocstrings.github.io/griffe/guide/users/checking · vale.sh/docs/styles
