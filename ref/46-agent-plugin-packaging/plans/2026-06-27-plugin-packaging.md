# Plugin Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every advertised AI-plugin install path (Claude Code, Cursor, GitHub Copilot, `npx skills`) actually work, self-hosted, generated from the `skills.toml` SSOT and CI-guarded against drift.

**Architecture:** `skills/skills.toml` gains a `[plugin]` table (metadata + semver) and branded `order` entries. `scripts/gen_skill_manifests.py` is rewritten to *generate* every wrapper/registration file from that SSOT (Claude `plugin.json` + `marketplace.json`, Cursor `plugin.json`, Copilot `.github/plugin/marketplace.json`, `.github/copilot-instructions.md`) rather than patch them in place. CI `gen_skill_manifests.py --check` plus widened guards fail on any drift. Skill dirs are renamed `gaspatchio-*` so `name == dir`. One canonical `skills/` tree; manifests point at it (no copies).

**Tech Stack:** Python 3.12 (`tomllib`, `json`, `argparse`, `pathlib`), pytest, JSON/Markdown manifests, GitHub Actions (`CI.yml`).

**Spec:** [`../specs/2026-06-27-plugin-packaging-design.md`](../specs/2026-06-27-plugin-packaging-design.md)

> **Post-cutoff caveat (read first):** The exact manifest schemas (Claude `marketplace.json`, Cursor `plugin.json`, Copilot `.github/plugin/marketplace.json`) are mid-2026 facts the research is past the knowledge cutoff for. **Task 0 confirms them against live docs before any generation.** Where a later task hardcodes a schema, it is the best-known shape from the field scan — the implementer adjusts keys per Task 0's findings if they differ. Do NOT skip Task 0.

---

## File Structure

- **Modify** `skills/skills.toml` — add `[plugin]` table; rename `order` entries to `gaspatchio-*`.
- **Rename** `skills/<name>/` → `skills/gaspatchio-<name>/` (×7).
- **Rewrite** `scripts/gen_skill_manifests.py` — generate all artifacts from the SSOT.
- **Modify/replace** `.claude-plugin/plugin.json` (generated), **create** `.claude-plugin/marketplace.json`.
- **Modify** `.cursor-plugin/plugin.json` (generated, drop `../skills`).
- **Move** `.github/plugin.json` → **create** `.github/plugin/marketplace.json` (per Task 0).
- **Create** `.github/copilot-instructions.md` (generated from AGENTS.md).
- **Modify** `bindings/python/AGENTS.md` — install section (npx slug, per-tool steps, branded list).
- **Modify** `tests/skills/test_skill_manifests.py`, `tests/skills/test_skill_structure.py` — branded dirs, new guards.
- **Create** `ref/46-agent-plugin-packaging/gates-findings.md` — Task 0 output.
- **Modify** `.github/workflows/CI.yml` — run the widened `--check` + validators.

---

## Task 0: Verification gates (confirm schemas before generating)

**Files:**
- Create: `ref/46-agent-plugin-packaging/gates-findings.md`

This task is verification, not code. Each gate is a question to answer against **live** docs/tools (use WebFetch on official docs + `gh api` on real repos cited in the field scan). Record the confirmed schema/answer in `gates-findings.md`. Subsequent tasks read it.

