# ruff: noqa: S101, ANN201, D102, S607
"""Tests for the gspio tutorial CLI commands."""

import subprocess
from pathlib import Path

TUTORIALS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "bindings"
    / "python"
    / "gaspatchio_core"
    / "tutorials"
)


def run_gspio(*args: str) -> subprocess.CompletedProcess[str]:
    """Run gspio command and return result."""
    return subprocess.run(  # noqa: S603
        ["uv", "run", "gspio", *args],
        capture_output=True,
        text=True,
        cwd=TUTORIALS_DIR.parent.parent,  # bindings/python/
        check=False,
    )


class TestTutorialList:
    """Tests for gspio tutorial list."""

    def test_list_shows_all_levels(self):
        result = run_gspio("tutorial", "list")
        assert result.returncode == 0
        for level in range(1, 6):
            assert f"level-{level}" in result.stdout

    def test_list_shows_descriptions(self):
        result = run_gspio("tutorial", "list")
        assert result.returncode == 0
        assert "Hello World" in result.stdout


class TestTutorialInit:
    """Tests for gspio tutorial init."""

    def test_init_copies_model_file(self, tmp_path: Path):
        dest = str(tmp_path / "test-model")
        result = run_gspio("tutorial", "init", "level-1", "--dest", dest)
        assert result.returncode == 0
        assert (tmp_path / "test-model" / "model.py").exists()

    def test_init_copies_expected_output(self, tmp_path: Path):
        dest = str(tmp_path / "test-model")
        run_gspio("tutorial", "init", "level-1", "--dest", dest)
        assert (tmp_path / "test-model" / "expected_output.txt").exists()

    def test_init_refuses_overwrite(self, tmp_path: Path):
        dest = tmp_path / "test-model"
        dest.mkdir()
        (dest / "model.py").write_text("existing")
        result = run_gspio("tutorial", "init", "level-1", "--dest", str(dest))
        assert result.returncode != 0
        assert "already exists" in result.stderr or "already exists" in result.stdout

    def test_init_accepts_short_name(self, tmp_path: Path):
        dest = str(tmp_path / "test-model")
        result = run_gspio("tutorial", "init", "1", "--dest", dest)
        assert result.returncode == 0
        assert (tmp_path / "test-model" / "model.py").exists()

    def test_init_rejects_unknown_level(self, tmp_path: Path):
        dest = str(tmp_path / "test-model")
        result = run_gspio("tutorial", "init", "level-99", "--dest", dest)
        assert result.returncode != 0


class TestTutorialVerify:
    """Tests for gspio tutorial verify."""

    def test_verify_level_1_passes(self):
        result = run_gspio("tutorial", "verify", "level-1")
        assert result.returncode == 0

    def test_verify_rejects_unknown_level(self):
        result = run_gspio("tutorial", "verify", "level-99")
        assert result.returncode != 0
