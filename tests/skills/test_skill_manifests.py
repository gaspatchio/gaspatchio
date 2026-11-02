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
# The plugin root is the skills tree, so the marketplace payload is skills only.
CLAUDE_PLUGIN_JSON = SKILLS_DIR / ".claude-plugin" / "plugin.json"


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
    assert data["skills"] == "./"                 # glob, self-maintaining
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
    # The payload, not the repo: "./" would ship core/, bindings/, tests/, ref/.
    assert entry["source"] == "./skills"
    assert entry["name"] == "gaspatchio"
    assert entry["version"] == gen.load_plugin()["version"]


def test_claude_manifest_uses_glob() -> None:
    """The Claude Code manifest globs the directory; it must not list skills."""
    data = json.loads(CLAUDE_PLUGIN_JSON.read_text(encoding="utf-8"))
    assert data["skills"] == "./"


def test_claude_plugin_root_is_the_skills_tree() -> None:
    """The manifest sits in skills/, so the install payload is skills only.

    A marketplace `source` is the payload: Claude Code copies that entire
    directory into ~/.claude/plugins/cache. Rooting the plugin at the repo
    shipped the Rust crate, the Python bindings, tests/ and ref/ to anyone
    installing seven markdown skills.
    """
    assert CLAUDE_PLUGIN_JSON.parent.parent == SKILLS_DIR
    assert not (REPO_ROOT / ".claude-plugin" / "plugin.json").exists()


def test_plugin_payload_carries_nothing_but_skills() -> None:
    """The payload root holds only skill dirs, the manifest, and the registry."""
    allowed = {".claude-plugin", ".codex-plugin", "skills.toml", *skill_dirs()}
    assert {p.name for p in SKILLS_DIR.iterdir()} <= allowed


def test_readme_count_and_list_in_sync() -> None:
    """The README install count and list match the registry.

    The install instructions moved out of bindings/python/AGENTS.md so that file
    plus the root AGENTS.md fit Codex's merged project-doc window; the pin moved
    with the text. The README is where someone deciding to install actually
    reads, which a file inside the plugin cache directory is not.
    """
    order = registry_order()
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"get {len(order)} actuarial modeling skills" in text
    assert f"- **{len(order)} skills**: {', '.join(order)}" in text


def test_plugin_meta_loads() -> None:
    """The [plugin] table exposes the canonical plugin metadata."""
    gen = _load_generator()
    meta = gen.load_plugin()
    assert meta["name"] == "gaspatchio"
    assert meta["license"] == "Apache-2.0"
    assert meta["version"]  # semver string present
    assert meta["repository"].endswith("gaspatchio/gaspatchio")


def test_cursor_manifest_points_at_one_tree() -> None:
    gen = _load_generator()
    data = json.loads(gen.render_cursor_plugin())
    assert data["name"] == "gaspatchio"
    assert "skills" in data
    # no parent-traversal ../skills paths (one canonical tree, pointer-style)
    skills = data["skills"]
    assert not any(str(s).startswith("../") for s in (skills if isinstance(skills, list) else []))


def test_codex_manifest_lists_every_skill_dir() -> None:
    """Codex ignores "./" at the plugin root; it loads only listed skill dirs.

    Verified with codex-cli 0.153.4: the Claude manifest's "./" installs the
    plugin but surfaces zero skills; an explicit list surfaces all of them.
    """
    gen = _load_generator()
    data = json.loads(gen.render_codex_plugin())
    assert data["skills"] == [f"./{name}" for name in registry_order()]
    for rel in data["skills"]:
        assert (SKILLS_DIR / rel / "SKILL.md").is_file()
    claude = json.loads(gen.render_claude_plugin())
    assert {k: v for k, v in data.items() if k != "skills"} == {
        k: v for k, v in claude.items() if k != "skills"
    }


def test_copilot_marketplace_generated() -> None:
    gen = _load_generator()
    mkt = json.loads(gen.render_copilot_marketplace())
    assert mkt["plugins"][0]["source"] == "./skills"


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
    for path in (CLAUDE_PLUGIN_JSON,
                 REPO_ROOT / ".cursor-plugin" / "plugin.json"):
        assert json.loads(path.read_text())["license"] == "Apache-2.0"


def test_readme_npx_slug_is_correct() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "npx skills add gaspatchio/gaspatchio" in text
    assert "npx skills add gaspatchio/gaspatchio-core" not in text


# --- PRINCIPLES.md is inlined into AGENTS.md, not merely linked ------------
# Codex does not expand `@file` imports the way CLAUDE.md does, and
# `project_doc_fallback_filenames` only fires when AGENTS.md is absent. The
# principles reach the model only if they are physically in AGENTS.md.

