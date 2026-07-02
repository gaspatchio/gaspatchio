# Core Skill Source-of-Truth + Structural Gates (L0 + L1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the gaspatchio skill set drift-proof in the public core repo — one canonical registry generates the distribution manifests, a CI guard fails on any mismatch, and the structural rubric is enforced and self-maintaining.

**Architecture:** Introduce `skills/skills.toml` as the single ordered source of truth. A generator (`scripts/gen_skill_manifests.py`) writes the Cursor/Copilot manifests' `skills` arrays from it; a `--check` mode + pytest guard fail CI when manifests, the `AGENTS.md` count/list, or the structural-test `EXPECTED_SKILLS` drift from it. Extend `tests/skills/test_skill_structure.py` with the safe subset of Anthropic's authoring rubric. Pure-Python, no secrets, never shipped in the wheel (lives at repo root, outside `bindings/python/`). This is the public half of the split system in `ref/43-skill-lifecycle/specs/2026-06-15-skill-lifecycle-design.md` (L0 + L1).

**Tech Stack:** Python 3.12 (stdlib `tomllib`, `json`, `re`, `pathlib`), pytest, PyYAML (already a dev dep), GitHub Actions. Tests run from `bindings/python/` against `../../tests/skills/` (mirrors the existing `skill-structure-tests` CI job).

**Out of scope (separate plans):** the shared md-sync engine, example-execution, Griffe API-delta, effectiveness evals, and LLM fix/draft authoring (L2/L3/L4) — those live in private `gaspatchio-docs`. Deferred core items, noted in Task 7: adding TOCs to the ~14 reference files >100 lines, and normalising the `extending-gaspatchio` name/dir exception.