- [ ] **Step 1 — Claude marketplace.json schema (Gate 1).** Fetch the current Claude Code plugin-marketplace docs (code.claude.com/docs) and `gh api repos/anthropics/claude-plugins-official/contents/.claude-plugin/marketplace.json`. Record the required key set and that a same-repo `source: "./"` entry is valid.
- [ ] **Step 2 — In-place discovery / copies decision (Gate 2).** Confirm whether Cursor and Copilot **open-repo** discovery follow a per-tool manifest pointer (`skills: "./skills/"`) or require skills physically under `.agents/skills/`. Inspect `obra/superpowers` (`.cursor-plugin/plugin.json`) and `flutter/devtools` (`.agents/skills/`). **Record the verdict: copies needed (yes/no).** Default no.
- [ ] **Step 3 — Cursor + Copilot manifest schemas (Gate 3).** Confirm `.cursor-plugin/plugin.json` keys (cursor.com/docs) and the Copilot `.github/plugin/marketplace.json` shape (`gh api repos/Azure/agentops/contents/.github/plugin/marketplace.json`); note whether a sibling `.github/plugin/plugin.json` is also required.
- [ ] **Step 4 — Validators (Gate 4).** Confirm whether `claude plugin validate --strict` and `skills-ref validate` exist/are installable in CI. Record fallbacks if not.
- [ ] **Step 5 — Write findings.** Write `gates-findings.md` with one section per gate: the confirmed schema (JSON skeleton), the copies verdict, validator availability. Commit:
```bash
git -C ~/projects/gaspatchio/gaspatchio-core add ref/46-agent-plugin-packaging/gates-findings.md
git -C ~/projects/gaspatchio/gaspatchio-core commit -m "docs(ref): plugin-packaging verification-gate findings"
```

---

## Task 1: `skills.toml` `[plugin]` table + loader

**Files:**
- Modify: `skills/skills.toml`
- Modify: `scripts/gen_skill_manifests.py`
- Test: `tests/skills/test_skill_manifests.py`

- [ ] **Step 1 — Write the failing test.** Append to `tests/skills/test_skill_manifests.py`:
```python
def test_plugin_meta_loads() -> None:
    """The [plugin] table exposes the canonical plugin metadata."""
    gen = _load_generator()
    meta = gen.load_plugin()
    assert meta["name"] == "gaspatchio"
    assert meta["license"] == "Apache-2.0"
    assert meta["version"]  # semver string present
    assert meta["repository"].endswith("opioinc/gaspatchio-core")
```

- [ ] **Step 2 — Run, expect fail.** `cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest ../../tests/skills/test_skill_manifests.py::test_plugin_meta_loads -q` → FAIL (`AttributeError: load_plugin`).

- [ ] **Step 3 — Add the `[plugin]` table** to `skills/skills.toml` (above `order`):
```toml
[plugin]
name         = "gaspatchio"
display_name = "Gaspatchio"
description  = "Actuarial modeling skills for gaspatchio (Python + Rust/Polars)."
version      = "1.0.0"
author_name  = "Opio Inc."
author_url   = "https://github.com/opioinc"
homepage     = "https://github.com/opioinc/gaspatchio-core"
repository   = "https://github.com/opioinc/gaspatchio-core"
license      = "Apache-2.0"
keywords     = ["actuarial", "polars", "insurance", "ifrs17", "solvency-ii", "rust"]
```
(Leave `order` unchanged in this task — the rename is Task 2.)

- [ ] **Step 4 — Add the loader** to `scripts/gen_skill_manifests.py` (after `load_order`):
```python
def load_plugin() -> dict:
    """Return the [plugin] metadata table from the canonical registry."""
    with REGISTRY.open("rb") as fh:
        return dict(tomllib.load(fh)["plugin"])
```

- [ ] **Step 5 — Run, expect pass.** Same command → PASS.

- [ ] **Step 6 — Commit.**
```bash
git -C ~/projects/gaspatchio/gaspatchio-core add skills/skills.toml scripts/gen_skill_manifests.py tests/skills/test_skill_manifests.py
git -C ~/projects/gaspatchio/gaspatchio-core commit -m "feat(skills): add [plugin] metadata table to the skills.toml SSOT"
```

---

## Task 2: Rename skill dirs `→ gaspatchio-*` (name == dir)

**Files:**
- Rename: `skills/<name>/` → `skills/gaspatchio-<name>/` (×7)
- Modify: `skills/skills.toml` (`order`), `bindings/python/AGENTS.md` (What You Get list), `tests/skills/test_skill_structure.py` (hardcoded dir refs + new guard)

