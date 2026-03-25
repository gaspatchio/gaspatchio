"""Tier 1: Verify test fixtures contain expected anti-patterns.

These tests ensure the model_with_antipatterns.py fixture actually contains
the anti-patterns the model-review skill should catch. If someone accidentally
"fixes" the fixture, these tests will fail.
"""

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_antipattern_fixture_exists() -> None:
    """The anti-pattern fixture file exists."""
    assert (FIXTURES_DIR / "model_with_antipatterns.py").exists()


def test_antipattern_has_map_elements() -> None:
    """Fixture contains map_elements (Critical anti-pattern)."""
    content = (FIXTURES_DIR / "model_with_antipatterns.py").read_text()
    assert "map_elements" in content


def test_antipattern_has_for_loop() -> None:
    """Fixture contains a for-loop over rows (Critical anti-pattern)."""
    content = (FIXTURES_DIR / "model_with_antipatterns.py").read_text()
    assert "iter_rows" in content or "for row in" in content


def test_antipattern_has_inline_polars() -> None:
    """Fixture contains inline Polars filtering (Important anti-pattern)."""
    content = (FIXTURES_DIR / "model_with_antipatterns.py").read_text()
    assert "df.filter" in content or ".filter(pl.col" in content


def test_antipattern_has_hardcoded_values() -> None:
    """Fixture contains hardcoded magic numbers (Important anti-pattern)."""
    content = (FIXTURES_DIR / "model_with_antipatterns.py").read_text()
    assert "ANTI-PATTERN: hardcoded" in content


def test_antipattern_has_all_markers() -> None:
    """Fixture has markers for all major anti-patterns."""
    content = (FIXTURES_DIR / "model_with_antipatterns.py").read_text()
    expected_markers = [
        "ANTI-PATTERN: map_elements",
        "ANTI-PATTERN: for-loop",
        "ANTI-PATTERN: hardcoded",
        "ANTI-PATTERN: inline-polars",
        "ANTI-PATTERN: scalar-list confusion",
    ]
    for marker in expected_markers:
        assert marker in content, f"Missing marker: {marker}"


def test_clean_model_exists() -> None:
    """L4 base model should exist as the clean reference."""
    clean = Path(__file__).resolve().parent.parent.parent / "tutorial" / "level-4-lifelib" / "base" / "model.py"
    assert clean.exists(), f"Clean model not found: {clean}"