**Conventions for every task:**
- Run tests from `bindings/python/`: `cd bindings/python` then the `uv run pytest …` command shown.
- Repo root is `Path(__file__).resolve().parents[2]` from a file in `tests/skills/`, and `Path(__file__).resolve().parent.parent` from a file in `scripts/`.
- Commit messages: conventional, signed, **no** AI/Co-Authored-By trailer (repo rule).
- **Lint discipline:** match the existing `tests/skills/*.py` conventions — give every new module, function, and test a compliant docstring (a summary line; a blank line before any further description per D205; the closing `"""` on its own line for multi-line docstrings per D209), and `import` only what is used *in that task* (the editor on-save hook strips unused imports, so don't park an import for a later task). **CI does not run ruff** (only `reuse` license lint), and `assert` in tests is expected — so do **not** modify `pyproject.toml`/ruff config to chase a clean `ruff check`. Optionally run `uv run ruff format` on changed files. (Observation, out of scope: the `tests/**/*.py` per-file-ignore in `bindings/python/pyproject.toml` does not match the repo-root `tests/` tree, so `S101` etc. are not actually suppressed there when ruff is run manually — a latent config gap to address separately, not in this plan.)

---

### Task 1: Canonical skill registry + registry↔directory guard

**Files:**
- Create: `skills/skills.toml`
- Create: `tests/skills/test_skill_manifests.py`

- [ ] **Step 1: Write the failing test**

Create `tests/skills/test_skill_manifests.py`:

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Guard: the skill set is defined once in skills/skills.toml and every derived
artifact (distribution manifests, AGENTS.md count/list) stays in sync with it."""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
REGISTRY = SKILLS_DIR / "skills.toml"


def registry_order() -> list[str]:
    with REGISTRY.open("rb") as fh:
        return list(tomllib.load(fh)["order"])


def skill_dirs() -> set[str]:
    return {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}


def test_registry_matches_directories() -> None:
    """Every skill directory is registered, and every registered skill exists."""
    assert set(registry_order()) == skill_dirs()


def test_registry_has_no_duplicates() -> None:
    order = registry_order()
    assert len(order) == len(set(order)), f"duplicate entries in {REGISTRY}"
```

- [ ] **Step 2: Run test to verify it fails**

Run from `bindings/python/`: `uv run pytest ../../tests/skills/test_skill_manifests.py -v`
Expected: FAIL — `FileNotFoundError` for `skills/skills.toml` (registry does not exist yet).

- [ ] **Step 3: Create the registry**

Create `skills/skills.toml`:

```toml
# Canonical, ordered registry of gaspatchio agent skills.
#
# THIS IS THE SINGLE SOURCE OF TRUTH for the skill set and its routing order.
# The Cursor/Copilot plugin manifests, the bindings/python/AGENTS.md install
# count+list, and the structural-test EXPECTED_SKILLS are all generated from or
# checked against this list.
#
# To add a skill:
#   1. create skills/<dir>/SKILL.md
#   2. add "<dir>" to `order` below, in its routing position
#   3. run: uv run python scripts/gen_skill_manifests.py
#   4. commit the regenerated manifests
#
# The Claude Code manifest (.claude-plugin/plugin.json) globs ./skills/ and is
# intentionally not listed here.
order = [
    "quickstart",
    "model-discovery",
    "model-building",
    "model-reconciliation",
    "model-review",
    "model-scenarios",
    "extending-gaspatchio",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run from `bindings/python/`: `uv run pytest ../../tests/skills/test_skill_manifests.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add skills/skills.toml tests/skills/test_skill_manifests.py
git commit -m "feat(skills): add canonical skills.toml registry + directory guard"
```

---

### Task 2: Manifest generator with `--check` mode

**Files:**
- Create: `scripts/gen_skill_manifests.py`
- Modify: `tests/skills/test_skill_manifests.py` (add a `render()` unit test)

- [ ] **Step 1: Write the failing test**

Add `import json` and `import importlib.util` to the file's imports (both first used here), then append the test below to `tests/skills/test_skill_manifests.py` (give each new function a one-line docstring):

```python
def _load_generator():
    path = REPO_ROOT / "scripts" / "gen_skill_manifests.py"
    spec = importlib.util.spec_from_file_location("gen_skill_manifests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_swaps_skills_and_preserves_other_keys(tmp_path) -> None:
    gen = _load_generator()
    manifest = tmp_path / "plugin.json"
    # An em dash in the description must survive (ensure_ascii=False).
    manifest.write_text(
        '{\n  "name": "x",\n  "description": "tool — desc",\n'
        '  "skills": ["../skills/old"]\n}\n'
    )
    out = gen.render(manifest, ["quickstart", "model-building"])
    data = json.loads(out)
    assert data["skills"] == ["../skills/quickstart", "../skills/model-building"]
    assert data["name"] == "x"
    assert "—" in out  # em dash preserved literally, not escaped
    assert out.endswith("}\n")  # trailing newline
```

- [ ] **Step 2: Run test to verify it fails**

Run from `bindings/python/`: `uv run pytest ../../tests/skills/test_skill_manifests.py::test_render_swaps_skills_and_preserves_other_keys -v`
Expected: FAIL — `FileNotFoundError`/import error (`scripts/gen_skill_manifests.py` does not exist).

- [ ] **Step 3: Write the generator**

Create `scripts/gen_skill_manifests.py`:

```python
#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Generate skill distribution manifests from the canonical registry.

`skills/skills.toml` is the single source of truth for the skill set and order.
This regenerates the `skills` array in the Cursor and Copilot plugin manifests.

    uv run python scripts/gen_skill_manifests.py           # write
    uv run python scripts/gen_skill_manifests.py --check    # verify (exit 1 on drift)

The Claude Code manifest (.claude-plugin/plugin.json) globs ./skills/ and is not
generated. The bindings/python/AGENTS.md install count/list is verified by
tests/skills/test_skill_manifests.py, not rewritten here.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "skills" / "skills.toml"
LIST_MANIFESTS = (
    REPO_ROOT / ".cursor-plugin" / "plugin.json",
    REPO_ROOT / ".github" / "plugin.json",
)


def load_order() -> list[str]:
    with REGISTRY.open("rb") as fh:
        return list(tomllib.load(fh)["order"])


def render(manifest_path: Path, order: list[str]) -> str:
    """Return the manifest JSON with its `skills` array set from `order`.

    Preserves all other keys and their order. `ensure_ascii=False` keeps the
    em dash in the description literal rather than escaping it.
    """
    data = json.loads(manifest_path.read_text())
    data["skills"] = [f"../skills/{name}" for name in order]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any manifest is out of date instead of writing",
    )
    args = parser.parse_args()
    order = load_order()

    drift: list[Path] = []
    for manifest in LIST_MANIFESTS:
        expected = render(manifest, order)
        if args.check:
            if manifest.read_text() != expected:
                drift.append(manifest)
        else:
            manifest.write_text(expected)

    if args.check and drift:
        names = ", ".join(str(p.relative_to(REPO_ROOT)) for p in drift)
        print(
            f"Out-of-date manifest(s): {names}\n"
            f"Run: uv run python scripts/gen_skill_manifests.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run from `bindings/python/`: `uv run pytest ../../tests/skills/test_skill_manifests.py::test_render_swaps_skills_and_preserves_other_keys -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/gen_skill_manifests.py tests/skills/test_skill_manifests.py
git commit -m "feat(skills): add manifest generator (skills.toml -> plugin manifests)"
```

---

### Task 3: Regenerate manifests + add in-sync guards

**Files:**
- Modify: `.cursor-plugin/plugin.json` (regenerated)
- Modify: `.github/plugin.json` (regenerated — `keywords` reformats to multi-line)
- Modify: `tests/skills/test_skill_manifests.py` (add in-sync + AGENTS.md guards)

- [ ] **Step 1: Write the failing tests**

Append to `tests/skills/test_skill_manifests.py` (`json` is already imported from Task 2; every function below needs a one-line docstring per the lint-discipline convention):

```python
def expected_skill_paths() -> list[str]:
    return [f"../skills/{name}" for name in registry_order()]


def test_cursor_manifest_in_sync() -> None:
    data = json.loads((REPO_ROOT / ".cursor-plugin" / "plugin.json").read_text())
    assert data["skills"] == expected_skill_paths()


def test_github_manifest_in_sync() -> None:
    data = json.loads((REPO_ROOT / ".github" / "plugin.json").read_text())
    assert data["skills"] == expected_skill_paths()


def test_claude_manifest_uses_glob() -> None:
    """The Claude Code manifest globs the directory; it must not list skills."""
    data = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert data["skills"] == "./skills/"


def test_agents_md_count_and_list_in_sync() -> None:
    order = registry_order()
    text = (REPO_ROOT / "bindings" / "python" / "AGENTS.md").read_text()
    assert f"get {len(order)} actuarial modeling skills" in text
    assert f"- **{len(order)} skills**: {', '.join(order)}" in text
```

- [ ] **Step 2: Run tests to verify the in-sync ones pass and confirm baseline**

Run from `bindings/python/`: `uv run pytest ../../tests/skills/test_skill_manifests.py -v`
Expected: all PASS. (`.cursor-plugin` and `.github` already list the 7 skills in registry order from the seed fix; the glob and AGENTS.md assertions match the current files.)

- [ ] **Step 3: Run the generator to take ownership of formatting**

Run from repo root: `uv run python scripts/gen_skill_manifests.py`
Then: `git --no-pager diff --stat`
Expected: `.github/plugin.json` changes — the hand-written single-line `"keywords": [...]` becomes one element per line (json.dumps indent=2). `.cursor-plugin/plugin.json` likely unchanged. The `skills` arrays are unchanged. This one-time reformat hands formatting to the generator; it is stable thereafter.

- [ ] **Step 4: Re-run tests + the check mode to verify clean**

Run from `bindings/python/`:
`uv run pytest ../../tests/skills/test_skill_manifests.py -v` → PASS
`uv run python ../../scripts/gen_skill_manifests.py --check` → exit 0 (prints nothing)
Run `git status --porcelain` → only the regenerated manifest(s) show as modified, nothing else.

- [ ] **Step 5: Commit**

```bash
git add .cursor-plugin/plugin.json .github/plugin.json tests/skills/test_skill_manifests.py
git commit -m "feat(skills): generate plugin manifests + guard them against skills.toml"
```

---

### Task 4: Derive `EXPECTED_SKILLS` from the registry (remove the hard-coded list)

**Files:**
- Modify: `tests/skills/test_skill_structure.py:15-25` (replace the hard-coded list)

- [ ] **Step 1: Add a guard test (stays meaningful after the refactor)**

Append a guard to `tests/skills/test_skill_structure.py`. It asserts the parametrised skill list covers exactly the skill directories on disk — comparing the registry-derived list to the *filesystem*, so it does NOT become a tautology after Step 3 derives `EXPECTED_SKILLS` from the registry:

```python
def test_expected_skills_cover_all_directories() -> None:
    """EXPECTED_SKILLS (from the registry) matches the skill directories on disk."""
    on_disk = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
    assert set(EXPECTED_SKILLS) == on_disk
```

- [ ] **Step 2: Run it to verify it passes**

Run from `bindings/python/`: `uv run pytest ../../tests/skills/test_skill_structure.py::test_expected_skills_cover_all_directories -v`
Expected: PASS (the hard-coded list currently equals the directories). It keeps guarding after Step 3, when `EXPECTED_SKILLS` is sourced from the registry.

- [ ] **Step 3: Replace the hard-coded list with a registry read**

In `tests/skills/test_skill_structure.py`, the current block is:

```python
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

EXPECTED_SKILLS = [
    "quickstart",
    "model-discovery",
    "model-building",
    "model-review",
    "model-reconciliation",
    "model-scenarios",
    "extending-gaspatchio",
]
```

Replace it with (add `import tomllib` to the imports at the top of the file alongside the existing `import yaml`):

```python
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

with (SKILLS_DIR / "skills.toml").open("rb") as _fh:
    EXPECTED_SKILLS = list(tomllib.load(_fh)["order"])
```

- [ ] **Step 4: Run the full structural suite to verify nothing regressed**

Run from `bindings/python/`: `uv run pytest ../../tests/skills/test_skill_structure.py -v`
Expected: all PASS (same skills, now sourced from the registry; parametrisation order follows `skills.toml`).

- [ ] **Step 5: Commit**

```bash
git add tests/skills/test_skill_structure.py
git commit -m "refactor(skills): derive EXPECTED_SKILLS from skills.toml registry"
```

---

### Task 5: L1 structural rubric — the safe subset of Anthropic's authoring rules

**Files:**
- Modify: `tests/skills/test_skill_structure.py` (add `import re`, a frontmatter helper, four parametrised tests)

These four checks pass for all current skills (verified: max SKILL.md is 496 lines; names are valid kebab-case; descriptions are short; no reference links onward to another reference).

- [ ] **Step 1: Write the failing tests**

Add `import re` to the imports. Add a frontmatter helper and the tests to `tests/skills/test_skill_structure.py`:

```python
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
REF_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def _frontmatter(skill_name: str) -> dict:
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text()
    return yaml.safe_load(content.split("---", 2)[1])


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_md_under_500_lines(skill_name: str) -> None:
    """Anthropic guidance: keep SKILL.md under 500 lines (split into references)."""
    n = len((SKILLS_DIR / skill_name / "SKILL.md").read_text().splitlines())
    assert n <= 500, f"{skill_name} SKILL.md is {n} lines (max 500)"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_name_is_valid_kebab(skill_name: str) -> None:
    name = _frontmatter(skill_name)["name"]
    assert NAME_RE.match(name), f"{skill_name}: name '{name}' is not kebab-case"
    assert len(name) <= 64, f"{skill_name}: name exceeds 64 chars"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_description_within_1024(skill_name: str) -> None:
    desc = _frontmatter(skill_name)["description"]
    assert len(desc) <= 1024, f"{skill_name}: description is {len(desc)} chars (max 1024)"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_references_one_level_deep(skill_name: str) -> None:
    """A reference file must not link onward to another reference (Anthropic:
    'keep references one level deep from SKILL.md')."""
    refs = SKILLS_DIR / skill_name / "references"
    if not refs.is_dir():
        return
    for md in refs.glob("*.md"):
        for target in REF_LINK_RE.findall(md.read_text()):
            assert "references/" not in target, (
                f"{md.relative_to(SKILLS_DIR)} links onward to a reference: {target}"
            )
```

- [ ] **Step 2: Run the new tests to verify they pass for current skills**

Run from `bindings/python/`: `uv run pytest ../../tests/skills/test_skill_structure.py -k "under_500_lines or valid_kebab or within_1024 or one_level_deep" -v`
Expected: all PASS (28 = 4 checks × 7 skills).

- [ ] **Step 3: Prove the rules actually fail on bad input (red check)**

Add a focused negative test so the rules are not vacuous:

```python
def test_name_rule_rejects_bad_names() -> None:
    assert not NAME_RE.match("Gaspatchio_Quickstart")  # caps + underscore
    assert not NAME_RE.match("my/skill")               # namespace prefix (silent-load trap)
    assert NAME_RE.match("gaspatchio-quickstart")
```

- [ ] **Step 4: Run it**

Run from `bindings/python/`: `uv run pytest ../../tests/skills/test_skill_structure.py::test_name_rule_rejects_bad_names -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/skills/test_skill_structure.py
git commit -m "feat(skills): enforce Anthropic structural rubric (size, name, description, ref depth)"
```

---

### Task 6: Wire the manifest drift guard into CI

**Files:**
- Modify: `.github/workflows/CI.yml` (the `skill-structure-tests` job)

- [ ] **Step 1: Add the check step**

In `.github/workflows/CI.yml`, the `skill-structure-tests` job currently ends with:

```yaml
      - name: Run skill structure tests
        run: uv run pytest ../../tests/skills/ -v
```

Add a step immediately after it (same job, `working-directory: bindings/python` is already set for the job):

```yaml
      - name: Check skill manifests are generated from skills.toml
        run: uv run python ../../scripts/gen_skill_manifests.py --check
```

- [ ] **Step 2: Verify the command locally (acts as CI would)**

Run from `bindings/python/`: `uv run python ../../scripts/gen_skill_manifests.py --check`
Expected: exit 0, no output (manifests already regenerated in Task 3). Confirm with `echo $?` → `0`.

- [ ] **Step 3: Verify the guard catches drift (manual red check)**

Temporarily break a manifest, confirm the check fails, then restore:

```bash
python -c "import json,pathlib; p=pathlib.Path('.github/plugin.json'); d=json.loads(p.read_text()); d['skills']=d['skills'][:-1]; p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')"
( cd bindings/python && uv run python ../../scripts/gen_skill_manifests.py --check ); echo "exit=$?"   # expect: prints out-of-date, exit=1
git checkout -- .github/plugin.json
```

Expected: the check prints the out-of-date manifest and `exit=1`; after `git checkout`, the file is restored.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/CI.yml
git commit -m "ci(skills): fail when plugin manifests drift from skills.toml"
```

---

### Task 7: Record deferred follow-ons (no code)

**Files:**
- Modify: `ref/43-skill-lifecycle/specs/2026-06-15-skill-lifecycle-design.md` (append to §11 Open questions if not already captured)

- [ ] **Step 1: Confirm the deferred items are documented**

Ensure these are listed as deferred (they are intentionally NOT implemented here because they require content remediation or live in another repo):
1. **TOC for reference files >100 lines** — ~14 files currently lack a `## Contents` heading; adding them is a content task, plan separately before turning the TOC check on.
2. **`name` ↔ directory convention** — 6/7 skills are `gaspatchio-<dir>`; `extending-gaspatchio` has `name: gaspatchio-extending`. Decide whether to normalise (rename dir or `name`) before enforcing a name↔dir rule.
3. **L2/L3/L4 (shared md-sync engine, effectiveness evals, fix/draft authoring)** — separate plan in private `gaspatchio-docs`.
4. **`REF_LINK_RE` external-URL edge case** (found in review) — `test_references_one_level_deep` matches the literal substring `references/`, so a legitimate external link like `https://actuary.org/references/x.pdf` in a reference file would false-fail. Benign today (no such links); tighten to relative-path targets only if it ever triggers.
5. **ruff per-file-ignore gap** (found in review) — the `tests/**/*.py` ignore in `bindings/python/pyproject.toml` does not match the repo-root `tests/` tree (ruff resolves the glob relative to the config dir), so `S101` etc. are not actually suppressed there. CI doesn't run ruff so this is latent; fix deliberately (repo-root config or corrected glob) rather than per-task.
6. **Root `core/AGENTS.md` "Skill Routing" table** (found in final review) — it lists 6 skills and omits `extending-gaspatchio` (which has its own prose section), and is not guarded against the registry. The remaining drift surface for the skill set. Decide whether `extending-gaspatchio` belongs in that model-task routing table, then extend an `AGENTS.md`-style guard to cover it (L2 follow-up).

- [ ] **Step 2: Commit (if edited)**

```bash
git add ref/43-skill-lifecycle/specs/2026-06-15-skill-lifecycle-design.md
git commit -m "docs(skills): note deferred L1 items (TOC, name/dir) and docs-side scope"
```

---

## Self-review

**Spec coverage (L0 + L1 only — the public core subsystem):**
- L0 single source of truth → Task 1 (`skills.toml`) + Task 3 (manifests generated/guarded) + Task 4 (`EXPECTED_SKILLS` derived) + Task 6 (CI guard). ✓
- L0 cross-tool trap (no namespace prefixes / kebab-case) → Task 5 `test_skill_name_is_valid_kebab` + `test_name_rule_rejects_bad_names`. ✓
- L1 structural rubric (≤500 lines, name, description, reference depth) → Task 5. ✓
- `claude plugin validate --strict` → **intentionally omitted** (requires the `claude` CLI in CI, not currently installed); the generator-diff guard + structural tests cover the same drift deterministically. Noted here so the omission is explicit, not a gap.
- L2/L3/L4 → out of scope (private docs), Task 7 records it.

**Placeholder scan:** none — every code/step has concrete content and commands.

**Type/name consistency:** `registry_order()`, `skill_dirs()`, `expected_skill_paths()`, `render()`, `load_order()`, `EXPECTED_SKILLS`, `NAME_RE`, `REF_LINK_RE`, `_frontmatter()` are used consistently across tasks. `render()` signature `(manifest_path: Path, order: list[str]) -> str` matches its call in Task 2's test and its use in `main()`.
