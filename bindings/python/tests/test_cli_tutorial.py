# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for gspio tutorial list/init/verify.
# ABOUTME: Covers sequential levels and the patterns/ collections (gh#94).
"""Tests for the gspio tutorial subcommands."""

from pathlib import Path

from typer.testing import CliRunner

from gaspatchio.tutorial_cli import tutorial_app

runner = CliRunner()


class TestTutorialList:
    """Tests for `gspio tutorial list`."""

    def test_list_shows_levels(self):
        """The five sequential levels are listed."""
        result = runner.invoke(tutorial_app, ["list"])
        assert result.exit_code == 0
        assert "level-1" in result.output
        assert "level-5" in result.output

    def test_list_shows_rollforward_patterns(self):
        """The patterns collections are listed, not just the levels (gh#94)."""
        result = runner.invoke(tutorial_app, ["list"])
        assert result.exit_code == 0
        assert "rollforward" in result.output


class TestTutorialInit:
    """Tests for `gspio tutorial init`."""

    def test_init_level_copies_base(self, tmp_path: Path):
        """A level init copies the level's base/ contents."""
        dest = tmp_path / "level-one"
        result = runner.invoke(tutorial_app, ["init", "level-1", "--dest", str(dest)])
        assert result.exit_code == 0
        assert (dest / "model.py").exists()

    def test_init_pattern_by_bare_name(self, tmp_path: Path):
        """A pattern init resolves the bare collection name (gh#94)."""
        dest = tmp_path / "rf-patterns"
        result = runner.invoke(
            tutorial_app, ["init", "rollforward-patterns", "--dest", str(dest)]
        )
        assert result.exit_code == 0
        assert (dest / "01_single_state_fund.py").exists()
        assert (dest / "02_multistate_ratchet.py").exists()
        assert (dest / "03_lapse_stop.py").exists()
        assert (dest / "README.md").exists()

    def test_init_pattern_by_full_path(self, tmp_path: Path):
        """A pattern init also resolves the patterns/-prefixed name (gh#94)."""
        dest = tmp_path / "rf-patterns-full"
        result = runner.invoke(
            tutorial_app,
            ["init", "patterns/rollforward-patterns", "--dest", str(dest)],
        )
        assert result.exit_code == 0
        assert (dest / "01_single_state_fund.py").exists()

    def test_unknown_name_error_names_patterns(self):
        """The unknown-name error lists patterns among the available targets."""
        result = runner.invoke(tutorial_app, ["init", "no-such-tutorial"])
        assert result.exit_code != 0
        assert "rollforward-patterns" in result.output


class TestTutorialVerify:
    """Tests for `gspio tutorial verify`."""

    def test_verify_pattern_runs_all_scripts(self):
        """Verifying a pattern collection runs its numbered scripts (gh#94).

        The scripts assert internally against closed-form expectations, so a
        clean exit is a real verification, not just a smoke run.
        """
        result = runner.invoke(tutorial_app, ["verify", "rollforward-patterns"])
        assert result.exit_code == 0
        assert "PASS" in result.output
