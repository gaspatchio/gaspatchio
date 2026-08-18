# Workbook-conversion skill hardening — design

**Date:** 2026-08-18
**Scope:** PR #114 (`feat/95-workbook-conversion-skill`), pre-merge additions
**Decided with:** Matt, brainstorm session 2026-08-18

## Problem

PR #114 adds `gaspatchio-workbook-conversion` — the conversion *discipline* as the 8th
skill. The skill is a document full of factual claims: fastexcel truncates floats behind
a String-dtype inference, `round_charge=` exists on the rollforward ops, sibling skills
and reference files sit at named paths. Documents rot; none of those claims is currently
guarded, so the skill could drift from reality without any signal. Separately, the
xl-marinade guidance the skill routes to is stale (cites marinade #12 as an open caveat —
fixed in 0.3.0 — and names no version floor), and the plugin version string is unchanged
at 1.0.0, which means `/plugin update` would no-op and installed users would never
receive the new skill.

## Decision

Approach B — claims-as-tests. Rejected: A (merge as-is; leaves every claim unguarded)
and C (B plus new prescriptive skill content; bloats the PR — the review skill already
owns negative-control discipline and #122 is the designated home for guidance gaps).

**Principles served:** *Audit by default* (the skill's claims carry executable proof —
the document eats its own dog food) and *LLM-shaped from the inside out* (the skill is
retrieval surface; keeping it factually current is a correctness property, not hygiene).
Strains none.

## Components

### 1. `tests/skills/test_workbook_conversion_claims.py` (new)

Runs in the existing Skill Structure CI job (`uv run pytest ../../tests/skills/` from
`bindings/python`, full venv available — `fastexcel>=0.14.0` and `xlsxwriter>=3.2.9`
are already dependencies). Three tests, one per claim species:

1. **Truncation hazard is real** — build a workbook in-memory with xlsxwriter (text
   header row + floats carrying more significant digits than the ~9 the String path
   preserves, including the skill's own probe values), read it back with fastexcel two
   ways, assert the HARD GATE table:
   String-inferred read truncates the values, header-skipped Float64 read is lossless.
   *Deliberate direction:* the test asserts the hazard EXISTS. If a future fastexcel
   release fixes the truncation, this test fails — red CI meaning "update the skill's
   HARD GATE," which is exactly the wanted signal. The defense (reader-vs-XML
   validation) is converting-agent behaviour, not library code; the hazard's existence
   is the testable fact.
2. **Cross-references resolve** — parse the skill's SKILL.md for the sibling skills and
   in-repo files it names (`gaspatchio-model-discovery`,
   `references/spreadsheet-conversion.md`, …) and assert each exists on disk. Guards
   the likeliest real failure: a reference file gets renamed and the skill points at
   nothing.
3. **API pin** — the skill prose names `round_charge=` on rollforward ops and `.clip()`
   on the lookup key. Assert via `inspect.signature` / attribute checks that the named
   surface exists on the real API. Prose pinned to the shipped surface.

Red-verification: each test must demonstrably fail when its claim breaks (checked by
temporary mutation during development — e.g. point the link-rot scan at a bogus name —
then restored). Zero ruff/format delta vs baseline on all touched files.

### 2. xl-marinade guidance refresh

Canonical home per #114's own ownership table: the **discovery** skill's
`references/spreadsheet-conversion.md` (it already carries the install lines). Changes:

- Version floor: require `xl-marinade>=0.3.0` (released 2026-08-15) and say why —
  0.3.0 fixed #12 (formula_pattern), #13 (`marinade --version`), #15 (stale skill
  contract), #17 (`extract -o` on missing dir).
- Replace the stale #12 caveat with the two still-open ones, verified live 2026-08-18:
  **#14** (agent_cells contract: NULL data_type for numerics, JSON-string values,
  `formula=''` — the obvious SQL is silently wrong) and **#16** (intra-binding edges
  dropped — a within-column recurrence is structurally inexpressible in the binding
  graph; the #115 blind spot).
- `#114`'s SKILL.md gets only a two-line Tooling pointer (install one-liner + "the
  discovery reference owns the detail") — a full Tooling section would violate the
  skill's own "what this one deliberately does not repeat" table.

### 3. Plugin version bump

`skills.toml` `[plugin] version` 1.0.0 → **1.1.0** (new skill = minor), then
`uv run python scripts/gen_skill_manifests.py` and commit the regenerated manifests.
Rationale: `/plugin update` no-ops on an unchanged version string even when content
changed — observed twice (gaspatchio plugin and xl-marinade plugin). Without the bump,
installed users never receive the 8th skill.

### 4. Post-merge follow-up (docs repo, not this PR)

`gaspatchio-docs/docs/ai/skills.md` ("Seven Areas of Expertise", 7-row table) and
`docs/ai/setup.md` need a hand-written 8th row and seven→eight wording — skills are not
importables, so the docs delta engine will never flag this. Commit over HTTPS as usual;
the RAG rebuild fires automatically off the docs commit.

## Testing

- New module runs green in `tests/skills/` locally (from `bindings/python`) and each
  test proven red-capable by mutation during development.
- Existing skill-structure + manifest suites stay green (the manifest sync test must
  pass against the regenerated 1.1.0 artifacts).
- Gates: zero ruff/mypy/format delta vs per-file baselines; signed conventional
  commits; PR body updated with the revision and verification SHAs.

## Out of scope

#122's four conversion-guidance gaps and #115's SCC-rule honesty note (follow-up PR
against the merged skill); any new prescriptive content in the skill body; the docs-repo
edit (post-merge).
