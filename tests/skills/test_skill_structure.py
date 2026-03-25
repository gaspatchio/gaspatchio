"""Tier 1: Verify skill files exist and have valid structure.

These tests are deterministic, free, and run in milliseconds.
They catch: missing files, broken frontmatter, missing sections.
"""

import pytest
import yaml
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

EXPECTED_SKILLS = [
    "quickstart",
    "model-discovery",
    "model-building",
    "model-review",
    "model-reconciliation",
    "model-scenarios",
]


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
    refs = list((SKILLS_DIR / "model-building" / "references").iterdir())
    ref_names = [r.name for r in refs]
    assert len(refs) >= 6, f"Expected 6+ reference files, got {len(refs)}: {ref_names}"


def test_model_reconciliation_has_techniques() -> None:
    """Reconciliation skill has at least 8 technique reference files."""
    refs = list((SKILLS_DIR / "model-reconciliation" / "references").iterdir())
    ref_names = [r.name for r in refs]
    assert len(refs) >= 8, f"Expected 8+ technique files, got {len(refs)}: {ref_names}"


def test_model_review_has_references() -> None:
    """Review skill has antipatterns and ASOP 56 reference files."""
    refs_dir = SKILLS_DIR / "model-review" / "references"
    assert (refs_dir / "gaspatchio-antipatterns.md").exists(), "Missing gaspatchio-antipatterns.md"
    assert (refs_dir / "asop56-checklist.md").exists(), "Missing asop56-checklist.md"