AGENTS_MD = REPO_ROOT / "AGENTS.md"
END_PRINCIPLES = b"<!-- END GENERATED PRINCIPLES -->"
CODEX_PROJECT_DOC_DEFAULT_CAP = 32 * 1024


def test_principles_inlined_into_agents_md() -> None:
    """Every principle heading in PRINCIPLES.md appears in the generated block."""
    principles = (REPO_ROOT / "PRINCIPLES.md").read_text(encoding="utf-8")
    agents = AGENTS_MD.read_text(encoding="utf-8")
    headings = [ln[3:].strip() for ln in principles.splitlines() if ln.startswith("## ")]
    assert headings, "PRINCIPLES.md has no '##' sections"
    for heading in headings:
        assert f"### {heading}" in agents, f"principle not inlined: {heading}"


def test_principles_survive_codex_default_truncation() -> None:
    """The principles block sits inside Codex's default 32 KB project-doc window.

    Codex truncates the merged AGENTS.md at `project_doc_max_bytes` (default
    32 KB), keeping the HEAD and dropping the tail, with no warning. Contributors
    cannot commit a larger cap -- repo-level `.codex/config.toml` is ignored -- so
    anything that must always be in context has to sit in the first 32 KB.
    """
    data = AGENTS_MD.read_bytes()
    end = data.index(END_PRINCIPLES)
    assert end < CODEX_PROJECT_DOC_DEFAULT_CAP, (
        f"principles block ends at byte {end}, past the {CODEX_PROJECT_DOC_DEFAULT_CAP} B "
        f"default cap; it would be silently dropped for anyone who has not raised "
        f"project_doc_max_bytes in ~/.codex/config.toml"
    )


# --- The budget is the chain's, not the root file's ------------------------
# Codex merges instruction files from the repository root down to the working
# directory and stops adding them once their combined size reaches
# `project_doc_max_bytes` (32 KiB by default), silently. Guarding the root file
# alone missed exactly that: on 2026-09-14 the root sat 25 B under the cap, and a
# session in core/ loaded 65,178 B against the budget while one in
# bindings/python/ loaded 62,068 B -- so the subtree's rules, the rules for the
# code in front of the agent, were dropped whole. The 2026-09-15 restructure
# fits the root file plus either subtree file inside that budget.

SUBTREE_AGENTS_MD = (
    REPO_ROOT / "core" / "AGENTS.md",
    REPO_ROOT / "bindings" / "python" / "AGENTS.md",
)
CHAIN_HEADROOM = 1024           # trim before adding, not at the cliff edge
ROOT_AGENTS_CEILING = 23_000    # 18,053 B of it is the framework half, unmovable
SUBTREE_AGENTS_CEILING = 8_700


def test_agents_md_chain_fits_codex_default_cap() -> None:
    """Root AGENTS.md plus either subtree file fits the window Codex merges.

    Nothing warns when it does not: the tail is dropped in silence, and the tail
    is whichever file came last, which is the subtree one.
    """
    budget = CODEX_PROJECT_DOC_DEFAULT_CAP - CHAIN_HEADROOM
    root = len(AGENTS_MD.read_bytes())
    for path in SUBTREE_AGENTS_MD:
        subtree = len(path.read_bytes())
        chain = root + subtree
        assert chain <= budget, (
            f"AGENTS.md ({root} B) + {path.relative_to(REPO_ROOT)} ({subtree} B) = "
            f"{chain} B, over the {budget} B working budget by {chain - budget} B. "
            f"A Codex session in that directory loses the tail of the pair with no "
            f"warning. Move text to a file the instruction file points at by path."
        )


def test_each_agents_md_is_under_its_own_ceiling() -> None:
    """Each file stays under its share, so one growing cannot starve the other."""
    assert ROOT_AGENTS_CEILING + SUBTREE_AGENTS_CEILING <= (
        CODEX_PROJECT_DOC_DEFAULT_CAP - CHAIN_HEADROOM
    ), "the per-file ceilings no longer add up to a chain that fits the budget"
    root = len(AGENTS_MD.read_bytes())
    assert root <= ROOT_AGENTS_CEILING, (
        f"AGENTS.md is {root} B, over its {ROOT_AGENTS_CEILING} B ceiling by "
        f"{root - ROOT_AGENTS_CEILING} B; it keeps the framework knowledge, and "
        f"contributor rules belong in CONTRIBUTING.md"
    )
    for path in SUBTREE_AGENTS_MD:
        size = len(path.read_bytes())
        assert size <= SUBTREE_AGENTS_CEILING, (
            f"{path.relative_to(REPO_ROOT)} is {size} B, over its "
            f"{SUBTREE_AGENTS_CEILING} B ceiling by {size - SUBTREE_AGENTS_CEILING} B; "
            f"general practice belongs in that subtree's docs/ directory"
        )