- [ ] **Step 1 — Write the `name == dir` guard (failing).** Add to `tests/skills/test_skill_structure.py`:
```python
@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_frontmatter_name_matches_dir(skill_name: str) -> None:
    """Open Agent Skills spec: frontmatter name must equal the parent directory."""
    assert _frontmatter(skill_name)["name"] == skill_name
```

- [ ] **Step 2 — Run, expect fail.** `cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest ../../tests/skills/test_skill_structure.py -k name_matches_dir -q` → FAIL (dir `quickstart` ≠ name `gaspatchio-quickstart`).

- [ ] **Step 3 — Rename the 7 dirs** (git mv preserves history):
```bash
cd ~/projects/gaspatchio/gaspatchio-core
for n in quickstart model-discovery model-building model-reconciliation model-review model-scenarios extending-gaspatchio; do
  git mv "skills/$n" "skills/gaspatchio-$n"
done
```
Note: `extending-gaspatchio` → `gaspatchio-extending-gaspatchio`? **No** — its frontmatter name is `gaspatchio-extending` (verified). Rename that one to match its name: `git mv skills/extending-gaspatchio skills/gaspatchio-extending`. Do the other six as `gaspatchio-<name>`. Confirm each new dir name equals its SKILL.md frontmatter `name` (`grep -m1 '^name:' skills/*/SKILL.md`).

- [ ] **Step 4 — Update `skills.toml order`** to the branded dir names:
```toml
order = [
  "gaspatchio-quickstart",
  "gaspatchio-model-discovery",
  "gaspatchio-model-building",
  "gaspatchio-model-reconciliation",
  "gaspatchio-model-review",
  "gaspatchio-model-scenarios",
  "gaspatchio-extending",
]
```

- [ ] **Step 5 — Update the hardcoded dir refs** in `tests/skills/test_skill_structure.py`. These reference old dir names and will `FileNotFoundError` after the rename: `test_model_building_has_references` (`"model-building"` → `"gaspatchio-model-building"`), `test_model_reconciliation_has_techniques` (`"gaspatchio-model-reconciliation"`), `test_model_review_has_references` (`"gaspatchio-model-review"`), `test_extending_has_references` (`"gaspatchio-extending"`), and the routing-DAG tests (`test_building_routes_to_*`, `test_discovery_routes_to_building`, `test_quickstart_routes_to_discovery`, `test_review_routes_to_extending`, `test_discovery_mentions_excel_porting`) which read `SKILLS_DIR / "<old>" / "SKILL.md"` — update each path to `gaspatchio-<old>`. Leave the `"... in content" in content` substring assertions (they match conceptual prose) unchanged.

- [ ] **Step 6 — Update the AGENTS.md "What You Get" list** in `bindings/python/AGENTS.md` to the branded names so `test_agents_md_count_and_list_in_sync` passes:
```
- **7 skills**: gaspatchio-quickstart, gaspatchio-model-discovery, gaspatchio-model-building, gaspatchio-model-reconciliation, gaspatchio-model-review, gaspatchio-model-scenarios, gaspatchio-extending
```

- [ ] **Step 7 — Run the full skills suite, expect green.** `cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest ../../tests/skills/ -q` → all pass (incl. the new `name == dir` guard, `test_registry_matches_directories`, `test_expected_skills_cover_all_directories`).

- [ ] **Step 8 — Commit.**
```bash
git -C ~/projects/gaspatchio/gaspatchio-core add -A skills/ tests/skills/test_skill_structure.py skills/skills.toml bindings/python/AGENTS.md
git -C ~/projects/gaspatchio/gaspatchio-core commit -m "refactor(skills): rename dirs to gaspatchio-* so name == dir (open-spec compliance)"
```

> Note: the Cursor/Copilot manifests still carry the OLD `../skills/<name>` paths and will be regenerated in Task 4; `test_cursor_manifest_in_sync` / `test_github_manifest_in_sync` may go red here — that is expected and closed by Task 4. If you want green between tasks, run `uv run python scripts/gen_skill_manifests.py` after Task 4's generator rewrite, not here.

