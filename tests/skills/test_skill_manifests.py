# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Guard: skills/skills.toml is the single source of truth.

Every derived artifact (distribution manifests, AGENTS.md count/list) must
stay in sync with it.
"""

import importlib.util
import json
import tomllib
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
REGISTRY = SKILLS_DIR / "skills.toml"


def registry_order() -> list[str]:
    """Return the ordered list of skill names from the registry."""
    with REGISTRY.open("rb") as fh:
        return list(tomllib.load(fh)["order"])


def skill_dirs() -> set[str]:
    """Return the set of skill directory names that contain a SKILL.md."""
    return {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}


def test_registry_matches_directories() -> None:
    """Every skill directory is registered, and every registered skill exists."""
    assert set(registry_order()) == skill_dirs()


def test_registry_has_no_duplicates() -> None:
    """Each skill name appears exactly once in the registry order list."""
    order = registry_order()
    assert len(order) == len(set(order)), f"duplicate entries in {REGISTRY}"


def _load_generator() -> types.ModuleType:
    """Load scripts/gen_skill_manifests.py as a module."""
    path = REPO_ROOT / "scripts" / "gen_skill_manifests.py"
    spec = importlib.util.spec_from_file_location("gen_skill_manifests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_claude_plugin_generated_from_meta() -> None:
    gen = _load_generator()
    data = json.loads(gen.render_claude_plugin())
    meta = gen.load_plugin()
    assert data["name"] == meta["name"]
    assert data["license"] == "Apache-2.0"
    assert data["skills"] == "./skills/"          # glob, self-maintaining
    assert data["author"]["name"] == "Opio Inc."  # canonical, not "Gaspatchio"
    assert isinstance(data["keywords"], list)      # array, not string (hard validation rule)


def test_marketplace_self_hosts_same_repo() -> None:
    gen = _load_generator()
    mkt = json.loads(gen.render_marketplace())
    assert mkt["name"] == "gaspatchio"
    assert mkt["owner"]["name"]                    # owner has a name
    assert "url" not in mkt["owner"]               # owner takes name/email, not url (Gate 1)
    assert mkt["description"]                       # required by `claude plugin validate --strict`
    entry = mkt["plugins"][0]
    assert entry["source"] == "./"
    assert entry["name"] == "gaspatchio"
    assert entry["version"] == gen.load_plugin()["version"]


def test_claude_manifest_uses_glob() -> None:
    """The Claude Code manifest globs the directory; it must not list skills."""
    data = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["skills"] == "./skills/"


def test_agents_md_count_and_list_in_sync() -> None:
    """The AGENTS.md install count and list match the registry."""
    order = registry_order()
    text = (REPO_ROOT / "bindings" / "python" / "AGENTS.md").read_text(encoding="utf-8")
    assert f"get {len(order)} actuarial modeling skills" in text
    assert f"- **{len(order)} skills**: {', '.join(order)}" in text


def test_plugin_meta_loads() -> None:
    """The [plugin] table exposes the canonical plugin metadata."""
    gen = _load_generator()
    meta = gen.load_plugin()
    assert meta["name"] == "gaspatchio"
    assert meta["license"] == "Apache-2.0"
    assert meta["version"]  # semver string present
    assert meta["repository"].endswith("opioinc/gaspatchio-core")


def test_cursor_manifest_points_at_one_tree() -> None:
    gen = _load_generator()
    data = json.loads(gen.render_cursor_plugin())
    assert data["name"] == "gaspatchio"
    assert "skills" in data
    # no parent-traversal ../skills paths (one canonical tree, pointer-style)
    skills = data["skills"]
    assert not any(str(s).startswith("../") for s in (skills if isinstance(skills, list) else []))


def test_copilot_marketplace_generated() -> None:
    gen = _load_generator()
    mkt = json.loads(gen.render_copilot_marketplace())
    assert mkt["plugins"][0]["source"] == "./"


def test_copilot_instructions_generated() -> None:
    gen = _load_generator()
    out = gen.render_copilot_instructions()
    assert "Skill Routing" in out
    assert "gaspatchio" in out


def test_all_generated_artifacts_in_sync() -> None:
    """Every generated file on disk matches the generator output (no drift)."""
    gen = _load_generator()
    for path, renderer in gen.ARTIFACTS.items():
        assert path.read_text(encoding="utf-8") == renderer(), f"drift: {path}"


def test_license_consistent_across_manifests() -> None:
    for path in (REPO_ROOT / ".claude-plugin" / "plugin.json",
                 REPO_ROOT / ".cursor-plugin" / "plugin.json"):
        assert json.loads(path.read_text())["license"] == "Apache-2.0"


def test_agents_md_npx_slug_is_correct() -> None:
    text = (REPO_ROOT / "bindings" / "python" / "AGENTS.md").read_text(encoding="utf-8")
    assert "npx skills add opioinc/gaspatchio-core" in text
    assert "npx skills add gaspatchio/gaspatchio-core" not in text
