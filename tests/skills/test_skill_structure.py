# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tier 1: Verify skill files exist and have valid structure.

These tests are deterministic, free, and run in milliseconds.
They catch: missing files, broken frontmatter, missing sections.
"""

import re
import tomllib
from pathlib import Path

import pytest
import yaml

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

with (SKILLS_DIR / "skills.toml").open("rb") as _fh:
    EXPECTED_SKILLS = list(tomllib.load(_fh)["order"])


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_exists(skill_name: str) -> None:
    """Every expected skill has a SKILL.md file."""
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_path.exists(), f"Missing: {skill_path}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_has_valid_frontmatter(skill_name: str) -> None:
    """Every skill has YAML frontmatter with name and description."""
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text()
    assert content.startswith("---"), f"{skill_name} missing YAML frontmatter"

    parts = content.split("---", 2)
    assert len(parts) >= 3, f"{skill_name} frontmatter not properly closed"

    fm = yaml.safe_load(parts[1])
    assert "name" in fm, f"{skill_name} missing 'name' in frontmatter"
    assert "description" in fm, f"{skill_name} missing 'description' in frontmatter"
    assert fm["description"].startswith("Use when"), (
        f"{skill_name} description should start with 'Use when' for discoverability"
    )


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_mentions_standalone(skill_name: str) -> None:
    """Every skill documents that it can be used independently."""
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text().lower()
    assert "standalone" in content or "independent" in content, (
        f"{skill_name} must mention standalone/independent invocation"
    )


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_has_completion_gate(skill_name: str) -> None:
    """Every skill has a completion gate or hard gate."""
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text().lower()
    assert "gate" in content or "checklist" in content or "completion" in content, (
        f"{skill_name} must have a completion gate"
    )


def test_model_building_has_references() -> None:
    """Building skill has at least 6 reference files."""
    refs = list((SKILLS_DIR / "gaspatchio-model-building" / "references").iterdir())
    ref_names = [r.name for r in refs]
    assert len(refs) >= 6, f"Expected 6+ reference files, got {len(refs)}: {ref_names}"


def test_model_reconciliation_has_techniques() -> None:
    """Reconciliation skill has at least 8 technique reference files."""
    refs = list((SKILLS_DIR / "gaspatchio-model-reconciliation" / "references").iterdir())
    ref_names = [r.name for r in refs]
    assert len(refs) >= 8, f"Expected 8+ technique files, got {len(refs)}: {ref_names}"


def test_model_review_has_references() -> None:
    """Review skill has antipatterns and ASOP 56 reference files."""
    refs_dir = SKILLS_DIR / "gaspatchio-model-review" / "references"
    assert (refs_dir / "gaspatchio-antipatterns.md").exists(), "Missing gaspatchio-antipatterns.md"
    assert (refs_dir / "asop56-checklist.md").exists(), "Missing asop56-checklist.md"


def test_extending_has_references() -> None:
    """Extending skill has accessor template, performance ladder, and anti-patterns."""
    refs_dir = SKILLS_DIR / "gaspatchio-extending" / "references"
    assert (refs_dir / "accessor-template.md").exists(), "Missing accessor-template.md"
    assert (refs_dir / "performance-ladder.md").exists(), "Missing performance-ladder.md"
    assert (refs_dir / "anti-patterns.md").exists(), "Missing anti-patterns.md"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_has_integration_section(skill_name: str) -> None:
    """Every skill has an Integration section mapping the workflow DAG."""
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text()
    assert "## Integration" in content, (
        f"{skill_name} must have an '## Integration' section mapping "
        f"called-by, required-next, and routes-to relationships"
    )


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_has_red_flags(skill_name: str) -> None:
    """Every skill has a Red Flags or anti-rationalization table."""
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text().lower()
    assert "red flag" in content or "anti-rational" in content or "distrust" in content, (
        f"{skill_name} must have a Red Flags, Anti-rationalization, "
        f"or Distrust-Based section to prevent skill skipping"
    )


# --- Skill routing DAG tests ---
# These verify the workflow connections between skills are documented.

def test_building_routes_to_reconciliation() -> None:
    """model-building must route to model-reconciliation as REQUIRED."""
    content = (SKILLS_DIR / "gaspatchio-model-building" / "SKILL.md").read_text()
    assert "model-reconciliation" in content
    assert "REQUIRED" in content


def test_building_routes_to_review() -> None:
    """model-building must route to model-review as REQUIRED."""
    content = (SKILLS_DIR / "gaspatchio-model-building" / "SKILL.md").read_text()
    assert "model-review" in content
    assert "REQUIRED" in content


def test_building_routes_to_scenarios() -> None:
    """model-building must route to model-scenarios as REQUIRED."""
    content = (SKILLS_DIR / "gaspatchio-model-building" / "SKILL.md").read_text()
    assert "model-scenarios" in content


def test_discovery_routes_to_building() -> None:
    """model-discovery must route to model-building after spec approval."""
    content = (SKILLS_DIR / "gaspatchio-model-discovery" / "SKILL.md").read_text()
    assert "model-building" in content


def test_discovery_mentions_excel_porting() -> None:
    """model-discovery must explicitly mention Excel porting as a trigger."""
    content = (SKILLS_DIR / "gaspatchio-model-discovery" / "SKILL.md").read_text().lower()
    assert "excel" in content, "model-discovery must mention Excel porting"


def test_quickstart_routes_to_discovery() -> None:
    """quickstart must route to model-discovery for new models."""
    content = (SKILLS_DIR / "gaspatchio-quickstart" / "SKILL.md").read_text()
    assert "model-discovery" in content


def test_review_routes_to_extending() -> None:
    """model-review must route to extending when anti-patterns are found."""
    content = (SKILLS_DIR / "gaspatchio-model-review" / "SKILL.md").read_text()
    assert "extending" in content


def test_output_file_flag_consistency() -> None:
    """Skills referencing --output-file must use it with gspio commands."""
    for skill_name in EXPECTED_SKILLS:
        content = (SKILLS_DIR / skill_name / "SKILL.md").read_text()
        if "--output-file" in content:
            # If a skill references --output-file, it must be with a gspio command
            assert "gspio" in content, (
                f"{skill_name} references --output-file but not a gspio command"
            )


def test_expected_skills_cover_all_directories() -> None:
    """EXPECTED_SKILLS (from the registry) matches the skill directories on disk."""
    on_disk = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
    assert set(EXPECTED_SKILLS) == on_disk, (
        f"registry-only={set(EXPECTED_SKILLS) - on_disk} "
        f"disk-only={on_disk - set(EXPECTED_SKILLS)}"
    )


# --- Anthropic structural rubric (L1 safe subset) ---

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
REF_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def _frontmatter(skill_name: str) -> dict:
    """Parse and return the YAML frontmatter of a skill's SKILL.md."""
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text()
    return yaml.safe_load(content.split("---", 2)[1])


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_frontmatter_name_matches_dir(skill_name: str) -> None:
    """Open Agent Skills spec: frontmatter name must equal the parent directory."""
    assert _frontmatter(skill_name)["name"] == skill_name


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_md_under_600_lines(skill_name: str) -> None:
    """Anthropic guidance: keep SKILL.md under 600 lines (split into references)."""
    n = len((SKILLS_DIR / skill_name / "SKILL.md").read_text().splitlines())
    assert n <= 600, f"{skill_name} SKILL.md is {n} lines (max 600)"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_name_is_valid_kebab(skill_name: str) -> None:
    """The frontmatter name is lowercase kebab-case and <= 64 chars."""
    name = _frontmatter(skill_name)["name"]
    assert NAME_RE.match(name), f"{skill_name}: name '{name}' is not kebab-case"
    assert len(name) <= 64, f"{skill_name}: name exceeds 64 chars"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_description_within_1024(skill_name: str) -> None:
    """The frontmatter description is within Anthropic's 1024-char limit."""
    desc = _frontmatter(skill_name)["description"]
    assert len(desc) <= 1024, f"{skill_name}: description is {len(desc)} chars (max 1024)"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_references_one_level_deep(skill_name: str) -> None:
    """A reference file must not link onward to another reference (one level deep)."""
    refs = SKILLS_DIR / skill_name / "references"
    if not refs.is_dir():
        return
    for md in refs.glob("*.md"):
        for target in REF_LINK_RE.findall(md.read_text()):
            assert "references/" not in target, (
                f"{md.relative_to(SKILLS_DIR)} links onward to a reference: {target}"
            )


def test_name_rule_rejects_bad_names() -> None:
    """The kebab-case rule rejects caps/underscores and namespace prefixes."""
    assert not NAME_RE.match("Gaspatchio_Quickstart")
    assert not NAME_RE.match("my/skill")
    assert NAME_RE.match("gaspatchio-quickstart")