---

## Task 3: Generate the Claude manifest + marketplace.json

**Files:**
- Rewrite: `scripts/gen_skill_manifests.py` (generation, not patching)
- Generated: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- Test: `tests/skills/test_skill_manifests.py`

- [ ] **Step 1 — Write failing tests** for the Claude artifacts. Add to `tests/skills/test_skill_manifests.py`:
```python
def test_claude_plugin_generated_from_meta() -> None:
    gen = _load_generator()
    data = json.loads(gen.render_claude_plugin())
    meta = gen.load_plugin()
    assert data["name"] == meta["name"]
    assert data["license"] == "Apache-2.0"
    assert data["skills"] == "./skills/"          # glob, self-maintaining
    assert data["author"]["name"] == "Opio Inc."  # canonical, not "Gaspatchio"

def test_marketplace_self_hosts_same_repo() -> None:
    gen = _load_generator()
    mkt = json.loads(gen.render_marketplace())
    assert mkt["name"] == "gaspatchio"
    entry = mkt["plugins"][0]
    assert entry["source"] == "./"
    assert entry["name"] == "gaspatchio"
    assert entry["version"] == gen.load_plugin()["version"]
```

- [ ] **Step 2 — Run, expect fail** (`render_claude_plugin` / `render_marketplace` undefined).

- [ ] **Step 3 — Rewrite `scripts/gen_skill_manifests.py`** to a generate-everything structure. Keep `load_order`/`load_plugin`. Replace the in-place `render`/`main` with per-artifact renderers and a write/check driver. Add (using the Task-0-confirmed Claude `marketplace.json` schema — the body below is the best-known shape):
```python
def _dumps(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

def render_claude_plugin() -> str:
    """The Claude Code plugin manifest (globs ./skills/; self-maintaining)."""
    m = load_plugin()
    return _dumps({
        "name": m["name"],
        "version": m["version"],
        "description": m["description"],
        "author": {"name": m["author_name"], "url": m["author_url"]},
        "homepage": m["homepage"],
        "repository": m["repository"],
        "license": m["license"],
        "keywords": m["keywords"],
        "skills": "./skills/",
    })

def render_marketplace() -> str:
    """Self-hosted marketplace listing this repo as a single plugin (source ./)."""
    m = load_plugin()
    return _dumps({
        "name": m["name"],
        "owner": {"name": m["author_name"], "url": m["author_url"]},
        "plugins": [{
            "name": m["name"],
            "source": "./",
            "description": m["description"],
            "version": m["version"],
        }],
    })

# Map of generated-file path -> renderer. Extended in Tasks 4-5.
ARTIFACTS = {
    REPO_ROOT / ".claude-plugin" / "plugin.json": render_claude_plugin,
    REPO_ROOT / ".claude-plugin" / "marketplace.json": render_marketplace,
}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any generated file is out of date")
    args = parser.parse_args()
    drift: list[Path] = []
    for path, renderer in ARTIFACTS.items():
        expected = renderer()
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != expected:
                drift.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
    if args.check and drift:
        names = ", ".join(str(p.relative_to(REPO_ROOT)) for p in drift)
        print(f"Out-of-date generated file(s): {names}\n"
              f"Run: uv run python scripts/gen_skill_manifests.py", file=sys.stderr)
        return 1
    return 0
```
Remove the now-dead `render(manifest_path, order)` and `LIST_MANIFESTS`. Update `test_render_swaps_skills_and_preserves_other_keys` (it tested the old `render`) — delete it; the new renderers are covered by the tests above.

- [ ] **Step 4 — Run, expect pass.** `cd .../bindings/python && uv run pytest ../../tests/skills/test_skill_manifests.py -k "claude_plugin_generated or marketplace_self_hosts" -q` → PASS.

- [ ] **Step 5 — Generate + commit.**
```bash
cd ~/projects/gaspatchio/gaspatchio-core && uv run python scripts/gen_skill_manifests.py
git -C . add scripts/gen_skill_manifests.py tests/skills/test_skill_manifests.py .claude-plugin/plugin.json .claude-plugin/marketplace.json
git -C . commit -m "feat(plugin): generate Claude plugin.json + self-hosted marketplace.json from SSOT"
```

---

## Task 4: Generate the Cursor + Copilot manifests

**Files:**
- Modify: `scripts/gen_skill_manifests.py` (add renderers to `ARTIFACTS`)
- Generated: `.cursor-plugin/plugin.json`; **move** `.github/plugin.json` → `.github/plugin/marketplace.json`
- Test: `tests/skills/test_skill_manifests.py`

> Use the Task-0 (Gate 3) confirmed schemas. The shapes below are the best-known forms — adjust keys to match Gate 3.

- [ ] **Step 1 — Write failing tests:**
```python
def test_cursor_manifest_points_at_one_tree() -> None:
    gen = _load_generator()
    data = json.loads(gen.render_cursor_plugin())
    assert data["name"] == "gaspatchio"
    assert "skills" in data
    assert not any(str(s).startswith("../") for s in (data["skills"] if isinstance(data["skills"], list) else []))

def test_copilot_marketplace_generated() -> None:
    gen = _load_generator()
    mkt = json.loads(gen.render_copilot_marketplace())
    assert mkt["plugins"][0]["source"] == "./"
```

- [ ] **Step 2 — Run, expect fail.**

- [ ] **Step 3 — Add renderers** to `gen_skill_manifests.py` and register them in `ARTIFACTS`:
```python
def render_cursor_plugin() -> str:
    """Thin Cursor manifest pointing at the one canonical ./skills tree."""
    m = load_plugin()
    return _dumps({
        "name": m["name"],
        "version": m["version"],
        "description": m["description"],
        "author": {"name": m["author_name"], "url": m["author_url"]},
        "license": m["license"],
        "skills": "./skills/",   # per Gate 3: dir-glob pointer, no ../ traversal
    })

def render_copilot_marketplace() -> str:
    """Copilot agent-plugin marketplace (.github/plugin/marketplace.json)."""
    return render_marketplace()  # same self-hosted shape unless Gate 3 differs

ARTIFACTS[REPO_ROOT / ".cursor-plugin" / "plugin.json"] = render_cursor_plugin
ARTIFACTS[REPO_ROOT / ".github" / "plugin" / "marketplace.json"] = render_copilot_marketplace
```
Then remove the stale file: `git rm .github/plugin.json`. Update `test_cursor_manifest_in_sync`/`test_github_manifest_in_sync` (they asserted the old `../skills/...` array) — replace with the two new tests above; delete the obsolete `expected_skill_paths()` helper if unused.

- [ ] **Step 4 — Run, expect pass.**

- [ ] **Step 5 — Generate + commit.**
```bash
cd ~/projects/gaspatchio/gaspatchio-core && uv run python scripts/gen_skill_manifests.py
git -C . rm .github/plugin.json
git -C . add scripts/gen_skill_manifests.py tests/skills/test_skill_manifests.py .cursor-plugin/plugin.json .github/plugin/marketplace.json
git -C . commit -m "feat(plugin): generate Cursor + Copilot manifests pointing at one skills tree"
```

> **Gate 2 branch:** if Task 0 found in-place discovery needs physical `.agents/skills/`, add a renderer that materializes `.agents/skills/<name>/` as **copies** (Windows-safe) of `skills/<name>/`, register it in `ARTIFACTS`, and add a `--check` over the copied tree. Otherwise skip — no copies.

---

## Task 5: Generate `.github/copilot-instructions.md` from AGENTS.md

**Files:**
- Modify: `scripts/gen_skill_manifests.py`
- Generated: `.github/copilot-instructions.md`
- Test: `tests/skills/test_skill_manifests.py`

- [ ] **Step 1 — Write the failing test:**
```python
def test_copilot_instructions_generated() -> None:
    gen = _load_generator()
    out = gen.render_copilot_instructions()
    assert "Skill Routing" in out          # the routing table is carried over
    assert "gaspatchio" in out
```

- [ ] **Step 2 — Run, expect fail.**

- [ ] **Step 3 — Add the renderer** (derive from the repo-root `AGENTS.md` framework knowledge; a generated copy is acceptable — generator-owned, `--check`-guarded):
```python
AGENTS_MD = REPO_ROOT / "AGENTS.md"

def render_copilot_instructions() -> str:
    """Copilot always-loaded instructions, derived from the root AGENTS.md."""
    body = AGENTS_MD.read_text(encoding="utf-8")
    header = ("<!-- GENERATED from AGENTS.md by scripts/gen_skill_manifests.py. "
              "Do not edit. -->\n\n")
    return header + body

ARTIFACTS[REPO_ROOT / ".github" / "copilot-instructions.md"] = render_copilot_instructions
```

- [ ] **Step 4 — Run, expect pass** (ensure the root `AGENTS.md` contains "Skill Routing"; it does).

- [ ] **Step 5 — Generate + commit.**
```bash
cd ~/projects/gaspatchio/gaspatchio-core && uv run python scripts/gen_skill_manifests.py
git -C . add scripts/gen_skill_manifests.py tests/skills/test_skill_manifests.py .github/copilot-instructions.md
git -C . commit -m "feat(plugin): generate .github/copilot-instructions.md from AGENTS.md"
```

---

## Task 6: Widen the drift guard + add consistency guards

**Files:**
- Test: `tests/skills/test_skill_manifests.py`

- [ ] **Step 1 — Write failing guards:**
```python
def test_all_generated_artifacts_in_sync() -> None:
    """Every generated file on disk matches the generator output (no drift)."""
    gen = _load_generator()
    for path, renderer in gen.ARTIFACTS.items():
        assert path.read_text(encoding="utf-8") == renderer(), f"drift: {path}"

def test_license_consistent_across_manifests() -> None:
    gen = _load_generator()
    for path in (REPO_ROOT / ".claude-plugin" / "plugin.json",
                 REPO_ROOT / ".cursor-plugin" / "plugin.json"):
        assert json.loads(path.read_text())["license"] == "Apache-2.0"

def test_agents_md_npx_slug_is_correct() -> None:
    text = (REPO_ROOT / "bindings" / "python" / "AGENTS.md").read_text(encoding="utf-8")
    assert "npx skills add opioinc/gaspatchio-core" in text
    assert "npx skills add gaspatchio/gaspatchio-core" not in text
```
(`test_agents_md_npx_slug_is_correct` fails until Task 7; that is expected — Task 7 closes it.)

- [ ] **Step 2 — Run** the two manifest guards (`-k "all_generated_artifacts or license_consistent"`) → PASS now; npx guard fails (closed in Task 7).

- [ ] **Step 3 — Add the validators to CI** in `.github/workflows/CI.yml`: a step running `uv run python scripts/gen_skill_manifests.py --check`, and — only if Task 0/Gate 4 confirmed they exist — `claude plugin validate --strict` and `skills-ref validate ./skills/<name>`. If unavailable, rely on the pytest guards above.

- [ ] **Step 4 — Commit.**
```bash
git -C ~/projects/gaspatchio/gaspatchio-core add tests/skills/test_skill_manifests.py .github/workflows/CI.yml
git -C ~/projects/gaspatchio/gaspatchio-core commit -m "test(plugin): guard all generated artifacts + license/npx consistency in CI"
```

---

## Task 7: Fix the AGENTS.md install section

**Files:**
- Modify: `bindings/python/AGENTS.md`

- [ ] **Step 1 — Fix the npx slug** (line ~336): `npx skills add gaspatchio/gaspatchio-core` → `npx skills add opioinc/gaspatchio-core`, and add the Windows note: `# Windows: append --copy (symlinks need Developer Mode)`.
- [ ] **Step 2 — Refresh the per-tool steps** to match the generated artifacts (Cursor open-repo/import; Copilot `chat.plugins.marketplaces`; Claude `/plugin marketplace add` then `/plugin install gaspatchio@gaspatchio`).
- [ ] **Step 3 — Run the npx guard, expect pass.** `cd .../bindings/python && uv run pytest ../../tests/skills/test_skill_manifests.py -k npx_slug -q` → PASS.
- [ ] **Step 4 — Commit.**
```bash
git -C ~/projects/gaspatchio/gaspatchio-core add bindings/python/AGENTS.md
git -C ~/projects/gaspatchio/gaspatchio-core commit -m "docs(agents): fix npx slug to opioinc + Windows --copy note + per-tool install steps"
```

---

## Task 8: Full-suite check + end-to-end install verification

**Files:** none (verification + branch finish)

- [ ] **Step 1 — Full skills suite green.** `cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest ../../tests/skills/ -q` → all pass.
- [ ] **Step 2 — Generator is idempotent.** `cd ~/projects/gaspatchio/gaspatchio-core && uv run python scripts/gen_skill_manifests.py && git -C . diff --exit-code` → no diff (running it produces no change).
- [ ] **Step 3 — `--check` clean.** `uv run python scripts/gen_skill_manifests.py --check` → exit 0.
- [ ] **Step 4 — Manual install smoke (record results):** Claude `/plugin marketplace add opioinc/gaspatchio-core` + `/plugin install`; `npx skills add opioinc/gaspatchio-core --copy` on a Windows (or `--copy`) check; open the repo in Cursor and confirm skills load; Copilot `chat.plugins.marketplaces` add. Note any gate-schema corrections discovered and feed them back into the generator.
- [ ] **Step 5 — Finish the branch** via superpowers:finishing-a-development-branch (PR to develop, since this is substantive cross-cutting change — not trunk-direct).

---

## Self-Review

**Spec coverage:** Goal/non-goals → Task 0 (gates) bounds scope; decisions 1–7 map to Tasks 1 (SSOT meta + semver), 2 (rename/name==dir), 3 (Claude + marketplace), 4 (Cursor/Copilot, one-tree pointers), 5 (copilot-instructions), 6–7 (guards + hygiene: license/npx). Versioning → `[plugin].version` flows into every manifest (Tasks 1/3/4). "Generate everything" → the `ARTIFACTS` map is the single writer; `--check` over it (Task 6). No `.agents/skills/` copies unless Gate 2 flips (Task 4 branch).

**Placeholder scan:** No TODOs. The manifest JSON bodies are the best-known shapes explicitly gated on Task 0 — the one honest soft spot, quarantined by design, not omission.

**Type/contract consistency:** `load_plugin()` returns the `[plugin]` dict; every renderer reads the same keys (`name`, `version`, `author_name`, `author_url`, `homepage`, `repository`, `license`, `keywords`, `description`). `ARTIFACTS` (path→renderer) is defined in Task 3 and extended in 4–5; the Task 6 drift guard iterates `gen.ARTIFACTS`. The renamed dir set (Task 2) is the same list used by `order`, the structure tests, and the AGENTS.md list.

**Known cross-task red windows (intentional):** Task 2 leaves the Cursor/Copilot manifests stale until Task 4; the npx guard (Task 6) stays red until Task 7. Both are called out at the source.

---

## Execution Handoff

Two options:
1. **Subagent-Driven (recommended)** — fresh subagent per task + two-stage (spec then quality) review. **REQUIRED SUB-SKILL:** superpowers:subagent-driven-development. Task 0 (verification gates) should run first and its `gates-findings.md` handed to the Task 3/4 implementers as context.
2. **Inline Execution** — **REQUIRED SUB-SKILL:** superpowers:executing-plans.

Because the manifest schemas are post-cutoff, **Task 0 is a hard prerequisite** for Tasks 3–5 regardless of execution mode.
